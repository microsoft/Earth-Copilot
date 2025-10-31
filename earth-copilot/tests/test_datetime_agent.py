"""
Test script for datetime_translation_agent in comparison mode
Tests extraction of before/after dates from diverse natural language queries
"""

import sys
import os

# Set UTF-8 encoding for Windows console output to handle emoji in logs
if sys.platform == 'win32':
    import codecs
    sys.stdout = codecs.getwriter('utf-8')(sys.stdout.buffer, 'strict')
    sys.stderr = codecs.getwriter('utf-8')(sys.stderr.buffer, 'strict')

import asyncio
import json
from datetime import datetime
from semantic_translator import SemanticQueryTranslator

# Initialize the semantic translator
semantic_translator = None

async def init_translator():
    """Initialize the semantic translator with API credentials"""
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

# Test cases with diverse query formats
TEST_QUERIES = [
    # Basic "between...and..." format
    {
        "query": "Compare NYC satellite data between January 2023 and January 2024",
        "expected_before": "2023-01",
        "expected_after": "2024-01"
    },
    {
        "query": "Show changes between March 2022 and March 2023",
        "expected_before": "2022-03",
        "expected_after": "2023-03"
    },
    
    # "from...to..." format
    {
        "query": "Compare imagery from January 2023 to December 2023",
        "expected_before": "2023-01",
        "expected_after": "2023-12"
    },
    {
        "query": "Show me changes from 2022 to 2023",
        "expected_before": "2022",
        "expected_after": "2023"
    },
    
    # Specific date formats
    {
        "query": "Compare data from 2023-01-15 to 2024-01-15",
        "expected_before": "2023-01-15",
        "expected_after": "2024-01-15"
    },
    {
        "query": "Show changes from Jan 1, 2023 to Jan 1, 2024",
        "expected_before": "2023-01-01",
        "expected_after": "2024-01-01"
    },
    
    # Natural language with relative dates
    {
        "query": "Compare last year to this year",
        "expected_before": "2024",  # Will be dynamic based on current date
        "expected_after": "2025"
    },
    {
        "query": "Show changes over the past year",
        "expected_before": "2024",
        "expected_after": "2025"
    },
    
    # Different phrasing
    {
        "query": "What changed between summer 2023 and winter 2023",
        "expected_before": "2023-06",  # Summer
        "expected_after": "2023-12"   # Winter
    },
    {
        "query": "Compare Q1 2023 with Q1 2024",
        "expected_before": "2023-01",
        "expected_after": "2024-01"
    },
    
    # Location-specific temporal queries
    {
        "query": "Compare New York City before and after the 2023 floods in September 2023",
        "expected_before": "2023-08",  # Before September
        "expected_after": "2023-09"    # September
    },
    
    # Edge cases - should these work?
    {
        "query": "Compare January 2023 to Juanry 2024",  # Typo
        "expected_before": "2023-01",
        "expected_after": None  # Might fail
    },
    {
        "query": "Show me before and after images",  # No dates!
        "expected_before": None,
        "expected_after": None
    },
    
    # Year-only comparisons
    {
        "query": "Compare 2020 versus 2021",
        "expected_before": "2020",
        "expected_after": "2021"
    },
    {
        "query": "Show changes in 2023 compared to 2024",
        "expected_before": "2023",
        "expected_after": "2024"
    },
    
    # Month-Year format
    {
        "query": "Compare May 2023 with May 2024",
        "expected_before": "2023-05",
        "expected_after": "2024-05"
    },
    
    # Complex temporal descriptions
    {
        "query": "Compare early 2023 to late 2023",
        "expected_before": "2023-01",
        "expected_after": "2023-12"
    },
    {
        "query": "Show the difference between beginning of 2023 and end of 2023",
        "expected_before": "2023-01",
        "expected_after": "2023-12"
    }
]


