# FastAPI Earth Copilot API - Complete Implementation
# Containerized version with full Earth Copilot functionality ported from Azure Functions

from fastapi import FastAPI, HTTPException, Request, Body
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
import json
import logging
import os
import sys
import traceback
import asyncio
from datetime import datetime, timedelta
from typing import Dict, Any, List, Optional, Tuple
import aiohttp
import sys
import os
from pathlib import Path
import hashlib
import time

# Import Earth Copilot modules
from semantic_translator import SemanticQueryTranslator
from titiler_config import get_tile_scale  # Legacy tile scale function
from hybrid_rendering_system import HybridRenderingSystem  # [ART] Comprehensive rendering system
from tile_selector import TileSelector  # [TARGET] Smart tile selection and ranking
from quickstart_cache import (
    is_quickstart_query, 
    get_quickstart_classification, 
    get_quickstart_location,
    get_quickstart_stats
)  # [LAUNCH] Pre-computed cache for demo queries
from cloud_config import cloud_cfg  # [CLOUD] Cloud environment configuration (Commercial/Government)

# Microsoft Teams Bot integration (optional — requires botbuilder-core)
try:
    from teams_bot import EarthCopilotBot, create_bot_adapter
    from botbuilder.schema import Activity
    TEAMS_BOT_AVAILABLE = True
except ImportError:
    TEAMS_BOT_AVAILABLE = False

# ============================================================================
# � INSTANT PIPELINE TRACING - Collect steps for API response
# ============================================================================
# This allows instant troubleshooting by including trace in the response
# No need to wait for Log Analytics - see exactly what each agent did
# ============================================================================
pipeline_traces: Dict[str, List[Dict]] = {}  # session_id -> list of trace entries

def get_pipeline_trace(session_id: str) -> List[Dict]:
    """Get all trace entries for a session"""
    return pipeline_traces.get(session_id, [])

def clear_pipeline_trace(session_id: str):
    """Clear trace for a session (call at start of new query)"""
    pipeline_traces[session_id] = []

# ============================================================================
# �[SEARCH] PIPELINE LOGGING HELPER - Structured logging for debugging queries
# ============================================================================
def log_pipeline_step(session_id: str, step_name: str, stage: str, data: dict, elapsed_ms: float = None):
    """
    Log a pipeline step with structured format for easy filtering and debugging.
    
    Args:
        session_id: Unique identifier for this query session
        step_name: Name of the agent/step (e.g., "STAC_SEARCH", "TILE_URLS")
        stage: Either "INPUT" or "OUTPUT"
        data: Dictionary of relevant data to log
        elapsed_ms: Optional elapsed time in milliseconds
    """
    prefix = f"[PIPELINE:{session_id}]"
    timing = f" ({elapsed_ms:.0f}ms)" if elapsed_ms else ""
    
    # Truncate large data for readability
    data_str = json.dumps(data, default=str)
    if len(data_str) > 500:
        data_str = data_str[:500] + "..."
    
    logging.info(f"{prefix} {step_name} {stage}: {data_str}{timing}")
    
    # [MICRO] INSTANT TRACING: Also collect for API response
    if session_id and session_id != 'N/A':
        if session_id not in pipeline_traces:
            pipeline_traces[session_id] = []
        
        trace_entry = {
            "timestamp": datetime.utcnow().isoformat(),
            "step": step_name,
            "stage": stage,
            "data": data,  # Keep full data for trace
        }
        if elapsed_ms:
            trace_entry["elapsed_ms"] = round(elapsed_ms, 1)
        
        pipeline_traces[session_id].append(trace_entry)

# ========================================================================
# [TARGET] SMART TILE DEDUPLICATION
# ========================================================================
# Prevents multiple tiles from different dates overlapping on the same location.
# Only applies to optical imagery when no explicit temporal query is made.
# ========================================================================

# Collections that benefit from deduplication (optical imagery)
OPTICAL_COLLECTIONS = [
    'sentinel-2-l2a', 'sentinel-2-l1c',
    'landsat-c2-l2', 'landsat-c2-l1', 'landsat-8-c2-l2', 'landsat-9-c2-l2',
    'hls-l30', 'hls-s30', 'hls2-l30', 'hls2-s30',
    'naip'
]

# Keywords indicating user wants multiple dates (skip deduplication)
TEMPORAL_KEYWORDS = [
    'change', 'time series', 'progression', 'over time', 'compare',
    'before and after', 'between', 'from', 'to', 'trend', 'evolution',
    'history', 'historical', 'monthly', 'weekly', 'daily'
]

# Collections to NEVER deduplicate (fire, disaster monitoring need temporal data)
SKIP_DEDUP_COLLECTIONS = [
    'modis-14A1-061', 'modis-14A2-061',  # Fire detection
    'sentinel-1-rtc', 'sentinel-1-grd',   # SAR (different polarizations)
]

def should_deduplicate_tiles(collections: List[str], original_query: str = None) -> bool:
    """
    Determine if tile deduplication should be applied.
    
    Returns True only for optical imagery queries without explicit temporal intent.
    """
    if not collections:
        return False
    
    # Check if any collection is optical
    is_optical = any(
        any(opt in coll.lower() for opt in OPTICAL_COLLECTIONS)
        for coll in collections
    )
    
    if not is_optical:
        logging.debug(f"[SYNC] Dedup: Skipping - not optical collection: {collections}")
        return False
    
    # Check if any collection should never be deduplicated
    should_skip = any(
        any(skip in coll.lower() for skip in SKIP_DEDUP_COLLECTIONS)
        for coll in collections
    )
    
    if should_skip:
        logging.debug(f"[SYNC] Dedup: Skipping - fire/SAR collection: {collections}")
        return False
    
    # Check for temporal keywords in query
    if original_query:
        query_lower = original_query.lower()
        has_temporal_intent = any(kw in query_lower for kw in TEMPORAL_KEYWORDS)
        if has_temporal_intent:
            logging.info(f"[SYNC] Dedup: Skipping - temporal query detected: '{original_query[:50]}...'")
            return False
    
    logging.info(f"[OK] Dedup: Will deduplicate optical tiles for: {collections}")
    return True

def extract_tile_grid_id(feature: Dict[str, Any]) -> Optional[str]:
    """
    Extract the grid/tile ID from a STAC feature.
    
    Works for:
    - Sentinel-2: MGRS tile ID (e.g., T37VDC)
    - Landsat: WRS-2 path/row (e.g., path_168_row_37)
    - HLS: MGRS tile ID
    """
    feature_id = feature.get('id', '')
    collection = feature.get('collection', '')
    properties = feature.get('properties', {})
    
    # Sentinel-2 / HLS: Extract MGRS tile from ID
    # Format: S2B_MSIL2A_20251229T085259_R107_T37VDC_20251229T110511
    # The MGRS tile is the part starting with 'T' followed by numbers+letters
    if 'sentinel-2' in collection.lower() or 'hls' in collection.lower():
        import re
        mgrs_match = re.search(r'_T(\d{2}[A-Z]{3})_', feature_id)
        if mgrs_match:
            return f"T{mgrs_match.group(1)}"
        # Also check properties
        if 's2:mgrs_tile' in properties:
            return properties['s2:mgrs_tile']
    
    # Landsat: Extract path/row
    # Format: LC09_L2SP_168037_20251225_... or properties contain path/row
    if 'landsat' in collection.lower():
        # Check properties first
        if 'landsat:wrs_path' in properties and 'landsat:wrs_row' in properties:
            return f"p{properties['landsat:wrs_path']}_r{properties['landsat:wrs_row']}"
        # Extract from ID
        import re
        pathrow_match = re.search(r'_(\d{6})_', feature_id)
        if pathrow_match:
            return pathrow_match.group(1)
    
    # Fallback: Use bbox as a rough grid ID (round to 1 degree)
    bbox = feature.get('bbox')
    if bbox and len(bbox) >= 4:
        # Round to nearest degree for grid cell
        return f"grid_{int(bbox[0])}_{int(bbox[1])}"
    
    return None

def deduplicate_tiles_by_grid(features: List[Dict[str, Any]], original_query: str = None) -> List[Dict[str, Any]]:
    """
    Deduplicate STAC features by grid location, keeping only the most recent tile per grid cell.
    
    This prevents multiple tiles from different dates overlapping on the same location.
    Features are assumed to be sorted by datetime descending (most recent first).
    
    Args:
        features: List of STAC features (sorted by datetime desc)
        original_query: Original user query (to check for temporal intent)
    
    Returns:
        Deduplicated list of features (one per grid cell)
    """
    if not features:
        return features
    
    # Get collection from first feature
    collections = list(set(f.get('collection', '') for f in features if f.get('collection')))
    
    # Check if we should deduplicate
    if not should_deduplicate_tiles(collections, original_query):
        return features
    
    original_count = len(features)
    seen_grids = set()
    deduplicated = []
    
    for feature in features:
        grid_id = extract_tile_grid_id(feature)
        
        if grid_id is None:
            # Can't determine grid - keep the feature
            deduplicated.append(feature)
            continue
        
        if grid_id not in seen_grids:
            seen_grids.add(grid_id)
            deduplicated.append(feature)
        else:
            # Skip - we already have a more recent tile for this grid
            logging.debug(f"[SYNC] Dedup: Skipping duplicate grid {grid_id} (feature: {feature.get('id', 'unknown')[:50]})")
    
    if len(deduplicated) < original_count:
        logging.info(f"[TARGET] TILE DEDUPLICATION: {original_count} -> {len(deduplicated)} tiles (removed {original_count - len(deduplicated)} duplicates)")
        logging.info(f"[TARGET] Unique grid cells: {list(seen_grids)[:10]}{'...' if len(seen_grids) > 10 else ''}")
    
    return deduplicated

# ========================================================================

# Wrapper for backward compatibility
def build_tile_url_params(collection_id: str, query_context: str = None) -> str:
    """
    Build optimal TiTiler URL parameters using the Hybrid Rendering System.
    
    This provides intelligent rendering for 113+ STAC collections through:
    1. Explicit configurations for known collections
    2. Smart pattern matching for collection families  
    3. Dynamic STAC metadata inference
    4. Safe fallbacks for unknown collections
    """
    return HybridRenderingSystem.build_titiler_url_params(collection_id, query_context)

# Import Planetary Computer authentication
try:
    import planetary_computer
    PLANETARY_COMPUTER_AVAILABLE = True
    logging.info("[OK] Planetary Computer authentication available")
except ImportError as e:
    PLANETARY_COMPUTER_AVAILABLE = False
    logging.warning(f"[WARN] Planetary Computer authentication not available: {e}")

# Import PC config loader for STAC search and rendering (single source of truth)
try:
    from pc_tasks_config_loader import (
        load_pc_metadata,
        get_collection_metadata,
        get_pc_rendering_config as get_rendering_config,
        get_all_collection_ids
    )
    PC_METADATA_AVAILABLE = True
    metadata = load_pc_metadata()
    total_collections = metadata.get('metadata', {}).get('total_collections', 0)
    logging.info(f"[OK] PC metadata loaded: {total_collections} collections from PC repository")
except ImportError as e:
    PC_METADATA_AVAILABLE = False
    logging.warning(f"[WARN] PC config loader not available: {e}")
    
    # Fallback stubs
    def load_pc_metadata(): return {'categories': []}
    def get_collection_metadata(cid): return None
    def get_rendering_config(cid): return None
    def get_all_collection_ids(): return []

# Coverage check function (using PC metadata)
def check_collection_coverage(collection_id: str, bbox: list) -> dict:
    """Check if collection covers the requested bbox - using PC metadata"""
    coll_metadata = get_collection_metadata(collection_id)
    if coll_metadata:
        # For now, assume all collections have global or sufficient coverage
        # Can be enhanced with actual spatial extent checks
        return {"covered": True, "message": f"Collection {collection_id} available"}
    return {"covered": False, "message": f"Collection {collection_id} not found in PC metadata"}

# Import GEOINT functionality - endpoints use lazy imports per request
GEOINT_AVAILABLE = True  # Always available - imports happen at endpoint level
logging.info("[OK] GEOINT endpoints available (lazy import mode)")

# Environment loading
try:
    from dotenv import load_dotenv
    env_path = os.path.join(os.path.dirname(__file__), '.env')
    if os.path.exists(env_path):
        load_dotenv(env_path)
        print(f"Loaded local environment from: {env_path}")
except ImportError:
    print("Using system environment variables")

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Initialize FastAPI app
app = FastAPI(title="Earth Copilot API", version="1.0.0")

# Configure CORS origins from environment variable
cors_origins_str = os.environ.get("CORS_ORIGINS", "*")
cors_origins = [origin.strip() for origin in cors_origins_str.split(",")] if cors_origins_str != "*" else ["*"]
logger.info(f"[LOCK] CORS configured for origins: {cors_origins}")

