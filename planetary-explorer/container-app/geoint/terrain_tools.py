"""
Terrain Analysis Tools for Azure AI Agent Service

Refactored from Semantic Kernel @kernel_function class methods to standalone
functions compatible with Azure AI Agent Service FunctionTool.

Each function uses docstring-based parameter descriptions (the format
FunctionTool expects) and returns JSON-serializable results.

Usage:
    from geoint.terrain_tools import create_terrain_functions
    functions = create_terrain_functions()  # Returns Set[Callable]
    tool = FunctionTool(functions)
"""

import logging
import json
from typing import Dict, Any, List, Set, Callable

import numpy as np
from cloud_config import cloud_cfg

logger = logging.getLogger(__name__)

# Module-level STAC catalog (lazy-loaded)
_catalog = None
_stac_endpoint = cloud_cfg.stac_catalog_url


def _get_catalog():
    """Lazy-load STAC catalog."""
    global _catalog
    if _catalog is None:
        from pystac_client import Client
        _catalog = Client.open(_stac_endpoint)
    return _catalog


def _calculate_bbox(latitude: float, longitude: float, radius_km: float) -> List[float]:
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


def get_elevation_analysis(latitude: float, longitude: float, radius_km: float = 5.0) -> str:
    """Analyze elevation data for a location. Returns min, max, mean elevation in meters, 
    elevation range, and terrain classification (flat, hilly, mountainous).
    Use this when the user asks about elevation, altitude, height, or topography.
    
    :param latitude: Center latitude of the area to analyze
    :param longitude: Center longitude of the area to analyze
    :param radius_km: Radius in kilometers for analysis area (default 5.0)
    :return: JSON string with elevation statistics and terrain classification
    """
    try:
        import rasterio
        from rasterio.windows import from_bounds
        import planetary_computer
        
        logger.info(f"[TOOL] get_elevation_analysis at ({latitude:.4f}, {longitude:.4f}), radius={radius_km}km")
        
        bbox = _calculate_bbox(latitude, longitude, radius_km)
        catalog = _get_catalog()
        
        search = catalog.search(collections=["cop-dem-glo-30"], bbox=bbox, limit=1)
        items = list(search.items())
        
        if not items:
            return json.dumps({"error": "No DEM data available for this location"})
        
        item = planetary_computer.sign(items[0])
        dem_url = item.assets["data"].href
        
        with rasterio.open(dem_url) as src:
            window = from_bounds(*bbox, src.transform)
            window = window.intersection(rasterio.windows.Window(0, 0, src.width, src.height))
            
            if window.width < 1 or window.height < 1:
                return json.dumps({"error": "Area too small for DEM analysis"})
            
            elevation = src.read(1, window=window)
            elevation = np.ma.masked_equal(elevation, src.nodata or -9999)
            
            if elevation.count() == 0:
                return json.dumps({"error": "No valid elevation data"})
            
            elev_min = float(elevation.min())
            elev_max = float(elevation.max())
            elev_mean = float(elevation.mean())
            elev_range = elev_max - elev_min
            
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
            
            logger.info(f"[TOOL] Elevation: {elev_min:.0f}m - {elev_max:.0f}m, type: {terrain_type}")
            return json.dumps(result)
            
    except Exception as e:
        logger.error(f"[TOOL] Elevation analysis failed: {e}")
        return json.dumps({"error": str(e)})


def get_slope_analysis(latitude: float, longitude: float, radius_km: float = 5.0) -> str:
    """Analyze terrain slope (steepness) for a location. Returns min, max, mean slope 
    in degrees, percentage of flat/moderate/steep areas, and traversability assessment.
    Use this when user asks about slope, steepness, gradient, or terrain difficulty.
    
    :param latitude: Center latitude of the area to analyze
    :param longitude: Center longitude of the area to analyze
    :param radius_km: Radius in kilometers for analysis area (default 5.0)
    :return: JSON string with slope statistics and traversability
    """
    try:
        import rasterio
        from rasterio.windows import from_bounds
        import planetary_computer
        
        logger.info(f"[TOOL] get_slope_analysis at ({latitude:.4f}, {longitude:.4f})")
        
        bbox = _calculate_bbox(latitude, longitude, radius_km)
        catalog = _get_catalog()
        
        search = catalog.search(collections=["cop-dem-glo-30"], bbox=bbox, limit=1)
        items = list(search.items())
        
        if not items:
            return json.dumps({"error": "No DEM data available"})
        
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
            
            slope_min = float(np.min(slope))
            slope_max = float(np.max(slope))
            slope_mean = float(np.mean(slope))
            
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
            
            logger.info(f"[TOOL] Slope: mean {slope_mean:.1f} deg, {flat_pct:.0f}% flat")
            return json.dumps(result)
            
    except Exception as e:
        logger.error(f"[TOOL] Slope analysis failed: {e}")
        return json.dumps({"error": str(e)})


