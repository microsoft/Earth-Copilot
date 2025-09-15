# Copyright (c) Microsoft Corporation.
# Licensed under the MIT license.

#!/usr/bin/env python3
"""
Enhanced STAC Collection Analyzer - Deep Probe for Data Availability
Thoroughly tests collections with multiple strategies to find what data exists.
"""

import asyncio
import aiohttp
import json
from datetime import datetime, timedelta
from typing import Dict, List, Tuple, Optional
import logging

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

class DeepSTACAnalyzer:
    def __init__(self):
        self.base_url = "https://planetarycomputer.microsoft.com/api/stac/v1"
        self.session = None
        
        # Multiple test strategies with different time ranges and locations
        self.test_strategies = {
            "global_recent": {
                "datetime": "2024-01-01/2024-12-31",
                "bbox": [-180, -85, 180, 85],  # Global
                "limit": 10
            },
            "global_2023": {
                "datetime": "2023-01-01/2023-12-31", 
                "bbox": [-180, -85, 180, 85],
                "limit": 10
            },
            "global_2022": {
                "datetime": "2022-01-01/2022-12-31",
                "bbox": [-180, -85, 180, 85], 
                "limit": 10
            },
            "usa_recent": {
                "datetime": "2024-01-01/2024-12-31",
                "bbox": [-125, 25, -65, 50],  # Continental US
                "limit": 10
            },
            "california_recent": {
                "datetime": "2024-01-01/2024-12-31",
                "bbox": [-124.4, 32.5, -114.1, 42.0],  # California
                "limit": 10
            },
            "europe_recent": {
                "datetime": "2024-01-01/2024-12-31",
                "bbox": [-10, 35, 40, 70],  # Europe
                "limit": 10
            },
            "global_older": {
                "datetime": "2020-01-01/2021-12-31",
                "bbox": [-180, -85, 180, 85],
                "limit": 10
            },
            "global_very_old": {
                "datetime": "2015-01-01/2019-12-31",
                "bbox": [-180, -85, 180, 85],
                "limit": 10
            },
            "minimal_any_data": {
                "bbox": [-180, -85, 180, 85],  # No datetime filter - any data
                "limit": 5
            },
            "minimal_small_area": {
                "datetime": "2020-01-01/2024-12-31",
                "bbox": [-122.5, 37.7, -122.3, 37.8],  # Small SF Bay Area
                "limit": 5
            }
        }
        
        # Collection categories for organization
        self.collection_categories = {
            "Optical Satellite": ["sentinel-2-l2a", "sentinel-2-l1c", "landsat-c2-l2", "landsat-c2-l1", 
                                "hls-l30", "hls-s30", "modis-09A1-061", "modis-09Q1-061"],
            "Radar": ["sentinel-1-grd", "sentinel-1-rtc", "alos-palsar-mosaic", "alos-dem"],
            "Fire Detection": ["modis-14A1-061", "modis-14A2-061", "modis-64A1-061", "goes-glm"],
            "Climate": ["era5-pds", "terraclimate", "noaa-climate-normals-tabular", "noaa-climate-normals-netcdf"],
            "Vegetation": ["modis-13Q1-061", "modis-13A1-061", "modis-15A2H-061", "modis-17A2H-061", "modis-17A3HGF-061"],
            "Ocean": ["cop-dem-glo-30", "cop-dem-glo-90", "aster-l1t", "nasadem"],
            "Demographics": ["3dep-seamless", "gap", "mtbs", "nwi"]
        }
        
    async def __aenter__(self):
        self.session = aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=30))
        return self
        
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        if self.session:
            await self.session.close()
    
    async def get_all_collections(self) -> List[str]:
        """Get all available collection IDs."""
        try:
            if not self.session:
                return []
            async with self.session.get(f"{self.base_url}/collections") as response:
                if response.status == 200:
                    data = await response.json()
                    collections = [c["id"] for c in data.get("collections", [])]
                    logger.info(f"Found {len(collections)} total collections")
                    return collections
                else:
                    logger.error(f"Failed to get collections: {response.status}")
                    return []
        except Exception as e:
            logger.error(f"Error getting collections: {e}")
            return []
    
    async def test_collection_strategy(self, collection_id: str, strategy_name: str, strategy_params: dict) -> dict:
        """Test a specific collection with a specific strategy."""
        url = f"{self.base_url}/search"
        
        payload = {
            "collections": [collection_id],
            **strategy_params
        }
        
        try:
            if not self.session:
                return {
                    "success": False,
                    "feature_count": 0,
                    "has_data": False,
                    "strategy": strategy_name,
                    "error": "No session available",
                    "feature_details": None
                }
            
            async with self.session.post(url, json=payload) as response:
                if response.status == 200:
                    data = await response.json()
                    features = data.get("features", [])
                    
                    # Get detailed info about first feature if available
                    feature_details = None
                    if features:
                        first_feature = features[0]
                        feature_details = {
                            "datetime": first_feature.get("properties", {}).get("datetime"),
                            "assets": list(first_feature.get("assets", {}).keys()),
                            "bbox": first_feature.get("bbox"),
                            "geometry_type": first_feature.get("geometry", {}).get("type") if first_feature.get("geometry") else None
                        }
                    
                    return {
                        "success": True,
                        "feature_count": len(features),
                        "has_data": len(features) > 0,
                        "strategy": strategy_name,
                        "feature_details": feature_details,
                        "response_size": len(str(data))
                    }
                else:
                    return {
                        "success": False,
                        "feature_count": 0,
                        "has_data": False,
                        "strategy": strategy_name,
                        "error": f"HTTP {response.status}",
                        "feature_details": None
                    }
        except Exception as e:
            return {
                "success": False,
                "feature_count": 0,
                "has_data": False,
                "strategy": strategy_name,
                "error": str(e),
                "feature_details": None
            }
    
    async def analyze_collection_deep(self, collection_id: str) -> dict:
        """Deeply analyze a single collection with all strategies."""
        logger.info(f"Deep analyzing collection: {collection_id}")
        
        results = {}
        working_strategies = []
        total_features_found = 0
        best_strategy = None
        best_feature_count = 0
        
        # Test all strategies
        for strategy_name, strategy_params in self.test_strategies.items():
            result = await self.test_collection_strategy(collection_id, strategy_name, strategy_params)
            results[strategy_name] = result
            
            if result["has_data"]:
                working_strategies.append(strategy_name)
                total_features_found += result["feature_count"]
                
                if result["feature_count"] > best_feature_count:
                    best_feature_count = result["feature_count"]
                    best_strategy = strategy_name
        
        # Determine category
        category = "Other"
        for cat, collections in self.collection_categories.items():
            if collection_id in collections:
                category = cat
                break
        
        # Create comprehensive analysis
        analysis = {
            "collection_id": collection_id,
            "category": category,
            "working": len(working_strategies) > 0,
            "working_strategies": working_strategies,
            "total_working_strategies": len(working_strategies),
            "total_features_found": total_features_found,
            "best_strategy": best_strategy,
            "best_feature_count": best_feature_count,
            "strategy_results": results
        }
        
        # Add best strategy details if available
        if best_strategy and results[best_strategy]["feature_details"]:
            analysis["sample_data"] = results[best_strategy]["feature_details"]
        
        return analysis
    
    async def analyze_all_collections(self) -> dict:
        """Analyze all collections comprehensively."""
        logger.info("Starting comprehensive deep analysis of all collections...")
        
        # Get all collections
        all_collections = await self.get_all_collections()
        if not all_collections:
            logger.error("No collections found!")
            return {}
        
        logger.info(f"Analyzing {len(all_collections)} collections...")
        
        # Analyze each collection
        detailed_results = {}
        working_collections = []
        
        for i, collection_id in enumerate(all_collections, 1):
            logger.info(f"[{i}/{len(all_collections)}] Analyzing {collection_id}")
            
            analysis = await self.analyze_collection_deep(collection_id)
            detailed_results[collection_id] = analysis
            
            if analysis["working"]:
                working_collections.append(collection_id)
            
            # Add small delay to be nice to the API
            await asyncio.sleep(0.2)
        
        # Create summary
        summary = {
            "analysis_timestamp": datetime.now().isoformat(),
            "total_collections": len(all_collections),
            "working_collections": len(working_collections),
            "success_rate": round((len(working_collections) / len(all_collections)) * 100, 1),
            "detailed_results": detailed_results
        }
        
        # Categorize results
        categories = {}
        for collection_id, analysis in detailed_results.items():
            category = analysis["category"]
            if category not in categories:
                categories[category] = {"total": 0, "working": 0, "collections": []}
            
            categories[category]["total"] += 1
            if analysis["working"]:
                categories[category]["working"] += 1
            categories[category]["collections"].append({
                "id": collection_id,
                "working": analysis["working"],
                "working_strategies": analysis["total_working_strategies"],
                "best_feature_count": analysis["best_feature_count"],
                "best_strategy": analysis["best_strategy"]
            })
        
        summary["categories"] = categories
        
        return summary

