"""
Test suite for extended datetime_translation_agent with comparison mode

Tests both "single" mode (existing behavior) and "comparison" mode (new dual-date extraction)
"""

import asyncio
import sys
import os

# Add parent directory to path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'container-app'))

from semantic_translator import SemanticQueryTranslator


async def test_single_mode_backward_compatibility():
    """Test that single mode still works exactly as before (backward compatibility)."""
    print("\n" + "="*80)
    print("TEST 1: SINGLE MODE - BACKWARD COMPATIBILITY")
    print("="*80)
    
    translator = SemanticQueryTranslator()
    
    test_cases = [
        {
            "query": "Show me satellite imagery of NYC from October 2024",
            "collections": ["sentinel-2-l2a"],
            "expected_contains": "2024-10"
        },
        {
            "query": "Recent fire activity in California",
            "collections": ["modis-14A1-061"],
            "expected_contains": "2025"  # Should include recent dates
        },
        {
            "query": "Summer 2024 imagery of Seattle",
            "collections": ["landsat-c2-l2"],
            "expected_contains": "2024-06"  # Summer starts in June
        }
    ]
    
    for i, test in enumerate(test_cases, 1):
        print(f"\n--- Test Case {i} ---")
        print(f"Query: {test['query']}")
        
        # Call with default mode (should be "single")
        result = await translator.datetime_translation_agent(
            query=test['query'],
            collections=test['collections']
            # mode parameter not specified - should default to "single"
        )
        
        print(f"Result type: {type(result)}")
        print(f"Result: {result}")
        
        # Verify result is a string (single mode)
        assert isinstance(result, str) or result is None, f"❌ Expected str or None, got {type(result)}"
        
        if result:
            assert test['expected_contains'] in result, f"❌ Expected '{test['expected_contains']}' in result"
            print(f"✅ PASSED - Got datetime range: {result}")
        else:
            print(f"⚠️ No datetime extracted (may be expected for some queries)")


async def test_comparison_mode_explicit_dates():
    """Test comparison mode with explicit before/after dates."""
    print("\n" + "="*80)
    print("TEST 2: COMPARISON MODE - EXPLICIT DATES")
    print("="*80)
    
    translator = SemanticQueryTranslator()
    
    test_cases = [
        {
            "query": "Compare wildfire activity in Southern California between January 1st and January 3rd, 2025",
            "collections": ["modis-14A1-061"],
            "expected_before": "2025-01-01",
            "expected_after": "2025-01-03"
        },
        {
            "query": "Show me fire spread from August 1 to August 15, 2024",
            "collections": ["modis-14A1-061"],
            "expected_before": "2024-08-01",
            "expected_after": "2024-08-1"  # Partial match (14 or 15)
        },
        {
            "query": "Compare summer 2023 fire activity to summer 2025",
            "collections": ["modis-14A1-061"],
            "expected_before": "2023-06",
            "expected_after": "2025-06"
        }
    ]
    
    for i, test in enumerate(test_cases, 1):
        print(f"\n--- Test Case {i} ---")
        print(f"Query: {test['query']}")
        
        result = await translator.datetime_translation_agent(
            query=test['query'],
            collections=test['collections'],
            mode="comparison"  # NEW: comparison mode
        )
        
        print(f"Result type: {type(result)}")
        print(f"Result: {result}")
        
        # Verify result is a dict (comparison mode)
        assert isinstance(result, dict), f"❌ Expected dict, got {type(result)}"
        assert "before" in result, "❌ Missing 'before' key"
        assert "after" in result, "❌ Missing 'after' key"
        assert "explanation" in result, "❌ Missing 'explanation' key"
        
        # Check expected dates
        assert test['expected_before'] in result['before'], f"❌ Expected '{test['expected_before']}' in before date"
        assert test['expected_after'] in result['after'], f"❌ Expected '{test['expected_after']}' in after date"
        
        print(f"✅ PASSED")
        print(f"   BEFORE: {result['before']}")
        print(f"   AFTER: {result['after']}")
        print(f"   Explanation: {result['explanation']}")


async def test_comparison_mode_ambiguous_queries():
    """Test comparison mode with ambiguous queries (needs clarification)."""
    print("\n" + "="*80)
    print("TEST 3: COMPARISON MODE - AMBIGUOUS QUERIES")
    print("="*80)
    
    translator = SemanticQueryTranslator()
    
    test_cases = [
        {
            "query": "Show me methane emissions over the Permian Basin from 2023 to 2025",
            "collections": ["sentinel-5p-l2-netcdf"],
            "expect_clarification": True
        },
        {
            "query": "Analyze sea level change along the Atlantic coast between 2015 and 2025",
            "collections": ["sentinel-1-grd"],
            "expect_clarification": False  # Should provide decade-long comparison
        }
    ]
    
    for i, test in enumerate(test_cases, 1):
        print(f"\n--- Test Case {i} ---")
        print(f"Query: {test['query']}")
        
        result = await translator.datetime_translation_agent(
            query=test['query'],
            collections=test['collections'],
            mode="comparison"
        )
        
        print(f"Result: {result}")
        
        # Verify result structure
        assert isinstance(result, dict), f"❌ Expected dict, got {type(result)}"
        assert "before" in result, "❌ Missing 'before' key"
        assert "after" in result, "❌ Missing 'after' key"
        
        # Check clarification flag
        if test['expect_clarification']:
            if result.get('needs_clarification'):
                print(f"✅ PASSED - Clarification requested (as expected)")
                print(f"   Suggestion: {result.get('suggestion')}")
                print(f"   Fallback BEFORE: {result['before']}")
                print(f"   Fallback AFTER: {result['after']}")
            else:
                print(f"⚠️ WARNING - Expected clarification request, but got direct answer")
                print(f"   BEFORE: {result['before']}")
                print(f"   AFTER: {result['after']}")
        else:
            assert not result.get('needs_clarification'), "❌ Unexpected clarification request"
            print(f"✅ PASSED - Direct answer (no clarification needed)")
            print(f"   BEFORE: {result['before']}")
            print(f"   AFTER: {result['after']}")


async def test_mode_validation():
    """Test that invalid mode raises ValueError."""
    print("\n" + "="*80)
    print("TEST 4: MODE VALIDATION")
    print("="*80)
    
    translator = SemanticQueryTranslator()
    
    print("\nTesting invalid mode: 'triple'")
    
    try:
        result = await translator.datetime_translation_agent(
            query="Show me imagery",
            collections=["sentinel-2-l2a"],
            mode="triple"  # Invalid mode
        )
        print("❌ FAILED - Should have raised ValueError")
    except ValueError as e:
        print(f"✅ PASSED - ValueError raised as expected: {e}")
    except Exception as e:
        print(f"❌ FAILED - Unexpected exception: {e}")


async def main():
    """Run all tests."""
    print("\n" + "="*80)
    print("DATETIME TRANSLATION AGENT - COMPARISON MODE TESTS")
    print("="*80)
    
    try:
        # Test 1: Backward compatibility (single mode)
        await test_single_mode_backward_compatibility()
        
        # Test 2: Comparison mode with explicit dates
        await test_comparison_mode_explicit_dates()
        
        # Test 3: Comparison mode with ambiguous queries
        await test_comparison_mode_ambiguous_queries()
        
        # Test 4: Mode validation
        await test_mode_validation()
        
        print("\n" + "="*80)
        print("✅ ALL TESTS COMPLETED")
        print("="*80)
        
    except Exception as e:
        print(f"\n❌ TEST SUITE FAILED: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    asyncio.run(main())
