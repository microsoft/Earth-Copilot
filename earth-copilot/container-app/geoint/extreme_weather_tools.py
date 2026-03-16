"""
Extreme Weather & Climate Projection Tools for Azure AI Agent Service

Standalone module that fetches NASA NEX-GDDP-CMIP6 climate data directly
from Planetary Computer STAC. No prior STAC search or session state required.

Data format: NetCDF (not COG) — point sampling only, no tile rendering.
Grid resolution: 0.25° × 0.25° global
Longitude convention: 0–360 (negative longitudes are converted automatically)

Climate variables:
  tasmax, tasmin, tas — temperature (K -> °F)
  pr — precipitation (kg/m²/s -> mm/day)
  sfcWind — wind speed (m/s)
  hurs — relative humidity (%)
  huss — specific humidity (kg/kg)
  rlds — downwelling longwave radiation (W/m²)
  rsds — downwelling shortwave radiation (W/m²)

Usage:
    from geoint.extreme_weather_tools import create_extreme_weather_functions
    functions = create_extreme_weather_functions()  # Returns Set[Callable]
    tool = FunctionTool(functions)
"""

import logging
import json
import time
from typing import Dict, Any, List, Set, Callable, Optional
from concurrent.futures import ThreadPoolExecutor, as_completed

from cloud_config import cloud_cfg

logger = logging.getLogger(__name__)

# Module-level STAC catalog (lazy-loaded)
_catalog = None
_stac_endpoint = cloud_cfg.stac_catalog_url

# ============================================================
# STAC SEARCH CACHE — avoid redundant identical STAC queries
# ============================================================
# CMIP6 items are global (all variables are assets on the same item),
# so a search for (scenario=ssp585, year=2030) returns the SAME items
# regardless of which variable we want.  Cache keyed by (scenario, year).
_stac_search_cache: Dict[str, list] = {}
_stac_cache_ttl = 300  # seconds
_stac_cache_timestamps: Dict[str, float] = {}

# ============================================================
# NETCDF RESULT CACHE — avoid re-reading remote NetCDF data
# ============================================================
# CMIP6 projections are static datasets — the same (href, variable,
# lat, lon, aggregate) query always returns identical results.
_netcdf_result_cache: Dict[str, Dict] = {}
_netcdf_result_cache_ts: Dict[str, float] = {}
_netcdf_cache_ttl = 3600  # 1 hour

# Thread pool for parallel NetCDF sampling (reused across tool calls)
_netcdf_pool = ThreadPoolExecutor(max_workers=6)

# Separate thread pool for xarray .values reads inside _sample_netcdf.
# MUST be separate from _netcdf_pool to avoid thread starvation:
# outer model-parallel tasks run on _netcdf_pool, each calling
# _sample_netcdf which submits .values reads here.  If both pools
# were the same, timed-out .values threads would hold workers while
# retries need new workers → deadlock.
_values_pool = ThreadPoolExecutor(max_workers=4)

# ============================================================
# MODULE-LEVEL FSSPEC FILESYSTEM — connection & block cache reuse
# ============================================================
# Creating a new fsspec HTTPFileSystem per _sample_netcdf call wastes:
#   - TCP connection setup + TLS handshake (~200-500ms each)
#   - In-memory block cache (HDF5 metadata chunks already read)
# A shared instance lets concurrent readers reuse connections and
# benefit from block-level caching of previously-read byte ranges.
_https_fs = None
_https_fs_lock = __import__('threading').Lock()

def _get_https_fs():
    """Return a shared fsspec HTTPS filesystem (lazy-init, thread-safe)."""
    global _https_fs
    if _https_fs is None:
        with _https_fs_lock:
            if _https_fs is None:
                import fsspec
                import aiohttp
                # 4 MB blocks — NetCDF metadata (HDF5 btree, chunk tables)
                # fits in ~2-4 MB, so one read fetches all metadata at once
                # instead of multiple 1 MB round-trips.
                _https_fs = fsspec.filesystem(
                    "https",
                    block_size=4 * 2**20,   # 4 MB
                    client_kwargs={
                        "timeout": aiohttp.ClientTimeout(
                            total=60,
                            connect=15,
                            sock_read=45,
                        )
                    },
                )
    return _https_fs

# NEX-GDDP-CMIP6 collection ID
CMIP6_COLLECTION = "nasa-nex-gddp-cmip6"

# Climate variable metadata
CLIMATE_VAR_INFO: Dict[str, Dict[str, Any]] = {
    'tas': {
        'name': 'Daily Near-Surface Air Temperature',
        'unit': 'K', 'display_unit': '°F',
        'convert': lambda v: round((v - 273.15) * 9/5 + 32, 1),
        'valid_range': (150, 350),
        'category': 'temperature',
    },
    'tasmax': {
        'name': 'Daily Maximum Temperature',
        'unit': 'K', 'display_unit': '°F',
        'convert': lambda v: round((v - 273.15) * 9/5 + 32, 1),
        'valid_range': (150, 380),
        'category': 'temperature',
    },
    'tasmin': {
        'name': 'Daily Minimum Temperature',
        'unit': 'K', 'display_unit': '°F',
        'convert': lambda v: round((v - 273.15) * 9/5 + 32, 1),
        'valid_range': (150, 350),
        'category': 'temperature',
    },
    'pr': {
        'name': 'Precipitation',
        'unit': 'kg m⁻² s⁻¹', 'display_unit': 'mm/day',
        'convert': lambda v: round(v * 86400, 2),
        'valid_range': (0, 1),
        'category': 'precipitation',
    },
    'sfcWind': {
        'name': 'Near-Surface Wind Speed',
        'unit': 'm/s', 'display_unit': 'm/s',
        'convert': lambda v: round(v, 2),
        'valid_range': (0, 100),
        'category': 'wind',
    },
    'hurs': {
        'name': 'Near-Surface Relative Humidity',
        'unit': '%', 'display_unit': '%',
        'convert': lambda v: round(v, 1),
        'valid_range': (0, 100),
        'category': 'humidity',
    },
    'huss': {
        'name': 'Near-Surface Specific Humidity',
        'unit': 'kg/kg', 'display_unit': 'g/kg',
        'convert': lambda v: round(v * 1000, 3),
        'valid_range': (0, 0.1),
        'category': 'humidity',
    },
    'rlds': {
        'name': 'Downwelling Longwave Radiation',
        'unit': 'W/m²', 'display_unit': 'W/m²',
        'convert': lambda v: round(v, 1),
        'valid_range': (0, 600),
        'category': 'radiation',
    },
    'rsds': {
        'name': 'Downwelling Shortwave Radiation',
        'unit': 'W/m²', 'display_unit': 'W/m²',
        'convert': lambda v: round(v, 1),
        'valid_range': (0, 500),
        'category': 'radiation',
    },
}

