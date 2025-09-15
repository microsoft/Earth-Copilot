"""
Comprehensive Visualization Test Suite
Tests diverse queries across all visualization types and collection categories
"""

import asyncio
import aiohttp
import json
from datetime import datetime
from typing import Dict, List, Any

class VisualizationTestSuite:
    """Comprehensive test suite for all visualization types"""
    
    def __init__(self, base_url: str = "http://localhost:7071"):
        self.base_url = base_url
        self.results = []
        
    async def run_all_tests(self):
        """Run comprehensive test suite across all visualization types"""
        
        print("🎨 Earth Copilot Comprehensive Visualization Test Suite")
        print("=" * 70)
        print(f"⏰ Started: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        print()
        
        # Test categories with diverse queries
        test_categories = [
            ("Optical Imagery", self.get_optical_tests()),
            ("SAR/Radar Data", self.get_sar_tests()),
            ("Elevation/Terrain", self.get_elevation_tests()),
            ("Climate/Weather", self.get_climate_tests()),
            ("Fire Monitoring", self.get_fire_tests()),
            ("Ocean/Marine", self.get_ocean_tests()),
            ("Snow/Ice", self.get_snow_tests()),
            ("Vegetation/Agriculture", self.get_vegetation_tests()),
            ("Atmospheric/Air Quality", self.get_atmospheric_tests()),
            ("Multi-Modal Analysis", self.get_multimodal_tests()),
            ("Analytical Queries", self.get_analytical_tests()),
            ("Incomplete Queries", self.get_incomplete_tests())
        ]
        
        total_tests = sum(len(tests) for _, tests in test_categories)
        test_count = 0
        
        for category_name, test_cases in test_categories:
            print(f"📋 {category_name}")
            print("-" * 50)
            
            category_results = []
            for test_case in test_cases:
                test_count += 1
                print(f"🧪 Test {test_count}/{total_tests}: {test_case['name']}")
                print(f"   Query: \"{test_case['query']}\"")
                
                result = await self.run_single_test(test_case)
                category_results.append(result)
                
                # Display results
                if result["success"]:
                    print(f"   ✅ SUCCESS: {result['summary']}")
                    
                    # Show visualization info if available
                    viz_info = result.get("visualization_info", {})
                    if viz_info:
                        print(f"   🎨 Visualization: {viz_info.get('types', 'N/A')}")
                        print(f"   📊 Categories: {viz_info.get('categories', 'N/A')}")
                    
                    # Show response type
                    response_type = result.get("response_type", "unknown")
                    print(f"   📱 Response Type: {response_type}")
                    
                else:
                    print(f"   ❌ FAILED: {result['error']}")
                
                print()
            
            # Category summary
            success_count = sum(1 for r in category_results if r["success"])
            print(f"   📊 Category Summary: {success_count}/{len(category_results)} passed")
            print()
        
        # Overall summary
        await self.generate_final_report()
    
    async def run_single_test(self, test_case: Dict[str, Any]) -> Dict[str, Any]:
        """Run a single test case"""
        
        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    f"{self.base_url}/api/earth-copilot-query",
                    json={"query": test_case["query"]},
                    timeout=aiohttp.ClientTimeout(total=45)
                ) as response:
                    
                    if response.status == 200:
                        result = await response.json()
                        
                        # Analyze response
                        analysis = self.analyze_response(result, test_case)
                        
                        test_result = {
                            "success": True,
                            "test_case": test_case,
                            "response": result,
                            "analysis": analysis,
                            "summary": analysis["summary"],
                            "visualization_info": analysis.get("visualization_info", {}),
                            "response_type": analysis.get("response_type", "unknown")
                        }
                        
                        self.results.append(test_result)
                        return test_result
                    
                    else:
                        error_text = await response.text()
                        return {
                            "success": False,
                            "test_case": test_case,
                            "error": f"HTTP {response.status}: {error_text}",
                            "summary": f"HTTP error {response.status}"
                        }
        
        except Exception as e:
            return {
                "success": False,
                "test_case": test_case,
                "error": str(e),
                "summary": f"Exception: {str(e)}"
            }
    
    def analyze_response(self, response: Dict[str, Any], test_case: Dict[str, Any]) -> Dict[str, Any]:
        """Analyze response quality and extract visualization information"""
        
        analysis = {
            "summary": "Response received",
            "has_results": False,
            "visualization_info": {},
            "response_type": "unknown"
        }
        
        # Check if response has STAC data
        stac_data = response.get("data", {}).get("stac_results", {})
        if stac_data.get("success"):
            results = stac_data.get("results", {})
            features = results.get("features", [])
            
            analysis["has_results"] = len(features) > 0
            analysis["result_count"] = len(features)
            
            if features:
                analysis["summary"] = f"Found {len(features)} results"
                
                # Extract visualization information
                collection_summary = results.get("collection_summary", {})
                categories = collection_summary.get("categories_represented", [])
                viz_types = collection_summary.get("visualization_types", [])
                
                analysis["visualization_info"] = {
                    "categories": categories,
                    "types": viz_types,
                    "collections": collection_summary.get("collections_found", [])
                }
                
                # Check if expected collections were found
                expected_collections = test_case.get("expected_collections", [])
                if expected_collections:
                    found_collections = collection_summary.get("collections_found", [])
                    expected_found = any(exp in found_collections for exp in expected_collections)
                    analysis["expected_collections_found"] = expected_found
            
            else:
                analysis["summary"] = "No results found"
        
        # Determine response type
        user_response = response.get("response", "")
        if "analysis" in response.get("data", {}):
            analysis["response_type"] = "analytical"
        elif analysis["has_results"]:
            analysis["response_type"] = "map_with_data"
        elif "clarification" in user_response.lower() or "need" in user_response.lower():
            analysis["response_type"] = "clarification_needed"
        else:
            analysis["response_type"] = "information_only"
        
        return analysis
    
    async def generate_final_report(self):
        """Generate comprehensive test report"""
        
        print("🏁 FINAL TEST REPORT")
        print("=" * 70)
        
        total_tests = len(self.results)
        successful_tests = sum(1 for r in self.results if r["success"])
        
        print(f"📊 Overall Results: {successful_tests}/{total_tests} tests passed ({(successful_tests/total_tests)*100:.1f}%)")
        print()
        
        # Analyze by visualization type
        viz_categories = {}
        response_types = {}
        
        for result in self.results:
            if result["success"]:
                # Group by visualization categories
                viz_info = result.get("visualization_info", {})
                categories = viz_info.get("categories", [])
                
                for category in categories:
                    if category not in viz_categories:
                        viz_categories[category] = []
                    viz_categories[category].append(result)
                
                # Group by response type
                response_type = result.get("response_type", "unknown")
                if response_type not in response_types:
                    response_types[response_type] = 0
                response_types[response_type] += 1
        
        # Visualization category breakdown
        print("🎨 Visualization Categories Tested:")
        for category, results in viz_categories.items():
            print(f"   {category}: {len(results)} successful tests")
        print()
        
        # Response type breakdown
        print("📱 Response Types:")
        for resp_type, count in response_types.items():
            print(f"   {resp_type}: {count} tests")
        print()
        
        # Identify any issues
        failed_tests = [r for r in self.results if not r["success"]]
        if failed_tests:
            print("❌ Failed Tests:")
            for test in failed_tests:
                print(f"   - {test['test_case']['name']}: {test['error']}")
            print()
        
        # Save detailed results
        report_filename = f"visualization_test_report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        with open(report_filename, 'w') as f:
            json.dump({
                "summary": {
                    "total_tests": total_tests,
                    "successful_tests": successful_tests,
                    "success_rate": (successful_tests/total_tests)*100,
                    "timestamp": datetime.now().isoformat()
                },
                "visualization_categories": {k: len(v) for k, v in viz_categories.items()},
                "response_types": response_types,
                "detailed_results": self.results
            }, f, indent=2)
        
        print(f"📄 Detailed report saved to: {report_filename}")
    
    # Test case definitions for each visualization type
    
    def get_optical_tests(self) -> List[Dict[str, Any]]:
        """High-resolution optical imagery tests"""
        return [
            {
                "name": "Basic Satellite Imagery",
                "query": "Show me recent high-resolution satellite imagery of Seattle",
                "expected_collections": ["sentinel-2-l2a", "landsat-c2-l2"],
                "expected_viz_type": "optical"
            },
            {
                "name": "Urban Analysis",
                "query": "Find detailed aerial imagery of downtown San Francisco for urban planning",
                "expected_collections": ["naip", "sentinel-2-l2a"],
                "expected_viz_type": "optical"
            },
            {
                "name": "Agricultural Monitoring",
                "query": "Show me Landsat imagery of Iowa farmland with low cloud cover",
                "expected_collections": ["landsat-c2-l2"],
                "expected_viz_type": "optical"
            }
        ]
    
    def get_sar_tests(self) -> List[Dict[str, Any]]:
        """SAR/Radar data tests"""
        return [
            {
                "name": "Flood Monitoring",
                "query": "I need radar data for flood monitoring in Louisiana during hurricane season",
                "expected_collections": ["sentinel-1-grd"],
                "expected_viz_type": "sar"
            },
            {
                "name": "All-Weather Monitoring",
                "query": "Show me Sentinel-1 radar data for the Pacific Northwest",
                "expected_collections": ["sentinel-1-grd"],
                "expected_viz_type": "sar"
            },
            {
                "name": "Maritime Surveillance",
                "query": "Find SAR imagery for ship detection in the Gulf of Mexico",
                "expected_collections": ["sentinel-1-grd"],
                "expected_viz_type": "sar"
            }
        ]
    
    def get_elevation_tests(self) -> List[Dict[str, Any]]:
        """Elevation and terrain tests"""
        return [
            {
                "name": "Mountain Terrain",
                "query": "Show me elevation data and topography for the Colorado Rocky Mountains",
                "expected_collections": ["cop-dem-glo-30", "nasadem"],
                "expected_viz_type": "elevation"
            },
            {
                "name": "Watershed Analysis",
                "query": "I need digital elevation models for California watershed analysis",
                "expected_collections": ["cop-dem-glo-30"],
                "expected_viz_type": "elevation"
            },
            {
                "name": "Slope Analysis",
                "query": "Find high-resolution elevation data for landslide risk assessment",
                "expected_collections": ["cop-dem-glo-30", "nasadem"],
                "expected_viz_type": "elevation"
            }
        ]
    
    def get_climate_tests(self) -> List[Dict[str, Any]]:
        """Climate and weather data tests"""
        return [
            {
                "name": "Temperature Trends",
                "query": "Show me temperature and precipitation patterns in the Midwest for 2023",
                "expected_collections": ["era5-pds", "daymet-daily-na"],
                "expected_viz_type": "climate"
            },
            {
                "name": "Drought Monitoring",
                "query": "Analyze drought conditions in Texas using weather data",
                "expected_collections": ["era5-pds", "daymet-daily-na"],
                "expected_viz_type": "climate"
            },
            {
                "name": "Precipitation Analysis",
                "query": "Find real-time precipitation data for flood forecasting",
                "expected_collections": ["gpm-imerg-hhr", "era5-pds"],
                "expected_viz_type": "climate"
            }
        ]
    
    def get_fire_tests(self) -> List[Dict[str, Any]]:
        """Fire monitoring tests"""
        return [
            {
                "name": "Wildfire Detection",
                "query": "Show me active fire detection and burned areas in California",
                "expected_collections": ["modis-mcd64a1-061", "viirs-thermal-anomalies-nrt"],
                "expected_viz_type": "fire"
            },
            {
                "name": "Fire Risk Assessment",
                "query": "Monitor fire activity in the Pacific Northwest during fire season",
                "expected_collections": ["modis-mcd14ml", "viirs-thermal-anomalies-nrt"],
                "expected_viz_type": "fire"
            },
            {
                "name": "Burn Scar Mapping",
                "query": "Find burned area data for post-fire recovery analysis",
                "expected_collections": ["modis-mcd64a1-061"],
                "expected_viz_type": "fire"
            }
        ]
    
    def get_ocean_tests(self) -> List[Dict[str, Any]]:
        """Ocean and marine data tests"""
        return [
            {
                "name": "Ocean Health",
                "query": "Show me ocean color and chlorophyll data off the California coast",
                "expected_collections": ["modis-oc"],
                "expected_viz_type": "ocean"
            },
            {
                "name": "Sea Temperature",
                "query": "Monitor sea surface temperature in the Gulf of Mexico",
                "expected_collections": ["modis-sst"],
                "expected_viz_type": "ocean"
            },
            {
                "name": "Marine Ecosystem",
                "query": "Analyze marine productivity using ocean color data",
                "expected_collections": ["modis-oc"],
                "expected_viz_type": "ocean"
            }
        ]
    
    def get_snow_tests(self) -> List[Dict[str, Any]]:
        """Snow and ice monitoring tests"""
        return [
            {
                "name": "Snow Cover Monitoring",
                "query": "Show me snow cover extent in Alaska during winter",
                "expected_collections": ["modis-10a1-061", "viirs-snow-cover"],
                "expected_viz_type": "snow"
            },
            {
                "name": "Seasonal Snow Analysis",
                "query": "Track seasonal snow patterns in the Sierra Nevada mountains",
                "expected_collections": ["modis-10a1-061"],
                "expected_viz_type": "snow"
            }
        ]
    
    def get_vegetation_tests(self) -> List[Dict[str, Any]]:
        """Vegetation and agriculture tests"""
        return [
            {
                "name": "Agricultural Monitoring",
                "query": "Show me crop classification and vegetation health in Iowa farmland",
                "expected_collections": ["usda-cdl", "modis-13q1-061"],
                "expected_viz_type": "vegetation"
            },
            {
                "name": "Forest Health",
                "query": "Monitor vegetation indices and forest health in the Amazon",
                "expected_collections": ["modis-13q1-061", "sentinel-2-l2a"],
                "expected_viz_type": "vegetation"
            },
            {
                "name": "Land Cover Analysis",
                "query": "Find global land cover classification for conservation planning",
                "expected_collections": ["esa-worldcover"],
                "expected_viz_type": "landcover"
            }
        ]
    
    def get_atmospheric_tests(self) -> List[Dict[str, Any]]:
        """Atmospheric and air quality tests"""
        return [
            {
                "name": "Air Quality Monitoring",
                "query": "Show me air pollution and nitrogen dioxide levels in Los Angeles",
                "expected_collections": ["sentinel-5p-l2", "tropomi-no2"],
                "expected_viz_type": "atmosphere"
            },
            {
                "name": "Atmospheric Composition",
                "query": "Monitor atmospheric gases and aerosols over major cities",
                "expected_collections": ["sentinel-5p-l2"],
                "expected_viz_type": "atmosphere"
            }
        ]
    
    def get_multimodal_tests(self) -> List[Dict[str, Any]]:
        """Multi-modal analysis tests"""
        return [
            {
                "name": "Comprehensive Fire Analysis",
                "query": "Show me comprehensive wildfire monitoring combining fire detection, weather data, and terrain",
                "expected_collections": ["modis-mcd64a1-061", "era5-pds", "cop-dem-glo-30"],
                "expected_viz_type": "multi_modal"
            },
            {
                "name": "Flood Impact Assessment",
                "query": "Analyze flood impacts using radar, optical, and elevation data",
                "expected_collections": ["sentinel-1-grd", "sentinel-2-l2a", "cop-dem-glo-30"],
                "expected_viz_type": "multi_modal"
            },
            {
                "name": "Agricultural Intelligence",
                "query": "Comprehensive agricultural analysis with crop data, weather, and vegetation indices",
                "expected_collections": ["usda-cdl", "daymet-daily-na", "modis-13q1-061"],
                "expected_viz_type": "multi_modal"
            }
        ]
    
    def get_analytical_tests(self) -> List[Dict[str, Any]]:
        """Analytical query tests"""
        return [
            {
                "name": "Image Count Analysis",
                "query": "How many Sentinel-2 images are available for Seattle in 2023?",
                "expected_response_type": "analytical"
            },
            {
                "name": "Cloud Cover Statistics",
                "query": "What is the average cloud cover for satellite imagery in California during summer?",
                "expected_response_type": "analytical"
            },
            {
                "name": "Temporal Analysis",
                "query": "Analyze trends in vegetation health over the last 5 years",
                "expected_response_type": "analytical"
            }
        ]
    
    def get_incomplete_tests(self) -> List[Dict[str, Any]]:
        """Incomplete query tests (should trigger clarification)"""
        return [
            {
                "name": "Missing Location",
                "query": "Show me satellite imagery",
                "expected_response_type": "clarification"
            },
            {
                "name": "Missing Time Period",
                "query": "Find elevation data for Colorado",
                "expected_response_type": "clarification"
            },
            {
                "name": "Vague Data Type",
                "query": "I need some data for my research",
                "expected_response_type": "clarification"
            }
        ]

# Main execution
async def main():
    """Run the comprehensive visualization test suite"""
    
    test_suite = VisualizationTestSuite()
    await test_suite.run_all_tests()

if __name__ == "__main__":
    asyncio.run(main())
