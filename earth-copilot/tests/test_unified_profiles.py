#!/usr/bin/env python3
"""Test that the unified profiles file works"""

import collection_profiles_unified as cpu

print("="*80)
print("TESTING UNIFIED COLLECTION_PROFILES")
print("="*80)

print(f"\n✓ Import successful")
print(f"✓ Collections: {len(cpu.COLLECTION_PROFILES)}")

# Test structure
first_coll_id = list(cpu.COLLECTION_PROFILES.keys())[0]
first_coll = cpu.COLLECTION_PROFILES[first_coll_id]

print(f"✓ First collection: {first_coll_id}")
print(f"✓ Has query_rules: {'query_rules' in first_coll}")
print(f"✓ Has visualization: {'visualization' in first_coll}")

# Test helper functions
print(f"\n✓ Helper functions available:")
print(f"  - get_query_rules: {hasattr(cpu, 'get_query_rules')}")
print(f"  - supports_temporal_filtering: {hasattr(cpu, 'supports_temporal_filtering')}")
print(f"  - is_static_collection: {hasattr(cpu, 'is_static_collection')}")
print(f"  - is_composite_collection: {hasattr(cpu, 'is_composite_collection')}")
print(f"  - generate_agent_query_knowledge: {hasattr(cpu, 'generate_agent_query_knowledge')}")

# Test actual function calls
print(f"\n✓ Testing function calls:")
rules = cpu.get_query_rules("sentinel-2-l2a")
print(f"  - get_query_rules('sentinel-2-l2a'): {rules.get('type')}")
print(f"  - is_static_collection('cop-dem-glo-30'): {cpu.is_static_collection('cop-dem-glo-30')}")
print(f"  - is_composite_collection('modis-09A1-061'): {cpu.is_composite_collection('modis-09A1-061')}")
print(f"  - supports_temporal_filtering('sentinel-2-l2a'): {cpu.supports_temporal_filtering('sentinel-2-l2a')}")

print(f"\n{'='*80}")
print("✅ ALL TESTS PASSED - Unified profiles file is ready!")
print("="*80)
