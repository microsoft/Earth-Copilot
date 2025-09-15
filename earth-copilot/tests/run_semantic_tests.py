# Copyright (c) Microsoft Corporation.
# Licensed under the MIT license.

#!/usr/bin/env python3
"""
Direct test runner for semantic translator - bypasses pytest complexity
"""

import sys
import os
import asyncio
import json
from datetime import datetime

# Add router function app to path
router_path = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'router_function_app'))
sys.path.insert(0, router_path)

print(f"Added to Python path: {router_path}")

try:
    from semantic_translator import SemanticQueryTranslator
    print("✅ Import successful")
except ImportError as e:
    print(f"❌ Import failed: {e}")
    print("Available files in router_function_app:")
    for f in os.listdir(router_path):
        print(f"  {f}")
    sys.exit(1)

# Configuration
AZURE_OPENAI_ENDPOINT = "https://admin-me6cp2y9-eastus2.openai.azure.com"
AZURE_OPENAI_API_KEY = "YOUR_AZURE_OPENAI_API_KEY_HERE"
MODEL_NAME = "gpt-5"

# Test cases (subset of the full test suite for quick validation)
QUICK_TEST_CASES = [
    {
        "name": "California Wildfire Test",
        "query": "Show me wildfire damage assessment in California from September 2023",
        "expected": {
            "location": "California",
            "disaster": "wildfire",
            "year": "2023",
            "month": "09"
        }
    },
    {
        "name": "Hurricane Ida Test", 
        "query": "Analyze Hurricane Ida damage in Louisiana August 2021",
        "expected": {
            "location": "Louisiana",
            "disaster": "hurricane",
            "year": "2021",
            "month": "08"
        }
    },
    {
        "name": "Houston Flooding Test",
        "query": "Show flooding in Houston Texas after recent storms",
        "expected": {
            "location": "Houston",
            "disaster": "flood",
            "relative": "recent"
        }
    }
]

