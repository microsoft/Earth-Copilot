# Copyright (c) Microsoft Corporation.
# Licensed under the MIT license.

#!/usr/bin/env python3
"""
End-to-end test script for the Earth Copilot system.
Tests the complete pipeline from query input to STAC results.
"""

import requests
import json
import time

def test_health_endpoints():
    """Test health endpoints for both services."""
    print("🔍 Testing health endpoints...")
    
    # Test router function health
    try:
        response = requests.get("http://localhost:7071/api/health", timeout=10)
        print(f"✅ Router health: {response.status_code} - {response.text}")
    except Exception as e:
        print(f"❌ Router health failed: {e}")
    
    # Test STAC function health
    try:
        response = requests.get("http://localhost:7072/api/health", timeout=10)
        print(f"✅ STAC health: {response.status_code} - {response.text}")
    except Exception as e:
        print(f"❌ STAC health failed: {e}")

def test_query_pipeline(query):
    """Test the complete query pipeline."""
    print(f"\n🚀 Testing query: '{query}'")
    
    try:
        # Send query to router function
        payload = {"query": query}
        response = requests.post("http://localhost:7071/api/query", 
                               json=payload, 
                               timeout=30)
        
        print(f"📋 Response status: {response.status_code}")
        
        if response.status_code == 200:
            result = response.json()
            print(f"✅ Query successful!")
            print(f"📊 Collections found: {len(result.get('results', []))}")
            print(f"🎯 Confidence: {result.get('confidence', 'N/A')}")
            print(f"🗺️  STAC query: {json.dumps(result.get('stac_query', {}), indent=2)}")
        else:
            print(f"❌ Query failed: {response.text}")
            
    except Exception as e:
        print(f"❌ Query pipeline failed: {e}")

def main():
    """Run all tests."""
    print("🌍 Earth Copilot End-to-End Testing")
    print("=" * 50)
    
    # Test health endpoints
    test_health_endpoints()
    
    # Wait a moment
    time.sleep(2)
    
    # Test the guaranteed working queries
    test_queries = [
        "assess camp fire damage in paradise california 2018",
        "show crop health in iowa during summer 2023",
        "monitor sea ice changes in arctic 2024"
    ]
    
    for query in test_queries:
        test_query_pipeline(query)
        time.sleep(1)

if __name__ == "__main__":
    main()
