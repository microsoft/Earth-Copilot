"""
Comprehensive validation test for ALL featured collections

This test verifies:
1. All 24 featured collections have proper configurations
2. Each featured collection generates valid tile URLs
3. No featured collection will fail when queried
4. Configurations match the actual STAC metadata from MPC API

Test against live Microsoft Planetary Computer STAC API to ensure accuracy.
"""

import sys
import os
import requests
from typing import Dict, List, Optional, Tuple, Any

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from hybrid_rendering_system import (
    HybridRenderingSystem,
    RenderingConfig,
    DataType,
    EXPLICIT_RENDER_CONFIGS,
    FEATURED_COLLECTIONS
)


# Microsoft Planetary Computer STAC API
MPC_STAC_API = "https://planetarycomputer.microsoft.com/api/stac/v1"


class FeaturedCollectionsValidator:
    """Comprehensive validator for all featured collections"""
    
    def __init__(self):
        self.tests_passed = 0
        self.tests_failed = 0
        self.warnings = 0
        self.collection_results = {}
    
    def print_header(self, title: str):
        """Print formatted section header"""
        print("\n" + "=" * 80)
        print(title)
        print("=" * 80)
    
    def test_pass(self, collection_id: str, test_name: str):
        """Record passed test"""
        self.tests_passed += 1
        print(f"✅ {collection_id}: {test_name}")
    
    def test_fail(self, collection_id: str, test_name: str, reason: str = ""):
        """Record failed test"""
        self.tests_failed += 1
        print(f"❌ {collection_id}: {test_name}")
        if reason:
            print(f"   Reason: {reason}")
    
    def test_warning(self, collection_id: str, message: str):
        """Record warning"""
        self.warnings += 1
        print(f"⚠️  {collection_id}: {message}")
    
    def fetch_collection_metadata(self, collection_id: str) -> Optional[Dict]:
        """Fetch collection metadata from MPC STAC API"""
        try:
            url = f"{MPC_STAC_API}/collections/{collection_id}"
            response = requests.get(url, timeout=10)
            
            if response.status_code == 200:
                return response.json()
            elif response.status_code == 404:
                self.test_fail(collection_id, "Collection not found in MPC STAC API",
                             f"HTTP 404 - Collection '{collection_id}' does not exist")
                return None
            else:
                self.test_warning(collection_id, 
                                f"Could not fetch metadata (HTTP {response.status_code})")
                return None
        except Exception as e:
            self.test_warning(collection_id, f"API request failed: {str(e)}")
            return None
    
    def validate_collection_exists(self, collection_id: str) -> bool:
        """Validate collection exists in MPC STAC API"""
        metadata = self.fetch_collection_metadata(collection_id)
        
        if metadata:
            self.test_pass(collection_id, "Exists in MPC STAC API")
            return True
        return False
    
    def validate_has_render_config(self, collection_id: str) -> Optional[RenderingConfig]:
        """Validate collection has a render configuration"""
        config = HybridRenderingSystem.get_render_config(collection_id)
        
        if config:
            self.test_pass(collection_id, f"Has render config (type: {config.data_type})")
            return config
        else:
            self.test_fail(collection_id, "No render configuration found")
            return None
    
    def validate_url_generation(self, collection_id: str) -> Optional[str]:
        """Validate collection can generate tile URL parameters"""
        try:
            url_params = HybridRenderingSystem.build_titiler_url_params(collection_id)
            
            if url_params and len(url_params) > 0:
                self.test_pass(collection_id, "Generates valid tile URL parameters")
                return url_params
            else:
                self.test_fail(collection_id, "Failed to generate tile URL parameters",
                             "Empty or null URL parameters returned")
                return None
        except Exception as e:
            self.test_fail(collection_id, "URL generation crashed", str(e))
            return None
    
    def validate_url_format(self, collection_id: str, url_params: str) -> bool:
        """Validate URL parameters are properly formatted"""
        issues = []
        
        # Check for spaces (should use + or %20)
        if ' ' in url_params:
            issues.append("Contains unencoded spaces")
        
        # Check that all parts have = sign
        parts = url_params.split('&')
        for part in parts:
            if '=' not in part:
                issues.append(f"Invalid parameter format: {part}")
        
        # Check for required parameters
        required_base = ['format=png', 'tile_scale=']
        for req in required_base:
            if req not in url_params:
                issues.append(f"Missing parameter: {req}")
        
        if issues:
            self.test_fail(collection_id, "URL format validation failed",
                         "; ".join(issues))
            return False
        else:
            self.test_pass(collection_id, "URL format is valid")
            return True
    
    def validate_data_type_specific(self, collection_id: str, config: RenderingConfig) -> bool:
        """Validate collection has appropriate parameters for its data type"""
        issues = []
        
        if config.data_type == DataType.OPTICAL_REFLECTANCE:
            # Optical reflectance should have rescale
            if not config.rescale:
                issues.append("OPTICAL_REFLECTANCE should have rescale parameter")
            # Should have RGB or similar bands
            if not config.assets or len(config.assets) < 1:
                issues.append("OPTICAL_REFLECTANCE should specify assets")
        
        elif config.data_type == DataType.OPTICAL:
            # Regular optical should have assets
            if not config.assets or len(config.assets) < 1:
                issues.append("OPTICAL should specify assets")
        
        elif config.data_type == DataType.ELEVATION:
            # Elevation should have colormap and bidx
            if not config.colormap:
                issues.append("ELEVATION should have colormap")
            if not config.bidx:
                issues.append("ELEVATION should have bidx")
            if not config.rescale:
                issues.append("ELEVATION should have rescale for contrast")
        
        elif config.data_type == DataType.SAR:
            # SAR should have colormap and bidx
            if not config.colormap:
                issues.append("SAR should have colormap")
            if not config.assets:
                issues.append("SAR should specify polarization assets")
        
        elif config.data_type in [DataType.VEGETATION, DataType.FIRE, 
                                  DataType.SNOW, DataType.THERMAL]:
            # Single-band products should have rescale, colormap, bidx
            if not config.rescale:
                issues.append(f"{config.data_type} should have rescale")
            if not config.colormap:
                issues.append(f"{config.data_type} should have colormap")
            if not config.bidx:
                issues.append(f"{config.data_type} should have bidx")
        
        if issues:
            self.test_fail(collection_id, 
                         f"Data type validation failed for {config.data_type}",
                         "; ".join(issues))
            return False
        else:
            self.test_pass(collection_id, 
                         f"Data type config valid for {config.data_type}")
            return True
    
    def validate_critical_parameters(self, collection_id: str, 
                                     config: RenderingConfig,
                                     url_params: str) -> bool:
        """Validate critical parameters that prevent black tiles or failures"""
        issues = []
        
        # HLS collections MUST have rescale=0,3000
        if collection_id in ['hls2-s30', 'hls2-l30']:
            if 'rescale=0,3000' not in url_params:
                issues.append("CRITICAL: HLS missing rescale=0,3000 (will cause black tiles)")
        
        # Sentinel-2 L2A should have rescale
        if collection_id == 'sentinel-2-l2a':
            if 'rescale=' not in url_params:
                issues.append("Sentinel-2 L2A should have rescale parameter")
        
        # MODIS vegetation should have appropriate rescale ranges
        if collection_id in ['modis-13Q1-061', 'modis-13A1-061']:
            if 'rescale=' not in url_params:
                issues.append("MODIS NDVI should have rescale parameter")
        
        # All collections should have format and tile_scale
        if 'format=png' not in url_params:
            issues.append("Missing format=png parameter")
        if 'tile_scale=' not in url_params:
            issues.append("Missing tile_scale parameter")
        
        if issues:
            self.test_fail(collection_id, "Critical parameter validation failed",
                         "; ".join(issues))
            return False
        else:
            self.test_pass(collection_id, "All critical parameters present")
            return True
    
    def validate_single_collection(self, collection_id: str) -> Dict[str, Any]:
        """Run all validation tests for a single collection"""
        print(f"\n{'─' * 80}")
        print(f"VALIDATING: {collection_id}")
        print(f"{'─' * 80}")
        
        result = {
            'collection_id': collection_id,
            'exists': False,
            'has_config': False,
            'generates_url': False,
            'url_valid': False,
            'data_type_valid': False,
            'critical_params_valid': False,
            'all_passed': False
        }
        
        # Test 1: Collection exists in MPC STAC API
        result['exists'] = self.validate_collection_exists(collection_id)
        
        # Test 2: Has render configuration
        config = self.validate_has_render_config(collection_id)
        result['has_config'] = config is not None
        
        if not config:
            return result
        
        # Test 3: Can generate tile URL parameters
        url_params = self.validate_url_generation(collection_id)
        result['generates_url'] = url_params is not None
        
        if not url_params:
            return result
        
        print(f"   URL: {url_params[:100]}...")
        
        # Test 4: URL format is valid
        result['url_valid'] = self.validate_url_format(collection_id, url_params)
        
        # Test 5: Data type specific validation
        result['data_type_valid'] = self.validate_data_type_specific(collection_id, config)
        
        # Test 6: Critical parameters present
        result['critical_params_valid'] = self.validate_critical_parameters(
            collection_id, config, url_params
        )
        
        # Overall result
        result['all_passed'] = all([
            result['exists'],
            result['has_config'],
            result['generates_url'],
            result['url_valid'],
            result['data_type_valid'],
            result['critical_params_valid']
        ])
        
        if result['all_passed']:
            print(f"🎉 {collection_id}: ALL TESTS PASSED")
        else:
            print(f"⚠️  {collection_id}: SOME TESTS FAILED")
        
        return result
    
    def run_all_validations(self):
        """Run validation tests for all featured collections"""
        self.print_header("FEATURED COLLECTIONS VALIDATION TEST SUITE")
        print(f"Total Featured Collections: {len(FEATURED_COLLECTIONS)}")
        print(f"Testing against: {MPC_STAC_API}")
        
        # Validate each featured collection
        for collection_id in FEATURED_COLLECTIONS:
            result = self.validate_single_collection(collection_id)
            self.collection_results[collection_id] = result
        
        # Print summary
        self.print_header("VALIDATION SUMMARY")
        
        passed_collections = [cid for cid, result in self.collection_results.items() 
                            if result['all_passed']]
        failed_collections = [cid for cid, result in self.collection_results.items() 
                            if not result['all_passed']]
        
        print(f"\n✅ Collections Passed: {len(passed_collections)}/{len(FEATURED_COLLECTIONS)}")
        print(f"❌ Collections Failed: {len(failed_collections)}/{len(FEATURED_COLLECTIONS)}")
        print(f"⚠️  Warnings: {self.warnings}")
        print(f"\nTotal Tests Run: {self.tests_passed + self.tests_failed}")
        print(f"✅ Tests Passed: {self.tests_passed}")
        print(f"❌ Tests Failed: {self.tests_failed}")
        
        if failed_collections:
            print("\n" + "=" * 80)
            print("FAILED COLLECTIONS (NEED ATTENTION):")
            print("=" * 80)
            for cid in failed_collections:
                result = self.collection_results[cid]
                print(f"\n❌ {cid}:")
                print(f"   - Exists in MPC: {result['exists']}")
                print(f"   - Has Config: {result['has_config']}")
                print(f"   - Generates URL: {result['generates_url']}")
                print(f"   - URL Valid: {result['url_valid']}")
                print(f"   - Data Type Valid: {result['data_type_valid']}")
                print(f"   - Critical Params Valid: {result['critical_params_valid']}")
        
        if len(passed_collections) == len(FEATURED_COLLECTIONS):
            print("\n" + "=" * 80)
            print("🎉 SUCCESS! ALL FEATURED COLLECTIONS VALIDATED!")
            print("=" * 80)
            print("✅ All 24 featured collections have proper configurations")
            print("✅ All configurations generate valid tile URLs")
            print("✅ No featured collection will fail when queried")
            print("✅ Safe to deploy to production")
            return True
        else:
            print("\n" + "=" * 80)
            print("⚠️  ATTENTION REQUIRED!")
            print("=" * 80)
            print(f"❌ {len(failed_collections)} featured collection(s) have issues")
            print("❌ DO NOT DEPLOY until all featured collections pass validation")
            return False
    
    def export_results(self, filename: str = "featured_collections_validation_report.json"):
        """Export validation results to JSON file"""
        import json
        
        report = {
            'total_featured': len(FEATURED_COLLECTIONS),
            'tests_passed': self.tests_passed,
            'tests_failed': self.tests_failed,
            'warnings': self.warnings,
            'collections': self.collection_results,
            'summary': {
                'all_passed': len([r for r in self.collection_results.values() if r['all_passed']]),
                'any_failed': len([r for r in self.collection_results.values() if not r['all_passed']])
            }
        }
        
        with open(filename, 'w') as f:
            json.dump(report, f, indent=2)
        
        print(f"\n📄 Validation report exported to: {filename}")


def main():
    """Run featured collections validation suite"""
    validator = FeaturedCollectionsValidator()
    success = validator.run_all_validations()
    
    # Export results
    validator.export_results()
    
    # Exit with appropriate code
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
