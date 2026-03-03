# Copyright (c) Microsoft Corporation.
# Licensed under the MIT license.

"""
Microsoft Planetary Computer Collection Profiles - UNIFIED VERSION
This is the SINGLE SOURCE OF TRUTH for all collection metadata.

Contains:
- Display metadata (names, categories, visualization configs)
- Query construction rules (STAC parameters, capabilities, AI guidance)
- Helper functions for querying collection metadata

Based on consolidation of:
- collection_profiles.py (display metadata)
- collection_query_patterns.py (query rules)
- parameter_validator.py (validation logic)
"""

import logging
from typing import Dict, List, Any, Optional

logger = logging.getLogger(__name__)

# ============================================================================
# COLLECTION PROFILES: Single Source of Truth
# ============================================================================

COLLECTION_PROFILES = {
    "sentinel-2-l2a": {
            "name": "Sentinel-2 Level-2A Surface Reflectance",
            "category": "optical",
            "resolution": "10-60m",
            "status": "excellent",
            "visualization": {
                    "type": "true_color",
                    "renderer": "optical_rgb",
                    "assets": {
                            "red": "B04",
                            "green": "B03",
                            "blue": "B02",
                            "nir": "B08",
                            "swir1": "B11",
                            "swir2": "B12"
                    },
                    "stretch": {
                            "type": "percentile",
                            "min": 2,
                            "max": 98
                    },
                    "gamma": 1.2
            },
            "temporal": {
                    "start": "2015-06-27",
                    "end": "ongoing"
            },
            "platform": "Sentinel-2A/2B",
            "cloud_filter": "eo:cloud_cover",
            "query_rules": {
                    "type": "dynamic_timeseries",
                    "description": "Sentinel-2 Level-2A surface reflectance (10-60m, cloud-filtered)",
                    "required_params": [
                            "bbox"
                    ],
                    "supported_params": [
                            "bbox",
                            "datetime",
                            "query.eo:cloud_cover",
                            "limit",
                            "collections"
                    ],
                    "ignored_params": [],
                    "capabilities": {
                            "temporal_filtering": True,
                            "cloud_filtering": True,
                            "spatial_filtering": True,
                            "dynamic_data": True
                    },
                    "query_template": {
                            "collections": [
                                    "sentinel-2-l2a"
                            ],
                            "bbox": "<spatial_bounds>",
                            "datetime": "<temporal_range>",
                            "query": {
                                    "eo:cloud_cover": {
                                            "lt": "<threshold>"
                                    }
                            },
                            "limit": 100
                    },
                    "agent_guidance": "Full time-series satellite imagery. Supports ALL standard STAC parameters including datetime and cloud_cover filters."
            }
    },

    "landsat-c2-l1": {
            "name": "Landsat Collection 2 Level-1 (Historical MSS)",
            "category": "optical",
            "resolution": "79m",
            "status": "archive_only",
            "visualization": {
                    "type": "false_color",
                    "renderer": "optical_nir",
                    "assets": {
                            "nir": "nir08",
                            "red": "red",
                            "green": "green"
                    },
                    "notes": "Landsat 1-5 MSS sensor has no blue band - uses false color NIR/Red/Green composite for visualization"
            },
            "temporal": {
                    "start": "1972-07-25",
                    "end": "2013-01-07"
            },
            "platform": "Landsat 1-5 MSS",
            "cloud_filter": None,
            "query_rules": {
                    "type": "historical_archive",
                    "description": "Landsat Collection 2 Level-1 raw digital numbers (79m, historical 1972-2013)",
                    "required_params": [
                            "bbox"
                    ],
                    "supported_params": [
                            "bbox",
                            "datetime",
                            "limit",
                            "collections"
                    ],
                    "ignored_params": [
                            "query.eo:cloud_cover"
                    ],
                    "capabilities": {
                            "temporal_filtering": True,
                            "cloud_filtering": False,
                            "spatial_filtering": True,
                            "dynamic_data": False
                    },
                    "query_template": {
                            "collections": [
                                    "landsat-c2-l1"
                            ],
                            "bbox": "<spatial_bounds>",
                            "datetime": "<temporal_range>",
                            "limit": 100
                    },
                    "agent_guidance": "Historical Landsat 1-5 MSS archive (1972-2013). NO cloud filtering available. Raw DN data requires calibration."
            }
    },

    "landsat-c2-l2": {
            "name": "Landsat Collection 2 Level-2",
            "category": "optical",
            "resolution": "30m",
            "status": "excellent",
            "visualization": {
                    "type": "true_color",
                    "renderer": "optical_rgb",
                    "assets": {
                            "red": "red",
                            "green": "green",
                            "blue": "blue",
                            "nir": "nir08",
                            "swir1": "swir16",
                            "swir2": "swir22",
                            "thermal": "lwir11"
                    },
                    "stretch": {
                            "type": "percentile",
                            "min": 2,
                            "max": 98
                    },
                    "gamma": 1.1,
                    "thermal_visualization": {
                            "type": "thermal_infrared",
                            "renderer": "thermal_overlay",
                            "colormap": "thermal"
                    }
            },
            "temporal": {
                    "start": "1982-08-22",
                    "end": "ongoing"
            },
            "platform": "Landsat 4-5 TM, Landsat 7 ETM+, Landsat 8-9 OLI/TIRS",
            "cloud_filter": "eo:cloud_cover",
            "query_rules": {
                    "type": "dynamic_timeseries",
                    "description": "Landsat Collection 2 Level-2 surface reflectance (30m, cloud-filtered)",
                    "required_params": [
                            "bbox"
                    ],
                    "supported_params": [
                            "bbox",
                            "datetime",
                            "query.eo:cloud_cover",
                            "limit",
                            "collections"
                    ],
                    "ignored_params": [],
                    "capabilities": {
                            "temporal_filtering": True,
                            "cloud_filtering": True,
                            "spatial_filtering": True,
                            "dynamic_data": True
                    },
                    "query_template": {
                            "collections": [
                                    "landsat-c2-l2"
                            ],
                            "bbox": "<spatial_bounds>",
                            "datetime": "<temporal_range>",
                            "query": {
                                    "eo:cloud_cover": {
                                            "lt": "<threshold>"
                                    }
                            },
                            "limit": 100
                    },
                    "agent_guidance": "Full time-series satellite imagery. Supports ALL standard STAC parameters including datetime and cloud_cover filters."
            }
    },

    "modis-43A4-061": {
            "name": "MODIS Nadir BRDF-Adjusted Reflectance (NBAR) Daily",
            "category": "global_optical",
            "resolution": "500m",
            "status": "excellent",
            "visualization": {
                    "type": "true_color",
                    "renderer": "optical_rgb",
                    "assets": {
                            "red": "Nadir_Reflectance_Band1",
                            "green": "Nadir_Reflectance_Band4",
                            "blue": "Nadir_Reflectance_Band3",
                            "nir": "Nadir_Reflectance_Band2",
                            "swir1": "Nadir_Reflectance_Band6",
                            "swir2": "Nadir_Reflectance_Band7"
                    },
                    "notes": "BRDF-corrected reflectance at local solar noon using 16-day moving window"
            },
            "temporal": {
                    "start": "2000-02-16",
                    "end": "ongoing"
            },
            "platform": "Terra+Aqua combined",
            "cloud_filter": None,
            "query_rules": {
                    "type": "dynamic_timeseries",
                    "description": "MODIS NBAR daily product (500m, BRDF-corrected, no cloud filter)",
                    "required_params": [
                            "bbox"
                    ],
                    "supported_params": [
                            "bbox",
                            "datetime",
                            "limit",
                            "collections"
                    ],
                    "ignored_params": [
                            "query.eo:cloud_cover"
                    ],
                    "capabilities": {
                            "temporal_filtering": True,
                            "cloud_filtering": False,
                            "spatial_filtering": True,
                            "dynamic_data": True
                    },
                    "query_template": {
                            "collections": [
                                    "modis-43A4-061"
                            ],
                            "bbox": "<spatial_bounds>",
                            "datetime": "<temporal_range>",
                            "limit": 100
                    },
                    "agent_guidance": "BRDF-corrected reflectance for consistent time-series. NO cloud filtering. Use datetime for date selection."
            }
    },

    "modis-09A1-061": {
            "name": "MODIS Surface Reflectance 8-Day (500m)",
            "category": "global_optical",
            "resolution": "500m",
            "status": "excellent",
            "visualization": {
                    "type": "true_color",
                    "renderer": "modis_surface_reflectance",
                    "assets": {
                            "bands": "7 spectral bands",
                            "qa": "QA"
                    },
                    "composite": "8-day"
            },
            "temporal": {
                    "start": "2000-02-18",
                    "end": "ongoing"
            },
            "platform": "Terra/Aqua MODIS",
            "query_rules": {
                    "type": "8day_composite",
                    "description": "MODIS 8-day surface reflectance composite (clouds already removed)",
                    "required_params": [
                            "bbox"
                    ],
                    "supported_params": [
                            "bbox",
                            "sortby",
                            "limit",
                            "collections"
                    ],
                    "ignored_params": [
                            "datetime",
                            "query.eo:cloud_cover",
                            "query.cloud_cover"
                    ],
                    "capabilities": {
                            "temporal_filtering": "use_sortby",
                            "cloud_filtering": False,
                            "spatial_filtering": True,
                            "composite_data": True
                    },
                    "query_template": {
                            "collections": [
                                    "modis-09A1-061"
                            ],
                            "bbox": "<spatial_bounds>",
                            "sortby": [
                                    {
                                            "field": "datetime",
                                            "direction": "desc"
                                    }
                            ],
                            "limit": 10
                    },
                    "agent_guidance": "8-day composite imagery with clouds already removed during processing. DO NOT use datetime filter or cloud_cover filter. Use sortby to get recent data instead."
            }
    },

    "modis-09Q1-061": {
            "name": "MODIS Surface Reflectance 8-Day (250m)",
            "category": "global_optical",
            "resolution": "250m",
            "status": "excellent",
            "visualization": {
                    "type": "true_color",
                    "renderer": "modis_surface_reflectance",
                    "assets": {
                            "bands": "Red/NIR bands",
                            "qa": "QA"
                    },
                    "composite": "8-day"
            },
            "temporal": {
                    "start": "2000-02-18",
                    "end": "ongoing"
            },
            "platform": "Terra/Aqua MODIS",
            "query_rules": {
                    "type": "8day_composite",
                    "description": "MODIS 8-day surface reflectance composite 250m (clouds already removed)",
                    "required_params": [
                            "bbox"
                    ],
                    "supported_params": [
                            "bbox",
                            "sortby",
                            "limit",
                            "collections"
                    ],
                    "ignored_params": [
                            "datetime",
                            "query.eo:cloud_cover",
                            "query.cloud_cover"
                    ],
                    "capabilities": {
                            "temporal_filtering": "use_sortby",
                            "cloud_filtering": False,
                            "spatial_filtering": True,
                            "composite_data": True
                    },
                    "query_template": {
                            "collections": [
                                    "modis-09Q1-061"
                            ],
                            "bbox": "<spatial_bounds>",
                            "sortby": [
                                    {
                                            "field": "datetime",
                                            "direction": "desc"
                                    }
                            ],
                            "limit": 10
                    },
                    "agent_guidance": "8-day composite imagery with clouds already removed. DO NOT use datetime or cloud_cover filters. Use sortby for recent data."
            }
    },

    "aster-l1t": {
            "name": "ASTER Level 1T Precision Terrain Corrected",
            "category": "optical",
            "resolution": "15-90m",
            "status": "excellent",
            "visualization": {
                    "type": "multispectral",
                    "renderer": "aster_multispectral",
                    "assets": {
                            "vnir": "VNIR bands",
                            "swir": "SWIR bands",
                            "tir": "TIR bands"
                    }
            },
            "temporal": {
                    "start": "2000-03-04",
                    "end": "ongoing"
            },
            "platform": "Terra ASTER",
            "query_rules": {
                    "type": "dynamic_timeseries",
                    "required_params": [
                            "bbox"
                    ],
                    "supported_params": [
                            "bbox",
                            "datetime",
                            "query.eo:cloud_cover",
                            "limit",
                            "sortby"
                    ],
                    "ignored_params": [],
                    "capabilities": {
                            "temporal_filtering": True,
                            "cloud_filtering": True,
                            "spatial_filtering": True,
                            "static_data": False,
                            "composite_data": False
                    },
                    "agent_guidance": "Full time-series optical satellite imagery. Supports ALL standard STAC parameters."
            }
    },

    "sentinel-1-grd": {
            "name": "Sentinel-1 Ground Range Detected",
            "category": "sar",
            "resolution": "10m",
            "status": "excellent",
            "visualization": {
                    "type": "sar_intensity",
                    "renderer": "sar_backscatter",
                    "assets": {
                            "vh": "VH",
                            "vv": "VV"
                    },
                    "colormap": "gray",
                    "rescale": [
                            -25,
                            0
                    ]
            },
            "temporal": {
                    "start": "2014-10-10",
                    "end": "ongoing"
            },
            "platform": "Sentinel-1A/1B/1C",
            "weather_independent": True,
            "query_rules": {
                    "type": "dynamic_timeseries",
                    "description": "Sentinel-1 GRD (Ground Range Detected SAR)",
                    "required_params": [
                            "bbox"
                    ],
                    "supported_params": [
                            "bbox",
                            "datetime",
                            "limit",
                            "collections"
                    ],
                    "ignored_params": [
                            "query.eo:cloud_cover"
                    ],
                    "capabilities": {
                            "temporal_filtering": True,
                            "cloud_filtering": False,
                            "spatial_filtering": True,
                            "dynamic_data": True
                    },
                    "query_template": {
                            "collections": [
                                    "sentinel-1-grd"
                            ],
                            "bbox": "<spatial_bounds>",
                            "datetime": "<temporal_range>",
                            "limit": 100
                    },
                    "agent_guidance": "SAR radar imagery. Supports datetime but NOT cloud_cover (radar penetrates clouds)."
            }
    },

    "sentinel-1-rtc": {
            "name": "Sentinel-1 Radiometrically Terrain Corrected",
            "category": "sar",
            "resolution": "10m",
            "status": "excellent",
            "visualization": {
                    "type": "sar_terrain_corrected",
                    "renderer": "sar_rtc",
                    "assets": {
                            "vh": "VH",
                            "vv": "VV",
                            "mask": "mask"
                    }
            },
            "temporal": {
                    "start": "2014-10-10",
                    "end": "ongoing"
            },
            "platform": "Sentinel-1A/1B/1C",
            "usage": "Terrain analysis, biomass estimation, land cover mapping",
            "query_rules": {
                    "type": "dynamic_timeseries",
                    "description": "Sentinel-1 RTC (Radiometric Terrain Corrected SAR)",
                    "required_params": [
                            "bbox"
                    ],
                    "supported_params": [
                            "bbox",
                            "datetime",
                            "limit",
                            "collections"
                    ],
                    "ignored_params": [
                            "query.eo:cloud_cover"
                    ],
                    "capabilities": {
                            "temporal_filtering": True,
                            "cloud_filtering": False,
                            "spatial_filtering": True,
                            "dynamic_data": True
                    },
                    "query_template": {
                            "collections": [
                                    "sentinel-1-rtc"
                            ],
                            "bbox": "<spatial_bounds>",
                            "datetime": "<temporal_range>",
                            "limit": 100
                    },
                    "agent_guidance": "SAR radar imagery. Supports datetime but NOT cloud_cover (radar penetrates clouds)."
            }
    },

    "alos-palsar-mosaic": {
            "name": "ALOS PALSAR Annual Mosaic",
            "category": "sar",
            "resolution": "25m",
            "status": "excellent",
            "visualization": {
                    "type": "sar_mosaic",
                    "renderer": "alos_palsar",
                    "assets": {
                            "hh": "HH",
                            "hv": "HV",
                            "mask": "mask"
                    }
            },
            "temporal": {
                    "start": "2007-01-01",
                    "end": "2010-12-31"
            },
            "platform": "ALOS PALSAR",
            "query_rules": {
                    "type": "dynamic_timeseries",
                    "required_params": [
                            "bbox"
                    ],
                    "supported_params": [
                            "bbox",
                            "datetime",
                            "limit",
                            "sortby"
                    ],
                    "ignored_params": [
                            "query.eo:cloud_cover"
                    ],
                    "capabilities": {
                            "temporal_filtering": True,
                            "cloud_filtering": False,
                            "spatial_filtering": True,
                            "static_data": False,
                            "composite_data": False
                    },
                    "agent_guidance": "SAR imagery. Weather-independent. DO NOT use cloud_cover filters."
            }
    },

    "alos-dem": {
            "name": "ALOS World 3D Digital Elevation Model",
            "category": "elevation",
            "resolution": "30m",
            "status": "excellent",
            "visualization": {
                    "type": "elevation",
                    "renderer": "dem_hillshade",
                    "assets": {
                            "elevation": "Elevation",
                            "mask": "mask"
                    }
            },
            "temporal": {
                    "static": True
            },
            "platform": "ALOS",
            "query_rules": {
                    "type": "static_elevation",
                    "description": "ALOS World 3D - global elevation model",
                    "required_params": [
                            "bbox"
                    ],
                    "supported_params": [
                            "bbox",
                            "limit",
                            "collections"
                    ],
                    "ignored_params": [
                            "datetime",
                            "query.eo:cloud_cover",
                            "query.cloud_cover"
                    ],
                    "capabilities": {
                            "temporal_filtering": False,
                            "cloud_filtering": False,
                            "spatial_filtering": True,
                            "static_data": True
                    },
                    "query_template": {
                            "collections": [
                                    "alos-dem"
                            ],
                            "bbox": "<spatial_bounds>",
                            "limit": 10
                    },
                    "agent_guidance": "Static elevation data that doesn't change over time. NEVER use datetime or cloud filters. Only spatial queries with bbox."
            }
    },

    "modis-14A1-061": {
            "name": "MODIS Thermal Anomalies Daily",
            "category": "fire",
            "resolution": "1km",
            "status": "excellent",
            "visualization": {
                    "type": "fire_detection",
                    "renderer": "thermal_raster",
                    "assets": {
                            "fire_mask": "FireMask",
                            "max_frp": "MaxFRP",
                            "qa": "QA"
                    },
                    "rendering": {
                            "type": "raster_tile",
                            "primary_asset": "FireMask",
                            "colormap_name": "modis-14A1|A2",
                            "colormap_description": "Black (no fire) -> Red -> Orange -> Yellow (high intensity)",
                            "rescale": None,  # MODIS fire has discrete classes, no rescaling needed
                            "opacity": 0.8,
                            "note": "Fire data is sparse - most pixels will be nodata/transparent"
                    },
                    "point_style": {
                            "color": "red",
                            "size": "confidence_based"
                    },
                    "real_time": True,
                    "sparse_data": True,
                    "zoom_recommendation": "8-12 to see fire pixels"
            },
            "temporal": {
                    "start": "2000-11-01",
                    "end": "ongoing"
            },
            "platform": "Terra/Aqua MODIS",
            "usage": "Real-time fire detection and monitoring",
            "query_rules": {
                    "type": "daily_fire_composite",
                    "description": "MODIS daily thermal anomalies/fire (composite product)",
                    "required_params": [
                            "bbox"
                    ],
                    "supported_params": [
                            "bbox",
                            "sortby",
                            "limit",
                            "collections"
                    ],
                    "ignored_params": [
                            "datetime",
                            "query.eo:cloud_cover",
                            "query.cloud_cover"
                    ],
                    "capabilities": {
                            "temporal_filtering": "use_sortby",
                            "cloud_filtering": False,
                            "spatial_filtering": True,
                            "composite_data": True
                    },
                    "query_template": {
                            "collections": [
                                    "modis-14A1-061"
                            ],
                            "bbox": "<spatial_bounds>",
                            "sortby": [
                                    {
                                            "field": "datetime",
                                            "direction": "desc"
                                    }
                            ],
                            "limit": 10
                    },
                    "agent_guidance": "Daily fire composite product. DO NOT use datetime or cloud_cover filters. Use sortby to get recent fire detections."
            }
    },

    "modis-14A2-061": {
            "name": "MODIS Thermal Anomalies 8-Day",
            "category": "fire",
            "resolution": "1km",
            "status": "excellent",
            "visualization": {
                    "type": "fire_detection",
                    "renderer": "thermal_raster",
                    "assets": {
                            "fire_mask": "FireMask",
                            "qa": "QA",
                            "tilejson": "tilejson"
                    },
                    "rendering": {
                            "type": "raster_tile",
                            "primary_asset": "FireMask",
                            "colormap_name": "modis-14A1|A2",
                            "colormap_description": "Black (no fire) -> Red -> Orange -> Yellow (high intensity)",
                            "rescale": None,  # MODIS fire has discrete classes, no rescaling needed
                            "opacity": 0.8,
                            "note": "8-day composite, fire data is sparse"
                    },
                    "point_style": {
                            "color": "orange",
                            "size": "confidence_based"
                    },
                    "temporal_composite": True,
                    "sparse_data": True,
                    "zoom_recommendation": "8-12 to see fire pixels"
            },
            "temporal": {
                    "start": "2000-11-01",
                    "end": "ongoing"
            },
            "platform": "Terra/Aqua MODIS",
            "usage": "Fire pattern analysis and weekly reporting",
            "query_rules": {
                    "type": "8day_fire_composite",
                    "description": "MODIS 8-day thermal anomalies/fire composite",
                    "required_params": [
                            "bbox"
                    ],
                    "supported_params": [
                            "bbox",
                            "sortby",
                            "limit",
                            "collections"
                    ],
                    "ignored_params": [
                            "datetime",
                            "query.eo:cloud_cover",
                            "query.cloud_cover"
                    ],
                    "capabilities": {
                            "temporal_filtering": "use_sortby",
                            "cloud_filtering": False,
                            "spatial_filtering": True,
                            "composite_data": True
                    },
                    "query_template": {
                            "collections": [
                                    "modis-14A2-061"
                            ],
                            "bbox": "<spatial_bounds>",
                            "sortby": [
                                    {
                                            "field": "datetime",
                                            "direction": "desc"
                                    }
                            ],
                            "limit": 10
                    },
                    "agent_guidance": "8-day fire composite product. DO NOT use datetime or cloud_cover filters. Use sortby for recent data."
            }
    },

    "modis-MCD64A1-061": {
            "name": "MODIS Burned Area Monthly",
            "category": "fire",
            "resolution": "500m",
            "status": "excellent",
            "visualization": {
                    "type": "burned_area",
                    "renderer": "fire_overlay",
                    "assets": {
                            "burn_date": "Burn_Date",
                            "last_day": "Last_Day",
                            "qa": "QA"
                    },
                    "colormap": "fire_severity",
                    "temporal_animation": True,
                    "opacity": 0.8
            },
            "temporal": {
                    "start": "2000-11-01",
                    "end": "ongoing"
            },
            "platform": "Terra/Aqua MODIS",
            "usage": "Post-fire assessment and burn scar mapping",
            "query_rules": {
                    "type": "8day_fire_composite",
                    "description": "MODIS 8-day burned area composite",
                    "required_params": [
                            "bbox"
                    ],
                    "supported_params": [
                            "bbox",
                            "sortby",
                            "limit",
                            "collections"
                    ],
                    "ignored_params": [
                            "datetime",
                            "query.eo:cloud_cover",
                            "query.cloud_cover"
                    ],
                    "capabilities": {
                            "temporal_filtering": "use_sortby",
                            "cloud_filtering": False,
                            "spatial_filtering": True,
                            "composite_data": True
                    },
                    "query_template": {
                            "collections": [
                                    "modis-MCD64A1-061"
                            ],
                            "bbox": "<spatial_bounds>",
                            "sortby": [
                                    {
                                            "field": "datetime",
                                            "direction": "desc"
                                    }
                            ],
                            "limit": 10
                    },
                    "agent_guidance": "8-day burned area composite. DO NOT use datetime or cloud_cover filters. Use sortby for recent data."
            }
    },

    "goes-glm": {
            "name": "GOES Geostationary Lightning Mapper",
            "category": "lightning",
            "resolution": "8km",
            "status": "excellent",
            "visualization": {
                    "type": "lightning_detection",
                    "renderer": "lightning_points",
                    "assets": {
                            "flash": "flash data",
                            "groups": "groups",
                            "events": "events"
                    }
            },
            "temporal": {
                    "start": "2017-01-01",
                    "end": "ongoing"
            },
            "platform": "GOES-16/17",
            "coverage": "Americas",
            "usage": "Lightning detection, severe weather monitoring",
            "query_rules": {
                    "type": "dynamic_timeseries",
                    "required_params": [
                            "bbox"
                    ],
                    "supported_params": [
                            "bbox",
                            "datetime",
                            "limit",
                            "sortby"
                    ],
                    "ignored_params": [],
                    "capabilities": {
                            "temporal_filtering": True,
                            "cloud_filtering": False,
                            "spatial_filtering": True,
                            "static_data": False,
                            "composite_data": False
                    },
                    "agent_guidance": "Standard time-series data. Supports temporal filtering."
            }
    },

    "modis-13Q1-061": {
            "name": "MODIS Vegetation Indices 16-Day (250m)",
            "category": "vegetation",
            "resolution": "250m",
            "status": "excellent",
            "visualization": {
                    "type": "vegetation_index",
                    "renderer": "ndvi_colormap",
                    "assets": {
                            "ndvi": "250m_16_days_NDVI",
                            "evi": "250m_16_days_EVI",
                            "qa": "VI_Quality"
                    },
                    "colormap": "viridis",
                    "rescale": [
                            0,
                            1
                    ]
            },
            "temporal": {
                    "start": "2000-02-18",
                    "end": "ongoing"
            },
            "platform": "Terra/Aqua MODIS",
            "usage": "High-resolution vegetation monitoring and agriculture",
            "query_rules": {
                    "type": "16day_composite",
                    "description": "MODIS 16-day NDVI 250m vegetation index composite",
                    "required_params": [
                            "bbox"
                    ],
                    "supported_params": [
                            "bbox",
                            "sortby",
                            "limit",
                            "collections"
                    ],
                    "ignored_params": [
                            "datetime",
                            "query.eo:cloud_cover",
                            "query.cloud_cover"
                    ],
                    "capabilities": {
                            "temporal_filtering": "use_sortby",
                            "cloud_filtering": False,
                            "spatial_filtering": True,
                            "composite_data": True
                    },
                    "query_template": {
                            "collections": [
                                    "modis-13Q1-061"
                            ],
                            "bbox": "<spatial_bounds>",
                            "sortby": [
                                    {
                                            "field": "datetime",
                                            "direction": "desc"
                                    }
                            ],
                            "limit": 10
                    },
                    "agent_guidance": "16-day NDVI composite. DO NOT use datetime or cloud_cover filters. Use sortby for recent data."
            }
    },

    "modis-13A1-061": {
            "name": "MODIS Vegetation Indices 16-Day (500m)",
            "category": "vegetation",
            "resolution": "500m",
            "status": "excellent",
            "visualization": {
                    "type": "vegetation_index",
                    "renderer": "ndvi_colormap",
                    "assets": {
                            "ndvi": "500m_16_days_NDVI",
                            "evi": "500m_16_days_EVI"
                    }
            },
            "temporal": {
                    "start": "2000-02-18",
                    "end": "ongoing"
            },
            "platform": "Terra/Aqua MODIS",
            "query_rules": {
                    "type": "16day_composite",
                    "description": "MODIS 16-day NDVI 500m vegetation index composite",
                    "required_params": [
                            "bbox"
                    ],
                    "supported_params": [
                            "bbox",
                            "sortby",
                            "limit",
                            "collections"
                    ],
                    "ignored_params": [
                            "datetime",
                            "query.eo:cloud_cover",
                            "query.cloud_cover"
                    ],
                    "capabilities": {
                            "temporal_filtering": "use_sortby",
                            "cloud_filtering": False,
                            "spatial_filtering": True,
                            "composite_data": True
                    },
                    "query_template": {
                            "collections": [
                                    "modis-13A1-061"
                            ],
                            "bbox": "<spatial_bounds>",
                            "sortby": [
                                    {
                                            "field": "datetime",
                                            "direction": "desc"
                                    }
                            ],
                            "limit": 10
                    },
                    "agent_guidance": "16-day NDVI composite. DO NOT use datetime or cloud_cover filters. Use sortby for recent data."
            }
    },

    "modis-11A1-061": {
            "name": "MODIS Land Surface Temperature Daily",
            "category": "agriculture",
            "resolution": "1km",
            "status": "excellent",
            "visualization": {
                    "type": "thermal_infrared",
                    "renderer": "temperature_gradient",
                    "assets": {
                            "lst_day": "LST_Day_1km",
                            "lst_night": "LST_Night_1km",
                            "qc_day": "QC_Day",
                            "qc_night": "QC_Night"
                    },
                    "colormap": "thermal",
                    "rescale": [
                            250,
                            350
                    ]
            },
            "temporal": {
                    "start": "2000-03-05",
                    "end": "ongoing"
            },
            "platform": "Terra/Aqua MODIS",
            "usage": "Agricultural stress monitoring, thermal analysis",
            "query_rules": {
                    "type": "daily_composite",
                    "description": "MODIS daily land surface temperature composite",
                    "required_params": [
                            "bbox"
                    ],
                    "supported_params": [
                            "bbox",
                            "sortby",
                            "limit",
                            "collections"
                    ],
                    "ignored_params": [
                            "datetime",
                            "query.eo:cloud_cover",
                            "query.cloud_cover"
                    ],
                    "capabilities": {
                            "temporal_filtering": "use_sortby",
                            "cloud_filtering": False,
                            "spatial_filtering": True,
                            "composite_data": True
                    },
                    "query_template": {
                            "collections": [
                                    "modis-11A1-061"
                            ],
                            "bbox": "<spatial_bounds>",
                            "sortby": [
                                    {
                                            "field": "datetime",
                                            "direction": "desc"
                                    }
                            ],
                            "limit": 10
                    },
                    "agent_guidance": "Daily temperature composite. DO NOT use datetime or cloud_cover filters. Use sortby for recent data."
            }
    },

    "modis-15A2H-061": {
            "name": "MODIS Leaf Area Index 8-Day",
            "category": "vegetation",
            "resolution": "500m",
            "status": "excellent",
            "visualization": {
                    "type": "leaf_area_index",
                    "renderer": "lai_colormap",
                    "assets": {
                            "lai": "Lai_500m",
                            "fpar": "Fpar_500m"
                    }
            },
            "temporal": {
                    "start": "2002-07-04",
                    "end": "ongoing"
            },
            "platform": "Terra/Aqua MODIS",
            "query_rules": {
                    "type": "8day_composite",
                    "description": "MODIS 8-day Leaf Area Index (LAI) composite",
                    "required_params": [
                            "bbox"
                    ],
                    "supported_params": [
                            "bbox",
                            "sortby",
                            "limit",
                            "collections"
                    ],
                    "ignored_params": [
                            "datetime",
                            "query.eo:cloud_cover",
                            "query.cloud_cover"
                    ],
                    "capabilities": {
                            "temporal_filtering": "use_sortby",
                            "cloud_filtering": False,
                            "spatial_filtering": True,
                            "composite_data": True
                    },
                    "query_template": {
                            "collections": [
                                    "modis-15A2H-061"
                            ],
                            "bbox": "<spatial_bounds>",
                            "sortby": [
                                    {
                                            "field": "datetime",
                                            "direction": "desc"
                                    }
                            ],
                            "limit": 10
                    },
                    "agent_guidance": "8-day LAI composite. DO NOT use datetime or cloud_cover filters. Use sortby for recent data."
            }
    },

    "modis-17A2H-061": {
            "name": "MODIS Gross Primary Productivity 8-Day",
            "category": "vegetation",
            "resolution": "500m",
            "status": "excellent",
            "visualization": {
                    "type": "productivity",
                    "renderer": "gpp_colormap",
                    "assets": {
                            "gpp": "Gpp_500m",
                            "psn_qa": "Psn_QC_500m"
                    }
            },
            "temporal": {
                    "start": "2000-02-18",
                    "end": "ongoing"
            },
            "platform": "Terra/Aqua MODIS",
            "query_rules": {
                    "type": "8day_composite",
                    "description": "MODIS 8-day Gross Primary Productivity (GPP)",
                    "required_params": [
                            "bbox"
                    ],
                    "supported_params": [
                            "bbox",
                            "sortby",
                            "limit",
                            "collections"
                    ],
                    "ignored_params": [
                            "datetime",
                            "query.eo:cloud_cover",
                            "query.cloud_cover"
                    ],
                    "capabilities": {
                            "temporal_filtering": "use_sortby",
                            "cloud_filtering": False,
                            "spatial_filtering": True,
                            "composite_data": True
                    },
                    "query_template": {
                            "collections": [
                                    "modis-17A2H-061"
                            ],
                            "bbox": "<spatial_bounds>",
                            "sortby": [
                                    {
                                            "field": "datetime",
                                            "direction": "desc"
                                    }
                            ],
                            "limit": 10
                    },
                    "agent_guidance": "8-day GPP composite. DO NOT use datetime or cloud_cover filters. Use sortby for recent data."
            }
    },

    "hls2-l30": {
            "name": "Harmonized Landsat Sentinel-2 L30",
            "category": "optical",
            "resolution": "30m",
            "status": "excellent",
            "visualization": {
                    "type": "true_color",
                    "renderer": "hls_optical",
                    "assets": {
                            "bands": "B01-B12 harmonized bands"
                    }
            },
            "temporal": {
                    "start": "2020-01-01",
                    "end": "ongoing"
            },
            "platform": "Landsat/Sentinel-2 Harmonized",
            "query_rules": {
                    "type": "dynamic_timeseries",
                    "description": "Harmonized Landsat Sentinel-2 (HLS) Landsat 30m",
                    "required_params": [
                            "bbox"
                    ],
                    "supported_params": [
                            "bbox",
                            "datetime",
                            "query.eo:cloud_cover",
                            "limit",
                            "collections"
                    ],
                    "ignored_params": [],
                    "capabilities": {
                            "temporal_filtering": True,
                            "cloud_filtering": True,
                            "spatial_filtering": True,
                            "dynamic_data": True
                    },
                    "query_template": {
                            "collections": [
                                    "hls2-l30",
                                    "hls2-s30"
                            ],
                            "bbox": "<spatial_bounds>",
                            "datetime": "<temporal_range>",
                            "query": {
                                    "eo:cloud_cover": {
                                            "lt": 20
                                    }
                            },
                            "sortby": [
                                    {
                                            "field": "eo:cloud_cover",
                                            "direction": "asc"
                                    },
                                    {
                                            "field": "datetime",
                                            "direction": "desc"
                                    }
                            ],
                            "limit": 50
                    },
                    "agent_guidance": """
[STAR] DEFAULT COLLECTION: HLS should be your FIRST CHOICE for optical imagery queries unless user explicitly requests a different collection.

WHY HLS IS THE BEST DEFAULT:
[OK] MAXIMUM COVERAGE: Combines Landsat 8/9 + Sentinel-2A/B/C for 2-3 day revisit (vs 5-16 days individual)
[OK] ANALYSIS-READY: Atmospherically corrected, BRDF-normalized, harmonized processing
[OK] GLOBAL: Available worldwide (unlike NAIP which is USA-only)
[OK] CONSISTENT: Same 30m resolution and band definitions across all sensors
[OK] DEEP ARCHIVE: 12+ years of consistent data (April 2013 - Present)

USE HLS FOR:
[OK] Generic requests like "show me images of Seattle" or "imagery of Paris in October"
[OK] Time-series analysis and change detection
[OK] Agriculture and crop monitoring
[OK] Any query without specific resolution requirements
[OK] Multi-temporal composites

QUERY BOTH COLLECTIONS TOGETHER:
CRITICAL: Always query ["hls2-l30", "hls2-s30"] together to maximize temporal coverage.
- hls2-l30: Landsat harmonized (16-day revisit per satellite)
- hls2-s30: Sentinel-2 harmonized (5-day revisit per satellite)
- Combined: Effective 2-3 day revisit globally

OPTIMIZED PARAMETERS:
- Cloud filter: eo:cloud_cover < 20 (strict for quality)
- Sort: Primary by cloud_cover ASC (least cloudy first), Secondary by datetime DESC (most recent first)
- Limit: 50+ items to ensure good temporal coverage

ONLY USE ALTERNATIVES WHEN:
-> User explicitly requests "Sentinel-2" or "Landsat" or "NAIP"
-> Need higher resolution: Sentinel-2 (10m) or NAIP (0.6m USA-only)
-> Need real-time data (< 24 hours): Sentinel-2 direct (HLS has 1-2 day processing lag)
-> Need thermal bands: Landsat direct (not in HLS)
"""
            }
    },

    "hls2-s30": {
            "name": "Harmonized Landsat Sentinel-2 S30",
            "category": "optical",
            "resolution": "30m",
            "status": "excellent",
            "visualization": {
                    "type": "true_color",
                    "renderer": "hls_optical",
                    "assets": {
                            "bands": "B01-B12 harmonized bands"
                    }
            },
            "temporal": {
                    "start": "2020-01-01",
                    "end": "ongoing"
            },
            "platform": "Sentinel-2A/B/C Harmonized",
            "query_rules": {
                    "type": "dynamic_timeseries",
                    "description": "Harmonized Landsat Sentinel-2 (HLS) Sentinel 30m",
                    "required_params": [
                            "bbox"
                    ],
                    "supported_params": [
                            "bbox",
                            "datetime",
                            "query.eo:cloud_cover",
                            "limit",
                            "collections"
                    ],
                    "ignored_params": [],
                    "capabilities": {
                            "temporal_filtering": True,
                            "cloud_filtering": True,
                            "spatial_filtering": True,
                            "dynamic_data": True
                    },
                    "query_template": {
                            "collections": [
                                    "hls2-s30",
                                    "hls2-l30"
                            ],
                            "bbox": "<spatial_bounds>",
                            "datetime": "<temporal_range>",
                            "query": {
                                    "eo:cloud_cover": {
                                            "lt": 20
                                    }
                            },
                            "sortby": [
                                    {
                                            "field": "eo:cloud_cover",
                                            "direction": "asc"
                                    },
                                    {
                                            "field": "datetime",
                                            "direction": "desc"
                                    }
                            ],
                            "limit": 50
                    },
                    "agent_guidance": """
[STAR] DEFAULT COLLECTION: HLS should be your FIRST CHOICE for optical imagery queries unless user explicitly requests a different collection.

Same guidance as hls2-l30 - these collections should ALWAYS be queried together for maximum coverage.
Query both ["hls2-s30", "hls2-l30"] to achieve 2-3 day revisit globally.
"""
            }
    },

    "cop-dem-glo-30": {
            "name": "Copernicus Digital Elevation Model 30m",
            "category": "elevation",
            "resolution": "30m",
            "status": "excellent",
            "visualization": {
                    "type": "elevation",
                    "renderer": "dem_hillshade",
                    "assets": {
                            "elevation": "elevation data"
                    },
                    "colormap": "terrain",
                    "hillshade": True
            },
            "temporal": {
                    "static": True
            },
            "platform": "Copernicus",
            "usage": "High-resolution topographic analysis and terrain modeling",
            "query_rules": {
                    "type": "static_elevation",
                    "description": "Copernicus DEM 30m - global elevation model",
                    "required_params": [
                            "bbox"
                    ],
                    "supported_params": [
                            "bbox",
                            "limit",
                            "collections"
                    ],
                    "ignored_params": [
                            "datetime",
                            "query.eo:cloud_cover",
                            "query.cloud_cover"
                    ],
                    "capabilities": {
                            "temporal_filtering": False,
                            "cloud_filtering": False,
                            "spatial_filtering": True,
                            "static_data": True
                    },
                    "query_template": {
                            "collections": [
                                    "cop-dem-glo-30"
                            ],
                            "bbox": "<spatial_bounds>",
                            "limit": 10
                    },
                    "agent_guidance": "Static elevation data that doesn't change over time. NEVER use datetime or cloud filters. Only spatial queries with bbox."
            }
    },

    "cop-dem-glo-90": {
            "name": "Copernicus Digital Elevation Model 90m",
            "category": "elevation",
            "resolution": "90m",
            "status": "excellent",
            "visualization": {
                    "type": "elevation",
                    "renderer": "dem_hillshade",
                    "assets": {
                            "elevation": "elevation data"
                    },
                    "colormap": "terrain",
                    "hillshade": True
            },
            "temporal": {
                    "static": True
            },
            "platform": "Copernicus",
            "usage": "Global topographic data for broad terrain analysis",
            "query_rules": {
                    "type": "static_elevation",
                    "description": "Copernicus DEM 90m - global elevation model",
                    "required_params": [
                            "bbox"
                    ],
                    "supported_params": [
                            "bbox",
                            "limit",
                            "collections"
                    ],
                    "ignored_params": [
                            "datetime",
                            "query.eo:cloud_cover",
                            "query.cloud_cover"
                    ],
                    "capabilities": {
                            "temporal_filtering": False,
                            "cloud_filtering": False,
                            "spatial_filtering": True,
                            "static_data": True
                    },
                    "query_template": {
                            "collections": [
                                    "cop-dem-glo-90"
                            ],
                            "bbox": "<spatial_bounds>",
                            "limit": 10
                    },
                    "agent_guidance": "Static elevation data that doesn't change over time. NEVER use datetime or cloud filters. Only spatial queries with bbox."
            }
    },

    "nasadem": {
            "name": "NASA Digital Elevation Model",
            "category": "elevation",
            "resolution": "30m",
            "status": "excellent",
            "visualization": {
                    "type": "elevation",
                    "renderer": "dem_hillshade",
                    "assets": {
                            "elevation": "elevation",
                            "slope": "slope",
                            "aspect": "aspect"
                    }
            },
            "temporal": {
                    "static": True
            },
            "platform": "NASA",
            "usage": "High-quality topographic data for terrain analysis",
            "query_rules": {
                    "type": "static_elevation",
                    "description": "NASA DEM - global elevation model",
                    "required_params": [
                            "bbox"
                    ],
                    "supported_params": [
                            "bbox",
                            "limit",
                            "collections"
                    ],
                    "ignored_params": [
                            "datetime",
                            "query.eo:cloud_cover",
                            "query.cloud_cover"
                    ],
                    "capabilities": {
                            "temporal_filtering": False,
                            "cloud_filtering": False,
                            "spatial_filtering": True,
                            "static_data": True
                    },
                    "query_template": {
                            "collections": [
                                    "nasadem"
                            ],
                            "bbox": "<spatial_bounds>",
                            "limit": 10
                    },
                    "agent_guidance": "Static elevation data that doesn't change over time. NEVER use datetime or cloud filters. Only spatial queries with bbox."
            }
    },

    "3dep-seamless": {
            "name": "USGS 3D Elevation Program (3DEP)",
            "category": "elevation",
            "resolution": "10m",
            "status": "medium",
            "visualization": {
                    "type": "elevation",
                    "renderer": "usgs_dem",
                    "assets": {
                            "elevation": "elevation rasters"
                    }
            },
            "temporal": {
                    "static": True
            },
            "platform": "USGS",
            "coverage": "USA only",
            "query_rules": {
                    "type": "static_elevation",
                    "required_params": [
                            "bbox"
                    ],
                    "supported_params": [
                            "bbox",
                            "limit"
                    ],
                    "ignored_params": [
                            "datetime",
                            "query.eo:cloud_cover",
                            "sortby"
                    ],
                    "capabilities": {
                            "temporal_filtering": False,
                            "cloud_filtering": False,
                            "spatial_filtering": True,
                            "static_data": True,
                            "composite_data": False
                    },
                    "agent_guidance": "Static elevation data. NEVER use datetime or cloud filters."
            }
    },

    "era5-pds": {
            "name": "ERA5 Reanalysis",
            "category": "climate",
            "resolution": "31km",
            "status": "good",
            "visualization": {
                    "type": "weather_reanalysis",
                    "renderer": "climate_data",
                    "assets": {
                            "multiple": "weather variables"
                    }
            },
            "temporal": {
                    "start": "1979-01-01",
                    "end": "ongoing"
            },
            "platform": "ECMWF",
            "usage": "Comprehensive historical and current weather patterns",
            "query_rules": {
                    "type": "dynamic_timeseries",
                    "required_params": [
                            "bbox"
                    ],
                    "supported_params": [
                            "bbox",
                            "datetime",
                            "limit",
                            "sortby"
                    ],
                    "ignored_params": [],
                    "capabilities": {
                            "temporal_filtering": True,
                            "cloud_filtering": False,
                            "spatial_filtering": True,
                            "static_data": False,
                            "composite_data": False
                    },
                    "agent_guidance": "Standard time-series data. Supports temporal filtering."
            }
    },

    "noaa-climate-normals-netcdf": {
            "name": "NOAA Climate Normals NetCDF",
            "category": "climate",
            "resolution": "4km",
            "status": "good",
            "visualization": {
                    "type": "climate_normals",
                    "renderer": "climate_gridded"
            },
            "temporal": {
                    "climate_normals": "1991-2020"
            },
            "platform": "NOAA",
            "query_rules": {
                    "type": "dynamic_timeseries",
                    "required_params": [
                            "bbox"
                    ],
                    "supported_params": [
                            "bbox",
                            "datetime",
                            "limit",
                            "sortby"
                    ],
                    "ignored_params": [],
                    "capabilities": {
                            "temporal_filtering": True,
                            "cloud_filtering": False,
                            "spatial_filtering": True,
                            "static_data": False,
                            "composite_data": False
                    },
                    "agent_guidance": "Standard time-series data. Supports temporal filtering."
            }
    },

    "noaa-climate-normals-gridded": {
            "name": "NOAA Climate Normals Gridded",
            "category": "climate",
            "resolution": "800m",
            "status": "good",
            "visualization": {
                    "type": "climate_normals",
                    "renderer": "climate_gridded"
            },
            "temporal": {
                    "climate_normals": "1991-2020"
            },
            "platform": "NOAA",
            "query_rules": {
                    "type": "dynamic_timeseries",
                    "required_params": [
                            "bbox"
                    ],
                    "supported_params": [
                            "bbox",
                            "datetime",
                            "limit",
                            "sortby"
                    ],
                    "ignored_params": [],
                    "capabilities": {
                            "temporal_filtering": True,
                            "cloud_filtering": False,
                            "spatial_filtering": True,
                            "static_data": False,
                            "composite_data": False
                    },
                    "agent_guidance": "Standard time-series data. Supports temporal filtering."
            }
    },

    "goes-cmi": {
            "name": "GOES Cloud and Moisture Imagery",
            "category": "ocean",
            "resolution": "2km",
            "status": "excellent",
            "visualization": {
                    "type": "ocean_color",
                    "renderer": "goes_marine",
                    "assets": {
                            "multiple": "ocean bands"
                    }
            },
            "temporal": {
                    "start": "2017-05-24",
                    "end": "ongoing"
            },
            "platform": "GOES-16/17",
            "coverage": "Americas",
            "query_rules": {
                    "type": "dynamic_timeseries",
                    "description": "GOES-R Cloud and Moisture Imagery (real-time weather satellite)",
                    "required_params": [
                            "bbox"
                    ],
                    "supported_params": [
                            "bbox",
                            "datetime",
                            "limit",
                            "collections"
                    ],
                    "ignored_params": [
                            "query.eo:cloud_cover"
                    ],
                    "capabilities": {
                            "temporal_filtering": True,
                            "cloud_filtering": False,
                            "spatial_filtering": True,
                            "dynamic_data": True
                    },
                    "query_template": {
                            "collections": [
                                    "goes-cmi"
                            ],
                            "bbox": "<spatial_bounds>",
                            "datetime": "<temporal_range>",
                            "limit": 100
                    },
                    "agent_guidance": "Real-time weather satellite imagery. Supports datetime filtering but NOT cloud_cover (it's a weather satellite - clouds are the data!)."
            }
    },

    # "mur-sst": {  # REMOVED: Collection no longer in STAC API
    #         "name": "Multi-scale Ultra-high Resolution Sea Surface Temperature",
    #         "category": "ocean",
    #         "resolution": "1km",
    #         "status": "excellent",
    #         "visualization": {
    #                 "type": "sea_surface_temperature",
    #                 "renderer": "sst_colormap",
    #                 "colormap": "thermal"
    #         },
    #         "temporal": {
    #                 "start": "2002-06-01",
    #                 "end": "ongoing"
    #         },
    #         "platform": "Multi-sensor",
    #         "query_rules": {
    #                 "type": "dynamic_timeseries",
    #                 "required_params": [
    #                         "bbox"
    #                 ],
    #                 "supported_params": [
    #                         "bbox",
    #                         "datetime",
    #                         "limit",
    #                         "sortby"
    #                 ],
    #                 "ignored_params": [],
    #                 "capabilities": {
    #                         "temporal_filtering": True,
    #                         "cloud_filtering": False,
    #                         "spatial_filtering": True,
    #                         "static_data": False,
    #                         "composite_data": False
    #                 },
    #                 "agent_guidance": "Standard time-series data. Supports temporal filtering."
    #         }
    # },


    "naip": {
            "name": "National Agriculture Imagery Program",
            "category": "aerial",
            "resolution": "0.6-1m",
            "status": "good",
            "visualization": {
                    "type": "true_color",
                    "renderer": "high_res_aerial",
                    "assets": {
                            "red": "red",
                            "green": "green",
                            "blue": "blue",
                            "nir": "nir"
                    }
            },
            "temporal": {
                    "start": "2009-01-01",
                    "end": "ongoing"
            },
            "platform": "Aerial imagery",
            "coverage": "USA only",
            "geographic_extent": {
                    "type": "multi_bbox",
                    "countries": ["USA"],
                    # Source: Planetary Computer STAC API (queried 2025-10-19)
                    # https://planetarycomputer.microsoft.com/api/stac/v1/collections/naip
                    "bboxes": [
                            [-124.784, 24.744, -66.951, 49.346],    # Continental US
                            [-156.003, 19.059, -154.809, 20.127],   # Hawaii
                            [-67.316, 17.871, -65.596, 18.565],     # Puerto Rico
                            [-64.94, 17.622, -64.56, 17.814]        # US Virgin Islands
                    ],
                    "description": "Continental United States, Hawaii, Puerto Rico, and US Virgin Islands",
                    "exclusions": ["Alaska (most years)", "Other US territories"]
            },
            "usage": "Very high-resolution aerial imagery for detailed infrastructure analysis",
            "query_rules": {
                    "type": "dynamic_timeseries",
                    "description": "NAIP - National Agriculture Imagery Program (high-res aerial imagery)",
                    "required_params": [
                            "bbox"
                    ],
                    "supported_params": [
                            "bbox",
                            "datetime",
                            "limit",
                            "collections"
                    ],
                    "ignored_params": [
                            "query.eo:cloud_cover"
                    ],
                    "capabilities": {
                            "temporal_filtering": True,
                            "cloud_filtering": False,
                            "spatial_filtering": True,
                            "dynamic_data": True
                    },
                    "query_template": {
                            "collections": [
                                    "naip"
                            ],
                            "bbox": "<spatial_bounds>",
                            "datetime": "<temporal_range>",
                            "limit": 100
                    },
                    "agent_guidance": "High-resolution aerial imagery. Supports datetime but NOT cloud_cover (imagery is already cloud-free selected). COVERAGE LIMITATION: NAIP only covers the continental United States. If the user asks for locations outside the USA, explain that NAIP is not available and suggest alternative global collections like Sentinel-2 or Landsat."
            }
    },

    # "worldpop": {  # REMOVED: Collection no longer in STAC API
    #         "name": "WorldPop Population Estimates",
    #         "category": "demographics",
    #         "resolution": "100m",
    #         "status": "excellent",
    #         "visualization": {
    #                 "type": "population_density",
    #                 "renderer": "population_heatmap"
    #         },
    #         "temporal": {
    #                 "start": "2000-01-01",
    #                 "end": "2020-12-31"
    #         },
    #         "platform": "WorldPop",
    #         "query_rules": {
    #                 "type": "dynamic_timeseries",
    #                 "required_params": [
    #                         "bbox"
    #                 ],
    #                 "supported_params": [
    #                         "bbox",
    #                         "datetime",
    #                         "limit",
    #                         "sortby"
    #                 ],
    #                 "ignored_params": [],
    #                 "capabilities": {
    #                         "temporal_filtering": True,
    #                         "cloud_filtering": False,
    #                         "spatial_filtering": True,
    #                         "static_data": False,
    #                         "composite_data": False
    #                 },
    #                 "agent_guidance": "Standard time-series data. Supports temporal filtering."
    #         }
    # },

    "ms-buildings": {
            "name": "Microsoft Building Footprints",
            "category": "infrastructure",
            "resolution": "vector",
            "status": "excellent",
            "visualization": {
                    "type": "building_footprints",
                    "renderer": "vector_overlay"
            },
            "temporal": {
                    "static": True
            },
            "platform": "Microsoft AI",
            "coverage": "Global building footprints",
            "query_rules": {
                    "type": "dynamic_timeseries",
                    "required_params": [
                            "bbox"
                    ],
                    "supported_params": [
                            "bbox",
                            "datetime",
                            "limit",
                            "sortby"
                    ],
                    "ignored_params": [],
                    "capabilities": {
                            "temporal_filtering": True,
                            "cloud_filtering": False,
                            "spatial_filtering": True,
                            "static_data": False,
                            "composite_data": False
                    },
                    "agent_guidance": "Standard time-series data. Supports temporal filtering."
            }
    },

    "us-census": {
            "name": "US Census Data",
            "category": "demographics",
            "resolution": "census_block",
            "status": "excellent",
            "visualization": {
                    "type": "demographic_data",
                    "renderer": "census_choropleth"
            },
            "temporal": {
                    "census_years": True
            },
            "platform": "US Census Bureau",
            "coverage": "USA only",
            "query_rules": {
                    "type": "dynamic_timeseries",
                    "required_params": [
                            "bbox"
                    ],
                    "supported_params": [
                            "bbox",
                            "datetime",
                            "limit",
                            "sortby"
                    ],
                    "ignored_params": [],
                    "capabilities": {
                            "temporal_filtering": True,
                            "cloud_filtering": False,
                            "spatial_filtering": True,
                            "static_data": False,
                            "composite_data": False
                    },
                    "agent_guidance": "Standard time-series data. Supports temporal filtering."
            }
    },

    "modis-10A1-061": {
            "name": "MODIS Snow Cover Daily",
            "category": "snow",
            "resolution": "500m",
            "status": "excellent",
            "visualization": {
                    "type": "snow_cover",
                    "renderer": "snow_colormap"
            },
            "temporal": {
                    "start": "2000-02-24",
                    "end": "ongoing"
            },
            "platform": "Terra/Aqua MODIS",
            "query_rules": {
                    "type": "daily_composite",
                    "description": "MODIS daily snow cover composite",
                    "required_params": [
                            "bbox"
                    ],
                    "supported_params": [
                            "bbox",
                            "sortby",
                            "limit",
                            "collections"
                    ],
                    "ignored_params": [
                            "datetime",
                            "query.eo:cloud_cover",
                            "query.cloud_cover"
                    ],
                    "capabilities": {
                            "temporal_filtering": "use_sortby",
                            "cloud_filtering": False,
                            "spatial_filtering": True,
                            "composite_data": True
                    },
                    "query_template": {
                            "collections": [
                                    "modis-10A1-061"
                            ],
                            "bbox": "<spatial_bounds>",
                            "sortby": [
                                    {
                                            "field": "datetime",
                                            "direction": "desc"
                                    }
                            ],
                            "limit": 10
                    },
                    "agent_guidance": "Daily snow cover composite. DO NOT use datetime or cloud_cover filters. Use sortby for recent data."
            }
    },

    "modis-10A2-061": {
            "name": "MODIS Snow Cover 8-Day",
            "category": "snow",
            "resolution": "500m",
            "status": "excellent",
            "visualization": {
                    "type": "snow_cover",
                    "renderer": "snow_colormap"
            },
            "temporal": {
                    "start": "2000-02-24",
                    "end": "ongoing"
            },
            "platform": "Terra/Aqua MODIS",
            "query_rules": {
                    "type": "dynamic_timeseries",
                    "required_params": [
                            "bbox"
                    ],
                    "supported_params": [
                            "bbox",
                            "datetime",
                            "limit",
                            "sortby"
                    ],
                    "ignored_params": [],
                    "capabilities": {
                            "temporal_filtering": True,
                            "cloud_filtering": False,
                            "spatial_filtering": True,
                            "static_data": False,
                            "composite_data": False
                    },
                    "agent_guidance": "Standard time-series data. Supports temporal filtering."
            }
    },

    "modis-17A3HGF-061": {
            "name": "MODIS Net Primary Production Yearly",
            "category": "vegetation",
            "resolution": "500m",
            "status": "excellent",
            "visualization": {
                    "type": "productivity",
                    "renderer": "npp_colormap"
            },
            "temporal": {
                    "start": "2000-01-01",
                    "end": "ongoing"
            },
            "platform": "Terra/Aqua MODIS",
            "query_rules": {
                    "type": "annual_composite",
                    "description": "MODIS annual Net Primary Productivity (NPP)",
                    "required_params": [
                            "bbox"
                    ],
                    "supported_params": [
                            "bbox",
                            "sortby",
                            "limit",
                            "collections"
                    ],
                    "ignored_params": [
                            "datetime",
                            "query.eo:cloud_cover",
                            "query.cloud_cover"
                    ],
                    "capabilities": {
                            "temporal_filtering": "use_sortby",
                            "cloud_filtering": False,
                            "spatial_filtering": True,
                            "composite_data": True
                    },
                    "query_template": {
                            "collections": [
                                    "modis-17A3HGF-061"
                            ],
                            "bbox": "<spatial_bounds>",
                            "sortby": [
                                    {
                                            "field": "datetime",
                                            "direction": "desc"
                                    }
                            ],
                            "limit": 10
                    },
                    "agent_guidance": "Annual NPP composite. DO NOT use datetime or cloud_cover filters. Use sortby for recent data."
            }
    },

}


