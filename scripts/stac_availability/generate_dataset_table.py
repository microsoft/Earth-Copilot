"""
Generate a comprehensive dataset table from Planetary Computer tasks repo.

This script extracts:
- Dataset name (collection ID)
- Description (from local files or Planetary Computer STAC API)
- Search parameters (datetime, location requirements)
- Colormap/visualization info
"""

import json
import yaml
import os
import requests
from pathlib import Path
from typing import Dict, List, Any

def fetch_description_from_pc_api(collection_id: str) -> str:
    """Fetch collection description from Planetary Computer STAC API."""
    try:
        url = f"https://planetarycomputer.microsoft.com/api/stac/v1/collections/{collection_id}"
        response = requests.get(url, timeout=10)
        if response.status_code == 200:
            data = response.json()
            description = data.get('description', '')
            if description:
                # Truncate long descriptions
                return description[:300] + '...' if len(description) > 300 else description
        return None
    except Exception as e:
        print(f"  [WARN] Could not fetch description from PC API for {collection_id}: {e}")
        return None

def extract_description(description_file: Path, collection_id: str = None) -> str:
    """Extract first paragraph from description.md file or fetch from PC API."""
    if description_file.exists():
        with open(description_file, 'r', encoding='utf-8') as f:
            content = f.read()
            # Get first paragraph (before first blank line)
            lines = content.split('\n')
            desc_lines = []
            for line in lines:
                line = line.strip()
                if not line and desc_lines:  # Stop at first blank line after content
                    break
                if line and not line.startswith('#'):  # Skip markdown headers
                    desc_lines.append(line)
            local_desc = ' '.join(desc_lines)
            if local_desc:
                return local_desc[:300] + '...' if len(local_desc) > 300 else local_desc
    
    # If no local description, try fetching from Planetary Computer API
    if collection_id:
        print(f"  [SIGNAL] Fetching description from Planetary Computer API for {collection_id}...")
        api_desc = fetch_description_from_pc_api(collection_id)
        if api_desc:
            return api_desc + " (Source: Planetary Computer API)"
    
    return "No description available"

def extract_config_info(config_file: Path) -> Dict[str, Any]:
    """Extract render config and search parameters from config.json."""
    if not config_file.exists():
        return {}
    
    with open(config_file, 'r', encoding='utf-8') as f:
        config = json.load(f)
    
    render_config = config.get('render_config', {})
    assets = render_config.get('assets', [])
    
    # Handle assets being either list or dict or None
    if isinstance(assets, list):
        assets_str = ', '.join(assets)
    elif isinstance(assets, dict):
        assets_str = ', '.join(assets.keys())
    elif assets is None:
        assets_str = 'N/A'
    else:
        assets_str = str(assets)
    
    return {
        'colormap': render_config.get('render_params', {}).get('colormap_name', 'N/A'),
        'assets': assets_str,
        'minzoom': render_config.get('minzoom', 'N/A'),
        'maxzoom': render_config.get('maxzoom', 'N/A'),
        'requires_token': render_config.get('requires_token', False)
    }

def extract_stac_info(template_file: Path) -> Dict[str, Any]:
    """Extract STAC metadata from template.json."""
    if not template_file.exists():
        return {}
    
    with open(template_file, 'r', encoding='utf-8') as f:
        template = json.load(f)
    
    # Check temporal extent
    extent = template.get('extent', {})
    temporal = extent.get('temporal', {}).get('interval', [[None, None]])[0]
    spatial = extent.get('spatial', {}).get('bbox', [[]])[0]
    
    # Check item assets for data types
    item_assets = template.get('item_assets', {})
    
    return {
        'start_datetime': temporal[0] if temporal[0] else 'Open',
        'end_datetime': temporal[1] if temporal[1] else 'Ongoing',
        'has_spatial': bool(spatial),
        'data_types': list(item_assets.keys())[:3] if item_assets else []
    }

