# ============================================================
# app/domain/email_composer/schemas/models.py
#
# Pydantic request/response schemas for the Email Composer agent.
#
# All existing fields preserved. New optional enrichment fields
# (skill_gap, company_intelligence) added to GenerateEmailRequest
# without breaking existing .NET backend calls.
# ============================================================
from typing import List, Optional, Dict, Any
from pydantic import BaseModel, Field, AliasChoices, ConfigDict, field_validator


# ── Candidate & Offer inputs ──────────────────────────────────────────────────

from typing import Union, Literal

class CandidateInput(BaseModel):
    full_name: str
    email: Optional[str] = None
    phone: Optional[str] = None
    current_title: Optional[str] = None
    skills: List[Union[str, Dict[str, Any]]] = Field(default_factory=list)
    experiences: List[Union[str, Dict[str, Any]]] = Field(default_factory=list)
    education: List[Union[str, Dict[str, Any]]] = Field(default_factory=list)
    projects: List[Union[str, Dict[str, Any]]] = Field(default_factory=list)
    certifications: List[Union[str, Dict[str, Any]]] = Field(default_factory=list)


class JobOfferInput(BaseModel):
    job_title: str
    company_name: Optional[str] = None
    location: Optional[str] = None
    required_skills: List[str] = Field(default_factory=list)
    preferred_skills: List[str] = Field(default_factory=list)
    missions: List[str] = Field(default_factory=list)
    requirements: List[str] = Field(default_factory=list)
    raw_text: Optional[str] = None
    analysis_json: Optional[Dict[str, Any]] = None


class EmailOptions(BaseModel):
    language: str = "en"
    tone: str = "professionnel"
    include_motivation_letter: bool = False


# ── Optional enrichment from pipeline agents ─────────────────────────────────
# These are OPTIONAL. Legacy .NET calls omitting them will still work.

class SkillGapInput(BaseModel):
    """
    Subset of skill_gap agent output used to personalize the email.
    All fields are optional — if the pipeline did not run skill_gap,
    this entire object will be None.
    """
    matching_skills: List[str] = Field(default_factory=list)
    missing_skills: List[str] = Field(default_factory=list)
    important_missing_skills: List[str] = Field(default_factory=list)
    minor_missing_skills: List[str] = Field(default_factory=list)
    recommendations: List[str] = Field(default_factory=list)
    score: Optional[float] = None


class CompanyIntelligenceInput(BaseModel):
    """
    Subset of company agent output used to personalize the motivation
    paragraph. All fields optional — the agent uses only what is reliable.
    """
    summary: Optional[str] = None
    values: List[str] = Field(default_factory=list)
    products_or_services: List[str] = Field(default_factory=list)
    recent_context: Optional[str] = None
    recommendations: List[str] = Field(default_factory=list)
    score: Optional[int] = None


# ── Application email request/response ───────────────────────────────────────

class GenerateEmailRequest(BaseModel):
    candidature_id: str
    candidate: CandidateInput
    job_offer: JobOfferInput
    options: EmailOptions = Field(default_factory=EmailOptions)
    # Optional pipeline enrichment — absent from .NET calls, used by pipeline mode
    skill_gap: Optional[Dict[str, Any]] = None
    company_intelligence: Optional[Dict[str, Any]] = None


class GenerateEmailResponse(BaseModel):
    subject: str = Field(..., description="L'objet de l'email")
    body: str = Field(..., description="Le corps de l'email, structuré impérativement avec des sauts de ligne doubles entre les paragraphes pour la lisibilité.")
    language: str
    tone: str


# ── Follow-up / Relance models ────────────────────────────────────────────────

class PreviousEmailInput(BaseModel):
    """Context about the previously sent email that received no reply."""
    subject: str
    body: str
    sent_at_utc: Optional[str] = None


class FollowUpOptions(BaseModel):
    """Options for the follow-up email generation."""
    language: str = "en"
    tone: str = "professionnel"
    days_since_sent: Optional[int] = None


class GenerateFollowUpEmailRequest(BaseModel):
    """Request payload for POST /email/generate-follow-up."""
    candidature_id: str
    candidate: CandidateInput
    job_offer: JobOfferInput
    previous_email: PreviousEmailInput
    options: FollowUpOptions = Field(default_factory=FollowUpOptions)


# ── Response classification models ───────────────────────────────────────────

class ClassifyResponseRequest(BaseModel):
    """Request payload for POST /email/classify-response."""
    candidature_id: str
    candidate_name: Optional[str] = None
    job_title: Optional[str] = None
    company_name: Optional[str] = None
    previous_email_subject: Optional[str] = None
    previous_email_body: Optional[str] = None
    reply_from: Optional[str] = None
    reply_date_utc: Optional[str] = None
    reply_subject: Optional[str] = None
    reply_snippet: str
    language: str = "en"


