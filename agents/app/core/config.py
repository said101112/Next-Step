import asyncio
import json
import logging
import re
import time
from concurrent.futures import ThreadPoolExecutor
from concurrent.futures import TimeoutError as FuturesTimeoutError
from functools import lru_cache
from pathlib import Path
from typing import Optional, List, Dict

import dotenv
from langchain_core.runnables import Runnable
from pydantic_settings import BaseSettings, SettingsConfigDict

logger = logging.getLogger(__name__)

def find_env_file() -> str:
    """Recherche dynamiquement le fichier .env dans les dossiers parents."""
    current = Path(__file__).resolve().parent
    for _ in range(6):
        env_path = current / ".env"
        if env_path.exists():
            return str(env_path)
        agents_env = current / "agents" / ".env"
        if agents_env.exists():
            return str(agents_env)
        current = current.parent
    return str(Path.cwd() / ".env")

# Charge le fichier .env
dotenv.load_dotenv(find_env_file())

# Modèles par défaut pour Groq
GROQ_DEFAULTS = {
    "offer_analyzer": "openai/gpt-oss-120b",
    "cv_optimizer": "openai/gpt-oss-120b",
    "company": "openai/gpt-oss-120b",
    "resume": "openai/gpt-oss-120b",
    "email": "openai/gpt-oss-120b",
    "default": "openai/gpt-oss-20b",
}

_PROVIDER_COOLDOWNS: Dict[str, float] = {}

class Settings(BaseSettings):
    """Configuration de l'application via variables d'environnement."""

    # --- Infrastructure & Database ---
    # Set by docker-compose from .env; no credentials in code.
    DATABASE_URL: str = "postgresql+asyncpg://postgres@localhost:5432/nextstep_db"
    DOTNET_BACKEND_URL: str = "http://localhost:5000"

    # --- LLM Core Settings ---
    LLM_PROVIDER_PRIORITY: str = "groq,openai,gemini"
    LLM_PRIORITY_CV_OPTIMIZER: str = "groq,openai,gemini"
    LLM_TEMPERATURE: float = 0.1
    # Reasoning models (Groq gpt-oss) spend part of this budget thinking before answering:
    # 2000 was too small and truncated long JSON answers (e.g. a full CV).
    LLM_MAX_TOKENS: int = 8192
    LLM_REQUEST_TIMEOUT: float = 90.0
    # Caps one provider attempt inside the multi-provider fallback loop. Some SDKs retry
    # rate-limit errors internally for much longer than they admit (Gemini's client, for
    # example, can spend a minute retrying a quota error that request-level timeouts and
    # max_retries=0 don't stop). This timeout forces the fallback loop to move to the next
    # provider — or fail fast — instead of waiting on a provider that is already struggling.
    LLM_PROVIDER_ATTEMPT_TIMEOUT: float = 20.0

    # --- Groq Configuration ---
    GROQ_API_KEY: str = ""
    GROQ_MODEL: str = "openai/gpt-oss-20b"
    GROQ_MODEL_PRECISE: str = "openai/gpt-oss-120b"
    # Agent Overrides
    GROQ_MODEL_OFFER_ANALYZER: str = ""
    GROQ_MODEL_CV_OPTIMIZER: str = ""
    GROQ_MODEL_COMPANY: str = ""

    # --- Gemini / Google Configuration ---
    GEMINI_API_KEY: str = ""
    GOOGLE_API_KEY: str = ""  # Fallback
    GEMINI_MODEL: str = "gemini-flash-latest"  # alias: survives model retirements
    # Agent Overrides
    GEMINI_MODEL_CV_OPTIMIZER: str = ""

    # --- OpenAI Configuration ---
    OPENAI_API_KEY: str = ""
    OPENAI_MODEL: str = "gpt-4o-mini"
    # Agent Overrides
    OPENAI_MODEL_CV_OPTIMIZER: str = ""

    # --- External APIs ---
    TAVILY_API_KEY: str = ""

    # --- Security ---
    # Shared secret required on every request (sent by the backend). Empty = all requests rejected.
    AGENTS_API_KEY: str = ""

    model_config = SettingsConfigDict(
        env_file=find_env_file(),
        env_file_encoding="utf-8",
        extra="ignore"
    )

    @property
    def effective_gemini_api_key(self) -> str:
        return self.GEMINI_API_KEY or self.GOOGLE_API_KEY

@lru_cache()
def get_settings() -> Settings:
    return Settings()

settings = get_settings()

# --- Resolution Helpers ---

