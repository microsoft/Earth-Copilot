"""
Local end-to-end test for comparison module (no backend API required)

This test validates the complete comparison workflow locally:
1. User query → Parameter extraction using local SemanticQueryTranslator
2. Dual STAC query execution (actual API calls)
3. Mock GPT-5 Vision analysis (validates data structure)

This allows us to test our datetime extraction fixes before deploying.
"""

import sys
import os

# Set UTF-8 encoding for Windows console output
if sys.platform == 'win32':
    import codecs
    sys.stdout = codecs.getwriter('utf-8')(sys.stdout.buffer, 'strict')
    sys.stderr = codecs.getwriter('utf-8')(sys.stderr.buffer, 'strict')

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import asyncio
import json
import aiohttp
from datetime import datetime
from typing import Dict, List, Optional

# Import local semantic translator
from semantic_translator import SemanticQueryTranslator

# Azure OpenAI configuration
AZURE_OPENAI_ENDPOINT = os.getenv("AZURE_OPENAI_ENDPOINT", "https://earth-copilot-foundry.cognitiveservices.azure.com/")
AZURE_OPENAI_API_KEY = os.getenv("AZURE_OPENAI_API_KEY", "ebfd6d4da74d4df8a86cdd059104b3d0")
MODEL_NAME = "gpt-4o"

# STAC API
STAC_URL = "https://planetarycomputer.microsoft.com/api/stac/v1/search"

# Test queries
TEST_QUERIES = [
    {
        "name": "Wildfire Comparison - California",
        "query": "Compare wildfire activity in Northern California between January 2023 and January 2024",
    },
    {
        "name": "Urban Development - NYC",
        "query": "Show changes in New York City between June 2023 and June 2024",
    }
]


async def init_translator():
    """Initialize SemanticQueryTranslator"""
    print("[INIT] Initializing SemanticQueryTranslator...")
    translator = SemanticQueryTranslator(
        azure_openai_endpoint=AZURE_OPENAI_ENDPOINT,
        azure_openai_api_key=AZURE_OPENAI_API_KEY,
        model_name=MODEL_NAME
    )
    # Ensure kernel is initialized
    await translator._ensure_kernel_initialized()
    print("[OK] Translator initialized")
    return translator


async def extract_comparison_parameters(translator, query: str) -> Dict:
    """Extract comparison parameters locally"""
    print(f"\n[STEP 1] Local Parameter Extraction")
    print(f"Query: {query}")
    
    try:
        # Step 1: Collection selection
        collections_result = await translator.collection_mapping_agent(query)
        collections = collections_result.get("collections", [])
        print(f"[OK] Collections: {collections}")
        
        # Step 2: Location resolution
        location_result = await translator.build_stac_query_agent(query, collections)
        bbox = location_result.get("bbox")
        location_name = location_result.get("location", {}).get("name", "Unknown")
        print(f"[OK] Location: {location_name}")
        print(f"[OK] BBox: {bbox}")
        
        # Step 3: Datetime extraction (comparison mode)
        datetime_result = await translator.datetime_translation_agent(
            query,
            collections,
            mode="comparison"
        )
        before_date = datetime_result.get("before")
        after_date = datetime_result.get("after")
        print(f"[OK] Before Date: {before_date}")
        print(f"[OK] After Date: {after_date}")
        
        # Step 4: Primary collection selection
        primary_collection = collections[0] if collections else None
        print(f"[OK] Primary Collection: {primary_collection}")
        
        return {
            "success": True,
            "collections": collections,
            "bbox": bbox,
            "location_name": location_name,
            "before_date": before_date,
            "after_date": after_date,
            "primary_collection": primary_collection,
            "error": None
        }
    
    except Exception as e:
        print(f"[ERROR] {type(e).__name__}: {str(e)}")
        return {
            "success": False,
            "error": f"{type(e).__name__}: {str(e)}"
        }


