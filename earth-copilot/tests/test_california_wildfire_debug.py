"""
Quick standalone test for semantic translator - diagnose the California wildfire issue
Run this to quickly test the specific problem we identified
"""

import asyncio
import json
import sys
import os
from datetime import datetime

# Add the router function app to the path
sys.path.append(os.path.join(os.path.dirname(__file__), '..', 'router_function_app'))

from semantic_translator import SemanticQueryTranslator

# Configuration - update these with your actual values
AZURE_OPENAI_ENDPOINT = os.getenv("AZURE_OPENAI_ENDPOINT", "your-endpoint-here")
AZURE_OPENAI_API_KEY = os.getenv("AZURE_OPENAI_API_KEY", "your-key-here")
MODEL_NAME = os.getenv("AZURE_OPENAI_MODEL", "gpt-5")

async def test_california_wildfire_issue():
    """Test the specific California wildfire query that was returning Arctic results"""
    
    print("=== TESTING CALIFORNIA WILDFIRE ISSUE ===\n")
    
    try:
        # Initialize translator
        print("Initializing Semantic Translator...")
        translator = SemanticQueryTranslator(
            azure_openai_endpoint=AZURE_OPENAI_ENDPOINT,
            azure_openai_api_key=AZURE_OPENAI_API_KEY,
            model_name=MODEL_NAME
        )
        print("✓ Translator initialized successfully\n")
        
        # Test the problematic query
        test_query = "Show me wildfire damage assessment in California from September 2023"
        print(f"Testing query: '{test_query}'\n")
        
        # Step 1: Test entity extraction
        print("STEP 1: Entity Extraction")
        print("-" * 40)
        entities = await translator.extract_entities(test_query)
        print(f"Raw entities: {json.dumps(entities, indent=2)}")
        
        # Validate location extraction
        location = entities.get("location", {})
        location_name = location.get("name")
        print(f"\nExtracted location: {location_name}")
        print(f"Location type: {location.get('type')}")
        print(f"Location confidence: {location.get('confidence')}")
        
        if location_name != "California":
            print(f"❌ ISSUE: Expected 'California', got '{location_name}'")
            return False
        else:
            print("✓ Location extraction correct")
        
        # Step 2: Test bbox resolution
        print(f"\nSTEP 2: Bbox Resolution for '{location_name}'")
        print("-" * 40)
        
        if location_name:
            bbox = await translator.resolve_location_to_bbox(location_name)
            print(f"Resolved bbox: {bbox}")
            
            # California should be approximately [-124.7, 32.5, -114.1, 42.0]
            expected_bbox = [-124.7, 32.5, -114.1, 42.0]
            
            if bbox and len(bbox) == 4:
                print(f"Expected bbox (approx): {expected_bbox}")
                print(f"Longitude range: {bbox[0]:.2f} to {bbox[2]:.2f} (expected: -124.7 to -114.1)")
                print(f"Latitude range: {bbox[1]:.2f} to {bbox[3]:.2f} (expected: 32.5 to 42.0)")
                
                # Check if we're getting Arctic coordinates (high latitude)
                if bbox[3] > 70:  # Max latitude > 70 degrees (Arctic region)
                    print(f"❌ ISSUE: Got Arctic coordinates! Max lat: {bbox[3]}")
                    print("This explains why we got Arctic satellite data instead of California data")
                    return False
                
                # Check if coordinates are reasonable for California
                if (-130 <= bbox[0] <= -110 and 30 <= bbox[1] <= 45 and 
                    -130 <= bbox[2] <= -110 and 30 <= bbox[3] <= 45):
                    print("✓ Bbox coordinates are reasonable for California")
                else:
                    print(f"❌ ISSUE: Bbox coordinates don't match California region")
                    return False
            else:
                print(f"❌ ISSUE: Invalid bbox format: {bbox}")
                return False
        
        # Step 3: Test complete STAC query generation
        print(f"\nSTEP 3: Complete STAC Query Generation")
        print("-" * 40)
        
        stac_query = await translator.translate_query(test_query)
        print(f"Generated STAC query: {json.dumps(stac_query, indent=2)}")
        
        # Validate collections for wildfire
        collections = stac_query.get("collections", [])
        expected_wildfire_collections = ["modis-14A1-061", "modis-14A2-061", "sentinel-2-l2a", "landsat-c2-l2"]
        
        print(f"\nSelected collections: {collections}")
        print(f"Expected wildfire collections: {expected_wildfire_collections}")
        
        wildfire_collections_found = any(col in collections for col in expected_wildfire_collections[:2])  # Primary collections
        if wildfire_collections_found:
            print("✓ Appropriate wildfire collections selected")
        else:
            print(f"❌ ISSUE: No wildfire-specific collections found")
        
        # Validate final bbox in STAC query
        final_bbox = stac_query.get("bbox")
        print(f"\nFinal STAC bbox: {final_bbox}")
        
        if final_bbox and len(final_bbox) == 4:
            if final_bbox[3] > 70:  # Max latitude > 70 (Arctic)
                print(f"❌ CRITICAL ISSUE: STAC query has Arctic coordinates!")
                print(f"This is why the UI showed Arctic satellite data instead of California")
                print(f"Max latitude: {final_bbox[3]} (should be ~42 for California)")
                return False
            else:
                print("✓ STAC bbox coordinates look reasonable")
        
        # Validate datetime
        datetime_range = stac_query.get("datetime")
        print(f"Datetime range: {datetime_range}")
        
        if "2023" in str(datetime_range):
            print("✓ Correct year (2023) in datetime range")
        else:
            print(f"❌ ISSUE: Expected 2023 in datetime, got: {datetime_range}")
        
        print(f"\n{'='*50}")
        print("🎉 ALL TESTS PASSED! The semantic translator is working correctly.")
        print("If you were getting Arctic results before, the issue was likely:")
        print("1. Router function stopped/crashed during processing")
        print("2. Fallback to default/global bbox")  
        print("3. Network issues with Nominatim geocoding service")
        print(f"{'='*50}")
        
        return True
        
    except Exception as e:
        print(f"❌ ERROR: {e}")
        import traceback
        traceback.print_exc()
        return False

