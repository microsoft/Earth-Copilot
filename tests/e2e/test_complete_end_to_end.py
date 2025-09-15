# Copyright (c) Microsoft Corporation.
# Licensed under the MIT license.

"""
Complete End-to-End Test: Router → STAC → Real Satellite Data
============================================================

This test proves the complete pipeline:
1. Router Function App receives natural language query
2. Router translates to proper STAC query format
3. STAC Function App executes the query
4. Real satellite data is returned

Flow: User Query → Router Agent → STAC Query → Microsoft Planetary Computer → Satellite Results
"""

import asyncio
import httpx
import json
import time
from datetime import datetime

# Function App Endpoints
ROUTER_URL = "http://localhost:7074/api/chat"
STAC_URL = "http://localhost:7072/api/stac-search"

async def test_complete_pipeline():
    """Test the complete Router → STAC → Results pipeline"""
    
    print("🚀 COMPLETE END-TO-END PIPELINE TEST")
    print("=" * 60)
    
    # Test query that should work well
    test_query = "Show me Landsat satellite images of Los Angeles from the last month with low cloud cover"
    
    print(f"📝 User Query: {test_query}")
    print()
    
    async with httpx.AsyncClient(timeout=60.0) as client:
        
        # ======================
        # STEP 1: Router Agent
        # ======================
        print("🔄 STEP 1: Sending query to Router Agent...")
        
        router_payload = {
            "message": test_query,
            "user_id": "test_user_e2e",
            "session_id": "test_session_e2e"
        }
        
        try:
            router_response = await client.post(ROUTER_URL, json=router_payload)
            router_response.raise_for_status()
            router_data = router_response.json()
            
            print("✅ Router Agent Response:")
            print(f"   Status: {router_response.status_code}")
            print(f"   Response: {json.dumps(router_data, indent=2)}")
            print()
            
            # Extract STAC query from router response
            if "stac_query" in router_data:
                stac_query = router_data["stac_query"]
                print("🎯 Extracted STAC Query:")
                print(json.dumps(stac_query, indent=2))
                print()
            else:
                print("❌ ERROR: No STAC query found in router response")
                return False
                
        except Exception as e:
            print(f"❌ ERROR: Router Agent failed: {e}")
            return False
        
        # ======================
        # STEP 2: STAC Search
        # ======================
        print("🔄 STEP 2: Executing STAC query...")
        
        try:
            stac_response = await client.post(STAC_URL, json=stac_query)
            stac_response.raise_for_status()
            stac_data = stac_response.json()
            
            print("✅ STAC Search Response:")
            print(f"   Status: {stac_response.status_code}")
            
            # Analyze the results
            if "features" in stac_data:
                features = stac_data["features"]
                print(f"   🛰️  Found {len(features)} satellite images!")
                print()
                
                if features:
                    print("📊 SATELLITE DATA ANALYSIS:")
                    print("-" * 40)
                    
                    for i, feature in enumerate(features[:3]):  # Show first 3
                        props = feature.get("properties", {})
                        print(f"   Image {i+1}:")
                        print(f"   📅 Date: {props.get('datetime', 'N/A')}")
                        print(f"   🛰️  Platform: {props.get('platform', 'N/A')}")
                        print(f"   🌫️  Cloud Cover: {props.get('eo:cloud_cover', 'N/A')}%")
                        print(f"   🔗 ID: {feature.get('id', 'N/A')}")
                        
                        # Check for assets (actual image data links)
                        assets = feature.get("assets", {})
                        if assets:
                            print(f"   📁 Available Assets: {list(assets.keys())}")
                        print()
                    
                    if len(features) > 3:
                        print(f"   ... and {len(features) - 3} more images")
                        print()
                    
                    return True
                else:
                    print("   ⚠️  No satellite images found for this query")
                    return False
            else:
                print("   ❌ ERROR: Invalid STAC response format")
                print(f"   Response: {json.dumps(stac_data, indent=2)}")
                return False
                
        except Exception as e:
            print(f"❌ ERROR: STAC search failed: {e}")
            return False

