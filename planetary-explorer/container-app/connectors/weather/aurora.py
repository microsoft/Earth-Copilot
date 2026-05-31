"""Microsoft Aurora 1.x provider.

Pointed at the CPU stub today (``/aurora/score``). When the real Foundry
endpoint is provisioned, change ``AURORA_ENDPOINT_URL`` — agent code is
unchanged.

Env vars:
    AURORA_ENDPOINT_URL   base URL (must respond to POST /aurora/score and GET /health)
    AURORA_API_KEY        optional bearer token

The stub also exposes ``/aurora/score``; Foundry's real Aurora deployment
exposes its scoring URI directly so set ``AURORA_SCORE_PATH=/score``
when you swap.
"""
from __future__ import annotations

import os

from . import _http
from .provider import Capability, ForecastBundle, ForecastQuery, HealthStatus


class AuroraProvider:
    provider_id = "aurora-1.x"
    vendor = "Microsoft"
    capabilities: tuple[Capability, ...] = (
        Capability.GLOBAL,
        Capability.MEDIUM_RANGE_10D,
        Capability.CYCLONE_TRACKS,
    )

    def __init__(self, endpoint_url: str, api_key: str | None, score_path: str = "/aurora/score") -> None:
        self.endpoint_url = endpoint_url
        self.api_key = api_key
        self.score_path = score_path

    @classmethod
    def try_from_env(cls) -> "AuroraProvider | None":
        url = os.getenv("AURORA_ENDPOINT_URL")
        if not url:
            return None
        return cls(
            endpoint_url=url,
            api_key=os.getenv("AURORA_API_KEY") or None,
            score_path=os.getenv("AURORA_SCORE_PATH", "/aurora/score"),
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
            extra_response_keys=("cyclone_tracks",),
        )

    async def health(self) -> HealthStatus:
        return await _http.call_health(self.endpoint_url, self.api_key, self.provider_id)