def get_aspect_analysis(latitude: float, longitude: float, radius_km: float = 5.0) -> str:
    """Analyze terrain aspect (slope direction/facing). Returns dominant direction 
    (N, NE, E, etc), direction distribution, and sun exposure assessment.
    Use this when user asks about which way slopes face, sun exposure, or orientation.
    
    :param latitude: Center latitude of the area to analyze
    :param longitude: Center longitude of the area to analyze
    :param radius_km: Radius in kilometers for analysis area (default 5.0)
    :return: JSON string with aspect direction and sun exposure
    """
    try:
        import rasterio
        from rasterio.windows import from_bounds
        import planetary_computer
        
        logger.info(f"[TOOL] get_aspect_analysis at ({latitude:.4f}, {longitude:.4f})")
        
        bbox = _calculate_bbox(latitude, longitude, radius_km)
        catalog = _get_catalog()
        
        search = catalog.search(collections=["cop-dem-glo-30"], bbox=bbox, limit=1)
        items = list(search.items())
        
        if not items:
            return json.dumps({"error": "No DEM data available"})
        
        item = planetary_computer.sign(items[0])
        
        with rasterio.open(item.assets["data"].href) as src:
            window = from_bounds(*bbox, src.transform)
            window = window.intersection(rasterio.windows.Window(0, 0, src.width, src.height))
            
            elevation = src.read(1, window=window).astype(float)
            dy, dx = np.gradient(elevation, src.res[0])
            
            aspect = np.degrees(np.arctan2(-dx, dy))
            aspect = np.where(aspect < 0, aspect + 360, aspect)
            
            # Compute slope magnitude to identify flat pixels (slope < 5°)
            slope = np.degrees(np.arctan(np.sqrt(dx**2 + dy**2)))
            flat_mask = slope < 5.0
            flat_pct = float(flat_mask.sum()) / float(aspect.size) * 100
            
            directions = {
                "N": int(((aspect >= 337.5) | (aspect < 22.5)).sum()),
                "NE": int(((aspect >= 22.5) & (aspect < 67.5)).sum()),
                "E": int(((aspect >= 67.5) & (aspect < 112.5)).sum()),
                "SE": int(((aspect >= 112.5) & (aspect < 157.5)).sum()),
                "S": int(((aspect >= 157.5) & (aspect < 202.5)).sum()),
                "SW": int(((aspect >= 202.5) & (aspect < 247.5)).sum()),
                "W": int(((aspect >= 247.5) & (aspect < 292.5)).sum()),
                "NW": int(((aspect >= 292.5) & (aspect < 337.5)).sum())
            }
            
            total = sum(directions.values())
            distribution = {k: round(v / total * 100, 1) for k, v in directions.items()}
            dominant = max(directions, key=directions.get)
            
            # --------------------------------------------------------
            # Sun exposure rating for solar suitability
            # --------------------------------------------------------
            # Flat terrain (slope < 5°) is FAVORABLE for solar: panels
            # can be mounted at any tilt/azimuth, so aspect is irrelevant.
            # Only count sloped pixels when evaluating sun exposure.
            # 
            # Rating logic:
            #   - flat_pct >= 60%  → "good" (flat terrain dominates)
            #   - Otherwise, score sloped pixels by direction:
            #     S/SE/SW = favorable, E/W = neutral, N/NE/NW = unfavorable
            #     favorable > 50% of sloped → "good"
            #     favorable > 30% of sloped → "moderate"
            #     else → "limited"
            if flat_pct >= 60.0:
                sun_exposure = "good"
                sun_note = f"{flat_pct:.0f}% of terrain is flat — panels can face any direction (optimal for south-facing mounting)"
            else:
                # Only consider sloped pixels
                sloped_total = total - int(flat_mask.sum())  # approximate: flat_mask is per-pixel
                if sloped_total > 0:
                    favorable = directions.get("S", 0) + directions.get("SE", 0) + directions.get("SW", 0)
                    unfavorable = directions.get("N", 0) + directions.get("NE", 0) + directions.get("NW", 0)
                    fav_ratio = favorable / total  # as fraction of all pixels
                    unfav_ratio = unfavorable / total
                    
                    if fav_ratio > 0.50:
                        sun_exposure = "good"
                        sun_note = f"Majority of slopes face south/SE/SW — favorable for solar"
                    elif fav_ratio > 0.30:
                        sun_exposure = "moderate"
                        sun_note = f"{fav_ratio*100:.0f}% south-facing slopes, {flat_pct:.0f}% flat terrain"
                    elif unfav_ratio > 0.50:
                        sun_exposure = "limited"
                        sun_note = f"Majority of slopes face north — reduced solar exposure"
                    else:
                        sun_exposure = "moderate"
                        sun_note = f"Mixed slope aspects ({flat_pct:.0f}% flat, {fav_ratio*100:.0f}% south-facing)"
                else:
                    sun_exposure = "good"
                    sun_note = "Terrain is effectively flat — optimal for solar"
            
            result = {
                "dominant_direction": dominant,
                "direction_distribution_percent": distribution,
                "flat_terrain_percent": round(flat_pct, 1),
                "sun_exposure": sun_exposure,
                "sun_exposure_note": sun_note,
            }
            
            logger.info(f"[TOOL] Aspect: dominant {dominant}, flat {flat_pct:.0f}%, sun exposure {sun_exposure}")
            return json.dumps(result)
            
    except Exception as e:
        logger.error(f"[TOOL] Aspect analysis failed: {e}")
        return json.dumps({"error": str(e)})


