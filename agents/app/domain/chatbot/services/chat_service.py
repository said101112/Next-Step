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
import logging

from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.chatbot.graph import interview_graph
from app.domain.chatbot.state import InterviewPrepState, SalaryResult
from app.domain.chatbot.schemas import ArenaConfigSchema, MessageSchema, FreeChatResponse, SalaryContextSchema

logger = logging.getLogger(__name__)
from .context_service import get_offer_context_from_db, _to_arena_config, _to_message_turns

# SERVICE 2 — FREE CHAT (Tab 1 chat)
async def free_chat_service(
    user_input: str,
    thread_id: str,
    history: list[MessageSchema],
    offer_id: str | None,
    user_id: str,
    db: AsyncSession,
    mode: str | None = None,
    chat_type: str | None = None,
    arena_config: ArenaConfigSchema | None = None,
    salary_context: SalaryContextSchema | None = None,
) -> FreeChatResponse:
    """Répond à une question libre. Sauvegarde dans chat_message."""

    offer_ctx = None
    if offer_id:
        offer_ctx = await get_offer_context_from_db(offer_id, user_id, db)

    # Si le thread_id se termine par '-q', c'est une question de scénario de quiz, on ne la persiste pas forcément de la même manière, mais on garde la compatibilité
    db_chat_type = chat_type if chat_type else "questions"

    salary_res = None
    if salary_context:
        salary_res = SalaryResult(
            range_min=salary_context.range_min,
            range_max=salary_context.range_max,
            currency=salary_context.currency,
            your_target=salary_context.your_target,
            confidence_level="medium",
        )

    state = InterviewPrepState(
        session_id=thread_id,
        user_id=user_id,
        request_type="ask_free",
        mode=mode if mode in ["offer", "arena"] else ("offer" if offer_ctx else "arena"),
        offer_context=offer_ctx,
        arena_config=_to_arena_config(arena_config),
        salary=salary_res,
        messages=_to_message_turns(history),
        user_input=user_input,
        chat_type=db_chat_type,
    )

    result = await interview_graph.ainvoke(state)
    messages_out = result.get("messages", [])
    last_ai = next((m for m in reversed(messages_out) if m.role == "ai"), None)
    ai_content = last_ai.content if last_ai else ""

    return FreeChatResponse(
        thread_id=thread_id,
        response=ai_content,
    )
