"""
GEOINT Mobility Agent - Agent 5

This agent provides terrain-based mobility analysis for military operations.
Triggered exclusively via UI (GEOINT toggle + pin drop), not by query detection.

Analysis Components:
- Water Detection: Sentinel-1 SAR (all-weather water body detection)
- Terrain Classification: Sentinel-1 RTC backscatter analysis
- Vegetation Density: Sentinel-2 NDVI calculation
- Elevation/Slope: Copernicus DEM GLO-30 slope analysis
- Active Fires: MODIS Thermal Anomalies
- Directional Analysis: N, S, E, W mobility corridors (5-mile radius)
- Mobility Status: GO / SLOW-GO / NO-GO classifications
"""

from typing import Dict, Any, List, Tuple, Optional
import logging
from datetime import datetime, timedelta
import numpy as np
import aiohttp
import asyncio
# REMOVED: import rasterio - now imported lazily only when needed
# REMOVED: from rasterio.windows import from_bounds - now imported lazily only when needed
import planetary_computer

logger = logging.getLogger(__name__)


class GeointMobilityAgent:
    """
    GEOINT Mobility Analysis Agent
    
    Analyzes terrain for military mobility based on:
    - Water bodies (Sentinel-1 SAR - works through clouds)
    - Terrain roughness (Sentinel-1 RTC backscatter)
    - Vegetation density (Sentinel-2 NDVI)
    - Elevation/slope (Copernicus DEM GLO-30)
    - Active fires (MODIS Thermal Anomalies)
    
    Collections used (all available in Planetary Computer):
    - sentinel-1-grd: Water detection via SAR (10m, all-weather)
    - sentinel-1-rtc: Terrain classification via backscatter
    - sentinel-2-l2a: Vegetation NDVI (10-60m, cloud-filtered)
    - cop-dem-glo-30: Digital Elevation Model (30m, static)
    - modis-14A1-061: Active fire detection (1km, daily)
    """
    
    def __init__(self, stac_endpoint: str = "https://planetarycomputer.microsoft.com/api/stac/v1"):
        """
        Initialize the GEOINT Mobility Agent.
        
        Args:
            stac_endpoint: Planetary Computer STAC API endpoint URL
        """
        self.stac_endpoint = stac_endpoint
        self.name = "geoint_mobility"
        self.radius_miles = 5  # Analysis radius from pin drop point (changed from 50 to 5 miles)
        
        # Mobility thresholds
        self.SLOPE_THRESHOLD_SLOW = 15  # degrees
        self.SLOPE_THRESHOLD_NO_GO = 30  # degrees
        self.WATER_BACKSCATTER_THRESHOLD = -20  # dB for Sentinel-1
        self.VEGETATION_NDVI_DENSE = 0.6  # NDVI > 0.6 = dense vegetation
        self.FIRE_CONFIDENCE_THRESHOLD = 50  # MODIS fire confidence %
        
    async def analyze_mobility(
        self, 
        latitude: float, 
        longitude: float,
        user_context: str = None,
        include_vision_analysis: bool = True
    ) -> Dict[str, Any]:
        """
        Perform comprehensive mobility analysis for a pinned location.
        
        Args:
            latitude: Pin drop latitude
            longitude: Pin drop longitude
            user_context: Optional context from chat (not used for core analysis)
            include_vision_analysis: Whether to include GPT-5 Vision analysis (default True)
            
        Returns:
            Dict containing mobility analysis results with directional assessments
        """
        logger.info(f"🎖️ Starting GEOINT mobility analysis at ({latitude}, {longitude})")
        
        # Calculate analysis bounding box (5-mile radius)
        bbox = self._calculate_analysis_bbox(latitude, longitude)
        
        # Gather terrain data from multiple STAC collections (algorithmic analysis)
        terrain_data = await self._gather_terrain_data(bbox)
        
        # Perform directional mobility analysis (algorithmic)
        mobility_assessment = self._assess_directional_mobility(
            latitude, longitude, terrain_data
        )
        
        # Add GPT-5 Vision analysis if enabled
        vision_analysis = None
        if include_vision_analysis:
            logger.info("🔍 Adding GPT-5 Vision analysis for enhanced mobility assessment...")
            try:
                from geoint.vision_analyzer import get_vision_analyzer
                
                vision_analyzer = get_vision_analyzer()
                
                # Prepare context from algorithmic analysis for vision prompt
                vision_context = {
                    "water_detected": bool(terrain_data.get("water_detection")),
                    "steep_slopes": any(
                        direction["status"] == "NO-GO" and "slope" in str(direction.get("reasons", [])).lower()
                        for direction in mobility_assessment.values()
                    ),
                    "vegetation_dense": bool(terrain_data.get("vegetation_density")),
                    "active_fires": bool(terrain_data.get("active_fires")),
                    "slope_summary": self._get_slope_summary(mobility_assessment)
                }
                
                vision_result = await vision_analyzer.analyze_location_with_vision(
                    latitude=latitude,
                    longitude=longitude,
                    module_type="mobility",
                    radius_miles=self.radius_miles,
                    user_query="Assess terrain mobility and trafficability for ground vehicles",
                    additional_context=vision_context
                )
                
                vision_analysis = vision_result
                logger.info("✅ Vision analysis completed")
                
            except Exception as e:
                logger.error(f"⚠️ Vision analysis failed (continuing with algorithmic analysis): {e}")
                vision_analysis = None
        
        # Generate natural language summary (incorporating both algorithmic + vision)
        nl_summary = self._generate_mobility_summary(
            latitude, longitude, mobility_assessment, user_context, vision_analysis
        )
        
        result = {
            "agent": "geoint_mobility",
            "location": {"latitude": latitude, "longitude": longitude},
            "radius_miles": self.radius_miles,
            "analysis_bbox": bbox,
            "directional_analysis": mobility_assessment,
            "summary": nl_summary,
            "timestamp": datetime.utcnow().isoformat(),
            "data_sources": terrain_data.get("sources", []),
            "collection_status": terrain_data.get("collection_status", {})
        }
        
        # Add vision analysis if available
        if vision_analysis:
            result["vision_analysis"] = {
                "visual_assessment": vision_analysis.get("visual_analysis"),
                "features_identified": vision_analysis.get("features_identified", []),
                "imagery_metadata": vision_analysis.get("imagery_metadata", {}),
                "confidence": vision_analysis.get("confidence", 0.0)
            }
            # Also add vision data sources
            if vision_analysis.get("imagery_metadata", {}).get("source"):
                result["data_sources"].append(f"{vision_analysis['imagery_metadata']['source']} (GPT-5 Vision)")
        
        return result
    
    async def _query_stac_collection(
        self,
        collection: str,
        bbox: List[float],
        datetime_range: Optional[str] = None,
        query_params: Optional[Dict[str, Any]] = None,
        limit: int = 10
    ) -> List[Dict[str, Any]]:
        """
        Query a STAC collection via HTTP API.
        
        Args:
            collection: Collection ID
            bbox: Bounding box [min_lon, min_lat, max_lon, max_lat]
            datetime_range: Optional datetime range (ISO 8601 format)
            query_params: Optional query parameters (e.g., cloud cover filter)
            limit: Maximum number of items to return
            
        Returns:
            List of STAC items
        """
        search_url = f"{self.stac_endpoint}/search"
        
        request_body = {
            "collections": [collection],
            "bbox": bbox,
            "limit": limit
        }
        
        if datetime_range:
            request_body["datetime"] = datetime_range
        
        if query_params:
            request_body["query"] = query_params
        
        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(search_url, json=request_body, timeout=aiohttp.ClientTimeout(total=30)) as response:
                    if response.status == 200:
                        data = await response.json()
                        features = data.get("features", [])
                        logger.debug(f"STAC query for {collection}: {len(features)} items found")
                        return features
                    else:
                        error_text = await response.text()
                        logger.error(f"STAC query failed for {collection}: HTTP {response.status} - {error_text[:200]}")
                        return []
        except asyncio.TimeoutError:
            logger.error(f"STAC query timeout for {collection}")
            return []
        except Exception as e:
            logger.error(f"STAC query error for {collection}: {e}")
            return []
    
    def _calculate_analysis_bbox(
        self, 
        latitude: float, 
        longitude: float
    ) -> List[float]:
        """
        Calculate bounding box for 5-mile radius analysis.
        
        Args:
            latitude: Center point latitude
            longitude: Center point longitude
            
        Returns:
            Bounding box as [min_lon, min_lat, max_lon, max_lat]
        """
        # Approximate: 1 degree latitude ≈ 69 miles
        # 1 degree longitude ≈ 69 * cos(latitude) miles
        import math
        
        lat_delta = self.radius_miles / 69.0
        lon_delta = self.radius_miles / (69.0 * math.cos(math.radians(latitude)))
        
        return [
            longitude - lon_delta,  # min_lon
            latitude - lat_delta,   # min_lat
            longitude + lon_delta,  # max_lon
            latitude + lat_delta    # max_lat
        ]
    
    async def _gather_terrain_data(self, bbox: List[float]) -> Dict[str, Any]:
        """
        Query STAC collections for terrain data.
        
        Collections used (optimized for mobility analysis):
        1. sentinel-1-grd: Water detection via SAR backscatter (all-weather, 10m)
        2. sentinel-1-rtc: Terrain classification via normalized backscatter
        3. sentinel-2-l2a: Vegetation NDVI calculation (10-60m, cloud-filtered)
        4. cop-dem-glo-30: Elevation for slope analysis (30m, static)
        5. modis-14A1-061: Active fire detection (1km, daily composite)
        
        Args:
            bbox: Bounding box [min_lon, min_lat, max_lon, max_lat]
            
        Returns:
            Dictionary with terrain data from each collection
        """
        terrain_data = {
            "sources": [],
            "water_detection": None,
            "terrain_backscatter": None,
            "vegetation_density": None,
            "elevation_profile": None,
            "active_fires": None,
            "collection_status": {}
        }
        
        # Time windows for dynamic collections
        end_date = datetime.utcnow()
        recent_start = end_date - timedelta(days=30)  # Last 30 days
        datetime_range_30d = f"{recent_start.isoformat()}Z/{end_date.isoformat()}Z"
        
        # Query all collections concurrently
        logger.info("📡 Querying 5 STAC collections concurrently...")
        
        results = await asyncio.gather(
            # 1. Sentinel-1 GRD (Water Detection)
            self._query_stac_collection("sentinel-1-grd", bbox, datetime_range_30d, limit=10),
            # 2. Sentinel-1 RTC (Terrain Backscatter)
            self._query_stac_collection("sentinel-1-rtc", bbox, datetime_range_30d, limit=10),
            # 3. Sentinel-2 L2A (Vegetation)
            self._query_stac_collection("sentinel-2-l2a", bbox, datetime_range_30d, 
                                       query_params={"eo:cloud_cover": {"lt": 20}}, limit=10),
            # 4. Copernicus DEM (Elevation - static, no datetime)
            self._query_stac_collection("cop-dem-glo-30", bbox, limit=10),
            # 5. MODIS Fire (Active Fires - daily composite, no datetime filter)
            self._query_stac_collection("modis-14A1-061", bbox, limit=10),
            return_exceptions=True
        )
        
        # Process results
        collection_names = ["sentinel-1-grd", "sentinel-1-rtc", "sentinel-2-l2a", "cop-dem-glo-30", "modis-14A1-061"]
        data_keys = ["water_detection", "terrain_backscatter", "vegetation_density", "elevation_profile", "active_fires"]
        display_names = ["Sentinel-1 GRD (Water)", "Sentinel-1 RTC (Terrain)", "Sentinel-2 L2A (Vegetation)", 
                        "Copernicus DEM (Elevation)", "MODIS Fire Detection"]
        
        for idx, (collection, data_key, display_name, result) in enumerate(zip(collection_names, data_keys, display_names, results)):
            if isinstance(result, Exception):
                logger.error(f"❌ {collection} failed: {result}")
                terrain_data["collection_status"][collection] = f"error: {str(result)}"
            elif result:
                item_count = len(result)
                terrain_data[data_key] = {
                    "items_found": item_count,
                    "collection": collection,
                    "features": result[:3]  # Store first 3 features for analysis
                }
                terrain_data["sources"].append(display_name)
                terrain_data["collection_status"][collection] = "success"
                logger.info(f"✅ {collection}: {item_count} items")
            else:
                logger.warning(f"⚠️ {collection}: No data")
                terrain_data["collection_status"][collection] = "no_data"
        
        # Log summary
        success_count = sum(1 for status in terrain_data["collection_status"].values() if status == "success")
        logger.info(f"📊 Terrain data collection: {success_count}/5 collections successful")
        
        return terrain_data
        """
        Query STAC collections for terrain data.
        
        Collections used (optimized for mobility analysis):
        1. sentinel-1-grd: Water detection via SAR backscatter (all-weather, 10m)
        2. sentinel-1-rtc: Terrain classification via normalized backscatter
        3. sentinel-2-l2a: Vegetation NDVI calculation (10-60m, cloud-filtered)
        4. cop-dem-glo-30: Elevation for slope analysis (30m, static)
        5. modis-14A1-061: Active fire detection (1km, daily composite)
        
        Args:
            bbox: Bounding box [min_lon, min_lat, max_lon, max_lat]
            
        Returns:
            Dictionary with terrain data from each collection
        """
        terrain_data = {
            "sources": [],
            "water_detection": None,
            "terrain_backscatter": None,
            "vegetation_density": None,
            "elevation_profile": None,
            "active_fires": None,
            "collection_status": {}
        }
        
        # Time windows for dynamic collections
        end_date = datetime.utcnow()
        recent_start = end_date - timedelta(days=30)  # Last 30 days
        fire_start = end_date - timedelta(days=7)  # Last 7 days for fires
        
        try:
            # 1. Water Detection: Sentinel-1 GRD (SAR works through clouds)
            logger.info("Querying Sentinel-1 GRD for water detection...")
            try:
                sentinel1_items = list(self.stac.search(
                    collections=["sentinel-1-grd"],
                    bbox=bbox,
                    datetime=f"{recent_start.isoformat()}Z/{end_date.isoformat()}Z",
                    limit=10
                ).items())
                
                if sentinel1_items:
                    terrain_data["water_detection"] = {
                        "items_found": len(sentinel1_items),
                        "collection": "sentinel-1-grd",
                        "resolution": "10m",
                        "assets": ["vv", "vh"],
                        "method": "SAR backscatter analysis"
                    }
                    terrain_data["sources"].append("Sentinel-1 GRD (Water Detection)")
                    terrain_data["collection_status"]["sentinel-1-grd"] = "success"
                    logger.info(f"✅ Sentinel-1 GRD: {len(sentinel1_items)} items found")
                else:
                    logger.warning("⚠️ Sentinel-1 GRD: No items found")
                    terrain_data["collection_status"]["sentinel-1-grd"] = "no_data"
            except Exception as e:
                logger.error(f"❌ Sentinel-1 GRD query failed: {e}")
                terrain_data["collection_status"]["sentinel-1-grd"] = f"error: {str(e)}"
            
            # 2. Terrain Classification: Sentinel-1 RTC (Radiometrically Terrain Corrected)
            logger.info("Querying Sentinel-1 RTC for terrain backscatter...")
            try:
                sentinel1_rtc_items = list(self.stac.search(
                    collections=["sentinel-1-rtc"],
                    bbox=bbox,
                    datetime=f"{recent_start.isoformat()}Z/{end_date.isoformat()}Z",
                    limit=10
                ).items())
                
                if sentinel1_rtc_items:
                    terrain_data["terrain_backscatter"] = {
                        "items_found": len(sentinel1_rtc_items),
                        "collection": "sentinel-1-rtc",
                        "resolution": "10-20m",
                        "assets": ["vh", "vv"],
                        "method": "Normalized radar backscatter"
                    }
                    terrain_data["sources"].append("Sentinel-1 RTC (Terrain Classification)")
                    terrain_data["collection_status"]["sentinel-1-rtc"] = "success"
                    logger.info(f"✅ Sentinel-1 RTC: {len(sentinel1_rtc_items)} items found")
                else:
                    logger.warning("⚠️ Sentinel-1 RTC: No items found")
                    terrain_data["collection_status"]["sentinel-1-rtc"] = "no_data"
            except Exception as e:
                logger.error(f"❌ Sentinel-1 RTC query failed: {e}")
                terrain_data["collection_status"]["sentinel-1-rtc"] = f"error: {str(e)}"
            
            # 3. Vegetation: Sentinel-2 L2A for NDVI calculation (cloud-filtered)
            logger.info("Querying Sentinel-2 L2A for vegetation NDVI...")
            try:
                sentinel2_items = list(self.stac.search(
                    collections=["sentinel-2-l2a"],
                    bbox=bbox,
                    datetime=f"{recent_start.isoformat()}Z/{end_date.isoformat()}Z",
                    query={"eo:cloud_cover": {"lt": 20}},
                    limit=10
                ).items())
                
                if sentinel2_items:
                    terrain_data["vegetation_density"] = {
                        "items_found": len(sentinel2_items),
                        "collection": "sentinel-2-l2a",
                        "resolution": "10m (RGB/NIR), 20m (RE/SWIR)",
                        "cloud_cover_threshold": 20,
                        "bands_for_ndvi": ["B04 (Red)", "B08 (NIR)"],
                        "method": "NDVI = (NIR - Red) / (NIR + Red)"
                    }
                    terrain_data["sources"].append("Sentinel-2 L2A (Vegetation/NDVI)")
                    terrain_data["collection_status"]["sentinel-2-l2a"] = "success"
                    logger.info(f"✅ Sentinel-2 L2A: {len(sentinel2_items)} items found")
                else:
                    logger.warning("⚠️ Sentinel-2 L2A: No items found")
                    terrain_data["collection_status"]["sentinel-2-l2a"] = "no_data"
            except Exception as e:
                logger.error(f"❌ Sentinel-2 L2A query failed: {e}")
                terrain_data["collection_status"]["sentinel-2-l2a"] = f"error: {str(e)}"
            
            # 4. Elevation: Copernicus DEM GLO-30 (static elevation data)
            logger.info("Querying Copernicus DEM GLO-30 for elevation...")
            try:
                dem_items = list(self.stac.search(
                    collections=["cop-dem-glo-30"],
                    bbox=bbox,
                    limit=10
                ).items())
                
                if dem_items:
                    terrain_data["elevation_profile"] = {
                        "items_found": len(dem_items),
                        "collection": "cop-dem-glo-30",
                        "resolution": "30m",
                        "vertical_accuracy": "±4m",
                        "method": "Slope calculation from elevation gradient"
                    }
                    terrain_data["sources"].append("Copernicus DEM GLO-30 (Elevation/Slope)")
                    terrain_data["collection_status"]["cop-dem-glo-30"] = "success"
                    logger.info(f"✅ Copernicus DEM: {len(dem_items)} items found")
                else:
                    logger.warning("⚠️ Copernicus DEM: No items found")
                    terrain_data["collection_status"]["cop-dem-glo-30"] = "no_data"
            except Exception as e:
                logger.error(f"❌ Copernicus DEM query failed: {e}")
                terrain_data["collection_status"]["cop-dem-glo-30"] = f"error: {str(e)}"
            
            # 5. Active Fires: MODIS Thermal Anomalies (daily composite)
            logger.info("Querying MODIS 14A1-061 for active fires...")
            try:
                # MODIS 14A1-061 is a daily composite - use sortby instead of datetime
                fire_items = list(self.stac.search(
                    collections=["modis-14A1-061"],
                    bbox=bbox,
                    sortby=[{"field": "datetime", "direction": "desc"}],
                    limit=10
                ).items())
                
                if fire_items:
                    terrain_data["active_fires"] = {
                        "items_found": len(fire_items),
                        "collection": "modis-14A1-061",
                        "resolution": "1km",
                        "assets": ["FireMask", "MaxFRP", "QA"],
                        "method": "Thermal anomaly detection"
                    }
                    terrain_data["sources"].append("MODIS Active Fire Detection")
                    terrain_data["collection_status"]["modis-14A1-061"] = "success"
                    logger.info(f"✅ MODIS Fire: {len(fire_items)} items found")
                else:
                    logger.warning("⚠️ MODIS Fire: No items found (no active fires)")
                    terrain_data["collection_status"]["modis-14A1-061"] = "no_data"
            except Exception as e:
                logger.error(f"❌ MODIS Fire query failed: {e}")
                terrain_data["collection_status"]["modis-14A1-061"] = f"error: {str(e)}"
                
        except Exception as e:
            logger.error(f"Critical error gathering terrain data: {e}")
            terrain_data["critical_error"] = str(e)
        
        # Log summary
        success_count = sum(1 for status in terrain_data["collection_status"].values() if status == "success")
        total_collections = len(terrain_data["collection_status"])
        logger.info(f"📊 Terrain data collection complete: {success_count}/{total_collections} collections successful")
        
        return terrain_data
    
    async def _read_cog_window(
        self,
        asset_url: str,
        bbox: List[float],
        band: int = 1
    ) -> Optional[np.ndarray]:
        """
        Read pixels from Cloud-Optimized GeoTIFF for a bounding box.
        
        Args:
            asset_url: COG asset URL from STAC item
            bbox: Bounding box [min_lon, min_lat, max_lon, max_lat]
            band: Band number to read (default 1)
            
        Returns:
            Numpy array of pixel values, or None if read fails
        """
        try:
            # Lazy import rasterio only when actually needed
            import rasterio
            from rasterio.windows import from_bounds
            
            # Sign the URL for Azure Blob Storage access
            signed_url = planetary_computer.sign_url(asset_url)
            
            with rasterio.open(signed_url) as src:
                # Convert bbox to pixel window
                window = from_bounds(*bbox, src.transform)
                
                # Read data for the window
                data = src.read(band, window=window)
                
                # Replace nodata values with NaN
                if src.nodata is not None:
                    data = data.astype(float)
                    data[data == src.nodata] = np.nan
                
                logger.debug(f"Read COG window: shape={data.shape}, dtype={data.dtype}")
                return data
                
        except Exception as e:
            logger.error(f"Failed to read COG window from {asset_url[:100]}: {e}")
            return None
    
    def _analyze_elevation(self, elevation_pixels: np.ndarray) -> Dict[str, Any]:
        """
        Analyze elevation data to calculate terrain slopes.
        
        Args:
            elevation_pixels: 2D numpy array of elevation values in meters
            
        Returns:
            Dictionary with slope analysis results
        """
        try:
            # Remove NaN values for statistics
            valid_pixels = elevation_pixels[~np.isnan(elevation_pixels)]
            
            if len(valid_pixels) == 0:
                return {"status": "GO", "reason": "No elevation data available", "confidence": "low"}
            
            # Calculate slopes using gradient (30m DEM resolution)
            dy, dx = np.gradient(elevation_pixels, 30)  # 30 meters per pixel
            slope_radians = np.arctan(np.sqrt(dx**2 + dy**2))
            slope_degrees = np.degrees(slope_radians)
            
            # Remove NaN slopes
            valid_slopes = slope_degrees[~np.isnan(slope_degrees)]
            
            if len(valid_slopes) == 0:
                return {"status": "GO", "reason": "Unable to calculate slopes", "confidence": "low"}
            
            # Calculate slope statistics
            total_pixels = len(valid_slopes)
            gentle_pct = (np.sum(valid_slopes < 15) / total_pixels) * 100
            moderate_pct = (np.sum((valid_slopes >= 15) & (valid_slopes < 30)) / total_pixels) * 100
            steep_pct = (np.sum(valid_slopes >= 30) / total_pixels) * 100
            
            max_slope = np.max(valid_slopes)
            avg_slope = np.mean(valid_slopes)
            
            # Classify mobility based on slope distribution
            if steep_pct > 30:
                status = "NO-GO"
                reason = f"⛰️ Steep terrain: {steep_pct:.1f}% > 30° slopes (max {max_slope:.1f}°)"
            elif moderate_pct + steep_pct > 50:
                status = "SLOW-GO"
                reason = f"⛰️ Moderate terrain: {moderate_pct:.1f}% slopes 15-30° (avg {avg_slope:.1f}°)"
            else:
                status = "GO"
                reason = f"✅ Gentle terrain: {gentle_pct:.1f}% < 15° slopes (avg {avg_slope:.1f}°)"
            
            return {
                "status": status,
                "reason": reason,
                "confidence": "high",
                "metrics": {
                    "avg_slope": round(avg_slope, 1),
                    "max_slope": round(max_slope, 1),
                    "gentle_pct": round(gentle_pct, 1),
                    "moderate_pct": round(moderate_pct, 1),
                    "steep_pct": round(steep_pct, 1)
                }
            }
            
        except Exception as e:
            logger.error(f"Elevation analysis failed: {e}")
            return {"status": "GO", "reason": "Elevation analysis error", "confidence": "low"}
    
    def _analyze_water(self, sar_vv_pixels: np.ndarray) -> Dict[str, Any]:
        """
        Analyze SAR backscatter to detect water bodies.
        
        Args:
            sar_vv_pixels: 2D numpy array of SAR VV backscatter values in dB
            
        Returns:
            Dictionary with water detection results
        """
        try:
            # Remove NaN values
            valid_pixels = sar_vv_pixels[~np.isnan(sar_vv_pixels)]
            
            if len(valid_pixels) == 0:
                return {"status": "GO", "reason": "No SAR data available", "confidence": "low"}
            
            # Water detection: SAR backscatter < -20 dB indicates smooth water surfaces
            water_mask = valid_pixels < self.WATER_BACKSCATTER_THRESHOLD
            total_pixels = len(valid_pixels)
            water_coverage_pct = (np.sum(water_mask) / total_pixels) * 100
            
            # Classify mobility based on water coverage
            if water_coverage_pct > 30:
                status = "NO-GO"
                reason = f"💧 Major water bodies: {water_coverage_pct:.1f}% coverage"
            elif water_coverage_pct > 10:
                status = "SLOW-GO"
                reason = f"💧 Moderate water coverage: {water_coverage_pct:.1f}%"
            else:
                status = "GO"
                reason = f"✅ Minimal water: {water_coverage_pct:.1f}% coverage"
            
            return {
                "status": status,
                "reason": reason,
                "confidence": "high",
                "metrics": {
                    "water_coverage_pct": round(water_coverage_pct, 1),
                    "threshold_db": self.WATER_BACKSCATTER_THRESHOLD
                }
            }
            
        except Exception as e:
            logger.error(f"Water analysis failed: {e}")
            return {"status": "GO", "reason": "Water analysis error", "confidence": "low"}
    
    def _analyze_fire(self, fire_mask_pixels: np.ndarray) -> Dict[str, Any]:
        """
        Analyze MODIS FireMask to detect active fires.
        
        Args:
            fire_mask_pixels: 2D numpy array of FireMask values (0-9)
            
        Returns:
            Dictionary with fire detection results
        """
        try:
            # Remove NaN values
            valid_pixels = fire_mask_pixels[~np.isnan(fire_mask_pixels)]
            
            if len(valid_pixels) == 0:
                return {"status": "GO", "reason": "No fire data available", "confidence": "low"}
            
            # FireMask values: 7 = low confidence, 8 = nominal, 9 = high confidence
            high_conf_fires = np.sum(valid_pixels == 9)
            nominal_fires = np.sum(valid_pixels == 8)
            low_conf_fires = np.sum(valid_pixels == 7)
            total_fires = high_conf_fires + nominal_fires + low_conf_fires
            
            # Safety-first: ANY high-confidence fire = NO-GO
            if high_conf_fires > 0:
                status = "NO-GO"
                reason = f"🔥 Active fires detected: {high_conf_fires} high-confidence fire pixels"
            elif total_fires > 5:
                status = "SLOW-GO"
                reason = f"🔥 Multiple fire detections: {total_fires} pixels (low/nominal confidence)"
            elif total_fires > 0:
                status = "SLOW-GO"
                reason = f"⚠️ Potential fires: {total_fires} low-confidence detections"
            else:
                status = "GO"
                reason = f"✅ No active fires detected"
            
            return {
                "status": status,
                "reason": reason,
                "confidence": "high" if high_conf_fires > 0 else "medium",
                "metrics": {
                    "high_conf_fires": int(high_conf_fires),
                    "nominal_fires": int(nominal_fires),
                    "low_conf_fires": int(low_conf_fires),
                    "total_fires": int(total_fires)
                }
            }
            
        except Exception as e:
            logger.error(f"Fire analysis failed: {e}")
            return {"status": "GO", "reason": "Fire analysis error", "confidence": "low"}
    
    def _analyze_vegetation(self, red_pixels: np.ndarray, nir_pixels: np.ndarray) -> Dict[str, Any]:
        """
        Calculate NDVI from Sentinel-2 to assess vegetation density.
        
        Args:
            red_pixels: 2D numpy array of Red band (B04) reflectance
            nir_pixels: 2D numpy array of NIR band (B08) reflectance
            
        Returns:
            Dictionary with vegetation analysis results
        """
        try:
            # Calculate NDVI: (NIR - Red) / (NIR + Red)
            # Add small epsilon to avoid division by zero
            ndvi = (nir_pixels - red_pixels) / (nir_pixels + red_pixels + 1e-8)
            
            # Remove NaN and invalid values (valid NDVI range: -1 to 1)
            valid_ndvi = ndvi[(~np.isnan(ndvi)) & (ndvi >= -1) & (ndvi <= 1)]
            
            if len(valid_ndvi) == 0:
                return {"status": "GO", "reason": "No vegetation data available", "confidence": "low"}
            
            # Calculate vegetation density statistics
            total_pixels = len(valid_ndvi)
            sparse_pct = (np.sum(valid_ndvi < 0.5) / total_pixels) * 100  # Sparse/bare ground
            moderate_pct = (np.sum((valid_ndvi >= 0.5) & (valid_ndvi < 0.7)) / total_pixels) * 100
            dense_pct = (np.sum(valid_ndvi >= 0.7) / total_pixels) * 100  # Dense vegetation
            
            avg_ndvi = np.mean(valid_ndvi)
            
            # Classify mobility based on vegetation density
            if dense_pct > 50:
                status = "NO-GO"
                reason = f"🌲 Dense vegetation: {dense_pct:.1f}% (NDVI > 0.7)"
            elif moderate_pct + dense_pct > 60:
                status = "SLOW-GO"
                reason = f"🌳 Moderate vegetation: {moderate_pct:.1f}% (NDVI 0.5-0.7, avg {avg_ndvi:.2f})"
            else:
                status = "GO"
                reason = f"✅ Light vegetation: {sparse_pct:.1f}% sparse (avg NDVI {avg_ndvi:.2f})"
            
            return {
                "status": status,
                "reason": reason,
                "confidence": "high",
                "metrics": {
                    "avg_ndvi": round(avg_ndvi, 2),
                    "sparse_pct": round(sparse_pct, 1),
                    "moderate_pct": round(moderate_pct, 1),
                    "dense_pct": round(dense_pct, 1)
                }
            }
            
        except Exception as e:
            logger.error(f"Vegetation analysis failed: {e}")
            return {"status": "GO", "reason": "Vegetation analysis error", "confidence": "low"}
    
    def _assess_directional_mobility(
        self,
        latitude: float,
        longitude: float,
        terrain_data: Dict[str, Any]
    ) -> Dict[str, Dict[str, Any]]:
        """
        Assess mobility in four cardinal directions (N, S, E, W).
        
        Args:
            latitude: Center point latitude
            longitude: Center point longitude
            terrain_data: Terrain data from STAC collections
            
        Returns:
            Dictionary with mobility status for each direction
        """
        # Check if we have ANY successful data sources
        success_count = sum(1 for status in terrain_data.get("collection_status", {}).values() if status == "success")
        total_collections = len(terrain_data.get("collection_status", {}))
        
        if success_count == 0:
            logger.error(f"❌ NO DATA SOURCES AVAILABLE: 0/{total_collections} collections succeeded")
            # Return "no data" assessment for all directions
            no_data_response = {
                "status": "UNKNOWN",
                "factors": ["❌ No satellite data available for this location"],
                "confidence": "none",
                "data_sources_used": ["No data sources available"],
                "metrics": {},
                "note": "Unable to perform mobility analysis - all data sources failed"
            }
            return {
                "north": {**no_data_response, "direction": "North", "cardinal": "N"},
                "south": {**no_data_response, "direction": "South", "cardinal": "S"},
                "east": {**no_data_response, "direction": "East", "cardinal": "E"},
                "west": {**no_data_response, "direction": "West", "cardinal": "W"}
            }
        
        logger.info(f"📊 Data sources available: {success_count}/{total_collections} successful")
        
        directions = {
            "north": self._analyze_direction("North", latitude, longitude, terrain_data, "N"),
            "south": self._analyze_direction("South", latitude, longitude, terrain_data, "S"),
            "east": self._analyze_direction("East", latitude, longitude, terrain_data, "E"),
            "west": self._analyze_direction("West", latitude, longitude, terrain_data, "W")
        }
        
        return directions
    
    def _analyze_direction(
        self,
        direction_name: str,
        latitude: float,
        longitude: float,
        terrain_data: Dict[str, Any],
        cardinal: str
    ) -> Dict[str, Any]:
        """
        Analyze mobility for a specific direction using pixel-based raster analysis.
        
        Mobility Classification Logic (Priority Order):
        1. FIRE: Any high-confidence fire → NO-GO (safety hazard)
        2. WATER: SAR backscatter analysis → coverage thresholds
        3. ELEVATION: Slope calculation from DEM → gradient thresholds
        4. VEGETATION: NDVI calculation → density thresholds
        
        Args:
            direction_name: Human-readable direction (e.g., "North")
            latitude: Center latitude
            longitude: Center longitude
            terrain_data: Terrain data dictionary from STAC collections
            cardinal: Cardinal direction code (N/S/E/W)
            
        Returns:
            Mobility assessment with pixel-based analysis results
        """
        status = "GO"  # Default to GO
        factors = []
        confidence = "medium"
        data_used = []
        metrics = {}
        
        # Calculate directional bounding box (sector from center point)
        direction_bbox = self._calculate_directional_bbox(latitude, longitude, cardinal)
        
        logger.info(f"🧭 Analyzing {direction_name} direction with pixel-based raster analysis...")
        
        # Priority 1: Active Fire Detection (IMMEDIATE NO-GO)
        fire_analysis = None
        if terrain_data.get("active_fires") and terrain_data["active_fires"].get("features"):
            try:
                # Get first available fire item
                fire_item = terrain_data["active_fires"]["features"][0]
                fire_mask_url = fire_item.get("assets", {}).get("FireMask", {}).get("href")
                
                if fire_mask_url:
                    logger.info("🔥 Reading MODIS FireMask pixels...")
                    fire_pixels = asyncio.run(self._read_cog_window(fire_mask_url, direction_bbox, band=1))
                    
                    if fire_pixels is not None:
                        fire_analysis = self._analyze_fire(fire_pixels)
                        status = fire_analysis["status"]
                        factors.append(fire_analysis["reason"])
                        confidence = fire_analysis["confidence"]
                        data_used.append("MODIS Fire (pixel analysis)")
                        metrics["fire"] = fire_analysis.get("metrics", {})
            except Exception as e:
                logger.error(f"Fire analysis failed: {e}")
        
        # Priority 2: Water Detection (Sentinel-1 SAR VV backscatter)
        water_analysis = None
        if status != "NO-GO" and terrain_data.get("water_detection") and terrain_data["water_detection"].get("features"):
            try:
                # Get first available SAR item
                sar_item = terrain_data["water_detection"]["features"][0]
                vv_asset_url = sar_item.get("assets", {}).get("vv", {}).get("href")
                
                if vv_asset_url:
                    logger.info("💧 Reading Sentinel-1 SAR VV backscatter pixels...")
                    sar_pixels = asyncio.run(self._read_cog_window(vv_asset_url, direction_bbox, band=1))
                    
                    if sar_pixels is not None:
                        water_analysis = self._analyze_water(sar_pixels)
                        
                        # Update status if water is worse than current
                        if water_analysis["status"] == "NO-GO":
                            status = "NO-GO"
                        elif water_analysis["status"] == "SLOW-GO" and status == "GO":
                            status = "SLOW-GO"
                        
                        factors.append(water_analysis["reason"])
                        if water_analysis["confidence"] == "high":
                            confidence = "high"
                        data_used.append("Sentinel-1 SAR (pixel analysis)")
                        metrics["water"] = water_analysis.get("metrics", {})
            except Exception as e:
                logger.error(f"Water analysis failed: {e}")
        
        # Priority 3: Elevation/Slope Analysis (Copernicus DEM)
        elevation_analysis = None
        if status == "GO" and terrain_data.get("elevation_profile") and terrain_data["elevation_profile"].get("features"):
            try:
                # Get first available DEM tile
                dem_item = terrain_data["elevation_profile"]["features"][0]
                dem_asset_url = dem_item.get("assets", {}).get("data", {}).get("href")
                
                if dem_asset_url:
                    logger.info("⛰️ Reading Copernicus DEM elevation pixels...")
                    dem_pixels = asyncio.run(self._read_cog_window(dem_asset_url, direction_bbox, band=1))
                    
                    if dem_pixels is not None:
                        elevation_analysis = self._analyze_elevation(dem_pixels)
                        
                        # Update status if elevation is worse than current
                        if elevation_analysis["status"] == "NO-GO":
                            status = "NO-GO"
                        elif elevation_analysis["status"] == "SLOW-GO" and status == "GO":
                            status = "SLOW-GO"
                        
                        factors.append(elevation_analysis["reason"])
                        if elevation_analysis["confidence"] == "high":
                            confidence = "high"
                        data_used.append("Copernicus DEM (pixel analysis)")
                        metrics["elevation"] = elevation_analysis.get("metrics", {})
            except Exception as e:
                logger.error(f"Elevation analysis failed: {e}")
        
        # Priority 4: Vegetation Density (Sentinel-2 NDVI)
        vegetation_analysis = None
        if status == "GO" and terrain_data.get("vegetation_density") and terrain_data["vegetation_density"].get("features"):
            try:
                # Get first available Sentinel-2 item with low cloud cover
                s2_item = terrain_data["vegetation_density"]["features"][0]
                red_asset_url = s2_item.get("assets", {}).get("B04", {}).get("href")  # Red band
                nir_asset_url = s2_item.get("assets", {}).get("B08", {}).get("href")  # NIR band
                
                if red_asset_url and nir_asset_url:
                    logger.info("🌳 Reading Sentinel-2 Red/NIR pixels for NDVI...")
                    red_pixels = asyncio.run(self._read_cog_window(red_asset_url, direction_bbox, band=1))
                    nir_pixels = asyncio.run(self._read_cog_window(nir_asset_url, direction_bbox, band=1))
                    
                    if red_pixels is not None and nir_pixels is not None:
                        vegetation_analysis = self._analyze_vegetation(red_pixels, nir_pixels)
                        
                        # Update status if vegetation is worse than current
                        if vegetation_analysis["status"] == "NO-GO":
                            status = "NO-GO"
                        elif vegetation_analysis["status"] == "SLOW-GO" and status == "GO":
                            status = "SLOW-GO"
                        
                        factors.append(vegetation_analysis["reason"])
                        if vegetation_analysis["confidence"] == "high":
                            confidence = "high"
                        data_used.append("Sentinel-2 NDVI (pixel analysis)")
                        metrics["vegetation"] = vegetation_analysis.get("metrics", {})
            except Exception as e:
                logger.error(f"Vegetation analysis failed: {e}")
        
        # If no analysis was successful, fall back to GO with low confidence
        if not factors:
            factors.append("✅ No major obstructions detected - clear terrain")
            confidence = "low"
            data_used.append("No pixel-based analysis available")
        
        return {
            "direction": direction_name,
            "cardinal": cardinal,
            "status": status,
            "factors": factors,
            "confidence": confidence,
            "data_sources_used": data_used if data_used else ["No detailed data available"],
            "metrics": metrics,
            "note": "Analysis based on pixel-level raster processing of satellite imagery"
        }
    
    def _calculate_directional_bbox(
        self,
        latitude: float,
        longitude: float,
        cardinal: str
    ) -> List[float]:
        """
        Calculate bounding box for a specific cardinal direction sector.
        
        Args:
            latitude: Center point latitude
            longitude: Center point longitude
            cardinal: Cardinal direction (N/S/E/W)
            
        Returns:
            Bounding box for the directional sector [min_lon, min_lat, max_lon, max_lat]
        """
        import math
        
        # Use half radius for directional sector (25 miles)
        sector_radius = self.radius_miles / 2.0
        
        lat_delta = sector_radius / 69.0
        lon_delta = sector_radius / (69.0 * math.cos(math.radians(latitude)))
        
        if cardinal == "N":
            # North sector: from center to north
            return [
                longitude - lon_delta,
                latitude,
                longitude + lon_delta,
                latitude + lat_delta
            ]
        elif cardinal == "S":
            # South sector: from center to south
            return [
                longitude - lon_delta,
                latitude - lat_delta,
                longitude + lon_delta,
                latitude
            ]
        elif cardinal == "E":
            # East sector: from center to east
            return [
                longitude,
                latitude - lat_delta,
                longitude + lon_delta,
                latitude + lat_delta
            ]
        else:  # W
            # West sector: from center to west
            return [
                longitude - lon_delta,
                latitude - lat_delta,
                longitude,
                latitude + lat_delta
            ]
    
    def _generate_mobility_summary(
        self,
        latitude: float,
        longitude: float,
        mobility_assessment: Dict[str, Dict[str, Any]],
        user_context: str = None,
        vision_analysis: Optional[Dict[str, Any]] = None
    ) -> str:
        """
        Generate natural language summary of mobility analysis.
        
        Args:
            latitude: Pin location latitude
            longitude: Pin location longitude
            mobility_assessment: Directional mobility analysis results
            user_context: Optional user context from chat
            vision_analysis: Optional GPT-5 Vision analysis results
            
        Returns:
            Natural language summary string (Markdown formatted)
        """
        try:
            # Check if all directions are UNKNOWN (no data available)
            unknown_count = sum(1 for a in mobility_assessment.values() if a.get("status") == "UNKNOWN")
            
            if unknown_count == 4:
                # ALL data sources failed - return informative error message
                return (
                    f"## 🎖️ GEOINT Mobility Analysis\n\n"
                    f"**Location:** {latitude:.4f}°N, {longitude:.4f}°E\n"
                    f"**Analysis Radius:** {self.radius_miles} miles\n\n"
                    f"### ❌ Unable to Perform Mobility Analysis\n\n"
                    f"**Reason:** No satellite data available for this location.\n\n"
                    f"**Attempted Data Sources:**\n"
                    f"- **Sentinel-1 GRD/RTC** - All-weather water & terrain detection (SAR)\n"
                    f"- **Sentinel-2 L2A** - Vegetation density analysis (optical)\n"
                    f"- **Copernicus DEM GLO-30** - Elevation & slope data\n"
                    f"- **MODIS 14A1-061** - Active fire detection\n\n"
                    f"**Possible Reasons:**\n"
                    f"- Location may be outside satellite coverage area\n"
                    f"- Data may not yet be available for recent acquisitions\n"
                    f"- Temporary service unavailability\n\n"
                    f"**Recommendation:** Try a different location or check back later when more data becomes available."
                )
            
            # Build structured summary
            summary_parts = [
                f"## 🎖️ GEOINT Mobility Analysis",
                f"**Location:** {latitude:.4f}°N, {longitude:.4f}°E",
                f"**Analysis Radius:** {self.radius_miles} miles\n",
                f"### Directional Mobility Assessment:\n"
            ]
            
            # Count statuses for overview
            go_count = sum(1 for a in mobility_assessment.values() if a.get("status") == "GO")
            slow_go_count = sum(1 for a in mobility_assessment.values() if a.get("status") == "SLOW-GO")
            no_go_count = sum(1 for a in mobility_assessment.values() if a.get("status") == "NO-GO")
            unknown_count_partial = sum(1 for a in mobility_assessment.values() if a.get("status") == "UNKNOWN")
            
            # Add each direction with detailed factors
            for direction_key in ["north", "south", "east", "west"]:
                if direction_key not in mobility_assessment:
                    continue
                    
                assessment = mobility_assessment[direction_key]
                direction = assessment["direction"]
                status = assessment.get("status", "UNKNOWN")
                factors = assessment.get("factors", [])
                confidence = assessment.get("confidence", "medium")
                
                # Add emoji indicators
                if status == "GO":
                    emoji = "✅"
                elif status == "SLOW-GO":
                    emoji = "⚠️"
                elif status == "NO-GO":
                    emoji = "🛑"
                else:  # UNKNOWN
                    emoji = "❓"
                
                confidence_emoji = "🔴" if confidence == "low" or confidence == "none" else "🟡" if confidence == "medium" else "🟢"
                
                summary_parts.append(
                    f"**{emoji} {direction} ({status})** {confidence_emoji}"
                )
                
                # Add factors as sub-bullets
                for factor in factors:
                    summary_parts.append(f"  - {factor}")
                
                summary_parts.append("")  # Blank line between directions
            
            # Add overall assessment summary
            summary_parts.append(f"### Overall Assessment:")
            summary_parts.append(f"- **✅ GO Directions:** {go_count}/4")
            summary_parts.append(f"- **⚠️ SLOW-GO Directions:** {slow_go_count}/4")
            summary_parts.append(f"- **🛑 NO-GO Directions:** {no_go_count}/4")
            if unknown_count_partial > 0:
                summary_parts.append(f"- **❓ UNKNOWN (No Data):** {unknown_count_partial}/4")
            summary_parts.append("")
            
            # Add data sources used with availability status
            summary_parts.append(f"### Satellite Data Sources:")
            
            # Get collection status from any direction's analysis
            first_direction = list(mobility_assessment.values())[0]
            data_sources_used = first_direction.get("data_sources_used", [])
            
            # Show which data sources were actually used
            if "No data sources available" not in str(data_sources_used):
                available_sources = []
                all_sources = {
                    "Sentinel-1 SAR": "All-weather water & terrain detection (10-20m)",
                    "Sentinel-2 NDVI": "Vegetation density analysis (10-60m optical)",
                    "Copernicus DEM": "Elevation & slope analysis (30m)",
                    "MODIS Fire": "Active fire detection (1km daily)"
                }
                
                # Check which sources were used
                for source_key, description in all_sources.items():
                    if any(source_key.lower() in str(ds).lower() for ds in data_sources_used):
                        summary_parts.append(f"- ✅ **{source_key}** - {description}")
                        available_sources.append(source_key)
                    else:
                        summary_parts.append(f"- ❌ **{source_key}** - Not available for this location")
                
                if len(available_sources) < 4:
                    summary_parts.append(f"\n⚠️ **Note:** Analysis performed with partial data ({len(available_sources)}/4 sources available)")
            else:
                summary_parts.append("- **Sentinel-1 GRD/RTC** - All-weather water & terrain detection (10-20m SAR)")
                summary_parts.append("- **Sentinel-2 L2A** - Vegetation density via NDVI (10-60m optical)")
                summary_parts.append("- **Copernicus DEM GLO-30** - Elevation & slope analysis (30m)")
                summary_parts.append("- **MODIS 14A1-061** - Active fire detection (1km daily)")
            
            summary_parts.append("")
            
            # Add methodology note
            summary_parts.append(f"### Methodology:")
            summary_parts.append(f"✅ **Pixel-Based Raster Analysis** - Direct processing of Cloud-Optimized GeoTIFFs (COGs)")
            summary_parts.append(f"- **Fire Detection:** MODIS FireMask pixel counting (values 7/8/9 = fire detections)")
            summary_parts.append(f"- **Water Detection:** SAR backscatter threshold analysis (< -20 dB = water)")
            summary_parts.append(f"- **Slope Analysis:** DEM gradient calculation (30m resolution)")
            summary_parts.append(f"- **Vegetation:** NDVI calculation from Red/NIR bands (NDVI > 0.7 = dense)")
            summary_parts.append(f"\nConfidence: 🟢 High = pixel analysis | 🟡 Medium = partial data | 🔴 Low = no data")
            
            # Add GPT-5 Vision Analysis if available
            if vision_analysis and vision_analysis.get("visual_analysis"):
                summary_parts.append("")
                summary_parts.append(f"### 🔍 GPT-5 Visual Intelligence Assessment:")
                summary_parts.append("")
                summary_parts.append(vision_analysis["visual_analysis"])
                
                if vision_analysis.get("features_identified"):
                    summary_parts.append("")
                    summary_parts.append(f"**Visual Features Identified:** {', '.join(vision_analysis['features_identified'])}")
                
                if vision_analysis.get("imagery_metadata"):
                    meta = vision_analysis["imagery_metadata"]
                    summary_parts.append("")
                    summary_parts.append(f"**Imagery:** {meta.get('source', 'Unknown')} ({meta.get('date', 'Unknown')[:10]}, {meta.get('resolution', 'Unknown')})")
            
            return "\n".join(summary_parts)
            
        except Exception as e:
            logger.error(f"Error generating mobility summary: {e}")
            return (
                f"## 🎖️ GEOINT Mobility Analysis\n\n"
                f"**Location:** {latitude:.4f}°, {longitude:.4f}°\n"
                f"**Radius:** {self.radius_miles} miles\n\n"
                f"Mobility analysis completed for location. Analyzed N/S/E/W directions using "
                f"Sentinel-1 SAR, Sentinel-2 optical, Copernicus DEM, and MODIS fire data."
            )
    
    def _get_slope_summary(self, mobility_assessment: Dict[str, Dict[str, Any]]) -> str:
        """Generate a brief slope summary for vision context."""
        steep_directions = []
        for direction, assessment in mobility_assessment.items():
            if assessment.get("status") == "NO-GO":
                reasons = assessment.get("reasons", [])
                if any("slope" in str(r).lower() for r in reasons):
                    steep_directions.append(direction)
        
        if steep_directions:
            return f"Steep slopes detected in {', '.join(steep_directions)} direction(s)"
        return "No significant steep slopes detected"
