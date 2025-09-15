# Copyright (c) Microsoft Corporation.
# Licensed under the MIT license.

"""
Automated test suite for Semantic Kernel translator functionality
Tests entity extraction, bbox resolution, and STAC query generation across diverse queries
"""

import asyncio
import json
import pytest
import logging
from typing import Dict, List, Any, Optional
from datetime import datetime
import sys
import os

# Add the router function app to the path
sys.path.append(os.path.join(os.path.dirname(__file__), '..', 'router_function_app'))

from semantic_translator import SemanticQueryTranslator

# Test configuration
AZURE_OPENAI_ENDPOINT = os.getenv("AZURE_OPENAI_ENDPOINT", "https://your-endpoint.openai.azure.com/")
AZURE_OPENAI_API_KEY = os.getenv("AZURE_OPENAI_API_KEY", "your-key")
MODEL_NAME = os.getenv("AZURE_OPENAI_MODEL", "gpt-5")

# Comprehensive test cases covering diverse scenarios
TEST_QUERIES = [
    # California wildfire queries - various specificity levels
    {
        "query": "Show me wildfire damage assessment in California from September 2023",
        "expected": {
            "location": {"name": "California", "type": "state"},
            "temporal": {"year": "2023", "month": "09"},
            "disaster": {"type": "wildfire"},
            "analysis_intent": {"type": "damage_analysis"}
        },
        "expected_bbox": ["-124.7", "32.5", "-114.1", "42.0"],  # Approximate California bounds
        "expected_collections": ["modis-14A1-061", "modis-14A2-061", "sentinel-2-l2a"]
    },
    
    # Hurricane with specific event name
    {
        "query": "Analyze Hurricane Ida damage in Louisiana August 2021",
        "expected": {
            "location": {"name": "Louisiana", "type": "state"},
            "temporal": {"year": "2021", "month": "08"},
            "disaster": {"type": "hurricane", "name": "Ida"},
            "analysis_intent": {"type": "damage_analysis"}
        },
        "expected_bbox": ["-94.0", "28.9", "-88.8", "33.0"],  # Approximate Louisiana bounds
        "expected_collections": ["sentinel-1-grd", "sentinel-2-l2a"]
    },
    
    # Flooding with city-level location
    {
        "query": "Show flooding in Houston Texas after recent storms",
        "expected": {
            "location": {"name": "Houston", "type": "city"},
            "temporal": {"relative": "recent"},
            "disaster": {"type": "flood"},
            "analysis_intent": {"type": "impact_assessment"}
        },
        "expected_bbox": ["-95.8", "29.5", "-95.0", "30.1"],  # Approximate Houston bounds
        "expected_collections": ["sentinel-1-grd", "sentinel-2-l2a"]
    },
    
    # Earthquake damage assessment
    {
        "query": "Earthquake damage assessment Turkey February 2023",
        "expected": {
            "location": {"name": "Turkey", "type": "country"},
            "temporal": {"year": "2023", "month": "02"},
            "disaster": {"type": "earthquake"},
            "analysis_intent": {"type": "damage_analysis"}
        },
        "expected_bbox": ["26.0", "35.8", "45.0", "42.1"],  # Approximate Turkey bounds
        "expected_collections": ["sentinel-1-grd", "alos-dem"]
    },
    
    # Wildfire with less specific temporal info
    {
        "query": "Recent wildfire activity in Australia",
        "expected": {
            "location": {"name": "Australia", "type": "country"},
            "temporal": {"relative": "recent"},
            "disaster": {"type": "wildfire"},
            "analysis_intent": {"type": "impact_assessment"}
        },
        "expected_bbox": ["113.0", "-44.0", "154.0", "-10.0"],  # Approximate Australia bounds
        "expected_collections": ["modis-14A1-061", "modis-14A2-061"]
    },
    
    # Recovery monitoring query
    {
        "query": "Monitor recovery progress in Puerto Rico after hurricanes",
        "expected": {
            "location": {"name": "Puerto Rico", "type": "region"},
            "disaster": {"type": "hurricane"},
            "analysis_intent": {"type": "recovery_monitoring"}
        },
        "expected_bbox": ["-67.3", "17.9", "-65.2", "18.5"],  # Approximate Puerto Rico bounds
        "expected_collections": ["sentinel-2-l2a", "landsat-c2-l2"]
    },
    
    # General satellite imagery (no disaster)
    {
        "query": "Show me satellite images of New York City from 2024",
        "expected": {
            "location": {"name": "New York City", "type": "city"},
            "temporal": {"year": "2024"},
            "disaster": {"type": None},
            "analysis_intent": {"type": "general_imagery"}
        },
        "expected_bbox": ["-74.3", "40.5", "-73.7", "40.9"],  # Approximate NYC bounds
        "expected_collections": ["sentinel-2-l2a", "landsat-c2-l2"]
    },
    
    # Tornado damage with state and season
    {
        "query": "Tornado damage in Oklahoma during spring 2024",
        "expected": {
            "location": {"name": "Oklahoma", "type": "state"},
            "temporal": {"year": "2024", "season": "spring"},
            "disaster": {"type": "tornado"},
            "analysis_intent": {"type": "damage_analysis"}
        },
        "expected_bbox": ["-103.0", "33.6", "-94.4", "37.0"],  # Approximate Oklahoma bounds
        "expected_collections": ["sentinel-2-l2a", "landsat-c2-l2"]
    }
]

