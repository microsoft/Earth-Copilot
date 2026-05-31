"""
Specialized Raster Analysis Tools for GEOINT Modules

These tools download and analyze geospatial raster data (GeoTIFF, COG, NetCDF, HDF)
and return quantitative metrics. They are designed to be called by autonomous agents
like the Vision Agent or Terrain Analysis Agent.

Tools:
1. calculate_terrain_slope - DEM slope analysis
2. measure_elevation_profile - Elevation statistics
3. detect_water_bodies - SAR-based water detection
4. calculate_vegetation_index - NDVI/NDWI/EVI calculation
5. detect_active_fires - MODIS fire detection
6. classify_land_cover - Multi-spectral land classification
7. analyze_temporal_change - Before/after change detection
8. analyze_visual_features - Wrapper for Vision Agent (PNG analysis)
"""

from typing import Dict, Any, Optional, List, Literal
import logging
import asyncio
from datetime import datetime, timedelta
import numpy as np
import planetary_computer
import pystac_client
import aiohttp

logger = logging.getLogger(__name__)


class GeospatialTools:
    """Collection of specialized tools for raster analysis."""
    
    # Thresholds
    WATER_BACKSCATTER_THRESHOLD = -20  # dB for SAR water detection
    STEEP_SLOPE_THRESHOLD = 30  # degrees
    MODERATE_SLOPE_THRESHOLD = 15  # degrees
    FIRE_HIGH_CONFIDENCE = 9  # MODIS FireMask value
    
    def __init__(self):
        """Initialize the tools with STAC endpoint."""
        from cloud_config import cloud_cfg
        self.stac_endpoint = cloud_cfg.stac_catalog_url
        logger.info(" GeospatialTools initialized")
    
    async def calculate_terrain_slope(
        self,
        latitude: float,
        longitude: float,
        radius_miles: float = 5.0
    ) -> Dict[str, Any]:
        """
        Calculate terrain slope from Digital Elevation Model (DEM).
        
        Args:
            latitude: Center point latitude
            longitude: Center point longitude
            radius_miles: Analysis radius in miles
            
        Returns:
            {
                "avg_slope": float,  # Average slope in degrees
                "max_slope": float,  # Maximum slope in degrees
                "min_slope": float,  # Minimum slope in degrees
                "steep_pct": float,  # Percentage with slope > 30°
                "moderate_pct": float,  # Percentage with slope 15-30°
                "gentle_pct": float,  # Percentage with slope < 15°
                "confidence": str  # "high", "medium", "low"
            }
        """
        try:
            logger.info(f" Calculating terrain slope for ({latitude:.6f}, {longitude:.6f}), radius={radius_miles}mi")
            
            # Calculate bounding box
            bbox = self._calculate_bbox(latitude, longitude, radius_miles)
            
            # Download DEM data
            elevation_data = await self._download_raster(
                collection_id="cop-dem-glo-30",
                bbox=bbox,
                asset_key="data"
            )
            
            if elevation_data is None:
                return {
                    "avg_slope": 0,
                    "max_slope": 0,
                    "min_slope": 0,
                    "steep_pct": 0,
                    "moderate_pct": 0,
                    "gentle_pct": 0,
                    "confidence": "low",
                    "error": "No DEM data available"
                }
            
            # Calculate slope using numpy gradient
            dy, dx = np.gradient(elevation_data)
            slope_radians = np.arctan(np.sqrt(dx**2 + dy**2))
            slope_degrees = np.degrees(slope_radians)
            
            # Remove NaN values
            valid_slopes = slope_degrees[~np.isnan(slope_degrees)]
            
            if len(valid_slopes) == 0:
                return {"error": "No valid slope data", "confidence": "low"}
            
            # Calculate statistics
            avg_slope = float(np.mean(valid_slopes))
            max_slope = float(np.max(valid_slopes))
            min_slope = float(np.min(valid_slopes))
            
            steep_pct = float(np.sum(valid_slopes > self.STEEP_SLOPE_THRESHOLD) / len(valid_slopes) * 100)
            moderate_pct = float(np.sum((valid_slopes >= self.MODERATE_SLOPE_THRESHOLD) & 
                                       (valid_slopes <= self.STEEP_SLOPE_THRESHOLD)) / len(valid_slopes) * 100)
            gentle_pct = float(np.sum(valid_slopes < self.MODERATE_SLOPE_THRESHOLD) / len(valid_slopes) * 100)
            
            logger.info(f" Slope analysis: avg={avg_slope:.1f}°, max={max_slope:.1f}°, steep={steep_pct:.1f}%")
            
            return {
                "avg_slope": round(avg_slope, 1),
                "max_slope": round(max_slope, 1),
                "min_slope": round(min_slope, 1),
                "steep_pct": round(steep_pct, 1),
                "moderate_pct": round(moderate_pct, 1),
                "gentle_pct": round(gentle_pct, 1),
                "confidence": "high"
            }
            
        except Exception as e:
            logger.error(f" Slope calculation failed: {e}")
            return {"error": str(e), "confidence": "low"}
    
    async def measure_elevation_profile(
        self,
        latitude: float,
        longitude: float,
        radius_miles: float = 5.0
    ) -> Dict[str, Any]:
        """
        Measure elevation statistics from DEM.
        
        Args:
            latitude: Center point latitude
            longitude: Center point longitude
            radius_miles: Analysis radius in miles
            
        Returns:
            {
                "min_elevation": float,  # Meters
                "max_elevation": float,  # Meters
                "avg_elevation": float,  # Meters
                "relief": float,  # Max - Min (meters)
                "std_dev": float,  # Standard deviation
                "confidence": str
            }
        """
        try:
            logger.info(f" Measuring elevation profile for ({latitude:.6f}, {longitude:.6f})")
            
            bbox = self._calculate_bbox(latitude, longitude, radius_miles)
            elevation_data = await self._download_raster("cop-dem-glo-30", bbox, "data")
            
            if elevation_data is None:
                return {"error": "No DEM data available", "confidence": "low"}
            
            valid_elev = elevation_data[~np.isnan(elevation_data)]
            
            if len(valid_elev) == 0:
                return {"error": "No valid elevation data", "confidence": "low"}
            
            min_elev = float(np.min(valid_elev))
            max_elev = float(np.max(valid_elev))
            avg_elev = float(np.mean(valid_elev))
            relief = max_elev - min_elev
            std_dev = float(np.std(valid_elev))
            
            logger.info(f" Elevation: min={min_elev:.0f}m, max={max_elev:.0f}m, avg={avg_elev:.0f}m, relief={relief:.0f}m")
            
            return {
                "min_elevation": round(min_elev, 1),
                "max_elevation": round(max_elev, 1),
                "avg_elevation": round(avg_elev, 1),
                "relief": round(relief, 1),
                "std_dev": round(std_dev, 1),
                "confidence": "high"
            }
            
        except Exception as e:
            logger.error(f" Elevation measurement failed: {e}")
            return {"error": str(e), "confidence": "low"}
    
    async def detect_water_bodies(
        self,
        latitude: float,
        longitude: float,
        radius_miles: float = 5.0
    ) -> Dict[str, Any]:
        """
        Detect water bodies using SAR backscatter analysis.
        
        Args:
            latitude: Center point latitude
            longitude: Center point longitude
            radius_miles: Analysis radius in miles
            
        Returns:
            {
                "water_coverage_pct": float,  # Percentage of area covered by water
                "water_detected": bool,  # True if significant water bodies found
                "confidence": str,
                "method": "SAR backscatter < -20dB"
            }
        """
        try:
            logger.info(f" Detecting water bodies for ({latitude:.6f}, {longitude:.6f})")
            
            bbox = self._calculate_bbox(latitude, longitude, radius_miles)
            
            # Use Sentinel-1 GRD VV polarization
            sar_data = await self._download_raster(
                collection_id="sentinel-1-grd",
                bbox=bbox,
                asset_key="vv",
                days_back=30
            )
            
            if sar_data is None:
                return {"error": "No SAR data available", "confidence": "low"}
            
            valid_pixels = sar_data[~np.isnan(sar_data)]
            
            if len(valid_pixels) == 0:
                return {"error": "No valid SAR data", "confidence": "low"}
            
            # Water detection: backscatter < -20 dB
            water_mask = valid_pixels < self.WATER_BACKSCATTER_THRESHOLD
            water_coverage_pct = float(np.sum(water_mask) / len(valid_pixels) * 100)
            water_detected = water_coverage_pct > 5.0  # Threshold: 5% coverage
            
            logger.info(f" Water detection: {water_coverage_pct:.1f}% coverage")
            
            return {
                "water_coverage_pct": round(water_coverage_pct, 1),
                "water_detected": water_detected,
                "threshold_db": self.WATER_BACKSCATTER_THRESHOLD,
                "confidence": "high",
                "method": "SAR backscatter analysis"
            }
            
        except Exception as e:
            logger.error(f" Water detection failed: {e}")
            return {"error": str(e), "confidence": "low"}
    
    async def calculate_vegetation_index(
        self,
        latitude: float,
        longitude: float,
        radius_miles: float = 5.0,
        index_type: Literal["NDVI", "NDWI", "EVI"] = "NDVI"
    ) -> Dict[str, Any]:
        """
        Calculate vegetation index from Sentinel-2 optical imagery.
        
        Args:
            latitude: Center point latitude
            longitude: Center point longitude
            radius_miles: Analysis radius in miles
            index_type: Type of index (NDVI, NDWI, EVI)
            
        Returns:
            {
                "avg_index": float,  # Average index value (-1 to 1)
                "dense_vegetation_pct": float,  # Percentage with high NDVI (>0.6)
                "sparse_vegetation_pct": float,  # Percentage with low NDVI (0.2-0.6)
                "no_vegetation_pct": float,  # Percentage with no vegetation (<0.2)
                "confidence": str
            }
        """
        try:
            logger.info(f" Calculating {index_type} for ({latitude:.6f}, {longitude:.6f})")
            
            bbox = self._calculate_bbox(latitude, longitude, radius_miles)
            
            # Download Sentinel-2 bands (NIR=B08, Red=B04, Green=B03, SWIR=B11)
            if index_type == "NDVI":
                # NDVI = (NIR - Red) / (NIR + Red)
                nir_data = await self._download_raster("sentinel-2-l2a", bbox, "B08", days_back=30)
                red_data = await self._download_raster("sentinel-2-l2a", bbox, "B04", days_back=30)
                
                if nir_data is None or red_data is None:
                    return {"error": "No Sentinel-2 data available", "confidence": "low"}
                
                # Calculate NDVI
                with np.errstate(divide='ignore', invalid='ignore'):
                    index_data = (nir_data - red_data) / (nir_data + red_data)
                
            elif index_type == "NDWI":
                # NDWI = (Green - NIR) / (Green + NIR)
                green_data = await self._download_raster("sentinel-2-l2a", bbox, "B03", days_back=30)
                nir_data = await self._download_raster("sentinel-2-l2a", bbox, "B08", days_back=30)
                
                if green_data is None or nir_data is None:
                    return {"error": "No Sentinel-2 data available", "confidence": "low"}
                
                with np.errstate(divide='ignore', invalid='ignore'):
                    index_data = (green_data - nir_data) / (green_data + nir_data)
            
            else:  # EVI
                return {"error": f"Index type {index_type} not yet implemented", "confidence": "low"}
            
            # Remove invalid values
            valid_index = index_data[(~np.isnan(index_data)) & (index_data >= -1) & (index_data <= 1)]
            
            if len(valid_index) == 0:
                return {"error": "No valid index data", "confidence": "low"}
            
            avg_index = float(np.mean(valid_index))
            
            if index_type == "NDVI":
                dense_pct = float(np.sum(valid_index > 0.6) / len(valid_index) * 100)
                sparse_pct = float(np.sum((valid_index >= 0.2) & (valid_index <= 0.6)) / len(valid_index) * 100)
                none_pct = float(np.sum(valid_index < 0.2) / len(valid_index) * 100)
            else:
                dense_pct = sparse_pct = none_pct = 0.0
            
            logger.info(f" {index_type}: avg={avg_index:.2f}, dense={dense_pct:.1f}%")
            
            return {
                "index_type": index_type,
                "avg_index": round(avg_index, 2),
                "dense_vegetation_pct": round(dense_pct, 1),
                "sparse_vegetation_pct": round(sparse_pct, 1),
                "no_vegetation_pct": round(none_pct, 1),
                "confidence": "high"
            }
            
        except Exception as e:
            logger.error(f" Vegetation index calculation failed: {e}")
            return {"error": str(e), "confidence": "low"}
    
    async def detect_active_fires(
        self,
        latitude: float,
        longitude: float,
        radius_miles: float = 5.0
    ) -> Dict[str, Any]:
        """
        Detect active fires using MODIS fire detection.
        
        Args:
            latitude: Center point latitude
            longitude: Center point longitude
            radius_miles: Analysis radius in miles
            
        Returns:
            {
                "high_confidence_fires": int,  # Count of high-confidence fire pixels
                "nominal_fires": int,  # Count of nominal-confidence fire pixels
                "low_confidence_fires": int,  # Count of low-confidence fire pixels
                "total_fires": int,  # Total fire detections
                "fire_detected": bool,  # True if any fires found
                "confidence": str
            }
        """
        try:
            logger.info(f" Detecting active fires for ({latitude:.6f}, {longitude:.6f})")
            
            bbox = self._calculate_bbox(latitude, longitude, radius_miles)
            
            # Download MODIS FireMask
            fire_data = await self._download_raster(
                collection_id="modis-14A1-061",
                bbox=bbox,
                asset_key="FireMask",
                days_back=7  # Last week
            )
            
            if fire_data is None:
                return {"error": "No MODIS fire data available", "confidence": "low"}
            
            valid_pixels = fire_data[~np.isnan(fire_data)]
            
            if len(valid_pixels) == 0:
                return {"error": "No valid fire data", "confidence": "low"}
            
            # FireMask values: 7=low, 8=nominal, 9=high confidence
            high_conf = int(np.sum(valid_pixels == 9))
            nominal = int(np.sum(valid_pixels == 8))
            low_conf = int(np.sum(valid_pixels == 7))
            total = high_conf + nominal + low_conf
            
            logger.info(f" Fire detection: high={high_conf}, nominal={nominal}, low={low_conf}")
            
            return {
                "high_confidence_fires": high_conf,
                "nominal_fires": nominal,
                "low_confidence_fires": low_conf,
                "total_fires": total,
                "fire_detected": total > 0,
                "confidence": "high" if total > 0 else "medium"
            }
            
        except Exception as e:
            logger.error(f" Fire detection failed: {e}")
            return {"error": str(e), "confidence": "low"}
    
    async def classify_land_cover(
        self,
        latitude: float,
        longitude: float,
        radius_miles: float = 5.0
    ) -> Dict[str, Any]:
        """
        Classify land cover using multi-spectral analysis.
        
        Uses simple thresholds on NDVI, NDWI, and NDBI to classify:
        - Water: NDWI > 0.3
        - Dense vegetation: NDVI > 0.6
        - Sparse vegetation: 0.2 < NDVI < 0.6
        - Urban: NDBI > 0 (approximation)
        - Bare soil: Everything else
        
        Args:
            latitude: Center point latitude
            longitude: Center point longitude
            radius_miles: Analysis radius in miles
            
        Returns:
            {
                "water_pct": float,
                "dense_vegetation_pct": float,
                "sparse_vegetation_pct": float,
                "urban_pct": float,
                "bare_soil_pct": float,
                "confidence": str
            }
        """
        try:
            logger.info(f" Classifying land cover for ({latitude:.6f}, {longitude:.6f})")
            
            # Get NDVI and NDWI
            ndvi_result = await self.calculate_vegetation_index(latitude, longitude, radius_miles, "NDVI")
            ndwi_result = await self.calculate_vegetation_index(latitude, longitude, radius_miles, "NDWI")
            
            if "error" in ndvi_result or "error" in ndwi_result:
                return {"error": "Failed to calculate indices", "confidence": "low"}
            
            # Simple classification (this is a placeholder - real classification would need pixel-level analysis)
            water_pct = max(0, ndwi_result.get("avg_index", 0) * 30)  # Rough approximation
            dense_veg_pct = ndvi_result.get("dense_vegetation_pct", 0)
            sparse_veg_pct = ndvi_result.get("sparse_vegetation_pct", 0)
            bare_soil_pct = ndvi_result.get("no_vegetation_pct", 0)
            urban_pct = max(0, 100 - water_pct - dense_veg_pct - sparse_veg_pct - bare_soil_pct)
            
            logger.info(f" Land cover: water={water_pct:.1f}%, veg={dense_veg_pct+sparse_veg_pct:.1f}%")
            
            return {
                "water_pct": round(water_pct, 1),
                "dense_vegetation_pct": round(dense_veg_pct, 1),
                "sparse_vegetation_pct": round(sparse_veg_pct, 1),
                "urban_pct": round(urban_pct, 1),
                "bare_soil_pct": round(bare_soil_pct, 1),
                "confidence": "medium"  # Simplified classification
            }
            
        except Exception as e:
            logger.error(f" Land cover classification failed: {e}")
            return {"error": str(e), "confidence": "low"}
    
    async def analyze_temporal_change(
        self,
        latitude: float,
        longitude: float,
        before_date: str,
        after_date: str,
        radius_miles: float = 5.0,
        metric: Literal["NDVI", "elevation", "backscatter"] = "NDVI"
    ) -> Dict[str, Any]:
        """
        Analyze temporal change between two dates.
        
        Args:
            latitude: Center point latitude
            longitude: Center point longitude
            before_date: ISO date string (YYYY-MM-DD)
            after_date: ISO date string (YYYY-MM-DD)
            radius_miles: Analysis radius in miles
            metric: What to measure (NDVI, elevation, backscatter)
            
        Returns:
            {
                "change_pct": float,  # Percentage change
                "increased_area_pct": float,  # Percentage that increased
                "decreased_area_pct": float,  # Percentage that decreased
                "unchanged_area_pct": float,  # Percentage unchanged
                "avg_before": float,
                "avg_after": float,
                "confidence": str
            }
        """
        try:
            logger.info(f" Analyzing temporal change: {before_date} -> {after_date}")
            
            # This is a simplified implementation
            # Real implementation would download rasters for both dates and compute pixel-wise differences
            
            return {
                "error": "Temporal change analysis not yet fully implemented",
                "confidence": "low",
                "note": "Requires pixel-level raster comparison"
            }
            
        except Exception as e:
            logger.error(f" Temporal change analysis failed: {e}")
            return {"error": str(e), "confidence": "low"}
    
    # Helper methods
    
    def _calculate_bbox(self, latitude: float, longitude: float, radius_miles: float) -> List[float]:
        """Calculate bounding box for given radius."""
        import math
        
        lat_delta = radius_miles / 69.0
        lon_delta = radius_miles / (69.0 * math.cos(math.radians(latitude)))
        
        return [
            longitude - lon_delta,  # min_lon
            latitude - lat_delta,   # min_lat
            longitude + lon_delta,  # max_lon
            latitude + lat_delta    # max_lat
        ]
    
    async def _download_raster(
        self,
        collection_id: str,
        bbox: List[float],
        asset_key: str = "data",
        days_back: Optional[int] = None
    ) -> Optional[np.ndarray]:
        """
        Download raster data from STAC collection.
        
        Args:
            collection_id: STAC collection ID
            bbox: Bounding box [min_lon, min_lat, max_lon, max_lat]
            asset_key: Asset key to download (e.g., 'data', 'B08', 'vv')
            days_back: Number of days to look back (None for static collections like DEM)
            
        Returns:
            Numpy array of raster data, or None if download fails
        """
        try:
            # Lazy import to avoid issues if rasterio not available
            import rasterio
            from rasterio.windows import from_bounds
            
            # Build datetime range if needed
            datetime_filter = None
            if days_back:
                end_date = datetime.utcnow()
                start_date = end_date - timedelta(days=days_back)
                datetime_filter = f"{start_date.isoformat()}Z/{end_date.isoformat()}Z"
            
            # Search STAC
            catalog = pystac_client.Client.open(
                self.stac_endpoint,
                modifier=planetary_computer.sign_inplace
            )
            
            search_params = {
                "collections": [collection_id],
                "bbox": bbox,
                "limit": 1
            }
            
            if datetime_filter:
                search_params["datetime"] = datetime_filter
            
            search = catalog.search(**search_params)
            items = list(search.items())
            
            if not items:
                logger.warning(f" No STAC items found for {collection_id}")
                return None
            
            item = items[0]
            
            # Get asset URL
            if asset_key not in item.assets:
                # Try to find alternative asset
                available_assets = list(item.assets.keys())
                logger.warning(f" Asset {asset_key} not found. Available: {available_assets}")
                if available_assets:
                    asset_key = available_assets[0]
                else:
                    return None
            
            asset_url = item.assets[asset_key].href
            signed_url = planetary_computer.sign_url(asset_url)
            
            # Download raster
            with rasterio.open(signed_url) as src:
                # Read window for bbox
                window = from_bounds(*bbox, src.transform)
                data = src.read(1, window=window)
                
                # Replace nodata with NaN
                if src.nodata is not None:
                    data = data.astype(float)
                    data[data == src.nodata] = np.nan
            
            logger.debug(f" Downloaded {collection_id}/{asset_key}: shape={data.shape}")
            return data
            
        except Exception as e:
            logger.error(f" Raster download failed for {collection_id}: {e}")
            return None


# Singleton instance
_tools_instance = None

def get_geospatial_tools() -> GeospatialTools:
    """Get singleton instance of GeospatialTools."""
    global _tools_instance
    if _tools_instance is None:
        _tools_instance = GeospatialTools()
    return _tools_instance