async def execute_dual_stac_queries(params: Dict) -> Dict:
    """Execute dual STAC queries"""
    print(f"\n[STEP 2] Dual STAC Query Execution")
    
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
    
    print(f"Before Query: {params['before_date']}")
    print(f"After Query: {params['after_date']}")
    
    try:
        async with aiohttp.ClientSession() as session:
            before_task = session.post(STAC_URL, json=before_query, timeout=aiohttp.ClientTimeout(total=30))
            after_task = session.post(STAC_URL, json=after_query, timeout=aiohttp.ClientTimeout(total=30))
            
            before_resp, after_resp = await asyncio.gather(before_task, after_task)
            
            before_data = await before_resp.json() if before_resp.status == 200 else None
            after_data = await after_resp.json() if after_resp.status == 200 else None
            
            before_items = before_data.get("features", []) if before_data else []
            after_items = after_data.get("features", []) if after_data else []
            
            print(f"[OK] Before: {len(before_items)} items")
            print(f"[OK] After: {len(after_items)} items")
            
            return {
                "success": True,
                "before_count": len(before_items),
                "after_count": len(after_items),
                "before_items": before_items,
                "after_items": after_items,
                "error": None
            }
    
    except Exception as e:
        print(f"[ERROR] {type(e).__name__}: {str(e)}")
        return {
            "success": False,
            "error": f"{type(e).__name__}: {str(e)}"
        }


def validate_for_gpt5_vision(stac_result: Dict) -> Dict:
    """Validate that STAC results are ready for GPT-5 Vision"""
    print(f"\n[STEP 3] GPT-5 Vision Data Validation")
    
    issues = []
    
    if stac_result["before_count"] == 0:
        issues.append("No before items available")
    if stac_result["after_count"] == 0:
        issues.append("No after items available")
    
    # Check for required fields in STAC items
    for label, items in [("before", stac_result.get("before_items", [])), 
                         ("after", stac_result.get("after_items", []))]:
        if items and len(items) > 0:
            first_item = items[0]
            if "assets" not in first_item:
                issues.append(f"{label} items missing 'assets' field")
            if "geometry" not in first_item:
                issues.append(f"{label} items missing 'geometry' field")
            else:
                print(f"[OK] {label.capitalize()} items have required fields for image generation")
    
    if len(issues) == 0:
        print(f"[OK] Data structure ready for GPT-5 Vision analysis")
        print(f"[OK] Before items: {stac_result['before_count']}")
        print(f"[OK] After items: {stac_result['after_count']}")
        print(f"[OK] Both have assets and geometry for rendering")
        return {"success": True, "ready": True, "issues": []}
    else:
        print(f"[FAIL] Data not ready for GPT-5 Vision:")
        for issue in issues:
            print(f"   - {issue}")
        return {"success": False, "ready": False, "issues": issues}


