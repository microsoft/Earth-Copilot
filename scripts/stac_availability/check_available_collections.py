# Copyright (c) Microsoft Corporation.
# Licensed under the MIT license.

#!/usr/bin/env python3
"""Check what collections are actually available in Microsoft Planetary Computer"""

import asyncio
import aiohttp
import json

async def check_collections():
    """Check what collections exist"""
    try:
        async with aiohttp.ClientSession() as session:
            url = "https://planetarycomputer.microsoft.com/api/stac/v1/collections"
            timeout = aiohttp.ClientTimeout(total=30)
            
            async with session.get(url, timeout=timeout) as response:
                if response.status == 200:
                    data = await response.json()
                    collections = data.get("collections", [])
                    
                    print(f"Total collections available: {len(collections)}")
                    print("\n🔍 MODIS Collections:")
                    modis_collections = [c for c in collections if 'modis' in c['id'].lower()]
                    for c in modis_collections:
                        print(f"  ✅ {c['id']} - {c.get('title', 'No title')}")
                    
                    print(f"\n🔍 Fire/Thermal Collections:")
                    fire_collections = [c for c in collections if any(keyword in c['id'].lower() for keyword in ['fire', 'thermal', 'burn'])]
                    for c in fire_collections:
                        print(f"  ✅ {c['id']} - {c.get('title', 'No title')}")
                    
                    print(f"\n🔍 HLS Collections:")
                    hls_collections = [c for c in collections if 'hls' in c['id'].lower()]
                    for c in hls_collections:
                        print(f"  ✅ {c['id']} - {c.get('title', 'No title')}")
                    
                    print(f"\n🔍 VIIRS Collections:")
                    viirs_collections = [c for c in collections if 'viirs' in c['id'].lower()]
                    for c in viirs_collections:
                        print(f"  ✅ {c['id']} - {c.get('title', 'No title')}")
                    
                    print(f"\n🔍 Agriculture/Vegetation Collections:")
                    ag_collections = [c for c in collections if any(keyword in c['id'].lower() for keyword in ['vegetation', 'ndvi', 'crop', 'agriculture'])]
                    for c in ag_collections:
                        print(f"  ✅ {c['id']} - {c.get('title', 'No title')}")
                    
                    # Save all collection IDs
                    all_ids = [c['id'] for c in collections]
                    with open("available_collections.json", "w") as f:
                        json.dump(all_ids, f, indent=2)
                    
                    print(f"\n💾 All {len(all_ids)} collection IDs saved to available_collections.json")
                else:
                    print(f"Failed to get collections: {response.status}")
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    asyncio.run(check_collections())