def _resolve_model(provider: str, agent_name: Optional[str] = None) -> str:
    """Résout le modèle à utiliser selon le provider et l'agent."""
    if provider == "groq":
        if agent_name == "precise":
            return settings.GROQ_MODEL_PRECISE
        if agent_name:
            overrides = {
                "offer_analyzer": settings.GROQ_MODEL_OFFER_ANALYZER,
                "cv_optimizer": settings.GROQ_MODEL_CV_OPTIMIZER,
                "company": settings.GROQ_MODEL_COMPANY,
            }
            if val := overrides.get(agent_name): return val
            if val := GROQ_DEFAULTS.get(agent_name): return val
        return settings.GROQ_MODEL

    elif provider == "gemini":
        if agent_name == "cv_optimizer" and settings.GEMINI_MODEL_CV_OPTIMIZER:
            return settings.GEMINI_MODEL_CV_OPTIMIZER
        return settings.GEMINI_MODEL

    elif provider == "openai":
        if agent_name == "cv_optimizer" and settings.OPENAI_MODEL_CV_OPTIMIZER:
            return settings.OPENAI_MODEL_CV_OPTIMIZER
        return settings.OPENAI_MODEL

    return ""

def _create_provider_llm(
    provider: str,
    agent_name: Optional[str] = None,
    temperature: Optional[float] = None,
    bound_kwargs: Optional[dict] = None,
    structured_output=None,
    structured_method: Optional[str] = None,
):
    """Crée une instance LLM pour un provider donné."""
    temp = temperature if temperature is not None else settings.LLM_TEMPERATURE
    model = _resolve_model(provider, agent_name)

    try:
        # Some providers do not support OpenAI-style `response_format` in bind kwargs.
        # We sanitize per provider to avoid runtime failures like:
        # generate_content() got an unexpected keyword argument 'response_format'
        effective_bound_kwargs = dict(bound_kwargs or {})
        if provider == "gemini" and "response_format" in effective_bound_kwargs:
            logger.info("[LLM] gemini: dropping unsupported bind kwarg 'response_format'")
            effective_bound_kwargs.pop("response_format", None)

        # Each client has its own internal retry-with-backoff loop on failure (Gemini alone
        # retries up to 6 times with a growing delay). That fights our own fallback loop below,
        # which already retries across providers with cooldown tracking: on a quota or rate-limit
        # error, a client should fail immediately so we move to the next provider right away,
        # not spend up to a minute retrying a provider whose quota is already exhausted.
        if provider == "groq":
            if not settings.GROQ_API_KEY: return None
            from langchain_groq import ChatGroq
            llm = ChatGroq(
                model=model,
                api_key=settings.GROQ_API_KEY,
                temperature=temp,
                max_tokens=settings.LLM_MAX_TOKENS,
                timeout=settings.LLM_REQUEST_TIMEOUT,
                max_retries=0,
                # gpt-oss models reason before answering; keep it short so the answer fits and returns fast.
                model_kwargs={"reasoning_effort": "low"} if model.startswith("openai/gpt-oss") else {},
            )

        elif provider == "gemini":
            api_key = settings.effective_gemini_api_key
            if not api_key: return None
            from langchain_google_genai import ChatGoogleGenerativeAI
            llm = ChatGoogleGenerativeAI(
                model=model,
                google_api_key=api_key,
                temperature=temp,
                timeout=settings.LLM_REQUEST_TIMEOUT,
                max_retries=0,
            )

        elif provider == "openai":
            if not settings.OPENAI_API_KEY: return None
            from langchain_openai import ChatOpenAI
            llm = ChatOpenAI(
                model=model,
                api_key=settings.OPENAI_API_KEY,
                temperature=temp,
                timeout=settings.LLM_REQUEST_TIMEOUT,
                max_retries=0,
            )
        else:
            return None

        # Post-processing (structured output, binding)
        if structured_output:
            try:
                # The method (e.g. "json_mode") only applies to Groq: tool calling is less
                # reliable with its reasoning models. Other providers keep their default.
                if provider == "groq" and structured_method:
                    llm = llm.with_structured_output(structured_output, method=structured_method)
                else:
                    llm = llm.with_structured_output(structured_output)
            except Exception:
                logger.warning(f"{provider} ne supporte pas structured_output")
                return None

        if effective_bound_kwargs:
            llm = llm.bind(**effective_bound_kwargs)

        return llm

    except Exception as e:
        logger.warning(f"Echec init {provider}: {e}")
        return None

# ── Client reuse ────────────────────────────────────────────────────────────
# Building a chat model opens a new HTTP client: each (provider, model, settings) is
# built once and reused. Async clients cannot be shared between event loops, so the
# running loop is part of the key (one loop in the service; tests/scripts create more).
_MAX_CACHED_CLIENTS = 64
_LLM_CLIENTS: Dict[tuple, Runnable] = {}


