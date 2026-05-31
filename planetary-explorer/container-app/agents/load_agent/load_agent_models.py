"""Pydantic models for LoadAgent input / output.

The LoadAgent fills the architectural gap where Layer-1 ActionRouter classifies
a turn as `LOAD` and the v2 pipeline then returned an empty answer, leaving the
FastAPI layer to keyword-match a STAC collection and render tiles silently.

This agent owns slot extraction (intent / location / collection / datetime /
deliverable), asks ONE focused clarification when a slot is ambiguous, and
ALWAYS produces a `chat_summary` so the chat bubble never says
"No response received".
"""

from __future__ import annotations

from typing import List, Literal, Optional

from pydantic import BaseModel, Field


# ------------------------------------------------------------------ #
#  Input                                                              #
# ------------------------------------------------------------------ #


class LoadAgentInput(BaseModel):
    """Inputs the LoadAgent needs to plan a STAC load.

    Run after Layer-1 ActionRouter has decided `LOAD` (or `LOAD_AND_ANALYZE`).
    """

    query: str = Field(..., description="User's latest natural-language message.")

    # Spatial context
    location_name: Optional[str] = Field(
        None, description="Place name extracted by Layer-1 (e.g. 'California')."
    )
    has_bbox: bool = Field(False, description="Request carries a usable bbox.")
    bbox: Optional[List[float]] = Field(
        None,
        description="WGS84 [minx, miny, maxx, maxy] when known. None when only a name is available.",
    )

    # Temporal context
    has_time_range: bool = Field(False)
    time_range: Optional[List[str]] = Field(
        None, description="ISO 8601 [start, end] when explicitly provided."
    )

    # Map state at the time of the load request
    has_rendered_map: bool = Field(False)
    loaded_collections: List[str] = Field(
        default_factory=list,
        description="Collection ids already loaded; informs replace-vs-add.",
    )

    # Pin (rare for LOAD but kept for completeness)
    has_pin: bool = Field(False)
    pin_lat: Optional[float] = None
    pin_lng: Optional[float] = None

    # Layer-1 hints (forwarded; never trusted blindly)
    layer1_stac_query: Optional[str] = None
    layer1_reasoning: Optional[str] = None

    # Catalog routing (MPC Public vs Pro / GeoCatalog). When ``stac_mode``
    # is "pro", the agent should pick from ``available_pro_collections``
    # rather than its built-in public PC collection list.
    stac_mode: Optional[str] = Field(
        None, description="'public' (default) or 'pro' -- routes to MPC Pro catalog."
    )
    available_pro_collections: List[str] = Field(
        default_factory=list,
        description="Collection ids the configured MPC Pro catalog exposes.",
    )

    # Clarification resume — populated when this turn is the user's
    # response to a previous LoadAgent action='clarify' turn. The
    # current ``query`` field then holds the user's reply (e.g. "yes",
    # "both", "the second one") and these fields carry the prior turn's
    # context so the agent can resolve the ambiguity instead of re-asking.
    prior_query: Optional[str] = Field(
        None,
        description="The user's ORIGINAL load query from the turn that triggered the prior clarification.",
    )
    prior_clarification_question: Optional[str] = Field(
        None, description="Exact clarification question asked on the prior turn."
    )
    prior_clarification_options: List[str] = Field(
        default_factory=list,
        description="Chip options shown to the user on the prior turn.",
    )
    prior_collection_candidates: List[str] = Field(
        default_factory=list,
        description="Collection ids the LoadAgent ranked on the prior turn.",
    )
    prior_clarification_history: List[dict] = Field(
        default_factory=list,
        description=(
            "Full Q/A chain across the clarify session. Each item is "
            "{'question': str, 'answer': str}. Lets the agent see EVERY "
            "slot the user has already filled, not just the latest reply."
        ),
    )
    clarification_round: int = Field(
        0,
        description=(
            "How many clarification turns have already happened in this "
            "chain. >=2 means the agent has asked at least twice; "
            ">=3 means MUST execute with sensible defaults rather than "
            "asking again."
        ),
    )


# ------------------------------------------------------------------ #
#  Slot models                                                        #
# ------------------------------------------------------------------ #


LoadIntent = Literal[
    "snapshot",          # one collection at one time → single layer
    "temporal_change",   # before/after of one collection → diff or 2 layers
    "timeseries",        # one collection across many times → animation/stats
    "compare_collections",  # 2+ collections at the same time
]


DeliverableKind = Literal[
    "single_layer",
    "before_after",
    "diff",
    "stats_only",
    "timeseries",
]


class CollectionCandidate(BaseModel):
    """One ranked STAC collection the agent thinks could satisfy the query."""

    id: str = Field(..., description="STAC collection id, e.g. 'nlcd-licenses'.")
    title: str = Field("", description="Human-readable label for the chat answer.")
    rank: int = Field(0, description="0 = best, 1 = next, ...")
    reason: str = Field("", description="Why this collection was picked.")


class LocationSlot(BaseModel):
    name: Optional[str] = None
    needs_geocoding: bool = False
    suggested_bbox: Optional[List[float]] = Field(
        None,
        description="Optional WGS84 [minx, miny, maxx, maxy] hint when the agent knows one.",
    )


class DatetimeSlot(BaseModel):
    ambiguous: bool = False
    range: Optional[List[str]] = Field(
        None, description="ISO 8601 [start, end] when concrete."
    )
    suggestions: List[List[str]] = Field(
        default_factory=list,
        description=(
            "Candidate ranges the agent could disambiguate to, e.g. "
            "[['2001-01-01','2001-12-31'], ['2021-01-01','2021-12-31']]."
        ),
    )


# ------------------------------------------------------------------ #
#  Output                                                             #
# ------------------------------------------------------------------ #


class LoadPlan(BaseModel):
    """Structured output of the LoadAgent.

    `chat_summary` is REQUIRED to be non-empty so the v2 pipeline can never
    return `answer=""` for a LOAD turn again.
    """

    action: Literal["execute", "clarify"] = Field(
        ..., description="Whether to run the STAC search now or ask the user first."
    )
    intent: LoadIntent

    location: LocationSlot = Field(default_factory=LocationSlot)
    collection_candidates: List[CollectionCandidate] = Field(default_factory=list)
    datetime: DatetimeSlot = Field(default_factory=DatetimeSlot)
    deliverable: DeliverableKind = "single_layer"

    # Effective STAC search params when action == "execute".
    stac_query: Optional[str] = Field(
        None,
        description=(
            "Free-text or collection-id query to hand to /api/stac-search. "
            "Required when action='execute'."
        ),
    )

    # Clarification surface when action == "clarify".
    clarification_question: Optional[str] = Field(
        None, description="Exact text shown to user. Required when action='clarify'."
    )
    options: List[str] = Field(
        default_factory=list, description="Chip suggestions for the clarify turn."
    )

    # Always populated, even on clarify (the question itself can be the summary).
    chat_summary: str = Field(
        ...,
        description=(
            "Non-empty natural-language summary that the chat UI renders as "
            "the assistant answer for this turn."
        ),
        min_length=1,
    )

    confidence: float = Field(0.0, ge=0.0, le=1.0)
    reasoning: str = Field("", description="One-line internal explanation.")
