"""
Test: Quick Start Button Queries
================================

Tests all queries from GetStartedButton.tsx to validate:
1. Single collection (or same-family) is returned
2. STAC results are returned
3. No mixed product families

Run with: python tests/test_quick_start_queries.py
"""

import httpx
import asyncio
import subprocess
import json
from typing import List, Dict, Set, Tuple, Optional
from dataclasses import dataclass
from datetime import datetime


# ============================================================================
# CONFIGURATION
# ============================================================================

# Azure resource identifiers - discovered dynamically from resource group
RESOURCE_GROUP = "rg-earthcopilot"

# Override endpoint (set to None to fetch dynamically from Azure)
API_ENDPOINT_OVERRIDE = None
# API_ENDPOINT_OVERRIDE = "http://localhost:8000"  # Uncomment for local testing

TIMEOUT = 90.0  # seconds


def get_api_endpoint() -> str:
    """
    Get the API endpoint dynamically from Azure or use override.
    
    This ensures we always use the correct endpoint regardless of
    the dynamically generated Container App name.
    """
    if API_ENDPOINT_OVERRIDE:
        return API_ENDPOINT_OVERRIDE
    
    try:
        # Discover container app name dynamically
        result = subprocess.run(
            [
                "az", "containerapp", "list",
                "--resource-group", RESOURCE_GROUP,
                "--query", "[0].name",
                "-o", "tsv"
            ],
            capture_output=True,
            text=True,
            timeout=30
        )
        
        container_app_name = result.stdout.strip()
        if not container_app_name:
            print("⚠️ No Container App found in resource group")
            return "http://localhost:8000"  # Run backend locally for testing

        # Get the FQDN
        result = subprocess.run(
            [
                "az", "containerapp", "show",
                "--name", container_app_name,
                "--resource-group", RESOURCE_GROUP,
                "--query", "properties.configuration.ingress.fqdn",
                "-o", "tsv"
            ],
            capture_output=True,
            text=True,
            timeout=30
        )
        
        if result.returncode == 0 and result.stdout.strip():
            fqdn = result.stdout.strip()
            return f"https://{fqdn}"
        else:
            print(f"⚠️ Failed to get endpoint from Azure: {result.stderr}")
            return "http://localhost:8000"  # Run backend locally for testing
    except subprocess.TimeoutExpired:
        print("⚠️ Azure CLI timed out, using local fallback")
        return "http://localhost:8000"  # Run backend locally for testing
    except FileNotFoundError:
        print("⚠️ Azure CLI not found, using local fallback")
        return "http://localhost:8000"  # Run backend locally for testing


# ============================================================================
# COLLECTION FAMILY DEFINITIONS
# ============================================================================

COLLECTION_FAMILIES = {
    "hls": {"hls2-l30", "hls2-s30"},
    "sentinel-2": {"sentinel-2-l2a"},
    "sentinel-1": {"sentinel-1-rtc", "sentinel-1-grd"},
    "landsat": {"landsat-c2-l2", "landsat-c2-l1"},
    "modis-fire": {"modis-14A1-061", "modis-14A2-061"},
    "modis-burn": {"modis-64A1-061"},
    "modis-vegetation": {"modis-13Q1-061"},
    "modis-snow": {"modis-10A1-061"},
    "modis-npp": {"modis-17A3HGF-061"},
    "modis-brdf": {"modis-43A4-061"},
    "copernicus-dem": {"cop-dem-glo-30", "cop-dem-glo-90"},
    "3dep": {"3dep-seamless", "3dep-lidar-hag", "3dep-lidar-dtm", "3dep-lidar-dsm"},
    "alos-dem": {"alos-dem"},
    "alos-palsar": {"alos-palsar-mosaic"},
    "naip": {"naip"},
    "jrc-gsw": {"jrc-gsw"},
    "chloris": {"chloris-biomass"},
    "usda-cdl": {"usda-cdl"},
    "ms-buildings": {"ms-buildings"},
    "noaa-sst": {"noaa-cdr-sea-surface-temperature-whoi"},
    "mtbs": {"mtbs"},
}


@dataclass
class QueryTestCase:
    """Test case for a single query."""
    category: str
    query: str
    expected_collection: str
    location: str


# ============================================================================
# QUICK START QUERIES - FROM GetStartedButton.tsx
# ============================================================================

