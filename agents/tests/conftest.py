# ============================================================
# agents/tests/conftest.py
# Configuration pytest partagée entre tous les tests
# ============================================================
import sys
import os
import pytest

# ── Ajoute le dossier agents/ au PYTHONPATH ────────────────────
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


# ── Données de test partagées (fixtures) ──────────────────────

@pytest.fixture
def sample_offer_text():
    """Texte brut d'offre pour les tests d'intégration."""
    return (
        "Nous recherchons un Développeur Fullstack Senior (CDI) à Paris. "
        "Compétences requises : React.js, Node.js, TypeScript, PostgreSQL, Docker. "
        "Compétences souhaitées : Kubernetes, Redis, GraphQL. "
        "Mots-clés ATS : React, Node, TypeScript, Docker, PostgreSQL, REST API, CI/CD. "
        "Expérience : 3 ans minimum. Niveau : Bac+5. "
        "Rémunération : 50-65k€. Télétravail hybride possible."
    )


@pytest.fixture
def sample_analyzed_offer():
    """Offre déjà analysée (résultat Agent 1 simulé)."""
    return {
        "titre": "Développeur Fullstack Senior",
        "entreprise": "TechCorp",
        "type_contrat": "CDI",
        "localisation": "Paris",
        "competences_requises": ["React", "Node.js", "TypeScript", "PostgreSQL", "Docker"],
        "competences_souhaitees": ["Kubernetes", "Redis", "GraphQL"],
        "keywords_ats": ["react", "node.js", "typescript", "docker", "postgresql", "rest api", "ci/cd"],
        "annees_experience": 3,
        "niveau_etudes": "Bac+5",
        "description_poste": "Développement d'une plateforme SaaS en full remote partiel.",
    }


@pytest.fixture
def sample_profile():
    """Profil candidat simulé (résultat Agent 2)."""
    return {
        "user_id": "test-user-uuid-1234",
        "nom": "Dupont",
        "prenom": "Jean",
        "titre": "Développeur Full-Stack React Node.js",
        "resume": (
            "Développeur passionné avec 4 ans d'expérience en React, TypeScript et Node.js. "
            "Expert Docker et CI/CD, habitué aux environnements cloud (AWS)."
        ),
        "telephone": "+33612345678",
        "ville": "Paris",
        "competences": [
            {"nom": "React", "niveau": 5},
            {"nom": "TypeScript", "niveau": 4},
            {"nom": "Node.js", "niveau": 4},
            {"nom": "PostgreSQL", "niveau": 3},
            {"nom": "Docker", "niveau": 3},
            {"nom": "Python", "niveau": 2},
            {"nom": "AWS", "niveau": 2},
        ],
        "experiences": [
            {
                "titre": "Développeur Full-Stack",
                "entreprise": "StartupX",
                "date_debut": "2021-01-01",
                "date_fin": None,
                "description": "Développement React et Node.js, déploiement Docker.",
            },
            {
                "titre": "Développeur Frontend",
                "entreprise": "AgenceY",
                "date_debut": "2019-06-01",
                "date_fin": "2020-12-31",
                "description": "Interfaces React et TypeScript.",
            },
        ],
        "formations": [
            {"diplome": "Master Informatique", "etablissement": "Université Paris-Saclay", "annee": 2019},
        ],
        "certifications": [
            {"nom": "AWS Certified Developer", "organisme": "Amazon"},
        ],
        "projets": [
            {
                "titre": "Portfolio Personnel",
                "description": "Site Next.js avec TypeScript et Vercel.",
                "technologies": ["Next.js", "TypeScript", "Vercel"],
            }
        ],
    }


@pytest.fixture
def sample_match_result():
    """Résultat de scoring simulé (résultat Agent 4)."""
    return {
        "score_matching": 75,
        "score_ats": 68,
        "keywords_presents": ["react", "node.js", "typescript", "docker"],
        "keywords_manquants": ["kubernetes", "redis"],
        "recommandations": ["Ajouter Kubernetes dans votre profil"],
        "competences_matching": ["React", "TypeScript", "Node.js", "Docker"],
        "competences_manquantes": ["Kubernetes", "Redis"],
    }

import uuid
from unittest.mock import AsyncMock, MagicMock

from app.domain.chatbot.state import (
    QuestionItem, FeedbackResult,
    DimensionScore, SalaryResult, OfferContext,
    OfferData, CompanyData, MatchData,
)
from app.domain.chatbot.schemas import ArenaConfigSchema, MessageSchema


