"""Deterministic per-facility hazard scoring.

Each scorer:

  1. Takes a :class:`weather.FacilityForecast` and the facility's row from
     the registry (a pd.Series).
  2. Returns ``{score, severity, peak_value, peak_day, summary, drivers}``.

Scores are 0-100 where higher = more risk (opposite of Site Intel, where
higher = better candidate site). This is intentional: Resilience is a
risk product, so "high score" must read as "needs attention".

Thresholds are tunable via env vars so the same scoring runs against
either Texas or, say, Arizona without code changes.
"""

from __future__ import annotations

import logging
import os
from typing import Any

import pandas as pd

from .weather import FacilityForecast

logger = logging.getLogger(__name__)


# Heat thresholds — defaults are reasonable for Texas industrial sites.
HEAT_WATCH_F = float(os.getenv("RESILIENCE_HEAT_WATCH_F", "95"))
HEAT_WARNING_F = float(os.getenv("RESILIENCE_HEAT_WARN_F", "100"))
HEAT_EMERGENCY_F = float(os.getenv("RESILIENCE_HEAT_EMERG_F", "105"))

# Wildfire / smoke thresholds.
PM25_MODERATE = float(os.getenv("RESILIENCE_PM25_MODERATE", "12"))   # µg/m³
PM25_UNHEALTHY = float(os.getenv("RESILIENCE_PM25_UNHEALTHY", "35"))
PM25_HAZARDOUS = float(os.getenv("RESILIENCE_PM25_HAZARDOUS", "55"))


def _severity_from_score(score: float) -> str:
    """Bucket a 0-100 risk score into a label the UI can colour."""
    if score < 25:
        return "low"
    if score < 55:
        return "moderate"
    if score < 80:
        return "high"
    return "severe"


def _max_with_day(values: list[Any], days: list[Any]) -> tuple[float | None, str | None]:
    """Return (max_value, day_iso) ignoring None entries. Empty -> (None, None)."""
    if not values:
        return None, None
    best_v: float | None = None
    best_d: str | None = None
    for v, d in zip(values, days):
        if v is None:
            continue
        try:
            fv = float(v)
        except (TypeError, ValueError):
            continue
        if best_v is None or fv > best_v:
            best_v = fv
            best_d = str(d) if d is not None else None
    return best_v, best_d


def _consecutive_above(values: list[Any], threshold: float) -> int:
    """Longest run of consecutive days where value >= threshold."""
    longest = 0
    current = 0
    for v in values:
        try:
            fv = float(v) if v is not None else None
        except (TypeError, ValueError):
            fv = None
        if fv is not None and fv >= threshold:
            current += 1
            longest = max(longest, current)
        else:
            current = 0
    return longest


def score_heat(forecast: FacilityForecast, facility: pd.Series) -> dict[str, Any]:
    """Score heat-dome risk for one facility.

    Combines:
      * Peak apparent (feels-like) temperature against the facility's
        ``heat_threshold_f`` (with a global default).
      * Number of consecutive days above the facility threshold.
      * Criticality multiplier (a fab matters more than a yard).

    Output is a single 0-100 score that the aggregator carries into the
    dashboard. No probabilistic model in the MVP — interpretable
    threshold logic is more useful for demos.
    """
    if not forecast.daily or forecast.error:
        return {
            "score": 0.0,
            "severity": "low",
            "peak_value": None,
            "peak_day": None,
            "summary": f"Forecast unavailable ({forecast.error or 'no data'})",
            "drivers": [],
        }

    days = forecast.daily.get("time", [])
    feels_like = forecast.daily.get("apparent_temperature_max", [])
    raw_max = forecast.daily.get("temperature_2m_max", [])
    # Prefer feels-like when present, fall back to raw max.
    series = feels_like if any(v is not None for v in feels_like) else raw_max

    peak_v, peak_d = _max_with_day(series, days)
    if peak_v is None:
        return {
            "score": 0.0,
            "severity": "low",
            "peak_value": None,
            "peak_day": None,
            "summary": "No temperature values in forecast.",
            "drivers": [],
        }

    facility_threshold = float(facility.get("heat_threshold_f") or HEAT_WARNING_F)
    consecutive = _consecutive_above(series, facility_threshold)
    criticality = float(facility.get("criticality") or 0.5)

    # Base score by peak temperature relative to thresholds.
    if peak_v >= HEAT_EMERGENCY_F:
        base = 85.0 + min((peak_v - HEAT_EMERGENCY_F) * 3.0, 15.0)
    elif peak_v >= HEAT_WARNING_F:
        base = 55.0 + (peak_v - HEAT_WARNING_F) * (30.0 / max(HEAT_EMERGENCY_F - HEAT_WARNING_F, 1.0))
    elif peak_v >= HEAT_WATCH_F:
        base = 25.0 + (peak_v - HEAT_WATCH_F) * (30.0 / max(HEAT_WARNING_F - HEAT_WATCH_F, 1.0))
    else:
        base = max(0.0, (peak_v - 80.0) * (25.0 / max(HEAT_WATCH_F - 80.0, 1.0)))

    # Duration penalty: each consecutive day above threshold adds up to 15.
    duration_bonus = min(consecutive, 5) * 3.0

    # Criticality scales the WHOLE risk by 0.7-1.15 — a critical fab gets
    # boosted, a low-criticality DC is slightly dampened.
    score = (base + duration_bonus) * (0.7 + 0.45 * criticality)
    score = max(0.0, min(100.0, score))

    drivers: list[str] = []
    drivers.append(f"Peak feels-like {peak_v:.0f}°F on {peak_d}")
    if consecutive >= 2:
        drivers.append(f"{consecutive} consecutive days ≥ facility threshold ({facility_threshold:.0f}°F)")
    if criticality >= 0.75:
        drivers.append(f"High facility criticality ({criticality:.2f})")
    if peak_v >= HEAT_EMERGENCY_F:
        drivers.append("Peak exceeds extreme-heat emergency threshold (105°F)")

    # Compose a human summary — only mention the consecutive-day streak
    # when it actually fired (≥ 1 day above the facility threshold).
    # Otherwise the line reads "0d streak ≥ 100°F" which is noise.
    if consecutive >= 1:
        streak_suffix = (
            f"; {consecutive}-day streak ≥ {facility_threshold:.0f}°F"
            if consecutive == 1
            else f"; {consecutive} consecutive days ≥ {facility_threshold:.0f}°F"
        )
    else:
        streak_suffix = ""
    summary = f"Peak feels-like {peak_v:.0f}°F on {peak_d}{streak_suffix}."

    return {
        "score": round(score, 1),
        "severity": _severity_from_score(score),
        "peak_value": round(peak_v, 1),
        "peak_day": peak_d,
        "summary": summary,
        "drivers": drivers,
        "consecutive_days": consecutive,
        "facility_threshold_f": facility_threshold,
    }


