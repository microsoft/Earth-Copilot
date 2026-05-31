"""Open-Meteo climatology client used by the Site Intel audit.

Why Open-Meteo? It's a free, no-auth, no-token public API with ERA5-backed
historical reanalysis for any global point. We use the Archive API to pull
one recent calendar year of daily summaries and compute a small set of
hazard-relevant indicators (annual max temp, days >35 C, annual precip,
max wind). The audit feeds those into the hazards dimension and surfaces
them as evidence/citation rows alongside the Fabric + MPC sources.

Design notes:
  • One HTTP call per audit, ~365 daily rows of small JSON. No paging.
  • All network I/O is async via aiohttp so it runs concurrent with the
    Fabric Delta loads and the MPC raster sampling.
  • Failures degrade gracefully — the helper returns ``None`` and the
    caller falls back to MPC-only hazard scoring.
  • Source / units / endpoint are surfaced verbatim so the chat renderer
    can build a proper citation row (matches the Public PC + Fabric
    citation pattern introduced in commit bc8a129).
"""

from __future__ import annotations

import asyncio
import logging
from datetime import date, timedelta
from typing import Any

import aiohttp

logger = logging.getLogger(__name__)

# Public Open-Meteo Archive API. No auth required.
# Docs: https://open-meteo.com/en/docs/historical-weather-api
_ARCHIVE_BASE = "https://archive-api.open-meteo.com/v1/archive"

# Single year of daily data is enough for hazard climatology proxies and
# keeps the response under ~30 kB. We use the most recent fully-closed
# calendar year so the audit is reproducible across runs within that year.
_REFERENCE_YEAR_OFFSET = 1  # last fully-closed year (e.g. 2025 -> use 2024)
_REQUEST_TIMEOUT_S = 12.0


def _reference_window() -> tuple[str, str, int]:
    """Return ``(start_iso, end_iso, year)`` for the climatology window.

    Uses the last fully-closed calendar year so two audits on the same day
    produce the same numbers (matters for the regulator-grade dossier the
    audit promises).
    """
    today = date.today()
    year = today.year - _REFERENCE_YEAR_OFFSET
    return (
        f"{year}-01-01",
        f"{year}-12-31",
        year,
    )


