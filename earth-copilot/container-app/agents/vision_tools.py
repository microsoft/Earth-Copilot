"""
Vision Agent Tools - Standalone functions for Azure AI Agent Service FunctionTool.

Refactored from Semantic Kernel @kernel_function class methods on VisionAgentTools
to standalone functions compatible with Azure AI Agent Service FunctionTool.

Each function uses docstring-based parameter descriptions and returns str.
Session context (screenshot, STAC items, map bounds) is shared via module-level
_session_context dict, which must be set via set_session_context() before each
agent invocation.

Usage:
    from agents.vision_tools import create_vision_functions, set_session_context
    functions = create_vision_functions()
    tool = FunctionTool(functions)
"""

import logging
import os
import json
import math
import time
import re
from typing import Dict, Any, Optional, List, Set, Callable
from datetime import datetime
from calendar import monthrange

logger = logging.getLogger(__name__)


# ============================================================================
# MODULE-LEVEL STATE
# ============================================================================

_session_context: Dict[str, Any] = {
    'screenshot_base64': None,
    'map_bounds': None,
    'stac_items': [],
    'loaded_collections': [],
    'tile_urls': [],
}

_vision_client = None
_tool_calls: List[Dict[str, Any]] = []
_AzureOpenAI = None


def set_session_context(
    screenshot_base64: Optional[str] = None,
    map_bounds: Optional[Dict[str, float]] = None,
    stac_items: Optional[List[Dict[str, Any]]] = None,
    loaded_collections: Optional[List[str]] = None,
    tile_urls: Optional[List[str]] = None,
):
    """Set the session context for tool functions. Call before each agent invocation."""
    global _session_context
    _session_context = {
        'screenshot_base64': screenshot_base64,
        'map_bounds': map_bounds or {},
        'stac_items': stac_items or [],
        'loaded_collections': loaded_collections or [],
        'tile_urls': tile_urls or [],
    }


def get_tool_calls() -> List[Dict[str, Any]]:
    """Get list of tool calls made during this invocation."""
    return list(_tool_calls)


def clear_tool_calls():
    """Clear tool call history. Call before each agent invocation."""
    global _tool_calls
    _tool_calls = []


def _log_tool_call(tool_name: str, args: Dict[str, Any], result_preview: str = ""):
    """Log a tool call for tracing."""
    _tool_calls.append({
        "tool": tool_name,
        "timestamp": datetime.utcnow().isoformat(),
        "args": args,
        "result_preview": result_preview[:200] if result_preview else ""
    })
    logger.info(f"[TOOL] TOOL CALL: {tool_name} | Args: {args}")


# ============================================================================
# VISION CLIENT (lazy singleton)
# ============================================================================

def _load_openai():
    """Lazy load Azure OpenAI SDK."""
    global _AzureOpenAI
    if _AzureOpenAI is None:
        try:
            from openai import AzureOpenAI
            _AzureOpenAI = AzureOpenAI
        except ImportError as e:
            logger.warning(f"Azure OpenAI SDK not available: {e}")


def _get_vision_client():
    """Get or create the Azure OpenAI client for vision and knowledge calls."""
    global _vision_client
    if _vision_client is None:
        _load_openai()
        if _AzureOpenAI is None:
            return None
        from azure.identity import DefaultAzureCredential, get_bearer_token_provider
        from cloud_config import cloud_cfg
        credential = DefaultAzureCredential()
        token_provider = get_bearer_token_provider(
            credential, cloud_cfg.cognitive_services_scope
        )
        _vision_client = _AzureOpenAI(
            azure_ad_token_provider=token_provider,
            api_version=os.getenv("AZURE_OPENAI_API_VERSION", "2025-01-01-preview"),
            azure_endpoint=os.getenv("AZURE_OPENAI_ENDPOINT"),
            timeout=120.0
        )
    return _vision_client


# ============================================================================
# RASTER UTILITY FUNCTIONS (synchronous)
# ============================================================================

def _sample_cog_sync(cog_url: str, latitude: float, longitude: float,
                     band: int = 1, max_retries: int = 3,
                     _retry_count: int = 0) -> Dict[str, Any]:
    """
    Sample a Cloud Optimized GeoTIFF (COG) at a specific lat/lng coordinate.
    Synchronous version — directly calls rasterio without thread pool.
    """
    try:
        import rasterio
        from rasterio.session import AWSSession
        import planetary_computer as pc

        # Sign the URL if from Planetary Computer
        if 'blob.core.windows.net' in cog_url:
            try:
                signed_url = pc.sign(cog_url)
            except Exception:
                signed_url = cog_url
        else:
            signed_url = cog_url

        env_options = {
            'GDAL_DISABLE_READDIR_ON_OPEN': 'EMPTY_DIR',
            'CPL_VSIL_CURL_ALLOWED_EXTENSIONS': '.tif,.TIF,.tiff,.TIFF',
            'GDAL_HTTP_TIMEOUT': '30',
            'GDAL_HTTP_MAX_RETRY': '3',
        }

        with rasterio.Env(**env_options):
            with rasterio.open(signed_url) as src:
                crs = str(src.crs)

                # Transform from WGS84 to raster CRS if needed
                if src.crs and str(src.crs) != 'EPSG:4326':
                    from rasterio.warp import transform as transform_coords
                    xs, ys = transform_coords('EPSG:4326', src.crs, [longitude], [latitude])
                    x, y = xs[0], ys[0]
                else:
                    x, y = longitude, latitude

                try:
                    row, col = src.index(x, y)
                except Exception:
                    return {'value': None, 'error': f'Coordinate transform failed', 'crs': crs}

                if row < 0 or row >= src.height or col < 0 or col >= src.width:
                    return {'value': None, 'error': 'Point outside raster pixel bounds', 'crs': crs}

                from rasterio.windows import Window
                window = Window(col, row, 1, 1)
                data = src.read(band, window=window)
                value = float(data[0, 0])

                nodata = src.nodata
                # NaN-aware nodata check: NaN != NaN in IEEE 754, so equality fails
                if nodata is not None:
                    if (math.isnan(nodata) and math.isnan(value)) or value == nodata:
                        return {'value': None, 'error': 'No data at this location (pixel masked)', 'nodata_value': nodata, 'crs': crs, 'reason': 'nodata_mask'}
                # Additional guard: catch NaN even if nodata metadata is missing
                if math.isnan(value):
                    return {'value': None, 'error': 'No data at this location (NaN pixel)', 'crs': crs, 'reason': 'nan_value'}

                description = src.descriptions[band - 1] if src.descriptions and len(src.descriptions) >= band else None
                return {
                    'value': value, 'band': band, 'description': description,
                    'crs': crs, 'pixel_location': {'row': row, 'col': col},
                    'nodata_value': nodata
                }

    except ImportError as e:
        return {'value': None, 'error': f'rasterio not available: {e}'}
    except Exception as e:
        error_str = str(e)
        if '409' in error_str and _retry_count < max_retries:
            delay = 2 ** _retry_count
            logger.warning(f"Rate limited (409), retrying in {delay}s")
            time.sleep(delay)
            return _sample_cog_sync(cog_url, latitude, longitude, band, max_retries, _retry_count + 1)
        return {'value': None, 'error': f'Sampling error: {e}'}


def _fetch_stac_item_sync(collection: str, item_id: str) -> Optional[Dict[str, Any]]:
    """Fetch a STAC item from Planetary Computer (synchronous)."""
    try:
        import httpx
        url = f"https://planetarycomputer.microsoft.com/api/stac/v1/collections/{collection}/items/{item_id}"
        with httpx.Client(timeout=30.0) as client:
            response = client.get(url)
            if response.status_code == 200:
                return response.json()
    except Exception as e:
        logger.error(f"Error fetching STAC item: {e}")
    return None


def _parse_tile_url(tile_url: str) -> Dict[str, str]:
    """Parse a Planetary Computer tile URL to extract collection, item, and asset."""
    from urllib.parse import urlparse, parse_qs
    parsed = urlparse(tile_url)
    params = parse_qs(parsed.query)
    return {
        'collection': params.get('collection', [''])[0],
        'item': params.get('item', [''])[0],
        'assets': params.get('assets', [''])[0]
    }


def _compute_ndvi_sync(red_url: str, nir_url: str, bbox: Optional[List[float]] = None) -> Dict[str, Any]:
    """Compute NDVI statistics from RED and NIR band COG URLs (synchronous)."""
    try:
        import rasterio
        from rasterio.windows import from_bounds
        from rasterio.warp import transform_bounds
        import planetary_computer as pc
        import numpy as np

        try:
            signed_red = pc.sign(red_url) if 'blob.core.windows.net' in red_url else red_url
            signed_nir = pc.sign(nir_url) if 'blob.core.windows.net' in nir_url else nir_url
        except Exception:
            signed_red, signed_nir = red_url, nir_url

        env_options = {
            'GDAL_DISABLE_READDIR_ON_OPEN': 'EMPTY_DIR',
            'CPL_VSIL_CURL_ALLOWED_EXTENSIONS': '.tif,.TIF,.tiff,.TIFF',
            'GDAL_HTTP_TIMEOUT': '30',
            'GDAL_HTTP_MAX_RETRY': '3',
        }

        with rasterio.Env(**env_options):
            with rasterio.open(signed_red) as red_src, rasterio.open(signed_nir) as nir_src:
                if bbox:
                    # Reproject bbox from EPSG:4326 to raster's native CRS if needed
                    if red_src.crs and str(red_src.crs) != 'EPSG:4326':
                        reprojected = transform_bounds('EPSG:4326', red_src.crs, *bbox)
                    else:
                        reprojected = bbox
                    window = from_bounds(*reprojected, red_src.transform)
                    red_data = red_src.read(1, window=window).astype(np.float32)
                    nir_data = nir_src.read(1, window=window).astype(np.float32)
                else:
                    out_shape = (min(512, red_src.height), min(512, red_src.width))
                    red_data = red_src.read(1, out_shape=out_shape).astype(np.float32)
                    nir_data = nir_src.read(1, out_shape=out_shape).astype(np.float32)

                red_nodata = red_src.nodata or 0
                nir_nodata = nir_src.nodata or 0
                valid_mask = (red_data != red_nodata) & (nir_data != nir_nodata)
                valid_mask &= (red_data > 0) | (nir_data > 0)

                if not np.any(valid_mask):
                    return {'error': 'No valid pixels found'}

                denominator = nir_data + red_data
                denominator[denominator == 0] = np.nan
                ndvi = (nir_data - red_data) / denominator
                ndvi_valid = np.clip(ndvi[valid_mask], -1, 1)
                ndvi_valid = ndvi_valid[~np.isnan(ndvi_valid)]

                if len(ndvi_valid) == 0:
                    return {'error': 'No valid NDVI values computed'}

                dense_veg = np.sum(ndvi_valid > 0.6) / len(ndvi_valid) * 100
                moderate_veg = np.sum((ndvi_valid > 0.2) & (ndvi_valid <= 0.6)) / len(ndvi_valid) * 100
                sparse_veg = np.sum((ndvi_valid > 0) & (ndvi_valid <= 0.2)) / len(ndvi_valid) * 100
                non_veg = np.sum(ndvi_valid <= 0) / len(ndvi_valid) * 100

                return {
                    'min': float(np.min(ndvi_valid)),
                    'max': float(np.max(ndvi_valid)),
                    'mean': float(np.mean(ndvi_valid)),
                    'std': float(np.std(ndvi_valid)),
                    'median': float(np.median(ndvi_valid)),
                    'valid_pixels': int(len(ndvi_valid)),
                    'total_pixels': int(red_data.size),
                    'classification': {
                        'dense_vegetation': round(dense_veg, 1),
                        'moderate_vegetation': round(moderate_veg, 1),
                        'sparse_vegetation': round(sparse_veg, 1),
                        'non_vegetation': round(non_veg, 1)
                    }
                }

    except ImportError as e:
        return {'error': f'rasterio not available: {e}'}
    except Exception as e:
        logger.error(f"NDVI computation error: {e}")
        return {'error': f'NDVI computation failed: {e}'}


# ============================================================================
# TOOL 1: ANALYZE SCREENSHOT
# ============================================================================

