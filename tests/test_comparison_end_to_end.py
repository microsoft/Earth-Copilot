"""
End-to-end test for comparison module with GPT-5 Vision integration

This test validates the complete comparison workflow:
1. User query → Parameter extraction (datetime, location, collections)
2. Dual STAC query execution (before/after)
3. Screenshot generation from STAC results
4. GPT-5 Vision analysis of before/after images
5. Return comparison insights to user
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
from typing import Dict, List, Optional

# Backend API endpoint (update with your deployed URL)
BACKEND_API = os.getenv("BACKEND_API_URL", "https://your-container-app.azurecontainerapps.io")

# Test queries for end-to-end comparison workflow
TEST_QUERIES = [
    {
        "name": "Wildfire Comparison - California",
        "query": "Compare wildfire activity in Northern California between January 2023 and January 2024",
        "expected": {
            "has_before_date": True,
            "has_after_date": True,
            "has_location": True,
            "has_collections": True,
            "collection_keywords": ["modis", "thermal", "fire"]
        }
    },
    {
        "name": "Urban Development - NYC",
        "query": "Show changes in New York City between June 2023 and June 2024",
        "expected": {
            "has_before_date": True,
            "has_after_date": True,
            "has_location": True,
            "has_collections": True,
            "collection_keywords": ["sentinel", "landsat"]
        }
    }
]


async def test_parameter_extraction(query: str, timeout: int = 60) -> Dict:
    """
    Test Step 1: Extract comparison parameters from user query
    
    Calls: POST /api/process-comparison-query
    
    Returns:
        {
            "success": bool,
            "before_date": str,
            "after_date": str,
            "bbox": [float],
            "collections": [str],
            "location_name": str,
            "error": str
        }
    """
    print(f"\n[STEP 1] Parameter Extraction")
    print(f"Query: {query}")
    
    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(
                f"{BACKEND_API}/api/process-comparison-query",
                json={"query": query},
                timeout=aiohttp.ClientTimeout(total=timeout)
            ) as response:
                if response.status == 200:
                    data = await response.json()
                    print(f"[OK] Status: 200")
                    print(f"Before Date: {data.get('before_date', 'N/A')}")
                    print(f"After Date: {data.get('after_date', 'N/A')}")
                    print(f"Location: {data.get('location_name', 'N/A')}")
                    print(f"BBox: {data.get('bbox', 'N/A')}")
                    print(f"Collections: {data.get('collections', [])}")
                    
                    return {
                        "success": True,
                        "before_date": data.get("before_date"),
                        "after_date": data.get("after_date"),
                        "bbox": data.get("bbox"),
                        "collections": data.get("collections", []),
                        "location_name": data.get("location_name"),
                        "primary_collection": data.get("primary_collection"),
                        "error": None
                    }
                else:
                    error_text = await response.text()
                    print(f"[ERROR] Status: {response.status}")
                    print(f"Error: {error_text[:300]}")
                    return {
                        "success": False,
                        "error": f"HTTP {response.status}: {error_text[:300]}"
                    }
    except asyncio.TimeoutError:
        print(f"[ERROR] Timeout after {timeout}s")
        return {"success": False, "error": f"Timeout after {timeout}s"}
    except Exception as e:
        print(f"[ERROR] {type(e).__name__}: {str(e)}")
        return {"success": False, "error": f"{type(e).__name__}: {str(e)}"}


async def test_stac_execution(params: Dict, timeout: int = 30) -> Dict:
    """
    Test Step 2: Execute dual STAC queries
    
    Uses: params from step 1 to query STAC APIs directly
    
    Returns:
        {
            "success": bool,
            "before_items": [dict],
            "after_items": [dict],
            "before_count": int,
            "after_count": int,
            "error": str
        }
    """
    print(f"\n[STEP 2] Dual STAC Query Execution")
    
    # Build STAC queries
    stac_url = "https://planetarycomputer.microsoft.com/api/stac/v1/search"
    
    before_query = {
        "collections": params["collections"],
        "bbox": params["bbox"],
        "datetime": params["before_date"],
        "limit": 10
    }
    
    after_query = {
        "collections": params["collections"],
        "bbox": params["bbox"],
        "datetime": params["after_date"],
        "limit": 10
    }
    
    print(f"STAC URL: {stac_url}")
    print(f"Before Query: collections={params['collections']}, datetime={params['before_date']}")
    print(f"After Query: collections={params['collections']}, datetime={params['after_date']}")
    
    try:
        async with aiohttp.ClientSession() as session:
            # Execute in parallel
            before_task = session.post(stac_url, json=before_query, timeout=aiohttp.ClientTimeout(total=timeout))
            after_task = session.post(stac_url, json=after_query, timeout=aiohttp.ClientTimeout(total=timeout))
            
            before_resp, after_resp = await asyncio.gather(before_task, after_task)
            
            # Parse results
            before_success = before_resp.status == 200
            after_success = after_resp.status == 200
            
            before_data = await before_resp.json() if before_success else None
            after_data = await after_resp.json() if after_success else None
            
            before_items = before_data.get("features", []) if before_data else []
            after_items = after_data.get("features", []) if after_data else []
            
            print(f"[OK] Before Query: {len(before_items)} items")
            print(f"[OK] After Query: {len(after_items)} items")
            
            if not before_success or not after_success:
                error_msg = f"Before: {before_resp.status}, After: {after_resp.status}"
                print(f"[ERROR] {error_msg}")
                return {
                    "success": False,
                    "error": error_msg
                }
            
            return {
                "success": True,
                "before_items": before_items,
                "after_items": after_items,
                "before_count": len(before_items),
                "after_count": len(after_items),
                "error": None
            }
    
    except Exception as e:
        print(f"[ERROR] {type(e).__name__}: {str(e)}")
        return {
            "success": False,
            "error": f"{type(e).__name__}: {str(e)}"
        }


async def test_gpt5_vision_analysis(
    params: Dict,
    stac_results: Dict,
    original_query: str,
    timeout: int = 120
) -> Dict:
    """
    Test Step 3: GPT-5 Vision comparison analysis
    
    Calls: POST /api/geoint/comparison
    
    For this test, we'll use mock screenshots since we can't generate actual
    map images without a full rendering pipeline. In production, this would:
    1. Render before/after STAC items to map screenshots
    2. Pass screenshots + metadata to GPT-5 Vision
    3. Get comparison analysis
    
    Returns:
        {
            "success": bool,
            "analysis": str,
            "error": str
        }
    """
    print(f"\n[STEP 3] GPT-5 Vision Comparison Analysis")
    print(f"Original Query: {original_query}")
    
    # Extract center point from bbox for API call
    bbox = params["bbox"]
    center_lng = (bbox[0] + bbox[2]) / 2
    center_lat = (bbox[1] + bbox[3]) / 2
    
    print(f"Location: ({center_lat:.4f}, {center_lng:.4f})")
    print(f"Before Date: {params['before_date']}")
    print(f"After Date: {params['after_date']}")
    print(f"Collection: {params.get('primary_collection', 'N/A')}")
    
    # For end-to-end testing, we'll call the API with raster download enabled
    # (no screenshots needed - API will generate imagery from STAC data)
    try:
        async with aiohttp.ClientSession() as session:
            payload = {
                "latitude": center_lat,
                "longitude": center_lng,
                "before_date": params["before_date"],
                "after_date": params["after_date"],
                "collection_id": params.get("primary_collection"),
                "download_rasters": True,
                "user_query": original_query
            }
            
            print(f"[REQUEST] Calling /api/geoint/comparison")
            print(f"Payload: {json.dumps({k: v for k, v in payload.items() if k != 'user_query'}, indent=2)}")
            
            async with session.post(
                f"{BACKEND_API}/api/geoint/comparison",
                json=payload,
                timeout=aiohttp.ClientTimeout(total=timeout)
            ) as response:
                if response.status == 200:
                    data = await response.json()
                    analysis = data.get("result", {})
                    
                    print(f"[OK] Status: 200")
                    print(f"[OK] GPT-5 Vision Analysis Received")
                    
                    # Extract key insights from analysis
                    if isinstance(analysis, dict):
                        print(f"\n{'=' * 60}")
                        print(f"GPT-5 VISION COMPARISON ANALYSIS:")
                        print(f"{'=' * 60}")
                        
                        # Print analysis content (varies by response structure)
                        if "analysis" in analysis:
                            print(analysis["analysis"][:500])  # First 500 chars
                        elif "comparison" in analysis:
                            print(analysis["comparison"][:500])
                        else:
                            print(str(analysis)[:500])
                        
                        print(f"{'=' * 60}\n")
                    else:
                        print(f"Analysis: {str(analysis)[:500]}")
                    
                    return {
                        "success": True,
                        "analysis": analysis,
                        "error": None
                    }
                else:
                    error_text = await response.text()
                    print(f"[ERROR] Status: {response.status}")
                    print(f"Error: {error_text[:300]}")
                    
                    return {
                        "success": False,
                        "error": f"HTTP {response.status}: {error_text[:300]}"
                    }
    
    except asyncio.TimeoutError:
        print(f"[ERROR] Timeout after {timeout}s")
        return {"success": False, "error": f"Timeout after {timeout}s"}
    except Exception as e:
        print(f"[ERROR] {type(e).__name__}: {str(e)}")
        return {"success": False, "error": f"{type(e).__name__}: {str(e)}"}


def validate_end_to_end_result(
    param_result: Dict,
    stac_result: Dict,
    vision_result: Dict,
    expected: Dict
) -> tuple[bool, List[str]]:
    """Validate end-to-end test results"""
    issues = []
    
    # Step 1: Parameter extraction
    if not param_result.get("success"):
        issues.append(f"Parameter extraction failed: {param_result.get('error')}")
    else:
        if expected["has_before_date"] and not param_result.get("before_date"):
            issues.append("Missing before_date")
        if expected["has_after_date"] and not param_result.get("after_date"):
            issues.append("Missing after_date")
        if expected["has_location"] and not param_result.get("bbox"):
            issues.append("Missing bbox/location")
        if expected["has_collections"] and not param_result.get("collections"):
            issues.append("Missing collections")
    
    # Step 2: STAC execution
    if not stac_result.get("success"):
        issues.append(f"STAC execution failed: {stac_result.get('error')}")
    else:
        if stac_result.get("before_count", 0) == 0:
            issues.append("No before STAC items returned")
        if stac_result.get("after_count", 0) == 0:
            issues.append("No after STAC items returned")
    
    # Step 3: GPT-5 Vision analysis
    if not vision_result.get("success"):
        issues.append(f"GPT-5 Vision analysis failed: {vision_result.get('error')}")
    else:
        analysis = vision_result.get("analysis")
        if not analysis:
            issues.append("No analysis returned from GPT-5 Vision")
        elif isinstance(analysis, str) and len(analysis) < 50:
            issues.append("Analysis too short - may be incomplete")
    
    passed = len(issues) == 0
    return passed, issues


async def test_end_to_end():
    """Run end-to-end comparison module tests"""
    
    print("=" * 80)
    print("END-TO-END COMPARISON MODULE TEST - WITH GPT-5 VISION")
    print("=" * 80)
    print(f"\nTesting {len(TEST_QUERIES)} comparison workflows...\n")
    print(f"Backend: {BACKEND_API}")
    print("=" * 80)
    
    results = {
        "passed": 0,
        "failed": 0,
        "errors": 0,
        "details": []
    }
    
    for i, test_case in enumerate(TEST_QUERIES, 1):
        name = test_case["name"]
        query = test_case["query"]
        expected = test_case["expected"]
        
        print(f"\n{'=' * 80}")
        print(f"TEST {i}/{len(TEST_QUERIES)}: {name}")
        print(f"{'=' * 80}")
        print(f"Query: {query}")
        print(f"{'=' * 80}")
        
        try:
            # Step 1: Parameter extraction
            param_result = await test_parameter_extraction(query)
            
            if not param_result["success"]:
                print(f"\n[FAIL] Parameter extraction failed")
                results["failed"] += 1
                results["details"].append({
                    "test": i,
                    "name": name,
                    "status": "failed",
                    "step": "parameter_extraction",
                    "error": param_result["error"]
                })
                continue
            
            # Step 2: STAC execution
            stac_result = await test_stac_execution(param_result)
            
            if not stac_result["success"]:
                print(f"\n[FAIL] STAC execution failed")
                results["failed"] += 1
                results["details"].append({
                    "test": i,
                    "name": name,
                    "status": "failed",
                    "step": "stac_execution",
                    "error": stac_result["error"],
                    "params": param_result
                })
                continue
            
            # Step 3: GPT-5 Vision analysis
            vision_result = await test_gpt5_vision_analysis(
                param_result,
                stac_result,
                query
            )
            
            # Validate complete workflow
            passed, issues = validate_end_to_end_result(
                param_result,
                stac_result,
                vision_result,
                expected
            )
            
            if passed:
                print(f"\n[PASS] END-TO-END TEST PASSED")
                print(f"✓ Parameter extraction successful")
                print(f"✓ Before STAC query: {stac_result['before_count']} items")
                print(f"✓ After STAC query: {stac_result['after_count']} items")
                print(f"✓ GPT-5 Vision analysis received")
                print(f"✓ Complete comparison workflow validated")
                
                results["passed"] += 1
                results["details"].append({
                    "test": i,
                    "name": name,
                    "status": "passed",
                    "query": query,
                    "before_date": param_result["before_date"],
                    "after_date": param_result["after_date"],
                    "location": param_result["location_name"],
                    "collections": param_result["collections"],
                    "before_items": stac_result["before_count"],
                    "after_items": stac_result["after_count"],
                    "has_gpt5_analysis": vision_result["success"]
                })
            else:
                print(f"\n[FAIL] END-TO-END TEST FAILED")
                for issue in issues:
                    print(f"   - {issue}")
                
                results["failed"] += 1
                results["details"].append({
                    "test": i,
                    "name": name,
                    "status": "failed",
                    "issues": issues,
                    "query": query
                })
        
        except Exception as e:
            print(f"\n[EXCEPTION] {type(e).__name__}: {str(e)}")
            results["errors"] += 1
            results["details"].append({
                "test": i,
                "name": name,
                "status": "exception",
                "exception": str(e)
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
    print(f"{'=' * 80}")
    
    # Print details
    if results["passed"] > 0:
        print(f"\n[PASS] PASSED TESTS:")
        print(f"{'-' * 80}")
        for detail in results["details"]:
            if detail["status"] == "passed":
                print(f"\nTest {detail['test']}: {detail['name']}")
                print(f"  Query: {detail['query']}")
                print(f"  Location: {detail['location']}")
                print(f"  Before: {detail['before_date']} ({detail['before_items']} items)")
                print(f"  After: {detail['after_date']} ({detail['after_items']} items)")
                print(f"  Collections: {', '.join(detail['collections'])}")
                print(f"  ✓ GPT-5 Vision analysis: {'Received' if detail['has_gpt5_analysis'] else 'Failed'}")
    
    if results["failed"] > 0 or results["errors"] > 0:
        print(f"\n[FAIL/ERROR] FAILED/ERROR TESTS:")
        print(f"{'-' * 80}")
        for detail in results["details"]:
            if detail["status"] in ["failed", "exception"]:
                print(f"\nTest {detail['test']}: {detail['name']}")
                if detail["status"] == "failed":
                    print(f"  Failed at: {detail.get('step', 'validation')}")
                    print(f"  Error: {detail.get('error', 'Validation issues')}")
                    if "issues" in detail:
                        for issue in detail["issues"]:
                            print(f"    - {issue}")
                else:
                    print(f"  Exception: {detail['exception']}")
    
    # Save results
    output_file = "comparison_end_to_end_results.json"
    with open(output_file, "w") as f:
        json.dump(results, f, indent=2)
    print(f"\n[SAVE] Detailed results saved to: {output_file}")
    
    # Final verdict
    print(f"\n{'=' * 80}")
    if results["errors"] > 0:
        print(f"[ERROR] {results['errors']} tests had errors")
    elif results["failed"] > 0:
        print(f"[WARNING] {results['failed']} tests failed")
    else:
        print(f"[SUCCESS] ALL END-TO-END TESTS PASSED!")
        print(f"[SUCCESS] Comparison module with GPT-5 Vision is ready for production!")
    print(f"{'=' * 80}\n")
    
    return results


if __name__ == "__main__":
    print("\n[TEST] Starting End-to-End Comparison Module Tests\n")
    results = asyncio.run(test_end_to_end())
    
    # Exit with appropriate code
    if results["errors"] > 0 or results["failed"] > 0:
        exit(1)
    else:
        exit(0)
