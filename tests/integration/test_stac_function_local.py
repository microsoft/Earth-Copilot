# Copyright (c) Microsoft Corporation.
# Licensed under the MIT license.

"""
Integration tests for STAC Function Local Adapter

Tests the FastAPI adapter that mimics Azure Function behavior for local development.
"""
import pytest
from fastapi.testclient import TestClient

from earth_copilot.services.stac_function.app_adapter import app


@pytest.fixture(scope="module")
def client():
    """FastAPI test client for STAC function adapter"""
    return TestClient(app)


@pytest.fixture
def example_plan_spec():
    """Standard test plan specification"""
    return {
        "aoi": {"type": "bbox", "value": [-123.3, 37.1, -121.8, 38.2]},
        "time": "2025-08-01/2025-09-01",
        "collections": ["sentinel-2-l2a"],
        "filters": {"eo:cloud_cover": 20},  # Fixed: should be a simple number, not a nested dict
        "limit": 10,
    }


@pytest.mark.integration
@pytest.mark.stac
def test_health_endpoint(client):
    """Test that the health endpoint returns success"""
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json().get("status") == "healthy"


@pytest.mark.integration
@pytest.mark.stac
def test_search_endpoint_with_mock(client, example_plan_spec, monkeypatch):
    """Test search endpoint with mocked STAC client"""
    # Mock the pystac_client and planetary_computer directly
    import earth_copilot.services.stac_function.search_service as search_service

    class MockSTACClient:
        def search(self, collections=None, bbox=None, datetime=None, query=None, limit=10):
            class MockSearchResult:
                def items(self):
                    # Create mock STAC items that have a to_dict method
                    class MockItem:
                        def __init__(self, id, collection, bbox):
                            self.id = id
                            self.collection = collection
                            self.bbox = bbox
                            
                        def to_dict(self):
                            return {
                                "id": self.id, 
                                "type": "Feature",
                                "collection": self.collection, 
                                "bbox": self.bbox, 
                                "geometry": {"type": "Point", "coordinates": [self.bbox[0], self.bbox[1]]}, 
                                "properties": {"eo:cloud_cover": 5, "datetime": "2025-08-15T10:30:00Z"}
                            }
                    
                    items = [
                        MockItem("item1", collections[0] if collections else "sentinel-2-l2a", bbox),
                        MockItem("item2", collections[0] if collections else "sentinel-2-l2a", bbox),
                    ]
                    return items[:limit]
            
            return MockSearchResult()
        
        @staticmethod
        def open(url, modifier=None):
            return MockSTACClient()

    # Mock the planetary computer client
    monkeypatch.setattr(search_service, "pystac_client", type('MockModule', (), {'Client': MockSTACClient})())
    monkeypatch.setattr(search_service, "STAC_AVAILABLE", True)

    # Test the search endpoint
    payload = {
        "plan_spec": example_plan_spec, 
        "search_preferences": {}
    }
    response = client.post("/search", json=payload)
    
    assert response.status_code == 200
    data = response.json()
    assert data.get("success") is True
    assert "search_results" in data
    assert isinstance(data["search_results"].get("items", []), list)
    assert len(data["search_results"]["items"]) > 0


@pytest.mark.integration
@pytest.mark.stac
@pytest.mark.network
def test_search_endpoint_real_network(client, example_plan_spec):
    """Test search endpoint with real network calls (marked as network test)"""
    payload = {
        "plan_spec": example_plan_spec, 
        "search_preferences": {}
    }
    response = client.post("/search", json=payload)
    
    # Should succeed even with real network (though might be slow)
    assert response.status_code == 200
    data = response.json()
    assert "search_results" in data
