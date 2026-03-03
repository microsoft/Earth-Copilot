# Copyright (c) Microsoft Corporation.
# Licensed under the MIT license.

#!/usr/bin/env python3
"""
Comprehensive VEDA Collection Analyzer
Tests all VEDA collections to understand their data availability patterns.
Similar to STAC analyzer but for NASA VEDA collections.
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

class VEDAAnalyzer:
    """Comprehensive analyzer for VEDA collections to understand their data patterns"""
    
    def __init__(self):
        self.base_url = "https://openveda.cloud/api/stac"
        self.search_url = "https://openveda.cloud/api/stac/search"
        self.results = {}
        self.collections_metadata = {}
        
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
            
            # Strategy 4: Last 2 years
            "last_2_years": {
                "description": "Last 2 years data",
                "params": {
                    "datetime": "2023-01-01/2024-12-31"
                }
            },
            
            # Strategy 5: Specific recent date
            "specific_recent": {
                "description": "Specific recent date",
                "params": {
                    "datetime": "2024-06-01/2024-06-30"
                }
            },
            
            # Strategy 6: All time (very broad)
            "all_time": {
                "description": "All time (2000-2025)",
                "params": {
                    "datetime": "2000-01-01/2025-12-31"
                }
            }
        }

    async def fetch_all_collections(self) -> List[Dict[str, Any]]:
        """Fetch all available VEDA collections"""
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(f"{self.base_url}/collections") as response:
                    if response.status == 200:
                        data = await response.json()
                        collections = data.get("collections", [])
                        logger.info(f"[OK] Found {len(collections)} VEDA collections")
                        return collections
                    else:
                        logger.error(f"[FAIL] Failed to fetch collections: HTTP {response.status}")
                        return []
        except Exception as e:
            logger.error(f"[FAIL] Error fetching collections: {e}")
            return []

    async def analyze_collection(self, collection_id: str, session: aiohttp.ClientSession) -> Dict[str, Any]:
        """Analyze a single collection with all test strategies"""
        logger.info(f"[SEARCH] Analyzing collection: {collection_id}")
        
        collection_result = {
            "collection_id": collection_id,
            "metadata": self.collections_metadata.get(collection_id, {}),
            "strategies": {},
            "working_strategies": [],
            "failed_strategies": [],
            "best_strategy": None,
            "data_availability": "unknown",
            "asset_types": [],
            "temporal_extent": None,
            "spatial_extent": None
        }
        
        # Test each strategy
        for strategy_name, strategy_config in self.test_strategies.items():
            try:
                # Build query
                query = {
                    "collections": [collection_id],
                    "limit": 5
                }
                query.update(strategy_config["params"])
                
                logger.info(f"  [CHART] Testing strategy '{strategy_name}' for {collection_id}")
                
                async with session.post(self.search_url, json=query) as response:
                    if response.status == 200:
                        data = await response.json()
                        features = data.get("features", [])
                        
                        strategy_result = {
                            "status": "success",
                            "feature_count": len(features),
                            "strategy_description": strategy_config["description"],
                            "query_used": query,
                            "sample_feature": features[0] if features else None
                        }
                        
                        if features:
                            # Extract asset types from first feature
                            assets = features[0].get("assets", {})
                            asset_types = list(assets.keys())
                            strategy_result["asset_types"] = asset_types
                            
                            # Extract temporal info
                            props = features[0].get("properties", {})
                            if "datetime" in props:
                                strategy_result["sample_datetime"] = props["datetime"]
                            
                            # Extract geometry info
                            geometry = features[0].get("geometry", {})
                            if geometry:
                                strategy_result["geometry_type"] = geometry.get("type")
                        
                        collection_result["strategies"][strategy_name] = strategy_result
                        collection_result["working_strategies"].append(strategy_name)
                        
                        # Update collection-level info from successful strategy
                        if features and not collection_result["best_strategy"]:
                            collection_result["best_strategy"] = strategy_name
                            collection_result["data_availability"] = "available"
                            collection_result["asset_types"] = strategy_result.get("asset_types", [])
                        
                        logger.info(f"    [OK] Strategy '{strategy_name}': {len(features)} features found")
                        
                    else:
                        error_text = await response.text()
                        strategy_result = {
                            "status": "failed",
                            "error": f"HTTP {response.status}: {error_text}",
                            "strategy_description": strategy_config["description"],
                            "query_used": query
                        }
                        collection_result["strategies"][strategy_name] = strategy_result
                        collection_result["failed_strategies"].append(strategy_name)
                        logger.warning(f"    [FAIL] Strategy '{strategy_name}': HTTP {response.status}")
                        
            except Exception as e:
                strategy_result = {
                    "status": "error",
                    "error": str(e),
                    "strategy_description": strategy_config["description"]
                }
                collection_result["strategies"][strategy_name] = strategy_result
                collection_result["failed_strategies"].append(strategy_name)
                logger.error(f"    [BOOM] Strategy '{strategy_name}': {e}")
        
        # Determine overall status
        if collection_result["working_strategies"]:
            success_rate = len(collection_result["working_strategies"]) / len(self.test_strategies)
            if success_rate >= 0.8:
                collection_result["status"] = "excellent"
            elif success_rate >= 0.5:
                collection_result["status"] = "good"
            else:
                collection_result["status"] = "limited"
        else:
            collection_result["status"] = "unavailable"
        
        logger.info(f"[UP] Collection {collection_id}: {collection_result['status']} ({len(collection_result['working_strategies'])}/{len(self.test_strategies)} strategies working)")
        return collection_result

    async def analyze_all_collections(self):
        """Analyze all VEDA collections"""
        logger.info("[LAUNCH] Starting comprehensive VEDA collection analysis...")
        
        # Fetch all collections first
        collections = await self.fetch_all_collections()
        if not collections:
            logger.error("[FAIL] No collections found, aborting analysis")
            return
        
        # Store metadata for each collection
        for collection in collections:
            collection_id = collection.get("id")
            if collection_id:
                self.collections_metadata[collection_id] = {
                    "title": collection.get("title", ""),
                    "description": collection.get("description", ""),
                    "license": collection.get("license", ""),
                    "providers": collection.get("providers", []),
                    "temporal_extent": collection.get("extent", {}).get("temporal", {}),
                    "spatial_extent": collection.get("extent", {}).get("spatial", {}),
                    "stac_extensions": collection.get("stac_extensions", [])
                }
        
        logger.info(f"[DOCS] Collected metadata for {len(self.collections_metadata)} collections")
        
        # Analyze each collection
        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=30)) as session:
            for collection in collections:
                collection_id = collection.get("id")
                if collection_id:
                    try:
                        result = await self.analyze_collection(collection_id, session)
                        self.results[collection_id] = result
                        
                        # Add a small delay to be nice to the API
                        await asyncio.sleep(0.5)
                        
                    except Exception as e:
                        logger.error(f"[BOOM] Failed to analyze {collection_id}: {e}")
                        self.results[collection_id] = {
                            "collection_id": collection_id,
                            "status": "error",
                            "error": str(e)
                        }

    def generate_summary_report(self) -> str:
        """Generate a comprehensive summary report"""
        if not self.results:
            return "No analysis results available."
        
        total_collections = len(self.results)
        status_counts = {"excellent": 0, "good": 0, "limited": 0, "unavailable": 0, "error": 0}
        
        working_collections = []
        problematic_collections = []
        
        for collection_id, result in self.results.items():
            status = result.get("status", "error")
            status_counts[status] += 1
            
            if status in ["excellent", "good"]:
                working_collections.append({
                    "id": collection_id,
                    "status": status,
                    "working_strategies": len(result.get("working_strategies", [])),
                    "total_strategies": len(self.test_strategies),
                    "best_strategy": result.get("best_strategy"),
                    "asset_types": result.get("asset_types", []),
                    "title": result.get("metadata", {}).get("title", "")
                })
            else:
                problematic_collections.append({
                    "id": collection_id,
                    "status": status,
                    "error": result.get("error", ""),
                    "title": result.get("metadata", {}).get("title", "")
                })
        
        # Generate report
        report = f"""
