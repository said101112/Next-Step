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
from app.domain.chatbot.state import InterviewPrepState
from app.domain.chatbot.schemas import ArenaConfigSchema, QuestionsResponse, QuestionOut

logger = logging.getLogger(__name__)
from .context_service import get_offer_context_from_db, _to_arena_config

# SERVICE 1 — QUESTIONS (Tab 1)
async def generate_questions_service(
    mode: str,
    offer_id: str | None,
    arena_config: ArenaConfigSchema | None,
    user_id: str,
    db: AsyncSession,
) -> QuestionsResponse:
    """
    Génère les questions via LangGraph. Rien n'est enregistré ici : le backend (module
    Coaching) réutilise les questions existantes et sauvegarde les nouvelles.
    """

    # 1. Récupérer le contexte offre si mode offer
    offer_ctx = None
    if mode == "offer" and offer_id:
        offer_ctx = await get_offer_context_from_db(offer_id, user_id, db)

    # 2. Construire l'état initial
    state = InterviewPrepState(
        session_id=str(uuid.uuid4()),
        user_id=user_id,
        mode=mode,
        request_type="generate_questions",
        offer_context=offer_ctx,
        arena_config=_to_arena_config(arena_config),
    )

    # 3. Invoquer le graphe
    result = await interview_graph.ainvoke(state)
    questions_out = result.get("questions", [])

    if not questions_out:
        logger.warning("Graph returned 0 questions")

    # 4. Retourner le schema de réponse
    return QuestionsResponse(
        mode=mode,
        total=len(questions_out),
        questions=[
            QuestionOut(
                id=q.id,
                question=q.question,
                type=q.type,
                source=q.source,
                company_specific=q.company_specific,
                tip=q.tip,
            )
            for q in questions_out
        ],
    )
