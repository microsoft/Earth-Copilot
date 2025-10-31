"""
Automated MODIS Fire Data Availability Testing Script

This script queries Microsoft Planetary Computer STAC API for MODIS fire detection data
across multiple locations and date ranges to find available data.

PURPOSE:
- Test MODIS 14A1 (daily fire mask) and 14A2 (8-day fire radiative power)
- Identify which date ranges have actual fire data
- Validate before implementing comparison module

USAGE:
    python test_modis_fire_queries.py
"""

import asyncio
import aiohttp
import json
from typing import Dict, List, Any
from datetime import datetime, timedelta


# Microsoft Planetary Computer STAC API endpoint
STAC_ENDPOINT = "https://planetarycomputer.microsoft.com/api/stac/v1/search"


async def query_stac_api(stac_query: Dict[str, Any]) -> Dict[str, Any]:
    """
    Query STAC API with the given parameters.
    
    Args:
        stac_query: STAC query parameters
    
    Returns:
        STAC response with features
    """
    async with aiohttp.ClientSession() as session:
        async with session.post(STAC_ENDPOINT, json=stac_query) as response:
            if response.status == 200:
                return await response.json()
            else:
                error_text = await response.text()
                raise Exception(f"STAC query failed: {response.status} - {error_text}")


async def test_modis_fire_availability():
    """
    Automated test: Query MODIS fire data for multiple dates/locations
    until we find available data.
    """
    
    print("\n" + "="*80)
    print("MODIS FIRE DATA AVAILABILITY TEST")
    print("="*80)
    print(f"Testing collections: modis-14A1-061 (Daily), modis-14A2-061 (8-Day)")
    print(f"STAC Endpoint: {STAC_ENDPOINT}")
    print("="*80 + "\n")
    
    test_cases = [
        # January 2025 LA Fires (IF AVAILABLE - current date is Oct 2025, so Jan 2025 is in the past)
        {
            "name": "Los Angeles Fires - January 2025",
            "location": "Los Angeles, California",
            "bbox": [-118.668, 33.704, -118.155, 34.337],
            "dates": [
                "2025-01-01/2025-01-10",
                "2025-01-10/2025-01-20",
                "2025-01-01/2025-01-31"  # Full month
            ]
        },
        # Fall 2024 California Fire Season
        {
            "name": "California - Fall 2024",
            "location": "Northern California",
            "bbox": [-122.5, 38.0, -121.5, 39.0],
            "dates": [
                "2024-09-01/2024-09-30",
                "2024-10-01/2024-10-31",
                "2024-11-01/2024-11-30"
            ]
        },
        # Summer 2024 California Fire Season (RELIABLE)
        {
            "name": "California - Summer 2024",
            "location": "Paradise, California area",
            "bbox": [-121.7, 39.7, -121.5, 39.9],
            "dates": [
                "2024-07-01/2024-07-31",
                "2024-08-01/2024-08-31",
                "2024-06-01/2024-06-30"
            ]
        },
        # Australia Bushfires (Southern Hemisphere Summer)
        {
            "name": "Australia - Summer 2024/2025",
            "location": "New South Wales, Australia",
            "bbox": [149.0, -33.9, 151.3, -33.5],
            "dates": [
                "2024-12-01/2024-12-31",
                "2025-01-01/2025-01-31",
                "2024-11-01/2024-11-30"
            ]
        },
        # Recent data (last 30 days from Oct 23, 2025)
        {
            "name": "Recent Global Fires",
            "location": "Western United States",
            "bbox": [-125.0, 32.0, -114.0, 42.0],  # CA, OR, WA, NV
            "dates": [
                "2025-09-23/2025-10-23",  # Last 30 days
                "2025-10-01/2025-10-23"   # This month
            ]
        }
    ]
    
    results = []
    
    for test_location in test_cases:
        print(f"\n{'='*80}")
        print(f"LOCATION: {test_location['name']}")
        print(f"Bbox: {test_location['bbox']}")
        print(f"{'='*80}")
        
        for date_range in test_location["dates"]:
            # Test MODIS 14A1 (Daily Fire Mask)
            await test_single_query(
                collection="modis-14A1-061",
                location_name=test_location['name'],
                bbox=test_location['bbox'],
                date_range=date_range,
                results=results
            )
            
            # Test MODIS 14A2 (8-Day Fire Radiative Power)
            await test_single_query(
                collection="modis-14A2-061",
                location_name=test_location['name'],
                bbox=test_location['bbox'],
                date_range=date_range,
                results=results
            )
    
    # Generate comprehensive report
    generate_report(results)
    
    return results


