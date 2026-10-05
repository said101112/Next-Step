# ============================================================
# app/domain/offer_analyzer/schemas/state.py
# ============================================================
import operator
from typing import Annotated, Optional, TypedDict
from langchain_core.messages import BaseMessage
from langgraph.graph.message import add_messages


class OfferAnalyzerState(TypedDict, total=False):
    """État interne de l'agent offer_analyzer.

    Après exécution, cet agent retourne également les champs normalisés
    de l'offre afin d'éviter un nœud normalizer séparé.
    """
    raw_offer_text: str
    analyzed_offer: Optional[dict]

    # ── Champs normalisés (calculés en sortie de l'agent) ─────
    normalized_offer_skills: Annotated[list[str], operator.add]
    normalized_keywords: Annotated[list[str], operator.add]

    messages: Annotated[list[BaseMessage], add_messages]
    errors: Annotated[list[str], operator.add]
    iteration_count: int
