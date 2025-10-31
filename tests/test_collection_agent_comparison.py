"""
Test suite for collection_mapping_agent integration with comparison queries

This test validates that the collection agent:
1. Correctly identifies appropriate collections for comparison queries
2. Avoids static collections (DEMs) which don't support temporal filtering
3. Selects collections that support temporal comparisons
4. Handles different query types (wildfire, flood, urban change, etc.)
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
from semantic_translator import SemanticQueryTranslator

# Initialize the semantic translator
semantic_translator = None

# Static collections that should NOT be used for temporal comparisons
STATIC_COLLECTIONS = [
    "cop-dem-glo-30",
    "cop-dem-glo-90", 
    "nasadem",
    "alos-dem",
    "3dep-seamless"
]

# Test cases with expected collection characteristics
TEST_QUERIES = [
    {
        "query": "Compare wildfire activity in California between 2023 and 2024",
        "expected_type": "thermal/fire",
        "should_contain": ["modis", "viirs"],  # Thermal anomaly collections
        "should_not_contain": STATIC_COLLECTIONS,
        "description": "Wildfire comparison should use thermal/fire detection collections"
    },
    {
        "query": "Show flood extent changes in Houston from 2023 to 2024",
        "expected_type": "SAR/optical",
        "should_contain": ["sentinel-1", "sentinel-2"],
        "should_not_contain": STATIC_COLLECTIONS,
        "description": "Flood comparison should use SAR or optical collections"
    },
    {
        "query": "Compare urban development in NYC between January 2023 and January 2024",
        "expected_type": "optical",
        "should_contain": ["sentinel-2", "landsat"],
        "should_not_contain": STATIC_COLLECTIONS,
        "description": "Urban change should use high-resolution optical imagery"
    },
    {
        "query": "Analyze vegetation changes in Amazon from 2022 to 2023",
        "expected_type": "optical/NDVI",
        "should_contain": ["sentinel-2", "landsat", "modis"],
        "should_not_contain": STATIC_COLLECTIONS,
        "description": "Vegetation analysis should use optical/NDVI capable collections"
    },
    {
        "query": "Compare snow cover in Colorado between winter 2023 and winter 2024",
        "expected_type": "optical",
        "should_contain": ["sentinel-2", "landsat"],
        "should_not_contain": STATIC_COLLECTIONS,
        "description": "Snow cover should use optical collections with good temporal resolution"
    },
    {
        "query": "Show coastal erosion changes in Miami from 2020 to 2024",
        "expected_type": "optical/SAR",
        "should_contain": ["sentinel-1", "sentinel-2", "landsat"],
        "should_not_contain": STATIC_COLLECTIONS,
        "description": "Coastal change should use high-resolution imagery"
    },
    {
        "query": "Compare satellite data in Los Angeles from 2023 to 2024",
        "expected_type": "optical",
        "should_contain": ["sentinel-2", "landsat"],  # General query = general collections
        "should_not_contain": STATIC_COLLECTIONS,
        "description": "General comparison should use primary optical collections"
    },
    {
        "query": "Analyze deforestation in Brazil between 2022 and 2023",
        "expected_type": "optical/NDVI",
        "should_contain": ["sentinel-2", "landsat"],
        "should_not_contain": STATIC_COLLECTIONS,
        "description": "Deforestation should use optical collections for vegetation analysis"
    }
]


async def init_translator():
    """Initialize SemanticQueryTranslator with Azure OpenAI credentials"""
    global semantic_translator
    
    # Get API credentials from environment
    azure_openai_endpoint = os.getenv("AZURE_OPENAI_ENDPOINT")
    azure_openai_api_key = os.getenv("AZURE_OPENAI_API_KEY")
    model_name = os.getenv("AZURE_OPENAI_GPT4_DEPLOYMENT_NAME", "gpt-4o")
    
    if not azure_openai_endpoint or not azure_openai_api_key:
        raise ValueError("Missing AZURE_OPENAI_ENDPOINT or AZURE_OPENAI_API_KEY environment variables")
    
    print(f"[OK] Initializing with model: {model_name}")
    
    # Disable logging output to console to avoid Unicode encoding issues
    import logging
    logging.getLogger().handlers = []
    
    semantic_translator = SemanticQueryTranslator(
        azure_openai_endpoint=azure_openai_endpoint,
        azure_openai_api_key=azure_openai_api_key,
        model_name=model_name
    )
    print(f"[OK] Semantic translator initialized")
    return semantic_translator


def validate_collections(collections, test_case):
    """
    Validate that collections meet the test case requirements
    
    Returns: (passed, issues)
    """
    issues = []
    
    # Check if any collections were returned
    if not collections:
        issues.append("No collections returned")
        return False, issues
    
    # Check for static collections (should NOT be present)
    found_static = [c for c in collections if c in test_case["should_not_contain"]]
    if found_static:
        issues.append(f"Found static collections that don't support temporal filtering: {found_static}")
    
    # Check for expected collection types
    found_expected = False
    for expected_keyword in test_case["should_contain"]:
        # Check if any collection contains the expected keyword
        if any(expected_keyword.lower() in c.lower() for c in collections):
            found_expected = True
            break
    
    if not found_expected:
        issues.append(f"No collections found matching expected types: {test_case['should_contain']}")
    
    # Overall pass/fail
    passed = len(issues) == 0
    
    return passed, issues


async def test_collection_agent():
    """Test collection agent with comparison queries"""
    
    # Initialize translator first
    translator = await init_translator()
    
    print("=" * 80)
    print("COLLECTION AGENT TEST - COMPARISON MODE")
    print("=" * 80)
    print(f"\nTesting {len(TEST_QUERIES)} comparison queries...\n")
    
    results = {
        "passed": 0,
        "failed": 0,
        "errors": 0,
        "details": []
    }
    
    for i, test_case in enumerate(TEST_QUERIES, 1):
        query = test_case["query"]
        
        print(f"\n{'=' * 80}")
        print(f"TEST {i}/{len(TEST_QUERIES)}")
        print(f"{'=' * 80}")
        print(f"Query: {query}")
        print(f"Expected: {test_case['expected_type']}")
        print(f"Should contain: {test_case['should_contain']}")
        print(f"{'-' * 80}")
        
        try:
            # Call the collection_mapping_agent
            collections = await translator.collection_mapping_agent(query)
            
            print(f"\n[OK] Agent Response:")
            print(f"Collections: {collections}")
            print(f"Count: {len(collections) if collections else 0}")
            
            # Validate results
            passed, issues = validate_collections(collections, test_case)
            
            if passed:
                print(f"\n[PASS] TEST PASSED")
                results["passed"] += 1
                results["details"].append({
                    "test": i,
                    "query": query,
                    "status": "passed",
                    "collections": collections,
                    "description": test_case["description"]
                })
            else:
                print(f"\n[FAIL] TEST FAILED")
                for issue in issues:
                    print(f"   - {issue}")
                results["failed"] += 1
                results["details"].append({
                    "test": i,
                    "query": query,
                    "status": "failed",
                    "collections": collections,
                    "issues": issues,
                    "description": test_case["description"]
                })
            
        except Exception as e:
            print(f"\n[EXCEPTION] {type(e).__name__}: {str(e)}")
            results["errors"] += 1
            results["details"].append({
                "test": i,
                "query": query,
                "status": "exception",
                "exception": str(e),
                "description": test_case["description"]
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
    
    # Print failed/error cases
    if results["failed"] > 0 or results["errors"] > 0:
        print(f"\n[FAIL/ERROR] FAILED/ERROR CASES:")
        print(f"{'-' * 80}")
        for detail in results["details"]:
            if detail["status"] in ["failed", "exception"]:
                print(f"\nTest {detail['test']}: {detail['query']}")
                if detail["status"] == "failed":
                    print(f"  Collections: {detail['collections']}")
                    print(f"  Issues:")
                    for issue in detail["issues"]:
                        print(f"    - {issue}")
                else:
                    print(f"  Exception: {detail['exception']}")
    
    # Print passed cases
    if results["passed"] > 0:
        print(f"\n[PASS] PASSED CASES:")
        print(f"{'-' * 80}")
        for detail in results["details"]:
            if detail["status"] == "passed":
                print(f"\nTest {detail['test']}: {detail['query']}")
                print(f"  Collections: {detail['collections']}")
                print(f"  ✓ {detail['description']}")
    
    # Save results to JSON
    output_file = "collection_agent_test_results.json"
    with open(output_file, "w") as f:
        json.dump(results, f, indent=2)
    print(f"\n[SAVE] Detailed results saved to: {output_file}")
    
    # Final verdict
    print(f"\n{'=' * 80}")
    if results["errors"] > 0:
        print(f"[ERROR] {results['errors']} tests had errors - agent may need fixes")
    elif results["failed"] > 0:
        print(f"[WARNING] {results['failed']} tests failed - review collection selection logic")
    else:
        print(f"[SUCCESS] ALL TESTS PASSED! Collection agent is ready for comparison queries")
    print(f"{'=' * 80}\n")
    
    return results


if __name__ == "__main__":
    print("\n[TEST] Starting Collection Agent Tests for Comparison Mode\n")
    results = asyncio.run(test_collection_agent())
    
    # Exit with appropriate code
    if results["errors"] > 0 or results["failed"] > 0:
        exit(1)
    else:
        exit(0)