# Add CORS middleware (must be outermost — runs first on requests, last on responses)
app.add_middleware(
    CORSMiddleware,
    allow_origins=cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Add Entra ID JWT auth middleware (validates Bearer tokens on protected routes)
# Registered AFTER CORSMiddleware so CORS headers are always added, even on 401.
# Open paths (/api/health, /docs, etc.) are excluded from auth.
try:
    from auth_middleware import EntraAuthMiddleware
    app.add_middleware(EntraAuthMiddleware)
    logger.info("[AUTH] Entra ID auth middleware registered")
except ImportError as e:
    logger.warning(f"[AUTH] Auth middleware not available — all routes are open: {e}")

# Mount static files for React frontend (if static directory exists)
static_dir = os.path.join(os.path.dirname(__file__), "static")
if os.path.exists(static_dir):
    from fastapi.staticfiles import StaticFiles
    
    # Mount static assets at root level to match React build paths
    app.mount("/assets", StaticFiles(directory=os.path.join(static_dir, "assets")), name="assets")
    logger.info(f"[OK] Mounted static assets from: {os.path.join(static_dir, 'assets')}")
    
    # Also mount full static directory for any other static files
    app.mount("/static", StaticFiles(directory=static_dir), name="static")
    logger.info(f"[OK] Mounted static files from: {static_dir}")
    
    # Handle favicon requests to prevent 404 errors
    @app.get("/favicon.ico")
    async def favicon():
        """Return empty response for favicon to prevent 404 errors"""
        from fastapi.responses import Response
        return Response(status_code=204)  # 204 No Content
    
    # Serve JSON files from static root
    @app.get("/pc_collections_metadata.json")
    async def serve_pc_collections_metadata():
        """Serve PC collections metadata JSON (from unified config)"""
        from fastapi.responses import JSONResponse
        
        # Get data from unified JSON
        metadata = load_pc_metadata()
        
        if metadata and metadata.get('categories'):
            return JSONResponse(content=metadata)
        
        # Fallback: try to serve static file if it exists
        from fastapi.responses import FileResponse
        json_path = os.path.join(static_dir, "pc_collections_metadata.json")
        if os.path.exists(json_path):
            logger.warning("[WARN]  Serving legacy pc_collections_metadata.json - should migrate to unified config")
            return FileResponse(json_path, media_type="application/json")
        
        from fastapi import HTTPException
        raise HTTPException(status_code=404, detail="Collections metadata not found")
    
    @app.get("/stac_collections.json")
    async def serve_stac_collections():
        """
        Serve STAC collections JSON for frontend dropdown
        Now generated dynamically from unified pc_rendering_config.json
        """
        from fastapi.responses import JSONResponse
        
        if not PC_METADATA_AVAILABLE:
            from fastapi import HTTPException
            raise HTTPException(status_code=503, detail="Collections metadata not loaded")
        
        # Load metadata from unified source
        pc_metadata = load_pc_metadata()
        categories = pc_metadata.get('categories', [])
        
        # Transform categories structure to flat frontend format
        frontend_collections = []
        
        for category in categories:
            for collection in category.get('collections', []):
                frontend_collections.append({
                    "collection_id": collection.get('id'),
                    "description": collection.get('description', 'No description available'),
                    "category": category.get('name', 'Other')
                })
        
        # Sort by category, then by collection_id
        frontend_collections.sort(key=lambda x: (x["category"], x["collection_id"]))
        
        return JSONResponse(content=frontend_collections)
    
    # Serve React app at root path
    @app.get("/")
    async def serve_react_app():
        """Serve the React application"""
        index_path = os.path.join(static_dir, "index.html")
        if os.path.exists(index_path):
            with open(index_path, 'r', encoding='utf-8') as f:
                html_content = f.read()
            from fastapi.responses import HTMLResponse
            return HTMLResponse(content=html_content)
        else:
            return {"message": "Earth Copilot API is running", "frontend": "not_available"}
else:
    logger.warning(f"[WARN] Static directory not found: {static_dir}")
    
    # Default root endpoint when no static files
    @app.get("/")
    async def root():
        return {"message": "Earth Copilot API is running", "status": "ok", "version": "1.0.0"}

# Serve PC rendering config (ALWAYS AVAILABLE - not dependent on static dir)
@app.get("/pc_rendering_config.json")
async def serve_pc_rendering_config():
    """Serve unified PC rendering config JSON (contains descriptions AND rendering params)"""
    from fastapi.responses import FileResponse
    # Check in current directory (where fastapi_app.py is)
    json_path = os.path.join(os.path.dirname(__file__), "pc_rendering_config.json")
    logger.info(f"[SEARCH] Looking for pc_rendering_config.json at: {json_path}")
    logger.info(f"[DIR] File exists: {os.path.exists(json_path)}")
    if os.path.exists(json_path):
        logger.info(f"[OK] Serving pc_rendering_config.json from {json_path}")
        return FileResponse(json_path, media_type="application/json")
    from fastapi import HTTPException
    logger.error(f"[FAIL] PC rendering config not found at {json_path}")
    raise HTTPException(status_code=404, detail="PC rendering config not found")

# Global variables for components
semantic_translator = None
global_translator = None  # For session management
router_agent = None  # RouterAgent for intelligent query classification

# Initialize GEOINT processors
terrain_analyzer = None
mobility_classifier = None
los_calculator = None
geoint_utils = None
geoint_executor = None

# STAC endpoints configuration (driven by cloud_config for Commercial/Government)
STAC_ENDPOINTS = {
    "planetary_computer": cloud_cfg.stac_api_url,
    "veda": "https://openveda.cloud/api/stac/search"
}

# Feature availability flags
SEMANTIC_KERNEL_AVAILABLE = True  # Will be updated in startup

async def execute_direct_stac_search(stac_query: Dict[str, Any], stac_endpoint: str = "planetary_computer", original_query: str = None) -> Dict[str, Any]:
    """Execute STAC search against specified endpoint (Planetary Computer or VEDA)
    
    Args:
        stac_query: STAC API query parameters
        stac_endpoint: Which STAC endpoint to use
        original_query: Original user query (for smart deduplication)
    """
    try:
        stac_url = STAC_ENDPOINTS.get(stac_endpoint, STAC_ENDPOINTS["planetary_computer"])
        logger.info(f"[SEARCH] STAC SEARCH: {stac_endpoint} | collections={stac_query.get('collections', [])} | bbox={stac_query.get('bbox', 'NONE')} | datetime={stac_query.get('datetime', 'NONE')} | limit={stac_query.get('limit', 'default')}")
        
        # NOTE: We do NOT validate coverage proactively because STAC collection extents
        # represent "data exists somewhere in this region" not "complete coverage".
        # Instead, we let the search run and handle empty results with helpful messages.
        
        timeout = aiohttp.ClientTimeout(total=60)
        
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.post(stac_url, json=stac_query) as response:
                logger.info(f"[SEARCH] STAC SEARCH: HTTP {response.status}")
                
                if response.status == 200:
                    stac_response = await response.json()
                    features = stac_response.get('features', [])
                    
                    # Summarize results in one line
                    if features:
                        collections_returned = list(set(f.get('collection', '?') for f in features))
                        logger.info(f"[OK] STAC RESULTS: {len(features)} items from {collections_returned}")
                    else:
                        logger.warning(f"[WARN] STAC RESULTS: 0 items returned")
                    
                    # If no results, add helpful coverage information
                    coverage_info = None
                    if len(features) == 0:
                        collections = stac_query.get("collections", [])
                        bbox = stac_query.get("bbox")
                        
                        if collections and bbox:
                            # Check if location is likely outside collection coverage
                            for collection_id in collections:
                                coverage_check = check_collection_coverage(collection_id, bbox)
                                if not coverage_check["covered"]:
                                    coverage_info = {
                                        "message": coverage_check["message"],
                                        "alternatives": coverage_check.get("alternatives", [])
                                    }
                                    logger.info(f"ℹ️ No results - likely due to coverage: {coverage_info['message']}")
                                    break
                    
                    # Basic feature enhancement (simplified for now)
                    enhanced_features = features  # TODO: Add visualization metadata enhancement
                    
                    # [TARGET] TILE SELECTION: Select best tiles with temporal consistency
                    # IMPORTANT: TileSelector runs FIRST on all features so it can group by
                    # acquisition date and pick a single consistent date. Grid deduplication
                    # runs AFTER to remove duplicate grid cells within the selected date.
                    # This ensures all tiles on the map come from the same time period.
                    from tile_selector import TileSelector
                    bbox = stac_query.get("bbox")
                    collections = stac_query.get("collections", [])
                    
                    # Determine optimal tile limit based on ACTUAL area coverage needed
                    # HLS/Sentinel-2 tiles are ~100km × 100km (~1° × 1° at mid-latitudes)
                    max_tiles = 10  # Default for city-scale areas
                    if bbox and len(bbox) == 4:
                        # Calculate area in square degrees
                        width_deg = bbox[2] - bbox[0]
                        height_deg = bbox[3] - bbox[1]
                        area_degrees = width_deg * height_deg
                        
                        # Calculate tiles needed for full spatial coverage
                        # Assuming ~1° × 1° tiles (HLS/Sentinel-2), add 50% margin for overlap
                        import math
                        tiles_wide = math.ceil(width_deg / 1.0)
                        tiles_tall = math.ceil(height_deg / 1.0)
                        tiles_for_coverage = int(tiles_wide * tiles_tall * 1.5)  # 50% overlap margin
                        
                        if area_degrees > 25:  # Country-scale (e.g., Greece ~71 sq deg)
                            max_tiles = min(100, max(50, tiles_for_coverage))  # 50-100 tiles for countries
                            logger.info(f"[GLOBE] Country-scale area ({area_degrees:.1f} sq deg) -> max_tiles={max_tiles}")
                        elif area_degrees > 5:  # Large region (e.g., California, large state)
                            max_tiles = min(60, max(30, tiles_for_coverage))  # 30-60 tiles
                            logger.info(f"[MAP] Large region ({area_degrees:.1f} sq deg) -> max_tiles={max_tiles}")
                        elif area_degrees > 1.0:  # Medium region (multi-city area)
                            max_tiles = min(30, max(15, tiles_for_coverage))  # 15-30 tiles
                        elif area_degrees > 0.1:  # Small region (single city area)
                            max_tiles = 15
                        else:  # Point/small area
                            max_tiles = 10
                    
                    # STEP 1: Intelligent tile selection with date grouping on ALL candidates
                    # TileSelector groups by acquisition date and picks the best single date
                    selected_features = TileSelector.select_best_tiles(
                        features=enhanced_features,
                        query_bbox=bbox,
                        collections=collections,
                        max_tiles=max_tiles,
                        query=original_query
                    )
                    
                    # STEP 2: Grid deduplication within the selected date
                    # Removes duplicate grid cells (keeps most recent per location)
                    selected_features = deduplicate_tiles_by_grid(selected_features, original_query)
                    
                    logger.info(f"[TARGET] TILE PIPELINE: {len(features)} raw -> {len(selected_features)} final tiles (max={max_tiles})")
                    
                    result = {
                        "success": True,
                        "results": {
                            "type": "FeatureCollection",
                            "features": selected_features
                        },
                        "search_metadata": {
                            "total_found": len(features),
                            "total_selected": len(selected_features),
                            "query_used": stac_query,
                            "timestamp": datetime.utcnow().isoformat()
                        }
                    }
                    
                    # Add coverage info if no results and likely coverage issue
                    if coverage_info:
                        result["coverage_info"] = coverage_info
                    
                    return result
                else:
                    error_text = await response.text()
                    logger.error(f"[FAIL] STAC API error {response.status}: {error_text}")
                    return {
                        "success": False,
                        "error": f"STAC API returned {response.status}: {error_text}",
                        "results": {"type": "FeatureCollection", "features": []}
                    }
                    
    except Exception as e:
        logger.error(f"[FAIL] STAC search error: {e}")
        return {
            "success": False,
            "error": f"STAC search failed: {str(e)}",
            "results": {"type": "FeatureCollection", "features": []}
        }

@app.on_event("startup")
async def startup_event():
    """Initialize the application components"""
    global semantic_translator, global_translator, SEMANTIC_KERNEL_AVAILABLE, router_agent
    global terrain_analyzer, mobility_classifier, los_calculator, geoint_utils, GEOINT_AVAILABLE
    
    logger.info("[LAUNCH] EARTH COPILOT CONTAINER STARTING UP")
    
    try:
        # Initialize Semantic Translator components with environment variables
        azure_openai_endpoint = os.getenv("AZURE_OPENAI_ENDPOINT", "")
        azure_openai_api_key = os.getenv("AZURE_OPENAI_API_KEY", "")
        azure_openai_deployment = os.getenv("AZURE_OPENAI_DEPLOYMENT_NAME", "gpt-5")
        azure_openai_fast_deployment = os.getenv("AZURE_OPENAI_FAST_DEPLOYMENT", "gpt-4o-mini")
        use_managed_identity = os.getenv("USE_MANAGED_IDENTITY", "false").lower() == "true"
        
        logger.info(f"[LOCK] Environment check - Endpoint: {'[OK]' if azure_openai_endpoint else '[FAIL]'}, Key: {'[OK]' if azure_openai_api_key else '[FAIL]'}, Model: {azure_openai_deployment}, FastModel: {azure_openai_fast_deployment}, ManagedIdentity: {use_managed_identity}")
        
        # Initialize with API key if provided
        if azure_openai_endpoint and azure_openai_api_key:
            semantic_translator = SemanticQueryTranslator(
                azure_openai_endpoint=azure_openai_endpoint,
                azure_openai_api_key=azure_openai_api_key,
                model_name=azure_openai_deployment
            )
            global_translator = semantic_translator  # For session management
            SEMANTIC_KERNEL_AVAILABLE = True
            logger.info("[OK] Earth Copilot API initialized successfully with Semantic Translator (API Key)")
        # Try managed identity if endpoint provided but no API key
        elif azure_openai_endpoint and use_managed_identity:
            try:
                from azure.identity import DefaultAzureCredential
                logger.info("[KEY] Attempting managed identity authentication for Azure OpenAI...")
                credential = DefaultAzureCredential()
                # Get token to verify credential works
                token = credential.get_token(cloud_cfg.cognitive_services_scope)
                logger.info("[OK] Successfully obtained Azure AD token for Cognitive Services")
                
                semantic_translator = SemanticQueryTranslator(
                    azure_openai_endpoint=azure_openai_endpoint,
                    azure_openai_api_key=None,  # No API key - will use credential
                    model_name=azure_openai_deployment,
                    azure_credential=credential  # Pass credential for managed identity
                )
                global_translator = semantic_translator  # For session management
                SEMANTIC_KERNEL_AVAILABLE = True
                logger.info("[OK] Earth Copilot API initialized successfully with Semantic Translator (Managed Identity)")
            except Exception as e:
                logger.error(f"[FAIL] Failed to initialize with managed identity: {e}")
                logger.warning("[WARN] Running in limited mode - no Azure OpenAI access")
                semantic_translator = None
                global_translator = None
                SEMANTIC_KERNEL_AVAILABLE = False
        else:
            logger.warning("[WARN] Azure OpenAI credentials not provided - running in limited mode")
            semantic_translator = None
            global_translator = None
            SEMANTIC_KERNEL_AVAILABLE = False
            
        # GEOINT endpoints use lazy imports - no initialization needed here
        logger.info("[OK] GEOINT endpoints ready (lazy import mode)")

        # Initialize RouterAgent for intelligent query classification
        try:
            from geoint.router_agent import get_router_agent
            router_agent = get_router_agent()
            if global_translator:
                router_agent.set_semantic_translator(global_translator)
            logger.info("[OK] RouterAgent initialized for intelligent query routing")
        except Exception as e:
            logger.warning(f"[WARN] RouterAgent initialization failed: {e} - will use fallback classification")
            router_agent = None
        
        # Log quick start cache status
        qs_stats = get_quickstart_stats()
        logger.info(f"[LAUNCH] Quick Start Cache: {qs_stats['total_queries']} queries, {len(qs_stats['collections_covered'])} collections")
        
        # Initialize Teams Bot (optional)
        global teams_bot, teams_bot_adapter
        if TEAMS_BOT_AVAILABLE:
            try:
                teams_bot = EarthCopilotBot()
                teams_bot_adapter = create_bot_adapter()
                app_id = os.getenv('MICROSOFT_APP_ID', '')
                logger.info(f"[BOT] Teams Bot initialized (app_id={'configured' if app_id else 'not set — open for testing'})")
            except Exception as e:
                logger.warning(f"[WARN] Teams Bot init failed: {e}")
                teams_bot = None
                teams_bot_adapter = None
        else:
            teams_bot = None
            teams_bot_adapter = None
            logger.info("ℹ️ Teams Bot not available (botbuilder-core not installed)")

        logger.info("[OK] EARTH COPILOT CONTAINER READY")
            
    except Exception as e:
        logger.error(f"[FAIL] Failed to initialize components: {str(e)}")
        logger.warning("[WARN] Running in limited mode")
        semantic_translator = None
        global_translator = None
        router_agent = None
        SEMANTIC_KERNEL_AVAILABLE = False

# Helper functions ported from Router Function App
def detect_collections(query: str) -> List[str]:
    """
    Enhanced collection detection from Router Function App - detects relevant collections based on query keywords
    """
    query = query.lower()
    detected_collections = []
    
    # Priority mapping for common use cases (matches Router Function App logic)
    if any(term in query for term in ['fire', 'wildfire', 'burn', 'thermal', 'heat']):
        # Fire detection - HIGH RESOLUTION FIRST for detailed fire perimeter analysis
        # Landsat (30m thermal) + Sentinel-2 (10m optical smoke) show detailed fire boundaries
        # MODIS (1km) included last for wide-area context only
        detected_collections.extend(['landsat-c2-l2', 'sentinel-2-l2a', 'modis-14A1-061'])
        
    elif any(term in query for term in ['elevation', 'dem', 'topography', 'terrain', 'height']):
        detected_collections.extend(['cop-dem-glo-30', 'cop-dem-glo-90', 'alos-dem'])
        
    elif any(term in query for term in ['radar', 'sar', 'interferometry']):
        detected_collections.extend(['sentinel-1-grd', 'sentinel-1-rtc'])
        
    elif any(term in query for term in ['optical', 'rgb', 'visible', 'true color']):
        detected_collections.extend(['sentinel-2-l2a', 'landsat-c2-l2'])
        
    elif any(term in query for term in ['vegetation', 'ndvi', 'agriculture', 'crop']):
        # Vegetation/NDVI - HIGH RESOLUTION FIRST for detailed crop analysis
        # Sentinel-2 (10m) and Landsat (30m) provide field-level detail
        # MODIS (250m-500m) included last for large-scale regional trends only
        detected_collections.extend(['sentinel-2-l2a', 'landsat-c2-l2', 'modis-13A1-061'])
        
    elif any(term in query for term in ['water', 'ocean', 'sea', 'lake', 'river']):
        detected_collections.extend(['sentinel-2-l2a', 'landsat-c2-l2', 'sentinel-1-grd'])
        
    else:
        # Default collections for general queries - HIGH RESOLUTION PRIORITY
        # Only Sentinel-2 (10m) and Landsat (30m) to ensure crisp imagery for cities/detailed areas
        # MODIS (500m) excluded from default as it's too coarse for most use cases (4 pixels per city block)
        detected_collections.extend(['sentinel-2-l2a', 'landsat-c2-l2'])
    
    # Remove duplicates while preserving order (validate against PC metadata)
    seen = set()
    unique_collections = []
    valid_collection_ids = set(get_all_collection_ids())
    for collection in detected_collections:
        if collection not in seen and collection in valid_collection_ids:
            seen.add(collection)
            unique_collections.append(collection)
    
    logger.info(f"[SEARCH] Detected collections for '{query}': {unique_collections}")
    return unique_collections

def generate_contextual_empty_response(
    query: str, 
    collections: List[str],
    diagnostics: Dict[str, Any]
) -> str:
    """
    Generate helpful response when no results found, with context-aware suggestions
    based on where the filtering pipeline failed.
    
    Args:
        query: Original user query
        collections: Collections searched
        diagnostics: {
            "raw_count": int,              # Results from STAC API
            "spatial_filtered_count": int, # After spatial overlap filter
            "final_count": int,            # After tile selection
            "stac_query": dict,            # Full STAC query with filters
            "failure_stage": str           # Where it failed
        }
    """
    raw_count = diagnostics.get("raw_count", 0)
    spatial_count = diagnostics.get("spatial_filtered_count", 0)
    final_count = diagnostics.get("final_count", 0)
    stac_query = diagnostics.get("stac_query", {})
    failure_stage = diagnostics.get("failure_stage", "unknown")
    
    response_parts = []
    
    # SCENARIO 1: STAC API returned nothing (most common)
    if raw_count == 0:
        response_parts.append(f"I searched for satellite data related to '{query}', but didn't find any available imagery matching your criteria.")
        
        # Analyze STAC query filters to provide specific suggestions
        suggestions = []
        
        # Check datetime constraints
        datetime_str = stac_query.get("datetime", "")
        if datetime_str and "/" in datetime_str:
            start, end = datetime_str.split("/")
            start_date = start[:10] if len(start) >= 10 else start
            end_date = end[:10] if len(end) >= 10 else end
            
            # Calculate date range in days
            try:
                from datetime import datetime as dt
                start_dt = dt.fromisoformat(start_date)
                end_dt = dt.fromisoformat(end_date)
                days = (end_dt - start_dt).days
                
                if days < 90:
                    suggestions.append(f"**Expand the date range**: Currently searching {days} days ({start_date} to {end_date}). Try expanding to 6 months or 1 year for more results.")
            except:
                pass
        
        # Check cloud cover constraints
        cloud_filter = stac_query.get("filter", {})
        if "eo:cloud_cover" in str(cloud_filter):
            cloud_threshold = None
            # Try to extract threshold from filter
            if isinstance(cloud_filter, dict):
                try:
                    # Handle different filter structures
                    filter_str = str(cloud_filter)
                    if "lt" in filter_str and "10" in filter_str:
                        cloud_threshold = 10
                    elif "lt" in filter_str and "20" in filter_str:
                        cloud_threshold = 20
                except:
                    pass
            
            if cloud_threshold:
                suggestions.append(f"**Relax cloud cover filter**: Currently requiring <{cloud_threshold}% clouds. Try allowing up to {cloud_threshold + 20}% for more options.")
        
        # Check collections
        if collections:
            collection_names = ", ".join(collections)
            suggestions.append(f"**Verify data availability**: Searched {collection_names} - confirm this data exists for your location and time period.")
        
        # Check location (if we can detect potential issues)
        query_lower = query.lower()
        if any(term in query_lower for term in ["ocean", "sea", "water", "pacific", "atlantic"]):
            suggestions.append("**Check location**: Some collections (like NAIP) only cover land areas, not oceans.")
        
        # Add suggestions
        if suggestions:
            response_parts.append("\n**Suggestions to find results:**")
            for suggestion in suggestions:
                response_parts.append(f"- {suggestion}")
        else:
            response_parts.append("\n**Try:** adjusting your search area, expanding the time range, or checking if the location name is spelled correctly.")
    
    # SCENARIO 2: STAC returned results, but spatial filter removed them
    elif raw_count > 0 and spatial_count == 0:
        response_parts.append(f"I found {raw_count} satellite images in the catalog, but none had sufficient coverage of your requested area.")
        response_parts.append("\n**This usually means:**")
        response_parts.append("- The imagery tiles only partially overlap your location (less than 10% coverage)")
        response_parts.append("- Your search area might be at the edge of the satellite's coverage zone")
        response_parts.append("\n**Try:** expanding your search area or choosing a nearby location with better coverage.")
    
    # SCENARIO 3: Spatial filter passed, but tile selection removed everything (unlikely)
    elif spatial_count > 0 and final_count == 0:
        response_parts.append(f"I found {spatial_count} satellite images covering your area, but they didn't meet quality thresholds.")
        response_parts.append("\n**Try:** relaxing quality filters or accepting imagery with higher cloud cover.")
    
    # SCENARIO 4: Unknown failure
    else:
        response_parts.append(f"I couldn't find satellite data matching your query for '{query}'.")
        response_parts.append("\n**Try:** adjusting your search parameters or rephrasing your query.")
    
    return " ".join(response_parts)


async def try_alternative_queries(
    original_query: str,
    original_stac_query: Dict[str, Any],
    original_stac_params: Dict[str, Any],
    translator: Any,
    stac_endpoint: str,
    requested_bbox: Optional[List[float]]
) -> Dict[str, Any]:
    """
    [NEW] Automatically try progressively relaxed queries to find available alternatives.
    
    Strategy:
    1. Keep location FIXED (highest priority)
    2. Try relaxing filters in order:
       - Cloud cover (10% -> 30% -> 50%)
       - Date range (expand backwards)
       - Collections (try related alternatives)
    
    Returns:
        {
            "success": bool,
            "features": List[Dict],
            "relaxation_applied": str,  # Description of what was changed
            "original_filters": dict,   # What was originally requested
            "alternative_filters": dict # What was actually used
        }
    """
    logger.info("[SYNC] Attempting to find alternative results with relaxed filters...")
    
    alternatives_tried = []
    original_filters = {
        "datetime": original_stac_query.get("datetime"),
        "cloud_cover": None,
        "collections": original_stac_query.get("collections", [])
    }
    
    # Extract original cloud cover threshold
    original_filter = original_stac_query.get("filter", {})
    if "eo:cloud_cover" in str(original_filter):
        filter_str = str(original_filter)
        if "10" in filter_str:
            original_filters["cloud_cover"] = 10
        elif "20" in filter_str:
            original_filters["cloud_cover"] = 20
    
    # RELAXATION 1: Try relaxing cloud cover
    if original_filters["cloud_cover"] and original_filters["cloud_cover"] < 50:
        for cloud_threshold in [30, 50]:
            if cloud_threshold <= original_filters["cloud_cover"]:
                continue
                
            logger.info(f"[WEATHER] Trying alternative with cloud cover <{cloud_threshold}%...")
            
            # Modify query
            alt_query = original_stac_query.copy()
            # Update cloud filter (simplified - adjust based on your filter structure)
            alt_query["filter"] = {"eo:cloud_cover": {"lt": cloud_threshold}}
            
            # Try search
            try:
                alt_response = await execute_direct_stac_search(alt_query, stac_endpoint)
                
                if alt_response.get("success"):
                    alt_features = alt_response.get("results", {}).get("features", [])
                    
                    if alt_features:
                        # Apply spatial filtering
                        if translator and requested_bbox:
                            filtered_results = translator._filter_stac_results_by_spatial_overlap(
                                {"features": alt_features}, requested_bbox, min_overlap=0.1
                            )
                            alt_features = filtered_results.get("features", [])
                        
                        # Apply cloud cover filtering (client-side safety net)
                        if translator and cloud_threshold:
                            # Get collection for property name lookup
                            collections = alt_query.get("collections", [])
                            primary_collection = collections[0] if collections else None
                            
                            cloud_filtered = translator._filter_stac_results_by_cloud_cover(
                                {"features": alt_features}, 
                                max_cloud_cover=cloud_threshold,
                                collection_id=primary_collection  # Pass collection for property lookup
                            )
                            alt_features = cloud_filtered.get("features", [])
                        
                        # Apply tile selection
                        if alt_features:
                            from tile_selector import TileSelector
                            # Use same dynamic tile limit as main query
                            fallback_max_tiles = 50  # Default for fallback queries
                            if requested_bbox and len(requested_bbox) == 4:
                                fb_area = (requested_bbox[2] - requested_bbox[0]) * (requested_bbox[3] - requested_bbox[1])
                                if fb_area > 25:
                                    fallback_max_tiles = 100
                                elif fb_area > 5:
                                    fallback_max_tiles = 60
                            selected_features = TileSelector.select_best_tiles(
                                features=alt_features,
                                query_bbox=requested_bbox,
                                collections=alt_query.get("collections"),
                                max_tiles=fallback_max_tiles,
                                query=original_query
                            )
                            
                            if selected_features:
                                logger.info(f"[OK] Found {len(selected_features)} results with cloud cover <{cloud_threshold}%")
                                return {
                                    "success": True,
                                    "features": selected_features,
                                    "relaxation_applied": f"cloud_cover_relaxed_to_{cloud_threshold}",
                                    "original_filters": original_filters,
                                    "alternative_filters": {
                                        **original_filters,
                                        "cloud_cover": cloud_threshold
                                    },
                                    "explanation": f"Relaxed cloud cover from <{original_filters['cloud_cover']}% to <{cloud_threshold}%"
                                }
            except Exception as e:
                logger.warning(f"[WARN] Alternative query failed: {e}")
                continue
    
    # RELAXATION 2: Try expanding date range
    datetime_str = original_stac_query.get("datetime", "")
    logger.info(f"[DATE] RELAXATION 2: Checking date range expansion for datetime='{datetime_str}'")
    if datetime_str and "/" in datetime_str:
        try:
            from datetime import datetime as dt, timedelta
            start, end = datetime_str.split("/")
            logger.info(f"[DATE] Parsed date range: start='{start}', end='{end}'")
            start_dt = dt.fromisoformat(start.replace("Z", ""))
            end_dt = dt.fromisoformat(end.replace("Z", ""))
            current_days = (end_dt - start_dt).days
            logger.info(f"[DATE] Current range is {current_days} days")
            
            # Try expanding backwards
            for expand_days in [30, 60, 90]:
                if current_days >= expand_days:
                    continue
                
                logger.info(f"[DATE] Trying alternative with {expand_days}-day date range...")
                
                new_start = end_dt - timedelta(days=expand_days)
                new_datetime = f"{new_start.isoformat()}Z/{end_dt.isoformat()}Z"
                logger.info(f"[DATE] Expanded datetime: {new_datetime}")
                
                alt_query = original_stac_query.copy()
                alt_query["datetime"] = new_datetime
                logger.info(f"[DATE] Alt query collections: {alt_query.get('collections')}, bbox: {alt_query.get('bbox')}")
                
                try:
                    alt_response = await execute_direct_stac_search(alt_query, stac_endpoint)
                    logger.info(f"[DATE] Alt response success: {alt_response.get('success')}, features: {len(alt_response.get('results', {}).get('features', []))}")
                    
                    if alt_response.get("success"):
                        alt_features = alt_response.get("results", {}).get("features", [])
                        
                        if alt_features:
                            # Apply filtering
                            if translator and requested_bbox:
                                filtered_results = translator._filter_stac_results_by_spatial_overlap(
                                    {"features": alt_features}, requested_bbox, min_overlap=0.1
                                )
                                alt_features = filtered_results.get("features", [])
                            
                            if alt_features:
                                from tile_selector import TileSelector
                                # Use same dynamic tile limit as main query
                                fallback_max_tiles = 50
                                if requested_bbox and len(requested_bbox) == 4:
                                    fb_area = (requested_bbox[2] - requested_bbox[0]) * (requested_bbox[3] - requested_bbox[1])
                                    if fb_area > 25:
                                        fallback_max_tiles = 100
                                    elif fb_area > 5:
                                        fallback_max_tiles = 60
                                selected_features = TileSelector.select_best_tiles(
                                    features=alt_features,
                                    query_bbox=requested_bbox,
                                    collections=alt_query.get("collections"),
                                    max_tiles=fallback_max_tiles,
                                    query=original_query
                                )
                                
                                if selected_features:
                                    logger.info(f"[OK] Found {len(selected_features)} results with {expand_days}-day range")
                                    return {
                                        "success": True,
                                        "features": selected_features,
                                        "relaxation_applied": f"date_range_expanded_to_{expand_days}_days",
                                        "original_filters": original_filters,
                                        "alternative_filters": {
                                            **original_filters,
                                            "datetime": new_datetime,
                                            "days_expanded": expand_days
                                        },
                                        "explanation": f"Expanded date range from {current_days} to {expand_days} days"
                                    }
                except Exception as e:
                    logger.warning(f"[WARN] Date expansion failed for {expand_days} days: {type(e).__name__}: {e}")
                    import traceback
                    logger.warning(f"[WARN] Traceback: {traceback.format_exc()}")
                    continue
        except Exception as e:
            logger.warning(f"[WARN] Date parsing failed: {type(e).__name__}: {e}")
            import traceback
            logger.warning(f"[WARN] Traceback: {traceback.format_exc()}")
    
    # RELAXATION 3: Try related collections (if applicable)
    # NOTE: Removed HLS -> Landsat fallback - when user explicitly requests HLS,
    # they should get HLS only, not mixed results with Landsat
    # The 500 errors on some HLS tiles are a Planetary Computer issue, not a collection issue
    original_collections = original_stac_query.get("collections", [])
    alternative_collection_sets = []
    
    # Only fall back for Sentinel -> Landsat (same optical imagery category)
    # Do NOT fall back for HLS - user explicitly requested harmonized data
    if any("sentinel" in c.lower() for c in original_collections) and not any("hls" in c.lower() for c in original_collections):
        alternative_collection_sets.append({
            "collections": ["landsat-c2-l2"],
            "name": "Landsat"
        })
    
    for alt_collections in alternative_collection_sets:
        logger.info(f"[SAT] Trying alternative collections: {alt_collections['name']}...")
        
        alt_query = original_stac_query.copy()
        alt_query["collections"] = alt_collections["collections"]
        
        try:
            alt_response = await execute_direct_stac_search(alt_query, stac_endpoint)
            
            if alt_response.get("success"):
                alt_features = alt_response.get("results", {}).get("features", [])
                
                if alt_features:
                    # Apply filtering
                    if translator and requested_bbox:
                        filtered_results = translator._filter_stac_results_by_spatial_overlap(
                            {"features": alt_features}, requested_bbox, min_overlap=0.1
                        )
                        alt_features = filtered_results.get("features", [])
                    
                    if alt_features:
                        from tile_selector import TileSelector
                        # Use same dynamic tile limit as main query
                        fallback_max_tiles = 50
                        if requested_bbox and len(requested_bbox) == 4:
                            fb_area = (requested_bbox[2] - requested_bbox[0]) * (requested_bbox[3] - requested_bbox[1])
                            if fb_area > 25:
                                fallback_max_tiles = 100
                            elif fb_area > 5:
                                fallback_max_tiles = 60
                        selected_features = TileSelector.select_best_tiles(
                            features=alt_features,
                            query_bbox=requested_bbox,
                            collections=alt_query.get("collections"),
                            max_tiles=fallback_max_tiles,
                            query=original_query
                        )
                        
                        if selected_features:
                            logger.info(f"[OK] Found {len(selected_features)} results with {alt_collections['name']}")
                            return {
                                "success": True,
                                "features": selected_features,
                                "relaxation_applied": f"collections_changed_to_{alt_collections['name'].lower()}",
                                "original_filters": original_filters,
                                "alternative_filters": {
                                    **original_filters,
                                    "collections": alt_collections["collections"]
                                },
                                "explanation": f"Used {alt_collections['name']} instead of {', '.join(original_collections)}"
                            }
        except Exception as e:
            logger.warning(f"[WARN] Alternative collection search failed: {e}")
            continue
    
    # No alternatives found
    logger.info("[FAIL] No alternatives found with relaxed filters")
    return {
        "success": False,
        "features": [],
        "relaxation_applied": "none",
        "original_filters": original_filters,
        "alternative_filters": original_filters,
        "explanation": "No alternatives found"
    }


def generate_fallback_response(query: str, features: List[Dict], collections: List[str]) -> str:
    """
    Enhanced fallback response generation from Router Function App
    """
    try:
        feature_count = len(features)
        
        # Build response components
        response_parts = []
        
        # Opening with feature count
        if feature_count == 0:
            response_parts.append(f"I searched for satellite data related to '{query}', but didn't find any available imagery for the specified area and time period.")
            response_parts.append("Try adjusting your search area or time range, or check if the location name is spelled correctly.")
        elif feature_count == 1:
            response_parts.append(f"Found 1 satellite image matching your query for '{query}'.")
        else:
            response_parts.append(f"Found {feature_count} satellite images matching your query for '{query}'.")
        
        # Add temporal context if we have features
        if feature_count > 0:
            try:
                dates = []
                for feature in features:
                    properties = feature.get('properties', {})
                    if 'datetime' in properties:
                        dates.append(properties['datetime'])
                    elif 'start_datetime' in properties:
                        dates.append(properties['start_datetime'])
                
                if dates:
                    dates.sort()
                    earliest = dates[0][:10] if dates else "unknown"
                    latest = dates[-1][:10] if len(dates) > 1 else earliest
                    
                    if earliest == latest:
                        response_parts.append(f"The imagery is from {earliest}.")
                    else:
                        response_parts.append(f"The imagery spans from {earliest} to {latest}.")
            except Exception as e:
                logger.warning(f"Could not extract temporal info: {e}")
        
        # Collection-specific insights
        if collections and feature_count > 0:
            # Map collections to friendly names (matching Router Function App)
            collection_descriptions = {
                'modis-14A1-061': 'MODIS fire detection (daily global coverage)',
                'modis-14A2-061': 'MODIS fire detection (8-day composite)',
                'modis-MCD64A1-061': 'MODIS burned area mapping',
                'cop-dem-glo-30': 'Copernicus 30m elevation data',
                'cop-dem-glo-90': 'Copernicus 90m elevation data',
                'sentinel-2-l2a': 'Sentinel-2 (high-resolution 10m optical)',
                'landsat-c2-l2': 'Landsat (30m optical with thermal)',
                'modis-09A1-061': 'MODIS (daily global coverage)',
                'sentinel-1-grd': 'Sentinel-1 SAR (radar, all-weather)'
            }
            described_collections = [collection_descriptions.get(c, c) for c in collections]
            
            if len(described_collections) == 1:
                response_parts.append(f"The data comes from {described_collections[0]} satellite.")
            else:
                response_parts.append(f"The data includes imagery from: {', '.join(described_collections)}.")
        
        # Query-specific context with more detail
        query_lower = query.lower()
        if any(term in query_lower for term in ['elevation', 'dem', 'topography', 'terrain']):
            response_parts.append("This elevation data can be used for terrain analysis, slope calculations, watershed mapping, and 3D visualization.")
        elif any(term in query_lower for term in ['optical', 'rgb', 'satellite', 'imagery', 'urban', 'city']):
            response_parts.append("This optical imagery is perfect for visual analysis, urban planning, change detection, and land cover mapping. You can see buildings, roads, vegetation, and water features clearly.")
        elif any(term in query_lower for term in ['radar', 'sar']):
            response_parts.append("This radar data can penetrate clouds and is excellent for all-weather monitoring, including surface changes and ground deformation.")
        elif any(term in query_lower for term in ['fire', 'wildfire', 'burn']):
            response_parts.append("This thermal and optical data is ideal for fire monitoring, burn area assessment, and recovery tracking.")
        else:
            response_parts.append("This satellite data provides comprehensive coverage suitable for environmental monitoring and analysis.")
        
        response_parts.append("All data is ready for analysis and has been loaded on the map for interactive exploration.")
        
        final_response = " ".join(response_parts)
        logger.info(f"Generated fallback response ({len(final_response)} chars): {final_response[:100]}...")
        
        return final_response
        
    except Exception as e:
        logger.error(f"Error in fallback response generation: {e}")
        return f"Found {len(features)} satellite images for '{query}'. The imagery shows excellent coverage of the requested area and is ready for analysis on the map."

def build_stac_query(stac_params: Dict[str, Any]) -> Dict[str, Any]:
    """
    Build STAC search query from semantic parameters (ported from Router Function App)
    
    NOTE: MODIS items use start_datetime/end_datetime instead of datetime,
    but the STAC API still correctly filters MODIS by datetime range.
    We DO apply datetime filter for MODIS collections.
    """
    query = {}
    
    # Add collections
    if stac_params.get('collections'):
        query['collections'] = stac_params['collections']
    
    # Add temporal filter for ALL collections (including MODIS)
    # MODIS items use start_datetime/end_datetime but STAC API filters correctly
    if stac_params.get('datetime'):
        query['datetime'] = stac_params['datetime']
        logger.info(f"[DATE] Adding datetime filter to STAC query: {stac_params['datetime']}")
    
    # Add spatial filter (bbox) - required for MODIS!
    if stac_params.get('bbox'):
        query['bbox'] = stac_params['bbox']
    
    # Add limit - uses dynamic value from semantic_translator (based on bbox size)
    # Default 50 is fallback, but semantic_translator calculates optimal limit from bbox area
    query['limit'] = stac_params.get('limit', 50)
    
    # Add sortby - CRITICAL for getting most recent imagery when no datetime filter
    # Without this, STAC API returns results in undefined order (often oldest first)
    if stac_params.get('sortby'):
        query['sortby'] = stac_params['sortby']
        logger.info(f"[CHART] Adding sortby to STAC query: {stac_params['sortby']}")
    else:
        # Default: sort by datetime descending to get most recent imagery first
        query['sortby'] = [{"field": "datetime", "direction": "desc"}]
        logger.info(f"[CHART] Adding default sortby (datetime desc) to get most recent imagery")
    
    # Add query parameters
    if stac_params.get('query'):
        query['query'] = stac_params['query']
    
    return query

def calculate_center_from_bbox(bbox: List[float]) -> List[float]:
    """
    Calculate center coordinates from bounding box [west, south, east, north]
    """
    if not bbox or len(bbox) != 4:
        return [0, 0]
    
    west, south, east, north = bbox
    center_lon = (west + east) / 2
    center_lat = (south + north) / 2
    
    return [center_lon, center_lat]

def calculate_zoom_level(bbox: List[float]) -> int:
    """
    Calculate appropriate zoom level based on bounding box size
    """
    if not bbox or len(bbox) != 4:
        return 10
    
    west, south, east, north = bbox
    lon_diff = abs(east - west)
    lat_diff = abs(north - south)
    
    # Use the larger dimension to determine zoom
    max_diff = max(lon_diff, lat_diff)
    
    if max_diff > 90:
        return 2
    elif max_diff > 45:
        return 3
    elif max_diff > 20:
        return 4
    elif max_diff > 10:
        return 5
    elif max_diff > 5:
        return 6
    elif max_diff > 2:
        return 7
    elif max_diff > 1:
        return 8
    elif max_diff > 0.5:
        return 9
    elif max_diff > 0.1:
        return 10
    else:
        return 12

def clean_tilejson_urls(stac_results: Dict[str, Any]) -> Dict[str, Any]:
    """
    Build TiTiler tilejson URLs for ALL collections using PC rendering configs.
    
    ALL collections go through TiTiler API with correct render parameters from
    planetary-computer-tasks repository configs. This includes:
    - Optical imagery (RGB): TiTiler with assets + color_formula from PC configs
    - Colormap data (SAR, DEM, MODIS): TiTiler with colormap_name + rescale from PC configs
    - Single-band data: TiTiler with appropriate single-band params from PC configs
    
    We ALWAYS build TiTiler URLs from scratch using the official PC configs,
    never relying on STAC API's default tilejson URLs.
    """
    logger.info(f"[CLEAN] clean_tilejson_urls() called with stac_results type: {type(stac_results)}")
    logger.info(f"[CLEAN] stac_results keys: {list(stac_results.keys()) if isinstance(stac_results, dict) else 'Not a dict'}")
    
    try:
        features = stac_results.get("features", [])
        if not features:
            return stac_results
        
        cleaned_features = []
        for i, feature in enumerate(features):
            collection_id = feature.get("collection", "unknown")
            item_id = feature.get("id", "unknown")
            
            cleaned_feature = feature.copy()
            config = HybridRenderingSystem.get_render_config(collection_id)
            
            if "assets" in cleaned_feature and cleaned_feature["assets"]:
                cleaned_assets = {}
                has_tilejson = False
                
                for asset_name, asset_data in cleaned_feature["assets"].items():
                    cleaned_asset = asset_data.copy()
                    
                    if asset_name == "tilejson" and "href" in cleaned_asset:
                        has_tilejson = True
                        original_url = cleaned_asset["href"]
                        
                        # Expression-based collections: keep original STAC tilejson URL
                        expression_collections = ["alos-palsar-mosaic", "sentinel-1-grd", "sentinel-1-rtc"]
                        if collection_id in expression_collections and "expression=" in original_url:
                            pass  # Keep original URL
                        elif config:
                            titiler_url = HybridRenderingSystem.build_titiler_tilejson_url(item_id, collection_id)
                            cleaned_asset["href"] = titiler_url
                    
                    cleaned_assets[asset_name] = cleaned_asset
                
                # Generate tilejson URL for collections that don't have it in STAC response
                if not has_tilejson and config:
                    titiler_url = HybridRenderingSystem.build_titiler_tilejson_url(item_id, collection_id)
                    cleaned_assets["tilejson"] = {
                        "href": titiler_url,
                        "type": "application/json",
                        "roles": ["tiles"],
                        "title": "TileJSON for visualization (auto-generated)"
                    }
                elif not has_tilejson:
                    logger.warning(f"[CLEAN] No tilejson and no PC config for {collection_id}/{item_id}")
                
                cleaned_feature["assets"] = cleaned_assets
            
            cleaned_features.append(cleaned_feature)
        
        # Return cleaned results
        cleaned_results = stac_results.copy()
        cleaned_results["features"] = cleaned_features
        
        collection_name = cleaned_features[0].get('collection') if cleaned_features else 'N/A'
        logger.info(f"[CLEAN] URL cleaning done — {len(cleaned_features)} features, collection={collection_name}")
        return cleaned_results
        
    except Exception as e:
        logger.error(f"[CLEAN] [FAIL] Error cleaning tilejson URLs: {e}")
        # Return original results if cleaning fails
        return stac_results


def _enhance_tilejson_url(url: str, collection_id: str) -> str:
    """
    Enhance a tilejson URL with correct rendering parameters from HybridRenderingSystem.
    
    This function ensures that SAR, MODIS, and other non-optical collections get the
    correct assets, rescale, colormap, and other parameters they need to render properly.
    
    Args:
        url: Cleaned tilejson URL
        collection_id: STAC collection ID
        
    Returns:
        Enhanced URL with optimal rendering parameters
    """
    try:
        from urllib.parse import urlparse, parse_qs, urlencode, urlunparse
        
        # Get optimal rendering configuration from HybridRenderingSystem
        render_config = HybridRenderingSystem.get_render_config(collection_id)
        
        # Parse the URL
        parsed = urlparse(url)
        params = parse_qs(parsed.query, keep_blank_values=True)
        
        # Convert multi-value params to single values (parse_qs returns lists)
        params = {k: v[0] if isinstance(v, list) and len(v) == 1 else v for k, v in params.items()}
        
        # Inject optimal rendering parameters based on config
        config_dict = render_config.to_dict()
        
        # Add assets if specified (critical for SAR, MODIS)
        if config_dict.get("assets"):
            assets = config_dict["assets"]
            if isinstance(assets, list):
                # For multi-asset (RGB), set assets parameter
                params["assets"] = ",".join(assets)
                logger.info(f"[ART] Injecting assets: {params['assets']}")
            else:
                # For single asset, set assets parameter
                params["assets"] = assets
                logger.info(f"[ART] Injecting asset: {assets}")
        
        # Add rescale if specified (critical for SAR and MODIS)
        if config_dict.get("rescale") is not None:
            min_val, max_val = config_dict["rescale"]
            params["rescale"] = f"{min_val},{max_val}"
            logger.info(f"[ART] Injecting rescale: {params['rescale']}")
        
        # Add colormap for single-band data (SAR, MODIS vegetation, elevation)
        if config_dict.get("colormap_name"):
            params["colormap_name"] = config_dict["colormap_name"]
            logger.info(f"[ART] Injecting colormap: {params['colormap_name']}")
        
        # Add bidx if specified
        if config_dict.get("bidx"):
            params["bidx"] = str(config_dict["bidx"])
            logger.info(f"[ART] Injecting bidx: {params['bidx']}")
        
        # Add resampling method
        if config_dict.get("resampling"):
            params["resampling"] = config_dict["resampling"]
            logger.info(f"[ART] Injecting resampling: {params['resampling']}")
        
        # Add color formula if specified (for Landsat adjustments)
        if config_dict.get("color_formula"):
            # URL encode the formula
            formula = config_dict["color_formula"].replace(" ", "+").replace(",", "%2C")
            params["color_formula"] = formula
            logger.info(f"[ART] Injecting color_formula: {config_dict['color_formula']}")
        
        # Rebuild the URL with enhanced parameters
        # Convert params back to list format for urlencode
        encoded_params = []
        for key, value in params.items():
            if isinstance(value, list):
                for v in value:
                    encoded_params.append((key, v))
            else:
                encoded_params.append((key, value))
        
        new_query = urlencode(encoded_params)
        enhanced_url = urlunparse((
            parsed.scheme,
            parsed.netloc,
            parsed.path,
            parsed.params,
            new_query,
            parsed.fragment
        ))
        
        return enhanced_url
        
    except Exception as e:
        logger.error(f"[FAIL] Error enhancing tilejson URL for {collection_id}: {e}")
        logger.exception("Full exception details:")
        return url  # Return original URL if enhancement fails

# ============================================================================
# [BOT] TEAMS BOT ENDPOINT — Receives activities from Bot Framework Connector
# ============================================================================
@app.post("/api/messages")
async def teams_bot_messages(request: Request):
    """Bot Framework messaging endpoint for Microsoft Teams integration."""
    if not TEAMS_BOT_AVAILABLE or not teams_bot or not teams_bot_adapter:
        raise HTTPException(
            status_code=503,
            detail="Teams bot is not configured. Set MICROSOFT_APP_ID and install botbuilder-core.",
        )
    try:
        body = await request.json()
        activity = Activity().deserialize(body)
        auth_header = request.headers.get("Authorization", "")

        invoke_response = await teams_bot_adapter.process_activity(
            activity, auth_header, teams_bot.on_turn
        )

        if invoke_response:
            return JSONResponse(
                content=invoke_response.body,
                status_code=invoke_response.status,
            )
        return JSONResponse(content={}, status_code=201)

    except Exception as e:
        logger.error(f"Teams bot /api/messages error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/health")
async def health_check():
    """Lightweight health check — no GPT calls, no verbose logging."""
    try:
        checks = {}
        all_healthy = True

        # 1. Azure OpenAI — config check only (no billable test call)
        endpoint = os.getenv("AZURE_OPENAI_ENDPOINT")
        has_auth = bool(os.getenv("AZURE_OPENAI_API_KEY")) or os.getenv("USE_MANAGED_IDENTITY", "").lower() == "true"
        if endpoint and has_auth:
            checks["azure_openai"] = {"status": "configured", "endpoint": endpoint}
        else:
            checks["azure_openai"] = {"status": "misconfigured"}
            all_healthy = False

        # 2. STAC API — quick GET, no search
        try:
            async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=5)) as session:
                async with session.get(cloud_cfg.stac_catalog_url + "/") as resp:
                    checks["stac_api"] = {"status": "connected" if resp.status == 200 else "degraded"}
        except Exception:
            checks["stac_api"] = {"status": "degraded"}

        # 3. Azure Maps — config check only
        maps_key = os.getenv("AZURE_MAPS_SUBSCRIPTION_KEY") or os.getenv("AZURE_MAPS_KEY")
        maps_mi = os.getenv("AZURE_MAPS_USE_MANAGED_IDENTITY", "").lower() == "true"
        if maps_key or maps_mi:
            checks["azure_maps"] = {"status": "configured"}
        else:
            checks["azure_maps"] = {"status": "misconfigured"}
            all_healthy = False

        overall = "healthy" if all_healthy else "degraded"
        logger.info(f"[BLDG] Health: {overall} | openai={checks['azure_openai']['status']} stac={checks['stac_api']['status']} maps={checks['azure_maps']['status']}")

        return JSONResponse(
            content={
                "status": overall,
                "timestamp": datetime.now().strftime("%Y-%m-%dT%H:%M:%SZ"),
                "checks": checks,
            },
            status_code=200 if all_healthy else 503,
        )
    except Exception as e:
        logger.error(f"[FAIL] Health check error: {e}")
        return JSONResponse(content={"status": "unhealthy", "error": str(e)}, status_code=500)

@app.get("/api/config")
async def get_config():
    """Configuration endpoint for frontend - provides Azure Maps key and other settings"""
    return {
        "azureMaps": {
            "subscriptionKey": os.environ.get('AZURE_MAPS_SUBSCRIPTION_KEY', os.environ.get('AZURE_MAPS_KEY', '')),
            "clientId": os.environ.get('AZURE_MAPS_CLIENT_ID', '')
        },
        "api": {
            "baseUrl": "/api"
        }
    }

@app.post("/api/sign-mosaic-url")
async def sign_mosaic_url(request: Request):
    """Sign a Planetary Computer mosaic URL with authentication token"""
    try:
        body = await request.json()
        mosaic_url = body.get('url')
        
        if not mosaic_url:
            raise HTTPException(status_code=400, detail="Missing 'url' parameter")
        
        if not PLANETARY_COMPUTER_AVAILABLE:
            logger.warning("[LOCK] [SIGN-MOSAIC-URL] PC auth unavailable — returning unsigned URL")
            return {"signed_url": mosaic_url, "authenticated": False}
        
        try:
            signed_url = planetary_computer.sign(mosaic_url)
        except Exception as sign_error:
            logger.error(f"[LOCK] [SIGN-MOSAIC-URL] sign() failed: {sign_error}")
            signed_url = mosaic_url
        
        is_titiler = 'planetarycomputer.microsoft.com/api/data/v1' in signed_url
        has_sas = 'se=' in signed_url or 'sig=' in signed_url
        logger.info(f"[LOCK] [SIGN-MOSAIC-URL] [OK] type={'titiler' if is_titiler else 'blob'} sas={has_sas} len={len(signed_url)}")
        
        return {"signed_url": signed_url, "authenticated": True}
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"[LOCK] [SIGN-MOSAIC-URL] [FAIL] {type(e).__name__}: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to sign URL: {str(e)}")

# ============================================================================
# COLORMAP ENDPOINTS REMOVED
# ============================================================================
# The colormap service has been removed as it's redundant.
# Colormap information comes directly from PC tasks rendering config.
# Legend display uses hardcoded colormap gradients in the frontend.
# ============================================================================

