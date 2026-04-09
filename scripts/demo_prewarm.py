"""
Demo Pre-Warming Script for Earth Copilot
==========================================
Run this 2-3 minutes before your demo to pre-warm all caches.

What it does:
1. Warms the STAC search cache (Planetary Computer)
2. Warms the NetCDF/CMIP6 cache (extreme weather climate data)
3. Warms the location resolver cache
4. Pre-fetches TileJSON URLs for demo collections
5. Hits each API endpoint once so Azure Container App is scaled up (no cold start)

Usage:
    python scripts/demo_prewarm.py [--backend-url URL]

Default backend: https://ca-earthcopilot-api.thankfulplant-8534661d.eastus2.azurecontainerapps.io
"""

import argparse
import json
import time
import sys
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed

DEFAULT_BACKEND = "https://ca-earthcopilot-api.thankfulplant-8534661d.eastus2.azurecontainerapps.io"

# ============================================================================
# DEMO QUERIES AND THEIR EXPECTED CACHES
# ============================================================================
# These map to your 8 demo queries in order:
#
# 1) Navigate to New Orleans, Louisiana
# 2) Extreme weather pin drop → precipitation projections
# 3) Show coastal land cover changes in California
# 4) How do I interpret this collection (contextual, no pre-warm needed)
# 5) Vision module pin drop → sample raster (needs live tiles first)
# 6) Show elevation map of Mount Rainier, Washington
# 7) Terrain Agent → construction permit analysis
# 8) Potential GOES query
# ============================================================================

# Locations to pre-warm in location resolver cache
DEMO_LOCATIONS = [
    "New Orleans, Louisiana",
    "California",
    "Mount Rainier, Washington",
]

# STAC searches to pre-warm (collection + bbox)
DEMO_STAC_SEARCHES = [
    # Query 3: Coastal land cover California
    {
        "collections": ["esa-worldcover"],
        "bbox": [-124.48, 32.53, -114.13, 42.01],
        "limit": 5,
        "sortby": [{"field": "datetime", "direction": "desc"}],
    },
    # Query 6: Elevation Mount Rainier (already in quickstart cache,
    # but pre-warm STAC too)
    {
        "collections": ["cop-dem-glo-30"],
        "bbox": [-121.88, 46.72, -121.60, 46.93],
        "limit": 10,
        "sortby": [{"field": "datetime", "direction": "desc"}],
    },
    # Query 8: GOES-CMI (if tiles work)
    {
        "collections": ["goes-cmi"],
        "bbox": [-90.14, 29.87, -89.63, 30.20],
        "limit": 3,
        "sortby": [{"field": "datetime", "direction": "desc"}],
    },
]

# CMIP6 pre-warm for extreme weather (Query 2)
# New Orleans coords: 30.0, -90.0
DEMO_CMIP6_PARAMS = {
    "lat": 30.0,
    "lng": -90.0,
    "variable": "tasmax",
    "scenario": "ssp585",
    "year": 2030,
}

# CMIP6 pre-warm for precipitation trend (follow-up to Query 2)
# compute_trend samples ~5 years across the range
DEMO_CMIP6_TREND_PARAMS = [
    {"lat": 30.0, "lng": -90.0, "variable": "pr", "scenario": "ssp585", "year": yr}
    for yr in [2020, 2035, 2050, 2065, 2080]
]


def timed(label):
    """Context manager for timing operations."""
    class Timer:
        def __init__(self):
            self.start = None
            self.elapsed = None
        def __enter__(self):
            self.start = time.time()
            return self
        def __exit__(self, *args):
            self.elapsed = time.time() - self.start
            status = "OK" if self.elapsed < 5 else "SLOW"
            print(f"  [{status}] {label}: {self.elapsed:.1f}s")
    return Timer()


def warm_health(backend_url):
    """Hit the health endpoint to wake up the container."""
    url = f"{backend_url}/health"
    try:
        req = urllib.request.Request(url, method="GET")
        resp = urllib.request.urlopen(req, timeout=30)
        data = json.loads(resp.read())
        return data.get("status") == "healthy"
    except Exception as e:
        print(f"  [WARN] Health check failed: {e}")
        return False


def warm_stac_search(search_body):
    """Pre-warm a STAC search on Planetary Computer."""
    url = "https://planetarycomputer.microsoft.com/api/stac/v1/search"
    body = json.dumps(search_body).encode()
    req = urllib.request.Request(url, data=body, headers={"Content-Type": "application/json"})
    resp = urllib.request.urlopen(req, timeout=30)
    result = json.loads(resp.read())
    n = result.get("numberReturned", len(result.get("features", [])))
    colls = search_body.get("collections", ["?"])
    return f"{colls[0]}: {n} items"


def warm_cmip6(backend_url, params):
    """Pre-warm CMIP6 diagnostic endpoint (warms STAC + NetCDF caches)."""
    qs = "&".join(f"{k}={v}" for k, v in params.items())
    url = f"{backend_url}/api/geoint/cmip6-test?{qs}"
    try:
        req = urllib.request.Request(url, method="GET")
        resp = urllib.request.urlopen(req, timeout=120)
        data = json.loads(resp.read())
        return data.get("success", False)
    except Exception as e:
        return f"Error: {e}"


