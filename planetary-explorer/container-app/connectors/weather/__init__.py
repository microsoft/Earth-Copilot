"""Weather model connectors — provider abstraction over Aurora / Earth-2.

The Forecast Agent never talks to a specific model. It talks to a
:class:`WeatherModelProvider` instance. Today those instances point at
the local CPU stub; tomorrow they point at a real Foundry / AzureML
GPU endpoint with no code change.
"""

from .provider import (
    Capability,
    ForecastBundle,
    ForecastQuery,
    HealthStatus,
    WeatherModelProvider,
)
from .registry import WeatherProviderRegistry, get_registry

__all__ = [
    "Capability",
    "ForecastBundle",
    "ForecastQuery",
    "HealthStatus",
    "WeatherModelProvider",
    "WeatherProviderRegistry",
    "get_registry",
]
