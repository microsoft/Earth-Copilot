"""
GEOINT Mobility Analysis Tools for Azure AI Agent Service

Standalone synchronous functions compatible with Azure AI Agent Service FunctionTool.
Each function uses docstring-based parameter descriptions and returns JSON strings.

IMPORTANT: All functions are fully synchronous (no asyncio wrappers) to avoid
event-loop conflicts when the Agent SDK calls them from its own async context.

Usage:
    from geoint.mobility_tools import create_mobility_functions
    functions = create_mobility_functions()  # Returns Set[Callable]
    tool = AsyncFunctionTool(functions)
"""

import logging
import json
import math
import os
from typing import Dict, Any, List, Optional, Set, Callable
from datetime import datetime, timedelta
from concurrent.futures import ThreadPoolExecutor, as_completed

import numpy as np
import planetary_computer
import pystac_client
import requests
from cloud_config import cloud_cfg

logger = logging.getLogger(__name__)

# Module-level constants
STAC_ENDPOINT = cloud_cfg.stac_catalog_url
RADIUS_MILES = 5
SLOPE_THRESHOLD_SLOW = 15   # degrees
SLOPE_THRESHOLD_NO_GO = 30  # degrees
WATER_BACKSCATTER_THRESHOLD = -20  # dB
VEGETATION_NDVI_DENSE = 0.6
FIRE_CONFIDENCE_THRESHOLD = 50

# ESA WorldCover land cover class labels
WORLDCOVER_CLASSES = {
    10: "Tree cover",
    20: "Shrubland",
    30: "Grassland",
    40: "Cropland",
    50: "Built-up",
    60: "Bare / sparse vegetation",
    70: "Snow and ice",
    80: "Permanent water bodies",
    90: "Herbaceous wetland",
    95: "Mangroves",
    100: "Moss and lichen",
}

# Mobility impact per WorldCover class
WORLDCOVER_MOBILITY = {
    10: "SLOW-GO",  # Tree cover — canopy, roots
    20: "GO",       # Shrubland — passable
    30: "GO",       # Grassland — clear
    40: "GO",       # Cropland — flat, may be muddy
    50: "GO",       # Built-up — roads likely
    60: "GO",       # Bare — easy traverse
    70: "NO-GO",    # Snow/ice — dangerous
    80: "NO-GO",    # Permanent water — impassable
    90: "SLOW-GO",  # Wetland — soft ground
    95: "NO-GO",    # Mangroves — impassable
    100: "GO",      # Moss/lichen — passable
}

# Lazy-loaded STAC catalog
_catalog = None


def _get_catalog():
    """Lazy-load STAC catalog (synchronous pystac_client)."""
    global _catalog
    if _catalog is None:
        _catalog = pystac_client.Client.open(STAC_ENDPOINT)
    return _catalog


def _convert_numpy_to_python(obj: Any) -> Any:
    """Recursively convert numpy types to Python native types for JSON serialization."""
    if isinstance(obj, np.ndarray):
        return obj.tolist()
    elif isinstance(obj, (np.float32, np.float64)):
        return float(obj)
    elif isinstance(obj, (np.int32, np.int64)):
        return int(obj)
    elif isinstance(obj, np.bool_):
        return bool(obj)
    elif isinstance(obj, dict):
        return {key: _convert_numpy_to_python(value) for key, value in obj.items()}
    elif isinstance(obj, list):
        return [_convert_numpy_to_python(item) for item in obj]
    elif isinstance(obj, tuple):
        return tuple(_convert_numpy_to_python(item) for item in obj)
    return obj


def _calculate_bbox(latitude: float, longitude: float, radius_miles: float = 5.0) -> List[float]:
    """Calculate bounding box from center point and radius in miles."""
    lat_delta = radius_miles / 69.0
    lon_delta = radius_miles / (69.0 * math.cos(math.radians(latitude)))
    return [
        longitude - lon_delta,
        latitude - lat_delta,
        longitude + lon_delta,
        latitude + lat_delta
    ]


def _calculate_directional_bbox(latitude: float, longitude: float, cardinal: str) -> List[float]:
    """Calculate bounding box for a cardinal direction sector (N/S/E/W)."""
    sector_radius = RADIUS_MILES / 2.0
    lat_delta = sector_radius / 69.0
    lon_delta = sector_radius / (69.0 * math.cos(math.radians(latitude)))

    if cardinal == "N":
        return [longitude - lon_delta, latitude, longitude + lon_delta, latitude + lat_delta]
    elif cardinal == "S":
        return [longitude - lon_delta, latitude - lat_delta, longitude + lon_delta, latitude]
    elif cardinal == "E":
        return [longitude, latitude - lat_delta, longitude + lon_delta, latitude + lat_delta]
    else:  # W
        return [longitude - lon_delta, latitude - lat_delta, longitude, latitude + lat_delta]


def _calculate_corridor_bbox(lat1: float, lon1: float, lat2: float, lon2: float, padding_miles: float = 6.0) -> List[float]:
    """Calculate bounding box encompassing the full A→B corridor with padding.
    Padding covers endpoint 5-mile analysis radii plus margin.
    """
    mid_lat = (lat1 + lat2) / 2
    lat_pad = padding_miles / 69.0
    lon_pad = padding_miles / (69.0 * math.cos(math.radians(mid_lat)))
    return [
        min(lon1, lon2) - lon_pad,
        min(lat1, lat2) - lat_pad,
        max(lon1, lon2) + lon_pad,
        max(lat1, lat2) + lat_pad
    ]


def _items_covering_point(items: list, lat: float, lon: float) -> list:
    """Filter STAC items to those whose bbox covers a given point.
    Handles corridors that span multiple tiles (e.g., DEM 1°×1° tiles).
    Falls back to the full list if no items match (e.g., missing bbox metadata).
    """
    covering = []
    for item in items:
        if hasattr(item, 'bbox') and item.bbox:
            b = item.bbox  # [west, south, east, north]
            if b[0] <= lon <= b[2] and b[1] <= lat <= b[3]:
                covering.append(item)
    return covering if covering else items  # graceful fallback


