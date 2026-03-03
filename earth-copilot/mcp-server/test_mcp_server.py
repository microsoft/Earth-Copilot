"""
Test script for Earth Copilot MCP Server
Tests the HTTP bridge endpoints
"""

import requests
import json

BASE_URL = "http://127.0.0.1:8080"

def test_tools_list():
    """Test listing available MCP tools."""
    print("=" * 60)
    print("TEST 1: List Available Tools")
    print("=" * 60)
    
    try:
        response = requests.post(f"{BASE_URL}/tools/list")
        response.raise_for_status()
        
        data = response.json()
        print(f"[OK] Success! Found {len(data.get('tools', []))} tools:")
        print()
        
        for tool in data.get('tools', []):
            print(f"  [TOOL] {tool['name']}")
            print(f"     {tool['description']}")
            print()
        
        return data
    except Exception as e:
        print(f"[FAIL] Error: {e}")
        return None

def test_resources_list():
    """Test listing available MCP resources."""
    print("=" * 60)
    print("TEST 2: List Available Resources")
    print("=" * 60)
    
    try:
        response = requests.post(f"{BASE_URL}/resources/list")
        response.raise_for_status()
        
        data = response.json()
        print(f"[OK] Success! Found {len(data.get('resources', []))} resources:")
        print()
        
        for resource in data.get('resources', []):
            print(f"  [PKG] {resource['name']}")
            print(f"     URI: {resource['uri']}")
            print(f"     {resource['description']}")
            print()
        
        return data
    except Exception as e:
        print(f"[FAIL] Error: {e}")
        return None

def test_read_resource(uri="earth://stac/sentinel-2"):
    """Test reading a specific resource."""
    print("=" * 60)
    print(f"TEST 3: Read Resource - {uri}")
    print("=" * 60)
    
    try:
        response = requests.post(
            f"{BASE_URL}/resources/read",
            json={"uri": uri}
        )
        response.raise_for_status()
        
        data = response.json()
        print(f"[OK] Success! Resource data:")
        print()
        print(json.dumps(data, indent=2)[:500] + "...")
        print()
        
        return data
    except Exception as e:
        print(f"[FAIL] Error: {e}")
        return None

def test_terrain_analysis():
    """Test terrain analysis tool (should work)."""
    print("=" * 60)
    print("TEST 4: Terrain Analysis Tool")
    print("=" * 60)
    
    try:
        response = requests.post(
            f"{BASE_URL}/tools/call",
            json={
                "name": "terrain_analysis",
                "arguments": {
                    "location": "Grand Canyon, Arizona",
                    "analysis_types": ["elevation", "slope"],
                    "resolution": 30
                }
            }
        )
        response.raise_for_status()
        
        data = response.json()
        print(f"[OK] Success! Terrain analysis result:")
        print()
        print(json.dumps(data, indent=2)[:1000] + "...")
        print()
        
        return data
    except Exception as e:
        print(f"[FAIL] Error: {e}")
        return None

def test_health():
    """Test health endpoint."""
    print("=" * 60)
    print("TEST 0: Health Check")
    print("=" * 60)
    
    try:
        response = requests.get(f"{BASE_URL}/")
        response.raise_for_status()
        
        print(f"[OK] Server is healthy!")
        print(f"   Response: {response.text}")
        print()
        
        return True
    except Exception as e:
        print(f"[FAIL] Server not responding: {e}")
        return False

if __name__ == "__main__":
    print("\n[GLOBE] Earth Copilot MCP Server - HTTP Bridge Tests\n")
    
    # Test health
    if not test_health():
        print("\n[FAIL] Server is not running! Start it with:")
        print("   python -m uvicorn mcp_bridge:app --host 127.0.0.1 --port 8080")
        exit(1)
    
    # Run tests
    test_tools_list()
    test_resources_list()
    test_read_resource()
    test_terrain_analysis()
    
    print("\n" + "=" * 60)
    print("[DONE] Testing Complete!")
    print("=" * 60)
    print("\n[INFO] Next steps:")
    print("   1. Check which tools returned data")
    print("   2. Update .env with your actual backend URLs")
    print("   3. Test again with real backend connections")
    print()
