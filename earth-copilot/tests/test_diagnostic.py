# Copyright (c) Microsoft Corporation.
# Licensed under the MIT license.

"""
Quick diagnostic test using local.settings.json configuration
Tests the California wildfire query issue directly
"""

import asyncio
import json
import sys
import os

# Add the router function app to the path
sys.path.append(os.path.join(os.path.dirname(__file__), '..', 'router_function_app'))

from semantic_translator import SemanticQueryTranslator

# Use the same config as the router function
AZURE_OPENAI_ENDPOINT = "https://admin-me6cp2y9-eastus2.openai.azure.com"
AZURE_OPENAI_API_KEY = "YOUR_AZURE_OPENAI_API_KEY_HERE"
MODEL_NAME = "gpt-5"

async def diagnose_california_issue():
    """Diagnose the California wildfire Arctic coordinates issue"""
    
    print("🔍 DIAGNOSING CALIFORNIA WILDFIRE ISSUE")
    print("=" * 50)
    
    try:
        # Initialize translator with real credentials
        print("Initializing translator...")
        translator = SemanticQueryTranslator(
            azure_openai_endpoint=AZURE_OPENAI_ENDPOINT,
            azure_openai_api_key=AZURE_OPENAI_API_KEY,
            model_name=MODEL_NAME
        )
        print("✅ Translator initialized\n")
        
        # Test the exact query that was failing
        query = "Show me wildfire damage assessment in California from September 2023"
        print(f"🧪 Testing query: '{query}'\n")
        
        # Step 1: Entity extraction
        print("STEP 1: Entity Extraction")
        print("-" * 30)
        entities = await translator.extract_entities(query)
        
        location = entities.get("location", {})
        temporal = entities.get("temporal", {})
        disaster = entities.get("disaster", {})
        
        print(f"📍 Location: {location.get('name')} ({location.get('type')})")
        print(f"🗓️  Temporal: {temporal.get('year')}-{temporal.get('month')} ({temporal.get('relative')})")
        print(f"🔥 Disaster: {disaster.get('type')} ({disaster.get('name')})")
        
        location_name = location.get("name")
        if location_name != "California":
            print(f"❌ ENTITY EXTRACTION ISSUE: Expected 'California', got '{location_name}'")
            return
        print("✅ Entity extraction looks correct\n")
        
        # Step 2: Direct bbox resolution test
        print("STEP 2: Direct Bbox Resolution")
        print("-" * 30)
        
        bbox = await translator.resolve_location_to_bbox("California")
        print(f"🌐 California bbox: {bbox}")
        
        if not bbox or len(bbox) != 4:
            print(f"❌ BBOX FORMAT ISSUE: Invalid bbox format")
            return
        
        # Check coordinates
        min_lon, min_lat, max_lon, max_lat = bbox
        print(f"   Longitude: {min_lon:.2f} to {max_lon:.2f}")
        print(f"   Latitude:  {min_lat:.2f} to {max_lat:.2f}")
        
        # California should be roughly:
        # Longitude: -124.7 to -114.1
        # Latitude: 32.5 to 42.0
        
        if max_lat > 70:
            print(f"❌ ARCTIC COORDINATES DETECTED!")
            print(f"   Max latitude {max_lat:.2f} is in the Arctic region")
            print(f"   This explains the Arctic satellite data!")
            return
        
        if min_lon < -130 or max_lon > -110 or min_lat < 25 or max_lat > 50:
            print(f"⚠️  COORDINATES SEEM UNUSUAL for California")
            print(f"   Expected roughly: lon -124.7 to -114.1, lat 32.5 to 42.0")
        else:
            print("✅ Coordinates look reasonable for California")
        
        print()
        
        # Step 3: Full query translation
        print("STEP 3: Complete Query Translation")
        print("-" * 30)
        
        stac_query = await translator.translate_query(query)
        
        final_bbox = stac_query.get("bbox", [])
        collections = stac_query.get("collections", [])
        datetime_range = stac_query.get("datetime", "")
        
        print(f"🗺️  Final bbox: {final_bbox}")
        print(f"📦 Collections: {collections}")
        print(f"📅 Datetime: {datetime_range}")
        
        # Check final bbox for Arctic issue
        if final_bbox and len(final_bbox) == 4:
            if final_bbox[3] > 70:
                print(f"\n❌ CRITICAL: Final STAC query has Arctic coordinates!")
                print(f"   Max latitude: {final_bbox[3]:.2f}")
                print(f"   This is why you got Arctic satellite data in the UI")
            else:
                print(f"\n✅ Final bbox looks correct for California")
        
        # Check collections for wildfire
        wildfire_collections = ["modis-14A1-061", "modis-14A2-061"]
        if any(col in collections for col in wildfire_collections):
            print("✅ Wildfire-appropriate collections selected")
        else:
            print(f"⚠️  No wildfire-specific collections found")
            print(f"   Expected: {wildfire_collections}")
        
        print(f"\n{'='*50}")
        if final_bbox and len(final_bbox) == 4 and final_bbox[3] <= 70:
            print("🎉 SUCCESS: Semantic translator working correctly!")
            print("   If you saw Arctic data before, it was likely a temporary issue")
            print("   or the function had crashed during processing.")
        else:
            print("❌ ISSUE CONFIRMED: Geographic resolution is failing")
        print(f"{'='*50}")
        
    except Exception as e:
        print(f"❌ ERROR: {e}")
        import traceback
        traceback.print_exc()

