from typing import List, Optional
from pydantic import BaseModel, ConfigDict
from pydantic.alias_generators import to_camel

class CamelCaseBaseModel(BaseModel):
    model_config = ConfigDict(
        populate_by_name=True,
        alias_generator=to_camel
    )

class QuestPDFCandidate(CamelCaseBaseModel):
    name: str = ""
    email: str = ""
    phone: Optional[str] = None
    location: Optional[str] = None
    photo_url: Optional[str] = None
    linked_in: Optional[str] = None
    git_hub: Optional[str] = None
    portfolio: Optional[str] = None

class QuestPDFSkill(CamelCaseBaseModel):
    name: str = ""
    level: int = 1
    is_matched: bool = False

class QuestPDFExperience(CamelCaseBaseModel):
    role: str = ""
    company: str = ""
    start: Optional[str] = None
    end: Optional[str] = None
    bullets: List[str] = []

class QuestPDFEducation(CamelCaseBaseModel):
    degree: str = ""
    institution: str = ""
    year: Optional[str] = None

class QuestPDFProject(CamelCaseBaseModel):
    title: str = ""
    description: Optional[str] = None
    bullets: List[str] = []

class QuestPDFActivity(CamelCaseBaseModel):
    title: str = ""
    role: Optional[str] = None
    description: Optional[str] = None
    start: Optional[str] = None
    end: Optional[str] = None

class QuestPDFCvData(CamelCaseBaseModel):
    """
    Modèle racine envoyé au moteur .NET QuestPDF.
    Il mappe exactement la classe C# CvData.cs.
    """
    candidate: QuestPDFCandidate = QuestPDFCandidate()
    summary: Optional[str] = None
    experience: List[QuestPDFExperience] = []
    education: List[QuestPDFEducation] = []
    skills: List[QuestPDFSkill] = []
    projects: List[QuestPDFProject] = []
    certifications: List[str] = []
    languages: List[str] = []
    activities: List[QuestPDFActivity] = []

    # Customization
    theme_color: Optional[str] = None
    font_family: Optional[str] = None

    # AI Metadata
    ats_score: int = 0
    matching_score: int = 0
    ats_coverage_pct: float = 0.0

class PrepareCvRequest(BaseModel):
    """Re-creation of the legacy orchestrator payload."""
    user_id: str
    template_slug: str
    offer_data: Optional[dict] = None
