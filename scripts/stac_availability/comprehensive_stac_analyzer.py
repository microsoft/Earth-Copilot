# Copyright (c) Microsoft Corporation.
# Licensed under the MIT license.

#!/usr/bin/env python3
"""
Comprehensive STAC Collection Analyzer
Tests all collections with different strategies to understand their data availability patterns.
Documents findings for reference when creating queries.
"""

import asyncio
import aiohttp
import json
from datetime import datetime, timedelta
from typing import Dict, List, Any, Optional
import logging
import os

# Set up logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

class STACAnalyzer:
    """Comprehensive analyzer for STAC collections to understand their data patterns"""
    
    def __init__(self):
        self.base_url = "https://planetarycomputer.microsoft.com/api/stac/v1"
        self.results = {}
        
        # All collections from collection_profiles.py
        self.all_collections = {
            # Optical Satellite
            "sentinel-2-l2a": {"category": "Optical Satellite", "priority": "high"},
            "landsat-c2-l2": {"category": "Optical Satellite", "priority": "high"},
            "landsat-c2-l1": {"category": "Optical Satellite", "priority": "medium"},
            "hls-l30": {"category": "Optical Satellite", "priority": "medium"},
            "hls-s30": {"category": "Optical Satellite", "priority": "medium"},
            
            # SAR/Radar
            "sentinel-1-grd": {"category": "SAR/Radar", "priority": "high"},
            "sentinel-1-rtc": {"category": "SAR/Radar", "priority": "medium"},
            "alos-palsar-rtc": {"category": "SAR/Radar", "priority": "medium"},
            
            # Elevation/DEM
            "cop-dem-glo-30": {"category": "Elevation/DEM", "priority": "high"},
            "cop-dem-glo-90": {"category": "Elevation/DEM", "priority": "medium"},
            "nasadem": {"category": "Elevation/DEM", "priority": "medium"},
            "3dep-lidar-dsm": {"category": "Elevation/DEM", "priority": "low"},
            
            # Climate/Weather
            "era5-pds": {"category": "Climate/Weather", "priority": "high"},
            "daymet-daily-na": {"category": "Climate/Weather", "priority": "high"},
            "terraclimate": {"category": "Climate/Weather", "priority": "medium"},
            "prism": {"category": "Climate/Weather", "priority": "medium"},
            
            # Fire Detection
            "modis-mcd64a1-061": {"category": "Fire Detection", "priority": "high"},
            "modis-mcd14ml": {"category": "Fire Detection", "priority": "high"},
            "viirs-thermal-anomalies-nrt": {"category": "Fire Detection", "priority": "high"},
            
            # Agriculture/Vegetation
            "modis-13q1-061": {"category": "Agriculture/Vegetation", "priority": "high"},
            "modis-11a1-061": {"category": "Agriculture/Vegetation", "priority": "medium"},
            "chloris-biomass": {"category": "Agriculture/Vegetation", "priority": "medium"},
            
            # Ocean/Marine
            "modis-sst": {"category": "Ocean/Marine", "priority": "high"},
            "goes-cmi": {"category": "Ocean/Marine", "priority": "medium"},
            
            # High-res Aerial
            "naip": {"category": "High-res Aerial", "priority": "high"},
            
            # Urban/Infrastructure
            "bing-vfp": {"category": "Urban/Infrastructure", "priority": "medium"},
            
            # Night Lights
            "viirs-dnb-monthly": {"category": "Night Lights", "priority": "medium"}
        }
        
        # Test strategies for different collection types
        self.test_strategies = {
            # Strategy 1: No datetime filter (for static collections)
            "no_datetime": {
                "description": "No datetime filter - for static collections",
                "params": {}
            },
            
            # Strategy 2: Recent data (last 30 days)
            "recent": {
                "description": "Recent data (last 30 days)",
                "params": {
                    "datetime": f"{(datetime.now() - timedelta(days=30)).strftime('%Y-%m-%d')}/{datetime.now().strftime('%Y-%m-%d')}"
                }
            },
            
            # Strategy 3: Last year
            "last_year": {
                "description": "Last year data",
                "params": {
                    "datetime": "2024-01-01/2024-12-31"
                }
            },
            
            # Strategy 4: Historical data (2020-2023)
            "historical": {
                "description": "Historical data (2020-2023)",
                "params": {
                    "datetime": "2020-01-01/2023-12-31"
                }
            },
            
            # Strategy 5: Single point in time (recent)
            "single_recent": {
                "description": "Single recent date",
                "params": {
                    "datetime": "2024-06-01"
                }
            },
            
            # Strategy 6: Single point in time (historical)
            "single_historical": {
                "description": "Single historical date",
                "params": {
                    "datetime": "2023-06-01"
                }
            }
        }
        
        # Test locations for different geographic patterns
        self.test_locations = {
            "seattle": {
                "description": "Seattle, WA (urban, temperate)",
                "bbox": [-122.5, 47.5, -122.3, 47.7]
            },
            "california_central": {
                "description": "Central California (fire-prone, agriculture)",
                "bbox": [-120.0, 36.0, -119.0, 37.0]
            },
            "midwest_agriculture": {
                "description": "Midwest agriculture region",
                "bbox": [-100.0, 40.0, -99.0, 41.0]
            },
            "florida_coast": {
                "description": "Florida coast (hurricane-prone, ocean)",
                "bbox": [-81.0, 25.0, -80.0, 26.0]
            },
            "global_sample": {
                "description": "Global sample area",
                "bbox": [-10.0, 50.0, 0.0, 60.0]  # UK area
            }
        }
    
    async def get_collection_info(self, session: aiohttp.ClientSession, collection_id: str) -> Dict[str, Any]:
        """Get detailed collection information"""
        try:
            url = f"{self.base_url}/collections/{collection_id}"
            async with session.get(url) as response:
                if response.status == 200:
                    return await response.json()
                else:
                    logger.warning(f"Failed to get collection info for {collection_id}: {response.status}")
                    return {}
        except Exception as e:
            logger.error(f"Error getting collection info for {collection_id}: {e}")
            return {}
    
    async def test_collection_strategy(self, session: aiohttp.ClientSession, 
                                     collection_id: str, strategy_name: str, 
                                     location_name: str, limit: int = 5) -> Dict[str, Any]:
        """Test a specific strategy for a collection"""
        try:
            strategy = self.test_strategies[strategy_name]
            location = self.test_locations[location_name]
            
            search_params = {
                "collections": [collection_id],
                "bbox": location["bbox"],
                "limit": limit
            }
            
            # Add datetime if strategy includes it
            if "datetime" in strategy["params"]:
                search_params["datetime"] = strategy["params"]["datetime"]
            
            url = f"{self.base_url}/search"
            async with session.post(url, json=search_params) as response:
                if response.status == 200:
                    data = await response.json()
                    feature_count = len(data.get("features", []))
                    
                    return {
                        "success": True,
                        "feature_count": feature_count,
                        "strategy": strategy_name,
                        "location": location_name,
                        "search_params": search_params,
                        "has_features": feature_count > 0
                    }
                else:
                    return {
                        "success": False,
                        "error": f"HTTP {response.status}",
                        "strategy": strategy_name,
                        "location": location_name
                    }
        except Exception as e:
            return {
                "success": False,
                "error": str(e),
                "strategy": strategy_name,
                "location": location_name
            }
    
    async def analyze_collection(self, session: aiohttp.ClientSession, collection_id: str) -> Dict[str, Any]:
        """Comprehensive analysis of a single collection"""
        logger.info(f"🔬 Analyzing collection: {collection_id}")
        
        collection_info = self.all_collections.get(collection_id, {})
        stac_info = await self.get_collection_info(session, collection_id)
        
        analysis = {
            "collection_id": collection_id,
            "category": collection_info.get("category", "Unknown"),
            "priority": collection_info.get("priority", "unknown"),
            "stac_info": {
                "title": stac_info.get("title", ""),
                "description": stac_info.get("description", "")[:200] + "..." if len(stac_info.get("description", "")) > 200 else stac_info.get("description", ""),
                "temporal_extent": stac_info.get("extent", {}).get("temporal", {}).get("interval", []),
                "spatial_extent": stac_info.get("extent", {}).get("spatial", {}).get("bbox", [])
            },
            "test_results": {},
            "successful_strategies": [],
            "working_combinations": [],
            "recommended_usage": {}
        }
        
        # Test all strategy-location combinations
        for strategy_name in self.test_strategies:
            analysis["test_results"][strategy_name] = {}
            
            for location_name in self.test_locations:
                result = await self.test_collection_strategy(
                    session, collection_id, strategy_name, location_name
                )
                analysis["test_results"][strategy_name][location_name] = result
                
                if result.get("has_features", False):
                    analysis["successful_strategies"].append(f"{strategy_name}+{location_name}")
                    analysis["working_combinations"].append({
                        "strategy": strategy_name,
                        "location": location_name,
                        "feature_count": result.get("feature_count", 0),
                        "search_params": result.get("search_params", {})
                    })
        
        # Generate recommendations based on successful patterns
        analysis["recommended_usage"] = self.generate_recommendations(analysis)
        
        return analysis
    
    def generate_recommendations(self, analysis: Dict[str, Any]) -> Dict[str, Any]:
        """Generate usage recommendations based on test results"""
        working_combos = analysis["working_combinations"]
        
        if not working_combos:
            return {
                "status": "no_data_found",
                "recommendation": "Collection may be inactive, have geographic restrictions, or require specific parameters"
            }
        
        # Analyze patterns
        successful_strategies = [combo["strategy"] for combo in working_combos]
        successful_locations = [combo["location"] for combo in working_combos]
        
        # Count occurrences
        strategy_counts = {}
        location_counts = {}
        
        for strategy in successful_strategies:
            strategy_counts[strategy] = strategy_counts.get(strategy, 0) + 1
        
        for location in successful_locations:
            location_counts[location] = location_counts.get(location, 0) + 1
        
        # Determine best patterns
        best_strategy = max(strategy_counts.items(), key=lambda x: x[1]) if strategy_counts else None
        best_location = max(location_counts.items(), key=lambda x: x[1]) if location_counts else None
        
        recommendations = {
            "status": "data_available",
            "best_strategy": best_strategy[0] if best_strategy else None,
            "best_location": best_location[0] if best_location else None,
            "datetime_required": not any(combo["strategy"] == "no_datetime" for combo in working_combos),
            "geographic_restrictions": len(set(successful_locations)) < len(self.test_locations),
            "temporal_patterns": {
                "works_recent": any("recent" in combo["strategy"] for combo in working_combos),
                "works_historical": any("historical" in combo["strategy"] for combo in working_combos),
                "works_without_datetime": any(combo["strategy"] == "no_datetime" for combo in working_combos)
            },
            "sample_working_query": working_combos[0]["search_params"] if working_combos else None
        }
        
        return recommendations
    
    async def run_comprehensive_analysis(self) -> Dict[str, Any]:
        """Run comprehensive analysis on all collections"""
        print("🔬 Comprehensive STAC Collection Analysis")
        print("=" * 80)
        print(f"Analyzing {len(self.all_collections)} collections across {len(self.test_strategies)} strategies and {len(self.test_locations)} locations")
        print()
        
        async with aiohttp.ClientSession() as session:
            results = {}
            
            for i, collection_id in enumerate(self.all_collections.keys(), 1):
                print(f"[{i}/{len(self.all_collections)}] {collection_id}")
                results[collection_id] = await self.analyze_collection(session, collection_id)
                
                # Brief status update
                working_count = len(results[collection_id]["working_combinations"])
                print(f"   ✅ {working_count} working combinations found")
                print()
        
        # Generate overall summary
        summary = self.generate_overall_summary(results)
        
        # Save detailed results
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        detailed_file = f"stac_analysis_detailed_{timestamp}.json"
        summary_file = f"stac_analysis_summary_{timestamp}.json"
        
        with open(detailed_file, 'w') as f:
            json.dump(results, f, indent=2)
        
        with open(summary_file, 'w') as f:
            json.dump(summary, f, indent=2)
        
        print("=" * 80)
        print("📊 ANALYSIS COMPLETE")
        print("=" * 80)
        print(f"📁 Detailed results: {detailed_file}")
        print(f"📋 Summary: {summary_file}")
        print()
        
        self.print_summary(summary)
        
        return {
            "detailed_results": results,
            "summary": summary,
            "files_created": [detailed_file, summary_file]
        }
    
    def generate_overall_summary(self, results: Dict[str, Any]) -> Dict[str, Any]:
        """Generate overall summary of analysis"""
        total_collections = len(results)
        working_collections = sum(1 for r in results.values() if r["working_combinations"])
        
        category_stats = {}
        strategy_effectiveness = {}
        location_effectiveness = {}
        
        for collection_id, analysis in results.items():
            category = analysis["category"]
            if category not in category_stats:
                category_stats[category] = {"total": 0, "working": 0, "collections": []}
            
            category_stats[category]["total"] += 1
            category_stats[category]["collections"].append({
                "id": collection_id,
                "working": len(analysis["working_combinations"]) > 0,
                "combo_count": len(analysis["working_combinations"])
            })
            
            if analysis["working_combinations"]:
                category_stats[category]["working"] += 1
            
            # Track strategy effectiveness
            for combo in analysis["working_combinations"]:
                strategy = combo["strategy"]
                location = combo["location"]
                
                strategy_effectiveness[strategy] = strategy_effectiveness.get(strategy, 0) + 1
                location_effectiveness[location] = location_effectiveness.get(location, 0) + 1
        
        return {
            "total_collections": total_collections,
            "working_collections": working_collections,
            "success_rate": round((working_collections / total_collections) * 100, 1),
            "category_breakdown": category_stats,
            "most_effective_strategies": sorted(strategy_effectiveness.items(), key=lambda x: x[1], reverse=True),
            "most_effective_locations": sorted(location_effectiveness.items(), key=lambda x: x[1], reverse=True),
            "recommendations": {
                "reliable_collections": [
                    collection_id for collection_id, analysis in results.items()
                    if len(analysis["working_combinations"]) >= 5
                ],
                "problematic_collections": [
                    collection_id for collection_id, analysis in results.items()
                    if not analysis["working_combinations"]
                ],
                "geographic_restricted": [
                    collection_id for collection_id, analysis in results.items()
                    if analysis["recommended_usage"].get("geographic_restrictions", False)
                ],
                "datetime_sensitive": [
                    collection_id for collection_id, analysis in results.items()
                    if analysis["recommended_usage"].get("datetime_required", False)
                ]
            }
        }
    
    def print_summary(self, summary: Dict[str, Any]):
        """Print formatted summary"""
        print(f"📊 Collections Analyzed: {summary['total_collections']}")
        print(f"✅ Working Collections: {summary['working_collections']}")
        print(f"📈 Success Rate: {summary['success_rate']}%")
        print()
        
        print("🎯 Most Effective Strategies:")
        for strategy, count in summary["most_effective_strategies"][:5]:
            print(f"   {strategy}: {count} collections")
        print()
        
        print("🌍 Most Effective Locations:")
        for location, count in summary["most_effective_locations"][:5]:
            print(f"   {location}: {count} collections")
        print()
        
        print("✅ Reliable Collections (5+ working combinations):")
        for collection in summary["recommendations"]["reliable_collections"]:
            print(f"   - {collection}")
        print()
        
        print("❌ Problematic Collections (no working combinations):")
        for collection in summary["recommendations"]["problematic_collections"]:
            print(f"   - {collection}")
        print()
        
        print("🔧 USAGE RECOMMENDATIONS:")
        print("For reliable queries, use these proven combinations:")
        print("- Strategy: 'recent' or 'last_year' for most collections")
        print("- Location: 'seattle' or 'california_central' for best coverage")
        print("- Always include datetime unless collection is static (DEM/elevation)")

async def main():
    analyzer = STACAnalyzer()
    await analyzer.run_comprehensive_analysis()

if __name__ == "__main__":
    asyncio.run(main())
