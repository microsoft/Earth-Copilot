"""
GEOINT Comparison Analysis Tools for Azure AI Agent Service

Refactored from ComparisonAgent class methods to standalone functions
compatible with Azure AI Agent Service FunctionTool.

Usage:
    from geoint.comparison_tools import create_comparison_functions
    functions = create_comparison_functions()  # Returns Set[Callable]
    tool = AsyncFunctionTool(functions)
"""

import logging
import json
import re
import requests
import math
import concurrent.futures
import asyncio
from typing import Dict, Any, Optional, List, Set, Callable
from datetime import datetime
from calendar import monthrange

logger = logging.getLogger(__name__)

from cloud_config import cloud_cfg

STAC_URL = cloud_cfg.stac_catalog_url

# Module-level capture of the last compare_temporal_imagery result.
# The Azure AI Agent SDK's run_steps API may not reliably expose tool outputs
# when using enable_auto_function_calls. This provides a reliable fallback.
_last_comparison_result: Optional[Dict] = None

def get_last_comparison_result() -> Optional[Dict]:
    """Get the last captured comparison result (tile URLs, bbox, etc.)."""
    return _last_comparison_result

def reset_comparison_capture():
    """Reset the capture before a new agent run."""
    global _last_comparison_result
    _last_comparison_result = None

COLLECTION_MAP = {
    # Optical imagery
    "reflectance": "sentinel-2-l2a",
    "surface reflectance": "sentinel-2-l2a",
    "optical": "sentinel-2-l2a",
    "sentinel": "sentinel-2-l2a",
    "sentinel-2": "sentinel-2-l2a",
    "sentinel 2": "sentinel-2-l2a",
    # HLS
    "hls": "hls2-l30",
    "harmonized landsat": "hls2-l30",
    "harmonized landsat sentinel": "hls2-l30",
    # Landsat
    "landsat": "landsat-c2-l2",
    # Vegetation
    "vegetation": "sentinel-2-l2a",
    "ndvi": "sentinel-2-l2a",
    "deforestation": "sentinel-2-l2a",
    "forest": "sentinel-2-l2a",
    # Water
    "water": "jrc-gsw",
    "flood": "jrc-gsw",
    "flooding": "jrc-gsw",
    # Snow
    "snow": "modis-10A1-061",
    "snow cover": "modis-10A1-061",
    # Fire / MODIS fire (use 8-day composite – daily modis-14A1-061 tiles
    # return 500 from PC tile server; modis-14A2-061 works reliably)
    "fire": "modis-14A2-061",
    "modis fire": "modis-14A2-061",
    "modis fire activity": "modis-14A2-061",
    "fire activity": "modis-14A2-061",
    "fire detection": "modis-14A2-061",
    "wildfire": "modis-14A2-061",
    "wildfire activity": "modis-14A2-061",
    "burn": "modis-14A2-061",
    "burned area": "modis-14A2-061",
    "active fire": "modis-14A2-061",
    "thermal": "modis-14A2-061",
    # SAR / Sentinel-1
    "sentinel-1": "sentinel-1-rtc",
    "sentinel 1": "sentinel-1-rtc",
    "sar": "sentinel-1-rtc",
    "radar": "sentinel-1-rtc",
    "sentinel-1 rtc": "sentinel-1-rtc",
    "sentinel-1 grd": "sentinel-1-grd",
    # Direct collection IDs (pass-through)
    "sentinel-2-l2a": "sentinel-2-l2a",
    "hls2-l30": "hls2-l30",
    "hls2-s30": "hls2-s30",
    "landsat-c2-l2": "landsat-c2-l2",
    "jrc-gsw": "jrc-gsw",
    "modis-10A1-061": "modis-10A1-061",
    "modis-14A1-061": "modis-14A1-061",
    "modis-14A2-061": "modis-14A2-061",
    "sentinel-1-grd": "sentinel-1-grd",
    "sentinel-1-rtc": "sentinel-1-rtc",
}

ASSET_MAP = {
    "sentinel-2-l2a": "visual",
    "landsat-c2-l2": "visual",
    "hls2-l30": "visual",
    "hls2-s30": "visual",
    "jrc-gsw": "occurrence",
    "modis-10A1-061": "NDSI_Snow_Cover",
    "modis-14A1-061": "FireMask",
    "modis-14A2-061": "FireMask",
    "sentinel-1-grd": "vv",
    "sentinel-1-rtc": "vv",
}