def _prefetch_corridor_stac_items(corridor_bbox: List[float]) -> Dict[str, list]:
    """Pre-fetch STAC items for all 6 collections using a single corridor bbox.

    Eliminates ~20 redundant STAC queries by querying each collection ONCE
    for the full corridor instead of per-endpoint/per-waypoint/per-transect-point.
    Returns dict mapping collection name → list of signed STAC items.
    """
    end_date = datetime.utcnow()
    recent = f"{(end_date - timedelta(days=90)).isoformat()}Z/{end_date.isoformat()}Z"
    queries = [
        ("jrc-gsw", None, None),
        ("sentinel-1-rtc", recent, None),
        ("sentinel-2-l2a", recent, {"eo:cloud_cover": {"lt": 50}}),
        ("cop-dem-glo-30", None, None),
        ("modis-14A1-061", None, None),
        ("esa-worldcover", None, None),
    ]

    results = {}
    with ThreadPoolExecutor(max_workers=6) as executor:
        futures = {
            executor.submit(
                _query_stac_collection_sync, col, corridor_bbox, dt_range, qparams, 10
            ): col
            for col, dt_range, qparams in queries
        }
        for f in as_completed(futures):
            col = futures[f]
            try:
                results[col] = f.result()
            except Exception as e:
                logger.error(f"Corridor prefetch {col} failed: {e}")
                results[col] = []
    found = sum(1 for v in results.values() if v)
    logger.info(f"Corridor prefetch complete: {found}/6 collections returned data")
    return results


def _query_stac_collection_sync(
    collection: str, bbox: List[float],
    datetime_range: Optional[str] = None,
    query_params: Optional[Dict] = None,
    limit: int = 10
) -> list:
    """Query a STAC collection synchronously via pystac_client."""
    try:
        catalog = _get_catalog()
        search_params = {
            "collections": [collection],
            "bbox": bbox,
            "limit": limit,
        }
        if datetime_range:
            search_params["datetime"] = datetime_range
        if query_params:
            search_params["query"] = query_params

        search = catalog.search(**search_params)
        items = list(search.items())
        return [planetary_computer.sign(item) for item in items]
    except Exception as e:
        logger.error(f"STAC query error for {collection}: {e}")
        return []


def _read_cog_window_sync(asset_url: str, bbox: List[float], band: int = 1) -> Optional[np.ndarray]:
    """Read pixels from a Cloud-Optimized GeoTIFF for a bounding box (synchronous)."""
    try:
        import rasterio
        from rasterio.windows import from_bounds
        from rasterio.warp import transform_bounds

        signed_url = planetary_computer.sign_url(asset_url)
        with rasterio.open(signed_url) as src:
            # Reproject bbox from EPSG:4326 to raster's native CRS if needed
            if src.crs and str(src.crs) != "EPSG:4326":
                reprojected = transform_bounds("EPSG:4326", src.crs, *bbox)
            else:
                reprojected = bbox
            window = from_bounds(*reprojected, src.transform)
            data = src.read(band, window=window)
            if src.nodata is not None:
                data = data.astype(float)
                data[data == src.nodata] = np.nan
            return data
    except Exception as e:
        logger.error(f"Failed to read COG: {e}")
        return None


def _analyze_fire_pixels(pixels: np.ndarray) -> Dict[str, Any]:
    """Analyze MODIS FireMask pixel values."""
    valid = pixels[~np.isnan(pixels)]
    if len(valid) == 0:
        return {"status": "GO", "reason": "No fire data available", "confidence": "low"}
    high = int(np.sum(valid == 9))
    nominal = int(np.sum(valid == 8))
    low = int(np.sum(valid == 7))
    total = high + nominal + low
    if high > 0:
        return {"status": "NO-GO", "reason": f"Active fires detected: {high} high-confidence fire pixels", "confidence": "high", "metrics": {"high": high, "nominal": nominal, "low": low, "total": total}}
    elif total > 5:
        return {"status": "SLOW-GO", "reason": f"Multiple fire detections: {total} pixels", "confidence": "medium", "metrics": {"high": high, "nominal": nominal, "low": low, "total": total}}
    elif total > 0:
        return {"status": "SLOW-GO", "reason": f"Potential fires: {total} low-confidence detections", "confidence": "medium", "metrics": {"high": high, "nominal": nominal, "low": low, "total": total}}
    return {"status": "GO", "reason": "No active fires detected", "confidence": "high", "metrics": {"total": 0}}


def _analyze_water_pixels(pixels: np.ndarray) -> Dict[str, Any]:
    """Analyze SAR VV backscatter for water bodies."""
    valid = pixels[~np.isnan(pixels)]
    if len(valid) == 0:
        return {"status": "GO", "reason": "No SAR data available", "confidence": "low"}
    water_pct = float((np.sum(valid < WATER_BACKSCATTER_THRESHOLD) / len(valid)) * 100)
    if water_pct > 30:
        return {"status": "NO-GO", "reason": f"Major water bodies: {water_pct:.1f}% coverage", "confidence": "high", "metrics": {"water_pct": round(water_pct, 1)}}
    elif water_pct > 10:
        return {"status": "SLOW-GO", "reason": f"Moderate water coverage: {water_pct:.1f}%", "confidence": "high", "metrics": {"water_pct": round(water_pct, 1)}}
    return {"status": "GO", "reason": f"Minimal water: {water_pct:.1f}% coverage", "confidence": "high", "metrics": {"water_pct": round(water_pct, 1)}}


def _analyze_jrc_water_pixels(pixels: np.ndarray) -> Dict[str, Any]:
    """Analyze JRC Global Surface Water occurrence data.
    Pixel values: 0-100 = % of time water was observed (1984-2021).
    Values 0 or nodata = never water. 100 = permanent water.
    """
    valid = pixels[~np.isnan(pixels)]
    if len(valid) == 0:
        return {"status": "GO", "reason": "No water occurrence data available", "confidence": "low"}
    # Pixels with occurrence >= 50% are considered water bodies
    water_pixels = np.sum(valid >= 50)
    water_pct = float(water_pixels / len(valid) * 100)
    avg_occurrence = float(np.mean(valid[valid > 0])) if np.any(valid > 0) else 0.0
    permanent_pct = float(np.sum(valid >= 80) / len(valid) * 100)  # Near-permanent water
    if water_pct > 30:
        return {"status": "NO-GO", "reason": f"Major water bodies: {water_pct:.1f}% coverage ({permanent_pct:.1f}% permanent)", "confidence": "high", "metrics": {"water_pct": round(water_pct, 1), "permanent_pct": round(permanent_pct, 1), "avg_occurrence": round(avg_occurrence, 1)}}
    elif water_pct > 10:
        return {"status": "SLOW-GO", "reason": f"Moderate water coverage: {water_pct:.1f}% (avg occurrence {avg_occurrence:.0f}%)", "confidence": "high", "metrics": {"water_pct": round(water_pct, 1), "permanent_pct": round(permanent_pct, 1), "avg_occurrence": round(avg_occurrence, 1)}}
    return {"status": "GO", "reason": f"Minimal water: {water_pct:.1f}% coverage", "confidence": "high", "metrics": {"water_pct": round(water_pct, 1), "permanent_pct": round(permanent_pct, 1), "avg_occurrence": round(avg_occurrence, 1)}}


