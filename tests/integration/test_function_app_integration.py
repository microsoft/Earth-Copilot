# Copyright (c) Microsoft Corporation.
# Licensed under the MIT license.

#!/usr/bin/env python3
"""
Fast Function App STAC Test
===========================

Quick test with a simple, proven STAC query that should return results fast.
Uses Landsat-8 over a small area with recent data.
"""

import requests
import json
from datetime import datetime, timedelta

def test_fast_stac_search():
    """Test Function App with a simple, fast STAC query"""
    
    print("🚀 FAST FUNCTION APP STAC TEST")
    print("=" * 40)
    
    # Function App URL
    function_url = "http://localhost:7071/api/stac-search"
    
    # Simple, fast query - Landsat-8 over San Francisco Bay (small area)
    # Recent time window (last 30 days) with good cloud cover
    end_date = datetime.now()
    start_date = end_date - timedelta(days=30)
    
    fast_query = {
        "collections": ["landsat-c2-l2"],  # Landsat Collection 2 Level 2
        "bbox": [-122.5, 37.5, -122.0, 38.0],  # Small SF Bay area
        "datetime": f"{start_date.strftime('%Y-%m-%d')}/{end_date.strftime('%Y-%m-%d')}",
        "query": {
            "eo:cloud_cover": {"lt": 20}  # Low cloud cover
        },
        "limit": 10  # Small result set
    }
    
    print(f"📍 Query: Landsat-8 over San Francisco Bay")
    print(f"📅 Time: {start_date.strftime('%Y-%m-%d')} to {end_date.strftime('%Y-%m-%d')}")
    print(f"☁️  Cloud cover: < 20%")
    print(f"📦 Max items: 10")
    
    try:
        print("\n🌐 Sending request to Function App...")
        start_time = datetime.now()
        
        response = requests.post(
            function_url,
            json=fast_query,
            timeout=60,  # Give it a minute
            headers={"Content-Type": "application/json"}
        )
        
        end_time = datetime.now()
        duration = (end_time - start_time).total_seconds()
        
        print(f"⏱️  Response time: {duration:.2f} seconds")
        print(f"📊 Status code: {response.status_code}")
        
        if response.status_code == 200:
            result = response.json()
            
            # Create evidence file
            evidence = {
                "timestamp": datetime.now().isoformat(),
                "test_type": "fast_function_app_stac",
                "query": fast_query,
                "response_time_seconds": duration,
                "status_code": response.status_code,
                "result": result
            }
            
            # Count items if present
            if isinstance(result, dict):
                if "features" in result:
                    item_count = len(result["features"])
                    print(f"✅ SUCCESS: Found {item_count} STAC items!")
                elif "items" in result:
                    item_count = len(result["items"])
                    print(f"✅ SUCCESS: Found {item_count} STAC items!")
                elif "data" in result and isinstance(result["data"], dict) and "features" in result["data"]:
                    item_count = len(result["data"]["features"])
                    print(f"✅ SUCCESS: Found {item_count} STAC items!")
                else:
                    print(f"📄 Response structure: {list(result.keys())}")
                    item_count = "unknown"
                
                evidence["item_count"] = item_count
            
            # Save evidence
            evidence_file = f"fast_stac_test_evidence_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
            with open(evidence_file, 'w') as f:
                json.dump(evidence, f, indent=2)
            
            print(f"💾 Evidence saved to: {evidence_file}")
            
            # Show first item if available
            if isinstance(result, dict) and "features" in result and result["features"]:
                first_item = result["features"][0]
                if "properties" in first_item:
                    props = first_item["properties"]
                    print(f"\n🛰️  First item example:")
                    print(f"   - ID: {first_item.get('id', 'N/A')}")
                    print(f"   - Date: {props.get('datetime', 'N/A')}")
                    print(f"   - Cloud Cover: {props.get('eo:cloud_cover', 'N/A')}%")
                    print(f"   - Collection: {props.get('collection', 'N/A')}")
            
            return True
            
        else:
            error_text = response.text
            print(f"❌ FAILED: {error_text}")
            
            # Save error evidence
            evidence = {
                "timestamp": datetime.now().isoformat(),
                "test_type": "fast_function_app_stac",
                "query": fast_query,
                "response_time_seconds": duration,
                "status_code": response.status_code,
                "error": error_text
            }
            
            evidence_file = f"fast_stac_test_error_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
            with open(evidence_file, 'w') as f:
                json.dump(evidence, f, indent=2)
            
            print(f"💾 Error evidence saved to: {evidence_file}")
            return False
            
    except requests.RequestException as e:
        print(f"❌ REQUEST ERROR: {e}")
        return False
    except Exception as e:
        print(f"❌ UNEXPECTED ERROR: {e}")
        return False

if __name__ == "__main__":
    print("Testing Function App with fast STAC query...")
    success = test_fast_stac_search()
    
    if success:
        print("\n🎉 SUCCESS: Function App is working with real STAC data!")
    else:
        print("\n💥 FAILED: Function App test failed")
        print("Check the evidence file for details")
