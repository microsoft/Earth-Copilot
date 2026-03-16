#!/usr/bin/env python3
"""
Test script for GEOINT pin-drop sampling across all agent modules.

Tests that every geoint endpoint correctly handles pin coordinates
and returns valid responses (not errors or empty data).

Usage:
    python scripts/test_pin_sampling.py [--backend URL]

Defaults to the deployed backend at:
    https://ca-earthcopilot-api.thankfulplant-8534661d.eastus2.azurecontainerapps.io

Requires: httpx, rich (pip install httpx rich)
"""

import argparse
import asyncio
import json
import sys
import time
import uuid
from dataclasses import dataclass, field
from typing import Optional

try:
    import httpx
except ImportError:
    print("ERROR: httpx required. Run: pip install httpx")
    sys.exit(1)

try:
    from rich.console import Console
    from rich.table import Table
    console = Console()
    HAS_RICH = True
except ImportError:
    HAS_RICH = False

# ── Test locations covering edge cases ──────────────────────────────────
TEST_LOCATIONS = {
    "greece_coastal": {
        "name": "Thebes, Greece (original NDVI failure)",
        "lat": 38.3332, "lng": 23.6599,
        "notes": "HLS NDVI was cloud-masked here"
    },
    "dc_urban": {
        "name": "Washington DC (urban)",
        "lat": 38.8977, "lng": -77.0365,
        "notes": "Dense urban area, good for building damage"
    },
    "amazon_forest": {
        "name": "Amazon (dense vegetation)",
        "lat": -3.4653, "lng": -62.2159,
        "notes": "Dense canopy, good for NDVI/vegetation"
    },
    "sahara_desert": {
        "name": "Sahara Desert (arid)",
        "lat": 25.0, "lng": 10.0,
        "notes": "Low vegetation, clear skies, good for terrain"
    },
    "equator_prime_meridian": {
        "name": "Gulf of Guinea (lat=0, lng=0)",
        "lat": 0.0, "lng": 0.0,
        "notes": "Edge case: tests truthiness bugs with zero coords"
    },
    "alps_mountain": {
        "name": "Swiss Alps (elevation)",
        "lat": 46.5588, "lng": 7.9800,
        "notes": "High elevation, good for terrain/mobility"
    },
    "new_orleans_coastal": {
        "name": "New Orleans (flood risk)",
        "lat": 29.9511, "lng": -90.0715,
        "notes": "Low elevation, near water — good for extreme weather"
    },
}

DEFAULT_BACKEND = "https://ca-earthcopilot-api.thankfulplant-8534661d.eastus2.azurecontainerapps.io"


@dataclass
class TestResult:
    module: str
    location: str
    status: str  # "PASS", "FAIL", "SKIP", "WARN"
    http_status: Optional[int] = None
    response_preview: str = ""
    duration_ms: float = 0
    error: str = ""


async def test_endpoint(
    client: httpx.AsyncClient,
    module: str,
    endpoint: str,
    body: dict,
    location_name: str,
    timeout: float = 120.0,
) -> TestResult:
    """Test a single endpoint with given body."""
    start = time.monotonic()
    try:
        resp = await client.post(endpoint, json=body, timeout=timeout)
        duration = (time.monotonic() - start) * 1000

        if resp.status_code == 200:
            data = resp.json()
            # Check for meaningful content
            result_text = ""
            if isinstance(data, dict):
                result_text = (
                    data.get("response", "")
                    or data.get("result", {}).get("response", "")
                    or data.get("result", {}).get("analysis", "")
                    or json.dumps(data)[:200]
                )
            preview = str(result_text)[:120].replace("\n", " ")

            # Check for known failure patterns
            if any(err in str(result_text).lower() for err in [
                "no stac items", "no data loaded", "sampling returned no values",
                "pixel masked", "no valid data"
            ]):
                return TestResult(module, location_name, "WARN", resp.status_code,
                                  preview, duration, "Response indicates no data at pin")
            return TestResult(module, location_name, "PASS", resp.status_code,
                              preview, duration)
        elif resp.status_code == 400:
            detail = resp.json().get("detail", resp.text[:100])
            return TestResult(module, location_name, "FAIL", resp.status_code,
                              "", (time.monotonic() - start) * 1000,
                              f"400: {detail}")
        else:
            return TestResult(module, location_name, "FAIL", resp.status_code,
                              "", (time.monotonic() - start) * 1000,
                              f"HTTP {resp.status_code}: {resp.text[:100]}")

    except httpx.TimeoutException:
        duration = (time.monotonic() - start) * 1000
        return TestResult(module, location_name, "WARN", None, "", duration,
                          f"Timeout after {timeout}s (not necessarily a bug)")
    except Exception as e:
        duration = (time.monotonic() - start) * 1000
        return TestResult(module, location_name, "FAIL", None, "", duration, str(e))


