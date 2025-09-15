"""
Test Configuration and Fixtures

Shared configuration and fixtures for the Earth Copilot test suite.
"""
import os
import pytest
from typing import Dict, Any

# Test environment configuration
TEST_ENV = {
    "STAC_FUNCTION_URL": "http://testserver",
    "USE_STAC_FUNCTION": "true",
    "AZURE_OPENAI_API_KEY": "test-key",
    "AZURE_OPENAI_ENDPOINT": "https://test.openai.azure.com/",
    "PLANETARY_COMPUTER_API_URL": "https://planetarycomputer.microsoft.com/api/stac/v1"
}


@pytest.fixture(autouse=True)
def setup_test_environment(monkeypatch):
    """Automatically configure test environment for all tests"""
    for key, value in TEST_ENV.items():
        monkeypatch.setenv(key, value)


@pytest.fixture
def sample_bbox():
    """Standard test bounding box (San Francisco Bay Area)"""
    return [-123.3, 37.1, -121.8, 38.2]


@pytest.fixture
def sample_datetime():
    """Standard test datetime range"""
    return "2025-08-01/2025-09-01"


@pytest.fixture
def sample_collections():
    """Standard test collections"""
    return ["sentinel-2-l2a"]


@pytest.fixture
def sample_filters():
    """Standard test filters"""
    return {"eo:cloud_cover": {"lt": 20}}


@pytest.fixture
def basic_plan_spec(sample_bbox, sample_datetime, sample_collections, sample_filters):
    """Basic plan specification for testing"""
    return {
        "aoi": {"type": "bbox", "value": sample_bbox},
        "time": sample_datetime,
        "collections": sample_collections,
        "filters": sample_filters,
        "limit": 10,
    }


@pytest.fixture
def mock_stac_response():
    """Mock STAC API response"""
    return {
        "type": "FeatureCollection",
        "features": [
            {
                "id": "test-item-1",
                "type": "Feature",
                "collection": "sentinel-2-l2a",
                "bbox": [-123.0, 37.5, -122.0, 38.0],
                "geometry": {
                    "type": "Polygon",
                    "coordinates": [[
                        [-123.0, 37.5], [-122.0, 37.5], 
                        [-122.0, 38.0], [-123.0, 38.0], 
                        [-123.0, 37.5]
                    ]]
                },
                "properties": {
                    "datetime": "2025-08-15T10:30:00Z",
                    "eo:cloud_cover": 15,
                    "platform": "sentinel-2a"
                }
            }
        ]
    }


@pytest.fixture
def mock_agent_request():
    """Mock agent request structure"""
    return {
        "agent_name": "TestAgent",
        "request_id": "test-123",
        "user_query": "Show me satellite imagery of San Francisco",
        "context": {}
    }
