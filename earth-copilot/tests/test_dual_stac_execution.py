"""
Test suite for dual STAC query execution in comparison module

This test validates that the comparison workflow can:
1. Generate two properly formatted STAC queries (before/after) from comparison parameters
2. Execute both STAC queries in parallel
3. Handle various success/failure scenarios
4. Return results suitable for GPT-5 Vision analysis
"""

import sys
import os

# Set UTF-8 encoding for Windows console output
if sys.platform == 'win32':
    import codecs
    sys.stdout = codecs.getwriter('utf-8')(sys.stdout.buffer, 'strict')
    sys.stderr = codecs.getwriter('utf-8')(sys.stderr.buffer, 'strict')

import asyncio
import json
import aiohttp
from datetime import datetime
from typing import Dict, List, Optional, Tuple

# STAC API endpoints
PLANETARY_COMPUTER_STAC = "https://planetarycomputer.microsoft.com/api/stac/v1/search"
VEDA_STAC = "https://openveda.cloud/api/stac/search"

# Test scenarios with hypothetical comparison queries
TEST_SCENARIOS = [
    {
        "name": "Wildfire Comparison - California 2023 vs 2024",
        "collections": ["modis-14A1-061"],
        "bbox": [-122.5, 37.0, -121.5, 38.0],  # Northern California
        "before_date": "2023-08-01/2023-08-31",
        "after_date": "2024-08-01/2024-08-31",
        "expected_results": "both",  # Both queries should return results
        "description": "Thermal anomaly comparison for wildfire activity"
    },
    {
        "name": "Urban Development - NYC 2023 vs 2024",
        "collections": ["sentinel-2-l2a"],
        "bbox": [-74.1, 40.6, -73.8, 40.9],  # New York City
        "before_date": "2023-06-01/2023-06-30",
        "after_date": "2024-06-01/2024-06-30",
        "expected_results": "both",
        "description": "Optical imagery for urban change detection"
    },
    {
        "name": "Flood Analysis - Houston 2023 vs 2024",
        "collections": ["sentinel-1-grd"],
        "bbox": [-95.5, 29.6, -95.2, 29.9],  # Houston area
        "before_date": "2023-05-01/2023-05-31",
        "after_date": "2024-05-01/2024-05-31",
        "expected_results": "both",
        "description": "SAR imagery for flood extent comparison"
    },
    {
        "name": "Vegetation Change - Amazon 2022 vs 2023",
        "collections": ["sentinel-2-l2a", "landsat-c2-l2"],
        "bbox": [-60.0, -3.5, -59.0, -2.5],  # Amazon region
        "before_date": "2022-07-01/2022-07-31",
        "after_date": "2023-07-01/2023-07-31",
        "expected_results": "both",
        "description": "Multi-collection vegetation analysis"
    },
    {
        "name": "Coastal Change - Miami 2020 vs 2024",
        "collections": ["sentinel-2-l2a"],
        "bbox": [-80.3, 25.7, -80.1, 25.9],  # Miami coastline
        "before_date": "2020-03-01/2020-03-31",
        "after_date": "2024-03-01/2024-03-31",
        "expected_results": "both",
        "description": "Long-term coastal erosion monitoring"
    }
]


def build_stac_query(
    collections: List[str],
    bbox: List[float],
    datetime_range: str,
    limit: int = 10
) -> Dict:
    """
    Build a STAC query dictionary
    
    Args:
        collections: List of collection IDs
        bbox: Bounding box [west, south, east, north]
        datetime_range: ISO 8601 datetime range (e.g., "2023-01-01/2023-01-31")
        limit: Maximum number of items to return
    
    Returns:
        STAC query dictionary
    """
    query = {
        "collections": collections,
        "bbox": bbox,
        "datetime": datetime_range,
        "limit": limit
    }
    return query


async def execute_stac_query(
    stac_url: str,
    query: Dict,
    timeout: int = 30
) -> Tuple[bool, Optional[Dict], Optional[str]]:
    """
    Execute a STAC query against the API
    
    Args:
        stac_url: STAC API endpoint URL
        query: STAC query dictionary
        timeout: Request timeout in seconds
    
    Returns:
        (success, result_dict, error_message)
    """
    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(
                stac_url,
                json=query,
                timeout=aiohttp.ClientTimeout(total=timeout)
            ) as response:
                if response.status == 200:
                    result = await response.json()
                    return True, result, None
                else:
                    error_text = await response.text()
                    return False, None, f"HTTP {response.status}: {error_text[:200]}"
    except asyncio.TimeoutError:
        return False, None, f"Timeout after {timeout}s"
    except Exception as e:
        return False, None, f"{type(e).__name__}: {str(e)}"


