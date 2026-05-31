#!/usr/bin/env python
"""Direct smoke test of the Forecast Agent (connectors + workflow) against
a locally-running weather-stub. Skips the FastAPI app for speed.

Usage:
    # Start stub first (separate terminal):
    cd weather-stub-server && uvicorn app:app --port 8090
    # Then:
    python scripts/smoke_forecast_agent.py
"""
from __future__ import annotations

import asyncio
import json
import os
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "container-app"))

# Wire env BEFORE importing the connectors (registry caches on first call).
os.environ.setdefault("AURORA_ENDPOINT_URL", "http://127.0.0.1:8090")
os.environ.setdefault("EARTH2_FCN_ENDPOINT_URL", "http://127.0.0.1:8090")
os.environ.setdefault("AURORA_SCORE_PATH", "/aurora/score")
os.environ.setdefault("EARTH2_FCN_SCORE_PATH", "/earth2/fcn/score")


async def main() -> int:
    from agents.forecast import (
        ForecastAgentQuery,
        forecast,
        forecast_direct,
        is_available,
    )
    from connectors.weather.registry import get_registry

    registry = get_registry()
    print(f"registry providers: {[p.provider_id for p in registry.all]}")
    if len(registry.all) < 2:
        print("FAIL: expected 2 providers in registry", file=sys.stderr)
        return 1

    query = ForecastAgentQuery(
        lat=38.9, lon=-77.0, lead_hours=72,
        variables=("t2m", "precip", "u10", "v10"),
        grid_size=6,
        user_query="Forecast for Washington, DC next 72 hours",
        location_label="Washington, DC",
    )

    # 1. direct path (no MAF) — always available
    print("\n[1] forecast_direct (asyncio.gather, no MAF):")
    dossier = await forecast_direct(query)
    print(f"    providers_succeeded: {dossier['providers_succeeded']}")
    print(f"    timing_ms          : {dossier['timing_ms']}")
    print(f"    ensemble t2m       : {dossier['ensemble_summary']['variables'].get('t2m')}")
    if len(dossier["providers_succeeded"]) < 2:
        print("FAIL: direct path did not get both providers", file=sys.stderr)
        return 1

    # 2. MAF path (if installed)
    print(f"\n[2] MAF path (is_available={is_available()}):")
    dossier2 = await forecast(query)
    print(f"    providers_succeeded: {dossier2['providers_succeeded']}")
    print(f"    timing_ms          : {dossier2['timing_ms']}")
    print(f"    ensemble t2m       : {dossier2['ensemble_summary']['variables'].get('t2m')}")
    if len(dossier2["providers_succeeded"]) < 2:
        print("FAIL: MAF path did not get both providers", file=sys.stderr)
        return 1

    # 3. capability-based selection (cyclone tracks — Aurora only)
    print("\n[3] cyclone selection (Aurora-only capability):")
    cyclone_query = ForecastAgentQuery(
        lat=25.0, lon=-75.0, lead_hours=96,
        variables=("t2m", "msl", "cyclone"),
        grid_size=4,
        requested_providers=("aurora-1.x",),
        location_label="N Atlantic test",
    )
    dossier3 = await forecast(cyclone_query)
    aurora_forecast = next((f for f in dossier3["forecasts"] if f["provider_id"] == "aurora-1.x"), None)
    if not aurora_forecast or "cyclone_tracks" not in aurora_forecast.get("extras", {}):
        print("FAIL: expected cyclone_tracks in Aurora extras", file=sys.stderr)
        return 1
    tracks = aurora_forecast["extras"]["cyclone_tracks"]
    print(f"    aurora returned {len(tracks)} cyclone tracks with {len(tracks[0]['points'])} points each")

    print("\nPASS — Forecast Agent end-to-end (direct + MAF + capability routing)")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