async def main():
    """Main execution function."""
    logger.info("Starting Deep STAC Collection Analysis...")
    
    async with DeepSTACAnalyzer() as analyzer:
        results = await analyzer.analyze_all_collections()
        
        if results:
            # Save detailed results
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            detailed_file = f"deep_stac_analysis_detailed_{timestamp}.json"
            summary_file = f"deep_stac_analysis_summary_{timestamp}.json"
            
            with open(detailed_file, 'w') as f:
                json.dump(results, f, indent=2)
            
            # Create a more readable summary
            summary = {
                "analysis_timestamp": results["analysis_timestamp"],
                "total_collections": results["total_collections"],
                "working_collections": results["working_collections"],
                "success_rate": results["success_rate"],
                "categories": results["categories"]
            }
            
            with open(summary_file, 'w') as f:
                json.dump(summary, f, indent=2)
            
            logger.info(f"Analysis complete!")
            logger.info(f"Found {results['working_collections']}/{results['total_collections']} working collections ({results['success_rate']}%)")
            logger.info(f"Detailed results saved to: {detailed_file}")
            logger.info(f"Summary saved to: {summary_file}")
            
            # Print quick overview of categories
            print("\n=== CATEGORY OVERVIEW ===")
            for category, stats in results["categories"].items():
                print(f"{category}: {stats['working']}/{stats['total']} working")
                for collection in stats["collections"]:
                    status = "✅" if collection["working"] else "❌"
                    strategies = collection["working_strategies"] if collection["working"] else 0
                    features = collection["best_feature_count"] if collection["working"] else 0
                    print(f"  {status} {collection['id']} - {strategies} strategies, {features} features")
        
        else:
            logger.error("Analysis failed!")

if __name__ == "__main__":
    asyncio.run(main())