# ============================================================
# app/domain/offer_analyzer/agents/agent.py
# Agent 1 — Analyseur d'offre d'emploi (LLM)
#
# Pattern : Prompt → LLM (Groq/OpenAI) → JsonOutputParser
# Entrée  : raw_offer_text (texte brut de l'offre)
# Sortie  : analyzed_offer (dict JSON structuré)
#           + normalized_offer_skills + normalized_keywords
# ============================================================
import logging
import re
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.messages import AIMessage
from app.core.config import get_llm
from app.core.utils.normalizer import normalize_skills
from app.domain.offer_analyzer.schemas.state import OfferAnalyzerState
from app.domain.offer_analyzer.schemas.models import AnalyzedOffer
from app.domain.offer_analyzer.agents.prompt import SYSTEM_PROMPT, HUMAN_PROMPT

logger = logging.getLogger(__name__)


def _is_short_cloud_keyword(value: str, max_words: int = 4) -> bool:
    token = (value or "").strip()
    if not token:
        return False
    # Reject sentence-like entries and comma-separated fragments.
    if "," in token or ";" in token:
        return False
    if len(token.split()) > max_words:
        return False
    blocked_connectors = {" and ", " or ", " avec ", " pour "}
    lowered = f" {token.lower()} "
    if any(conn in lowered for conn in blocked_connectors):
        return False
    return True


def _fallback_offer_from_text(raw_text: str) -> dict:
    text = (raw_text or "").strip()
    low = text.lower()

    def first_match(patterns: list[str]) -> str | None:
        for p in patterns:
            m = re.search(p, text, re.IGNORECASE)
            if m and m.group(1).strip():
                return m.group(1).strip()
        return None

    title = first_match([r"titre\s*[:\-]\s*(.+)", r"poste\s*[:\-]\s*(.+)"])
    if not title:
        lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
        title = lines[0][:120] if lines else "Poste non precise"

    entreprise = first_match([r"entreprise\s*[:\-]\s*(.+)", r"societe\s*[:\-]\s*(.+)"])
    localisation = first_match([r"localisation\s*[:\-]\s*(.+)", r"location\s*[:\-]\s*(.+)"])

    type_contrat = None
    if "stage" in low:
        type_contrat = "Stage"
    elif "alternance" in low:
        type_contrat = "Alternance"
    elif "freelance" in low:
        type_contrat = "Freelance"
    elif "cdd" in low:
        type_contrat = "CDD"
    elif "cdi" in low:
        type_contrat = "CDI"

    years = None
    ym = re.search(r"(\d+)\s*(?:\+|ans|an|years?)", low)
    if ym:
        years = ym.group(1)

    education = None
    em = re.search(r"(bac\+\d|master|ingenieur|licence|phd|doctorat)", low, re.IGNORECASE)
    if em:
        education = em.group(1)

    tech_patterns = [
        (r"\bjavascript\b|\bjs\b", "JavaScript"),
        (r"\btypescript\b|\bts\b", "TypeScript"),
        (r"\bnode\.?js\b", "Node.js"),
        (r"\bexpress\.?js\b|\bexpress\b", "Express.js"),
        (r"\breact(\.js)?\b", "React"),
        (r"\bnext\.?js\b", "Next.js"),
        (r"\bpostgres(ql)?\b", "PostgreSQL"),
        (r"\bsql\b", "SQL"),
        (r"\bmongodb\b|\bmongo\b", "MongoDB"),
        (r"\bdocker\b", "Docker"),
        (r"\bkubernetes\b|\bk8s\b", "Kubernetes"),
        (r"\bterraform\b", "Terraform"),
        (r"\bairflow\b", "Airflow"),
        (r"\bkafka\b", "Apache Kafka"),
        (r"\bspark\b", "Apache Spark"),
        (r"\bscala\b", "Scala"),
        (r"\bdbt\b", "dbt"),
        (r"\bbigquery\b", "BigQuery"),
        (r"\bsnowflake\b", "Snowflake"),
        (r"\bgcp\b|\bgoogle cloud\b", "GCP"),
        (r"\baws\b|\bamazon web services\b", "AWS"),
        (r"\bazure\b", "Azure"),
        (r"\bfastapi\b", "FastAPI"),
        (r"\bci\/cd\b|\bcicd\b|\bgithub actions\b|\bgitlab ci\b", "CI/CD"),
        (r"\bn8n\b", "n8n"),
        (r"\brag\b|retrieval augmented generation", "RAG"),
        (r"\bchatbot(s)?\b", "Chatbot"),
        (r"\bia\b|\bai\b|intelligence artificielle|artificial intelligence", "IA"),
        (r"\bagile\b|\bscrum\b", "Agile"),
        (r"\bgit\b|\bgithub\b|\bgitlab\b", "Git"),
    ]

    kws: list[str] = []
    for pattern, label in tech_patterns:
        if re.search(pattern, low, re.IGNORECASE):
            kws.append(label)
    kws = list(dict.fromkeys(kws))

    required = kws[:11]
    preferred = kws[11:17]

    sentences = re.split(r"(?<=[\.\!\?])\s+", text)
    description = " ".join([s.strip() for s in sentences[:2] if s.strip()])[:400]
    if not description:
        description = "Description de poste non structuree, extraite en mode fallback."

    return {
        "titre": title or "Poste non precise",
        "entreprise": entreprise,
        "type_contrat": type_contrat,
        "localisation": localisation,
        "competences_requises": required,
        "competences_souhaitees": preferred,
        "keywords_ats": kws[:20],
        "annees_experience": years,
        "niveau_etudes": education,
        "description_poste": description,
    }