async def execute_dual_stac_queries(
    collections: List[str],
    bbox: List[float],
    before_date: str,
    after_date: str,
    stac_url: str = PLANETARY_COMPUTER_STAC
) -> Dict:
    """
    Execute two STAC queries in parallel (before and after)
    
    Returns:
        {
            "before": {"success": bool, "items": [...], "count": int, "error": str},
            "after": {"success": bool, "items": [...], "count": int, "error": str},
            "parallel_execution": bool,
            "total_time_ms": float
        }
    """
    start_time = datetime.now()
    
    # Build both queries
    before_query = build_stac_query(collections, bbox, before_date)
    after_query = build_stac_query(collections, bbox, after_date)
    
    # Execute in parallel
    before_task = execute_stac_query(stac_url, before_query)
    after_task = execute_stac_query(stac_url, after_query)
    
    before_result, after_result = await asyncio.gather(before_task, after_task)
    
    end_time = datetime.now()
    total_time_ms = (end_time - start_time).total_seconds() * 1000
    
    # Parse results
    before_success, before_data, before_error = before_result
    after_success, after_data, after_error = after_result
    
    result = {
        "before": {
            "success": before_success,
            "items": before_data.get("features", []) if before_data else [],
            "count": len(before_data.get("features", [])) if before_data else 0,
            "error": before_error
        },
        "after": {
            "success": after_success,
            "items": after_data.get("features", []) if after_data else [],
            "count": len(after_data.get("features", [])) if after_data else 0,
            "error": after_error
        },
        "parallel_execution": True,
        "total_time_ms": total_time_ms
    }
    
    return result


def validate_stac_results(result: Dict, expected: str) -> Tuple[bool, List[str]]:
    """
    Validate STAC query results
    
    Args:
        result: Result from execute_dual_stac_queries
        expected: "both", "before_only", "after_only", or "neither"
    
    Returns:
        (passed, issues)
    """
    issues = []
    
    before_success = result["before"]["success"]
    after_success = result["after"]["success"]
    before_count = result["before"]["count"]
    after_count = result["after"]["count"]
    
    # Check execution
    if not result.get("parallel_execution"):
        issues.append("Queries were not executed in parallel")
    
    # Check expected results
    if expected == "both":
        if not before_success:
            issues.append(f"Before query failed: {result['before']['error']}")
        if not after_success:
            issues.append(f"After query failed: {result['after']['error']}")
        if before_count == 0:
            issues.append("Before query returned 0 items")
        if after_count == 0:
            issues.append("After query returned 0 items")
    
    elif expected == "before_only":
        if not before_success or before_count == 0:
            issues.append("Before query should have succeeded with results")
        if after_success and after_count > 0:
            issues.append("After query should have failed or returned no results")
    
    elif expected == "after_only":
        if not after_success or after_count == 0:
            issues.append("After query should have succeeded with results")
        if before_success and before_count > 0:
            issues.append("Before query should have failed or returned no results")
    
    # Check for GPT-5 Vision readiness
    if before_success and after_success:
        # Check that items have necessary fields for image retrieval
        for label, items in [("before", result["before"]["items"]), ("after", result["after"]["items"])]:
            if items and len(items) > 0:
                first_item = items[0]
                if "assets" not in first_item:
                    issues.append(f"{label} items missing 'assets' field")
                if "geometry" not in first_item:
                    issues.append(f"{label} items missing 'geometry' field")
    
    passed = len(issues) == 0
    return passed, issues


