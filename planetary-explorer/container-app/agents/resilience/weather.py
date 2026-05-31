"""Weather forecast adapter — Open-Meteo.

Open-Meteo is a free, no-key, low-rate weather API suitable for an MVP.
For production we'd front this with NOAA NDFD + ECMWF + ECMWF-AIFS
ensembles via a paid provider, but the call signature here is the same:

    ``fetch_forecasts(points, horizon_days)``  →  list[FacilityForecast]

so swapping in a different provider is a one-file change.

Free tier reference: https://open-meteo.com/en/docs
"""

from __future__ import annotations

import asyncio
import logging
import os
from dataclasses import dataclass, field
from typing import Any

import httpx

logger = logging.getLogger(__name__)

OPEN_METEO_URL = os.getenv(
    "RESILIENCE_OPEN_METEO_URL",
    "https://api.open-meteo.com/v1/forecast",
)
OPEN_METEO_AQI_URL = os.getenv(
    "RESILIENCE_OPEN_METEO_AQI_URL",
    "https://air-quality-api.open-meteo.com/v1/air-quality",
)

# httpx timeout — Open-Meteo is fast (~200 ms), but we batch up to 10
# requests concurrently so the upper bound matters during cold starts.
_HTTPX_TIMEOUT = httpx.Timeout(15.0, connect=5.0)

# Cache: { (round(lat,2), round(lng,2), horizon, kind): (loaded_at, payload) }
# The Resilience workflow runs the same set of facilities repeatedly during
# a session — we don't need to re-hit Open-Meteo every time the user reloads.
_CACHE: dict[tuple, tuple[float, dict[str, Any]]] = {}
_CACHE_TTL_SEC = 900   # 15 minutes is fine for a 7-day forecast


@dataclass
class FacilityForecast:
    """Per-facility forecast bundle returned by :func:`fetch_forecasts`."""

    facility_id: str
    lat: float
    lng: float
    horizon_days: int
    daily: dict[str, list[Any]] = field(default_factory=dict)
    # Optional air-quality block (PM2.5, AQI) — populated when
    # ``fetch_air_quality`` is included in the request.
    aqi_daily: dict[str, list[Any]] = field(default_factory=dict)
    provider: str = "open-meteo"
    error: str | None = None


def _cache_key(lat: float, lng: float, horizon: int, kind: str) -> tuple:
    return (round(lat, 2), round(lng, 2), int(horizon), kind)