async def offer_analyzer_node(state: OfferAnalyzerState) -> dict:
    """
    Nœud LangGraph — Agent 1 : Analyse du texte brut via LLM et Pydantic.

    ┌─────────────────────────────────────────────────────────┐
    │  Entrées state  │  raw_offer_text                       │
    │  Sorties state  │  analyzed_offer                       │
    │                 │  normalized_offer_skills (requis)     │
    │                 │  normalized_keywords (ATS)            │
    │                 │  messages                             │
    │  Erreurs state  │  errors (accumulés)                   │
    │  LLM utilisé    │  Groq llama-3.3-70b | OpenAI gpt-4o  │
    └─────────────────────────────────────────────────────────┘
    """
    logger.info("Agent 1 [Offer Analyzer] -- START (Iteration: %d)", state.get("iteration_count", 0) + 1)
    raw_text = state.get("raw_offer_text", "")
    current_count = state.get("iteration_count", 0)

    if not raw_text:
        logger.warning("Agent 1 — raw_offer_text vide")
        return {
            "analyzed_offer": None,
            "errors": ["Agent1: raw_offer_text est vide"],
            "iteration_count": current_count + 1
        }

    try:
        # Configuration du LLM avec sortie structurée Pydantic (temperature 0.0 pour un score déterministe)
        llm = get_llm(agent_name="offer_analyzer", temperature=0.0).with_structured_output(AnalyzedOffer)

        # On peut injecter les erreurs précédentes dans le prompt si c'est un retry
        prev_errors = state.get("errors", [])
        system_msg = SYSTEM_PROMPT
        if prev_errors and current_count > 0:
            # Escape braces in error messages to avoid LangChain template parsing issues
            safe_errors = str(prev_errors).replace("{", "{{").replace("}", "}}")
            system_msg += f"\n\nIMPORTANT: Tes précédentes tentatives ont échoué avec ces erreurs : {safe_errors}. Corrige-les impérativement."

        prompt = ChatPromptTemplate.from_messages([
            ("system", system_msg),
            ("human", HUMAN_PROMPT),
        ])

        chain = prompt | llm

        # Invocation
        analyzed_obj: AnalyzedOffer = await chain.ainvoke({"raw_offer_text": raw_text})
        result = analyzed_obj.model_dump()

        # Safety net: if LLM returns an empty structure, enrich with deterministic fallback.
        if not result.get("titre") or (not result.get("competences_requises") and not result.get("keywords_ats")):
            fallback = _fallback_offer_from_text(raw_text)
            if not result.get("titre"):
                result["titre"] = fallback["titre"]
            if not result.get("competences_requises"):
                result["competences_requises"] = fallback["competences_requises"]
            if not result.get("keywords_ats"):
                result["keywords_ats"] = fallback["keywords_ats"]
            if not result.get("description_poste"):
                result["description_poste"] = fallback["description_poste"]

        # ── Normalisation intégrée ──────────────────────────────
        offer_skills = normalize_skills(result.get("competences_requises", []))
        keywords     = normalize_skills(result.get("keywords_ats", []))

        return {
            "analyzed_offer":          result,
            "normalized_offer_skills": offer_skills,
            "normalized_keywords":     keywords,
            "messages": [AIMessage(content=f"Analyse terminée (Tentative {current_count + 1})", name="offer_analyzer")],
            "iteration_count": current_count + 1
        }

    except Exception as e:
        logger.error("Agent 1 ❌ — Erreur LLM : %s", str(e))
        fallback = _fallback_offer_from_text(raw_text)
        offer_skills = normalize_skills(fallback.get("competences_requises", []))
        keywords = normalize_skills(fallback.get("keywords_ats", []))
        return {
            "analyzed_offer": fallback,
            "normalized_offer_skills": offer_skills,
            "normalized_keywords": keywords,
            "errors": [f"Agent1: fallback active (LLM indisponible): {str(e)}"],
            "messages": [AIMessage(content="Analyse fallback locale activee (sans LLM).", name="offer_analyzer")],
            "iteration_count": current_count + 1
        }