# ============================================================================
# HELPER FUNCTIONS: Collection Metadata Access
# ============================================================================

def get_query_rules(collection_id: str) -> Dict[str, Any]:
    """Get query construction rules for a collection"""
    if collection_id in COLLECTION_PROFILES:
        return COLLECTION_PROFILES[collection_id].get("query_rules", _get_default_query_rules())
    return _get_default_query_rules()

def _get_default_query_rules() -> Dict[str, Any]:
    """Conservative defaults for unknown collections"""
    return {
        "type": "dynamic_timeseries",
        "required_params": ["bbox"],
        "supported_params": ["bbox", "datetime", "limit"],
        "ignored_params": [],
        "capabilities": {
            "temporal_filtering": True,
            "cloud_filtering": False,
            "spatial_filtering": True,
            "static_data": False,
            "composite_data": False
        },
        "agent_guidance": "Standard STAC collection with temporal and spatial filtering."
    }

def supports_temporal_filtering(collection_id: str) -> bool:
    """Check if collection supports datetime filtering"""
    rules = get_query_rules(collection_id)
    temporal = rules["capabilities"].get("temporal_filtering", False)
    return temporal is True  # Not "use_sortby"

def is_static_collection(collection_id: str) -> bool:
    """Check if collection is static (no temporal dimension)"""
    rules = get_query_rules(collection_id)
    return rules["capabilities"].get("static_data", False)

