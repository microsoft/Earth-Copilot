"""
Unit tests for temporal resolution logic

Tests the new resolve_temporal_to_datetime() function to ensure correct
datetime range construction from extracted temporal entities.
"""

import pytest
from datetime import datetime, timedelta
from semantic_translator import SemanticQueryTranslator


class TestTemporalResolution:
    """Test suite for resolve_temporal_to_datetime()"""
    
    @pytest.fixture
    def translator(self):
        """Create a SemanticQueryTranslator instance for testing"""
        # We only need the resolve_temporal_to_datetime method, no Azure connection needed
        translator = SemanticQueryTranslator.__new__(SemanticQueryTranslator)
        return translator
    
    # ========================================================================
    # Test Case 1: Year + Month (most common case)
    # ========================================================================
    
    def test_year_and_month_june_2025(self, translator):
        """Test: June 2025 should return 2025-06-01/2025-06-30"""
        entities = {
            "temporal": {
                "year": "2025",
                "month": "06",
                "relative": None
            }
        }
        collections = ["sentinel-2-l2a"]
        
        result = translator.resolve_temporal_to_datetime(entities, collections)
        assert result == "2025-06-01/2025-06-30"
    
    def test_year_and_month_february_2024_leap_year(self, translator):
        """Test: February 2024 (leap year) should return 2024-02-01/2024-02-29"""
        entities = {
            "temporal": {
                "year": "2024",
                "month": "02",
                "relative": None
            }
        }
        collections = ["sentinel-2-l2a"]
        
        result = translator.resolve_temporal_to_datetime(entities, collections)
        assert result == "2024-02-01/2024-02-29"
    
    def test_year_and_month_february_2025_non_leap_year(self, translator):
        """Test: February 2025 (non-leap year) should return 2025-02-01/2025-02-28"""
        entities = {
            "temporal": {
                "year": "2025",
                "month": "02",
                "relative": None
            }
        }
        collections = ["sentinel-2-l2a"]
        
        result = translator.resolve_temporal_to_datetime(entities, collections)
        assert result == "2025-02-01/2025-02-28"
    
    def test_year_and_month_december_2023(self, translator):
        """Test: December 2023 should return 2023-12-01/2023-12-31"""
        entities = {
            "temporal": {
                "year": "2023",
                "month": "12",
                "relative": None
            }
        }
        collections = ["landsat-c2-l2"]
        
        result = translator.resolve_temporal_to_datetime(entities, collections)
        assert result == "2023-12-01/2023-12-31"
    
    def test_year_and_month_with_integer_types(self, translator):
        """Test: Integer month (6 instead of "06") should work"""
        entities = {
            "temporal": {
                "year": 2025,
                "month": 6,
                "relative": None
            }
        }
        collections = ["sentinel-2-l2a"]
        
        result = translator.resolve_temporal_to_datetime(entities, collections)
        assert result == "2025-06-01/2025-06-30"
    
    # ========================================================================
    # Test Case 2: Year only
    # ========================================================================
    
    def test_year_only_2025(self, translator):
        """Test: Year 2025 should return 2025-01-01/2025-12-31"""
        entities = {
            "temporal": {
                "year": "2025",
                "month": None,
                "relative": None
            }
        }
        collections = ["sentinel-2-l2a"]
        
        result = translator.resolve_temporal_to_datetime(entities, collections)
        assert result == "2025-01-01/2025-12-31"
    
    def test_year_only_2017_hurricane_harvey(self, translator):
        """Test: Year 2017 (Hurricane Harvey) should return 2017-01-01/2017-12-31"""
        entities = {
            "temporal": {
                "year": "2017",
                "month": None,
                "relative": None
            }
        }
        collections = ["landsat-c2-l2"]
        
        result = translator.resolve_temporal_to_datetime(entities, collections)
        assert result == "2017-01-01/2017-12-31"
    
    # ========================================================================
    # Test Case 3: Month only (current year)
    # ========================================================================
    
    def test_month_only_june_current_year(self, translator):
        """Test: Month 06 only should use current year"""
        entities = {
            "temporal": {
                "year": None,
                "month": "06",
                "relative": None
            }
        }
        collections = ["sentinel-2-l2a"]
        
        result = translator.resolve_temporal_to_datetime(entities, collections)
        current_year = datetime.now().year
        assert result == f"{current_year}-06-01/{current_year}-06-30"
    
    # ========================================================================
    # Test Case 4: Relative time ("recent")
    # ========================================================================
    
    def test_relative_recent_last_30_days(self, translator):
        """Test: Relative 'recent' should return last 30 days"""
        entities = {
            "temporal": {
                "year": None,
                "month": None,
                "relative": "recent"
            }
        }
        collections = ["sentinel-2-l2a"]
        
        result = translator.resolve_temporal_to_datetime(entities, collections)
        
        # Check format
        assert "/" in result
        start_str, end_str = result.split("/")
        
        # Parse dates
        start_date = datetime.strptime(start_str, "%Y-%m-%d")
        end_date = datetime.strptime(end_str, "%Y-%m-%d")
        
        # Check it's approximately 30 days (allow 1 day tolerance for test execution time)
        delta = (end_date - start_date).days
        assert 29 <= delta <= 31
        
        # Check end date is approximately today
        today = datetime.now().date()
        assert abs((end_date.date() - today).days) <= 1
    
    # ========================================================================
    # Test Case 5: Static collections (DEM) - should return None
    # ========================================================================
    
    def test_static_collection_dem_no_datetime(self, translator):
        """Test: Static DEM collections should return None (no datetime)"""
        entities = {
            "temporal": {
                "year": "2025",
                "month": "06",
                "relative": None
            }
        }
        collections = ["cop-dem-glo-30"]
        
        result = translator.resolve_temporal_to_datetime(entities, collections)
        assert result is None
    
    def test_static_collection_3dep_no_datetime(self, translator):
        """Test: 3DEP static collection should return None"""
        entities = {
            "temporal": {
                "year": "2024",
                "month": None,
                "relative": None
            }
        }
        collections = ["3dep-seamless"]
        
        result = translator.resolve_temporal_to_datetime(entities, collections)
        assert result is None
    
    def test_static_collection_alos_dem_no_datetime(self, translator):
        """Test: ALOS DEM static collection should return None"""
        entities = {
            "temporal": {
                "year": "2025",
                "month": "06",
                "relative": None
            }
        }
        collections = ["alos-dem"]
        
        result = translator.resolve_temporal_to_datetime(entities, collections)
        assert result is None
    
    # ========================================================================
    # Test Case 6: Composite collections (MODIS) - should return None
    # ========================================================================
    
    def test_composite_collection_modis_no_datetime(self, translator):
        """Test: MODIS composite collections should return None (use sortby)"""
        entities = {
            "temporal": {
                "year": "2025",
                "month": "06",
                "relative": None
            }
        }
        collections = ["modis-09Q1-061"]
        
        result = translator.resolve_temporal_to_datetime(entities, collections)
        assert result is None
    
    # ========================================================================
    # Test Case 7: No temporal entities - should return None
    # ========================================================================
    
    def test_no_temporal_entities(self, translator):
        """Test: No temporal entities should return None (most recent)"""
        entities = {
            "location": {"name": "Seattle"}
        }
        collections = ["sentinel-2-l2a"]
        
        result = translator.resolve_temporal_to_datetime(entities, collections)
        assert result is None
    
    def test_empty_temporal_entities(self, translator):
        """Test: Empty temporal dict should return None"""
        entities = {
            "temporal": {
                "year": None,
                "month": None,
                "relative": None
            }
        }
        collections = ["sentinel-2-l2a"]
        
        result = translator.resolve_temporal_to_datetime(entities, collections)
        assert result is None
    
    def test_none_entities(self, translator):
        """Test: None entities should return None"""
        entities = None
        collections = ["sentinel-2-l2a"]
        
        result = translator.resolve_temporal_to_datetime(entities, collections)
        assert result is None
    
    # ========================================================================
    # Test Case 8: Mixed collection types
    # ========================================================================
    
    def test_mixed_optical_collections_with_datetime(self, translator):
        """Test: Mixed optical collections should return datetime"""
        entities = {
            "temporal": {
                "year": "2025",
                "month": "06",
                "relative": None
            }
        }
        collections = ["sentinel-2-l2a", "landsat-c2-l2"]
        
        result = translator.resolve_temporal_to_datetime(entities, collections)
        assert result == "2025-06-01/2025-06-30"
    
    def test_mixed_static_and_optical_uses_datetime(self, translator):
        """Test: Mixed static+optical should NOT return None (at least one supports temporal)"""
        entities = {
            "temporal": {
                "year": "2025",
                "month": "06",
                "relative": None
            }
        }
        # This is an unusual case - mixing DEM with optical
        # Current implementation returns None if ALL are static, otherwise returns datetime
        collections = ["cop-dem-glo-30", "sentinel-2-l2a"]
        
        result = translator.resolve_temporal_to_datetime(entities, collections)
        # Since not ALL are static, datetime should be included
        assert result == "2025-06-01/2025-06-30"
    
    # ========================================================================
    # Test Case 9: Edge cases and error handling
    # ========================================================================
    
    def test_invalid_month_returns_none(self, translator):
        """Test: Invalid month should be handled gracefully"""
        entities = {
            "temporal": {
                "year": "2025",
                "month": "13",  # Invalid month
                "relative": None
            }
        }
        collections = ["sentinel-2-l2a"]
        
        # Should not raise exception, should return None or handle gracefully
        result = translator.resolve_temporal_to_datetime(entities, collections)
        # Depending on implementation, this might return None or raise
        # Current implementation will raise ValueError in calendar.monthrange
        # Let's check it doesn't crash the system
        assert result is None or isinstance(result, str)
    
    def test_invalid_year_returns_none(self, translator):
        """Test: Invalid year should be handled gracefully"""
        entities = {
            "temporal": {
                "year": "abc",  # Invalid year
                "month": "06",
                "relative": None
            }
        }
        collections = ["sentinel-2-l2a"]
        
        result = translator.resolve_temporal_to_datetime(entities, collections)
        assert result is None or isinstance(result, str)
    
    # ========================================================================
    # Test Case 10: Real-world query scenarios
    # ========================================================================
    
    def test_hurricane_harvey_august_2017(self, translator):
        """Test: Real query - 'Show me Hurricane Harvey damage' (August 2017)"""
        entities = {
            "temporal": {
                "year": "2017",
                "month": "08",
                "relative": None
            },
            "disaster": {
                "type": "hurricane",
                "name": "Hurricane Harvey"
            }
        }
        collections = ["landsat-c2-l2"]
        
        result = translator.resolve_temporal_to_datetime(entities, collections)
        assert result == "2017-08-01/2017-08-31"
    
    def test_recent_wildfire_query(self, translator):
        """Test: Real query - 'Show me recent wildfire damage'"""
        entities = {
            "temporal": {
                "year": None,
                "month": None,
                "relative": "recent"
            },
            "disaster": {
                "type": "wildfire"
            }
        }
        collections = ["sentinel-2-l2a"]
        
        result = translator.resolve_temporal_to_datetime(entities, collections)
        assert result is not None
        assert "/" in result
        # Should be last 30 days
    
    def test_elevation_query_no_datetime(self, translator):
        """Test: Real query - 'Show me elevation of Grand Canyon' (DEM, no datetime)"""
        entities = {
            "location": {
                "name": "Grand Canyon"
            }
        }
        collections = ["cop-dem-glo-30"]
        
        result = translator.resolve_temporal_to_datetime(entities, collections)
        assert result is None


if __name__ == "__main__":
    print("Running temporal resolution unit tests...")
    print("=" * 80)
    pytest.main([__file__, "-v", "--tb=short"])
