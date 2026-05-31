"""Pydantic models for Layer2ClarifierAgent input / output."""

from __future__ import annotations

from typing import List, Literal, Optional

from pydantic import BaseModel, Field


class Layer2ClarifierInput(BaseModel):
    """Inputs the Layer-2 clarifier needs to pick a modality + analyzer.

    Run only after the Layer-1 clarifier (or ActionRouter) has decided the
    user wants `vision_analysis` / `hybrid` (i.e. `ANALYZE` / `LOAD_AND_ANALYZE`).
    """

    query: str = Field(..., description="User's latest natural-language message.")
    target_route: Literal["vision_analysis", "hybrid"] = Field(
        ..., description="Layer-1 decision; must be one of these two."
    )

    # Map state that disambiguates vision vs. text answers.
    has_rendered_map: bool = Field(False, description="Map currently has imagery rendered.")
    has_screenshot: bool = Field(False, description="Request included a map screenshot.")
    has_last_bbox: bool = Field(False, description="Session has a last bbox to reuse.")
    loaded_collections: List[str] = Field(
        default_factory=list, description="STAC collection ids currently loaded."
    )

    # Universal pin context.
    has_pin: bool = Field(False)
    pin_lat: Optional[float] = None
    pin_lng: Optional[float] = None

    # Prior partial slots (resume mid-clarification).
    prior_analyzer_kind: Optional[str] = None
    prior_analyzer: Optional[str] = None
    prior_analysis_target: Optional[str] = None


class Layer2ClarifierDecision(BaseModel):
    """Structured output of the Layer-2 clarifier."""

    action: Literal["passthrough", "clarify"] = Field(
        ..., description="Whether to dispatch immediately or ask a follow-up."
    )
    analyzer_kind: Optional[Literal["text", "vision", "both"]] = Field(
        None,
        description=(
            "Layer-2 modality. Required when action='passthrough'. "
            "Maps to the diagram's Text / Vision / Both columns."
        ),
    )
    analyzer: Optional[
        Literal[
            "contextual",
            "graph_rag",
            "vision",
            "raster_sampling",
            "terrain",
            "mobility",
            "extreme_weather",
            "netcdf_computation",
            "building_damage",
            "comparison",
        ]
    ] = Field(None, description="Specific analyzer; may be null when kind='both'.")
    missing_slot: Optional[
        Literal["analyzer_kind", "analysis_target", "has_imagery", "collection"]
    ] = Field(None, description="Slot to ask the user for. Null on passthrough.")
    user_response: str = Field("", description="Exact text shown to user. Empty on passthrough.")
    options: List[str] = Field(default_factory=list, description="Chip suggestions.")
    reasoning: str = Field("", description="One-line internal explanation.")