async def test_single_query(
    collection: str,
    location_name: str,
    bbox: List[float],
    date_range: str,
    results: List[Dict[str, Any]]
):
    """
    Test a single STAC query and record results.
    """
    print(f"\n🔍 Testing: {collection} | {date_range}")
    
    stac_query = {
        "collections": [collection],
        "bbox": bbox,
        "datetime": date_range,
        "limit": 100
    }
    
    try:
        response = await query_stac_api(stac_query)
        features = response.get("features", [])
        feature_count = len(features)
        
        result = {
            "location": location_name,
            "collection": collection,
            "date_range": date_range,
            "bbox": bbox,
            "feature_count": feature_count,
            "success": feature_count > 0,
            "query_time": datetime.now().isoformat(),
            "sample_features": features[:3] if features else []  # First 3 for inspection
        }
        
        results.append(result)
        
        if feature_count > 0:
            print(f"   ✅ FOUND DATA: {feature_count} features")
            
            # Show sample feature details
            if features:
                sample = features[0]
                print(f"   📅 Sample date: {sample.get('properties', {}).get('datetime')}")
                print(f"   🆔 Sample ID: {sample.get('id')}")
                
                # Check for fire-related properties
                props = sample.get('properties', {})
                if 'FireMask' in str(props) or 'MaxFRP' in str(props):
                    print(f"   🔥 Fire properties found in metadata")
        else:
            print(f"   ❌ NO DATA")
            
    except Exception as e:
        print(f"   ❌ QUERY FAILED: {e}")
        results.append({
            "location": location_name,
            "collection": collection,
            "date_range": date_range,
            "bbox": bbox,
            "success": False,
            "error": str(e),
            "query_time": datetime.now().isoformat()
        })


def generate_report(results: List[Dict[str, Any]]):
    """
    Generate comprehensive report from all test results.
    """
    print("\n" + "="*80)
    print("FINAL REPORT: MODIS FIRE DATA AVAILABILITY")
    print("="*80)
    
    successful_queries = [r for r in results if r.get("success")]
    failed_queries = [r for r in results if not r.get("success")]
    
    print(f"\n📊 SUMMARY:")
    print(f"   Total queries: {len(results)}")
    print(f"   Successful: {len(successful_queries)}")
    print(f"   Failed: {len(failed_queries)}")
    print(f"   Success rate: {len(successful_queries)/len(results)*100:.1f}%")
    
    if successful_queries:
        print(f"\n✅ SUCCESSFUL QUERIES ({len(successful_queries)}):")
        print("-" * 80)
        
        # Group by location
        by_location = {}
        for r in successful_queries:
            location = r['location']
            if location not in by_location:
                by_location[location] = []
            by_location[location].append(r)
        
        for location, queries in by_location.items():
            print(f"\n📍 {location}:")
            for q in queries:
                print(f"   - {q['collection']}: {q['date_range']} ({q['feature_count']} features)")
        
        # Recommend best test case for comparison module
        print(f"\n🎯 RECOMMENDED TEST CASE FOR COMPARISON MODULE:")
        best = max(successful_queries, key=lambda x: x['feature_count'])
        print(f"   Location: {best['location']}")
        print(f"   Collection: {best['collection']}")
        print(f"   Date Range: {best['date_range']}")
        print(f"   Features: {best['feature_count']}")
        print(f"   Bbox: {best['bbox']}")
        
        # Suggest before/after dates for comparison
        date_parts = best['date_range'].split('/')
        if len(date_parts) == 2:
            start_date = date_parts[0]
            end_date = date_parts[1]
            print(f"\n   💡 Suggested comparison:")
            print(f"      BEFORE: {start_date} (first day of range)")
            print(f"      AFTER: {end_date} (last day of range)")
    
    else:
        print("\n❌ NO SUCCESSFUL QUERIES")
        print("⚠️ ACTION REQUIRED:")
        print("   1. Check STAC API connectivity")
        print("   2. Verify collection IDs are correct")
        print("   3. Try broader date ranges")
        print("   4. Check if MODIS data requires authentication")
    
    if failed_queries:
        print(f"\n❌ FAILED QUERIES ({len(failed_queries)}):")
        print("-" * 80)
        for q in failed_queries[:5]:  # Show first 5 failures
            print(f"   - {q['location']}: {q['collection']} | {q['date_range']}")
            if 'error' in q:
                print(f"     Error: {q['error']}")
    
    # Save detailed results to JSON file
    output_file = "modis_fire_test_results.json"
    with open(output_file, 'w') as f:
        json.dump(results, f, indent=2)
    
    print(f"\n💾 Detailed results saved to: {output_file}")
    print("="*80 + "\n")


