"""
Test script to verify STAC collections exist and have data for specific scenarios:
1. MODIS fire data for California wildfires (January 2025)
2. Sentinel-2 for Ukraine farmland
3. Methane emissions data for Permian Basin (2023-2025)
4. Sea level data for U.S. Atlantic coast (past decade)

This test verifies:
- Collection exists in Planetary Computer
- Data is available for the specified area and timeframe
- Items have proper assets for rendering (COG, thumbnails, etc.)
"""

import asyncio
import json
from datetime import datetime
from typing import Dict, List, Any
from pystac_client import Client

# Test scenarios with their parameters
TEST_SCENARIOS = {
    "modis_california_fires": {
        "name": "MODIS California Wildfires - January 2025",
        "collections": [
            "modis-14A1-061",  # MODIS Thermal Anomalies/Fire
            "modis-64A1-061",  # MODIS Burned Area
            "modis-09A1-061"   # MODIS Surface Reflectance
        ],
        "bbox": [-119.0, 33.0, -116.0, 35.0],  # Southern California
        "datetime": "2025-01-01/2025-01-31",
        "description": "Wildfire activity in Southern California, January 2025",
        "expected_min_items": 5
    },
    "ukraine_farmland": {
        "name": "Ukraine Farmland - Sentinel-2",
        "collections": [
            "sentinel-2-l2a",  # Sentinel-2 Level 2A
        ],
        "bbox": [30.0, 48.0, 35.0, 51.0],  # Central/Eastern Ukraine
        "datetime": "2024-06-01/2024-08-31",  # Summer growing season
        "description": "Farmland monitoring in Ukraine",
        "expected_min_items": 10
    },
    "permian_methane": {
        "name": "Permian Basin Methane Emissions (2023-2025)",
        "collections": [
            "emit-ch4plume",  # EMIT Methane plumes
            "sentinel-2-l2a",  # Backup for visual context
        ],
        "bbox": [-104.0, 31.0, -102.0, 33.0],  # Permian Basin, TX/NM
        "datetime": "2023-01-01/2025-01-31",
        "description": "Methane emissions tracking in Permian Basin",
        "expected_min_items": 1
    },
    "atlantic_sea_level": {
        "name": "U.S. Atlantic Coast Sea Level (Past Decade)",
        "collections": [
            "nasadem",  # NASA DEM for elevation reference
            "sentinel-2-l2a",  # For visual coastline tracking
            "landsat-c2-l2",  # Landsat for historical comparison
        ],
        "bbox": [-80.0, 25.0, -70.0, 45.0],  # U.S. Atlantic Coast (FL to ME)
        "datetime": "2015-01-01/2025-01-31",  # Past decade
        "description": "Coastal change monitoring along U.S. Atlantic coast",
        "expected_min_items": 50
    }
}


async def search_stac_collection(
    collection: str,
    bbox: List[float],
    datetime_str: str,
    max_items: int = 10
) -> Dict[str, Any]:
    """
    Search a specific STAC collection for items.
    
    Args:
        collection: Collection ID to search
        bbox: Bounding box [minx, miny, maxx, maxy]
        datetime_str: Datetime range string (e.g., "2024-01-01/2024-12-31")
        max_items: Maximum items to return
        
    Returns:
        Dictionary with search results and metadata
    """
    try:
        # Connect to Planetary Computer STAC API
        catalog = Client.open("https://planetarycomputer.microsoft.com/api/stac/v1")
        
        # Search for items
        search = catalog.search(
            collections=[collection],
            bbox=bbox,
            datetime=datetime_str,
            max_items=max_items
        )
        
        items = list(search.items())
        
        # Analyze available assets
        asset_types = set()
        has_cog = False
        has_thumbnail = False
        has_rendered_preview = False
        
        for item in items[:5]:  # Check first 5 items
            for asset_key, asset in item.assets.items():
                asset_types.add(asset_key)
                if 'image/tiff' in asset.media_type or 'cog' in asset_key.lower():
                    has_cog = True
                if 'thumbnail' in asset_key.lower():
                    has_thumbnail = True
                if 'rendered_preview' in asset_key.lower() or 'tilejson' in asset_key.lower():
                    has_rendered_preview = True
        
        return {
            "collection": collection,
            "success": True,
            "item_count": len(items),
            "asset_types": sorted(list(asset_types)),
            "has_cog": has_cog,
            "has_thumbnail": has_thumbnail,
            "has_rendered_preview": has_rendered_preview,
            "sample_items": [
                {
                    "id": item.id,
                    "datetime": str(item.datetime),
                    "assets": list(item.assets.keys())
                }
                for item in items[:3]
            ]
        }
        
    except Exception as e:
        return {
            "collection": collection,
            "success": False,
            "error": str(e),
            "error_type": type(e).__name__
        }


