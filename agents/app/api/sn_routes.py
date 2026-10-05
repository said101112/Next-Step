# ============================================================
# agents/app/api/sn_routes.py
#
# FastAPI routes for SN Executive AI Copilot
# Endpoint: POST /api/agents/sn/chat
# ============================================================
import logging
from typing import Dict, List, Optional
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from app.domain.sn_copilot.graph import run_sn_agent

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/agents/sn", tags=["SN Copilot"])


class SnChatRequest(BaseModel):
    user_id: str = Field(..., description="ID de l'utilisateur (UUID ou Keycloak ID)")
    message: str = Field(..., description="Message ou commande pour SN Copilot")
    user_name: Optional[str] = Field(None, description="Nom ou prénom du candidat pour personnalisation")
    history: Optional[List[Dict[str, str]]] = Field(default_factory=list, description="Historique récent des échanges")


class SnCardDto(BaseModel):
    id: Optional[str] = None
    id_offre: Optional[str] = None
    entreprise: str
    role: str
    statut: str
    channel: str = "EMAIL"
    channel_url: Optional[str] = None
    application_date: Optional[str] = None
    has_response: bool = False
    response_status: Optional[str] = "EN_ATTENTE"
    notes: Optional[str] = None
    response_summary: Optional[str] = None
    recommended_action: Optional[str] = None
    follow_up_needed: bool = False


class SnChatResponse(BaseModel):
    markdown_text: str = Field(..., description="Réponse exécutive formatée en Markdown")
    actions_performed: List[str] = Field(default_factory=list, description="Liste des actions et mutations exécutées")
    cards: List[SnCardDto] = Field(default_factory=list, description="Cartes interactives de candidatures associées")
    follow_up_suggestions: List[str] = Field(default_factory=list, description="Suggestions dynamiques de questions à poser")


@router.post("/chat", response_model=SnChatResponse, summary="Discuter avec SN Copilot")
async def chat_with_sn(req: SnChatRequest):
    """
    Interagit avec SN Copilot pour interroger la base, modifier des statuts,
    analyser le pipeline ou postuler à des offres.
    """
    try:
        result = await run_sn_agent(
            user_id=req.user_id,
            user_message=req.message,
            history=req.history,
            user_name=req.user_name,
        )
        return SnChatResponse(**result)
    except Exception as e:
        logger.error("[SN:Route] Chat error: %s", e, exc_info=True)
        raise HTTPException(status_code=500, detail="Erreur lors de la communication avec SN Copilot.")