def _analyze_elevation_pixels(pixels: np.ndarray) -> Dict[str, Any]:
    """Analyze DEM elevation for slope classification."""
    valid = pixels[~np.isnan(pixels)]
    if len(valid) == 0:
        return {"status": "GO", "reason": "No elevation data", "confidence": "low"}
    dy, dx = np.gradient(pixels, 30)
    slope_deg = np.degrees(np.arctan(np.sqrt(dx**2 + dy**2)))
    valid_slopes = slope_deg[~np.isnan(slope_deg)]
    if len(valid_slopes) == 0:
        return {"status": "GO", "reason": "Unable to calculate slopes", "confidence": "low"}
    total = len(valid_slopes)
    gentle = float(np.sum(valid_slopes < 15) / total * 100)
    moderate = float(np.sum((valid_slopes >= 15) & (valid_slopes < 30)) / total * 100)
    steep = float(np.sum(valid_slopes >= 30) / total * 100)
    max_s = float(np.max(valid_slopes))
    avg_s = float(np.mean(valid_slopes))
    if steep > 30:
        return {"status": "NO-GO", "reason": f"Steep terrain: {steep:.1f}% > 30 deg slopes (max {max_s:.1f} deg)", "confidence": "high", "metrics": {"avg": round(avg_s, 1), "max": round(max_s, 1), "gentle_pct": round(gentle, 1), "moderate_pct": round(moderate, 1), "steep_pct": round(steep, 1)}}
    elif moderate + steep > 50:
        return {"status": "SLOW-GO", "reason": f"Moderate terrain: {moderate:.1f}% slopes 15-30 deg (avg {avg_s:.1f} deg)", "confidence": "high", "metrics": {"avg": round(avg_s, 1), "max": round(max_s, 1), "gentle_pct": round(gentle, 1), "moderate_pct": round(moderate, 1), "steep_pct": round(steep, 1)}}
    return {"status": "GO", "reason": f"Gentle terrain: {gentle:.1f}% < 15 deg slopes (avg {avg_s:.1f} deg)", "confidence": "high", "metrics": {"avg": round(avg_s, 1), "max": round(max_s, 1), "gentle_pct": round(gentle, 1), "moderate_pct": round(moderate, 1), "steep_pct": round(steep, 1)}}


def _analyze_vegetation_pixels(red: np.ndarray, nir: np.ndarray) -> Dict[str, Any]:
    """Analyze NDVI from Sentinel-2 red/NIR bands."""
    ndvi = (nir - red) / (nir + red + 1e-8)
    valid = ndvi[(~np.isnan(ndvi)) & (ndvi >= -1) & (ndvi <= 1)]
    if len(valid) == 0:
        return {"status": "GO", "reason": "No vegetation data", "confidence": "low"}
    total = len(valid)
    sparse = float(np.sum(valid < 0.5) / total * 100)
    moderate = float(np.sum((valid >= 0.5) & (valid < 0.7)) / total * 100)
    dense = float(np.sum(valid >= 0.7) / total * 100)
    avg = float(np.mean(valid))
    if dense > 50:
        return {"status": "NO-GO", "reason": f"Dense vegetation: {dense:.1f}% (NDVI > 0.7)", "confidence": "high", "metrics": {"avg_ndvi": round(avg, 2), "dense_pct": round(dense, 1)}}
    elif moderate + dense > 60:
        return {"status": "SLOW-GO", "reason": f"Moderate vegetation: {moderate:.1f}% (avg NDVI {avg:.2f})", "confidence": "high", "metrics": {"avg_ndvi": round(avg, 2), "dense_pct": round(dense, 1)}}
    return {"status": "GO", "reason": f"Light vegetation: {sparse:.1f}% sparse (avg NDVI {avg:.2f})", "confidence": "high", "metrics": {"avg_ndvi": round(avg, 2), "dense_pct": round(dense, 1)}}


def _analyze_landcover_pixels(pixels: np.ndarray) -> Dict[str, Any]:
    """Analyze ESA WorldCover 10m land cover classification.
    Values: 10=Tree, 20=Shrub, 30=Grass, 40=Crop, 50=Built-up,
    60=Bare, 70=Snow/Ice, 80=Water, 90=Wetland, 95=Mangrove, 100=Moss.
    """
    valid = pixels[~np.isnan(pixels)].astype(int)
    if len(valid) == 0:
        return {"status": "GO", "reason": "No land cover data", "confidence": "low"}

    total = len(valid)
    class_pcts = {}
    for val, label in WORLDCOVER_CLASSES.items():
        count = int(np.sum(valid == val))
        if count > 0:
            class_pcts[label] = round(count / total * 100, 1)

    # Determine dominant class
    dominant_val = int(np.bincount(valid.flatten()).argmax()) if len(valid) > 0 else 0
    # Round to nearest WorldCover class value (they're multiples of 10, plus 95)
    wc_vals = sorted(WORLDCOVER_CLASSES.keys())
    dominant_class = min(wc_vals, key=lambda v: abs(v - dominant_val))
    dominant_label = WORLDCOVER_CLASSES.get(dominant_class, "Unknown")
    dominant_mobility = WORLDCOVER_MOBILITY.get(dominant_class, "GO")

    # Compute overall status from area-weighted mobility
    nogo_pct = sum(class_pcts.get(WORLDCOVER_CLASSES[v], 0) for v in [70, 80, 95])
    slowgo_pct = sum(class_pcts.get(WORLDCOVER_CLASSES[v], 0) for v in [10, 90])

    if nogo_pct > 30:
        status = "NO-GO"
        reason = f"Impassable land cover: {nogo_pct:.0f}% ({', '.join(k for k, v in class_pcts.items() if k in ['Snow and ice', 'Permanent water bodies', 'Mangroves'] and v > 5)})"
    elif slowgo_pct > 40:
        status = "SLOW-GO"
        reason = f"Challenging terrain: {slowgo_pct:.0f}% tree cover/wetland"
    else:
        status = dominant_mobility
        reason = f"Dominant: {dominant_label} ({class_pcts.get(dominant_label, 0):.0f}%)"

    return {
        "status": status,
        "reason": reason,
        "confidence": "high",
        "metrics": {
            "dominant_class": dominant_label,
            "class_percentages": class_pcts,
            "has_roads_likely": class_pcts.get("Built-up", 0) > 5,
        }
    }


