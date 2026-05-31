"""Pydantic models for the ContextualAgent."""

from __future__ import annotations

from typing import List, Optional

from pydantic import BaseModel, Field


class ContextualInput(BaseModel):
    """Inputs the ContextualAgent needs to answer an educational question."""

    question: str = Field(..., description="User's natural-language question.")
    hint: Optional[str] = Field(
        None,
        description=(
            "Optional planning hint from the AnalysisRouter "
            "('methodology', 'fallback after step failure', ...)."
        ),
    )
    history: List[dict] = Field(
        default_factory=list,
        description="Optional recent conversation turns for grounding.",
    )


class ContextualResult(BaseModel):
    """Structured output of a ContextualAgent run."""

    success: bool
    answer: str = ""
    confidence: float = 0.0
    error: Optional[str] = None
    elapsed_ms: int = 0