def analyze_screenshot(question: str) -> str:
    """Analyze the current map screenshot using GPT-5 Vision.
    Use for visual questions about map features, patterns, colors, or land cover.

    :param question: The specific question to answer about the visible imagery
    :return: Natural language description of visible imagery
    """
    logger.info(f"[CAM] analyze_screenshot(question='{question[:50]}...')")
    ctx = _session_context
    screenshot = ctx.get('screenshot_base64')

    if not screenshot:
        _log_tool_call("analyze_screenshot", {"question": question}, "No screenshot")
        return "No screenshot available. The user needs to have a map view loaded."

    try:
        client = _get_vision_client()
        if not client:
            return "Vision analysis unavailable - Azure OpenAI client not initialized."

        image_data = screenshot
        if image_data.startswith('data:image'):
            image_data = image_data.split(',', 1)[1]

        context_parts = []
        bounds = ctx.get('map_bounds', {})
        if bounds:
            context_parts.append(f"Map location: ({bounds.get('center_lat', 'N/A')}, {bounds.get('center_lng', 'N/A')})")
        collections = ctx.get('loaded_collections', [])
        if collections:
            context_parts.append(f"Data layers: {', '.join(collections)}")
        context_str = "\n".join(context_parts) if context_parts else "No additional context"

        system_prompt = f"""You are a geospatial imagery analyst. Analyze the satellite/map imagery and answer the question.

Context:
{context_str}

Guidelines:
- Describe visible features clearly (water bodies, vegetation, urban areas, terrain)
- Identify patterns, colors, and their likely meaning
- Be specific about locations and features
- If you can't see something clearly, say so"""

        deployment = os.getenv("AZURE_OPENAI_DEPLOYMENT_NAME", "gpt-5")
        response = client.chat.completions.create(
            model=deployment,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": [
                    {"type": "text", "text": question},
                    {"type": "image_url", "image_url": {
                        "url": f"data:image/png;base64,{image_data}", "detail": "high"
                    }}
                ]}
            ],
            max_completion_tokens=1000, temperature=0.3
        )
        result = response.choices[0].message.content
        _log_tool_call("analyze_screenshot", {"question": question, "has_image": True}, result)
        return result

    except Exception as e:
        logger.error(f"[FAIL] analyze_screenshot failed: {e}")
        return f"Screenshot analysis failed: {str(e)}"


# ============================================================================
# TOOL 2: ANALYZE RASTER
# ============================================================================

def analyze_raster(metric_type: str = "general") -> str:
    """Get quantitative metrics from loaded raster data like elevation, slope, NDVI,
    or sea surface temperature (SST). Use for numerical questions about terrain
    statistics, temperature values, measurements, and calculations.

    :param metric_type: Type of metric: 'elevation', 'slope', 'ndvi', 'temperature', 'sst', or 'general'
    :return: Quantitative analysis results as text
    """
    logger.info(f"[CHART] analyze_raster(metric_type='{metric_type}')")
    ctx = _session_context
    collections = ctx.get('loaded_collections', [])
    stac_items = ctx.get('stac_items', [])

    if not collections:
        _log_tool_call("analyze_raster", {"metric_type": metric_type}, "No raster data")
        return "No raster data loaded. The user needs to load satellite imagery first."

    try:
        results = []

        # ELEVATION ANALYSIS
        if metric_type in ['elevation', 'general']:
            dem_items = [i for i in stac_items if 'dem' in i.get('collection', '').lower() or 'elevation' in i.get('collection', '').lower()]
            if dem_items:
                item = dem_items[0]
                results.append(f"**Elevation Data (from {item.get('collection')}):**")
                results.append(f"- Item ID: {item.get('id')}")
                if item.get('properties', {}).get('datetime'):
                    results.append(f"- Captured: {item['properties']['datetime'][:10]}")
                if item.get('bbox'):
                    bbox = item['bbox']
                    results.append(f"- Coverage: {bbox[0]:.2f}°W to {bbox[2]:.2f}°E, {bbox[1]:.2f}°S to {bbox[3]:.2f}°N")

        # SST ANALYSIS
        if metric_type in ['temperature', 'sst', 'general']:
            sst_keywords = ['sea-surface-temperature', 'sst', 'temperature-whoi', 'noaa-cdr']
            sst_items = [i for i in stac_items if any(kw in i.get('collection', '').lower() for kw in sst_keywords)]
            if not sst_items:
                sst_items = [i for i in stac_items if 'temperature' in i.get('collection', '').lower()]

            if sst_items:
                item = sst_items[0]
                props = item.get('properties', {})
                assets = item.get('assets', {})
                results.append(f"\n**Sea Surface Temperature Data (from {item.get('collection')}):**")
                results.append(f"- Item ID: {item.get('id')}")
                if props.get('datetime'):
                    results.append(f"- Date: {props['datetime'][:10]}")
                if item.get('bbox'):
                    bbox = item['bbox']
                    results.append(f"- Coverage: {bbox[0]:.2f}° to {bbox[2]:.2f}°E, {bbox[1]:.2f}° to {bbox[3]:.2f}°N")
                results.append(f"\n**Temperature Information:**")
                results.append(f"- Data Unit: Kelvin (K)")
                results.append(f"- Typical Ocean Range: 270K to 310K (-3°C to 37°C)")
                if 'sea_surface_temperature' in assets:
                    results.append(f"\n**SST Asset Available:** sea_surface_temperature")

                bounds = ctx.get('map_bounds', {})
                pin_lat = bounds.get('pin_lat') or bounds.get('center_lat')
                pin_lng = bounds.get('pin_lng') or bounds.get('center_lng')
                if pin_lat and pin_lng:
                    results.append(f"\n**Pin Location:** ({pin_lat:.4f}, {pin_lng:.4f})")

        # NDVI ANALYSIS
        if metric_type in ['ndvi', 'general']:
            optical_keywords = ['sentinel-2', 'landsat', 'hls', 's30', 'l30']
            optical_items = [i for i in stac_items if any(kw in i.get('collection', '').lower() for kw in optical_keywords)]

            if optical_items:
                item = optical_items[0]
                props = item.get('properties', {})
                assets = item.get('assets', {})
                results.append(f"\n**Optical Imagery (from {item.get('collection')}):**")
                results.append(f"- Item ID: {item.get('id')}")
                if props.get('datetime'):
                    results.append(f"- Captured: {props['datetime'][:10]}")

                red_url = assets.get('B04', {}).get('href') or assets.get('red', {}).get('href')
                nir_url = assets.get('B08', {}).get('href') or assets.get('nir08', {}).get('href') or assets.get('B8A', {}).get('href')

                if red_url and nir_url:
                    logger.info(f"[CHART] Computing NDVI from {item.get('collection')}...")
                    ndvi_stats = _compute_ndvi_sync(red_url, nir_url)

                    if 'error' in ndvi_stats:
                        results.append(f"\n**NDVI Analysis:** Error: {ndvi_stats['error']}")
                    else:
                        results.append(f"\n**NDVI Statistics (Computed):**")
                        results.append(f"- Min: **{ndvi_stats['min']:.3f}**")
                        results.append(f"- Max: **{ndvi_stats['max']:.3f}**")
                        results.append(f"- Mean: **{ndvi_stats['mean']:.3f}**")
                        results.append(f"- Std Dev: {ndvi_stats['std']:.3f}")
                        results.append(f"- Valid Pixels: {ndvi_stats['valid_pixels']:,} / {ndvi_stats['total_pixels']:,}")

                        mean_ndvi = ndvi_stats['mean']
                        if mean_ndvi > 0.6:
                            veg_health = "Dense healthy vegetation"
                        elif mean_ndvi > 0.4:
                            veg_health = "Moderate vegetation"
                        elif mean_ndvi > 0.2:
                            veg_health = "Sparse/stressed vegetation"
                        elif mean_ndvi > 0:
                            veg_health = "Minimal vegetation or bare soil"
                        else:
                            veg_health = "Water, snow, or non-vegetated"
                        results.append(f"\n**Interpretation:** {veg_health}")

                        if 'classification' in ndvi_stats:
                            cls = ndvi_stats['classification']
                            results.append(f"\n**Land Cover Classification:**")
                            results.append(f"- Dense Vegetation (NDVI > 0.6): {cls['dense_vegetation']:.1f}%")
                            results.append(f"- Moderate Vegetation (0.2-0.6): {cls['moderate_vegetation']:.1f}%")
                            results.append(f"- Sparse Vegetation (0-0.2): {cls['sparse_vegetation']:.1f}%")
                            results.append(f"- Non-Vegetation (≤ 0): {cls['non_vegetation']:.1f}%")

        # SUMMARY
        if metric_type == 'general' and stac_items:
            results.append(f"\n**Loaded Imagery Summary:** {len(stac_items)} items")
            for i, item in enumerate(stac_items[:5]):
                props = item.get('properties', {})
                dt = props.get('datetime', 'unknown')[:10] if props.get('datetime') else 'unknown'
                cloud = props.get('eo:cloud_cover', 'N/A')
                cloud_str = f"{cloud:.1f}%" if isinstance(cloud, (int, float)) else cloud
                results.append(f"  {i + 1}. {item.get('id', 'unknown')} ({dt}, cloud: {cloud_str})")

        if not results:
            return f"No {metric_type} data available in loaded collections: {collections}"

        result = "\n".join(results)
        _log_tool_call("analyze_raster", {"metric_type": metric_type}, result)
        return result

    except Exception as e:
        logger.error(f"[FAIL] analyze_raster failed: {e}")
        return f"Raster analysis failed: {str(e)}"


# ============================================================================
# TOOL 3: ANALYZE VEGETATION
# ============================================================================

def analyze_vegetation(analysis_type: str = "general") -> str:
    """Analyze vegetation indices from satellite imagery. Supports MODIS vegetation
    products (pre-computed NDVI/EVI) and optical imagery (HLS, Sentinel-2, Landsat)
    for calculating NDVI from RED/NIR bands.

    :param analysis_type: Type: 'ndvi', 'lai', 'fpar', 'npp', 'gpp', or 'general'
    :return: Vegetation indices, health assessment, and interpretation
    """
    logger.info(f"[LEAF] analyze_vegetation(analysis_type='{analysis_type}')")
    ctx = _session_context
    collections = ctx.get('loaded_collections', [])
    stac_items = ctx.get('stac_items', [])

    if not collections:
        return "No vegetation data loaded. Load MODIS vegetation products or optical imagery first."

    try:
        results = []

        veg_products = {
            'modis-13a1-061': {'name': 'MODIS Vegetation Indices 16-Day (500m)', 'metrics': ['NDVI', 'EVI'], 'resolution': '500m'},
            'modis-13q1-061': {'name': 'MODIS Vegetation Indices 16-Day (250m)', 'metrics': ['NDVI', 'EVI'], 'resolution': '250m'},
            'modis-15a2h-061': {'name': 'MODIS LAI/FPAR 8-Day', 'metrics': ['LAI', 'FPAR'], 'resolution': '500m'},
            'modis-17a2h-061': {'name': 'MODIS GPP 8-Day', 'metrics': ['GPP', 'PSN'], 'resolution': '500m'},
            'modis-17a3hgf-061': {'name': 'MODIS NPP Yearly', 'metrics': ['NPP'], 'resolution': '500m'},
        }

        optical_products = {
            'hls2-l30': {'name': 'HLS Landsat', 'resolution': '30m', 'red': 'B04', 'nir': 'B05'},
            'hls2-s30': {'name': 'HLS Sentinel', 'resolution': '30m', 'red': 'B04', 'nir': 'B08'},
            'hls-l30': {'name': 'HLS Landsat 30m', 'resolution': '30m', 'red': 'B04', 'nir': 'B05'},
            'hls-s30': {'name': 'HLS Sentinel 30m', 'resolution': '30m', 'red': 'B04', 'nir': 'B8A'},
            'sentinel-2-l2a': {'name': 'Sentinel-2 L2A', 'resolution': '10m', 'red': 'B04', 'nir': 'B08'},
            'landsat-c2-l2': {'name': 'Landsat Collection 2 L2', 'resolution': '30m', 'red': 'red', 'nir': 'nir08'},
        }

        veg_items, optical_items = [], []
        for item in stac_items:
            coll = item.get('collection', '').lower()
            if any(vp in coll for vp in veg_products):
                veg_items.append(item)
            elif any(op in coll for op in optical_products):
                optical_items.append(item)

        if optical_items and analysis_type in ['ndvi', 'general']:
            results.append("**[LEAF] NDVI Analysis from Optical Imagery:**\n")
            for item in optical_items[:3]:
                coll = item.get('collection', '').lower()
                props = item.get('properties', {})
                assets = item.get('assets', {})
                product_info = next((info for key, info in optical_products.items() if key in coll), None)
                if product_info:
                    results.append(f"**{product_info['name']}:** Item: {item.get('id')}")
                    if props.get('datetime'):
                        results.append(f"- Date: {props['datetime'][:10]}, Resolution: {product_info['resolution']}")
                    has_red = product_info['red'] in assets
                    has_nir = product_info['nir'] in assets
                    if has_red and has_nir:
                        results.append(f"- [OK] RED ({product_info['red']}) and NIR ({product_info['nir']}) available for NDVI")
                    if props.get('eo:cloud_cover') is not None:
                        results.append(f"- Cloud Cover: {props['eo:cloud_cover']:.1f}%")
                    results.append("")

            results.append("**NDVI Interpretation:** -1->0: Water/bare | 0->0.2: Sparse | 0.2->0.5: Moderate | 0.5->1.0: Dense\n")
            return "\n".join(results)

        if veg_items:
            results.append("**[LEAF] Vegetation Analysis Results:**\n")
            for item in veg_items[:3]:
                coll = item.get('collection', '').lower()
                props = item.get('properties', {})
                product_info = next((info for key, info in veg_products.items() if key in coll), None)
                if product_info:
                    results.append(f"**{product_info['name']}:**")
                    results.append(f"- Item: {item.get('id')}, Resolution: {product_info['resolution']}")
                    if props.get('datetime'):
                        results.append(f"- Date: {props['datetime'][:10]}")
                    results.append(f"- Metrics: {', '.join(product_info['metrics'])}")
                    results.append("")

        if not results:
            results.append("No vegetation data loaded. Use modis-13a1-061 for NDVI or optical imagery (HLS, Sentinel-2).")

        return "\n".join(results)

    except Exception as e:
        logger.error(f"[FAIL] analyze_vegetation failed: {e}")
        return f"Vegetation analysis failed: {str(e)}"


