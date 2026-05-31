"""Message types passed between Site Intel MAF executors.

These are deliberately plain dataclasses (not Pydantic) so that pandas
DataFrames can be carried in ``RetrievalBundle`` without serialization
overhead. MAF messages don't need to be Pydantic — any picklable Python
object works.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import pandas as pd


# All six dimensions the workflow knows how to score. Kept here so both the
# planner (which selects a subset) and the aggregator (which weights the
# survivors) agree on the canonical names.
ALL_DIMENSIONS: tuple[str, ...] = (
    "power",
    "water",
    "hazards",
    "competition",
    "parcel_match",
    "precedent",
)


@dataclass
class SiteSpec:
    """Audit input — the raw payload sent to the workflow."""

    user_assertion: str
    lat: float
    lng: float
    claimed_mw: float = 200.0
    user_query: str | None = None
    workspace_id: str | None = None
    lakehouse_id: str | None = None


@dataclass
class PlannedSpec:
    """Output of :class:`PlannerExecutor` — wraps :class:`SiteSpec` with the
    planner's verdict on which dimensions to score and how to weight them.

    The planner is advisory — when ``SITE_PLANNER=0`` (default) it returns
    every dimension active with :data:`executors.DEFAULT_WEIGHTS`, giving the
    workflow byte-for-byte parity with v2.0. When enabled it can prune
    dimensions (e.g., skip ``competition`` for federal sites) and re-weight
    the survivors so the dossier reflects what actually mattered.
    """

    spec: SiteSpec
    active_dimensions: set[str]
    weights: dict[str, float]
    planner_reasoning: str = ""
    planner_engine: str = "default"  # "default" | "llm" | "fallback"


@dataclass
class RetrievalBundle:
    """Output of :class:`RetrievalExecutor` — fanned out to all 6 scorers.

    Carries the planner's verdict along with the Fabric frames so each scorer
    can short-circuit when its dimension is inactive.
    """

    spec: SiteSpec
    sites: pd.DataFrame
    power: pd.DataFrame
    water: pd.DataFrame
    dcs: pd.DataFrame
    workspace_id: str
    lakehouse_id: str
    active_dimensions: set[str] = field(default_factory=lambda: set(ALL_DIMENSIONS))
    weights: dict[str, float] = field(default_factory=dict)
    planner_reasoning: str = ""
    planner_engine: str = "default"


@dataclass
class DimensionResult:
    """One scoring agent's output — collected by :class:`AggregatorExecutor`.

    When ``skipped`` is True the scorer was a no-op (planner deselected the
    dimension) and ``score`` is None; the aggregator drops it from the
    weighted overall and re-normalizes.
    """

    dimension: str               # "power" | "water" | "hazards" | "competition" | "parcel_match" | "precedent"
    score: float | None          # 0-100, or None when skipped
    summary: str
    evidence: list[dict[str, Any]] = field(default_factory=list)
    provenance: list[dict[str, Any]] = field(default_factory=list)
    skipped: bool = False