QUICK_START_QUERIES = [
    # 🌍 High-Resolution Imagery
    QueryTestCase("🌍 Imagery", "Show Harmonized Landsat Sentinel-2 (HLS) Version 2.0 imagery of Greece with low cloud cover in June 2025", "hls2-s30/hls2-l30", "Greece"),
    QueryTestCase("🌍 Imagery", "Show Sentinel-2 Level 2A for NYC with low cloud cover on January 1st 2026", "sentinel-2-l2a", "NYC"),
    QueryTestCase("🌍 Imagery", "Show Landsat Collection 2 Level 2 imagery of Washington DC", "landsat-c2-l2", "Washington DC"),
    
    # 🔥 Fire Detection
    QueryTestCase("🔥 Fire", "Show wildfire MODIS data for California", "modis-14A1-061", "California"),
    QueryTestCase("🔥 Fire", "Show fire modis thermal anomalies daily activity for Australia from June 2025", "modis-14A2-061", "Australia"),
    QueryTestCase("🔥 Fire", "Show MTBS burn severity for California in 2017", "mtbs", "California"),
    
    # 🌊 Water
    QueryTestCase("🌊 Water", "Display JRC Global Surface Water in Bangladesh", "jrc-gsw", "Bangladesh"),
    QueryTestCase("🌊 Water", "Show modis snow cover daily for Quebec for January 2025", "modis-10A1-061", "Quebec"),
    QueryTestCase("🌊 Water", "Show me Sea Surface Temperature near Madagascar", "noaa-cdr-sea-surface-temperature-whoi", "Madagascar"),
    
    # 🌲 Vegetation
    QueryTestCase("🌲 Veg", "Show modis net primary production for San Jose", "modis-17A3HGF-061", "San Jose"),
    QueryTestCase("🌲 Veg", "Show me chloris biomass for the Amazon rainforest", "chloris-biomass", "Amazon"),
    QueryTestCase("🌲 Veg", "Show modis vedgetation indices for Ukraine", "modis-13Q1-061", "Ukraine"),
    QueryTestCase("🌲 Veg", "Show USDA Cropland Data Layers (CDLs) for Florida", "usda-cdl", "Florida"),
    QueryTestCase("🌲 Veg", "Show recent modis nadir BDRF adjusted reflectance for the Gulf of America", "modis-43A4-061", "Gulf of America"),
    
    # 🏔️ Elevation
    QueryTestCase("🏔️ Elev", "Show elevation map of Grand Canyon", "cop-dem-glo-30", "Grand Canyon"),
    QueryTestCase("🏔️ Elev", "Show ALOS World 3D-30m of Tomas de Berlanga", "alos-dem", "Galápagos"),
    QueryTestCase("🏔️ Elev", "Show buildings in Reston, Virginia", "ms-buildings", "Reston, VA"),
    QueryTestCase("🏔️ Elev", "Show USGS 3DEP Lidar Height above Ground for New Orleans", "3dep-lidar-hag", "New Orleans, LA"),
    QueryTestCase("🏔️ Elev", "Show USGS 3DEP Lidar Height above Ground for Denver, Colorado", "3dep-lidar-hag", "Denver, CO"),
    
    # 📡 Radar
    QueryTestCase("📡 Radar", "Show Sentinel 1 RTC for Baltimore", "sentinel-1-rtc", "Baltimore"),
    QueryTestCase("📡 Radar", "Show ALOS PALSAR Annual for Ecuador", "alos-palsar-mosaic", "Ecuador"),
    QueryTestCase("📡 Radar", "Show Sentinel 1 Radiometrically Terrain Corrected (RTC) for Philipines", "sentinel-1-rtc", "Philippines"),
]


# ============================================================================
# HELPER FUNCTIONS
# ============================================================================

def get_collection_family(collection_id: str) -> str:
    """Get the family name for a collection ID."""
    for family_name, collections in COLLECTION_FAMILIES.items():
        if collection_id in collections:
            return family_name
    return collection_id


def collections_are_same_family(collections: List[str]) -> Tuple[bool, Set[str]]:
    """Check if all collections belong to the same family."""
    families = set()
    for coll in collections:
        families.add(get_collection_family(coll))
    return len(families) <= 1, families


async def query_api(query: str, api_endpoint: str) -> Dict:
    """Send a query to the API and return the response."""
    async with httpx.AsyncClient(timeout=TIMEOUT) as client:
        response = await client.post(
            f"{api_endpoint}/api/query",
            json={"query": query},
            headers={"Content-Type": "application/json"}
        )
        response.raise_for_status()
        return response.json()