async def run_tests(backend_url: str, locations: list[str], modules: list[str], auth_token: str = ""):
    """Run pin-drop tests across all modules and locations."""
    results: list[TestResult] = []
    headers = {"Content-Type": "application/json"}
    if auth_token:
        headers["Authorization"] = f"Bearer {auth_token}"

    async with httpx.AsyncClient(base_url=backend_url, headers=headers) as client:
        # Quick health check
        try:
            health = await client.get("/api/health", timeout=10)
            print(f"Backend health: {health.status_code}")
            if health.status_code != 200:
                print(f"WARNING: Backend may be down. Response: {health.text[:200]}")
        except Exception as e:
            print(f"WARNING: Health check failed: {e}")
            print("Continuing with tests anyway...\n")

        for loc_key in locations:
            loc = TEST_LOCATIONS[loc_key]
            lat, lng = loc["lat"], loc["lng"]
            print(f"\n{'='*60}")
            print(f"Location: {loc['name']} ({lat}, {lng})")
            print(f"Notes: {loc['notes']}")
            print(f"{'='*60}")

            for module in modules:
                session_id = str(uuid.uuid4())
                print(f"  Testing {module}...", end=" ", flush=True)

                if module == "terrain":
                    result = await test_endpoint(
                        client, module, "/api/geoint/terrain/chat",
                        {
                            "session_id": session_id,
                            "message": "What is the elevation and slope at this location?",
                            "latitude": lat,
                            "longitude": lng,
                            "radius_km": 5.0,
                        },
                        loc["name"],
                    )

                elif module == "vision":
                    result = await test_endpoint(
                        client, module, "/api/geoint/vision/chat",
                        {
                            "session_id": session_id,
                            "message": "What is the NDVI value at this pin location?",
                            "latitude": lat,
                            "longitude": lng,
                            "tile_urls": [],
                            "stac_items": [],
                            "collection": "hls2-l30",
                            "analysis_type": "ndvi",
                        },
                        loc["name"],
                    )

                elif module == "mobility":
                    # Single-point mobility assessment
                    result = await test_endpoint(
                        client, module, "/api/geoint/mobility",
                        {
                            "latitude": lat,
                            "longitude": lng,
                            "user_query": "Assess ground vehicle mobility at this location",
                        },
                        loc["name"],
                    )

                elif module == "building_damage":
                    result = await test_endpoint(
                        client, module, "/api/geoint/building-damage",
                        {
                            "latitude": lat,
                            "longitude": lng,
                            "user_query": "Assess structural condition at this location",
                        },
                        loc["name"],
                    )

                elif module == "extreme_weather":
                    result = await test_endpoint(
                        client, module, "/api/geoint/extreme-weather",
                        {
                            "session_id": session_id,
                            "message": "What are the climate projections for temperature at this location?",
                            "latitude": lat,
                            "longitude": lng,
                        },
                        loc["name"],
                    )

                elif module == "comparison":
                    result = await test_endpoint(
                        client, module, "/api/geoint/comparison",
                        {
                            "session_id": session_id,
                            "user_query": f"Compare vegetation change at coordinates ({lat}, {lng}) between January 2024 and January 2025",
                            "latitude": lat,
                            "longitude": lng,
                        },
                        loc["name"],
                    )

                else:
                    result = TestResult(module, loc["name"], "SKIP", error=f"Unknown module: {module}")

                results.append(result)
                status_icon = {"PASS": "OK", "FAIL": "FAIL", "WARN": "WARN", "SKIP": "SKIP"}[result.status]
                duration_str = f"{result.duration_ms:.0f}ms" if result.duration_ms else ""
                error_str = f" - {result.error}" if result.error else ""
                preview_str = f" - {result.response_preview[:60]}" if result.response_preview else ""
                print(f"[{status_icon}] {duration_str}{error_str}{preview_str}")

    return results