def _interpolate_points(lat1: float, lon1: float, lat2: float, lon2: float, num_points: int) -> List[Dict[str, float]]:
    """Generate equally-spaced intermediate points along a great-circle arc."""
    points = []
    for i in range(num_points):
        fraction = (i + 1) / (num_points + 1)  # exclude endpoints
        lat = lat1 + fraction * (lat2 - lat1)
        lon = lon1 + fraction * (lon2 - lon1)
        points.append({"latitude": round(lat, 6), "longitude": round(lon, 6), "fraction": round(fraction, 2)})
    return points


def _sample_corridor_point(lat: float, lon: float, prefetched_items: Optional[Dict[str, list]] = None) -> Dict[str, Any]:
    """Lightweight terrain check at a single corridor waypoint.
    Only checks elevation/slope and land cover — fire and water are already
    assessed at the endpoints and don't need re-checking along the corridor.
    Uses a smaller 2-mile radius. When prefetched_items are provided,
    skips STAC queries entirely (uses corridor-level pre-fetched items).
    """
    bbox = _calculate_bbox(lat, lon, radius_miles=2.0)  # smaller radius for corridor
    result = {"latitude": lat, "longitude": lon, "status": "GO", "hazards": [], "data": {}}

    def _fetch(col, asset_key):
        if prefetched_items and col in prefetched_items and prefetched_items[col]:
            items = _items_covering_point(prefetched_items[col], lat, lon)
        else:
            items = _query_stac_collection_sync(col, bbox, limit=3)
        if items:
            asset = items[0].assets.get(asset_key)
            if asset:
                return _read_cog_window_sync(asset.href, bbox)
        return None

    # Parallel COG reads (STAC queries skipped when prefetched)
    fetched = {}
    with ThreadPoolExecutor(max_workers=2) as executor:
        futures = {
            executor.submit(_fetch, "cop-dem-glo-30", "data"): "elevation",
            executor.submit(_fetch, "esa-worldcover", "map"): "landcover",
        }
        for f in as_completed(futures):
            fetched[futures[f]] = f.result()

    # Evaluate elevation/slope
    if fetched.get("elevation") is not None:
        r = _analyze_elevation_pixels(fetched["elevation"])
        if r["status"] == "NO-GO":
            result["status"] = "NO-GO"
        elif r["status"] == "SLOW-GO":
            result["status"] = "SLOW-GO"
        if r["status"] != "GO":
            result["hazards"].append(r["reason"])
        result["data"]["elevation"] = r.get("metrics", {})

    # Evaluate land cover
    if fetched.get("landcover") is not None:
        r = _analyze_landcover_pixels(fetched["landcover"])
        result["data"]["landcover"] = r.get("metrics", {})
        if r["status"] == "NO-GO" and result["status"] != "NO-GO":
            result["status"] = "NO-GO"
            result["hazards"].append(r["reason"])
        elif r["status"] == "SLOW-GO" and result["status"] == "GO":
            result["status"] = "SLOW-GO"
            result["hazards"].append(r["reason"])

    if not result["hazards"]:
        result["hazards"].append("Clear terrain")
    return result


def _build_elevation_transect(lat1: float, lon1: float, lat2: float, lon2: float, num_samples: int = 10, prefetched_dem_items: Optional[list] = None) -> Dict[str, Any]:
    """Sample the DEM at points along A→B to produce an elevation profile.
    When prefetched_dem_items are provided, skips per-point STAC queries (saves ~10 queries).
    """
    points_coords = [(lat1, lon1)]  # include start
    for i in range(1, num_samples - 1):
        f = i / (num_samples - 1)
        points_coords.append((lat1 + f * (lat2 - lat1), lon1 + f * (lon2 - lon1)))
    points_coords.append((lat2, lon2))  # include end

    elevations = []

    def _sample_elev(lat, lon):
        bbox = _calculate_bbox(lat, lon, radius_miles=0.5)
        if prefetched_dem_items:
            items = _items_covering_point(prefetched_dem_items, lat, lon)
        else:
            items = _query_stac_collection_sync("cop-dem-glo-30", bbox, limit=1)
        if items:
            asset = items[0].assets.get("data")
            if asset:
                px = _read_cog_window_sync(asset.href, bbox)
                if px is not None:
                    valid = px[~np.isnan(px)]
                    if len(valid) > 0:
                        return float(np.median(valid))
        return None

    with ThreadPoolExecutor(max_workers=min(num_samples, 6)) as executor:
        futures = [executor.submit(_sample_elev, lat, lon) for lat, lon in points_coords]
        for f in futures:
            elevations.append(f.result())

    profile = []
    for i, ((lat, lon), elev) in enumerate(zip(points_coords, elevations)):
        profile.append({
            "index": i,
            "latitude": round(lat, 6),
            "longitude": round(lon, 6),
            "elevation_m": round(elev, 1) if elev is not None else None,
            "fraction": round(i / (num_samples - 1), 2),
        })

    valid_elevs = [e for e in elevations if e is not None]
    if len(valid_elevs) >= 2:
        total_ascent = sum(max(0, valid_elevs[i+1] - valid_elevs[i]) for i in range(len(valid_elevs)-1))
        total_descent = sum(max(0, valid_elevs[i] - valid_elevs[i+1]) for i in range(len(valid_elevs)-1))
        max_elev = max(valid_elevs)
        min_elev = min(valid_elevs)
    else:
        total_ascent = total_descent = max_elev = min_elev = 0

    return {
        "profile": profile,
        "summary": {
            "total_ascent_m": round(total_ascent, 1),
            "total_descent_m": round(total_descent, 1),
            "max_elevation_m": round(max_elev, 1),
            "min_elevation_m": round(min_elev, 1),
            "elevation_range_m": round(max_elev - min_elev, 1),
            "start_elevation_m": round(valid_elevs[0], 1) if valid_elevs else None,
            "end_elevation_m": round(valid_elevs[-1], 1) if valid_elevs else None,
        }
    }


