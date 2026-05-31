"""Weather provider server — exposes Aurora / Earth-2 FCN / MAI Weather
scoring contracts on top of real NWP data from Open-Meteo's public API.

Each route fronts a *different* operational global model so the Forecast
Agent ensembles three real, diverging forecasts:

    /aurora/score        -> ECMWF IFS (open data)  badge as aurora-1.x
    /earth2/fcn/score    -> NOAA GFS               badge as earth2-fcn
    /mai-weather/score   -> DWD ICON               badge as mai-weather-1.x

When real Aurora / Earth-2 / MAI Weather endpoints are wired in production,
set AURORA_ENDPOINT_URL / EARTH2_FCN_ENDPOINT_URL / MAI_WEATHER_ENDPOINT_URL
to those URLs and this service is no longer needed. Until then, this gives
the agent honest, location-accurate ensemble inputs to reason over.

Falls back to a deterministic synthetic field if Open-Meteo is unreachable
or returns no data, so the agent never sees a hard failure mid-demo.

Auth: ``Authorization: Bearer <STUB_API_KEY>`` (skipped if env var unset).
"""
from __future__ import annotations

import hashlib
import logging
import math
import os
from datetime import datetime, timedelta, timezone
from typing import Any

import aiohttp
from fastapi import FastAPI, Header, HTTPException
from pydantic import BaseModel, Field

logger = logging.getLogger("weather-providers")
logging.basicConfig(level=logging.INFO)

API_KEY = os.getenv("STUB_API_KEY", "")
OPENMETEO_BASE = os.getenv("OPENMETEO_BASE_URL", "https://api.open-meteo.com/v1/forecast")
OPENMETEO_TIMEOUT_S = float(os.getenv("OPENMETEO_TIMEOUT_S", "10"))

app = FastAPI(title="Planetary Explorer weather providers", version="0.2.0")


def _check_auth(authorization: str | None) -> None:
    if not API_KEY:
        return
    if authorization != f"Bearer {API_KEY}":
        raise HTTPException(status_code=401, detail="invalid bearer token")


class ScoreRequest(BaseModel):
    lat: float = Field(..., ge=-90, le=90)
    lon: float = Field(..., ge=-180, le=180)
    lead_hours: int = Field(72, ge=1, le=240)
    variables: list[str] = Field(default_factory=lambda: ["t2m", "precip"])
    grid_size: int = Field(8, ge=2, le=32)
    issued_at: str | None = None


# ── Model routing ─────────────────────────────────────────────────────────
# Each badge maps to a distinct Open-Meteo operational model so the
# ensemble actually sees disagreement from independent forecasting systems.
_MODEL_ROUTING: dict[str, dict[str, str]] = {
    "aurora-1.x":      {"openmeteo_model": "ecmwf_ifs025", "source": "ECMWF IFS 0.25"},
    "earth2-fcn":      {"openmeteo_model": "gfs_seamless",  "source": "NOAA GFS"},
    "mai-weather-1.x": {"openmeteo_model": "icon_seamless", "source": "DWD ICON"},
}

# Map our internal variable names to Open-Meteo hourly fields + unit conversions.
_VAR_MAP: dict[str, tuple[str, str, Any]] = {
    "t2m":    ("temperature_2m",   "K",        lambda c: c + 273.15),
    "precip": ("precipitation",    "mm/hr",    lambda v: v),
    "u10":    ("wind_speed_10m",   "m/s",      None),  # computed in builder
    "v10":    ("wind_speed_10m",   "m/s",      None),  # computed in builder
    "msl":    ("pressure_msl",     "hPa",      lambda v: v),
    "tcwv":   ("",                 "kg/m^2",   None),  # not in OM hourly
    "q500":   ("",                 "g/kg",     None),  # not in OM hourly
}


# ── Synthetic fallback ────────────────────────────────────────────────────
def _seed_for(lat: float, lon: float, lead: int, model: str) -> int:
    key = f"{model}:{lat:.3f}:{lon:.3f}:{lead}"
    return int(hashlib.sha256(key.encode()).hexdigest()[:8], 16)


def _grid_axis(center: float, n: int, deg_step: float = 0.25) -> list[float]:
    half = (n - 1) / 2.0
    return [round(center + (i - half) * deg_step, 4) for i in range(n)]


def _flat_field(value: float, n: int, seed: int, amp: float = 0.0) -> list[list[float]]:
    rng = (seed % 997) / 997.0
    out = []
    for i in range(n):
        row = []
        for j in range(n):
            delta = amp * (
                math.sin((i + rng) * 0.6) * 0.5
                + math.cos((j + rng * 2) * 0.5) * 0.3
            )
            row.append(round(value + delta, 3))
        out.append(row)
    return out


_VAR_CATALOG_FALLBACK = {
    "t2m":     (288.0, 6.0, "K"),
    "precip":  (1.2,   1.5, "mm/hr"),
    "u10":     (3.0,   4.0, "m/s"),
    "v10":     (1.0,   4.0, "m/s"),
    "msl":     (1013.0, 4.0, "hPa"),
    "tcwv":    (25.0,  10.0, "kg/m^2"),
    "q500":    (3.0,   1.0, "g/kg"),
}


