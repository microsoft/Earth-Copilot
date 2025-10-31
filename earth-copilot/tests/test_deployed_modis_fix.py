"""
Test the DEPLOYED backend API to verify MODIS tile URL generation is fixed.
This script makes actual API calls to the production container to check for 404-causing parameters.
"""

import requests
import json
import urllib.parse

# Production backend URL
BACKEND_URL = "https://earthcopilot-api.blueriver-c8300d15.canadacentral.azurecontainerapps.io"

def test_deployed_modis_tiles():
    """Test the deployed backend API for MODIS fire tile URL generation"""
    
    print("=" * 80)
    print("TESTING DEPLOYED BACKEND - MODIS TILE URL GENERATION")
    print("=" * 80)
    print(f"Backend URL: {BACKEND_URL}")
    print()
    
    # Test query for California fires
    test_query = {
        "query": "Show me fires in California",
        "conversation_id": "test_modis_fix_verification"
    }
    
    print(f"📤 Sending query: '{test_query['query']}'")
    print()
    
    try:
        # Make request to query endpoint
        response = requests.post(
            f"{BACKEND_URL}/api/query",
            json=test_query,
            timeout=60
        )
        
        print(f"📥 Response Status: {response.status_code}")
        
        if response.status_code != 200:
            print(f"❌ ERROR: Got status code {response.status_code}")
            print(f"Response: {response.text[:500]}")
            return
        
        data = response.json()
        print(f"✅ Got successful response")
        print()
        
        # Debug: check response structure
        print(f"📋 Response Keys: {list(data.keys())}")
        
        # Check multiple possible locations for STAC results
        features = None
        
        if "data" in data and isinstance(data["data"], dict):
            if "stac_results" in data["data"] and "features" in data["data"]["stac_results"]:
                features = data["data"]["stac_results"]["features"]
                print(f"✅ Found features in data.stac_results.features")
            elif "features" in data["data"]:
                features = data["data"]["features"]
                print(f"✅ Found features in data.features")
        
        if not features and "stac_results" in data and "features" in data["stac_results"]:
            features = data["stac_results"]["features"]
            print(f"✅ Found features in stac_results.features")
        
        if not features:
            print("❌ ERROR: No STAC features found in response")
            print(f"Data structure: {json.dumps(data, indent=2)[:1000]}")
            return
        print(f"📊 Found {len(features)} STAC features")
        
        if not features:
            print("❌ ERROR: No features returned (maybe no fires in California right now)")
            return
        
        # Check first feature
        first_feature = features[0]
        collection = first_feature.get("collection", "unknown")
        item_id = first_feature.get("id", "unknown")
        
        print(f"\n📍 First Feature:")
        print(f"   Collection: {collection}")
        print(f"   Item ID: {item_id}")
        print(f"   Bbox: {first_feature.get('bbox', 'N/A')}")
        
        # Check for tile URLs in translation metadata
        translation_metadata = data.get("translation_metadata", {})
        
        print(f"\n🔍 Translation Metadata Keys:")
        for key in translation_metadata.keys():
            print(f"   - {key}")
        
        # Look for tile URLs
        tile_urls = []
        
        if "all_tile_urls" in translation_metadata:
            all_tile_urls = translation_metadata["all_tile_urls"]
            print(f"\n✅ Found 'all_tile_urls': {len(all_tile_urls)} tile URLs")
            tile_urls = [t.get("tilejson_url") for t in all_tile_urls if isinstance(t, dict) and "tilejson_url" in t]
        
        if "tilejson_url" in translation_metadata:
            print(f"✅ Found 'tilejson_url'")
            tile_urls.append(translation_metadata["tilejson_url"])
        
        if not tile_urls:
            print("❌ ERROR: No tile URLs found in translation_metadata")
            print(f"Full metadata: {json.dumps(translation_metadata, indent=2)[:500]}")
            return
        
        print(f"\n🔗 Analyzing {len(tile_urls)} tile URL(s)...")
        print("=" * 80)
        
        # Analyze each tile URL
        issues_found = []
        
        for idx, url in enumerate(tile_urls[:3], 1):  # Check first 3 URLs
            print(f"\n📍 Tile URL #{idx}:")
            print(f"   {url}")
            print()
            
            # Parse URL to check parameters
            parsed = urllib.parse.urlparse(url)
            params = urllib.parse.parse_qs(parsed.query)
            
            print(f"   Parameters:")
            for param_name, param_values in params.items():
                print(f"      {param_name} = {param_values[0] if param_values else 'N/A'}")
            
            # Check for problematic parameters
            print(f"\n   ✅ Validation:")
            
            if "rescale" in params:
                issue = f"❌ FAIL: Tile #{idx} has 'rescale' parameter (causes 404 on PC native tiles)"
                print(f"      {issue}")
                issues_found.append(issue)
            else:
                print(f"      ✓ No 'rescale' parameter")
            
            if "tile_scale" in params:
                issue = f"❌ FAIL: Tile #{idx} has 'tile_scale' parameter (causes 404 on PC native tiles)"
                print(f"      {issue}")
                issues_found.append(issue)
            else:
                print(f"      ✓ No 'tile_scale' parameter")
            
            if "colormap_name" in params:
                colormap = params["colormap_name"][0]
                if "modis-14A1" in colormap or "modis-14A2" in colormap:
                    print(f"      ✓ Correct colormap: {colormap}")
                else:
                    print(f"      ⚠️  Unexpected colormap: {colormap}")
            else:
                print(f"      ⚠️  No colormap_name parameter")
            
            if "assets" in params:
                assets = params["assets"]
                if "FireMask" in assets:
                    print(f"      ✓ Correct asset: FireMask")
                else:
                    print(f"      ⚠️  Unexpected assets: {assets}")
            else:
                print(f"      ⚠️  No assets parameter")
        
        # Final summary
        print("\n" + "=" * 80)
        print("FINAL VERDICT:")
        print("=" * 80)
        
        if issues_found:
            print(f"❌ DEPLOYMENT HAS BUGS - {len(issues_found)} issue(s) found:")
            for issue in issues_found:
                print(f"   {issue}")
            print()
            print("⚠️  The deployed backend is still generating URLs with unsupported parameters.")
            print("   This means the latest fix has NOT been deployed yet.")
            print("   You need to redeploy the backend with the fixed code.")
        else:
            print("✅ DEPLOYMENT IS FIXED!")
            print("   All tile URLs are clean - no unsupported parameters found.")
            print("   MODIS fire tiles should now work without 404 errors.")
        
        print()
        
    except requests.exceptions.RequestException as e:
        print(f"❌ ERROR making request: {e}")
    except Exception as e:
        print(f"❌ ERROR: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    test_deployed_modis_tiles()