async def fetch_climate_indicators(
    lat: float,
    lng: float,
    *,
    session: aiohttp.ClientSession | None = None,
) -> dict[str, Any] | None:
    """Pull one year of ERA5 daily summaries and reduce to hazard signals.

    Returns ``None`` on failure (network, 5xx, parse error). Successful
    returns include ``source``, ``endpoint``, ``citation_url`` so the
    chat renderer can produce a proper citation row matching the
    "Public PC · ..." style we use for MPC.
    """
    start, end, year = _reference_window()
    params = {
        "latitude": f"{lat:.5f}",
        "longitude": f"{lng:.5f}",
        "start_date": start,
        "end_date": end,
        # ERA5-derived daily aggregates available worldwide:
        "daily": ",".join([
            "temperature_2m_max",
            "temperature_2m_min",
            "precipitation_sum",
            "wind_speed_10m_max",
        ]),
        "timezone": "UTC",
        # Wind in km/h is the API default; precip in mm; temp in C.
    }

    owns_session = session is None
    if owns_session:
        session = aiohttp.ClientSession()
    try:
        timeout = aiohttp.ClientTimeout(total=_REQUEST_TIMEOUT_S)
        async with session.get(_ARCHIVE_BASE, params=params, timeout=timeout) as r:
            if r.status != 200:
                body = (await r.text())[:200]
                logger.warning(
                    "[WEATHER] open-meteo %s returned %s: %s",
                    _ARCHIVE_BASE, r.status, body,
                )
                return None
            doc = await r.json()
    except (aiohttp.ClientError, asyncio.TimeoutError) as exc:
        logger.warning("[WEATHER] open-meteo request failed: %s", exc)
        return None
    finally:
        if owns_session:
            await session.close()

    daily = (doc or {}).get("daily") or {}
    tmax: list[float | None] = daily.get("temperature_2m_max") or []
    tmin: list[float | None] = daily.get("temperature_2m_min") or []
    precip: list[float | None] = daily.get("precipitation_sum") or []
    wind: list[float | None] = daily.get("wind_speed_10m_max") or []

    def _num(seq: list[float | None]) -> list[float]:
        return [float(x) for x in seq if x is not None]

    tmax_n, tmin_n = _num(tmax), _num(tmin)
    precip_n, wind_n = _num(precip), _num(wind)
    if not tmax_n:
        # Open-Meteo returns empty arrays for some grid cells (e.g., far
        # offshore). Without daily temps we have nothing to score; bail
        # out the same way a transport error would.
        logger.info(
            "[WEATHER] open-meteo returned no daily data for (%s, %s)",
            lat, lng,
        )
        return None

    days_over_35 = sum(1 for t in tmax_n if t >= 35.0)
    days_under_minus10 = sum(1 for t in tmin_n if t <= -10.0)
    days_precip_over_25mm = sum(1 for p in precip_n if p >= 25.0)
    annual_precip_mm = round(sum(precip_n), 1) if precip_n else None
    max_temp_c = round(max(tmax_n), 1)
    min_temp_c = round(min(tmin_n), 1) if tmin_n else None
    max_wind_kmh = round(max(wind_n), 1) if wind_n else None

    return {
        "source": "open_meteo",
        "endpoint": _ARCHIVE_BASE,
        "model": "ERA5",
        "reference_year": year,
        "lat": round(lat, 5),
        "lng": round(lng, 5),
        # Hazard indicators
        "max_temp_c": max_temp_c,
        "min_temp_c": min_temp_c,
        "days_over_35c": days_over_35,
        "days_under_minus10c": days_under_minus10,
        "annual_precip_mm": annual_precip_mm,
        "days_precip_over_25mm": days_precip_over_25mm,
        "max_wind_kmh": max_wind_kmh,
        # Citation: Open-Meteo doesn't host a per-point landing page, so
        # we link to the query URL itself which renders the JSON the
        # audit consumed. Reviewers can replay the call exactly.
        "citation_url": (
            f"{_ARCHIVE_BASE}?latitude={lat:.5f}&longitude={lng:.5f}"
            f"&start_date={start}&end_date={end}&daily={params['daily']}"
        ),
        "docs_url": "https://open-meteo.com/en/docs/historical-weather-api",
    }


def score_climate_impact(indicators: dict[str, Any] | None) -> tuple[float, list[str]]:
    """Translate climate indicators into a (delta, notes) tuple.

    The returned ``delta`` is a *cap* — the hazards dimension takes the
    minimum of its existing score and ``70 + delta`` so extreme climates
    pull the score down but a mild climate doesn't artificially inflate
    it. Notes are appended to the dimension summary so the user sees
    why the score moved.
    """
    if not indicators:
        return 0.0, []
    notes: list[str] = []
    cap_candidates: list[float] = []

    days_hot = int(indicators.get("days_over_35c") or 0)
    if days_hot >= 60:
        cap_candidates.append(45.0)
        notes.append(f"extreme heat exposure ({days_hot} days/yr ≥35°C)")
    elif days_hot >= 30:
        cap_candidates.append(60.0)
        notes.append(f"high heat exposure ({days_hot} days/yr ≥35°C)")
    elif days_hot >= 10:
        notes.append(f"moderate heat exposure ({days_hot} days/yr ≥35°C)")

    precip = float(indicators.get("annual_precip_mm") or 0.0)
    if precip >= 1800:
        cap_candidates.append(60.0)
        notes.append(f"very wet climate ({precip:.0f} mm/yr) — flood-risk proxy")
    elif precip <= 200:
        notes.append(f"arid climate ({precip:.0f} mm/yr) — cooling-water proxy concern")

    wind = float(indicators.get("max_wind_kmh") or 0.0)
    if wind >= 110:
        cap_candidates.append(65.0)
        notes.append(f"high peak wind ({wind:.0f} km/h)")

    cap = min(cap_candidates) if cap_candidates else 100.0
    return cap, notes