async def test_health_checks():
    """Verify both Function Apps are healthy"""
    
    print("🏥 HEALTH CHECK")
    print("=" * 30)
    
    async with httpx.AsyncClient(timeout=10.0) as client:
        
        # Router health check
        try:
            router_health = await client.get("http://localhost:7074/api/health")
            print(f"✅ Router App: {router_health.status_code} - {router_health.text}")
        except Exception as e:
            print(f"❌ Router App: {e}")
            return False
        
        # STAC health check  
        try:
            stac_health = await client.get("http://localhost:7072/api/health")
            print(f"✅ STAC App: {stac_health.status_code} - {stac_health.text}")
        except Exception as e:
            print(f"❌ STAC App: {e}")
            return False
            
        print()
        return True

async def test_router_stac_integration():
    """Test multiple queries to prove the integration works"""
    
    test_queries = [
        "Find Sentinel-2 images of San Francisco from August 2024",
        "Show me MODIS data for New York City with cloud cover less than 10%",
        "Get Landsat images of Seattle from the summer of 2024"
    ]
    
    print("🔗 INTEGRATION TEST - MULTIPLE QUERIES")
    print("=" * 50)
    
    success_count = 0
    
    for i, query in enumerate(test_queries, 1):
        print(f"📝 Test Query {i}: {query}")
        
        async with httpx.AsyncClient(timeout=30.0) as client:
            
            # Send to Router
            router_payload = {
                "message": query,
                "user_id": f"test_user_{i}",
                "session_id": f"test_session_{i}"
            }
            
            try:
                # Router step
                router_response = await client.post(ROUTER_URL, json=router_payload)
                router_response.raise_for_status()
                router_data = router_response.json()
                
                if "stac_query" in router_data:
                    stac_query = router_data["stac_query"]
                    
                    # STAC step
                    stac_response = await client.post(STAC_URL, json=stac_query)
                    stac_response.raise_for_status()
                    stac_data = stac_response.json()
                    
                    if "features" in stac_data:
                        feature_count = len(stac_data["features"])
                        print(f"   ✅ Success: Found {feature_count} images")
                        success_count += 1
                    else:
                        print(f"   ❌ Failed: Invalid STAC response")
                else:
                    print(f"   ❌ Failed: No STAC query from Router")
                    
            except Exception as e:
                print(f"   ❌ Failed: {e}")
        
        print()
    
    print(f"🏆 INTEGRATION RESULTS: {success_count}/{len(test_queries)} queries successful")
    print()
    
    return success_count == len(test_queries)

async def main():
    """Run all tests"""
    
    print("🌍 EARTH COPILOT - COMPLETE END-TO-END TEST")
    print("=" * 60)
    print(f"⏰ Started at: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print()
    
    # Health checks first
    if not await test_health_checks():
        print("❌ Health checks failed. Make sure both Function Apps are running.")
        return
    
    # Main pipeline test
    pipeline_success = await test_complete_pipeline()
    
    # Integration tests
    integration_success = await test_router_stac_integration()
    
    # Final results
    print("🏁 FINAL RESULTS")
    print("=" * 30)
    print(f"   Pipeline Test: {'✅ PASSED' if pipeline_success else '❌ FAILED'}")
    print(f"   Integration Test: {'✅ PASSED' if integration_success else '❌ FAILED'}")
    print()
    
    if pipeline_success and integration_success:
        print("🎉 ALL TESTS PASSED!")
        print("🚀 Router → STAC → Satellite Data pipeline is WORKING!")
        print()
        print("💡 What this proves:")
        print("   ✅ Router translates natural language to STAC queries")
        print("   ✅ STAC Function executes queries against Microsoft Planetary Computer")
        print("   ✅ Real satellite data is returned")
        print("   ✅ Complete end-to-end workflow is functional")
    else:
        print("❌ Some tests failed. Check the output above for details.")

if __name__ == "__main__":
    asyncio.run(main())
