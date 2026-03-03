"""
[LAUNCH] Quick Start Cache Module
Pre-computed classifications and locations for demo queries to speed up response time.
Provides ~3-5 second speedup for quick start button clicks by skipping AI classification.
"""

from typing import Dict, Optional, List, Any
import logging

logger = logging.getLogger(__name__)

# ============================================================================
# [LAUNCH] PRE-COMPUTED QUICK START QUERIES
# ============================================================================
# These are the exact queries from the GetStartedButton.tsx component.
# Pre-computing their classification/location data avoids calling GPT for demo queries.
# ============================================================================

QUICKSTART_QUERIES: Dict[str, Dict[str, Any]] = {
    # Fire Detection & Monitoring
    "show wildfire modis data for california": {
        "collections": ["modis-14A1-061"],
        "location": "California",
        "bbox": [-124.48, 32.53, -114.13, 42.01],
        "description": "1km thermal anomalies and fire detection, daily updates",
        "dataset": "MODIS 14A1",
        "intent": "stac"
    },
    "show fire modis thermal anomalies daily activity for australia from june 2025": {
        "collections": ["modis-14A2-061"],
        "location": "Australia",
        "bbox": [112.92, -43.74, 153.64, -10.05],
        "description": "1km thermal anomalies and fire locations, 8-day composite",
        "dataset": "MODIS 14A2",
        "intent": "stac",
        "temporal": "2025-06"
    },
    "show mtbs burn severity for california in 2017": {
        "collections": ["mtbs"],
        "location": "California",
        "bbox": [-124.48, 32.53, -114.13, 42.01],
        "description": "30m burn severity assessment for large fires",
        "dataset": "MTBS",
        "intent": "stac",
        "temporal": "2017"
    },
    
    # High Resolution Imagery
    "show harmonized landsat sentinel-2 imagery of athens": {
        "collections": ["hls2-l30", "hls2-s30"],
        "location": "Athens",
        "bbox": [23.27, 37.81, 24.57, 38.83],
        "description": "30m resolution harmonized imagery",
        "dataset": "HLS",
        "intent": "stac"
    },
    "show harmonized landsat sentinel-2 (hls) version 2.0 images of moscow from november 2024": {
        "collections": ["hls2-l30", "hls2-s30"],
        "location": "Moscow",
        "bbox": [37.32, 55.57, 37.94, 55.92],
        "description": "30m resolution harmonized imagery",
        "dataset": "HLS S30",
        "intent": "stac",
        "temporal": "2024-11"
    },
    "show hls images of washington dc": {
        "collections": ["hls2-l30", "hls2-s30"],
        "location": "Washington DC",
        "bbox": [-77.12, 38.79, -76.91, 38.99],
        "description": "30m resolution harmonized imagery",
        "dataset": "HLS S30",
        "intent": "stac"
    },
    
    # Water & Surface Reflectance
    "display jrc global surface water in bangladesh": {
        "collections": ["jrc-gsw"],
        "location": "Bangladesh",
        "bbox": [88.01, 20.74, 92.68, 26.63],
        "description": "30m water occurrence mapping",
        "dataset": "JRC Global Surface Water",
        "intent": "stac"
    },
    "show modis snow cover daily for quebec for january 2025": {
        "collections": ["modis-10A1-061"],
        "location": "Quebec",
        "bbox": [-79.76, 44.99, -57.10, 62.59],
        "description": "500m snow cover and NDSI, daily updates",
        "dataset": "MODIS 10A1",
        "intent": "stac",
        "temporal": "2025-01"
    },
    "show me sea surface temperature near madagascar": {
        "collections": ["noaa-cdr-sea-surface-temperature-whoi"],
        "location": "Madagascar",
        "bbox": [43.22, -25.61, 50.48, -11.95],
        "description": "0.25° resolution daily sea surface temperature",
        "dataset": "NOAA CDR SST",
        "intent": "stac"
    },
    
    # Vegetation & Agriculture
    "show modis net primary production for san jose": {
        "collections": ["modis-17A3HGF-061"],
        "location": "San Jose",
        "bbox": [-122.05, 37.18, -121.64, 37.47],
        "description": "500m net primary productivity",
        "dataset": "MODIS 17A3HGF",
        "intent": "stac"
    },
    "show me chloris biomass for the amazon rainforest": {
        "collections": ["chloris-biomass"],
        "location": "Amazon Rainforest",
        "bbox": [-73.98, -18.03, -43.94, 5.27],
        "description": "30m aboveground woody biomass",
        "dataset": "Chloris Biomass",
        "intent": "stac"
    },
    "show modis vedgetation indices for ukraine": {
        "collections": ["modis-13Q1-061"],
        "location": "Ukraine",
        "bbox": [22.14, 44.39, 40.22, 52.38],
        "description": "250m NDVI and EVI vegetation indices",
        "dataset": "MODIS 13Q1",
        "intent": "stac"
    },
    "show usda cropland data layers (cdls) for florida": {
        "collections": ["usda-cdl"],
        "location": "Florida",
        "bbox": [-87.63, 24.52, -80.03, 31.00],
        "description": "30m crop-specific land cover",
        "dataset": "USDA CDL",
        "intent": "stac"
    },
    "show recent modis nadir bdrf adjusted reflectance for mexico": {
        "collections": ["modis-43A4-061"],
        "location": "Mexico",
        "bbox": [-117.12, 14.53, -86.81, 32.72],
        "description": "500m nadir BRDF-adjusted reflectance",
        "dataset": "MODIS 43A4",
        "intent": "stac"
    },
    
    # Elevation & Buildings
    "show dem elevation map of grand canyon": {
        "collections": ["cop-dem-glo-30"],
        "location": "Grand Canyon",
        "bbox": [-113.83, 35.81, -111.79, 36.41],
        "description": "30m Copernicus Digital Elevation Model",
        "dataset": "COP-DEM GLO-30",
        "intent": "stac"
    },
    "show elevation map of grand canyon": {
        "collections": ["cop-dem-glo-30"],
        "location": "Grand Canyon",
        "bbox": [-113.83, 35.81, -111.79, 36.41],
        "description": "30m Copernicus Digital Elevation Model",
        "dataset": "COP-DEM GLO-30",
        "intent": "stac"
    },
    "show elevation map of mount rainier, washington": {
        "collections": ["cop-dem-glo-30"],
        "location": "Mount Rainier, Washington",
        "bbox": [-121.87, 46.72, -121.63, 46.92],
        "description": "30m Copernicus Digital Elevation Model",
        "dataset": "COP-DEM GLO-30",
        "intent": "stac"
    },
    "show alos world 3d-30m of tomas de berlanga": {
        "collections": ["alos-dem"],
        "location": "Tomas de Berlanga",
        "bbox": [-91.17, -0.97, -90.87, -0.75],
        "description": "30m ALOS World 3D digital surface model",
        "dataset": "ALOS World 3D-30m",
        "intent": "stac"
    },
    "show usgs 3dep lidar height above ground for new orleans": {
        "collections": ["3dep-lidar-hag"],
        "location": "New Orleans",
        "bbox": [-90.14, 29.87, -89.97, 30.03],
        "description": "High-resolution lidar-derived height above ground",
        "dataset": "USGS 3DEP Lidar HAG",
        "intent": "stac"
    },
    "show usgs 3dep lidar height above ground for denver, colorado": {
        "collections": ["3dep-lidar-hag"],
        "location": "Denver, Colorado",
        "bbox": [-105.11, 39.61, -104.87, 39.87],
        "description": "High-resolution lidar-derived height above ground",
        "dataset": "USGS 3DEP Lidar HAG",
        "intent": "stac"
    },
    
    # Terrain Module Setup Queries
    "show hls imagery of houston": {
        "collections": ["hls2-l30", "hls2-s30"],
        "location": "Houston",
        "bbox": [-95.79, 29.52, -95.01, 30.11],
        "description": "30m resolution harmonized imagery",
        "dataset": "HLS",
        "intent": "stac"
    },
    "display jrc global surface water in florida": {
        "collections": ["jrc-gsw"],
        "location": "Florida",
        "bbox": [-87.63, 24.52, -80.03, 31.00],
        "description": "30m water occurrence mapping",
        "dataset": "JRC Global Surface Water",
        "intent": "stac"
    },
    
    # Mobility Module Setup Queries
    "jalalabad, afghanistan": {
        "collections": ["hls2-l30", "hls2-s30"],
        "location": "Jalalabad, Afghanistan",
        "bbox": [70.32, 34.32, 70.56, 34.50],
        "description": "30m HLS imagery for mobility analysis",
        "dataset": "HLS",
        "intent": "stac"
    },
    "kathmandu, nepal": {
        "collections": ["hls2-l30", "hls2-s30"],
        "location": "Kathmandu, Nepal",
        "bbox": [85.20, 27.60, 85.45, 27.80],
        "description": "30m HLS imagery for mobility analysis",
        "dataset": "HLS",
        "intent": "stac"
    },
    "el fasher, sudan": {
        "collections": ["hls2-l30", "hls2-s30"],
        "location": "El Fasher, Sudan",
        "bbox": [25.28, 13.55, 25.48, 13.75],
        "description": "30m HLS imagery for mobility analysis",
        "dataset": "HLS",
        "intent": "stac"
    },
    
    # Extreme Weather Module Setup Queries
    "bangkok, thailand": {
        "collections": ["hls2-l30", "hls2-s30"],
        "location": "Bangkok, Thailand",
        "bbox": [100.35, 13.60, 100.70, 13.95],
        "description": "30m HLS imagery for climate analysis",
        "dataset": "HLS",
        "intent": "stac"
    },
    "new orleans, louisiana": {
        "collections": ["hls2-l30", "hls2-s30"],
        "location": "New Orleans, Louisiana",
        "bbox": [-90.14, 29.87, -89.97, 30.03],
        "description": "30m HLS imagery for climate analysis",
        "dataset": "HLS",
        "intent": "stac"
    },
    "dhaka, bangladesh": {
        "collections": ["hls2-l30", "hls2-s30"],
        "location": "Dhaka, Bangladesh",
        "bbox": [90.30, 23.65, 90.50, 23.85],
        "description": "30m HLS imagery for climate analysis",
        "dataset": "HLS",
        "intent": "stac"
    },
    "maputo, mozambique": {
        "collections": ["hls2-l30", "hls2-s30"],
        "location": "Maputo, Mozambique",
        "bbox": [32.45, -26.05, 32.70, -25.85],
        "description": "30m HLS imagery for climate analysis",
        "dataset": "HLS",
        "intent": "stac"
    },
    
    # Building Damage Assessment
    # NAIP at 0.6m resolution shows individual buildings, cleared lots, foundations.
    # Post-fire NAIP flown July 2020 — 20 months after Camp Fire (Nov 8-25, 2018).
    # Sentinel-2 (10m) and HLS (30m) are too coarse to see building-level damage.
    "show naip aerial imagery of paradise, california from 2020": {
        "collections": ["naip"],
        "location": "Paradise, California",
        "bbox": [-121.65, 39.73, -121.55, 39.81],
        "description": "0.6m NAIP aerial imagery showing Camp Fire aftermath",
        "dataset": "NAIP",
        "intent": "stac",
        "temporal": "2020"
    },
    "show naip aerial imagery of houston, texas from 2018": {
        "collections": ["naip"],
        "location": "Houston, Texas",
        "bbox": [-95.79, 29.52, -95.01, 30.11],
        "description": "1m NAIP aerial imagery of Houston",
        "dataset": "NAIP",
        "intent": "stac",
        "temporal": "2018"
    },
    
    # SAR Imagery
    "show sentinel 1 rtc for baltimore": {
        "collections": ["sentinel-1-rtc"],
        "location": "Baltimore",
        "bbox": [-76.71, 39.20, -76.53, 39.37],
        "description": "10m Sentinel-1 Radiometrically Terrain Corrected SAR",
        "dataset": "Sentinel-1 RTC",
        "intent": "stac"
    },
    "show alos palsar annual for ecuador": {
        "collections": ["alos-palsar-mosaic"],
        "location": "Ecuador",
        "bbox": [-81.08, -5.01, -75.19, 1.44],
        "description": "25m L-band SAR annual mosaic",
        "dataset": "ALOS PALSAR",
        "intent": "stac"
    },
    "show sentinel 1 radiometrically terrain corrected (rtc) for philippines": {
        "collections": ["sentinel-1-rtc"],
        "location": "Philippines",
        "bbox": [116.93, 4.64, 126.60, 21.12],
        "description": "10m Sentinel-1 Radiometrically Terrain Corrected SAR",
        "dataset": "Sentinel-1 RTC",
        "intent": "stac"
    }
}


