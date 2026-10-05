import operator
from typing import Annotated, Optional, TypedDict, Dict, Any
from langchain_core.messages import BaseMessage
from langgraph.graph.message import add_messages

class PipelineState(TypedDict, total=False):
    """État global du pipeline NextStep."""

    # -- Entrées --
    raw_offer_text: str
    user_id: str
    template_id: int
    offer_id: str

    # -- Données intermédiaires --
    analyzed_offer: Optional[Dict[str, Any]]
    normalized_offer_skills: Annotated[list[str], operator.add]
    normalized_keywords: Annotated[list[str], operator.add]

    profile_data: Optional[Dict[str, Any]]
    profile_full_text: str
    normalized_profile_skills: Annotated[list[str], operator.add]

    skill_gap_analysis: Optional[Dict[str, Any]]
    match_result: Optional[Dict[str, Any]]
    """Skill gap analysis result (legacy key used by skill_gap_node)."""

    # -- Phase 2: Company + Email composer --
    company_intelligence: Optional[Dict[str, Any]]
    """Output of the company agent (intelligence + score + recommendations)."""

    company_intelligence_source: str
    """Where it came from: "request" (sent by the backend), "cache" (recent analysis) or "fresh"."""

    company_intelligence_collected_at: Any
    """When a reused analysis was collected (keeps its cache age when linked to this offer)."""

    email_draft: Optional[Dict[str, Any]]
    """Generated email draft: {subject, body, language, tone}."""

    generation_options: Optional[Dict[str, Any]]
    """Email generation options passed from the API request: language, tone, etc."""

    # -- Métadonnées --
    messages: Annotated[list[BaseMessage], add_messages]
    errors: Annotated[list[str], operator.add]
    warnings: Annotated[list[str], operator.add]

    # -- Sorties Finales (CV) --
    cv_optimized_content: Optional[Dict[str, Any]]
    cv_engine_result: Optional[Dict[str, Any]]

    # -- Contrôle du flux --
    only_analysis: bool  # True pour s'arrêter après le skill gap et intel

