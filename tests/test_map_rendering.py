"""
Test map rendering for all verified STAC collections.
This script validates that STAC items can be properly displayed on Azure Maps
with appropriate visualization configurations for each dataset type.
"""

import asyncio
import json
from datetime import datetime
from typing import Dict, List, Any
from pystac_client import Client
import os

# Test scenarios with specific STAC queries
TEST_SCENARIOS = {
    "california_fires": {
        "name": "MODIS Fire Detection - California January 2025",
        "bbox": [-124.0, 32.5, -114.0, 42.0],  # California
        "datetime": "2025-01-01/2025-01-31",
        "collections": ["modis-14A1-061", "modis-64A1-061", "modis-09A1-061"],
        "visualization": {
            "type": "fire_detection",
            "primary_layer": "FireMask",
            "color_scheme": "red_heat",
            "opacity": 0.7,
            "blend_mode": "multiply"
        }
    },
    "ukraine_farmland": {
        "name": "Sentinel-2 Agriculture - Ukraine Summer 2024",
        "bbox": [22.0, 44.0, 40.0, 52.0],  # Ukraine
        "datetime": "2024-06-01/2024-08-31",
        "collections": ["sentinel-2-l2a"],
        "visualization": {
            "type": "true_color",
            "bands": ["B04", "B03", "B02"],  # RGB
            "color_scheme": "natural",
            "opacity": 1.0,
            "contrast_enhancement": "histogram"
        }
    },
    "permian_methane": {
        "name": "Methane Emissions - Permian Basin 2023-2025",
        "bbox": [-104.0, 31.0, -102.0, 33.0],  # Permian Basin
        "datetime": "2023-01-01/2025-01-31",
        "collections": ["sentinel-2-l2a", "emit-ch4plume-v1"],
        "visualization": {
            "type": "methane_overlay",
            "primary_layer": "ch4_enhancement",
            "color_scheme": "yellow_orange",
            "opacity": 0.8,
            "threshold": 500  # ppb
        }
    },
    "atlantic_sea_level": {
        "name": "Sea Level Change - Atlantic Coast 2015-2025",
        "bbox": [-81.0, 24.0, -70.0, 45.0],  # U.S. Atlantic Coast
        "datetime": "2015-01-01/2025-01-31",
        "collections": ["sentinel-2-l2a", "landsat-c2-l2", "nasadem"],
        "visualization": {
            "type": "elevation_change",
            "primary_layer": "elevation",
            "color_scheme": "blue_gradient",
            "opacity": 0.6,
            "dem_hillshade": True
        }
    }
}

# Azure Maps rendering configuration
AZURE_MAPS_CONFIG = {
    "base_url": "https://atlas.microsoft.com",
    "api_version": "2.0",
    "tile_format": "pbf",
    "zoom_levels": {
        "min": 0,
        "max": 22,
        "default": 10
    },
    "projection": "EPSG:3857"  # Web Mercator
}

# STAC API configuration
STAC_API_URL = "https://planetarycomputer.microsoft.com/api/stac/v1"


