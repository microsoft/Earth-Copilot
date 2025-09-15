# Copyright (c) Microsoft Corporation.
# Licensed under the MIT license.

"""
End-to-End API Tests
Tests actual FastAPI endpoints
"""
import sys
import os
import pytest

# Set up path - adjust for being in tests/e2e
current_dir = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.join(current_dir, '..', '..')
sys.path.insert(0, project_root)

from fastapi.testclient import TestClient

def test_health_endpoint():
    """Test the health endpoint"""
    try:
        from earth_copilot.app import app
        client = TestClient(app)
        
        response = client.get("/health")
        assert response.status_code == 200
        data = response.json()
        assert "status" in data
        
    except ImportError:
        pytest.skip("App module not available")
    except Exception as e:
        pytest.fail(f"Health endpoint test failed: {e}")

def test_query_endpoint():
    """Test the query endpoint"""
    try:
        from earth_copilot.app import app
        client = TestClient(app)
        
        payload = {"query": "Show me satellite imagery of San Francisco"}
        response = client.post("/query", json=payload)
        
        # Should get some response (200 or error, but not 404)
        assert response.status_code != 404
        
        if response.status_code == 200:
            data = response.json()
            assert "success" in data
            
    except ImportError:
        pytest.skip("App module not available")
    except Exception as e:
        pytest.fail(f"Query endpoint test failed: {e}")

if __name__ == "__main__":
    pytest.main([__file__, "-v"])
