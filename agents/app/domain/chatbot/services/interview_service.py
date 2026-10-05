"""
SERVICE — Logique métier du module chatbot.

RESPONSABILITÉS :
  1. Récupérer le contexte de l'offre (tables agents + backend)
  2. Appeler le graphe LangGraph
  3. Retourner les schemas de réponse API

Les sessions et questions sont enregistrées par le backend (module Coaching).

Le router appelle le service.
Le service appelle le graphe.
Le service ne connaît pas HTTP.
"""

from __future__ import annotations
import uuid
import logging

from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.chatbot.graph import interview_graph
from app.domain.chatbot.state import InterviewPrepState, FeedbackResult
from app.domain.chatbot.schemas import (
    ArenaConfigSchema,
    MessageSchema,
    StartInterviewResponse,
    SendMessageResponse,
    EndInterviewResponse,
    FeedbackOut,
    DimensionOut,
)

logger = logging.getLogger(__name__)
from .context_service import get_offer_context_from_db, _to_arena_config, _to_message_turns

# SERVICE 3 — START INTERVIEW (Tab 2)
async def start_interview_service(
    mode: str,
    offer_id: str | None,
    arena_config: ArenaConfigSchema | None,
    user_id: str,
    db: AsyncSession,
    session_id: str | None = None,
) -> StartInterviewResponse:
    """Message d'ouverture de l'entretien (la session est créée par le backend)."""

    offer_ctx = None
    if mode == "offer" and offer_id:
        offer_ctx = await get_offer_context_from_db(offer_id, user_id, db)

    # The backend (Coaching module) creates the session and sends its id.
    session_id = session_id or str(uuid.uuid4())

    # Appeler le graphe pour le message d'ouverture
    state = InterviewPrepState(
        session_id=session_id,
        user_id=user_id,
        mode=mode,
        request_type="start_interview",
        offer_context=offer_ctx,
        arena_config=_to_arena_config(arena_config),
        messages=[],
    )

    result = await interview_graph.ainvoke(state)
    messages_out = result.get("messages", [])
    opening = messages_out[-1].content if messages_out else "Hello! Let's begin the interview."
    return StartInterviewResponse(
        session_id=session_id,
        opening_message=opening,
    )

# SERVICE 4 — SEND MESSAGE (Tab 2)
async def send_message_service(
    session_id: str,
    user_input: str,
    history: list[MessageSchema],
    mode: str,
    offer_id: str | None,
    arena_config: ArenaConfigSchema | None,
    user_id: str,
    db: AsyncSession,
) -> SendMessageResponse:
    """Envoie un message et reçoit la réponse du recruteur IA."""

    offer_ctx = None
    if mode == "offer" and offer_id:
        offer_ctx = await get_offer_context_from_db(offer_id, user_id, db)

    state = InterviewPrepState(
        session_id=session_id,
        user_id=user_id,
        mode=mode,
        request_type="continue_interview",
        offer_context=offer_ctx,
        arena_config=_to_arena_config(arena_config),
        messages=_to_message_turns(history),
        user_input=user_input,
    )

    result = await interview_graph.ainvoke(state)
    messages_out = result.get("messages", [])
    last_ai = next((m for m in reversed(messages_out) if m.role == "ai"), None)
    ai_content = last_ai.content if last_ai else ""

    return SendMessageResponse(
        session_id=session_id,
        ai_response=ai_content,
    )

# SERVICE 5 — END INTERVIEW + EVALUATE (Tab 2)
async def end_interview_service(
    session_id: str,
    history: list[MessageSchema],
    mode: str,
    offer_id: str | None,
    arena_config: ArenaConfigSchema | None,
    user_id: str,
    db: AsyncSession,
) -> EndInterviewResponse:
    """Évalue l'entretien (le backend enregistre le score et le feedback)."""

    offer_ctx = None
    if mode == "offer" and offer_id:
        offer_ctx = await get_offer_context_from_db(offer_id, user_id, db)

    state = InterviewPrepState(
        session_id=session_id,
        user_id=user_id,
        mode=mode,
        request_type="end_interview",
        offer_context=offer_ctx,
        arena_config=_to_arena_config(arena_config),
        messages=_to_message_turns(history),
        session_complete=True,
    )

    result = await interview_graph.ainvoke(state)
    feedback: FeedbackResult | None = result.get("feedback")
    score = feedback.global_score if feedback else 0

    # Construire la réponse
    feedback_out = FeedbackOut(
        global_score=feedback.global_score if feedback else 0,
        dimensions=[DimensionOut(**d.model_dump()) for d in (feedback.dimensions if feedback else [])],
        strengths=feedback.strengths    if feedback else [],
        improvements=feedback.improvements if feedback else [],
        best_answer=feedback.best_answer   if feedback else "",
        worst_answer=feedback.worst_answer  if feedback else "",
        coaching_tips=feedback.coaching_tips if feedback else [],
    )

    return EndInterviewResponse(
        session_id=session_id,
        score=score,
        feedback=feedback_out,
    )