async def test_multiple_locations():
    """Test bbox resolution for multiple locations to verify geocoding"""
    
    print("\n=== TESTING MULTIPLE LOCATION RESOLUTIONS ===\n")
    
    try:
        translator = SemanticQueryTranslator(
            azure_openai_endpoint=AZURE_OPENAI_ENDPOINT,
            azure_openai_api_key=AZURE_OPENAI_API_KEY,
            model_name=MODEL_NAME
        )
        
        test_locations = [
            ("California", "State in western US"),
            ("Louisiana", "State in southern US"), 
            ("Houston", "City in Texas"),
            ("New York City", "City in New York state"),
            ("Turkey", "Country in Europe/Asia"),
        ]
        
        for location, description in test_locations:
            print(f"Testing: {location} ({description})")
            try:
                bbox = await translator.resolve_location_to_bbox(location)
                print(f"  Bbox: {bbox}")
                
                if bbox and len(bbox) == 4:
                    print(f"  Lon: {bbox[0]:.2f} to {bbox[2]:.2f}")
                    print(f"  Lat: {bbox[1]:.2f} to {bbox[3]:.2f}")
                    
                    # Check for Arctic issue
                    if bbox[3] > 70:
                        print(f"  ⚠️  High latitude detected: {bbox[3]:.2f} (possible Arctic coordinates)")
                    else:
                        print(f"  ✓ Reasonable coordinates")
                else:
                    print(f"  ❌ Invalid bbox")
                    
            except Exception as e:
                print(f"  ❌ Error: {e}")
            
            print()
    
    except Exception as e:
        print(f"❌ Setup error: {e}")

if __name__ == "__main__":
    async def main():
        # Check environment variables
        if AZURE_OPENAI_ENDPOINT == "your-endpoint-here" or AZURE_OPENAI_API_KEY == "your-key-here":
            print("❌ Please set environment variables:")
            print("  AZURE_OPENAI_ENDPOINT")
            print("  AZURE_OPENAI_API_KEY")
            print("  AZURE_OPENAI_MODEL (optional)")
            return
        
        # Run California wildfire test
        success = await test_california_wildfire_issue()
        
        if success:
            # If main test passed, run additional location tests
            await test_multiple_locations()
        
        print("\nTest completed!")
    
    asyncio.run(main())
