"""Forecast Agent — multi-model atmospheric forecasting under the GEOINT
module surface.

Topology
--------
::

    ForecastQuery
        │
        ▼
    PlannerExecutor          (validate + decide which providers to call)
        │  fan-out
        ├──► ProviderExecutor("aurora-1.x")          # Microsoft Aurora
        ├──► ProviderExecutor("earth2-fcn")          # NVIDIA Earth-2 FCN
        └──► ProviderExecutor("mai-weather-1.x")     # Microsoft MAI Weather (Foundry)
        │  fan-in
        ▼
    AggregatorExecutor       (compose dossier, compute ensemble spread,
                              gracefully degrade if a provider failed)

Same gating idiom as Resilience: ``FORECAST_AGENT_ENABLED=1`` plus
``is_available()`` for the MAF import. Non-MAF code path
(``forecast_direct``) is also exposed so the API endpoint still works
when ``agent_framework`` isn't installed.
"""

from .workflow import (
    forecast,
    forecast_direct,
    is_available,
)
from .messages import (
    ForecastAgentQuery,
    ForecastDossier,
)

__all__ = [
    "forecast",
    "forecast_direct",
    "is_available",
    "ForecastAgentQuery",
    "ForecastDossier",
]