def is_composite_collection(collection_id: str) -> bool:
    """Check if collection is composite/aggregated data"""
    rules = get_query_rules(collection_id)
    return rules["capabilities"].get("composite_data", False)

def supports_cloud_filtering(collection_id: str) -> bool:
    """Check if collection supports cloud cover filtering"""
    rules = get_query_rules(collection_id)
    return rules["capabilities"].get("cloud_filtering", False)

def uses_sortby_instead_of_datetime(collection_id: str) -> bool:
    """Check if collection uses sortby instead of datetime (composites)"""
    rules = get_query_rules(collection_id)
    return rules["capabilities"].get("temporal_filtering") == "use_sortby"

def get_ignored_parameters(collection_id: str) -> List[str]:
    """Get list of parameters that should be ignored for this collection"""
    rules = get_query_rules(collection_id)
    return rules.get("ignored_params", [])

def get_supported_parameters(collection_id: str) -> List[str]:
    """Get list of parameters supported by this collection"""
    rules = get_query_rules(collection_id)
    return rules.get("supported_params", [])

def get_agent_guidance(collection_id: str) -> str:
    """Get AI agent guidance for constructing queries for this collection"""
    rules = get_query_rules(collection_id)
    return rules.get("agent_guidance", "")

def get_cloud_cover_property(collection_id: str) -> Optional[str]:
    """Get the cloud cover property name for a collection"""
    if collection_id in COLLECTION_PROFILES:
        # Check old-style cloud_filter first
        profile = COLLECTION_PROFILES[collection_id]
        if "cloud_filter" in profile:
            return profile["cloud_filter"]
        
        # Check if cloud filtering is supported in query_rules
        if supports_cloud_filtering(collection_id):
            # Default to eo:cloud_cover for collections that support it
            return "eo:cloud_cover"
    
    return None

