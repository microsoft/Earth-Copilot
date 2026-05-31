"""Message types passed between Resilience MAF executors."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import pandas as pd


# Hazards the MVP scores. Adding a new hazard means adding a scorer in
# ``risk_scoring.py`` and including it here; the aggregator iterates over
# this tuple.
ALL_HAZARDS: tuple[str, ...] = ("heat", "wildfire")


@dataclass
class ResilienceQuery:
    """Assessment input — the payload sent to the workflow.

    A ``ResilienceQuery`` is region-scoped (``region_filter``) rather than
    pin-scoped: the workflow assesses every facility the caller has access
    to that matches the filter. Pass ``region_filter=None`` to assess the
    full facility registry.
    """

    user_assertion: str
    region_filter: str | None = None         # e.g. "TX" or "Texas"; None = all
    horizon_days: int = 7                    # forecast lookahead
    hazards: tuple[str, ...] = ALL_HAZARDS   # which hazard scorers to run
    user_query: str | None = None            # the natural-language ask
    workspace_id: str | None = None
    lakehouse_id: str | None = None


@dataclass
class FacilityRegistry:
    """Fabric-loaded (or seed-fallback) facility + supply-edge tables.

    Fanned out to all hazard scorers and the context executor.
    """

    query: ResilienceQuery
    facilities: pd.DataFrame                 # rows: facility_id, name, lat, lng, type, region, criticality, ...
    supply_edges: pd.DataFrame               # rows: src_facility_id, dst_facility_id, kind, lead_time_days, ...
    data_source: str                         # "fabric" | "seed"
    workspace_id: str | None = None
    lakehouse_id: str | None = None


@dataclass
class HazardForecast:
    """One hazard scorer's output for the whole facility set.

    Per-facility risk scores live in ``facility_risk`` keyed by facility_id.
    Aggregator stitches results from all hazards together.
    """

    hazard: str                              # "heat" | "wildfire" | ...
    facility_risk: dict[str, dict[str, Any]] # facility_id -> {score, severity, peak_value, peak_day, summary, drivers}
    evidence: list[dict[str, Any]] = field(default_factory=list)
    provenance: list[dict[str, Any]] = field(default_factory=list)
    skipped: bool = False


@dataclass
class SupplyImpact:
    """SupplyGraphExecutor output — propagated risk through edges.

    ``impacted_by`` maps a facility to the upstream facilities whose
    weather risk could disrupt it (with edge metadata).
    ``downstream_of`` is the inverse view used by the dashboard to show
    "if X is heat-stressed, who else is affected?".
    """

    impacted_by: dict[str, list[dict[str, Any]]]   # facility_id -> [{src_id, hazard, score, edge_kind, lead_time_days}]
    downstream_of: dict[str, list[dict[str, Any]]] # facility_id -> [{dst_id, hazard, score, edge_kind}]
    provenance: list[dict[str, Any]] = field(default_factory=list)


@dataclass
class ContextSnippets:
    """ContextExecutor output — relevant playbook / BCP doc snippets.

    Keyed by facility_id; each entry is a list of doc hits with the
    standard Azure AI Search shape (``id``, ``title``, ``content``,
    ``@search.score``, …).
    """

    docs_by_facility: dict[str, list[dict[str, Any]]]
    provenance: list[dict[str, Any]] = field(default_factory=list)


# Discriminated-union channel into the aggregator. MAF's fan-in delivers
# whichever subset of these the upstream executors emitted in a single
# ``list[ResilienceFanIn]`` to the aggregator handler.
ResilienceFanIn = HazardForecast | SupplyImpact | ContextSnippets