# ============================================================================
# TOOL 4: ANALYZE FIRE
# ============================================================================

def analyze_fire(analysis_type: str = "general") -> str:
    """Analyze fire activity and burn severity from MODIS fire products.
    Detects active fires, thermal anomalies, and burned areas.

    :param analysis_type: Type: 'active', 'thermal', 'burned', or 'general'
    :return: Fire detection results and interpretation
    """
    logger.info(f"[FIRE] analyze_fire(analysis_type='{analysis_type}')")
    ctx = _session_context
    stac_items = ctx.get('stac_items', [])
    collections = ctx.get('loaded_collections', [])

    if not collections:
        return "No fire data loaded. Load MODIS fire products first."

    fire_products = {
        'modis-14a1-061': {'name': 'MODIS Thermal Anomalies Daily (1km)', 'type': 'active_fire'},
        'modis-14a2-061': {'name': 'MODIS Thermal Anomalies 8-Day (1km)', 'type': 'active_fire'},
        'modis-64a1-061': {'name': 'MODIS Burned Area Monthly', 'type': 'burned_area'},
        'mtbs': {'name': 'Monitoring Trends in Burn Severity', 'type': 'burn_severity'},
    }

    fire_items = [i for i in stac_items if any(fp in i.get('collection', '').lower() for fp in fire_products)]
    results = []

    if fire_items:
        results.append("**[FIRE] Fire Analysis Results:**\n")
        for item in fire_items[:3]:
            coll = item.get('collection', '').lower()
            props = item.get('properties', {})
            product_info = next((info for key, info in fire_products.items() if key in coll), None)
            if product_info:
                results.append(f"**{product_info['name']}:**")
                results.append(f"- Item: {item.get('id')}")
                if props.get('datetime'):
                    results.append(f"- Date: {props['datetime'][:10]}")
                results.append(f"- Detection Type: {product_info['type'].replace('_', ' ').title()}")
                if product_info['type'] == 'active_fire':
                    results.append("- Confidence levels: Low/Nominal/High")
                    results.append("- Fire Radiative Power (FRP) in MW indicates intensity")
                if product_info['type'] in ['burned_area', 'burn_severity']:
                    results.append("- Severity: Unburned -> Low -> Moderate -> High")
                results.append("")
    else:
        results.append("No fire data loaded. Try modis-14a1-061 or mtbs.")

    return "\n".join(results)


# ============================================================================
# TOOL 5: ANALYZE LAND COVER
# ============================================================================

def analyze_land_cover(analysis_type: str = "general") -> str:
    """Analyze land cover and land use classification. Returns land cover types,
    urban areas, forest cover, and agricultural land percentages.

    :param analysis_type: Type: 'classification', 'urban', 'forest', 'agriculture', or 'general'
    :return: Land cover types and distributions
    """
    logger.info(f"[HOUSES] analyze_land_cover(analysis_type='{analysis_type}')")
    ctx = _session_context
    stac_items = ctx.get('stac_items', [])
    collections = ctx.get('loaded_collections', [])

    if not collections:
        return "No land cover data loaded."

    lc_products = {
        'esa-worldcover': {'name': 'ESA WorldCover 10m', 'resolution': '10m', 'classes': 11},
        'io-lulc': {'name': 'Esri Land Use/Land Cover', 'resolution': '10m', 'classes': 9},
        'usda-cdl': {'name': 'USDA Cropland Data Layer', 'resolution': '30m', 'classes': 130},
    }

    lc_items = [i for i in stac_items if any(lp in i.get('collection', '').lower() for lp in lc_products)]
    results = []

    if lc_items:
        results.append("**[HOUSES] Land Cover Analysis Results:**\n")
        for item in lc_items[:3]:
            coll = item.get('collection', '').lower()
            props = item.get('properties', {})
            product_info = next((info for key, info in lc_products.items() if key in coll), None)
            if product_info:
                results.append(f"**{product_info['name']}:**")
                results.append(f"- Item: {item.get('id')}, Resolution: {product_info['resolution']}")
                if props.get('datetime'):
                    results.append(f"- Date: {props['datetime'][:10]}")
                results.append(f"- Classes: Water, Trees, Grassland, Cropland, Built-up, Bare, Wetlands")
                results.append("")
    else:
        results.append("No land cover data loaded. Try esa-worldcover or usda-cdl.")

    return "\n".join(results)


# ============================================================================
# TOOL 6: ANALYZE SNOW
# ============================================================================

def analyze_snow(analysis_type: str = "general") -> str:
    """Analyze snow and ice cover from MODIS snow products.
    Use for snow, ice, glaciers, winter conditions, snow cover percentage.

    :param analysis_type: Type: 'cover', 'extent', 'albedo', or 'general'
    :return: Snow cover percentage and seasonal patterns
    """
    logger.info(f"[SNOW] analyze_snow(analysis_type='{analysis_type}')")
    ctx = _session_context
    stac_items = ctx.get('stac_items', [])
    collections = ctx.get('loaded_collections', [])

    if not collections:
        return "No snow data loaded."

    snow_products = {
        'modis-10a1-061': {'name': 'MODIS Snow Cover Daily (500m)', 'temporal': 'daily'},
        'modis-10a2-061': {'name': 'MODIS Snow Cover 8-Day (500m)', 'temporal': '8-day'},
    }

    snow_items = [i for i in stac_items if any(sp in i.get('collection', '').lower() for sp in snow_products)]
    results = []

    if snow_items:
        results.append("**[SNOW] Snow/Ice Analysis Results:**\n")
        for item in snow_items[:3]:
            coll = item.get('collection', '').lower()
            props = item.get('properties', {})
            product_info = next((info for key, info in snow_products.items() if key in coll), None)
            if product_info:
                results.append(f"**{product_info['name']}:**")
                results.append(f"- Item: {item.get('id')}")
                if props.get('datetime'):
                    results.append(f"- Date: {props['datetime'][:10]}")
                results.append(f"- NDSI Snow Cover: 0-100%")
                results.append("- 0-10%: Snow-free | 10-50%: Partial | 50-100%: Significant coverage")
                results.append("")
    else:
        results.append("No snow data loaded. Try modis-10a1-061 or modis-10a2-061.")

    return "\n".join(results)


# ============================================================================
# TOOL 7: ANALYZE SAR
# ============================================================================

def analyze_sar(analysis_type: str = "general") -> str:
    """Analyze Synthetic Aperture Radar (SAR) data from Sentinel-1 or ALOS PALSAR.
    Use for radar, backscatter, VV/VH polarization, flood detection, urban detection.
    Works through clouds.

    :param analysis_type: Type: 'backscatter', 'flood', 'change', or 'general'
    :return: SAR analysis results and interpretation
    """
    logger.info(f"[SIGNAL] analyze_sar(analysis_type='{analysis_type}')")
    ctx = _session_context
    stac_items = ctx.get('stac_items', [])
    collections = ctx.get('loaded_collections', [])

    if not collections:
        return "No SAR data loaded."

    sar_products = {
        'sentinel-1-grd': {'name': 'Sentinel-1 GRD', 'type': 'amplitude'},
        'sentinel-1-rtc': {'name': 'Sentinel-1 RTC', 'type': 'calibrated'},
        'alos-palsar-mosaic': {'name': 'ALOS PALSAR Annual Mosaic', 'type': 'L-band'},
    }

    sar_items = [i for i in stac_items if any(sp in i.get('collection', '').lower() for sp in sar_products)]
    results = []

    if sar_items:
        results.append("**[SIGNAL] SAR Analysis Results:**\n")
        for item in sar_items[:3]:
            coll = item.get('collection', '').lower()
            props = item.get('properties', {})
            assets = item.get('assets', {})
            product_info = next((info for key, info in sar_products.items() if key in coll), None)
            if product_info:
                results.append(f"**{product_info['name']}:**")
                results.append(f"- Item: {item.get('id')}, Type: {product_info['type']}")
                if props.get('datetime'):
                    results.append(f"- Date: {props['datetime'][:10]}")
                pols = [p for p in ['vv', 'vh', 'VV', 'VH'] if p in assets]
                if pols:
                    results.append(f"- Polarizations: {', '.join(p.upper() for p in pols)}")
                results.append("- Dark areas = smooth/water | Bright = rough/urban/forest")
                results.append("- Works through clouds!")
                results.append("")
    else:
        results.append("No SAR data loaded. Try sentinel-1-rtc or sentinel-1-grd.")

    return "\n".join(results)


# ============================================================================
# TOOL 8: ANALYZE WATER
# ============================================================================

def analyze_water(analysis_type: str = "general") -> str:
    """Analyze surface water and flooding from JRC GSW or SAR data.
    Use for water bodies, floods, lakes, rivers, wetlands, coastal areas.

    :param analysis_type: Type: 'occurrence', 'seasonality', 'change', 'flood', or 'general'
    :return: Water occurrence, seasonality, and flood detection results
    """
    logger.info(f"[DROP] analyze_water(analysis_type='{analysis_type}')")
    ctx = _session_context
    stac_items = ctx.get('stac_items', [])
    collections = ctx.get('loaded_collections', [])

    if not collections:
        return "No water data loaded."

    water_items, sar_items = [], []
    for item in stac_items:
        coll = item.get('collection', '').lower()
        if 'jrc' in coll or 'gsw' in coll or 'water' in coll:
            water_items.append(item)
        elif 'sentinel-1' in coll or 'sar' in coll:
            sar_items.append(item)

    results = []

    if water_items:
        results.append("**[DROP] Surface Water Analysis Results:**\n")
        for item in water_items[:3]:
            results.append(f"**JRC Global Surface Water:**")
            results.append(f"- Item: {item.get('id')}")
            results.append(f"- Resolution: 30m, Period: 1984-present")
            results.append("- Water Occurrence 0-100%: 0%=never water, 100%=permanent")
            results.append("- Seasonality: Permanent / Seasonal / Ephemeral")
            results.append("")
    elif sar_items:
        results.append("**[DROP] SAR-Based Water/Flood Analysis:**\n")
        for item in sar_items[:3]:
            results.append(f"**Sentinel-1 Water Detection:**")
            results.append(f"- Item: {item.get('id')}")
            results.append("- Dark areas = Water (specular reflection)")
            results.append("- VV: Best for calm water | VH: Flooded vegetation")
            results.append("- Works through clouds - ideal for floods!")
            results.append("")
    else:
        results.append("No water data loaded. Try jrc-gsw or sentinel-1-rtc for flood detection.")

    return "\n".join(results)


# ============================================================================
# TOOL 9: ANALYZE BIOMASS
# ============================================================================