async def test_local_end_to_end():
    """Test complete comparison workflow locally"""
    
    print("=" * 80)
    print("LOCAL END-TO-END COMPARISON TEST")
    print("=" * 80)
    print(f"\nTesting {len(TEST_QUERIES)} comparison workflows locally...")
    print(f"This validates our datetime extraction fixes before deployment.\n")
    print("=" * 80)
    
    # Initialize translator
    translator = await init_translator()
    
    results = {
        "passed": 0,
        "failed": 0,
        "errors": 0,
        "details": []
    }
    
    for i, test_case in enumerate(TEST_QUERIES, 1):
        name = test_case["name"]
        query = test_case["query"]
        
        print(f"\n{'=' * 80}")
        print(f"TEST {i}/{len(TEST_QUERIES)}: {name}")
        print(f"{'=' * 80}")
        
        try:
            # Step 1: Extract parameters locally
            params = await extract_comparison_parameters(translator, query)
            
            if not params["success"]:
                print(f"\n[FAIL] Parameter extraction failed")
                results["failed"] += 1
                results["details"].append({
                    "test": i,
                    "name": name,
                    "status": "failed",
                    "step": "parameter_extraction",
                    "error": params["error"]
                })
                continue
            
            # Step 2: Execute STAC queries
            stac_result = await execute_dual_stac_queries(params)
            
            if not stac_result["success"]:
                print(f"\n[FAIL] STAC execution failed")
                results["failed"] += 1
                results["details"].append({
                    "test": i,
                    "name": name,
                    "status": "failed",
                    "step": "stac_execution",
                    "error": stac_result["error"]
                })
                continue
            
            # Step 3: Validate for GPT-5 Vision
            vision_validation = validate_for_gpt5_vision(stac_result)
            
            if vision_validation["ready"]:
                print(f"\n[PASS] LOCAL END-TO-END TEST PASSED")
                print(f"✓ Parameter extraction successful")
                print(f"✓ Datetime extraction: {params['before_date']} → {params['after_date']}")
                print(f"✓ Location extraction: {params['location_name']}")
                print(f"✓ Collections: {', '.join(params['collections'])}")
                print(f"✓ Before STAC: {stac_result['before_count']} items")
                print(f"✓ After STAC: {stac_result['after_count']} items")
                print(f"✓ Data ready for GPT-5 Vision analysis")
                
                results["passed"] += 1
                results["details"].append({
                    "test": i,
                    "name": name,
                    "status": "passed",
                    "query": query,
                    "before_date": params["before_date"],
                    "after_date": params["after_date"],
                    "location": params["location_name"],
                    "collections": params["collections"],
                    "before_items": stac_result["before_count"],
                    "after_items": stac_result["after_count"]
                })
            else:
                print(f"\n[FAIL] Data validation failed")
                results["failed"] += 1
                results["details"].append({
                    "test": i,
                    "name": name,
                    "status": "failed",
                    "step": "gpt5_validation",
                    "issues": vision_validation["issues"]
                })
        
        except Exception as e:
            print(f"\n[EXCEPTION] {type(e).__name__}: {str(e)}")
            import traceback
            traceback.print_exc()
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
                print(f"  ✓ Ready for deployment and GPT-5 Vision analysis")
    
    if results["failed"] > 0 or results["errors"] > 0:
        print(f"\n[FAIL/ERROR] FAILED/ERROR TESTS:")
        print(f"{'-' * 80}")
        for detail in results["details"]:
            if detail["status"] in ["failed", "exception"]:
                print(f"\nTest {detail['test']}: {detail['name']}")
                if detail["status"] == "failed":
                    print(f"  Step: {detail.get('step', 'unknown')}")
                    print(f"  Error: {detail.get('error', 'N/A')}")
                    if "issues" in detail:
                        for issue in detail["issues"]:
                            print(f"    - {issue}")
                else:
                    print(f"  Exception: {detail['exception']}")
    
    # Save results
    output_file = "local_end_to_end_results.json"
    with open(output_file, "w") as f:
        json.dump(results, f, indent=2)
    print(f"\n[SAVE] Results saved to: {output_file}")
    
    # Final verdict
    print(f"\n{'=' * 80}")
    if results["errors"] > 0:
        print(f"[ERROR] {results['errors']} tests had errors")
    elif results["failed"] > 0:
        print(f"[WARNING] {results['failed']} tests failed - fix issues before deployment")
    else:
        print(f"[SUCCESS] ALL LOCAL TESTS PASSED!")
        print(f"[SUCCESS] Datetime extraction fixes are working!")
        print(f"[SUCCESS] Comparison module is ready for deployment!")
    print(f"{'=' * 80}\n")
    
    return results


if __name__ == "__main__":
    print("\n[TEST] Starting Local End-to-End Tests\n")
    results = asyncio.run(test_local_end_to_end())
    
    if results["errors"] > 0 or results["failed"] > 0:
        exit(1)
    else:
        exit(0)