def offer_validator_node(state: OfferAnalyzerState) -> dict:
    """
    Nœud Algorithmique — Valide et nettoie les données extraites par l'Agent 1.
    """
    logger.info("🔧 Validation Algorithmique — START")
    data = state.get("analyzed_offer")

    # On vide les erreurs précédentes pour ne pas boucler à l'infini sur de vieux logs
    # Note: Dans LangGraph avec operator.add, on ne peut pas "vider".
    # On va donc utiliser une logique dans le router basée uniquement sur les erreurs fraîches.
    current_errors = []

    if not data:
        fallback = _fallback_offer_from_text(state.get("raw_offer_text", ""))
        return {
            "analyzed_offer": fallback,
            "errors": [],
            "messages": [AIMessage(content="Validator: fallback local applique (donnees minimales).", name="validator")]
        }

    # 1. Vérification des champs critiques
    if not data.get("titre") or data["titre"].lower() in ["string", "n/a", "unknown"]:
        current_errors.append("Validator: Le titre du poste est manquant ou invalide.")

    # 2. Nettoyage des listes
    for field in ["competences_requises", "competences_souhaitees", "keywords_ats"]:
        original_list = data.get(field, [])
        # dict.fromkeys de-duplicates but keeps the offer's order (a set shuffles it).
        cleaned_list = list(dict.fromkeys(
            item.strip() for item in original_list
            if item and item.strip() and item.strip().lower() not in ["string", "skill"]
        ))
        if field == "keywords_ats":
            cleaned_list = [item for item in cleaned_list if _is_short_cloud_keyword(item, max_words=4)]
        data[field] = cleaned_list

    if not data["competences_requises"]:
        # Do not block the pipeline: derive required skills from ATS keywords.
        data["competences_requises"] = (data.get("keywords_ats") or [])[:8]

    # 3. Validation logique — annees_experience (string parsé)
    exp = data.get("annees_experience")
    if exp is not None:
        import re
        match = re.search(r'\d+', str(exp))
        if match:
            val = int(match.group())
            if val < 0 or val > 40:
                data["annees_experience"] = None
            else:
                data["annees_experience"] = str(val)
        else:
            data["annees_experience"] = None

    # 4. Vérification du contrat
    from app.domain.offer_analyzer.schemas.models import TypeContrat
    valid_contracts = [item.value for item in TypeContrat]
    if data.get("type_contrat") and data["type_contrat"] not in valid_contracts:
        current_errors.append(f"Validator: Type de contrat '{data['type_contrat']}' non supporté.")

    return {
        "analyzed_offer": data,
        "errors": current_errors,
        "messages": [AIMessage(content=f"Validation terminée. {len(current_errors)} erreurs.", name="validator")]
    }


def offer_analyzer_router(state: OfferAnalyzerState) -> str:
    """
    Routeur — Décide s'il faut recommencer l'analyse ou terminer.
    Si des erreurs persistent après 3 tentatives, on continue quand même
    avec le dernier résultat obtenu.
    """
    count = state.get("iteration_count", 0)
    errors = state.get("errors", [])
    data = state.get("analyzed_offer") or {}
    has_min_payload = bool(data.get("titre")) and bool(data.get("description_poste")) and (
        bool(data.get("competences_requises")) or bool(data.get("keywords_ats"))
    )

    # If we already have a minimally usable payload, stop retries.
    if has_min_payload:
        return "end"

    # On retente uniquement s'il y a des erreurs ET qu'on n'a pas dépassé 3 essais
    if errors and count < 3:
        logger.warning("🔄 Retry demandé (Tentative %d/3). Erreurs: %s", count, errors[-1:])
        return "retry"

    # Dans tous les autres cas (succès OU max atteint), on termine
    if errors:
        logger.warning("⚠️ Max iterations atteintes (3/3). On continue avec le dernier résultat malgré les erreurs.")
    else:
        logger.info("✅ Analyse validée avec succès.")

    return "end"


