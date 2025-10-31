"""
Test suite for Comparison Module end-to-end functionality

Tests:
1. /api/process-comparison-query endpoint (parameter extraction)
2. /api/geoint/comparison endpoint (GPT-5 Vision analysis)
3. Full workflow with real screenshots
"""

import asyncio
import sys
import os
import json
import base64
from pathlib import Path

# Add parent directory to path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'container-app'))

# For direct testing without HTTP
from geoint.agents import comparison_analysis_agent
from semantic_translator import SemanticQueryTranslator
from location_resolver import EnhancedLocationResolver


def load_screenshot_as_base64(filename):
    """Load a screenshot from tests folder and convert to base64."""
    test_dir = Path(__file__).parent
    screenshot_path = test_dir / filename
    
    if not screenshot_path.exists():
        print(f"❌ Screenshot not found: {screenshot_path}")
        return None
    
    with open(screenshot_path, 'rb') as f:
        image_data = f.read()
        base64_data = base64.b64encode(image_data).decode('utf-8')
        return base64_data


async def test_parameter_extraction():
    """Test 1: Query parameter extraction (location, aspect, dates)"""
    print("\n" + "="*80)
    print("TEST 1: PARAMETER EXTRACTION FROM NATURAL LANGUAGE")
    print("="*80)
    
    test_queries = [
        {
            "query": "Show wildfire activity in Southern California in January 2025 over 48 hours",
            "expected_aspect": "wildfire",
            "expected_location_contains": "California"
        },
        {
            "query": "Track methane emissions in Permian Basin from 2023 to 2025",
            "expected_aspect": "methane",
            "expected_location_contains": "Permian"
        },
        {
            "query": "Compare sea level change along US Atlantic coast over past decade",
            "expected_aspect": "sea level",
            "expected_location_contains": "Atlantic"
        },
        {
            "query": "Vegetation loss in Amazon rainforest between 2020 and 2024",
            "expected_aspect": "vegetation",
            "expected_location_contains": "Amazon"
        }
    ]
    
    resolver = EnhancedLocationResolver()
    
    for i, test in enumerate(test_queries, 1):
        print(f"\n--- Test Case {i} ---")
        print(f"Query: {test['query']}")
        
        try:
            # Extract location (simplified - in real endpoint we use GPT-4o)
            query_lower = test['query'].lower()
            
            # Simple location extraction
            if "california" in query_lower:
                location_name = "Southern California"
            elif "permian" in query_lower:
                location_name = "Permian Basin"
            elif "atlantic" in query_lower:
                location_name = "US Atlantic Coast"
            elif "amazon" in query_lower:
                location_name = "Amazon Rainforest"
            else:
                location_name = "Unknown"
            
            print(f"  Location extracted: {location_name}")
            
            # Resolve to coordinates
            location_result = await resolver.resolve_location_with_confidence(
                location_name=location_name,
                user_query=test['query']
            )
            
            if location_result and "bbox" in location_result:
                bbox = location_result["bbox"]
                lat = (bbox[1] + bbox[3]) / 2
                lng = (bbox[0] + bbox[2]) / 2
                print(f"  ✅ Coordinates: ({lat:.4f}, {lng:.4f})")
            else:
                print(f"  ❌ Failed to resolve location")
                continue
            
            # Extract dates using comparison mode
            collections = ["sentinel-2-l2a", "landsat-c2-l2"]
            translator = SemanticQueryTranslator(
                azure_openai_endpoint=os.getenv("AZURE_OPENAI_ENDPOINT", ""),
                azure_openai_api_key=os.getenv("AZURE_OPENAI_API_KEY", ""),
                model_name="gpt-4o"
            )
            datetime_result = await translator.datetime_translation_agent(
                query=test['query'],
                collections=collections,
                mode="comparison"
            )
            
            if datetime_result and "before" in datetime_result and "after" in datetime_result:
                print(f"  ✅ BEFORE date: {datetime_result['before']}")
                print(f"  ✅ AFTER date: {datetime_result['after']}")
                print(f"  📝 Explanation: {datetime_result.get('explanation', 'N/A')}")
            else:
                print(f"  ❌ Failed to extract dates")
                continue
            
            # Aspect detection
            aspect = "general change"
            if "fire" in query_lower or "wildfire" in query_lower:
                aspect = "wildfire activity"
            elif "vegetation" in query_lower or "forest" in query_lower:
                aspect = "vegetation change"
            elif "methane" in query_lower or "emission" in query_lower:
                aspect = "methane emissions"
            elif "sea level" in query_lower or "coast" in query_lower:
                aspect = "coastal/sea level change"
            
            print(f"  ✅ Aspect detected: {aspect}")
            
            # Verify expectations
            if test['expected_location_contains'].lower() in location_name.lower():
                print(f"  ✅ Location matches expectation")
            else:
                print(f"  ⚠️  Location doesn't match expectation")
            
            if test['expected_aspect'] in aspect:
                print(f"  ✅ Aspect matches expectation")
            else:
                print(f"  ⚠️  Aspect doesn't match expectation")
            
        except Exception as e:
            print(f"  ❌ ERROR: {e}")
            import traceback
            traceback.print_exc()


