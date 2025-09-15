# Copyright (c) Microsoft Corporation.
# Licensed under the MIT license.

#!/usr/bin/env python3

import requests
import json

def test_disaster_analysis():
    """Test the enhanced disaster analysis functionality"""
    
    url = "http://localhost:7071/api/query"
    
    # Test query that should trigger disaster analysis
    test_query = "what damage did hurricane harvey cause to houston in 2017?"
    
    payload = {
        "query": test_query
    }
    
    print(f"Testing disaster analysis with query: {test_query}")
    print("=" * 60)
    
    try:
        # Make the request
        response = requests.post(url, json=payload, timeout=60)
        
        print(f"Status Code: {response.status_code}")
        
        if response.status_code == 200:
            result = response.json()
            
            print(f"Response Type: {result.get('query_type', 'unknown')}")
            print(f"Analysis Type: {result.get('analysis_type', 'unknown')}")
            print()
            
            # Print the message which should now be comprehensive disaster analysis
            if 'message' in result:
                print("DISASTER ANALYSIS RESPONSE:")
                print("-" * 40)
                print(result['message'])
                print("-" * 40)
            
            # Check for other important fields
            if 'stac_data' in result:
                stac_data = result['stac_data']
                print(f"\nSTAC Data: {len(stac_data.get('features', []))} features found")
                
                if stac_data.get('features'):
                    first_feature = stac_data['features'][0]
                    print(f"First feature collection: {first_feature.get('collection', 'unknown')}")
                    print(f"First feature datetime: {first_feature.get('properties', {}).get('datetime', 'unknown')}")
            
        else:
            print(f"Error: {response.status_code}")
            print(response.text)
            
    except requests.exceptions.RequestException as e:
        print(f"Request failed: {e}")
    except Exception as e:
        print(f"Unexpected error: {e}")

if __name__ == "__main__":
    test_disaster_analysis()
