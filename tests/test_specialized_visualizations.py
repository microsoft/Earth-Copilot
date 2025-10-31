● Medium: Moderate return (vegetation)
● Dark: Low return (smooth surfaces)"""
Test rendering specialized visualization types beyond optical satellite imagery.
Focus on: MODIS Fire, NASADEM elevation, Sentinel-1 SAR, and ALOS PALSAR.
"""

import asyncio
from pystac_client import Client
import json
import os

STAC_API_URL = "https://planetarycomputer.microsoft.com/api/stac/v1"


# Test scenarios for non-optical visualizations
SPECIALIZED_SCENARIOS = {
    "modis_fires_australia": {
        "name": "MODIS Fire Detection - Australia Bushfires",
        "bbox": [140.0, -38.0, 150.0, -28.0],
        "datetime": "2024-01-01/2024-03-31",  # Australian summer
        "collections": ["modis-14A1-061", "modis-64A1-061"],
        "visualization": {
            "type": "fire_thermal",
            "description": "Thermal anomalies and fire detection (NOT optical imagery)",
            "assets": ["FireMask", "MaxFRP", "QA"],
            "colormap": "modis-14A1|A2",
            "gradient": "Black → Red → Orange → Yellow (increasing fire intensity)"
        }
    },
    "nasadem_grand_canyon": {
        "name": "NASADEM Elevation - Grand Canyon",
        "bbox": [-113.0, 35.5, -111.5, 36.5],
        "datetime": None,  # Static DEM
        "collections": ["nasadem"],
        "visualization": {
            "type": "elevation_dem",
            "description": "Digital Elevation Model - terrain height (NOT satellite photo)",
            "assets": ["elevation"],
            "colormap": "terrain",
            "gradient": "Blue (low) → Green → Yellow → Brown → White (high elevation)"
        }
    },
    "sentinel1_sar_amazon": {
        "name": "Sentinel-1 SAR - Amazon Rainforest",
        "bbox": [-70.0, -10.0, -65.0, -5.0],
        "datetime": "2024-01-01/2024-12-31",
        "collections": ["sentinel-1-rtc"],
        "visualization": {
            "type": "radar_sar",
            "description": "Synthetic Aperture Radar - surface texture (NOT optical)",
            "assets": ["vv", "vh"],
            "colormap": "gray",
            "gradient": "Black → Gray → White (radar backscatter intensity)"
        }
    },
    "alos_palsar_indonesia": {
        "name": "ALOS PALSAR - Indonesian Deforestation",
        "bbox": [100.0, -5.0, 110.0, 5.0],
        "datetime": None,  # Mosaic product
        "collections": ["alos-palsar-mosaic"],
        "visualization": {
            "type": "radar_mosaic",
            "description": "L-band SAR mosaic - forest structure (NOT optical)",
            "assets": ["HH", "HV"],
            "colormap": "viridis",
            "gradient": "Purple → Blue → Green → Yellow (radar return strength)"
        }
    }
}


async def search_and_verify(scenario_id: str, config: dict):
    """Search for items and verify they have the expected assets."""
    
    print(f"\n{'='*80}")
    print(f"TESTING: {config['name']}")
    print(f"{'='*80}")
    print(f"Type: {config['visualization']['type']}")
    print(f"Description: {config['visualization']['description']}")
    print(f"Expected gradient: {config['visualization']['gradient']}")
    
    catalog = Client.open(STAC_API_URL)
    
    results = {
        "scenario_id": scenario_id,
        "name": config["name"],
        "visualization_type": config["visualization"]["type"],
        "collections_tested": config["collections"],
        "collection_results": []
    }
    
    for collection_id in config["collections"]:
        print(f"\nSearching: {collection_id}")
        
        try:
            search_params = {
                "collections": [collection_id],
                "bbox": config["bbox"],
                "max_items": 5
            }
            
            if config.get("datetime"):
                search_params["datetime"] = config["datetime"]
            
            search = catalog.search(**search_params)
            items = list(search.items())
            
            print(f"  Found: {len(items)} items")
            
            if items:
                # Check first item for expected assets
                item = items[0]
                print(f"  Sample item: {item.id}")
                
                available_assets = list(item.assets.keys())
                print(f"  Assets: {available_assets[:10]}")
                
                # Check if expected assets exist
                expected_assets = config["visualization"]["assets"]
                found_assets = [a for a in expected_assets if a in available_assets]
                
                if found_assets:
                    print(f"  ✓ Found expected assets: {found_assets}")
                else:
                    print(f"  ⚠ Expected assets not found. Looking for alternatives...")
                    # Show what's actually available
                    data_assets = [a for a in available_assets if not a.startswith('rendered')]
                    print(f"  Available data assets: {data_assets[:5]}")
                
                # Check for tilejson/rendering URLs
                tilejson_assets = [k for k, v in item.assets.items() if 'tilejson' in k]
                rendered_assets = [k for k, v in item.assets.items() if 'rendered' in k or 'preview' in k]
                
                print(f"  Tilejson assets: {tilejson_assets}")
                print(f"  Rendered assets: {rendered_assets}")
                
                results["collection_results"].append({
                    "collection": collection_id,
                    "items_found": len(items),
                    "sample_item": item.id,
                    "available_assets": available_assets,
                    "expected_assets_found": found_assets,
                    "tilejson_available": len(tilejson_assets) > 0,
                    "rendered_preview": len(rendered_assets) > 0
                })
            else:
                print(f"  ✗ No items found")
                results["collection_results"].append({
                    "collection": collection_id,
                    "items_found": 0,
                    "error": "No items in this bbox/datetime"
                })
                
        except Exception as e:
            print(f"  ✗ Error: {e}")
            results["collection_results"].append({
                "collection": collection_id,
                "error": str(e)
            })
    
    return results


async def main():
    """Main test execution."""
    
    print("\n" + "="*80)
    print("SPECIALIZED VISUALIZATION DATA INVESTIGATION")
    print("="*80)
    print("\nGoal: Find NON-OPTICAL data that proves we can render beyond satellite photos")
    print("Target types: Fire thermal, Elevation DEM, SAR radar")
    
    all_results = []
    
    for scenario_id, config in SPECIALIZED_SCENARIOS.items():
        result = await search_and_verify(scenario_id, config)
        all_results.append(result)
    
    # Save results
    output_file = os.path.join(os.path.dirname(__file__), "specialized_data_investigation.json")
    with open(output_file, 'w') as f:
        json.dump(all_results, f, indent=2)
    
    print(f"\n{'='*80}")
    print("SUMMARY")
    print(f"{'='*80}")
    
    for result in all_results:
        print(f"\n{result['name']}:")
        print(f"  Type: {result['visualization_type']}")
        
        for coll in result["collection_results"]:
            if "error" in coll and coll.get("items_found", 0) == 0:
                print(f"  ✗ {coll['collection']}: {coll.get('error', 'Failed')}")
            else:
                print(f"  ✓ {coll['collection']}: {coll['items_found']} items")
                if coll.get("tilejson_available"):
                    print(f"    → Tilejson rendering available")
                if coll.get("expected_assets_found"):
                    print(f"    → Has expected assets: {coll['expected_assets_found']}")
    
    print(f"\n✓ Results saved to: {output_file}\n")


if __name__ == "__main__":
    asyncio.run(main())
