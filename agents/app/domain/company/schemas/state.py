# ============================================================
# app/domain/company/schemas/state.py
# État LangGraph du domaine COMPANY (Analyse entreprise)
# ============================================================
import operator
from typing import Annotated, Optional, TypedDict
from langchain_core.messages import BaseMessage
from langgraph.graph.message import add_messages


class CompanyState(TypedDict, total=False):
    """
    État du domaine COMPANY — Intelligence Agent.

    Cycle de vie :
    1. START (company_name, job_title, user_id)
    2. Search Node (accumule raw_search_results via tools)
    3. Intelligence Node (LLM structure les résultats en CompanyIntelligence)
    4. Analyst Node (Calcule la compatibilité et les reco)
    5. END
    """

    # ── Accumulatifs (Reducers) ───────────────────────────────
    messages: Annotated[list[BaseMessage], add_messages]
    errors: Annotated[list[str], operator.add]
    raw_search_results: Annotated[list[dict], operator.add]
    """Résultats bruts des outils (Glassdoor, LinkedIn, Web)."""

    # ── Entrées ───────────────────────────────────────────────
    company_name: str
    """Nom de l'entreprise cible."""

    job_title: str
    """Intitulé du poste pour la recherche de salaires."""

    user_id: str
    """ID utilisateur pour le contexte."""

    # ── Intelligence Data (Agent 1: Researcher) ───────────────
    company_summary: str
    """Résumé narratif de l'entreprise."""

    salaries: list[dict]
    """Données de salaires récupérées (SalaryInfo)."""

    culture_metrics: dict
    """Metrics de culture (Glassdoor rating, turnover etc)."""

    # ── Analyse (Agent 2: Strategist) ─────────────────────────
    intelligence: Optional[dict]
    """Objet CompanyIntelligence complet et structuré."""

    score: int
    """Score de "fit" candidat/entreprise (0-100)."""

    recommendations: list[str]
    """Conseils pour l'entretien et la candidature."""

    # ── Routeur ──────────────────────────────────────────────
    next_agent: Optional[str]
    pipeline_version: str