async def run_quick_tests():
    """Run a subset of tests for rapid validation"""
    
    print("=" * 60)
    print("🧪 SEMANTIC TRANSLATOR QUICK TEST SUITE")
    print("=" * 60)
    
    try:
        # Initialize translator
        print("\n🔧 Initializing Semantic Translator...")
        translator = SemanticQueryTranslator(
            azure_openai_endpoint=AZURE_OPENAI_ENDPOINT,
            azure_openai_api_key=AZURE_OPENAI_API_KEY,
            model_name=MODEL_NAME
        )
        print("✅ Translator initialized successfully")
        
        results = []
        
        for i, test_case in enumerate(QUICK_TEST_CASES, 1):
            print(f"\n{'='*20} TEST {i}: {test_case['name']} {'='*20}")
            query = test_case["query"]
            expected = test_case["expected"]
            
            print(f"📝 Query: {query}")
            
            try:
                # Test entity extraction
                print("\n🔍 Step 1: Entity Extraction")
                entities = await translator.extract_entities(query)
                
                location = entities.get("location", {})
                temporal = entities.get("temporal", {})
                disaster = entities.get("disaster", {})
                
                print(f"   📍 Location: {location.get('name')} ({location.get('type')})")
                print(f"   🗓️  Temporal: {temporal.get('year')}-{temporal.get('month')} ({temporal.get('relative')})")
                print(f"   🔥 Disaster: {disaster.get('type')}")
                
                # Validate entities
                entity_score = 0
                max_entity_score = 0
                
                if "location" in expected:
                    max_entity_score += 1
                    if location.get("name") == expected["location"]:
                        entity_score += 1
                        print("   ✅ Location extraction correct")
                    else:
                        print(f"   ❌ Location: expected '{expected['location']}', got '{location.get('name')}'")
                
                if "disaster" in expected:
                    max_entity_score += 1
                    if disaster.get("type") == expected["disaster"]:
                        entity_score += 1
                        print("   ✅ Disaster extraction correct")
                    else:
                        print(f"   ❌ Disaster: expected '{expected['disaster']}', got '{disaster.get('type')}'")
                
                if "year" in expected:
                    max_entity_score += 1
                    if temporal.get("year") == expected["year"]:
                        entity_score += 1
                        print("   ✅ Year extraction correct")
                    else:
                        print(f"   ❌ Year: expected '{expected['year']}', got '{temporal.get('year')}'")
                
                # Test bbox resolution
                print("\n🗺️  Step 2: Bbox Resolution")
                location_name = location.get("name")
                if location_name:
                    bbox = await translator.resolve_location_to_bbox(location_name)
                    print(f"   Bbox: {bbox}")
                    
                    bbox_valid = False
                    if bbox and len(bbox) == 4:
                        min_lon, min_lat, max_lon, max_lat = bbox
                        if (-180 <= min_lon <= 180 and -90 <= min_lat <= 90 and 
                            -180 <= max_lon <= 180 and -90 <= max_lat <= 90 and
                            min_lon < max_lon and min_lat < max_lat):
                            bbox_valid = True
                            print(f"   ✅ Valid bbox: lon {min_lon:.2f} to {max_lon:.2f}, lat {min_lat:.2f} to {max_lat:.2f}")
                            
                            # Check for Arctic coordinates issue
                            if max_lat > 70:
                                print(f"   ⚠️  WARNING: High latitude {max_lat:.2f} detected (Arctic region)")
                            
                        else:
                            print("   ❌ Invalid bbox coordinates")
                    else:
                        print("   ❌ Invalid bbox format")
                else:
                    print("   ❌ No location to resolve")
                    bbox_valid = False
                
                # Test complete STAC query
                print("\n🎯 Step 3: Complete STAC Query")
                stac_query = await translator.translate_query(query)
                
                collections = stac_query.get("collections", [])
                final_bbox = stac_query.get("bbox", [])
                datetime_range = stac_query.get("datetime", "")
                
                print(f"   Collections: {collections}")
                print(f"   Final bbox: {final_bbox}")
                print(f"   Datetime: {datetime_range}")
                
                # Validate STAC query
                stac_valid = True
                if not collections:
                    print("   ❌ No collections selected")
                    stac_valid = False
                else:
                    print("   ✅ Collections selected")
                
                if not final_bbox or len(final_bbox) != 4:
                    print("   ❌ Invalid final bbox")
                    stac_valid = False
                elif final_bbox[3] > 70:
                    print(f"   ❌ CRITICAL: Arctic coordinates in final STAC query! Max lat: {final_bbox[3]:.2f}")
                    stac_valid = False
                else:
                    print("   ✅ Final bbox valid")
                
                if not datetime_range:
                    print("   ❌ No datetime range")
                    stac_valid = False
                else:
                    print("   ✅ Datetime range generated")
                
                # Calculate overall score
                entity_pct = (entity_score / max_entity_score * 100) if max_entity_score > 0 else 0
                overall_score = (entity_pct + (100 if bbox_valid else 0) + (100 if stac_valid else 0)) / 3
                
                result = {
                    "test": test_case["name"],
                    "query": query,
                    "entity_score": f"{entity_score}/{max_entity_score}",
                    "bbox_valid": bbox_valid,
                    "stac_valid": stac_valid,
                    "overall_score": overall_score,
                    "passed": overall_score >= 70
                }
                results.append(result)
                
                status = "✅ PASSED" if result["passed"] else "❌ FAILED"
                print(f"\n🏆 {status} - Overall Score: {overall_score:.1f}%")
                
            except Exception as e:
                print(f"\n❌ TEST FAILED: {e}")
                results.append({
                    "test": test_case["name"],
                    "query": query,
                    "error": str(e),
                    "passed": False
                })
        
        # Print summary
        print("\n" + "=" * 60)
        print("📊 TEST SUMMARY")
        print("=" * 60)
        
        passed = sum(1 for r in results if r.get("passed", False))
        total = len(results)
        
        print(f"Tests Passed: {passed}/{total} ({passed/total*100:.1f}%)")
        print()
        
        for i, result in enumerate(results, 1):
            status = "✅" if result.get("passed", False) else "❌"
            score = result.get("overall_score", 0)
            print(f"{status} Test {i}: {result['test']} - {score:.1f}%")
        
        print("\n" + "=" * 60)
        if passed >= total * 0.7:
            print("🎉 SEMANTIC TRANSLATOR IS WORKING WELL!")
            print("The translator correctly extracts entities, resolves locations, and generates STAC queries.")
        else:
            print("⚠️  ISSUES DETECTED - Review failed tests above")
        print("=" * 60)
        
        return results
        
    except Exception as e:
        print(f"❌ Test setup failed: {e}")
        import traceback
        traceback.print_exc()
        return []

if __name__ == "__main__":
    asyncio.run(run_quick_tests())
