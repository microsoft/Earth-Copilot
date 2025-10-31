"""
Quick test script for deployed GEOINT agent endpoints
Run this after deployment completes to verify the refactoring worked
"""

import requests
import json

# Your backend URL
BASE_URL = "https://earthcopilot-api.blueriver-c8300d15.canadacentral.azurecontainerapps.io"

print("=" * 80)
print("TESTING DEPLOYED GEOINT AGENT ENDPOINTS")
print("=" * 80)

# Test 1: Check OpenAPI schema
print("\n1. Checking OpenAPI schema for GEOINT endpoints...")
try:
    response = requests.get(f"{BASE_URL}/openapi.json")
    openapi = response.json()
    paths = openapi.get("paths", {})
    
    geoint_endpoints = [p for p in paths.keys() if 'geoint' in p.lower()]
    
    print(f"   Found {len(geoint_endpoints)} GEOINT endpoints in OpenAPI:")
    for endpoint in sorted(geoint_endpoints):
        print(f"   ✅ {endpoint}")
    
    if "/api/geoint/terrain" in geoint_endpoints:
        print("\n   ✅ TERRAIN ENDPOINT IN OPENAPI (404 issue fixed!)")
    else:
        print("\n   ❌ TERRAIN ENDPOINT MISSING FROM OPENAPI")
        
except Exception as e:
    print(f"   ❌ Failed: {e}")

# Test 2: Test terrain endpoint directly
print("\n2. Testing terrain endpoint with sample request...")
try:
    response = requests.post(
        f"{BASE_URL}/api/geoint/terrain",
        json={
            "latitude": 38.89,
            "longitude": -77.03,
            "radius_miles": 5.0,
            "user_query": "Test query"
        },
        timeout=30
    )
    
    print(f"   Status: {response.status_code}")
    
    if response.status_code == 200:
        print("   ✅ TERRAIN ENDPOINT WORKS! (No more 404!)")
        result = response.json()
        if "result" in result:
            agent_type = result["result"].get("agent", "unknown")
            print(f"   Agent type: {agent_type}")
    elif response.status_code == 404:
        print("   ❌ Still getting 404 - check deployment logs")
    else:
        print(f"   ⚠️ Got status {response.status_code}: {response.text[:200]}")
        
except requests.exceptions.Timeout:
    print("   ⏱️ Request timeout (agent may be working but slow)")
except Exception as e:
    print(f"   ❌ Failed: {e}")

# Test 3: Test mobility endpoint
print("\n3. Testing mobility endpoint...")
try:
    response = requests.post(
        f"{BASE_URL}/api/geoint/mobility",
        json={
            "latitude": 38.89,
            "longitude": -77.03,
            "user_query": "Test query"
        },
        timeout=30
    )
    
    print(f"   Status: {response.status_code}")
    
    if response.status_code == 200:
        print("   ✅ MOBILITY ENDPOINT WORKS")
    else:
        print(f"   ⚠️ Got status {response.status_code}")
        
except requests.exceptions.Timeout:
    print("   ⏱️ Request timeout")
except Exception as e:
    print(f"   ❌ Failed: {e}")

# Test 4: Test new orchestrator endpoint
print("\n4. Testing NEW orchestrator endpoint...")
try:
    response = requests.post(
        f"{BASE_URL}/api/geoint/orchestrate",
        json={
            "latitude": 38.89,
            "longitude": -77.03,
            "modules": ["terrain", "mobility"],
            "radius_miles": 5.0
        },
        timeout=60
    )
    
    print(f"   Status: {response.status_code}")
    
    if response.status_code == 200:
        print("   ✅ ORCHESTRATOR ENDPOINT WORKS")
        result = response.json()
        if "result" in result and "results" in result["result"]:
            modules = result["result"]["results"].keys()
            print(f"   Modules executed: {list(modules)}")
    else:
        print(f"   ⚠️ Got status {response.status_code}")
        
except requests.exceptions.Timeout:
    print("   ⏱️ Request timeout (orchestrator may take longer)")
except Exception as e:
    print(f"   ❌ Failed: {e}")

print("\n" + "=" * 80)
print("TEST COMPLETE")
print("=" * 80)
print("\nIf terrain endpoint returned 200 instead of 404, the refactoring worked! 🎉")
print()