@app.post("/api/proxy-tilejson")
async def proxy_tilejson(request: Request):
    """Proxy TileJSON requests through the backend to avoid browser CORS/network issues"""
    import httpx
    try:
        body = await request.json()
        tilejson_url = body.get('url')
        
        if not tilejson_url:
            raise HTTPException(status_code=400, detail="Missing 'url' parameter")
        
        # Only allow proxying to Planetary Computer URLs
        from urllib.parse import urlparse
        parsed = urlparse(tilejson_url)
        if parsed.hostname not in ('planetarycomputer.microsoft.com',):
            raise HTTPException(status_code=400, detail="Only Planetary Computer URLs are supported")
        
        # Sign the URL if possible
        if PLANETARY_COMPUTER_AVAILABLE:
            try:
                tilejson_url = planetary_computer.sign(tilejson_url)
            except Exception as sign_err:
                logger.warning(f"[PROXY-TILEJSON] sign() failed: {sign_err}")
        
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.get(tilejson_url)
            resp.raise_for_status()
            data = resp.json()
        
        logger.info(f"[PROXY-TILEJSON] [OK] tiles={len(data.get('tiles', []))} minzoom={data.get('minzoom')} maxzoom={data.get('maxzoom')}")
        return data
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"[PROXY-TILEJSON] [FAIL] {type(e).__name__}: {e}")
        raise HTTPException(status_code=502, detail=f"Failed to fetch TileJSON: {str(e)}")

