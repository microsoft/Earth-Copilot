# Copyright (c) Microsoft Corporation.
# Licensed under the MIT license.

#!/usr/bin/env python3
"""
Simple test to debug Router Function
"""
import requests
import json

def test_simple_query():
    """Test with a very simple query to avoid token limits"""
    url = "http://localhost:7071/api/query"
    payload = {
        "query": "hello"  # Very simple query
    }
    
    try:
        print("🧪 Testing Router Function with simple query...")
        response = requests.post(url, json=payload, timeout=10)
        
        print(f"Status Code: {response.status_code}")
        
        if response.status_code == 200:
            try:
                data = response.json()
                print("✅ Router Function Response:")
                print(json.dumps(data, indent=2))
            except json.JSONDecodeError:
                print("❌ Response is not valid JSON")
                print(f"Raw response: {response.text}")
        else:
            print(f"❌ Router Function returned error: {response.status_code}")
            print(f"Response: {response.text}")
            
    except requests.exceptions.ConnectTimeout:
        print("❌ Connection timeout - Router Function may be hanging")
    except requests.exceptions.ReadTimeout:
        print("❌ Read timeout - Router Function processing too long")
    except requests.exceptions.RequestException as e:
        print(f"❌ Error connecting to Router Function: {e}")

def test_stac_function():
    """Test STAC function directly"""
    url = "http://localhost:7072/api/stac-search" 
    payload = {
        "collections": ["sentinel-2-l2a"],
        "bbox": [-84.0, 25.0, -80.0, 27.0],  # Simple Florida bbox
        "datetime": "2023-01-01/2023-12-31",
        "limit": 5
    }
    
    try:
        print("\n🧪 Testing STAC Function directly...")
        response = requests.post(url, json=payload, timeout=10)
        
        print(f"Status Code: {response.status_code}")
        
        if response.status_code == 200:
            try:
                data = response.json()
                print("✅ STAC Function Response:")
                print(f"Found {len(data.get('results', {}).get('features', []))} features")
            except json.JSONDecodeError:
                print("❌ Response is not valid JSON")
                print(f"Raw response: {response.text}")
        else:
            print(f"❌ STAC Function returned error: {response.status_code}")
            print(f"Response: {response.text}")
            
    except requests.exceptions.RequestException as e:
        print(f"❌ Error connecting to STAC Function: {e}")

if __name__ == "__main__":
    print("🚀 Simple Router Function Debug Test")
    print("=" * 50)
    
    test_simple_query()
    test_stac_function()