async def test_datetime_extraction():
    """Test datetime extraction for comparison queries"""
    
    # Initialize translator first
    translator = await init_translator()
    
    print("=" * 80)
    print("DATETIME TRANSLATION AGENT - COMPARISON MODE TEST")
    print("=" * 80)
    print(f"\nTesting {len(TEST_QUERIES)} queries...\n")
    
    results = {
        "passed": 0,
        "failed": 0,
        "errors": 0,
        "details": []
    }
    
    for i, test_case in enumerate(TEST_QUERIES, 1):
        query = test_case["query"]
        expected_before = test_case["expected_before"]
        expected_after = test_case["expected_after"]
        
        print(f"\n{'=' * 80}")
        print(f"TEST {i}/{len(TEST_QUERIES)}")
        print(f"{'=' * 80}")
        print(f"Query: {query}")
        print(f"Expected Before: {expected_before}")
        print(f"Expected After:  {expected_after}")
        print(f"{'-' * 80}")
        
        try:
            # Call the datetime_translation_agent in comparison mode
            # Pass collections parameter (empty list for general comparison queries)
            result = await translator.datetime_translation_agent(
                query=query,
                collections=["sentinel-2-l2a"],  # Pass a sample collection to enable temporal filtering
                mode="comparison"
            )
            
            print(f"\n[OK] Agent Response:")
            print(json.dumps(result, indent=2))
            
            # Check if it's an error response
            if "error" in result:
                print(f"\n[ERROR] {result['error']}")
                results["errors"] += 1
                results["details"].append({
                    "test": i,
                    "query": query,
                    "status": "error",
                    "error": result["error"]
                })
                continue
            
            # Extract dates from result
            actual_before = result.get("before")  # Changed from "before_date"
            actual_after = result.get("after")    # Changed from "after_date"
            
            print(f"\nActual Before: {actual_before}")
            print(f"Actual After:  {actual_after}")
            
            # Validate results
            before_match = check_date_match(expected_before, actual_before)
            after_match = check_date_match(expected_after, actual_after)
            
            if before_match and after_match:
                print(f"\n[PASS] TEST PASSED")
                results["passed"] += 1
                results["details"].append({
                    "test": i,
                    "query": query,
                    "status": "passed",
                    "before_date": actual_before,
                    "after_date": actual_after
                })
            else:
                print(f"\n[FAIL] TEST FAILED")
                if not before_match:
                    print(f"   Before date mismatch: expected {expected_before}, got {actual_before}")
                if not after_match:
                    print(f"   After date mismatch: expected {expected_after}, got {actual_after}")
                results["failed"] += 1
                results["details"].append({
                    "test": i,
                    "query": query,
                    "status": "failed",
                    "expected_before": expected_before,
                    "expected_after": expected_after,
                    "actual_before": actual_before,
                    "actual_after": actual_after
                })
        
        except Exception as e:
            print(f"\n[EXCEPTION] {type(e).__name__}: {str(e)}")
            results["errors"] += 1
            results["details"].append({
                "test": i,
                "query": query,
                "status": "exception",
                "exception": str(e)
            })
    
    # Print summary
    print("\n" + "=" * 80)
    print("TEST SUMMARY")
    print("=" * 80)
    print(f"Total Tests:  {len(TEST_QUERIES)}")
    print(f"[PASS] Passed:  {results['passed']} ({results['passed']/len(TEST_QUERIES)*100:.1f}%)")
    print(f"[FAIL] Failed:  {results['failed']} ({results['failed']/len(TEST_QUERIES)*100:.1f}%)")
    print(f"[ERR]  Errors:  {results['errors']} ({results['errors']/len(TEST_QUERIES)*100:.1f}%)")
    print("=" * 80)
    
    # Show failed/error cases
    if results["failed"] > 0 or results["errors"] > 0:
        print("\n[FAIL/ERROR] FAILED/ERROR CASES:")
        print("-" * 80)
        for detail in results["details"]:
            if detail["status"] in ["failed", "error", "exception"]:
                print(f"\nTest {detail['test']}: {detail['query']}")
                if detail["status"] == "failed":
                    print(f"  Expected: before={detail.get('expected_before')}, after={detail.get('expected_after')}")
                    print(f"  Actual:   before={detail.get('actual_before')}, after={detail.get('actual_after')}")
                elif detail["status"] == "error":
                    print(f"  Error: {detail.get('error')}")
                elif detail["status"] == "exception":
                    print(f"  Exception: {detail.get('exception')}")
    
    # Show passed cases
    if results["passed"] > 0:
        print("\n[PASS] PASSED CASES:")
        print("-" * 80)
        for detail in results["details"]:
            if detail["status"] == "passed":
                print(f"Test {detail['test']}: {detail['query']}")
                print(f"  Before: {detail['before_date']}")
                print(f"  After:  {detail['after_date']}")
    
    # Save results to file
    with open("datetime_agent_test_results.json", "w") as f:
        json.dump(results, f, indent=2)
    print(f"\n[SAVE] Detailed results saved to: datetime_agent_test_results.json")
    
    return results


def check_date_match(expected, actual):
    """
    Check if actual date matches expected date (flexible matching)
    Handles None values and partial date matches
    """
    if expected is None and actual is None:
        return True
    
    if expected is None or actual is None:
        return False
    
    # Convert both to strings for comparison
    expected_str = str(expected)
    actual_str = str(actual)
    
    # Check if actual starts with expected (handles partial matches)
    # e.g., expected "2023-01" matches actual "2023-01-15T00:00:00Z"
    return actual_str.startswith(expected_str)


if __name__ == "__main__":
    print("\n[TEST] Starting Datetime Translation Agent Tests for Comparison Mode\n")
    results = asyncio.run(test_datetime_extraction())
    
    print("\n" + "=" * 80)
    if results["passed"] == len(TEST_QUERIES):
        print("[SUCCESS] ALL TESTS PASSED!")
    elif results["errors"] == 0:
        print(f"[WARNING] {results['passed']}/{len(TEST_QUERIES)} tests passed")
    else:
        print(f"[ERROR] {results['errors']} tests had errors - agent may need fixes")
    print("=" * 80)