# ═══════════════════════════════════════════════════════════════
# FIXTURES — DONNÉES DE TEST
# ═══════════════════════════════════════════════════════════════

@pytest.fixture
def offer_id() -> str:
    """UUID fixe de l'offre de test — même que dans seed_mock_data.sql."""
    return "22222222-2222-2222-2222-222222222222"


@pytest.fixture
def user_id() -> str:
    """UUID fixe de l'utilisateur de test."""
    return "11111111-1111-1111-1111-111111111111"


@pytest.fixture
def session_id() -> str:
    """UUID fixe pour une session de test."""
    return "55555555-5555-5555-5555-555555555555"


@pytest.fixture
def arena_config_schema() -> ArenaConfigSchema:
    """Config Arena valide pour les tests."""
    return ArenaConfigSchema(
        domain="Data & AI",
        level="junior",
        duration_minutes=20,
        language="en",
        focus_areas=["Python", "SQL"],
    )


@pytest.fixture
def message_history() -> list[MessageSchema]:
    """Historique de conversation simple pour les tests."""
    return [
        MessageSchema(role="ai",   content="Hello! Tell me about yourself."),
        MessageSchema(role="user", content="I have 3 years of Python experience."),
        MessageSchema(role="ai",   content="Great! Can you describe a pipeline you built?"),
    ]


# ═══════════════════════════════════════════════════════════════
# FIXTURES — MOCKS DONNÉES DB
# ═══════════════════════════════════════════════════════════════

@pytest.fixture
def mock_offre_row():
    """
    Simule une ligne retournée par la table offre_analysee.
    MagicMock = objet dont tu peux définir tous les attributs.
    """
    row = MagicMock()
    row.titre_poste          = "Data Engineer"
    row.entreprise           = "OCP Group"
    row.competences_requises = ["Python", "Spark", "Airflow"]
    row.keywords_ats         = ["ETL", "pipeline", "data lake"]
    row.stack_technique      = ["PySpark", "Airflow", "dbt"]
    row.annees_experience    = 3
    row.localisation         = ""
    row.type_contrat         = ""
    return row


@pytest.fixture
def mock_intel_row():
    """Simule une ligne retournée par la table intel_entreprise."""
    row = MagicMock()
    row.nom_entreprise       = "OCP Group"
    row.note_glassdoor       = 3.8
    row.salaire_min          = 18000
    row.salaire_max          = 28000
    row.devise_salaire       = "MAD"
    row.resume_entreprise    = "OCP is the world leader in phosphates."
    row.difficulte_entretien = "medium"
    row.questions_connues    = [
        "Describe a complex ETL pipeline you built.",
        "How do you handle data quality issues?",
    ]
    return row


@pytest.fixture
def mock_match_row():
    """Simule une ligne retournée par la table resultat_matching."""
    row = MagicMock()
    row.score_global             = 78
    row.competences_manquantes   = ["Kafka", "Kubernetes"]
    row.points_forts             = ["Python", "Spark", "SQL"]
    return row


@pytest.fixture
def mock_offer_context(mock_offre_row, mock_intel_row, mock_match_row) -> OfferContext:
    """OfferContext complet simulant les 3 agents collègues."""
    return OfferContext(
        offer=OfferData(
            offer_id="22222222-2222-2222-2222-222222222222",
            job_title=mock_offre_row.titre_poste,
            company_name=mock_offre_row.entreprise,
            required_skills=mock_offre_row.competences_requises,
            ats_keywords=mock_offre_row.keywords_ats,
            tech_stack=mock_offre_row.stack_technique,
            experience_years=mock_offre_row.annees_experience,
            location=mock_offre_row.localisation,
            contract_type=mock_offre_row.type_contrat,
        ),
        company=CompanyData(
            company_name=mock_intel_row.nom_entreprise,
            glassdoor_rating=mock_intel_row.note_glassdoor,
            salary_min=mock_intel_row.salaire_min,
            salary_max=mock_intel_row.salaire_max,
            currency=mock_intel_row.devise_salaire,
            company_summary=mock_intel_row.resume_entreprise,
            interview_difficulty=mock_intel_row.difficulte_entretien,
            known_questions=mock_intel_row.questions_connues,
        ),
        match=MatchData(
            score_global=mock_match_row.score_global,
            missing_skills=mock_match_row.competences_manquantes,
            strengths=mock_match_row.points_forts,
        ),
    )


# ═══════════════════════════════════════════════════════════════
# FIXTURES — MOCKS RÉSULTATS GRAPH LANGGRAPH
# ═══════════════════════════════════════════════════════════════

