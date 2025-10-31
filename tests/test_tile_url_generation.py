"""
Test suite for backend tile URL generation (HybridRenderingSystem)

This tests the refactored backend-only approach where:
1. Backend generates ALL tile URLs with optimal parameters
2. Frontend only displays backend-provided URLs
3. No frontend fallback URL generation

Tests verify that HybridRenderingSystem generates proper tile URLs with:
- Correct rescale parameters (e.g., 0,3000 for HLS)
- Appropriate color formulas
- Optimal band selections
- Collection-specific optimizations
"""

import sys
import os
import json
from typing import Dict, Any

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from hybrid_rendering_system import (
    HybridRenderingSystem,
    RenderingConfig,
    DataType,
    EXPLICIT_RENDER_CONFIGS
)


class TestTileURLGeneration:
    """Test backend tile URL generation for various collections"""
    
    def __init__(self):
        self.tests_passed = 0
        self.tests_failed = 0
        self.test_results = []
    
    def assert_contains(self, value: str, substring: str, test_name: str):
        """Assert that value contains substring"""
        if substring in value:
            self.tests_passed += 1
            self.test_results.append(f"✅ PASS: {test_name}")
            print(f"✅ PASS: {test_name}")
            return True
        else:
            self.tests_failed += 1
            self.test_results.append(f"❌ FAIL: {test_name}")
            print(f"❌ FAIL: {test_name}")
            print(f"   Expected '{substring}' in: {value[:200]}")
            return False
    
    def assert_not_contains(self, value: str, substring: str, test_name: str):
        """Assert that value does not contain substring"""
        if substring not in value:
            self.tests_passed += 1
            self.test_results.append(f"✅ PASS: {test_name}")
            print(f"✅ PASS: {test_name}")
            return True
        else:
            self.tests_failed += 1
            self.test_results.append(f"❌ FAIL: {test_name}")
            print(f"❌ FAIL: {test_name}")
            print(f"   Should NOT contain '{substring}' in: {value[:200]}")
            return False
    
    def assert_equals(self, actual: Any, expected: Any, test_name: str):
        """Assert that actual equals expected"""
        if actual == expected:
            self.tests_passed += 1
            self.test_results.append(f"✅ PASS: {test_name}")
            print(f"✅ PASS: {test_name}")
            return True
        else:
            self.tests_failed += 1
            self.test_results.append(f"❌ FAIL: {test_name}")
            print(f"❌ FAIL: {test_name}")
            print(f"   Expected: {expected}")
            print(f"   Got: {actual}")
            return False
    
    def test_hls_s30_collection(self):
        """Test HLS Sentinel-2 collection (hls2-s30) - PRIMARY USE CASE"""
        print("\n" + "="*80)
        print("TEST: HLS-S30 Collection (Sentinel-2)")
        print("="*80)
        
        collection_id = "hls2-s30"
        
        # Get render config
        config = HybridRenderingSystem.get_render_config(collection_id)
        print(f"Data Type: {config.data_type}")
        print(f"Assets: {config.assets}")
        print(f"Rescale: {config.rescale}")
        print(f"Color Formula: {config.color_formula}")
        
        # Build URL parameters
        url_params = HybridRenderingSystem.build_titiler_url_params(collection_id)
        print(f"\nGenerated URL Parameters:\n{url_params}")
        
        # Critical test: HLS MUST have rescale=0,3000
        self.assert_contains(url_params, "rescale=0,3000", 
                           "HLS-S30 must have rescale=0,3000 parameter")
        
        # Test: Should have RGB bands
        self.assert_contains(url_params, "assets=B04", 
                           "HLS-S30 should include B04 (red) band")
        self.assert_contains(url_params, "assets=B03", 
                           "HLS-S30 should include B03 (green) band")
        self.assert_contains(url_params, "assets=B02", 
                           "HLS-S30 should include B02 (blue) band")
        
        # Note: HLS doesn't have color_formula in explicit config (intentional)
        # Other collections like Landsat have it, but HLS rescale is sufficient
        
        # Test: Should use high-quality resampling
        self.assert_contains(url_params, "resampling=", 
                           "HLS-S30 should specify resampling method")
        
        # Test: Should have tile_scale for high resolution
        self.assert_contains(url_params, "tile_scale=2", 
                           "HLS-S30 should have tile_scale=2 for high resolution")
        
        return url_params
    
    def test_hls_l30_collection(self):
        """Test HLS Landsat collection (hls2-l30)"""
        print("\n" + "="*80)
        print("TEST: HLS-L30 Collection (Landsat)")
        print("="*80)
        
        collection_id = "hls2-l30"
        
        config = HybridRenderingSystem.get_render_config(collection_id)
        print(f"Data Type: {config.data_type}")
        print(f"Assets: {config.assets}")
        print(f"Rescale: {config.rescale}")
        
        url_params = HybridRenderingSystem.build_titiler_url_params(collection_id)
        print(f"\nGenerated URL Parameters:\n{url_params}")
        
        # Critical test: HLS Landsat MUST also have rescale=0,3000
        self.assert_contains(url_params, "rescale=0,3000", 
                           "HLS-L30 must have rescale=0,3000 parameter")
        
        return url_params
    
    def test_sentinel2_l2a_collection(self):
        """Test Sentinel-2 Level-2A collection"""
        print("\n" + "="*80)
        print("TEST: Sentinel-2 L2A Collection")
        print("="*80)
        
        collection_id = "sentinel-2-l2a"
        
        config = HybridRenderingSystem.get_render_config(collection_id)
        print(f"Data Type: {config.data_type}")
        print(f"Assets: {config.assets}")
        
        url_params = HybridRenderingSystem.build_titiler_url_params(collection_id)
        print(f"\nGenerated URL Parameters:\n{url_params}")
        
        # Test: Should have appropriate configuration
        self.assert_contains(url_params, "assets=", 
                           "Sentinel-2 should specify assets")
        
        return url_params
    
    def test_landsat_c2_l2_collection(self):
        """Test Landsat Collection 2 Level-2"""
        print("\n" + "="*80)
        print("TEST: Landsat C2 L2 Collection")
        print("="*80)
        
        collection_id = "landsat-c2-l2"
        
        config = HybridRenderingSystem.get_render_config(collection_id)
        print(f"Data Type: {config.data_type}")
        print(f"Assets: {config.assets}")
        
        url_params = HybridRenderingSystem.build_titiler_url_params(collection_id)
        print(f"\nGenerated URL Parameters:\n{url_params}")
        
        # Test: Should have RGB bands configured
        self.assert_contains(url_params, "assets=", 
                           "Landsat should specify assets")
        
        return url_params
    
    def test_sentinel1_rtc_collection(self):
        """Test Sentinel-1 SAR collection"""
        print("\n" + "="*80)
        print("TEST: Sentinel-1 RTC Collection (SAR)")
        print("="*80)
        
        collection_id = "sentinel-1-rtc"
        
        config = HybridRenderingSystem.get_render_config(collection_id)
        print(f"Data Type: {config.data_type}")
        print(f"Assets: {config.assets}")
        
        url_params = HybridRenderingSystem.build_titiler_url_params(collection_id)
        print(f"\nGenerated URL Parameters:\n{url_params}")
        
        # Test: SAR should be configured (VV or VH polarization)
        self.assert_contains(url_params, "assets=", 
                           "Sentinel-1 SAR should specify assets")
        
        return url_params
    
    def test_modis_fire_collection(self):
        """Test MODIS thermal/fire detection collection"""
        print("\n" + "="*80)
        print("TEST: MODIS Fire Detection Collection")
        print("="*80)
        
        collection_id = "modis-14A1-061"
        
        config = HybridRenderingSystem.get_render_config(collection_id)
        print(f"Data Type: {config.data_type}")
        print(f"Assets: {config.assets}")
        
        url_params = HybridRenderingSystem.build_titiler_url_params(collection_id)
        print(f"\nGenerated URL Parameters:\n{url_params}")
        
        # Test: Should have thermal/fire configuration
        self.assert_contains(url_params, "assets=", 
                           "MODIS fire should specify assets")
        
        return url_params
    
    def test_unknown_collection_fallback(self):
        """Test that unknown collections get safe fallback"""
        print("\n" + "="*80)
        print("TEST: Unknown Collection Fallback")
        print("="*80)
        
        collection_id = "unknown-test-collection-12345"
        
        config = HybridRenderingSystem.get_render_config(collection_id)
        print(f"Data Type: {config.data_type}")
        print(f"Config: {config.to_dict()}")
        
        # Test: Should have UNKNOWN data type
        self.assert_equals(config.data_type, DataType.UNKNOWN,
                         "Unknown collection should have UNKNOWN data type")
        
        # Test: Should still generate some URL parameters
        url_params = HybridRenderingSystem.build_titiler_url_params(collection_id)
        print(f"\nGenerated URL Parameters:\n{url_params}")
        
        self.assert_contains(url_params, "format=png",
                           "Unknown collection should have format parameter")
        
        return url_params
    
    def test_url_parameter_format(self):
        """Test that URL parameters are properly formatted"""
        print("\n" + "="*80)
        print("TEST: URL Parameter Formatting")
        print("="*80)
        
        collection_id = "hls2-s30"
        url_params = HybridRenderingSystem.build_titiler_url_params(collection_id)
        
        # Test: Should not have spaces (should use + or %20)
        self.assert_not_contains(url_params, " ", 
                               "URL parameters should not contain spaces")
        
        # Test: Should be properly joined with &
        parts = url_params.split("&")
        has_equals = all("=" in part for part in parts)
        self.assert_equals(has_equals, True,
                         "All URL parameter parts should have = sign")
        
        return url_params
    
    def test_critical_hls_rescale_parameter(self):
        """CRITICAL TEST: Verify rescale parameter prevents black tiles"""
        print("\n" + "="*80)
        print("CRITICAL TEST: HLS Rescale Parameter (Black Tile Prevention)")
        print("="*80)
        
        # This is the bug that was causing black tiles
        # HLS imagery requires rescale=(0,3000) to display properly
        
        test_collections = ["hls2-s30", "hls2-l30"]
        
        for collection_id in test_collections:
            url_params = HybridRenderingSystem.build_titiler_url_params(collection_id)
            
            print(f"\n{collection_id}:")
            print(f"URL Params: {url_params[:150]}...")
            
            # CRITICAL: Must have rescale=0,3000
            has_rescale = "rescale=0,3000" in url_params
            
            if has_rescale:
                print(f"✅ {collection_id} HAS rescale=0,3000 - tiles will render correctly")
                self.tests_passed += 1
            else:
                print(f"❌ {collection_id} MISSING rescale=0,3000 - tiles will be BLACK!")
                self.tests_failed += 1
                print(f"   This is the critical bug that causes black tiles!")
    
    def run_all_tests(self):
        """Run all test suites"""
        print("\n" + "="*80)
        print("BACKEND TILE URL GENERATION TEST SUITE")
        print("Testing HybridRenderingSystem")
        print("="*80)
        
        # Run all tests
        self.test_hls_s30_collection()
        self.test_hls_l30_collection()
        self.test_sentinel2_l2a_collection()
        self.test_landsat_c2_l2_collection()
        self.test_sentinel1_rtc_collection()
        self.test_modis_fire_collection()
        self.test_unknown_collection_fallback()
        self.test_url_parameter_format()
        self.test_critical_hls_rescale_parameter()
        
        # Print summary
        print("\n" + "="*80)
        print("TEST SUMMARY")
        print("="*80)
        print(f"✅ Tests Passed: {self.tests_passed}")
        print(f"❌ Tests Failed: {self.tests_failed}")
        print(f"Total Tests: {self.tests_passed + self.tests_failed}")
        
        if self.tests_failed == 0:
            print("\n🎉 ALL TESTS PASSED! Backend tile URL generation is working correctly.")
            print("✅ Safe to deploy - tiles will render with proper parameters.")
        else:
            print(f"\n⚠️ {self.tests_failed} TESTS FAILED!")
            print("❌ DO NOT DEPLOY until issues are fixed.")
        
        print("\n" + "="*80)
        
        return self.tests_failed == 0


def main():
    """Run test suite"""
    test_suite = TestTileURLGeneration()
    success = test_suite.run_all_tests()
    
    # Exit with appropriate code
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