def score_wildfire(forecast: FacilityForecast, facility: pd.Series) -> dict[str, Any]:
    """Score wildfire / smoke risk.

    MVP heuristic: combine peak PM2.5 from the AQI forecast with peak
    wind-gust and (inverse) precipitation. A real implementation would
    bring in NIFC perimeter feeds and red-flag warnings; that's a
    follow-up.
    """
    if not forecast.daily or forecast.error:
        return {
            "score": 0.0,
            "severity": "low",
            "peak_value": None,
            "peak_day": None,
            "summary": f"Forecast unavailable ({forecast.error or 'no data'})",
            "drivers": [],
        }

    days = forecast.daily.get("time", [])
    pm25_series = forecast.aqi_daily.get("pm2_5_max", []) if forecast.aqi_daily else []
    aqi_series = forecast.aqi_daily.get("us_aqi_max", []) if forecast.aqi_daily else []
    gusts = forecast.daily.get("wind_gusts_10m_max", [])
    precip = forecast.daily.get("precipitation_sum", [])

    pm_peak, pm_day = _max_with_day(pm25_series, days)
    aqi_peak, _ = _max_with_day(aqi_series, days)
    gust_peak, _ = _max_with_day(gusts, days)
    total_precip = sum((float(p) for p in precip if p is not None), 0.0) if precip else 0.0

    if pm_peak is None and aqi_peak is None and gust_peak is None:
        return {
            "score": 0.0,
            "severity": "low",
            "peak_value": None,
            "peak_day": None,
            "summary": "No wildfire-relevant signals in forecast.",
            "drivers": [],
        }

    # PM2.5 component (0-60)
    if pm_peak is None:
        pm_component = 0.0
    elif pm_peak >= PM25_HAZARDOUS:
        pm_component = 60.0
    elif pm_peak >= PM25_UNHEALTHY:
        pm_component = 35.0 + (pm_peak - PM25_UNHEALTHY) * (25.0 / max(PM25_HAZARDOUS - PM25_UNHEALTHY, 1.0))
    elif pm_peak >= PM25_MODERATE:
        pm_component = 10.0 + (pm_peak - PM25_MODERATE) * (25.0 / max(PM25_UNHEALTHY - PM25_MODERATE, 1.0))
    else:
        pm_component = max(0.0, pm_peak * (10.0 / PM25_MODERATE))

    # Fire-weather component (0-25): high gusts + dry air = elevated risk.
    gust_component = 0.0
    if gust_peak is not None:
        gust_component = max(0.0, min(25.0, (gust_peak - 20.0) * 0.8))
        # Heavy precip damps the risk.
        if total_precip > 0.5:
            gust_component *= 0.4

    criticality = float(facility.get("criticality") or 0.5)
    score = (pm_component + gust_component) * (0.7 + 0.45 * criticality)
    score = max(0.0, min(100.0, score))

    drivers: list[str] = []
    if pm_peak is not None:
        drivers.append(f"Peak PM2.5 {pm_peak:.0f} µg/m³ on {pm_day}")
    if aqi_peak is not None:
        drivers.append(f"Peak US AQI {aqi_peak:.0f}")
    if gust_peak is not None and gust_peak >= 25:
        drivers.append(f"Peak wind gust {gust_peak:.0f} mph")
    if total_precip < 0.05:
        drivers.append("Effectively dry forecast week")

    peak_value = pm_peak if pm_peak is not None else (aqi_peak or 0.0)
    if pm_peak is not None:
        summary_head = f"PM2.5 peak {pm_peak:.0f} µg/m³"
    elif aqi_peak is not None:
        summary_head = f"AQI peak {aqi_peak:.0f}"
    else:
        summary_head = "Air-quality data unavailable"
    summary = summary_head + (
        f"; gusts to {gust_peak:.0f} mph"
        if gust_peak is not None and gust_peak >= 25
        else ""
    )

    return {
        "score": round(score, 1),
        "severity": _severity_from_score(score),
        "peak_value": round(peak_value, 1) if peak_value is not None else None,
        "peak_day": pm_day,
        "summary": summary,
        "drivers": drivers,
        "total_precip_in": round(total_precip, 2),
    }


SCORERS = {
    "heat": score_heat,
    "wildfire": score_wildfire,
}
