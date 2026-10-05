# ============================================================
# app/domain/offer_analyzer/graph/workflow.py
# Sous-graphe pour l'analyse d'offres d'emploi.
# Inclut un validateur et une boucle de retry (max 3).
# ============================================================
from langgraph.graph import StateGraph, END
from app.domain.offer_analyzer.schemas.state import OfferAnalyzerState
from app.domain.offer_analyzer.agents.agent import (
    offer_analyzer_node,
    offer_validator_node,
    offer_analyzer_router
)

def build_offer_analyzer_workflow() -> StateGraph:
    """
    Construit le graphe pour l'analyseur d'offre.
    Flux : Analyzer -> Validator -> (Router: retry or end)
    """
    graph = StateGraph(OfferAnalyzerState)

    # 1. Ajout des nœuds
    graph.add_node("offer_analyzer", offer_analyzer_node)
    graph.add_node("validator", offer_validator_node)

    # 2. Définition des connexions
    graph.set_entry_point("offer_analyzer")
    graph.add_edge("offer_analyzer", "validator")

    # 3. Arête conditionnelle (Routeur de retry)
    graph.add_conditional_edges(
        "validator",
        offer_analyzer_router,
        {
            "retry": "offer_analyzer",
            "end": END
        }
    )

    return graph.compile()