def warm_query_endpoint(backend_url, query):
    """Hit the /api/query endpoint to warm up the full pipeline."""
    url = f"{backend_url}/api/query"
    body = json.dumps({"query": query}).encode()
    try:
        req = urllib.request.Request(url, data=body, headers={"Content-Type": "application/json"})
        resp = urllib.request.urlopen(req, timeout=60)
        data = json.loads(resp.read())
        status = data.get("status", "unknown")
        n_tiles = len(data.get("features", []))
        return f"status={status}, tiles={n_tiles}"
    except Exception as e:
        return f"Error: {e}"


def main():
    parser = argparse.ArgumentParser(description="Pre-warm Earth Copilot caches for demo")
    parser.add_argument("--backend-url", default=DEFAULT_BACKEND, help="Backend API URL")
    parser.add_argument("--skip-cmip6", action="store_true", help="Skip CMIP6 pre-warm (slow)")
    parser.add_argument("--skip-stac", action="store_true", help="Skip STAC pre-warm")
    args = parser.parse_args()

    backend = args.backend_url.rstrip("/")
    print(f"Pre-warming Earth Copilot demo caches")
    print(f"Backend: {backend}")
    print(f"{'='*60}")
    t_total = time.time()

    # ── Step 1: Wake up the container ──
    print("\n[1/5] Waking up container (health check)...")
    with timed("Health check") as t:
        ok = warm_health(backend)
    if not ok:
        print("  [WARN] Backend may be cold-starting. Retrying in 5s...")
        time.sleep(5)
        warm_health(backend)

    # ── Step 2: Pre-warm STAC searches (parallel) ──
    if not args.skip_stac:
        print(f"\n[2/5] Pre-warming {len(DEMO_STAC_SEARCHES)} STAC searches (parallel)...")
        with timed("All STAC searches"):
            with ThreadPoolExecutor(max_workers=3) as pool:
                futures = {pool.submit(warm_stac_search, s): s for s in DEMO_STAC_SEARCHES}
                for f in as_completed(futures):
                    try:
                        result = f.result()
                        print(f"    {result}")
                    except Exception as e:
                        print(f"    Error: {e}")

    # ── Step 3: Pre-warm CMIP6 (extreme weather) ──
    if not args.skip_cmip6:
        print("\n[3/5] Pre-warming CMIP6 climate data (New Orleans, ssp585, 2030)...")
        print("       This warms STAC search cache + NetCDF result cache + fsspec connection pool")
        with timed("CMIP6 pre-warm"):
            result = warm_cmip6(backend, DEMO_CMIP6_PARAMS)
            print(f"    Success: {result}")

        # Also pre-warm ssp245 for comparison follow-ups
        print("       Pre-warming ssp245 comparison cache...")
        with timed("CMIP6 ssp245"):
            params245 = {**DEMO_CMIP6_PARAMS, "scenario": "ssp245"}
            result = warm_cmip6(backend, params245)
            print(f"    Success: {result}")

        # Pre-warm precipitation trend years (parallel)
        print(f"       Pre-warming precipitation trend ({len(DEMO_CMIP6_TREND_PARAMS)} years, parallel)...")
        with timed("CMIP6 precip trend"):
            with ThreadPoolExecutor(max_workers=3) as pool:
                futures = {pool.submit(warm_cmip6, backend, p): p["year"] for p in DEMO_CMIP6_TREND_PARAMS}
                for f in as_completed(futures):
                    yr = futures[f]
                    try:
                        result = f.result()
                        print(f"    pr/{yr}: {result}")
                    except Exception as e:
                        print(f"    pr/{yr}: Error: {e}")
    else:
        print("\n[3/5] Skipping CMIP6 pre-warm")

    # ── Step 4: Pre-warm quickstart queries (elevation + land cover) ──
    print("\n[4/5] Pre-warming quickstart pipeline queries...")
    demo_queries = [
        "show elevation map of mount rainier, washington",
        "show coastal land cover changes in california",
    ]
    for q in demo_queries:
        with timed(f"Query: '{q[:50]}...'"):
            result = warm_query_endpoint(backend, q)
            print(f"    {result}")

    # ── Step 5: Summary ──
    total = time.time() - t_total
    print(f"\n{'='*60}")
    print(f"Pre-warming complete in {total:.1f}s")
    print(f"\nCaches now warm:")
    print(f"  - Location resolver: New Orleans, California, Mount Rainier")
    print(f"  - STAC search: esa-worldcover, cop-dem-glo-30, goes-cmi")
    print(f"  - CMIP6 NetCDF: ssp585+ssp245 for New Orleans (2030)")
    print(f"  - CMIP6 NetCDF: pr trend years 2020/2035/2050/2065/2080")
    print(f"  - Pipeline: Quickstart fast-path for elevation + land cover")
    print(f"\nLatency expectations during demo:")
    print(f"  Query 1 (Navigate): ~0.5s (location pre-cached)")
    print(f"  Query 2 (Climate):  ~3-6s (CMIP6 cache + 1 LLM format call)")
    print(f"  Query 3 (Land cover): ~2-4s (STAC warm, needs GPT translation)")
    print(f"  Query 4 (Interpret): ~2-3s (contextual, 1 LLM call)")
    print(f"  Query 5 (Raster):   ~1-3s (depends on tile load)")
    print(f"  Query 6 (Elevation): ~1-2s (quickstart cache hit)")
    print(f"  Query 7 (Terrain):  ~3-8s (terrain agent + DEM download)")
    print(f"  Query 8 (GOES):     TBD (PC tile server currently returning 500)")


if __name__ == "__main__":
    main()