def scan_datasets(pc_tasks_path: Path) -> List[Dict[str, Any]]:
    """Scan all datasets in PC tasks repo."""
    datasets_dir = pc_tasks_path / 'datasets'
    datasets = []
    
    if not datasets_dir.exists():
        print(f"Error: Datasets directory not found: {datasets_dir}")
        return datasets
    
    # Iterate through all dataset folders
    for dataset_folder in sorted(datasets_dir.iterdir()):
        if not dataset_folder.is_dir():
            continue
        
        collection_dir = dataset_folder / 'collection'
        if not collection_dir.exists():
            continue
        
        # Check if this is a single-collection dataset (files directly in collection/)
        # or multi-collection dataset (subdirectories in collection/)
        config_in_root = (collection_dir / 'config.json').exists()
        template_in_root = (collection_dir / 'template.json').exists()
        
        if config_in_root or template_in_root:
            # Single collection - extract from template.json
            template_file = collection_dir / 'template.json'
            if template_file.exists():
                with open(template_file, 'r', encoding='utf-8') as f:
                    template = json.load(f)
                    collection_id = template.get('id', dataset_folder.name)
            else:
                collection_id = dataset_folder.name
            
            # Extract information from files
            description_file = collection_dir / 'description.md'
            config_file = collection_dir / 'config.json'
            
            description = extract_description(description_file, collection_id)
            config_info = extract_config_info(config_file)
            stac_info = extract_stac_info(template_file)
            
            datasets.append({
                'collection_id': collection_id,
                'category': dataset_folder.name.upper(),
                'description': description,
                'temporal_range': f"{stac_info.get('start_datetime', 'N/A')} to {stac_info.get('end_datetime', 'N/A')}",
                'datetime_required': stac_info.get('start_datetime') != 'N/A',
                'location_required': stac_info.get('has_spatial', False),
                'colormap': config_info.get('colormap', 'N/A'),
                'assets': config_info.get('assets', 'N/A'),
                'zoom_range': f"{config_info.get('minzoom', 'N/A')}-{config_info.get('maxzoom', 'N/A')}",
                'data_types': ', '.join(stac_info.get('data_types', [])),
            })
        else:
            # Multi-collection dataset - scan subdirectories
            for collection_folder in sorted(collection_dir.iterdir()):
                if not collection_folder.is_dir():
                    continue
                
                collection_id = collection_folder.name
                
                # Extract information from files
                description_file = collection_folder / 'description.md'
                config_file = collection_folder / 'config.json'
                template_file = collection_folder / 'template.json'
                
                description = extract_description(description_file, collection_id)
                config_info = extract_config_info(config_file)
                stac_info = extract_stac_info(template_file)
                
                datasets.append({
                    'collection_id': collection_id,
                    'category': dataset_folder.name.upper(),
                    'description': description,
                    'temporal_range': f"{stac_info.get('start_datetime', 'N/A')} to {stac_info.get('end_datetime', 'N/A')}",
                    'datetime_required': stac_info.get('start_datetime') != 'N/A',
                    'location_required': stac_info.get('has_spatial', False),
                    'colormap': config_info.get('colormap', 'N/A'),
                    'assets': config_info.get('assets', 'N/A'),
                    'zoom_range': f"{config_info.get('minzoom', 'N/A')}-{config_info.get('maxzoom', 'N/A')}",
                    'data_types': ', '.join(stac_info.get('data_types', [])),
                })
    
    return datasets

def generate_markdown_table(datasets: List[Dict[str, Any]]) -> str:
    """Generate a markdown table from dataset information."""
    
    md = "# Planetary Computer STAC Collections\n\n"
    md += "Complete reference of available datasets, search parameters, and visualization options.\n\n"
    
    # Group by category
    current_category = None
    
    for dataset in datasets:
        if dataset['category'] != current_category:
            current_category = dataset['category']
            md += f"\n## {current_category}\n\n"
            md += "| Collection ID | Description | Temporal Range | DateTime Required | Location Required | Colormap | Assets | Zoom Range |\n"
            md += "|---------------|-------------|----------------|-------------------|-------------------|----------|--------|------------|\n"
        
        md += f"| `{dataset['collection_id']}` "
        md += f"| {dataset['description'][:100]}... " if len(dataset['description']) > 100 else f"| {dataset['description']} "
        md += f"| {dataset['temporal_range']} "
        md += f"| {'[OK]' if dataset['datetime_required'] else '[FAIL]'} "
        md += f"| {'[OK]' if dataset['location_required'] else '[FAIL]'} "
        md += f"| `{dataset['colormap']}` "
        md += f"| {dataset['assets']} "
        md += f"| {dataset['zoom_range']} |\n"
    
    return md

def generate_json_output(datasets: List[Dict[str, Any]]) -> str:
    """Generate JSON output for frontend use."""
    return json.dumps(datasets, indent=2)

def main():
    # Path to PC tasks repo
    pc_tasks_path = Path(__file__).parent.parent / 'planetary-computer-tasks'
    
    if not pc_tasks_path.exists():
        print(f"Error: PC tasks repo not found at {pc_tasks_path}")
        return
    
    print("Scanning Planetary Computer datasets...")
    datasets = scan_datasets(pc_tasks_path)
    
    print(f"Found {len(datasets)} collections")
    
    # Generate markdown table
    output_dir = Path(__file__).parent.parent.parent / 'documentation'
    output_dir.mkdir(exist_ok=True)
    
    md_output = output_dir / 'stac_dataset_reference.md'
    with open(md_output, 'w', encoding='utf-8') as f:
        f.write(generate_markdown_table(datasets))
    
    print(f"[OK] Markdown table saved to: {md_output}")
    
    # Generate JSON for frontend
    json_output = output_dir / 'stac_collections.json'
    with open(json_output, 'w', encoding='utf-8') as f:
        f.write(generate_json_output(datasets))
    
    print(f"[OK] JSON data saved to: {json_output}")
    
    # Summary stats
    print(f"\n[CHART] Summary:")
    print(f"   Total collections: {len(datasets)}")
    print(f"   Datetime required: {sum(1 for d in datasets if d['datetime_required'])}")
    print(f"   Location required: {sum(1 for d in datasets if d['location_required'])}")
    
    categories = set(d['category'] for d in datasets)
    print(f"   Categories: {', '.join(sorted(categories))}")

if __name__ == '__main__':
    main()