class TestSemanticTranslator:
    """Automated test suite for semantic translator functionality"""
    
    @classmethod
    def setup_class(cls):
        """Initialize translator for all tests"""
        try:
            cls.translator = SemanticQueryTranslator(
                azure_openai_endpoint=AZURE_OPENAI_ENDPOINT,
                azure_openai_api_key=AZURE_OPENAI_API_KEY,
                model_name=MODEL_NAME
            )
        except Exception as e:
            pytest.skip(f"Could not initialize semantic translator: {e}")
    
    @pytest.mark.asyncio
    async def test_entity_extraction_comprehensive(self):
        """Test entity extraction across all diverse queries"""
        results = []
        
        for i, test_case in enumerate(TEST_QUERIES):
            query = test_case["query"]
            expected = test_case["expected"]
            
            print(f"\n--- Test {i+1}: {query} ---")
            
            try:
                # Extract entities
                entities = await self.translator.extract_entities(query)
                
                # Validate extracted entities
                validation_result = self._validate_extraction(entities, expected, query)
                results.append({
                    "query": query,
                    "entities": entities,
                    "validation": validation_result,
                    "passed": validation_result["overall_score"] >= 0.7
                })
                
                print(f"Entities: {json.dumps(entities, indent=2)}")
                print(f"Validation Score: {validation_result['overall_score']:.2f}")
                
            except Exception as e:
                print(f"ERROR: {e}")
                results.append({
                    "query": query,
                    "entities": None,
                    "validation": {"overall_score": 0.0, "error": str(e)},
                    "passed": False
                })
        
        # Print summary
        passed = sum(1 for r in results if r["passed"])
        total = len(results)
        print(f"\n=== ENTITY EXTRACTION SUMMARY ===")
        print(f"Passed: {passed}/{total} ({passed/total*100:.1f}%)")
        
        for i, result in enumerate(results):
            status = "✓" if result["passed"] else "✗"
            score = result["validation"]["overall_score"]
            print(f"{status} Test {i+1}: {score:.2f} - {TEST_QUERIES[i]['query'][:60]}...")
        
        # Assert that most tests passed
        assert passed >= total * 0.7, f"Only {passed}/{total} tests passed. Expected at least 70%"
    
    @pytest.mark.asyncio
    async def test_bbox_resolution(self):
        """Test geographic bbox resolution for various locations"""
        bbox_results = []
        
        for i, test_case in enumerate(TEST_QUERIES):
            query = test_case["query"]
            expected_bbox = test_case.get("expected_bbox")
            
            if not expected_bbox:
                continue
                
            print(f"\n--- Bbox Test {i+1}: {query} ---")
            
            try:
                # First extract entities to get location
                entities = await self.translator.extract_entities(query)
                location_name = entities.get("location", {}).get("name")
                
                if location_name:
                    # Resolve location to bbox
                    bbox = await self.translator.resolve_location_to_bbox(location_name)
                    
                    # Validate bbox format and reasonableness
                    bbox_validation = self._validate_bbox(bbox, expected_bbox, location_name)
                    bbox_results.append({
                        "location": location_name,
                        "bbox": bbox,
                        "expected_bbox": expected_bbox,
                        "validation": bbox_validation,
                        "passed": bbox_validation["valid"]
                    })
                    
                    print(f"Location: {location_name}")
                    print(f"Bbox: {bbox}")
                    print(f"Expected: {expected_bbox}")
                    print(f"Valid: {bbox_validation['valid']}")
                    
                else:
                    print(f"No location extracted from query")
                    bbox_results.append({
                        "location": None,
                        "bbox": None,
                        "passed": False
                    })
                    
            except Exception as e:
                print(f"ERROR: {e}")
                bbox_results.append({
                    "location": entities.get("location", {}).get("name") if 'entities' in locals() else None,
                    "bbox": None,
                    "error": str(e),
                    "passed": False
                })
        
        # Print bbox summary
        passed = sum(1 for r in bbox_results if r["passed"])
        total = len(bbox_results)
        print(f"\n=== BBOX RESOLUTION SUMMARY ===")
        print(f"Passed: {passed}/{total} ({passed/total*100:.1f}%)")
        
        for result in bbox_results:
            status = "✓" if result["passed"] else "✗"
            print(f"{status} {result['location']}: {result.get('bbox', 'Failed')}")
        
        # Assert that most bbox resolutions worked
        assert passed >= total * 0.6, f"Only {passed}/{total} bbox resolutions passed. Expected at least 60%"
    
    @pytest.mark.asyncio
    async def test_stac_query_generation(self):
        """Test complete STAC query generation pipeline"""
        stac_results = []
        
        for i, test_case in enumerate(TEST_QUERIES):
            query = test_case["query"]
            expected_collections = test_case.get("expected_collections", [])
            
            print(f"\n--- STAC Test {i+1}: {query} ---")
            
            try:
                # Generate complete STAC query
                stac_query = await self.translator.translate_query(query)
                
                # Validate STAC query structure and collections
                stac_validation = self._validate_stac_query(stac_query, expected_collections, query)
                stac_results.append({
                    "query": query,
                    "stac_query": stac_query,
                    "validation": stac_validation,
                    "passed": stac_validation["valid"]
                })
                
                print(f"Collections: {stac_query.get('collections', [])}")
                print(f"Bbox: {stac_query.get('bbox')}")
                print(f"Datetime: {stac_query.get('datetime')}")
                print(f"Valid: {stac_validation['valid']}")
                
            except Exception as e:
                print(f"ERROR: {e}")
                stac_results.append({
                    "query": query,
                    "stac_query": None,
                    "error": str(e),
                    "passed": False
                })
        
        # Print STAC summary
        passed = sum(1 for r in stac_results if r["passed"])
        total = len(stac_results)
        print(f"\n=== STAC QUERY GENERATION SUMMARY ===")
        print(f"Passed: {passed}/{total} ({passed/total*100:.1f}%)")
        
        for i, result in enumerate(stac_results):
            status = "✓" if result["passed"] else "✗"
            print(f"{status} Test {i+1}: {TEST_QUERIES[i]['query'][:50]}...")
        
        # Assert that most STAC queries generated correctly
        assert passed >= total * 0.7, f"Only {passed}/{total} STAC queries passed. Expected at least 70%"
    
    def _validate_extraction(self, entities: Dict[str, Any], expected: Dict[str, Any], query: str) -> Dict[str, Any]:
        """Validate extracted entities against expected values"""
        score = 0.0
        max_score = 0.0
        details = {}
        
        # Location validation
        if "location" in expected:
            max_score += 2.0
            if entities.get("location", {}).get("name") == expected["location"].get("name"):
                score += 1.5
                details["location_name"] = "✓"
            else:
                details["location_name"] = f"✗ Got: {entities.get('location', {}).get('name')}, Expected: {expected['location'].get('name')}"
            
            if entities.get("location", {}).get("type") == expected["location"].get("type"):
                score += 0.5
                details["location_type"] = "✓"
            else:
                details["location_type"] = f"✗ Got: {entities.get('location', {}).get('type')}, Expected: {expected['location'].get('type')}"
        
        # Temporal validation
        if "temporal" in expected:
            max_score += 2.0
            temporal_score = 0.0
            
            if expected["temporal"].get("year") and entities.get("temporal", {}).get("year") == expected["temporal"]["year"]:
                temporal_score += 1.0
                details["temporal_year"] = "✓"
            elif expected["temporal"].get("year"):
                details["temporal_year"] = f"✗ Got: {entities.get('temporal', {}).get('year')}, Expected: {expected['temporal']['year']}"
            
            if expected["temporal"].get("month") and entities.get("temporal", {}).get("month") == expected["temporal"]["month"]:
                temporal_score += 0.5
                details["temporal_month"] = "✓"
            elif expected["temporal"].get("month"):
                details["temporal_month"] = f"✗ Got: {entities.get('temporal', {}).get('month')}, Expected: {expected['temporal']['month']}"
            
            if expected["temporal"].get("relative") and entities.get("temporal", {}).get("relative") == expected["temporal"]["relative"]:
                temporal_score += 0.5
                details["temporal_relative"] = "✓"
            elif expected["temporal"].get("relative"):
                details["temporal_relative"] = f"✗ Got: {entities.get('temporal', {}).get('relative')}, Expected: {expected['temporal']['relative']}"
            
            score += temporal_score
        
        # Disaster validation
        if "disaster" in expected:
            max_score += 1.5
            if entities.get("disaster", {}).get("type") == expected["disaster"].get("type"):
                score += 1.0
                details["disaster_type"] = "✓"
            else:
                details["disaster_type"] = f"✗ Got: {entities.get('disaster', {}).get('type')}, Expected: {expected['disaster'].get('type')}"
            
            if expected["disaster"].get("name") and entities.get("disaster", {}).get("name") == expected["disaster"]["name"]:
                score += 0.5
                details["disaster_name"] = "✓"
            elif expected["disaster"].get("name"):
                details["disaster_name"] = f"✗ Got: {entities.get('disaster', {}).get('name')}, Expected: {expected['disaster']['name']}"
        
        # Analysis intent validation
        if "analysis_intent" in expected:
            max_score += 1.0
            if entities.get("analysis_intent", {}).get("type") == expected["analysis_intent"].get("type"):
                score += 1.0
                details["analysis_intent"] = "✓"
            else:
                details["analysis_intent"] = f"✗ Got: {entities.get('analysis_intent', {}).get('type')}, Expected: {expected['analysis_intent'].get('type')}"
        
        return {
            "overall_score": score / max_score if max_score > 0 else 0.0,
            "score": score,
            "max_score": max_score,
            "details": details
        }
    
    def _validate_bbox(self, bbox: List[float], expected_bbox: List[str], location: str) -> Dict[str, Any]:
        """Validate bbox format and approximate correctness"""
        if not bbox or len(bbox) != 4:
            return {"valid": False, "reason": "Invalid bbox format"}
        
        try:
            # Convert expected bbox to floats for comparison
            expected_floats = [float(x) for x in expected_bbox]
            
            # Check if bbox is within reasonable bounds of expected
            # Allow for some variance in geocoding results
            tolerance = 5.0  # degrees
            
            within_tolerance = all(
                abs(bbox[i] - expected_floats[i]) <= tolerance
                for i in range(4)
            )
            
            # Basic sanity checks
            valid_bounds = (
                -180 <= bbox[0] <= 180 and  # min_lon
                -90 <= bbox[1] <= 90 and    # min_lat
                -180 <= bbox[2] <= 180 and  # max_lon
                -90 <= bbox[3] <= 90 and    # max_lat
                bbox[0] < bbox[2] and       # min_lon < max_lon
                bbox[1] < bbox[3]           # min_lat < max_lat
            )
            
            return {
                "valid": valid_bounds and within_tolerance,
                "within_tolerance": within_tolerance,
                "valid_bounds": valid_bounds,
                "bbox": bbox,
                "expected": expected_floats
            }
            
        except Exception as e:
            return {"valid": False, "reason": f"Error validating bbox: {e}"}
    
    def _validate_stac_query(self, stac_query: Dict[str, Any], expected_collections: List[str], query: str) -> Dict[str, Any]:
        """Validate complete STAC query structure and content"""
        if not stac_query:
            return {"valid": False, "reason": "No STAC query generated"}
        
        issues = []
        
        # Check required fields
        required_fields = ["collections", "bbox"]
        for field in required_fields:
            if field not in stac_query:
                issues.append(f"Missing required field: {field}")
        
        # Validate collections
        if "collections" in stac_query:
            collections = stac_query["collections"]
            if not collections:
                issues.append("No collections specified")
            elif expected_collections:
                # Check if any expected collections are present
                matching_collections = [c for c in collections if c in expected_collections]
                if not matching_collections:
                    issues.append(f"None of expected collections {expected_collections} found in {collections}")
        
        # Validate bbox
        if "bbox" in stac_query:
            bbox = stac_query["bbox"]
            if not bbox or len(bbox) != 4:
                issues.append("Invalid bbox format")
            else:
                try:
                    bbox_floats = [float(x) for x in bbox]
                    if not (-180 <= bbox_floats[0] <= 180 and -90 <= bbox_floats[1] <= 90 and
                           -180 <= bbox_floats[2] <= 180 and -90 <= bbox_floats[3] <= 90 and
                           bbox_floats[0] < bbox_floats[2] and bbox_floats[1] < bbox_floats[3]):
                        issues.append("Bbox coordinates out of valid range")
                except (ValueError, TypeError):
                    issues.append("Bbox contains non-numeric values")
        
        return {
            "valid": len(issues) == 0,
            "issues": issues,
            "stac_query": stac_query
        }

