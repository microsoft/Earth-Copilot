"""Microsoft AI Weather (MAI Weather) provider.

MAI Weather is Microsoft's productized AI weather forecasting endpoint —
the Foundry-hosted sibling of the Aurora research model. Same provider
contract as Aurora and Earth-2: capability-tagged ``WeatherModelProvider``
that the Forecast Agent picks from based on query characteristics.

Today this is *inert*: the provider only activates when
``MAI_WEATHER_ENDPOINT_URL`` is set. With no endpoint URL the registry
silently skips it so existing behaviour is unchanged. When the real
Foundry endpoint is provisioned, set the env vars and the agent picks it
up automatically.

Env vars:
    MAI_WEATHER_ENDPOINT_URL   base URL of the Foundry deployment
    MAI_WEATHER_API_KEY        optional bearer token (omit for Managed Identity)
    MAI_WEATHER_SCORE_PATH     scoring path (default ``/score``)
"""
from __future__ import annotations

import os

from . import _http
from .provider import Capability, ForecastBundle, ForecastQuery, HealthStatus


class MaiWeatherProvider:
    provider_id = "mai-weather-1.x"
    vendor = "Microsoft"
    # Conservative capability set — Foundry MAI Weather is global medium-range
    # in the public preview. Add KM_SCALE / CYCLONE_TRACKS once the endpoint
    # contract confirms those outputs.
    capabilities: tuple[Capability, ...] = (
        Capability.GLOBAL,
        Capability.MEDIUM_RANGE_10D,
    )

    def __init__(
        self,
        endpoint_url: str,
        api_key: str | None,
        score_path: str = "/score",
    ) -> None:
        self.endpoint_url = endpoint_url
        self.api_key = api_key
        self.score_path = score_path

    @classmethod
    def try_from_env(cls) -> "MaiWeatherProvider | None":
        url = os.getenv("MAI_WEATHER_ENDPOINT_URL")
        if not url:
            return None
        return cls(
            endpoint_url=url,
            api_key=os.getenv("MAI_WEATHER_API_KEY") or None,
            score_path=os.getenv("MAI_WEATHER_SCORE_PATH", "/score"),
        )

    async def forecast(self, query: ForecastQuery) -> ForecastBundle:
        return await _http.call_score_endpoint(
            endpoint_url=self.endpoint_url,
            score_path=self.score_path,
            api_key=self.api_key,
            query=query,
            provider_id=self.provider_id,
            vendor=self.vendor,
            capabilities=self.capabilities,
        )

    async def health(self) -> HealthStatus:
        return await _http.call_health(self.endpoint_url, self.api_key, self.provider_id)