def generate_agent_query_knowledge() -> str:
    """
    Generate formatted collection knowledge for AI agent system prompt.
    This provides the agent with rules for constructing correct queries.
    """
    
    # Group collections by type
    static_collections = []
    composite_collections = []
    dynamic_collections = []
    
    for collection_id, profile in COLLECTION_PROFILES.items():
        rules = profile.get("query_rules", {})
        caps = rules.get("capabilities", {})
        
        if caps.get("static_data"):
            static_collections.append(collection_id)
        elif caps.get("composite_data"):
            composite_collections.append(collection_id)
        else:
            dynamic_collections.append(collection_id)
    
    knowledge_text = f"""
=================================================================================
STAC QUERY CONSTRUCTION RULES - COLLECTION CAPABILITIES
=================================================================================

CRITICAL: Different collections support different query parameters. You MUST 
construct queries using ONLY the parameters each collection supports.

COLLECTION TYPES:

1. STATIC COLLECTIONS (Elevation/DEM data - NO temporal dimension):
   Collections: {", ".join(static_collections)}
   
   RULES FOR STATIC COLLECTIONS:
   [OK] ONLY use: bbox, limit
   [FAIL] NEVER use: datetime, cloud_cover
   Why: Elevation data is static and doesn't change over time
   
2. COMPOSITE COLLECTIONS (Pre-aggregated with clouds removed):
   Collections: {", ".join(composite_collections)}
   
   RULES FOR COMPOSITE COLLECTIONS:
   [OK] ONLY use: bbox, sortby, limit
   [FAIL] NEVER use: datetime (use sortby instead), cloud_cover (already filtered)
   Why: These are composites with clouds already removed during processing
   
3. DYNAMIC COLLECTIONS (Full time-series data):
   Collections: {", ".join(dynamic_collections[:10])}{"..." if len(dynamic_collections) > 10 else ""}
   
   RULES FOR DYNAMIC COLLECTIONS:
   [OK] CAN use: ALL standard STAC parameters
   [OK] datetime, cloud_cover (if optical), bbox all supported

=================================================================================
"""
    
    return knowledge_text

