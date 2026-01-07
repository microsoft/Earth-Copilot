"""
Raster Data Fetcher for Enhanced Terrain Analysis

This module fetches actual raster data from STAC sources (DEM, spectral bands)
to provide quantitative terrain metrics alongside visual analysis.

Features:
- DEM (Digital Elevation Model) for accurate elevation, slope, aspect
- Spectral bands from displayed collection for NDVI, water indices
- Cloud-Optimized GeoTIFF (COG) window reading for efficiency
"""

import logging
import os
from typing import Dict, Any, Optional, List, Tuple
import numpy as np
from io import BytesIO
import aiohttp
import planetary_computer
from pystac_client import Client

logger = logging.getLogger(__name__)

# Copernicus DEM collection (global 30m resolution)
DEM_COLLECTION = "cop-dem-glo-30"

# Spectral band mappings for common collections
SPECTRAL_BAND_MAPPINGS = {
    "landsat-c2-l2": {
        "red": "red",
        "nir": "nir08",
        "green": "green",
        "blue": "blue",
        "swir": "swir16"
    },
    "sentinel-2-l2a": {
        "red": "B04",
        "nir": "B08",
        "green": "B03",
        "blue": "B02",
        "swir": "B11"
    },
    "naip": {
        "red": "image",  # NAIP has 4-band single asset
        "nir": "image",
        "green": "image",
        "blue": "image"
    }
}