def _get_azure_maps_route(lat1: float, lon1: float, lat2: float, lon2: float) -> Optional[Dict[str, Any]]:
    """Call Azure Maps Route Directions API to get road route info."""
    maps_key = os.getenv("AZURE_MAPS_SUBSCRIPTION_KEY") or os.getenv("AZURE_MAPS_KEY")
    if not maps_key:
        logger.warning("Azure Maps key not configured — skipping route lookup")
        return None
    try:
        url = f"{cloud_cfg.azure_maps_base_url}/route/directions/json"
        params = {
            "api-version": "1.0",
            "subscription-key": maps_key,
            "query": f"{lat1},{lon1}:{lat2},{lon2}",
            "travelMode": "car",
            "routeType": "fastest",
        }
        resp = requests.get(url, params=params, timeout=10)
        if resp.status_code == 200:
            data = resp.json()
            routes = data.get("routes", [])
            if routes:
                summary = routes[0].get("summary", {})
                return {
                    "road_route_available": True,
                    "travel_time_seconds": summary.get("travelTimeInSeconds", 0),
                    "travel_time_minutes": round(summary.get("travelTimeInSeconds", 0) / 60, 1),
                    "road_distance_km": round(summary.get("lengthInMeters", 0) / 1000, 2),
                    "road_distance_miles": round(summary.get("lengthInMeters", 0) / 1609.34, 2),
                    "traffic_delay_seconds": summary.get("trafficDelayInSeconds", 0),
                    "departure_time": summary.get("departureTime", ""),
                    "arrival_time": summary.get("arrivalTime", ""),
                }
            else:
                return {"road_route_available": False, "reason": "No road route found between points"}
        else:
            logger.error(f"Azure Maps Route API returned {resp.status_code}")
            return {"road_route_available": False, "reason": f"API error {resp.status_code}"}
    except Exception as e:
        logger.error(f"Azure Maps route lookup failed: {e}")
        return None


def _get_azure_maps_weather(lat: float, lon: float) -> Optional[Dict[str, Any]]:
    """Call Azure Maps Weather - Current Conditions for a point."""
    maps_key = os.getenv("AZURE_MAPS_SUBSCRIPTION_KEY") or os.getenv("AZURE_MAPS_KEY")
    if not maps_key:
        return None
    try:
        url = f"{cloud_cfg.azure_maps_base_url}/weather/currentConditions/json"
        params = {
            "api-version": "1.1",
            "subscription-key": maps_key,
            "query": f"{lat},{lon}",
        }
        resp = requests.get(url, params=params, timeout=10)
        if resp.status_code == 200:
            data = resp.json()
            results = data.get("results", [])
            if results:
                r = results[0]
                return {
                    "phrase": r.get("phrase", "Unknown"),
                    "temperature_c": r.get("temperature", {}).get("value"),
                    "humidity_pct": r.get("relativeHumidity"),
                    "wind_speed_kmh": r.get("wind", {}).get("speed", {}).get("value"),
                    "wind_direction": r.get("wind", {}).get("direction", {}).get("localizedDescription"),
                    "visibility_km": r.get("visibility", {}).get("value"),
                    "cloud_cover_pct": r.get("cloudCover"),
                    "has_precipitation": r.get("hasPrecipitation", False),
                    "precipitation_type": r.get("precipitationType"),
                    "observation_time": r.get("dateTime", ""),
                }
        return None
    except Exception as e:
        logger.error(f"Azure Maps weather lookup failed: {e}")
        return None


# ============================================================================
# PUBLIC TOOL FUNCTIONS (registered with AsyncFunctionTool)
# All functions are fully synchronous — no asyncio wrappers.
# ============================================================================

def analyze_directional_mobility(latitude: float, longitude: float) -> str:
    """Analyze terrain mobility in all four cardinal directions (N, S, E, W) from a location.
    Returns GO / SLOW-GO / NO-GO status for each direction based on fire, water, slope, and vegetation.
    Use this when the user asks about mobility, trafficability, or ground movement.

    :param latitude: Center latitude of the analysis area
    :param longitude: Center longitude of the analysis area
    :return: JSON string with directional mobility assessments (north, south, east, west)
    """
    try:
        logger.info(f"[TOOL] analyze_directional_mobility at ({latitude:.4f}, {longitude:.4f})")
        result = _analyze_all_directions_sync(latitude, longitude)
        return json.dumps(_convert_numpy_to_python(result))
    except Exception as e:
        logger.error(f"[TOOL] analyze_directional_mobility failed: {e}")
        return json.dumps({"error": str(e)})


def _analyze_all_directions_sync(latitude: float, longitude: float, prefetched_items: Optional[Dict[str, list]] = None) -> Dict[str, Any]:
    """Synchronous directional mobility analysis.

    When prefetched_items are provided (collection name → item list), skips all
    STAC queries. Analyzes all 4 directions in parallel for additional speed.
    """
    bbox = _calculate_bbox(latitude, longitude, RADIUS_MILES)

    # Map collection names to internal data keys
    col_to_key = {
        "jrc-gsw": "water_detection",
        "sentinel-1-rtc": "terrain_backscatter",
        "sentinel-2-l2a": "vegetation_density",
        "cop-dem-glo-30": "elevation_profile",
        "modis-14A1-061": "active_fires",
        "esa-worldcover": "land_cover",
    }

    data_keys = list(col_to_key.values())
    terrain_data = {k: None for k in data_keys}
    terrain_data["collection_status"] = {}
    terrain_data["sources"] = []

    if prefetched_items:
        # Use corridor-level pre-fetched items — zero new STAC queries
        # Filter items to those covering THIS endpoint (handles tile boundaries)
        for col, key in col_to_key.items():
            all_items = prefetched_items.get(col, [])
            items = _items_covering_point(all_items, latitude, longitude) if all_items else []
            if items:
                terrain_data[key] = {"items_found": len(items), "collection": col, "items": items[:3]}
                terrain_data["collection_status"][col] = "success"
                terrain_data["sources"].append(col)
            else:
                terrain_data["collection_status"][col] = "no_data"
    else:
        # Query each collection in PARALLEL (original path for single-point analysis)
        end_date = datetime.utcnow()
        recent = f"{(end_date - timedelta(days=90)).isoformat()}Z/{end_date.isoformat()}Z"

        collection_queries = [
            ("jrc-gsw", None, None),
            ("sentinel-1-rtc", recent, None),
            ("sentinel-2-l2a", recent, {"eo:cloud_cover": {"lt": 50}}),
            ("cop-dem-glo-30", None, None),
            ("modis-14A1-061", None, None),
            ("esa-worldcover", None, None),
        ]

        def _fetch_collection(col, dt_range, qparams, key):
            try:
                items = _query_stac_collection_sync(col, bbox, datetime_range=dt_range, query_params=qparams, limit=10)
                if items:
                    return key, col, {"items_found": len(items), "collection": col, "items": items[:3]}, "success"
                return key, col, None, "no_data"
            except Exception as e:
                logger.error(f"Collection {col} query failed: {e}")
                return key, col, None, "error"

        with ThreadPoolExecutor(max_workers=6) as executor:
            futures = [
                executor.submit(_fetch_collection, col, dt_range, qparams, key)
                for (col, dt_range, qparams), key in zip(collection_queries, data_keys)
            ]
            for future in as_completed(futures):
                key, col, result, status = future.result()
                terrain_data["collection_status"][col] = status
                if result:
                    terrain_data[key] = result
                    terrain_data["sources"].append(col)

    # Analyze directions in parallel pairs (2 at a time to avoid network saturation)
    directions = {}
    with ThreadPoolExecutor(max_workers=2) as dir_executor:
        dir_futures = {
            dir_executor.submit(
                _analyze_single_direction_sync, name.title(), latitude, longitude, terrain_data, cardinal
            ): name
            for name, cardinal in [("north", "N"), ("south", "S"), ("east", "E"), ("west", "W")]
        }
        for f in as_completed(dir_futures):
            name = dir_futures[f]
            try:
                directions[name] = f.result()
            except Exception as e:
                logger.error(f"Direction {name} analysis failed: {e}")
                directions[name] = {
                    "direction": name.title(), "cardinal": name[0].upper(),
                    "status": "GO", "factors": [f"Analysis error: {e}"],
                    "confidence": "low", "data_sources_used": [], "metrics": {}
                }

    return {
        "location": {"latitude": latitude, "longitude": longitude},
        "radius_miles": RADIUS_MILES,
        "directions": directions,
        "data_sources": terrain_data["sources"],
        "collection_status": terrain_data["collection_status"]
    }


