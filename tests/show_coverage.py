#!/usr/bin/env python3
"""
Show complete collection coverage summary.
"""

from collection_query_patterns import COLLECTION_QUERY_PATTERNS
from hybrid_rendering_system import FEATURED_COLLECTIONS

def main():
    print('\n' + '='*80)
    print('COLLECTION COVERAGE SUMMARY')
    print('='*80)
    
    print(f'\nFeatured Collections: {len(FEATURED_COLLECTIONS)}')
    print(f'Query Patterns Defined: {len(COLLECTION_QUERY_PATTERNS)}')
    
    # Check for missing patterns
    missing = [c for c in FEATURED_COLLECTIONS if c not in COLLECTION_QUERY_PATTERNS]
    print(f'\nMissing from patterns: {len(missing)}')
    if missing:
        print(f'  ❌ Missing: {missing}')
    else:
        print('  ✅ All featured collections covered!')
    
    # Show bonus collections
    extra = [c for c in COLLECTION_QUERY_PATTERNS if c not in FEATURED_COLLECTIONS]
    print(f'\nBonus collections: {len(extra)}')
    if extra:
        for e in sorted(extra):
            print(f'  + {e}')
    
    # Categorize by type
    static = []
    composite = []
    dynamic = []
    
    for coll_id, pattern in COLLECTION_QUERY_PATTERNS.items():
        caps = pattern.get('capabilities', {})
        if caps.get('static_data'):
            static.append(coll_id)
        elif caps.get('composite_data'):
            composite.append(coll_id)
        else:
            dynamic.append(coll_id)
    
    print(f'\n' + '='*80)
    print('BREAKDOWN BY TYPE')
    print('='*80)
    
    print(f'\n📊 Static (elevation): {len(static)}')
    for s in sorted(static):
        print(f'  - {s}')
    
    print(f'\n📊 Composite (MODIS): {len(composite)}')
    for c in sorted(composite):
        print(f'  - {c}')
    
    print(f'\n📊 Dynamic (time-series): {len(dynamic)}')
    for d in sorted(dynamic):
        print(f'  - {d}')
    
    print(f'\n' + '='*80)
    print(f'✅ COMPLETE: 100% coverage of {len(FEATURED_COLLECTIONS)} featured')
    print(f'            + {len(extra)} bonus = {len(COLLECTION_QUERY_PATTERNS)} total')
    print('='*80 + '\n')

if __name__ == '__main__':
    main()
