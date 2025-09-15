# Copyright (c) Microsoft Corporation.
# Licensed under the MIT license.

#!/usr/bin/env python3
"""
STAC Discovery Tool - Find available features and engineer working queries
This tool helps discover what data is actually available in Microsoft Planetary Computer
and generates queries that will return real features.
"""

import asyncio
import aiohttp
import json
from datetime import datetime, timedelta
from typing import Dict, List, Any, Optional
import logging

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class STACDiscovery:
    """Tool to discover available STAC features and generate working queries"""
    
    def __init__(self):
        self.base_url = "https://planetarycomputer.microsoft.com/api/stac/v1"
        self.collections_cache = {}
        
    async def get_collections(self) -> List[Dict[str, Any]]:
        """Get all available collections from Microsoft Planetary Computer"""
        try:
            async with aiohttp.ClientSession() as session:
                url = f"{self.base_url}/collections"
                timeout = aiohttp.ClientTimeout(total=30)
                
                async with session.get(url, timeout=timeout) as response:
                    if response.status == 200:
                        data = await response.json()
                        collections = data.get("collections", [])
                        logger.info(f"✅ Found {len(collections)} collections")
                        return collections
                    else:
                        logger.error(f"❌ Failed to get collections: {response.status}")
                        return []
        except Exception as e:
            logger.error(f"❌ Error getting collections: {e}")
            return []
    
    async def inspect_collection(self, collection_id: str) -> Dict[str, Any]:
        """Get detailed information about a specific collection"""
        try:
            async with aiohttp.ClientSession() as session:
                url = f"{self.base_url}/collections/{collection_id}"
                timeout = aiohttp.ClientTimeout(total=30)
                
                async with session.get(url, timeout=timeout) as response:
                    if response.status == 200:
                        data = await response.json()
                        
                        # Extract key information
                        info = {
                            "id": data.get("id"),
                            "title": data.get("title"),
                            "description": data.get("description", "")[:200] + "..." if len(data.get("description", "")) > 200 else data.get("description", ""),
                            "spatial_extent": data.get("extent", {}).get("spatial", {}).get("bbox", []),
                            "temporal_extent": data.get("extent", {}).get("temporal", {}).get("interval", []),
                            "item_assets": list(data.get("item_assets", {}).keys()) if data.get("item_assets") else [],
                            "properties": data.get("summaries", {}),
                            "keywords": data.get("keywords", []),
                            "providers": [p.get("name") for p in data.get("providers", [])],
                            "license": data.get("license", ""),
                            "links": [{"rel": link.get("rel"), "href": link.get("href")} for link in data.get("links", [])]
                        }
                        
                        logger.info(f"✅ Inspected collection: {collection_id}")
                        return info
                    else:
                        logger.error(f"❌ Failed to inspect collection {collection_id}: {response.status}")
                        return {}
        except Exception as e:
            logger.error(f"❌ Error inspecting collection {collection_id}: {e}")
            return {}
    
    async def search_features(self, collection_id: str, bbox: Optional[List[float]] = None, 
                            datetime_range: Optional[str] = None, limit: int = 10) -> Dict[str, Any]:
        """Search for actual features in a collection"""
        try:
            async with aiohttp.ClientSession() as session:
                url = f"{self.base_url}/search"
                
                # Build search parameters
                search_params = {
                    "collections": [collection_id],
                    "limit": limit
                }
                
                if bbox:
                    search_params["bbox"] = bbox
                    
                if datetime_range:
                    search_params["datetime"] = datetime_range
                
                timeout = aiohttp.ClientTimeout(total=60)
                
                async with session.post(url, json=search_params, timeout=timeout) as response:
                    if response.status == 200:
                        data = await response.json()
                        features = data.get("features", [])
                        
                        # Analyze features
                        analysis = {
                            "collection_id": collection_id,
                            "total_features": len(features),
                            "features": features,
                            "bbox_used": bbox,
                            "datetime_used": datetime_range,
                            "sample_properties": {},
                            "sample_assets": {},
                            "datetime_range_found": [],
                            "bbox_range_found": []
                        }
                        
                        if features:
                            # Analyze first feature
                            first_feature = features[0]
                            analysis["sample_properties"] = first_feature.get("properties", {})
                            analysis["sample_assets"] = list(first_feature.get("assets", {}).keys())
                            
                            # Analyze datetime range of found features
                            datetimes = []
                            bboxes = []
                            
                            for feature in features:
                                if "datetime" in feature.get("properties", {}):
                                    datetimes.append(feature["properties"]["datetime"])
                                
                                if "geometry" in feature and feature["geometry"]:
                                    # Extract bbox from geometry
                                    geom = feature["geometry"]
                                    if geom["type"] == "Polygon" and geom["coordinates"]:
                                        coords = geom["coordinates"][0]
                                        lons = [c[0] for c in coords]
                                        lats = [c[1] for c in coords]
                                        bbox_calc = [min(lons), min(lats), max(lons), max(lats)]
                                        bboxes.append(bbox_calc)
                            
                            if datetimes:
                                analysis["datetime_range_found"] = [min(datetimes), max(datetimes)]
                            
                            if bboxes:
                                # Calculate overall bbox
                                all_west = [b[0] for b in bboxes]
                                all_south = [b[1] for b in bboxes]
                                all_east = [b[2] for b in bboxes]
                                all_north = [b[3] for b in bboxes]
                                analysis["bbox_range_found"] = [min(all_west), min(all_south), max(all_east), max(all_north)]
                        
                        logger.info(f"✅ Found {len(features)} features in {collection_id}")
                        return analysis
                    else:
                        error_text = await response.text()
                        logger.error(f"❌ Search failed for {collection_id}: {response.status} - {error_text}")
                        return {"error": f"HTTP {response.status}: {error_text}", "collection_id": collection_id}
        except Exception as e:
            logger.error(f"❌ Error searching {collection_id}: {e}")
            return {"error": str(e), "collection_id": collection_id}
    
    async def discover_working_parameters(self, collection_ids: List[str]) -> Dict[str, Any]:
        """Discover working spatial and temporal parameters for collections"""
        results = {}
        
        # Test locations - small areas likely to have data
        test_locations = {
            "seattle": [-122.4, 47.5, -122.3, 47.7],           # Seattle, WA
            "san_francisco": [-122.5, 37.7, -122.4, 37.8],     # San Francisco, CA  
            "new_york": [-74.1, 40.7, -74.0, 40.8],            # New York, NY
            "london": [-0.2, 51.4, -0.1, 51.6],                # London, UK
            "paris": [2.2, 48.8, 2.4, 49.0],                   # Paris, France
            "global_small": [-1, -1, 1, 1]                     # Small global area
        }
        
        # Test time periods - recent data more likely
        current_date = datetime.now()
        test_periods = {
            "last_month": f"{(current_date - timedelta(days=30)).isoformat()}Z/{current_date.isoformat()}Z",
            "last_3_months": f"{(current_date - timedelta(days=90)).isoformat()}Z/{current_date.isoformat()}Z",
            "last_year": f"{(current_date - timedelta(days=365)).isoformat()}Z/{current_date.isoformat()}Z",
            "2024": "2024-01-01T00:00:00Z/2024-12-31T23:59:59Z",
            "2023": "2023-01-01T00:00:00Z/2023-12-31T23:59:59Z"
        }
        
        for collection_id in collection_ids:
            logger.info(f"🔍 Discovering parameters for {collection_id}")
            results[collection_id] = {
                "collection_info": await self.inspect_collection(collection_id),
                "search_results": {}
            }
            
            # Try different combinations
            for location_name, bbox in test_locations.items():
                for period_name, datetime_range in test_periods.items():
                    search_key = f"{location_name}_{period_name}"
                    logger.info(f"  Testing {search_key}...")
                    
                    search_result = await self.search_features(
                        collection_id, bbox, datetime_range, limit=5
                    )
                    
                    results[collection_id]["search_results"][search_key] = search_result
                    
                    # If we found features, we can use these parameters
                    if search_result.get("total_features", 0) > 0:
                        logger.info(f"  ✅ {search_key}: Found {search_result['total_features']} features")
                    else:
                        logger.info(f"  ⚪ {search_key}: No features")
                    
                    # Small delay to be nice to the API
                    await asyncio.sleep(0.1)
        
        return results
    
    def generate_working_queries(self, discovery_results: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Generate natural language queries that should work based on discovery results"""
        working_queries = []
        
        for collection_id, results in discovery_results.items():
            collection_info = results.get("collection_info", {})
            search_results = results.get("search_results", {})
            
            # Find successful searches
            successful_searches = []
            for search_key, search_result in search_results.items():
                if search_result.get("total_features", 0) > 0:
                    successful_searches.append((search_key, search_result))
            
            if successful_searches:
                # Take the best result (most features)
                best_search = max(successful_searches, key=lambda x: x[1].get("total_features", 0))
                search_key, search_result = best_search
                
                location_name, period_name = search_key.split("_", 1)
                
                # Generate natural language query
                location_map = {
                    "seattle": "Seattle",
                    "san": "San Francisco", 
                    "new": "New York",
                    "london": "London",
                    "paris": "Paris",
                    "global": "the world"
                }
                
                period_map = {
                    "last": "recent",
                    "month": "last month",
                    "3": "last 3 months", 
                    "year": "last year",
                    "2024": "in 2024",
                    "2023": "in 2023"
                }
                
                # Map collection to data type
                collection_to_query = {
                    "sentinel-2-l2a": "satellite imagery",
                    "sentinel-1-grd": "radar data",
                    "landsat-c2-l2": "satellite imagery", 
                    "modis-mcd14ml": "fire detection data",
                    "naip": "aerial imagery",
                    "cop-dem-glo-30": "elevation data",
                    "era5-pds": "weather data",
                    "modis-13q1-061": "vegetation data"
                }
                
                location_text = next((v for k, v in location_map.items() if k in location_name), location_name)
                period_text = next((v for k, v in period_map.items() if k in period_name), period_name)
                data_type = collection_to_query.get(collection_id, "data")
                
                query_text = f"Show me {data_type} for {location_text} {period_text}"
                
                working_query = {
                    "query": query_text,
                    "collection": collection_id,
                    "expected_features": search_result["total_features"],
                    "bbox": search_result["bbox_used"],
                    "datetime": search_result["datetime_used"],
                    "sample_properties": list(search_result.get("sample_properties", {}).keys())[:5],
                    "sample_assets": search_result.get("sample_assets", [])[:5]
                }
                
                working_queries.append(working_query)
        
        return working_queries

async def main():
    """Main discovery and testing function"""
    print("🔍 STAC Discovery Tool - Finding Available Features")
    print("=" * 60)
    
    discovery = STACDiscovery()
    
    # Key collections from your semantic translator
    priority_collections = [
        "sentinel-2-l2a",      # High-res optical
        "sentinel-1-grd",      # SAR/radar
        "landsat-c2-l2",       # Landsat
        "cop-dem-glo-30",      # Elevation
        "modis-mcd14ml",       # Fire detection
        "naip",                # Aerial imagery
        "era5-pds",            # Weather/climate
        "modis-13q1-061"       # Vegetation
    ]
    
    print(f"🎯 Testing {len(priority_collections)} priority collections...")
    print()
    
    # Discover working parameters
    results = await discovery.discover_working_parameters(priority_collections)
    
    # Generate working queries
    working_queries = discovery.generate_working_queries(results)
    
    print("\n" + "=" * 60)
    print("📊 DISCOVERY RESULTS")
    print("=" * 60)
    
    for collection_id, data in results.items():
        print(f"\n🗂️  {collection_id.upper()}")
        print("-" * 50)
        
        collection_info = data.get("collection_info", {})
        if collection_info:
            print(f"Title: {collection_info.get('title', 'N/A')}")
            print(f"Description: {collection_info.get('description', 'N/A')}")
            if collection_info.get("temporal_extent"):
                print(f"Temporal Range: {collection_info['temporal_extent']}")
        
        # Count successful searches
        search_results = data.get("search_results", {})
        successful = sum(1 for r in search_results.values() if r.get("total_features", 0) > 0)
        total_searches = len(search_results)
        
        print(f"Successful Searches: {successful}/{total_searches}")
        
        if successful > 0:
            # Show best result
            best_result = max(search_results.values(), key=lambda x: x.get("total_features", 0))
            if best_result.get("total_features", 0) > 0:
                print(f"Best Result: {best_result['total_features']} features")
                if best_result.get("sample_properties"):
                    props = list(best_result["sample_properties"].keys())[:5]
                    print(f"Sample Properties: {', '.join(props)}")
        
        print()
    
    print("\n" + "=" * 60) 
    print("🎯 WORKING QUERIES GENERATED")
    print("=" * 60)
    
    for i, query in enumerate(working_queries, 1):
        print(f"\n{i}. Collection: {query['collection']}")
        print(f"   Query: \"{query['query']}\"")
        print(f"   Expected Features: {query['expected_features']}")
        print(f"   Bbox: {query['bbox']}")
        print(f"   Sample Assets: {', '.join(query['sample_assets'][:3])}")
    
    # Save results
    output_file = "stac_discovery_results.json"
    with open(output_file, "w") as f:
        json.dump({
            "discovery_results": results,
            "working_queries": working_queries,
            "timestamp": datetime.now().isoformat()
        }, f, indent=2)
    
    print(f"\n💾 Results saved to: {output_file}")
    print("\n🚀 Ready to test these queries with your Earth Copilot system!")

if __name__ == "__main__":
    asyncio.run(main())
