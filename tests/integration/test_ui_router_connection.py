# Copyright (c) Microsoft Corporation.
# Licensed under the MIT license.

import requests
import json

def test_router_connection():
    """Test the Router Function App connection and your Seattle query"""
    
    router_url = "http://localhost:7071"
    
    print("🧪 Testing Router Connection...")
    print("=" * 50)
    
    # Test 1: Health check
    try:
        health_response = requests.get(f"{router_url}/api/health", timeout=10)
        if health_response.status_code == 200:
            print("✅ Router health check: SUCCESS")
            print(f"   Response: {health_response.json()}")
        else:
            print(f"❌ Router health check failed: {health_response.status_code}")
            return False
    except Exception as e:
        print(f"❌ Router health check error: {e}")
        return False
    
    # Test 2: Your Seattle query
    print("\n🌍 Testing Your Seattle Query...")
    print("-" * 50)
    
    seattle_query = {
        "query": "Show me Landsat 8 imagery over Seattle from the last 30 days",
        "preferences": {
            "interface_type": "earth_copilot",
            "data_source": "planetary_computer"
        },
        "include_visualization": True,
        "session_id": "seattle-test-123"
    }
    
    try:
        print(f"📤 Sending query: {seattle_query['query']}")
        
        response = requests.post(
            f"{router_url}/api/chat",
            json=seattle_query,
            timeout=30,
            headers={"Content-Type": "application/json"}
        )
        
        print(f"📥 Response status: {response.status_code}")
        
        if response.status_code == 200:
            result = response.json()
            print("✅ Seattle query: SUCCESS")
            print("\n📊 Response preview:")
            print(json.dumps(result, indent=2)[:1000] + "...")
            
            # Check if STAC query was generated
            if 'stac_query' in str(result):
                print("\n✅ STAC query generated successfully!")
                return True
            else:
                print("\n⚠️  No STAC query found in response")
                return False
        else:
            print(f"❌ Seattle query failed: {response.status_code}")
            try:
                error_data = response.json()
                print(f"   Error: {error_data}")
            except:
                print(f"   Raw response: {response.text}")
            return False
            
    except Exception as e:
        print(f"❌ Seattle query error: {e}")
        return False

def test_ui_connection():
    """Test if React UI can reach Router through proxy"""
    
    print("\n🌐 Testing React UI Connection...")
    print("=" * 50)
    
    ui_url = "http://localhost:5173"
    
    try:
        # Test UI is running
        ui_response = requests.get(ui_url, timeout=5)
        if ui_response.status_code == 200:
            print("✅ React UI is accessible")
        else:
            print(f"⚠️  React UI returned status: {ui_response.status_code}")
    except Exception as e:
        print(f"❌ React UI not accessible: {e}")
        return False
    
    # Test UI proxy to Router
    try:
        # This should go through Vite proxy to Router
        proxy_response = requests.get(f"{ui_url}/api/health", timeout=10)
        if proxy_response.status_code == 200:
            print("✅ UI → Router proxy: SUCCESS")
            print("✅ UI can reach Router without Docker!")
            return True
        else:
            print(f"❌ UI → Router proxy failed: {proxy_response.status_code}")
            return False
    except Exception as e:
        print(f"❌ UI → Router proxy error: {e}")
        print("⚠️  This might be why you get 'Failed to send message'")
        return False

if __name__ == "__main__":
    print("🚀 TESTING UI → ROUTER CONNECTION")
    print("=" * 60)
    
    router_works = test_router_connection()
    ui_works = test_ui_connection()
    
    print("\n" + "=" * 60)
    print("🏁 FINAL RESULTS")
    print("=" * 60)
    
    print(f"🧠 Router Direct: {'✅ WORKING' if router_works else '❌ FAILED'}")
    print(f"🌐 UI → Router Proxy: {'✅ WORKING' if ui_works else '❌ FAILED'}")
    
    if router_works and ui_works:
        print("\n🎉 SUCCESS: No Docker needed!")
        print("✅ UI can reach Router directly")
        print("✅ Your Seattle query should work in the UI")
    elif router_works and not ui_works:
        print("\n⚠️  PARTIAL: Router works, UI proxy doesn't")
        print("🔧 Issue: Vite proxy configuration")
        print("💡 Solution: Check Vite proxy settings or use Docker")
    else:
        print("\n❌ FAILED: Router connection issues")
        print("🐳 Recommendation: Use Docker for reliable networking")
