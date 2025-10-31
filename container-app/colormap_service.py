"""
TiTiler Colormap Service for Earth-Copilot

This service fetches and caches colormap definitions from TiTiler/Planetary Computer,
providing the correct color specifications for elevation and other data types.

Based on TiTiler documentation:
- GET /colorMaps - List all available colormaps
- GET /colorMaps/{colorMapId} - Get RGB values for specific colormap (returns JSON with 0-255 mapping)

Reference:
- https://developmentseed.org/titiler/endpoints/colormaps/
- https://planetarycomputer.microsoft.com/api/data/v1/docs
"""
import asyncio
import logging
from typing import Dict, List, Optional, Tuple
from datetime import datetime, timedelta
import httpx

logger = logging.getLogger(__name__)

# Planetary Computer TiTiler endpoint
TITILER_BASE_URL = "https://planetarycomputer.microsoft.com/api/data/v1"

# Cache for colormap data (colormaps rarely change)
_colormap_cache: Dict[str, Dict] = {}
_cache_timestamp: Dict[str, datetime] = {}
CACHE_TTL = timedelta(hours=24)  # Cache for 24 hours

# Fallback colormaps (matplotlib colormaps for when TiTiler API is unavailable)
FALLBACK_COLORMAPS = {
    "terrain": {
        "0": [68, 27, 108, 255], "25": [44, 105, 168, 255], "50": [33, 145, 140, 255],
        "75": [94, 201, 98, 255], "100": [253, 187, 132, 255], "125": [254, 224, 182, 255],
        "150": [247, 252, 253, 255], "175": [229, 245, 224, 255], "200": [199, 233, 180, 255],
        "225": [127, 205, 187, 255], "250": [65, 182, 196, 255], "255": [44, 127, 184, 255]
    },
    "viridis": {
        "0": [68, 1, 84, 255], "51": [59, 82, 139, 255], "102": [33, 145, 140, 255],
        "153": [94, 201, 98, 255], "204": [253, 231, 37, 255], "255": [253, 231, 37, 255]
    },
    "plasma": {
        "0": [13, 8, 135, 255], "51": [126, 3, 168, 255], "102": [204, 71, 120, 255],
        "153": [248, 149, 64, 255], "204": [252, 253, 191, 255], "255": [240, 249, 33, 255]
    },
    "inferno": {
        "0": [0, 0, 4, 255], "51": [87, 16, 110, 255], "102": [188, 55, 84, 255],
        "153": [249, 142, 9, 255], "204": [252, 255, 164, 255], "255": [252, 255, 164, 255]
    },
    "magma": {
        "0": [0, 0, 4, 255], "51": [80, 18, 123, 255], "102": [182, 54, 121, 255],
        "153": [251, 136, 97, 255], "204": [254, 254, 189, 255], "255": [252, 253, 191, 255]
    },
    "cividis": {
        "0": [0, 32, 77, 255], "51": [26, 83, 92, 255], "102": [87, 130, 107, 255],
        "153": [157, 173, 120, 255], "204": [234, 212, 170, 255], "255": [255, 234, 201, 255]
    }
}


