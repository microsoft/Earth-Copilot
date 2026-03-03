"""
Extract ALL Planetary Computer Dataset Configurations

This is the SINGLE EXTRACTION SCRIPT that creates the golden source JSON file.

What it extracts from planetary-computer-tasks repository:
- Rendering configurations (colormap, rescale, assets, resampling) from config.json
- Descriptions from description.md files
- Metadata (keywords, titles) from template.json files
- Data classification (optical, SAR, elevation, etc.)
- Query capabilities (temporal filtering, cloud filtering)
- Categories for organizing collections

Output:
    - earth-copilot/container-app/pc_rendering_config.json
    
This JSON is the SINGLE SOURCE OF TRUTH:
    - Loaded by pc_tasks_config_loader.py at app startup
    - Cached in memory for fast access
    - Referenced by all agents (semantic_translator, collection_mapping, etc.)
    - Served to frontend via API endpoints

Usage:
    python scripts/extract_all_pc_configs.py
    
Run this whenever you need to update configs from the PC tasks repository.
"""

import json
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Any
from datetime import datetime


class UnifiedPCExtractor:
    """Extract ALL dataset configurations from Planetary Computer Tasks repo"""
    
    def __init__(self, pc_tasks_path: str = "planetary-computer-tasks/datasets"):
        self.pc_tasks_path = Path(pc_tasks_path)
        if not self.pc_tasks_path.exists():
            raise FileNotFoundError(
                f"Planetary Computer Tasks repository not found at {self.pc_tasks_path}\n"
                f"Run: git clone https://github.com/microsoft/planetary-computer-tasks.git"
            )
        
        self.collections: Dict[str, Dict[str, Any]] = {}
        self.errors: List[Tuple[Path, str]] = []
    
    def extract_all(self):
        """Extract all dataset folders from PC tasks repo"""
        print(f" Scanning {self.pc_tasks_path}...")
        
        dataset_folders = [d for d in self.pc_tasks_path.iterdir() if d.is_dir()]
        print(f"   Found {len(dataset_folders)} dataset folders")
        
        for folder in sorted(dataset_folders):
            # Config files are in the collection/ subdirectory
            collection_folder = folder / "collection"
            if not collection_folder.exists():
                self.errors.append((folder, "No collection/ folder found"))
                continue
            
            # Check if this is a multi-collection folder (like MODIS)
            # Multi-collection folders have subdirectories in collection/, each with its own config
            subdirs = [d for d in collection_folder.iterdir() if d.is_dir()]
            
            if subdirs and not (collection_folder / "config.json").exists():
                # This is a multi-collection folder (e.g., modis/)
                print(f"    Found multi-collection folder: {folder.name} ({len(subdirs)} collections)")
                for subdir in sorted(subdirs):
                    config_file = subdir / "config.json"
                    description_file = subdir / "description.md"
                    template_file = subdir / "template.json"
                    
                    if not config_file.exists():
                        self.errors.append((subdir, "No config.json found"))
                        continue
                    
                    try:
                        collection_data = self._extract_collection(
                            subdir, config_file, description_file, template_file
                        )
                        
                        if collection_data:
                            collection_id = collection_data['collection_id']
                            self.collections[collection_id] = collection_data
                            
                    except Exception as e:
                        self.errors.append((subdir, str(e)))
            else:
                # Single collection folder (standard structure)
                config_file = collection_folder / "config.json"
                description_file = collection_folder / "description.md"
                template_file = collection_folder / "template.json"
                
                if not config_file.exists():
                    self.errors.append((folder, "No config.json found in collection/"))
                    continue
                
                try:
                    collection_data = self._extract_collection(
                        folder, config_file, description_file, template_file
                    )
                    
                    if collection_data:
                        collection_id = collection_data['collection_id']
                        self.collections[collection_id] = collection_data
                        
                except Exception as e:
                    self.errors.append((folder, str(e)))
        
        print(f" Extracted {len(self.collections)} collections")
        
        if self.errors:
            print(f"  {len(self.errors)} errors:")
            for path, error in self.errors[:5]:  # Show first 5
                print(f"   - {path.name}: {error}")
    
    def _extract_collection(
        self,
        folder: Path,
        config_file: Path,
        description_file: Path,
        template_file: Path
    ) -> Optional[Dict[str, Any]]:
        """Extract complete configuration for a single collection"""
        
        # Load config.json (rendering params)
        with open(config_file, encoding='utf-8') as f:
            pc_config = json.load(f)
        
        render_config = pc_config.get("render_config", {})
        render_params = render_config.get("render_params", {})
        mosaic_info = pc_config.get("mosaic_info", {})
        render_options = mosaic_info.get("render_options", [])
        
        collection_id = folder.name
        
        # Start building unified configuration
        unified_config = {
            "collection_id": collection_id,
            "source_folder": folder.name,
        }
        
        # --- RENDERING CONFIGURATION ---
        rendering = {}
        
        # Assets
        if "assets" in render_config:
            rendering["assets"] = render_config["assets"]
        elif "assets" in pc_config:
            rendering["assets"] = pc_config["assets"]
        
        # Zoom levels
        rendering["min_zoom"] = render_config.get("minzoom", 6)
        rendering["max_zoom"] = render_config.get("maxzoom", 18)
        
        # Extract rendering parameters
        if "colormap_name" in render_params:
            rendering["colormap_name"] = render_params["colormap_name"]
        
        if "rescale" in render_params:
            rescale = self._parse_rescale(render_params["rescale"])
            if rescale:
                rendering["rescale"] = rescale
        
        if "color_formula" in render_params:
            rendering["color_formula"] = render_params["color_formula"]
        
        if "expression" in render_params:
            rendering["expression"] = render_params["expression"]
        
        if "asset_bidx" in render_params:
            rendering["asset_bidx"] = render_params["asset_bidx"]
        
        if "nodata" in render_params:
            rendering["nodata"] = render_params["nodata"]
        
        # Parse render_options for additional params
        if render_options and render_options[0].get("options"):
            options_str = render_options[0]["options"]
            options_params = self._parse_options_string(options_str)
            
            # Only add if not already set
            for key in ["colormap_name", "rescale", "color_formula", "expression", "asset_bidx"]:
                if key not in rendering and key in options_params:
                    rendering[key] = options_params[key]
        
        unified_config["rendering"] = rendering
        
        # --- METADATA (for GPT catalog) ---
        metadata = {}
        
        # Load description from description.md
        has_description = False
        if description_file.exists():
            with open(description_file, encoding='utf-8') as f:
                description = f.read().strip()
                if description:  # Only use if not empty
                    # Clean up description
                    description = description.replace('\n\n', ' ').replace('\n', ' ')
                    # Limit length
                    if len(description) > 500:
                        description = description[:497] + "..."
                    metadata["description"] = description
                    has_description = True
        
        # Load keywords and title from template.json
        if template_file.exists():
            with open(template_file, encoding='utf-8') as f:
                template = json.load(f)
                
                if "keywords" in template:
                    metadata["keywords"] = template["keywords"]
                
                if "title" in template:
                    metadata["title"] = template["title"]
                elif "item_assets" in template:
                    # Some collections have title in item_assets
                    for asset_name, asset_info in template.get("item_assets", {}).items():
                        if "title" in asset_info:
                            metadata["title"] = f"{collection_id} - {asset_info['title']}"
                            break
        
        # If no title found, use collection_id
        if "title" not in metadata:
            metadata["title"] = collection_id.replace('-', ' ').title()
        
        # --- DATA CLASSIFICATION (for intelligent querying) ---
        # Note: We need to classify BEFORE generating description (needs data_type)
        classification = {
            "data_type": self._classify_data_type(collection_id, rendering, metadata),
            "is_static": self._is_static_collection(collection_id, metadata),
            "supports_temporal": None,  # Will be set based on is_static
            "supports_cloud_filter": None,  # Will be set based on data_type
        }
        
        # Generate description if missing
        if not has_description:
            metadata["description"] = self._generate_description(
                collection_id, metadata, classification["data_type"]
            )
        
        unified_config["metadata"] = metadata
        
        # Set capabilities based on classification
        classification["supports_temporal"] = not classification["is_static"]
        classification["supports_cloud_filter"] = classification["data_type"] in [
            "optical", "optical_reflectance"
        ]
        
        unified_config["classification"] = classification
        
        # --- CATEGORIZATION (for GPT catalog grouping) ---
        unified_config["category"] = self._categorize_collection(
            collection_id, classification["data_type"], metadata
        )
        
        return unified_config
    
    def _parse_rescale(self, rescale_value) -> Optional[List[float]]:
        """Parse various rescale formats into [min, max] list"""
        if not rescale_value:
            return None
        
        if isinstance(rescale_value, list):
            if len(rescale_value) == 0:
                return None
            elif len(rescale_value) == 1:
                # Format: ["0,10000"] or ["-1000,4000"]
                parts = str(rescale_value[0]).split(",")
                return [float(parts[0]), float(parts[1])]
            elif len(rescale_value) == 2:
                # Format: [-1000, 4000]
                return [float(rescale_value[0]), float(rescale_value[1])]
            else:
                # Multi-band rescale: ["0,8000", "0,1.000", "0,1.000"]
                # Use first band
                parts = str(rescale_value[0]).split(",")
                return [float(parts[0]), float(parts[1])]
        
        return None
    
    def _parse_options_string(self, options_str: str) -> Dict[str, Any]:
        """Parse URL parameter string into dict"""
        params = {}
        
        for param_pair in options_str.split("&"):
            if "=" not in param_pair:
                continue
            
            key, value = param_pair.split("=", 1)
            
            if key == "colormap_name":
                params["colormap_name"] = value
            elif key == "rescale":
                # Parse rescale from URL format
                if "," in value:
                    parts = value.split(",")
                    params["rescale"] = [float(parts[0]), float(parts[1])]
            elif key == "color_formula":
                params["color_formula"] = value
            elif key == "expression":
                params["expression"] = value
            elif key == "asset_bidx":
                params["asset_bidx"] = value
            elif key == "assets":
                params["assets"] = value.split(",")
        
        return params
    
    def _classify_data_type(
        self, collection_id: str, rendering: Dict, metadata: Dict
    ) -> str:
        """Classify collection data type"""
        cid_lower = collection_id.lower()
        desc_lower = metadata.get("description", "").lower()
        keywords_lower = " ".join(metadata.get("keywords", [])).lower()
        
        # Fire detection
        if any(x in cid_lower for x in ["14a1", "14a2", "64a1", "fire", "burn"]):
            return "fire"
        
        # NDVI/Vegetation indices
        if any(x in cid_lower for x in ["13q1", "13a1", "15a", "16a", "17a", "ndvi", "evi", "lai", "npp", "gpp"]):
            return "vegetation"
        
        # Snow cover
        if any(x in cid_lower for x in ["10a1", "10a2", "snow"]):
            return "snow"
        
        # Temperature/Thermal
        if any(x in cid_lower for x in ["11a1", "11a2", "21a", "lst", "temperature"]) or "temperature" in desc_lower:
            return "thermal"
        
        # SAR
        if "sentinel-1" in cid_lower or "sar" in cid_lower or "alos-palsar" in cid_lower:
            return "sar"
        
        # Elevation/DEM
        if any(x in cid_lower for x in ["dem", "elevation", "nasadem", "3dep"]) or "elevation" in desc_lower:
            return "elevation"
        
        # Surface reflectance (MODIS 09, 43)
        if any(x in cid_lower for x in ["09a1", "09q1", "43a4"]) or "reflectance" in desc_lower:
            return "optical_reflectance"
        
        # HLS, Landsat, Sentinel-2 (optical)
        if any(x in cid_lower for x in ["hls", "landsat", "sentinel-2", "naip"]):
            if rendering.get("color_formula"):
                return "optical"
            else:
                return "optical_reflectance"
        
        # Land cover
        if any(x in cid_lower for x in ["lulc", "land-cover", "landcover", "cdl", "worldcover", "land_cover"]):
            return "land_cover"
        
        # Climate
        if any(x in cid_lower for x in ["era5", "climate", "terraclimate"]) or "climate" in desc_lower:
            return "climate"
        
        # Ocean
        if "sst" in cid_lower or "ocean" in cid_lower or "ocean" in desc_lower:
            return "ocean"
        
        return "unknown"
    
    def _is_static_collection(self, collection_id: str, metadata: Dict) -> bool:
        """Determine if collection is static (no temporal dimension)"""
        static_keywords = ["elevation", "dem", "digital elevation model"]
        
        # Check collection ID
        if any(x in collection_id.lower() for x in ["dem", "elevation"]):
            return True
        
        # Check metadata
        desc = metadata.get("description", "").lower()
        if any(keyword in desc for keyword in static_keywords):
            return True
        
        return False
    
    def _generate_description(self, collection_id: str, metadata: Dict, data_type: str) -> str:
        """Generate a description for collections missing description.md"""
        
        # Extract collection name parts
        parts = collection_id.split('-')
        title = metadata.get("title", collection_id.replace('-', ' ').title())
        
        # Common patterns and descriptions
        if "3dep" in collection_id:
            if "lidar" in collection_id:
                product = collection_id.split('-')[-1].upper()
                return f"USGS 3DEP LiDAR {product} product providing high-resolution elevation and terrain data across the United States."
            return "USGS 3D Elevation Program providing seamless elevation data for the United States."
        
        if "alos" in collection_id:
            return "Advanced Land Observing Satellite (ALOS) digital elevation model providing 30m resolution global terrain data."
        
        if "aster" in collection_id:
            return "ASTER Global Digital Elevation Model providing 30m resolution elevation data derived from stereo-pair imagery."
        
        if "chesapeake" in collection_id:
            return "High-resolution land cover classification for the Chesapeake Bay watershed region."
        
        if "gbif" in collection_id:
            return "Global Biodiversity Information Facility (GBIF) species occurrence data aggregated from multiple sources worldwide."
        
        if "gap" in collection_id:
            return "USGS Gap Analysis Project providing land cover and species habitat models for conservation planning."
        
        if "io-lulc" in collection_id:
            year = collection_id.split('-')[-1] if collection_id.split('-')[-1].isdigit() else "annual"
            return f"Impact Observatory Land Use Land Cover classification at 10m resolution for {year}, derived from Sentinel-2 imagery."
        
        if "mtbs" in collection_id:
            return "Monitoring Trends in Burn Severity (MTBS) dataset mapping fire extent and severity across the United States."
        
        if "nrcan" in collection_id:
            return "Natural Resources Canada land cover classification providing comprehensive coverage of Canadian landscapes."
        
        if "terraclimate" in collection_id:
            return "TerraClimate monthly climate and water balance data at 4km resolution covering global terrestrial surfaces."
        
        # Generic descriptions based on data type
        type_descriptions = {
            "optical": f"{title} optical satellite imagery providing multi-spectral Earth observation data.",
            "optical_reflectance": f"{title} surface reflectance product for Earth observation and analysis.",
            "sar": f"{title} Synthetic Aperture Radar (SAR) data for all-weather surface monitoring.",
            "elevation": f"{title} digital elevation model providing terrain height information.",
            "fire": f"{title} thermal anomaly and fire detection product.",
            "vegetation": f"{title} vegetation index product for monitoring plant health and productivity.",
            "snow": f"{title} snow cover product for cryosphere monitoring.",
            "thermal": f"{title} land surface temperature product.",
            "land_cover": f"{title} land cover classification dataset.",
            "climate": f"{title} climate and environmental monitoring dataset.",
            "ocean": f"{title} ocean and marine data product.",
        }
        
        return type_descriptions.get(data_type, f"{title} geospatial dataset from Microsoft Planetary Computer.")
    
    def _categorize_collection(
        self, collection_id: str, data_type: str, metadata: Dict
    ) -> str:
        """Categorize collection for GPT catalog grouping"""
        
        # Map data types to categories
        category_map = {
            "optical": "Optical Satellite Imagery",
            "optical_reflectance": "Optical Satellite Imagery",
            "sar": "Synthetic Aperture Radar (SAR)",
            "elevation": "Elevation & Terrain",
            "fire": "Fire Detection & Analysis",
            "vegetation": "Vegetation Indices",
            "snow": "Snow & Ice Cover",
            "thermal": "Thermal & Temperature",
            "land_cover": "Land Cover & Land Use",
            "climate": "Climate & Weather",
            "ocean": "Ocean & Marine",
        }
        
        # Use data type for category
        if data_type in category_map:
            return category_map[data_type]
        
        # Fallback: try to infer from keywords
        keywords_lower = " ".join(metadata.get("keywords", [])).lower()
        
        if "satellite" in keywords_lower or "sentinel" in keywords_lower:
            return "Optical Satellite Imagery"
        elif "radar" in keywords_lower:
            return "Synthetic Aperture Radar (SAR)"
        elif "vegetation" in keywords_lower:
            return "Vegetation Indices"
        
        return "Other Datasets"
    
    def export_unified_json(self):
        """Export single comprehensive JSON file"""
        from datetime import datetime
        import shutil
        
        today = datetime.now().strftime("%Y-%m-%d")
        
        # Group collections by category for better organization
        by_category: Dict[str, List[str]] = {}
        for cid, config in self.collections.items():
            category = config["category"]
            if category not in by_category:
                by_category[category] = []
            by_category[category].append(cid)
        
        # Build categories list for GPT catalog
        categories = []
        for category_name, collection_ids in sorted(by_category.items()):
            category_collections = []
            for cid in sorted(collection_ids):
                config = self.collections[cid]
                category_collections.append({
                    "id": cid,
                    "title": config["metadata"].get("title", cid),
                    "description": config["metadata"].get("description", ""),
                    "keywords": config["metadata"].get("keywords", []),
                })
            
            categories.append({
                "name": category_name,
                "count": len(collection_ids),
                "collections": category_collections
            })
        
        unified_data = {
            "metadata": {
                "total_collections": len(self.collections),
                "last_updated": today,
                "source": "planetary-computer-tasks repository (config.json, description.md, template.json)",
                "note": "AUTO-GENERATED - Do not edit manually. Regenerate using scripts/extract_all_pc_configs.py",
                "extraction_timestamp": datetime.now().isoformat(),
                "pc_repo_path": str(self.pc_tasks_path),
                "contains": [
                    "rendering configurations (colormap, rescale, assets)",
                    "metadata (descriptions, keywords, titles)",
                    "classification (data_type, capabilities)",
                    "categories (for GPT catalog grouping)"
                ]
            },
            "categories": categories,
            "collections": self.collections
        }
        
        # Output to container-app directory
        output_dir = Path(__file__).parent.parent / "earth-copilot" / "container-app"
        output_file = output_dir / "pc_rendering_config.json"
        
        print(f"\n Exporting unified configuration...")
        print(f"    Output: {output_file}")
        
        with open(output_file, 'w', encoding='utf-8') as f:
            json.dump(unified_data, f, indent=2, ensure_ascii=False)
        
        file_size_kb = output_file.stat().st_size / 1024
        print(f"    Created {output_file.name} ({file_size_kb:.2f} KB)")
        print(f"    Contains:")
        print(f"      - {len(self.collections)} collections")
        print(f"      - {len(categories)} categories")
        print(f"      - Rendering configs, metadata, classification")
        
        return output_file


