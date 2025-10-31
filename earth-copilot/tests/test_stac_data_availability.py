"""
Test STAC Data Availability for Mobility Analysis

This script tests whether we can actually get data from the 5 STAC collections
used for mobility analysis. It queries real data for a test location and shows
what's available.

Run this to verify data availability before implementing pixel-based analysis.
"""

import asyncio
import aiohttp
import logging
from typing import Dict, List, Any
from datetime import datetime, timedelta

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


class STACDataTester:
    """Test STAC data availability for mobility analysis."""
    
    def __init__(self, stac_endpoint: str = "https://planetarycomputer.microsoft.com/api/stac/v1"):
        self.stac_endpoint = stac_endpoint
        self.test_locations = {
            "seattle": {"lat": 47.6062, "lon": -122.3321, "name": "Seattle, WA"},
            "florida": {"lat": 28.5383, "lon": -81.3792, "name": "Orlando, FL"},
            "desert": {"lat": 36.1699, "lon": -115.1398, "name": "Las Vegas, NV (desert)"},
            "mountains": {"lat": 39.7392, "lon": -104.9903, "name": "Denver, CO (mountains)"}
        }
    
    def calculate_bbox(self, lat: float, lon: float, radius_miles: float = 50) -> List[float]:
        """Calculate bounding box for analysis radius."""
        import math
        lat_delta = radius_miles / 69.0
        lon_delta = radius_miles / (69.0 * math.cos(math.radians(lat)))
        
        return [
            lon - lon_delta,  # min_lon
            lat - lat_delta,  # min_lat
            lon + lon_delta,  # max_lon
            lat + lat_delta   # max_lat
        ]
    
    async def query_stac_collection(
        self,
        collection: str,
        bbox: List[float],
        datetime_range: str = None,
        query_params: Dict = None,
        limit: int = 10
    ) -> Dict[str, Any]:
        """Query a STAC collection and return detailed results."""
        search_url = f"{self.stac_endpoint}/search"
        
        request_body = {
            "collections": [collection],
            "bbox": bbox,
            "limit": limit
        }
        
        if datetime_range:
            request_body["datetime"] = datetime_range
        
        if query_params:
            request_body["query"] = query_params
        
        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    search_url,
                    json=request_body,
                    timeout=aiohttp.ClientTimeout(total=30)
                ) as response:
                    if response.status == 200:
                        data = await response.json()
                        features = data.get("features", [])
                        
                        # Extract detailed information
                        result = {
                            "success": True,
                            "items_found": len(features),
                            "items": []
                        }
                        
                        for feature in features[:3]:  # Show first 3 items
                            item_info = {
                                "id": feature.get("id"),
                                "datetime": feature.get("properties", {}).get("datetime"),
                                "assets": list(feature.get("assets", {}).keys()),
                                "cloud_cover": feature.get("properties", {}).get("eo:cloud_cover"),
                                "bbox": feature.get("bbox")
                            }
                            
                            # Get sample asset URL
                            assets = feature.get("assets", {})
                            if assets:
                                first_asset = list(assets.keys())[0]
                                item_info["sample_asset"] = {
                                    "name": first_asset,
                                    "href": assets[first_asset].get("href", "")[:100] + "...",
                                    "type": assets[first_asset].get("type")
                                }
                            
                            result["items"].append(item_info)
                        
                        return result
                    else:
                        error_text = await response.text()
                        return {
                            "success": False,
                            "error": f"HTTP {response.status}: {error_text[:200]}"
                        }
        except asyncio.TimeoutError:
            return {"success": False, "error": "Request timeout"}
        except Exception as e:
            return {"success": False, "error": str(e)}
    
    async def test_all_collections(self, location_key: str = "seattle"):
        """Test data availability for all 5 mobility collections."""
        
        location = self.test_locations[location_key]
        lat, lon = location["lat"], location["lon"]
        bbox = self.calculate_bbox(lat, lon, radius_miles=50)
        
        logger.info(f"\n{'='*80}")
        logger.info(f"TESTING DATA AVAILABILITY: {location['name']}")
        logger.info(f"Coordinates: {lat:.4f}°, {lon:.4f}°")
        logger.info(f"Bounding Box: {bbox}")
        logger.info(f"{'='*80}\n")
        
        # Time windows
        end_date = datetime.utcnow()
        start_30d = end_date - timedelta(days=30)
        datetime_range_30d = f"{start_30d.isoformat()}Z/{end_date.isoformat()}Z"
        
        # Test each collection
        collections_to_test = [
            {
                "id": "sentinel-1-grd",
                "name": "Sentinel-1 GRD (Water Detection - SAR)",
                "datetime": datetime_range_30d,
                "query": None
            },
            {
                "id": "sentinel-1-rtc",
                "name": "Sentinel-1 RTC (Terrain Backscatter)",
                "datetime": datetime_range_30d,
                "query": None
            },
            {
                "id": "sentinel-2-l2a",
                "name": "Sentinel-2 L2A (Vegetation - Optical)",
                "datetime": datetime_range_30d,
                "query": {"eo:cloud_cover": {"lt": 20}}
            },
            {
                "id": "cop-dem-glo-30",
                "name": "Copernicus DEM GLO-30 (Elevation)",
                "datetime": None,  # Static dataset
                "query": None
            },
            {
                "id": "modis-14A1-061",
                "name": "MODIS 14A1-061 (Active Fires)",
                "datetime": None,  # Daily composite, no datetime filter
                "query": None
            }
        ]
        
        results = {}
        
        for collection_config in collections_to_test:
            collection_id = collection_config["id"]
            collection_name = collection_config["name"]
            
            logger.info(f"\n📡 Querying: {collection_name}")
            logger.info(f"   Collection ID: {collection_id}")
            
            result = await self.query_stac_collection(
                collection=collection_id,
                bbox=bbox,
                datetime_range=collection_config["datetime"],
                query_params=collection_config["query"],
                limit=10
            )
            
            results[collection_id] = result
            
            if result["success"]:
                logger.info(f"   ✅ SUCCESS - Found {result['items_found']} items")
                
                if result["items_found"] > 0:
                    logger.info(f"\n   📊 Sample Items:")
                    for idx, item in enumerate(result["items"], 1):
                        logger.info(f"      {idx}. ID: {item['id']}")
                        logger.info(f"         Date: {item['datetime']}")
                        logger.info(f"         Assets: {', '.join(item['assets'])}")
                        if item.get("cloud_cover") is not None:
                            logger.info(f"         Cloud Cover: {item['cloud_cover']:.1f}%")
                        if item.get("sample_asset"):
                            logger.info(f"         Sample Asset: {item['sample_asset']['name']} ({item['sample_asset']['type']})")
                        logger.info(f"         URL: {item['sample_asset']['href']}" if item.get("sample_asset") else "")
                else:
                    logger.warning(f"   ⚠️  No items found in this region")
            else:
                logger.error(f"   ❌ FAILED - {result['error']}")
        
        # Summary
        logger.info(f"\n{'='*80}")
        logger.info(f"SUMMARY FOR {location['name']}")
        logger.info(f"{'='*80}")
        
        success_count = sum(1 for r in results.values() if r["success"] and r["items_found"] > 0)
        total_collections = len(collections_to_test)
        
        logger.info(f"\n✅ Collections with data: {success_count}/{total_collections}")
        
        for collection_id, result in results.items():
            status = "✅" if result["success"] and result["items_found"] > 0 else "❌"
            items = result.get("items_found", 0) if result["success"] else 0
            logger.info(f"   {status} {collection_id}: {items} items")
        
        logger.info(f"\n{'='*80}\n")
        
        return results
    
    async def test_multiple_locations(self):
        """Test data availability across multiple test locations."""
        logger.info("\n" + "="*80)
        logger.info("TESTING MULTIPLE LOCATIONS")
        logger.info("="*80 + "\n")
        
        all_results = {}
        
        for location_key, location in self.test_locations.items():
            results = await self.test_all_collections(location_key)
            all_results[location_key] = results
            await asyncio.sleep(1)  # Be nice to the API
        
        # Overall summary
        logger.info("\n" + "="*80)
        logger.info("OVERALL SUMMARY - DATA AVAILABILITY BY LOCATION")
        logger.info("="*80 + "\n")
        
        for location_key, location in self.test_locations.items():
            results = all_results[location_key]
            success_count = sum(1 for r in results.values() if r.get("success") and r.get("items_found", 0) > 0)
            total = len(results)
            
            logger.info(f"{location['name']}: {success_count}/{total} collections have data")
        
        logger.info(f"\n{'='*80}\n")


async def main():
    """Run the STAC data availability tests."""
    tester = STACDataTester()
    
    # Test single location (Seattle)
    print("\n🧪 Testing single location (Seattle)...")
    await tester.test_all_collections("seattle")
    
    # Uncomment to test all locations (takes longer)
    # print("\n🧪 Testing all locations...")
    # await tester.test_multiple_locations()


if __name__ == "__main__":
    asyncio.run(main())