def analyze_biomass(analysis_type: str = "general") -> str:
    """Analyze above-ground biomass from CHLORIS dataset.
    Returns biomass estimates in tonnes per hectare.

    :param analysis_type: Type: 'carbon', 'density', or 'general'
    :return: Biomass estimates and carbon stock interpretation
    """
    logger.info(f"[TREE] analyze_biomass(analysis_type='{analysis_type}')")
    ctx = _session_context
    stac_items = ctx.get('stac_items', [])
    collections = ctx.get('loaded_collections', [])

    if not collections:
        return "No biomass data loaded."

    biomass_items = [i for i in stac_items if any(k in i.get('collection', '').lower() for k in ['biomass', 'chloris'])]
    results = []

    if biomass_items:
        results.append("**[TREE] Biomass Analysis Results:**\n")
        for item in biomass_items[:3]:
            results.append(f"- Item: {item.get('id')}")
            results.append(f"- Unit: Mg/ha (tonnes per hectare)")
            results.append("- 0-50: Grassland | 50-150: Woodland | 150-300: Dense forest | 300+: Tropical rainforest")
            results.append("- Carbon ≈ Biomass × 0.47")
            results.append("")
    else:
        results.append("No biomass data loaded. Try chloris-biomass.")

    return "\n".join(results)


# ============================================================================
# TOOL 10: SAMPLE RASTER VALUE (most complex tool)
# ============================================================================