# VEDA Collection Analysis Report
Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}

## Summary Statistics
- **Total Collections Tested**: {total_collections}
- **Excellent Collections**: {status_counts['excellent']} ({status_counts['excellent']/total_collections*100:.1f}%)
- **Good Collections**: {status_counts['good']} ({status_counts['good']/total_collections*100:.1f}%)
- **Limited Collections**: {status_counts['limited']} ({status_counts['limited']/total_collections*100:.1f}%)
- **Unavailable Collections**: {status_counts['unavailable']} ({status_counts['unavailable']/total_collections*100:.1f}%)
- **Error Collections**: {status_counts['error']} ({status_counts['error']/total_collections*100:.1f}%)

## Working Collections ({len(working_collections)} total)

"""
        
        # Sort working collections by status and strategy count
        working_collections.sort(key=lambda x: (x["status"] == "excellent", x["working_strategies"]), reverse=True)
        
        for col in working_collections:
            report += f"### {col['id']}\n"
            report += f"- **Title**: {col['title']}\n"
            report += f"- **Status**: {col['status']}\n"
            report += f"- **Working Strategies**: {col['working_strategies']}/{col['total_strategies']}\n"
            report += f"- **Best Strategy**: {col['best_strategy']}\n"
            report += f"- **Asset Types**: {', '.join(col['asset_types'])}\n\n"
        
        if problematic_collections:
            report += f"## Problematic Collections ({len(problematic_collections)} total)\n\n"
            for col in problematic_collections:
                report += f"### {col['id']}\n"
                report += f"- **Title**: {col['title']}\n"
                report += f"- **Status**: {col['status']}\n"
                if col['error']:
                    report += f"- **Error**: {col['error']}\n"
                report += "\n"
        
        return report

    def save_results(self, output_dir: str = "veda_analysis_results"):
        """Save detailed results to files"""
        os.makedirs(output_dir, exist_ok=True)
        
        # Save detailed JSON results
        with open(f"{output_dir}/veda_analysis_detailed.json", "w") as f:
            json.dump(self.results, f, indent=2, default=str)
        
        # Save summary report
        report = self.generate_summary_report()
        with open(f"{output_dir}/veda_analysis_summary.md", "w") as f:
            f.write(report)
        
        # Save collection profiles (for integration) - include limited collections since they work with no_datetime
        working_profiles = {}
        for collection_id, result in self.results.items():
            if result.get("status") in ["excellent", "good", "limited"] and result.get("working_strategies"):
                metadata = result.get("metadata", {})
                working_profiles[collection_id] = {
                    "name": metadata.get("title", collection_id),
                    "description": metadata.get("description", ""),
                    "status": result.get("status"),
                    "best_strategy": result.get("best_strategy"),
                    "asset_types": result.get("asset_types", []),
                    "working_strategies": result.get("working_strategies", []),
                    "temporal_extent": metadata.get("temporal_extent"),
                    "spatial_extent": metadata.get("spatial_extent"),
                    "category": self._categorize_collection(collection_id, metadata),
                    "priority": self._determine_priority(result)
                }
        
        with open(f"{output_dir}/veda_collection_profiles.json", "w") as f:
            json.dump(working_profiles, f, indent=2, default=str)
        
        logger.info(f"[DIR] Results saved to {output_dir}/")
        logger.info(f"[CHART] Found {len(working_profiles)} working VEDA collections")

    def _categorize_collection(self, collection_id: str, metadata: Dict) -> str:
        """Categorize collection based on ID and metadata"""
        collection_lower = collection_id.lower()
        title_lower = metadata.get("title", "").lower()
        desc_lower = metadata.get("description", "").lower()
        
        # Category mapping based on keywords
        if any(keyword in collection_lower or keyword in title_lower for keyword in 
               ["fire", "burn", "thermal", "barc", "modis-14", "viirs"]):
            return "Fire Detection"
        elif any(keyword in collection_lower or keyword in title_lower for keyword in 
                 ["era5", "climate", "temperature", "pressure", "weather"]):
            return "Climate/Weather"
        elif any(keyword in collection_lower or keyword in title_lower for keyword in 
                 ["landcover", "land-cover", "vegetation", "biomass", "forest"]):
            return "Land Cover/Vegetation"
        elif any(keyword in collection_lower or keyword in title_lower for keyword in 
                 ["elevation", "dem", "topography", "terrain"]):
            return "Elevation/DEM"
        elif any(keyword in collection_lower or keyword in title_lower for keyword in 
                 ["ocean", "sea", "marine", "sst", "chlorophyll"]):
            return "Ocean/Marine"
        elif any(keyword in collection_lower or keyword in title_lower for keyword in 
                 ["urban", "population", "city", "infrastructure"]):
            return "Urban/Infrastructure"
        elif any(keyword in collection_lower or keyword in title_lower for keyword in 
                 ["agriculture", "crop", "farming", "agricultural"]):
            return "Agriculture"
        elif any(keyword in collection_lower or keyword in title_lower for keyword in 
                 ["disaster", "hurricane", "flood", "earthquake"]):
            return "Disaster Response"
        else:
            return "Research/Specialized"

    def _determine_priority(self, result: Dict) -> str:
        """Determine priority based on analysis results"""
        status = result.get("status", "error")
        working_strategies = len(result.get("working_strategies", []))
        
        if status == "excellent" and working_strategies >= 5:
            return "high"
        elif status in ["excellent", "good"] and working_strategies >= 3:
            return "medium"
        else:
            return "low"

async def main():
    """Main analysis function"""
    analyzer = VEDAAnalyzer()
    
    try:
        await analyzer.analyze_all_collections()
        analyzer.save_results()
        
        # Print summary
        print("\n" + "="*80)
        print("VEDA COLLECTION ANALYSIS COMPLETE")
        print("="*80)
        print(analyzer.generate_summary_report())
        
    except Exception as e:
        logger.error(f"[BOOM] Analysis failed: {e}")
        raise

if __name__ == "__main__":
    asyncio.run(main())