def normalize_query(query: str) -> str:
    """Normalize query for matching (lowercase, strip whitespace)."""
    return query.lower().strip()


def is_quickstart_query(query: str) -> bool:
    """Check if a query matches one of the pre-defined quick start queries."""
    normalized = normalize_query(query)
    return normalized in QUICKSTART_QUERIES


def get_quickstart_classification(query: str) -> Optional[Dict[str, Any]]:
    """
    Get pre-computed classification for a quick start query.
    Returns None if the query is not a quick start query.
    
    Returns a classification dict compatible with the main query processor:
    {
        "is_quickstart": True,
        "intent": "stac",
        "collections": [...],
        "has_location": True,
        ...
    }
    """
    normalized = normalize_query(query)
    if normalized not in QUICKSTART_QUERIES:
        return None
    
    qs_data = QUICKSTART_QUERIES[normalized]
    
    return {
        "is_quickstart": True,
        "intent": qs_data.get("intent", "stac"),
        "intent_type": qs_data.get("intent", "stac"),  # Duplicate for compatibility with response generation
        "collections": qs_data.get("collections", []),
        "has_location": True,
        "has_temporal": "temporal" in qs_data,
        "data_type": "satellite_imagery",
        "confidence": 1.0,
        "router_action": None,  # No RouterAgent needed for quickstart
        "description": qs_data.get("description", ""),
        "dataset": qs_data.get("dataset", ""),
        "needs_satellite_data": True,
        "needs_contextual_info": False,
        "needs_vision_analysis": False
    }


