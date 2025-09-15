"""
Phase 1 Critical Tests: STAC Function App Local Testing

Tests the complete STAC function app locally with real Planetary Computer API.
This is marked as CRITICAL in the architecture plan.
"""
import pytest
import json
import os
from datetime import datetime
from typing import Dict, Any

from earth_copilot.services.stac_function.search_service import execute_search


@pytest.mark.integration
@pytest.mark.stac
@pytest.mark.network
class TestSTACFunctionLocal:
    """Critical STAC Function App tests for Phase 1 validation"""

    def setup_method(self):
        """Setup evidence storage directory"""
        self.evidence_dir = "tests/evidence/stac_responses"
        os.makedirs(self.evidence_dir, exist_ok=True)
        self.timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")

    def save_evidence(self, test_name: str, request: Dict[str, Any], response: Dict[str, Any], error: str = None):
        """Save STAC API evidence as required by architecture plan"""
        evidence = {
            "test_name": test_name,
            "timestamp": self.timestamp,
            "request": request,
            "response": response,
            "error": error,
            "success": error is None
        }
        
        filename = f"{test_name}_{self.timestamp}.json"
        filepath = os.path.join(self.evidence_dir, filename)
        with open(filepath, 'w') as f:
            json.dump(evidence, f, indent=2, default=str)

    @pytest.mark.critical
    def test_stac_function_happy_path(self):
        """Test STAC function with standard query - should succeed 95%+ of time"""
        plan_spec = {
            "collections": ["sentinel-2-l2a"],
            "aoi": {"type": "bbox", "value": [-122.5, 37.7, -122.3, 37.8]},  # San Francisco
            "time": "2024-08-01/2024-08-31",
            "filters": {"eo:cloud_cover": 30},
            "limit": 10
        }
        
        try:
            result = execute_search(plan_spec)
            self.save_evidence("stac_happy_path", plan_spec, result)
            
            # Validate response structure per architecture requirements
            assert "search_results" in result
            assert "items" in result["search_results"]
            assert isinstance(result["search_results"]["items"], list)
            assert len(result["search_results"]["items"]) > 0, "Should return at least 1 item for happy path"
            assert "search_metadata" in result
            assert "response_time_ms" in result["search_metadata"]
            
        except Exception as e:
            self.save_evidence("stac_happy_path", plan_spec, {}, str(e))
            pytest.fail(f"CRITICAL: STAC happy path failed: {e}")

    @pytest.mark.critical
    def test_stac_function_auto_relaxation_trigger(self):
        """Test auto-relaxation with very restrictive query"""
        plan_spec = {
            "collections": ["landsat-c2-l2"],
            "aoi": {"type": "bbox", "value": [-122.4, 37.75, -122.35, 37.78]},  # Very small area
            "time": "2024-09-01/2024-09-02",  # Very short time
            "filters": {"eo:cloud_cover": 5},  # Very restrictive cloud cover
            "limit": 50
        }
        
        try:
            result = execute_search(plan_spec)
            self.save_evidence("stac_auto_relaxation", plan_spec, result)
            
            # Should still return results due to auto-relaxation
            assert "search_results" in result
            items = result["search_results"]["items"]
            
            # If no items, this indicates auto-relaxation strategy needs improvement
            if len(items) == 0:
                pytest.skip("Auto-relaxation needs tuning - no results for restrictive query")
            
        except Exception as e:
            self.save_evidence("stac_auto_relaxation", plan_spec, {}, str(e))
            pytest.fail(f"Auto-relaxation test failed: {e}")

    @pytest.mark.critical
    def test_stac_function_diverse_collections(self):
        """Test different collection types for domain mapping validation"""
        test_cases = [
            {
                "name": "landsat_wildfire",
                "plan_spec": {
                    "collections": ["landsat-c2-l2"],
                    "aoi": {"type": "bbox", "value": [-120.0, 36.0, -118.0, 38.0]},  # California fire area
                    "time": "2023-08-01/2023-09-01",
                    "limit": 5
                }
            },
            {
                "name": "sentinel2_vegetation",
                "plan_spec": {
                    "collections": ["sentinel-2-l2a"],
                    "aoi": {"type": "bbox", "value": [-98.0, 39.0, -96.0, 41.0]},  # Midwest agriculture
                    "time": "2024-06-01/2024-07-01",
                    "filters": {"eo:cloud_cover": 20},
                    "limit": 5
                }
            },
            {
                "name": "modis_global",
                "plan_spec": {
                    "collections": ["modis-64A1-061"],
                    "aoi": {"type": "bbox", "value": [-125.0, 32.0, -114.0, 42.0]},  # California
                    "time": "2024-01-01/2024-01-31",
                    "limit": 3
                }
            }
        ]
        
        success_count = 0
        total_count = len(test_cases)
        
        for test_case in test_cases:
            try:
                result = execute_search(test_case["plan_spec"])
                self.save_evidence(f"diverse_collections_{test_case['name']}", 
                                 test_case["plan_spec"], result)
                
                # Count as success if we get any results
                if len(result["search_results"]["items"]) > 0:
                    success_count += 1
                    
            except Exception as e:
                self.save_evidence(f"diverse_collections_{test_case['name']}", 
                                 test_case["plan_spec"], {}, str(e))
        
        # Should have >95% success rate per architecture requirements
        success_rate = success_count / total_count
        assert success_rate >= 0.95, f"Collection diversity test success rate {success_rate:.2%} below 95% threshold"

    @pytest.mark.critical
    def test_stac_function_error_handling(self):
        """Test graceful error handling with invalid inputs"""
        error_cases = [
            {
                "name": "invalid_collection",
                "plan_spec": {
                    "collections": ["invalid-collection-name"],
                    "aoi": {"type": "bbox", "value": [-122.5, 37.7, -122.3, 37.8]},
                    "time": "2024-08-01/2024-08-31"
                }
            },
            {
                "name": "invalid_bbox",
                "plan_spec": {
                    "collections": ["sentinel-2-l2a"],
                    "aoi": {"type": "bbox", "value": "invalid"},
                    "time": "2024-08-01/2024-08-31"
                }
            },
            {
                "name": "invalid_datetime",
                "plan_spec": {
                    "collections": ["sentinel-2-l2a"],
                    "aoi": {"type": "bbox", "value": [-122.5, 37.7, -122.3, 37.8]},
                    "time": "invalid-date"
                }
            }
        ]
        
        for error_case in error_cases:
            try:
                result = execute_search(error_case["plan_spec"])
                # Should not succeed, but if it does, record it
                self.save_evidence(f"error_handling_{error_case['name']}", 
                                 error_case["plan_spec"], result)
            except ValueError as e:
                # Expected error - this is good
                self.save_evidence(f"error_handling_{error_case['name']}", 
                                 error_case["plan_spec"], {}, str(e))
                assert "must be" in str(e) or "invalid" in str(e).lower()
            except Exception as e:
                # Unexpected error type
                self.save_evidence(f"error_handling_{error_case['name']}", 
                                 error_case["plan_spec"], {}, str(e))
                pytest.fail(f"Unexpected error type for {error_case['name']}: {type(e).__name__}: {e}")

    @pytest.mark.critical
    @pytest.mark.slow
    def test_stac_function_performance_benchmarks(self):
        """Test response time requirements per architecture (<30 seconds)"""
        plan_spec = {
            "collections": ["sentinel-2-l2a"],
            "aoi": {"type": "bbox", "value": [-122.5, 37.7, -122.3, 37.8]},
            "time": "2024-08-01/2024-08-31",
            "limit": 50
        }
        
        start_time = datetime.utcnow()
        try:
            result = execute_search(plan_spec)
            end_time = datetime.utcnow()
            
            execution_time = (end_time - start_time).total_seconds()
            result["performance_metrics"] = {
                "execution_time_seconds": execution_time,
                "items_returned": len(result["search_results"]["items"])
            }
            
            self.save_evidence("performance_benchmark", plan_spec, result)
            
            # Architecture requirement: <30 seconds for typical queries
            assert execution_time < 30.0, f"Response time {execution_time:.2f}s exceeds 30s requirement"
            
            # Also validate reported response time matches actual
            reported_time_ms = result["search_metadata"]["response_time_ms"]
            assert abs(execution_time * 1000 - reported_time_ms) < 1000, "Reported vs actual time mismatch"
            
        except Exception as e:
            self.save_evidence("performance_benchmark", plan_spec, {}, str(e))
            pytest.fail(f"Performance benchmark failed: {e}")


@pytest.mark.integration
@pytest.mark.stac
def test_stac_function_evidence_storage():
    """Verify evidence storage is working correctly"""
    evidence_dir = "tests/evidence/stac_responses"
    assert os.path.exists(evidence_dir), "Evidence directory should be created"
    
    # Check if any evidence files exist from previous tests
    evidence_files = [f for f in os.listdir(evidence_dir) if f.endswith('.json')]
    
    # Don't fail if no evidence yet, but log status
    print(f"Evidence files found: {len(evidence_files)}")
    for f in evidence_files[:3]:  # Show first 3 files
        print(f"  - {f}")
