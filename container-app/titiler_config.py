"""
TiTiler Quality Optimization Configuration for Earth-Copilot

This module provides optimal TiTiler rendering parameters for different data types
to ensure the highest quality map tiles on the frontend.

Key Quality Improvements:
1. @2x resolution for Retina/HiDPI displays
2. Proper rescaling for elevation data
3. Band indexing for multi-band assets
4. Resampling methods for quality enhancement
5. Collection-specific colormap mappings

References:
- https://developmentseed.org/titiler/
- https://planetarycomputer.microsoft.com/docs/quickstarts/reading-stac/
"""

from typing import Dict, List, Optional, Tuple
from enum import Enum

class ResamplingMethod(str, Enum):
    """TiTiler resampling methods for quality enhancement"""
    NEAREST = "nearest"  # Fast, preserves exact values (good for categorical data)
    BILINEAR = "bilinear"  # Good quality, fast (default for most)
    CUBIC = "cubic"  # Better quality, slower (best for elevation)
    CUBICSPLINE = "cubicspline"  # Highest quality, slowest
    LANCZOS = "lanczos"  # High quality, good for downsampling
    AVERAGE = "average"  # Good for aggregation
    MODE = "mode"  # Best for categorical data

class TiTilerQualityConfig:
    """Configuration for optimal TiTiler tile rendering"""
    
    # Default parameters
    DEFAULT_SCALE = 2  # Use @2x for HiDPI displays
    DEFAULT_RESAMPLING = ResamplingMethod.BILINEAR
    DEFAULT_FORMAT = "png"
    
    # Collection-specific configurations
    ELEVATION_COLLECTIONS = [
        "cop-dem-glo-30",
        "cop-dem-glo-90", 
        "nasadem",
        "3dep-seamless",
        "aster-l1t",
        "alos-dem"
    ]
    
    OPTICAL_COLLECTIONS = [
        "sentinel-2-l2a",
        "landsat-c2-l2",
        "naip",
        "hls2-l30",
        "hls2-s30"
    ]
    
    THERMAL_COLLECTIONS = [
        "landsat-c2-l2"  # Has thermal bands
    ]
    
    SAR_COLLECTIONS = [
        "sentinel-1-grd",
        "sentinel-1-rtc"
    ]
    
    # Colormap mappings for different data types
    COLORMAP_MAPPING = {
        # Elevation data
        "elevation": "terrain",
        "dem": "terrain",
        "dsm": "terrain",
        
        # Vegetation indices
        "ndvi": "rdylgn",
        "evi": "greens",
        "vegetation": "viridis",
        
        # Temperature/thermal
        "temperature": "plasma",
        "thermal": "inferno",
        "heat": "hot",
        "sst": "turbo",
        
        # Water/ocean
        "water": "blues",
        "ocean": "ocean",
        "chlorophyll": "algae",
        
        # Fire/burned area
        "fire": "reds",
        "burned": "greys",
        
        # Default
        "default": "viridis"
    }
    
    # Rescaling ranges for different data types
    RESCALE_RANGES = {
        "cop-dem-glo-30": (0, 4000),  # Meters above sea level
        "cop-dem-glo-90": (0, 4000),
        "nasadem": (0, 4000),
        "3dep-seamless": (0, 4000),
        "alos-dem": (0, 4000),
        "aster-l1t": (0, 4000),
        
        # HLS Surface Reflectance (0-10000 range, but 0-3000 gives good contrast)
        "hls2-l30": (0, 3000),  # Harmonized Landsat Sentinel-2 L30
        "hls2-s30": (0, 3000),  # Harmonized Landsat Sentinel-2 S30
        
        # Thermal (Landsat Band 10 - in Kelvin, convert to Celsius range)
        "thermal": (250, 330),  # ~-23°C to 57°C
        
        # NDVI
        "ndvi": (-1, 1),
        
        # Default
        "default": None  # Let TiTiler auto-detect
    }
    
    @classmethod
    def get_optimal_params(cls, collection_id: str, query_context: Optional[str] = None) -> Dict[str, any]:
        """
        Get optimal TiTiler parameters for a given collection and query context.
        
        Args:
            collection_id: STAC collection ID (e.g., 'cop-dem-glo-90')
            query_context: Optional query string to infer intent (e.g., 'thermal', 'elevation')
            
        Returns:
            Dictionary of optimal TiTiler parameters
        """
        params = {
            "scale": cls.DEFAULT_SCALE,  # @2x for HiDPI
            "format": cls.DEFAULT_FORMAT,
            "resampling": cls.DEFAULT_RESAMPLING.value
        }
        
        # Determine data type and add specific parameters
        is_elevation = collection_id in cls.ELEVATION_COLLECTIONS
        is_thermal = query_context and any(kw in query_context.lower() for kw in ["thermal", "temperature", "heat", "infrared"])
        is_optical = collection_id in cls.OPTICAL_COLLECTIONS
        
        # Elevation data configuration
        if is_elevation:
            params["resampling"] = ResamplingMethod.CUBIC.value  # Best for elevation
            params["colormap_name"] = "terrain"
            params["rescale"] = cls.RESCALE_RANGES.get(collection_id, (0, 4000))
            params["assets"] = "data"  # DEM collections use 'data' asset
            params["bidx"] = 1  # Single band
            
        # Thermal data configuration  
        elif is_thermal and collection_id == "landsat-c2-l2":
            params["resampling"] = ResamplingMethod.BILINEAR.value
            params["colormap_name"] = "plasma"
            params["rescale"] = cls.RESCALE_RANGES.get("thermal", (250, 330))
            params["assets"] = "ST_B10"  # Landsat Surface Temperature Band 10 (correct asset name)
            params["bidx"] = 1
            
        # Optical RGB data configuration
        elif is_optical:
            params["resampling"] = ResamplingMethod.LANCZOS.value  # Best for RGB
            
            # HLS collections use band numbers (B04, B03, B02)
            if collection_id in ["hls2-l30", "hls2-s30"]:
                params["assets"] = ["B04", "B03", "B02"]  # HLS RGB bands
                params["rescale"] = cls.RESCALE_RANGES.get(collection_id, (0, 3000))
            else:
                params["assets"] = ["red", "green", "blue"]  # Standard RGB composite
            
            # Add color enhancement for Landsat
            if collection_id == "landsat-c2-l2":
                params["color_formula"] = "gamma RGB 2.7, saturation 1.5, sigmoidal RGB 15 0.55"
        
        return params
    
    @classmethod
    def build_quality_url_params(cls, collection_id: str, query_context: Optional[str] = None) -> str:
        """
        Build URL query string with optimal quality parameters.
        
        Args:
            collection_id: STAC collection ID
            query_context: Optional query string for context
            
        Returns:
            URL query string (e.g., 'assets=data&colormap_name=terrain&rescale=0,4000&resampling=cubic')
        """
        params = cls.get_optimal_params(collection_id, query_context)
        
        query_parts = []
        
        # Handle assets (can be list or string)
        if "assets" in params:
            assets = params["assets"]
            if isinstance(assets, list):
                for asset in assets:
                    query_parts.append(f"assets={asset}")
            else:
                query_parts.append(f"assets={assets}")
        
        # Handle rescale (tuple)
        if "rescale" in params and params["rescale"]:
            min_val, max_val = params["rescale"]
            query_parts.append(f"rescale={min_val},{max_val}")
        
        # Handle bidx
        if "bidx" in params:
            query_parts.append(f"bidx={params['bidx']}")
        
        # Handle colormap
        if "colormap_name" in params:
            query_parts.append(f"colormap_name={params['colormap_name']}")
        
        # Handle resampling
        if "resampling" in params:
            query_parts.append(f"resampling={params['resampling']}")
        
        # Handle color formula
        if "color_formula" in params:
            # URL encode the formula
            formula = params["color_formula"].replace(" ", "+").replace(",", "%2C")
            query_parts.append(f"color_formula={formula}")
        
        # Handle format
        if "format" in params:
            query_parts.append(f"format={params['format']}")
        
        # Handle tile scale (@2x for HiDPI displays)
        if "scale" in params and params["scale"] > 1:
            query_parts.append(f"tile_scale={params['scale']}")
        
        return "&".join(query_parts)
    
    @classmethod
    def get_scale_suffix(cls, use_hidpi: bool = True) -> str:
        """Get the scale suffix for tile URLs (@1x or @2x)"""
        return f"@{cls.DEFAULT_SCALE}x" if use_hidpi else "@1x"
    
    @classmethod
    def get_colormap_for_collection(cls, collection_id: str, query_context: Optional[str] = None) -> str:
        """
        Get the best colormap for a collection based on data type.
        
        Args:
            collection_id: STAC collection ID
            query_context: Optional query string for context
            
        Returns:
            Colormap name
        """
        # Check collection type
        if collection_id in cls.ELEVATION_COLLECTIONS:
            return "terrain"
        
        # Check query context for keywords
        if query_context:
            query_lower = query_context.lower()
            for keyword, colormap in cls.COLORMAP_MAPPING.items():
                if keyword in query_lower:
                    return colormap
        
        return cls.COLORMAP_MAPPING["default"]


# Convenience functions for quick access
def get_optimal_tile_params(collection_id: str, query_context: Optional[str] = None) -> Dict[str, any]:
    """Quick access to optimal tile parameters"""
    return TiTilerQualityConfig.get_optimal_params(collection_id, query_context)


def build_tile_url_params(collection_id: str, query_context: Optional[str] = None) -> str:
    """Quick access to URL parameter string"""
    return TiTilerQualityConfig.build_quality_url_params(collection_id, query_context)


def get_tile_scale() -> str:
    """Get the recommended tile scale suffix (@2x for HiDPI)"""
    return TiTilerQualityConfig.get_scale_suffix(use_hidpi=True)
