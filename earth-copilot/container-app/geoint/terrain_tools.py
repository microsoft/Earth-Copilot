"""
Terrain Analysis Tools for Semantic Kernel Agent

These are the tools the terrain agent can call to perform geospatial analysis.
Each tool is a kernel function that can be invoked by the agent during reasoning.
"""

import logging
import os
from typing import Annotated, Dict, Any, Optional, List
import numpy as np
from semantic_kernel.functions import kernel_function

logger = logging.getLogger(__name__)


class TerrainAnalysisTools:
    """
    Terrain analysis tools that can be invoked by Semantic Kernel agents.
    Each method decorated with @kernel_function becomes a callable tool.
    """
    
    def __init__(self):
        """Initialize terrain tools with STAC client."""
        self.stac_endpoint = "https://planetarycomputer.microsoft.com/api/stac/v1"
        self._catalog = None
        logger.info("✅ TerrainAnalysisTools initialized")
    
    @property
    def catalog(self):
        """Lazy-load STAC catalog."""
        if self._catalog is None:
            from pystac_client import Client
            self._catalog = Client.open(self.stac_endpoint)
        return self._catalog
    
    def _calculate_bbox(self, latitude: float, longitude: float, radius_km: float) -> List[float]:
        """Calculate bounding box from center and radius."""
        lat_deg_per_km = 1 / 111.0
        lon_deg_per_km = 1 / (111.0 * np.cos(np.radians(latitude)))
        
        lat_delta = radius_km * lat_deg_per_km
        lon_delta = radius_km * lon_deg_per_km
        
        return [
            longitude - lon_delta,
            latitude - lat_delta,
            longitude + lon_delta,
            latitude + lat_delta
        ]
    
    @kernel_function(
        name="get_elevation_analysis",
        description="Analyze elevation data for a location. Returns min, max, mean elevation in meters, elevation range, and terrain classification (flat, hilly, mountainous). Use this when the user asks about elevation, altitude, height, or topography."
    )
    async def get_elevation_analysis(
        self,
        latitude: Annotated[float, "Center latitude of the area to analyze"],
        longitude: Annotated[float, "Center longitude of the area to analyze"],
        radius_km: Annotated[float, "Radius in kilometers for analysis area"] = 5.0
    ) -> Dict[str, Any]:
        """Fetch DEM data and calculate elevation statistics."""
        try:
            import rasterio
            from rasterio.windows import from_bounds
            import planetary_computer
            
            logger.info(f"🏔️ [TOOL] get_elevation_analysis at ({latitude:.4f}, {longitude:.4f}), radius={radius_km}km")
            
            bbox = self._calculate_bbox(latitude, longitude, radius_km)
            
            # Search for DEM
            search = self.catalog.search(
                collections=["cop-dem-glo-30"],
                bbox=bbox,
                limit=1
            )
            
            items = list(search.items())
            if not items:
                return {"error": "No DEM data available for this location", "elevation_stats": {}}
            
            item = items[0]
            signed_item = planetary_computer.sign(item)
            dem_url = signed_item.assets["data"].href
            
            with rasterio.open(dem_url) as src:
                window = from_bounds(*bbox, src.transform)
                window = window.intersection(rasterio.windows.Window(0, 0, src.width, src.height))
                
                if window.width < 1 or window.height < 1:
                    return {"error": "Area too small for DEM analysis", "elevation_stats": {}}
                
                elevation = src.read(1, window=window)
                elevation = np.ma.masked_equal(elevation, src.nodata or -9999)
                
                if elevation.count() == 0:
                    return {"error": "No valid elevation data", "elevation_stats": {}}
                
                elev_min = float(elevation.min())
                elev_max = float(elevation.max())
                elev_mean = float(elevation.mean())
                elev_range = elev_max - elev_min
                
                # Classify terrain
                if elev_range < 50:
                    terrain_type = "flat plains"
                elif elev_range < 200:
                    terrain_type = "gently rolling hills"
                elif elev_range < 500:
                    terrain_type = "hilly terrain"
                elif elev_range < 1000:
                    terrain_type = "rugged hills"
                else:
                    terrain_type = "mountainous terrain"
                
                result = {
                    "elevation_min_meters": round(elev_min, 1),
                    "elevation_max_meters": round(elev_max, 1),
                    "elevation_mean_meters": round(elev_mean, 1),
                    "elevation_range_meters": round(elev_range, 1),
                    "terrain_type": terrain_type,
                    "data_source": "Copernicus DEM GLO-30 (30m resolution)"
                }
                
                logger.info(f"✅ [TOOL] Elevation: {elev_min:.0f}m - {elev_max:.0f}m, type: {terrain_type}")
                return result
                
        except Exception as e:
            logger.error(f"❌ [TOOL] Elevation analysis failed: {e}")
            return {"error": str(e), "elevation_stats": {}}
    
    @kernel_function(
        name="get_slope_analysis", 
        description="Analyze terrain slope (steepness) for a location. Returns min, max, mean slope in degrees, and identifies steep areas. Use this when user asks about slope, steepness, gradient, or terrain difficulty."
    )
    async def get_slope_analysis(
        self,
        latitude: Annotated[float, "Center latitude"],
        longitude: Annotated[float, "Center longitude"],
        radius_km: Annotated[float, "Radius in kilometers"] = 5.0
    ) -> Dict[str, Any]:
        """Calculate slope from DEM data."""
        try:
            import rasterio
            from rasterio.windows import from_bounds
            import planetary_computer
            
            logger.info(f"📐 [TOOL] get_slope_analysis at ({latitude:.4f}, {longitude:.4f})")
            
            bbox = self._calculate_bbox(latitude, longitude, radius_km)
            
            search = self.catalog.search(collections=["cop-dem-glo-30"], bbox=bbox, limit=1)
            items = list(search.items())
            
            if not items:
                return {"error": "No DEM data available", "slope_stats": {}}
            
            item = planetary_computer.sign(items[0])
            
            with rasterio.open(item.assets["data"].href) as src:
                window = from_bounds(*bbox, src.transform)
                window = window.intersection(rasterio.windows.Window(0, 0, src.width, src.height))
                
                elevation = src.read(1, window=window).astype(float)
                
                # CRITICAL: Convert cell size from degrees to meters
                # The DEM resolution is in degrees, but elevation is in meters
                # At the equator, 1 degree ≈ 111,320 meters
                # At latitude φ: 1 degree longitude ≈ 111,320 * cos(φ) meters
                cell_size_deg = src.res[0]  # Resolution in degrees
                cell_size_meters = cell_size_deg * 111320 * np.cos(np.radians(latitude))
                
                # Calculate slope using proper cell size in meters
                dy, dx = np.gradient(elevation, cell_size_meters)
                slope = np.degrees(np.arctan(np.sqrt(dx**2 + dy**2)))
                
                slope_min = float(np.min(slope))
                slope_max = float(np.max(slope))
                slope_mean = float(np.mean(slope))
                
                # Classify areas
                flat_pct = float(np.sum(slope < 5) / slope.size * 100)
                moderate_pct = float(np.sum((slope >= 5) & (slope < 15)) / slope.size * 100)
                steep_pct = float(np.sum(slope >= 15) / slope.size * 100)
                
                result = {
                    "slope_min_degrees": round(slope_min, 1),
                    "slope_max_degrees": round(slope_max, 1),
                    "slope_mean_degrees": round(slope_mean, 1),
                    "flat_area_percent": round(flat_pct, 1),
                    "moderate_slope_percent": round(moderate_pct, 1),
                    "steep_area_percent": round(steep_pct, 1),
                    "traversability": "easy" if slope_mean < 5 else "moderate" if slope_mean < 15 else "difficult"
                }
                
                logger.info(f"✅ [TOOL] Slope: mean {slope_mean:.1f}°, {flat_pct:.0f}% flat")
                return result
                
        except Exception as e:
            logger.error(f"❌ [TOOL] Slope analysis failed: {e}")
            return {"error": str(e)}
    
    @kernel_function(
        name="get_aspect_analysis",
        description="Analyze terrain aspect (slope direction/facing). Returns dominant direction (N, NE, E, etc) and distribution. Use this when user asks about which way slopes face, sun exposure, or orientation."
    )
    async def get_aspect_analysis(
        self,
        latitude: Annotated[float, "Center latitude"],
        longitude: Annotated[float, "Center longitude"],
        radius_km: Annotated[float, "Radius in kilometers"] = 5.0
    ) -> Dict[str, Any]:
        """Calculate aspect (slope direction) from DEM."""
        try:
            import rasterio
            from rasterio.windows import from_bounds
            import planetary_computer
            
            logger.info(f"🧭 [TOOL] get_aspect_analysis at ({latitude:.4f}, {longitude:.4f})")
            
            bbox = self._calculate_bbox(latitude, longitude, radius_km)
            search = self.catalog.search(collections=["cop-dem-glo-30"], bbox=bbox, limit=1)
            items = list(search.items())
            
            if not items:
                return {"error": "No DEM data available"}
            
            item = planetary_computer.sign(items[0])
            
            with rasterio.open(item.assets["data"].href) as src:
                window = from_bounds(*bbox, src.transform)
                window = window.intersection(rasterio.windows.Window(0, 0, src.width, src.height))
                
                elevation = src.read(1, window=window).astype(float)
                dy, dx = np.gradient(elevation, src.res[0])
                
                # Aspect in degrees (0=N, 90=E, 180=S, 270=W)
                aspect = np.degrees(np.arctan2(-dx, dy))
                aspect = np.where(aspect < 0, aspect + 360, aspect)
                
                # Categorize
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
                distribution = {k: round(v / total * 100, 1) for k, v in directions.items()}
                dominant = max(directions, key=directions.get)
                
                result = {
                    "dominant_direction": dominant,
                    "direction_distribution_percent": distribution,
                    "sun_exposure": "good" if dominant in ["S", "SE", "SW"] else "moderate" if dominant in ["E", "W"] else "limited"
                }
                
                logger.info(f"✅ [TOOL] Aspect: dominant {dominant}, sun exposure {result['sun_exposure']}")
                return result
                
        except Exception as e:
            logger.error(f"❌ [TOOL] Aspect analysis failed: {e}")
            return {"error": str(e)}
    
    # NOTE: NDVI (get_vegetation_index) and NDWI (identify_water_bodies) tools have been removed
    # due to unreliable Sentinel-2 tile coverage and intersection errors.
    # Visual analysis via GPT-4 Vision provides better vegetation/water detection.
    
    @kernel_function(
        name="find_flat_areas",
        description="Find flat areas suitable for landing zones, construction, or camps. Returns percentage of flat land and locations. Use when user asks about landing zones, flat ground, or buildable areas."
    )
    async def find_flat_areas(
        self,
        latitude: Annotated[float, "Center latitude"],
        longitude: Annotated[float, "Center longitude"],
        radius_km: Annotated[float, "Radius in kilometers"] = 5.0,
        max_slope_degrees: Annotated[float, "Maximum slope to consider 'flat'"] = 5.0
    ) -> Dict[str, Any]:
        """Find flat areas based on slope threshold."""
        try:
            import rasterio
            from rasterio.windows import from_bounds
            import planetary_computer
            
            logger.info(f"🛬 [TOOL] find_flat_areas at ({latitude:.4f}, {longitude:.4f}), max_slope={max_slope_degrees}°")
            
            bbox = self._calculate_bbox(latitude, longitude, radius_km)
            search = self.catalog.search(collections=["cop-dem-glo-30"], bbox=bbox, limit=1)
            items = list(search.items())
            
            if not items:
                return {"error": "No DEM data available"}
            
            item = planetary_computer.sign(items[0])
            
            with rasterio.open(item.assets["data"].href) as src:
                window = from_bounds(*bbox, src.transform)
                window = window.intersection(rasterio.windows.Window(0, 0, src.width, src.height))
                
                elevation = src.read(1, window=window).astype(float)
                
                # Convert cell size from degrees to meters
                cell_size_deg = src.res[0]
                cell_size_meters = cell_size_deg * 111320 * np.cos(np.radians(latitude))
                
                dy, dx = np.gradient(elevation, cell_size_meters)
                slope = np.degrees(np.arctan(np.sqrt(dx**2 + dy**2)))
                
                flat_mask = slope < max_slope_degrees
                flat_pct = float(np.sum(flat_mask) / flat_mask.size * 100)
                
                # Find largest contiguous flat area (simplified)
                suitable = "excellent" if flat_pct > 50 else "good" if flat_pct > 20 else "limited" if flat_pct > 5 else "poor"
                
                result = {
                    "flat_area_percent": round(flat_pct, 1),
                    "slope_threshold_degrees": max_slope_degrees,
                    "suitability_for_landing": suitable,
                    "recommendation": f"{'Abundant' if flat_pct > 30 else 'Some' if flat_pct > 10 else 'Limited'} flat areas available within {radius_km}km radius"
                }
                
                logger.info(f"✅ [TOOL] Flat areas: {flat_pct:.1f}% below {max_slope_degrees}°")
                return result
                
        except Exception as e:
            logger.error(f"❌ [TOOL] Flat area search failed: {e}")
            return {"error": str(e)}
    
    @kernel_function(
        name="exit_analysis_mode",
        description="Call this tool when the user's question is UNRELATED to terrain/location analysis and should be handled by a different system. Examples: asking about satellite datasets (Landsat, Sentinel), requesting imagery for a NEW location, weather questions, or general knowledge queries. This signals the frontend to exit GEOINT mode."
    )
    async def exit_analysis_mode(
        self,
        user_query: Annotated[str, "The user's original question that should be routed elsewhere"],
        reason: Annotated[str, "Brief explanation of why this query should exit terrain mode"] = "Query not related to current terrain analysis"
    ) -> Dict[str, Any]:
        """Signal that user's query should be handled by a different system."""
        logger.info(f"🚪 [TOOL] exit_analysis_mode called - reason: {reason}")
        logger.info(f"🚪 [TOOL] Query to reroute: {user_query[:100]}...")
        
        return {
            "action": "EXIT_GEOINT_MODE",
            "reason": reason,
            "reprocess_query": user_query,
            "message": "This question should be handled by the main Earth Copilot assistant. Exiting terrain analysis mode."
        }
    
    # NOTE: analyze_screenshot tool has been removed.
    # Visual analysis is now performed automatically BEFORE agent invocation
    # and included in the agent's context as [Visual Analysis of Current Map View].
    # This ensures screenshot analysis always succeeds and is available to the agent.
