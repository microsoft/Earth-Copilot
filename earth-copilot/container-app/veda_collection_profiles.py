# Copyright (c) Microsoft Corporation.
# Licensed under the MIT license.

"""
VEDA Collection Profiles - VERIFIED WORKING COLLECTIONS
Based on comprehensive VEDA availability testing (September 28, 2025)
10 working collections out of 10 tested (100% success rate with no_datetime strategy)

Key Finding: VEDA collections are primarily STATIC/HISTORICAL datasets that work best 
without datetime filters, unlike Planetary Computer's time-series satellite data.
"""

# Comprehensive collection profiles for all verified working VEDA collections
VEDA_COLLECTION_PROFILES = {
    
    # ========================================
    # 1. LAND COVER/VEGETATION (1/1 working - 100% success)
    # ========================================
    "bangladesh-landcover-2001-2020": {
        "name": "Annual land cover maps for 2001 and 2020",
        "category": "land_cover",
        "resolution": "500m",
        "status": "limited",  # Works with no_datetime only
        "visualization": {
            "type": "land_cover",
            "renderer": "categorical",
            "assets": {
                "cog_default": "cog_default"
            },
            "colormap": {
                "0": [0, 0, 0, 128],      # No data
                "100": [0, 130, 0, 255],  # Forest
                "200": [17, 131, 226, 255], # Water
                "300": [199, 43, 32, 255],  # Urban
                "400": [98, 234, 37, 255]   # Cropland
            }
        },
        "temporal": {"start": "2001-01-01", "end": "2020-12-31", "static": True},
        "platform": "MODIS MCD12Q1",
        "best_strategy": "no_datetime",
        "query_pattern": {"collections": ["bangladesh-landcover-2001-2020"]},
        "use_cases": ["land cover change", "bangladesh", "modis land cover", "vegetation mapping"]
    },
    
    # ========================================
    # 2. FIRE DETECTION (1/1 working - 100% success)
    # ========================================
    "barc-thomasfire": {
        "name": "Burn Area Reflectance Classification for Thomas Fire",
        "category": "fire_detection",
        "resolution": "30m",
        "status": "limited",
        "visualization": {
            "type": "burn_severity",
            "renderer": "categorical",
            "assets": {
                "cog_default": "cog_default"
            },
            "stretch": {"type": "categorical"}
        },
        "temporal": {"start": "2017-12-01", "end": "2017-12-31", "static": True},
        "platform": "Landsat-derived BARC",
        "best_strategy": "no_datetime",
        "query_pattern": {"collections": ["barc-thomasfire"]},
        "use_cases": ["thomas fire", "burn severity", "barc", "wildfire damage", "california fire"]
    },
    
    # ========================================
    # 3. CLIMATE/WEATHER RESEARCH (4/4 working - 100% success)
    # ========================================
    "blizzard-era5-10m-wind": {
        "name": "ERA5 Reanalysis – 10 Meter Wind (Select Events)",
        "category": "climate_weather",
        "resolution": "0.25°",
        "status": "limited",
        "visualization": {
            "type": "wind_speed",
            "renderer": "continuous",
            "assets": {
                "cog_default": "cog_default"
            },
            "stretch": {"type": "percentile", "min": 2, "max": 98}
        },
        "temporal": {"start": "select events", "end": "select events", "static": True},
        "platform": "ERA5 Reanalysis",
        "best_strategy": "no_datetime",
        "query_pattern": {"collections": ["blizzard-era5-10m-wind"]},
        "use_cases": ["era5", "wind", "blizzard", "weather reanalysis", "10m wind"]
    },
    
    "blizzard-era5-2m-temp": {
        "name": "ERA5 Reanalysis – 2 Meter Temperature (Select Events)",
        "category": "climate_weather",
        "resolution": "0.25°",
        "status": "limited",
        "visualization": {
            "type": "temperature",
            "renderer": "continuous",
            "assets": {
                "cog_default": "cog_default"
            },
            "stretch": {"type": "percentile", "min": 2, "max": 98}
        },
        "temporal": {"start": "select events", "end": "select events", "static": True},
        "platform": "ERA5 Reanalysis",
        "best_strategy": "no_datetime",
        "query_pattern": {"collections": ["blizzard-era5-2m-temp"]},
        "use_cases": ["era5", "temperature", "blizzard", "weather reanalysis", "2m temperature"]
    },
    
    "blizzard-era5-cfrac": {
        "name": "ERA5 Reanalysis – Cloud Fraction (Select Events)",
        "category": "climate_weather",
        "resolution": "0.25°",
        "status": "limited",
        "visualization": {
            "type": "cloud_fraction",
            "renderer": "continuous",
            "assets": {
                "cog_default": "cog_default"
            },
            "stretch": {"type": "percentile", "min": 0, "max": 100}
        },
        "temporal": {"start": "select events", "end": "select events", "static": True},
        "platform": "ERA5 Reanalysis",
        "best_strategy": "no_datetime",
        "query_pattern": {"collections": ["blizzard-era5-cfrac"]},
        "use_cases": ["era5", "cloud fraction", "blizzard", "weather reanalysis", "clouds"]
    },
    
    "blizzard-era5-mslp": {
        "name": "ERA5 Reanalysis – Mean Sea Level Pressure (Select Events)",
        "category": "climate_weather",
        "resolution": "0.25°",
        "status": "limited",
        "visualization": {
            "type": "pressure",
            "renderer": "continuous",
            "assets": {
                "cog_default": "cog_default"
            },
            "stretch": {"type": "percentile", "min": 2, "max": 98}
        },
        "temporal": {"start": "select events", "end": "select events", "static": True},
        "platform": "ERA5 Reanalysis",
        "best_strategy": "no_datetime",
        "query_pattern": {"collections": ["blizzard-era5-mslp"]},
        "use_cases": ["era5", "pressure", "blizzard", "weather reanalysis", "sea level pressure"]
    },
    
    # ========================================
    # 4. RESEARCH/SPECIALIZED (4/4 working - 100% success)
    # ========================================
    "blizzard-alley": {
        "name": "Blizzard Alley",
        "category": "research_specialized",
        "resolution": "statistical",
        "status": "limited",
        "visualization": {
            "type": "frequency_map",
            "renderer": "continuous",
            "assets": {
                "cog_default": "cog_default"
            },
            "stretch": {"type": "percentile", "min": 2, "max": 98}
        },
        "temporal": {"start": "1950", "end": "2021", "static": True},
        "platform": "NCEI Storm Events Database",
        "best_strategy": "no_datetime",
        "query_pattern": {"collections": ["blizzard-alley"]},
        "use_cases": ["blizzard alley", "blizzard frequency", "storm climatology", "north dakota"]
    },
    
    "blizzard-clipper": {
        "name": "AB/SK/MB Clipper Snowfall Footprint",
        "category": "research_specialized",
        "resolution": "statistical",
        "status": "limited",
        "visualization": {
            "type": "snowfall_footprint",
            "renderer": "continuous",
            "assets": {
                "cog_default": "cog_default"
            },
            "stretch": {"type": "percentile", "min": 2, "max": 98}
        },
        "temporal": {"start": "climatological", "end": "climatological", "static": True},
        "platform": "Storm Analysis",
        "best_strategy": "no_datetime",
        "query_pattern": {"collections": ["blizzard-clipper"]},
        "use_cases": ["alberta clipper", "saskatchewan screamer", "manitoba mauler", "snowfall patterns"]
    },
    
    "blizzard-co-low": {
        "name": "Colorado Low Snowfall Footprint",
        "category": "research_specialized",
        "resolution": "statistical",
        "status": "limited",
        "visualization": {
            "type": "snowfall_footprint",
            "renderer": "continuous",
            "assets": {
                "cog_default": "cog_default"
            },
            "stretch": {"type": "percentile", "min": 2, "max": 98}
        },
        "temporal": {"start": "climatological", "end": "climatological", "static": True},
        "platform": "Storm Analysis",
        "best_strategy": "no_datetime",
        "query_pattern": {"collections": ["blizzard-co-low"]},
        "use_cases": ["colorado low", "snowfall patterns", "cyclone footprint"]
    },
    
    "blizzard-count": {
        "name": "Blizzard Count 1950-2021",
        "category": "research_specialized",
        "resolution": "interpolated",
        "status": "limited",
        "visualization": {
            "type": "count_map",
            "renderer": "continuous",
            "assets": {
                "cog_default": "cog_default"
            },
            "stretch": {"type": "percentile", "min": 2, "max": 98}
        },
        "temporal": {"start": "1950", "end": "2021", "static": True},
        "platform": "NCEI Storm Events Database",
        "best_strategy": "no_datetime",
        "query_pattern": {"collections": ["blizzard-count"]},
        "use_cases": ["blizzard count", "storm frequency", "blizzard climatology", "storm events"]
    }
}