def extract_collections_from_response(response: Dict) -> List[str]:
    """Extract all unique collection IDs from the API response."""
    collections = set()
    
    if "search_metadata" in response:
        searched = response["search_metadata"].get("collections_searched", [])
        collections.update(searched)
    
    if "translation_metadata" in response:
        tile_urls = response["translation_metadata"].get("all_tile_urls", [])
        for tile in tile_urls:
            if "collection" in tile:
                collections.add(tile["collection"])
    
    if "debug" in response and "semantic_translator" in response["debug"]:
        selected = response["debug"]["semantic_translator"].get("selected_collections", [])
        collections.update(selected)
    
    return list(collections)


def truncate(text: str, max_len: int) -> str:
    """Truncate text to max length with ellipsis."""
    if len(text) <= max_len:
        return text
    return text[:max_len-3] + "..."


# ============================================================================
# TEST RUNNER
# ============================================================================

async def test_single_query(test_case: QueryTestCase, api_endpoint: str) -> Dict:
    """Test a single query and return results."""
    try:
        response = await query_api(test_case.query, api_endpoint)
        collections = extract_collections_from_response(response)
        is_same_family, families = collections_are_same_family(collections)
        
        num_results = 0
        if "search_metadata" in response:
            num_results = response["search_metadata"].get("total_items", 0)
        
        if not collections:
            return {
                "status": "⚠️ NO DATA",
                "collections": [],
                "families": set(),
                "is_single": True,
                "num_results": 0,
                "error": None
            }
        
        return {
            "status": "✅ PASS" if is_same_family else "❌ MIXED",
            "collections": collections,
            "families": families,
            "is_single": is_same_family,
            "num_results": num_results,
            "error": None
        }
        
    except httpx.TimeoutException:
        return {"status": "⏱️ TIMEOUT", "collections": [], "families": set(), "is_single": False, "num_results": 0, "error": "Timeout"}
    except httpx.HTTPStatusError as e:
        return {"status": f"❌ HTTP {e.response.status_code}", "collections": [], "families": set(), "is_single": False, "num_results": 0, "error": str(e)}
    except Exception as e:
        return {"status": "❌ ERROR", "collections": [], "families": set(), "is_single": False, "num_results": 0, "error": str(e)}


async def run_category_tests(category_filter: Optional[str] = None):
    """Run tests for a specific category or all."""
    
    # Get API endpoint dynamically
    api_endpoint = get_api_endpoint()
    
    # Filter queries
    if category_filter:
        queries = [q for q in QUICK_START_QUERIES if category_filter.lower() in q.category.lower()]
    else:
        queries = QUICK_START_QUERIES
    
    print("\n" + "="*120)
    print(f"QUICK START QUERIES TEST - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"API: {api_endpoint}")
    print(f"Testing: {len(queries)} queries" + (f" (category: {category_filter})" if category_filter else " (all)"))
    print("="*120)
    
    # Table header
    print(f"\n{'Cat':<10} | {'Location':<15} | {'Expected':<25} | {'Actual Collections':<35} | {'#':<4} | {'Status':<12}")
    print("-"*120)
    
    results = []
    passed = 0
    failed = 0
    
    for tc in queries:
        result = await test_single_query(tc, api_endpoint)
        results.append((tc, result))
        
        # Format collections for display
        coll_str = ", ".join(result["collections"][:3])
        if len(result["collections"]) > 3:
            coll_str += f" (+{len(result['collections'])-3})"
        
        # Print row
        print(f"{tc.category:<10} | {truncate(tc.location, 15):<15} | {truncate(tc.expected_collection, 25):<25} | {truncate(coll_str, 35):<35} | {result['num_results']:<4} | {result['status']:<12}")
        
        if result["is_single"] and result["num_results"] > 0:
            passed += 1
        elif result["status"] == "⚠️ NO DATA":
            pass  # Don't count as failed
        else:
            failed += 1
    
    # Summary
    print("-"*120)
    print(f"\n📊 SUMMARY: {passed} passed, {failed} failed, {len(queries) - passed - failed} warnings")
    
    # Show failures in detail
    failures = [(tc, r) for tc, r in results if not r["is_single"] and r["status"] not in ["⚠️ NO DATA", "⏱️ TIMEOUT"]]
    if failures:
        print("\n🚨 MIXED COLLECTION FAILURES (BUG):")
        for tc, r in failures:
            print(f"   Query: {truncate(tc.query, 80)}")
            print(f"   Expected: {tc.expected_collection}")
            print(f"   Actual: {r['collections']}")
            print(f"   Families: {r['families']}")
            print()
    
    return results


async def main():
    """Main entry point - run all tests or by category."""
    import sys
    
    category = None
    if len(sys.argv) > 1:
        category = sys.argv[1]
        print(f"Running tests for category: {category}")
    
    await run_category_tests(category)


if __name__ == "__main__":
    asyncio.run(main())