@app.post("/api/query")
async def unified_query_processor(request: Request):
    """
    Unified query processor that combines Router Function logic with direct STAC search
    This implements the complete Earth Copilot query processing pipeline
    """
    try:
        # Parse request with robust handling
        try:
            req_body = await request.json()
            if not req_body:
                raise ValueError("Request body is empty")
            
        except Exception as json_error:
            logger.error(f"JSON parsing error: {json_error}")
            raise HTTPException(
                status_code=400,
                detail=f"Invalid JSON data: {str(json_error)}"
            )
        
        # Support both 'query' and 'user_query' keys (frontend uses 'user_query')
        natural_query = req_body.get('query') or req_body.get('user_query') or 'No query provided'
        session_id = req_body.get('session_id') or req_body.get('conversation_id')
        pin = req_body.get('pin')  # Optional pin parameter {lat, lng}
        selected_model = req_body.get('model', 'gpt-5')  # Model selection from frontend, default to gpt-5
        
        logger.info(f"[BOT] Selected Model: {selected_model}")
        
        # Set the active model on the semantic translator before processing
        if semantic_translator:
            semantic_translator.set_model(selected_model)
        else:
            logger.warning("[WARN] semantic_translator is None - AI functionality disabled")
        
        # [MICRO] Generate unique pipeline session ID for tracing
        import uuid
        pipeline_session_id = str(uuid.uuid4())[:8]
        
        # [MICRO] Clear any stale trace and start fresh
        clear_pipeline_trace(pipeline_session_id)
        
        # [MICRO] TRACE: Initial query received
        log_pipeline_step(pipeline_session_id, "QUERY_RECEIVED", "INPUT", {
            "query": natural_query,
            "session_id": session_id,
            "has_pin": bool(pin),
            "pin_coords": f"({pin.get('lat'):.4f}, {pin.get('lng'):.4f})" if pin else None
        })
        
        pin_str = f"({pin.get('lat'):.4f},{pin.get('lng'):.4f})" if pin else "none"
        logger.info(f"[TEXT] Query='{natural_query}' session={session_id} pin={pin_str}")
        
        # Normal STAC search routing (vision handled by /api/geoint/vision)
        
        # Check for pin parameter
        if pin:
            pin_lat = pin.get('lat')
            pin_lng = pin.get('lng')
            logger.info(f"[PIN] Pin detected: ({pin_lat:.4f}, {pin_lng:.4f})")
        
        has_satellite_data = req_body.get("has_satellite_data", False)
        query_lower = natural_query.lower().strip()
        
        # ================================================================
        # [FAST] QUICKSTART FAST PATH: Skip ALL GPT calls for demo queries
        # ================================================================
        # For the pre-defined quick start queries, we have pre-computed
        # collections, bbox, datetime, and classification. This bypasses:
        #   1. RouterAgent GPT call (~2-4s saved)
        #   2. translate_query with 3 GPT agent calls (~3-6s saved)
        #   3. generate_contextual_earth_science_response GPT call (~2-4s saved)
        # Total savings: ~7-14 seconds per demo query
        # ================================================================
        if is_quickstart_query(natural_query):
            import time as _time
            _qs_start = _time.perf_counter()
            
            qs_location = get_quickstart_location(natural_query)
            logger.info(f"[FAST] QUICKSTART FAST PATH: '{natural_query}' -> {qs_location['collections']} @ {qs_location['location']}")
            
            # Build STAC params from pre-computed data
            temporal = qs_location.get('temporal')
            datetime_range = None
            if temporal:
                if len(temporal) == 4:  # Year: "2017"
                    datetime_range = f"{temporal}-01-01/{temporal}-12-31"
                elif len(temporal) == 7:  # Month: "2025-06"
                    import calendar as _cal
                    _y, _m = int(temporal[:4]), int(temporal[5:7])
                    _last = _cal.monthrange(_y, _m)[1]
                    datetime_range = f"{temporal}-01/{temporal}-{_last:02d}"
                else:
                    datetime_range = temporal
            
            qs_stac_params = {
                'collections': qs_location['collections'],
                'bbox': qs_location['bbox'],
                'datetime': datetime_range,
                'location_name': qs_location['location'],
                'is_quickstart': True
            }
            qs_stac_query = build_stac_query(qs_stac_params)
            
            # Execute STAC search (the only step that MUST hit the network)
            qs_stac_endpoint = "planetary_computer"
            qs_stac_response = await execute_direct_stac_search(qs_stac_query, qs_stac_endpoint, original_query=natural_query)
            
            qs_features = []
            if qs_stac_response.get("success"):
                qs_features = qs_stac_response.get("results", {}).get("features", [])
                logger.info(f"[FAST] STAC returned {len(qs_features)} features")
            
            # Generate template response (no GPT call needed)
            qs_dataset = qs_location.get('dataset', qs_location['collections'][0])
            qs_desc = qs_location.get('description', '')
            if qs_features:
                qs_first = qs_features[0]
                qs_props = qs_first.get('properties', {})
                qs_date = qs_props.get('datetime') or qs_props.get('start_datetime') or qs_props.get('end_datetime') or ''
                if qs_date and len(qs_date) >= 10:
                    qs_date = qs_date[:10]
                if qs_date:
                    qs_response_msg = (
                        f"Loaded {len(qs_features)} {qs_dataset} tiles for {qs_location['location']}. "
                        f"{qs_desc}. Most recent tile: {qs_date}."
                    )
                else:
                    qs_response_msg = (
                        f"Loaded {len(qs_features)} {qs_dataset} tiles for {qs_location['location']}. "
                        f"{qs_desc}."
                    )
            else:
                qs_response_msg = (
                    f"Searched {qs_dataset} for {qs_location['location']} but no tiles were found "
                    f"matching the current filters. Try adjusting the time range."
                )
            
            # Build tile URLs (same logic as main path but inlined for speed)
            qs_tile_urls = []
            qs_bboxes = []
            qs_collection_id = qs_location['collections'][0] if qs_location['collections'] else ""
            
            for feat in qs_features[:20]:
                tj_asset = feat.get("assets", {}).get("tilejson", {})
                if tj_asset and "href" in tj_asset:
                    feat_bbox = feat.get("bbox")
                    if not feat_bbox or len(feat_bbox) != 4:
                        continue
                    if any(v is None or not isinstance(v, (int, float)) for v in feat_bbox):
                        continue
                    
                    original_url = tj_asset["href"]
                    quality_params = build_tile_url_params(qs_collection_id, natural_query)
                    if quality_params and "?" in original_url:
                        base_url, existing_params = original_url.split("?", 1)
                        param_list = [p for p in existing_params.split("&")
                                     if not any(p.startswith(k) for k in [
                                         "assets=", "asset_bidx=", "colormap_name=", "rescale=",
                                         "resampling=", "bidx=", "format=", "nodata=",
                                         "color_formula=", "expression=", "asset_as_band="])]
                        optimized_url = f"{base_url}?{'&'.join(param_list)}&{quality_params}" if param_list else f"{base_url}?{quality_params}"
                    elif quality_params:
                        optimized_url = f"{original_url}?{quality_params}"
                    else:
                        optimized_url = original_url
                    
                    qs_tile_urls.append({
                        "item_id": feat.get("id"),
                        "bbox": feat_bbox,
                        "tilejson_url": optimized_url
                    })
                    qs_bboxes.append(feat_bbox)
            
            # Calculate union bbox
            qs_union_bbox = None
            if qs_bboxes:
                qs_union_bbox = [
                    min(b[0] for b in qs_bboxes),
                    min(b[1] for b in qs_bboxes),
                    max(b[2] for b in qs_bboxes),
                    max(b[3] for b in qs_bboxes)
                ]
            
            # Mosaic for optical collections
            qs_mosaic = None
            optical_qs = ["sentinel-2-l2a", "landsat-c2-l2", "landsat-8-c2-l2", "landsat-9-c2-l2", "hls", "hls2-l30", "hls2-s30"]
            if any(qs_collection_id.startswith(oc) or qs_collection_id == oc for oc in optical_qs):
                try:
                    from hybrid_rendering_system import get_mosaic_tilejson_url
                    qs_mosaic = await get_mosaic_tilejson_url(
                        collections=[qs_collection_id],
                        bbox=qs_location['bbox'],
                        datetime_range=datetime_range,
                        query_filters=None
                    )
                except Exception:
                    pass
            
            # Update session context
            if router_agent and session_id and (qs_tile_urls or qs_features):
                stac_items_for_session = []
                for f in qs_features[:10]:
                    stac_items_for_session.append({
                        "id": f.get("id"),
                        "collection": f.get("collection"),
                        "bbox": f.get("bbox"),
                        "properties": {
                            "datetime": f.get("properties", {}).get("datetime"),
                            "eo:cloud_cover": f.get("properties", {}).get("eo:cloud_cover"),
                        },
                        "assets": {k: {"href": v.get("href"), "type": v.get("type")} for k, v in (f.get("assets") or {}).items()}
                    })
                router_agent.update_session_context(session_id, {
                    "has_rendered_map": True,
                    "last_bbox": qs_location['bbox'],
                    "last_location": qs_location['location'],
                    "last_collections": qs_location['collections'],
                    "last_stac_items": stac_items_for_session,
                    "query_count": router_agent.tools.session_contexts.get(session_id, {}).get("query_count", 0) + 1
                })
            
            _qs_elapsed = (_time.perf_counter() - _qs_start) * 1000
            logger.info(f"[FAST] QUICKSTART FAST PATH completed in {_qs_elapsed:.0f}ms (skipped RouterAgent + translate_query + response GPT)")
            
            cleaned_qs_results = clean_tilejson_urls(qs_stac_response.get("results", {}))
            
            return {
                "success": True,
                "response": qs_response_msg,
                "data": {
                    "stac_results": cleaned_qs_results,
                    "search_metadata": {
                        "total_items": len(qs_features),
                        "collections_searched": qs_location['collections'],
                        "spatial_extent": qs_location['bbox'],
                        "temporal_range": datetime_range,
                        "search_timestamp": datetime.utcnow().isoformat()
                    },
                    "query_classification": {
                        "intent_type": "stac",
                        "needs_satellite_data": True,
                        "needs_contextual_info": False,
                        "confidence": 1.0
                    }
                },
                "translation_metadata": {
                    "original_query": natural_query,
                    "translated_params": qs_stac_params,
                    "stac_query": qs_stac_query,
                    "translation_timestamp": datetime.utcnow().isoformat(),
                    "all_tile_urls": qs_tile_urls if qs_tile_urls else None,
                    "mosaic_tilejson": qs_mosaic
                },
                "debug": {
                    "semantic_translator": {
                        "available": True,
                        "selected_collections": qs_location['collections'],
                        "location_info": {
                            "bbox": qs_location['bbox'],
                            "location_name": qs_location['location']
                        }
                    },
                    "fast_path": True,
                    "fast_path_elapsed_ms": round(_qs_elapsed, 1)
                }
            }
        
        # ================================================================
        # [PIN] EARLY SESSION BBOX OVERRIDE: Fix stale frontend coordinates
        # ================================================================
        # After navigate_to, the frontend's map bounds may still be stale
        # (the useEffect doesn't always re-fire immediately). We override
        # map_bounds with the session bbox here so that ALL downstream
        # handlers (vision, contextual, STAC) get the correct coordinates.
        # ================================================================
        frontend_map_bounds = req_body.get('map_bounds')
        if router_agent and session_id:
            session_ctx = router_agent.tools.session_contexts.get(session_id, {})
            session_bbox_early = session_ctx.get('last_bbox')
            recently_navigated_early = session_bbox_early and not session_ctx.get('has_rendered_map', True)
            
            if session_bbox_early and (not frontend_map_bounds or recently_navigated_early):
                override_reason_early = "no frontend bounds" if not frontend_map_bounds else "post-navigate_to (frontend bounds stale)"
                corrected_bounds = {
                    'west': session_bbox_early[0], 'south': session_bbox_early[1],
                    'east': session_bbox_early[2], 'north': session_bbox_early[3],
                    'center_lat': (session_bbox_early[1] + session_bbox_early[3]) / 2,
                    'center_lng': (session_bbox_early[0] + session_bbox_early[2]) / 2
                }
                req_body['map_bounds'] = corrected_bounds
                logger.info(f"[PIN] EARLY BBOX OVERRIDE ({override_reason_early}): Using session bbox for {session_ctx.get('last_location')}: center=({corrected_bounds['center_lat']:.4f}, {corrected_bounds['center_lng']:.4f})")
        
        # Continue with regular STAC search flow
        router_action = None
        
        # ========================================================================
        # [ROUTE] ROUTER AGENT: Intelligent Query Classification and Routing
        # ========================================================================
        # RouterAgent classifies queries and routes them to the appropriate handler.
        #
        # Action Types:
        # - navigate_to: Pan map to location (no STAC search, immediate response)
        # - stac_search: Load satellite imagery (continues to existing STAC flow)
        #
        # NOTE: Vision analysis is now handled by explicit Vision GEOINT module,
        # not by the RouterAgent. Users activate Vision mode, then all queries
        # route directly to the Vision Agent.
        # ========================================================================
        
        if router_action is None and router_agent and session_id:
            try:
                # Update session context for the router
                if global_translator:
                    context = global_translator.get_conversation_context(session_id)
                    context["has_screenshot"] = bool(req_body.get("imagery_base64"))
                    # ================================================================
                    # CRITICAL FIX: Preserve has_rendered_map from router's existing context
                    # The router agent may have set has_rendered_map=True from a previous
                    # STAC render, and we don't want to overwrite it with the translator's
                    # context (which may not have been updated). This ensures follow-up
                    # questions like "what is on the map" route to vision correctly.
                    # ================================================================
                    existing_router_context = router_agent.tools.session_contexts.get(session_id, {})
                    
                    # Preserve has_rendered_map if already True in router context
                    if existing_router_context.get("has_rendered_map"):
                        context["has_rendered_map"] = True
                    # Also set from frontend's has_satellite_data flag (new request indicator)
                    elif req_body.get("has_satellite_data"):
                        context["has_rendered_map"] = True
                    
                    # Preserve last_bbox and last_location from router context if not in translator context
                    if not context.get("last_bbox") and existing_router_context.get("last_bbox"):
                        context["last_bbox"] = existing_router_context.get("last_bbox")
                    if not context.get("last_location") and existing_router_context.get("last_location"):
                        context["last_location"] = existing_router_context.get("last_location")
                    if not context.get("last_collections") and existing_router_context.get("last_collections"):
                        context["last_collections"] = existing_router_context.get("last_collections")
                        
                    router_agent.update_session_context(session_id, context)
                
                # Vision mode already checked above - just invoke RouterAgent
                logger.info("[ROUTE] Invoking RouterAgent for query classification...")
                router_action = await router_agent.route_query(
                    query=natural_query,
                    session_id=session_id,
                    has_screenshot=bool(req_body.get("imagery_base64"))
                )
                
                logger.info(f"[ROUTE] RouterAgent decision: {router_action.get('action_type', 'unknown')}")
                log_pipeline_step(pipeline_session_id, "ROUTER_AGENT", "OUTPUT", {
                    "action_type": router_action.get("action_type"),
                    "needs_stac": router_action.get("needs_stac_search", False),
                    "needs_vision": router_action.get("needs_vision_analysis", False)
                })
                
                # ================================================================
                # HANDLE NAVIGATE_TO ACTION: Map-only navigation (no STAC search)
                # ================================================================
                if router_action.get("action_type") == "navigate_to":
                    # Get location from router action, or fall back to original query for bare locations
                    location = router_action.get("location") or router_action.get("original_query", "")
                    zoom_level = router_action.get("zoom_level", 12)
                    
                    # Capitalize location name properly (e.g., "albania" -> "Albania")
                    location_display = location.title() if location else location
                    
                    logger.info(f"[MAP] NAVIGATE_TO ACTION: Navigating to '{location_display}' at zoom {zoom_level}")
                    
                    # Resolve location to coordinates using location_resolver
                    from location_resolver import EnhancedLocationResolver
                    resolver = EnhancedLocationResolver()
                    
                    try:
                        bbox = await resolver.resolve_location_to_bbox(location)
                        if bbox and len(bbox) == 4:
                            # Calculate center from bbox [west, south, east, north]
                            center_lng = (bbox[0] + bbox[2]) / 2
                            center_lat = (bbox[1] + bbox[3]) / 2
                            
                            logger.info(f"[OK] Location resolved: {location_display} -> ({center_lat:.4f}, {center_lng:.4f})")
                            
                            # ============================================================
                            # [PIN] UPDATE SESSION CONTEXT: Store bbox for follow-up queries
                            # ============================================================
                            # When user navigates to a location, we store the bbox so that
                            # follow-up queries like "show me Sentinel tiles" will use this location
                            # ============================================================
                            if router_agent and session_id:
                                navigate_context = {
                                    "last_bbox": bbox,
                                    "last_location": location_display,
                                    "has_rendered_map": False,  # No imagery yet, just navigation
                                    "query_count": router_agent.tools.session_contexts.get(session_id, {}).get("query_count", 0) + 1
                                }
                                router_agent.update_session_context(session_id, navigate_context)
                                logger.info(f"[PIN] Updated session context with navigate_to location: {location_display}, bbox: {bbox}")
                            
                            return {
                                "success": True,
                                "action": "navigate_to",
                                "response": f"Navigating to {location_display}.",
                                "user_response": f"Navigating to {location_display}.",
                                "navigate_to": {
                                    "latitude": center_lat,
                                    "longitude": center_lng,
                                    "zoom": zoom_level,
                                    "bbox": bbox,
                                    "location_name": location_display
                                },
                                "processing_type": "map_navigation",
                                "timestamp": datetime.utcnow().isoformat()
                            }
                        else:
                            logger.warning(f"[WARN] Could not resolve location '{location}' via stored locations")
                            # Try Azure Maps as a last resort before giving up
                            try:
                                maps_bbox = await resolver._strategy_azure_maps(location)
                                if maps_bbox and len(maps_bbox) == 4:
                                    center_lng = (maps_bbox[0] + maps_bbox[2]) / 2
                                    center_lat = (maps_bbox[1] + maps_bbox[3]) / 2
                                    logger.info(f"[OK] Azure Maps fallback resolved: {location_display} -> ({center_lat:.4f}, {center_lng:.4f})")
                                    
                                    if router_agent and session_id:
                                        navigate_context = {
                                            "last_bbox": maps_bbox,
                                            "last_location": location_display,
                                            "has_rendered_map": False,
                                            "query_count": router_agent.tools.session_contexts.get(session_id, {}).get("query_count", 0) + 1
                                        }
                                        router_agent.update_session_context(session_id, navigate_context)
                                    
                                    return {
                                        "success": True,
                                        "action": "navigate_to",
                                        "response": f"Navigating to {location_display}.",
                                        "user_response": f"Navigating to {location_display}.",
                                        "navigate_to": {
                                            "latitude": center_lat,
                                            "longitude": center_lng,
                                            "zoom": zoom_level,
                                            "bbox": maps_bbox,
                                            "location_name": location_display
                                        },
                                        "processing_type": "map_navigation",
                                        "timestamp": datetime.utcnow().isoformat()
                                    }
                            except Exception as maps_err:
                                logger.warning(f"[WARN] Azure Maps fallback also failed: {maps_err}")
                            
                            # All resolution failed — return contextual response, NOT STAC
                            logger.info(f"[MAP] All geocoding failed for '{location}', returning contextual response instead of falling through to STAC")
                            return {
                                "success": True,
                                "action": "contextual",
                                "response": f"I couldn't pinpoint the exact location for '{location_display}'. Could you try a more specific place name or add the country?",
                                "user_response": f"I couldn't pinpoint the exact location for '{location_display}'. Could you try a more specific place name or add the country?",
                                "processing_type": "contextual",
                                "timestamp": datetime.utcnow().isoformat()
                            }
                    except Exception as loc_error:
                        logger.error(f"[FAIL] Location resolution failed: {loc_error}")
                        # Return contextual response instead of falling through to STAC
                        return {
                            "success": True,
                            "action": "contextual",
                            "response": f"I had trouble resolving the location '{location_display}'. Please try again or use a different place name.",
                            "user_response": f"I had trouble resolving the location '{location_display}'. Please try again or use a different place name.",
                            "processing_type": "contextual",
                            "timestamp": datetime.utcnow().isoformat()
                        }
                
                # ================================================================
                # [STORM] HANDLE EXTREME_WEATHER ACTION: Climate projection via CMIP6
                # ================================================================
                # Route climate projection queries to ExtremeWeatherAgent inline,
                # so users can ask climate questions from the normal chat without
                # needing to manually select the extreme weather module + drop a pin.
                # ================================================================
                if router_action.get("action_type") == "extreme_weather":
                    location = router_action.get("location") or router_action.get("original_query", "")
                    logger.info(f"[STORM] EXTREME_WEATHER ACTION: Climate query for '{location}'")
                    
                    try:
                        # Resolve location to coordinates
                        from location_resolver import EnhancedLocationResolver
                        resolver = EnhancedLocationResolver()
                        
                        bbox = await resolver.resolve_location_to_bbox(location) if location else None
                        
                        # Use session context bbox as fallback
                        if not bbox and router_agent and session_id:
                            ctx = router_agent.tools.session_contexts.get(session_id, {})
                            bbox = ctx.get("last_bbox")
                            location = location or ctx.get("last_location", "this location")
                        
                        if bbox and len(bbox) == 4:
                            center_lng = (bbox[0] + bbox[2]) / 2
                            center_lat = (bbox[1] + bbox[3]) / 2
                        else:
                            # Cannot determine coordinates — fall through to STAC
                            logger.warning(f"[WARN] No coordinates for climate query, falling through")
                            center_lat = center_lng = None
                        
                        if center_lat is not None and center_lng is not None:
                            import uuid as _uuid
                            from geoint.extreme_weather_agent import get_extreme_weather_agent
                            
                            agent = get_extreme_weather_agent()
                            climate_session_id = session_id or str(_uuid.uuid4())
                            user_query = router_action.get("original_query", "Provide a climate overview.")
                            
                            result = await asyncio.wait_for(
                                agent.chat(
                                    session_id=climate_session_id,
                                    user_message=user_query,
                                    latitude=center_lat,
                                    longitude=center_lng,
                                ),
                                timeout=280.0
                            )
                            
                            analysis = result.get("response", "Climate analysis complete.")
                            location_display = location.title() if location else "this location"
                            
                            logger.info(f"[STORM] Climate analysis complete for {location_display}")
                            
                            # Return with navigate_to so map pans to location
                            return {
                                "success": True,
                                "action": "navigate_to",
                                "response": analysis,
                                "user_response": analysis,
                                "navigate_to": {
                                    "latitude": center_lat,
                                    "longitude": center_lng,
                                    "zoom": 10,
                                    "bbox": bbox,
                                    "location_name": location_display
                                },
                                "processing_type": "climate_projection",
                                "session_id": climate_session_id,
                                "timestamp": datetime.utcnow().isoformat()
                            }
                    except asyncio.TimeoutError:
                        logger.error(f"[STORM] Climate analysis timed out for {location}")
                        return {
                            "success": False,
                            "response": f"[TIME] Climate analysis for {location} timed out. Please try a more specific question.",
                            "user_response": f"[TIME] Climate analysis for {location} timed out. Please try a more specific question.",
                            "processing_type": "climate_projection",
                            "timestamp": datetime.utcnow().isoformat()
                        }
                    except Exception as climate_error:
                        logger.error(f"[STORM] Climate analysis failed: {climate_error}")
                        # Fall through to STAC search as fallback

                # ================================================================
                # [STORM] HANDLE NETCDF_COMPUTATION ACTION
                # ================================================================
                if router_action.get("action_type") == "netcdf_computation":
                    location = router_action.get("location") or router_action.get("original_query", "")
                    logger.info(f"[STORM] NETCDF_COMPUTATION ACTION: '{location}'")

                    try:
                        from location_resolver import EnhancedLocationResolver
                        resolver = EnhancedLocationResolver()

                        bbox = await resolver.resolve_location_to_bbox(location) if location else None

                        if not bbox and router_agent and session_id:
                            ctx = router_agent.tools.session_contexts.get(session_id, {})
                            bbox = ctx.get("last_bbox")
                            location = location or ctx.get("last_location", "this location")

                        if bbox and len(bbox) == 4:
                            center_lng = (bbox[0] + bbox[2]) / 2
                            center_lat = (bbox[1] + bbox[3]) / 2
                        else:
                            center_lat = center_lng = None

                        if center_lat is not None and center_lng is not None:
                            import uuid as _uuid
                            from geoint.netcdf_computation_agent import get_netcdf_computation_agent

                            agent = get_netcdf_computation_agent()
                            comp_session_id = session_id or str(_uuid.uuid4())
                            user_query = router_action.get("original_query", "Provide a climate computation analysis.")

                            result = await asyncio.wait_for(
                                agent.chat(
                                    session_id=comp_session_id,
                                    user_message=user_query,
                                    latitude=center_lat,
                                    longitude=center_lng,
                                ),
                                timeout=280.0,
                            )

                            analysis = result.get("response", "Climate computation complete.")
                            location_display = location.title() if location else "this location"

                            return {
                                "success": True,
                                "action": "navigate_to",
                                "response": analysis,
                                "user_response": analysis,
                                "navigate_to": {
                                    "latitude": center_lat,
                                    "longitude": center_lng,
                                    "zoom": 10,
                                    "bbox": bbox,
                                    "location_name": location_display,
                                },
                                "processing_type": "netcdf_computation",
                                "session_id": comp_session_id,
                                "timestamp": datetime.utcnow().isoformat(),
                            }
                    except asyncio.TimeoutError:
                        logger.error(f"[STORM] NetCDF computation timed out for {location}")
                        return {
                            "success": False,
                            "response": f"Climate computation for {location} timed out. Try a simpler query.",
                            "user_response": f"Climate computation for {location} timed out. Try a simpler query.",
                            "processing_type": "netcdf_computation",
                            "timestamp": datetime.utcnow().isoformat(),
                        }
                    except Exception as comp_error:
                        logger.error(f"[STORM] NetCDF computation failed: {comp_error}")
                
            except Exception as router_error:
                logger.warning(f"[WARN] RouterAgent failed: {router_error}, falling back to legacy classification")
                router_action = None
        
        # PHASE 0: EARLY QUERY INTENT CLASSIFICATION
        classification = None
        early_contextual_response = None
        translator = None
        vision_task = None  # For parallel processing of hybrid queries
        
        # ========================================================================
        # ROUTER AGENT -> CLASSIFICATION BRIDGE
        # ========================================================================
        # Convert RouterAgent action_type to classification format for compatibility
        # with existing downstream handlers. This is the SINGLE source of truth for
        # query classification - no legacy Intent Classifier fallback needed.
        # ========================================================================
        if router_action:
            action_type = router_action.get("action_type", "")
            
            if action_type == "stac_search":
                logger.info(f"Converting RouterAgent 'stac_search' to classification format")
                classification = {
                    "intent_type": "stac",
                    "confidence": 0.95,
                    "needs_satellite_data": True,
                    "needs_vision_analysis": False,
                    "needs_contextual_info": False,
                    "reasoning": "RouterAgent routed to STAC search",
                    "router_action": router_action
                }
            elif action_type == "vision_analysis":
                logger.info(f"Converting RouterAgent 'vision_analysis' to classification format")
                classification = {
                    "intent_type": "vision",
                    "confidence": 0.95,
                    "needs_satellite_data": False,
                    "needs_vision_analysis": True,
                    "needs_contextual_info": False,
                    "reasoning": "RouterAgent routed to vision analysis",
                    "router_action": router_action
                }
            elif action_type == "contextual":
                logger.info(f"Converting RouterAgent 'contextual' to classification format")
                classification = {
                    "intent_type": "contextual",
                    "confidence": 0.95,
                    "needs_satellite_data": False,
                    "needs_vision_analysis": False,
                    "needs_contextual_info": True,
                    "reasoning": "RouterAgent routed to contextual/knowledge response",
                    "router_action": router_action
                }
            elif action_type == "hybrid":
                logger.info(f"Converting RouterAgent 'hybrid' to classification format")
                classification = {
                    "intent_type": "hybrid",
                    "confidence": 0.95,
                    "needs_satellite_data": True,
                    "needs_vision_analysis": True,
                    "needs_contextual_info": False,
                    "reasoning": "RouterAgent routed to hybrid (STAC + vision)",
                    "router_action": router_action
                }
            # Note: navigate_to and extreme_weather return early before this point
            # Safety net: if navigate_to somehow didn't return early, treat as contextual
            if action_type == "navigate_to":
                logger.warning(f"[WARN] navigate_to reached classification bridge (should have returned early). Treating as contextual.")
                classification = {
                    "intent_type": "contextual",
                    "confidence": 0.7,
                    "needs_satellite_data": False,
                    "needs_vision_analysis": False,
                    "needs_contextual_info": True,
                    "reasoning": "navigate_to fallthrough safety net",
                    "router_action": router_action
                }
        
        logger.info(f"[SEARCH] SEMANTIC_KERNEL_AVAILABLE: {SEMANTIC_KERNEL_AVAILABLE}")
        if SEMANTIC_KERNEL_AVAILABLE and global_translator:
            try:
                translator = global_translator
                
                # ========================================================================
                # [LAUNCH] QUICK START QUERY OPTIMIZATION
                # ========================================================================
                # Skip expensive AI classification for pre-defined demo queries
                # Provides ~3-5 second speedup for quick start button clicks
                # ========================================================================
                quickstart_classification = get_quickstart_classification(natural_query)
                quickstart_location = get_quickstart_location(natural_query)
                
                if quickstart_classification and quickstart_location:
                    logger.info(f"[LAUNCH] QUICK START QUERY DETECTED: '{natural_query}'")
                    logger.info(f"   Pre-computed: collection={quickstart_location['collections']}, location={quickstart_location['location']}")
                    classification = quickstart_classification
                    # Store location data for later use in STAC search
                    quickstart_data = quickstart_location
                else:
                    quickstart_data = None
                
                # ========================================================================
                # [BRAIN] UNIFIED INTENT CLASSIFICATION - Single GPT-5 call
                # ========================================================================
                # Intent Types: vision | stac | hybrid | contextual
                # - vision: Analyze currently visible imagery (no new data loading)
                # - stac: Load new satellite imagery only (no analysis)
                # - hybrid: Load new imagery AND analyze it (sequential operation)
                # - contextual: Information/education only (no map interaction)
                # ========================================================================
                
                # ========================================================================
                # CLASSIFICATION SOURCE: RouterAgent is the SINGLE source of truth
                # ========================================================================
                # RouterAgent has already classified the query and set `classification`.
                # No fallback to legacy Intent Classifier needed.
                # If RouterAgent fails (router_action is None), default to STAC search.
                # ========================================================================
                if not classification:
                    # RouterAgent failed or wasn't available - default to STAC search
                    logger.warning("RouterAgent did not provide classification, defaulting to STAC search")
                    classification = {
                        "intent_type": "stac",
                        "confidence": 0.5,
                        "needs_satellite_data": True,
                        "needs_vision_analysis": False,
                        "needs_contextual_info": False,
                        "reasoning": "Fallback: RouterAgent unavailable",
                        "modules": []
                    }
                elif classification.get("is_quickstart"):
                    logger.info("Skipping classification - Quick start query with pre-computed result")
                else:
                    logger.info("Using RouterAgent classification")
                        
                intent_type = classification.get('intent_type', 'stac')  # Default to STAC query
                confidence = classification.get('confidence', 0)
                modules_to_execute = classification.get('modules', [])
                
                logger.info(f"CLASSIFICATION RESULT (from RouterAgent):")
                logger.info(f"   Query: '{natural_query}'")
                logger.info(f"   Intent: {intent_type}")
                logger.info(f"   Confidence: {confidence:.2f}")
                logger.info(f"   Needs satellite data: {classification.get('needs_satellite_data', False)}")
                logger.info(f"   Needs contextual info: {classification.get('needs_contextual_info', False)}")
                logger.info(f"   Needs vision analysis: {classification.get('needs_vision_analysis', False)}")
                
                # TRACE: Classification result
                log_pipeline_step(pipeline_session_id, "CLASSIFICATION", "OUTPUT", {
                    "intent_type": intent_type,
                    "confidence": round(confidence, 2),
                    "modules": modules_to_execute,
                    "needs_satellite_data": classification.get('needs_satellite_data', False),
                    "needs_vision": classification.get('needs_vision_analysis', False),
                    "reasoning": classification.get('reasoning', 'N/A')[:100]  # Truncate for readability
                })
                
                # Note: GEOINT mode is now UI-driven via /api/geoint/mobility endpoint
                # No query-based detection needed - all triggered by toggle + pin drop
                
                # ========================================================================
                # CHAT VISION ANALYSIS - Priority Detection
                # ========================================================================
                # RouterAgent classification is the SOURCE OF TRUTH for intent.
                # The keyword detector is a FALLBACK only — it must NOT override
                # the Router when the Router explicitly classified as stac_search.
                #
                # Bug this fixes: "Show me Sentinel-2 imagery here" after navigating
                # to Canada. The keyword detector sees "show me" + "sentinel" in
                # conversation history and flags it as vision. But the Router correctly
                # classified it as stac_search (has_collection=true). The keyword
                # detector was hijacking STAC queries into the Vision path, which
                # then fails with "No STAC items available to sample" because no
                # imagery has been loaded yet.
                # ========================================================================
                
                from agents import get_vision_agent  # EnhancedVisionAgent with 5 tools
                vision_agent = get_vision_agent()
                conversation_history = req_body.get('conversation_history', []) or req_body.get('messages', [])
                
                # STEP 1: Check if Router explicitly classified as STAC search
                # If so, do NOT let keyword detector override — the user wants to LOAD data, not analyze it
                router_says_stac = classification and classification.get('intent_type') == 'stac'
                
                if router_says_stac:
                    needs_vision = False
                    logger.info("[CHART] RouterAgent classified as STAC search — skipping vision keyword detection")
                else:
                    # STEP 2: Use keyword detector for non-STAC queries
                    from geoint.chat_vision_analyzer import get_chat_vision_analyzer
                    chat_vision_detector = get_chat_vision_analyzer()
                    needs_vision = chat_vision_detector.should_use_vision(natural_query, conversation_history)
                    
                    if needs_vision:
                        logger.info("[SEARCH] Vision query detected by KEYWORD/CONTEXT matching (priority check)")
                    else:
                        # STEP 3: Fallback to classification if keywords didn't match
                        # This catches edge cases where user doesn't use explicit vision keywords
                        needs_vision = classification.get('needs_vision_analysis', False)
                        if needs_vision:
                            logger.info("[SEARCH] Vision query detected by GPT CLASSIFICATION (fallback check)")
                
                # ========================================================================
                # [LAUNCH] PARALLEL PROCESSING: Vision + Data for Hybrid Queries
                # ========================================================================
                # For hybrid queries that need both vision analysis AND STAC data,
                # we can run them in parallel to save ~5-8 seconds
                # ========================================================================
                
                if needs_vision:
                    logger.info("[IMG] VISION QUERY DETECTED: User is asking about visible imagery")
                    
                    # Check if frontend provided map context
                    map_bounds = req_body.get('map_bounds')  # {north, south, east, west, center_lat, center_lng}
                    imagery_url = req_body.get('imagery_url')  # Current visible imagery URL
                    imagery_base64 = req_body.get('imagery_base64')  # Base64 screenshot from frontend
                    current_collection = req_body.get('current_collection')  # Collection ID (string)
                    tile_urls = req_body.get('tile_urls', [])  # TiTiler URLs from prior STAC response
                    has_satellite_data = req_body.get('has_satellite_data', False)  # Flag if STAC imagery loaded
                    conversation_history = req_body.get('conversation_history', []) or req_body.get('messages', [])
                    
                    # Initialize collections_list (will be populated from session context or current_collection)
                    collections_list = []
                    
                    # ================================================================
                    # ENHANCED CONTEXT: Include session history from router
                    # ================================================================
                    # The Vision Agent should have full context from the session:
                    # - Previous locations viewed
                    # - Collections previously loaded
                    # - Conversation history
                    # ================================================================
                    session_context = {}
                    stac_items_from_session = []
                    if router_agent and session_id:
                        session_context = router_agent.tools.session_contexts.get(session_id, {})
                        logger.info(f"[LIST] Session context for Vision Agent: {list(session_context.keys())}")
                        
                        # Merge session collections with current collection
                        session_collections = session_context.get('last_collections', [])
                        if session_collections and not collections_list:
                            collections_list = session_collections
                        
                        # Get STAC items from session for raster analysis
                        stac_items_from_session = session_context.get('last_stac_items', [])
                        if stac_items_from_session:
                            logger.info(f"[PKG] Retrieved {len(stac_items_from_session)} STAC items from session for vision agent")
                        
                        # ================================================================
                        # [PIN] SESSION BBOX OVERRIDE
                        # ================================================================
                        # Use session bbox in TWO cases:
                        # 1. Frontend sent no bounds at all (map_bounds is None)
                        # 2. User recently navigated (navigate_to set has_rendered_map=False)
                        #    but frontend bounds are STALE because the useEffect that
                        #    computes mapContext.bounds doesn't track camera position —
                        #    it only re-fires on satelliteData/visionMode changes.
                        #    After navigate_to, the camera moved but no dependency changed,
                        #    so frontend still sends the old US-center coordinates.
                        # ================================================================
                        session_bbox = session_context.get('last_bbox')
                        recently_navigated = session_bbox and not session_context.get('has_rendered_map', True)
                        
                        if session_bbox and (not map_bounds or recently_navigated):
                            bbox = session_bbox
                            map_bounds = {
                                'west': bbox[0], 'south': bbox[1],
                                'east': bbox[2], 'north': bbox[3],
                                'center_lat': (bbox[1] + bbox[3]) / 2,
                                'center_lng': (bbox[0] + bbox[2]) / 2
                            }
                            override_reason = "no frontend bounds" if not map_bounds else "post-navigate_to (frontend bounds stale)"
                            logger.info(f"[PIN] Using session bbox for Vision Agent ({override_reason}): {session_context.get('last_location')}")
                    
                    # Convert collection to list for Vision Agent (typically one collection per query)
                    if current_collection and current_collection not in collections_list:
                        collections_list = [current_collection] + collections_list
                    
                    # Log vision context availability
                    logger.info(f"[SNAP] Map screenshot available: {bool(imagery_base64)}")
                    logger.info(f"[SAT] Satellite data loaded: {has_satellite_data}")
                    logger.info(f"[MAP] Map bounds available: {bool(map_bounds)}")
                    
                    # Check if this is a HYBRID query (vision + data)
                    needs_data = classification.get('needs_satellite_data', False)
                    is_hybrid_vision = needs_vision and needs_data
                    
                    if is_hybrid_vision:
                        logger.info("[SHUFFLE] HYBRID VISION + DATA QUERY: Will run vision + STAC in PARALLEL for optimal performance")
                    
                    if map_bounds or imagery_url or imagery_base64:
                        try:
                            # For hybrid queries, we'll start vision analysis but continue to STAC
                            # Both will run in parallel (vision task created, STAC search proceeds)
                            vision_task = None
                            
                            if is_hybrid_vision:
                                # Create vision agent task (runs in background)
                                logger.info("[FAST] Starting Vision Agent task (parallel execution)...")
                                vision_task = asyncio.create_task(
                                    vision_agent.analyze(
                                        user_query=natural_query,
                                        session_id=session_id,
                                        imagery_base64=imagery_base64,
                                        map_bounds=map_bounds or {},
                                        collections=collections_list,
                                        tile_urls=tile_urls,
                                        stac_items=stac_items_from_session,
                                        conversation_history=conversation_history
                                    )
                                )
                                # Don't await yet - let it run in parallel with STAC search
                                logger.info("[SYNC] Vision Agent task created, continuing to STAC data retrieval (parallel)...")
                            else:
                                # Pure vision query - invoke Vision Agent and return immediately
                                logger.info("[BOT] Invoking Vision Agent for pure vision query")
                                logger.info(f"   Collections: {collections_list}")
                                logger.info(f"   Tile URLs: {len(tile_urls)} tiles")
                                logger.info(f"   STAC items: {len(stac_items_from_session)} items")
                                logger.info(f"   Has screenshot: {bool(imagery_base64)}")
                                logger.info(f"   Has map_bounds: {bool(map_bounds)}")
                                
                                # EnhancedVisionAgent with tools - pass full context including STAC items
                                vision_result = await vision_agent.analyze(
                                    user_query=natural_query,
                                    session_id=session_id,
                                    imagery_base64=imagery_base64,
                                    map_bounds=map_bounds or {},
                                    collections=collections_list,
                                    tile_urls=tile_urls,
                                    stac_items=stac_items_from_session,
                                    conversation_history=conversation_history
                                )
                                
                                # ================================================================
                                # [SEARCH] DEBUG: Log vision_result to trace issues
                                # ================================================================
                                logger.info(f"[SEARCH] Vision Agent returned: {type(vision_result)}")
                                if vision_result:
                                    logger.info(f"   Keys: {list(vision_result.keys())}")
                                    logger.info(f"   Response: '{str(vision_result.get('response', ''))[:100]}...'")
                                    logger.info(f"   Analysis: '{str(vision_result.get('analysis', ''))[:100]}...'")
                                
                                # Check for response (or analysis as fallback)
                                response_text = vision_result.get("response") or vision_result.get("analysis") if vision_result else None
                                
                                if response_text:
                                    logger.info("[OK] Vision Agent analysis completed")
                                    logger.info(f"   Cached: {vision_result.get('cached', False)}")
                                    
                                    # ================================================================
                                    # VISION AGENT TRACING: Log tool usage for debugging
                                    # ================================================================
                                    tools_used = vision_result.get("tools_used", [])
                                    tool_calls = vision_result.get("tool_calls", [])
                                    logger.info(f"[TOOL] Vision Agent tools used: {tools_used}")
                                    
                                    # Log to pipeline trace
                                    log_pipeline_step(pipeline_session_id, "VISION_AGENT", "OUTPUT", {
                                        "tools_used": tools_used,
                                        "tool_calls": tool_calls,
                                        "has_screenshot": vision_result.get("context", {}).get("has_screenshot", False),
                                        "collections": vision_result.get("context", {}).get("collections", []),
                                        "response_length": len(response_text)
                                    })
                                    
                                    return {
                                        "success": True,
                                        "response": response_text,
                                        "vision_analysis": vision_result,
                                        "processing_type": "vision_agent",
                                        "timestamp": datetime.utcnow().isoformat()
                                    }
                                else:
                                    # ================================================================
                                    # [ALERT] VISION AGENT FAILED - Return error, DON'T fall through to STAC
                                    # ================================================================
                                    logger.warning(f"[WARN] Vision Agent returned empty response. Result: {vision_result}")
                                    log_pipeline_step(pipeline_session_id, "VISION_AGENT", "ERROR", {
                                        "error": "Empty response from Vision Agent",
                                        "vision_result": str(vision_result)[:500] if vision_result else "None"
                                    })
                                    
                                    # Return a helpful error message instead of falling through to STAC
                                    return {
                                        "success": False,
                                        "response": "I tried to analyze the map but couldn't generate a response. Please try asking your question again.",
                                        "error": "Vision Agent returned empty response",
                                        "processing_type": "vision_agent_error",
                                        "timestamp": datetime.utcnow().isoformat()
                                    }
                        except Exception as e:
                            logger.warning(f"[WARN] Chat vision analysis failed: {e}, returning error...")
                            logger.error(traceback.format_exc())
                            
                            # Return error, DON'T fall through to STAC for vision queries
                            return {
                                "success": False,
                                "response": f"I encountered an error analyzing the imagery: {str(e)}",
                                "error": str(e),
                                "processing_type": "vision_agent_error",
                                "timestamp": datetime.utcnow().isoformat()
                            }
                    else:
                        # ================================================================
                        # NO MAP CONTEXT: Still invoke Vision Agent with LLM tool
                        # ================================================================
                        # The Vision Agent can use its query_knowledge tool to provide
                        # a helpful response even without map context. This is better than
                        # just returning an error message.
                        # ================================================================
                        logger.info("ℹ️ No map screenshot, but Vision Agent can use LLM tool")
                        try:
                            vision_result = await vision_agent.analyze(
                                user_query=natural_query,
                                session_id=session_id,
                                imagery_base64=None,
                                map_bounds=map_bounds or {},
                                collections=collections_list,
                                conversation_history=conversation_history
                            )
                            
                            # [SEARCH] DEBUG: Log vision_result
                            logger.info(f"[SEARCH] Vision Agent (LLM mode) returned: {type(vision_result)}")
                            if vision_result:
                                logger.info(f"   Keys: {list(vision_result.keys())}")
                                logger.info(f"   Response: '{str(vision_result.get('response', ''))[:100]}...'")
                            
                            # Check for response (or analysis as fallback)
                            response_text = vision_result.get("response") or vision_result.get("analysis") if vision_result else None
                            
                            if response_text:
                                logger.info("[OK] Vision Agent (LLM mode) completed")
                                
                                # ================================================================
                                # VISION AGENT TRACING: Log tool usage for debugging
                                # ================================================================
                                tools_used = vision_result.get("tools_used", [])
                                tool_calls = vision_result.get("tool_calls", [])
                                logger.info(f"[TOOL] Vision Agent (LLM mode) tools used: {tools_used}")
                                
                                # Log to pipeline trace
                                log_pipeline_step(pipeline_session_id, "VISION_AGENT_LLM", "OUTPUT", {
                                    "tools_used": tools_used,
                                    "tool_calls": tool_calls,
                                    "has_screenshot": False,
                                    "collections": collections_list,
                                    "response_length": len(response_text)
                                })
                                
                                return {
                                    "success": True,
                                    "response": response_text,
                                    "vision_analysis": vision_result,
                                    "processing_type": "vision_agent_llm",
                                    "timestamp": datetime.utcnow().isoformat()
                                }
                            else:
                                # ================================================================
                                # [ALERT] VISION AGENT LLM MODE FAILED - Return helpful message
                                # ================================================================
                                logger.warning(f"[WARN] Vision Agent (LLM mode) returned empty. Result: {vision_result}")
                                
                                # For "what is on the map" without screenshot, give a helpful response
                                return {
                                    "success": True,
                                    "response": "I can see you're asking about what's on the map. I can see satellite imagery is displayed. Could you ask a more specific question about what you'd like to know, such as 'What city is shown?' or 'What features can you identify?'",
                                    "processing_type": "vision_agent_no_context",
                                    "timestamp": datetime.utcnow().isoformat()
                                }
                        except Exception as e:
                            logger.warning(f"[WARN] Vision Agent LLM fallback failed: {e}")
                            logger.error(traceback.format_exc())
                            
                            # Return helpful message instead of falling through to STAC
                            return {
                                "success": True,
                                "response": "I can see satellite imagery on the map but couldn't analyze it in detail. Please try asking a specific question about the location or features you see.",
                                "error": str(e),
                                "processing_type": "vision_agent_error",
                                "timestamp": datetime.utcnow().isoformat()
                            }
                
                # For contextual queries, skip STAC search and generate direct educational response
                # intent_type = "contextual" for information/education queries (e.g., "How do hurricanes form?")
                if intent_type == "contextual" and confidence > 0.8 and not classification.get('needs_satellite_data', False):
                    logger.info("[MSG] CONTEXTUAL REQUEST: Skipping STAC search, generating educational response...")
                    
                    # ================================================================
                    # LOCATION CONTEXT INJECTION: Enrich query with session location
                    # ================================================================
                    # If the user asks "what is on the map" after navigating to Tokyo,
                    # the contextual handler has no idea where the user is looking.
                    # We inject the session location so the LLM generates a correct answer.
                    # ================================================================
                    contextual_query = natural_query
                    if router_agent and session_id:
                        ctx = router_agent.tools.session_contexts.get(session_id, {})
                        session_location = ctx.get('last_location')
                        session_bbox = ctx.get('last_bbox')
                        current_map_bounds = req_body.get('map_bounds')
                        if session_location or session_bbox or current_map_bounds:
                            location_hint = session_location or ""
                            if not location_hint and current_map_bounds:
                                location_hint = f"({current_map_bounds.get('center_lat', 'N/A')}, {current_map_bounds.get('center_lng', 'N/A')})"
                            elif not location_hint and session_bbox:
                                center_lat = (session_bbox[1] + session_bbox[3]) / 2
                                center_lng = (session_bbox[0] + session_bbox[2]) / 2
                                location_hint = f"({center_lat:.4f}, {center_lng:.4f})"
                            
                            if location_hint:
                                contextual_query = f"{natural_query} [The user is currently viewing the map at: {location_hint}]"
                                logger.info(f"[PIN] Enriched contextual query with location: {location_hint}")
                    
                    try:
                        contextual_response = await asyncio.wait_for(
                            translator.generate_contextual_earth_science_response(
                                contextual_query, 
                                classification, 
                                {"success": True, "results": {"features": []}}  # Empty STAC response for contextual-only
                            ),
                            timeout=30.0
                        )
                        
                        if contextual_response and contextual_response.get("message"):
                            logger.info("[OK] Generated contextual response successfully")
                            return {
                                "success": True,
                                "response": contextual_response.get("message"),
                                "query_classification": {
                                    "intent_type": intent_type,
                                    "confidence": confidence,
                                    "needs_satellite_data": False,
                                    "needs_contextual_info": True
                                },
                                "processing_type": "contextual_only",
                                "timestamp": datetime.utcnow().isoformat()
                            }
                    except Exception as e:
                        logger.warning(f"[WARN] Contextual response generation failed: {e}, proceeding with STAC search...")
                
            except Exception as e:
                logger.error(f"[FAIL] Early classification failed: {e}")
                classification = None
        
        # PHASE 1: SEMANTIC TRANSLATION TO STAC PARAMETERS
        # ========================================================================
        # [GEAR] CONDITIONAL COLLECTION MAPPING: Only run for STAC and Hybrid queries
        # ========================================================================
        # Skip collection mapping for:
        # - "vision" queries (analyze existing imagery, no new data needed)
        # - "contextual" queries (information only, no map interaction)
        # Run collection mapping for:
        # - "stac" queries (load new imagery)
        # - "hybrid" queries (load new imagery + analyze)
        # ========================================================================
        stac_params = None
        stac_query = None
        response_message = "I can help you find Earth science data, but I need more specific information."
        
        # Check if we need to run collection mapping based on intent
        skip_collection_mapping = False
        if classification and intent_type:
            if intent_type in ["vision", "contextual"]:
                skip_collection_mapping = True
                logger.info(f"[SKIP] Skipping collection mapping for {intent_type} query (no STAC search needed)")
        
        if not skip_collection_mapping:
            if not SEMANTIC_KERNEL_AVAILABLE:
                logger.warning("[WARN] Semantic Kernel not available, using fallback processing")
                
                # Fallback: Simple collection detection (like Router Function App)
                collections = detect_collections(natural_query)
                stac_params = {
                    "collections": collections,
                    "limit": 20,  # PERFORMANCE: Reduced from 100 to 20 for faster queries (3-5s improvement)
                    "original_query": natural_query
                }
                
                if collections:
                    stac_query = build_stac_query(stac_params)
                    logger.info(f"[TOOL] Built fallback STAC query: {json.dumps(stac_query, indent=2)}")
                
            elif SEMANTIC_KERNEL_AVAILABLE and translator:
                try:
                    logger.info(f"[BOT] Starting multi-agent pipeline — query='{natural_query}' pin={pin}")
                    
                    # ========================================================================
                    # [PIN] SESSION BBOX: Fallback location for queries without explicit location
                    # ========================================================================
                    # Always pass the session's last_bbox as a fallback. The translate_query
                    # method will use it if Agent 2 doesn't extract a location from the query.
                    # This makes location handling more deterministic and less reliant on the
                    # LLM correctly setting use_current_location=True.
                    # ========================================================================
                    session_bbox = None
                    session_location = None
                    
                    # Get session context from router_agent (session_contexts is on router_agent.tools)
                    if router_agent and session_id:
                        try:
                            session_context = router_agent.tools.session_contexts.get(session_id, {})
                            session_bbox = session_context.get("last_bbox")
                            session_location = session_context.get("last_location")
                            if session_bbox:
                                logger.info(f"[PIN] Session fallback available: {session_location} bbox={session_bbox}")
                        except AttributeError:
                            logger.debug("[PIN] No session context available (router_agent.tools.session_contexts not found)")
                    
                    # If router explicitly said use_current_location, prioritize it
                    if router_action and router_action.get("use_current_location"):
                        logger.info(f"[PIN] Router set use_current_location=True")
                    
                    logger.info("[SYNC] Translating natural language to STAC parameters...")
                    
                    # ========================================================================
                    # [LAUNCH] QUICK START OPTIMIZATION: Skip expensive translation for demo queries
                    # ========================================================================
                    # For the 22 quick start queries, we have pre-computed collections + bbox.
                    # This saves ~3-5 seconds by skipping AI classification + geocoding.
                    # ========================================================================
                    if quickstart_data:
                        logger.info(f"[LAUNCH] Using pre-computed STAC params for quick start query")
                        
                        # Convert temporal to STAC datetime range format
                        temporal = quickstart_data.get('temporal')
                        datetime_range = None
                        if temporal:
                            # Handle different temporal formats:
                            # "2025-06" -> "2025-06-01/2025-06-30"
                            # "2017" -> "2017-01-01/2017-12-31"
                            # "2026-01-01" -> "2026-01-01/2026-01-01"
                            if len(temporal) == 4:  # Year only: "2017"
                                datetime_range = f"{temporal}-01-01/{temporal}-12-31"
                            elif len(temporal) == 7:  # Year-Month: "2025-06"
                                import calendar
                                year, month = int(temporal[:4]), int(temporal[5:7])
                                last_day = calendar.monthrange(year, month)[1]
                                datetime_range = f"{temporal}-01/{temporal}-{last_day:02d}"
                            elif len(temporal) == 10:  # Full date: "2026-01-01"
                                datetime_range = f"{temporal}/{temporal}"
                            else:
                                datetime_range = temporal  # Pass through as-is
                            logger.info(f"[DATE] Converted temporal '{temporal}' to datetime range: {datetime_range}")
                        
                        stac_params = {
                            'collections': quickstart_data['collections'],
                            'bbox': quickstart_data['bbox'],
                            'datetime': datetime_range,
                            'location_name': quickstart_data['location'],
                            'is_quickstart': True
                        }
                        logger.info(f"   Collections: {stac_params['collections']}")
                        logger.info(f"   Bbox: {stac_params['bbox']}")
                        if stac_params['datetime']:
                            logger.info(f"   Datetime: {stac_params['datetime']}")
                    else:
                        # Use the semantic translator's translate_query method with pin and session_bbox fallback
                        stac_params = await translator.translate_query(natural_query, pin_location=pin, session_bbox=session_bbox)
                    
                    # ========================================================================
                    # [ALERT] LOCATION VALIDATION: Check if location is required but missing
                    # ========================================================================
                    if stac_params and stac_params.get('error') == 'LOCATION_REQUIRED':
                        logger.warning(f"[WARN] Location required but not found in query")
                        return {
                            "success": False,
                            "error": "LOCATION_REQUIRED",
                            "response": stac_params.get('message', 'Please specify a location for your search.'),
                            "suggestions": stac_params.get('suggestions', []),
                            "timestamp": datetime.utcnow().isoformat()
                        }
                    # ========================================================================
                    
                    if stac_params and stac_params.get('collections'):
                        logger.info(f"[OK] Translation successful: {len(stac_params.get('collections', []))} collections selected")
                        
                        # [MICRO] TRACE: Semantic translation result
                        log_pipeline_step(pipeline_session_id, "SEMANTIC_TRANSLATION", "OUTPUT", {
                            "collections": stac_params.get('collections', []),
                            "bbox": stac_params.get('bbox'),
                            "datetime": stac_params.get('datetime'),
                            "location_name": stac_params.get('location_name', 'N/A')
                        })
                        
                        # Build STAC query from semantic analysis (like Router Function App)
                        stac_query = build_stac_query(stac_params)
                        logger.info(f"[TOOL] Built STAC query from params: {json.dumps(stac_query, indent=2)}")
                        
                        # ========================================================================
                        # [DATE] DATETIME SAFETY NET: Regex fallback if GPT datetime agent failed
                        # ========================================================================
                        # If the query mentions a date but stac_query has no datetime filter,
                        # use regex extraction as a deterministic fallback. This catches cases
                        # where the GPT datetime_translation_agent returns None or fails.
                        # ========================================================================
                        if not stac_query.get('datetime') and natural_query:
                            import re, calendar as cal_mod
                            query_lower = natural_query.lower()
                            month_names = {
                                'january': 1, 'february': 2, 'march': 3, 'april': 4,
                                'may': 5, 'june': 6, 'july': 7, 'august': 8,
                                'september': 9, 'october': 10, 'november': 11, 'december': 12
                            }
                            extracted_datetime = None
                            
                            # Pattern 1: "from/in/for MONTH YEAR" (e.g., "from December 2018")
                            month_year_match = re.search(
                                r'(?:from|in|for|of)\s+(january|february|march|april|may|june|july|august|september|october|november|december)\s+(\d{4})',
                                query_lower
                            )
                            if month_year_match:
                                m_name, y_str = month_year_match.group(1), month_year_match.group(2)
                                m_num = month_names[m_name]
                                y_num = int(y_str)
                                last_day = cal_mod.monthrange(y_num, m_num)[1]
                                extracted_datetime = f"{y_str}-{m_num:02d}-01/{y_str}-{m_num:02d}-{last_day:02d}"
                            
                            # Pattern 2: "MONTH YEAR" without preposition (e.g., "December 2018")
                            if not extracted_datetime:
                                month_year_match2 = re.search(
                                    r'(january|february|march|april|may|june|july|august|september|october|november|december)\s+(\d{4})',
                                    query_lower
                                )
                                if month_year_match2:
                                    m_name, y_str = month_year_match2.group(1), month_year_match2.group(2)
                                    m_num = month_names[m_name]
                                    y_num = int(y_str)
                                    last_day = cal_mod.monthrange(y_num, m_num)[1]
                                    extracted_datetime = f"{y_str}-{m_num:02d}-01/{y_str}-{m_num:02d}-{last_day:02d}"
                            
                            # Pattern 3: "from/in/for YEAR" (e.g., "from 2018")
                            if not extracted_datetime:
                                year_match = re.search(r'(?:from|in|for)\s+((?:19|20)\d{2})\b', query_lower)
                                if year_match:
                                    y_str = year_match.group(1)
                                    extracted_datetime = f"{y_str}-01-01/{y_str}-12-31"
                            
                            if extracted_datetime:
                                stac_query['datetime'] = extracted_datetime
                                stac_params['datetime'] = extracted_datetime
                                logger.info(f"[DATE] REGEX FALLBACK: Extracted datetime '{extracted_datetime}' from query (GPT agent missed it)")
                        
                        
                    else:
                        logger.warning(f"[WARN] Translation did not produce valid STAC parameters. Got: {stac_params}")
                        
                        # [MICRO] TRACE: Translation failed
                        log_pipeline_step(pipeline_session_id, "SEMANTIC_TRANSLATION", "ERROR", {
                            "error": "No valid collections returned",
                            "raw_params": str(stac_params)[:200]
                        })
                        
                except Exception as e:
                    logger.error(f"[FAIL] Semantic translation failed: {e}", exc_info=True)
                    logger.error(f"[FAIL] Full traceback: {traceback.format_exc()}")
                    stac_params = None
                    stac_query = None
        
        # PHASE 2: EXECUTE STAC SEARCH (if we have a valid query)
        stac_response = {"results": {"type": "FeatureCollection", "features": []}}
        features = []
        
        # [CHART] DIAGNOSTICS: Track filtering stages for helpful error messages
        search_diagnostics = {
            "raw_count": 0,
            "spatial_filtered_count": 0,
            "final_count": 0,
            "stac_query": stac_query,
            "failure_stage": "unknown"
        }
        
        # Note: pipeline_session_id already set at start of query processing
        
        if stac_query:
            try:
                logger.info("[WEB] Executing STAC search...")
                
                # [SEARCH] PIPELINE LOG: STAC Search Input
                log_pipeline_step(pipeline_session_id, "STAC_SEARCH", "INPUT", {
                    "collections": stac_query.get("collections"),
                    "bbox": stac_query.get("bbox"),
                    "datetime": stac_query.get("datetime"),
                    "filter": stac_query.get("filter")
                })
                
                # Determine which STAC endpoint to use (intelligent routing from Router Function App)
                stac_endpoint = translator.determine_stac_source(natural_query, stac_params)
                logger.info(f"[SIGNAL] STAC source determined: {stac_endpoint}")
                
                # Pass original_query for smart deduplication (removes duplicate grid cells)
                stac_response = await execute_direct_stac_search(stac_query, stac_endpoint, original_query=natural_query)
                
                if stac_response.get("success"):
                    raw_features = stac_response.get("results", {}).get("features", [])
                    search_diagnostics["raw_count"] = len(raw_features)
                    logger.info(f"[OK] STAC search completed: {len(raw_features)} raw features found")
                    
                    # [SEARCH] PIPELINE LOG: STAC Search Output
                    log_pipeline_step(pipeline_session_id, "STAC_SEARCH", "OUTPUT", {
                        "feature_count": len(raw_features),
                        "first_feature_id": raw_features[0].get("id") if raw_features else None,
                        "first_feature_bbox": raw_features[0].get("bbox") if raw_features else None
                    })
                    
                    # [SEARCH] MODIS BBOX FILTERING: MODIS STAC API returns tiles outside requested bbox
                    # MODIS uses sinusoidal grid (h/v tiles), so bbox filter isn't strict in PC STAC API
                    # Filter out tiles whose center is outside requested bbox to prevent showing
                    # Arizona/Texas tiles when user requested California
                    collections = stac_query.get('collections', [])
                    is_modis = any(col.startswith('modis-') for col in collections)
                    requested_bbox = stac_query.get("bbox")
                    
                    if is_modis and requested_bbox and raw_features:
                        logger.info(f"[MAP]  MODIS BBOX FILTER: Checking {len(raw_features)} tiles against requested bbox")
                        logger.info(f"   Requested bbox: [{requested_bbox[0]:.2f}, {requested_bbox[1]:.2f}, {requested_bbox[2]:.2f}, {requested_bbox[3]:.2f}]")
                        
                        filtered_features = []
                        req_west, req_south, req_east, req_north = requested_bbox
                        
                        for feature in raw_features:
                            tile_bbox = feature.get('bbox')
                            if not tile_bbox or len(tile_bbox) < 4:
                                continue
                            
                            # Calculate tile center
                            tile_west, tile_south, tile_east, tile_north = tile_bbox[:4]
                            tile_center_lon = (tile_west + tile_east) / 2
                            tile_center_lat = (tile_south + tile_north) / 2
                            
                            # Check if tile center is within requested bbox
                            if (req_west <= tile_center_lon <= req_east and 
                                req_south <= tile_center_lat <= req_north):
                                filtered_features.append(feature)
                            else:
                                logger.debug(f"   [FAIL] Filtered out tile with center ({tile_center_lon:.2f}, {tile_center_lat:.2f}) outside bbox")
                        
                        logger.info(f"[OK] MODIS BBOX FILTER: Kept {len(filtered_features)}/{len(raw_features)} tiles within requested bbox")
                        raw_features = filtered_features
                        search_diagnostics["raw_count"] = len(raw_features)
                        search_diagnostics["modis_bbox_filtered"] = True
                    
                    # [SEARCH] NO SPATIAL PRE-FILTERING: Agent 3 handles spatial coverage intelligently
                    # Agent 3's GPT-5 ensures full coverage by:
                    # 1. Understanding tile mosaicking and grid systems
                    # 2. Ensuring "NO GAPS in spatial coverage" (explicit in GPT prompt)
                    # 3. Using context-aware tile limits (5-50 based on AOI size)
                    # Pre-filtering with geometric overlap could remove tiles Agent 3 needs for seamless coverage
                    if SEMANTIC_KERNEL_AVAILABLE and translator and raw_features and stac_query.get("bbox"):
                        requested_bbox = stac_query.get("bbox")
                        
                        # Pass ALL tiles to Agent 3 for intelligent selection
                        spatially_filtered_features = raw_features
                        search_diagnostics["spatial_filter_skipped"] = True
                        search_diagnostics["spatial_filtered_count"] = len(raw_features)
                        logger.info(f"[SKIP] Skipping spatial pre-filter: Agent 3 will ensure coverage from {len(raw_features)} tiles")
                        
                        # [CLOUD] CLIENT-SIDE CLOUD COVER FILTERING: Safety net in case STAC API ignored the filter
                        # Extract cloud cover limit from query parameters OR detect from original query keywords
                        cloud_cover_limit = None
                        query_filter = stac_query.get("query", {})
                        logger.info(f"[SEARCH] DEBUG: Client-side check - stac_query.get('query') = {query_filter}")
                        
                        # Check both eo:cloud_cover (Sentinel-2, Landsat) and cloud_cover (HLS)
                        for prop_name in ["eo:cloud_cover", "cloud_cover"]:
                            if prop_name in query_filter:
                                cloud_cover_filter = query_filter[prop_name]
                                logger.info(f"[SEARCH] DEBUG: Found {prop_name} in query_filter: {cloud_cover_filter}")
                                if "lte" in cloud_cover_filter:
                                    cloud_cover_limit = cloud_cover_filter["lte"]
                                elif "lt" in cloud_cover_filter:
                                    cloud_cover_limit = cloud_cover_filter["lt"]
                                break
                            else:
                                logger.info(f"[SEARCH] DEBUG: {prop_name} NOT in query_filter")
                        
                        # [TOOL] FALLBACK: Keyword detection if no cloud filter in query parameters
                        # This catches cases where the cloud filter wasn't propagated through the pipeline
                        if cloud_cover_limit is None and natural_query:
                            query_lower = natural_query.lower()
                            low_cloud_keywords = ['low cloud', 'no cloud', 'clear', 'cloudless', 
                                                  'minimal cloud', 'cloud-free', 'without clouds',
                                                  'clear sky', 'clear skies', 'no clouds']
                            if any(kw in query_lower for kw in low_cloud_keywords):
                                cloud_cover_limit = 25
                                logger.info(f"[TOOL] FALLBACK: Detected low cloud keywords in query, applying {cloud_cover_limit}% filter")
                        
                        logger.info(f"[SEARCH] DEBUG: Final cloud_cover_limit = {cloud_cover_limit}")
                        
                        # Get collection ID for property name lookup
                        collections = stac_query.get("collections", [])
                        primary_collection = collections[0] if collections else None
                        
                        # Apply client-side cloud cover filtering with PROGRESSIVE RELAXATION
                        # If strict threshold returns 0, progressively relax to give users SOME results
                        cloud_relaxation_applied = None
                        if cloud_cover_limit is not None:
                            original_cloud_limit = cloud_cover_limit
                            relaxation_thresholds = [cloud_cover_limit, 50, 75, 100]  # Progressive relaxation
                            
                            for threshold in relaxation_thresholds:
                                cloud_filtered_results = translator._filter_stac_results_by_cloud_cover(
                                    {"features": spatially_filtered_features},
                                    max_cloud_cover=threshold,
                                    collection_id=primary_collection
                                )
                                filtered_features = cloud_filtered_results.get("features", [])
                                
                                if filtered_features or threshold == 100:
                                    spatially_filtered_features = filtered_features
                                    search_diagnostics["cloud_filtered_count"] = len(filtered_features)
                                    
                                    if threshold > original_cloud_limit:
                                        cloud_relaxation_applied = threshold
                                        logger.info(f"[CLOUD] Cloud filter relaxed: {original_cloud_limit}% -> {threshold}% (found {len(filtered_features)} tiles)")
                                        search_diagnostics["cloud_relaxation"] = f"{original_cloud_limit}% -> {threshold}%"
                                    else:
                                        logger.info(f"[CLOUD] After cloud cover filtering (≤{threshold}%): {len(filtered_features)} features kept")
                                    break
                        
                        # [TARGET] TILE SELECTION: Use STAC API ordering (sorted by datetime desc)
                        # When no datetime is specified, STAC API returns results sorted by most recent first
                        # This is more efficient than GPT-5 selection and respects user's implicit "latest" intent
                        logger.info(f"[LIST] Using STAC API ordering (results already sorted by datetime desc)")
                        
                        # Use all spatially filtered features (already ordered by recency from STAC API)
                        features = spatially_filtered_features
                        search_diagnostics["final_count"] = len(features)
                        search_diagnostics["tile_selection_method"] = "stac_api_ordering"
                        logger.info(f"[OK] Using {len(features)} tiles from STAC API (pre-sorted by datetime desc)")
                        
                        # Update stac_response with filtered results
                        stac_response["results"]["features"] = features
                    else:
                        features = raw_features
                        search_diagnostics["spatial_filtered_count"] = len(raw_features)
                        search_diagnostics["final_count"] = len(features)
                        logger.info("[WARN] Skipping spatial filtering and tile ranking (no translator or bbox)")
                    
                    # Determine failure stage if no results
                    if search_diagnostics["final_count"] == 0:
                        if search_diagnostics["raw_count"] == 0:
                            search_diagnostics["failure_stage"] = "stac_api"
                        elif search_diagnostics["spatial_filtered_count"] == 0:
                            search_diagnostics["failure_stage"] = "spatial_filter"
                        else:
                            search_diagnostics["failure_stage"] = "tile_selection"
                        
                        # [NEW] TRY ALTERNATIVE QUERIES: Automatically find available alternatives
                        logger.info("[SYNC] No results found - attempting to find alternatives with relaxed filters...")
                        logger.info(f"[SYNC] STAC query datetime: {stac_query.get('datetime')}, collections: {stac_query.get('collections')}, bbox: {stac_query.get('bbox')}")
                        try:
                            alternative_result = await try_alternative_queries(
                                natural_query,
                                stac_query,
                                stac_params,
                                translator,
                                stac_endpoint,
                                requested_bbox
                            )
                            logger.info(f"[SYNC] Alternative result: success={alternative_result.get('success')}, features={len(alternative_result.get('features', []))}")
                        except Exception as alt_ex:
                            logger.error(f"[SYNC] EXCEPTION in try_alternative_queries: {type(alt_ex).__name__}: {alt_ex}")
                            import traceback
                            logger.error(f"[SYNC] Traceback: {traceback.format_exc()}")
                            alternative_result = {"success": False, "features": []}
                        
                        if alternative_result.get("success") and alternative_result.get("features"):
                            # Successfully found alternatives!
                            features = alternative_result["features"]
                            search_diagnostics["final_count"] = len(features)
                            search_diagnostics["alternative_used"] = True
                            search_diagnostics["relaxation_applied"] = alternative_result.get("relaxation_applied")
                            search_diagnostics["alternative_explanation"] = alternative_result.get("explanation")
                            search_diagnostics["original_filters"] = alternative_result.get("original_filters")
                            search_diagnostics["alternative_filters"] = alternative_result.get("alternative_filters")
                            
                            # Update stac_response with alternative features
                            stac_response["results"]["features"] = features
                            
                            logger.info(f"[OK] Found {len(features)} alternative results: {alternative_result.get('explanation')}")
                        else:
                            logger.info("[FAIL] No alternatives found - will generate empty result response")
                else:
                    logger.error(f"[FAIL] STAC search failed: {stac_response.get('error', 'Unknown error')}")
                    search_diagnostics["failure_stage"] = "stac_error"
                    
            except Exception as e:
                logger.error(f"[FAIL] STAC search execution error: {e}")
                stac_response = {"results": {"type": "FeatureCollection", "features": []}}
                search_diagnostics["failure_stage"] = "exception"
        
        # ========================================================================
        # PHASE 3.4: EXECUTE GEOINT ANALYSIS (Legacy - for backward compatibility)
        # ========================================================================
        geoint_results = None
        
        if stac_params and stac_params.get('geoint_processing') and GEOINT_AVAILABLE and geoint_executor and features:
            try:
                logger.info("[MICRO] Query requires GEOINT analysis - executing analytical processing...")
                logger.info(f"[CHART] GEOINT intent detected: {stac_params.get('analysis_intent', {})}")
                
                # Extract analysis parameters
                analysis_intent = stac_params.get('analysis_intent', {})
                analysis_type = analysis_intent.get('analysis_type', 'terrain_analysis')
                bbox = stac_query.get('bbox') if stac_query else None
                
                # Execute GEOINT analysis (downloads COG rasters and performs calculations)
                geoint_results = await geoint_executor.execute_analysis(
                    analysis_type=analysis_type,
                    stac_features=features,
                    bbox=bbox,
                    query=natural_query,
                    **analysis_intent.get('parameters', {})
                )
                
                if geoint_results and geoint_results.get('success'):
                    logger.info("[OK] GEOINT analysis completed successfully")
                    logger.info(f"[UP] Analysis results preview: {list(geoint_results.get('results', {}).keys())}")
                    
                    # Log key metrics for debugging
                    if analysis_type == 'terrain_analysis':
                        elevation_stats = geoint_results.get('results', {}).get('elevation_statistics', {})
                        if elevation_stats:
                            logger.info(f"[MTN] Elevation: min={elevation_stats.get('min_elevation'):.1f}m, "
                                      f"max={elevation_stats.get('max_elevation'):.1f}m, "
                                      f"mean={elevation_stats.get('mean_elevation'):.1f}m")
                            peak_loc = elevation_stats.get('peak_location', {})
                            if peak_loc:
                                logger.info(f"[PIN] Peak location: ({peak_loc.get('latitude'):.4f}, "
                                          f"{peak_loc.get('longitude'):.4f}) @ {peak_loc.get('elevation'):.1f}m")
                    
                    elif analysis_type == 'mobility_analysis':
                        mobility_zones = geoint_results.get('results', {}).get('mobility_zones', {})
                        if mobility_zones:
                            go_pct = mobility_zones.get('go_zones', {}).get('percentage', 0)
                            logger.info(f"[CAR] Mobility: {go_pct:.1f}% accessible terrain")
                else:
                    logger.warning(f"[WARN] GEOINT analysis completed but returned no results or failed")
                    
            except Exception as e:
                logger.error(f"[FAIL] GEOINT analysis execution failed: {str(e)}", exc_info=True)
                geoint_results = None
        elif stac_params and stac_params.get('geoint_processing'):
            logger.warning("[WARN] GEOINT processing requested but prerequisites not met:")
            logger.warning(f"   - GEOINT_AVAILABLE: {GEOINT_AVAILABLE}")
            logger.warning(f"   - geoint_executor: {geoint_executor is not None}")
            logger.warning(f"   - features: {len(features) if features else 0}")
        
        # PHASE 3: GENERATE RESPONSE MESSAGE
        # [SEARCH] DEBUG: Log state before response generation to diagnose "no matches" bug
        logger.info(f"[SEARCH] RESPONSE GENERATION DEBUG:")
        logger.info(f"   - features count: {len(features) if features else 0}")
        logger.info(f"   - stac_response features: {len(stac_response.get('results', {}).get('features', []))}")
        logger.info(f"   - SEMANTIC_KERNEL_AVAILABLE: {SEMANTIC_KERNEL_AVAILABLE}")
        logger.info(f"   - translator: {translator is not None}")
        logger.info(f"   - stac_query: {stac_query is not None}")
        
        # [TOOL] SAFETY NET: Ensure features variable is synchronized with stac_response
        # This fixes a bug where features could be empty but stac_response has data
        stac_response_features = stac_response.get('results', {}).get('features', [])
        if not features and stac_response_features:
            logger.warning(f"[WARN] MISMATCH DETECTED: features is empty but stac_response has {len(stac_response_features)} features!")
            logger.warning(f"   Synchronizing features from stac_response to prevent 'no matches' bug")
            features = stac_response_features
            search_diagnostics["final_count"] = len(features)
        
        if SEMANTIC_KERNEL_AVAILABLE and translator and features:
            try:
                logger.info("[NOTE] Generating contextual response message...")
                
                # ========================================================================
                # [LAUNCH] AWAIT PARALLEL VISION TASK (if hybrid query)
                # ========================================================================
                # If we started a vision task in parallel with STAC search,
                # now is the time to wait for it to complete before combining results
                # ========================================================================
                vision_result = None
                if 'vision_task' in locals() and vision_task is not None:
                    try:
                        logger.info("[WAIT] Awaiting parallel vision analysis to complete...")
                        vision_result = await vision_task
                        if vision_result and vision_result.get("analysis"):
                            early_contextual_response = vision_result["analysis"]
                            logger.info("[OK] Parallel vision analysis completed and ready for combination")
                        else:
                            logger.warning("[WARN] Vision task completed but no analysis returned")
                    except Exception as e:
                        logger.error(f"[FAIL] Parallel vision task failed: {e}")
                        early_contextual_response = None
                
                # Check if we're showing alternative results
                if search_diagnostics.get("alternative_used"):
                    # [NEW] Generate special message explaining what alternative was shown
                    logger.info("[INFO] Generating alternative result explanation...")
                    contextual_response = await translator.generate_alternative_result_response(
                        natural_query,
                        classification or {},
                        {"success": True, "results": {"features": features}},
                        search_diagnostics.get("original_filters", {}),
                        search_diagnostics.get("alternative_filters", {}),
                        search_diagnostics.get("alternative_explanation", ""),
                        geoint_results
                    )
                    response_message = contextual_response.get("message", f"Found {len(features)} alternative results.")
                else:
                    # Standard success response
                    contextual_response = await translator.generate_contextual_earth_science_response(
                        natural_query, classification or {}, {"success": True, "results": {"features": features}}, geoint_results
                    )
                    response_message = contextual_response.get("message", f"Found {len(features)} satellite data results for your query.")
                    
                    # If we have vision analysis from hybrid query, prepend it
                    if early_contextual_response:
                        logger.info("[SHUFFLE] Combining vision analysis with STAC data response")
                        response_message = f"""**Visual Analysis:**
{early_contextual_response}

---

**Data Results:**
{response_message}"""
                
                logger.info("[OK] Contextual response message generated successfully")
            except Exception as e:
                logger.error(f"[FAIL] Response generation failed: {e}")
                response_message = generate_fallback_response(natural_query, features, stac_query.get("collections", []) if stac_query else [])
        elif not features and stac_query and SEMANTIC_KERNEL_AVAILABLE and translator:
            # [NEW] ENHANCED: Use GPT to generate context-aware response for empty results
            # GPT analyzes the specific failure point and provides intelligent, actionable suggestions
            try:
                logger.info(f"[BOT] Generating GPT-powered empty result response (failure stage: {search_diagnostics.get('failure_stage')})")
                response_message = await translator.generate_empty_result_response(
                    natural_query, 
                    stac_query,
                    stac_query.get("collections", []), 
                    search_diagnostics
                )
                logger.info("[OK] GPT-generated empty result response created")
            except Exception as e:
                logger.error(f"[FAIL] GPT empty result generation failed, using rule-based fallback: {e}")
                # Fall back to rule-based response if GPT fails
                response_message = generate_contextual_empty_response(
                    natural_query, 
                    stac_query.get("collections", []), 
                    search_diagnostics
                )
        elif not features and stac_query:
            # Fallback: Use rule-based response if Semantic Kernel not available
            logger.info(f"ℹ️ No features found - using rule-based diagnostic response (failure stage: {search_diagnostics.get('failure_stage')})")
            response_message = generate_contextual_empty_response(
                natural_query, 
                stac_query.get("collections", []), 
                search_diagnostics
            )
        else:
            # Fallback for edge cases (no stac_query generated)
            logger.info("[WARN] No STAC query generated - using generic fallback")
            response_message = "I can help you find Earth science data, but I need more specific information about the location, time period, or type of imagery you're looking for."
        
        # [MAP] Generate optimized tile URLs for collections that need seamless multi-tile coverage
        # Multi-tile rendering is for: DEM, MODIS composites, global coverage collections
        # Single-tile rendering is for: Optical imagery (Sentinel-2, HLS, Landsat) where we want the BEST image
        all_tile_urls = []
        all_bboxes = []  # [OK] Collect all bboxes for union calculation
        mosaic_result = None  # [GLOBE] NEW: Mosaic tilejson result for seamless coverage
        collections = stac_query.get("collections", []) if stac_query else []
        collection_id = collections[0].lower() if collections else ""
        
        # [SEARCH] DEBUG: Log what collections are in the features vs what was requested
        if features:
            feature_collections = list(set(f.get("collection", "unknown") for f in features))
            logger.info(f"[SEARCH] COLLECTION DEBUG: Requested={collections}, Features contain={feature_collections}")
            if set(feature_collections) != set(collections):
                logger.warning(f"[WARN] MISMATCH: STAC returned different collections than requested!")
        
        # ========================================================================
        # [GLOBE] MOSAIC SERVICE: RE-ENABLED FOR OPTICAL IMAGERY
        # ========================================================================
        # Mosaic provides seamless tile coverage for high-resolution optical imagery.
        # Without mosaic, item-level tiles cause 404 errors when zooming outside
        # individual granule bounds (causing white/missing tiles).
        # 
        # Enabled for: sentinel-2-l2a, landsat collections, hls collections
        # These have large granule footprints where users often zoom to areas
        # that fall between granule coverage.
        # ========================================================================
        optical_collections_needing_mosaic = [
            "sentinel-2-l2a",
            "landsat-c2-l2", "landsat-8-c2-l2", "landsat-9-c2-l2",
            "hls", "hls2-l30", "hls2-s30"
        ]
        
        # Check if this query is for an optical collection that benefits from mosaic
        needs_mosaic = any(
            collection_id.startswith(oc) or collection_id == oc 
            for oc in optical_collections_needing_mosaic
        )
        
        if needs_mosaic and stac_query and stac_query.get("bbox"):
            logger.info(f"[GLOBE] MOSAIC: Enabling mosaic for optical collection {collection_id}")
            try:
                # Import the mosaic function
                from hybrid_rendering_system import get_mosaic_tilejson_url
                
                mosaic_result = await get_mosaic_tilejson_url(
                    collections=[collection_id],
                    bbox=stac_query.get("bbox"),
                    datetime_range=stac_query.get("datetime"),
                    query_filters={"eo:cloud_cover": {"lt": 30}} if "cloud" not in natural_query.lower() else None
                )
                
                if mosaic_result:
                    logger.info(f"[OK] MOSAIC: Successfully registered mosaic for {collection_id}")
                else:
                    logger.warning(f"[WARN] MOSAIC: Registration failed for {collection_id}, will use item tiles")
            except Exception as e:
                logger.warning(f"[WARN] MOSAIC: Error registering mosaic: {e}")
                mosaic_result = None
        else:
            mosaic_result = None
            if not needs_mosaic:
                logger.info(f"[MAP] MOSAIC: Skipping mosaic for {collection_id} (not an optical collection)")
        
        # [MAP] TILE RENDERING: Generate individual tile URLs as fallback or supplement
        # The STAC query already returns features that cover the query bbox
        # We generate tile URLs for all features (up to 20) to ensure full area coverage
        # [ART] OPTIMIZATION: Generate optimized URLs for all features
        if features and len(features) > 0:
            # Process up to 20 features for full bbox coverage
            top_features = features[:20]
            logger.info(f"[MAP] Generating tile URLs for {len(top_features)} features (of {len(features)} total) for {collection_id}")
            
            for feature in top_features:
                tilejson_asset = feature.get("assets", {}).get("tilejson", {})
                if tilejson_asset and "href" in tilejson_asset:
                    feature_bbox = feature.get("bbox")
                    
                    # [OK] VALIDATION: Skip features with invalid bbox (prevents Azure Maps null value errors)
                    if not feature_bbox or len(feature_bbox) != 4:
                        logger.warning(f"[WARN] Skipping feature {feature.get('id')} - invalid bbox: {feature_bbox}")
                        continue
                    
                    # [OK] VALIDATION: Ensure all bbox values are numbers (not None)
                    if any(v is None or not isinstance(v, (int, float)) for v in feature_bbox):
                        logger.warning(f"[WARN] Skipping feature {feature.get('id')} - bbox contains null values: {feature_bbox}")
                        continue
                    
                    collection_id = feature.get("collection", collections[0] if collections else "unknown")
                    
                    # [ART] Apply quality optimization to tilejson URL
                    original_url = tilejson_asset["href"]
                    
                    # [SHIELD] EXPRESSION-BASED COLLECTIONS: Keep original STAC tilejson URL
                    # Collections like alos-palsar-mosaic use expressions (HH;HV;HH/HV) with multiple
                    # rescale values. The STAC tilejson already has the correct rendering params.
                    # Modifying the URL would strip the multi-rescale values and break rendering.
                    expression_collections = ["alos-palsar-mosaic", "sentinel-1-grd", "sentinel-1-rtc"]
                    if collection_id in expression_collections and "expression=" in original_url:
                        logger.info(f"[SHIELD] Keeping original STAC tilejson for expression-based collection {collection_id}")
                        all_tile_urls.append({
                            "item_id": feature.get("id"),
                            "bbox": feature_bbox,
                            "tilejson_url": original_url
                        })
                        if feature_bbox and len(feature_bbox) == 4:
                            all_bboxes.append(feature_bbox)
                        continue
                    
                    # Build quality parameters for this collection
                    quality_params = build_tile_url_params(collection_id, natural_query)
                    
                    # Enhance the URL with quality parameters
                    if quality_params:
                        # Parse URL to replace/append quality parameters
                        if "?" in original_url:
                            base_url, existing_params = original_url.split("?", 1)
                            # Remove existing quality params to replace with optimized ones
                            # CRITICAL: Also remove "assets=" and "asset_bidx=" to prevent duplication and 404s
                            # CRITICAL: Also remove "nodata=" which causes gray/blurry Sentinel-2 images (treats 0 values as missing data)
                            # CRITICAL: Also remove "color_formula=" to prevent duplicate color_formula parameters
                            # CRITICAL: Also remove "expression=" and "asset_as_band=" to prevent conflicts with SAR single-asset rendering
                            param_list = [p for p in existing_params.split("&") 
                                         if not any(p.startswith(k) for k in ["assets=", "asset_bidx=", "colormap_name=", "rescale=", "resampling=", "bidx=", "format=", "nodata=", "color_formula=", "expression=", "asset_as_band="])]
                            # Rebuild URL with optimized quality params
                            if param_list:
                                optimized_url = f"{base_url}?{'&'.join(param_list)}&{quality_params}"
                            else:
                                optimized_url = f"{base_url}?{quality_params}"
                        else:
                            optimized_url = f"{original_url}?{quality_params}"
                        
                        logger.info(f"[ART] Optimized tile URL for {feature.get('id')}: {quality_params}")
                    else:
                        optimized_url = original_url
                        logger.info(f"[WARN] No quality params generated for {feature.get('id')}")
                    
                    all_tile_urls.append({
                        "item_id": feature.get("id"),
                        "bbox": feature_bbox,
                        "tilejson_url": optimized_url  # [+] Use optimized URL
                    })
                    
                    # [OK] Collect bbox for union calculation
                    if feature_bbox and len(feature_bbox) == 4:
                        all_bboxes.append(feature_bbox)
            
            # Calculate skipped features (features with invalid bbox)
            skipped_count = len(top_features) - len(all_tile_urls)
            
            if all_tile_urls:
                logger.info(f"[MAP] Generated {len(all_tile_urls)} tile URLs for bbox coverage (skipped {skipped_count} with invalid bbox)")
                
                # [SEARCH] PIPELINE LOG: Tile URLs Output
                log_pipeline_step(pipeline_session_id, "TILE_URLS", "OUTPUT", {
                    "tile_count": len(all_tile_urls),
                    "skipped_invalid_bbox": skipped_count,
                    "tile_ids": [t.get("item_id") for t in all_tile_urls[:5]],  # First 5 for brevity
                    "has_more": len(all_tile_urls) > 5
                })
                
                # [OK] Calculate union bbox covering ALL tiles
                if all_bboxes:
                    union_bbox = [
                        min(bbox[0] for bbox in all_bboxes),  # min lon (west)
                        min(bbox[1] for bbox in all_bboxes),  # min lat (south)
                        max(bbox[2] for bbox in all_bboxes),  # max lon (east)
                        max(bbox[3] for bbox in all_bboxes)   # max lat (north)
                    ]
                    logger.info(f"[MAP] Union bbox calculated: {union_bbox}")
                    logger.info(f"   Coverage: {union_bbox[2] - union_bbox[0]:.2f}° × {union_bbox[3] - union_bbox[1]:.2f}°")
                    
                    # [SEARCH] PIPELINE LOG: Union BBox
                    log_pipeline_step(pipeline_session_id, "UNION_BBOX", "OUTPUT", {
                        "bbox": union_bbox,
                        "width_deg": round(union_bbox[2] - union_bbox[0], 2),
                        "height_deg": round(union_bbox[3] - union_bbox[1], 2)
                    })
                    
                    # [OK] Update stac_params with union bbox for response metadata
                    if stac_params:
                        stac_params["bbox"] = union_bbox
                        logger.info(f"[OK] Updated stac_params bbox to union: {union_bbox}")

        
        # Clean up STAC results to remove problematic asset_bidx parameters
        cleaned_stac_results = clean_tilejson_urls(stac_response.get("results", {}))
        
        # Prepare final response
        complete_response = {
            "success": True,
            "response": response_message,
            "data": {
                "stac_results": cleaned_stac_results,
                "search_metadata": {
                    "total_items": len(features),
                    "collections_searched": stac_query.get("collections", []) if stac_query else [],
                    "spatial_extent": stac_query.get("bbox") if stac_query else None,
                    "temporal_range": stac_query.get("datetime") if stac_query else None,
                    "search_timestamp": datetime.utcnow().isoformat()
                },
                "query_classification": {
                    "intent_type": classification.get("intent_type") if classification else "unknown",
                    "needs_satellite_data": classification.get("needs_satellite_data") if classification else True,
                    "needs_contextual_info": classification.get("needs_contextual_info") if classification else False,
                    "confidence": classification.get("confidence") if classification else 0
                } if classification else None
            },
            "translation_metadata": {
                "original_query": natural_query,
                "translated_params": stac_params,
                "stac_query": stac_query,
                "translation_timestamp": datetime.utcnow().isoformat(),
                "all_tile_urls": all_tile_urls if all_tile_urls else None,  # [+] Individual tile URLs for multi-tile rendering
                # [GLOBE] NEW: Mosaic tilejson for seamless composited coverage
                "mosaic_tilejson": mosaic_result if mosaic_result else None
            },
            "debug": {
                "semantic_translator": {
                    "available": SEMANTIC_KERNEL_AVAILABLE,
                    "selected_collections": stac_query.get("collections", []) if stac_query else [],
                    "location_info": {
                        "bbox": stac_query.get("bbox") if stac_query else None,
                        "location_name": natural_query
                    },
                    "query_processing": {
                        "original_query": natural_query,
                        "stac_parameters": stac_params,
                        "processing_timestamp": datetime.utcnow().isoformat()
                    }
                },
                # [MICRO] INSTANT PIPELINE TRACE - Visible in browser console!
                "pipeline_trace": {
                    "session_id": pipeline_session_id,
                    "steps": get_pipeline_trace(pipeline_session_id)
                }
            }
        }
        
        # [MICRO] TRACE: Final response summary
        log_pipeline_step(pipeline_session_id, "RESPONSE", "OUTPUT", {
            "success": True,
            "total_tiles": len(all_tile_urls) if all_tile_urls else 0,
            "total_features": len(features),
            "has_mosaic": mosaic_result is not None,
            "collections": stac_query.get("collections", []) if stac_query else []
        })
        
        logger.info("[OK] Unified query processing completed successfully")
        
        # ========================================================================
        # �️ UPDATE SESSION CONTEXT: Mark map as rendered for follow-up queries
        # ========================================================================
        # CRITICAL: This enables the router to default to VISION for follow-up questions
        # like "What city is on the map?" instead of trying another STAC search
        # ========================================================================
        if router_agent and session_id and (all_tile_urls or mosaic_result or features):
            # Prepare STAC items for vision agent (lightweight version with key fields)
            stac_items_for_vision = []
            for f in (features or [])[:10]:  # Limit to 10 items to keep context manageable
                stac_items_for_vision.append({
                    "id": f.get("id"),
                    "collection": f.get("collection"),
                    "bbox": f.get("bbox"),
                    "properties": {
                        "datetime": f.get("properties", {}).get("datetime"),
                        "eo:cloud_cover": f.get("properties", {}).get("eo:cloud_cover"),
                        "cloud_cover": f.get("properties", {}).get("cloud_cover"),
                    },
                    # IMPORTANT: Preserve asset 'type' and 'href' for COG sampling
                    "assets": {k: {"href": v.get("href"), "type": v.get("type")} for k, v in (f.get("assets") or {}).items()}
                })
            
            stac_render_context = {
                "has_rendered_map": True,  # Map now has rendered imagery
                "last_bbox": stac_query.get("bbox") if stac_query else None,
                "last_location": stac_params.get("location_name") if stac_params else None,
                "last_collections": stac_query.get("collections", []) if stac_query else [],
                "last_stac_items": stac_items_for_vision,  # STAC items for vision agent raster analysis
                "query_count": router_agent.tools.session_contexts.get(session_id, {}).get("query_count", 0) + 1
            }
            router_agent.update_session_context(session_id, stac_render_context)
            logger.info(f"[MAP] Updated session context: has_rendered_map=True, collections={stac_render_context['last_collections']}, stac_items={len(stac_items_for_vision)}")
        
        
        return complete_response
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"[FAIL] Unified query processor error: {str(e)}")
        logger.error(traceback.format_exc())
        raise HTTPException(status_code=500, detail=f"Query processing failed: {str(e)}")

