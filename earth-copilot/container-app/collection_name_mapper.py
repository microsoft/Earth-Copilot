"""
Comprehensive Collection Name Mapping
Generated from PC Tasks repository metadata

This module provides mappings between user-friendly dataset names and STAC collection IDs.
All mappings are derived from the official Planetary Computer Tasks repository.
"""
import json
from pathlib import Path
from typing import List, Dict, Optional

# Load collections metadata
COLLECTIONS_FILE = Path(__file__).parent.parent / "documentation" / "stac_collections.json"

class CollectionMapper:
    """Maps user queries to STAC collection IDs"""
    
    def __init__(self):
        """Load collection metadata and build keyword mappings"""
        self.collections = self._load_collections()
        self.keyword_map = self._build_keyword_map()
        self.collection_descriptions = self._build_description_map()
    
    def _load_collections(self) -> List[Dict]:
        """Load collection metadata from JSON file"""
        try:
            with open(COLLECTIONS_FILE, 'r', encoding='utf-8') as f:
                return json.load(f)
        except FileNotFoundError:
            print(f"Warning: Collections metadata file not found: {COLLECTIONS_FILE}")
            return []
    
    def _build_description_map(self) -> Dict[str, str]:
        """Build mapping of collection_id -> description"""
        return {
            col["collection_id"]: col.get("description", "")
            for col in self.collections
        }
    
    def _build_keyword_map(self) -> Dict[str, List[str]]:
        """
        Build comprehensive keyword -> collection_id mappings
        Includes dataset names, acronyms, and common search terms
        """
        keyword_map = {}
        
        # Explicit dataset name mappings (case-insensitive)
        explicit_mappings = {
            # USDA Cropland Data Layer
            "usda": ["usda-cdl"],
            "cdl": ["usda-cdl"],
            "usda-cdl": ["usda-cdl"],
            "usda cdl": ["usda-cdl"],
            "cropland": ["usda-cdl"],
            "crop data layer": ["usda-cdl"],
            "agricultural land": ["usda-cdl"],
            "farmland": ["usda-cdl"],
            
            # NAIP (National Agriculture Imagery Program)
            "naip": ["naip"],
            "aerial imagery": ["naip"],
            "high resolution imagery": ["naip"],
            
            # Landsat
            "landsat": ["landsat-c2-l2"],
            "landsat 8": ["landsat-c2-l2"],
            "landsat 9": ["landsat-c2-l2"],
            "landsat c2": ["landsat-c2-l2"],
            
            # Sentinel-2
            "sentinel": ["sentinel-2-l2a"],
            "sentinel-2": ["sentinel-2-l2a"],
            "sentinel 2": ["sentinel-2-l2a"],
            "s2": ["sentinel-2-l2a"],
            
            # Sentinel-1 (SAR)
            "sentinel-1": ["sentinel-1-rtc"],
            "sentinel 1": ["sentinel-1-rtc"],
            "sar": ["sentinel-1-rtc"],
            "radar": ["sentinel-1-rtc"],
            "rtc": ["sentinel-1-rtc"],
            
            # MODIS - both fire products accessible (14A2=8-day, 14A1=daily)
            "modis": ["modis-14A2-061", "modis-14A1-061", "modis-10A1-061", "modis-09Q1-061", "modis-13Q1-061", "modis-64A1-061"],
            "modis fire": ["modis-14A2-061", "modis-14A1-061"],
            "modis fire daily": ["modis-14A1-061"],
            "modis fire 8-day": ["modis-14A2-061"],
            "fire detection": ["modis-14A2-061", "modis-14A1-061"],
            "thermal anomalies": ["modis-14A2-061", "modis-14A1-061"],
            "active fire": ["modis-14A1-061"],  # Daily better for active fires
            "modis snow": ["modis-10A1-061"],
            "snow cover": ["modis-10A1-061"],
            
            # MTBS (Monitoring Trends in Burn Severity)
            "mtbs": ["mtbs"],
            "burn severity": ["mtbs"],
            "fire severity": ["mtbs"],
            "wildfire severity": ["mtbs"],
            "monitoring trends burn severity": ["mtbs"],
            "post-fire": ["mtbs"],
            "post fire": ["mtbs"],
            "fire damage assessment": ["mtbs"],
            "burn assessment": ["mtbs"],
            
            # HLS (Harmonized Landsat Sentinel)
            "hls": ["hls2-l30", "hls2-s30"],
            "hls2": ["hls2-l30", "hls2-s30"],
            "harmonized landsat sentinel": ["hls2-l30", "hls2-s30"],
            
            # DEM / Elevation
            "elevation": ["cop-dem-glo-30"],
            "dem": ["cop-dem-glo-30"],
            "terrain": ["cop-dem-glo-30"],
            "topography": ["cop-dem-glo-30"],
            "cop-dem": ["cop-dem-glo-30"],
            "copernicus dem": ["cop-dem-glo-30"],
            
            # Land Cover
            "land cover": ["io-lulc-annual-v02", "esa-worldcover"],
            "lulc": ["io-lulc-annual-v02"],
            "io land cover": ["io-lulc-annual-v02"],
            "esa worldcover": ["esa-worldcover"],
            "worldcover": ["esa-worldcover"],
            
            # NOAA Climate
            "climate normals": ["noaa-climate-normals-gridded", "noaa-climate-normals-tabular"],
            "noaa climate": ["noaa-climate-normals-gridded", "noaa-climate-normals-tabular"],
            "temperature normals": ["noaa-climate-normals-gridded"],
            "precipitation normals": ["noaa-climate-normals-gridded"],
            
            # NOAA NClimGrid
            "nclimgrid": ["noaa-nclimgrid-monthly"],
            "noaa nclimgrid": ["noaa-nclimgrid-monthly"],
            
            # NOAA MRMS QPE
            "mrms": ["noaa-mrms-qpe-1h-pass1", "noaa-mrms-qpe-24h-pass2"],
            "mrms qpe": ["noaa-mrms-qpe-1h-pass1", "noaa-mrms-qpe-24h-pass2"],
            "quantitative precipitation": ["noaa-mrms-qpe-1h-pass1", "noaa-mrms-qpe-24h-pass2"],
            "precipitation estimate": ["noaa-mrms-qpe-1h-pass1", "noaa-mrms-qpe-24h-pass2"],
            
            # USGS LCMAP
            "lcmap": ["usgs-lcmap-conus-v13"],
            "usgs lcmap": ["usgs-lcmap-conus-v13"],
            "land change monitoring": ["usgs-lcmap-conus-v13"],
            
            # Chesapeake
            "chesapeake": ["chesapeake-lc-7", "chesapeake-lc-13", "chesapeake-lu"],
            "chesapeake land cover": ["chesapeake-lc-7", "chesapeake-lc-13"],
            "chesapeake land use": ["chesapeake-lu"],
            
            # Buildings (Microsoft)
            "buildings": ["ms-buildings"],
            "building footprints": ["ms-buildings"],
            "microsoft buildings": ["ms-buildings"],
            
            # Sentinel-3
            "sentinel-3": ["sentinel-3-olci-wfr-l2-netcdf", "sentinel-3-slstr-wst-l2-netcdf", "sentinel-3-synergy-v10-l2-netcdf"],
            "sentinel 3": ["sentinel-3-olci-wfr-l2-netcdf", "sentinel-3-slstr-wst-l2-netcdf", "sentinel-3-synergy-v10-l2-netcdf"],
            "olci": ["sentinel-3-olci-wfr-l2-netcdf"],
            "slstr": ["sentinel-3-slstr-wst-l2-netcdf"],
            
            # Chloris Biomass
            "chloris": ["chloris-biomass"],
            "chloris biomass": ["chloris-biomass"],
            "biomass": ["chloris-biomass"],
            "aboveground biomass": ["chloris-biomass"],
            "woody biomass": ["chloris-biomass"],
            "forest biomass": ["chloris-biomass"],
            "carbon stock": ["chloris-biomass"],
            "forest carbon": ["chloris-biomass"],
            
            # JRC Global Surface Water
            "jrc": ["jrc-gsw"],
            "jrc gsw": ["jrc-gsw"],
            "jrc global surface water": ["jrc-gsw"],
            "global surface water": ["jrc-gsw"],
            "water occurrence": ["jrc-gsw"],
            "surface water": ["jrc-gsw"],
            
            # NOAA CDR Sea Surface Temperature
            "sea surface temperature": ["noaa-cdr-sea-surface-temperature-whoi"],
            "sst": ["noaa-cdr-sea-surface-temperature-whoi"],
            "ocean temperature": ["noaa-cdr-sea-surface-temperature-whoi"],
            "noaa cdr sst": ["noaa-cdr-sea-surface-temperature-whoi"],
            
            # ALOS World 3D
            "alos world 3d": ["alos-dem"],
            "alos dem": ["alos-dem"],
            "alos 3d": ["alos-dem"],
            "aw3d": ["alos-dem"],
            
            # USGS 3DEP Lidar
            "3dep": ["3dep-lidar-hag"],
            "usgs 3dep": ["3dep-lidar-hag"],
            "lidar": ["3dep-lidar-hag"],
            "lidar hag": ["3dep-lidar-hag"],
            "height above ground": ["3dep-lidar-hag"],
            "usgs lidar": ["3dep-lidar-hag"],
            
            # ALOS PALSAR
            "alos palsar": ["alos-palsar-mosaic"],
            "palsar": ["alos-palsar-mosaic"],
            "alos palsar mosaic": ["alos-palsar-mosaic"],
            "alos palsar annual": ["alos-palsar-mosaic"],
            "l-band sar": ["alos-palsar-mosaic"],
        }
        
        # Add all explicit mappings (case-insensitive)
        for keyword, collection_ids in explicit_mappings.items():
            keyword_lower = keyword.lower()
            if keyword_lower not in keyword_map:
                keyword_map[keyword_lower] = []
            keyword_map[keyword_lower].extend(collection_ids)
        
        # Add all collection IDs as keywords (exact match)
        for col in self.collections:
            col_id = col["collection_id"].lower()
            if col_id not in keyword_map:
                keyword_map[col_id] = []
            keyword_map[col_id].append(col["collection_id"])
        
        return keyword_map
    
    def find_collections_by_keywords(self, query: str) -> List[str]:
        """
        Find collection IDs that match keywords in the query
        Returns list of collection IDs sorted by relevance (longer/more-specific matches first)
        """
        query_lower = query.lower()
        collection_scores = {}
        
        # Check each keyword in our mapping and score matches
        for keyword, collection_ids in self.keyword_map.items():
            if keyword in query_lower:
                # Score = length of matched keyword (longer = more specific)
                # Bonus for exact word boundaries (not just substring)
                score = len(keyword)
                
                # Check for word boundary match (higher priority)
                import re
                if re.search(r'\b' + re.escape(keyword) + r'\b', query_lower):
                    score += 100  # Big bonus for whole-word match
                
                for collection_id in collection_ids:
                    if collection_id not in collection_scores:
                        collection_scores[collection_id] = 0
                    collection_scores[collection_id] += score
        
        # Sort by score (highest first)
        sorted_collections = sorted(collection_scores.items(), key=lambda x: x[1], reverse=True)
        return [collection_id for collection_id, score in sorted_collections]
    
    def get_collection_description(self, collection_id: str) -> Optional[str]:
        """Get description for a collection ID"""
        return self.collection_descriptions.get(collection_id)
    
    def get_all_collection_ids(self) -> List[str]:
        """Get list of all available collection IDs"""
        return [col["collection_id"] for col in self.collections]
    
    def get_collections_by_category(self, category: str) -> List[str]:
        """Get all collection IDs in a specific category"""
        return [
            col["collection_id"]
            for col in self.collections
            if col.get("category", "").upper() == category.upper()
        ]

# Singleton instance
_mapper_instance = None

def get_collection_mapper() -> CollectionMapper:
    """Get singleton instance of CollectionMapper"""
    global _mapper_instance
    if _mapper_instance is None:
        _mapper_instance = CollectionMapper()
    return _mapper_instance

# Convenience functions
def find_collections(query: str) -> List[str]:
    """Find collection IDs matching query keywords"""
    return get_collection_mapper().find_collections_by_keywords(query)

def get_description(collection_id: str) -> Optional[str]:
    """Get description for a collection"""
    return get_collection_mapper().get_collection_description(collection_id)

def get_all_collections() -> List[str]:
    """Get all available collection IDs"""
    return get_collection_mapper().get_all_collection_ids()