async def search_stac_items(
    scenario_id: str,
    scenario_config: Dict[str, Any],
    max_items: int = 5
) -> Dict[str, Any]:
    """
    Search for STAC items for a specific scenario.
    
    Args:
        scenario_id: Unique identifier for the scenario
        scenario_config: Configuration with bbox, datetime, collections
        max_items: Maximum number of items to retrieve per collection
        
    Returns:
        Dictionary with items and metadata
    """
    print(f"\n{'='*80}")
    print(f"Searching STAC items: {scenario_config['name']}")
    print(f"{'='*80}")
    
    try:
        catalog = Client.open(STAC_API_URL)
        
        results = {
            "scenario_id": scenario_id,
            "scenario_name": scenario_config["name"],
            "search_params": {
                "bbox": scenario_config["bbox"],
                "datetime": scenario_config["datetime"],
                "collections": scenario_config["collections"]
            },
            "items": [],
            "visualization_config": scenario_config["visualization"],
            "timestamp": datetime.utcnow().isoformat()
        }
        
        # Search each collection
        for collection_id in scenario_config["collections"]:
            print(f"\nSearching collection: {collection_id}")
            
            try:
                search = catalog.search(
                    collections=[collection_id],
                    bbox=scenario_config["bbox"],
                    datetime=scenario_config["datetime"],
                    max_items=max_items
                )
                
                items = list(search.items())
                print(f"  Found {len(items)} items")
                
                # Process items for rendering
                for item in items:
                    item_data = {
                        "id": item.id,
                        "collection": collection_id,
                        "bbox": item.bbox,
                        "geometry": item.geometry,
                        "datetime": item.datetime.isoformat() if item.datetime else None,
                        "assets": {},
                        "rendering": {
                            "tile_url": None,
                            "preview_url": None,
                            "cog_url": None
                        }
                    }
                    
                    # Extract rendering URLs from assets
                    for asset_key, asset in item.assets.items():
                        # Check for renderable assets
                        if asset.media_type in ["image/tiff", "image/vnd.stac.geotiff", "application/x-geotiff"]:
                            item_data["rendering"]["cog_url"] = asset.href
                            item_data["assets"][asset_key] = {
                                "href": asset.href,
                                "type": asset.media_type,
                                "roles": asset.roles if hasattr(asset, 'roles') else []
                            }
                        elif "rendered_preview" in asset_key or "preview" in asset_key:
                            item_data["rendering"]["preview_url"] = asset.href
                        elif "tilejson" in asset_key:
                            item_data["rendering"]["tile_url"] = asset.href
                    
                    results["items"].append(item_data)
                
            except Exception as e:
                print(f"  Error searching {collection_id}: {str(e)}")
                results.setdefault("errors", []).append({
                    "collection": collection_id,
                    "error": str(e)
                })
        
        print(f"\nTotal items found: {len(results['items'])}")
        return results
        
    except Exception as e:
        print(f"ERROR: Failed to search STAC: {str(e)}")
        return {
            "scenario_id": scenario_id,
            "error": str(e),
            "timestamp": datetime.utcnow().isoformat()
        }


def generate_map_layer_config(item: Dict[str, Any], viz_config: Dict[str, Any]) -> Dict[str, Any]:
    """
    Generate Azure Maps layer configuration for a STAC item.
    
    Args:
        item: STAC item data with rendering URLs
        viz_config: Visualization configuration for the scenario
        
    Returns:
        Azure Maps layer configuration
    """
    layer_config = {
        "id": f"layer_{item['id']}",
        "type": "RasterLayer",
        "source": {
            "type": "raster",
            "tiles": []
        },
        "paint": {
            "raster-opacity": viz_config.get("opacity", 1.0),
            "raster-fade-duration": 300
        },
        "metadata": {
            "stac_id": item["id"],
            "collection": item["collection"],
            "datetime": item["datetime"]
        }
    }
    
    # Configure tile source
    if item["rendering"]["tile_url"]:
        layer_config["source"]["tiles"].append(item["rendering"]["tile_url"])
    elif item["rendering"]["cog_url"]:
        # Use COG with titiler for dynamic tiling
        titiler_url = f"https://planetarycomputer.microsoft.com/api/data/v1/item/tiles/{{z}}/{{x}}/{{y}}.png?collection={item['collection']}&item={item['id']}"
        layer_config["source"]["tiles"].append(titiler_url)
    elif item["rendering"]["preview_url"]:
        # Fallback to static preview
        layer_config["type"] = "ImageLayer"
        layer_config["source"] = {
            "type": "image",
            "url": item["rendering"]["preview_url"],
            "coordinates": [
                [item["bbox"][0], item["bbox"][3]],  # top-left
                [item["bbox"][2], item["bbox"][3]],  # top-right
                [item["bbox"][2], item["bbox"][1]],  # bottom-right
                [item["bbox"][0], item["bbox"][1]]   # bottom-left
            ]
        }
    
    # Apply visualization-specific styling
    viz_type = viz_config.get("type")
    
    if viz_type == "fire_detection":
        layer_config["paint"]["raster-saturation"] = 0.5
        layer_config["paint"]["raster-hue-rotate"] = 0  # Red emphasis
        layer_config["paint"]["raster-brightness-max"] = 1.2
    
    elif viz_type == "true_color":
        layer_config["paint"]["raster-saturation"] = 1.0
        layer_config["paint"]["raster-contrast"] = 0.1
    
    elif viz_type == "methane_overlay":
        layer_config["paint"]["raster-saturation"] = 0.8
        layer_config["paint"]["raster-hue-rotate"] = 30  # Yellow-orange
    
    elif viz_type == "elevation_change":
        layer_config["paint"]["raster-saturation"] = 0.6
        layer_config["paint"]["raster-hue-rotate"] = 200  # Blue gradient
    
    return layer_config