def sample_raster_value(data_type: str = "auto") -> str:
    """Extract the actual pixel/raster value from loaded satellite data at a specific
    location. Returns the numeric value (e.g., SST in Celsius, elevation in meters,
    NDVI, reflectance) at the pin/center coordinates. Use when the user asks for the
    value at a point, temperature at location, elevation at spot, etc.

    :param data_type: Type of data: 'sst', 'temperature', 'elevation', 'ndvi', 'burn', 'fire', 'water', 'snow', 'sar', 'biomass', 'reflectance', 'climate', or 'auto'
    :return: Numeric value with interpretation at the pin/center location
    """
    logger.info(f"[PIN] sample_raster_value(data_type='{data_type}')")
    ctx = _session_context

    bounds = ctx.get('map_bounds', {})
    if not bounds:
        return "No location available. Please set a pin or center the map."

    lat = bounds.get('pin_lat') or bounds.get('center_lat')
    lng = bounds.get('pin_lng') or bounds.get('center_lng')
    if lat is None or lng is None:
        return "No coordinates available. Please pin a location on the map."

    stac_items = list(ctx.get('stac_items', []))
    tile_urls = ctx.get('tile_urls', [])
    collections = ctx.get('loaded_collections', [])

    # If no STAC items but have tile_urls, fetch from tile URLs
    if not stac_items and tile_urls:
        for tile_url in tile_urls[:5]:
            try:
                parsed = _parse_tile_url(tile_url)
                if parsed.get('collection') and parsed.get('item'):
                    item = _fetch_stac_item_sync(parsed['collection'], parsed['item'])
                    if item:
                        stac_items.append(item)
                        break
            except Exception:
                pass

    if not stac_items:
        return f"No STAC items available to sample. Collections: {collections}"

    try:
        results = [f"**Point Sampling at ({lat:.4f}°, {lng:.4f}°):**\n"]

        # Determine target items and transforms based on data_type
        target_items = []
        asset_keys = []
        value_transforms = []

        # SST/temperature
        if data_type in ['sst', 'temperature', 'auto']:
            sst_keywords = ['sea-surface-temperature', 'sst', 'temperature-whoi', 'noaa-cdr']
            for item in stac_items:
                coll = item.get('collection', '').lower()
                if any(kw in coll for kw in sst_keywords) or 'temperature' in coll:
                    target_items.append(item)
                    asset_keys.append('sea_surface_temperature')
                    value_transforms.append({
                        'name': 'Sea Surface Temperature', 'unit_raw': '°C',
                        'unit_display': '°C', 'transform': lambda v: v, 'valid_range': (-2, 40)
                    })

        # DEM/elevation
        if data_type in ['elevation', 'height', 'auto'] and not target_items:
            for item in stac_items:
                coll = item.get('collection', '').lower()
                if 'dem' in coll or 'elevation' in coll or 'cop-dem' in coll or '3dep' in coll:
                    assets = item.get('assets', {})
                    target_items.append(item)
                    asset_keys.append('data' if 'data' in assets else (list(assets.keys())[0] if assets else 'data'))
                    name = 'Height Above Ground' if '3dep' in coll else 'Elevation'
                    value_transforms.append({
                        'name': name, 'unit_raw': 'm', 'unit_display': 'm',
                        'transform': lambda v: v, 'valid_range': (-500, 9000)
                    })

        # NDVI from optical
        if data_type in ['ndvi', 'auto'] and not target_items:
            optical_keywords = ['sentinel-2', 'landsat', 'hls', 's30', 'l30']
            for item in stac_items:
                coll = item.get('collection', '').lower()
                if any(kw in coll for kw in optical_keywords):
                    assets = item.get('assets', {})
                    red_key = 'B04' if 'B04' in assets else ('red' if 'red' in assets else None)
                    nir_key = None
                    for candidate in ['B08', 'B8A', 'B05', 'nir08', 'nir']:
                        if candidate in assets:
                            nir_key = candidate
                            break
                    if red_key and nir_key:
                        target_items.append(item)
                        asset_keys.append((red_key, nir_key))
                        value_transforms.append({
                            'name': 'NDVI', 'unit_raw': 'index', 'unit_display': '',
                            'is_ndvi': True, 'valid_range': (-1, 1)
                        })

        # MTBS Burn Severity
        if data_type in ['burn', 'severity', 'mtbs', 'fire', 'auto'] and not target_items:
            for item in stac_items:
                coll = item.get('collection', '').lower()
                if 'mtbs' in coll or 'burn' in coll:
                    assets = item.get('assets', {})
                    target_items.append(item)
                    asset_keys.append('burn-severity' if 'burn-severity' in assets else 'data')
                    value_transforms.append({
                        'name': 'Burn Severity Class', 'unit_raw': 'class', 'unit_display': '',
                        'transform': lambda v: v, 'valid_range': (0, 6),
                        'class_labels': {1: 'Unburned to Low', 2: 'Low', 3: 'Moderate', 4: 'High',
                                         5: 'Increased Greenness', 6: 'Non-Processing Area'}
                    })

        # MODIS Fire — sample BOTH MaxFRP and FireMask when available
        if data_type in ['fire', 'thermal', 'auto'] and not target_items:
            for item in stac_items:
                coll = item.get('collection', '').lower()
                if 'modis-14' in coll or 'fire' in coll:
                    assets = item.get('assets', {})
                    # Always sample MaxFRP first (actual Fire Radiative Power in MW)
                    if 'MaxFRP' in assets:
                        target_items.append(item)
                        asset_keys.append('MaxFRP')
                        value_transforms.append({
                            'name': 'Fire Radiative Power (MaxFRP)', 'unit_raw': 'MW',
                            'unit_display': 'MW',
                            'transform': lambda v: round(v, 1) if v else v,
                            'valid_range': (0, 5000)
                        })
                    # Also sample FireMask (fire detection class)
                    if 'FireMask' in assets:
                        target_items.append(item)
                        asset_keys.append('FireMask')
                        value_transforms.append({
                            'name': 'Fire Detection Class', 'unit_raw': 'class',
                            'unit_display': '',
                            'transform': lambda v: v, 'valid_range': (0, 9),
                            'class_labels': {0: 'Not processed', 3: 'Non-fire water', 4: 'Cloud',
                                             5: 'Non-fire land', 7: 'Low confidence fire',
                                             8: 'Nominal confidence fire', 9: 'High confidence fire'}
                        })
                    # Fallback to generic 'data' asset
                    if not any(k in assets for k in ['MaxFRP', 'FireMask']):
                        target_items.append(item)
                        asset_keys.append('data')
                        value_transforms.append({
                            'name': 'Fire Detection', 'unit_raw': 'class', 'unit_display': '',
                            'transform': lambda v: v, 'valid_range': (0, 9),
                            'class_labels': {0: 'Not processed', 3: 'Non-fire water', 4: 'Cloud',
                                             5: 'Non-fire land', 7: 'Low confidence fire',
                                             8: 'Nominal confidence fire', 9: 'High confidence fire'}
                        })

        # JRC Water
        if data_type in ['water', 'occurrence', 'jrc', 'auto'] and not target_items:
            for item in stac_items:
                coll = item.get('collection', '').lower()
                assets = item.get('assets', {})
                if 'jrc' in coll or 'gsw' in coll or 'surface-water' in coll or 'occurrence' in assets:
                    asset_key = next((k for k in ['occurrence', 'extent', 'seasonality', 'data'] if k in assets), 'data')
                    target_items.append(item)
                    asset_keys.append(asset_key)
                    value_transforms.append({
                        'name': 'Water Occurrence', 'unit_raw': '%', 'unit_display': '%',
                        'transform': lambda v: v, 'valid_range': (0, 100)
                    })

        # MODIS Snow
        if data_type in ['snow', 'ice', 'auto'] and not target_items:
            for item in stac_items:
                coll = item.get('collection', '').lower()
                if 'modis-10' in coll or 'snow' in coll:
                    assets = item.get('assets', {})
                    target_items.append(item)
                    asset_keys.append('NDSI_Snow_Cover' if 'NDSI_Snow_Cover' in assets else 'data')
                    value_transforms.append({
                        'name': 'Snow Cover', 'unit_raw': '%', 'unit_display': '%',
                        'transform': lambda v: v, 'valid_range': (0, 100)
                    })

        # Land Cover
        _ESA_WORLDCOVER_CLASSES = {
            10: 'Tree Cover', 20: 'Shrubland', 30: 'Grassland',
            40: 'Cropland', 50: 'Built-up', 60: 'Bare / Sparse Vegetation',
            70: 'Snow and Ice', 80: 'Permanent Water Bodies',
            90: 'Herbaceous Wetland', 95: 'Mangroves', 100: 'Moss and Lichen',
        }
        _IO_LULC_CLASSES = {
            1: 'No Data', 2: 'Water', 4: 'Flooded Vegetation', 5: 'Crops',
            7: 'Built Area', 8: 'Bare Ground', 9: 'Snow/Ice',
            10: 'Clouds', 11: 'Rangeland',
        }
        _NOAA_CCAP_CLASSES = {
            2: 'High Intensity Developed', 3: 'Medium Intensity Developed',
            4: 'Low Intensity Developed', 5: 'Developed Open Space',
            6: 'Cultivated Land', 7: 'Pasture/Hay',
            8: 'Grassland', 9: 'Deciduous Forest', 10: 'Evergreen Forest',
            11: 'Mixed Forest', 12: 'Scrub/Shrub', 13: 'Palustrine Forested Wetland',
            14: 'Palustrine Scrub/Shrub Wetland', 15: 'Palustrine Emergent Wetland',
            16: 'Estuarine Forested Wetland', 17: 'Estuarine Scrub/Shrub Wetland',
            18: 'Estuarine Emergent Wetland', 19: 'Unconsolidated Shore',
            20: 'Bare Land', 21: 'Open Water', 22: 'Palustrine Aquatic Bed',
            23: 'Estuarine Aquatic Bed', 25: 'Tundra',
        }

        _LANDCOVER_KEYWORDS = [
            'cdl', 'cropland', 'land-cover', 'worldcover', 'lulc',
            'noaa-c-cap', 'chesapeake', 'nrcan', 'drcog', 'esa-cci-lc',
        ]

        if data_type in ['landcover', 'cdl', 'crop', 'auto'] and not target_items:
            for item in stac_items:
                coll = item.get('collection', '').lower()
                if any(kw in coll for kw in _LANDCOVER_KEYWORDS):
                    assets = item.get('assets', {})
                    # Pick the best asset key for land cover raster
                    asset_key_lc = 'map' if 'map' in assets else ('data' if 'data' in assets else (list(assets.keys())[0] if assets else 'data'))
                    target_items.append(item)
                    asset_keys.append(asset_key_lc)
                    # Select the right class label table
                    if 'worldcover' in coll:
                        labels = _ESA_WORLDCOVER_CLASSES
                        name = 'ESA WorldCover'
                    elif 'io-lulc' in coll or 'lulc' in coll:
                        labels = _IO_LULC_CLASSES
                        name = 'Land Use / Land Cover'
                    elif 'noaa-c-cap' in coll:
                        labels = _NOAA_CCAP_CLASSES
                        name = 'NOAA C-CAP Coastal Land Cover'
                    else:
                        labels = None
                        name = 'Land Cover Class'
                    value_transforms.append({
                        'name': name, 'unit_raw': 'class', 'unit_display': '',
                        'transform': lambda v: v, 'valid_range': (0, 255),
                        'is_classification': True, 'class_labels': labels,
                    })

        # Biomass
        if data_type in ['biomass', 'carbon', 'auto'] and not target_items:
            for item in stac_items:
                coll = item.get('collection', '').lower()
                if 'biomass' in coll or 'chloris' in coll:
                    assets = item.get('assets', {})
                    asset_key = next((k for k in ['biomass_wm', 'biomass', 'aboveground', 'agb', 'data'] if k in assets), 'data')
                    target_items.append(item)
                    asset_keys.append(asset_key)
                    pixel_area_ha = 2146
                    value_transforms.append({
                        'name': 'Above-Ground Biomass', 'unit_raw': 'tonnes (total per pixel)',
                        'unit_display': 'Mg/ha', 'transform': lambda v, a=pixel_area_ha: round(v / a, 1) if v else v,
                        'valid_range': (0, 500)
                    })

        # MODIS Vegetation (NDVI, LAI, GPP, NPP)
        if data_type in ['vegetation', 'lai', 'gpp', 'npp', 'auto'] and not target_items:
            for item in stac_items:
                coll = item.get('collection', '').lower()
                if 'modis-13' in coll or 'modis-15' in coll or 'modis-17' in coll:
                    assets = item.get('assets', {})
                    if '250m_16_days_NDVI' in assets:
                        ak, nm, tf = '250m_16_days_NDVI', 'NDVI', lambda v: v * 0.0001 if v else v
                    elif 'Lai_500m' in assets:
                        ak, nm, tf = 'Lai_500m', 'LAI', lambda v: v * 0.1 if v else v
                    elif 'Gpp_500m' in assets:
                        ak, nm, tf = 'Gpp_500m', 'GPP', lambda v: v * 0.0001 if v else v
                    elif 'Npp_500m' in assets:
                        ak, nm, tf = 'Npp_500m', 'NPP', lambda v: v * 0.0001 if v else v
                    else:
                        ak = list(assets.keys())[0] if assets else 'data'
                        nm, tf = 'MODIS Vegetation', lambda v: v
                    target_items.append(item)
                    asset_keys.append(ak)
                    value_transforms.append({'name': nm, 'unit_raw': 'scaled', 'unit_display': '', 'transform': tf, 'valid_range': None})

        # SAR/Radar
        if data_type in ['sar', 'radar', 'backscatter', 'water', 'auto'] and not target_items:
            for item in stac_items:
                coll = item.get('collection', '').lower()
                assets = item.get('assets', {})
                if 'sentinel-1' in coll or 'alos-palsar' in coll or 'sar' in coll or 'rtc' in coll:
                    for sar_key in ['vv', 'vh', 'hh', 'hv', 'VV', 'VH', 'HH', 'HV']:
                        if sar_key in assets:
                            target_items.append(item)
                            asset_keys.append(sar_key)
                            value_transforms.append({
                                'name': f'SAR Backscatter ({sar_key.upper()})', 'unit_raw': 'linear',
                                'unit_display': 'dB',
                                'transform': lambda v: 10 * math.log10(v) if v and v > 0 else v,
                                'valid_range': (-30, 10)
                            })
                            break

        # Reflectance (MODIS BRDF / HLS)
        if data_type in ['reflectance', 'brdf', 'surface', 'auto'] and not target_items:
            for item in stac_items:
                coll = item.get('collection', '').lower()
                assets = item.get('assets', {})
                if 'modis-43' in coll or 'brdf' in coll:
                    # Sample ALL available BRDF bands (1-7), not just the first one
                    for band_num in range(1, 8):
                        bk = f'Nadir_Reflectance_Band{band_num}'
                        if bk in assets:
                            target_items.append(item)
                            asset_keys.append(bk)
                            # Use default arg to capture band_num in closure
                            value_transforms.append({
                                'name': f'BRDF Reflectance Band {band_num}', 'unit_raw': 'scaled',
                                'unit_display': 'reflectance', 'transform': lambda v: v * 0.0001 if v else v,
                                'valid_range': (0, 10000)
                            })
                    if target_items:
                        break  # Found bands in this item, don't check other items
                elif 'hls' in coll or 's30' in coll or 'l30' in coll:
                    for bk in ['B04', 'B03', 'B02', 'B05', 'B08']:
                        if bk in assets:
                            target_items.append(item)
                            asset_keys.append(bk)
                            value_transforms.append({
                                'name': f'Surface Reflectance ({bk})', 'unit_raw': 'scaled',
                                'unit_display': 'reflectance', 'transform': lambda v: v * 0.0001 if v else v,
                                'valid_range': (0, 10000)
                            })
                            break

        # 3DEP LiDAR
        if data_type in ['lidar', 'hag', '3dep', 'auto'] and not target_items:
            for item in stac_items:
                coll = item.get('collection', '').lower()
                if '3dep' in coll or 'lidar' in coll or 'hag' in coll:
                    assets = item.get('assets', {})
                    target_items.append(item)
                    asset_keys.append('data' if 'data' in assets else (list(assets.keys())[0] if assets else 'data'))
                    value_transforms.append({
                        'name': 'Height Above Ground', 'unit_raw': 'm', 'unit_display': 'm',
                        'transform': lambda v: v, 'valid_range': (0, 500)
                    })

        # Climate Projections (NEX-GDDP-CMIP6) — NetCDF assets, not COG
        if data_type in ['climate', 'auto'] and not target_items:
            climate_var_info = {
                'tas': {'name': 'Daily Near-Surface Air Temperature', 'unit': 'K', 'display_unit': '°C', 'kelvin': True},
                'tasmax': {'name': 'Daily Maximum Temperature', 'unit': 'K', 'display_unit': '°C', 'kelvin': True},
                'tasmin': {'name': 'Daily Minimum Temperature', 'unit': 'K', 'display_unit': '°C', 'kelvin': True},
                'pr': {'name': 'Precipitation', 'unit': 'kg m-2 s-1', 'display_unit': 'mm/day', 'kelvin': False},
                'hurs': {'name': 'Near-Surface Relative Humidity', 'unit': '%', 'display_unit': '%', 'kelvin': False},
                'huss': {'name': 'Near-Surface Specific Humidity', 'unit': '1', 'display_unit': 'kg/kg', 'kelvin': False},
                'sfcWind': {'name': 'Near-Surface Wind Speed', 'unit': 'm/s', 'display_unit': 'm/s', 'kelvin': False},
                'rlds': {'name': 'Downwelling Longwave Radiation', 'unit': 'W/m²', 'display_unit': 'W/m²', 'kelvin': False},
                'rsds': {'name': 'Downwelling Shortwave Radiation', 'unit': 'W/m²', 'display_unit': 'W/m²', 'kelvin': False},
            }
            for item in stac_items:
                coll = item.get('collection', '').lower()
                if 'nex-gddp' in coll or 'cmip6' in coll:
                    assets = item.get('assets', {})
                    # Pick the best variable: tasmax > tas > pr > sfcWind > first available
                    preferred_order = ['tasmax', 'tas', 'pr', 'sfcWind', 'hurs', 'rlds', 'rsds', 'huss', 'tasmin']
                    chosen_var = None
                    for var in preferred_order:
                        if var in assets:
                            chosen_var = var
                            break
                    if not chosen_var and assets:
                        chosen_var = next((k for k in assets if k in climate_var_info), None)
                    if chosen_var:
                        var_info = climate_var_info.get(chosen_var, {'name': chosen_var, 'unit': 'raw', 'display_unit': '', 'kelvin': False})
                        target_items.append(item)
                        asset_keys.append(chosen_var)
                        if var_info['kelvin']:
                            value_transforms.append({
                                'name': var_info['name'], 'unit_raw': 'K',
                                'unit_display': '°C', 'transform': lambda v: round(v - 273.15, 1) if v else v,
                                'valid_range': (150, 350), 'is_netcdf': True
                            })
                        elif chosen_var == 'pr':
                            value_transforms.append({
                                'name': var_info['name'], 'unit_raw': 'kg m-2 s-1',
                                'unit_display': 'mm/day', 'transform': lambda v: round(v * 86400, 2) if v else v,
                                'valid_range': (0, 1), 'is_netcdf': True
                            })
                        else:
                            value_transforms.append({
                                'name': var_info['name'], 'unit_raw': var_info['unit'],
                                'unit_display': var_info['display_unit'], 'transform': lambda v: round(v, 2) if v else v,
                                'valid_range': None, 'is_netcdf': True
                            })
                    break  # One climate item is enough

        # Generic fallback
        if not target_items and stac_items:
            for item in stac_items:
                assets = item.get('assets', {})
                coll = item.get('collection', 'unknown')
                for asset_key, asset_info in assets.items():
                    asset_type = asset_info.get('type', '') if isinstance(asset_info, dict) else ''
                    is_raster = asset_type.startswith('image/tiff') or asset_type.startswith('application/x-geotiff')
                    is_common = asset_key.lower() in ['data', 'visual', 'default', 'occurrence', 'extent']
                    if is_raster or is_common:
                        target_items.append(item)
                        asset_keys.append(asset_key)
                        value_transforms.append({
                            'name': f'{coll} - {asset_key}', 'unit_raw': 'raw', 'unit_display': '',
                            'transform': lambda v: v, 'valid_range': None
                        })
                        break

        if not target_items:
            return f"No {data_type} data loaded to sample. Collections: {collections}"

        # Tile selection: sort by whether pin is in bbox
        def point_in_bbox(lt, ln, bbox):
            if not bbox or len(bbox) < 4:
                return True
            return bbox[0] <= ln <= bbox[2] and bbox[1] <= lt <= bbox[3]

        items_in = [(it, ak, tf) for it, ak, tf in zip(target_items, asset_keys, value_transforms) if point_in_bbox(lat, lng, it.get('bbox'))]
        items_out = [(it, ak, tf) for it, ak, tf in zip(target_items, asset_keys, value_transforms) if not point_in_bbox(lat, lng, it.get('bbox'))]
        sorted_data = items_in + items_out

        # Track whether the original query was NDVI (for fallback awareness)
        is_ndvi_sampling = any(tf.get('is_ndvi') for tf in value_transforms)

        # Fallback STAC search if no tiles contain pin
        if not items_in and items_out:
            collection_id = items_out[0][0].get('collection', '')
            if collection_id:
                try:
                    import httpx
                    import planetary_computer as pc
                    buf = 0.5
                    pin_bbox = [lng - buf, lat - buf, lng + buf, lat + buf]
                    is_optical_coll = any(kw in collection_id.lower() for kw in ['sentinel-2', 'landsat', 'hls', 's30', 'l30'])
                    search_body = {"collections": [collection_id], "bbox": pin_bbox, "limit": 10}
                    if is_optical_coll:
                        search_body["query"] = {"eo:cloud_cover": {"lt": 20}}
                        search_body["sortby"] = [{"field": "properties.datetime", "direction": "desc"}]
                    with httpx.Client(timeout=30) as http_client:
                        resp = http_client.post(
                            "https://planetarycomputer.microsoft.com/api/stac/v1/search",
                            json=search_body,
                            headers={"Content-Type": "application/json"}
                        )
                        if resp.status_code == 200:
                            for feature in resp.json().get("features", []):
                                if point_in_bbox(lat, lng, feature.get('bbox')):
                                    try:
                                        signed = pc.sign(feature)
                                    except Exception:
                                        signed = feature
                                    assets = signed.get('assets', {})
                                    ak = None
                                    tf_info = None
                                    # NDVI-aware fallback: detect red/NIR bands
                                    if is_ndvi_sampling:
                                        red_key = 'B04' if 'B04' in assets else ('red' if 'red' in assets else None)
                                        nir_key = None
                                        for candidate in ['B08', 'B8A', 'B05', 'nir08', 'nir']:
                                            if candidate in assets:
                                                nir_key = candidate
                                                break
                                        if red_key and nir_key:
                                            ak = (red_key, nir_key)
                                            tf_info = {
                                                'name': 'NDVI', 'unit_raw': 'index', 'unit_display': '',
                                                'is_ndvi': True, 'valid_range': (-1, 1)
                                            }
                                    elif 'dem' in collection_id.lower() or 'cop-dem' in collection_id.lower():
                                        ak = 'data'
                                        tf_info = {'name': 'Elevation', 'unit_raw': 'm', 'unit_display': 'meters',
                                                   'transform': lambda v: v, 'valid_range': (-500, 9000)}
                                    else:
                                        for k in ['data', 'visual', 'default']:
                                            if k in assets:
                                                ak = k
                                                tf_info = {'name': collection_id, 'unit_raw': 'raw', 'unit_display': '',
                                                           'transform': lambda v: v, 'valid_range': None}
                                                break
                                    if ak and tf_info:
                                        # For tuple NDVI keys, check both bands exist
                                        if isinstance(ak, tuple):
                                            if ak[0] in assets and ak[1] in assets:
                                                sorted_data.insert(0, (signed, ak, tf_info))
                                        elif ak in assets:
                                            sorted_data.insert(0, (signed, ak, tf_info))
                except Exception as e:
                    logger.error(f"Fallback STAC search error: {e}")

        # Sample each target
        sampled_count = 0
        max_samples = 7  # Allow up to 7 bands for multi-band reflectance (MODIS BRDF has bands 1-7)
        
        # Detailed failure tracking for accurate error messages
        nodata_tiles = []       # Tiles where pixel was masked (cloud/shadow/water/snow)
        outside_tiles = []      # Tiles where pin is outside the raster extent
        error_tiles = []        # Tiles that failed due to HTTP/access errors
        tile_cloud_covers = []  # Cloud cover % for each attempted tile

        for i, (item, asset_key, transform_info) in enumerate(sorted_data[:8]):
            if sampled_count >= max_samples:
                break
            if i > 0:
                time.sleep(0.05)  # Brief pause to avoid rate-limiting (was 0.5s)

            props = item.get('properties', {})
            assets = item.get('assets', {})
            collection = item.get('collection', 'unknown')
            tile_date = (props.get('datetime') or '')[:10]
            tile_cloud = props.get('eo:cloud_cover')
            tile_id_short = item.get('id', 'unknown')[:30]

            # NDVI special case (two bands)
            if transform_info.get('is_ndvi') and isinstance(asset_key, tuple):
                red_key, nir_key = asset_key
                red_url = assets.get(red_key, {}).get('href')
                nir_url = assets.get(nir_key, {}).get('href')
                if red_url and nir_url:
                    red_result = _sample_cog_sync(red_url, lat, lng)
                    nir_result = _sample_cog_sync(nir_url, lat, lng)

                    if red_result.get('error') and 'outside' in str(red_result['error']).lower():
                        outside_tiles.append({'id': tile_id_short, 'date': tile_date})
                        continue
                    if nir_result.get('error') and 'outside' in str(nir_result['error']).lower():
                        outside_tiles.append({'id': tile_id_short, 'date': tile_date})
                        continue
                    if red_result.get('error') and 'no data' in str(red_result['error']).lower():
                        nodata_tiles.append({'id': tile_id_short, 'date': tile_date, 'cloud_cover': tile_cloud})
                        if tile_cloud is not None:
                            tile_cloud_covers.append(tile_cloud)
                        continue
                    if nir_result.get('error') and 'no data' in str(nir_result['error']).lower():
                        nodata_tiles.append({'id': tile_id_short, 'date': tile_date, 'cloud_cover': tile_cloud})
                        if tile_cloud is not None:
                            tile_cloud_covers.append(tile_cloud)
                        continue

                    if red_result.get('value') is not None and nir_result.get('value') is not None:
                        red_val = float(red_result['value'])
                        nir_val = float(nir_result['value'])
                        if (nir_val + red_val) != 0:
                            ndvi = max(-1, min(1, (nir_val - red_val) / (nir_val + red_val)))
                            results.append(f"**NDVI at Pin ({collection}):**")
                            results.append(f"- RED ({red_key}): {red_val:.0f}, NIR ({nir_key}): {nir_val:.0f}")
                            results.append(f"- **NDVI Value: {ndvi:.3f}**")
                            if ndvi > 0.6: interp = "Dense, healthy vegetation"
                            elif ndvi > 0.4: interp = "Moderate vegetation"
                            elif ndvi > 0.2: interp = "Sparse or stressed vegetation"
                            elif ndvi > 0: interp = "Minimal vegetation, bare soil"
                            else: interp = "Water, snow, or non-vegetated"
                            results.append(f"- Interpretation: {interp}")
                            if props.get('datetime'):
                                results.append(f"- Date: {props['datetime'][:10]}")
                            sampled_count += 1
                results.append("")
                continue

            # NetCDF climate data special case (NEX-GDDP-CMIP6)
            if transform_info.get('is_netcdf'):
                nc_href = assets.get(asset_key, {}).get('href', '') if isinstance(assets.get(asset_key), dict) else ''
                if nc_href:
                    try:
                        import planetary_computer as pc
                        signed_url = pc.sign(nc_href) if 'blob.core.windows.net' in nc_href else nc_href
                        # Use rasterio's NETCDF driver — read the last band (most recent day)
                        import rasterio
                        netcdf_path = f"NETCDF:{signed_url}:{asset_key}"
                        env_options = {
                            'GDAL_DISABLE_READDIR_ON_OPEN': 'EMPTY_DIR',
                            'GDAL_HTTP_TIMEOUT': '60',
                            'GDAL_HTTP_MAX_RETRY': '3',
                        }
                        with rasterio.Env(**env_options):
                            with rasterio.open(netcdf_path) as src:
                                # NEX-GDDP lon is 0-360; convert if needed
                                sample_lng = lng if lng >= 0 else lng + 360
                                try:
                                    row, col = src.index(sample_lng, lat)
                                except Exception:
                                    results.append(f"**{transform_info['name']} ({collection}):** Coordinate outside grid")
                                    continue
                                if row < 0 or row >= src.height or col < 0 or col >= src.width:
                                    outside_tiles.append({'id': tile_id_short, 'date': tile_date})
                                    continue
                                # Read last band (most recent day in the year)
                                last_band = src.count
                                from rasterio.windows import Window
                                window = Window(col, row, 1, 1)
                                data = src.read(last_band, window=window)
                                raw_value = float(data[0, 0])
                                nodata = src.nodata
                                if nodata is not None and raw_value == nodata:
                                    nodata_tiles.append({'id': tile_id_short, 'date': tile_date, 'cloud_cover': None})
                                    continue
                                try:
                                    display_value = transform_info['transform'](raw_value)
                                except Exception:
                                    display_value = raw_value
                                model_scenario = tile_id_short  # e.g. "ACCESS-CM2.ssp585.2050"
                                results.append(f"**{transform_info['name']} ({collection}):**")
                                results.append(f"- Raw value: {raw_value:.4f} {transform_info['unit_raw']}")
                                results.append(f"- **Converted: {display_value} {transform_info['unit_display']}**")
                                results.append(f"- Model/Scenario: {model_scenario}")
                                results.append(f"- Grid resolution: 0.25° × 0.25°")
                                results.append(f"- Band sampled: {last_band} (last day in file)")
                                if tile_date:
                                    results.append(f"- Year: {tile_date[:4]}")
                                sampled_count += 1
                    except Exception as e:
                        logger.warning(f"[WARN] NetCDF sampling failed for {collection}/{asset_key}: {e}")
                        # Provide descriptive context even on failure
                        item_id = item.get('id', '')
                        parts = item_id.split('.')
                        model_name = parts[0] if parts else 'Unknown'
                        scenario = parts[1] if len(parts) > 1 else 'Unknown'
                        year = parts[2] if len(parts) > 2 else 'Unknown'
                        results.append(f"**{transform_info['name']} ({collection}):**")
                        results.append(f"- [WARN] Direct NetCDF sampling not available (data is not COG-optimized)")
                        results.append(f"- Variable: {asset_key} ({transform_info['name']})")
                        results.append(f"- Model: {model_name}, Scenario: {scenario}, Year: {year}")
                        results.append(f"- Unit: {transform_info['unit_raw']} -> {transform_info['unit_display']}")
                        results.append(f"- Resolution: 0.25° × 0.25° global grid")
                        results.append(f"- This is a CMIP6 climate **projection**, not observed data")
                        error_tiles.append({'id': tile_id_short, 'date': tile_date, 'error': f'NetCDF: {e}'})
                else:
                    results.append(f"**{transform_info['name']}:** No asset URL for variable '{asset_key}'")
                results.append("")
                continue

            # Standard single-band sampling
            cog_url = None
            if asset_key in assets:
                cog_url = assets[asset_key].get('href')
            if not cog_url:
                for fk in ['data', 'visual', 'default']:
                    if fk in assets:
                        ai = assets[fk]
                        if ai.get('type', '').startswith('image/tiff') or ai.get('href', '').endswith('.tif'):
                            cog_url = ai.get('href')
                            break
            if not cog_url:
                continue

            sample_result = _sample_cog_sync(cog_url, lat, lng)

            if sample_result.get('error'):
                err = str(sample_result['error']).lower()
                if 'outside' in err or 'pixel bounds' in err:
                    outside_tiles.append({'id': tile_id_short, 'date': tile_date})
                    continue
                if 'no data' in err or 'nodata' in err:
                    nodata_tiles.append({'id': tile_id_short, 'date': tile_date, 'cloud_cover': tile_cloud})
                    if tile_cloud is not None:
                        tile_cloud_covers.append(tile_cloud)
                    continue
                # HTTP/access/timeout errors
                error_tiles.append({'id': tile_id_short, 'date': tile_date, 'error': sample_result['error']})
                logger.warning(f"[WARN] COG sampling error for {tile_id_short}: {sample_result['error']}")
            elif sample_result.get('value') is not None:
                raw_value = sample_result['value']
                try:
                    display_value = transform_info['transform'](raw_value)
                except Exception:
                    display_value = raw_value

                results.append(f"**{transform_info['name']} ({collection}):**")

                class_labels = transform_info.get('class_labels')
                if class_labels:
                    int_val = int(round(raw_value))
                    results.append(f"- Class: **{int_val}** — {class_labels.get(int_val, f'Unknown class {int_val}')}")
                else:
                    if transform_info['unit_raw'] != transform_info['unit_display']:
                        results.append(f"- Raw: {raw_value:.2f} {transform_info['unit_raw']}")
                        results.append(f"- Converted: **{display_value:.2f} {transform_info['unit_display']}**")
                    else:
                        results.append(f"- Value: **{display_value:.2f} {transform_info['unit_display']}**")

                    # Interpretations
                    name_lower = transform_info['name'].lower()
                    if 'water' in name_lower or 'occurrence' in name_lower:
                        pct = float(raw_value)
                        if pct == 0: results.append("- [DESERT] Never water")
                        elif pct < 25: results.append(f"- [DROP] Rarely water ({pct:.0f}%)")
                        elif pct < 75: results.append(f"- [WAVE] Often water ({pct:.0f}%)")
                        else: results.append(f"- [WAVE][WAVE] Permanent water ({pct:.0f}%)")
                    elif 'snow' in name_lower:
                        pct = float(raw_value)
                        if pct == 0: results.append("- [SUN] No snow")
                        elif pct < 25: results.append(f"- [SNOW] Light snow ({pct:.0f}%)")
                        elif pct < 75: results.append(f"- [SNOW][SNOW] Moderate snow ({pct:.0f}%)")
                        else: results.append(f"- [SNOW][SNOW][SNOW] Heavy snow ({pct:.0f}%)")

                if props.get('datetime'):
                    results.append(f"- Date: {props['datetime'][:10]}")
                sampled_count += 1
            results.append("")

        # ── Clear-sky fallback: search for un-masked tiles when all loaded ones failed ──
        if sampled_count == 0 and stac_items:
            collection_id = stac_items[0].get('collection', '')
            is_optical_coll = any(kw in collection_id.lower() for kw in ['sentinel-2', 'landsat', 'hls', 's30', 'l30'])
            if collection_id and (is_ndvi_sampling or is_optical_coll):
                try:
                    import httpx
                    import planetary_computer as pc
                    buf = 0.05  # ~5km buffer around pin
                    pin_bbox = [lng - buf, lat - buf, lng + buf, lat + buf]
                    already_tried = {item.get('id', '') for item in stac_items}
                    # Also include items from sorted_data (fallback search may have added them)
                    for sd_item, _, _ in sorted_data:
                        already_tried.add(sd_item.get('id', ''))

                    search_body = {
                        "collections": [collection_id],
                        "bbox": pin_bbox,
                        "limit": 10,
                        "query": {"eo:cloud_cover": {"lt": 15}},
                        "sortby": [{"field": "properties.datetime", "direction": "desc"}]
                    }
                    logger.info(f"[PIN] Clear-sky fallback search: collection={collection_id}, bbox={pin_bbox}")

                    with httpx.Client(timeout=30) as http_client:
                        resp = http_client.post(
                            "https://planetarycomputer.microsoft.com/api/stac/v1/search",
                            json=search_body,
                            headers={"Content-Type": "application/json"}
                        )

                        if resp.status_code == 200:
                            features = resp.json().get("features", [])
                            logger.info(f"[PIN] Clear-sky fallback found {len(features)} candidates")

                            for feature in features:
                                if sampled_count >= 1:
                                    break
                                fid = feature.get('id', '')
                                if fid in already_tried:
                                    continue
                                if not point_in_bbox(lat, lng, feature.get('bbox')):
                                    continue

                                try:
                                    signed = pc.sign(feature)
                                except Exception:
                                    signed = feature

                                f_assets = signed.get('assets', {})
                                f_props = signed.get('properties', {})
                                f_date = (f_props.get('datetime') or '')[:10]
                                f_cloud = f_props.get('eo:cloud_cover')
                                f_id_short = fid[:30]

                                if is_ndvi_sampling:
                                    # NDVI: sample red + NIR bands
                                    red_key = 'B04' if 'B04' in f_assets else ('red' if 'red' in f_assets else None)
                                    nir_key = None
                                    for candidate in ['B08', 'B8A', 'B05', 'nir08', 'nir']:
                                        if candidate in f_assets:
                                            nir_key = candidate
                                            break
                                    if not red_key or not nir_key:
                                        continue

                                    red_url = f_assets.get(red_key, {}).get('href')
                                    nir_url = f_assets.get(nir_key, {}).get('href')
                                    if not red_url or not nir_url:
                                        continue

                                    red_result = _sample_cog_sync(red_url, lat, lng)
                                    nir_result = _sample_cog_sync(nir_url, lat, lng)

                                    if red_result.get('error') or nir_result.get('error'):
                                        logger.info(f"[PIN] Fallback tile {f_id_short} also masked: red={red_result.get('error')}, nir={nir_result.get('error')}")
                                        continue

                                    if red_result.get('value') is not None and nir_result.get('value') is not None:
                                        red_val = float(red_result['value'])
                                        nir_val = float(nir_result['value'])
                                        if (nir_val + red_val) != 0:
                                            ndvi = max(-1, min(1, (nir_val - red_val) / (nir_val + red_val)))
                                            results.append(f"\n**NDVI at Pin (clear-sky fallback, {collection_id}):**")
                                            results.append(f"- RED ({red_key}): {red_val:.0f}, NIR ({nir_key}): {nir_val:.0f}")
                                            results.append(f"- **NDVI Value: {ndvi:.3f}**")
                                            if ndvi > 0.6: interp = "Dense, healthy vegetation"
                                            elif ndvi > 0.4: interp = "Moderate vegetation"
                                            elif ndvi > 0.2: interp = "Sparse or stressed vegetation"
                                            elif ndvi > 0: interp = "Minimal vegetation, bare soil"
                                            else: interp = "Water, snow, or non-vegetated"
                                            results.append(f"- Interpretation: {interp}")
                                            results.append(f"- Date: {f_date}")
                                            if f_cloud is not None:
                                                results.append(f"- Cloud cover: {f_cloud:.0f}%")
                                            results.append(f"- *(Used a different date because the loaded tiles were cloud-masked at this pin)*")
                                            sampled_count += 1
                                else:
                                    # Generic single-band fallback for non-NDVI optical
                                    for ak_candidate in ['data', 'visual', 'default']:
                                        if ak_candidate in f_assets:
                                            cog_url = f_assets[ak_candidate].get('href')
                                            if cog_url:
                                                fb_result = _sample_cog_sync(cog_url, lat, lng)
                                                if fb_result.get('value') is not None:
                                                    raw_value = fb_result['value']
                                                    results.append(f"\n**{collection_id} (clear-sky fallback):**")
                                                    results.append(f"- Value: **{raw_value:.2f}**")
                                                    results.append(f"- Date: {f_date}")
                                                    if f_cloud is not None:
                                                        results.append(f"- Cloud cover: {f_cloud:.0f}%")
                                                    results.append(f"- *(Used a different date because the loaded tiles were cloud-masked at this pin)*")
                                                    sampled_count += 1
                                            break

                except Exception as e:
                    logger.error(f"[PIN] Clear-sky fallback search failed: {e}")

        if sampled_count == 0:
            total_attempted = len(nodata_tiles) + len(outside_tiles) + len(error_tiles)
            results.append(f"\n[WARN] **Sampling returned no values** (tried {total_attempted} tile{'s' if total_attempted != 1 else ''}):\n")
            
            if nodata_tiles:
                # Determine most likely cause from cloud cover data
                high_cloud_count = sum(1 for t in nodata_tiles if t.get('cloud_cover') is not None and t['cloud_cover'] > 30)
                avg_cloud = sum(t['cloud_cover'] for t in nodata_tiles if t.get('cloud_cover') is not None) / max(1, len(tile_cloud_covers)) if tile_cloud_covers else None
                
                dates_str = ', '.join(t['date'] for t in nodata_tiles if t.get('date'))
                results.append(f"- **{len(nodata_tiles)} tile{'s' if len(nodata_tiles) != 1 else ''} had masked/empty pixels** at this pin location")
                
                # Determine if it's optical data (cloud-maskable) vs other
                is_optical = any(kw in ' '.join(collections).lower() for kw in ['sentinel-2', 'landsat', 'hls', 's30', 'l30', 'naip'])
                
                if is_optical and avg_cloud is not None and avg_cloud > 20:
                    results.append(f"- **Likely cause: Cloud cover** — the {len(nodata_tiles)} available tile{'s' if len(nodata_tiles) != 1 else ''} had an average of {avg_cloud:.0f}% cloud cover")
                    results.append(f"  The pixel at your pin ({lat:.4f}°, {lng:.4f}°) falls in a cloud-masked area")
                    results.append(f"  Dates attempted: {dates_str}")
                    results.append(f"\n**What to try:**")
                    results.append(f"- [SYNC] Move the pin to a nearby area where imagery is visible on the map")
                    results.append(f"- [DATE] Try a different date range with clearer skies")
                elif is_optical:
                    results.append(f"- **Likely cause: Cloud/shadow/snow mask** — the L2A processing pipeline masked this pixel")
                    results.append(f"  Even with low overall cloud cover, your specific pin location may be under a cloud or shadow")
                    if dates_str:
                        results.append(f"  Dates attempted: {dates_str}")
                    results.append(f"\n**What to try:**")
                    results.append(f"- [SYNC] Move the pin to a nearby area where data is visually rendered on the map")
                    results.append(f"- [DATE] Request a different date range")
                else:
                    results.append(f"- **Cause: NoData mask** — the pixel at ({lat:.4f}°, {lng:.4f}°) has no valid data in this collection")
                    if dates_str:
                        results.append(f"  Dates attempted: {dates_str}")
                    results.append(f"\n**What to try:**")
                    results.append(f"- [SYNC] Move the pin to an area where data is displayed on the map")
            
            if outside_tiles:
                results.append(f"- **{len(outside_tiles)} tile{'s' if len(outside_tiles) != 1 else ''} did not cover this pin location** (pin is outside their spatial extent)")
            
            if error_tiles:
                error_types = set(t.get('error', 'unknown')[:50] for t in error_tiles)
                results.append(f"- **{len(error_tiles)} tile{'s' if len(error_tiles) != 1 else ''} had access errors:** {'; '.join(error_types)}")
                results.append(f"  This may be a temporary Planetary Computer issue — try again in a moment")

        _log_tool_call("sample_raster_value", {"data_type": data_type, "lat": lat, "lng": lng, "samples": sampled_count, "nodata": len(nodata_tiles), "outside": len(outside_tiles), "errors": len(error_tiles)}, f"Sampled {sampled_count}")
        return "\n".join(results)

    except Exception as e:
        logger.error(f"[FAIL] sample_raster_value failed: {e}")
        import traceback
        logger.error(traceback.format_exc())
        return f"Raster sampling failed: {str(e)}"