@app.post("/api/stac-search")
async def stac_search(request: Request):
    """Direct STAC search endpoint for backwards compatibility (ported from Router Function App)"""
    try:
        logger.info("[SEARCH] Direct STAC search endpoint called")
        
        req_body = await request.json()
        if not req_body:
            raise HTTPException(
                status_code=400,
                detail="Request body required"
            )
        
        # Execute STAC search
        stac_response = await execute_direct_stac_search(req_body)
        
        # Clean tilejson URLs in the response
        if stac_response.get("success") and "results" in stac_response:
            stac_response["results"] = clean_tilejson_urls(stac_response["results"])
        
        return JSONResponse(
            content=stac_response,
            status_code=200 if stac_response.get("success") else 500
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"STAC search endpoint error: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"STAC search failed: {str(e)}"
        )

@app.post("/api/veda-search")
async def veda_search(request: Request):
    """Direct VEDA STAC search endpoint for NASA Earth data (ported from Router Function App)"""
    try:
        logger.info("[SAT] VEDA STAC search endpoint called")
        
        req_body = await request.json()
        if not req_body:
            raise HTTPException(
                status_code=400,
                detail="Request body required"
            )
        
        # Execute VEDA STAC search
        stac_response = await execute_direct_stac_search(req_body, stac_endpoint="veda")
        
        # Clean tilejson URLs in the response
        if stac_response.get("success") and "results" in stac_response:
            stac_response["results"] = clean_tilejson_urls(stac_response["results"])
        
        return JSONResponse(
            content=stac_response,
            status_code=200 if stac_response.get("success") else 500
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"VEDA search endpoint error: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"VEDA search failed: {str(e)}"
        )