async def test_scenario(scenario_name: str, scenario_config: Dict[str, Any]) -> Dict[str, Any]:
    """
    Test a complete scenario by checking all its collections.
    
    Args:
        scenario_name: Name of the scenario
        scenario_config: Configuration dictionary with collections, bbox, datetime, etc.
        
    Returns:
        Dictionary with test results
    """
    print(f"\n{'='*80}")
    print(f"Testing: {scenario_config['name']}")
    print(f"{'='*80}")
    print(f"Description: {scenario_config['description']}")
    print(f"Area: {scenario_config['bbox']}")
    print(f"Time Range: {scenario_config['datetime']}")
    print(f"Collections to test: {len(scenario_config['collections'])}")
    
    results = []
    total_items = 0
    
    for collection in scenario_config['collections']:
        print(f"\n  Searching collection: {collection}...")
        
        result = await search_stac_collection(
            collection=collection,
            bbox=scenario_config['bbox'],
            datetime_str=scenario_config['datetime'],
            max_items=20
        )
        
        results.append(result)
        
        if result['success']:
            total_items += result['item_count']
            print(f"    ✅ Found {result['item_count']} items")
            print(f"    Asset types: {', '.join(result['asset_types'][:5])}{'...' if len(result['asset_types']) > 5 else ''}")
            print(f"    Has COG: {result['has_cog']}")
            print(f"    Has Thumbnail: {result['has_thumbnail']}")
            print(f"    Has Rendered Preview: {result['has_rendered_preview']}")
            
            if result['sample_items']:
                print(f"    Sample item: {result['sample_items'][0]['id']}")
        else:
            print(f"    ❌ Error: {result['error']}")
    
    # Determine overall success
    has_data = total_items >= scenario_config['expected_min_items']
    has_working_collection = any(r['success'] and r['item_count'] > 0 for r in results)
    
    print(f"\n  {'='*76}")
    print(f"  Total items found: {total_items} (expected minimum: {scenario_config['expected_min_items']})")
    print(f"  Overall Status: {'✅ PASS' if has_data and has_working_collection else '⚠️  WARNING' if has_working_collection else '❌ FAIL'}")
    
    return {
        "scenario": scenario_name,
        "name": scenario_config['name'],
        "description": scenario_config['description'],
        "total_items": total_items,
        "expected_min_items": scenario_config['expected_min_items'],
        "has_sufficient_data": has_data,
        "has_working_collection": has_working_collection,
        "collection_results": results,
        "status": "PASS" if has_data and has_working_collection else "WARNING" if has_working_collection else "FAIL"
    }


async def run_all_tests():
    """Run all scenario tests."""
    print("="*80)
    print("STAC COLLECTION VERIFICATION TEST")
    print("="*80)
    print(f"Test Date: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"STAC API: https://planetarycomputer.microsoft.com/api/stac/v1")
    print(f"Total Scenarios: {len(TEST_SCENARIOS)}")
    
    all_results = []
    
    for scenario_name, scenario_config in TEST_SCENARIOS.items():
        result = await test_scenario(scenario_name, scenario_config)
        all_results.append(result)
    
    # Summary
    print(f"\n\n{'='*80}")
    print("TEST SUMMARY")
    print(f"{'='*80}")
    
    passed = sum(1 for r in all_results if r['status'] == 'PASS')
    warnings = sum(1 for r in all_results if r['status'] == 'WARNING')
    failed = sum(1 for r in all_results if r['status'] == 'FAIL')
    
    print(f"\nResults:")
    print(f"  ✅ PASS:    {passed}/{len(all_results)}")
    print(f"  ⚠️  WARNING: {warnings}/{len(all_results)}")
    print(f"  ❌ FAIL:    {failed}/{len(all_results)}")
    
    print(f"\nDetailed Results:")
    for result in all_results:
        status_icon = "✅" if result['status'] == 'PASS' else "⚠️" if result['status'] == 'WARNING' else "❌"
        print(f"  {status_icon} {result['name']}")
        print(f"      Items: {result['total_items']} (min: {result['expected_min_items']})")
        
        working_collections = [
            r['collection'] for r in result['collection_results'] 
            if r['success'] and r['item_count'] > 0
        ]
        if working_collections:
            print(f"      Working collections: {', '.join(working_collections)}")
        
        failed_collections = [
            r['collection'] for r in result['collection_results'] 
            if not r['success'] or r['item_count'] == 0
        ]
        if failed_collections:
            print(f"      Failed/Empty collections: {', '.join(failed_collections)}")
    
    # Recommendations
    print(f"\n{'='*80}")
    print("RECOMMENDATIONS")
    print(f"{'='*80}")
    
    for result in all_results:
        if result['status'] == 'FAIL':
            print(f"\n❌ {result['name']}:")
            print(f"   - No working collections found or insufficient data")
            print(f"   - Try different collections or adjust time range/bbox")
        elif result['status'] == 'WARNING':
            print(f"\n⚠️  {result['name']}:")
            print(f"   - Found some data but less than expected")
            print(f"   - Consider expanding search parameters or using different collections")
    
    # Save results to file
    output_file = "stac_collection_verification_results.json"
    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump({
            "test_date": datetime.now().isoformat(),
            "stac_api": "https://planetarycomputer.microsoft.com/api/stac/v1",
            "summary": {
                "total_scenarios": len(all_results),
                "passed": passed,
                "warnings": warnings,
                "failed": failed
            },
            "results": all_results
        }, f, indent=2)
    
    print(f"\n✅ Results saved to: {output_file}")
    
    return all_results


if __name__ == "__main__":
    # Run all tests
    results = asyncio.run(run_all_tests())
    
    # Exit with appropriate code
    failed_count = sum(1 for r in results if r['status'] == 'FAIL')
    exit(0 if failed_count == 0 else 1)
