"""Open-Meteo connector — free public weather API used as a fallback.

Inert by default in the sense that it requires no auth and has no env
vars. Aurora / Earth-2 / MAI Weather take priority in the Forecast
Agent's provider routing; Open-Meteo is the "always works" floor so the
chat never fails because no Foundry endpoint is configured.

Cached in-process for 10 minutes per ``(lat, lon, hourly, days)`` key
to absorb chat retries and repeated identical questions.
"""
from __future__ import annotations

import asyncio
import logging
import time
from typing import Any

import httpx

logger = logging.getLogger(__name__)

_OPEN_METEO_URL = "https://api.open-meteo.com/v1/forecast"
_CACHE_TTL_SEC = 600
_TIMEOUT_SEC = 10.0


class OpenMeteoClient:
    """Stateless wrapper. Safe to share a single instance per process."""

    def __init__(self, base_url: str = _OPEN_METEO_URL, timeout_sec: float = _TIMEOUT_SEC) -> None:
        self.base_url = base_url
        self.timeout_sec = timeout_sec
        self._cache: dict[tuple[Any, ...], tuple[float, dict[str, Any]]] = {}
        self._lock = asyncio.Lock()

    async def forecast(
        self,
        lat: float,
        lon: float,
        *,
        hourly: tuple[str, ...] = ("temperature_2m", "precipitation"),
        days: int = 3,
    ) -> dict[str, Any]:
        """Return the raw Open-Meteo response as a dict."""
        key = (round(lat, 3), round(lon, 3), tuple(hourly), days)
        now = time.monotonic()
        async with self._lock:
            cached = self._cache.get(key)
            if cached is not None and (now - cached[0]) < _CACHE_TTL_SEC:
                return cached[1]
        params = {
            "latitude": lat,
            "longitude": lon,
            "hourly": ",".join(hourly),
            "forecast_days": days,
        }
        async with httpx.AsyncClient(timeout=self.timeout_sec) as client:
            resp = await client.get(self.base_url, params=params)
            resp.raise_for_status()
            data = resp.json()
        async with self._lock:
            self._cache[key] = (now, data)
        return data


_default: OpenMeteoClient | None = None


def get_client() -> OpenMeteoClient:
    """Process-wide singleton."""
    global _default
    if _default is None:
        _default = OpenMeteoClient()
    return _default