@app.post("/api/structured-search")
async def structured_search(request: Request):
    """
    Structured STAC search using explicit parameters (collection, location, datetime)
    Leverages the same agents as natural language queries for consistency
    """
    try:
        logger.info("[TOOL] Structured search endpoint called")
        logger.info("="*100)
        logger.info("[TOOL][TOOL][TOOL] POST /api/structured-search ENDPOINT HIT [TOOL][TOOL][TOOL]")
        logger.info("="*100)
        
        req_body = await request.json()
        if not req_body:
            raise HTTPException(status_code=400, detail="Request body required")
        
        collection = req_body.get('collection')
        location = req_body.get('location')
        datetime_single = req_body.get('datetime')
        datetime_start = req_body.get('datetime_start')
        datetime_end = req_body.get('datetime_end')
        
        logger.info(f"[PKG] Structured search params:")
        logger.info(f"   Collection: {collection}")
        logger.info(f"   Location: {location}")
        logger.info(f"   Datetime (single): {datetime_single}")
        logger.info(f"   Datetime range: {datetime_start} to {datetime_end}")
        
        if not collection or not location:
            raise HTTPException(
                status_code=400,
                detail="Both 'collection' and 'location' parameters are required"
            )
        
        # Ensure semantic translator is initialized
        if not global_translator:
            logger.error("[FAIL] Semantic translator not initialized")
            raise HTTPException(
                status_code=500,
                detail="Semantic translator not initialized. Please try again."
            )
        
        # ========================================================================
        # [BOT] USE FULL MULTI-AGENT PIPELINE FOR STRUCTURED SEARCH
        # ========================================================================
        # Build a natural language query from structured parameters to leverage
        # the full agent pipeline (collection validation, datetime parsing, 
        # spatial coverage, rendering config, etc.)
        # ========================================================================
        
        logger.info("[BOT] Converting structured parameters to natural language for agent pipeline")
        
        # Build natural language query
        nl_parts = []
        if collection:
            nl_parts.append(f"{collection} data")
        if location:
            nl_parts.append(f"for {location}")
        if datetime_start and datetime_end:
            nl_parts.append(f"from {datetime_start} to {datetime_end}")
        elif datetime_single:
            nl_parts.append(f"on {datetime_single}")
        
        natural_query = " ".join(nl_parts)
        logger.info(f"[NOTE] Constructed natural language query: '{natural_query}'")
        
        # Use the semantic translator's translate_query method (FULL AGENT PIPELINE)
        logger.info("[SYNC] Running full multi-agent translation pipeline...")
        stac_params = await global_translator.translate_query(natural_query, pin_location=None)
        
        # Check if translation was successful
        if not stac_params or not stac_params.get('collections'):
            logger.error(f"[FAIL] Agent pipeline failed to produce valid STAC parameters")
            raise HTTPException(
                status_code=500,
                detail=f"Could not translate parameters to STAC query. Collection '{collection}' may not exist or location '{location}' could not be resolved."
            )
        
        # Build STAC query from agent-validated parameters
        stac_query = build_stac_query(stac_params)
        logger.info(f"� Agent-validated STAC Query: {json.dumps(stac_query, indent=2)}")
        
        # Get location info for response
        location_name = stac_params.get('location_name', location)
        bbox = stac_query.get('bbox')
        datetime_param = stac_query.get('datetime')
        
        # Execute STAC search with agent-optimized parameters
        stac_response = await execute_direct_stac_search(stac_query)
        
        if not stac_response.get("success"):
            return JSONResponse(
                content={
                    "success": False,
                    "response": f"No data found for {collection} in {location_name}",
                    "user_response": f"No data found for {collection} in {location_name}. Try adjusting the date range or location.",
                    "data": stac_response
                },
                status_code=200
            )
        
        # Clean tilejson URLs
        if "results" in stac_response:
            stac_response["results"] = clean_tilejson_urls(stac_response["results"])
        
        # Build response similar to /api/query format
        num_items = len(stac_response.get("results", {}).get("features", []))
        response_text = f"Found {num_items} {collection} items for {location_name}"
        if datetime_param:
            response_text += f" ({datetime_start or datetime_single}"
            if datetime_end:
                response_text += f" to {datetime_end}"
            response_text += ")"
        
        logger.info(f"[OK] Structured search complete: {num_items} items found")
        
        return JSONResponse(
            content={
                "success": True,
                "response": response_text,
                "user_response": response_text,
                "data": {
                    "stac_results": stac_response.get("results", {}),
                    "search_metadata": {
                        "total_items": num_items,
                        "collections_searched": [collection],
                        "spatial_extent": bbox,
                        "temporal_range": datetime_param,
                        "location_name": location_name,
                        "search_timestamp": datetime.utcnow().isoformat()
                    },
                    "query_classification": {
                        "intent_type": "stac",
                        "needs_satellite_data": True,
                        "confidence": 1.0
                    }
                },
                "translation_metadata": {
                    "original_query": f"{collection} for {location}",
                    "translated_params": stac_query,
                    "stac_query": stac_query,
                    "translation_method": "structured_input"
                }
            },
            status_code=200
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Structured search error: {e}")
        logger.error(traceback.format_exc())
        raise HTTPException(
            status_code=500,
            detail=f"Structured search failed: {str(e)}"
        )

@app.post("/api/session-reset")
async def session_reset(request: Request):
    """Reset/clear conversation context for session restart (ported from Router Function App)"""
    try:
        # Parse request body
        try:
            request_data = await request.json()
            conversation_id = request_data.get("session_id") or request_data.get("conversation_id")
        except:
            # Try query parameters if JSON parsing fails
            conversation_id = request.query_params.get("session_id") or request.query_params.get("conversation_id")
        
        if not conversation_id:
            raise HTTPException(
                status_code=400,
                detail="Missing session_id or conversation_id. Please provide a session_id to reset."
            )
        
        # Reset conversation context if translator is available
        if SEMANTIC_KERNEL_AVAILABLE and global_translator:
            global_translator.reset_conversation_context(conversation_id)
            message = f"Session {conversation_id} reset successfully"
        else:
            message = f"Session reset requested for {conversation_id} (semantic translator not available)"
        
        logger.info(f"[SYNC] {message}")
        
        return {
            "status": "success",
            "message": message,
            "session_id": conversation_id,
            "timestamp": datetime.utcnow().isoformat()
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"[FAIL] Session reset failed: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Session reset failed: {str(e)}"
        )

@app.post("/api/process-comparison-query")
async def process_comparison_query(request: Request):
    """
    Process natural language comparison query to extract parameters.
    
    REUSES EXISTING AGENTS:
    - Collection selection: collection_mapping_agent (same as regular queries)
    - Location resolution: build_stac_query_agent -> bbox extraction (same as regular queries)
    - Datetime extraction: datetime_translation_agent in "comparison" mode (NEW dual-date support)
    
    Request body:
    {
        "query": "Show wildfire activity in Southern California January 2025 over 48 hours"
    }
    
    Returns:
    {
        "location": {"lat": 34.05, "lng": -118.24},
        "aspect": "wildfire activity",
        "before_date": "2025-01-15T00:00:00Z",
        "after_date": "2025-01-17T00:00:00Z",
        "collections": ["modis-14A1-061", "sentinel-2-l2a"],
        "primary_collection": "modis-14A1-061",
        "explanation": "Analyzing wildfire progression over 48-hour period"
    }
    """
    try:
        data = await request.json()
        user_query = data.get("query", "")
        
        if not user_query:
            raise HTTPException(status_code=400, detail="Query is required")
        
        logger.info(f"[CHART] [COMPARISON] query='{user_query}'")
        
        global semantic_translator
        if not semantic_translator:
            raise HTTPException(status_code=500, detail="Semantic translator not initialized")
        
        # Step 1: Collection Selection
        collections = await semantic_translator.collection_mapping_agent(user_query)
        logger.info(f"[CHART] [COMPARISON] Step 1 collections={collections}")
        
        if not collections:
            logger.warning("[CHART] [COMPARISON] No collections returned")
        
        # Step 2: Location Resolution
        stac_query = await semantic_translator.build_stac_query_agent(user_query, collections)
        bbox = stac_query.get("bbox")
        location_name = stac_query.get("location_name", "Unknown location")
        
        if not bbox:
            logger.error(f"[CHART] [COMPARISON] No bbox returned: {stac_query}")
            raise HTTPException(status_code=400, detail=f"Could not resolve location from query: '{user_query}'")
        
        lng = (bbox[0] + bbox[2]) / 2
        lat = (bbox[1] + bbox[3]) / 2
        logger.info(f"[CHART] [COMPARISON] Step 2 location={location_name} ({lat:.4f},{lng:.4f})")
        
        # Step 3: Dual-Date Extraction
        datetime_result = await semantic_translator.datetime_translation_agent(
            query=user_query,
            collections=collections,
            mode="comparison"
        )
        
        if not datetime_result:
            raise HTTPException(status_code=400, detail="Could not extract timeframes from query. Please specify time periods (e.g., 'between 2023 and 2024').")
        
        if "before" not in datetime_result or "after" not in datetime_result:
            logger.error(f"[CHART] [COMPARISON] Missing before/after in datetime result: {datetime_result}")
            raise HTTPException(status_code=400, detail="Could not extract before/after timeframes from query. Please specify time periods (e.g., 'between 2023 and 2024').")
        
        before_date = datetime_result["before"]
        after_date = datetime_result["after"]
        explanation = datetime_result.get("explanation", "")
        logger.info(f"[CHART] [COMPARISON] Step 3 before={before_date} after={after_date}")
        
        # Step 4: Primary Collection Selection
        primary_collection = None
        aspect = "general change"
        
        if collections:
            priority_map = {
                "modis-14A1-061": "wildfire activity",
                "cop-dem-glo-30": "terrain/elevation",
                "cop-dem-glo-90": "terrain/elevation",
                "alos-dem": "terrain/elevation",
                "sentinel-2-l2a": "optical imagery",
                "landsat-c2-l2": "optical imagery"
            }
            
            for priority_collection, priority_aspect in priority_map.items():
                if priority_collection in collections:
                    primary_collection = priority_collection
                    aspect = priority_aspect
                    break
            
            if not primary_collection and collections:
                primary_collection = collections[0]
                aspect = "general change"
        
        logger.info(f"[CHART] [COMPARISON] Step 4 primary={primary_collection} aspect={aspect}")
        
        result = {
            "status": "success",
            "location": {"lat": lat, "lng": lng},
            "location_name": location_name,
            "bbox": bbox,
            "aspect": aspect,
            "before_date": before_date,
            "after_date": after_date,
            "collections": collections,
            "primary_collection": primary_collection,
            "explanation": explanation,
            "timestamp": datetime.now().isoformat()
        }
        
        logger.info(f"[CHART] [COMPARISON] [OK] Done — {location_name}, {primary_collection}, {before_date}->{after_date}")
        return result
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"[CHART] [COMPARISON] [FAIL] {type(e).__name__}: {e}")
        error_detail = str(e) if str(e) else f"{type(e).__name__} exception occurred"
        raise HTTPException(
            status_code=500,
            detail=f"Failed to process comparison query: {error_detail}"
        )

@app.post("/api/geoint/mobility")
async def geoint_mobility_analysis(request: Request):
    """
    GEOINT Mobility Analysis Endpoint
    
    Thin wrapper around mobility_analysis_agent.
    Called when user drops pin with GEOINT toggle enabled.
    Supports two-point A->B traversability analysis.
    
    Request body:
    {
        "latitude": float,       # Point A latitude (start)
        "longitude": float,      # Point A longitude (start)
        "latitude_b": float,     # Point B latitude (destination, optional)
        "longitude_b": float,    # Point B longitude (destination, optional)
        "screenshot": str (optional - base64 screenshot),
        "user_query": str (optional - user context),
        "user_context": str (optional - legacy field name)
    }
    """
    try:
        logger.info("[MEDAL] GEOINT Mobility endpoint called")
        
        # Parse request body
        request_data = await request.json()
        latitude = request_data.get("latitude")
        longitude = request_data.get("longitude")
        latitude_b = request_data.get("latitude_b")
        longitude_b = request_data.get("longitude_b")
        screenshot_base64 = request_data.get("screenshot")
        user_query = request_data.get("user_query") or request_data.get("user_context")
        
        # Validate required parameters
        if latitude is None or longitude is None:
            raise HTTPException(
                status_code=400,
                detail="Missing required parameters: latitude and longitude"
            )
        
        # Validate coordinate ranges
        if not (-90 <= latitude <= 90):
            raise HTTPException(
                status_code=400,
                detail=f"Invalid latitude: {latitude}. Must be between -90 and 90."
            )
        
        if not (-180 <= longitude <= 180):
            raise HTTPException(
                status_code=400,
                detail=f"Invalid longitude: {longitude}. Must be between -180 and 180."
            )
        
        logger.info(f"Validated coordinates: ({latitude}, {longitude})")
        if latitude_b is not None and longitude_b is not None:
            if not (-90 <= latitude_b <= 90):
                raise HTTPException(status_code=400, detail=f"Invalid latitude_b: {latitude_b}. Must be between -90 and 90.")
            if not (-180 <= longitude_b <= 180):
                raise HTTPException(status_code=400, detail=f"Invalid longitude_b: {longitude_b}. Must be between -180 and 180.")
            logger.info(f"Point B coordinates: ({latitude_b}, {longitude_b})")
        
        # Call mobility_analysis_agent (new agent-based architecture)
        from geoint.agents import mobility_analysis_agent
        
        analysis_result = await mobility_analysis_agent(
            latitude=latitude,
            longitude=longitude,
            screenshot_base64=screenshot_base64,
            user_query=user_query,
            include_vision=True,
            latitude_b=latitude_b,
            longitude_b=longitude_b
        )
        
        logger.info(f"Mobility agent completed")
        
        return {
            "status": "success",
            "result": analysis_result,
            "timestamp": datetime.utcnow().isoformat()
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"[FAIL] GEOINT Mobility Analysis failed: {e}")
        logger.error(traceback.format_exc())
        raise HTTPException(
            status_code=500,
            detail=f"GEOINT mobility analysis failed: {str(e)}"
        )

# ============================================================================
# [BRAIN] GEOINT MODULE-SPECIFIC ENDPOINTS
# ============================================================================
# Each GEOINT module has a dedicated endpoint for clear separation of concerns