def _synth_field(seed: int, n: int, base: float, amp: float) -> list[list[float]]:
    rng = (seed % 997) / 997.0
    out = []
    for i in range(n):
        row = []
        for j in range(n):
            v = (
                base
                + amp * math.sin((i + rng) * 0.6)
                + amp * 0.7 * math.cos((j + rng * 2) * 0.5)
                + amp * 0.3 * math.sin((i + j) * 0.3 + rng * 6.28)
            )
            row.append(round(v, 3))
        out.append(row)
    return out


# ── Open-Meteo client ─────────────────────────────────────────────────────
async def _fetch_openmeteo(
    lat: float,
    lon: float,
    om_model: str,
    hourly_fields: list[str],
) -> dict[str, Any] | None:
    params = {
        "latitude": f"{lat:.4f}",
        "longitude": f"{lon:.4f}",
        "hourly": ",".join(hourly_fields),
        "models": om_model,
        "forecast_days": 10,
        "timezone": "UTC",
    }
    try:
        timeout = aiohttp.ClientTimeout(total=OPENMETEO_TIMEOUT_S)
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.get(OPENMETEO_BASE, params=params) as resp:
                if resp.status != 200:
                    text = (await resp.text())[:200]
                    logger.warning("open-meteo %s returned %s: %s", om_model, resp.status, text)
                    return None
                return await resp.json()
    except Exception as exc:  # noqa: BLE001
        logger.warning("open-meteo %s fetch failed: %s", om_model, exc)
        return None


def _pick_hour_index(times: list[str], lead_hours: int, issued: datetime) -> int:
    target = issued + timedelta(hours=lead_hours)
    best_i, best_diff = 0, float("inf")
    for i, t in enumerate(times):
        try:
            dt = datetime.fromisoformat(t.replace("Z", "+00:00"))
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
        except Exception:
            continue
        diff = abs((dt - target).total_seconds())
        if diff < best_diff:
            best_diff, best_i = diff, i
    return best_i


def _build_field_from_value(
    value: float | None,
    n: int,
    seed: int,
    fallback_base: float,
    fallback_amp: float,
) -> tuple[list[list[float]], bool]:
    if value is None or (isinstance(value, float) and math.isnan(value)):
        return _synth_field(seed, n, fallback_base, fallback_amp), False
    amp = max(abs(value) * 0.01, 0.05)
    return _flat_field(float(value), n, seed, amp=amp), True


async def _build_response(req: ScoreRequest, badge: str) -> dict[str, Any]:
    routing = _MODEL_ROUTING.get(badge)
    issued = (
        datetime.fromisoformat(req.issued_at.replace("Z", "+00:00"))
        if req.issued_at
        else datetime.now(tz=timezone.utc)
    )
    valid = issued + timedelta(hours=req.lead_hours)

    om_fields: list[str] = []
    needs_wind = False
    for v in req.variables:
        if v in ("u10", "v10"):
            needs_wind = True
        elif v in _VAR_MAP and _VAR_MAP[v][0]:
            om_fields.append(_VAR_MAP[v][0])
    if needs_wind:
        om_fields.extend(["wind_speed_10m", "wind_direction_10m"])
    om_fields = sorted(set(om_fields))

    om_body: dict[str, Any] | None = None
    if routing and om_fields:
        om_body = await _fetch_openmeteo(
            lat=req.lat,
            lon=req.lon,
            om_model=routing["openmeteo_model"],
            hourly_fields=om_fields,
        )

    times = (om_body or {}).get("hourly", {}).get("time", []) if om_body else []
    idx = _pick_hour_index(times, req.lead_hours, issued) if times else -1

    fields: dict[str, list[list[float]]] = {}
    units: dict[str, str] = {}
    real_vars: list[str] = []
    fallback_vars: list[str] = []

    for v in req.variables:
        if v == "cyclone":
            continue
        seed = _seed_for(req.lat, req.lon, req.lead_hours, badge + ":" + v)
        if v in ("u10", "v10"):
            ws = wd = None
            if om_body and idx >= 0:
                ws_arr = om_body.get("hourly", {}).get("wind_speed_10m") or []
                wd_arr = om_body.get("hourly", {}).get("wind_direction_10m") or []
                if 0 <= idx < len(ws_arr):
                    ws = ws_arr[idx]
                if 0 <= idx < len(wd_arr):
                    wd = wd_arr[idx]
            if ws is not None and wd is not None:
                ws_ms = float(ws) / 3.6  # km/h -> m/s
                rad = math.radians(float(wd))
                u = -ws_ms * math.sin(rad)
                vv = -ws_ms * math.cos(rad)
                value = u if v == "u10" else vv
            else:
                value = None
            base, amp, unit = _VAR_CATALOG_FALLBACK[v]
            field, is_real = _build_field_from_value(value, req.grid_size, seed, base, amp)
        elif v in _VAR_MAP and _VAR_MAP[v][0]:
            om_field, unit_out, transform = _VAR_MAP[v]
            raw = None
            if om_body and idx >= 0:
                arr = om_body.get("hourly", {}).get(om_field) or []
                if 0 <= idx < len(arr):
                    raw = arr[idx]
            value = transform(raw) if (raw is not None and transform) else raw
            unit = unit_out
            base, amp, _u = _VAR_CATALOG_FALLBACK.get(v, (0.0, 1.0, unit_out))
            field, is_real = _build_field_from_value(value, req.grid_size, seed, base, amp)
        else:
            base, amp, unit = _VAR_CATALOG_FALLBACK.get(v, (0.0, 1.0, "unknown"))
            field = _synth_field(seed, req.grid_size, base, amp)
            is_real = False

        fields[v] = field
        units[v] = unit
        (real_vars if is_real else fallback_vars).append(v)

    any_real = bool(real_vars)
    body: dict[str, Any] = {
        "model": badge,
        "issued_at": issued.isoformat().replace("+00:00", "Z"),
        "valid_at": valid.isoformat().replace("+00:00", "Z"),
        "lead_hours": req.lead_hours,
        "grid": {
            "lat": _grid_axis(req.lat, req.grid_size),
            "lon": _grid_axis(req.lon, req.grid_size),
        },
        "variables": fields,
        "units": units,
        "stub": not any_real,
        "source": routing["source"] if routing else "synthetic",
        "data_source_note": (
            f"Forecast backed by {routing['source']} via Open-Meteo "
            f"(real fields: {sorted(real_vars)}; "
            f"synthetic fallback: {sorted(fallback_vars)})"
        ) if any_real else "All values synthetic (Open-Meteo unreachable).",
    }
    if badge == "aurora-1.x" and "cyclone" in req.variables:
        body["cyclone_tracks"] = _build_cyclone_tracks(req)
    return body


