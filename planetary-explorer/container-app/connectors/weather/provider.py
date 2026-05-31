"""Provider abstraction for AI weather models.

Three implementations today (``AuroraProvider``, ``Earth2FCNProvider``,
``MaiWeatherProvider``). Aurora + Earth-2 FCN point at the CPU stub by
default; MAI Weather is inert until ``MAI_WEATHER_ENDPOINT_URL`` is set.
When real Foundry / AzureML GPU endpoints come online, only the env
vars change.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Protocol, runtime_checkable


class Capability(str, Enum):
    """What a model can do. The ModelSelector routes by capability, not name."""

    GLOBAL = "GLOBAL"
    REGIONAL = "REGIONAL"
    MEDIUM_RANGE_10D = "MEDIUM_RANGE_10D"        # up to 10 days
    LONG_RANGE_14D_PLUS = "LONG_RANGE_14D_PLUS"  # 14+ days
    CYCLONE_TRACKS = "CYCLONE_TRACKS"            # named-storm tracking
    KM_SCALE = "KM_SCALE"                        # convection-resolving


@dataclass
class ForecastQuery:
    """Caller's intent — what they want forecasted."""

    lat: float
    lon: float
    lead_hours: int = 72
    variables: tuple[str, ...] = ("t2m", "precip")
    grid_size: int = 8
    required_capabilities: tuple[Capability, ...] = (Capability.GLOBAL,)


@dataclass
class ForecastBundle:
    """One model's forecast output, normalized.

    Provider-specific extras (e.g. Aurora's ``cyclone_tracks``) live in
    ``extras`` so the aggregator can fold them in without losing them.
    """

    provider_id: str          # "aurora-1.x", "earth2-fcn", "mai-weather-1.x"
    vendor: str               # "Microsoft", "NVIDIA"
    issued_at: str            # ISO-8601
    valid_at: str             # ISO-8601
    lead_hours: int
    grid: dict[str, list[float]]                     # {"lat":[...], "lon":[...]}
    variables: dict[str, list[list[float]]]          # var -> NxN field
    units: dict[str, str]
    capabilities: tuple[Capability, ...] = field(default_factory=tuple)
    extras: dict[str, Any] = field(default_factory=dict)
    stub: bool = False
    latency_ms: int | None = None


@dataclass
class HealthStatus:
    provider_id: str
    healthy: bool
    detail: str = ""
    endpoint: str | None = None


@runtime_checkable
class WeatherModelProvider(Protocol):
    """The single interface the Forecast Agent depends on."""

    provider_id: str
    vendor: str
    capabilities: tuple[Capability, ...]

    @classmethod
    def try_from_env(cls) -> "WeatherModelProvider | None":
        """Return an instance if env vars are configured, else None."""
        ...

    async def forecast(self, query: ForecastQuery) -> ForecastBundle:
        """Call the underlying scoring endpoint."""
        ...

    async def health(self) -> HealthStatus:
        """Cheap readiness check."""
        ...
