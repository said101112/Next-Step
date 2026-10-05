"""Gestionnaire d'exceptions global FastAPI.

Normalise toutes les réponses d'erreur du service IA selon le contrat commun :
    - erreurs de validation  -> 422 { error, type, details }
    - erreurs applicatives   ->  4xx { error, type } (détail conservé si sûr)
    - erreurs internes       ->  5xx { error, type } sans fuite de détails

Le détail des erreurs internes est loggé côté serveur uniquement ; jamais
renvoyé au client. Ceci permet au proxy .NET (AgentsProxyController) et au
frontend d'afficher un message propre et stable.
"""
import logging

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

logger = logging.getLogger(__name__)

INTERNAL_ERROR_MESSAGE = "Erreur interne du service IA."
INTERNAL_ERROR_TYPE = "AgentInternalError"


def register_exception_handlers(app: FastAPI) -> None:
    @app.exception_handler(RequestValidationError)
    async def validation_error_handler(request: Request, exc: RequestValidationError) -> JSONResponse:
        errors: list[str] = []
        for error in exc.errors():
            loc = ".".join(str(part) for part in error.get("loc", []) if part != "body")
            msg = error.get("msg", "Champ invalide.")
            errors.append(f"{loc}: {msg}" if loc else msg)
        return JSONResponse(
            status_code=422,
            content={"error": "Données invalides.", "type": "ValidationError", "details": errors},
        )

    @app.exception_handler(StarletteHTTPException)
    async def http_exception_handler(request: Request, exc: StarletteHTTPException) -> JSONResponse:
        if exc.status_code >= 500:
            logger.error(
                "Agent error %s %s -> %s: %s",
                request.method,
                request.url.path,
                exc.status_code,
                exc.detail,
            )
            return JSONResponse(
                status_code=exc.status_code,
                content={"error": INTERNAL_ERROR_MESSAGE, "type": INTERNAL_ERROR_TYPE},
            )

        # 4xx : on conserve le détail, il est intentionnel (404, 400, 401...).
        if isinstance(exc.detail, str):
            return JSONResponse(
                status_code=exc.status_code,
                content={"error": exc.detail, "type": "AgentError", "status": exc.status_code},
            )
        return JSONResponse(status_code=exc.status_code, content={"detail": exc.detail})

    @app.exception_handler(Exception)
    async def unhandled_error_handler(request: Request, exc: Exception) -> JSONResponse:
        logger.exception("Unhandled error on %s %s", request.method, request.url.path)
        return JSONResponse(
            status_code=500,
            content={"error": INTERNAL_ERROR_MESSAGE, "type": INTERNAL_ERROR_TYPE},
        )