async def _fetch_one(
    client: httpx.AsyncClient,
    *,
    lat: float,
    lng: float,
    horizon: int,
    include_aqi: bool,
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Fetch the daily forecast (+ optional AQI) for a single point.

    Returns ``(forecast_payload, aqi_payload)``. Either may be ``{}`` if the
    request failed; the error is logged but not raised — partial-failure is
    acceptable for the MVP.
    """
    import time

    now = time.time()
    fc_key = _cache_key(lat, lng, horizon, "fc")
    aqi_key = _cache_key(lat, lng, horizon, "aqi")

    cached_fc = _CACHE.get(fc_key)
    if cached_fc and (now - cached_fc[0]) < _CACHE_TTL_SEC:
        fc_payload = cached_fc[1]
    else:
        params = {
            "latitude": lat,
            "longitude": lng,
            "daily": ",".join([
                "temperature_2m_max",
                "temperature_2m_min",
                "apparent_temperature_max",
                "precipitation_sum",
                "wind_speed_10m_max",
                "wind_gusts_10m_max",
                "relative_humidity_2m_max",
            ]),
            "temperature_unit": "fahrenheit",
            "wind_speed_unit": "mph",
            "precipitation_unit": "inch",
            "forecast_days": horizon,
            "timezone": "auto",
        }
        try:
            r = await client.get(OPEN_METEO_URL, params=params)
            r.raise_for_status()
            fc_payload = r.json()
            _CACHE[fc_key] = (now, fc_payload)
        except Exception as exc:  # noqa: BLE001 — partial failure is OK
            logger.warning("[RESILIENCE] open-meteo fc lat=%.3f lng=%.3f failed: %s", lat, lng, exc)
            fc_payload = {}

    if not include_aqi:
        return fc_payload, {}

    cached_aqi = _CACHE.get(aqi_key)
    if cached_aqi and (now - cached_aqi[0]) < _CACHE_TTL_SEC:
        return fc_payload, cached_aqi[1]

    # Open-Meteo's air-quality API doesn't accept a `daily=` aggregation
    # parameter (returns HTTP 400). Fetch hourly PM2.5 + US AQI and roll
    # them up to per-day maxima client-side so the rest of the pipeline
    # can keep reading ``aqi_daily`` with the same shape as the forecast
    # endpoint.
    aqi_params = {
        "latitude": lat,
        "longitude": lng,
        "hourly": ",".join(["pm2_5", "us_aqi"]),
        "forecast_days": horizon,
        "timezone": "auto",
    }
    try:
        r = await client.get(OPEN_METEO_AQI_URL, params=aqi_params)
        r.raise_for_status()
        hourly_payload = r.json()
        aqi_payload = _aqi_hourly_to_daily(hourly_payload)
        _CACHE[aqi_key] = (now, aqi_payload)
    except Exception as exc:  # noqa: BLE001 — partial failure is OK
        logger.warning("[RESILIENCE] open-meteo aqi lat=%.3f lng=%.3f failed: %s", lat, lng, exc)
        aqi_payload = {}

    return fc_payload, aqi_payload


def _aqi_hourly_to_daily(payload: dict[str, Any]) -> dict[str, Any]:
    """Roll Open-Meteo hourly AQI rows into a daily-max shape.

    Returns ``{"time": [YYYY-MM-DD, ...], "pm2_5_max": [...], "us_aqi_max": [...]}``
    so callers can treat the air-quality response the same way they treat
    the forecast endpoint's ``daily`` block.
    """
    hourly = payload.get("hourly") or {}
    times: list[str] = list(hourly.get("time") or [])
    pm: list[Any] = list(hourly.get("pm2_5") or [])
    aqi: list[Any] = list(hourly.get("us_aqi") or [])
    if not times:
        return {}
    days: list[str] = []
    pm_max: dict[str, float] = {}
    aqi_max: dict[str, float] = {}
    for i, t in enumerate(times):
        day = str(t)[:10]
        if day not in pm_max:
            days.append(day)
            pm_max[day] = float("-inf")
            aqi_max[day] = float("-inf")
        try:
            pv = float(pm[i]) if i < len(pm) and pm[i] is not None else None
            if pv is not None and pv > pm_max[day]:
                pm_max[day] = pv
        except (TypeError, ValueError):
            pass
        try:
            av = float(aqi[i]) if i < len(aqi) and aqi[i] is not None else None
            if av is not None and av > aqi_max[day]:
                aqi_max[day] = av
        except (TypeError, ValueError):
            pass
    return {
        "daily": {
            "time": days,
            "pm2_5_max": [None if pm_max[d] == float("-inf") else round(pm_max[d], 1) for d in days],
            "us_aqi_max": [None if aqi_max[d] == float("-inf") else round(aqi_max[d], 0) for d in days],
        },
    }


async def fetch_forecasts(
    points: list[dict[str, Any]],
    *,
    horizon_days: int = 7,
    include_aqi: bool = True,
) -> list[FacilityForecast]:
    """Fetch daily forecasts for a batch of points concurrently.

    ``points`` is a list of dicts with ``facility_id``, ``lat``, ``lng``.
    Returns one :class:`FacilityForecast` per input row, in the same order.
    On a per-point failure the corresponding result has empty ``daily`` and
    populated ``error`` — the caller decides how to surface that to the
    user (the MVP just downgrades the affected hazard score to ``low``).
    """
    if not points:
        return []

    async with httpx.AsyncClient(timeout=_HTTPX_TIMEOUT) as client:
        tasks = [
            _fetch_one(
                client,
                lat=float(p["lat"]),
                lng=float(p["lng"]),
                horizon=horizon_days,
                include_aqi=include_aqi,
            )
            for p in points
        ]
        results = await asyncio.gather(*tasks, return_exceptions=False)

    out: list[FacilityForecast] = []
    for p, (fc, aqi) in zip(points, results):
        daily = fc.get("daily", {}) if isinstance(fc, dict) else {}
        aqi_daily = aqi.get("daily", {}) if isinstance(aqi, dict) else {}
        out.append(FacilityForecast(
            facility_id=str(p["facility_id"]),
            lat=float(p["lat"]),
            lng=float(p["lng"]),
            horizon_days=horizon_days,
            daily=daily,
            aqi_daily=aqi_daily,
            error=None if daily else "open-meteo forecast unavailable",
        ))
    return out