def main():
    """Main extraction workflow"""
    print("=" * 80)
    print("Unified Planetary Computer Configuration Extractor")
    print("Single JSON for ALL agents - rendering, GPT catalog, query rules")
    print("=" * 80 + "\n")
    
    try:
        extractor = UnifiedPCExtractor()
        
        # Extract all configurations
        extractor.extract_all()
        
        # Export to single unified JSON
        output_file = extractor.export_unified_json()
        
        print("\n" + "=" * 80)
        print(" Extraction Complete!")
        print("=" * 80)
        print(f"\n Unified configuration: {output_file.name}")
        print("\nThis file contains EVERYTHING:")
        print("   Rendering configurations (for tile generation)")
        print("   GPT catalog metadata (for collection selection)")
        print("   Query rules & capabilities (for STAC queries)")
        print("   Categories (for organizing collections)")
        print("\nNext steps:")
        print("  1. Verify pc_tasks_config_loader.py loads from this JSON")
        print("  2. Remove old pc_collections_metadata.json (now redundant)")
        print("  3. Test agents can access all data")
        print("  4. Commit to git")
        
    except FileNotFoundError as e:
        print(f"\n Error: {e}")
        print("\nPlease clone the planetary-computer-tasks repository:")
        print("  git clone https://github.com/microsoft/planetary-computer-tasks.git")
        return 1
    except Exception as e:
        print(f"\n Unexpected error: {e}")
        import traceback
        traceback.print_exc()
        return 1
    
    return 0


if __name__ == "__main__":
    exit(main())