class RasterDataFetcher:
    """
    Fetches raster data from STAC sources for terrain analysis enrichment.
    Uses Cloud-Optimized GeoTIFF (COG) window reading for efficiency.
    """
    
    def __init__(self):
        """Initialize the raster data fetcher."""
        self.stac_endpoint = "https://planetarycomputer.microsoft.com/api/stac/v1"
        self._catalog = None
        logger.info("✅ RasterDataFetcher initialized")
    
    @property
    def catalog(self):
        """Lazy-load STAC catalog."""
        if self._catalog is None:
            self._catalog = Client.open(self.stac_endpoint)
        return self._catalog
    
    async def fetch_terrain_data(
        self,
        latitude: float,
        longitude: float,
        radius_miles: float = 5.0,
        collection_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Fetch terrain data (DEM + spectral) for a location.
        
        Args:
            latitude: Center latitude
            longitude: Center longitude
            radius_miles: Radius in miles for data fetch
            collection_id: Optional collection ID for spectral data
            
        Returns:
            Dict containing:
            - elevation_stats: Dict with min, max, mean, std elevation
            - slope_stats: Dict with terrain slope statistics
            - aspect_stats: Dict with terrain aspect (direction) statistics
            - spectral_indices: Dict with NDVI, NDWI if available
            - metadata: Source data information
        """
        try:
            logger.info(f"📡 Fetching terrain data at ({latitude:.4f}, {longitude:.4f})")
            
            # Calculate bounding box
            bbox = self._calculate_bbox(latitude, longitude, radius_miles)
            
            # Fetch DEM data
            dem_result = await self._fetch_dem_data(bbox, latitude, longitude)
            
            # Fetch spectral data if collection specified
            spectral_result = {}
            if collection_id and collection_id in SPECTRAL_BAND_MAPPINGS:
                spectral_result = await self._fetch_spectral_data(
                    bbox, latitude, longitude, collection_id
                )
            
            # Combine results
            result = {
                "elevation_stats": dem_result.get("elevation_stats", {}),
                "slope_stats": dem_result.get("slope_stats", {}),
                "aspect_stats": dem_result.get("aspect_stats", {}),
                "terrain_classification": dem_result.get("terrain_classification", "unknown"),
                "spectral_indices": spectral_result.get("indices", {}),
                "vegetation_classification": spectral_result.get("vegetation_classification", ""),
                "metadata": {
                    "dem_source": dem_result.get("source", ""),
                    "spectral_source": spectral_result.get("source", ""),
                    "bbox": bbox,
                    "center": [longitude, latitude]
                }
            }
            
            logger.info(f"✅ Terrain data fetched: elevation range {result['elevation_stats'].get('min', 0):.0f}-{result['elevation_stats'].get('max', 0):.0f}m")
            return result
            
        except Exception as e:
            logger.error(f"❌ Failed to fetch terrain data: {e}")
            return {
                "elevation_stats": {},
                "slope_stats": {},
                "aspect_stats": {},
                "terrain_classification": "unknown",
                "spectral_indices": {},
                "vegetation_classification": "",
                "metadata": {"error": str(e)}
            }
    
    def _calculate_bbox(
        self, 
        latitude: float, 
        longitude: float, 
        radius_miles: float
    ) -> List[float]:
        """Calculate bounding box from center point and radius."""
        # Approximate degrees per mile
        lat_deg_per_mile = 1 / 69.0
        lon_deg_per_mile = 1 / (69.0 * np.cos(np.radians(latitude)))
        
        lat_delta = radius_miles * lat_deg_per_mile
        lon_delta = radius_miles * lon_deg_per_mile
        
        return [
            longitude - lon_delta,  # min lon
            latitude - lat_delta,   # min lat
            longitude + lon_delta,  # max lon
            latitude + lat_delta    # max lat
        ]
    
    async def _fetch_dem_data(
        self,
        bbox: List[float],
        latitude: float,
        longitude: float
    ) -> Dict[str, Any]:
        """
        Fetch DEM data and calculate elevation/slope/aspect statistics.
        Uses rasterio with windowed reading for efficiency.
        """
        try:
            import rasterio
            from rasterio.windows import from_bounds
            
            # Search for DEM item
            search = self.catalog.search(
                collections=[DEM_COLLECTION],
                bbox=bbox,
                limit=1
            )
            
            items = list(search.items())
            if not items:
                logger.warning("No DEM data found for location")
                return {"elevation_stats": {}, "source": "none"}
            
            item = items[0]
            signed_item = planetary_computer.sign(item)
            
            # Get DEM asset URL
            dem_asset = signed_item.assets.get("data")
            if not dem_asset:
                logger.warning("DEM item has no 'data' asset")
                return {"elevation_stats": {}, "source": "none"}
            
            dem_url = dem_asset.href
            
            # Read DEM data using windowed reading
            with rasterio.open(dem_url) as src:
                # Calculate window from bbox
                window = from_bounds(*bbox, src.transform)
                
                # Ensure window is within bounds
                window = window.intersection(rasterio.windows.Window(
                    0, 0, src.width, src.height
                ))
                
                if window.width < 1 or window.height < 1:
                    logger.warning("DEM window too small")
                    return {"elevation_stats": {}, "source": DEM_COLLECTION}
                
                # Read elevation data
                elevation = src.read(1, window=window)
                
                # Handle nodata
                nodata = src.nodata or -9999
                elevation = np.ma.masked_equal(elevation, nodata)
                
                if elevation.count() == 0:
                    logger.warning("No valid DEM data in window")
                    return {"elevation_stats": {}, "source": DEM_COLLECTION}
                
                # Calculate elevation statistics
                elevation_stats = {
                    "min": float(elevation.min()),
                    "max": float(elevation.max()),
                    "mean": float(elevation.mean()),
                    "std": float(elevation.std()),
                    "range": float(elevation.max() - elevation.min())
                }
                
                # Calculate slope and aspect
                slope, aspect = self._calculate_slope_aspect(
                    elevation, 
                    src.res[0]  # pixel resolution in meters
                )
                
                slope_stats = {
                    "min": float(slope.min()) if slope.size > 0 else 0,
                    "max": float(slope.max()) if slope.size > 0 else 0,
                    "mean": float(slope.mean()) if slope.size > 0 else 0,
                    "std": float(slope.std()) if slope.size > 0 else 0
                }
                
                aspect_stats = self._categorize_aspect(aspect)
                
                # Classify terrain type
                terrain_class = self._classify_terrain(elevation_stats, slope_stats)
                
                return {
                    "elevation_stats": elevation_stats,
                    "slope_stats": slope_stats,
                    "aspect_stats": aspect_stats,
                    "terrain_classification": terrain_class,
                    "source": DEM_COLLECTION
                }
                
        except Exception as e:
            logger.error(f"Error fetching DEM data: {e}")
            import traceback
            logger.error(traceback.format_exc())
            return {"elevation_stats": {}, "source": "error", "error": str(e)}
    
    def _calculate_slope_aspect(
        self, 
        elevation: np.ndarray, 
        cell_size: float
    ) -> Tuple[np.ndarray, np.ndarray]:
        """Calculate slope (degrees) and aspect (degrees) from elevation."""
        try:
            # Calculate gradients
            dy, dx = np.gradient(elevation, cell_size)
            
            # Slope in degrees
            slope = np.degrees(np.arctan(np.sqrt(dx**2 + dy**2)))
            
            # Aspect in degrees (0-360, 0=North, 90=East)
            aspect = np.degrees(np.arctan2(-dx, dy))
            aspect = np.where(aspect < 0, aspect + 360, aspect)
            
            return slope, aspect
        except Exception:
            return np.array([]), np.array([])
    
    def _categorize_aspect(self, aspect: np.ndarray) -> Dict[str, Any]:
        """Categorize aspect into cardinal directions."""
        if aspect.size == 0:
            return {"dominant_direction": "unknown", "distribution": {}}
        
        # Define direction bins
        directions = {
            "N": ((aspect >= 337.5) | (aspect < 22.5)).sum(),
            "NE": ((aspect >= 22.5) & (aspect < 67.5)).sum(),
            "E": ((aspect >= 67.5) & (aspect < 112.5)).sum(),
            "SE": ((aspect >= 112.5) & (aspect < 157.5)).sum(),
            "S": ((aspect >= 157.5) & (aspect < 202.5)).sum(),
            "SW": ((aspect >= 202.5) & (aspect < 247.5)).sum(),
            "W": ((aspect >= 247.5) & (aspect < 292.5)).sum(),
            "NW": ((aspect >= 292.5) & (aspect < 337.5)).sum()
        }
        
        total = sum(directions.values())
        if total == 0:
            return {"dominant_direction": "unknown", "distribution": {}}
        
        # Calculate percentages
        distribution = {k: round(v / total * 100, 1) for k, v in directions.items()}
        dominant = max(directions, key=directions.get)
        
        return {
            "dominant_direction": dominant,
            "distribution": distribution,
            "mean_aspect": float(np.mean(aspect))
        }
    
    def _classify_terrain(
        self, 
        elevation_stats: Dict[str, float], 
        slope_stats: Dict[str, float]
    ) -> str:
        """Classify terrain based on elevation and slope characteristics."""
        elev_range = elevation_stats.get("range", 0)
        mean_slope = slope_stats.get("mean", 0)
        max_elev = elevation_stats.get("max", 0)
        
        # Classification logic
        if mean_slope < 2 and elev_range < 50:
            return "flat_plains"
        elif mean_slope < 5 and elev_range < 100:
            return "gently_rolling"
        elif mean_slope < 10 and elev_range < 300:
            return "hilly"
        elif mean_slope < 20 and elev_range < 500:
            return "rugged_hills"
        elif mean_slope >= 20 or elev_range >= 500:
            if max_elev > 2000:
                return "mountainous_high_altitude"
            else:
                return "mountainous"
        else:
            return "varied"
    
    async def _fetch_spectral_data(
        self,
        bbox: List[float],
        latitude: float,
        longitude: float,
        collection_id: str
    ) -> Dict[str, Any]:
        """
        Fetch spectral band data and calculate vegetation indices.
        """
        try:
            import rasterio
            from rasterio.windows import from_bounds
            
            band_mapping = SPECTRAL_BAND_MAPPINGS.get(collection_id, {})
            if not band_mapping:
                return {"indices": {}, "source": "unsupported_collection"}
            
            # Search for recent imagery
            search = self.catalog.search(
                collections=[collection_id],
                bbox=bbox,
                sortby=[{"field": "datetime", "direction": "desc"}],
                limit=1
            )
            
            items = list(search.items())
            if not items:
                logger.warning(f"No imagery found for {collection_id}")
                return {"indices": {}, "source": "none"}
            
            item = items[0]
            signed_item = planetary_computer.sign(item)
            
            indices = {}
            
            # Try to calculate NDVI
            red_band_name = band_mapping.get("red")
            nir_band_name = band_mapping.get("nir")
            
            if red_band_name and nir_band_name:
                red_asset = signed_item.assets.get(red_band_name)
                nir_asset = signed_item.assets.get(nir_band_name)
                
                if red_asset and nir_asset:
                    # For NAIP, bands are in single asset
                    if collection_id == "naip":
                        ndvi = await self._calculate_naip_ndvi(red_asset.href, bbox)
                    else:
                        ndvi = await self._calculate_ndvi(
                            red_asset.href, nir_asset.href, bbox
                        )
                    
                    if ndvi is not None:
                        indices["ndvi"] = ndvi
            
            # Classify vegetation based on NDVI
            veg_class = self._classify_vegetation(indices.get("ndvi", {}))
            
            return {
                "indices": indices,
                "vegetation_classification": veg_class,
                "source": collection_id,
                "item_datetime": item.datetime.isoformat() if item.datetime else None
            }
            
        except Exception as e:
            logger.error(f"Error fetching spectral data: {e}")
            return {"indices": {}, "source": "error", "error": str(e)}
    
    async def _calculate_ndvi(
        self, 
        red_url: str, 
        nir_url: str, 
        bbox: List[float]
    ) -> Optional[Dict[str, float]]:
        """Calculate NDVI from red and NIR bands."""
        try:
            import rasterio
            from rasterio.windows import from_bounds
            
            with rasterio.open(red_url) as red_src, rasterio.open(nir_url) as nir_src:
                # Calculate window
                window = from_bounds(*bbox, red_src.transform)
                window = window.intersection(rasterio.windows.Window(
                    0, 0, red_src.width, red_src.height
                ))
                
                if window.width < 1 or window.height < 1:
                    return None
                
                red = red_src.read(1, window=window).astype(float)
                nir = nir_src.read(1, window=window).astype(float)
                
                # Handle nodata
                red = np.ma.masked_equal(red, red_src.nodata or 0)
                nir = np.ma.masked_equal(nir, nir_src.nodata or 0)
                
                # Calculate NDVI
                denominator = nir + red
                ndvi = np.where(
                    denominator > 0,
                    (nir - red) / denominator,
                    0
                )
                
                # Clip to valid range
                ndvi = np.clip(ndvi, -1, 1)
                
                return {
                    "min": float(np.min(ndvi)),
                    "max": float(np.max(ndvi)),
                    "mean": float(np.mean(ndvi)),
                    "std": float(np.std(ndvi))
                }
                
        except Exception as e:
            logger.error(f"Error calculating NDVI: {e}")
            return None
    
    async def _calculate_naip_ndvi(
        self, 
        image_url: str, 
        bbox: List[float]
    ) -> Optional[Dict[str, float]]:
        """Calculate NDVI from NAIP 4-band image (R, G, B, NIR)."""
        try:
            import rasterio
            from rasterio.windows import from_bounds
            
            with rasterio.open(image_url) as src:
                window = from_bounds(*bbox, src.transform)
                window = window.intersection(rasterio.windows.Window(
                    0, 0, src.width, src.height
                ))
                
                if window.width < 1 or window.height < 1:
                    return None
                
                # NAIP: band 1=R, band 2=G, band 3=B, band 4=NIR
                red = src.read(1, window=window).astype(float)
                nir = src.read(4, window=window).astype(float)
                
                denominator = nir + red
                ndvi = np.where(
                    denominator > 0,
                    (nir - red) / denominator,
                    0
                )
                
                ndvi = np.clip(ndvi, -1, 1)
                
                return {
                    "min": float(np.min(ndvi)),
                    "max": float(np.max(ndvi)),
                    "mean": float(np.mean(ndvi)),
                    "std": float(np.std(ndvi))
                }
                
        except Exception as e:
            logger.error(f"Error calculating NAIP NDVI: {e}")
            return None
    
    def _classify_vegetation(self, ndvi_stats: Dict[str, float]) -> str:
        """Classify vegetation based on NDVI values."""
        if not ndvi_stats:
            return "unknown"
        
        mean_ndvi = ndvi_stats.get("mean", 0)
        
        if mean_ndvi < 0:
            return "water_or_barren"
        elif mean_ndvi < 0.1:
            return "barren_or_sparse"
        elif mean_ndvi < 0.2:
            return "sparse_vegetation"
        elif mean_ndvi < 0.3:
            return "moderate_vegetation"
        elif mean_ndvi < 0.5:
            return "healthy_vegetation"
        elif mean_ndvi < 0.7:
            return "dense_vegetation"
        else:
            return "very_dense_vegetation"
    
    def format_terrain_summary(self, data: Dict[str, Any]) -> str:
        """
        Format terrain data into a human-readable summary for GPT-4o context.
        """
        lines = ["📊 **Quantitative Terrain Metrics:**"]
        
        # Elevation
        elev = data.get("elevation_stats", {})
        if elev:
            lines.append(f"- **Elevation:** {elev.get('min', 0):.0f}m - {elev.get('max', 0):.0f}m (mean: {elev.get('mean', 0):.0f}m, range: {elev.get('range', 0):.0f}m)")
        
        # Slope
        slope = data.get("slope_stats", {})
        if slope:
            lines.append(f"- **Slope:** avg {slope.get('mean', 0):.1f}° (max: {slope.get('max', 0):.1f}°)")
        
        # Aspect
        aspect = data.get("aspect_stats", {})
        if aspect.get("dominant_direction"):
            lines.append(f"- **Dominant Slope Direction:** {aspect.get('dominant_direction')}")
        
        # Terrain classification
        terrain_class = data.get("terrain_classification", "")
        if terrain_class:
            lines.append(f"- **Terrain Type:** {terrain_class.replace('_', ' ').title()}")
        
        # NDVI
        ndvi = data.get("spectral_indices", {}).get("ndvi", {})
        if ndvi:
            lines.append(f"- **NDVI:** {ndvi.get('mean', 0):.2f} (range: {ndvi.get('min', 0):.2f} to {ndvi.get('max', 0):.2f})")
        
        # Vegetation classification
        veg_class = data.get("vegetation_classification", "")
        if veg_class:
            lines.append(f"- **Vegetation:** {veg_class.replace('_', ' ').title()}")
        
        return "\n".join(lines)


# Singleton instance
_raster_fetcher = None

def get_raster_fetcher() -> RasterDataFetcher:
    """Get singleton RasterDataFetcher instance."""
    global _raster_fetcher
    if _raster_fetcher is None:
        _raster_fetcher = RasterDataFetcher()
    return _raster_fetcher
