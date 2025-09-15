# Copyright (c) Microsoft Corporation.
# Licensed under the MIT license.

import requests
import json

stac_url = "http://localhost:7072/api/stac-search"
payload = {
    "collections": ["landsat-c2-l2"],
    "bbox": [-122.459696, 47.481002, -122.224433, 47.734136],
    "datetime": "2023-01-01/2023-12-31",
    "query": {},
    "limit": 10,
    "original_query": "Show me Landsat 8 imagery over Seattle from 2023"
}

print("Testing STAC function directly with Seattle coordinates:")
print("Payload:", json.dumps(payload, indent=2))
print("\n" + "="*50 + "\n")

try:
    response = requests.post(stac_url, json=payload)
    print("Status Code:", response.status_code)
    print("Response:")
    result = response.json()
    print(json.dumps(result, indent=2))
    
    # Check coordinates in results
    if "results" in result and "features" in result["results"]:
        print(f"\nFound {len(result['results']['features'])} features")
        for i, feature in enumerate(result['results']['features'][:3]):  # Show first 3
            if 'bbox' in feature:
                bbox = feature['bbox']
                print(f"Feature {i+1} bbox: {bbox}")
            if 'geometry' in feature and 'coordinates' in feature['geometry']:
                coords = feature['geometry']['coordinates']
                print(f"Feature {i+1} geometry coords: {coords}")
                
except Exception as e:
    print("Error:", str(e))
    if 'response' in locals():
        print("Raw response:", response.text)