def _analyze_single_direction_sync(direction_name: str, lat: float, lon: float, terrain_data: Dict, cardinal: str) -> Dict:
    """Analyze mobility for one cardinal direction (synchronous).
    
    Pre-fetches all COG raster data in parallel, then evaluates fire → water →
    elevation → vegetation logic sequentially for correct status propagation.
    """
    status = "GO"
    factors = []
    confidence = "medium"
    data_used = []
    metrics = {}
    d_bbox = _calculate_directional_bbox(lat, lon, cardinal)

    # ── Pre-fetch all COG pixels in PARALLEL (biggest I/O savings) ──
    fire_px = water_px = elev_px = red_px = nir_px = None
    fetch_tasks = {}

    if terrain_data.get("active_fires") and terrain_data["active_fires"].get("items"):
        item = terrain_data["active_fires"]["items"][0]
        url = item.assets.get("FireMask", None)
        if url:
            fetch_tasks["fire"] = (url.href, d_bbox, 1)

    if terrain_data.get("water_detection") and terrain_data["water_detection"].get("items"):
        item = terrain_data["water_detection"]["items"][0]
        asset = item.assets.get("occurrence", None)
        if asset:
            fetch_tasks["water"] = (asset.href, d_bbox, 1)

    if terrain_data.get("elevation_profile") and terrain_data["elevation_profile"].get("items"):
        item = terrain_data["elevation_profile"]["items"][0]
        asset = item.assets.get("data", None)
        if asset:
            fetch_tasks["elevation"] = (asset.href, d_bbox, 1)

    if terrain_data.get("vegetation_density") and terrain_data["vegetation_density"].get("items"):
        item = terrain_data["vegetation_density"]["items"][0]
        red_asset = item.assets.get("B04", None)
        nir_asset = item.assets.get("B08", None)
        if red_asset and nir_asset:
            fetch_tasks["veg_red"] = (red_asset.href, d_bbox, 1)
            fetch_tasks["veg_nir"] = (nir_asset.href, d_bbox, 1)

    if terrain_data.get("land_cover") and terrain_data["land_cover"].get("items"):
        item = terrain_data["land_cover"]["items"][0]
        asset = item.assets.get("map", None)
        if asset:
            fetch_tasks["landcover"] = (asset.href, d_bbox, 1)

    # Fetch all COGs concurrently
    fetched = {}
    if fetch_tasks:
        with ThreadPoolExecutor(max_workers=min(len(fetch_tasks), 6)) as executor:
            futures = {
                executor.submit(_read_cog_window_sync, href, bbox, band): key
                for key, (href, bbox, band) in fetch_tasks.items()
            }
            for future in as_completed(futures):
                key = futures[future]
                try:
                    fetched[key] = future.result()
                except Exception as e:
                    logger.error(f"COG fetch {key} failed: {e}")
                    fetched[key] = None

    # ── Evaluate analysis chain (sequential logic, but data already loaded) ──

    # Fire
    if "fire" in fetched and fetched["fire"] is not None:
        try:
            r = _analyze_fire_pixels(fetched["fire"])
            status = r["status"]
            factors.append(r["reason"])
            confidence = r["confidence"]
            data_used.append("MODIS Fire")
            metrics["fire"] = r.get("metrics", {})
        except Exception as e:
            logger.error(f"Fire analysis failed: {e}")

    # Water (JRC Global Surface Water occurrence)
    if status != "NO-GO" and "water" in fetched and fetched["water"] is not None:
        try:
            r = _analyze_jrc_water_pixels(fetched["water"])
            if r["status"] == "NO-GO":
                status = "NO-GO"
            elif r["status"] == "SLOW-GO" and status == "GO":
                status = "SLOW-GO"
            factors.append(r["reason"])
            data_used.append("JRC Global Surface Water")
            metrics["water"] = r.get("metrics", {})
        except Exception as e:
            logger.error(f"Water analysis failed: {e}")

    # Elevation/Slope
    if status == "GO" and "elevation" in fetched and fetched["elevation"] is not None:
        try:
            r = _analyze_elevation_pixels(fetched["elevation"])
            if r["status"] == "NO-GO":
                status = "NO-GO"
            elif r["status"] == "SLOW-GO" and status == "GO":
                status = "SLOW-GO"
            factors.append(r["reason"])
            data_used.append("Copernicus DEM")
            metrics["elevation"] = r.get("metrics", {})
        except Exception as e:
            logger.error(f"Elevation analysis failed: {e}")

    # Vegetation
    if (status == "GO" and "veg_red" in fetched and "veg_nir" in fetched
            and fetched["veg_red"] is not None and fetched["veg_nir"] is not None):
        try:
            r = _analyze_vegetation_pixels(fetched["veg_red"], fetched["veg_nir"])
            if r["status"] == "NO-GO":
                status = "NO-GO"
            elif r["status"] == "SLOW-GO" and status == "GO":
                status = "SLOW-GO"
            factors.append(r["reason"])
            data_used.append("Sentinel-2 NDVI")
            metrics["vegetation"] = r.get("metrics", {})
        except Exception as e:
            logger.error(f"Vegetation analysis failed: {e}")

    # Land Cover (ESA WorldCover)
    if "landcover" in fetched and fetched["landcover"] is not None:
        try:
            r = _analyze_landcover_pixels(fetched["landcover"])
            if r["status"] == "NO-GO" and status != "NO-GO":
                status = "NO-GO"
            elif r["status"] == "SLOW-GO" and status == "GO":
                status = "SLOW-GO"
            factors.append(r["reason"])
            data_used.append("ESA WorldCover")
            metrics["landcover"] = r.get("metrics", {})
        except Exception as e:
            logger.error(f"Land cover analysis failed: {e}")

    if not factors:
        factors.append("No major obstructions detected")
        confidence = "low"

    return {
        "direction": direction_name, "cardinal": cardinal,
        "status": status, "factors": factors, "confidence": confidence,
        "data_sources_used": data_used or ["No raster data available"],
        "metrics": metrics
    }