if __name__ == "__main__":
    # Run tests directly
    import asyncio
    
    async def run_all_tests():
        """Run all tests for quick verification"""
        print("=== AUTOMATED SEMANTIC TRANSLATOR TESTS ===\n")
        
        try:
            translator = SemanticQueryTranslator(
                azure_openai_endpoint=AZURE_OPENAI_ENDPOINT,
                azure_openai_api_key=AZURE_OPENAI_API_KEY,
                model_name=MODEL_NAME
            )
            
            test_instance = TestSemanticTranslator()
            test_instance.translator = translator
            
            print("Running entity extraction tests...")
            await test_instance.test_entity_extraction_comprehensive()
            
            print("\nRunning bbox resolution tests...")
            await test_instance.test_bbox_resolution()
            
            print("\nRunning STAC query generation tests...")
            await test_instance.test_stac_query_generation()
            
            print("\n=== ALL TESTS COMPLETED ===")
            
        except Exception as e:
            print(f"Test setup failed: {e}")
            print("Make sure environment variables are set:")
            print("- AZURE_OPENAI_ENDPOINT")
            print("- AZURE_OPENAI_API_KEY")
            print("- AZURE_OPENAI_MODEL (optional, defaults to gpt-5)")
    
    # Run if executed directly
    asyncio.run(run_all_tests())