def find_flat_areas(latitude: float, longitude: float, radius_km: float = 5.0, max_slope_degrees: float = 5.0) -> str:
    """Find flat areas suitable for landing zones, construction, or camps. Returns 
    percentage of flat land and suitability assessment.
    Use when user asks about landing zones, flat ground, or buildable areas.
    
    :param latitude: Center latitude of the area to analyze
    :param longitude: Center longitude of the area to analyze
    :param radius_km: Radius in kilometers for analysis area (default 5.0)
    :param max_slope_degrees: Maximum slope in degrees to consider flat (default 5.0)
    :return: JSON string with flat area percentage and suitability
    """
    try:
        import rasterio
        from rasterio.windows import from_bounds
        import planetary_computer
        
        logger.info(f"[TOOL] find_flat_areas at ({latitude:.4f}, {longitude:.4f}), max_slope={max_slope_degrees} deg")
        
        bbox = _calculate_bbox(latitude, longitude, radius_km)
        catalog = _get_catalog()
        
        search = catalog.search(collections=["cop-dem-glo-30"], bbox=bbox, limit=1)
        items = list(search.items())
        
        if not items:
            return json.dumps({"error": "No DEM data available"})
        
        item = planetary_computer.sign(items[0])
        
        with rasterio.open(item.assets["data"].href) as src:
            window = from_bounds(*bbox, src.transform)
            window = window.intersection(rasterio.windows.Window(0, 0, src.width, src.height))
            
            elevation = src.read(1, window=window).astype(float)
            
            cell_size_deg = src.res[0]
            cell_size_meters = cell_size_deg * 111320 * np.cos(np.radians(latitude))
            
            dy, dx = np.gradient(elevation, cell_size_meters)
            slope = np.degrees(np.arctan(np.sqrt(dx**2 + dy**2)))
            
            flat_mask = slope < max_slope_degrees
            flat_pct = float(np.sum(flat_mask) / flat_mask.size * 100)
            
            suitable = "excellent" if flat_pct > 50 else "good" if flat_pct > 20 else "limited" if flat_pct > 5 else "poor"
            
            result = {
                "flat_area_percent": round(flat_pct, 1),
                "slope_threshold_degrees": max_slope_degrees,
                "suitability_for_landing": suitable,
                "recommendation": f"{'Abundant' if flat_pct > 30 else 'Some' if flat_pct > 10 else 'Limited'} flat areas available within {radius_km}km radius"
            }
            
            logger.info(f"[TOOL] Flat areas: {flat_pct:.1f}% below {max_slope_degrees} deg")
            return json.dumps(result)
            
    except Exception as e:
        logger.error(f"[TOOL] Flat area search failed: {e}")
        return json.dumps({"error": str(e)})


