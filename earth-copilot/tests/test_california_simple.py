# Copyright (c) Microsoft Corporation.
# Licensed under the MIT license.

"""
Ultra-simple test for the California wildfire issue
"""
import sys
import os
import asyncio

# Add router function app to path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'router_function_app')))

async def test_california_only():
    print("🧪 TESTING CALIFORNIA WILDFIRE QUERY")
    print("=" * 50)
    
    try:
        from semantic_translator import SemanticQueryTranslator
        print("✅ Import successful")
        
        translator = SemanticQueryTranslator(
            azure_openai_endpoint="https://admin-me6cp2y9-eastus2.openai.azure.com",
            azure_openai_api_key="YOUR_AZURE_OPENAI_API_KEY_HERE",
            model_name="gpt-5"
        )
        print("✅ Translator initialized")
        
        query = "Show me wildfire damage assessment in California from September 2023"
        print(f"\n📝 Query: {query}")
        
        # Test 1: Entity extraction
        print("\n🔍 Testing entity extraction...")
        entities = await translator.extract_entities(query)
        
        location = entities.get("location", {}).get("name")
        disaster = entities.get("disaster", {}).get("type")
        year = entities.get("temporal", {}).get("year")
        month = entities.get("temporal", {}).get("month")
        
        print(f"📍 Location: {location}")
        print(f"🔥 Disaster: {disaster}")  
        print(f"📅 Date: {year}-{month}")
        
        # Test 2: Bbox resolution
        print(f"\n🗺️  Testing bbox resolution for '{location}'...")
        if location:
            bbox = await translator.resolve_location_to_bbox(location)
            print(f"Bbox: {bbox}")
            
            if bbox and len(bbox) == 4:
                min_lon, min_lat, max_lon, max_lat = bbox
                print(f"Longitude: {min_lon:.2f} to {max_lon:.2f}")
                print(f"Latitude:  {min_lat:.2f} to {max_lat:.2f}")
                
                # Check for Arctic issue
                if max_lat > 70:
                    print(f"❌ ARCTIC COORDINATES DETECTED! Max lat: {max_lat:.2f}")
                    print("This explains why you got Arctic satellite data!")
                else:
                    print("✅ Coordinates look reasonable for California")
            else:
                print("❌ Invalid bbox format")
        
        # Test 3: Complete STAC query
        print(f"\n🎯 Testing complete STAC query generation...")
        stac_query = await translator.translate_query(query)
        
        collections = stac_query.get("collections", [])
        final_bbox = stac_query.get("bbox", [])
        datetime_str = stac_query.get("datetime", "")
        
        print(f"Collections: {collections}")
        print(f"Final bbox: {final_bbox}")
        print(f"Datetime: {datetime_str}")
        
        # Final validation
        print(f"\n{'='*50}")
        
        issues = []
        if location != "California":
            issues.append(f"Wrong location: '{location}' (expected 'California')")
        if disaster != "wildfire":
            issues.append(f"Wrong disaster: '{disaster}' (expected 'wildfire')")
        if year != "2023":
            issues.append(f"Wrong year: '{year}' (expected '2023')")
        if month != "09":
            issues.append(f"Wrong month: '{month}' (expected '09')")
        if final_bbox and len(final_bbox) == 4 and final_bbox[3] > 70:
            issues.append(f"Arctic coordinates in final bbox: max_lat={final_bbox[3]:.2f}")
        if not collections:
            issues.append("No collections selected")
        
        if issues:
            print("❌ ISSUES FOUND:")
            for issue in issues:
                print(f"   • {issue}")
        else:
            print("🎉 ALL TESTS PASSED!")
            print("The semantic translator is working correctly for California wildfire queries.")
        
        print(f"{'='*50}")
        
    except Exception as e:
        print(f"❌ Test failed: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    asyncio.run(test_california_only())