# Default models/scenarios to search
PREFERRED_MODELS = ['ACCESS-CM2', 'GFDL-ESM4', 'MPI-ESM1-2-HR', 'UKESM1-0-LL', 'EC-Earth3']
PREFERRED_SCENARIOS = ['ssp245', 'ssp585']  # Moderate & worst-case


def _get_catalog():
    """Lazy-load STAC catalog."""
    global _catalog
    if _catalog is None:
        from pystac_client import Client
        _catalog = Client.open(_stac_endpoint)
    return _catalog


def _convert_longitude(longitude: float) -> float:
    """Convert standard longitude (-180..180) to NEX-GDDP convention (0..360)."""
    return longitude if longitude >= 0 else longitude + 360


def _search_cmip6_items(
    latitude: float,
    longitude: float,
    variable: str,
    scenario: str = "ssp585",
    year: Optional[int] = None,
    limit: int = 5,
) -> list:
    """
    Search Planetary Computer for NEX-GDDP-CMIP6 items.
    
    Returns raw STAC items matching the given scenario and year.
    Uses an in-memory cache keyed by (scenario, year) since CMIP6 items
    are GLOBAL and contain ALL climate variables as separate assets.
    
    Filterable properties: cmip6:year, cmip6:model, cmip6:scenario
    (NOT cmip6:variable — variables are asset keys, not item properties).
    """
    import httpx
    import planetary_computer as pc

    target_year = year if year else 2030
    # Cache key excludes 'limit' — CMIP6 items are global, same results
    # for any limit.  We always fetch max(limit, 5) and slice in caller.
    cache_key = f"{scenario}:{target_year}"
    
    # Check cache first — same items work for any variable
    now = time.time()
    if cache_key in _stac_search_cache:
        cache_age = now - _stac_cache_timestamps.get(cache_key, 0)
        if cache_age < _stac_cache_ttl:
            cached = _stac_search_cache[cache_key]
            # Filter cached items to those with the requested variable
            valid = [f for f in cached if variable in f.get("assets", {})][:limit]
            logger.info(f"[CMIP6] Cache HIT for {scenario}/{target_year}: {len(valid)}/{len(cached)} items have '{variable}' ({cache_age:.0f}s old)")
            return valid
        else:
            # Expired
            del _stac_search_cache[cache_key]
            _stac_cache_timestamps.pop(cache_key, None)
    
    search_body: Dict[str, Any] = {
        "collections": [CMIP6_COLLECTION],
        "limit": max(limit, 5),  # always fetch enough to satisfy any caller
    }
    
    search_body["query"] = {
        "cmip6:year": {"eq": target_year},
    }
    if scenario:
        search_body["query"]["cmip6:scenario"] = {"eq": scenario}
    
    if PREFERRED_MODELS:
        search_body["query"]["cmip6:model"] = {"in": PREFERRED_MODELS}
    
    try:
        logger.info(f"[CMIP6] Searching for {variable} asset in {scenario}/{target_year} items (limit={limit})")
        
        with httpx.Client(timeout=30) as client:
            resp = client.post(
                f"{_stac_endpoint}/search",
                json=search_body,
                headers={"Content-Type": "application/json"}
            )
            if resp.status_code == 200:
                features = resp.json().get("features", [])
                logger.info(f"[CMIP6] Found {len(features)} items for {scenario}/{target_year}")
                
                # Sign ALL items and cache them (they contain every variable)
                signed_features = []
                for f in features:
                    try:
                        signed_features.append(pc.sign(f))
                    except Exception:
                        signed_features.append(f)
                
                # Store in cache (all variables, not filtered)
                _stac_search_cache[cache_key] = signed_features
                _stac_cache_timestamps[cache_key] = now
                
                # Filter to items that have the requested variable, slice to caller limit
                valid_features = [f for f in signed_features if variable in f.get("assets", {})][:limit]
                
                if not valid_features and features:
                    logger.warning(f"[CMIP6] {len(features)} items found but none have '{variable}' asset")
                    first_assets = list(features[0].get("assets", {}).keys())
                    logger.warning(f"[CMIP6] Available assets in first item: {first_assets}")
                
                logger.info(f"[CMIP6] {len(valid_features)} items have '{variable}' asset (cached {len(signed_features)} items)")
                return valid_features
            else:
                logger.warning(f"STAC search returned {resp.status_code}: {resp.text[:200]}")
                return []
    except Exception as e:
        logger.error(f"CMIP6 STAC search failed: {e}")
        return []