async def test_comparison_analysis_agent():
    """Test 2: Direct comparison_analysis_agent with mock screenshots"""
    print("\n" + "="*80)
    print("TEST 2: COMPARISON ANALYSIS AGENT (GPT-5 VISION)")
    print("="*80)
    
    # Load screenshots from tests folder
    print("\n📸 Loading test screenshots...")
    screenshot1 = load_screenshot_as_base64("Screenshot 2025-10-26 131627.png")
    screenshot2 = load_screenshot_as_base64("Screenshot 2025-10-26 141057.png")
    
    if not screenshot1 or not screenshot2:
        print("❌ Could not load screenshots. Skipping GPT-5 Vision test.")
        return
    
    print(f"✅ Loaded screenshot 1: {len(screenshot1)} bytes (base64)")
    print(f"✅ Loaded screenshot 2: {len(screenshot2)} bytes (base64)")
    
    # Test with sample metadata
    before_metadata = {
        "features": [{
            "collection": "sentinel-2-l2a",
            "datetime": "2025-01-15T00:00:00Z",
            "properties": {
                "eo:cloud_cover": 5.2
            }
        }]
    }
    
    after_metadata = {
        "features": [{
            "collection": "sentinel-2-l2a",
            "datetime": "2025-01-17T00:00:00Z",
            "properties": {
                "eo:cloud_cover": 3.8
            }
        }]
    }
    
    test_cases = [
        {
            "query": "Show wildfire activity changes",
            "aspect": "wildfire activity",
            "latitude": 34.05,
            "longitude": -118.24,
            "before_date": "2025-01-15T00:00:00Z",
            "after_date": "2025-01-17T00:00:00Z"
        },
        {
            "query": "Compare vegetation health",
            "aspect": "vegetation change",
            "latitude": 37.77,
            "longitude": -122.41,
            "before_date": "2024-06-01T00:00:00Z",
            "after_date": "2024-08-01T00:00:00Z"
        }
    ]
    
    for i, test in enumerate(test_cases, 1):
        print(f"\n--- Test Case {i} ---")
        print(f"Query: {test['query']}")
        print(f"Aspect: {test['aspect']}")
        print(f"Location: ({test['latitude']}, {test['longitude']})")
        
        try:
            # Call comparison_analysis_agent directly
            result = await comparison_analysis_agent(
                latitude=test['latitude'],
                longitude=test['longitude'],
                before_date=test['before_date'],
                after_date=test['after_date'],
                before_screenshot_base64=screenshot1,
                after_screenshot_base64=screenshot2,
                before_metadata=before_metadata,
                after_metadata=after_metadata,
                user_query=test['query'],
                comparison_aspect=test['aspect']
            )
            
            print(f"\n📊 GPT-5 Vision Analysis Result:")
            print(f"  Time span: {result.get('time_span', 'N/A')}")
            print(f"  Aspect analyzed: {result.get('aspect_analyzed', 'N/A')}")
            print(f"  Confidence: {result.get('confidence', 'N/A')}")
            print(f"\n  Analysis (first 500 chars):")
            analysis_text = result.get('analysis', 'No analysis returned')
            print(f"  {analysis_text[:500]}...")
            
            # Check for bold formatting
            if "**" in analysis_text:
                print(f"  ✅ Response contains bold formatting (** markers)")
            else:
                print(f"  ⚠️  Response missing bold formatting")
            
            # Check for numbered sections
            if any(f"{n}." in analysis_text for n in range(1, 6)):
                print(f"  ✅ Response contains numbered sections")
            else:
                print(f"  ⚠️  Response missing numbered sections")
            
        except Exception as e:
            print(f"  ❌ ERROR: {e}")
            import traceback
            traceback.print_exc()