def generate_map_html(scenario_results: Dict[str, Any], output_file: str) -> str:
    """
    Generate an HTML file with Azure Maps visualization.
    
    Args:
        scenario_results: Results from STAC search with items
        output_file: Path to output HTML file
        
    Returns:
        Path to generated HTML file
    """
    scenario_name = scenario_results["scenario_name"]
    items = scenario_results.get("items", [])
    viz_config = scenario_results.get("visualization_config", {})
    
    # Calculate center from bbox
    bbox = scenario_results["search_params"]["bbox"]
    center_lon = (bbox[0] + bbox[2]) / 2
    center_lat = (bbox[1] + bbox[3]) / 2
    
    # Generate layer configurations
    layers = []
    for item in items[:5]:  # Limit to first 5 items for performance
        layer_config = generate_map_layer_config(item, viz_config)
        layers.append(layer_config)
    
    html_content = f"""<!DOCTYPE html>
<html>
<head>
    <title>{scenario_name} - Map Rendering Test</title>
    <meta charset="utf-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    
    <!-- Azure Maps SDK -->
    <link rel="stylesheet" href="https://atlas.microsoft.com/sdk/javascript/mapcontrol/2/atlas.min.css" type="text/css" />
    <script src="https://atlas.microsoft.com/sdk/javascript/mapcontrol/2/atlas.min.js"></script>
    
    <style>
        body {{
            margin: 0;
            padding: 0;
            font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
        }}
        #map {{
            position: absolute;
            width: 100%;
            height: 100%;
        }}
        .info-panel {{
            position: absolute;
            top: 10px;
            left: 10px;
            background: rgba(255, 255, 255, 0.95);
            padding: 15px;
            border-radius: 8px;
            box-shadow: 0 2px 8px rgba(0,0,0,0.2);
            max-width: 350px;
            z-index: 1000;
        }}
        .info-panel h3 {{
            margin: 0 0 10px 0;
            color: #0078D4;
        }}
        .info-panel p {{
            margin: 5px 0;
            font-size: 14px;
        }}
        .legend {{
            position: absolute;
            bottom: 30px;
            left: 10px;
            background: rgba(255, 255, 255, 0.95);
            padding: 10px;
            border-radius: 8px;
            box-shadow: 0 2px 8px rgba(0,0,0,0.2);
            z-index: 1000;
        }}
        .legend-title {{
            font-weight: bold;
            margin-bottom: 5px;
        }}
        .legend-item {{
            display: flex;
            align-items: center;
            margin: 5px 0;
        }}
        .legend-color {{
            width: 20px;
            height: 20px;
            margin-right: 8px;
            border: 1px solid #ccc;
        }}
        .status {{
            margin-top: 10px;
            padding: 8px;
            background: #e8f5e9;
            border-left: 4px solid #4caf50;
            border-radius: 4px;
        }}
        .error {{
            background: #ffebee;
            border-left-color: #f44336;
        }}
    </style>
</head>
<body>
    <div id="map"></div>
    
    <div class="info-panel">
        <h3>{scenario_name}</h3>
        <p><strong>Items Loaded:</strong> {len(items)}</p>
        <p><strong>Visualization:</strong> {viz_config.get('type', 'N/A')}</p>
        <p><strong>Date Range:</strong> {scenario_results['search_params']['datetime']}</p>
        <div id="status" class="status">
            ✓ Map initialized successfully
        </div>
    </div>
    
    <div class="legend">
        <div class="legend-title">Legend</div>
        <div id="legend-content"></div>
    </div>

    <script>
        // Azure Maps configuration
        const subscriptionKey = 'YOUR_AZURE_MAPS_KEY'; // Note: Replace with actual key
        
        // Initialize map
        const map = new atlas.Map('map', {{
            center: [{center_lon}, {center_lat}],
            zoom: 8,
            style: 'satellite_road_labels',
            view: 'Auto',
            authOptions: {{
                authType: 'subscriptionKey',
                subscriptionKey: subscriptionKey
            }}
        }});
        
        // Layer configurations from STAC items
        const layerConfigs = {json.dumps(layers, indent=12)};
        
        map.events.add('ready', function() {{
            console.log('Map ready, adding layers...');
            
            // Add each layer to the map
            layerConfigs.forEach((layerConfig, index) => {{
                try {{
                    if (layerConfig.type === 'RasterLayer' && layerConfig.source.tiles.length > 0) {{
                        // Add raster tile layer
                        const source = new atlas.source.RasterTileSource(layerConfig.id + '_source', {{
                            tiles: layerConfig.source.tiles,
                            tileSize: 256
                        }});
                        
                        map.sources.add(source);
                        
                        const layer = new atlas.layer.TileLayer({{
                            source: source,
                            opacity: layerConfig.paint['raster-opacity']
                        }});
                        
                        map.layers.add(layer);
                        console.log(`Added raster layer: ${{layerConfig.id}}`);
                    }}
                    else if (layerConfig.type === 'ImageLayer') {{
                        // Add static image layer
                        const layer = new atlas.layer.ImageLayer({{
                            url: layerConfig.source.url,
                            coordinates: layerConfig.source.coordinates,
                            opacity: layerConfig.paint['raster-opacity']
                        }});
                        
                        map.layers.add(layer);
                        console.log(`Added image layer: ${{layerConfig.id}}`);
                    }}
                }} catch (error) {{
                    console.error(`Error adding layer ${{layerConfig.id}}:`, error);
                    document.getElementById('status').innerHTML = `⚠ Error loading layer ${{index + 1}}`;
                    document.getElementById('status').classList.add('error');
                }}
            }});
            
            // Update status
            if (layerConfigs.length > 0) {{
                document.getElementById('status').innerHTML = `✓ Loaded ${{layerConfigs.length}} layers`;
            }} else {{
                document.getElementById('status').innerHTML = '⚠ No layers to display';
                document.getElementById('status').classList.add('error');
            }}
            
            // Generate legend
            generateLegend();
        }});
        
        function generateLegend() {{
            const vizType = '{viz_config.get("type", "")}';
            const legendContent = document.getElementById('legend-content');
            
            let legendHtml = '';
            
            if (vizType === 'fire_detection') {{
                legendHtml = `
                    <div class="legend-item">
                        <div class="legend-color" style="background: #ff0000;"></div>
                        <span>Active Fire</span>
                    </div>
                    <div class="legend-item">
                        <div class="legend-color" style="background: #ffaa00;"></div>
                        <span>High Temperature</span>
                    </div>
                `;
            }} else if (vizType === 'true_color') {{
                legendHtml = `
                    <div class="legend-item">
                        <div class="legend-color" style="background: #00ff00;"></div>
                        <span>Vegetation</span>
                    </div>
                    <div class="legend-item">
                        <div class="legend-color" style="background: #8b4513;"></div>
                        <span>Bare Soil</span>
                    </div>
                `;
            }} else if (vizType === 'methane_overlay') {{
                legendHtml = `
                    <div class="legend-item">
                        <div class="legend-color" style="background: #ffff00;"></div>
                        <span>High Methane</span>
                    </div>
                    <div class="legend-item">
                        <div class="legend-color" style="background: #ff8800;"></div>
                        <span>Moderate Methane</span>
                    </div>
                `;
            }} else if (vizType === 'elevation_change') {{
                legendHtml = `
                    <div class="legend-item">
                        <div class="legend-color" style="background: #0000ff;"></div>
                        <span>Below Sea Level</span>
                    </div>
                    <div class="legend-item">
                        <div class="legend-color" style="background: #ffffff;"></div>
                        <span>Sea Level</span>
                    </div>
                `;
            }}
            
            legendContent.innerHTML = legendHtml;
        }}
    </script>
</body>
</html>"""
    
    # Write HTML file
    with open(output_file, 'w', encoding='utf-8') as f:
        f.write(html_content)
    
    print(f"\n✓ Generated map HTML: {output_file}")
    return output_file