def detect_water_bodies(latitude: float, longitude: float) -> str:
    """Detect water bodies using JRC Global Surface Water occurrence data.
    Uses global water mapping from 1984-2021 to identify permanent and seasonal water.
    Returns water coverage percentage and classification.

    :param latitude: Center latitude of the analysis area
    :param longitude: Center longitude of the analysis area
    :return: JSON string with water detection results
    """
    try:
        logger.info(f"[TOOL] detect_water_bodies at ({latitude:.4f}, {longitude:.4f})")
        bbox = _calculate_bbox(latitude, longitude, RADIUS_MILES)
        items = _query_stac_collection_sync("jrc-gsw", bbox, limit=5)
        if not items:
            return json.dumps({"status": "no_data", "message": "No JRC Global Surface Water data available"})
        asset = items[0].assets.get("occurrence", None)
        if not asset:
            return json.dumps({"status": "no_data", "message": "No water occurrence asset in JRC GSW"})
        px = _read_cog_window_sync(asset.href, bbox)
        if px is None:
            return json.dumps({"status": "error", "message": "Failed to read water occurrence raster"})
        result = _analyze_jrc_water_pixels(px)
        return json.dumps(_convert_numpy_to_python(result))
    except Exception as e:
        logger.error(f"[TOOL] detect_water_bodies failed: {e}")
        return json.dumps({"error": str(e)})


def detect_active_fires(latitude: float, longitude: float) -> str:
    """Detect active fires using MODIS thermal anomaly data.
    Returns fire confidence levels and pixel counts.

    :param latitude: Center latitude of the analysis area
    :param longitude: Center longitude of the analysis area
    :return: JSON string with fire detection results
    """
    try:
        logger.info(f"[TOOL] detect_active_fires at ({latitude:.4f}, {longitude:.4f})")
        bbox = _calculate_bbox(latitude, longitude, RADIUS_MILES)
        items = _query_stac_collection_sync("modis-14A1-061", bbox, limit=5)
        if not items:
            return json.dumps({"status": "no_data", "message": "No MODIS fire data available"})
        asset = items[0].assets.get("FireMask", None)
        if not asset:
            return json.dumps({"status": "no_data", "message": "No FireMask asset"})
        px = _read_cog_window_sync(asset.href, bbox)
        if px is None:
            return json.dumps({"status": "error", "message": "Failed to read fire raster"})
        result = _analyze_fire_pixels(px)
        return json.dumps(_convert_numpy_to_python(result))
    except Exception as e:
        logger.error(f"[TOOL] detect_active_fires failed: {e}")
        return json.dumps({"error": str(e)})


def analyze_slope_for_mobility(latitude: float, longitude: float) -> str:
    """Analyze terrain slope from Copernicus DEM for vehicle mobility.
    Returns slope statistics and GO/SLOW-GO/NO-GO classification.

    :param latitude: Center latitude of the analysis area
    :param longitude: Center longitude of the analysis area
    :return: JSON string with slope analysis and mobility classification
    """
    try:
        logger.info(f"[TOOL] analyze_slope_for_mobility at ({latitude:.4f}, {longitude:.4f})")
        bbox = _calculate_bbox(latitude, longitude, RADIUS_MILES)
        items = _query_stac_collection_sync("cop-dem-glo-30", bbox, limit=5)
        if not items:
            return json.dumps({"status": "no_data", "message": "No DEM data available"})
        asset = items[0].assets.get("data", None)
        if not asset:
            return json.dumps({"status": "no_data", "message": "No DEM data asset"})
        px = _read_cog_window_sync(asset.href, bbox)
        if px is None:
            return json.dumps({"status": "error", "message": "Failed to read DEM raster"})
        result = _analyze_elevation_pixels(px)
        return json.dumps(_convert_numpy_to_python(result))
    except Exception as e:
        logger.error(f"[TOOL] analyze_slope_for_mobility failed: {e}")
        return json.dumps({"error": str(e)})


def analyze_vegetation_density(latitude: float, longitude: float) -> str:
    """Analyze vegetation density using Sentinel-2 NDVI calculation.
    Returns NDVI statistics and vegetation coverage classification.

    :param latitude: Center latitude of the analysis area
    :param longitude: Center longitude of the analysis area
    :return: JSON string with vegetation density analysis
    """
    try:
        logger.info(f"[TOOL] analyze_vegetation_density at ({latitude:.4f}, {longitude:.4f})")
        bbox = _calculate_bbox(latitude, longitude, RADIUS_MILES)
        end_date = datetime.utcnow()
        dt_range = f"{(end_date - timedelta(days=90)).isoformat()}Z/{end_date.isoformat()}Z"
        items = _query_stac_collection_sync("sentinel-2-l2a", bbox, dt_range, query_params={"eo:cloud_cover": {"lt": 50}}, limit=5)
        if not items:
            return json.dumps({"status": "no_data", "message": "No Sentinel-2 data available (may be cloudy)"})
        red_asset = items[0].assets.get("B04", None)
        nir_asset = items[0].assets.get("B08", None)
        if not red_asset or not nir_asset:
            return json.dumps({"status": "no_data", "message": "No Red/NIR band assets"})
        red_px = _read_cog_window_sync(red_asset.href, bbox)
        nir_px = _read_cog_window_sync(nir_asset.href, bbox)
        if red_px is None or nir_px is None:
            return json.dumps({"status": "error", "message": "Failed to read Sentinel-2 raster"})
        result = _analyze_vegetation_pixels(red_px, nir_px)
        return json.dumps(_convert_numpy_to_python(result))
    except Exception as e:
        logger.error(f"[TOOL] analyze_vegetation_density failed: {e}")
        return json.dumps({"error": str(e)})