def _cache_key(
    provider: str,
    agent_name: Optional[str],
    temperature: Optional[float],
    bound_kwargs: Optional[dict],
    structured_output,
    structured_method: Optional[str],
    loop: Optional[asyncio.AbstractEventLoop],
) -> tuple:
    try:
        hash(structured_output)
        schema_key = structured_output  # Pydantic model classes, None
    except TypeError:  # dict schemas are not hashable
        schema_key = json.dumps(structured_output, sort_keys=True, default=str)
    return (
        provider,
        _resolve_model(provider, agent_name),
        temperature if temperature is not None else settings.LLM_TEMPERATURE,
        json.dumps(bound_kwargs or {}, sort_keys=True, default=str),
        schema_key,
        structured_method,
        id(loop) if loop else None,
    )


def _get_provider_llm(
    provider: str,
    agent_name: Optional[str],
    temperature: Optional[float],
    bound_kwargs: Optional[dict],
    structured_output,
    structured_method: Optional[str],
    loop: Optional[asyncio.AbstractEventLoop] = None,
):
    """The chat model for these settings, built on first use and then reused.
    None when the provider is not configured (not cached: a key may be added later)."""
    key = _cache_key(provider, agent_name, temperature, bound_kwargs, structured_output, structured_method, loop)
    llm = _LLM_CLIENTS.get(key)
    if llm is None:
        llm = _create_provider_llm(provider, agent_name, temperature, bound_kwargs, structured_output, structured_method)
        if llm is not None:
            if len(_LLM_CLIENTS) >= _MAX_CACHED_CLIENTS:
                _LLM_CLIENTS.clear()
            _LLM_CLIENTS[key] = llm
    return llm


def _cooldown_key(provider: str, agent_name: Optional[str]) -> str:
    return f"{provider}:{agent_name or 'default'}"

def _extract_retry_seconds(message: str) -> int:
    patterns = [
        r"retry in ([0-9]+(?:\.[0-9]+)?)s",
        r"Please retry in ([0-9]+(?:\.[0-9]+)?)s",
        r"seconds:\s*([0-9]+)",
    ]
    for pattern in patterns:
        match = re.search(pattern, message, re.IGNORECASE)
        if match:
            try:
                return max(5, int(float(match.group(1))))
            except Exception:
                continue
    return 60

def _is_rate_limit_error(error: Exception) -> bool:
    message = str(error).lower()
    return (
        "429" in message
        or "quota exceeded" in message
        or "rate limit" in message
        or "too many requests" in message
    )

def _mark_provider_cooldown(provider: str, agent_name: Optional[str], error: Exception) -> None:
    seconds = _extract_retry_seconds(str(error))
    until = time.time() + seconds
    _PROVIDER_COOLDOWNS[_cooldown_key(provider, agent_name)] = until
    logger.warning(
        "[LLM] cooldown %s -> %s for %ss after rate limit",
        provider,
        agent_name or "default",
        seconds,
    )

# Cooldown applied when a provider is cut off by LLM_PROVIDER_ATTEMPT_TIMEOUT: it may still be
# retrying internally past our own timeout, so it is left alone for a while either way.
_STUCK_PROVIDER_COOLDOWN_SECONDS = 60

def _on_provider_stuck(provider: str, agent_name: Optional[str]) -> None:
    until = time.time() + _STUCK_PROVIDER_COOLDOWN_SECONDS
    _PROVIDER_COOLDOWNS[_cooldown_key(provider, agent_name)] = until
    logger.warning(
        "[LLM] %s -> %s exceeded %ss without answering (its SDK may be retrying a rate-limit "
        "or quota error internally); moving to the next provider and pausing it for %ss.",
        provider,
        agent_name or "default",
        settings.LLM_PROVIDER_ATTEMPT_TIMEOUT,
        _STUCK_PROVIDER_COOLDOWN_SECONDS,
    )

def _provider_on_cooldown(provider: str, agent_name: Optional[str]) -> bool:
    key = _cooldown_key(provider, agent_name)
    until = _PROVIDER_COOLDOWNS.get(key)
    if not until:
        return False
    if until <= time.time():
        _PROVIDER_COOLDOWNS.pop(key, None)
        return False
    remaining = int(until - time.time())
    logger.info(
        "[LLM] skip %s -> %s, provider cooling down for %ss",
        provider,
        agent_name or "default",
        remaining,
    )
    return True

# Backs the sync invoke() path's attempt timeout (see its comment). Not a context manager
# and never shut down: a timed-out call is simply abandoned, not waited on or cancelled.
_SYNC_INVOKE_POOL = ThreadPoolExecutor(max_workers=4, thread_name_prefix="llm-sync-invoke")