# ============================================================================
# TOOL 11: QUERY KNOWLEDGE
# ============================================================================

def query_knowledge(question: str) -> str:
    """Answer educational or factual questions about geography, satellite data,
    or scientific concepts. Use for 'why', 'how', 'explain', history, or general knowledge.

    :param question: The educational or factual question to answer
    :return: Educational/contextual information
    """
    logger.info(f"[DOCS] query_knowledge(question='{question[:50]}...')")
    try:
        client = _get_vision_client()
        if not client:
            return "Knowledge query unavailable - Azure OpenAI client not initialized."

        ctx = _session_context
        context_parts = []
        bounds = ctx.get('map_bounds', {})
        if bounds:
            context_parts.append(f"User is viewing: ({bounds.get('center_lat', 'N/A')}, {bounds.get('center_lng', 'N/A')})")
        collections = ctx.get('loaded_collections', [])
        if collections:
            context_parts.append(f"Loaded datasets: {', '.join(collections)}")
        context_str = "\n".join(context_parts) if context_parts else "No map context"

        system_prompt = f"""You are a knowledgeable geospatial expert. Answer the question.

Context:
{context_str}

Guidelines: Provide accurate, educational answers. Include relevant facts. Be concise but informative."""

        deployment = os.getenv("AZURE_OPENAI_DEPLOYMENT_NAME", "gpt-5")
        response = client.chat.completions.create(
            model=deployment,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": question}
            ],
            max_completion_tokens=800, temperature=0.5
        )
        result = response.choices[0].message.content
        _log_tool_call("query_knowledge", {"question": question}, result)
        return result

    except Exception as e:
        logger.error(f"[FAIL] query_knowledge failed: {e}")
        return f"Knowledge query failed: {str(e)}"


