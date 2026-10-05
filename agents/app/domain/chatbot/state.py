"""
STATE LANGGRAPH — Interview Prep Agent

Le State est l'objet qui circule entre tous les noeuds du graphe.
Chaque noeud lit ce dont il a besoin et retourne SEULEMENT ce qu'il modifie.

CYCLE DE VIE :
  START
    └─ router_node          ← décide où aller selon le type de requête
         ├─ questions_node  ← génère les questions (tab 1)
         ├─ interview_node  ← gère le mock interview (tab 2)
         │     └─ evaluator_node  ← évalue à la fin de session
         └─ salary_node     ← analyse salariale (tab 3)
  END
"""


from __future__ import annotations
from typing import Literal, Optional
from pydantic import BaseModel, Field, ConfigDict



class OfferData(BaseModel):
    """Output Agent 2 — lu depuis table offre_analysee."""
    offer_id: str = ""
    job_title: str = ""
    company_name: str = ""
    required_skills: list[str] = []
    ats_keywords: list[str] = []
    tech_stack: list[str] = []
    experience_years: int = 0
    raw_text: str = ""
    location: str = ""
    contract_type: str = ""


class CompanyData(BaseModel):
    """Output Agent 3 — lu depuis table intel_entreprise."""
    company_name: str = ""
    glassdoor_rating: float = 0.0
    salary_min: int = 0
    salary_max: int = 0
    currency: str = "MAD"
    company_summary: str = ""
    interview_difficulty: str = "medium"
    known_questions: list[str] = []    # vraies questions Glassdoor


class MatchData(BaseModel):
    """Output Agent 4 — lu depuis table resultat_matching."""
    score_global: int = 0
    missing_skills: list[str] = []
    strengths: list[str] = []


class OfferContext(BaseModel):
    """
    Agrégation des 3 agents collègues.
    Rempli SEULEMENT en mode 'offer'.
    None en mode 'arena'.
    """
    offer: OfferData = Field(default_factory=OfferData)
    company: CompanyData = Field(default_factory=CompanyData)
    match: MatchData = Field(default_factory=MatchData)


class ArenaConfig(BaseModel):
    """Config du mode Arena — vient du frontend stepper."""
    domain: str = ""
    level: Literal["junior", "mid", "senior"] = "junior"
    duration_minutes: int = 20
    language: str = "en"
    focus_areas: list[str] = []


class MessageTurn(BaseModel):
    """Un tour de conversation."""
    role: Literal["ai", "user"]
    content: str
    timestamp: str = ""


class QuestionItem(BaseModel):
    """Une question générée."""
    id: str = ""
    question: str = ""
    type: str = "behavioral"           # behavioral | technical | situational
    source: str = "generated"          # glassdoor | generated | web_search
    company_specific: bool = False
    tip: str = ""
    answer: str = ""                   # réponse de l'user (rempli pendant session)
    correction: str = ""               # correction IA (rempli après session)
    score: Optional[int] = None


class DimensionScore(BaseModel):
    name: str
    score: int
    comment: str


class FeedbackResult(BaseModel):
    """Résultat final de l'évaluation — stocké dans feedback_json."""
    global_score: int = 0
    dimensions: list[DimensionScore] = []
    strengths: list[str] = []
    improvements: list[str] = []
    best_answer: str = ""
    worst_answer: str = ""
    coaching_tips: list[str] = []


class SalaryResult(BaseModel):
    """Résultat du coach salaire."""
    range_min: int = 0
    range_max: int = 0
    currency: str = "MAD"
    your_target: int = 0
    confidence_level: str = "medium"
    market_sources: list[str] = []
    negotiation_script: list[dict] = []


# ─────────────────────────────────────────────────────────────
# STATE PRINCIPAL
# ─────────────────────────────────────────────────────────────

class InterviewPrepState(BaseModel):
    """
    État global du graphe LangGraph.

    IMPORTANT :
    - messages utilise operator.add → les messages s'accumulent
      (chaque noeud AJOUTE ses messages, ne remplace pas)
    - Tous les autres champs sont remplacés directement
    """

    # ── Identifiants ──────────────────────────────────────────
    session_id: str = ""
    user_id: str = ""
    thread_id: str = ""

    # ── Mode ──────────────────────────────────────────────────
    mode: Literal["offer", "arena"] = "arena"

    # ── Type de requête → le router décide ───────────────────
    request_type: Literal[
        "generate_questions",   # tab 1 — générer les questions
        "ask_free",             # tab 1 — question libre dans le chat
        "start_interview",      # tab 2 — démarrer la session
        "continue_interview",   # tab 2 — réponse de l'user
        "end_interview",        # tab 2 — terminer + évaluer
        "get_salary",           # tab 3 — analyse salariale
    ] = "generate_questions"

    # ── Contexte selon le mode ────────────────────────────────
    offer_context: Optional[OfferContext] = None  # mode offer seulement
    arena_config: Optional[ArenaConfig] = None    # mode arena seulement
    chat_type: Optional[str] = None

    # ── Messages — s'accumulent grâce à operator.add ─────────
    # NOTE: Pydantic + LangGraph → on gère l'accumulation manuellement
    messages: list[MessageTurn] = []

    # ── Input de l'user pour le tour courant ──────────────────
    user_input: str = ""

    # ── Outputs par noeud ─────────────────────────────────────
    questions: list[QuestionItem] = []
    feedback: Optional[FeedbackResult] = None
    salary: Optional[SalaryResult] = None

    # ── Contrôle de session ───────────────────────────────────
    session_complete: bool = False
    current_question_index: int = 0

    # ── Erreur ────────────────────────────────────────────────
    error: Optional[str] = None

    model_config = ConfigDict(arbitrary_types_allowed=True)

