import logging
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
from typing import Optional, Dict, Any

from app.domain.offer_analyzer.service import offer_analyzer_service
from app.domain.profile_retriever.service import profile_retriever_service
from app.domain.matching.skill_matcher import build_match_result

logger = logging.getLogger(__name__)
router = APIRouter(tags=["M2 - Offer Pipeline"])


class OfferInput(BaseModel):
    raw_text: str = Field(..., description="Le texte brut de l'offre d'emploi")
    user_id: str = Field(..., description="ID de l'utilisateur (UUID) pour recuperer son profil")
    template_id: int = Field(1, description="ID du template CV choisi")
    generation_options: Optional[Dict[str, Any]] = Field(
        None,
        description="Options de génération email : language, tone, include_motivation_letter"
    )
    offer_id: str = Field(..., description="ID de l'offre d'emploi (UUID) pour sauvegarde DB")
    only_analysis: bool = Field(False, description="Si True, s'arrete apres l'analyse (Skill Gap)")

    analyzed_offer: Optional[Dict[str, Any]] = None
    profile_data: Optional[Dict[str, Any]] = None
    skill_gap_analysis: Optional[Dict[str, Any]] = None
    match_result: Optional[Dict[str, Any]] = None
    company_intelligence: Optional[Dict[str, Any]] = None
    cv_optimized_content: Optional[Dict[str, Any]] = None


class MatchRequest(BaseModel):
    user_id: str
    analyzed_offer: Dict[str, Any]
    profile_data: Optional[Dict[str, Any]] = None


class PipelineResult(BaseModel):
    analyzed_offer: Optional[Dict[str, Any]] = None
    profile_data: Optional[Dict[str, Any]] = None
    skill_gap_analysis: Optional[Dict[str, Any]] = None
    match_result: Optional[Dict[str, Any]] = None
    skill_gap: Optional[Dict[str, Any]] = None
    email_draft: Optional[Dict[str, Any]] = None
    company_intelligence: Optional[Dict[str, Any]] = None
    cv_data: Optional[Dict[str, Any]] = None
    errors: list = []
    warnings: list = []


from app.domain.pipeline.workflow import get_offer_pipeline


@router.post(
    "/run-pipeline",
    response_model=PipelineResult,
    summary="Pipeline complet — Agents 1-5",
    description=(
        "Orchestre l'analyse de l'offre, la récupération du profil, le scoring/skill gap, "
        "l'intelligence entreprise, la génération du brouillon d'email et l'optimisation du CV."
    ),
)
async def run_pipeline(payload: OfferInput) -> PipelineResult:
    logger.info("POST /run-pipeline - user_id=%s", payload.user_id)

    try:
        pipeline = get_offer_pipeline()

        initial_state = {
            "raw_offer_text": payload.raw_text,
            "user_id": payload.user_id,
            "template_id": payload.template_id,
            "generation_options": payload.generation_options,
            "offer_id": payload.offer_id,
            "messages": [],
            "errors": [],
            "warnings": [],
            "normalized_offer_skills": [],
            "normalized_keywords": [],
            "normalized_profile_skills": [],
            "only_analysis": payload.only_analysis,
            "analyzed_offer": payload.analyzed_offer,
            "profile_data": payload.profile_data,
            "skill_gap_analysis": payload.skill_gap_analysis or payload.match_result,
            "match_result": payload.match_result,
            "company_intelligence": payload.company_intelligence,
            "cv_optimized_content": payload.cv_optimized_content,
        }

        final_state = await pipeline.ainvoke(initial_state)
        skill_gap_analysis = final_state.get("skill_gap_analysis") or final_state.get("match_result")

        return PipelineResult(
            analyzed_offer=final_state.get("analyzed_offer"),
            profile_data=final_state.get("profile_data"),
            skill_gap_analysis=skill_gap_analysis,
            match_result=final_state.get("match_result") or skill_gap_analysis,
            skill_gap=skill_gap_analysis,
            email_draft=final_state.get("email_draft"),
            company_intelligence=final_state.get("company_intelligence"),
            cv_data=final_state.get("cv_engine_result"),
            errors=final_state.get("errors", []),
            warnings=final_state.get("warnings", []),
        )

    except Exception as e:
        logger.error("POST /run-pipeline failed: %s", e, exc_info=True)
        raise HTTPException(status_code=500, detail="Erreur lors de l'execution du pipeline.")


@router.post("/analyze-offer", response_model=dict)
async def analyze_offer(payload: OfferInput) -> dict:
    logger.info("POST /analyze-offer - user_id=%s", payload.user_id)

    try:
        result = await offer_analyzer_service.analyze(payload.raw_text)

        if not result or not result.get("analyzed_offer"):
            raise HTTPException(status_code=502, detail="Erreur LLM - analyse echouee")

        return result

    except HTTPException:
        raise

    except Exception as e:
        logger.error("POST /analyze-offer failed: %s", e, exc_info=True)
        raise HTTPException(status_code=500, detail="Erreur lors de l'analyse de l'offre.")


@router.post("/match", response_model=dict)
async def match_profile(payload: MatchRequest) -> dict:
    logger.info("POST /match - user_id=%s", payload.user_id)

    try:
        if payload.profile_data:
            profile_data = payload.profile_data
        else:
            profile_res = await profile_retriever_service.get_profile(str(payload.user_id))
            profile_data = profile_res.get("profile_data", {})

        return {**build_match_result(profile_data or {}, payload.analyzed_offer or {}), "profile_data": profile_data or {}}

    except Exception as e:
        logger.error("POST /match failed: %s", e, exc_info=True)
        raise HTTPException(status_code=500, detail="Erreur lors de la mise en correspondance.")
