# Test Script for AI-First Query Construction
# Run this from the earth-copilot/container-app directory

import sys
import os

# No need to modify path - run from container-app directory

from collection_query_patterns import (
    COLLECTION_QUERY_PATTERNS,
    is_static_collection,
    is_composite_collection,
    supports_temporal_filtering,
    supports_cloud_filtering,
    uses_sortby_instead_of_datetime,
    get_ignored_parameters,
    get_agent_guidance,
    validate_query_for_collection,
    validate_multi_collection_query,
    generate_collection_knowledge_for_agent
)

print("=" * 80)
print("AI-FIRST QUERY CONSTRUCTION - TEST SCRIPT")
print("=" * 80)

# Test 1: Check collection capabilities
print("\n🧪 TEST 1: Collection Capability Detection")
print("-" * 80)

test_collections = [
    "cop-dem-glo-30",      # Static
    "modis-09A1-061",      # Composite
    "sentinel-2-l2a"       # Dynamic
]

for collection_id in test_collections:
    print(f"\n{collection_id}:")
    print(f"  Static: {is_static_collection(collection_id)}")
    print(f"  Composite: {is_composite_collection(collection_id)}")
    print(f"  Supports temporal filtering: {supports_temporal_filtering(collection_id)}")
    print(f"  Supports cloud filtering: {supports_cloud_filtering(collection_id)}")
    print(f"  Uses sortby: {uses_sortby_instead_of_datetime(collection_id)}")
    print(f"  Ignored params: {get_ignored_parameters(collection_id)}")

# Test 2: Validate queries
print("\n\n🧪 TEST 2: Query Validation")
print("-" * 80)

# Test case 1: Valid static query
print("\nTest Case 1: Valid Static Query")
query1 = {
    "collections": ["cop-dem-glo-30"],
    "bbox": [-122.5, 47.5, -122.0, 47.8],
    "limit": 10
}
is_valid, issues = validate_query_for_collection("cop-dem-glo-30", query1)
print(f"Query: {query1}")
print(f"Valid: {is_valid}")
if issues:
    print(f"Issues: {issues}")

# Test case 2: Invalid static query (has datetime)
print("\nTest Case 2: Invalid Static Query (with datetime)")
query2 = {
    "collections": ["cop-dem-glo-30"],
    "bbox": [-122.5, 47.5, -122.0, 47.8],
    "datetime": "2020-01-01/2024-12-31",  # ← Should be flagged
    "limit": 10
}
is_valid, issues = validate_query_for_collection("cop-dem-glo-30", query2)
print(f"Query: {query2}")
print(f"Valid: {is_valid}")
if issues:
    print(f"Issues:")
    for issue in issues:
        print(f"  - {issue}")

# Test case 3: Valid composite query
print("\nTest Case 3: Valid Composite Query")
query3 = {
    "collections": ["modis-09A1-061"],
    "bbox": [-122.5, 47.5, -122.0, 47.8],
    "sortby": [{"field": "datetime", "direction": "desc"}],
    "limit": 10
}
is_valid, issues = validate_query_for_collection("modis-09A1-061", query3)
print(f"Query: {query3}")
print(f"Valid: {is_valid}")
if issues:
    print(f"Issues: {issues}")

# Test case 4: Invalid composite query (has cloud filter)
print("\nTest Case 4: Invalid Composite Query (with cloud filter)")
query4 = {
    "collections": ["modis-09A1-061"],
    "bbox": [-122.5, 47.5, -122.0, 47.8],
    "query": {"eo:cloud_cover": {"lt": 20}},  # ← Should be flagged
    "limit": 10
}
is_valid, issues = validate_query_for_collection("modis-09A1-061", query4)
print(f"Query: {query4}")
print(f"Valid: {is_valid}")
if issues:
    print(f"Issues:")
    for issue in issues:
        print(f"  - {issue}")

# Test case 5: Valid dynamic query
print("\nTest Case 5: Valid Dynamic Query")
query5 = {
    "collections": ["sentinel-2-l2a"],
    "bbox": [-122.5, 47.5, -122.0, 47.8],
    "datetime": "2024-01-01/2024-12-31",
    "query": {"eo:cloud_cover": {"lt": 20}},
    "limit": 100
}
is_valid, issues = validate_query_for_collection("sentinel-2-l2a", query5)
print(f"Query: {query5}")
print(f"Valid: {is_valid}")
if issues:
    print(f"Issues: {issues}")

# Test case 6: Multi-collection query
print("\nTest Case 6: Multi-Collection Query")
query6 = {
    "collections": ["cop-dem-glo-30", "sentinel-2-l2a"],
    "bbox": [-122.5, 47.5, -122.0, 47.8],
    "datetime": "2024-01-01/2024-12-31",
    "limit": 100
}
is_valid, issues = validate_multi_collection_query(query6)
print(f"Query: {query6}")
print(f"Valid: {is_valid}")
if issues:
    print(f"Issues per collection:")
    for collection_id, collection_issues in issues.items():
        print(f"  {collection_id}:")
        for issue in collection_issues:
            print(f"    - {issue}")

# Test 3: Agent guidance
print("\n\n🧪 TEST 3: Agent Guidance")
print("-" * 80)

for collection_id in test_collections:
    guidance = get_agent_guidance(collection_id)
    print(f"\n{collection_id}:")
    print(f"  {guidance}")

# Test 4: Collection knowledge for agent
print("\n\n🧪 TEST 4: Collection Knowledge for Agent")
print("-" * 80)

knowledge = generate_collection_knowledge_for_agent()
print(knowledge[:500] + "...(truncated)")  # Show first 500 chars

# Test 5: Pattern completeness
print("\n\n🧪 TEST 5: Pattern Completeness")
print("-" * 80)

print(f"Total collections defined: {len(COLLECTION_QUERY_PATTERNS)}")
print(f"\nCollections by type:")

static_count = sum(1 for p in COLLECTION_QUERY_PATTERNS.values() if p.get('capabilities', {}).get('static_data'))
composite_count = sum(1 for p in COLLECTION_QUERY_PATTERNS.values() if p.get('capabilities', {}).get('composite_data'))
dynamic_count = len(COLLECTION_QUERY_PATTERNS) - static_count - composite_count

print(f"  Static: {static_count}")
print(f"  Composite: {composite_count}")
print(f"  Dynamic: {dynamic_count}")

print("\nStatic collections:")
for collection_id, pattern in COLLECTION_QUERY_PATTERNS.items():
    if pattern.get('capabilities', {}).get('static_data'):
        print(f"  - {collection_id}")

print("\nComposite collections:")
for collection_id, pattern in COLLECTION_QUERY_PATTERNS.items():
    if pattern.get('capabilities', {}).get('composite_data'):
        print(f"  - {collection_id}")

print("\nDynamic collections:")
for collection_id, pattern in COLLECTION_QUERY_PATTERNS.items():
    if not (pattern.get('capabilities', {}).get('static_data') or pattern.get('capabilities', {}).get('composite_data')):
        print(f"  - {collection_id}")

print("\n" + "=" * 80)
print("✅ ALL TESTS COMPLETED")
print("=" * 80)
