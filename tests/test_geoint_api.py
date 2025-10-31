"""
GEOINT Raster Analysis - Direct API Test Suite

This script tests GEOINT raster analysis functions by calling the container API directly,
bypassing the UI. Tests various use cases with different query types and locations.

Usage:
    python test_geoint_api.py
    python test_geoint_api.py --endpoint http://localhost:8000
    python test_geoint_api.py --test terrain_analysis
    python test_geoint_api.py --verbose
"""

import asyncio
import aiohttp
import json
import time
from typing import Dict, Any, List
import argparse
from datetime import datetime


class GeointAPITester:
    """Test suite for GEOINT raster analysis API endpoints."""
    
    def __init__(self, base_url: str = "http://localhost:8000", verbose: bool = False):
        """
        Initialize tester.
        
        Args:
            base_url: Container API base URL
            verbose: Enable detailed logging
        """
        self.base_url = base_url.rstrip('/')
        self.verbose = verbose
        self.results = []
    
    def log(self, message: str, level: str = "INFO"):
        """Log message if verbose enabled."""
        if self.verbose or level in ["ERROR", "SUCCESS"]:
            timestamp = datetime.now().strftime("%H:%M:%S")
            symbol = {
                "INFO": "ℹ️",
                "SUCCESS": "✅",
                "ERROR": "❌",
                "WARNING": "⚠️",
                "TEST": "🧪"
            }.get(level, "•")
            print(f"[{timestamp}] {symbol} {message}")
    
    async def test_query(self, 
                        query: str, 
                        pin: Dict[str, float] = None,
                        expected_analysis_type: str = None,
                        test_name: str = None) -> Dict[str, Any]:
        """
        Test a single query against the API.
        
        Args:
            query: Natural language query
            pin: Optional pin location {'lat': float, 'lng': float}
            expected_analysis_type: Expected GEOINT analysis type
            test_name: Name for this test
        
        Returns:
            Test result dictionary
        """
        test_name = test_name or query[:50]
        self.log(f"Testing: {test_name}", "TEST")
        self.log(f"Query: '{query}'")
        if pin:
            self.log(f"Pin: ({pin['lat']:.4f}, {pin['lng']:.4f})")
        
        start_time = time.time()
        
        try:
            # Prepare request
            payload = {"query": query}
            if pin:
                payload["pin"] = pin
            
            # Call API
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    f"{self.base_url}/api/query",
                    json=payload,
                    timeout=aiohttp.ClientTimeout(total=120)
                ) as response:
                    elapsed = time.time() - start_time
                    
                    if response.status != 200:
                        error_text = await response.text()
                        self.log(f"API returned {response.status}: {error_text}", "ERROR")
                        return {
                            "test_name": test_name,
                            "query": query,
                            "pin": pin,
                            "success": False,
                            "error": f"HTTP {response.status}",
                            "elapsed_sec": elapsed
                        }
                    
                    data = await response.json()
                    
                    # Extract key information
                    result = {
                        "test_name": test_name,
                        "query": query,
                        "pin": pin,
                        "success": data.get("success", False),
                        "elapsed_sec": round(elapsed, 2),
                        "response_message": data.get("message", ""),
                        "has_map_data": data.get("results", {}).get("features") is not None,
                        "num_features": len(data.get("results", {}).get("features", [])),
                        "geoint_executed": False,
                        "analysis_type": None,
                        "numerical_values_present": False
                    }
                    
                    # Check if GEOINT analysis was executed
                    # Look for numerical patterns in response
                    message = result["response_message"].lower()
                    
                    # Check for elevation values
                    if any(pattern in message for pattern in ['m at', 'meters', 'feet', 'elevation:', 'peak:']):
                        result["numerical_values_present"] = True
                    
                    # Check for mobility percentages
                    if any(pattern in message for pattern in ['%', 'accessible', 'go zones', 'no-go']):
                        result["numerical_values_present"] = True
                    
                    # Check for coordinates
                    if '°' in message or 'lat' in message or 'lon' in message:
                        result["numerical_values_present"] = True
                    
                    # Determine if GEOINT was likely executed
                    if result["numerical_values_present"]:
                        result["geoint_executed"] = True
                        if "elevation" in message or "peak" in message or "meters" in message:
                            result["analysis_type"] = "terrain_analysis"
                        elif "accessible" in message or "mobility" in message or "go zones" in message:
                            result["analysis_type"] = "mobility_analysis"
                        elif "visible" in message or "line of sight" in message:
                            result["analysis_type"] = "line_of_sight"
                    
                    # Validate expectations
                    if expected_analysis_type:
                        if result["analysis_type"] == expected_analysis_type:
                            result["expected_analysis_match"] = True
                            self.log(f"Analysis type matches expected: {expected_analysis_type}", "SUCCESS")
                        else:
                            result["expected_analysis_match"] = False
                            self.log(f"Expected {expected_analysis_type}, got {result['analysis_type']}", "WARNING")
                    
                    # Log result
                    if result["geoint_executed"]:
                        self.log(f"GEOINT executed: {result['analysis_type']}", "SUCCESS")
                        self.log(f"Response preview: {result['response_message'][:150]}...")
                    else:
                        self.log(f"No GEOINT analysis detected (may be map-only query)", "WARNING")
                    
                    self.log(f"Completed in {elapsed:.2f}s")
                    
                    self.results.append(result)
                    return result
        
        except asyncio.TimeoutError:
            elapsed = time.time() - start_time
            self.log(f"Request timeout after {elapsed:.1f}s", "ERROR")
            return {
                "test_name": test_name,
                "query": query,
                "pin": pin,
                "success": False,
                "error": "Timeout",
                "elapsed_sec": elapsed
            }
        except Exception as e:
            elapsed = time.time() - start_time
            self.log(f"Error: {str(e)}", "ERROR")
            return {
                "test_name": test_name,
                "query": query,
                "pin": pin,
                "success": False,
                "error": str(e),
                "elapsed_sec": elapsed
            }
    
    async def run_terrain_analysis_tests(self):
        """Test terrain analysis queries."""
        self.log("\n" + "="*60)
        self.log("TERRAIN ANALYSIS TESTS")
        self.log("="*60 + "\n")
        
        tests = [
            {
                "query": "What is the highest peak elevation in the Grand Canyon?",
                "pin": None,
                "expected": "terrain_analysis",
                "name": "Grand Canyon Peak Elevation"
            },
            {
                "query": "Analyze terrain slope near Fort Carson, Colorado",
                "pin": None,
                "expected": "terrain_analysis",
                "name": "Fort Carson Terrain Slope"
            },
            {
                "query": "What is the elevation here?",
                "pin": {"lat": 36.1, "lng": -112.1},  # Grand Canyon
                "expected": "terrain_analysis",
                "name": "Pin-based Elevation Query"
            },
            {
                "query": "Calculate terrain roughness in the Rocky Mountains",
                "pin": None,
                "expected": "terrain_analysis",
                "name": "Rocky Mountains Roughness"
            }
        ]
        
        for test in tests:
            await self.test_query(
                query=test["query"],
                pin=test.get("pin"),
                expected_analysis_type=test["expected"],
                test_name=test["name"]
            )
            await asyncio.sleep(2)  # Pause between tests
    
    async def run_mobility_analysis_tests(self):
        """Test mobility analysis queries."""
        self.log("\n" + "="*60)
        self.log("MOBILITY ANALYSIS TESTS")
        self.log("="*60 + "\n")
        
        tests = [
            {
                "query": "Can emergency vehicles access flood-prone areas in Louisiana?",
                "pin": None,
                "expected": "mobility_analysis",
                "name": "Louisiana Emergency Access"
            },
            {
                "query": "Evaluate terrain mobility for convoy movement near Fort Bragg",
                "pin": None,
                "expected": "mobility_analysis",
                "name": "Fort Bragg Convoy Mobility"
            },
            {
                "query": "Is this terrain accessible for rescue operations?",
                "pin": {"lat": 29.95, "lng": -90.07},  # New Orleans
                "expected": "mobility_analysis",
                "name": "New Orleans Rescue Accessibility"
            },
            {
                "query": "Assess vehicle traversability in mountainous terrain",
                "pin": {"lat": 39.5, "lng": -105.8},  # Rocky Mountains
                "expected": "mobility_analysis",
                "name": "Mountain Traversability"
            }
        ]
        
        for test in tests:
            await self.test_query(
                query=test["query"],
                pin=test.get("pin"),
                expected_analysis_type=test["expected"],
                test_name=test["name"]
            )
            await asyncio.sleep(2)
    
    async def run_line_of_sight_tests(self):
        """Test line-of-sight queries."""
        self.log("\n" + "="*60)
        self.log("LINE-OF-SIGHT TESTS")
        self.log("="*60 + "\n")
        
        tests = [
            {
                "query": "Calculate line of sight from observation point",
                "pin": {"lat": 36.05, "lng": -112.14},  # Grand Canyon South Rim
                "expected": "line_of_sight",
                "name": "Grand Canyon Viewshed"
            },
            {
                "query": "What is visible from this hilltop?",
                "pin": {"lat": 40.7, "lng": -111.9},  # Utah mountains
                "expected": "line_of_sight",
                "name": "Hilltop Visibility"
            }
        ]
        
        for test in tests:
            await self.test_query(
                query=test["query"],
                pin=test.get("pin"),
                expected_analysis_type=test["expected"],
                test_name=test["name"]
            )
            await asyncio.sleep(2)
    
    async def run_comparison_tests(self):
        """Test GEOINT vs regular imagery queries."""
        self.log("\n" + "="*60)
        self.log("GEOINT VS IMAGERY COMPARISON TESTS")
        self.log("="*60 + "\n")
        
        # These should trigger GEOINT analysis
        geoint_queries = [
            "Analyze elevation profile from Denver to Colorado Springs",
            "Calculate slope distribution in mountain terrain",
            "Assess emergency vehicle accessibility"
        ]
        
        # These should NOT trigger GEOINT (regular imagery)
        imagery_queries = [
            "Show me Sentinel-2 imagery of Colorado",
            "Display recent satellite data for Louisiana",
            "Get Landsat images of the Grand Canyon"
        ]
        
        self.log("Testing GEOINT analytical queries...")
        for query in geoint_queries:
            result = await self.test_query(query, test_name=f"GEOINT: {query[:30]}")
            if not result.get("geoint_executed"):
                self.log(f"Expected GEOINT but none executed for: {query}", "WARNING")
            await asyncio.sleep(1)
        
        self.log("\nTesting regular imagery queries...")
        for query in imagery_queries:
            result = await self.test_query(query, test_name=f"Imagery: {query[:30]}")
            if result.get("geoint_executed"):
                self.log(f"Unexpected GEOINT execution for imagery query: {query}", "WARNING")
            await asyncio.sleep(1)
    
    async def run_all_tests(self):
        """Run complete test suite."""
        self.log("="*60)
        self.log("GEOINT RASTER ANALYSIS - FULL TEST SUITE")
        self.log("="*60)
        self.log(f"API Endpoint: {self.base_url}")
        self.log(f"Start Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        self.log("")
        
        # Run all test categories
        await self.run_terrain_analysis_tests()
        await self.run_mobility_analysis_tests()
        await self.run_line_of_sight_tests()
        await self.run_comparison_tests()
        
        # Print summary
        self.print_summary()
    
    def print_summary(self):
        """Print test results summary."""
        self.log("\n" + "="*60)
        self.log("TEST RESULTS SUMMARY")
        self.log("="*60 + "\n")
        
        total_tests = len(self.results)
        successful = sum(1 for r in self.results if r.get("success"))
        geoint_executed = sum(1 for r in self.results if r.get("geoint_executed"))
        avg_time = sum(r.get("elapsed_sec", 0) for r in self.results) / total_tests if total_tests > 0 else 0
        
        self.log(f"Total Tests: {total_tests}")
        self.log(f"Successful: {successful} ({successful/total_tests*100:.1f}%)")
        self.log(f"GEOINT Executed: {geoint_executed} ({geoint_executed/total_tests*100:.1f}%)")
        self.log(f"Average Time: {avg_time:.2f}s")
        self.log("")
        
        # Detailed results table
        self.log("Detailed Results:")
        self.log("-" * 100)
        self.log(f"{'Test Name':<40} {'Success':<10} {'GEOINT':<10} {'Time(s)':<10} {'Analysis Type':<20}")
        self.log("-" * 100)
        
        for result in self.results:
            test_name = result.get("test_name", "Unknown")[:39]
            success = "✅" if result.get("success") else "❌"
            geoint = "✅" if result.get("geoint_executed") else "⬜"
            elapsed = result.get("elapsed_sec", 0)
            analysis = result.get("analysis_type", "N/A")[:19]
            
            self.log(f"{test_name:<40} {success:<10} {geoint:<10} {elapsed:<10.2f} {analysis:<20}")
        
        self.log("-" * 100)
        self.log("")
        
        # Performance analysis
        self.log("Performance Analysis:")
        geoint_times = [r["elapsed_sec"] for r in self.results if r.get("geoint_executed")]
        if geoint_times:
            self.log(f"  GEOINT queries - Min: {min(geoint_times):.2f}s, Max: {max(geoint_times):.2f}s, Avg: {sum(geoint_times)/len(geoint_times):.2f}s")
        
        imagery_times = [r["elapsed_sec"] for r in self.results if not r.get("geoint_executed") and r.get("success")]
        if imagery_times:
            self.log(f"  Imagery queries - Min: {min(imagery_times):.2f}s, Max: {max(imagery_times):.2f}s, Avg: {sum(imagery_times)/len(imagery_times):.2f}s")
        
        # Failure analysis
        failures = [r for r in self.results if not r.get("success")]
        if failures:
            self.log(f"\nFailures ({len(failures)}):", "ERROR")
            for failure in failures:
                self.log(f"  - {failure['test_name']}: {failure.get('error', 'Unknown error')}", "ERROR")
        
        # Save results to JSON
        with open("geoint_test_results.json", "w") as f:
            json.dump({
                "timestamp": datetime.now().isoformat(),
                "summary": {
                    "total_tests": total_tests,
                    "successful": successful,
                    "geoint_executed": geoint_executed,
                    "average_time_sec": avg_time
                },
                "results": self.results
            }, f, indent=2)
        
        self.log(f"\nResults saved to: geoint_test_results.json")


async def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(description="Test GEOINT raster analysis API")
    parser.add_argument("--endpoint", default="http://localhost:8000", help="API endpoint URL")
    parser.add_argument("--test", choices=["terrain", "mobility", "los", "comparison", "all"], default="all", help="Test category to run")
    parser.add_argument("--verbose", action="store_true", help="Enable verbose logging")
    
    args = parser.parse_args()
    
    tester = GeointAPITester(base_url=args.endpoint, verbose=args.verbose)
    
    if args.test == "all":
        await tester.run_all_tests()
    elif args.test == "terrain":
        await tester.run_terrain_analysis_tests()
        tester.print_summary()
    elif args.test == "mobility":
        await tester.run_mobility_analysis_tests()
        tester.print_summary()
    elif args.test == "los":
        await tester.run_line_of_sight_tests()
        tester.print_summary()
    elif args.test == "comparison":
        await tester.run_comparison_tests()
        tester.print_summary()


if __name__ == "__main__":
    asyncio.run(main())