# Pydantic models for GEOINT requests
@app.post("/api/geoint/terrain")
async def geoint_terrain_analysis(request: Request):
    """
    GEOINT Terrain Analysis - Unified endpoint for initial analysis AND follow-ups
    
    This endpoint now supports:
    1. Initial terrain analysis (no session_id) - One-shot analysis using terrain_analysis_agent
    2. Follow-up questions (with session_id) - Uses TerrainAgent with conversation memory
    
    Request body:
    {
        "latitude": float,
        "longitude": float,
        "screenshot": str (optional - base64 screenshot),
        "user_query": str (optional - user context),
        "user_context": str (optional - legacy field name),
        "radius_miles": float (optional - defaults to 5.0),
        "session_id": str (optional - provide for follow-up questions to maintain context)
    }
    
    Response includes session_id that can be used for follow-up questions.
    """
    import uuid
    request_id = f"terrain-{datetime.utcnow().timestamp()}"
    try:
        logger.info(f"[MTN] [{request_id}] ============================================================")
        logger.info(f"[MTN] [{request_id}] TERRAIN ENDPOINT CALLED")
        logger.info(f"[MTN] [{request_id}] ============================================================")
        logger.info(f"[MTN] [{request_id}] Request method: {request.method}")
        logger.info(f"[MTN] [{request_id}] Request URL: {request.url}")
        logger.info(f"[MTN] [{request_id}] Client: {request.client}")
        
        # Parse request body
        logger.info(f"[MTN] [{request_id}] Parsing request body...")
        request_data = await request.json()
        logger.info(f"[MTN] [{request_id}] [OK] Request body parsed successfully")
        logger.info(f"[MTN] [{request_id}] Request keys: {list(request_data.keys())}")
        
        latitude = request_data.get("latitude")
        longitude = request_data.get("longitude")
        screenshot = request_data.get("screenshot")
        user_query = request_data.get("user_query") or request_data.get("user_context")
        radius_miles = request_data.get("radius_miles", 5.0)
        session_id = request_data.get("session_id")  # NEW: For follow-up questions
        
        screenshot_size = len(screenshot) if screenshot else 0
        logger.info(f"[MTN] [{request_id}] Screenshot size: {screenshot_size} chars ({screenshot_size / 1024:.1f} KB)")
        logger.info(f"[MTN] [{request_id}] Session ID: {session_id or 'NEW SESSION'}")
        
        # ===== CRITICAL DEBUG: Screenshot validation =====
        if screenshot:
            logger.info(f"[MTN] [{request_id}] Screenshot received: YES")
            logger.info(f"[MTN] [{request_id}] Screenshot starts with: {screenshot[:50]}")
            
            # Check if it has data URL prefix (should be removed by frontend)
            if screenshot.startswith('data:image'):
                logger.warning(f"[MTN] [{request_id}] [WARN] Screenshot has data URL prefix (will be handled)")
            else:
                logger.info(f"[MTN] [{request_id}] Screenshot is pure base64 (correct format)")
                
            # Validate minimum size (empty canvas produces very small PNGs)
            if screenshot_size < 5000:
                logger.warning(f"[MTN] [{request_id}] [WARN] Screenshot is very small ({screenshot_size} chars) - may be blank canvas!")
            else:
                logger.info(f"[MTN] [{request_id}] Screenshot size looks good (>{screenshot_size / 1024:.1f}KB)")
        else:
            logger.warning(f"[MTN] [{request_id}] [WARN] NO SCREENSHOT PROVIDED - will use STAC fallback")
        # ===== END CRITICAL DEBUG =====
        
        # Validate required parameters
        logger.info(f"[MTN] [{request_id}] Validating parameters...")
        if latitude is None or longitude is None:
            logger.error(f"[MTN] [{request_id}] [FAIL] Missing required parameters")
            raise HTTPException(status_code=400, detail="latitude and longitude are required")
        
        # Validate coordinates
        if not (-90 <= latitude <= 90):
            logger.error(f"[MTN] [{request_id}] [FAIL] Invalid latitude: {latitude}")
            raise HTTPException(status_code=400, detail=f"Invalid latitude: {latitude}")
        if not (-180 <= longitude <= 180):
            logger.error(f"[MTN] [{request_id}] [FAIL] Invalid longitude: {longitude}")
            raise HTTPException(status_code=400, detail=f"Invalid longitude: {longitude}")
        
        logger.info(f"[MTN] [{request_id}] [OK] Parameters valid")
        logger.info(f"[MTN] [{request_id}] Coordinates: ({latitude}, {longitude})")
        logger.info(f"[MTN] [{request_id}] Radius: {radius_miles} miles")
        logger.info(f"[MTN] [{request_id}] User query: {user_query}")
        
        import time
        agent_start = time.time()
        
        # ========================================================================
        # DECISION: Use TerrainAgent (with memory) if session_id provided OR user_query exists
        # Otherwise use one-shot terrain_analysis_agent for initial analysis
        # ========================================================================
        
        import asyncio
        radius_km = radius_miles * 1.609
        
        if not session_id:
            session_id = str(uuid.uuid4())
            logger.info(f"[MTN] [{request_id}] Created new session: {session_id}")
        
        message = user_query or "Provide a comprehensive terrain analysis of this location including elevation, slope, and terrain classification."
        
        # Try Agent Service first, fall back to direct tools if PE-blocked
        agent_result = None
        try:
            if user_query or session_id:
                logger.info(f"[MTN] [{request_id}] USING TERRAIN AGENT (with memory and tools)")
                from geoint.terrain_agent import get_terrain_agent
                agent = get_terrain_agent()
                agent_result = await asyncio.wait_for(
                    agent.chat(
                        session_id=session_id,
                        user_message=message,
                        latitude=latitude,
                        longitude=longitude,
                        screenshot_base64=screenshot,
                        radius_km=radius_km
                    ),
                    timeout=240.0
                )
            else:
                logger.info(f"[MTN] [{request_id}] USING LEGACY ONE-SHOT AGENT (no memory)")
                from geoint.agents import terrain_analysis_agent
                agent_result = await asyncio.wait_for(
                    terrain_analysis_agent(
                        latitude=latitude,
                        longitude=longitude,
                        screenshot_base64=screenshot,
                        user_query=user_query,
                        radius_miles=radius_miles
                    ),
                    timeout=240.0
                )
            
            # Check if response contains PE error
            resp_text = str(agent_result.get("response", ""))
            if "403" in resp_text or "Public access is disabled" in resp_text or "private endpoint" in resp_text.lower():
                logger.warning(f"[MTN] [{request_id}] Agent returned PE error, falling back to direct tools")
                agent_result = None
        except asyncio.TimeoutError:
            agent_elapsed = time.time() - agent_start
            logger.error(f"[MTN] [{request_id}] [FAIL] AGENT TIMEOUT after {agent_elapsed:.1f}s")
            raise HTTPException(status_code=504, detail=f"Terrain analysis timed out after {agent_elapsed:.1f}s. Please try again.")
        except Exception as agent_err:
            logger.warning(f"[MTN] [{request_id}] Agent failed ({agent_err}), falling back to direct tools")
            agent_result = None
        
        # ── FALLBACK: Direct tool calls when Agent Service is blocked by PE ──
        if agent_result is None:
            logger.info(f"[MTN] [{request_id}] Using direct terrain tool fallback (PE lockdown)")
            from geoint.terrain_tools import get_elevation_analysis, get_slope_analysis, find_flat_areas, analyze_flood_risk, analyze_environmental_sensitivity
            from openai import AsyncAzureOpenAI
            from azure.identity import DefaultAzureCredential, get_bearer_token_provider as _gbt
            _aoai_endpoint = os.getenv("AZURE_AI_PROJECT_ENDPOINT") or os.getenv("AZURE_OPENAI_ENDPOINT")
            if not _aoai_endpoint:
                raise ValueError("AZURE_AI_PROJECT_ENDPOINT or AZURE_OPENAI_ENDPOINT environment variable is required")
            _terrain_client = AsyncAzureOpenAI(
                azure_endpoint=_aoai_endpoint,
                api_key=os.environ.get("AZURE_OPENAI_API_KEY"),
                azure_ad_token_provider=_gbt(
                    DefaultAzureCredential(), "https://cognitiveservices.azure.com/.default"
                ) if not os.environ.get("AZURE_OPENAI_API_KEY") else None,
                api_version="2024-12-01-preview",
            )
            
            tool_results = {}
            tool_calls_made = []
            
            try:
                tool_results["elevation"] = get_elevation_analysis(latitude, longitude, radius_km)
                tool_calls_made.append("get_elevation_analysis")
            except Exception as te:
                logger.warning(f"[MTN] [{request_id}] Elevation tool failed: {te}")
            
            try:
                tool_results["slope"] = get_slope_analysis(latitude, longitude, radius_km)
                tool_calls_made.append("get_slope_analysis")
            except Exception as te:
                logger.warning(f"[MTN] [{request_id}] Slope tool failed: {te}")
            
            try:
                tool_results["flat_areas"] = find_flat_areas(latitude, longitude, radius_km)
                tool_calls_made.append("find_flat_areas")
            except Exception as te:
                logger.warning(f"[MTN] [{request_id}] Flat areas tool failed: {te}")
            
            try:
                tool_results["flood_risk"] = analyze_flood_risk(latitude, longitude, radius_km)
                tool_calls_made.append("analyze_flood_risk")
            except Exception as te:
                logger.warning(f"[MTN] [{request_id}] Flood risk tool failed: {te}")
            
            try:
                tool_results["environment"] = analyze_environmental_sensitivity(latitude, longitude, radius_km)
                tool_calls_made.append("analyze_environmental_sensitivity")
            except Exception as te:
                logger.warning(f"[MTN] [{request_id}] Environment tool failed: {te}")
            
            # Synthesize with _terrain_client
            tool_summary = "\n\n".join([f"### {k.replace('_', ' ').title()}\n{v}" for k, v in tool_results.items() if v])
            
            visual_analysis = ""
            if screenshot:
                try:
                    clean_b64 = screenshot
                    if clean_b64.startswith('data:image'):
                        clean_b64 = clean_b64.split(',', 1)[1]
                    vision_resp = await _terrain_client.chat.completions.create(
                        model=os.getenv("AZURE_OPENAI_DEPLOYMENT_NAME", "gpt-5"),
                        messages=[
                            {"role": "system", "content": "You are an expert terrain analyst. Analyze satellite imagery for terrain features."},
                            {"role": "user", "content": [
                                {"type": "text", "text": f"Analyze this satellite image at ({latitude:.4f}, {longitude:.4f}). "
                                 f"Identify terrain features: elevation changes, slopes, water bodies, vegetation, flat areas. "
                                 f"{'User query: ' + user_query if user_query else ''}"},
                                {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{clean_b64}", "detail": "high"}}
                            ]}
                        ],
                        max_completion_tokens=2000,
                        temperature=1.0
                    )
                    visual_analysis = vision_resp.choices[0].message.content
                except Exception as vis_err:
                    logger.warning(f"[MTN] [{request_id}] Screenshot analysis failed: {vis_err}")
            
            # Use GPT to synthesize all tool results into a coherent response
            synthesis_parts = []
            if visual_analysis:
                synthesis_parts.append(f"## Visual Analysis\n\n{visual_analysis}")
            if tool_summary:
                synthesis_parts.append(f"## DEM & Tool Analysis\n\n{tool_summary}")
            
            combined = "\n\n".join(synthesis_parts) if synthesis_parts else "Terrain analysis completed. Limited data available for this location."
            
            agent_result = {
                "response": combined,
                "analysis": combined,
                "tool_calls": [{"tool": t} for t in tool_calls_made],
                "message_count": 1
            }
            logger.info(f"[MTN] [{request_id}] Direct terrain fallback completed ({len(tool_calls_made)} tools)")
        
        agent_elapsed = time.time() - agent_start
        logger.info(f"[MTN] [{request_id}] [OK] TERRAIN COMPLETED ({agent_elapsed:.2f}s)")
        
        return {
            "status": "success",
            "result": {
                "analysis": agent_result.get("response", "") or agent_result.get("analysis", ""),
                "tool_calls": agent_result.get("tool_calls", []),
                "message_count": agent_result.get("message_count", 1)
            },
            "session_id": session_id,
            "timestamp": datetime.utcnow().isoformat()
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"[MTN] [{request_id}] ============================================================")
        logger.error(f"[MTN] [{request_id}] [FAIL] TERRAIN ENDPOINT FAILED")
        logger.error(f"[MTN] [{request_id}] ============================================================")
        logger.error(f"[MTN] [{request_id}] Error: {e}")
        logger.error(f"[MTN] [{request_id}] Traceback:")
        logger.error(traceback.format_exc())
        raise HTTPException(
            status_code=500,
            detail=f"Terrain analysis failed: {str(e)}"
        )


@app.post("/api/geoint/terrain/chat")
async def geoint_terrain_chat(request: Request):
    """
    [BOT] GEOINT Terrain Agent Chat - Multi-turn conversation with memory
    
    A real AI agent that:
    - Remembers context from previous messages in the session
    - Calls terrain analysis tools (DEM, NDVI, slope, etc.) as needed
    - Synthesizes tool results into coherent answers
    
    Request body:
    {
        "session_id": str (optional - will create new session if not provided),
        "message": str (required - user's question),
        "latitude": float (required),
        "longitude": float (required),
        "screenshot": str (optional - base64 screenshot),
        "radius_km": float (optional - defaults to 5.0)
    }
    
    Returns:
    {
        "response": str (agent's answer),
        "tool_calls": list (tools the agent invoked),
        "session_id": str (use this for follow-up questions),
        "message_count": int (messages in this session)
    }
    """
    import uuid
    request_id = f"terrain-chat-{datetime.utcnow().timestamp()}"
    
    try:
        logger.info(f"[MSG] [{request_id}] ============================================================")
        logger.info(f"[MSG] [{request_id}] TERRAIN AGENT CHAT ENDPOINT")
        logger.info(f"[MSG] [{request_id}] ============================================================")
        
        request_data = await request.json()
        
        # Extract parameters
        session_id = request_data.get("session_id") or str(uuid.uuid4())
        message = request_data.get("message")
        latitude = request_data.get("latitude")
        longitude = request_data.get("longitude")
        screenshot = request_data.get("screenshot")
        radius_km = request_data.get("radius_km", 5.0)
        
        # Validate required parameters
        if not message:
            raise HTTPException(status_code=400, detail="message is required")
        if latitude is None or longitude is None:
            raise HTTPException(status_code=400, detail="latitude and longitude are required")
        if not (-90 <= latitude <= 90):
            raise HTTPException(status_code=400, detail=f"Invalid latitude: {latitude}. Must be between -90 and 90.")
        if not (-180 <= longitude <= 180):
            raise HTTPException(status_code=400, detail=f"Invalid longitude: {longitude}. Must be between -180 and 180.")
        
        logger.info(f"[MSG] [{request_id}] Session: {session_id}")
        logger.info(f"[MSG] [{request_id}] Message: {message[:100]}...")
        logger.info(f"[MSG] [{request_id}] Location: ({latitude}, {longitude})")
        logger.info(f"[MSG] [{request_id}] Screenshot: {'Yes (' + str(len(screenshot)) + ' chars)' if screenshot else 'No'}")
        if screenshot:
            logger.info(f"[MSG] [{request_id}] Screenshot starts with: {screenshot[:60]}...")
        
        # Try Agent Service first, fall back to direct tools if PE-blocked
        import time
        start_time = time.time()
        result = None
        
        try:
            from geoint.terrain_agent import get_terrain_agent
            agent = get_terrain_agent()
            result = await agent.chat(
                session_id=session_id,
                user_message=message,
                latitude=latitude,
                longitude=longitude,
                screenshot_base64=screenshot,
                radius_km=radius_km
            )
            resp_text = str(result.get("response", ""))
            if "403" in resp_text or "Public access is disabled" in resp_text or "private endpoint" in resp_text.lower():
                logger.warning(f"[MSG] [{request_id}] Agent returned PE error, falling back to direct tools")
                result = None
        except Exception as agent_err:
            logger.warning(f"[MSG] [{request_id}] Agent failed ({agent_err}), falling back to direct tools")
            result = None
        
        if result is None:
            logger.info(f"[MSG] [{request_id}] Using direct terrain tool fallback (PE lockdown)")
            from geoint.terrain_tools import get_elevation_analysis, get_slope_analysis, find_flat_areas, analyze_flood_risk
            
            tool_results = {}
            for name, fn in [("elevation", get_elevation_analysis), ("slope", get_slope_analysis),
                             ("flat_areas", find_flat_areas), ("flood_risk", analyze_flood_risk)]:
                try:
                    tool_results[name] = fn(latitude, longitude, radius_km)
                except Exception:
                    pass
            
            tool_summary = "\n\n".join([f"### {k.replace('_', ' ').title()}\n{v}" for k, v in tool_results.items() if v])
            
            # Synthesize with _terrain_client
            synthesis_prompt = f"User question: {message}\n\nTerrain data for ({latitude:.4f}, {longitude:.4f}):\n{tool_summary}"
            try:
                synth_resp = await _terrain_client.chat.completions.create(
                    model=os.getenv("AZURE_OPENAI_DEPLOYMENT_NAME", "gpt-5"),
                    messages=[
                        {"role": "system", "content": "You are a terrain analysis expert. Synthesize the provided DEM/terrain tool data into a clear, comprehensive answer to the user's question."},
                        {"role": "user", "content": synthesis_prompt}
                    ],
                    temperature=1.0,
                    max_completion_tokens=2000
                )
                response_text = synth_resp.choices[0].message.content
            except Exception:
                response_text = tool_summary or "Terrain analysis completed with limited data."
            
            result = {"response": response_text, "tool_calls": list(tool_results.keys()), "session_id": session_id, "message_count": 1}
        
        elapsed = time.time() - start_time
        logger.info(f"[MSG] [{request_id}] [OK] Agent responded in {elapsed:.2f}s")
        logger.info(f"[MSG] [{request_id}] Tool calls: {len(result.get('tool_calls', []))}")
        
        return {
            "status": "success",
            **result,
            "timestamp": datetime.utcnow().isoformat()
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"[MSG] [{request_id}] [FAIL] Chat endpoint failed: {e}")
        import traceback
        logger.error(traceback.format_exc())
        raise HTTPException(status_code=500, detail=f"Terrain chat failed: {str(e)}")


@app.get("/api/geoint/terrain/chat/{session_id}/history")
async def get_terrain_chat_history(session_id: str):
    """Get conversation history for a terrain agent session."""
    try:
        from geoint.terrain_agent import get_terrain_agent
        agent = get_terrain_agent()
        history = await agent.get_session_history(session_id)
        
        return {
            "status": "success",
            "session_id": session_id,
            "history": history,
            "message_count": len(history)
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.delete("/api/geoint/terrain/chat/{session_id}")
async def clear_terrain_chat_session(session_id: str):
    """Clear a terrain agent session (reset memory)."""
    try:
        from geoint.terrain_agent import get_terrain_agent
        agent = get_terrain_agent()
        cleared = await agent.clear_session(session_id)
        
        return {
            "status": "success" if cleared else "not_found",
            "session_id": session_id,
            "cleared": cleared
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ============================================================================
# GEOINT VISION ANALYSIS - Dedicated endpoint (matching terrain pattern)
# ============================================================================

@app.post("/api/geoint/vision")
async def geoint_vision_analysis(request: Request):
    """
    GEOINT Vision Analysis - Unified endpoint for initial analysis AND follow-ups
    
    This endpoint supports:
    1. Initial vision analysis (no session_id) - Screenshot + raster analysis
    2. Follow-up questions (with session_id) - Uses VisionAgent with conversation memory
    
    Request body:
    {
        "latitude": float,
        "longitude": float,
        "screenshot": str (base64 screenshot),
        "user_query": str (optional - user question),
        "radius_miles": float (optional - defaults to 5.0),
        "session_id": str (optional - provide for follow-up questions to maintain context)
    }
    
    Response includes session_id that can be used for follow-up questions.
    """
    import uuid
    request_id = f"vision-{datetime.utcnow().timestamp()}"
    try:
        logger.info(f"[EYE] [{request_id}] ============================================================")
        logger.info(f"[EYE] [{request_id}] VISION ENDPOINT CALLED")
        logger.info(f"[EYE] [{request_id}] ============================================================")
        
        # Parse request body
        request_data = await request.json()
        logger.info(f"[EYE] [{request_id}] Request keys: {list(request_data.keys())}")
        
        latitude = request_data.get("latitude")
        longitude = request_data.get("longitude")
        screenshot = request_data.get("screenshot")
        user_query = request_data.get("user_query") or request_data.get("user_context")
        radius_miles = request_data.get("radius_miles", 5.0)
        session_id = request_data.get("session_id")
        
        # [EYE] NEW: Accept tile_urls and collection directly from frontend
        tile_urls_from_request = request_data.get("tile_urls", [])
        collection_from_request = request_data.get("collection")
        map_bounds_from_request = request_data.get("map_bounds")
        # [CHART] NEW: Accept STAC items with assets directly from frontend for NDVI/raster analysis
        stac_items_from_request = request_data.get("stac_items", [])
        # [TARGET] NEW: Accept analysis_type hint from frontend (raster vs screenshot)
        analysis_type = request_data.get("analysis_type")
        
        screenshot_size = len(screenshot) if screenshot else 0
        logger.info(f"[EYE] [{request_id}] Screenshot: {screenshot_size / 1024:.1f} KB")
        logger.info(f"[EYE] [{request_id}] Session ID: {session_id or 'NEW SESSION'}")
        logger.info(f"[EYE] [{request_id}] User query: {user_query}")
        logger.info(f"[EYE] [{request_id}] Tile URLs from request: {len(tile_urls_from_request)}")
        logger.info(f"[EYE] [{request_id}] STAC items from request: {len(stac_items_from_request)}")
        logger.info(f"[EYE] [{request_id}] Collection from request: {collection_from_request}")
        if analysis_type:
            logger.info(f"[TARGET] [{request_id}] Analysis type hint: {analysis_type}")
        
        # Validate required parameters
        if latitude is None or longitude is None:
            raise HTTPException(status_code=400, detail="latitude and longitude are required")
        
        if not screenshot:
            raise HTTPException(status_code=400, detail="screenshot is required for vision analysis")
        
        # Validate coordinates
        if not (-90 <= latitude <= 90):
            raise HTTPException(status_code=400, detail=f"Invalid latitude: {latitude}")
        if not (-180 <= longitude <= 180):
            raise HTTPException(status_code=400, detail=f"Invalid longitude: {longitude}")
        
        logger.info(f"[EYE] [{request_id}] Coordinates: ({latitude}, {longitude})")
        logger.info(f"[EYE] [{request_id}] Radius: {radius_miles} miles")
        
        import time
        agent_start = time.time()
        
        # Get Vision Agent (SK Agent with memory and vision tools)
        from agents import get_vision_agent
        vision_agent = get_vision_agent()
        
        # Create session_id if not provided
        if not session_id:
            session_id = str(uuid.uuid4())
            logger.info(f"[EYE] [{request_id}] Created new session: {session_id}")
        
        # Build the message for the agent
        if not user_query:
            user_query = "Analyze this location. What can you identify from the imagery?"
        
        # Gather STAC context - prefer request data over session context
        # Use bounds from request if provided, otherwise build from coordinates
        if map_bounds_from_request:
            map_bounds = map_bounds_from_request
            # Ensure pin coordinates are set (this is a pin-based analysis)
            # Pin coordinates take priority for sampling
            map_bounds['pin_lat'] = latitude
            map_bounds['pin_lng'] = longitude
            # Also ensure center coordinates are present as fallback
            if 'center_lat' not in map_bounds:
                map_bounds['center_lat'] = latitude
            if 'center_lng' not in map_bounds:
                map_bounds['center_lng'] = longitude
        else:
            # No map bounds from request - build from pin coordinates
            map_bounds = {
                'pin_lat': latitude,
                'pin_lng': longitude,
                'center_lat': latitude,
                'center_lng': longitude
            }
        
        logger.info(f"[EYE] [{request_id}] Pin coordinates set: ({map_bounds.get('pin_lat')}, {map_bounds.get('pin_lng')})")
        
        # Get STAC context - prefer request data, fallback to session context
        collections_list = []
        stac_items_from_session = []
        tile_urls_for_agent = tile_urls_from_request  # Direct from frontend
        
        # Use collection from request if provided
        if collection_from_request:
            collections_list = [collection_from_request]
        
        # [CHART] PREFER STAC items from request (frontend has them with assets)
        # Only fallback to session context if request didn't provide STAC items
        if stac_items_from_request:
            stac_items_from_session = stac_items_from_request
            logger.info(f"[EYE] [{request_id}] Using {len(stac_items_from_request)} STAC items from request (with assets for NDVI)")
        elif router_agent and session_id:
            # Fallback: Try to get STAC items from session context
            session_context = router_agent.tools.session_contexts.get(session_id, {})
            if not collections_list:
                collections_list = session_context.get('last_collections', [])
            stac_items_from_session = session_context.get('last_stac_items', [])
            logger.info(f"[EYE] [{request_id}] Loaded session context: collections={collections_list}, stac_items={len(stac_items_from_session)}")
        
        logger.info(f"[EYE] [{request_id}] Tile URLs for agent: {len(tile_urls_for_agent)}")
        logger.info(f"[EYE] [{request_id}] STAC Items from session: {len(stac_items_from_session)}")
        logger.info(f"[EYE] [{request_id}] Collections: {collections_list}")
        
        # Call the vision agent
        import asyncio
        try:
            result = await asyncio.wait_for(
                vision_agent.analyze(
                    user_query=user_query,
                    session_id=session_id,
                    imagery_base64=screenshot,
                    map_bounds=map_bounds,
                    collections=collections_list,
                    stac_items=stac_items_from_session,
                    tile_urls=tile_urls_for_agent,  # NEW: Pass tile URLs directly
                    conversation_history=[],
                    analysis_type=analysis_type  # [TARGET] Pass hint from frontend
                ),
                timeout=240.0
            )
        except asyncio.TimeoutError:
            agent_elapsed = time.time() - agent_start
            logger.error(f"[EYE] [{request_id}] [FAIL] AGENT TIMEOUT after {agent_elapsed:.1f}s")
            raise HTTPException(
                status_code=504,
                detail=f"Vision analysis timed out after {agent_elapsed:.1f}s. Please try again."
            )
        
        agent_elapsed = time.time() - agent_start
        logger.info(f"[EYE] [{request_id}] [OK] VISION AGENT COMPLETED ({agent_elapsed:.2f}s)")
        
        response_text = result.get("response") or result.get("analysis")
        
        if not response_text:
            logger.warning(f"[EYE] [{request_id}] Empty response from vision agent")
            raise HTTPException(status_code=500, detail="Vision agent returned empty response")
        
        return {
            "status": "success",
            "result": {
                "analysis": response_text,
                "tools_used": result.get("tools_used", []),
                "vision_data": result.get("vision_data", {})
            },
            "session_id": session_id,
            "timestamp": datetime.utcnow().isoformat()
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"[EYE] [{request_id}] [FAIL] VISION ENDPOINT FAILED")
        logger.error(f"[EYE] [{request_id}] Error: {e}")
        logger.error(traceback.format_exc())
        raise HTTPException(
            status_code=500,
            detail=f"Vision analysis failed: {str(e)}"
        )


@app.post("/api/geoint/vision/chat")
async def geoint_vision_chat(request: Request):
    """
    [BOT] GEOINT Vision Agent Chat - Multi-turn conversation with memory
    
    Request body:
    {
        "session_id": str (required for follow-ups),
        "message": str (user's follow-up question),
        "latitude": float (optional - for context),
        "longitude": float (optional - for context),
        "screenshot": str (optional - updated screenshot),
        "tile_urls": list (optional - tile URLs from frontend),
        "collection": str (optional - current collection name)
    }
    """
    request_id = f"vision-chat-{datetime.utcnow().timestamp()}"
    try:
        logger.info(f"[MSG] [{request_id}] VISION CHAT endpoint called")
        
        request_data = await request.json()
        session_id = request_data.get("session_id")
        message = request_data.get("message")
        latitude = request_data.get("latitude")
        longitude = request_data.get("longitude")
        screenshot = request_data.get("screenshot")
        
        # [EYE] NEW: Accept tile_urls and collection from frontend
        tile_urls_from_request = request_data.get("tile_urls", [])
        collection_from_request = request_data.get("collection")
        # [CHART] NEW: Accept STAC items with assets from frontend for NDVI/raster analysis
        stac_items_from_request = request_data.get("stac_items", [])
        
        if not session_id:
            raise HTTPException(status_code=400, detail="session_id is required for chat")
        
        if not message:
            raise HTTPException(status_code=400, detail="message is required")
        
        logger.info(f"[MSG] [{request_id}] Session: {session_id}")
        logger.info(f"[MSG] [{request_id}] Message: {message[:100]}")
        logger.info(f"[MSG] [{request_id}] Tile URLs from request: {len(tile_urls_from_request)}")
        logger.info(f"[MSG] [{request_id}] STAC items from request: {len(stac_items_from_request)}")
        
        # [TARGET] NEW: Accept analysis_type hint from frontend
        analysis_type = request_data.get("analysis_type")
        if analysis_type:
            logger.info(f"[TARGET] [{request_id}] Analysis type hint from frontend: {analysis_type}")
        
        # [SEARCH] DETAILED STAC ITEM LOGGING
        if stac_items_from_request:
            for i, item in enumerate(stac_items_from_request[:2]):
                logger.info(f"[MSG] [{request_id}] STAC item {i}: id={item.get('id', 'unknown')}, collection={item.get('collection', 'unknown')}, assets={list(item.get('assets', {}).keys())[:5]}")
        logger.info(f"[MSG] [{request_id}] Collection from request: {collection_from_request}")
        
        from agents import get_vision_agent
        vision_agent = get_vision_agent()
        
        # Validate coordinate ranges if provided
        if latitude is not None and not (-90 <= latitude <= 90):
            raise HTTPException(status_code=400, detail=f"Invalid latitude: {latitude}. Must be between -90 and 90.")
        if longitude is not None and not (-180 <= longitude <= 180):
            raise HTTPException(status_code=400, detail=f"Invalid longitude: {longitude}. Must be between -180 and 180.")
        
        # Prepare context - ensure pin coordinates are set for point-based analysis
        map_bounds = None
        if latitude is not None and longitude is not None:
            map_bounds = {
                'pin_lat': latitude,      # Pin location takes priority for point sampling
                'pin_lng': longitude,
                'center_lat': latitude,   # Also set as center for fallback
                'center_lng': longitude
            }
            logger.info(f"[MSG] [{request_id}] Pin coordinates set: ({latitude}, {longitude})")
        
        # Get STAC context - prefer request data, fallback to session context
        collections_list = []
        stac_items_from_session = []
        tile_urls_for_agent = tile_urls_from_request
        
        # Use collection from request if provided
        if collection_from_request:
            collections_list = [collection_from_request]
        
        # Fallback to session context if no data from request
        if router_agent and session_id and not tile_urls_for_agent:
            session_context = router_agent.tools.session_contexts.get(session_id, {})
            if not collections_list:
                collections_list = session_context.get('last_collections', [])
            stac_items_from_session = session_context.get('last_stac_items', [])
        
        # [CHART] CRITICAL: Prefer STAC items from request (has fresh assets/band URLs for NDVI)
        final_stac_items = stac_items_from_request if stac_items_from_request else stac_items_from_session
        logger.info(f"[MSG] [{request_id}] Using {len(final_stac_items)} STAC items for analysis (request: {len(stac_items_from_request)}, session: {len(stac_items_from_session)})")
        
        import asyncio
        result = await asyncio.wait_for(
            vision_agent.analyze(
                user_query=message,
                session_id=session_id,
                imagery_base64=screenshot,
                map_bounds=map_bounds or {},
                collections=collections_list,
                stac_items=final_stac_items,  # Use request data if available
                tile_urls=tile_urls_for_agent,  # NEW: Pass tile URLs directly
                conversation_history=[],
                analysis_type=analysis_type  # [TARGET] Pass hint from frontend
            ),
            timeout=120.0
        )
        
        logger.info(f"[MSG] [{request_id}] [OK] Vision chat completed")
        
        response_text = result.get("response") or result.get("analysis")
        if not response_text:
            logger.warning(f"[MSG] [{request_id}] Empty response from vision agent in chat endpoint")
            response_text = (
                "I wasn't able to generate a response for this query. "
                "Please try rephrasing your question or adjusting the pin location."
            )
        
        return {
            "status": "success",
            "result": {
                "response": response_text,
                "tools_used": result.get("tools_used", [])
            },
            "session_id": session_id,
            "timestamp": datetime.utcnow().isoformat()
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"[MSG] [{request_id}] [FAIL] Vision chat failed: {e}")
        import traceback
        logger.error(traceback.format_exc())
        raise HTTPException(status_code=500, detail=f"Vision chat failed: {str(e)}")


@app.delete("/api/geoint/vision/chat/{session_id}")
async def clear_vision_chat_session(session_id: str):
    """Clear a vision agent session (reset memory)."""
    try:
        from agents import get_vision_agent
        vision_agent = get_vision_agent()
        
        # Clear session (vision agent should implement this)
        cleared = True  # Placeholder - implement session clearing in vision agent
        
        return {
            "status": "success" if cleared else "not_found",
            "session_id": session_id,
            "cleared": cleared
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# NOTE: Duplicate /api/geoint/mobility endpoint removed (was preventing terrain endpoint from registering)
# The correct mobility endpoint is at line ~2266

@app.post("/api/geoint/building-damage")
async def geoint_building_damage_analysis(request: Request):
    """
    [BUILD] GEOINT Building Damage Assessment
    
    Structure damage assessment using GPT-5 Vision and satellite imagery.
    
    When a screenshot is provided (user has loaded data on the map), analysis is
    performed on the VISIBLE imagery—the loaded tiles—not independently-fetched
    Sentinel-2.  When no screenshot is available the agent falls back to its own
    satellite imagery retrieval via the Agent Service tools.
    
    Request body:
    {
        "latitude": float,
        "longitude": float,
        "user_query": str (optional - user's question),
        "user_context": str (optional - legacy alias for user_query),
        "screenshot": str (optional - base64 map screenshot),
        "radius_miles": float (optional, default 5.0)
    }
    """
    try:
        body = await request.json()
        latitude = body.get("latitude")
        longitude = body.get("longitude")
        user_query = body.get("user_query") or body.get("user_context") or ""
        screenshot = body.get("screenshot")
        radius_miles = body.get("radius_miles", 5.0)
        
        # Validation
        if latitude is None or longitude is None:
            raise HTTPException(
                status_code=400,
                detail="Missing required fields: latitude and longitude"
            )
        
        if not (-90 <= latitude <= 90):
            raise HTTPException(status_code=400, detail=f"Invalid latitude: {latitude}")
        
        if not (-180 <= longitude <= 180):
            raise HTTPException(status_code=400, detail=f"Invalid longitude: {longitude}")
        
        logger.info(f"Building Damage endpoint: ({latitude}, {longitude})")
        logger.info(f"Building Damage: screenshot={'yes' if screenshot else 'no'}, query='{user_query[:100]}'" if user_query else "Building Damage: no query")
        
        import time
        agent_start = time.time()
        
        # Create vision client for GPT-5 screenshot analysis
        from openai import AsyncAzureOpenAI
        from azure.identity import DefaultAzureCredential, get_bearer_token_provider as _gbt
        _aoai_endpoint = os.getenv("AZURE_AI_PROJECT_ENDPOINT") or os.getenv("AZURE_OPENAI_ENDPOINT")
        if not _aoai_endpoint:
            raise ValueError("AZURE_AI_PROJECT_ENDPOINT or AZURE_OPENAI_ENDPOINT environment variable is required")
        _vision_client = AsyncAzureOpenAI(
            azure_endpoint=_aoai_endpoint,
            api_key=os.environ.get("AZURE_OPENAI_API_KEY"),
            azure_ad_token_provider=_gbt(
                DefaultAzureCredential(), "https://cognitiveservices.azure.com/.default"
            ) if not os.environ.get("AZURE_OPENAI_API_KEY") else None,
            api_version="2024-12-01-preview",
        )
        
        # ── PATH 1: Screenshot provided — analyze the loaded map imagery ──
        # When the user has loaded data (NAIP, Sentinel-2, Landsat, etc.) and
        # the frontend captured a screenshot, analyze THAT imagery directly via
        # GPT-5 Vision.  Do NOT fetch independent Sentinel-2 tiles.
        if screenshot:
            logger.info("Building Damage: Analyzing loaded map imagery via screenshot")
            
            # Reverse geocode for location context
            location_name = f"({latitude:.4f}, {longitude:.4f})"
            try:
                from semantic_translator import geocoding_plugin
                rg = await geocoding_plugin.azure_maps_reverse_geocode(latitude, longitude)
                import json as json_mod
                data = json_mod.loads(rg)
                if not data.get("error"):
                    name = data.get("name", "")
                    region = data.get("region", "")
                    country = data.get("country", "")
                    parts = [p for p in [name, region, country] if p and p != name]
                    location_name = f"{name}, {', '.join(parts)}" if name and parts else name or location_name
            except Exception:
                pass
            
            clean_b64 = screenshot
            if clean_b64.startswith('data:image'):
                clean_b64 = clean_b64.split(',', 1)[1]
            
            prompt = (
                f"You are an expert GEOINT analyst specializing in building damage assessment from satellite and aerial imagery.\n\n"
                f"Location: {location_name} ({latitude:.6f}, {longitude:.6f})\n"
                f"Analysis radius: {radius_miles} miles\n\n"
                f"Analyze the provided satellite/aerial image for building and structural damage.\n\n"
                f"Assess:\n"
                f"1. **Location** — Identify the area shown\n"
                f"2. **Damage Assessment** — Visual observations, damage indicators, severity classification\n"
                f"   Use scale: No Damage | Minor Damage | Major Damage | Destroyed\n"
                f"   Look for: collapsed/missing roofs, debris fields, burn scars, water damage, structural deformation\n"
                f"3. **Infrastructure Impact** — Roads, bridges, utilities affected\n"
                f"4. **Recommendations** — Priority areas for response teams, suggested next steps\n\n"
                f"Keep analysis factual. Acknowledge resolution limitations. Do NOT fetch additional imagery — analyze only what is visible in this image.\n"
            )
            if user_query:
                prompt += f"\nUser question: {user_query}\n"
            
            try:
                vision_response = await _vision_client.chat.completions.create(
                    model=os.getenv("AZURE_OPENAI_DEPLOYMENT_NAME", "gpt-5"),
                    messages=[
                        {"role": "system", "content": "You are a GEOINT Building Damage Assessment expert. Analyze the provided imagery and give structured damage assessments."},
                        {"role": "user", "content": [
                            {"type": "text", "text": prompt},
                            {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{clean_b64}", "detail": "high"}}
                        ]}
                    ],
                    temperature=1.0,
                    max_completion_tokens=3000
                )
                response_text = vision_response.choices[0].message.content
                elapsed = time.time() - agent_start
                logger.info(f"Building Damage: Screenshot analysis completed ({elapsed:.1f}s, {len(response_text)} chars)")
                
                return {
                    "status": "success",
                    "result": {
                        "agent": "building_damage_vision",
                        "response": response_text,
                        "summary": response_text[:500],
                        "tool_calls": [{"tool": "gpt_vision_analysis"}],
                        "location": {"latitude": latitude, "longitude": longitude},
                        "radius_miles": radius_miles,
                        "timestamp": datetime.utcnow().isoformat()
                    },
                    "timestamp": datetime.utcnow().isoformat()
                }
            except Exception as vis_err:
                logger.warning(f"Building Damage: Screenshot vision analysis failed: {vis_err}, falling back to Agent Service")
                # Fall through to Agent Service path
        
        # ── PATH 2: No screenshot — use Agent Service to fetch and analyze imagery ──
        logger.info("Building Damage: No screenshot, using Agent Service with tool-based imagery fetch")
        analysis_result = None
        try:
            from geoint.agents import building_damage_agent
            
            analysis_result = await building_damage_agent(
                latitude=latitude,
                longitude=longitude,
                screenshot_base64=None,
                user_query=user_query,
                radius_miles=radius_miles
            )
            
            # Check if agent returned an error (403 / PE lockdown / model errors)
            resp_text = str(analysis_result.get("response", ""))
            _error_patterns = [
                "403", "Public access is disabled", "private endpoint",
                "invalid_engine_error", "Failed to resolve model",
                "InternalServerError", "Unable to get resource",
                "DeploymentNotFound", "model_not_found",
            ]
            if any(pat.lower() in resp_text.lower() for pat in _error_patterns):
                logger.warning(f"Building damage agent returned error, falling back to direct tools: {resp_text[:200]}")
                analysis_result = None  # trigger fallback
        except Exception as agent_err:
            err_str = str(agent_err)
            logger.warning(f"Building damage agent failed ({err_str}), falling back to direct tools")
            analysis_result = None
        
        # ── FALLBACK: Direct tool calls when Agent Service is blocked by PE ──
        if analysis_result is None:
            logger.info("Building Damage: Using direct tool fallback (PE lockdown)")
            
            import json as json_mod
            
            # 1) Run the damage assessment tool directly (uses warm vision_analyzer)
            from geoint.building_damage_tools import _assess_damage_async, _classify_severity_async
            
            assess_result = await _assess_damage_async(latitude, longitude, radius_miles)
            classify_result = await _classify_severity_async(latitude, longitude)
            
            # 2) If screenshot provided, analyze it with _vision_client
            visual_analysis = None
            if screenshot:
                try:
                    clean_b64 = screenshot
                    if clean_b64.startswith('data:image'):
                        clean_b64 = clean_b64.split(',', 1)[1]
                    
                    vision_response = await _vision_client.chat.completions.create(
                        model=os.getenv("AZURE_OPENAI_DEPLOYMENT_NAME", "gpt-5"),
                        messages=[
                            {"role": "system", "content": "You are an expert in structural damage assessment from satellite imagery. Provide detailed, factual analysis."},
                            {"role": "user", "content": [
                                {"type": "text", "text": f"Analyze this satellite image at ({latitude:.4f}, {longitude:.4f}) for building damage. "
                                 f"Look for: collapsed structures, debris fields, burn scars, water damage, infrastructure impact. "
                                 f"Classify severity as: No Damage, Minor Damage, Major Damage, or Destroyed. "
                                 f"{'Additional context: ' + user_query if user_query else ''}"},
                                {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{clean_b64}", "detail": "high"}}
                            ]}
                        ],
                        temperature=1.0,
                        max_completion_tokens=2000
                    )
                    visual_analysis = vision_response.choices[0].message.content
                    logger.info(f"Building Damage: Screenshot analysis completed ({len(visual_analysis)} chars)")
                except Exception as vis_err:
                    logger.warning(f"Building Damage: Screenshot analysis failed: {vis_err}")
            
            # 3) Combine results into agent-like response
            tool_assessment = assess_result.get("visual_assessment", "")
            severity_assessment = classify_result.get("visual_assessment", "")
            
            # Build a comprehensive response
            parts = []
            if visual_analysis:
                parts.append(f"## Visual Analysis of Current Map View\n\n{visual_analysis}")
            if tool_assessment:
                parts.append(f"## Satellite Imagery Assessment\n\n{tool_assessment}")
            if severity_assessment and severity_assessment != tool_assessment:
                parts.append(f"## Severity Classification\n\n{severity_assessment}")
            
            combined_response = "\n\n".join(parts) if parts else "Building damage assessment completed. No significant damage indicators detected from available imagery."
            
            analysis_result = {
                "agent": "building_damage_agent_fallback",
                "response": combined_response,
                "summary": combined_response[:500],
                "tool_calls": [{"tool": "assess_building_damage"}, {"tool": "classify_damage_severity"}],
                "location": {"latitude": latitude, "longitude": longitude},
                "radius_miles": radius_miles,
                "timestamp": datetime.utcnow().isoformat()
            }
            logger.info("Building Damage: Direct fallback completed successfully")
        
        logger.info("Building damage agent completed")
        
        return {
            "status": "success",
            "result": analysis_result,
            "timestamp": datetime.utcnow().isoformat()
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Building Damage endpoint failed: {e}")
        logger.error(traceback.format_exc())
        raise HTTPException(
            status_code=500,
            detail=f"Building damage analysis failed: {str(e)}"
        )

@app.post("/api/geoint/extreme-weather")
async def geoint_extreme_weather_analysis(request: Request):
    """
    [STORM] GEOINT Extreme Weather & Climate Projection Analysis
    
    Climate projections from NASA NEX-GDDP-CMIP6 (NetCDF data, point-sampled).
    Returns temperature, precipitation, wind, humidity, and radiation projections.
    No map tiles — data is chat-based point values only.
    
    Request body:
    {
        "latitude": float,
        "longitude": float,
        "user_query": str (optional - climate question),
        "user_context": str (optional - legacy field name),
        "session_id": str (optional - for follow-up questions)
    }
    
    Response includes session_id for follow-up questions.
    """
    import uuid
    request_id = f"climate-{datetime.utcnow().timestamp()}"
    try:
        logger.info(f"[STORM] [{request_id}] EXTREME WEATHER ENDPOINT CALLED")
        
        request_data = await request.json()
        
        latitude = request_data.get("latitude")
        longitude = request_data.get("longitude")
        user_query = request_data.get("user_query") or request_data.get("user_context")
        session_id = request_data.get("session_id")
        screenshot = request_data.get("screenshot")
        
        # Validate required parameters
        if latitude is None or longitude is None:
            raise HTTPException(status_code=400, detail="latitude and longitude are required")
        
        if not (-90 <= latitude <= 90):
            raise HTTPException(status_code=400, detail=f"Invalid latitude: {latitude}")
        if not (-180 <= longitude <= 180):
            raise HTTPException(status_code=400, detail=f"Invalid longitude: {longitude}")
        
        logger.info(f"[STORM] [{request_id}] Coordinates: ({latitude}, {longitude}), query: {user_query}")
        
        import asyncio
        import time
        agent_start = time.time()
        
        # Use ExtremeWeatherAgent with conversation memory
        from geoint.extreme_weather_agent import get_extreme_weather_agent
        agent = get_extreme_weather_agent()
        
        if not session_id:
            session_id = str(uuid.uuid4())
            logger.info(f"[STORM] [{request_id}] Created new session: {session_id}")
        
        message = user_query or "Provide a comprehensive climate projection overview for this location."
        
        # ====================================================================
        # FAST PATH: Direct tool call for overview queries
        # ====================================================================
        # For first-time "general overview" queries, bypass the Agent Service
        # entirely.  Instead of LLM→plan→tool→results→LLM→synthesize
        # (2 LLM round-trips, ~10-20s overhead), call get_climate_overview
        # directly and format the results with a single LLM call.
        # This saves ~8-20s per overview query.
        # Only for new sessions with no custom query or the default overview query.
        is_overview_query = (
            not user_query
            or "overview" in message.lower()
            or ("climate" in message.lower() and "projection" in message.lower())
            or message == "Provide a comprehensive climate projection overview for this location."
        )
        
        if is_overview_query and not request_data.get("session_id"):
            try:
                logger.info(f"[STORM] [{request_id}] FAST PATH: Direct get_climate_overview call")
                from geoint.extreme_weather_tools import get_climate_overview
                from geoint.extreme_weather_agent import _reverse_geocode_cache
                
                # Run climate overview in thread pool (it's sync code with blocking I/O)
                loop = asyncio.get_event_loop()
                raw_result = await asyncio.wait_for(
                    loop.run_in_executor(None, get_climate_overview, latitude, longitude, "ssp585", 2030),
                    timeout=120.0
                )
                
                overview_data = json.loads(raw_result)
                fast_elapsed = time.time() - agent_start
                logger.info(f"[STORM] [{request_id}] FAST PATH: Data fetched in {fast_elapsed:.1f}s")
                
                if "error" not in overview_data:
                    # Resolve location name (cached)
                    geo_key = f"{latitude:.4f}:{longitude:.4f}"
                    location_name = _reverse_geocode_cache.get(geo_key)
                    if not location_name:
                        try:
                            from semantic_translator import geocoding_plugin
                            geo_result = await geocoding_plugin.azure_maps_reverse_geocode(latitude, longitude)
                            geo_data = json.loads(geo_result)
                            if not geo_data.get("error"):
                                name = geo_data.get("name", "")
                                region = geo_data.get("region", "")
                                country = geo_data.get("country", "")
                                parts = [p for p in [name, region, country] if p and p != name]
                                location_name = f"{name}, {', '.join(parts)}" if name and parts else name or f"({latitude:.4f}, {longitude:.4f})"
                            else:
                                location_name = f"({latitude:.4f}, {longitude:.4f})"
                            _reverse_geocode_cache[geo_key] = location_name
                        except Exception:
                            location_name = f"({latitude:.4f}, {longitude:.4f})"
                    
                    # Single LLM call to format the raw data into prose
                    from openai import AsyncAzureOpenAI
                    from azure.identity import DefaultAzureCredential, get_bearer_token_provider as _gbt
                    _aoai_endpoint = os.getenv("AZURE_AI_PROJECT_ENDPOINT") or os.getenv("AZURE_OPENAI_ENDPOINT")
                    if not _aoai_endpoint:
                        raise ValueError("AZURE_AI_PROJECT_ENDPOINT or AZURE_OPENAI_ENDPOINT environment variable is required")
                    _fmt_client = AsyncAzureOpenAI(
                        azure_endpoint=_aoai_endpoint,
                        api_key=os.environ.get("AZURE_OPENAI_API_KEY"),
                        azure_ad_token_provider=_gbt(
                            DefaultAzureCredential(), "https://cognitiveservices.azure.com/.default"
                        ) if not os.environ.get("AZURE_OPENAI_API_KEY") else None,
                        api_version="2024-12-01-preview",
                    )
                    
                    fmt_resp = await _fmt_client.chat.completions.create(
                        model=os.environ.get("AZURE_OPENAI_FAST_DEPLOYMENT", "gpt-4o-mini"),
                        messages=[
                            {"role": "system", "content": "You are a climate analyst. Format the provided climate projection data into a clear, informative summary. Use the same style and formatting as your normal extreme weather analysis responses. Include all available metrics with their values and units."},
                            {"role": "user", "content": f"Format this climate projection data for {location_name} (SSP5-8.5, 2030) into a comprehensive summary:\n\n{raw_result}"}
                        ],
                        max_completion_tokens=2000,
                        temperature=0.3,
                    )
                    
                    formatted_response = fmt_resp.choices[0].message.content
                    total_elapsed = time.time() - agent_start
                    logger.info(f"[STORM] [{request_id}] FAST PATH COMPLETE in {total_elapsed:.1f}s (data: {fast_elapsed:.1f}s, format: {total_elapsed - fast_elapsed:.1f}s)")
                    
                    # --------------------------------------------------------
                    # PRE-WARM: Kick off background ssp245 STAC item fetch
                    # so the cache is ready if user follows up with a
                    # "compare scenarios" question (saves ~2-5s on compare).
                    # --------------------------------------------------------
                    try:
                        from geoint.extreme_weather_tools import _search_cmip6_items as _prewarm_stac
                        loop.run_in_executor(None, _prewarm_stac, latitude, longitude, 'tasmax', 'ssp245', 2030, 1)
                        logger.info(f"[STORM] [{request_id}] Pre-warming ssp245 STAC cache")
                    except Exception:
                        pass  # best-effort
                    
                    return {
                        "status": "success",
                        "result": {
                            "analysis": formatted_response,
                            "tool_calls": [{"tool": "get_climate_overview", "result": overview_data}],
                            "message_count": 1
                        },
                        "session_id": session_id,
                        "timestamp": datetime.utcnow().isoformat()
                    }
            except asyncio.TimeoutError:
                logger.warning(f"[STORM] [{request_id}] FAST PATH timed out, falling back to agent")
            except Exception as e:
                logger.warning(f"[STORM] [{request_id}] FAST PATH failed ({e}), falling back to agent")
        
        # ====================================================================
        # FAST PATH 2: Direct tool call for comparison queries
        # ====================================================================
        # Detects "compare scenarios" / "SSP245 vs SSP585" patterns and calls
        # compare_climate_scenarios directly, saving 2 LLM round-trips (~8-15s).
        # Works for both new and follow-up sessions.
        import re as _re
        _msg_lower = message.lower()
        is_comparison_query = (
            ("compare" in _msg_lower and ("scenario" in _msg_lower or "ssp" in _msg_lower))
            or ("ssp245" in _msg_lower and "ssp585" in _msg_lower)
            or ("ssp2" in _msg_lower and "ssp5" in _msg_lower)
            or ("moderate" in _msg_lower and "worst" in _msg_lower
                and ("scenario" in _msg_lower or "emission" in _msg_lower or "climate" in _msg_lower))
        )
        
        if is_comparison_query:
            try:
                logger.info(f"[STORM] [{request_id}] FAST PATH COMPARE: Direct compare_climate_scenarios call")
                from geoint.extreme_weather_tools import compare_climate_scenarios
                from geoint.extreme_weather_agent import _reverse_geocode_cache
                
                # Extract year from query if mentioned (e.g. "by 2050", "in 2060")
                year_match = _re.search(r'\b(20[2-9]\d|2100)\b', message)
                target_year = int(year_match.group()) if year_match else 2030
                
                loop = asyncio.get_event_loop()
                raw_result = await asyncio.wait_for(
                    loop.run_in_executor(None, compare_climate_scenarios, latitude, longitude, target_year),
                    timeout=120.0
                )
                
                comparison_data = json.loads(raw_result)
                fast_elapsed = time.time() - agent_start
                logger.info(f"[STORM] [{request_id}] FAST PATH COMPARE: Data fetched in {fast_elapsed:.1f}s")
                
                if "error" not in comparison_data:
                    # Resolve location name (cached)
                    geo_key = f"{latitude:.4f}:{longitude:.4f}"
                    location_name = _reverse_geocode_cache.get(geo_key)
                    if not location_name:
                        try:
                            from semantic_translator import geocoding_plugin
                            geo_result = await geocoding_plugin.azure_maps_reverse_geocode(latitude, longitude)
                            geo_data = json.loads(geo_result)
                            if not geo_data.get("error"):
                                name = geo_data.get("name", "")
                                region = geo_data.get("region", "")
                                country = geo_data.get("country", "")
                                parts = [p for p in [name, region, country] if p and p != name]
                                location_name = f"{name}, {', '.join(parts)}" if name and parts else name or f"({latitude:.4f}, {longitude:.4f})"
                            else:
                                location_name = f"({latitude:.4f}, {longitude:.4f})"
                            _reverse_geocode_cache[geo_key] = location_name
                        except Exception:
                            location_name = f"({latitude:.4f}, {longitude:.4f})"
                    
                    # Single LLM call to format comparison data into prose
                    from openai import AsyncAzureOpenAI
                    from azure.identity import DefaultAzureCredential, get_bearer_token_provider as _gbt
                    _aoai_endpoint = os.getenv("AZURE_AI_PROJECT_ENDPOINT") or os.getenv("AZURE_OPENAI_ENDPOINT")
                    if not _aoai_endpoint:
                        raise ValueError("AZURE_AI_PROJECT_ENDPOINT or AZURE_OPENAI_ENDPOINT environment variable is required")
                    _fmt_client = AsyncAzureOpenAI(
                        azure_endpoint=_aoai_endpoint,
                        api_key=os.environ.get("AZURE_OPENAI_API_KEY"),
                        azure_ad_token_provider=_gbt(
                            DefaultAzureCredential(), "https://cognitiveservices.azure.com/.default"
                        ) if not os.environ.get("AZURE_OPENAI_API_KEY") else None,
                        api_version="2024-12-01-preview",
                    )
                    
                    fmt_resp = await _fmt_client.chat.completions.create(
                        model=os.environ.get("AZURE_OPENAI_FAST_DEPLOYMENT", "gpt-4o-mini"),
                        messages=[
                            {"role": "system", "content": (
                                "You are a climate analyst. Format the provided climate scenario comparison data "
                                "into a clear, informative analysis. Compare the moderate (SSP2-4.5) and worst-case "
                                "(SSP5-8.5) scenarios side by side. Highlight the temperature and precipitation "
                                "differences and their real-world implications for the region. "
                                "Use the same style and formatting as your normal extreme weather analysis responses."
                            )},
                            {"role": "user", "content": (
                                f"Format this climate scenario comparison for {location_name} into a comprehensive analysis. "
                                f"The user asked: '{user_query}'\n\nRaw data:\n{raw_result}"
                            )}
                        ],
                        max_completion_tokens=2000,
                        temperature=0.3,
                    )
                    
                    formatted_response = fmt_resp.choices[0].message.content
                    total_elapsed = time.time() - agent_start
                    logger.info(f"[STORM] [{request_id}] FAST PATH COMPARE COMPLETE in {total_elapsed:.1f}s (data: {fast_elapsed:.1f}s, format: {total_elapsed - fast_elapsed:.1f}s)")
                    
                    return {
                        "status": "success",
                        "result": {
                            "analysis": formatted_response,
                            "tool_calls": [{"tool": "compare_climate_scenarios", "result": comparison_data}],
                            "message_count": 1
                        },
                        "session_id": session_id,
                        "timestamp": datetime.utcnow().isoformat()
                    }
            except asyncio.TimeoutError:
                logger.warning(f"[STORM] [{request_id}] FAST PATH COMPARE timed out, falling back to agent")
            except Exception as e:
                logger.warning(f"[STORM] [{request_id}] FAST PATH COMPARE failed ({e}), falling back to agent")
        
        # ====================================================================
        # FAST PATH 3: Direct tool call for specific variable queries
        # ====================================================================
        # Detects "temperature" / "precipitation" / "wind" / "humidity" / "radiation"
        # and calls the matching tool directly.  Saves 2 LLM round-trips.
        #
        # NOTE: Cold-cache NetCDF reads from NASA Blob Storage can take 40-60s
        # per model.  With 3 models sampled in parallel, a single variable call
        # may take 60-180s on cold cache.  Timeout is set to 200s to cover
        # worst-case cold reads + STAC search overhead.
        _VARIABLE_FAST_PATHS = {
            "temperature": ("get_temperature_projection", ["temperature", "temp ", "how hot", "heat"]),
            "precipitation": ("get_precipitation_projection", ["precipitation", "precip", "rain", "rainfall", "monsoon", "flooding", "flood risk"]),
            "wind": ("get_wind_projection", ["wind speed", "wind projection", "how windy"]),
            "humidity": ("get_humidity_projection", ["humidity", "humid", "moisture"]),
            "radiation": ("get_radiation_projection", ["radiation", "solar", "shortwave", "longwave"]),
        }
        
        matched_tool = None
        for var_key, (tool_name, keywords) in _VARIABLE_FAST_PATHS.items():
            if any(kw in _msg_lower for kw in keywords):
                matched_tool = (var_key, tool_name)
                break
        
        # ----------------------------------------------------------------
        # TREND DETECTION: Does the user ask about change over time?
        # e.g., "is rainfall increasing?", "monsoon trends", "peak changing"
        # If so, fetch TWO years (2030 + 2070) in parallel.
        # ----------------------------------------------------------------
        _TREND_KEYWORDS = [
            "increasing", "decreasing", "trend", "changing", "change over",
            "getting worse", "getting better", "intensif", "peak daily",
            "over time", "by 2050", "by 2070", "by 2100", "future",
            "will it get", "projected to", "expected to",
        ]
        is_trend_query = any(kw in _msg_lower for kw in _TREND_KEYWORDS)
        
        # ----------------------------------------------------------------
        # If it's a trend query, skip the fast path entirely and let the
        # agent use the compute_trend tool (5-point linear regression with
        # R², confidence) instead of the naive 2-year delta comparison.
        # ----------------------------------------------------------------
        if matched_tool and not is_overview_query and not is_comparison_query and not is_trend_query:
            var_key, tool_name = matched_tool
            try:
                import geoint.extreme_weather_tools as _ewt
                from geoint.extreme_weather_agent import _reverse_geocode_cache
                
                tool_fn = getattr(_ewt, tool_name)
                
                # Extract scenario from query
                if "ssp245" in _msg_lower or "ssp2-4.5" in _msg_lower or "moderate" in _msg_lower:
                    scenario = "ssp245"
                else:
                    scenario = "ssp585"
                
                # Extract year from query
                year_match = _re.search(r'\b(20[2-9]\d|2100)\b', message)
                target_year = int(year_match.group()) if year_match else 2030
                
                loop = asyncio.get_event_loop()
                
                # --------------------------------------------------------
                # SINGLE-YEAR PATH (non-trend queries only; trend queries
                # skip the fast path and use the agent's compute_trend tool)
                # --------------------------------------------------------
                logger.info(f"[STORM] [{request_id}] FAST PATH VARIABLE: Direct {tool_name} call")
                raw_result = await asyncio.wait_for(
                    loop.run_in_executor(None, tool_fn, latitude, longitude, scenario, target_year),
                    timeout=200.0
                )
                
                tool_data = json.loads(raw_result)
                fast_elapsed = time.time() - agent_start
                logger.info(f"[STORM] [{request_id}] FAST PATH VARIABLE: {tool_name} data in {fast_elapsed:.1f}s")
                
                if "error" not in tool_data:
                    geo_key = f"{latitude:.4f}:{longitude:.4f}"
                    location_name = _reverse_geocode_cache.get(geo_key, f"({latitude:.4f}, {longitude:.4f})")
                    
                    from openai import AsyncAzureOpenAI
                    from azure.identity import DefaultAzureCredential, get_bearer_token_provider as _gbt
                    _aoai_endpoint = os.getenv("AZURE_AI_PROJECT_ENDPOINT") or os.getenv("AZURE_OPENAI_ENDPOINT")
                    if not _aoai_endpoint:
                        raise ValueError("AZURE_AI_PROJECT_ENDPOINT or AZURE_OPENAI_ENDPOINT environment variable is required")
                    _fmt_client = AsyncAzureOpenAI(
                        azure_endpoint=_aoai_endpoint,
                        api_key=os.environ.get("AZURE_OPENAI_API_KEY"),
                        azure_ad_token_provider=_gbt(
                            DefaultAzureCredential(), "https://cognitiveservices.azure.com/.default"
                        ) if not os.environ.get("AZURE_OPENAI_API_KEY") else None,
                        api_version="2024-12-01-preview",
                    )
                    
                    scenario_desc = "SSP2-4.5 (moderate)" if scenario == "ssp245" else "SSP5-8.5 (worst-case)"
                    fmt_resp = await _fmt_client.chat.completions.create(
                        model=os.environ.get("AZURE_OPENAI_FAST_DEPLOYMENT", "gpt-4o-mini"),
                        messages=[
                            {"role": "system", "content": (
                                "You are a climate analyst. Format the provided climate projection data "
                                "into a clear, informative summary. Include all values with units. "
                                "Address the user's specific question directly. "
                                "Conclude with a Summary section that gives a clear, direct answer grounded in the data."
                            )},
                            {"role": "user", "content": (
                                f"Format this {var_key} projection data for {location_name} "
                                f"({scenario_desc}, {target_year}). "
                                f"The user asked: '{user_query}'\n\nData:\n{raw_result}"
                            )}
                        ],
                        max_completion_tokens=1500,
                        temperature=1.0,
                    )
                    
                    formatted_response = fmt_resp.choices[0].message.content
                    total_elapsed = time.time() - agent_start
                    logger.info(f"[STORM] [{request_id}] FAST PATH VARIABLE COMPLETE in {total_elapsed:.1f}s")
                    
                    return {
                        "status": "success",
                        "result": {
                            "analysis": formatted_response,
                            "tool_calls": [{"tool": tool_name, "result": tool_data}],
                            "message_count": 1
                        },
                        "session_id": session_id,
                        "timestamp": datetime.utcnow().isoformat()
                    }
            except asyncio.TimeoutError:
                logger.warning(f"[STORM] [{request_id}] FAST PATH VARIABLE timed out after {time.time() - agent_start:.0f}s, falling back to agent")
            except Exception as e:
                logger.warning(f"[STORM] [{request_id}] FAST PATH VARIABLE failed ({e}), falling back to agent")
        
        # ====================================================================
        # STANDARD PATH: Full Agent Service round-trip
        # ====================================================================
        
        try:
            # Compute remaining time budget: Container Apps ingress hard limit
            # is 240s.  Subtract elapsed time (fast paths may have consumed
            # some) and leave a 15s buffer for JSON serialization + response.
            elapsed_so_far = time.time() - agent_start
            remaining_budget = max(230.0 - elapsed_so_far, 60.0)  # at least 60s
            logger.info(f"[STORM] [{request_id}] STANDARD PATH: elapsed={elapsed_so_far:.0f}s, budget={remaining_budget:.0f}s")
            
            result = await asyncio.wait_for(
                agent.chat(
                    session_id=session_id,
                    user_message=message,
                    latitude=latitude,
                    longitude=longitude,
                    screenshot_base64=screenshot,
                ),
                timeout=remaining_budget
            )
        except asyncio.TimeoutError:
            agent_elapsed = time.time() - agent_start
            logger.error(f"[STORM] [{request_id}] [FAIL] AGENT TIMEOUT after {agent_elapsed:.1f}s")
            raise HTTPException(
                status_code=504,
                detail=f"Climate analysis timed out after {agent_elapsed:.0f}s. The query may involve too many data lookups. Try a simpler question (e.g. 'What is the projected temperature for this location?')."
            )
        
        agent_elapsed = time.time() - agent_start
        logger.info(f"[STORM] [{request_id}] [OK] EXTREME WEATHER AGENT COMPLETED ({agent_elapsed:.2f}s)")
        
        # Enhanced diagnostic logging
        tool_calls_list = result.get("tool_calls", [])
        response_text = result.get("response", "")
        logger.info(f"[STORM] [{request_id}] Tool calls made: {len(tool_calls_list)}")
        for i, tc in enumerate(tool_calls_list):
            tool_name = tc.get('tool', 'unknown')
            tool_result = tc.get('result', {})
            if isinstance(tool_result, dict):
                has_error = 'error' in tool_result or any('error' in str(v) for v in tool_result.values() if isinstance(v, (dict, str)))
                logger.info(f"[STORM] [{request_id}]   Tool[{i}]: {tool_name} -> {'[FAIL] ERROR' if has_error else '[OK] OK'} (keys: {list(tool_result.keys())[:8]})")
                if has_error:
                    logger.warning(f"[STORM] [{request_id}]   Tool[{i}] error detail: {json.dumps(tool_result, default=str)[:500]}")
            else:
                logger.info(f"[STORM] [{request_id}]   Tool[{i}]: {tool_name} -> {str(tool_result)[:200]}")
        logger.info(f"[STORM] [{request_id}] Response preview ({len(response_text)} chars): {response_text[:300]}...")
        
        return {
            "status": "success",
            "result": {
                "analysis": result.get("response", ""),
                "tool_calls": tool_calls_list,
                "message_count": result.get("message_count", 1)
            },
            "session_id": session_id,
            "timestamp": datetime.utcnow().isoformat()
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"[STORM] [{request_id}] [FAIL] EXTREME WEATHER ENDPOINT FAILED: {e}")
        logger.error(traceback.format_exc())
        raise HTTPException(
            status_code=500,
            detail=f"Climate analysis failed: {str(e)}"
        )

@app.get("/api/geoint/cmip6-test")
async def cmip6_diagnostic_test(
    lat: float = 42.15,
    lng: float = -100.27,
    variable: str = "tasmax",
    scenario: str = "ssp585",
    year: int = 2030,
    aggregate: str = "last",
):
    """
    [MICRO] CMIP6 Diagnostic Test Endpoint
    
    Quick test of CMIP6 STAC search + NetCDF sampling without going through
    the full agent. Use this to verify:
    1. STAC search finds items
    2. Items have the requested variable as an asset
    3. NetCDF sampling returns valid data
    
    Example: /api/geoint/cmip6-test?lat=42.15&lng=-100.27&variable=tasmax
    Example: /api/geoint/cmip6-test?lat=18.47&lng=-66.10&variable=pr&aggregate=annual
    """
    from geoint.extreme_weather_tools import _search_cmip6_items, _sample_netcdf
    import time
    
    result = {"steps": [], "success": False}
    
    # Step 1: STAC Search
    t0 = time.time()
    try:
        items = _search_cmip6_items(lat, lng, variable, scenario, year, limit=3)
        elapsed = time.time() - t0
        result["steps"].append({
            "step": "STAC Search",
            "status": "ok" if items else "no_items",
            "items_found": len(items),
            "item_ids": [it.get("id", "?") for it in items],
            "elapsed_s": round(elapsed, 2),
        })
    except Exception as e:
        result["steps"].append({"step": "STAC Search", "status": "error", "error": str(e)})
        return result
    
    if not items:
        result["steps"].append({"step": "NetCDF Sample", "status": "skipped", "reason": "No items found"})
        return result
    
    # Step 2: NetCDF Sampling (first item)
    first_item = items[0]
    asset = first_item.get("assets", {}).get(variable, {})
    href = asset.get("href", "") if isinstance(asset, dict) else ""
    
    if not href:
        result["steps"].append({"step": "NetCDF Sample", "status": "error", "error": f"No href for {variable} asset"})
        return result
    
    t1 = time.time()
    try:
        sample = _sample_netcdf(href, variable, lat, lng, aggregate=aggregate)
        elapsed = time.time() - t1
        result["steps"].append({
            "step": "NetCDF Sample",
            "status": "ok" if "error" not in sample else "error",
            "result": sample,
            "elapsed_s": round(elapsed, 2),
            "item_id": first_item.get("id", "?"),
            "href_prefix": href[:100] + "...",
        })
        result["success"] = "error" not in sample
    except Exception as e:
        result["steps"].append({"step": "NetCDF Sample", "status": "error", "error": str(e)})
    
    return result


@app.post("/api/geoint/netcdf-compute")
async def geoint_netcdf_compute(request: Request):
    """
    [STORM] NetCDF Computation Endpoint — Advanced Climate Analysis

    Extends extreme-weather with time-series, area stats, anomalies, trends,
    and derived calculations.  Uses the NetCDFComputationAgent which has all
    existing climate tools PLUS the new computation tools.

    Request body:
    {
        "latitude": float,
        "longitude": float,
        "user_query": str,
        "session_id": str (optional)
    }
    """
    import uuid
    request_id = f"netcdf-calc-{datetime.utcnow().timestamp()}"
    try:
        logger.info(f"[STORM] [{request_id}] NETCDF COMPUTE ENDPOINT CALLED")

        request_data = await request.json()
        latitude = request_data.get("latitude")
        longitude = request_data.get("longitude")
        user_query = request_data.get("user_query") or request_data.get("user_context")
        session_id = request_data.get("session_id")

        if latitude is None or longitude is None:
            raise HTTPException(status_code=400, detail="latitude and longitude are required")
        if not (-90 <= latitude <= 90):
            raise HTTPException(status_code=400, detail=f"Invalid latitude: {latitude}")
        if not (-180 <= longitude <= 180):
            raise HTTPException(status_code=400, detail=f"Invalid longitude: {longitude}")

        if not user_query:
            raise HTTPException(status_code=400, detail="user_query is required")

        import asyncio
        import time
        agent_start = time.time()

        from geoint.netcdf_computation_agent import get_netcdf_computation_agent
        agent = get_netcdf_computation_agent()

        if not session_id:
            session_id = str(uuid.uuid4())

        try:
            remaining_budget = 230.0
            result = await asyncio.wait_for(
                agent.chat(
                    session_id=session_id,
                    user_message=user_query,
                    latitude=latitude,
                    longitude=longitude,
                ),
                timeout=remaining_budget,
            )
        except asyncio.TimeoutError:
            elapsed = time.time() - agent_start
            logger.error(f"[STORM] [{request_id}] COMPUTE AGENT TIMEOUT after {elapsed:.1f}s")
            raise HTTPException(
                status_code=504,
                detail=f"Computation timed out after {elapsed:.0f}s. Try a simpler query.",
            )

        elapsed = time.time() - agent_start
        logger.info(f"[STORM] [{request_id}] COMPUTE AGENT COMPLETED ({elapsed:.2f}s)")

        return {
            "status": "success",
            "result": {
                "analysis": result.get("response", ""),
                "tool_calls": result.get("tool_calls", []),
                "message_count": result.get("message_count", 1),
            },
            "session_id": session_id,
            "timestamp": datetime.utcnow().isoformat(),
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"[STORM] [{request_id}] NETCDF COMPUTE FAILED: {e}")
        import traceback
        logger.error(traceback.format_exc())
        raise HTTPException(status_code=500, detail=f"NetCDF computation failed: {str(e)}")


@app.post("/api/geoint/comparison")
async def geoint_comparison_analysis(request: Request):
    """
    GEOINT Comparison Analysis - Temporal change detection endpoint
    
    Supports TWO modes:
    
    1. QUERY MODE (new): Just provide user_query, we parse location + dates
       {
           "user_query": "How did Miami Beach surface reflectance change between 01/2020 and 01/2025?",
           "latitude": float (optional fallback),
           "longitude": float (optional fallback)
       }
       Returns: before/after tiles for map toggle + analysis summary
    
    2. SCREENSHOT MODE (legacy): Provide pre-captured screenshots + dates
       {
           "latitude": float,
           "longitude": float,
           "before_date": str,
           "after_date": str,
           "before_screenshot": str (base64),
           "after_screenshot": str (base64),
           ...
       }
    """
    try:
        body = await request.json()
        
        user_query = body.get("user_query")
        latitude = body.get("latitude")
        longitude = body.get("longitude")
        before_date = body.get("before_date")
        after_date = body.get("after_date")
        screenshot = body.get("screenshot")
        
        mode = "query" if user_query and not (before_date and after_date) else "direct"
        logger.info(f"[CHART] [COMPARISON-ANALYSIS] mode={mode} query='{user_query}' before={before_date} after={after_date}")
        
        # ================================================================
        # MODE 1: QUERY-BASED COMPARISON (new flow)
        # User provides natural language query, we parse and execute
        # ================================================================
        if user_query and not (before_date and after_date):
            logger.info(f"[SEARCH] QUERY MODE: Parsing query for comparison parameters...")
            logger.info(f"[MSG] User query: {user_query}")
            
            try:
                from geoint.comparison_agent import get_comparison_agent
                comparison_agent = get_comparison_agent()
                
                result = await comparison_agent.handle_query(
                    user_query=user_query,
                    latitude=latitude,
                    longitude=longitude,
                    session_id=body.get("session_id"),
                    screenshot_base64=screenshot,
                )
                
                logger.info(f"[OK] Comparison agent returned: status={result.get('status')}")
                
                # If it's a prompt response, return it directly
                if result.get("status") == "prompt":
                    return {
                        "status": "success",
                        "type": "prompt",
                        "message": result.get("message"),
                        "timestamp": datetime.utcnow().isoformat()
                    }
                
                # If it's an error, return with error status
                if result.get("status") == "error":
                    return {
                        "status": "error",
                        "message": result.get("message"),
                        "timestamp": datetime.utcnow().isoformat()
                    }
                
                # Success - return comparison result with before/after data
                return {
                    "status": "success",
                    "type": "comparison",
                    "result": result,
                    "timestamp": datetime.utcnow().isoformat()
                }
            except Exception as e:
                logger.warning(f"[WARN] Comparison agent failed: {e}, falling back to direct STAC approach")
                # --------------------------------------------------------
                # FALLBACK: Use process-comparison-query logic + direct
                # STAC search instead of the Agent Service comparison agent.
                # This avoids the separate AgentsClient that may fail when
                # Azure OpenAI has public access disabled.
                # --------------------------------------------------------
                try:
                    logger.info("[SEARCH] FALLBACK: Using direct STAC comparison approach")
                    # Step 1: Parse query with existing agents
                    if not semantic_translator:
                        raise RuntimeError("Semantic translator not initialized")
                    
                    collections = await semantic_translator.collection_mapping_agent(user_query)
                    stac_query = await semantic_translator.build_stac_query_agent(user_query, collections or [])
                    bbox = stac_query.get("bbox")
                    location_name = stac_query.get("location_name", "Unknown location")
                    
                    if not bbox:
                        raise RuntimeError(f"Could not resolve location from query: '{user_query}'")
                    
                    datetime_result = await semantic_translator.datetime_translation_agent(
                        query=user_query, collections=collections or [], mode="comparison"
                    )
                    if not datetime_result or "before" not in datetime_result or "after" not in datetime_result:
                        raise RuntimeError("Could not extract before/after timeframes from query")
                    
                    before_dt = datetime_result["before"]
                    after_dt = datetime_result["after"]
                    
                    # Step 2: Determine collection + asset
                    from geoint.comparison_tools import COLLECTION_MAP, ASSET_MAP, TILE_EXTRA_PARAMS, _get_scene_date, _format_date_display
                    
                    # Pick primary collection from parsed collections
                    primary_collection = None
                    if collections:
                        priority = ["modis-14A2-061", "modis-14A1-061", "sentinel-2-l2a", "landsat-c2-l2", "hls2-l30", "sentinel-1-rtc"]
                        for pc in priority:
                            if pc in collections:
                                primary_collection = pc
                                break
                        if not primary_collection:
                            primary_collection = collections[0]
                    else:
                        primary_collection = "sentinel-2-l2a"
                    
                    # Step 3: Execute dual STAC searches
                    from geoint.comparison_tools import _execute_stac_search
                    import asyncio as _asyncio
                    
                    before_result, after_result = await _asyncio.gather(
                        _execute_stac_search(primary_collection, bbox, before_dt, limit=3),
                        _execute_stac_search(primary_collection, bbox, after_dt, limit=3)
                    )
                    
                    before_features = before_result.get("features", [])
                    after_features = after_result.get("features", [])
                    
                    if not before_features and not after_features:
                        return {
                            "status": "error",
                            "message": f"No imagery found for {location_name} in either time period ({before_dt} / {after_dt}).",
                            "timestamp": datetime.utcnow().isoformat()
                        }
                    
                    center_lng = (bbox[0] + bbox[2]) / 2
                    center_lat = (bbox[1] + bbox[3]) / 2
                    
                    fallback_result = {
                        "status": "success",
                        "type": "comparison",
                        "location": location_name,
                        "analysis_type": "surface reflectance",
                        "bbox": bbox,
                        "center": {"lat": center_lat, "lng": center_lng},
                        "before": {
                            "datetime": before_dt,
                            "datetime_display": _format_date_display(before_dt),
                            "features_count": len(before_features),
                            "tile_urls": before_result.get("tile_urls", []),
                            "best_scene_date": _get_scene_date(before_features[0]) if before_features else None
                        },
                        "after": {
                            "datetime": after_dt,
                            "datetime_display": _format_date_display(after_dt),
                            "features_count": len(after_features),
                            "tile_urls": after_result.get("tile_urls", []),
                            "best_scene_date": _get_scene_date(after_features[0]) if after_features else None
                        },
                        "collection": primary_collection,
                        "analysis": f"**Comparison: {location_name}**\n\n"
                                    f"**Before:** {_format_date_display(before_dt)} ({len(before_features)} scenes)\n"
                                    f"**After:** {_format_date_display(after_dt)} ({len(after_features)} scenes)\n\n"
                                    f"Use the **BEFORE/AFTER** toggle buttons on the map to switch between time periods.",
                        "timestamp": datetime.utcnow().isoformat()
                    }
                    
                    logger.info(f"[OK] FALLBACK comparison succeeded: {location_name}, {primary_collection}, before={len(before_features)} after={len(after_features)} scenes")
                    return {
                        "status": "success",
                        "type": "comparison",
                        "result": fallback_result,
                        "timestamp": datetime.utcnow().isoformat()
                    }
                except Exception as fallback_err:
                    logger.error(f"[FAIL] Fallback comparison also failed: {fallback_err}", exc_info=True)
                    return {
                        "status": "error",
                        "message": f"Comparison query processing failed: {str(e)}",
                        "timestamp": datetime.utcnow().isoformat()
                    }
        
        # ================================================================
        # MODE 2: SCREENSHOT-BASED COMPARISON (legacy flow)
        # Requires pre-parsed dates and optional screenshots
        # ================================================================
        logger.info(f"[SNAP] SCREENSHOT MODE: Using provided dates and screenshots...")
        
        before_screenshot = body.get("before_screenshot")
        after_screenshot = body.get("after_screenshot")
        before_metadata = body.get("before_metadata")
        after_metadata = body.get("after_metadata")
        comparison_aspect = body.get("comparison_aspect")
        collection_id = body.get("collection_id")
        download_rasters = body.get("download_rasters", True)
        
        logger.info(f"[PIN] Location: ({latitude}, {longitude})")
        logger.info(f"[DATE] Before Date: {before_date}")
        logger.info(f"[DATE] After Date: {after_date}")
        logger.info(f"[SNAP] Before Screenshot: {'Provided' if before_screenshot else 'None'} ({len(before_screenshot) if before_screenshot else 0} chars)")
        logger.info(f"[SNAP] After Screenshot: {'Provided' if after_screenshot else 'None'} ({len(after_screenshot) if after_screenshot else 0} chars)")
        logger.info(f"[CHART] Before Metadata: {'Provided' if before_metadata else 'None'}")
        logger.info(f"[CHART] After Metadata: {'Provided' if after_metadata else 'None'}")
        logger.info(f"[MSG] User Query: {user_query}")
        logger.info(f"[TARGET] Comparison Aspect: {comparison_aspect}")
        logger.info(f"[LIST] Collection ID: {collection_id}")
        logger.info(f"⬇️  Download Rasters: {download_rasters}")
        
        # Validation
        logger.info("[SEARCH] Validating required parameters...")
        
        if latitude is None or longitude is None or not before_date or not after_date:
            logger.error("[FAIL] Missing required parameters")
            logger.error(f"   latitude: {latitude}")
            logger.error(f"   longitude: {longitude}")
            logger.error(f"   before_date: {before_date}")
            logger.error(f"   after_date: {after_date}")
            raise HTTPException(status_code=400, detail="Missing required parameters: latitude, longitude, before_date, after_date")
        
        if not (-90 <= latitude <= 90):
            logger.error(f"[FAIL] Invalid latitude: {latitude}")
            raise HTTPException(status_code=400, detail=f"Invalid latitude: {latitude}")
        
        if not (-180 <= longitude <= 180):
            logger.error(f"[FAIL] Invalid longitude: {longitude}")
            raise HTTPException(status_code=400, detail=f"Invalid longitude: {longitude}")
        
        # Screenshots are optional if raster download is enabled with collection_id
        has_screenshots = before_screenshot and after_screenshot
        can_download_rasters = download_rasters and collection_id
        
        logger.info(f"[OK] Has screenshots: {has_screenshots}")
        logger.info(f"[OK] Can download rasters: {can_download_rasters}")
        
        if not has_screenshots and not can_download_rasters:
            logger.error("[FAIL] Neither screenshots nor raster data source provided")
            raise HTTPException(
                status_code=400, 
                detail="Either screenshots (before_screenshot + after_screenshot) OR raster data (collection_id + download_rasters=true) must be provided"
            )
        
        logger.info("[OK] All validation checks passed")
        logger.info("")
        logger.info("[BOT] Calling comparison_analysis_agent...")
        logger.info(f"   Parameters:")
        logger.info(f"     - latitude: {latitude}")
        logger.info(f"     - longitude: {longitude}")
        logger.info(f"     - before_date: {before_date}")
        logger.info(f"     - after_date: {after_date}")
        logger.info(f"     - before_screenshot_base64: {'Provided' if before_screenshot else 'None'}")
        logger.info(f"     - after_screenshot_base64: {'Provided' if after_screenshot else 'None'}")
        logger.info(f"     - collection_id: {collection_id}")
        logger.info(f"     - download_rasters: {download_rasters}")
        
        # Call comparison_analysis_agent
        from geoint.agents import comparison_analysis_agent
        
        analysis_result = await comparison_analysis_agent(
            latitude=latitude,
            longitude=longitude,
            before_date=before_date,
            after_date=after_date,
            before_screenshot_base64=before_screenshot,
            after_screenshot_base64=after_screenshot,
            before_metadata=before_metadata,
            after_metadata=after_metadata,
            user_query=user_query,
            comparison_aspect=comparison_aspect,
            collection_id=collection_id,  # NEW
            download_rasters=download_rasters  # NEW
        )
        
        text_len = len(analysis_result.get('text', '')) if isinstance(analysis_result, dict) else 0
        logger.info(f"[CHART] [COMPARISON-ANALYSIS] [OK] Done — text={text_len} chars")
        
        return {
            "status": "success",
            "result": analysis_result,
            "timestamp": datetime.utcnow().isoformat()
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"[CHART] [COMPARISON-ANALYSIS] [FAIL] {type(e).__name__}: {e}")
        logger.exception("Full traceback:")
        raise HTTPException(status_code=500, detail=f"Comparison failed: {str(e)}")

@app.post("/api/geoint/animation")
async def geoint_animation_analysis(request: Request):
    """
    GEOINT Animation Generation - Thin wrapper around animation_generation_agent
    """
    try:
        body = await request.json()
        latitude = body.get("latitude")
        longitude = body.get("longitude")
        start_date = body.get("start_date")
        end_date = body.get("end_date")
        collection_id = body.get("collection_id", "sentinel-2-l2a")
        user_query = body.get("user_query")
        
        # Validation
        if latitude is None or longitude is None or not start_date or not end_date:
            raise HTTPException(status_code=400, detail="Missing required parameters")
        if not (-90 <= latitude <= 90):
            raise HTTPException(status_code=400, detail=f"Invalid latitude")
        if not (-180 <= longitude <= 180):
            raise HTTPException(status_code=400, detail=f"Invalid longitude")
        
        logger.info(f"Animation endpoint: ({latitude}, {longitude})")
        
        # Call animation_generation_agent (new agent-based architecture)
        from geoint.agents import animation_generation_agent
        
        analysis_result = await animation_generation_agent(
            latitude=latitude,
            longitude=longitude,
            start_date=start_date,
            end_date=end_date,
            collection_id=collection_id,
            user_query=user_query
        )
        
        logger.info("Animation agent completed")
        
        return {
            "status": "success",
            "result": analysis_result,
            "timestamp": datetime.utcnow().isoformat()
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Animation endpoint failed: {e}")
        raise HTTPException(status_code=500, detail=f"Animation failed: {str(e)}")

# Orchestrator endpoint for calling multiple GEOINT agents at once
@app.post("/api/geoint/orchestrate")
async def geoint_orchestrator_endpoint(request: Request):
    """
    GEOINT Orchestrator - Calls multiple agents in parallel
    
    Request body:
    {
        "latitude": float,
        "longitude": float,
        "modules": ["terrain", "mobility", ...],
        "screenshot": str (optional),
        "user_query": str (optional),
        "radius_miles": float (optional)
    }
    """
    try:
        body = await request.json()
        latitude = body.get("latitude")
        longitude = body.get("longitude")
        modules = body.get("modules", ["terrain", "mobility"])
        screenshot = body.get("screenshot")
        user_query = body.get("user_query")
        radius_miles = body.get("radius_miles", 5.0)
        
        # Validation
        if latitude is None or longitude is None:
            raise HTTPException(status_code=400, detail="Missing latitude or longitude")
        if not (-90 <= latitude <= 90):
            raise HTTPException(status_code=400, detail=f"Invalid latitude")
        if not (-180 <= longitude <= 180):
            raise HTTPException(status_code=400, detail=f"Invalid longitude")
        if not modules:
            raise HTTPException(status_code=400, detail="No modules specified")
        
        logger.info(f"Orchestrator endpoint: ({latitude}, {longitude}), modules={modules}")
        
        # Call geoint_orchestrator (new agent-based architecture)
        from geoint.agents import geoint_orchestrator
        
        result = await geoint_orchestrator(
            latitude=latitude,
            longitude=longitude,
            modules=modules,
            screenshot_base64=screenshot,
            user_query=user_query,
            radius_miles=radius_miles,
            **body  # Pass any additional kwargs
        )
        
        logger.info("Orchestrator completed")
        
        return {
            "status": "success",
            "result": result,
            "timestamp": datetime.utcnow().isoformat()
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Orchestrator failed: {e}")
        raise HTTPException(status_code=500, detail=f"Orchestration failed: {str(e)}")

@app.get("/api/debug/location/{location}")
async def debug_location_resolver(location: str):
    """Debug endpoint to test location resolver"""
    try:
        from location_resolver import EnhancedLocationResolver
        resolver = EnhancedLocationResolver()
        
        # Test preprocessing
        preprocessed = resolver._preprocess_location_query(location)
        
        # Test resolution
        bbox = await resolver.resolve_location_to_bbox(location, "region")
        
        return {
            "original_query": location,
            "preprocessed_query": preprocessed,
            "resolved_bbox": bbox,
            "timestamp": datetime.utcnow().isoformat()
        }
    except Exception as e:
        logger.error(f"Location resolver debug failed: {str(e)}")
        logger.error(traceback.format_exc())
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/debug/location/{location}")
async def debug_location_resolver(location: str):
    """Debug endpoint to test location resolver"""
    try:
        from location_resolver import EnhancedLocationResolver
        resolver = EnhancedLocationResolver()
        
        # Test preprocessing
        preprocessed = resolver._preprocess_location_query(location)
        
        # Test resolution
        bbox = await resolver.resolve_location_to_bbox(location, "region")
        
        return {
            "original_query": location,
            "preprocessed_query": preprocessed,
            "resolved_bbox": bbox,
            "timestamp": datetime.utcnow().isoformat()
        }
    except Exception as e:
        logger.error(f"Location resolver debug failed: {str(e)}")
        logger.error(traceback.format_exc())
        raise HTTPException(
            status_code=500,
            detail=f"Location resolver debug failed: {str(e)}"
        )

@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    """Global exception handler"""
    logger.error(f"Unhandled exception: {str(exc)}")
    logger.error(traceback.format_exc())
    return JSONResponse(
        status_code=500,
        content={
            "error": "Internal server error",
            "message": str(exc),
            "timestamp": datetime.utcnow().isoformat()
        }
    )

# Note: Container startup uses Dockerfile CMD: uvicorn fastapi_app:app --host 0.0.0.0 --port 8080
# The if __name__ == "__main__" block has been removed to prevent port conflicts
