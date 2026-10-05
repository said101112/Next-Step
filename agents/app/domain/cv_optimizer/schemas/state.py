from typing import Annotated, Optional, TypedDict
import operator
from langchain_core.messages import BaseMessage
from langgraph.graph.message import add_messages

class CVOptimizerState(TypedDict, total=False):
    """
    État interne du workflow d'optimisation de CV.
    """
    candidate_cv: dict
    job_offer: dict
    language: str
    """Output language for the rewritten CV text: "en" (default) or "fr"."""
    skill_gap_analysis: Optional[dict]
    match_result: Optional[dict]

    optimized_cv: Optional[dict]

    messages: Annotated[list[BaseMessage], add_messages]
    errors: Annotated[list[str], operator.add]
    iteration_count: int

    validation_errors: list[str]
    """Problems of the latest attempt that the model can fix (replaced at each validation)."""

    summary_problem: Optional[str]
    """Why the model's CV summary was rejected (e.g. it described the job, not the candidate)."""

    used_fallback: bool
    """The LLM failed and the profile was used as-is: no new attempt."""
