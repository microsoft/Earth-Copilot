"""Pydantic models for ClarifierAgent input / output."""

from __future__ import annotations

from typing import List, Literal, Optional

from pydantic import BaseModel, Field


class ClarifierInput(BaseModel):
    """Inputs the ClarifierAgent needs to make a decision."""

    query: str = Field(..., description="The user's latest natural-language message.")
    has_rendered_map: bool = Field(False, description="Map currently has imagery rendered.")
    has_screenshot: bool = Field(False, description="Request included a screenshot of the map.")
    has_last_bbox: bool = Field(False, description="Session has a last bbox to reuse.")
    pending_clarification: bool = Field(False, description="An in-progress clarification chain exists.")

    # Universal pin-drop context. When the user has dropped a pin on the map
    # (with or without a STAC layer rendered), the next free-text turn is
    # interpreted as a question *about that location*. The Clarifier uses this
    # to short-circuit "where?" prompts and route directly to the right Layer-2
    # analyzer (vision / raster_sampling / terrain / extreme_weather / etc).
    has_pin: bool = Field(False, description="User has dropped a pin on the map.")
    pin_lat: Optional[float] = Field(None, description="Pin latitude (only valid when has_pin=True).")
    pin_lng: Optional[float] = Field(None, description="Pin longitude (only valid when has_pin=True).")

    # Anything the upstream router_agent already extracted — the clarifier can
    # use this to decide whether the route is missing slots.
    prior_action: Optional[str] = None
    prior_target_route: Optional[str] = None
    prior_location: Optional[str] = None
    prior_collection: Optional[str] = None


class ClarifierDecision(BaseModel):
    """
    Structured output of the ClarifierAgent.

    The downstream code interprets this exactly like a `router_action`:
      - action="passthrough" → don't interrupt; let the original router action run.
      - action="clarify"     → emit a clarify response with user_response/options.
    """

    action: Literal["passthrough", "clarify"] = Field(
        ..., description="Whether to interrupt with a clarify or let the original action run."
    )
    target_route: Optional[
        Literal["navigate_to", "stac_search", "vision_analysis", "contextual", "hybrid"]
    ] = Field(None, description="Which Layer-1 route this clarification is leading toward.")
    analyzer_kind: Optional[Literal["text", "vision", "both"]] = Field(
        None,
        description=(
            "Layer-2 modality when target_route is vision_analysis or hybrid. "
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
    ] = Field(
        None,
        description="The specific Layer-2 analyzer to dispatch when known.",
    )
    missing_slot: Optional[
        Literal["intent", "location", "collection", "has_imagery", "question",
                "analyzer_kind", "analysis_target", "time_range"]
    ] = Field(None, description="Which slot to ask the user for.")
    user_response: str = Field(
        "", description="Exact text to display to the user. Empty for passthrough."
    )
    options: List[str] = Field(
        default_factory=list, description="Chip suggestions to display alongside the question."
    )
    reasoning: str = Field("", description="One-line internal explanation (logged, not shown).")