def check_collection_coverage(collection_id: str, bbox: list) -> dict:
    """
    Check if a collection covers the specified geographic area.
    
    Args:
        collection_id: The collection identifier
        bbox: Bounding box [west, south, east, north] in EPSG:4326
    
    Returns:
        dict with keys:
            - covered: bool - whether the area is covered
            - message: str - explanation if not covered
            - alternatives: list - suggested alternative collections
    """
    if collection_id not in COLLECTION_PROFILES:
        return {"covered": True, "message": "Unknown collection, cannot verify coverage"}
    
    profile = COLLECTION_PROFILES[collection_id]
    geo_extent = profile.get("geographic_extent")
    
    if not geo_extent:
        # No coverage restrictions specified
        return {"covered": True, "message": "Collection has global or unspecified coverage"}
    
    # Check if bbox overlaps with collection bbox(es)
    query_west, query_south, query_east, query_north = bbox
    
    # Handle single bbox or multiple bboxes
    collection_bboxes = []
    if "bbox" in geo_extent:
        collection_bboxes = [geo_extent["bbox"]]
    elif "bboxes" in geo_extent:
        collection_bboxes = geo_extent["bboxes"]
    
    if collection_bboxes:
        # Check if query bbox overlaps with ANY of the collection bboxes
        overlaps_any = False
        
        for collection_bbox in collection_bboxes:
            # bbox format: [west, south, east, north]
            coll_west, coll_south, coll_east, coll_north = collection_bbox
            
            # Check for overlap with this bbox
            overlaps = not (query_east < coll_west or 
                           query_west > coll_east or 
                           query_north < coll_south or 
                           query_south > coll_north)
            
            if overlaps:
                overlaps_any = True
                break
        
        if not overlaps_any:
            description = geo_extent.get("description", "specified geographic area")
            exclusions = geo_extent.get("exclusions", [])
            exclusion_text = f" (excludes: {', '.join(exclusions)})" if exclusions else ""
            
            return {
                "covered": False,
                "message": f"The '{profile['name']}' collection only covers {description}{exclusion_text}. Your query location [{query_west:.2f}, {query_south:.2f}, {query_east:.2f}, {query_north:.2f}] is outside this coverage area.",
                "alternatives": ["sentinel-2-l2a", "landsat-c2-l2", "hls2-s30", "hls2-l30"],
                "collection_name": profile['name'],
                "coverage_description": description
            }
    
    return {"covered": True, "message": "Location is within collection coverage"}


# Export key elements
__all__ = [
    'COLLECTION_PROFILES',
    'get_query_rules',
    'supports_temporal_filtering',
    'is_static_collection',
    'is_composite_collection',
    'supports_cloud_filtering',
    'uses_sortby_instead_of_datetime',
    'check_collection_coverage',
    'get_ignored_parameters',
    'get_supported_parameters',
    'get_agent_guidance',
    'get_cloud_cover_property',
    'generate_agent_query_knowledge'
]