def print_summary(results: list[TestResult]):
    """Print a summary table of all test results."""
    print(f"\n{'='*80}")
    print("SUMMARY")
    print(f"{'='*80}")

    if HAS_RICH:
        table = Table(title="Pin-Drop Test Results")
        table.add_column("Module", style="cyan")
        table.add_column("Location", style="white")
        table.add_column("Status", style="bold")
        table.add_column("HTTP", style="dim")
        table.add_column("Time", style="dim")
        table.add_column("Notes", style="dim", max_width=40)

        for r in results:
            status_style = {"PASS": "green", "FAIL": "red", "WARN": "yellow", "SKIP": "dim"}.get(r.status, "white")
            notes = r.error or r.response_preview[:40]
            table.add_row(
                r.module,
                r.location[:25],
                f"[{status_style}]{r.status}[/{status_style}]",
                str(r.http_status or ""),
                f"{r.duration_ms:.0f}ms" if r.duration_ms else "",
                notes,
            )
        console.print(table)
    else:
        for r in results:
            notes = r.error or r.response_preview[:50]
            print(f"  {r.status:4s} | {r.module:18s} | {r.location:25s} | {r.http_status or '':3} | {r.duration_ms:7.0f}ms | {notes}")

    # Totals
    pass_count = sum(1 for r in results if r.status == "PASS")
    warn_count = sum(1 for r in results if r.status == "WARN")
    fail_count = sum(1 for r in results if r.status == "FAIL")
    skip_count = sum(1 for r in results if r.status == "SKIP")
    total = len(results)

    print(f"\nTotal: {total} | PASS: {pass_count} | WARN: {warn_count} | FAIL: {fail_count} | SKIP: {skip_count}")

    if fail_count > 0:
        print("\nFAILURES:")
        for r in results:
            if r.status == "FAIL":
                print(f"  - {r.module} @ {r.location}: {r.error}")

    return fail_count


def main():
    parser = argparse.ArgumentParser(description="Test GEOINT pin-drop sampling across all modules")
    parser.add_argument("--backend", default=DEFAULT_BACKEND, help="Backend URL")
    parser.add_argument("--token", default="", help="Bearer token for auth (from /.auth/me id_token)")
    parser.add_argument(
        "--locations", nargs="*",
        default=["dc_urban", "equator_prime_meridian"],
        choices=list(TEST_LOCATIONS.keys()),
        help="Locations to test (default: dc_urban + equator edge case)"
    )
    parser.add_argument(
        "--modules", nargs="*",
        default=["terrain", "vision", "extreme_weather"],
        choices=["terrain", "vision", "mobility", "building_damage", "extreme_weather", "comparison"],
        help="Modules to test (default: terrain, vision, extreme_weather)"
    )
    parser.add_argument("--all-locations", action="store_true", help="Test ALL locations")
    parser.add_argument("--all-modules", action="store_true", help="Test ALL modules")
    args = parser.parse_args()

    locations = list(TEST_LOCATIONS.keys()) if args.all_locations else args.locations
    modules = ["terrain", "vision", "mobility", "building_damage", "extreme_weather", "comparison"] if args.all_modules else args.modules

    print(f"Backend: {args.backend}")
    print(f"Locations: {', '.join(locations)}")
    print(f"Modules: {', '.join(modules)}")
    print(f"Total tests: {len(locations) * len(modules)}")

    results = asyncio.run(run_tests(args.backend, locations, modules, args.token))
    fail_count = print_summary(results)
    sys.exit(1 if fail_count > 0 else 0)


if __name__ == "__main__":
    main()
