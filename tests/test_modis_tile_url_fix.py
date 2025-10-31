"""
Test MODIS tile URL generation to verify 404 fix.
This script tests that rescale and tile_scale parameters are NOT added to PC native tile URLs.
"""

import sys
sys.path.insert(0, '.')

from hybrid_rendering_system import HybridRenderingSystem, EXPLICIT_RENDER_CONFIGS

def test_modis_tile_url_generation():
    """Test that MODIS configs generate correct tile URLs without unsupported params"""
    
    print("=" * 80)
    print("TESTING MODIS TILE URL GENERATION - 404 FIX VERIFICATION")
    print("=" * 80)
    print()
    
    # Test both MODIS fire collections
    test_collections = ["modis-14A1-061", "modis-14A2-061"]
    
    for collection_id in test_collections:
        print(f"\n{'=' * 80}")
        print(f"Testing: {collection_id}")
        print(f"{'=' * 80}")
        
        # Get the config
        config = EXPLICIT_RENDER_CONFIGS.get(collection_id)
        if not config:
            print(f"❌ ERROR: No config found for {collection_id}")
            continue
        
        print(f"\n📋 Configuration:")
        print(f"   Collection: {config.collection_id}")
        print(f"   Data Type: {config.data_type}")
        print(f"   Assets: {config.assets}")
        print(f"   Rescale: {config.rescale}")
        print(f"   Tile Scale: {config.tile_scale}")
        print(f"   Colormap: {config.colormap}")
        print(f"   Min Zoom: {config.min_zoom}")
        print(f"   Max Zoom: {config.max_zoom}")
        
        # Convert to dict (what gets passed to URL builder)
        params_dict = config.to_dict()
        print(f"\n📦 Parameters Dict:")
        for key, value in params_dict.items():
            print(f"   {key}: {value}")
        
        # Build URL params
        url_params = HybridRenderingSystem.build_titiler_url_params(collection_id)
        print(f"\n🔗 Generated URL Parameters:")
        print(f"   {url_params}")
        
        # Check for problematic parameters
        print(f"\n✅ VALIDATION:")
        
        issues = []
        
        if "rescale=" in url_params:
            issues.append("❌ FAIL: 'rescale' parameter found in URL (should be None for PC native tiles)")
        else:
            print("   ✓ No 'rescale' parameter (correct!)")
        
        if "tile_scale=" in url_params:
            issues.append("❌ FAIL: 'tile_scale' parameter found in URL (should be None for PC native tiles)")
        else:
            print("   ✓ No 'tile_scale' parameter (correct!)")
        
        if "colormap_name=modis-14A1" not in url_params and "colormap_name=modis-14A1%7CA2" not in url_params:
            issues.append("❌ FAIL: Expected 'colormap_name=modis-14A1|A2' not found")
        else:
            print("   ✓ Colormap 'modis-14A1|A2' present (correct!)")
        
        if "assets=FireMask" not in url_params:
            issues.append("❌ FAIL: Expected 'assets=FireMask' not found")
        else:
            print("   ✓ Asset 'FireMask' present (correct!)")
        
        if "resampling=nearest" not in url_params:
            issues.append("❌ FAIL: Expected 'resampling=nearest' not found")
        else:
            print("   ✓ Resampling 'nearest' present (correct!)")
        
        # Summary
        if issues:
            print(f"\n❌ TEST FAILED for {collection_id}:")
            for issue in issues:
                print(f"   {issue}")
        else:
            print(f"\n✅ TEST PASSED for {collection_id}")
            print(f"   All parameters correct - no unsupported params in URL!")
        
        print()
    
    print("\n" + "=" * 80)
    print("FULL URL EXAMPLE (what browser will request):")
    print("=" * 80)
    
    # Show what a real tile URL would look like
    sample_item_id = "MYD14A1.A2025137.h09v05.061.2025148084034"
    url_params = HybridRenderingSystem.build_titiler_url_params("modis-14A1-061")
    
    sample_url = (
        f"https://planetarycomputer.microsoft.com/api/data/v1/item/tiles/"
        f"WebMercatorQuad/9/88/204@2x.png?"
        f"collection=modis-14A1-061&"
        f"item={sample_item_id}&"
        f"{url_params}"
    )
    
    print(f"\n{sample_url}")
    print()
    
    # Check if the problematic params are in the URL
    if "rescale=" in sample_url or "tile_scale=" in sample_url:
        print("❌ CRITICAL: Sample URL still contains unsupported parameters!")
        print("   This URL will return 404 errors!")
    else:
        print("✅ SUCCESS: Sample URL is clean - no unsupported parameters!")
        print("   This URL should work with Planetary Computer native tiles API!")
    
    print("\n" + "=" * 80)

if __name__ == "__main__":
    test_modis_tile_url_generation()