# Extra query parameters for tile URLs that need rescale or expression rendering
TILE_EXTRA_PARAMS = {
    "sentinel-1-grd": "&rescale=0,600",
    "sentinel-1-rtc": "&rescale=0,0.8",
    "modis-14A1-061": "&rescale=0,9",
    "modis-14A2-061": "&rescale=0,9",
    "modis-10A1-061": "&rescale=0,100",
}


def _parse_time_period(time_str: str) -> Optional[str]:
    """Parse a time period string into STAC datetime format."""
    time_str = time_str.strip()
    month_map = {
        'january': 1, 'jan': 1, 'february': 2, 'feb': 2, 'march': 3, 'mar': 3,
        'april': 4, 'apr': 4, 'may': 5, 'june': 6, 'jun': 6, 'july': 7, 'jul': 7,
        'august': 8, 'aug': 8, 'september': 9, 'sep': 9, 'sept': 9,
        'october': 10, 'oct': 10, 'november': 11, 'nov': 11, 'december': 12, 'dec': 12
    }
    mm_yyyy = re.match(r'^(\d{1,2})/(\d{4})$', time_str)
    if mm_yyyy:
        month, year = int(mm_yyyy.group(1)), int(mm_yyyy.group(2))
        if 1 <= month <= 12:
            last_day = monthrange(year, month)[1]
            return f"{year}-{month:02d}-01/{year}-{month:02d}-{last_day:02d}"
    month_year = re.search(r'(\w+)\s+(\d{4})', time_str.lower())
    if month_year:
        month_str, year_str = month_year.groups()
        month = month_map.get(month_str)
        if month:
            year = int(year_str)
            last_day = monthrange(year, month)[1]
            return f"{year}-{month:02d}-01/{year}-{month:02d}-{last_day:02d}"
    year_only = re.match(r'^(\d{4})$', time_str)
    if year_only:
        year = int(year_only.group(1))
        return f"{year}-01-01/{year}-12-31"
    return None


def _get_scene_date(feature: Dict) -> Optional[str]:
    """Extract the best available date from a STAC feature.
    
    MODIS items have datetime=null and use start_datetime/end_datetime instead.
    This safely handles all cases.
    """
    props = feature.get("properties", {})
    dt = props.get("datetime") or props.get("start_datetime") or props.get("end_datetime") or ""
    return dt[:10] if dt else None


def _format_date_display(datetime_range: str) -> str:
    """Format a STAC datetime range for display."""
    if not datetime_range:
        return "Unknown"
    try:
        start_date = datetime_range.split("/")[0]
        dt = datetime.strptime(start_date, "%Y-%m-%d")
        return dt.strftime("%B %Y")
    except Exception:
        return datetime_range


def _execute_stac_search_sync(collection: str, bbox: List[float], datetime_range: str, limit: int = 5) -> Dict:
    """Execute a synchronous STAC search and return results with tile URLs."""
    collection_aliases = {
        "sentinel-2": "sentinel-2-l2a",
        "landsat": "landsat-c2-l2",
        "hls": "hls2-l30",
    }
    stac_collection = collection_aliases.get(collection.lower(), collection)

    search_body = {
        "collections": [stac_collection],
        "bbox": bbox,
        "datetime": datetime_range,
        "limit": limit,
        "sortby": [{"field": "datetime", "direction": "desc"}]
    }
    if stac_collection in ["sentinel-2-l2a", "landsat-c2-l2"]:
        search_body["query"] = {"eo:cloud_cover": {"lt": 30}}

    try:
        resp = requests.post(
            f"{STAC_URL}/search",
            json=search_body,
            headers={"Content-Type": "application/json"},
            timeout=30,
        )
        if resp.status_code == 200:
            data = resp.json()
            features = data.get("features", [])
            tile_urls = []
            if features:
                item_id = features[0].get("id")
                asset = ASSET_MAP.get(stac_collection, "visual")
                extra = TILE_EXTRA_PARAMS.get(stac_collection, "")
                tile_urls.append(f"https://planetarycomputer.microsoft.com/api/data/v1/item/tilejson.json?collection={stac_collection}&item={item_id}&assets={asset}{extra}")
            return {"features": features, "tile_urls": tile_urls, "collection": stac_collection, "datetime": datetime_range}
        return {"features": [], "error": f"Status {resp.status_code}"}
    except Exception as e:
        return {"features": [], "error": str(e)}


# ============================================================================
# SYNC HELPERS
# ============================================================================

