# Copyright (c) Microsoft Corporation.
# Licensed under the MIT license.

"""
End-to-End STAC Tests
Tests actual STAC API calls
"""
import sys
import os
import pytest

# Set up path - adjust for being in tests/e2e
current_dir = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.join(current_dir, '..', '..')
sys.path.insert(0, project_root)

@pytest.mark.integration
def test_stac_search_real_api():
    """Test STAC search with real Planetary Computer API"""
    try:
        from earth_copilot.services.stac_function.search_service import execute_search
        
        plan_spec = {
            'collections': ['sentinel-2-l2a'],
            'aoi': {'type': 'bbox', 'value': [-122.5, 37.7, -122.3, 37.8]},
            'time': '2024-08-01/2024-08-31',
            'filters': {'eo:cloud_cover': 30},
            'limit': 2
        }
        
        result = execute_search(plan_spec)
        
        assert result is not None
        assert 'search_results' in result
        assert 'search_metadata' in result
        
        items_count = len(result['search_results']['items'])
        response_time = result['search_metadata']['response_time_ms']
        
        print(f'Items returned: {items_count}')
        print(f'Response time: {response_time:.1f}ms')
        
        if result['search_results']['items']:
            item = result['search_results']['items'][0]
            assert 'id' in item
            assert 'collection' in item
            
    except ImportError:
        pytest.skip("STAC search service not available")
    except Exception as e:
        pytest.fail(f"STAC search test failed: {e}")

if __name__ == "__main__":
    pytest.main([__file__, "-v"])