class ColormapService:
    """Service for fetching and managing TiTiler colormaps"""
    
    def __init__(self, base_url: str = TITILER_BASE_URL):
        self.base_url = base_url.rstrip('/')
        self.client = httpx.AsyncClient(timeout=30.0)
        logger.info(f"🎨 ColormapService initialized with base URL: {self.base_url}")
    
    async def close(self):
        """Close the HTTP client"""
        await self.client.aclose()
    
    async def list_available_colormaps(self) -> List[str]:
        """
        Get list of all available colormaps from TiTiler.
        
        Returns:
            List of colormap names (e.g., ['terrain', 'viridis', 'plasma', ...])
        """
        try:
            url = f"{self.base_url}/colorMaps"
            logger.info(f"📡 Fetching colormap list from: {url}")
            
            response = await self.client.get(url)
            response.raise_for_status()
            
            data = response.json()
            colormaps = data.get("colorMaps", [])
            logger.info(f"✅ Retrieved {len(colormaps)} available colormaps")
            return colormaps
            
        except Exception as e:
            logger.error(f"❌ Failed to fetch colormap list: {e}")
            # Return default colormaps as fallback
            return ["terrain", "viridis", "plasma", "inferno", "magma", "cividis"]
    
    async def get_colormap_definition(self, colormap_name: str, use_cache: bool = True) -> Optional[Dict[str, List[int]]]:
        """
        Get RGB color values for a specific colormap.
        
        Args:
            colormap_name: Name of the colormap (e.g., 'terrain', 'viridis')
            use_cache: Whether to use cached data if available
        
        Returns:
            Dictionary mapping position (0-255) to RGBA values: {"0": [R, G, B, A], "255": [R, G, B, A]}
            Returns None if fetch fails
        
        Example return:
            {
                "0": [68, 1, 84, 255],      # Dark blue (low elevation)
                "64": [59, 82, 139, 255],    # Medium blue
                "128": [33, 145, 140, 255],  # Teal/green (mid elevation)
                "192": [253, 231, 36, 255],  # Yellow (high elevation)
                "255": [253, 231, 36, 255]   # Yellow (peak elevation)
            }
        """
        # Check cache first
        if use_cache and colormap_name in _colormap_cache:
            cache_time = _cache_timestamp.get(colormap_name)
            if cache_time and (datetime.now() - cache_time) < CACHE_TTL:
                logger.info(f"📦 Using cached colormap: {colormap_name}")
                return _colormap_cache[colormap_name]
        
        try:
            url = f"{self.base_url}/colorMaps/{colormap_name}"
            logger.info(f"📡 Fetching colormap definition: {url}")
            
            response = await self.client.get(url)
            response.raise_for_status()
            
            colormap_data = response.json()
            
            # Cache the result
            _colormap_cache[colormap_name] = colormap_data
            _cache_timestamp[colormap_name] = datetime.now()
            
            logger.info(f"✅ Retrieved colormap '{colormap_name}' with {len(colormap_data)} color stops")
            return colormap_data
            
        except Exception as e:
            logger.error(f"❌ Failed to fetch colormap '{colormap_name}': {e}")
            
            # Try fallback colormap
            if colormap_name in FALLBACK_COLORMAPS:
                logger.info(f"📦 Using fallback colormap for '{colormap_name}'")
                fallback_data = FALLBACK_COLORMAPS[colormap_name]
                
                # Cache the fallback
                _colormap_cache[colormap_name] = fallback_data
                _cache_timestamp[colormap_name] = datetime.now()
                
                return fallback_data
            else:
                logger.warning(f"⚠️ No fallback colormap available for '{colormap_name}'")
                # Return a default terrain colormap as last resort
                if "terrain" in FALLBACK_COLORMAPS:
                    logger.info(f"📦 Using default 'terrain' colormap as fallback")
                    return FALLBACK_COLORMAPS["terrain"]
                return None
    
    def colormap_to_css_gradient(self, colormap_data: Dict[str, List[int]], orientation: str = "vertical") -> str:
        """
        Convert TiTiler colormap data to CSS gradient string.
        
        Args:
            colormap_data: Dictionary mapping position to RGBA values
            orientation: 'vertical' (bottom to top) or 'horizontal' (left to right)
        
        Returns:
            CSS linear-gradient string
        
        Example:
            "linear-gradient(to top, rgb(68,1,84) 0%, rgb(59,82,139) 25%, ...)"
        """
        if not colormap_data:
            return ""
        
        # Sort by position (0-255)
        sorted_stops = sorted([(int(pos), rgba) for pos, rgba in colormap_data.items()])
        
        # Convert to CSS gradient stops
        gradient_stops = []
        for position, rgba in sorted_stops:
            # Calculate percentage (0-255 -> 0-100%)
            percentage = (position / 255.0) * 100
            # Extract RGB (ignore alpha for CSS)
            r, g, b = rgba[0], rgba[1], rgba[2]
            gradient_stops.append(f"rgb({r},{g},{b}) {percentage:.1f}%")
        
        # Build CSS gradient
        direction = "to top" if orientation == "vertical" else "to right"
        gradient = f"linear-gradient({direction}, {', '.join(gradient_stops)})"
        
        logger.debug(f"🎨 Generated CSS gradient with {len(gradient_stops)} stops")
        return gradient
    
    async def get_colormap_for_collection(self, collection_id: str) -> Tuple[str, Optional[Dict]]:
        """
        Get the recommended colormap for a specific STAC collection.
        
        Args:
            collection_id: STAC collection ID (e.g., 'cop-dem-glo-30')
        
        Returns:
            Tuple of (colormap_name, colormap_data)
        
        Collection-specific mappings:
        - DEM/Elevation: terrain
        - NDVI/Vegetation: viridis or greens
        - Temperature: plasma or inferno
        - SAR: gray or viridis
        """
        # Map collections to appropriate colormaps
        colormap_mapping = {
            # Elevation/DEM collections -> terrain colormap
            "cop-dem-glo-30": "terrain",
            "cop-dem-glo-90": "terrain",
            "nasadem": "terrain",
            "alos-dem": "terrain",
            "3dep-seamless": "terrain",
            "aster-l1t": "terrain",
            
            # Vegetation indices -> viridis (perceptually uniform)
            "modis-13q1-061": "viridis",
            "modis-13a1-061": "viridis",
            "modis-09q1-061": "viridis",
            "modis-09a1-061": "viridis",
            
            # Fire Detection -> inferno (hot reds/oranges for fire)
            "modis-14a1-061": "inferno",  # ✅ CRITICAL: Fire daily
            "modis-14a2-061": "inferno",  # ✅ Fire 8-day
            "viirs-375": "inferno",       # VIIRS fire
            "modis-mcd64a1-061": "plasma",  # Burned area
            
            # Temperature -> plasma (hot colors)
            "modis-11a1-061": "plasma",  # ✅ Land Surface Temperature
            "modis-11a2-061": "plasma",  # LST 8-day
            "era5-pds": "plasma",
            "era5-land": "plasma",
            "modis-sst": "plasma",
            
            # Default fallback
            "default": "viridis"
        }
        
        colormap_name = colormap_mapping.get(collection_id, "viridis")
        logger.info(f"🎨 Collection '{collection_id}' -> colormap '{colormap_name}'")
        
        # Fetch the colormap data
        colormap_data = await self.get_colormap_definition(colormap_name)
        
        return colormap_name, colormap_data
    
    def extract_legend_labels(self, colormap_data: Dict[str, List[int]], 
                            min_value: float, max_value: float,
                            num_labels: int = 5) -> List[Tuple[float, str]]:
        """
        Generate legend labels for a colormap based on data range.
        
        Args:
            colormap_data: TiTiler colormap data
            min_value: Minimum data value (e.g., -1000m for elevation)
            max_value: Maximum data value (e.g., 4000m for elevation)
            num_labels: Number of labels to generate
        
        Returns:
            List of (value, label) tuples
        
        Example for elevation -1000 to 4000:
            [(-1000, "Below Sea Level"), (0, "Sea Level"), (1000, "1000m"), (2000, "2000m"), (4000, "4000m+")]
        """
        labels = []
        value_range = max_value - min_value
        
        for i in range(num_labels):
            # Calculate value at this position
            value = min_value + (value_range * i / (num_labels - 1))
            
            # Format label based on data type (assuming elevation for now)
            if value < 0:
                label = f"{int(value)}m (Below Sea Level)"
            elif value == 0:
                label = "Sea Level"
            elif value >= 1000:
                label = f"{int(value/1000)}km" if value >= 10000 else f"{int(value)}m"
            else:
                label = f"{int(value)}m"
            
            labels.append((value, label))
        
        return labels