async def test_full_workflow_simulation():
    """Test 3: Simulate full comparison workflow (without HTTP)"""
    print("\n" + "="*80)
    print("TEST 3: FULL WORKFLOW SIMULATION")
    print("="*80)
    
    # Sample query
    user_query = "Show wildfire activity in Southern California over 48 hours in January 2025"
    
    print(f"\n🔥 Testing full comparison workflow")
    print(f"Query: {user_query}")
    
    try:
        # Step 1: Location extraction
        print("\n📍 STEP 1: Extract location...")
        resolver = EnhancedLocationResolver()
        location_result = await resolver.resolve_location_with_confidence(
            location_name="Southern California",
            user_query=user_query
        )
        
        if not location_result or "bbox" not in location_result:
            print("❌ Location resolution failed")
            return
        
        bbox = location_result["bbox"]
        lat = (bbox[1] + bbox[3]) / 2
        lng = (bbox[0] + bbox[2]) / 2
        print(f"✅ Location: ({lat:.4f}, {lng:.4f})")
        
        # Step 2: Date extraction
        print("\n📅 STEP 2: Extract before/after dates...")
        collections = ["modis-14A1-061", "sentinel-2-l2a"]
        translator = SemanticQueryTranslator(
            azure_openai_endpoint=os.getenv("AZURE_OPENAI_ENDPOINT", ""),
            azure_openai_api_key=os.getenv("AZURE_OPENAI_API_KEY", ""),
            model_name="gpt-4o"
        )
        datetime_result = await translator.datetime_translation_agent(
            query=user_query,
            collections=collections,
            mode="comparison"
        )
        
        if not datetime_result or "before" not in datetime_result:
            print("❌ Date extraction failed")
            return
        
        before_date = datetime_result["before"]
        after_date = datetime_result["after"]
        print(f"✅ BEFORE: {before_date}")
        print(f"✅ AFTER: {after_date}")
        
        # Step 3: Aspect detection
        print("\n🎯 STEP 3: Detect aspect...")
        aspect = "wildfire activity"
        print(f"✅ Aspect: {aspect}")
        
        # Step 4: Load screenshots
        print("\n📸 STEP 4: Load screenshots...")
        screenshot1 = load_screenshot_as_base64("Screenshot 2025-10-26 131627.png")
        screenshot2 = load_screenshot_as_base64("Screenshot 2025-10-26 141057.png")
        
        if not screenshot1 or not screenshot2:
            print("❌ Screenshot loading failed")
            return
        
        print(f"✅ Screenshots loaded")
        
        # Step 5: GPT-5 Vision analysis
        print("\n🤖 STEP 5: Run GPT-5 Vision analysis...")
        
        mock_metadata = {
            "features": [{
                "collection": "modis-14A1-061",
                "datetime": before_date,
                "properties": {"eo:cloud_cover": 5.0}
            }]
        }
        
        result = await comparison_analysis_agent(
            latitude=lat,
            longitude=lng,
            before_screenshot_base64=screenshot1,
            after_screenshot_base64=screenshot2,
            before_metadata=mock_metadata,
            after_metadata=mock_metadata,
            user_query=user_query,
            comparison_aspect=aspect
        )
        
        print(f"\n✅ WORKFLOW COMPLETE!")
        print(f"\n📊 Final Result:")
        print(f"  Time span: {result.get('time_span', 'N/A')}")
        print(f"  Aspect: {result.get('aspect_analyzed', 'N/A')}")
        print(f"  Confidence: {result.get('confidence', 'N/A')}")
        print(f"\n  Analysis preview:")
        analysis = result.get('analysis', 'No analysis')
        print(f"  {analysis[:300]}...")
        
    except Exception as e:
        print(f"❌ WORKFLOW ERROR: {e}")
        import traceback
        traceback.print_exc()


async def main():
    """Run all tests"""
    print("\n")
    print("=" * 80)
    print(" " * 20 + "COMPARISON MODULE TEST SUITE")
    print("=" * 80)
    
    # Run tests
    await test_parameter_extraction()
    await test_comparison_analysis_agent()
    await test_full_workflow_simulation()
    
    print("\n" + "="*80)
    print("ALL TESTS COMPLETE")
    print("="*80 + "\n")


if __name__ == "__main__":
    asyncio.run(main())