# ============================================================================
# TOOL 12: IDENTIFY FEATURES
# ============================================================================

def identify_features(feature_type: str) -> str:
    """Identify specific geographic features visible on the map such as rivers,
    mountains, cities, or landmarks. Use when the user asks 'what is that' or
    wants to identify a specific feature.

    :param feature_type: Type: 'water', 'mountain', 'city', 'road', 'vegetation', or 'any'
    :return: Feature names, classifications, and descriptions
    """
    logger.info(f"[SEARCH] identify_features(feature_type='{feature_type}')")
    ctx = _session_context
    screenshot = ctx.get('screenshot_base64')

    if not screenshot:
        return "No map view available to identify features."

    try:
        client = _get_vision_client()
        if not client:
            return "Feature identification unavailable - client not initialized."

        image_data = screenshot
        if image_data.startswith('data:image'):
            image_data = image_data.split(',', 1)[1]

        bounds = ctx.get('map_bounds', {})
        location_hint = f"Approximate location: ({bounds.get('center_lat', 'N/A')}, {bounds.get('center_lng', 'N/A')})" if bounds else ""

        prompt = f"""Identify {feature_type} features visible in this satellite/map image.
{location_hint}
For each feature: name, type, notable characteristics. Be specific."""

        deployment = os.getenv("AZURE_OPENAI_DEPLOYMENT_NAME", "gpt-5")
        response = client.chat.completions.create(
            model=deployment,
            messages=[{"role": "user", "content": [
                {"type": "text", "text": prompt},
                {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{image_data}", "detail": "high"}}
            ]}],
            max_completion_tokens=800, temperature=0.3
        )
        result = response.choices[0].message.content
        _log_tool_call("identify_features", {"feature_type": feature_type}, result)
        return result

    except Exception as e:
        logger.error(f"[FAIL] identify_features failed: {e}")
        return f"Feature identification failed: {str(e)}"


# ============================================================================
# TOOL 13: COMPARE TEMPORAL
# ============================================================================

def _parse_time_period_to_stac(time_period: str) -> Optional[str]:
    """Parse natural language time period into STAC datetime format."""
    tp = time_period.lower().strip()
    month_map = {
        'january': 1, 'jan': 1, 'february': 2, 'feb': 2, 'march': 3, 'mar': 3,
        'april': 4, 'apr': 4, 'may': 5, 'june': 6, 'jun': 6, 'july': 7, 'jul': 7,
        'august': 8, 'aug': 8, 'september': 9, 'sep': 9, 'sept': 9,
        'october': 10, 'oct': 10, 'november': 11, 'nov': 11, 'december': 12, 'dec': 12
    }

    if tp in ["now", "current", "today", "present"]:
        now = datetime.now()
        start = now.replace(day=1)
        end_month = now.month + 1 if now.month < 12 else 1
        end_year = now.year if now.month < 12 else now.year + 1
        end = now.replace(year=end_year, month=end_month, day=1)
        return f"{start.strftime('%Y-%m-%d')}/{end.strftime('%Y-%m-%d')}"

    # "Month Year"
    match = re.search(r'(\w+)\s+(\d{4})', tp)
    if match:
        month = month_map.get(match.group(1))
        if month:
            year = int(match.group(2))
            last_day = monthrange(year, month)[1]
            return f"{year}-{month:02d}-01/{year}-{month:02d}-{last_day:02d}"

    # MM/YYYY
    match = re.match(r'^(\d{1,2})/(\d{4})$', time_period.strip())
    if match:
        month, year = int(match.group(1)), int(match.group(2))
        if 1 <= month <= 12:
            last_day = monthrange(year, month)[1]
            return f"{year}-{month:02d}-01/{year}-{month:02d}-{last_day:02d}"

    # Just year
    match = re.match(r'^(\d{4})$', time_period.strip())
    if match:
        year = int(match.group(1))
        return f"{year}-01-01/{year}-12-31"

    # Fallback: extract year
    match = re.search(r'(\d{4})', time_period)
    if match:
        year = int(match.group(1))
        return f"{year}-01-01/{year}-12-31"

    return None


def _select_collection_for_analysis(analysis_focus: str) -> str:
    """Select the best STAC collection for an analysis focus."""
    mapping = {
        "vegetation": "hls", "ndvi": "hls", "surface reflectance": "hls",
        "reflectance": "hls", "urban development": "sentinel-2-l2a",
        "urban": "sentinel-2-l2a", "water levels": "jrc-gsw",
        "snow cover": "modis-snow", "snow": "modis-snow",
        "fire": "modis-fire", "general": "sentinel-2-l2a",
    }
    return mapping.get(analysis_focus.lower(), "sentinel-2-l2a")


def _resolve_location_to_bbox_sync(location: str) -> Optional[List[float]]:
    """Resolve a location name to a bounding box using geocoding."""
    try:
        import httpx
        response = httpx.get(
            "https://nominatim.openstreetmap.org/search",
            params={"q": location, "format": "json", "limit": 1},
            headers={"User-Agent": "earth-copilot/1.0"},
            timeout=10.0
        )
        if response.status_code == 200:
            results = response.json()
            if results and 'boundingbox' in results[0]:
                bb = results[0]['boundingbox']
                return [float(bb[2]), float(bb[0]), float(bb[3]), float(bb[1])]
    except Exception as e:
        logger.warning(f"Geocoding failed: {e}")

    # Fallback to session context
    bounds = _session_context.get('map_bounds', {})
    if bounds:
        return [bounds.get("west", -180), bounds.get("south", -90),
                bounds.get("east", 180), bounds.get("north", 90)]
    return None


def _execute_stac_query_sync(collection: str, bbox: List[float], datetime_range: str, limit: int = 5) -> Dict[str, Any]:
    """Execute a STAC query synchronously."""
    try:
        import httpx
        aliases = {
            "hls": "hls-l30-v2.0", "sentinel-2": "sentinel-2-l2a",
            "modis-snow": "modis-10A1-061", "modis-fire": "modis-14A1-061",
        }
        stac_collection = aliases.get(collection.lower(), collection)

        search_body = {
            "collections": [stac_collection], "bbox": bbox,
            "datetime": datetime_range, "limit": limit,
            "sortby": [{"field": "datetime", "direction": "desc"}]
        }
        if stac_collection in ["sentinel-2-l2a", "hls-l30-v2.0", "landsat-c2-l2"]:
            search_body["query"] = {"eo:cloud_cover": {"lt": 30}}

        with httpx.Client(timeout=30) as client:
            resp = client.post(
                "https://planetarycomputer.microsoft.com/api/stac/v1/search",
                json=search_body, headers={"Content-Type": "application/json"}
            )
            if resp.status_code == 200:
                return resp.json()
        return {"features": []}
    except Exception as e:
        logger.error(f"STAC query failed: {e}")
        return {"features": [], "error": str(e)}


def _sample_reflectance_at_point(features: List[Dict], lat: float, lng: float,
                                  bands: Optional[List[str]] = None) -> Dict[str, Any]:
    """Sample reflectance values from STAC features at a point (sync)."""
    if not features:
        return {'error': 'No features', 'values': {}}
    if bands is None:
        bands = ['B02', 'B03', 'B04', 'B08']

    for feature in features[:3]:
        try:
            assets = feature.get('assets', {})
            props = feature.get('properties', {})
            sampled = {}
            for band in bands:
                for key in [band, band.lower()]:
                    if key in assets:
                        result = _sample_cog_sync(assets[key].get('href', ''), lat, lng)
                        if result.get('value') is not None:
                            raw = result['value']
                            scaled = raw * 0.0001 if raw > 100 else raw
                            sampled[band] = {'raw': raw, 'scaled': scaled, 'reflectance': scaled}
                        break
            if sampled:
                return {
                    'values': sampled, 'date': props.get('datetime', '')[:10],
                    'item_id': feature.get('id', 'unknown'),
                    'cloud_cover': props.get('eo:cloud_cover', 'N/A')
                }
        except Exception:
            continue
    return {'error': 'Could not sample', 'values': {}}


def _summarize_stac_results(features: List[Dict], time_period: str) -> str:
    """Create a text summary of STAC results."""
    if not features:
        return f"No imagery for {time_period}"
    lines = [f"Found {len(features)} scenes:"]
    for f in features[:3]:
        props = f.get("properties", {})
        dt = props.get("datetime", "Unknown")[:10]
        cc = props.get("eo:cloud_cover", "N/A")
        lines.append(f"  - {dt} (cloud: {cc}%)")
    return "\n".join(lines)


def compare_temporal(location: str, time_period_1: str, time_period_2: str,
                     analysis_focus: str = "surface reflectance") -> str:
    """Compare satellite imagery between two different time periods to detect changes.
    Samples actual pixel values and calculates quantitative change.

    :param location: The location to analyze (e.g., 'Athens', 'Miami Beach')
    :param time_period_1: First time period (e.g., '01/2020', 'June 2025')
    :param time_period_2: Second time period (e.g., '01/2024', 'now')
    :param analysis_focus: What to compare: 'surface reflectance', 'vegetation', 'ndvi', 'urban development', 'water levels', 'snow cover', or 'general'
    :return: Temporal comparison with quantitative change analysis
    """
    logger.info(f"[WAIT] compare_temporal(location='{location}', t1='{time_period_1}', t2='{time_period_2}')")

    try:
        dt1 = _parse_time_period_to_stac(time_period_1)
        dt2 = _parse_time_period_to_stac(time_period_2)
        if not dt1 or not dt2:
            return f"Could not parse time periods: '{time_period_1}' and '{time_period_2}'."

        collection = _select_collection_for_analysis(analysis_focus)
        bbox = _resolve_location_to_bbox_sync(location)
        if not bbox:
            return f"Could not resolve location: '{location}'."

        center_lng = (bbox[0] + bbox[2]) / 2
        center_lat = (bbox[1] + bbox[3]) / 2

        query_1 = _execute_stac_query_sync(collection, bbox, dt1, limit=5)
        query_2 = _execute_stac_query_sync(collection, bbox, dt2, limit=5)

        features_1 = query_1.get("features", [])
        features_2 = query_2.get("features", [])

        if not features_1 and not features_2:
            return f"No imagery found for {location} in either time period."

        # Sample reflectance for quantitative comparison
        reflectance_lines = []
        if center_lat and center_lng and features_1 and features_2:
            bands = ['B04', 'B08'] if 'ndvi' in analysis_focus.lower() else ['B02', 'B03', 'B04', 'B08']
            s1 = _sample_reflectance_at_point(features_1, center_lat, center_lng, bands)
            s2 = _sample_reflectance_at_point(features_2, center_lat, center_lng, bands)

            if s1.get('values') and s2.get('values'):
                reflectance_lines.append(f"\n### [CHART] Quantitative Comparison at ({center_lat:.4f}°, {center_lng:.4f}°)")
                reflectance_lines.append(f"\n**{time_period_1}** (Scene: {s1.get('date', 'N/A')})")
                for band, d in s1['values'].items():
                    reflectance_lines.append(f"- {band}: {d['reflectance']:.4f}")
                reflectance_lines.append(f"\n**{time_period_2}** (Scene: {s2.get('date', 'N/A')})")
                for band, d in s2['values'].items():
                    reflectance_lines.append(f"- {band}: {d['reflectance']:.4f}")

                reflectance_lines.append("\n**Changes:**")
                common = set(s1['values']) & set(s2['values'])
                for band in sorted(common):
                    v1 = s1['values'][band]['reflectance']
                    v2 = s2['values'][band]['reflectance']
                    pct = ((v2 - v1) / v1 * 100) if v1 != 0 else 0
                    reflectance_lines.append(f"- {band}: {v2 - v1:+.4f} ({pct:+.1f}%)")

                if 'B04' in common and 'B08' in common:
                    r1, n1 = s1['values']['B04']['reflectance'], s1['values']['B08']['reflectance']
                    r2, n2 = s2['values']['B04']['reflectance'], s2['values']['B08']['reflectance']
                    ndvi1 = (n1 - r1) / (n1 + r1) if (n1 + r1) != 0 else 0
                    ndvi2 = (n2 - r2) / (n2 + r2) if (n2 + r2) != 0 else 0
                    reflectance_lines.append(f"\n**NDVI:** {time_period_1}: {ndvi1:.3f} -> {time_period_2}: {ndvi2:.3f} (Change: {ndvi2 - ndvi1:+.3f})")

        # GPT-5 analysis
        analysis_text = ""
        client = _get_vision_client()
        if client:
            summary_1 = _summarize_stac_results(features_1, time_period_1)
            summary_2 = _summarize_stac_results(features_2, time_period_2)
            deployment = os.getenv("AZURE_OPENAI_DEPLOYMENT_NAME", "gpt-5")
            try:
                resp = client.chat.completions.create(
                    model=deployment,
                    messages=[
                        {"role": "system", "content": f"""Geospatial analyst comparing imagery.
Location: {location}, Collection: {collection}, Focus: {analysis_focus}
Period 1 ({time_period_1}): {summary_1}
Period 2 ({time_period_2}): {summary_2}
Describe expected changes, seasonal effects, and what to examine."""},
                        {"role": "user", "content": f"Compare {analysis_focus} in {location} between {time_period_1} and {time_period_2}."}
                    ],
                    max_completion_tokens=1000, temperature=0.5
                )
                analysis_text = resp.choices[0].message.content
            except Exception as e:
                logger.warning(f"GPT analysis failed: {e}")

        result_parts = [
            f"## Temporal Comparison: {location}",
            f"**Collection:** {collection}",
            f"**Periods:** {time_period_1} vs {time_period_2}",
            f"**Focus:** {analysis_focus}",
            f"\n### Data: {len(features_1)} scenes ({time_period_1}) | {len(features_2)} scenes ({time_period_2})",
        ]
        if reflectance_lines:
            result_parts.extend(reflectance_lines)
        if analysis_text:
            result_parts.append(f"\n### Expert Analysis\n{analysis_text}")

        result = "\n".join(result_parts)
        _log_tool_call("compare_temporal", {"location": location, "t1": time_period_1, "t2": time_period_2}, result[:200])
        return result

    except Exception as e:
        logger.error(f"[FAIL] compare_temporal failed: {e}")
        return f"Temporal comparison failed: {str(e)}"


# ============================================================================
# FACTORY FUNCTION
# ============================================================================

def create_vision_functions() -> Set[Callable]:
    """Create the set of vision analysis tool functions for FunctionTool.

    Returns a set of all 13 tool functions that can be registered with
    Azure AI Agent Service FunctionTool.
    """
    return {
        analyze_screenshot,
        analyze_raster,
        analyze_vegetation,
        analyze_fire,
        analyze_land_cover,
        analyze_snow,
        analyze_sar,
        analyze_water,
        analyze_biomass,
        sample_raster_value,
        query_knowledge,
        identify_features,
        compare_temporal,
    }