async def test_nominatim_directly():
    """Test Nominatim geocoding service directly"""
    
    print("\n🌍 TESTING NOMINATIM GEOCODING DIRECTLY")
    print("=" * 50)
    
    import aiohttp
    
    try:
        async with aiohttp.ClientSession() as session:
            # Test Nominatim API directly
            url = "https://nominatim.openstreetmap.org/search"
            params = {
                "q": "California, USA",
                "format": "json",
                "limit": 1,
                "addressdetails": 1
            }
            
            print("🔗 Testing Nominatim API...")
            print(f"   URL: {url}")
            print(f"   Query: {params['q']}")
            
            async with session.get(url, params=params) as response:
                if response.status == 200:
                    data = await response.json()
                    print(f"✅ Nominatim response received")
                    
                    if data:
                        result = data[0]
                        lat = float(result.get('lat', 0))
                        lon = float(result.get('lon', 0))
                        
                        print(f"📍 Nominatim result:")
                        print(f"   Name: {result.get('display_name', 'N/A')}")
                        print(f"   Lat: {lat:.6f}")
                        print(f"   Lon: {lon:.6f}")
                        
                        # Check if coordinates are reasonable for California
                        if 32 <= lat <= 42 and -125 <= lon <= -114:
                            print("✅ Nominatim coordinates look correct for California")
                        else:
                            print(f"⚠️  Nominatim coordinates seem unusual for California")
                            print(f"   Expected: lat 32-42, lon -125 to -114")
                        
                        # Get bounding box if available
                        boundingbox = result.get('boundingbox')
                        if boundingbox:
                            bbox = [float(x) for x in boundingbox]  # [min_lat, max_lat, min_lon, max_lon]
                            # Convert to [min_lon, min_lat, max_lon, max_lat] format
                            converted_bbox = [bbox[2], bbox[0], bbox[3], bbox[1]]
                            print(f"🗺️  Nominatim bbox: {converted_bbox}")
                            
                            if converted_bbox[3] > 70:
                                print(f"❌ NOMINATIM RETURNING ARCTIC COORDINATES!")
                            else:
                                print(f"✅ Nominatim bbox looks reasonable")
                    else:
                        print("❌ No results from Nominatim")
                else:
                    print(f"❌ Nominatim API error: {response.status}")
                    
    except Exception as e:
        print(f"❌ Nominatim test failed: {e}")

if __name__ == "__main__":
    async def main():
        await diagnose_california_issue()
        await test_nominatim_directly()
    
    asyncio.run(main())