def _parse_coordinates_to_bbox(location: str, buffer_deg: float = 0.15) -> Optional[List[float]]:
    """Parse a coordinate string like '39.7527, -121.6003' into a bbox with buffer.

    Supports formats:
      - "lat, lon"  /  "lat,lon"
      - "(lat, lon)"
      - "lat lon" (space-separated)
    Returns [west, south, east, north] or None if not a coordinate string.
    """
    location = location.strip().strip("()")
    # Try comma-separated
    coord_match = re.match(
        r'^([+-]?\d+(?:\.\d+)?)\s*[,\s]\s*([+-]?\d+(?:\.\d+)?)$', location
    )
    if not coord_match:
        return None
    try:
        lat = float(coord_match.group(1))
        lon = float(coord_match.group(2))
        if -90 <= lat <= 90 and -180 <= lon <= 180:
            return [lon - buffer_deg, lat - buffer_deg, lon + buffer_deg, lat + buffer_deg]
        # Maybe they were swapped (lon, lat)?
        if -90 <= lon <= 90 and -180 <= lat <= 180:
            return [lat - buffer_deg, lon - buffer_deg, lat + buffer_deg, lon + buffer_deg]
    except ValueError:
        pass
    return None


def _resolve_location_sync(location: str) -> Optional[List[float]]:
    """Resolve a location name to a bbox using the async LocationResolver from a sync context.

    First checks if the location is raw coordinates (e.g., "39.7527, -121.6003")
    and creates a bbox directly with a ~15km buffer. Otherwise, runs the async
    resolver in a dedicated thread with its own event loop so it never conflicts
    with the Agent SDK event loop.
    """
    # Fast path: raw coordinates -> bbox with buffer
    coord_bbox = _parse_coordinates_to_bbox(location)
    if coord_bbox:
        logger.info(f"Parsed coordinates directly from '{location}' -> bbox={coord_bbox}")
        return coord_bbox

    try:
        from location_resolver import get_location_resolver
        resolver = get_location_resolver()

        def _run():
            loop = asyncio.new_event_loop()
            try:
                return loop.run_until_complete(
                    resolver.resolve_location_to_bbox(location, location_type="region")
                )
            finally:
                loop.close()

        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
            return pool.submit(_run).result(timeout=30)
    except Exception as e:
        logger.warning(f"Location resolution failed: {e}")
        return None


def _fetch_tile_preview_sync(tile_json_url: str,
                             latitude: Optional[float] = None,
                             longitude: Optional[float] = None) -> Optional[str]:
    """Fetch a tile image from a TileJSON URL and return as base64.

    When latitude/longitude are provided, fetches the tile covering that
    exact location so the AI compares the area the user is looking at.
    Otherwise falls back to the scene-center tile.
    """
    import base64
    try:
        resp = requests.get(tile_json_url, timeout=15)
        if resp.status_code != 200:
            return None
        tilejson = resp.json()
        tiles_template = tilejson.get("tiles", [None])[0]
        if not tiles_template:
            return None

        # Use user's coordinates when available; fall back to scene center
        if latitude is not None and longitude is not None:
            use_lat, use_lon = latitude, longitude
            z = 13  # ~19m/pixel — good for local comparison
        else:
            center = tilejson.get("center", [0, 0, 10])
            use_lon, use_lat = center[0], center[1]
            z = min(int(center[2]) if len(center) > 2 else 10, 12)

        lat_rad = math.radians(use_lat)
        n = 2 ** z
        x = int((use_lon + 180) / 360 * n)
        y = int((1 - math.log(math.tan(lat_rad) + 1 / math.cos(lat_rad)) / math.pi) / 2 * n)
        tile_url = tiles_template.replace("{z}", str(z)).replace("{x}", str(x)).replace("{y}", str(y))
        tile_resp = requests.get(tile_url, timeout=15)
        if tile_resp.status_code == 200:
            return base64.b64encode(tile_resp.content).decode()
        return None
    except Exception as e:
        logger.warning(f"Failed to fetch tile preview: {e}")
        return None


# ============================================================================
# PUBLIC TOOL FUNCTIONS (registered with AsyncFunctionTool)
# ============================================================================