@pytest.fixture
def mock_questions_result() -> list[QuestionItem]:
    """Questions simulées retournées par le graphe LangGraph."""
    return [
        QuestionItem(
            id=str(uuid.uuid4()),
            question="Describe a complex ETL pipeline you built from scratch.",
            type="technical",
            source="glassdoor",
            company_specific=True,
            tip="Use STAR method. Focus on scale and architecture decisions.",
        ),
        QuestionItem(
            id=str(uuid.uuid4()),
            question="How do you handle data quality issues in production?",
            type="behavioral",
            source="generated",
            company_specific=False,
            tip="Mention monitoring tools, data validation, alerts.",
        ),
        QuestionItem(
            id=str(uuid.uuid4()),
            question="Explain the difference between Spark and MapReduce.",
            type="technical",
            source="generated",
            company_specific=False,
            tip="Focus on in-memory processing and performance.",
        ),
    ]


@pytest.fixture
def mock_feedback_result() -> FeedbackResult:
    """Feedback simulé retourné par le noeud evaluator."""
    return FeedbackResult(
        global_score=74,
        dimensions=[
            DimensionScore(name="Clarity",            score=80, comment="Clear and structured answers."),
            DimensionScore(name="STAR Method",        score=65, comment="STAR not always applied."),
            DimensionScore(name="Technical Accuracy", score=78, comment="Good technical knowledge."),
            DimensionScore(name="Communication",      score=75, comment="Professional language used."),
            DimensionScore(name="Confidence",         score=72, comment="Some hesitation detected."),
        ],
        strengths=["Strong Python knowledge", "Good pipeline design", "Clear communication"],
        improvements=["Apply STAR method more consistently", "Mention Kafka experience"],
        best_answer="My Spark pipeline processed 500GB daily using partitioning...",
        worst_answer="I don't know much about Kafka. Better: describe willingness to learn.",
        coaching_tips=[
            "Always structure answers with Situation, Task, Action, Result.",
            "Quantify your achievements — use numbers and scale.",
            "Prepare 2-3 stories about challenging projects.",
        ],
    )


@pytest.fixture
def mock_salary_result() -> SalaryResult:
    """Résultat salaire simulé."""
    return SalaryResult(
        range_min=18000,
        range_max=28000,
        currency="MAD",
        your_target=25000,
        confidence_level="high",
        market_sources=["Glassdoor 2025", "LinkedIn Salary Morocco"],
        negotiation_script=[
            {"step": 1, "action": "Anchor high", "phrase": "I was expecting around 25,000 MAD.", "why": "Sets anchor above target"},
            {"step": 2, "action": "Justify",      "phrase": "My Spark + dbt stack directly addresses your needs.", "why": "Links skills to value"},
        ],
    )


# ═══════════════════════════════════════════════════════════════
# FIXTURES — MOCK DB SESSION
# ═══════════════════════════════════════════════════════════════

@pytest.fixture
def mock_db():
    """
    Simule une session SQLAlchemy AsyncSession.
    Toutes les méthodes DB (add, commit, flush, get, execute)
    sont remplacées par des AsyncMock qui ne font rien.
    """
    db = AsyncMock()

    # Ces méthodes retournent None par défaut (comportement normal)
    db.add     = MagicMock()       # add() est synchrone dans SQLAlchemy
    db.flush   = AsyncMock()
    db.commit  = AsyncMock()
    db.rollback = AsyncMock()

    # db.get() → simule qu'on ne trouve pas de session existante par défaut
    # (on peut le surcharger dans chaque test)
    db.get = AsyncMock(return_value=None)

    return db


@pytest.fixture
def mock_db_with_session(mock_db, session_id):
    """
    DB qui retourne une vraie session quand on appelle db.get().
    Utilisé pour tester end_interview où on met à jour la session.
    """
    session_row = MagicMock()
    session_row.id_session      = uuid.UUID(session_id)
    session_row.status          = "in_progress"
    session_row.score_entretien = None
    session_row.completed_at    = None
    session_row.feedback_json   = None

    mock_db.get = AsyncMock(return_value=session_row)
    return mock_db, session_row


# ── No network in tests: backend calls answer "nothing found" unless a test patches them ──
@pytest.fixture(autouse=True)
def _no_backend_calls(monkeypatch):
    from unittest.mock import AsyncMock
    monkeypatch.setattr("app.core.backend_client._request", AsyncMock(return_value=None))