def analyze_flood_risk(latitude: float, longitude: float, radius_km: float = 5.0) -> str:
    """Analyze flood risk using JRC Global Surface Water historical data. Returns water 
    occurrence percentage (0-100%) indicating how often the area has been covered by water,
    flood risk level (LOW/MODERATE/HIGH), and permitting recommendation.
    
    :param latitude: Center latitude of the area to analyze
    :param longitude: Center longitude of the area to analyze
    :param radius_km: Radius in kilometers for analysis area (default 5.0)
    :return: JSON string with flood risk assessment and permitting status
    """
    try:
        import rasterio
        from rasterio.windows import from_bounds
        import planetary_computer
        
        logger.info(f"[TOOL] analyze_flood_risk at ({latitude:.4f}, {longitude:.4f})")
        
        bbox = _calculate_bbox(latitude, longitude, radius_km)
        catalog = _get_catalog()
        
        search = catalog.search(collections=["jrc-gsw"], bbox=bbox, limit=1)
        items = list(search.items())
        
        if not items:
            return json.dumps({"error": "No JRC Global Surface Water data available", "flood_risk": "unknown"})
        
        item = planetary_computer.sign(items[0])
        
        if 'occurrence' not in item.assets:
            return json.dumps({"error": "No occurrence data in JRC-GSW item", "flood_risk": "unknown"})
        
        occurrence_url = item.assets["occurrence"].href
        
        with rasterio.open(occurrence_url) as src:
            window = from_bounds(*bbox, src.transform)
            window = window.intersection(rasterio.windows.Window(0, 0, src.width, src.height))
            
            if window.width < 1 or window.height < 1:
                return json.dumps({"error": "Area too small for analysis", "flood_risk": "unknown"})
            
            occurrence = src.read(1, window=window)
            valid_mask = occurrence <= 100
            if not np.any(valid_mask):
                return json.dumps({"error": "No valid water occurrence data", "flood_risk": "unknown"})
            
            valid_data = occurrence[valid_mask]
            
            mean_occurrence = float(np.mean(valid_data))
            max_occurrence = float(np.max(valid_data))
            pct_ever_flooded = float(np.sum(valid_data > 0) / len(valid_data) * 100)
            pct_frequently_flooded = float(np.sum(valid_data > 25) / len(valid_data) * 100)
            
            if max_occurrence > 50 or pct_frequently_flooded > 10:
                risk_level = "HIGH"
                permitting_status = "NOT RECOMMENDED"
                risk_reason = "Significant historical flooding observed"
            elif max_occurrence > 10 or pct_ever_flooded > 20:
                risk_level = "MODERATE"
                permitting_status = "CONDITIONAL"
                risk_reason = "Some historical flooding, mitigation may be required"
            else:
                risk_level = "LOW"
                permitting_status = "SUITABLE"
                risk_reason = "Minimal historical flooding"
            
            result = {
                "mean_water_occurrence_percent": round(mean_occurrence, 1),
                "max_water_occurrence_percent": round(max_occurrence, 1),
                "area_ever_flooded_percent": round(pct_ever_flooded, 1),
                "area_frequently_flooded_percent": round(pct_frequently_flooded, 1),
                "flood_risk_level": risk_level,
                "permitting_status": permitting_status,
                "risk_reason": risk_reason,
                "data_source": "JRC Global Surface Water (1984-2021)"
            }
            
            logger.info(f"[TOOL] Flood risk: {risk_level} (max occurrence: {max_occurrence:.0f}%)")
            return json.dumps(result)
            
    except Exception as e:
        logger.error(f"[TOOL] Flood risk analysis failed: {e}")
        return json.dumps({"error": str(e), "flood_risk": "unknown"})


