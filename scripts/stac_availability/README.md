# STAC Availability Scripts

This folder contains scripts for analyzing and testing STAC collection availability in Microsoft Planetary Computer.

## Scripts Overview

### `check_available_collections.py`
- Checks what collections are actually available in Microsoft Planetary Computer
- Provides a count and list of available collections
- Useful for verifying collection availability before queries

### `comprehensive_stac_analyzer.py`
- Comprehensive analysis of STAC collections and their capabilities
- Deep dive into collection metadata and features
- Generates detailed reports on collection status

### `deep_stac_analyzer.py`
- In-depth analysis of specific STAC collections
- Detailed metadata extraction and validation
- Performance and feature analysis

### `quick_stac_catalog_test.py`
- Quick test of STAC catalog connectivity and basic functionality
- Lightweight verification of STAC API availability
- Good for health checks and debugging

### `stac_discovery.py`
- Discovery and exploration of STAC collections
- Collection metadata browsing and analysis
- Useful for understanding available datasets

## Usage

These scripts are primarily for:
- **Development**: Understanding what STAC collections are available
- **Debugging**: Troubleshooting STAC API connectivity issues
- **Analysis**: Deep-diving into collection capabilities and metadata
- **Testing**: Verifying STAC functionality before integration

## Dependencies

These scripts require:
- `aiohttp` for async HTTP requests
- `pystac-client` for STAC API interaction
- `planetary-computer` for Microsoft PC integration

Run from repository root:
```bash
python scripts/stac_availability/check_available_collections.py
```