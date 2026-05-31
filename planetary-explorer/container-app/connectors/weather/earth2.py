"""NVIDIA Earth-2 FourCastNet (FCN / FCNv2-SFNO) provider.

Today: CPU stub. Tomorrow: a deployed NIM container on an A100. Same
HTTP contract.

Env vars:
    EARTH2_FCN_ENDPOINT_URL   base URL
    EARTH2_FCN_API_KEY        optional bearer token
    EARTH2_FCN_SCORE_PATH     defaults to ``/earth2/fcn/score`` for stub;
                              set to ``/v1/infer`` (or whatever NIM uses)
                              when swapping to real NIM.
"""
from __future__ import annotations

import os

from . import _http
from .provider import Capability, ForecastBundle, ForecastQuery, HealthStatus


class Earth2FCNProvider:
    provider_id = "earth2-fcn"
    vendor = "NVIDIA"
    capabilities: tuple[Capability, ...] = (
        Capability.GLOBAL,
        Capability.MEDIUM_RANGE_10D,
    )

    def __init__(self, endpoint_url: str, api_key: str | None, score_path: str = "/earth2/fcn/score") -> None:
        self.endpoint_url = endpoint_url
        self.api_key = api_key
        self.score_path = score_path

    @classmethod
    def try_from_env(cls) -> "Earth2FCNProvider | None":
        url = os.getenv("EARTH2_FCN_ENDPOINT_URL")
        if not url:
            return None
        return cls(
            endpoint_url=url,
            api_key=os.getenv("EARTH2_FCN_API_KEY") or None,
            score_path=os.getenv("EARTH2_FCN_SCORE_PATH", "/earth2/fcn/score"),
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