async def test_scenario_rendering(
    scenario_id: str,
    scenario_config: Dict[str, Any],
    output_dir: str
) -> Dict[str, Any]:
    """
    Test rendering for a single scenario.
    
    Args:
        scenario_id: Unique identifier for the scenario
        scenario_config: Configuration with bbox, datetime, collections
        output_dir: Directory to save output files
        
    Returns:
        Test results with rendering status
    """
    print(f"\n{'#'*80}")
    print(f"TESTING SCENARIO: {scenario_id}")
    print(f"{'#'*80}")
    
    # Search for STAC items
    search_results = await search_stac_items(scenario_id, scenario_config)
    
    # Check if we found items
    if "error" in search_results:
        return {
            "scenario_id": scenario_id,
            "status": "FAILED",
            "error": search_results["error"]
        }
    
    items_found = len(search_results.get("items", []))
    
    if items_found == 0:
        return {
            "scenario_id": scenario_id,
            "status": "WARNING",
            "message": "No items found for rendering"
        }
    
    # Generate map HTML
    html_file = os.path.join(output_dir, f"{scenario_id}_map.html")
    generate_map_html(search_results, html_file)
    
    # Generate JSON report
    json_file = os.path.join(output_dir, f"{scenario_id}_rendering.json")
    with open(json_file, 'w', encoding='utf-8') as f:
        json.dump(search_results, f, indent=2)
    
    print(f"\n✓ Saved rendering data: {json_file}")
    
    # Calculate rendering statistics
    items_with_tiles = sum(1 for item in search_results["items"] if item["rendering"]["tile_url"])
    items_with_cog = sum(1 for item in search_results["items"] if item["rendering"]["cog_url"])
    items_with_preview = sum(1 for item in search_results["items"] if item["rendering"]["preview_url"])
    
    return {
        "scenario_id": scenario_id,
        "scenario_name": scenario_config["name"],
        "status": "PASS",
        "items_found": items_found,
        "rendering_stats": {
            "items_with_tiles": items_with_tiles,
            "items_with_cog": items_with_cog,
            "items_with_preview": items_with_preview,
            "renderable_items": max(items_with_tiles, items_with_cog, items_with_preview)
        },
        "output_files": {
            "html": html_file,
            "json": json_file
        },
        "visualization_config": scenario_config["visualization"]
    }