# Global service instance
_colormap_service: Optional[ColormapService] = None


async def get_colormap_service() -> ColormapService:
    """Get or create the global colormap service instance"""
    global _colormap_service
    if _colormap_service is None:
        _colormap_service = ColormapService()
    return _colormap_service


# Convenience functions for FastAPI endpoints
async def fetch_colormap(colormap_name: str = "terrain") -> Optional[Dict]:
    """
    Convenience function to fetch a colormap.
    Can be used directly in FastAPI endpoints.
    """
    service = await get_colormap_service()
    return await service.get_colormap_definition(colormap_name)


async def fetch_collection_colormap(collection_id: str) -> Dict:
    """
    Fetch the appropriate colormap for a STAC collection.
    Returns both the colormap data and CSS gradient.
    """
    service = await get_colormap_service()
    colormap_name, colormap_data = await service.get_colormap_for_collection(collection_id)
    
    if colormap_data:
        css_gradient = service.colormap_to_css_gradient(colormap_data, orientation="vertical")
        return {
            "colormap_name": colormap_name,
            "colormap_data": colormap_data,
            "css_gradient": css_gradient,
            "success": True
        }
    else:
        return {
            "colormap_name": colormap_name,
            "colormap_data": None,
            "css_gradient": "",
            "success": False,
            "error": f"Failed to fetch colormap '{colormap_name}'"
        }