def _build_cyclone_tracks(req: ScoreRequest) -> list[dict[str, Any]]:
    base_seed = _seed_for(req.lat, req.lon, req.lead_hours, "cyclone")
    tracks = []
    for member in range(3):
        seed = base_seed + member * 31
        rng = (seed % 1009) / 1009.0
        bearing = (rng * 2 * math.pi) + member * 0.4
        points = []
        for h in range(0, req.lead_hours + 1, 12):
            r = h * 0.06
            plat = req.lat + r * math.cos(bearing + h * 0.01)
            plon = req.lon + r * math.sin(bearing + h * 0.01)
            wind_kt = 60 + 25 * math.sin(h * 0.05 + rng * 6.28) - h * 0.05
            points.append({
                "valid_hours": h,
                "lat": round(plat, 4),
                "lon": round(plon, 4),
                "max_wind_kt": round(wind_kt, 1),
                "msl_hpa": round(990.0 + 8 * math.sin(h * 0.05), 1),
            })
        tracks.append({"member": member, "points": points})
    return tracks


# ── Routes ───────────────────────────────────────────────────────────────
@app.get("/health")
def health() -> dict[str, Any]:
    return {
        "status": "ok",
        "auth_required": bool(API_KEY),
        "backend": "open-meteo",
        "models": list(_MODEL_ROUTING.keys()),
    }


@app.get("/info")
def info() -> dict[str, Any]:
    return {
        "service": "weather-providers",
        "purpose": "Real NWP forecasts (ECMWF IFS / NOAA GFS / DWD ICON) wrapped behind "
                   "Aurora / Earth-2 FCN / MAI Weather scoring contracts.",
        "backend": "Open-Meteo public API",
        "routing": {badge: cfg["source"] for badge, cfg in _MODEL_ROUTING.items()},
        "endpoints": {
            "aurora-1.x":      "/aurora/score",
            "earth2-fcn":      "/earth2/fcn/score",
            "mai-weather-1.x": "/mai-weather/score",
        },
        "variables": list(_VAR_MAP.keys()) + ["cyclone (aurora only, synthetic)"],
        "note": "Swap to real Aurora / Earth-2 / MAI Weather endpoints in production by "
                "changing AURORA_ENDPOINT_URL / EARTH2_FCN_ENDPOINT_URL / MAI_WEATHER_ENDPOINT_URL.",
    }


@app.post("/aurora/score")
async def aurora_score(req: ScoreRequest, authorization: str | None = Header(default=None)) -> dict[str, Any]:
    _check_auth(authorization)
    return await _build_response(req, badge="aurora-1.x")


@app.post("/earth2/fcn/score")
async def earth2_fcn_score(req: ScoreRequest, authorization: str | None = Header(default=None)) -> dict[str, Any]:
    _check_auth(authorization)
    return await _build_response(req, badge="earth2-fcn")


@app.post("/mai-weather/score")
async def mai_weather_score(req: ScoreRequest, authorization: str | None = Header(default=None)) -> dict[str, Any]:
    _check_auth(authorization)
    return await _build_response(req, badge="mai-weather-1.x")