class _LLMProvider(Runnable):
    """Wrapper Runnable avec fallback automatique multi-provider."""

    def __init__(
        self,
        agent_name: Optional[str] = None,
        temperature: Optional[float] = None,
        bound_kwargs: Optional[dict] = None,
        structured_output=None,
        structured_method: Optional[str] = None,
    ):
        super().__init__()
        self._agent_name = agent_name
        self._temperature = temperature
        self._bound_kwargs = bound_kwargs or {}
        self._structured_output = structured_output
        self._structured_method = structured_method

    def bind(self, **kwargs):
        return _LLMProvider(
            agent_name=self._agent_name,
            temperature=self._temperature,
            bound_kwargs={**self._bound_kwargs, **kwargs},
            structured_output=self._structured_output,
            structured_method=self._structured_method,
        )

    def with_structured_output(self, schema, method: Optional[str] = None, **kwargs):
        return _LLMProvider(
            agent_name=self._agent_name,
            temperature=self._temperature,
            bound_kwargs=self._bound_kwargs,
            structured_output=schema,
            structured_method=method,
        )

    def _get_providers(self) -> List[str]:
        """Détermine la liste des providers à essayer pour cet agent."""
        if self._agent_name == "cv_optimizer" and settings.LLM_PRIORITY_CV_OPTIMIZER:
            return [p.strip() for p in settings.LLM_PRIORITY_CV_OPTIMIZER.split(",") if p.strip()]

        return [p.strip() for p in settings.LLM_PROVIDER_PRIORITY.split(",") if p.strip()]

    def invoke(self, input, config=None, **kwargs):
        last_error = None
        for provider in self._get_providers():
            if _provider_on_cooldown(provider, self._agent_name):
                continue
            llm = _get_provider_llm(
                provider, self._agent_name, self._temperature,
                self._bound_kwargs, self._structured_output, self._structured_method
            )
            if not llm: continue
            try:
                logger.info(f"[LLM] {provider} -> {self._agent_name or 'default'}")
                # Not a context manager: on timeout we abandon the future below and move on
                # immediately. A `with` block would wait for the stuck call to finish first
                # (ThreadPoolExecutor.shutdown(wait=True) on exit), defeating the timeout.
                future = _SYNC_INVOKE_POOL.submit(llm.invoke, input, config=config, **kwargs)
                return future.result(timeout=settings.LLM_PROVIDER_ATTEMPT_TIMEOUT)
            except FuturesTimeoutError as e:
                _on_provider_stuck(provider, self._agent_name)
                last_error = e
            except Exception as e:
                if _is_rate_limit_error(e):
                    _mark_provider_cooldown(provider, self._agent_name, e)
                logger.warning(f"{provider} failed: {e}")
                last_error = e
        raise last_error or RuntimeError("Aucun provider LLM disponible")

    async def ainvoke(self, input, config=None, **kwargs):
        last_error = None
        for provider in self._get_providers():
            if _provider_on_cooldown(provider, self._agent_name):
                continue
            llm = _get_provider_llm(
                provider, self._agent_name, self._temperature,
                self._bound_kwargs, self._structured_output, self._structured_method,
                loop=asyncio.get_running_loop(),
            )
            if not llm: continue
            try:
                logger.info(f"[LLM] {provider} -> {self._agent_name or 'default'}")
                # asyncio.wait_for is not an abandon: when the budget expires it cancels the
                # call and then *waits for the cancellation to land*. A provider SDK retrying a
                # rate-limit error internally catches that cancellation and keeps going, so
                # wait_for returns only when the stuck call finally stops: the caller waited
                # seconds for a deadline of 0.05s, which is the delay this loop exists to
                # avoid. asyncio.wait returns at the deadline whether the task is done or not,
                # so the provider is cancelled and left behind instead of waited on. The sync
                # path above already abandons its future the same way.
                task = asyncio.ensure_future(llm.ainvoke(input, config=config, **kwargs))
                done, _ = await asyncio.wait({task}, timeout=settings.LLM_PROVIDER_ATTEMPT_TIMEOUT)

                if not done:
                    task.cancel()
                    # Nothing awaits this task again, so its result is dropped. An eventual
                    # exception is still retrieved, otherwise Python reports it as a task
                    # exception that was never consumed.
                    task.add_done_callback(lambda abandoned: abandoned.cancelled() or abandoned.exception())
                    _on_provider_stuck(provider, self._agent_name)
                    last_error = asyncio.TimeoutError()
                    continue

                return task.result()
            except Exception as e:
                if _is_rate_limit_error(e):
                    _mark_provider_cooldown(provider, self._agent_name, e)
                logger.warning(f"{provider} failed: {e}")
                last_error = e
        raise last_error or RuntimeError("Aucun provider LLM disponible")

def get_llm(temperature: Optional[float] = None, agent_name: Optional[str] = None):
    """Factory: retourne un wrapper avec fallback multi-provider."""
    return _LLMProvider(agent_name=agent_name, temperature=temperature)

def get_llm_precise():
    """Modèle précis (GROQ_MODEL_PRECISE) avec température 0, avec fallback multi-provider."""
    return _LLMProvider(agent_name="precise", temperature=0.0)