def analyze_water_proximity(latitude: float, longitude: float, radius_km: float = 5.0, required_setback_meters: float = 500.0) -> str:
    """Calculate distance to nearest water body for setback requirements. Returns 
    estimated minimum distance to water based on JRC Global Surface Water.
    Use for permitting to verify buffer zones (e.g., 500m from wetlands).
    
    :param latitude: Center latitude of site to analyze
    :param longitude: Center longitude of site to analyze
    :param radius_km: Search radius in kilometers (default 5.0)
    :param required_setback_meters: Required setback distance from water in meters (default 500.0)
    :return: JSON string with water proximity and setback compliance
    """
    try:
        import rasterio
        from rasterio.windows import from_bounds
        import planetary_computer
        from scipy import ndimage
        
        logger.info(f"[TOOL] analyze_water_proximity at ({latitude:.4f}, {longitude:.4f})")
        
        bbox = _calculate_bbox(latitude, longitude, radius_km)
        catalog = _get_catalog()
        
        search = catalog.search(collections=["jrc-gsw"], bbox=bbox, limit=1)
        items = list(search.items())
        
        if not items:
            return json.dumps({"error": "No JRC Global Surface Water data available"})
        
        item = planetary_computer.sign(items[0])
        
        if 'occurrence' not in item.assets:
            return json.dumps({"error": "No occurrence data available"})
        
        occurrence_url = item.assets["occurrence"].href
        
        with rasterio.open(occurrence_url) as src:
            window = from_bounds(*bbox, src.transform)
            window = window.intersection(rasterio.windows.Window(0, 0, src.width, src.height))
            
            if window.width < 1 or window.height < 1:
                return json.dumps({"error": "Area too small for analysis"})
            
            occurrence = src.read(1, window=window)
            water_mask = (occurrence > 10) & (occurrence <= 100)
            
            if not np.any(water_mask):
                return json.dumps({
                    "water_detected": False,
                    "nearest_water_meters": "None within search radius",
                    "setback_requirement_meters": required_setback_meters,
                    "setback_satisfied": True,
                    "permitting_status": "SUITABLE",
                    "recommendation": "No significant water bodies detected within analysis area"
                })
            
            distance_pixels = ndimage.distance_transform_edt(~water_mask)
            center_row = distance_pixels.shape[0] // 2
            center_col = distance_pixels.shape[1] // 2
            center_distance_pixels = distance_pixels[center_row, center_col]
            
            pixel_size_meters = 30.0
            center_distance_meters = float(center_distance_pixels * pixel_size_meters)
            
            setback_satisfied = bool(center_distance_meters >= required_setback_meters)
            
            if setback_satisfied:
                status = "SUITABLE"
                recommendation = f"Site is {center_distance_meters:.0f}m from nearest water body, exceeds {required_setback_meters:.0f}m requirement"
            else:
                status = "NOT SUITABLE"
                recommendation = f"Site is only {center_distance_meters:.0f}m from water, does not meet {required_setback_meters:.0f}m setback requirement"
            
            water_percent = float(np.sum(water_mask) / water_mask.size * 100)
            
            result = {
                "water_detected": True,
                "nearest_water_meters": round(center_distance_meters, 0),
                "setback_requirement_meters": required_setback_meters,
                "setback_satisfied": setback_satisfied,
                "water_area_percent": round(water_percent, 1),
                "permitting_status": status,
                "recommendation": recommendation,
                "data_source": "JRC Global Surface Water (30m resolution)"
            }
            
            logger.info(f"[TOOL] Water proximity: {center_distance_meters:.0f}m, setback {'OK' if setback_satisfied else 'FAILED'}")
            return json.dumps(result)
            
    except ImportError:
        return json.dumps({"error": "scipy not available for distance calculation"})
    except Exception as e:
        logger.error(f"[TOOL] Water proximity analysis failed: {e}")
        return json.dumps({"error": str(e)})