async def main():
    """Main test execution."""
    print("\n" + "="*80)
    print("MAP RENDERING TEST - All STAC Collections")
    print("="*80)
    
    # Create output directory
    output_dir = os.path.join(os.path.dirname(__file__), "map_rendering_output")
    os.makedirs(output_dir, exist_ok=True)
    print(f"\nOutput directory: {output_dir}")
    
    # Run tests for all scenarios
    all_results = []
    
    for scenario_id, scenario_config in TEST_SCENARIOS.items():
        result = await test_scenario_rendering(scenario_id, scenario_config, output_dir)
        all_results.append(result)
    
    # Generate summary report
    print("\n" + "="*80)
    print("RENDERING TEST SUMMARY")
    print("="*80)
    
    passed = sum(1 for r in all_results if r["status"] == "PASS")
    failed = sum(1 for r in all_results if r["status"] == "FAILED")
    warnings = sum(1 for r in all_results if r["status"] == "WARNING")
    
    for result in all_results:
        status_icon = "✓" if result["status"] == "PASS" else "⚠" if result["status"] == "WARNING" else "✗"
        print(f"\n{status_icon} {result['scenario_id']}: {result['status']}")
        
        if result["status"] == "PASS":
            print(f"   Items found: {result['items_found']}")
            print(f"   Renderable items: {result['rendering_stats']['renderable_items']}")
            print(f"   HTML: {result['output_files']['html']}")
        elif "error" in result:
            print(f"   Error: {result['error']}")
        elif "message" in result:
            print(f"   {result['message']}")
    
    print(f"\n{'='*80}")
    print(f"Total Scenarios: {len(all_results)}")
    print(f"Passed: {passed}")
    print(f"Warnings: {warnings}")
    print(f"Failed: {failed}")
    print(f"{'='*80}\n")
    
    # Save summary report
    summary_file = os.path.join(output_dir, "rendering_test_summary.json")
    summary = {
        "timestamp": datetime.utcnow().isoformat(),
        "total_scenarios": len(all_results),
        "passed": passed,
        "warnings": warnings,
        "failed": failed,
        "scenarios": all_results
    }
    
    with open(summary_file, 'w', encoding='utf-8') as f:
        json.dump(summary, f, indent=2)
    
    print(f"✓ Summary saved: {summary_file}\n")
    
    # Print instructions
    print("="*80)
    print("NEXT STEPS")
    print("="*80)
    print("\n1. Open the generated HTML files in a browser:")
    for result in all_results:
        if result["status"] == "PASS":
            print(f"   - {result['output_files']['html']}")
    
    print("\n2. Update Azure Maps subscription key in HTML files:")
    print("   - Replace 'YOUR_AZURE_MAPS_KEY' with actual key")
    
    print("\n3. Verify visualizations:")
    print("   - Check that layers are displayed correctly")
    print("   - Verify color schemes match visualization configs")
    print("   - Test zoom and pan interactions")
    
    print("\n4. Integration with Earth Copilot:")
    print("   - Copy successful rendering configs to frontend")
    print("   - Update MapView component with layer configurations")
    print("   - Test end-to-end comparison queries\n")


if __name__ == "__main__":
    asyncio.run(main())