def _haversine_distance(lat1: float, lon1: float, lat2: float, lon2: float) -> Dict[str, float]:
    """Calculate distance and bearing between two points."""
    R = 3958.8  # Earth radius in miles
    rlat1, rlat2 = math.radians(lat1), math.radians(lat2)
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = math.sin(dlat / 2) ** 2 + math.cos(rlat1) * math.cos(rlat2) * math.sin(dlon / 2) ** 2
    dist_mi = R * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
    # Bearing
    y = math.sin(dlon) * math.cos(rlat2)
    x = math.cos(rlat1) * math.sin(rlat2) - math.sin(rlat1) * math.cos(rlat2) * math.cos(dlon)
    bearing = (math.degrees(math.atan2(y, x)) + 360) % 360
    return {"distance_miles": round(dist_mi, 2), "distance_km": round(dist_mi * 1.60934, 2), "bearing_degrees": round(bearing, 1)}


def analyze_two_point_traverse(latitude_a: float, longitude_a: float, latitude_b: float, longitude_b: float) -> str:
    """Analyze terrain traversability between two points (A and B) simultaneously.
    Runs mobility analysis at both endpoints IN PARALLEL, plus corridor waypoint
    sampling, elevation transect, Azure Maps road route, and weather conditions.
    Returns a comprehensive mobility assessment covering the entire A→B corridor.

    :param latitude_a: Start point (Point A) latitude
    :param longitude_a: Start point (Point A) longitude
    :param latitude_b: Destination point (Point B) latitude
    :param longitude_b: Destination point (Point B) longitude
    :return: JSON string with mobility assessments for both points, corridor, elevation profile, road route, and weather
    """
    try:
        logger.info(f"[TOOL] analyze_two_point_traverse A({latitude_a:.4f}, {longitude_a:.4f}) -> B({latitude_b:.4f}, {longitude_b:.4f})")
        route = _haversine_distance(latitude_a, longitude_a, latitude_b, longitude_b)

        # Determine number of corridor waypoints based on distance
        dist = route["distance_miles"]
        if dist > 50:
            num_waypoints = 5
        elif dist > 20:
            num_waypoints = 3
        elif dist > 5:
            num_waypoints = 2
        else:
            num_waypoints = 1
        waypoints = _interpolate_points(latitude_a, longitude_a, latitude_b, longitude_b, num_waypoints)

        # ── PRE-FETCH: Query all 6 STAC collections ONCE for the full corridor ──
        # Eliminates ~20 redundant STAC queries (was: 6/endpoint + 10 transect + 4 corridor = 26)
        corridor_bbox = _calculate_corridor_bbox(latitude_a, longitude_a, latitude_b, longitude_b)
        prefetched = _prefetch_corridor_stac_items(corridor_bbox)
        dem_items = prefetched.get("cop-dem-glo-30") or None

        # Run ALL analyses in PARALLEL with pre-fetched STAC data:
        with ThreadPoolExecutor(max_workers=6 + num_waypoints) as executor:
            future_a = executor.submit(_analyze_all_directions_sync, latitude_a, longitude_a, prefetched)
            future_b = executor.submit(_analyze_all_directions_sync, latitude_b, longitude_b, prefetched)
            future_transect = executor.submit(_build_elevation_transect, latitude_a, longitude_a, latitude_b, longitude_b, 10, dem_items)
            future_route = executor.submit(_get_azure_maps_route, latitude_a, longitude_a, latitude_b, longitude_b)
            future_weather_a = executor.submit(_get_azure_maps_weather, latitude_a, longitude_a)
            future_weather_b = executor.submit(_get_azure_maps_weather, latitude_b, longitude_b)
            corridor_futures = [
                executor.submit(_sample_corridor_point, wp["latitude"], wp["longitude"], prefetched)
                for wp in waypoints
            ]

            result_a = future_a.result(timeout=120)
            result_b = future_b.result(timeout=120)

            # Gather corridor results (tolerate individual failures)
            corridor_results = []
            for cf in corridor_futures:
                try:
                    corridor_results.append(cf.result(timeout=60))
                except Exception as e:
                    logger.error(f"Corridor waypoint failed: {e}")

            # Gather supplementary data (non-blocking)
            try:
                elevation_transect = future_transect.result(timeout=60)
            except Exception as e:
                logger.error(f"Elevation transect failed: {e}")
                elevation_transect = None

            road_route = future_route.result(timeout=15)
            weather_a = future_weather_a.result(timeout=10)
            weather_b = future_weather_b.result(timeout=10)

        # Compute corridor summary
        corridor_statuses = [wp.get("status", "GO") for wp in corridor_results]
        if "NO-GO" in corridor_statuses:
            corridor_overall = "NO-GO"
        elif "SLOW-GO" in corridor_statuses:
            corridor_overall = "SLOW-GO"
        else:
            corridor_overall = "GO"

        combined = {
            "route": route,
            "road_route": road_route,
            "weather": {
                "origin": weather_a,
                "destination": weather_b,
            },
            "elevation_transect": elevation_transect,
            "corridor": {
                "waypoints_sampled": len(corridor_results),
                "overall_status": corridor_overall,
                "waypoints": corridor_results,
            },
            "origin": result_a,
            "destination": result_b,
        }
        return json.dumps(_convert_numpy_to_python(combined))
    except Exception as e:
        logger.error(f"[TOOL] analyze_two_point_traverse failed: {e}")
        return json.dumps({"error": str(e)})


def create_mobility_functions() -> Set[Callable]:
    """Return the set of mobility tool functions for AsyncFunctionTool registration."""
    return {
        analyze_directional_mobility,
        analyze_two_point_traverse,
        detect_water_bodies,
        detect_active_fires,
        analyze_slope_for_mobility,
        analyze_vegetation_density,
    }