def get_quickstart_location(query: str) -> Optional[Dict[str, Any]]:
    """
    Get pre-computed location data for a quick start query.
    Returns None if the query is not a quick start query.
    
    Returns location dict with bbox and location name:
    {
        "location": "California",
        "bbox": [-124.48, 32.53, -114.13, 42.01],
        "collections": ["modis-14A1-061"],
        ...
    }
    """
    normalized = normalize_query(query)
    if normalized not in QUICKSTART_QUERIES:
        return None
    
    qs_data = QUICKSTART_QUERIES[normalized]
    
    return {
        "location": qs_data.get("location", ""),
        "bbox": qs_data.get("bbox", []),
        "collections": qs_data.get("collections", []),
        "temporal": qs_data.get("temporal"),
        "description": qs_data.get("description", ""),
        "dataset": qs_data.get("dataset", "")
    }


def get_quickstart_stats() -> Dict[str, Any]:
    """
    Get statistics about the quick start cache.
    Used for logging at startup.
    
    Returns:
    {
        "total_queries": 17,
        "collections_covered": ["modis-14A1-061", "modis-14A2-061", ...],
        ...
    }
    """
    all_collections = set()
    for query_data in QUICKSTART_QUERIES.values():
        for coll in query_data.get("collections", []):
            all_collections.add(coll)
    
    return {
        "total_queries": len(QUICKSTART_QUERIES),
        "collections_covered": sorted(list(all_collections)),
        "intents": ["stac"],  # Currently all quickstart queries are STAC queries
        "locations": [q.get("location", "") for q in QUICKSTART_QUERIES.values()]
    }


def get_all_quickstart_queries() -> List[str]:
    """Return all quick start query strings."""
    return list(QUICKSTART_QUERIES.keys())


# Log module initialization
logger.info(f"[LAUNCH] Quick Start Cache initialized with {len(QUICKSTART_QUERIES)} pre-computed queries")
