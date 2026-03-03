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
            # ================================================================
            # USDA Cropland Data Layer
            # ================================================================
            "usda": ["usda-cdl"],
            "cdl": ["usda-cdl"],
            "usda-cdl": ["usda-cdl"],
            "usda cdl": ["usda-cdl"],
            "cropland": ["usda-cdl"],
            "crop data layer": ["usda-cdl"],
            "agricultural land": ["usda-cdl"],
            "farmland": ["usda-cdl"],
            
            # ================================================================
            # NAIP (National Agriculture Imagery Program)
            # ================================================================
            "naip": ["naip"],
            "aerial imagery": ["naip"],
            "high resolution imagery": ["naip"],
            "aerial photo": ["naip"],
            "aerial photographs": ["naip"],
            
            # ================================================================
            # Landsat
            # ================================================================
            "landsat": ["landsat-c2-l2"],
            "landsat 4": ["landsat-c2-l2"],
            "landsat 5": ["landsat-c2-l2"],
            "landsat 7": ["landsat-c2-l2"],
            "landsat 8": ["landsat-c2-l2"],
            "landsat 9": ["landsat-c2-l2"],
            "landsat tm": ["landsat-c2-l2"],
            "landsat etm": ["landsat-c2-l2"],
            "landsat etm+": ["landsat-c2-l2"],
            "landsat oli": ["landsat-c2-l2"],
            "landsat c2": ["landsat-c2-l2"],
            "landsat level 2": ["landsat-c2-l2"],
            "landsat l2": ["landsat-c2-l2"],
            "landsat surface reflectance": ["landsat-c2-l2"],
            "landsat level 1": ["landsat-c2-l1"],
            "landsat l1": ["landsat-c2-l1"],
            "landsat toa": ["landsat-c2-l1"],
            "landsat top of atmosphere": ["landsat-c2-l1"],
            
            # ================================================================
            # Sentinel-2 (Optical)
            # ================================================================
            "sentinel": ["sentinel-2-l2a"],
            "sentinel-2": ["sentinel-2-l2a"],
            "sentinel 2": ["sentinel-2-l2a"],
            "s2": ["sentinel-2-l2a"],
            
            # ================================================================
            # Sentinel-1 (SAR)
            # ================================================================
            "sentinel-1": ["sentinel-1-rtc"],
            "sentinel 1": ["sentinel-1-rtc"],
            "sar": ["sentinel-1-rtc", "sentinel-1-grd"],
            "radar": ["sentinel-1-rtc", "sentinel-1-grd"],
            "rtc": ["sentinel-1-rtc"],
            "sentinel-1 grd": ["sentinel-1-grd"],
            "sentinel 1 grd": ["sentinel-1-grd"],
            "ground range detected": ["sentinel-1-grd"],
            "sar grd": ["sentinel-1-grd"],
            
            # ================================================================
            # MODIS - Comprehensive coverage of all products
            # ================================================================
            # General MODIS
            "modis": ["modis-14A2-061", "modis-14A1-061", "modis-10A1-061", "modis-09Q1-061", "modis-13Q1-061", "modis-64A1-061"],
            
            # Fire products (14A1=daily, 14A2=8-day, 64A1=burned area)
            "modis fire": ["modis-14A2-061", "modis-14A1-061"],
            "modis fire daily": ["modis-14A1-061"],
            "modis fire 8-day": ["modis-14A2-061"],
            "fire detection": ["modis-14A2-061", "modis-14A1-061"],
            "thermal anomalies": ["modis-14A2-061", "modis-14A1-061"],
            "active fire": ["modis-14A1-061"],
            "burned area": ["modis-64A1-061"],
            "modis burned area": ["modis-64A1-061"],
            "fire scar": ["modis-64A1-061"],
            
            # ================================================================
            # Climate Projections (NEX-GDDP-CMIP6)
            # ================================================================
            "nasa-nex-gddp-cmip6": ["nasa-nex-gddp-cmip6"],
            "nasa nex-gddp-cmip6": ["nasa-nex-gddp-cmip6"],
            "nex-gddp": ["nasa-nex-gddp-cmip6"],
            "nex gddp": ["nasa-nex-gddp-cmip6"],
            "cmip6": ["nasa-nex-gddp-cmip6"],
            "cmip 6": ["nasa-nex-gddp-cmip6"],
            "climate projection": ["nasa-nex-gddp-cmip6"],
            "climate projections": ["nasa-nex-gddp-cmip6"],
            "climate scenario": ["nasa-nex-gddp-cmip6"],
            "climate model": ["nasa-nex-gddp-cmip6"],
            "extreme weather": ["nasa-nex-gddp-cmip6"],
            "temperature projection": ["nasa-nex-gddp-cmip6"],
            "precipitation projection": ["nasa-nex-gddp-cmip6"],
            "downscaled climate": ["nasa-nex-gddp-cmip6"],
            "ssp585": ["nasa-nex-gddp-cmip6"],
            "ssp245": ["nasa-nex-gddp-cmip6"],
            
            # Snow/Ice products (10A1=daily, 10A2=8-day)
            "modis snow": ["modis-10A1-061"],
            "snow cover": ["modis-10A1-061", "modis-10A2-061"],
            "snow": ["modis-10A1-061", "modis-10A2-061"],
            "modis snow daily": ["modis-10A1-061"],
            "modis snow 8-day": ["modis-10A2-061"],
            "snow 8-day": ["modis-10A2-061"],
            "ice cover": ["modis-10A1-061", "modis-10A2-061"],
            
            # Surface reflectance (09A1=500m 8-day, 09Q1=250m 8-day)
            "modis surface reflectance": ["modis-09A1-061", "modis-09Q1-061"],
            "modis reflectance": ["modis-09A1-061", "modis-09Q1-061"],
            "modis 09a1": ["modis-09A1-061"],
            "modis 09q1": ["modis-09Q1-061"],
            "mod09a1": ["modis-09A1-061"],
            "mod09q1": ["modis-09Q1-061"],
            
            # Land Surface Temperature (11A1=daily, 11A2=8-day, 21A2=emissivity)
            "land surface temperature": ["modis-11A1-061", "modis-11A2-061"],
            "modis lst": ["modis-11A1-061", "modis-11A2-061"],
            "modis temperature": ["modis-11A1-061", "modis-11A2-061"],
            "modis temperature daily": ["modis-11A1-061"],
            "modis lst daily": ["modis-11A1-061"],
            "modis lst 8-day": ["modis-11A2-061"],
            "surface temperature": ["modis-11A1-061", "modis-11A2-061"],
            "lst": ["modis-11A1-061"],
            "modis emissivity": ["modis-21A2-061"],
            "emissivity": ["modis-21A2-061"],
            
            # Vegetation Indices (13A1=500m, 13Q1=250m)
            "modis ndvi": ["modis-13Q1-061", "modis-13A1-061"],
            "modis vegetation": ["modis-13Q1-061", "modis-13A1-061"],
            "modis evi": ["modis-13Q1-061", "modis-13A1-061"],
            "ndvi": ["modis-13Q1-061", "modis-13A1-061"],
            "vegetation index": ["modis-13Q1-061", "modis-13A1-061"],
            "vegetation health": ["modis-13Q1-061", "modis-13A1-061"],
            "modis ndvi 500m": ["modis-13A1-061"],
            "mod13a1": ["modis-13A1-061"],
            "mod13q1": ["modis-13Q1-061"],
            
            # LAI/FPAR (15A2H=8-day, 15A3H=4-day)
            "leaf area index": ["modis-15A2H-061", "modis-15A3H-061"],
            "lai": ["modis-15A2H-061"],
            "fpar": ["modis-15A2H-061"],
            "modis lai": ["modis-15A2H-061"],
            "lai fpar": ["modis-15A2H-061"],
            "photosynthetically active radiation": ["modis-15A2H-061"],
            
            # Evapotranspiration (16A3GF)
            "evapotranspiration": ["modis-16A3GF-061"],
            "modis et": ["modis-16A3GF-061"],
            "modis evapotranspiration": ["modis-16A3GF-061"],
            "net evapotranspiration": ["modis-16A3GF-061"],
            
            # GPP/NPP (17A2H=GPP 8-day, 17A2HGF=GPP gap-filled, 17A3HGF=NPP annual)
            "gross primary productivity": ["modis-17A2H-061", "modis-17A2HGF-061"],
            "modis gpp": ["modis-17A2H-061", "modis-17A2HGF-061"],
            "gpp": ["modis-17A2H-061"],
            "net primary production": ["modis-17A3HGF-061"],
            "modis npp": ["modis-17A3HGF-061"],
            "npp": ["modis-17A3HGF-061"],
            "primary productivity": ["modis-17A2H-061", "modis-17A3HGF-061"],
            "carbon productivity": ["modis-17A2H-061", "modis-17A3HGF-061"],
            
            # NBAR (43A4=BRDF-adjusted reflectance)
            "modis nbar": ["modis-43A4-061"],
            "nbar": ["modis-43A4-061"],
            "nadir brdf": ["modis-43A4-061"],
            "brdf": ["modis-43A4-061"],
            "mcd43a4": ["modis-43A4-061"],
            "modis true color": ["modis-43A4-061"],
            
            # ================================================================
            # MTBS (Monitoring Trends in Burn Severity)
            # ================================================================
            "mtbs": ["mtbs"],
            "burn severity": ["mtbs"],
            "fire severity": ["mtbs"],
            "wildfire severity": ["mtbs"],
            "monitoring trends burn severity": ["mtbs"],
            "post-fire": ["mtbs"],
            "post fire": ["mtbs"],
            "fire damage assessment": ["mtbs"],
            "burn assessment": ["mtbs"],
            
            # ================================================================
            # HLS (Harmonized Landsat Sentinel)
            # ================================================================
            "hls": ["hls2-l30", "hls2-s30"],
            "hls2": ["hls2-l30", "hls2-s30"],
            "harmonized landsat sentinel": ["hls2-l30", "hls2-s30"],
            "hls landsat": ["hls2-l30"],
            "hls sentinel": ["hls2-s30"],
            
            # ================================================================
            # DEM / Elevation - comprehensive coverage
            # ================================================================
            "elevation": ["cop-dem-glo-30"],
            "dem": ["cop-dem-glo-30"],
            "terrain": ["cop-dem-glo-30"],
            "topography": ["cop-dem-glo-30"],
            "cop-dem": ["cop-dem-glo-30"],
            "copernicus dem": ["cop-dem-glo-30"],
            "cop-dem-glo-90": ["cop-dem-glo-90"],
            "copernicus 90m": ["cop-dem-glo-90"],
            "90m elevation": ["cop-dem-glo-90"],
            "90 meter dem": ["cop-dem-glo-90"],
            "nasadem": ["nasadem"],
            "nasa dem": ["nasadem"],
            "nasa elevation": ["nasadem"],
            "srtm": ["nasadem"],
            "height map": ["cop-dem-glo-30"],
            "relief": ["cop-dem-glo-30"],
            "slope": ["cop-dem-glo-30"],
            "hillshade": ["cop-dem-glo-30"],
            
            # ================================================================
            # Land Cover & Land Use
            # ================================================================
            "land cover": ["io-lulc-annual-v02", "esa-worldcover"],
            "lulc": ["io-lulc-annual-v02"],
            "io land cover": ["io-lulc-annual-v02"],
            "io lulc": ["io-lulc-annual-v02"],
            "io-lulc": ["io-lulc-annual-v02"],
            "impact observatory": ["io-lulc-annual-v02"],
            "esri land cover": ["io-lulc-annual-v02"],
            "10m land cover": ["io-lulc-annual-v02"],
            "io lulc 9 class": ["io-lulc-9-class"],
            "io-lulc-9-class": ["io-lulc-9-class"],
            "9 class land cover": ["io-lulc-9-class"],
            "esa worldcover": ["esa-worldcover"],
            "worldcover": ["esa-worldcover"],
            "esa cci": ["esa-cci-lc"],
            "esa-cci-lc": ["esa-cci-lc"],
            "cci land cover": ["esa-cci-lc"],
            "climate change initiative land cover": ["esa-cci-lc"],
            "drcog": ["drcog-lulc"],
            "drcog lulc": ["drcog-lulc"],
            "denver land cover": ["drcog-lulc"],
            "denver land use": ["drcog-lulc"],
            "denver regional": ["drcog-lulc"],
            "nrcan": ["nrcan-landcover"],
            "nrcan landcover": ["nrcan-landcover"],
            "canada land cover": ["nrcan-landcover"],
            "canadian land cover": ["nrcan-landcover"],
            
            # ================================================================
            # NOAA Climate
            # ================================================================
            "climate normals": ["noaa-climate-normals-gridded"],
            "noaa climate": ["noaa-climate-normals-gridded"],
            "temperature normals": ["noaa-climate-normals-gridded"],
            "precipitation normals": ["noaa-climate-normals-gridded"],
            
            # NOAA NClimGrid
            "nclimgrid": ["noaa-nclimgrid-monthly"],
            "noaa nclimgrid": ["noaa-nclimgrid-monthly"],
            
            # NOAA MRMS QPE
            "mrms": ["noaa-mrms-qpe-1h-pass1", "noaa-mrms-qpe-1h-pass2", "noaa-mrms-qpe-24h-pass2"],
            "mrms qpe": ["noaa-mrms-qpe-1h-pass1", "noaa-mrms-qpe-1h-pass2", "noaa-mrms-qpe-24h-pass2"],
            "quantitative precipitation": ["noaa-mrms-qpe-1h-pass1", "noaa-mrms-qpe-24h-pass2"],
            "precipitation estimate": ["noaa-mrms-qpe-1h-pass1", "noaa-mrms-qpe-24h-pass2"],
            "rainfall estimate": ["noaa-mrms-qpe-1h-pass1", "noaa-mrms-qpe-24h-pass2"],
            
            # NOAA C-CAP (Coastal Change Analysis)
            "noaa c-cap": ["noaa-c-cap"],
            "c-cap": ["noaa-c-cap"],
            "coastal land cover": ["noaa-c-cap"],
            "coastal change analysis": ["noaa-c-cap"],
            "coastal change": ["noaa-c-cap"],
            
            # ================================================================
            # USGS LCMAP
            # ================================================================
            "lcmap": ["usgs-lcmap-conus-v13"],
            "usgs lcmap": ["usgs-lcmap-conus-v13"],
            "land change monitoring": ["usgs-lcmap-conus-v13"],
            "lcmap hawaii": ["usgs-lcmap-hawaii-v10"],
            "usgs lcmap hawaii": ["usgs-lcmap-hawaii-v10"],
            "hawaii land change": ["usgs-lcmap-hawaii-v10"],
            
            # ================================================================
            # USGS GAP
            # ================================================================
            "usgs gap": ["usgs-gap"],
            "gap analysis": ["usgs-gap"],
            "habitat model": ["usgs-gap"],
            "species habitat": ["usgs-gap"],
            
            # ================================================================
            # Chesapeake
            # ================================================================
            "chesapeake": ["chesapeake-lc-7", "chesapeake-lc-13", "chesapeake-lu"],
            "chesapeake land cover": ["chesapeake-lc-7", "chesapeake-lc-13"],
            "chesapeake land use": ["chesapeake-lu"],
            
            # ================================================================
            # Buildings (Microsoft)
            # ================================================================
            "buildings": ["ms-buildings"],
            "building footprints": ["ms-buildings"],
            "microsoft buildings": ["ms-buildings"],
            
            # ================================================================
            # Sentinel-3
            # ================================================================
            "sentinel-3": ["sentinel-3-olci-wfr-l2-netcdf", "sentinel-3-slstr-wst-l2-netcdf", "sentinel-3-synergy-v10-l2-netcdf"],
            "sentinel 3": ["sentinel-3-olci-wfr-l2-netcdf", "sentinel-3-slstr-wst-l2-netcdf", "sentinel-3-synergy-v10-l2-netcdf"],
            "olci": ["sentinel-3-olci-wfr-l2-netcdf"],
            "slstr": ["sentinel-3-slstr-wst-l2-netcdf"],
            
            # ================================================================
            # Chloris Biomass
            # ================================================================
            "chloris": ["chloris-biomass"],
            "chloris biomass": ["chloris-biomass"],
            "biomass": ["chloris-biomass"],
            "aboveground biomass": ["chloris-biomass"],
            "woody biomass": ["chloris-biomass"],
            "forest biomass": ["chloris-biomass"],
            "carbon stock": ["chloris-biomass"],
            "forest carbon": ["chloris-biomass"],
            
            # ================================================================
            # JRC Global Surface Water
            # ================================================================
            "jrc": ["jrc-gsw"],
            "jrc gsw": ["jrc-gsw"],
            "jrc global surface water": ["jrc-gsw"],
            "global surface water": ["jrc-gsw"],
            "water occurrence": ["jrc-gsw"],
            "surface water": ["jrc-gsw"],
            "water extent": ["jrc-gsw"],
            "water body mapping": ["jrc-gsw"],
            
            # ================================================================
            # NOAA CDR Sea Surface Temperature
            # ================================================================
            "sea surface temperature": ["noaa-cdr-sea-surface-temperature-whoi"],
            "sst": ["noaa-cdr-sea-surface-temperature-whoi"],
            "ocean temperature": ["noaa-cdr-sea-surface-temperature-whoi"],
            "noaa cdr sst": ["noaa-cdr-sea-surface-temperature-whoi"],
            
            # ================================================================
            # ALOS
            # ================================================================
            # ALOS World 3D / DEM
            "alos world 3d": ["alos-dem"],
            "alos dem": ["alos-dem"],
            "alos 3d": ["alos-dem"],
            "aw3d": ["alos-dem"],
            
            # ALOS PALSAR
            "alos palsar": ["alos-palsar-mosaic"],
            "palsar": ["alos-palsar-mosaic"],
            "alos palsar mosaic": ["alos-palsar-mosaic"],
            "alos palsar annual": ["alos-palsar-mosaic"],
            "l-band sar": ["alos-palsar-mosaic"],
            
            # ALOS Forest/Non-Forest
            "alos fnf": ["alos-fnf-mosaic"],
            "forest non-forest": ["alos-fnf-mosaic"],
            "alos forest": ["alos-fnf-mosaic"],
            "forest mosaic": ["alos-fnf-mosaic"],
            "fnf": ["alos-fnf-mosaic"],
            
            # ================================================================
            # USGS 3DEP Lidar - comprehensive coverage
            # ================================================================
            "3dep": ["3dep-lidar-hag"],
            "usgs 3dep": ["3dep-lidar-hag"],
            "lidar": ["3dep-lidar-hag"],
            "lidar hag": ["3dep-lidar-hag"],
            "height above ground": ["3dep-lidar-hag"],
            "usgs lidar": ["3dep-lidar-hag"],
            "lidar dsm": ["3dep-lidar-dsm"],
            "digital surface model": ["3dep-lidar-dsm"],
            "3dep dsm": ["3dep-lidar-dsm"],
            "lidar dtm": ["3dep-lidar-dtm"],
            "digital terrain model": ["3dep-lidar-dtm"],
            "3dep dtm": ["3dep-lidar-dtm"],
            "lidar classification": ["3dep-lidar-classification"],
            "point cloud classification": ["3dep-lidar-classification"],
            "3dep classification": ["3dep-lidar-classification"],
            "lidar intensity": ["3dep-lidar-intensity"],
            "3dep intensity": ["3dep-lidar-intensity"],
            "lidar returns": ["3dep-lidar-returns"],
            "3dep returns": ["3dep-lidar-returns"],
            "3dep seamless": ["3dep-seamless"],
            "seamless elevation": ["3dep-seamless"],
            "usgs seamless": ["3dep-seamless"],
            
            # ================================================================
            # ASTER
            # ================================================================
            "aster": ["aster"],
            "aster l1t": ["aster"],
            "aster satellite": ["aster"],
            "advanced spaceborne thermal emission": ["aster"],
            
            # ================================================================
            # Biodiversity & Ecology
            # ================================================================
            "io biodiversity": ["io-biodiversity"],
            "biodiversity intactness": ["io-biodiversity"],
            "biodiversity": ["io-biodiversity"],
            "species intactness": ["io-biodiversity"],
            "mobi": ["mobi"],
            "biodiversity importance": ["mobi"],
            "map of biodiversity importance": ["mobi"],
            
            # ================================================================
            # Harmonized Global Biomass
            # ================================================================
            "hgb": ["hgb"],
            "harmonized global biomass": ["hgb"],
            "global biomass": ["hgb"],
            
            # ================================================================
            # HREA (High Resolution Electricity Access)
            # ================================================================
            "hrea": ["hrea"],
            "electricity access": ["hrea"],
            "high resolution electricity access": ["hrea"],
            "electrification": ["hrea"],
            "night lights": ["hrea"],
            
            # ================================================================
            # Generic / Implicit collection keywords
            # ================================================================
            "satellite imagery": ["sentinel-2-l2a", "landsat-c2-l2"],
            "satellite": ["sentinel-2-l2a", "landsat-c2-l2"],
            "imagery": ["sentinel-2-l2a", "landsat-c2-l2"],
            "optical imagery": ["sentinel-2-l2a", "landsat-c2-l2", "naip"],
            "multispectral": ["sentinel-2-l2a", "landsat-c2-l2"],
            "true color": ["sentinel-2-l2a", "landsat-c2-l2", "naip"],
            "false color": ["sentinel-2-l2a", "landsat-c2-l2"],
            "infrared": ["sentinel-2-l2a", "landsat-c2-l2"],
            "vegetation": ["modis-13Q1-061", "sentinel-2-l2a"],
            "flood": ["sentinel-1-rtc", "sentinel-2-l2a"],
            "flood map": ["sentinel-1-rtc", "sentinel-2-l2a"],
            "wildfire": ["modis-14A1-061", "modis-14A2-061", "mtbs"],
            "drought": ["modis-13Q1-061", "modis-16A3GF-061"],
            "deforestation": ["sentinel-2-l2a", "landsat-c2-l2", "alos-fnf-mosaic"],
            "urban": ["sentinel-2-l2a", "naip", "io-lulc-annual-v02"],
            "agriculture": ["usda-cdl", "sentinel-2-l2a", "modis-13Q1-061"],
            "forest": ["sentinel-2-l2a", "alos-fnf-mosaic", "chloris-biomass"],
            "water": ["jrc-gsw", "sentinel-2-l2a"],
            "ocean": ["noaa-cdr-sea-surface-temperature-whoi", "sentinel-2-l2a"],
            "precipitation": ["noaa-mrms-qpe-1h-pass1", "noaa-mrms-qpe-24h-pass2"],
            "rainfall": ["noaa-mrms-qpe-1h-pass1", "noaa-mrms-qpe-24h-pass2"],
            "temperature": ["modis-11A1-061", "noaa-climate-normals-gridded"],
            "climate": ["noaa-climate-normals-gridded", "noaa-nclimgrid-monthly"],
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