async def test_modis_tile_url_generation():
    """
    Test generating proper TiTiler URLs for MODIS fire data.
    This validates the rendering configuration.
    """
    print("\n" + "="*80)
    print("MODIS TILE URL GENERATION TEST")
    print("="*80)
    
    # Example MODIS feature (structure from actual STAC response)
    sample_feature = {
        "id": "MCD14A1.061_2024_08_01",
        "collection": "modis-14A1-061",
        "properties": {
            "datetime": "2024-08-01T00:00:00Z"
        }
    }
    
    # Generate TiTiler URL for MODIS 14A1 (Fire Mask)
    base_url = "https://planetarycomputer.microsoft.com/api/data/v1"
    
    # MODIS 14A1 configuration
    modis_14a1_url = (
        f"{base_url}/item/tiles/WebMercatorQuad/{{z}}/{{x}}/{{y}}@2x?"
        f"collection={sample_feature['collection']}&"
        f"item={sample_feature['id']}&"
        f"assets=FireMask&"
        f"colormap_name=hot&"  # Black → Red → Yellow → White
        f"rescale=0,9&"  # FireMask values: 0-9
        f"resampling=nearest&"  # Preserve discrete values
        f"return_mask=true"
    )
    
    print(f"\n🔥 MODIS 14A1 (Daily Fire Mask) Tile URL:")
    print(f"   {modis_14a1_url}")
    
    # MODIS 14A2 configuration (8-Day FRP)
    sample_feature_14a2 = {
        "id": "MCD14A2.061_2024_08_01",
        "collection": "modis-14A2-061"
    }
    
    modis_14a2_url = (
        f"{base_url}/item/tiles/WebMercatorQuad/{{z}}/{{x}}/{{y}}@2x?"
        f"collection={sample_feature_14a2['collection']}&"
        f"item={sample_feature_14a2['id']}&"
        f"assets=MaxFRP&"  # Fire Radiative Power
        f"colormap_name=inferno&"  # Dark → Bright
        f"rescale=0,1000&"  # FRP in MW
        f"resampling=bilinear&"  # Smooth gradients
        f"return_mask=true"
    )
    
    print(f"\n🔥 MODIS 14A2 (8-Day FRP) Tile URL:")
    print(f"   {modis_14a2_url}")
    
    print(f"\n✅ Tile URL patterns generated successfully")
    print(f"   These should be used in tileJsonFetcher.ts")
    print("="*80 + "\n")


async def main():
    """
    Run all MODIS fire data tests.
    """
    print("\n" + "="*80)
    print("MODIS FIRE DATA - COMPREHENSIVE TEST SUITE")
    print("Current Date: October 23, 2025")
    print("="*80)
    
    try:
        # Test 1: Query STAC API for available MODIS fire data
        results = await test_modis_fire_availability()
        
        # Test 2: Generate proper tile URLs for rendering
        await test_modis_tile_url_generation()
        
        print("\n✅ ALL TESTS COMPLETED")
        
        # Provide next steps
        print("\n" + "="*80)
        print("NEXT STEPS:")
        print("="*80)
        print("1. Review modis_fire_test_results.json for detailed results")
        print("2. Use recommended test case for comparison module development")
        print("3. Update tileJsonFetcher.ts with MODIS tile URL configuration")
        print("4. Test rendering MODIS tiles on Azure Maps")
        print("5. Implement FireComparisonAgent with GPT-5 Vision")
        print("="*80 + "\n")
        
    except Exception as e:
        print(f"\n❌ TEST SUITE FAILED: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    asyncio.run(main())