def compare_temporal_imagery(location: str, before_period: str, after_period: str, analysis_type: str = "surface reflectance") -> str:
    """Compare satellite imagery between two time periods for temporal change detection.
    Executes dual STAC queries and generates before/after tile URLs for map display.
    Use this when the user asks to compare imagery across dates, detect changes, or analyze temporal differences.

    :param location: Location name or coordinates (e.g., 'Miami Beach' or '25.7907, -80.1300')
    :param before_period: Before time period in MM/YYYY, Month YYYY, or YYYY format (e.g., '01/2020', 'January 2020')
    :param after_period: After time period in same format (e.g., '01/2025', 'January 2025')
    :param analysis_type: Type of analysis: reflectance, vegetation, ndvi, water, snow, fire (default: surface reflectance)
    :return: JSON string with before/after tile URLs, scene counts, and analysis summary
    """
    global _last_comparison_result
    try:
        before_date = _parse_time_period(before_period)
        after_date = _parse_time_period(after_period)

        if not before_date or not after_date:
            result = {"status": "error", "message": f"Could not parse date ranges. Before: '{before_period}', After: '{after_period}'. Use MM/YYYY or Month YYYY format."}
            return json.dumps(result)

        bbox = _resolve_location_sync(location)
        if not bbox:
            result = {"status": "error", "message": f"Could not resolve location: '{location}'. Please provide a valid city or region name."}
            return json.dumps(result)

        collection = COLLECTION_MAP.get(analysis_type.lower(), "sentinel-2-l2a")

        before_result = _execute_stac_search_sync(collection, bbox, before_date, limit=3)
        after_result = _execute_stac_search_sync(collection, bbox, after_date, limit=3)

        before_features = before_result.get("features", [])
        after_features = after_result.get("features", [])

        if not before_features and not after_features:
            result = {"status": "error", "message": f"No imagery found for {location} in either time period."}
            return json.dumps(result)

        center_lng = (bbox[0] + bbox[2]) / 2
        center_lat = (bbox[1] + bbox[3]) / 2

        result = {
            "status": "success",
            "type": "comparison",
            "location": location,
            "analysis_type": analysis_type,
            "bbox": bbox,
            "center": {"lat": center_lat, "lng": center_lng},
            "before": {
                "datetime": before_date,
                "display": _format_date_display(before_date),
                "features_count": len(before_features),
                "tile_urls": before_result.get("tile_urls", []),
                "best_scene_date": _get_scene_date(before_features[0]) if before_features else None
            },
            "after": {
                "datetime": after_date,
                "display": _format_date_display(after_date),
                "features_count": len(after_features),
                "tile_urls": after_result.get("tile_urls", []),
                "best_scene_date": _get_scene_date(after_features[0]) if after_features else None
            },
            "collection": collection,
            "timestamp": datetime.utcnow().isoformat()
        }
        _last_comparison_result = result
        return json.dumps(result)
    except Exception as e:
        logger.error(f"compare_temporal_imagery failed: {e}")
        return json.dumps({"status": "error", "message": f"Comparison failed: {str(e)}"})


def search_stac_for_period(collection: str, location: str, time_period: str) -> str:
    """Search STAC catalog for satellite imagery in a specific time period and location.
    Returns matching scenes with tile URLs for map display.

    :param collection: STAC collection ID (e.g., 'sentinel-2-l2a', 'landsat-c2-l2')
    :param location: Location name (e.g., 'Miami Beach') 
    :param time_period: Time period in MM/YYYY, Month YYYY, or YYYY format
    :return: JSON string with matching scenes and tile URLs
    """
    try:
        dt_range = _parse_time_period(time_period)
        if not dt_range:
            return json.dumps({"status": "error", "message": f"Could not parse time period: '{time_period}'"})

        bbox = _resolve_location_sync(location)
        if not bbox:
            return json.dumps({"status": "error", "message": f"Could not resolve location: '{location}'"})

        result = _execute_stac_search_sync(collection, bbox, dt_range, limit=5)
        features = result.get("features", [])
        return json.dumps({
            "status": "success" if features else "no_data",
            "collection": collection,
            "location": location,
            "datetime": dt_range,
            "features_count": len(features),
            "tile_urls": result.get("tile_urls", []),
            "scenes": [
                {"id": f.get("id"), "datetime": f.get("properties", {}).get("datetime", "")[:10],
                 "cloud_cover": f.get("properties", {}).get("eo:cloud_cover")}
                for f in features[:5]
            ]
        })
    except Exception as e:
        logger.error(f"search_stac_for_period failed: {e}")
        return json.dumps({"status": "error", "message": str(e)})