async def test_dual_stac_execution():
    """Test dual STAC query execution for comparison module"""
    
    print("=" * 80)
    print("DUAL STAC QUERY EXECUTION TEST - COMPARISON MODULE")
    print("=" * 80)
    print(f"\nTesting {len(TEST_SCENARIOS)} comparison scenarios...\n")
    
    results = {
        "passed": 0,
        "failed": 0,
        "errors": 0,
        "details": []
    }
    
    for i, scenario in enumerate(TEST_SCENARIOS, 1):
        name = scenario["name"]
        collections = scenario["collections"]
        bbox = scenario["bbox"]
        before_date = scenario["before_date"]
        after_date = scenario["after_date"]
        expected = scenario["expected_results"]
        
        print(f"\n{'=' * 80}")
        print(f"TEST {i}/{len(TEST_SCENARIOS)}: {name}")
        print(f"{'=' * 80}")
        print(f"Collections: {collections}")
        print(f"BBox: {bbox}")
        print(f"Before: {before_date}")
        print(f"After:  {after_date}")
        print(f"Expected: {expected}")
        print(f"{'-' * 80}")
        
        try:
            # Execute dual STAC queries
            result = await execute_dual_stac_queries(
                collections=collections,
                bbox=bbox,
                before_date=before_date,
                after_date=after_date
            )
            
            print(f"\n[OK] Queries Executed")
            print(f"Execution Time: {result['total_time_ms']:.0f}ms")
            print(f"Parallel: {result['parallel_execution']}")
            print(f"\nBefore Query:")
            print(f"  Success: {result['before']['success']}")
            print(f"  Items: {result['before']['count']}")
            if result['before']['error']:
                print(f"  Error: {result['before']['error']}")
            print(f"\nAfter Query:")
            print(f"  Success: {result['after']['success']}")
            print(f"  Items: {result['after']['count']}")
            if result['after']['error']:
                print(f"  Error: {result['after']['error']}")
            
            # Validate results
            passed, issues = validate_stac_results(result, expected)
            
            if passed:
                print(f"\n[PASS] TEST PASSED")
                print(f"✓ Both queries executed successfully in parallel")
                print(f"✓ Before query returned {result['before']['count']} items")
                print(f"✓ After query returned {result['after']['count']} items")
                print(f"✓ Results ready for GPT-5 Vision analysis")
                
                results["passed"] += 1
                results["details"].append({
                    "test": i,
                    "name": name,
                    "status": "passed",
                    "before_count": result['before']['count'],
                    "after_count": result['after']['count'],
                    "execution_time_ms": result['total_time_ms'],
                    "description": scenario["description"]
                })
            else:
                print(f"\n[FAIL] TEST FAILED")
                for issue in issues:
                    print(f"   - {issue}")
                
                results["failed"] += 1
                results["details"].append({
                    "test": i,
                    "name": name,
                    "status": "failed",
                    "issues": issues,
                    "before_count": result['before']['count'],
                    "after_count": result['after']['count'],
                    "before_error": result['before']['error'],
                    "after_error": result['after']['error'],
                    "execution_time_ms": result['total_time_ms'],
                    "description": scenario["description"]
                })
        
        except Exception as e:
            print(f"\n[EXCEPTION] {type(e).__name__}: {str(e)}")
            results["errors"] += 1
            results["details"].append({
                "test": i,
                "name": name,
                "status": "exception",
                "exception": str(e),
                "description": scenario["description"]
            })
    
    # Print summary
    print(f"\n{'=' * 80}")
    print("TEST SUMMARY")
    print(f"{'=' * 80}")
    total = results["passed"] + results["failed"] + results["errors"]
    print(f"Total Tests:  {total}")
    print(f"[PASS] Passed:  {results['passed']} ({results['passed']/total*100:.1f}%)")
    print(f"[FAIL] Failed:  {results['failed']} ({results['failed']/total*100:.1f}%)")
    print(f"[ERR]  Errors:  {results['errors']} ({results['errors']/total*100:.1f}%)")
    
    if results["passed"] > 0:
        avg_time = sum(d["execution_time_ms"] for d in results["details"] if d["status"] == "passed") / results["passed"]
        print(f"\nAverage Execution Time: {avg_time:.0f}ms")
    
    print(f"{'=' * 80}")
    
    # Print failed/error cases
    if results["failed"] > 0 or results["errors"] > 0:
        print(f"\n[FAIL/ERROR] FAILED/ERROR CASES:")
        print(f"{'-' * 80}")
        for detail in results["details"]:
            if detail["status"] in ["failed", "exception"]:
                print(f"\nTest {detail['test']}: {detail['name']}")
                if detail["status"] == "failed":
                    print(f"  Before: {detail.get('before_count', 0)} items")
                    print(f"  After: {detail.get('after_count', 0)} items")
                    print(f"  Issues:")
                    for issue in detail.get("issues", []):
                        print(f"    - {issue}")
                    if detail.get("before_error"):
                        print(f"  Before Error: {detail['before_error']}")
                    if detail.get("after_error"):
                        print(f"  After Error: {detail['after_error']}")
                else:
                    print(f"  Exception: {detail['exception']}")
    
    # Print passed cases
    if results["passed"] > 0:
        print(f"\n[PASS] PASSED CASES:")
        print(f"{'-' * 80}")
        for detail in results["details"]:
            if detail["status"] == "passed":
                print(f"\nTest {detail['test']}: {detail['name']}")
                print(f"  Before: {detail['before_count']} items")
                print(f"  After: {detail['after_count']} items")
                print(f"  Time: {detail['execution_time_ms']:.0f}ms")
                print(f"  ✓ {detail['description']}")
    
    # Save results to JSON
    output_file = "dual_stac_test_results.json"
    with open(output_file, "w") as f:
        json.dump(results, f, indent=2)
    print(f"\n[SAVE] Detailed results saved to: {output_file}")
    
    # Final verdict
    print(f"\n{'=' * 80}")
    if results["errors"] > 0:
        print(f"[ERROR] {results['errors']} tests had errors - check execution logic")
    elif results["failed"] > 0:
        print(f"[WARNING] {results['failed']} tests failed - review STAC queries or data availability")
    else:
        print(f"[SUCCESS] ALL TESTS PASSED! Dual STAC execution ready for comparison module")
        print(f"[SUCCESS] Results are ready for GPT-5 Vision analysis")
    print(f"{'=' * 80}\n")
    
    return results


if __name__ == "__main__":
    print("\n[TEST] Starting Dual STAC Query Execution Tests\n")
    results = asyncio.run(test_dual_stac_execution())
    
    # Exit with appropriate code
    if results["errors"] > 0 or results["failed"] > 0:
        exit(1)
    else:
        exit(0)
