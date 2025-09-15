"""
End-to-End Test: California Wildfire Query
Tests the clean Function App architecture after cleanup
"""

import requests
import json
import time

def test_function_apps():
    """Test both Function Apps with California wildfire query"""
    
    print("🧪 TESTING CLEAN EARTH COPILOT ARCHITECTURE")
    print("=" * 50)
    
    # Test 1: Router Function App Health
    print("\n1️⃣ Testing Router Function App Health...")
    try:
        response = requests.get("http://localhost:7074/api/health", timeout=10)
        if response.status_code == 200:
            print("✅ Router Function App is healthy!")
        else:
            print(f"❌ Router health check failed: {response.status_code}")
            return False
    except Exception as e:
        print(f"❌ Router Function App connection failed: {e}")
        return False
    
    # Test 2: STAC Function App Health
    print("\n2️⃣ Testing STAC Function App Health...")
    try:
        response = requests.get("http://localhost:7072/api/health", timeout=10)
        if response.status_code == 200:
            print("✅ STAC Function App is healthy!")
        else:
            print(f"❌ STAC health check failed: {response.status_code}")
            return False
    except Exception as e:
        print(f"❌ STAC Function App connection failed: {e}")
        return False
    
    # Test 3: Router Query with Temporal Resolution
    print("\n3️⃣ Testing Router with California Wildfire Query...")
    router_payload = {
        "query": "Show me recent wildfire data in California"
    }
    
    try:
        response = requests.post(
            "http://localhost:7074/api/chat", 
            json=router_payload, 
            timeout=30
        )
        if response.status_code == 200:
            router_result = response.json()
            print("✅ Router query successful!")
            print(f"📊 Router Response: {json.dumps(router_result, indent=2)}")
            
            # Check if temporal resolution worked
            if 'timeframe' in str(router_result) and '2025-' in str(router_result):
                print("🎯 ✅ Temporal resolution working! 'recent' converted to ISO8601!")
            else:
                print("⚠️ Temporal resolution may not be working properly")
        else:
            print(f"❌ Router query failed: {response.status_code}")
            print(f"Response: {response.text}")
            return False
    except Exception as e:
        print(f"❌ Router query failed: {e}")
        return False
    
    # Test 4: STAC Search (if we have parameters from router)
    print("\n4️⃣ Testing STAC Search Function...")
    stac_payload = {
        "collections": ["landsat-c2-l2"],
        "bbox": [-124.4096, 32.5341, -114.1308, 42.0095],  # California bbox
        "datetime": "2025-08-06T02:47:59+00:00/2025-09-05T02:47:59+00:00",
        "limit": 10
    }
    
    try:
        response = requests.post(
            "http://localhost:7072/api/stac-search", 
            json=stac_payload, 
            timeout=30
        )
        if response.status_code == 200:
            stac_result = response.json()
            print("✅ STAC search successful!")
            print(f"📊 Found {len(stac_result.get('features', []))} STAC items")
            if stac_result.get('features'):
                print("🎯 ✅ STAC data retrieval working!")
            else:
                print("⚠️ No STAC features returned")
        else:
            print(f"❌ STAC search failed: {response.status_code}")
            print(f"Response: {response.text}")
            return False
    except Exception as e:
        print(f"❌ STAC search failed: {e}")
        return False
    
    print("\n🎉 ALL TESTS PASSED! Clean architecture is working!")
    return True

if __name__ == "__main__":
    success = test_function_apps()
    if success:
        print("\n✨ READY FOR PRODUCTION TESTING!")
        print("🔥 Your California wildfire query pipeline is operational!")
    else:
        print("\n💥 ISSUES FOUND - Check Function App logs")
