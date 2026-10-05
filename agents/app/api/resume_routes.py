from fastapi import APIRouter, UploadFile, File, HTTPException
from pydantic import BaseModel
from typing import Optional
from app.domain.resume.service import extract_text_from_pdf, parse_cv_with_ai, parse_linkedin_with_ai
from app.domain.resume.summary import generate_summary
import logging

router = APIRouter()
logger = logging.getLogger(__name__)

class LinkedInRequest(BaseModel):
    url: Optional[str] = None
    rawText: Optional[str] = None

@router.post("/parse")
async def parse_resume(file: UploadFile = File(...)):
    if not file.filename.endswith(".pdf"):
        raise HTTPException(status_code=400, detail="Seuls les fichiers PDF sont supportés pour le moment.")

    try:
        # 1. Extraction du texte du PDF
        pdf_content = await file.read()
        text = await extract_text_from_pdf(pdf_content)

        if not text.strip():
            raise HTTPException(status_code=400, detail="Impossible d'extraire du texte du PDF.")

        # 2. Appel au service d'analyse AI
        parsed_json = await parse_cv_with_ai(text)

        return parsed_json

    except Exception:
        logger.exception("Error parsing resume")
        raise HTTPException(status_code=500, detail="Erreur lors de l'analyse du CV.")

@router.post("/parse-linkedin")
async def parse_linkedin_route(payload: LinkedInRequest):
    try:
        parsed_json = await parse_linkedin_with_ai(url=payload.url, raw_text=payload.rawText)
        return parsed_json
    except Exception:
        logger.exception("Error parsing LinkedIn payload")
        raise HTTPException(status_code=500, detail="Erreur lors de l'import LinkedIn.")


# Mounted without prefix: the backend calls POST /generate-resume.
summary_router = APIRouter(tags=["Resume Parsing"])


@summary_router.post("/generate-resume")
async def generate_resume_route(profile: dict):
    """Writes the profile's professional summary: {"resume": "..."}."""
    try:
        return {"resume": await generate_summary(profile, language=profile.get("language") or "en")}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception:
        logger.exception("Error generating the profile summary")
        raise HTTPException(status_code=500, detail="Erreur lors de la génération du résumé.")
