"""
ROUTER — Reçoit les requêtes HTTP, appelle le service, retourne la réponse.
Aucune logique métier ici.
"""

import logging
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.domain.chatbot.schemas import (
    QuestionsRequest,   QuestionsResponse,
    FreeChatRequest,    FreeChatResponse,
    StartInterviewRequest,  StartInterviewResponse,
    SendMessageRequest,     SendMessageResponse,
    EndInterviewRequest,    EndInterviewResponse,
    SalaryRequest,          SalaryResponse,
)
from app.domain.chatbot import services as service

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/chatbot", tags=["Interview Prep"])


@router.get("/health")
async def health():
    return {"status": "ok", "agent": "interview-prep"}


# ── Tab 1 : Questions ─────────────────────────────────────────
#testé
@router.post("/questions", response_model=QuestionsResponse)
async def generate_questions(
    req: QuestionsRequest,
    db: AsyncSession = Depends(get_db),
):
    """
    Génère les questions d'entretien.

    Postman — Arena Mode:
    POST /api/chatbot/questions
    { "mode":"arena", "arena_config":{"domain":"Data & AI","level":"junior","duration_minutes":20,"language":"en","focus_areas":["Python","SQL"]}, "user_id":"test-user-001" }

    Postman — Offer Mode:
    POST /api/chatbot/questions
    { "mode":"offer", "offer_id":"uuid-de-l-offre", "user_id":"uuid-user" }
    """
    try:
        return await service.generate_questions_service(
            mode=req.mode,
            offer_id=req.offer_id,
            arena_config=req.arena_config,
            user_id=req.user_id,
            db=db,
        )
    except Exception as e:
        logger.error("generate_questions error: %s", e, exc_info=True)
        raise HTTPException(status_code=500, detail="Erreur lors de la generation des questions.")


# ── Tab 1 : Chat libre ────────────────────────────────────────
#testé
@router.post("/free-chat", response_model=FreeChatResponse)
async def free_chat(
    req: FreeChatRequest,
    db: AsyncSession = Depends(get_db),
):
    """
    Question libre dans le chat du tab Questions.

    Postman:
    POST /api/chatbot/free-chat
    { "user_input":"How to answer STAR questions?", "thread_id":"any-uuid", "history":[], "user_id":"test-user-001" }
    """
    try:
        return await service.free_chat_service(
            user_input=req.user_input,
            thread_id=req.thread_id,
            history=req.history,
            offer_id=req.offer_id,
            user_id=req.user_id,
            db=db,
            mode=req.mode,
            chat_type=req.chat_type,
            arena_config=req.arena_config,
            salary_context=req.salary_context,
        )
    except Exception as e:
        logger.error("free_chat error: %s", e, exc_info=True)
        raise HTTPException(status_code=500, detail="Erreur lors du chat libre.")


# ── Tab 2 : Démarrer ─────────────────────────────────────────
#testé
@router.post("/interview/start", response_model=StartInterviewResponse)
async def start_interview(
    req: StartInterviewRequest,
    db: AsyncSession = Depends(get_db),
):
    try:
        return await service.start_interview_service(
            mode=req.mode,
            offer_id=req.offer_id,
            arena_config=req.arena_config,
            user_id=req.user_id,
            db=db,
            session_id=req.session_id,
        )
    except Exception as e:
        logger.error("start_interview error: %s", e, exc_info=True)
        raise HTTPException(status_code=500, detail="Erreur lors du demarrage de l'entretien.")


# ── Tab 2 : Envoyer message ───────────────────────────────────
#testé
@router.post("/interview/message", response_model=SendMessageResponse)
async def send_message(
    req: SendMessageRequest,
    db: AsyncSession = Depends(get_db),
):
    try:
        return await service.send_message_service(
            session_id=req.session_id,
            user_input=req.user_input,
            history=req.history,
            mode=req.mode,
            offer_id=req.offer_id,
            arena_config=req.arena_config,
            user_id=req.user_id,
            db=db,
        )
    except Exception as e:
        logger.error("send_message error: %s", e, exc_info=True)
        raise HTTPException(status_code=500, detail="Erreur lors de l'envoi du message.")


# ── Tab 2 : Terminer + évaluer ────────────────────────────────
##testé
@router.post("/interview/end", response_model=EndInterviewResponse)
async def end_interview(
    req: EndInterviewRequest,
    db: AsyncSession = Depends(get_db),
):

    try:
        return await service.end_interview_service(
            session_id=req.session_id,
            history=req.history,
            mode=req.mode,
            offer_id=req.offer_id,
            arena_config=req.arena_config,
            user_id=req.user_id,
            db=db,
        )
    except Exception as e:
        logger.error("end_interview error: %s", e, exc_info=True)
        raise HTTPException(status_code=500, detail="Erreur lors de la fin de l'entretien.")


# ── Tab 3 : Salary ────────────────────────────────────────────

#testé
@router.post("/salary", response_model=SalaryResponse)
async def get_salary(
    req: SalaryRequest,
    db: AsyncSession = Depends(get_db),
):

    try:
        return await service.get_salary_service(
            mode=req.mode,
            offer_id=req.offer_id,
            arena_config=req.arena_config,
            user_id=req.user_id,
            db=db,
        )
    except Exception as e:
        logger.error("get_salary error: %s", e, exc_info=True)
        raise HTTPException(status_code=500, detail="Erreur lors de l'analyse salariale.")
