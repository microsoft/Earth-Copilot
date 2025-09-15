# Copyright (c) Microsoft Corporation.
# Licensed under the MIT license.

#!/usr/bin/env python3
"""
Quick STAC Catalog Feature Test
Efficiently test each collection type to prove they have available features.
Focus on proving different catalog types work rather than diverse locations.
"""

import asyncio
import aiohttp
import json
from datetime import datetime, timedelta
from typing import Dict, List, Any, Optional
import logging

# Set up logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

class QuickSTACTest:
    """Quick test to prove each collection type has available features"""
    
    def __init__(self):
        self.base_url = "https://planetarycomputer.microsoft.com/api/stac/v1"
        
        # Focus on key collection types from your semantic translator
        self.test_collections = {
            # High-priority optical
            "sentinel-2-l2a": {"type": "Optical Satellite", "bbox": [-122.5, 47.5, -122.3, 47.7]},  # Seattle
            "landsat-c2-l2": {"type": "Optical Satellite", "bbox": [-74.1, 40.7, -74.0, 40.8]},    # NYC
            
            # SAR/Radar
            "sentinel-1-grd": {"type": "SAR/Radar", "bbox": [-122.5, 47.5, -122.3, 47.7]},        # Seattle
            
            # Elevation/DEM
            "cop-dem-glo-30": {"type": "Elevation/DEM", "bbox": [-122.5, 47.5, -122.3, 47.7]},    # Seattle
            "nasadem": {"type": "Elevation/DEM", "bbox": [-122.5, 47.5, -122.3, 47.7]},           # Seattle
            
            # Climate/Weather
            "era5-pds": {"type": "Climate/Weather", "bbox": [-122.5, 47.5, -122.3, 47.7]},        # Seattle
            "daymet-daily-na": {"type": "Climate/Weather", "bbox": [-122.5, 47.5, -122.3, 47.7]}, # Seattle
            
            # Fire Detection
            "modis-mcd14ml": {"type": "Fire Detection", "bbox": [-120.0, 36.0, -119.0, 37.0]},    # CA fire area
            "viirs-thermal-anomalies-nrt": {"type": "Fire Detection", "bbox": [-120.0, 36.0, -119.0, 37.0]},
            
            # Agriculture/Vegetation
            "modis-13q1-061": {"type": "Agriculture/Vegetation", "bbox": [-100.0, 40.0, -99.0, 41.0]}, # Midwest
            "hls-l30": {"type": "Agriculture/Vegetation", "bbox": [-100.0, 40.0, -99.0, 41.0]},
            
            # High-res Aerial
            "naip": {"type": "High-res Aerial", "bbox": [-122.5, 47.5, -122.3, 47.7]},            # Seattle
            
            # Ocean/Marine
            "modis-sst": {"type": "Ocean/Marine", "bbox": [-125.0, 45.0, -124.0, 46.0]},          # Pacific Coast
        }
        
        # Test recent time periods (more likely to have data)
        current_date = datetime.now()
        self.test_periods = {
            "last_30_days": f"{(current_date - timedelta(days=30)).isoformat()}Z/{current_date.isoformat()}Z",
            "last_3_months": f"{(current_date - timedelta(days=90)).isoformat()}Z/{current_date.isoformat()}Z",
            "2024": "2024-01-01T00:00:00Z/2024-12-31T23:59:59Z",
            "2023": "2023-01-01T00:00:00Z/2023-12-31T23:59:59Z"
        }
    
    async def test_collection(self, collection_id: str, collection_info: Dict[str, Any]) -> Dict[str, Any]:
        """Test a single collection for available features"""
        logger.info(f"🔍 Testing collection: {collection_id} ({collection_info['type']})")
        
        bbox = collection_info["bbox"]
        results = {
            "collection_id": collection_id,
            "type": collection_info["type"],
            "bbox": bbox,
            "tests": {},
            "best_result": None,
            "total_features_found": 0
        }
        
        # Test each time period
        for period_name, datetime_range in self.test_periods.items():
            try:
                features = await self.search_features(collection_id, bbox, datetime_range, limit=10)
                
                test_result = {
                    "period": period_name,
                    "datetime": datetime_range,
                    "feature_count": len(features),
                    "success": len(features) > 0,
                    "sample_feature": features[0] if features else None
                }
                
                results["tests"][period_name] = test_result
                results["total_features_found"] += len(features)
                
                if len(features) > 0 and not results["best_result"]:
                    results["best_result"] = test_result
                
                logger.info(f"  📅 {period_name}: {len(features)} features")
                
                # Small delay to be nice to API
                await asyncio.sleep(0.1)
                
            except Exception as e:
                logger.error(f"  ❌ {period_name}: Error - {e}")
                results["tests"][period_name] = {
                    "period": period_name,
                    "datetime": datetime_range,
                    "feature_count": 0,
                    "success": False,
                    "error": str(e)
                }
        
        return results
    
    async def search_features(self, collection_id: str, bbox: List[float], 
                            datetime_range: str, limit: int = 10) -> List[Dict[str, Any]]:
        """Search for features in a collection"""
        try:
            async with aiohttp.ClientSession() as session:
                url = f"{self.base_url}/search"
                
                search_params = {
                    "collections": [collection_id],
                    "bbox": bbox,
                    "datetime": datetime_range,
                    "limit": limit
                }
                
                timeout = aiohttp.ClientTimeout(total=30)
                
                async with session.post(url, json=search_params, timeout=timeout) as response:
                    if response.status == 200:
                        data = await response.json()
                        return data.get("features", [])
                    else:
                        error_text = await response.text()
                        logger.warning(f"Search failed for {collection_id}: {response.status} - {error_text}")
                        return []
        except Exception as e:
            logger.error(f"Error searching {collection_id}: {e}")
            return []
    
    async def run_all_tests(self) -> Dict[str, Any]:
        """Run tests on all collections"""
        print("🎯 Quick STAC Catalog Feature Test")
        print("=" * 60)
        print(f"Testing {len(self.test_collections)} key collections from your semantic translator...")
        print()
        
        all_results = {}
        successful_collections = []
        failed_collections = []
        
        # Test each collection
        for collection_id, collection_info in self.test_collections.items():
            result = await self.test_collection(collection_id, collection_info)
            all_results[collection_id] = result
            
            if result["total_features_found"] > 0:
                successful_collections.append(collection_id)
            else:
                failed_collections.append(collection_id)
        
        # Generate summary
        summary = {
            "test_timestamp": datetime.now().isoformat(),
            "total_collections_tested": len(self.test_collections),
            "successful_collections": len(successful_collections),
            "failed_collections": len(failed_collections),
            "success_rate": len(successful_collections) / len(self.test_collections) * 100,
            "results": all_results,
            "working_queries": self.generate_working_queries(all_results)
        }
        
        return summary
    
    def generate_working_queries(self, results: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Generate natural language queries that should work"""
        working_queries = []
        
        # Map collections to natural language
        collection_to_query = {
            "sentinel-2-l2a": "satellite imagery of Seattle",
            "landsat-c2-l2": "satellite imagery of New York",
            "sentinel-1-grd": "radar data for Seattle",
            "cop-dem-glo-30": "elevation data for Seattle",
            "nasadem": "elevation data for Seattle",
            "era5-pds": "weather data for Seattle",
            "daymet-daily-na": "weather data for Seattle",
            "modis-mcd14ml": "fire detection data for California",
            "viirs-thermal-anomalies-nrt": "fire detection data for California",
            "modis-13q1-061": "vegetation data for Midwest",
            "hls-l30": "vegetation data for Midwest",
            "naip": "aerial imagery of Seattle",
            "modis-sst": "sea surface temperature for Pacific Coast"
        }
        
        for collection_id, result in results.items():
            if result["total_features_found"] > 0 and result["best_result"]:
                best = result["best_result"]
                
                # Create working query
                query_text = f"Show me {collection_to_query.get(collection_id, f'{collection_id} data')}"
                
                working_query = {
                    "query": query_text,
                    "collection": collection_id,
                    "type": result["type"],
                    "expected_features": best["feature_count"],
                    "bbox": result["bbox"],
                    "datetime": best["datetime"],
                    "working_period": best["period"]
                }
                
                working_queries.append(working_query)
        
        return working_queries
    
    def print_summary(self, summary: Dict[str, Any]):
        """Print a formatted summary of results"""
        print("\n" + "=" * 60)
        print("📊 QUICK TEST RESULTS SUMMARY")
        print("=" * 60)
        
        print(f"Collections Tested: {summary['total_collections_tested']}")
        print(f"✅ Successful: {summary['successful_collections']}")
        print(f"❌ Failed: {summary['failed_collections']}")
        print(f"Success Rate: {summary['success_rate']:.1f}%")
        print()
        
        # Group by type
        by_type = {}
        for collection_id, result in summary["results"].items():
            type_name = result["type"]
            if type_name not in by_type:
                by_type[type_name] = {"success": 0, "total": 0, "collections": []}
            
            by_type[type_name]["total"] += 1
            by_type[type_name]["collections"].append(collection_id)
            
            if result["total_features_found"] > 0:
                by_type[type_name]["success"] += 1
        
        print("📈 Results by Data Type:")
        print("-" * 30)
        for type_name, stats in by_type.items():
            success_rate = stats["success"] / stats["total"] * 100
            status = "✅" if success_rate > 50 else "⚠️" if success_rate > 0 else "❌"
            print(f"{status} {type_name}: {stats['success']}/{stats['total']} ({success_rate:.0f}%)")
        
        print("\n" + "🎯 WORKING QUERIES GENERATED")
        print("-" * 40)
        
        working_queries = summary["working_queries"]
        if working_queries:
            for i, query in enumerate(working_queries[:10], 1):  # Show top 10
                print(f"{i}. \"{query['query']}\"")
                print(f"   Collection: {query['collection']} ({query['type']})")
                print(f"   Expected Features: {query['expected_features']}")
                print()
        else:
            print("❌ No working queries found - all collections returned 0 features")
        
        print(f"💾 Full results saved to: stac_test_results.json")

async def main():
    """Main function"""
    tester = QuickSTACTest()
    
    # Run all tests
    summary = await tester.run_all_tests()
    
    # Print summary
    tester.print_summary(summary)
    
    # Save results
    output_file = "stac_test_results.json"
    with open(output_file, "w") as f:
        json.dump(summary, f, indent=2)
    
    print(f"\n🚀 Test complete! Use working queries to prove end-to-end functionality.")
    
    # Show example of how to test with your system
    working_queries = summary["working_queries"]
    if working_queries:
        print("\n" + "💡 TEST WITH YOUR SYSTEM:")
        print("-" * 30)
        best_query = working_queries[0]
        print(f"PowerShell test command:")
        print(f'$testQuery = @{{ query = "{best_query["query"]}" }} | ConvertTo-Json')
        print(f'$response = Invoke-RestMethod -Uri "http://localhost:7073/api/query" -Method POST -Body $testQuery -ContentType "application/json"')
        print(f'Write-Host "Features: $($response.data.map_data.features.Count)"')

if __name__ == "__main__":
    asyncio.run(main())
