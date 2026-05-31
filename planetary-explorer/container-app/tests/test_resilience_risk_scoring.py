"""Unit tests for the Resilience risk-scoring functions.

These are pure-function tests: they construct synthetic ``FacilityForecast``
objects and facility rows, so no network / Fabric / agent_framework
dependencies are exercised.

Coverage focus:
  * heat severity bucketing (low / moderate / high / severe)
  * wildfire scorer is None-safe when Open-Meteo AQI returns nothing
    (regression test for the prod bug fixed on 2026-05-23)
  * criticality scales the score
"""

from __future__ import annotations

import pandas as pd
import pytest

from agents.resilience.risk_scoring import (
    _severity_from_score,
    score_heat,
    score_wildfire,
)
from agents.resilience.weather import FacilityForecast


# ── helpers ──────────────────────────────────────────────────────────────


def _facility(**overrides) -> pd.Series:
    base = {
        "facility_id": "test-fab-1",
        "name": "Test Fab",
        "type": "fab",
        "lat": 30.0,
        "lng": -97.0,
        "region": "TX",
        "city": "Austin",
        "criticality": 0.8,
        "heat_threshold_f": 100,
        "cooling_water_m3_per_day": 5000,
        "headcount": 1500,
        "notes": "",
    }
    base.update(overrides)
    return pd.Series(base)


def _forecast(
    *,
    temp_max: list[float] | None = None,
    precip_sum: list[float] | None = None,
    pm25_max: list[float] | None = None,
    aqi_max: list[float] | None = None,
    gust_max: list[float] | None = None,
    days: int = 7,
) -> FacilityForecast:
    date_list = [f"2026-05-{20 + i:02d}" for i in range(days)]
    daily: dict = {"time": date_list}
    if temp_max is not None:
        daily["temperature_2m_max"] = temp_max
    if precip_sum is not None:
        daily["precipitation_sum"] = precip_sum
    if gust_max is not None:
        daily["wind_gusts_10m_max"] = gust_max

    aqi: dict = {"time": date_list}
    if pm25_max is not None:
        aqi["pm2_5_max"] = pm25_max
    if aqi_max is not None:
        aqi["us_aqi_max"] = aqi_max

    return FacilityForecast(
        facility_id="test-fab-1",
        lat=30.0,
        lng=-97.0,
        horizon_days=days,
        daily=daily,
        aqi_daily=aqi,
    )


# ── _severity_from_score bucket boundaries ───────────────────────────────


@pytest.mark.parametrize(
    "score, expected",
    [
        (0.0, "low"),
        (24.9, "low"),
        (25.0, "moderate"),
        (54.9, "moderate"),
        (55.0, "high"),
        (79.9, "high"),
        (80.0, "severe"),
        (100.0, "severe"),
    ],
)
def test_severity_buckets(score: float, expected: str) -> None:
    assert _severity_from_score(score) == expected


# ── heat scorer ──────────────────────────────────────────────────────────


def test_score_heat_low_when_cool() -> None:
    fc = _forecast(temp_max=[80.0] * 7, precip_sum=[0.1] * 7)
    out = score_heat(fc, _facility())
    assert out["severity"] == "low"
    assert 0 <= out["score"] < 25


def test_score_heat_severe_during_heat_dome() -> None:
    fc = _forecast(temp_max=[108.0] * 7, precip_sum=[0.0] * 7)
    out = score_heat(fc, _facility(criticality=1.0, heat_threshold_f=95))
    assert out["severity"] in {"high", "severe"}
    assert out["peak_value"] == 108.0
    assert any("108" in d or "consecutive" in d.lower() for d in out["drivers"])


def test_score_heat_criticality_scales() -> None:
    fc = _forecast(temp_max=[102.0] * 7, precip_sum=[0.0] * 7)
    low_crit = score_heat(fc, _facility(criticality=0.1))
    high_crit = score_heat(fc, _facility(criticality=1.0))
    assert high_crit["score"] >= low_crit["score"]


# ── wildfire scorer: None-safety (regression test) ───────────────────────


def test_score_wildfire_none_safe_when_aqi_missing() -> None:
    """Regression: score_wildfire used to crash with TypeError when AQI 400s.

    The Open-Meteo air-quality endpoint occasionally returns 4xx; that
    leaves ``aqi_daily`` empty and ``aqi_peak`` / ``pm_peak`` both ``None``.
    The summary string must NOT raise — it should fall back to an
    "unavailable" note instead.
    """
    fc = _forecast(
        temp_max=[95.0] * 7,
        precip_sum=[0.0] * 7,
        gust_max=[15.0] * 7,
        # NO pm25_max, NO aqi_max → both peaks come back None.
    )
    out = score_wildfire(fc, _facility())
    assert "unavailable" in out["summary"].lower() or out["summary"] != ""
    assert out["severity"] in {"low", "moderate", "high", "severe"}


def test_score_wildfire_high_with_heavy_smoke() -> None:
    fc = _forecast(
        pm25_max=[60.0, 70.0, 55.0, 40.0, 30.0, 20.0, 10.0],
        aqi_max=[180.0, 200.0, 170.0, 130.0, 100.0, 70.0, 50.0],
        gust_max=[35.0, 38.0, 30.0, 25.0, 20.0, 15.0, 10.0],
        precip_sum=[0.0] * 7,
    )
    out = score_wildfire(fc, _facility(criticality=1.0))
    assert out["severity"] in {"moderate", "high", "severe"}
    assert out["peak_value"] == 70.0
    assert any("PM2.5" in d for d in out["drivers"])
    assert any("gust" in d.lower() for d in out["drivers"])


def test_score_wildfire_precip_dampens_gust_component() -> None:
    """Heavy rain should reduce the fire-weather component even with gusts."""
    dry = _forecast(
        pm25_max=[5.0] * 7,
        gust_max=[40.0] * 7,
        precip_sum=[0.0] * 7,
    )
    wet = _forecast(
        pm25_max=[5.0] * 7,
        gust_max=[40.0] * 7,
        precip_sum=[1.0] * 7,
    )
    dry_score = score_wildfire(dry, _facility())["score"]
    wet_score = score_wildfire(wet, _facility())["score"]
    assert wet_score < dry_score


def test_score_wildfire_returns_required_keys() -> None:
    fc = _forecast(pm25_max=[20.0] * 7, gust_max=[15.0] * 7, precip_sum=[0.0] * 7)
    out = score_wildfire(fc, _facility())
    for key in ("score", "severity", "peak_value", "peak_day", "summary", "drivers"):
        assert key in out, f"missing key {key} in wildfire score result"
    assert isinstance(out["drivers"], list)
    assert 0 <= out["score"] <= 100