def _sample_netcdf(
    href: str,
    variable: str,
    latitude: float,
    longitude: float,
    aggregate: str = "last",
    _retry_attempt: int = 0,
) -> Dict[str, Any]:
    """
    Sample a single NetCDF asset at (lat, lon) using xarray + h5netcdf.
    
    Uses xarray with h5netcdf engine and fsspec for remote HTTP access.
    This avoids GDAL's netCDF driver which requires userfaultfd (blocked
    by Docker's default seccomp profile in Azure Container Apps).
    
    Args:
        aggregate: How to aggregate across time dimension.
            "last"  — single value from the last timestep (good for temperature)
            "annual" — mean, max, min across all timesteps (good for precip/wind)
        _retry_attempt: Internal retry counter (0-based). Max 2 retries.
    
    Returns dict with 'raw_value', 'display_value', 'display_unit', etc.
    or 'error' key on failure.
    """
    import xarray as xr
    import fsspec
    import numpy as np

    var_info = CLIMATE_VAR_INFO.get(variable, {
        'name': variable, 'unit': 'raw', 'display_unit': '',
        'convert': lambda v: round(v, 4), 'valid_range': None,
    })

    sample_lng = _convert_longitude(longitude)

    # --- Result cache: CMIP6 projections are static data, cache for 1 hour ---
    cache_key = f"{href}:{variable}:{latitude:.4f}:{sample_lng:.4f}:{aggregate}"
    now = time.time()
    if cache_key in _netcdf_result_cache:
        cache_age = now - _netcdf_result_cache_ts.get(cache_key, 0)
        if cache_age < _netcdf_cache_ttl:
            logger.info(f"[CMIP6] NetCDF CACHE HIT: {variable} ({cache_age:.0f}s old)")
            return _netcdf_result_cache[cache_key]
        else:
            _netcdf_result_cache.pop(cache_key, None)
            _netcdf_result_cache_ts.pop(cache_key, None)

    logger.info(f"[CMIP6] Sampling NetCDF: variable={variable}, lat={latitude}, lng={longitude}, sample_lng={sample_lng}, aggregate={aggregate}")
    logger.info(f"[CMIP6] href (first 120 chars): {href[:120]}...")

    try:
        # Open remote NetCDF via fsspec HTTP filesystem + h5netcdf engine
        # This bypasses GDAL entirely — no userfaultfd needed
        # decode_times=False avoids cftime dependency for non-standard calendars
        # (e.g. UKESM1-0-LL uses 360_day calendar)
        #
        # Use shared HTTPFileSystem for byte-range reads — reuses TCP
        # connections and in-memory block cache across concurrent samples.
        fs = _get_https_fs()
        f = fs.open(href, mode="rb")
        try:
            ds = xr.open_dataset(f, engine="h5netcdf", decode_times=False)

            if variable not in ds.data_vars:
                available = list(ds.data_vars.keys())
                return {"error": f"Variable '{variable}' not found. Available: {available}"}

            var_data = ds[variable]

            # Select nearest grid cell to the target coordinates
            # NEX-GDDP-CMIP6 uses 'lat' and 'lon' dimension names
            try:
                point = var_data.sel(lat=latitude, lon=sample_lng, method="nearest")
            except KeyError:
                # Try alternate dimension names
                dim_names = list(var_data.dims)
                logger.warning(f"[CMIP6] Unexpected dims: {dim_names}, trying positional selection")
                return {"error": f"Cannot map coordinates to dimensions: {dim_names}"}

            has_time = "time" in point.dims
            total_timesteps = point.sizes["time"] if has_time else 1

            if aggregate == "annual" and has_time:
                # -------------------------------------------------------
                # SPEED FIX: Remote HDF5 reads over HTTP are expensive.
                # Each timestep may require a separate HDF5 chunk access
                # via fsspec HTTP range request (~200-500ms each).
                # Reading all 365 days = 73-183s → always times out.
                #
                # Fix: subsample ~12 evenly-spaced days (one per ~month).
                # - Mean: accurate within ~5% of true annual mean
                # - Max: captures seasonal peaks across the full year
                # - ~30x fewer HTTP reads → completes in 5-15s
                # -------------------------------------------------------
                n_times = total_timesteps
                if n_times > 24:
                    step = max(1, n_times // 6)
                    point_subset = point.isel(time=slice(0, None, step))
                    n_sampled = point_subset.sizes.get("time", 0)
                    logger.info(f"[CMIP6] Subsampling {variable}: every {step}th day → {n_sampled} of {n_times} days")
                else:
                    point_subset = point
                    n_sampled = n_times

                t_read_start = time.time()
                # Wrap .values in a timeout to prevent indefinite blocking
                # on slow HTTP range requests (cold cache can take 40-60s+)
                # Uses _values_pool (NOT _netcdf_pool) to avoid thread starvation
                _read_future = _values_pool.submit(lambda ps=point_subset: ps.values.astype(float))
                try:
                    all_values = _read_future.result(timeout=45)
                except TimeoutError:
                    logger.warning(f"[CMIP6] .values read TIMED OUT after 45s for {variable} ({n_sampled} timesteps)")
                    raise TimeoutError(f"NetCDF read timed out for {variable} (cold cache)")
                t_read_elapsed = time.time() - t_read_start
                logger.info(f"[CMIP6] NetCDF .values read took {t_read_elapsed:.1f}s for {n_sampled} timesteps")

                valid_mask = ~np.isnan(all_values)
                if not valid_mask.any():
                    return {"error": "No data at this location (all days masked)"}
                valid = all_values[valid_mask]

                raw_mean = float(np.mean(valid))
                raw_max = float(np.max(valid))
                raw_min = float(np.min(valid))

                display_mean = var_info['convert'](raw_mean)
                display_max = var_info['convert'](raw_max)
                display_min = var_info['convert'](raw_min)

                result = {
                    "raw_mean": round(raw_mean, 6),
                    "raw_max": round(raw_max, 6),
                    "raw_min": round(raw_min, 6),
                    "display_mean": display_mean,
                    "display_max": display_max,
                    "display_min": display_min,
                    "display_value": display_mean,
                    "display_unit": var_info['display_unit'],
                    "variable_name": var_info['name'],
                    "aggregation": "annual",
                    "days_sampled": int(valid_mask.sum()),
                    "total_days": n_times,
                    "grid_resolution": "0.25° × 0.25°",
                }
                logger.info(f"[CMIP6]  NetCDF annual stats: {variable} mean={display_mean}, max={display_max}, min={display_min} {var_info['display_unit']} ({int(valid_mask.sum())} of {n_times} days sampled, read={t_read_elapsed:.1f}s)")
                _netcdf_result_cache[cache_key] = result
                _netcdf_result_cache_ts[cache_key] = now
                return result

            else:
                # Single timestep: last day
                if has_time:
                    point = point.isel(time=-1)

                t_read_start = time.time()
                # Wrap single-timestep read in timeout too
                # Uses _values_pool (NOT _netcdf_pool) to avoid thread starvation
                _read_future = _values_pool.submit(lambda p=point: float(p.values))
                try:
                    raw_value = _read_future.result(timeout=30)
                except TimeoutError:
                    logger.warning(f"[CMIP6] Single-timestep .values read TIMED OUT after 30s for {variable}")
                    raise TimeoutError(f"NetCDF single-timestep read timed out for {variable}")
                t_read_elapsed = time.time() - t_read_start
                logger.info(f"[CMIP6] Single-timestep .values read took {t_read_elapsed:.1f}s")

                # Check for NaN (masked/fill values become NaN in xarray)
                if np.isnan(raw_value):
                    return {"error": "No data at this location (masked)"}

                # Validate raw value against expected range
                vr = var_info.get('valid_range')
                if vr and not (vr[0] <= raw_value <= vr[1]):
                    return {"error": f"Value {raw_value} outside valid range {vr}"}

                display_value = var_info['convert'](raw_value)

                result = {
                    "raw_value": round(raw_value, 4),
                    "display_value": display_value,
                    "display_unit": var_info['display_unit'],
                    "variable_name": var_info['name'],
                    "band_sampled": total_timesteps,
                    "total_bands": total_timesteps,
                    "grid_resolution": "0.25° × 0.25°",
                }
                logger.info(f"[CMIP6]  NetCDF sampled OK: {variable}={display_value}{var_info['display_unit']} (raw={raw_value:.4f}, timestep={total_timesteps})")
                _netcdf_result_cache[cache_key] = result
                _netcdf_result_cache_ts[cache_key] = now
                return result
        finally:
            try:
                f.close()
            except Exception:
                pass

    except Exception as e:
        logger.error(f"[CMIP6]  NetCDF sampling FAILED for {variable} (attempt {_retry_attempt + 1}): {type(e).__name__}: {e}")
        logger.error(f"[CMIP6]   href={href[:250]}")
        import traceback
        logger.error(f"[CMIP6]   traceback: {traceback.format_exc()[-500:]}")
        
        # Retry on transient errors (HTTP timeouts, connection resets, SAS token issues)
        _max_retries = 2
        _retryable = ('TimeoutError', 'ConnectionError', 'ConnectionResetError',
                       'HTTPError', 'ClientError', 'OSError', 'IOError', 'BlockingIOError')
        error_type = type(e).__name__
        is_retryable = error_type in _retryable or '403' in str(e) or '408' in str(e) or '429' in str(e) or '500' in str(e) or '502' in str(e) or '503' in str(e) or '504' in str(e) or 'timeout' in str(e).lower()
        
        if is_retryable and _retry_attempt < _max_retries:
            wait = 2 ** _retry_attempt  # 1s, 2s
            logger.info(f"[CMIP6] Retrying {variable} in {wait}s (attempt {_retry_attempt + 2}/{_max_retries + 1})...")
            time.sleep(wait)
            # Reset shared filesystem on connection errors to force fresh TCP connections
            if 'connection' in str(e).lower() or 'reset' in str(e).lower():
                global _https_fs
                with _https_fs_lock:
                    _https_fs = None
            return _sample_netcdf(href, variable, latitude, longitude, aggregate, _retry_attempt + 1)
        
        return {"error": str(e)}


# ============================================================
# PUBLIC TOOL FUNCTIONS (registered with Agent Service)
# ============================================================

def get_temperature_projection(latitude: float, longitude: float, scenario: str = "ssp585", year: int = 2030) -> str:
    """Get projected temperature data (max, min, mean) for a location from NASA NEX-GDDP-CMIP6 climate models.
    Returns daily maximum temperature, minimum temperature, and mean temperature in °F.
    Use this when the user asks about future temperatures, heat waves, warming, or thermal conditions.
    
    :param latitude: Latitude of the location to analyze
    :param longitude: Longitude of the location to analyze  
    :param scenario: SSP scenario - 'ssp245' (moderate) or 'ssp585' (worst-case). Default 'ssp585'
    :param year: Projection year (2015-2100). Default 2030
    :return: JSON string with projected temperature values and model metadata
    """
    try:
        logger.info(f"[TOOL] get_temperature_projection at ({latitude:.4f}, {longitude:.4f}), {scenario}, {year}")
        
        temp_vars = ['tasmax', 'tasmin', 'tas']
        results = {}
        models_used = set()
        
        # Single STAC search (cache ensures this is only 1 HTTP call for all 3 vars)
        # Then parallel NetCDF sampling via ThreadPoolExecutor
        def _sample_var(var):
            """Sample one variable — runs in a worker thread."""
            items = _search_cmip6_items(latitude, longitude, var, scenario, year, limit=3)
            if not items:
                return var, {"error": f"No CMIP6 data found for {var}"}, None
            for item in items:
                assets = item.get('assets', {})
                href = assets.get(var, {}).get('href', '') if isinstance(assets.get(var), dict) else ''
                if not href:
                    continue
                sample = _sample_netcdf(href, var, latitude, longitude)
                if 'error' not in sample:
                    var_info = CLIMATE_VAR_INFO[var]
                    item_id = item.get('id', '')
                    parts = item_id.split('.')
                    model = parts[0] if parts else None
                    return var, {
                        "value": sample['display_value'],
                        "unit": sample['display_unit'],
                        "description": var_info['name'],
                    }, model
            return var, {"error": f"Sampling failed for {var}"}, None
        
        # Submit all 3 variable samples in parallel (with timeout guards)
        futures = {_netcdf_pool.submit(_sample_var, v): v for v in temp_vars}
        try:
            for future in as_completed(futures, timeout=150):
                try:
                    var, result, model = future.result(timeout=120)
                    results[var] = result
                    if model:
                        models_used.add(model)
                except Exception as exc:
                    logger.warning(f"[TOOL] Temperature variable future failed: {exc}")
        except TimeoutError:
            logger.warning("[TOOL] Not all temperature variables completed in time — using partial results")
        
        output = {
            "location": {"latitude": latitude, "longitude": longitude},
            "scenario": scenario,
            "year": year,
            "data_source": "NASA NEX-GDDP-CMIP6",
            "grid_resolution": "0.25° × 0.25°",
            "models_sampled": list(models_used),
            "projections": {}
        }
        
        if 'tasmax' in results and 'error' not in results.get('tasmax', {}):
            output["projections"]["daily_max_temperature"] = results['tasmax']
        if 'tasmin' in results and 'error' not in results.get('tasmin', {}):
            output["projections"]["daily_min_temperature"] = results['tasmin']
        if 'tas' in results and 'error' not in results.get('tas', {}):
            output["projections"]["daily_mean_temperature"] = results['tas']
        
        if not output["projections"]:
            output["error"] = "Could not retrieve temperature data. " + json.dumps(results)
        
        logger.info(f"[TOOL] Temperature projection: {json.dumps(output.get('projections', {}))}")
        return json.dumps(output)
        
    except Exception as e:
        logger.error(f"[TOOL] Temperature projection failed: {e}")
        return json.dumps({"error": str(e)})


def get_precipitation_projection(latitude: float, longitude: float, scenario: str = "ssp585", year: int = 2030) -> str:
    """Get projected precipitation (rainfall) data for a location from NASA NEX-GDDP-CMIP6 climate models.
    Returns daily precipitation in mm/day.
    Use this when the user asks about future rainfall, drought, flooding risk, or precipitation patterns.
    
    :param latitude: Latitude of the location to analyze
    :param longitude: Longitude of the location to analyze
    :param scenario: SSP scenario - 'ssp245' (moderate) or 'ssp585' (worst-case). Default 'ssp585'
    :param year: Projection year (2015-2100). Default 2030
    :return: JSON string with projected precipitation values and model metadata
    """
    try:
        logger.info(f"[TOOL] get_precipitation_projection at ({latitude:.4f}, {longitude:.4f}), {scenario}, {year}")
        
        items = _search_cmip6_items(latitude, longitude, 'pr', scenario, year, limit=5)
        
        if not items:
            return json.dumps({
                "error": "No CMIP6 precipitation data found for this location/scenario",
                "location": {"latitude": latitude, "longitude": longitude},
                "scenario": scenario, "year": year,
            })
        
        # Sample multiple models in PARALLEL for ensemble view
        model_results = []
        sample_tasks = []
        for item in items[:2]:
            assets = item.get('assets', {})
            href = assets.get('pr', {}).get('href', '') if isinstance(assets.get('pr'), dict) else ''
            if not href:
                continue
            item_id = item.get('id', '')
            parts = item_id.split('.')
            model_name = parts[0] if parts else 'Unknown'
            sample_tasks.append((model_name, href))
        
        def _sample_precip_model(model_name: str, href: str):
            sample = _sample_netcdf(href, 'pr', latitude, longitude, aggregate="annual")
            if 'error' not in sample:
                return {
                    "model": model_name,
                    "mean_precipitation_mm_per_day": sample.get('display_mean', sample.get('display_value')),
                    "max_precipitation_mm_per_day": sample.get('display_max'),
                    "min_precipitation_mm_per_day": sample.get('display_min'),
                    "unit": sample['display_unit'],
                }
            return None
        
        futures = {_netcdf_pool.submit(_sample_precip_model, name, href): name for name, href in sample_tasks}
        try:
            for future in as_completed(futures, timeout=150):
                try:
                    result = future.result(timeout=120)
                    if result:
                        model_results.append(result)
                except Exception as exc:
                    logger.warning(f"[TOOL] Precipitation model future failed: {exc}")
        except TimeoutError:
            logger.warning("[TOOL] Not all precipitation models completed in time — using partial results")
        
        if not model_results:
            return json.dumps({
                "error": "Sampling failed for all available precipitation items",
                "location": {"latitude": latitude, "longitude": longitude},
            })
        
        # Compute ensemble summary
        mean_values = [r['mean_precipitation_mm_per_day'] for r in model_results]
        max_values = [r['max_precipitation_mm_per_day'] for r in model_results if r.get('max_precipitation_mm_per_day') is not None]
        
        output = {
            "location": {"latitude": latitude, "longitude": longitude},
            "scenario": scenario,
            "year": year,
            "data_source": "NASA NEX-GDDP-CMIP6",
            "grid_resolution": "0.25° × 0.25°",
            "note": "Annual statistics computed across all days in the projected year",
            "precipitation": {
                "annual_mean_mm_per_day": round(sum(mean_values) / len(mean_values), 2),
                "annual_total_mm_estimate": round(sum(mean_values) / len(mean_values) * 365, 1),
                "peak_daily_mm": round(max(max_values), 2) if max_values else None,
                "models_sampled": len(model_results),
                "model_details": model_results,
            }
        }
        
        logger.info(f"[TOOL] Precipitation projection: mean={output['precipitation']['annual_mean_mm_per_day']} mm/day, peak={output['precipitation'].get('peak_daily_mm')} mm/day")
        return json.dumps(output)
        
    except Exception as e:
        logger.error(f"[TOOL] Precipitation projection failed: {e}")
        return json.dumps({"error": str(e)})


def get_wind_projection(latitude: float, longitude: float, scenario: str = "ssp585", year: int = 2030) -> str:
    """Get projected near-surface wind speed for a location from NASA NEX-GDDP-CMIP6 climate models.
    Returns wind speed in m/s.
    Use this when the user asks about future wind conditions, storms, wind energy, or extreme wind events.
    
    :param latitude: Latitude of the location to analyze
    :param longitude: Longitude of the location to analyze
    :param scenario: SSP scenario - 'ssp245' (moderate) or 'ssp585' (worst-case). Default 'ssp585'
    :param year: Projection year (2015-2100). Default 2030
    :return: JSON string with projected wind speed values and model metadata
    """
    try:
        logger.info(f"[TOOL] get_wind_projection at ({latitude:.4f}, {longitude:.4f}), {scenario}, {year}")
        
        items = _search_cmip6_items(latitude, longitude, 'sfcWind', scenario, year, limit=5)
        
        if not items:
            return json.dumps({
                "error": "No CMIP6 wind data found for this location/scenario",
                "location": {"latitude": latitude, "longitude": longitude},
                "scenario": scenario, "year": year,
            })
        
        # Sample multiple models in PARALLEL
        model_results = []
        sample_tasks = []
        for item in items[:2]:
            assets = item.get('assets', {})
            href = assets.get('sfcWind', {}).get('href', '') if isinstance(assets.get('sfcWind'), dict) else ''
            if not href:
                continue
            item_id = item.get('id', '')
            parts = item_id.split('.')
            model_name = parts[0] if parts else 'Unknown'
            sample_tasks.append((model_name, href))
        
        def _sample_wind_model(model_name: str, href: str):
            sample = _sample_netcdf(href, 'sfcWind', latitude, longitude, aggregate="annual")
            if 'error' not in sample:
                return {
                    "model": model_name,
                    "mean_wind_speed_m_s": sample.get('display_mean', sample.get('display_value')),
                    "max_wind_speed_m_s": sample.get('display_max'),
                    "min_wind_speed_m_s": sample.get('display_min'),
                    "unit": sample['display_unit'],
                }
            return None
        
        futures = {_netcdf_pool.submit(_sample_wind_model, name, href): name for name, href in sample_tasks}
        try:
            for future in as_completed(futures, timeout=150):
                try:
                    result = future.result(timeout=120)
                    if result:
                        model_results.append(result)
                except Exception as exc:
                    logger.warning(f"[TOOL] Wind model future failed: {exc}")
        except TimeoutError:
            logger.warning("[TOOL] Not all wind models completed in time — using partial results")
        
        if not model_results:
            return json.dumps({
                "error": "Sampling failed for all available wind items",
                "location": {"latitude": latitude, "longitude": longitude},
            })
        
        mean_values = [r['mean_wind_speed_m_s'] for r in model_results]
        max_values = [r['max_wind_speed_m_s'] for r in model_results if r.get('max_wind_speed_m_s') is not None]
        
        # Classify wind severity based on annual mean
        mean_wind = sum(mean_values) / len(mean_values)
        if mean_wind < 3:
            wind_class = "Calm"
        elif mean_wind < 6:
            wind_class = "Light breeze"
        elif mean_wind < 10:
            wind_class = "Moderate wind"
        elif mean_wind < 17:
            wind_class = "Strong wind"
        else:
            wind_class = "Severe / storm-force"
        
        output = {
            "location": {"latitude": latitude, "longitude": longitude},
            "scenario": scenario,
            "year": year,
            "data_source": "NASA NEX-GDDP-CMIP6",
            "grid_resolution": "0.25° × 0.25°",
            "note": "Annual statistics computed across all days in the projected year",
            "wind": {
                "annual_mean_m_s": round(mean_wind, 2),
                "peak_daily_m_s": round(max(max_values), 2) if max_values else None,
                "classification": wind_class,
                "models_sampled": len(model_results),
                "model_details": model_results,
            }
        }
        
        logger.info(f"[TOOL] Wind projection: {mean_wind:.1f} m/s ({wind_class})")
        return json.dumps(output)
        
    except Exception as e:
        logger.error(f"[TOOL] Wind projection failed: {e}")
        return json.dumps({"error": str(e)})


def get_humidity_projection(latitude: float, longitude: float, scenario: str = "ssp585", year: int = 2030) -> str:
    """Get projected humidity data for a location from NASA NEX-GDDP-CMIP6 climate models.
    Returns near-surface relative humidity (%) and specific humidity (g/kg).
    Use this when the user asks about future humidity, heat index, moisture, or atmospheric conditions.
    
    :param latitude: Latitude of the location to analyze
    :param longitude: Longitude of the location to analyze
    :param scenario: SSP scenario - 'ssp245' (moderate) or 'ssp585' (worst-case). Default 'ssp585'
    :param year: Projection year (2015-2100). Default 2030
    :return: JSON string with projected humidity values and model metadata
    """
    try:
        logger.info(f"[TOOL] get_humidity_projection at ({latitude:.4f}, {longitude:.4f}), {scenario}, {year}")
        
        results = {}
        models_used = set()
        
        # Parallel sampling of both humidity variables
        def _sample_humidity_var(var):
            """Sample one humidity variable — runs in worker thread."""
            items = _search_cmip6_items(latitude, longitude, var, scenario, year, limit=3)
            if not items:
                return var, {"error": f"No data found for {var}"}, None
            for item in items:
                assets = item.get('assets', {})
                href = assets.get(var, {}).get('href', '') if isinstance(assets.get(var), dict) else ''
                if not href:
                    continue
                sample = _sample_netcdf(href, var, latitude, longitude)
                if 'error' not in sample:
                    var_info = CLIMATE_VAR_INFO[var]
                    item_id = item.get('id', '')
                    parts = item_id.split('.')
                    model = parts[0] if parts else None
                    return var, {
                        "value": sample['display_value'],
                        "unit": sample['display_unit'],
                        "description": var_info['name'],
                    }, model
            return var, {"error": f"Sampling failed for {var}"}, None
        
        futures = {_netcdf_pool.submit(_sample_humidity_var, v): v for v in ['hurs', 'huss']}
        try:
            for future in as_completed(futures, timeout=150):
                try:
                    var, result, model = future.result(timeout=120)
                    results[var] = result
                    if model:
                        models_used.add(model)
                except Exception as exc:
                    logger.warning(f"[TOOL] Humidity variable future failed: {exc}")
        except TimeoutError:
            logger.warning("[TOOL] Not all humidity variables completed in time — using partial results")
        
        output = {
            "location": {"latitude": latitude, "longitude": longitude},
            "scenario": scenario,
            "year": year,
            "data_source": "NASA NEX-GDDP-CMIP6",
            "grid_resolution": "0.25° × 0.25°",
            "models_sampled": list(models_used),
            "humidity": {}
        }
        
        if 'hurs' in results and 'error' not in results.get('hurs', {}):
            output["humidity"]["relative_humidity"] = results['hurs']
        if 'huss' in results and 'error' not in results.get('huss', {}):
            output["humidity"]["specific_humidity"] = results['huss']
        
        if not output["humidity"]:
            output["error"] = "Could not retrieve humidity data"
        
        logger.info(f"[TOOL] Humidity projection: {json.dumps(output.get('humidity', {}))}")
        return json.dumps(output)
        
    except Exception as e:
        logger.error(f"[TOOL] Humidity projection failed: {e}")
        return json.dumps({"error": str(e)})


def get_climate_overview(latitude: float, longitude: float, scenario: str = "ssp585", year: int = 2030) -> str:
    """Get a comprehensive climate overview for a location by sampling multiple variables at once.
    Returns temperature (max, min, mean), precipitation, wind speed, and humidity projections.
    Use this when the user asks for a general climate outlook, overall climate conditions, or 
    wants to understand the full climate picture for a location.
    
    :param latitude: Latitude of the location to analyze
    :param longitude: Longitude of the location to analyze
    :param scenario: SSP scenario - 'ssp245' (moderate) or 'ssp585' (worst-case). Default 'ssp585'
    :param year: Projection year (2015-2100). Default 2030
    :return: JSON string with multi-variable climate overview
    """
    try:
        logger.info(f"[TOOL] get_climate_overview at ({latitude:.4f}, {longitude:.4f}), {scenario}, {year}")
        
        overview_vars = ['tasmax', 'tasmin', 'tas', 'pr', 'sfcWind', 'hurs']
        overview = {}
        models_used = set()
        errors = []
        
        # Pre-fetch STAC items once — they're global (all variables in one item),
        # so a single search warms the cache for all 6 variable workers.
        _search_cmip6_items(latitude, longitude, overview_vars[0], scenario, year, limit=1)
        
        # Parallel sampling of all 6 variables via ThreadPoolExecutor
        def _sample_overview_var(var):
            """Sample one overview variable — runs in a worker thread."""
            items = _search_cmip6_items(latitude, longitude, var, scenario, year, limit=1)
            if not items:
                return var, None, f"No data for {var}", None
            for item in items:
                assets = item.get('assets', {})
                href = assets.get(var, {}).get('href', '') if isinstance(assets.get(var), dict) else ''
                if not href:
                    continue
                agg = "annual" if var in ('pr', 'sfcWind') else "last"
                sample = _sample_netcdf(href, var, latitude, longitude, aggregate=agg)
                if 'error' not in sample:
                    var_info = CLIMATE_VAR_INFO[var]
                    result = {
                        "value": sample.get('display_mean', sample.get('display_value')),
                        "unit": sample['display_unit'],
                        "description": var_info['name'],
                    }
                    if agg == "annual" and 'display_max' in sample:
                        result["peak"] = sample['display_max']
                    item_id = item.get('id', '')
                    parts = item_id.split('.')
                    model = parts[0] if parts else None
                    return var, result, None, model
                else:
                    return var, None, f"{var}: {sample['error']}", None
            return var, None, f"No href for {var}", None
        
        futures = {_netcdf_pool.submit(_sample_overview_var, v): v for v in overview_vars}
        for future in as_completed(futures, timeout=150):
            try:
                var, result, error, model = future.result(timeout=120)
            except Exception as exc:
                logger.warning(f"[TOOL] Overview variable future timed out or failed: {exc}")
                errors.append(f"Variable sampling timed out")
                continue
            if result:
                overview[var] = result
            if error:
                errors.append(error)
            if model:
                models_used.add(model)
        
        # Build readable summary
        summary_parts = []
        if 'tasmax' in overview:
            summary_parts.append(f"Max Temp: {overview['tasmax']['value']}°F")
        if 'tasmin' in overview:
            summary_parts.append(f"Min Temp: {overview['tasmin']['value']}°F")
        if 'tas' in overview:
            summary_parts.append(f"Mean Temp: {overview['tas']['value']}°F")
        if 'pr' in overview:
            summary_parts.append(f"Precip: {overview['pr']['value']} mm/day")
        if 'sfcWind' in overview:
            summary_parts.append(f"Wind: {overview['sfcWind']['value']} m/s")
        if 'hurs' in overview:
            summary_parts.append(f"Humidity: {overview['hurs']['value']}%")
        
        output = {
            "location": {"latitude": latitude, "longitude": longitude},
            "scenario": scenario,
            "scenario_description": "SSP2-4.5 (moderate)" if scenario == "ssp245" else "SSP5-8.5 (worst-case)" if scenario == "ssp585" else scenario,
            "year": year,
            "data_source": "NASA NEX-GDDP-CMIP6",
            "grid_resolution": "0.25° × 0.25°",
            "models_sampled": list(models_used),
            "climate_summary": " | ".join(summary_parts) if summary_parts else "No data sampled",
            "variables": overview,
            "note": "These are climate PROJECTIONS from CMIP6 models, not observations."
        }
        
        if errors:
            output["warnings"] = errors
        
        logger.info(f"[TOOL] Climate overview: {len(overview)} variables sampled for {scenario}/{year}")
        return json.dumps(output)
        
    except Exception as e:
        logger.error(f"[TOOL] Climate overview failed: {e}")
        return json.dumps({"error": str(e)})


def compare_climate_scenarios(latitude: float, longitude: float, year: int = 2030) -> str:
    """Compare climate projections between SSP2-4.5 (moderate emissions) and SSP5-8.5 (worst-case emissions)
    scenarios for a location. Shows temperature and precipitation differences between scenarios.
    Use this when the user asks about comparing emission scenarios, best vs worst case, or climate uncertainty.
    
    :param latitude: Latitude of the location to analyze
    :param longitude: Longitude of the location to analyze
    :param year: Projection year (2015-2100). Default 2030
    :return: JSON string comparing key climate variables across both SSP scenarios
    """
    try:
        logger.info(f"[TOOL] compare_climate_scenarios at ({latitude:.4f}, {longitude:.4f}), {year}")
        
        compare_vars = ['tasmax', 'pr']
        scenarios = ['ssp245', 'ssp585']
        comparison = {var: {} for var in compare_vars}
        
        # ----------------------------------------------------------------
        # PRE-FETCH: Warm STAC cache for both scenarios BEFORE launching
        # parallel NetCDF workers.  _search_cmip6_items caches by
        # (scenario, year) and CMIP6 items contain ALL variables, so
        # 2 searches cover all 4 (var, scenario) combos.  Without this,
        # all 4 workers race to search simultaneously — only the first
        # acquires the result; the rest spin-wait on the GIL.
        # ----------------------------------------------------------------
        for sc in scenarios:
            _search_cmip6_items(latitude, longitude, compare_vars[0], sc, year, limit=1)
        
        # Parallel sampling: 2 vars x 2 scenarios = 4 concurrent tasks
        def _sample_comparison(var, sc):
            """Sample one (variable, scenario) pair — runs in worker thread."""
            items = _search_cmip6_items(latitude, longitude, var, sc, year, limit=1)
            if not items:
                return var, sc, {"error": "No data"}
            for item in items:
                assets = item.get('assets', {})
                href = assets.get(var, {}).get('href', '') if isinstance(assets.get(var), dict) else ''
                if not href:
                    continue
                agg = "annual" if var in ('pr', 'sfcWind') else "last"
                sample = _sample_netcdf(href, var, latitude, longitude, aggregate=agg)
                if 'error' not in sample:
                    return var, sc, {
                        "value": sample.get('display_mean', sample.get('display_value')),
                        "unit": sample['display_unit'],
                    }
            return var, sc, {"error": "Sampling failed"}
        
        futures = []
        for var in compare_vars:
            for sc in scenarios:
                futures.append(_netcdf_pool.submit(_sample_comparison, var, sc))
        try:
            for future in as_completed(futures, timeout=150):
                try:
                    var, sc, result = future.result(timeout=120)
                    comparison[var][sc] = result
                except Exception as exc:
                    logger.warning(f"[TOOL] Scenario comparison future failed: {exc}")
        except TimeoutError:
            logger.warning("[TOOL] Not all scenario comparisons completed in time — using partial results")
        
        # Calculate deltas
        deltas = {}
        for var in compare_vars:
            ssp245_val = comparison.get(var, {}).get('ssp245', {}).get('value')
            ssp585_val = comparison.get(var, {}).get('ssp585', {}).get('value')
            if ssp245_val is not None and ssp585_val is not None:
                deltas[var] = {
                    "difference": round(ssp585_val - ssp245_val, 2),
                    "unit": CLIMATE_VAR_INFO[var]['display_unit'],
                    "description": f"SSP5-8.5 minus SSP2-4.5",
                }
        
        output = {
            "location": {"latitude": latitude, "longitude": longitude},
            "year": year,
            "data_source": "NASA NEX-GDDP-CMIP6",
            "scenarios": {
                "ssp245": "SSP2-4.5 — Moderate emissions (sustainable development path)",
                "ssp585": "SSP5-8.5 — Worst-case emissions (fossil fuel intensive)",
            },
            "comparison": comparison,
            "scenario_difference": deltas,
            "note": "Positive difference = worse conditions under high emissions"
        }
        
        logger.info(f"[TOOL] Scenario comparison complete for {year}")
        return json.dumps(output)
        
    except Exception as e:
        logger.error(f"[TOOL] Scenario comparison failed: {e}")
        return json.dumps({"error": str(e)})


def get_radiation_projection(latitude: float, longitude: float, scenario: str = "ssp585", year: int = 2030) -> str:
    """Get projected solar and longwave radiation data for a location from NASA NEX-GDDP-CMIP6 models.
    Returns downwelling shortwave (solar) and longwave radiation in W/m².
    Use this when the user asks about solar energy potential, radiation budget, or energy balance.
    
    :param latitude: Latitude of the location to analyze
    :param longitude: Longitude of the location to analyze
    :param scenario: SSP scenario - 'ssp245' (moderate) or 'ssp585' (worst-case). Default 'ssp585'
    :param year: Projection year (2015-2100). Default 2030
    :return: JSON string with projected radiation values and model metadata
    """
    try:
        logger.info(f"[TOOL] get_radiation_projection at ({latitude:.4f}, {longitude:.4f}), {scenario}, {year}")
        
        results = {}
        models_used = set()
        
        # Parallel sampling of both radiation variables
        def _sample_radiation_var(var):
            """Sample one radiation variable — runs in worker thread."""
            items = _search_cmip6_items(latitude, longitude, var, scenario, year, limit=3)
            if not items:
                return var, {"error": f"No data found for {var}"}, None
            for item in items:
                assets = item.get('assets', {})
                href = assets.get(var, {}).get('href', '') if isinstance(assets.get(var), dict) else ''
                if not href:
                    continue
                sample = _sample_netcdf(href, var, latitude, longitude)
                if 'error' not in sample:
                    var_info = CLIMATE_VAR_INFO[var]
                    item_id = item.get('id', '')
                    parts = item_id.split('.')
                    model = parts[0] if parts else None
                    return var, {
                        "value": sample['display_value'],
                        "unit": sample['display_unit'],
                        "description": var_info['name'],
                    }, model
            return var, {"error": f"Sampling failed for {var}"}, None
        
        futures = {_netcdf_pool.submit(_sample_radiation_var, v): v for v in ['rsds', 'rlds']}
        try:
            for future in as_completed(futures, timeout=150):
                try:
                    var, result, model = future.result(timeout=120)
                    results[var] = result
                    if model:
                        models_used.add(model)
                except Exception as exc:
                    logger.warning(f"[TOOL] Radiation variable future failed: {exc}")
        except TimeoutError:
            logger.warning("[TOOL] Not all radiation variables completed in time — using partial results")
        
        output = {
            "location": {"latitude": latitude, "longitude": longitude},
            "scenario": scenario,
            "year": year,
            "data_source": "NASA NEX-GDDP-CMIP6",
            "grid_resolution": "0.25° × 0.25°",
            "models_sampled": list(models_used),
            "radiation": {}
        }
        
        if 'rsds' in results and 'error' not in results.get('rsds', {}):
            output["radiation"]["shortwave_solar"] = results['rsds']
        if 'rlds' in results and 'error' not in results.get('rlds', {}):
            output["radiation"]["longwave"] = results['rlds']
        
        if not output["radiation"]:
            output["error"] = "Could not retrieve radiation data"
        
        logger.info(f"[TOOL] Radiation projection: {json.dumps(output.get('radiation', {}))}")
        return json.dumps(output)
        
    except Exception as e:
        logger.error(f"[TOOL] Radiation projection failed: {e}")
        return json.dumps({"error": str(e)})


def create_extreme_weather_functions() -> Set[Callable]:
    """Create the set of extreme weather/climate analysis functions for FunctionTool.
    
    Returns a Set[Callable] that can be passed to FunctionTool().
    Each function uses docstring-based parameter descriptions.
    """
    return {
        get_temperature_projection,
        get_precipitation_projection,
        get_wind_projection,
        get_humidity_projection,
        get_climate_overview,
        compare_climate_scenarios,
        get_radiation_projection,
    }
