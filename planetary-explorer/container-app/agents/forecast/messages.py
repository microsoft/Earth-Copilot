"""Message types passed between Forecast MAF executors."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from connectors.weather import ForecastBundle


DEFAULT_VARIABLES: tuple[str, ...] = ("t2m", "precip", "u10", "v10")


@dataclass
class ForecastAgentQuery:
    """Public agent input — what the API endpoint passes in."""

    lat: float
    lon: float
    lead_hours: int = 72
    variables: tuple[str, ...] = DEFAULT_VARIABLES
    grid_size: int = 8
    requested_providers: tuple[str, ...] = ()   # () = all configured
    user_query: str | None = None               # natural-language ask, for the LLM-free PoC just echoed back
    location_label: str | None = None           # optional human-readable label


@dataclass
class ForecastPlan:
    """Output of the planner — which providers to call."""

    query: ForecastAgentQuery
    provider_ids: tuple[str, ...]
    reason: str


@dataclass
class ProviderResult:
    """Fan-in unit — one provider's bundle or its failure."""

    provider_id: str
    vendor: str
    bundle: ForecastBundle | None
    error: str | None = None
    latency_ms: int | None = None


@dataclass
class ForecastDossier:
    """Final API payload."""

    input: dict[str, Any]
    providers_called: list[str]
    providers_succeeded: list[str]
    providers_failed: list[dict[str, str]]
    forecasts: list[dict[str, Any]]
    ensemble_summary: dict[str, Any] = field(default_factory=dict)
    location: dict[str, Any] = field(default_factory=dict)
    timing_ms: dict[str, int] = field(default_factory=dict)
    routing: dict[str, Any] = field(default_factory=dict)
    note: str = ""