# Summary statistics for documentation
VEDA_STATS = {
    "total_collections": 10,
    "working_collections": 10,
    "success_rate": 100.0,
    "categories": {
        "land_cover": 1,
        "fire_detection": 1,
        "climate_weather": 4,
        "research_specialized": 4
    },
    "key_characteristics": {
        "static_datasets": True,
        "requires_no_datetime": True,
        "specialized_research_focus": True,
        "asset_type": "cog_default"
    }
}

# Collection routing mappings for semantic translator
VEDA_ROUTING_KEYWORDS = {
    # Land Cover
    "bangladesh": ["bangladesh-landcover-2001-2020"],
    "land cover": ["bangladesh-landcover-2001-2020"],
    "modis land cover": ["bangladesh-landcover-2001-2020"],
    
    # Fire Detection - Only specific Thomas Fire references go to VEDA
    # Generic "burn severity" goes to Planetary Computer's MTBS collection
    "thomas fire": ["barc-thomasfire"],
    "barc": ["barc-thomasfire"],
    "thomasfire": ["barc-thomasfire"],
    
    # Climate/Weather
    "era5": ["blizzard-era5-10m-wind", "blizzard-era5-2m-temp", "blizzard-era5-cfrac", "blizzard-era5-mslp"],
    "weather reanalysis": ["blizzard-era5-10m-wind", "blizzard-era5-2m-temp", "blizzard-era5-cfrac", "blizzard-era5-mslp"],
    "wind": ["blizzard-era5-10m-wind"],
    "temperature": ["blizzard-era5-2m-temp"],
    "cloud fraction": ["blizzard-era5-cfrac"],
    "pressure": ["blizzard-era5-mslp"],
    
    # Research/Specialized
    "blizzard": ["blizzard-alley", "blizzard-clipper", "blizzard-co-low", "blizzard-count"],
    "alberta clipper": ["blizzard-clipper"],
    "colorado low": ["blizzard-co-low"],
    "storm climatology": ["blizzard-alley", "blizzard-count"]
}

def get_veda_collections_for_query(query: str) -> list:
    """Get appropriate VEDA collections based on query keywords"""
    query_lower = query.lower()
    matched_collections = set()
    
    for keyword, collections in VEDA_ROUTING_KEYWORDS.items():
        if keyword.lower() in query_lower:
            matched_collections.update(collections)
    
    return list(matched_collections)

def is_veda_query(query: str) -> bool:
    """Determine if query should be routed to VEDA based on keywords"""
    veda_indicators = list(VEDA_ROUTING_KEYWORDS.keys()) + [
        "specialized research", "historical analysis", "static dataset",
        "nasa research", "climate model", "research study"
    ]
    
    query_lower = query.lower()
    return any(indicator.lower() in query_lower for indicator in veda_indicators)