class ClassifyResponseResult(BaseModel):
    """
    Result of LLM-based recruiter reply classification.

    response_type must be one of:
      ENTRETIEN_PROPOSE | INFORMATIONS_DEMANDEES | ACCEPTE | REFUSE |
      REPONSE_AUTOMATIQUE | REPONSE_GENERALE | INCONNU
    """
    model_config = ConfigDict(populate_by_name=True, extra="ignore")

    response_type: Literal[
        "ENTRETIEN_PROPOSE",
        "INFORMATIONS_DEMANDEES",
        "ACCEPTE",
        "REFUSE",
        "REPONSE_AUTOMATIQUE",
        "REPONSE_GENERALE",
        "INCONNU"
    ] = Field(
        default="INCONNU",
        description="Type de réponse du recruteur. Doit être strictement l'un de : ENTRETIEN_PROPOSE, INFORMATIONS_DEMANDEES, ACCEPTE, REFUSE, REPONSE_AUTOMATIQUE, REPONSE_GENERALE, INCONNU",
        validation_alias=AliasChoices("response_type", "category", "categorie", "type", "label")
    )
    confidence: float
    summary: str
    recommended_action: str
    should_generate_reply_draft: bool = False

    @field_validator("response_type", mode="before")
    @classmethod
    def normalize_response_type(cls, value: object) -> str:
        if value is None:
            return "INCONNU"

        raw = str(value).strip().upper()
        raw = (
            raw.replace("É", "E")
               .replace("È", "E")
               .replace("Ê", "E")
               .replace("Ë", "E")
               .replace("À", "A")
               .replace("Â", "A")
               .replace("Ù", "U")
               .replace("Û", "U")
               .replace("Î", "I")
               .replace("Ï", "I")
               .replace("Ô", "O")
               .replace("Ö", "O")
               .replace("Ç", "C")
               .replace("-", "_")
               .replace(" ", "_")
        )

        aliases = {
            "INTERVIEW_PROPOSED": "ENTRETIEN_PROPOSE",
            "INTERVIEW_SCHEDULED": "ENTRETIEN_PROPOSE",
            "ENTRETIEN": "ENTRETIEN_PROPOSE",
            "INTERVIEW": "ENTRETIEN_PROPOSE",
            "INVITATION_A_UN_ENTRETIEN": "ENTRETIEN_PROPOSE",
            "INVITATION_ENTRETIEN": "ENTRETIEN_PROPOSE",
            "PROPOSITION_D_ENTRETIEN": "ENTRETIEN_PROPOSE",
            "PROPOSITION_ENTRETIEN": "ENTRETIEN_PROPOSE",
            "DEMANDE_DISPONIBILITES": "ENTRETIEN_PROPOSE",
            "DISPONIBILITES": "ENTRETIEN_PROPOSE",
            "MORE_INFO_REQUESTED": "INFORMATIONS_DEMANDEES",
            "INFO_REQUESTED": "INFORMATIONS_DEMANDEES",
            "INFORMATION_DEMANDEE": "INFORMATIONS_DEMANDEES",
            "INFORMATIONS_DEMANDEE": "INFORMATIONS_DEMANDEES",
            "DEMANDE_D_INFORMATIONS": "INFORMATIONS_DEMANDEES",
            "DEMANDE_INFO": "INFORMATIONS_DEMANDEES",
            "ACCEPTED": "ACCEPTE",
            "ACCEPTE": "ACCEPTE",
            "REJECTED": "REFUSE",
            "REFUSE": "REFUSE",
            "DECLINED": "REFUSE",
            "REFUSED": "REFUSE",
            "AUTO_REPLY": "REPONSE_AUTOMATIQUE",
            "AUTOREPLY": "REPONSE_AUTOMATIQUE",
            "AUTOMATIC_REPLY": "REPONSE_AUTOMATIQUE",
            "GENERAL_REPLY": "REPONSE_GENERALE",
            "GENERAL": "REPONSE_GENERALE",
            "UNKNOWN": "INCONNU",
        }
        return aliases.get(raw, raw)


# ── Reply generation models ───────────────────────────────────────────────────

class RecruiterReplyInput(BaseModel):
    """Context about the recruiter's reply message."""
    from_email: Optional[str] = None
    subject: Optional[str] = None
    snippet: str
    received_at_utc: Optional[str] = None


class GenerateReplyEmailRequest(BaseModel):
    """Request payload for POST /email/generate-reply."""
    candidature_id: str
    candidate: CandidateInput
    job_offer: JobOfferInput
    previous_email: Optional[PreviousEmailInput] = None
    recruiter_reply: RecruiterReplyInput
    response_type: str
    response_summary: Optional[str] = None
    recommended_action: Optional[str] = None
    language: str = "en"
    tone: str = "professionnel"
    user_instructions: Optional[str] = None