def analyze_environmental_sensitivity(latitude: float, longitude: float, radius_km: float = 5.0) -> str:
    """Identify environmentally sensitive areas using ESA WorldCover land classification. 
    Detects wetlands, forests, mangroves, and other protected land types.
    Use for environmental permitting to check for protected habitats.
    
    :param latitude: Center latitude of the area to analyze
    :param longitude: Center longitude of the area to analyze
    :param radius_km: Radius in kilometers for analysis area (default 5.0)
    :return: JSON string with land cover breakdown and environmental sensitivity
    """
    try:
        import rasterio
        from rasterio.windows import from_bounds
        import planetary_computer
        
        logger.info(f"[TOOL] analyze_environmental_sensitivity at ({latitude:.4f}, {longitude:.4f})")
        
        bbox = _calculate_bbox(latitude, longitude, radius_km)
        catalog = _get_catalog()
        
        search = catalog.search(collections=["esa-worldcover"], bbox=bbox, limit=1)
        items = list(search.items())
        
        if not items:
            return json.dumps({"error": "No ESA WorldCover data available"})
        
        item = planetary_computer.sign(items[0])
        
        if 'map' not in item.assets:
            return json.dumps({"error": "No land cover map asset available"})
        
        map_url = item.assets["map"].href
        
        with rasterio.open(map_url) as src:
            window = from_bounds(*bbox, src.transform)
            window = window.intersection(rasterio.windows.Window(0, 0, src.width, src.height))
            
            if window.width < 1 or window.height < 1:
                return json.dumps({"error": "Area too small for analysis"})
            
            landcover = src.read(1, window=window)
            total_pixels = landcover.size
            
            class_counts = {
                "tree_cover": float(np.sum(landcover == 10) / total_pixels * 100),
                "shrubland": float(np.sum(landcover == 20) / total_pixels * 100),
                "grassland": float(np.sum(landcover == 30) / total_pixels * 100),
                "cropland": float(np.sum(landcover == 40) / total_pixels * 100),
                "built_up": float(np.sum(landcover == 50) / total_pixels * 100),
                "bare_sparse": float(np.sum(landcover == 60) / total_pixels * 100),
                "permanent_water": float(np.sum(landcover == 80) / total_pixels * 100),
                "herbaceous_wetland": float(np.sum(landcover == 90) / total_pixels * 100),
                "mangroves": float(np.sum(landcover == 95) / total_pixels * 100),
            }
            
            sensitive_classes = ["tree_cover", "herbaceous_wetland", "mangroves", "permanent_water"]
            sensitive_percent = sum(class_counts[c] for c in sensitive_classes)
            
            constraints = []
            if class_counts["herbaceous_wetland"] > 5:
                constraints.append(f"Wetlands ({class_counts['herbaceous_wetland']:.1f}%) - may require wetland mitigation")
            if class_counts["mangroves"] > 1:
                constraints.append(f"Mangroves ({class_counts['mangroves']:.1f}%) - protected habitat, development restricted")
            if class_counts["tree_cover"] > 30:
                constraints.append(f"Forest ({class_counts['tree_cover']:.1f}%) - may require deforestation permit")
            if class_counts["permanent_water"] > 10:
                constraints.append(f"Water bodies ({class_counts['permanent_water']:.1f}%) - setback requirements apply")
            
            if sensitive_percent > 40:
                sensitivity_level = "HIGH"
                permitting_status = "NOT RECOMMENDED"
            elif sensitive_percent > 15:
                sensitivity_level = "MODERATE"
                permitting_status = "CONDITIONAL"
            else:
                sensitivity_level = "LOW"
                permitting_status = "SUITABLE"
            
            dominant = max(class_counts, key=class_counts.get)
            
            result = {
                "land_cover_breakdown_percent": {k: round(v, 1) for k, v in class_counts.items() if v > 0.5},
                "dominant_land_cover": dominant.replace("_", " ").title(),
                "sensitive_area_percent": round(sensitive_percent, 1),
                "environmental_sensitivity": sensitivity_level,
                "permitting_status": permitting_status,
                "environmental_constraints": constraints if constraints else ["No major environmental constraints identified"],
                "data_source": "ESA WorldCover 2021 (10m resolution)"
            }
            
            logger.info(f"[TOOL] Environmental sensitivity: {sensitivity_level} ({sensitive_percent:.0f}% sensitive)")
            return json.dumps(result)
            
    except Exception as e:
        logger.error(f"[TOOL] Environmental sensitivity analysis failed: {e}")
        return json.dumps({"error": str(e)})


def create_terrain_functions() -> Set[Callable]:
    """Create the set of terrain analysis functions for FunctionTool.
    
    Returns a Set[Callable] that can be passed to FunctionTool().
    Each function uses docstring-based parameter descriptions.
    """
    return {
        get_elevation_analysis,
        get_slope_analysis,
        get_aspect_analysis,
        find_flat_areas,
        analyze_flood_risk,
        analyze_water_proximity,
        analyze_environmental_sensitivity,
    }