def analyze_comparison_imagery(location: str, before_tile_url: str, after_tile_url: str,
                               analysis_type: str = "general",
                               latitude: float = 0.0, longitude: float = 0.0) -> str:
    """Analyze visual differences between before and after satellite imagery using AI vision.
    Call this AFTER compare_temporal_imagery to get an AI-powered analysis of what changed between the two time periods.

    :param location: Location name for context (e.g., 'Beirut, Lebanon')
    :param before_tile_url: TileJSON URL for the before-period imagery
    :param after_tile_url: TileJSON URL for the after-period imagery
    :param analysis_type: Type of change to focus on: general, vegetation, urban, fire, water, disaster (default: general)
    :param latitude: Center latitude of the user's area of interest (default: 0.0)
    :param longitude: Center longitude of the user's area of interest (default: 0.0)
    :return: JSON string with AI analysis of observed differences
    """
    try:
        import os
        import base64

        # Pass user's coordinates so we fetch the tile at their pin, not scene center
        lat = latitude if latitude != 0.0 else None
        lon = longitude if longitude != 0.0 else None
        before_image = _fetch_tile_preview_sync(before_tile_url, latitude=lat, longitude=lon)
        after_image = _fetch_tile_preview_sync(after_tile_url, latitude=lat, longitude=lon)

        if not before_image and not after_image:
            return json.dumps({
                "status": "partial",
                "analysis": f"Could not fetch preview images for visual comparison of {location}. The before/after tile URLs are available on the map for manual inspection using the BEFORE/AFTER toggle buttons."
            })

        endpoint = os.getenv("AZURE_OPENAI_ENDPOINT")
        deployment = os.getenv("AZURE_OPENAI_DEPLOYMENT_NAME", "gpt-5")

        if not endpoint:
            return json.dumps({"status": "error", "analysis": "Azure OpenAI endpoint not configured."})

        from azure.identity import DefaultAzureCredential, get_bearer_token_provider
        from openai import AzureOpenAI
        credential = DefaultAzureCredential()
        token_provider = get_bearer_token_provider(credential, cloud_cfg.cognitive_services_scope)

        client = AzureOpenAI(
            azure_endpoint=endpoint,
            azure_ad_token_provider=token_provider,
            api_version="2024-12-01-preview",
            timeout=120.0,
        )

        analysis_prompts = {
            "general": f"Compare these two satellite images of {location}. The first is the BEFORE image and the second is the AFTER image. Describe all visible changes: structural, vegetation, water, land use, etc.",
            "vegetation": f"Compare vegetation changes between these two satellite images of {location}. Focus on deforestation, regrowth, agricultural changes, and NDVI-related observations.",
            "urban": f"Compare urban/structural changes between these two satellite images of {location}. Focus on new construction, demolition, road changes, and expansion patterns.",
            "fire": f"Compare these two satellite images of {location} for fire/burn damage. Identify burn scars, vegetation loss, and recovery patterns.",
            "water": f"Compare water body changes between these two satellite images of {location}. Focus on flooding, drought, coastal erosion, and water level changes.",
            "disaster": f"Compare these two satellite images of {location} for disaster damage assessment. Identify structural damage, debris fields, and affected areas."
        }

        prompt = analysis_prompts.get(analysis_type, analysis_prompts["general"])

        content = [{"type": "text", "text": prompt}]
        if before_image:
            content.append({"type": "image_url", "image_url": {"url": f"data:image/png;base64,{before_image}", "detail": "high"}})
        if after_image:
            content.append({"type": "image_url", "image_url": {"url": f"data:image/png;base64,{after_image}", "detail": "high"}})

        response = client.chat.completions.create(
            model=deployment,
            messages=[{"role": "user", "content": content}],
            max_completion_tokens=1000,
            temperature=1.0,
        )

        analysis = response.choices[0].message.content if response.choices else "No analysis generated."

        return json.dumps({
            "status": "success",
            "analysis": analysis,
            "location": location,
            "analysis_type": analysis_type,
            "images_analyzed": {
                "before": bool(before_image),
                "after": bool(after_image)
            }
        })

    except Exception as e:
        logger.error(f"Comparison imagery analysis error: {e}")
        return json.dumps({
            "status": "error",
            "analysis": f"Visual analysis failed: {str(e)}. Use the BEFORE/AFTER toggle on the map for manual inspection."
        })


def create_comparison_functions() -> Set[Callable]:
    """Return the set of comparison tool functions for AsyncFunctionTool registration."""
    return {
        compare_temporal_imagery,
        search_stac_for_period,
        analyze_comparison_imagery,
    }
