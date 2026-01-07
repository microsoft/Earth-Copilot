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
from hybrid_rendering_system import HybridRenderingSystem  # 🎨 Comprehensive rendering system
from tile_selector import TileSelector  # 🎯 Smart tile selection and ranking
from quickstart_cache import (
    is_quickstart_query, 
    get_quickstart_classification, 
    get_quickstart_location,
    get_quickstart_stats
)  # 🚀 Pre-computed cache for demo queries

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
# �🔍 PIPELINE LOGGING HELPER - Structured logging for debugging queries
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
    
    # 🔬 INSTANT TRACING: Also collect for API response
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
# 🎯 SMART TILE DEDUPLICATION
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
        logging.debug(f"🔄 Dedup: Skipping - not optical collection: {collections}")
        return False
    
    # Check if any collection should never be deduplicated
    should_skip = any(
        any(skip in coll.lower() for skip in SKIP_DEDUP_COLLECTIONS)
        for coll in collections
    )
    
    if should_skip:
        logging.debug(f"🔄 Dedup: Skipping - fire/SAR collection: {collections}")
        return False
    
    # Check for temporal keywords in query
    if original_query:
        query_lower = original_query.lower()
        has_temporal_intent = any(kw in query_lower for kw in TEMPORAL_KEYWORDS)
        if has_temporal_intent:
            logging.info(f"🔄 Dedup: Skipping - temporal query detected: '{original_query[:50]}...'")
            return False
    
    logging.info(f"✅ Dedup: Will deduplicate optical tiles for: {collections}")
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
            logging.debug(f"🔄 Dedup: Skipping duplicate grid {grid_id} (feature: {feature.get('id', 'unknown')[:50]})")
    
    if len(deduplicated) < original_count:
        logging.info(f"🎯 TILE DEDUPLICATION: {original_count} → {len(deduplicated)} tiles (removed {original_count - len(deduplicated)} duplicates)")
        logging.info(f"🎯 Unique grid cells: {list(seen_grids)[:10]}{'...' if len(seen_grids) > 10 else ''}")
    
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
    logging.info("✅ Planetary Computer authentication available")
except ImportError as e:
    PLANETARY_COMPUTER_AVAILABLE = False
    logging.warning(f"⚠️ Planetary Computer authentication not available: {e}")

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
    logging.info(f"✅ PC metadata loaded: {total_collections} collections from PC repository")
except ImportError as e:
    PC_METADATA_AVAILABLE = False
    logging.warning(f"⚠️ PC config loader not available: {e}")
    
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
logging.info("✅ GEOINT endpoints available (lazy import mode)")

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
logger.info(f"🔒 CORS configured for origins: {cors_origins}")

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Mount static files for React frontend (if static directory exists)
static_dir = os.path.join(os.path.dirname(__file__), "static")
if os.path.exists(static_dir):
    from fastapi.staticfiles import StaticFiles
    
    # Mount static assets at root level to match React build paths
    app.mount("/assets", StaticFiles(directory=os.path.join(static_dir, "assets")), name="assets")
    logger.info(f"✅ Mounted static assets from: {os.path.join(static_dir, 'assets')}")
    
    # Also mount full static directory for any other static files
    app.mount("/static", StaticFiles(directory=static_dir), name="static")
    logger.info(f"✅ Mounted static files from: {static_dir}")
    
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
            logger.warning("⚠️  Serving legacy pc_collections_metadata.json - should migrate to unified config")
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
    logger.warning(f"⚠️ Static directory not found: {static_dir}")
    
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
    logger.info(f"🔍 Looking for pc_rendering_config.json at: {json_path}")
    logger.info(f"📁 File exists: {os.path.exists(json_path)}")
    if os.path.exists(json_path):
        logger.info(f"✅ Serving pc_rendering_config.json from {json_path}")
        return FileResponse(json_path, media_type="application/json")
    from fastapi import HTTPException
    logger.error(f"❌ PC rendering config not found at {json_path}")
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

# STAC endpoints configuration
STAC_ENDPOINTS = {
    "planetary_computer": "https://planetarycomputer.microsoft.com/api/stac/v1/search",
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
        logger.info("=" * 80)
        logger.info(f"🔍 STAC SEARCH INITIATED")
        logger.info("=" * 80)
        logger.info(f"🌐 Endpoint: {stac_endpoint} -> {stac_url}")
        logger.info(f"📦 Collections: {stac_query.get('collections', [])}")
        logger.info(f"🗺️  BBox: {stac_query.get('bbox', 'NONE')}")
        logger.info(f"📅 DateTime: {stac_query.get('datetime', 'NONE')}")
        logger.info(f"☁️  Cloud Filter (query): {stac_query.get('query', 'NONE')}")
        logger.info(f"🔢 Limit: {stac_query.get('limit', 'default')}")
        logger.info(f"🔎 Full Query: {json.dumps(stac_query, indent=2)}")
        logger.info("=" * 80)
        
        # NOTE: We do NOT validate coverage proactively because STAC collection extents
        # represent "data exists somewhere in this region" not "complete coverage".
        # Instead, we let the search run and handle empty results with helpful messages.
        
        timeout = aiohttp.ClientTimeout(total=60)
        
        async with aiohttp.ClientSession(timeout=timeout) as session:
            logger.info("🔗 Opening HTTP session...")
            async with session.post(stac_url, json=stac_query) as response:
                logger.info(f"📡 Received HTTP response: {response.status}")
                
                if response.status == 200:
                    stac_response = await response.json()
                    features = stac_response.get('features', [])
                    
                    logger.info("=" * 80)
                    logger.info(f"✅ STAC SEARCH - RESULTS RECEIVED")
                    logger.info("=" * 80)
                    logger.info(f"📊 Total Features Found: {len(features)}")
                    
                    # ====================================================================
                    # 📋 LOG QUERY PARAMETERS (what was requested)
                    # ====================================================================
                    logger.info("=" * 80)
                    logger.info("📥 STAC QUERY - REQUEST PARAMETERS")
                    logger.info(f"🗂️  Collections Requested: {stac_query.get('collections', [])}")
                    logger.info(f"📍 BBox Requested: {stac_query.get('bbox', 'NONE')}")
                    logger.info(f"📅 DateTime Requested: {stac_query.get('datetime', 'NONE')}")
                    logger.info("=" * 80)
                    
                    # ====================================================================
                    # 📋 LOG RESPONSE COLLECTIONS & SPATIAL EXTENT (what was returned)
                    # ====================================================================
                    if features:
                        # Extract unique collections from results
                        collections_returned = list(set(f.get('collection', 'unknown') for f in features))
                        logger.info("=" * 80)
                        logger.info("📤 STAC RESPONSE - RETURNED DATA")
                        logger.info(f"🗂️  Collections Returned: {collections_returned}")
                        logger.info(f"📊 Items per Collection:")
                        for coll in collections_returned:
                            count = sum(1 for f in features if f.get('collection') == coll)
                            logger.info(f"   • {coll}: {count} items")
                        
                        # Extract spatial extent (bounding box of all returned features)
                        all_bboxes = []
                        for feature in features:
                            geom = feature.get('geometry', {})
                            bbox = feature.get('bbox')
                            if bbox:
                                all_bboxes.append(bbox)
                        
                        if all_bboxes:
                            # Calculate combined extent
                            min_lons = [b[0] for b in all_bboxes]
                            min_lats = [b[1] for b in all_bboxes]
                            max_lons = [b[2] for b in all_bboxes]
                            max_lats = [b[3] for b in all_bboxes]
                            
                            returned_extent = [
                                min(min_lons),
                                min(min_lats),
                                max(max_lons),
                                max(max_lats)
                            ]
                            
                            logger.info(f"📍 Spatial Extent of Results:")
                            logger.info(f"   Returned BBox: {returned_extent}")
                            logger.info(f"   West:  {returned_extent[0]:.6f}")
                            logger.info(f"   South: {returned_extent[1]:.6f}")
                            logger.info(f"   East:  {returned_extent[2]:.6f}")
                            logger.info(f"   North: {returned_extent[3]:.6f}")
                            
                            # Compare with requested bbox if available
                            requested_bbox = stac_query.get('bbox')
                            if requested_bbox:
                                logger.info(f"🔍 BBox Comparison:")
                                logger.info(f"   Requested: {requested_bbox}")
                                logger.info(f"   Returned:  {returned_extent}")
                        
                        logger.info("=" * 80)
                    
                    # Extract and log the date range of returned features
                    if features:
                        dates = []
                        for feature in features:
                            props = feature.get('properties', {})
                            dt = props.get('datetime')
                            if dt:
                                dates.append(dt)
                        
                        if dates:
                            dates_sorted = sorted(dates)
                            earliest = dates_sorted[0][:10] if dates_sorted else "Unknown"
                            latest = dates_sorted[-1][:10] if dates_sorted else "Unknown"
                            
                            logger.info(f"📅 RETURNED DATE RANGE:")
                            logger.info(f"   ├─ Earliest: {earliest}")
                            logger.info(f"   └─ Latest:   {latest}")
                            logger.info(f"📅 Sample Item Dates (first 5):")
                            for i, date in enumerate(dates_sorted[:5]):
                                logger.info(f"   {i+1}. {date}")
                        else:
                            # For MODIS or other items without datetime property
                            item_ids = [f.get('id', '') for f in features[:5]]
                            logger.info(f"ℹ️ Items have no 'datetime' property (may be encoded in item ID)")
                            logger.info(f"📅 Sample Item IDs (first 5): {item_ids}")
                            
                            # Try to parse MODIS dates from item IDs (format: modis-14A1-061.A2024169)
                            try:
                                parsed_dates = []
                                for item in features[:10]:  # Check first 10 items
                                    item_id = item.get('id', '')
                                    # MODIS format: A{YEAR}{DAY_OF_YEAR}
                                    if '.A' in item_id:
                                        parts = item_id.split('.A')
                                        if len(parts) > 1 and len(parts[1]) >= 7:
                                            year = parts[1][:4]
                                            day_of_year = parts[1][4:7]
                                            try:
                                                date_obj = datetime.strptime(f"{year}{day_of_year}", "%Y%j")
                                                parsed_dates.append((item_id, date_obj.strftime("%Y-%m-%d")))
                                            except:
                                                pass
                                
                                if parsed_dates:
                                    logger.info(f"📅 Parsed MODIS Dates from Item IDs:")
                                    for item_id, date_str in parsed_dates[:5]:
                                        logger.info(f"   {item_id} → {date_str}")
                                    
                                    # Show date range
                                    dates_only = [d[1] for d in parsed_dates]
                                    logger.info(f"📅 Date range from parsed IDs: {min(dates_only)} to {max(dates_only)}")
                            except Exception as e:
                                logger.debug(f"Could not parse MODIS dates: {e}")
                    
                    logger.info("=" * 80)
                    
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
                    
                    # 🎯 SMART TILE DEDUPLICATION
                    # Remove duplicate grid cells (keep most recent per location)
                    # Only applies to optical imagery without explicit temporal queries
                    deduplicated_features = deduplicate_tiles_by_grid(enhanced_features, original_query)
                    
                    # 🎯 TILE SELECTION: Limit to optimal number of tiles to prevent visual clutter
                    # This selects the best tiles based on recency, cloud cover, and coverage
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
                            logger.info(f"🌍 Country-scale area ({area_degrees:.1f} sq deg) → max_tiles={max_tiles}")
                        elif area_degrees > 5:  # Large region (e.g., California, large state)
                            max_tiles = min(60, max(30, tiles_for_coverage))  # 30-60 tiles
                            logger.info(f"🗺️ Large region ({area_degrees:.1f} sq deg) → max_tiles={max_tiles}")
                        elif area_degrees > 1.0:  # Medium region (multi-city area)
                            max_tiles = min(30, max(15, tiles_for_coverage))  # 15-30 tiles
                        elif area_degrees > 0.1:  # Small region (single city area)
                            max_tiles = 15
                        else:  # Point/small area
                            max_tiles = 10
                    
                    # Apply intelligent tile selection
                    selected_features = TileSelector.select_best_tiles(
                        features=deduplicated_features,
                        query_bbox=bbox,
                        collections=collections,
                        max_tiles=max_tiles,
                        query=original_query
                    )
                    
                    logger.info(f"🎯 TILE SELECTION: {len(deduplicated_features)} → {len(selected_features)} tiles (max={max_tiles})")
                    
                    result = {
                        "success": True,
                        "results": {
                            "type": "FeatureCollection",
                            "features": selected_features
                        },
                        "search_metadata": {
                            "total_found": len(features),
                            "total_after_dedup": len(deduplicated_features),
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
                    logger.error(f"❌ STAC API error {response.status}: {error_text}")
                    return {
                        "success": False,
                        "error": f"STAC API returned {response.status}: {error_text}",
                        "results": {"type": "FeatureCollection", "features": []}
                    }
                    
    except Exception as e:
        logger.error(f"❌ STAC search error: {e}")
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
    
    logger.info("🚀 EARTH COPILOT CONTAINER STARTING UP")
    logger.info("=" * 60)
    
    try:
        # Initialize Semantic Translator components with environment variables
        azure_openai_endpoint = os.getenv("AZURE_OPENAI_ENDPOINT", "")
        azure_openai_api_key = os.getenv("AZURE_OPENAI_API_KEY", "")
        azure_openai_deployment = os.getenv("AZURE_OPENAI_DEPLOYMENT_NAME", "gpt-5")
        use_managed_identity = os.getenv("USE_MANAGED_IDENTITY", "false").lower() == "true"
        
        logger.info(f"🔐 Environment check - Endpoint: {'✓' if azure_openai_endpoint else '✗'}, Key: {'✓' if azure_openai_api_key else '✗'}, Model: {azure_openai_deployment}, ManagedIdentity: {use_managed_identity}")
        
        # Initialize with API key if provided
        if azure_openai_endpoint and azure_openai_api_key:
            semantic_translator = SemanticQueryTranslator(
                azure_openai_endpoint=azure_openai_endpoint,
                azure_openai_api_key=azure_openai_api_key,
                model_name=azure_openai_deployment
            )
            global_translator = semantic_translator  # For session management
            SEMANTIC_KERNEL_AVAILABLE = True
            logger.info("✅ Earth Copilot API initialized successfully with Semantic Translator (API Key)")
        # Try managed identity if endpoint provided but no API key
        elif azure_openai_endpoint and use_managed_identity:
            try:
                from azure.identity import DefaultAzureCredential
                logger.info("🔑 Attempting managed identity authentication for Azure OpenAI...")
                credential = DefaultAzureCredential()
                # Get token to verify credential works
                token = credential.get_token("https://cognitiveservices.azure.com/.default")
                logger.info("✅ Successfully obtained Azure AD token for Cognitive Services")
                
                semantic_translator = SemanticQueryTranslator(
                    azure_openai_endpoint=azure_openai_endpoint,
                    azure_openai_api_key=None,  # No API key - will use credential
                    model_name=azure_openai_deployment,
                    azure_credential=credential  # Pass credential for managed identity
                )
                global_translator = semantic_translator  # For session management
                SEMANTIC_KERNEL_AVAILABLE = True
                logger.info("✅ Earth Copilot API initialized successfully with Semantic Translator (Managed Identity)")
            except Exception as e:
                logger.error(f"❌ Failed to initialize with managed identity: {e}")
                logger.warning("⚠️ Running in limited mode - no Azure OpenAI access")
                semantic_translator = None
                global_translator = None
                SEMANTIC_KERNEL_AVAILABLE = False
        else:
            logger.warning("⚠️ Azure OpenAI credentials not provided - running in limited mode")
            semantic_translator = None
            global_translator = None
            SEMANTIC_KERNEL_AVAILABLE = False
            
        # GEOINT endpoints use lazy imports - no initialization needed here
        logger.info("✅ GEOINT endpoints ready (lazy import mode)")

        # Initialize RouterAgent for intelligent query classification
        try:
            from geoint.router_agent import get_router_agent
            router_agent = get_router_agent()
            if global_translator:
                router_agent.set_semantic_translator(global_translator)
            logger.info("✅ RouterAgent initialized for intelligent query routing")
        except Exception as e:
            logger.warning(f"⚠️ RouterAgent initialization failed: {e} - will use fallback classification")
            router_agent = None
        
        # Log quick start cache status
        qs_stats = get_quickstart_stats()
        logger.info(f"🚀 Quick Start Cache: {qs_stats['total_queries']} queries pre-computed")
        logger.info(f"   Collections: {len(qs_stats['collections_covered'])} unique")
        
        logger.info("=" * 60)
        logger.info("🎯 EARTH COPILOT CONTAINER READY")
        logger.info("🎯 Available endpoints:")
        logger.info("🎯   GET  /api/health             - Health check and diagnostics")
        logger.info("🎯   POST /api/query              - Unified natural language query processing")
        logger.info("🎯   POST /api/stac-search        - Direct Planetary Computer STAC search")
        logger.info("🎯   POST /api/veda-search        - Direct NASA VEDA STAC search")
        logger.info("🎯   POST /api/session-reset      - Reset conversation context")
        logger.info("🎯   GET  /api/config             - Configuration for frontend")
        logger.info("🎯   POST /api/geoint/mobility    - GEOINT Mobility Analysis")
        logger.info("🎯   POST /api/geoint/terrain     - GEOINT Terrain Analysis (GPT-5 Vision)")
        logger.info("🎯   POST /api/geoint/building-damage - GEOINT Building Damage Assessment")
        logger.info("🎯   POST /api/geoint/comparison  - GEOINT Comparison Analysis")
        logger.info("🎯   POST /api/geoint/animation   - GEOINT Animation Generation")
        logger.info("=" * 60)
        
        # Log all registered routes for debugging
        logger.info("🔍 Registered FastAPI routes:")
        for route in app.routes:
            if hasattr(route, 'methods') and hasattr(route, 'path'):
                methods = ','.join(route.methods)
                logger.info(f"   {methods:8s} {route.path}")
        logger.info("=" * 60)
            
    except Exception as e:
        logger.error(f"❌ Failed to initialize components: {str(e)}")
        logger.warning("⚠️ Running in limited mode")
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
    
    logger.info(f"🔍 Detected collections for '{query}': {unique_collections}")
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
                response_parts.append(f"• {suggestion}")
        else:
            response_parts.append("\n**Try:** adjusting your search area, expanding the time range, or checking if the location name is spelled correctly.")
    
    # SCENARIO 2: STAC returned results, but spatial filter removed them
    elif raw_count > 0 and spatial_count == 0:
        response_parts.append(f"I found {raw_count} satellite images in the catalog, but none had sufficient coverage of your requested area.")
        response_parts.append("\n**This usually means:**")
        response_parts.append("• The imagery tiles only partially overlap your location (less than 10% coverage)")
        response_parts.append("• Your search area might be at the edge of the satellite's coverage zone")
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
    🆕 Automatically try progressively relaxed queries to find available alternatives.
    
    Strategy:
    1. Keep location FIXED (highest priority)
    2. Try relaxing filters in order:
       - Cloud cover (10% → 30% → 50%)
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
    logger.info("🔄 Attempting to find alternative results with relaxed filters...")
    
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
                
            logger.info(f"🌤️ Trying alternative with cloud cover <{cloud_threshold}%...")
            
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
                                logger.info(f"✅ Found {len(selected_features)} results with cloud cover <{cloud_threshold}%")
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
                logger.warning(f"⚠️ Alternative query failed: {e}")
                continue
    
    # RELAXATION 2: Try expanding date range
    datetime_str = original_stac_query.get("datetime", "")
    if datetime_str and "/" in datetime_str:
        try:
            from datetime import datetime as dt, timedelta
            start, end = datetime_str.split("/")
            start_dt = dt.fromisoformat(start.replace("Z", ""))
            end_dt = dt.fromisoformat(end.replace("Z", ""))
            current_days = (end_dt - start_dt).days
            
            # Try expanding backwards
            for expand_days in [30, 60, 90]:
                if current_days >= expand_days:
                    continue
                    
                logger.info(f"📅 Trying alternative with {expand_days}-day date range...")
                
                new_start = end_dt - timedelta(days=expand_days)
                new_datetime = f"{new_start.isoformat()}Z/{end_dt.isoformat()}Z"
                
                alt_query = original_stac_query.copy()
                alt_query["datetime"] = new_datetime
                
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
                                    logger.info(f"✅ Found {len(selected_features)} results with {expand_days}-day range")
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
                    logger.warning(f"⚠️ Date expansion failed: {e}")
                    continue
        except Exception as e:
            logger.warning(f"⚠️ Date parsing failed: {e}")
    
    # RELAXATION 3: Try related collections (if applicable)
    # NOTE: Removed HLS → Landsat fallback - when user explicitly requests HLS,
    # they should get HLS only, not mixed results with Landsat
    # The 500 errors on some HLS tiles are a Planetary Computer issue, not a collection issue
    original_collections = original_stac_query.get("collections", [])
    alternative_collection_sets = []
    
    # Only fall back for Sentinel → Landsat (same optical imagery category)
    # Do NOT fall back for HLS - user explicitly requested harmonized data
    if any("sentinel" in c.lower() for c in original_collections) and not any("hls" in c.lower() for c in original_collections):
        alternative_collection_sets.append({
            "collections": ["landsat-c2-l2"],
            "name": "Landsat"
        })
    
    for alt_collections in alternative_collection_sets:
        logger.info(f"🛰️ Trying alternative collections: {alt_collections['name']}...")
        
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
                            logger.info(f"✅ Found {len(selected_features)} results with {alt_collections['name']}")
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
            logger.warning(f"⚠️ Alternative collection search failed: {e}")
            continue
    
    # No alternatives found
    logger.info("❌ No alternatives found with relaxed filters")
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
        logger.info(f"📅 Adding datetime filter to STAC query: {stac_params['datetime']}")
    
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
        logger.info(f"📊 Adding sortby to STAC query: {stac_params['sortby']}")
    else:
        # Default: sort by datetime descending to get most recent imagery first
        query['sortby'] = [{"field": "datetime", "direction": "desc"}]
        logger.info(f"📊 Adding default sortby (datetime desc) to get most recent imagery")
    
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
    logger.info(f"🧹 clean_tilejson_urls() called with stac_results type: {type(stac_results)}")
    logger.info(f"🧹 stac_results keys: {list(stac_results.keys()) if isinstance(stac_results, dict) else 'Not a dict'}")
    
    try:
        features = stac_results.get("features", [])
        logger.info(f"🧹 Found {len(features)} features to process")
        
        if not features:
            logger.info("🧹 No features found, returning original stac_results")
            return stac_results
        
        cleaned_features = []
        for i, feature in enumerate(features):
            collection_id = feature.get("collection", "unknown")
            item_id = feature.get("id", "unknown")
            logger.info("=" * 80)
            logger.info(f"🧹 PROCESSING FEATURE {i+1}/{len(features)}")
            logger.info("=" * 80)
            logger.info(f"🆔 Item ID: {item_id}")
            logger.info(f"📦 Collection: {collection_id}")
            
            # Create a deep copy to avoid modifying the original
            cleaned_feature = feature.copy()
            
            # Get rendering config from PC repository
            config = HybridRenderingSystem.get_render_config(collection_id)
            
            if config:
                params = config.to_dict()
                logger.info(f"🎨 PC Rendering Config Found:")
                logger.info(f"   - colormap_name: {params.get('colormap_name')}")
                logger.info(f"   - rescale: {params.get('rescale')}")
                logger.info(f"   - color_formula: {params.get('color_formula')}")
                logger.info(f"   - assets: {params.get('assets')}")
            else:
                logger.warning(f"⚠️ No PC config found for {collection_id}, using STAC default URL")
            
            # Check if feature has assets
            if "assets" in cleaned_feature and cleaned_feature["assets"]:
                logger.info(f"🧹 Feature {item_id} has assets: {list(cleaned_feature['assets'].keys())}")
                cleaned_assets = {}
                has_tilejson = False
                
                for asset_name, asset_data in cleaned_feature["assets"].items():
                    cleaned_asset = asset_data.copy()
                    
                    # Process tilejson asset URL
                    if asset_name == "tilejson" and "href" in cleaned_asset:
                        has_tilejson = True
                        original_url = cleaned_asset["href"]
                        logger.info(f"🧹 Found tilejson URL in {item_id}: {original_url}")
                        
                        # 🛡️ EXPRESSION-BASED COLLECTIONS: Keep original STAC tilejson URL
                        # Collections like alos-palsar-mosaic use expressions with multiple rescale values.
                        # The STAC tilejson already has the correct rendering params - don't override!
                        expression_collections = ["alos-palsar-mosaic", "sentinel-1-grd", "sentinel-1-rtc"]
                        if collection_id in expression_collections and "expression=" in original_url:
                            logger.info(f"🛡️ Keeping original STAC tilejson for expression-based collection {collection_id}")
                            # Keep original URL - don't modify
                        elif config:
                            # ✅ BUILD TITILER URL FROM SCRATCH using PC configs
                            titiler_url = HybridRenderingSystem.build_titiler_tilejson_url(item_id, collection_id)
                            cleaned_asset["href"] = titiler_url
                            logger.info(f"🧹 ✅ Built TiTiler URL from PC config for {collection_id}")
                            logger.info(f"🧹    Original (STAC): {original_url}")
                            logger.info(f"🧹    PC TiTiler URL: {titiler_url}")
                        else:
                            # No PC config - keep original URL
                            logger.info(f"🧹 ⚠️ No PC config, keeping STAC URL for {collection_id}")
                    
                    cleaned_assets[asset_name] = cleaned_asset
                
                # ✅ FIX: Generate tilejson URL for collections that don't have it in STAC response
                # Collections like MTBS, JRC-GSW, etc. don't have tilejson asset but CAN be rendered via TiTiler
                if not has_tilejson and config:
                    logger.info(f"🧹 📍 No tilejson asset found for {item_id}, generating TiTiler URL...")
                    titiler_url = HybridRenderingSystem.build_titiler_tilejson_url(item_id, collection_id)
                    cleaned_assets["tilejson"] = {
                        "href": titiler_url,
                        "type": "application/json",
                        "roles": ["tiles"],
                        "title": "TileJSON for visualization (auto-generated)"
                    }
                    logger.info(f"🧹 ✅ Generated tilejson URL for {collection_id}: {titiler_url[:100]}...")
                elif not has_tilejson:
                    logger.warning(f"🧹 ⚠️ No tilejson and no PC config for {collection_id} - cannot visualize")
                
                cleaned_feature["assets"] = cleaned_assets
            else:
                logger.info(f"🧹 Feature {item_id} has no assets or empty assets")
            
            cleaned_features.append(cleaned_feature)
        
        # Return cleaned results
        cleaned_results = stac_results.copy()
        cleaned_results["features"] = cleaned_features
        
        # ========================================================================
        # 📊 FINAL URL ENHANCEMENT SUMMARY
        # ========================================================================
        logger.info("=" * 80)
        logger.info(f"🧹 URL CLEANING COMPLETED")
        logger.info("=" * 80)
        logger.info(f"✅ Processed {len(cleaned_features)} features")
        logger.info(f"📦 Collection: {cleaned_features[0].get('collection') if cleaned_features else 'N/A'}")
        logger.info(f"🔗 First Feature URL: {cleaned_features[0].get('assets', {}).get('tilejson', {}).get('href', 'N/A')[:150]}..." if cleaned_features else "N/A")
        logger.info("=" * 80)
        return cleaned_results
        
    except Exception as e:
        logger.error(f"🧹 ❌ Error cleaning tilejson URLs: {e}")
        logger.exception("Full exception details:")
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
                logger.info(f"🎨 Injecting assets: {params['assets']}")
            else:
                # For single asset, set assets parameter
                params["assets"] = assets
                logger.info(f"🎨 Injecting asset: {assets}")
        
        # Add rescale if specified (critical for SAR and MODIS)
        if config_dict.get("rescale") is not None:
            min_val, max_val = config_dict["rescale"]
            params["rescale"] = f"{min_val},{max_val}"
            logger.info(f"🎨 Injecting rescale: {params['rescale']}")
        
        # Add colormap for single-band data (SAR, MODIS vegetation, elevation)
        if config_dict.get("colormap_name"):
            params["colormap_name"] = config_dict["colormap_name"]
            logger.info(f"🎨 Injecting colormap: {params['colormap_name']}")
        
        # Add bidx if specified
        if config_dict.get("bidx"):
            params["bidx"] = str(config_dict["bidx"])
            logger.info(f"🎨 Injecting bidx: {params['bidx']}")
        
        # Add resampling method
        if config_dict.get("resampling"):
            params["resampling"] = config_dict["resampling"]
            logger.info(f"🎨 Injecting resampling: {params['resampling']}")
        
        # Add color formula if specified (for Landsat adjustments)
        if config_dict.get("color_formula"):
            # URL encode the formula
            formula = config_dict["color_formula"].replace(" ", "+").replace(",", "%2C")
            params["color_formula"] = formula
            logger.info(f"🎨 Injecting color_formula: {config_dict['color_formula']}")
        
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
        logger.error(f"❌ Error enhancing tilejson URL for {collection_id}: {e}")
        logger.exception("Full exception details:")
        return url  # Return original URL if enhancement fails

@app.get("/api/health")
async def health_check():
    """Enhanced health check endpoint with actual connectivity tests (ported from Router Function App)"""
    logger.info("🏥 HEALTH CHECK: Enhanced endpoint called")
    
    try:
        # Get current timestamp
        current_time = datetime.now().strftime("%m/%d/%Y %I:%M:%S %p")
        logger.info(f"🏥 HEALTH CHECK: Current time: {current_time}")
        
        # Initialize status tracking
        all_healthy = True
        connectivity_tests = {}
        
        # Check basic dependencies first
        logger.info("🏥 HEALTH CHECK: Checking basic dependencies...")
        use_managed_identity = os.getenv("USE_MANAGED_IDENTITY", "false").lower() == "true"
        basic_status = {
            "semantic_kernel": SEMANTIC_KERNEL_AVAILABLE,
            "geoint": GEOINT_AVAILABLE,
            "azure_openai_endpoint": bool(os.getenv("AZURE_OPENAI_ENDPOINT")),
            "azure_openai_api_key": bool(os.getenv("AZURE_OPENAI_API_KEY")),
            "azure_openai_deployment": bool(os.getenv("AZURE_OPENAI_DEPLOYMENT_NAME")),
            "azure_maps_key": bool(os.getenv("AZURE_MAPS_SUBSCRIPTION_KEY")),
            "use_managed_identity": use_managed_identity
        }
        
        # Test Azure OpenAI connectivity
        logger.info("🏥 HEALTH CHECK: Testing Azure OpenAI connectivity...")
        try:
            if SEMANTIC_KERNEL_AVAILABLE and semantic_translator:
                azure_openai_endpoint = os.getenv("AZURE_OPENAI_ENDPOINT")
                azure_openai_api_key = os.getenv("AZURE_OPENAI_API_KEY")
                model_name = os.getenv("AZURE_OPENAI_DEPLOYMENT_NAME", "gpt-5")
                
                # Check if using API key OR managed identity
                has_valid_auth = azure_openai_api_key or use_managed_identity
                auth_method = "Managed Identity" if use_managed_identity else ("API Key" if azure_openai_api_key else "None")
                
                logger.info(f"🏥 Azure OpenAI Config Check - Endpoint: {'✓' if azure_openai_endpoint else '✗'}, Auth: {auth_method}, Model: {model_name}")
                
                if azure_openai_endpoint and has_valid_auth and model_name:
                    logger.info(f"🏥 Attempting connection to {azure_openai_endpoint} with model {model_name}...")
                    test_result = await semantic_translator.test_connection()
                    
                    if test_result:
                        connectivity_tests["azure_openai"] = {
                            "status": "connected",
                            "message": "✅ Azure OpenAI model is accessible and responding",
                            "endpoint": azure_openai_endpoint,
                            "model": model_name,
                            "last_tested": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                        }
                        logger.info("✅ Azure OpenAI connectivity test PASSED")
                    else:
                        connectivity_tests["azure_openai"] = {
                            "status": "failed",
                            "message": "❌ Azure OpenAI model configured but not responding",
                            "endpoint": azure_openai_endpoint,
                            "model": model_name,
                            "auth_method": auth_method,
                            "troubleshooting": "Verify deployment exists and is running in Azure OpenAI Studio",
                            "last_tested": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                        }
                        logger.error("❌ Azure OpenAI connectivity test FAILED - service not responding")
                        all_healthy = False
                else:
                    missing_vars = []
                    if not azure_openai_endpoint: missing_vars.append("AZURE_OPENAI_ENDPOINT")
                    if not has_valid_auth: missing_vars.append("AZURE_OPENAI_API_KEY or USE_MANAGED_IDENTITY=true")
                    if not model_name: missing_vars.append("AZURE_OPENAI_DEPLOYMENT_NAME")
                    
                    connectivity_tests["azure_openai"] = {
                        "status": "misconfigured",
                        "message": f"❌ Missing required environment variables: {', '.join(missing_vars)}",
                        "troubleshooting": "Set the missing environment variables in your .env file or container configuration. Use either AZURE_OPENAI_API_KEY or USE_MANAGED_IDENTITY=true",
                        "missing_variables": missing_vars
                    }
                    logger.error(f"❌ Azure OpenAI misconfigured - missing vars: {missing_vars}")
                    all_healthy = False
            else:
                connectivity_tests["azure_openai"] = {
                    "status": "unavailable",
                    "message": "❌ Semantic Kernel library not available - cannot connect to AI models",
                    "troubleshooting": "Install semantic-kernel package and restart the container"
                }
                logger.error("❌ Semantic Kernel not available - AI functionality disabled")
                all_healthy = False
        except Exception as e:
            error_msg = str(e)
            connectivity_tests["azure_openai"] = {
                "status": "error",
                "message": f"❌ Connection test failed: {error_msg[:150]}...",
                "error_details": error_msg,
                "troubleshooting": "Check Azure OpenAI service logs and network connectivity"
            }
            all_healthy = False
            logger.error(f"❌ Azure OpenAI test exception: {error_msg}")
        
        # Test STAC API connectivity
        logger.info("🏥 HEALTH CHECK: Testing STAC API connectivity...")
        try:
            stac_url = "https://planetarycomputer.microsoft.com/api/stac/v1/"
            
            async with aiohttp.ClientSession() as session:
                async with session.get(stac_url, timeout=aiohttp.ClientTimeout(total=5)) as response:
                    if response.status == 200:
                        response_data = await response.json()
                        api_info = response_data.get('title', 'Microsoft Planetary Computer STAC API')
                        
                        connectivity_tests["stac_api"] = {
                            "status": "connected",
                            "message": f"✅ {api_info} is accessible and responding",
                            "api_url": stac_url,
                            "last_tested": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                        }
                        logger.info("✅ STAC API connectivity test PASSED")
                    else:
                        error_detail = await response.text()
                        connectivity_tests["stac_api"] = {
                            "status": "degraded",
                            "message": f"⚠️ STAC API returned error (HTTP {response.status}) - non-critical",
                            "error_details": error_detail[:200],
                            "troubleshooting": "Microsoft Planetary Computer STAC API may be temporarily slow"
                        }
                        logger.warning(f"⚠️ STAC API warning: HTTP {response.status} (non-critical)")
                        # Don't mark as unhealthy for STAC issues
        except Exception as e:
            error_msg = str(e)
            connectivity_tests["stac_api"] = {
                "status": "degraded",
                "message": f"⚠️ STAC connectivity test failed (non-critical): {error_msg[:150]}...",
                "error_details": error_msg,
                "troubleshooting": "STAC API may be slow or rate-limiting - service can still operate"
            }
            # IMPORTANT: Don't mark service as unhealthy for STAC issues
            # The service can still function with cached data or alternative endpoints
            logger.warning(f"⚠️ STAC API test exception (non-critical): {error_msg}")
        
        # Test Azure Maps connectivity (GEOCODING API for location resolution)
        logger.info("🏥 HEALTH CHECK: Testing Azure Maps connectivity...")
        try:
            azure_maps_key = os.getenv("AZURE_MAPS_SUBSCRIPTION_KEY") or os.getenv("AZURE_MAPS_KEY")
            azure_maps_client_id = os.getenv("AZURE_MAPS_CLIENT_ID")
            azure_maps_use_mi = os.getenv("AZURE_MAPS_USE_MANAGED_IDENTITY", "").lower() == "true"
            
            if azure_maps_key:
                # Test Azure Maps SEARCH API (geocoding) with API key
                maps_test_url = f"https://atlas.microsoft.com/search/address/json?api-version=1.0&query=New%20York&subscription-key={azure_maps_key}"
                
                async with aiohttp.ClientSession() as session:
                    async with session.get(maps_test_url, timeout=aiohttp.ClientTimeout(total=10)) as response:
                        if response.status == 200:
                            connectivity_tests["azure_maps"] = {
                                "status": "connected",
                                "message": "✅ Azure Maps Geocoding API is accessible and responding",
                                "service": "Azure Maps Search API (Location Resolution)",
                                "auth_method": "API Key",
                                "last_tested": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                            }
                            logger.info("✅ Azure Maps Geocoding API connectivity test PASSED (API Key)")
                        else:
                            error_detail = await response.text()
                            connectivity_tests["azure_maps"] = {
                                "status": "failed",
                                "message": f"❌ Azure Maps Geocoding API returned error (HTTP {response.status})",
                                "error_details": error_detail[:200],
                                "troubleshooting": "Check Azure Maps subscription key and service status",
                                "impact": "⚠️ Location resolution will fail - queries need valid coordinates"
                            }
                            logger.error(f"❌ Azure Maps Geocoding API error: HTTP {response.status}")
                            all_healthy = False
            elif azure_maps_use_mi and azure_maps_client_id:
                # Test Azure Maps with Managed Identity
                try:
                    from azure.identity import DefaultAzureCredential
                    credential = DefaultAzureCredential()
                    token = credential.get_token("https://atlas.microsoft.com/.default")
                    
                    maps_test_url = f"https://atlas.microsoft.com/search/address/json?api-version=1.0&query=New%20York"
                    headers = {
                        "Authorization": f"Bearer {token.token}",
                        "x-ms-client-id": azure_maps_client_id
                    }
                    
                    async with aiohttp.ClientSession() as session:
                        async with session.get(maps_test_url, headers=headers, timeout=aiohttp.ClientTimeout(total=10)) as response:
                            if response.status == 200:
                                connectivity_tests["azure_maps"] = {
                                    "status": "connected",
                                    "message": "✅ Azure Maps Geocoding API is accessible via Managed Identity",
                                    "service": "Azure Maps Search API (Location Resolution)",
                                    "auth_method": "Managed Identity",
                                    "last_tested": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                                }
                                logger.info("✅ Azure Maps Geocoding API connectivity test PASSED (Managed Identity)")
                            else:
                                error_detail = await response.text()
                                connectivity_tests["azure_maps"] = {
                                    "status": "failed",
                                    "message": f"❌ Azure Maps Geocoding API returned error (HTTP {response.status})",
                                    "error_details": error_detail[:200],
                                    "auth_method": "Managed Identity",
                                    "troubleshooting": "Check Azure Maps role assignment and client ID"
                                }
                                logger.error(f"❌ Azure Maps Geocoding API error: HTTP {response.status}")
                                all_healthy = False
                except Exception as mi_error:
                    connectivity_tests["azure_maps"] = {
                        "status": "error",
                        "message": f"❌ Azure Maps MI authentication failed: {str(mi_error)[:150]}",
                        "auth_method": "Managed Identity",
                        "troubleshooting": "Check Azure Maps Data Reader role assignment on the Container App identity"
                    }
                    logger.error(f"❌ Azure Maps MI test exception: {mi_error}")
                    all_healthy = False
            else:
                connectivity_tests["azure_maps"] = {
                    "status": "misconfigured",
                    "message": "❌ Azure Maps NOT configured",
                    "troubleshooting": "Set AZURE_MAPS_SUBSCRIPTION_KEY or enable Managed Identity (AZURE_MAPS_USE_MANAGED_IDENTITY=true and AZURE_MAPS_CLIENT_ID)",
                    "impact": "⚠️ CRITICAL: Location resolution will fail - all queries with locations will fail"
                }
                logger.warning("⚠️ CRITICAL: Azure Maps not configured - location resolution disabled")
                all_healthy = False  # This should mark the service as degraded!
        except Exception as e:
            error_msg = str(e)
            connectivity_tests["azure_maps"] = {
                "status": "error",
                "message": f"❌ Azure Maps connectivity test failed: {error_msg[:150]}...",
                "error_details": error_msg,
                "troubleshooting": "Check network connectivity and Azure Maps service status"
            }
            all_healthy = False
            logger.error(f"❌ Azure Maps test exception: {error_msg}")
        
        # Determine overall health status
        overall_status = "healthy" if all_healthy else "degraded"
        if not any(basic_status.values()):
            overall_status = "unhealthy"
        
        response = {
            "status": overall_status,
            "timestamp": current_time,
            "message": "Earth Copilot Container API with enhanced connectivity checks",
            "version": "1.0.0",
            "basic_checks": basic_status,
            "connectivity_tests": connectivity_tests,
            "endpoints": {
                "health": "/api/health",
                "query": "/api/query",
                "stac_search": "/api/stac-search",
                "config": "/api/config"
            }
        }
        
        status_code = 200 if overall_status == "healthy" else 503
        logger.info(f"✅ HEALTH CHECK: Overall status: {overall_status}")
        
        return JSONResponse(
            content=response,
            status_code=status_code
        )
        
    except Exception as e:
        logger.error(f"❌ HEALTH CHECK: Error occurred: {e}")
        
        error_response = {
            "status": "unhealthy",
            "timestamp": datetime.now().strftime("%m/%d/%Y %I:%M:%S %p"),
            "error": str(e),
            "service": "Earth Copilot Container API",
            "version": "1.0.0"
        }
        
        return JSONResponse(
            content=error_response,
            status_code=500
        )

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
    logger.info("=" * 80)
    logger.info("🔐 [SIGN-MOSAIC-URL] Endpoint called!")
    logger.info("=" * 80)
    
    try:
        # Log request details
        logger.info(f"🔐 [SIGN-MOSAIC-URL] Request method: {request.method}")
        logger.info(f"🔐 [SIGN-MOSAIC-URL] Request URL: {request.url}")
        logger.info(f"🔐 [SIGN-MOSAIC-URL] Client: {request.client}")
        logger.info(f"🔐 [SIGN-MOSAIC-URL] Headers: {dict(request.headers)}")
        
        body = await request.json()
        logger.info(f"🔐 [SIGN-MOSAIC-URL] Request body keys: {list(body.keys())}")
        
        mosaic_url = body.get('url')
        
        if not mosaic_url:
            logger.error("🔐 [SIGN-MOSAIC-URL] ❌ Missing 'url' parameter in request body!")
            raise HTTPException(status_code=400, detail="Missing 'url' parameter")
        
        logger.info(f"🔐 [SIGN-MOSAIC-URL] Original URL: {mosaic_url[:150]}...")
        logger.info(f"🔐 [SIGN-MOSAIC-URL] URL length: {len(mosaic_url)} characters")
        
        if not PLANETARY_COMPUTER_AVAILABLE:
            logger.warning("🔐 [SIGN-MOSAIC-URL] ⚠️ Planetary Computer authentication not available!")
            logger.warning("🔐 [SIGN-MOSAIC-URL] ⚠️ Returning unsigned URL - tiles will be LOW RESOLUTION")
            return {"signed_url": mosaic_url, "authenticated": False}
        
        logger.info("🔐 [SIGN-MOSAIC-URL] ✅ Planetary Computer library available, signing...")
        
        # Sign the URL using planetary_computer library
        # NOTE: For TiTiler URLs, planetary_computer.sign() does NOT add SAS tokens (they're not needed!)
        # TiTiler service is publicly accessible and handles authentication server-side
        # SAS tokens are only added for direct blob storage access (which we don't use)
        try:
            signed_url = planetary_computer.sign(mosaic_url)
            logger.info("🔐 [SIGN-MOSAIC-URL] planetary_computer.sign() called successfully")
        except Exception as sign_error:
            logger.error(f"🔐 [SIGN-MOSAIC-URL] ❌ Error calling planetary_computer.sign(): {sign_error}")
            # Fall back to unsigned URL if signing fails
            signed_url = mosaic_url
        
        # Check if URL got SAS tokens (for informational purposes only)
        # NOTE: TiTiler URLs will NOT have SAS tokens - this is EXPECTED and CORRECT
        original_has_token = 'se=' in mosaic_url or 'sig=' in mosaic_url or 'st=' in mosaic_url
        signed_has_token = 'se=' in signed_url or 'sig=' in signed_url or 'st=' in signed_url
        is_titiler_url = 'planetarycomputer.microsoft.com/api/data/v1' in signed_url
        
        logger.info("🔐 [SIGN-MOSAIC-URL] " + "=" * 60)
        logger.info(f"🔐 [SIGN-MOSAIC-URL] ✅ URL SIGNED SUCCESSFULLY!")
        logger.info(f"🔐 [SIGN-MOSAIC-URL] URL type: {'TiTiler (public, no SAS needed)' if is_titiler_url else 'Blob Storage (may need SAS)'}")
        logger.info(f"🔐 [SIGN-MOSAIC-URL] Original URL had SAS token: {original_has_token}")
        logger.info(f"🔐 [SIGN-MOSAIC-URL] Signed URL has SAS token: {signed_has_token}")
        logger.info(f"🔐 [SIGN-MOSAIC-URL] Signed URL preview: {signed_url[:150]}...")
        logger.info(f"🔐 [SIGN-MOSAIC-URL] Signed URL length: {len(signed_url)} characters")
        
        if not signed_has_token and is_titiler_url:
            logger.info("🔐 [SIGN-MOSAIC-URL] ℹ️ INFO: TiTiler URL has no SAS token (EXPECTED - service is public)")
            logger.info("🔐 [SIGN-MOSAIC-URL] ✅ Full resolution tiles enabled via TiTiler public API")
        elif not signed_has_token and not is_titiler_url:
            logger.warning("🔐 [SIGN-MOSAIC-URL] ⚠️ WARNING: Non-TiTiler URL has no SAS token!")
            logger.warning("🔐 [SIGN-MOSAIC-URL] ⚠️ Direct blob access may fail without authentication")
        else:
            logger.info("🔐 [SIGN-MOSAIC-URL] ✅ SAS token present - authenticated blob storage access")
        
        logger.info("🔐 [SIGN-MOSAIC-URL] " + "=" * 60)
        
        return {
            "signed_url": signed_url,
            "authenticated": True
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error("🔐 [SIGN-MOSAIC-URL] " + "=" * 60)
        logger.error(f"🔐 [SIGN-MOSAIC-URL] ❌ EXCEPTION during URL signing!")
        logger.error(f"🔐 [SIGN-MOSAIC-URL] ❌ Error type: {type(e).__name__}")
        logger.error(f"🔐 [SIGN-MOSAIC-URL] ❌ Error message: {str(e)}")
        logger.error(f"🔐 [SIGN-MOSAIC-URL] ❌ Traceback:")
        logger.error(traceback.format_exc())
        logger.error("🔐 [SIGN-MOSAIC-URL] " + "=" * 60)
        raise HTTPException(status_code=500, detail=f"Failed to sign URL: {str(e)}")

# ============================================================================
# COLORMAP ENDPOINTS REMOVED
# ============================================================================
# The colormap service has been removed as it's redundant.
# Colormap information comes directly from PC tasks rendering config.
# Legend display uses hardcoded colormap gradients in the frontend.
# ============================================================================

@app.post("/api/query")
async def unified_query_processor(request: Request):
    """
    Unified query processor that combines Router Function logic with direct STAC search
    This implements the complete Earth Copilot query processing pipeline
    """
    try:
        logger.info("=" * 100)
        logger.info("🚀🚀🚀 POST /api/query ENDPOINT HIT - UNIFIED QUERY PROCESSOR STARTED 🚀🚀🚀")
        logger.info("=" * 100)
        logger.info(f"🌐 Request Method: {request.method}")
        logger.info(f"🌐 Request URL: {request.url}")
        logger.info(f"🌐 Request Headers: {dict(request.headers)}")
        logger.info(f"🌐 Client Host: {request.client.host if request.client else 'Unknown'}")
        logger.info("=" * 100)
        
        # Parse request with robust handling
        try:
            req_body = await request.json()
            if not req_body:
                raise ValueError("Request body is empty")
            
            # ========================================================================
            # �️ VISION GEOINT MODE - CHECK FIRST BEFORE CACHE
            # ========================================================================
            # Note: Caching removed - all queries get fresh responses
            logger.info(f"📥 Container received request: {json.dumps(req_body, indent=2)}")
            
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
        
        # 🔬 Generate unique pipeline session ID for tracing
        import uuid
        pipeline_session_id = str(uuid.uuid4())[:8]
        
        # 🔬 Clear any stale trace and start fresh
        clear_pipeline_trace(pipeline_session_id)
        
        # 🔬 TRACE: Initial query received
        log_pipeline_step(pipeline_session_id, "QUERY_RECEIVED", "INPUT", {
            "query": natural_query,
            "session_id": session_id,
            "has_pin": bool(pin),
            "pin_coords": f"({pin.get('lat'):.4f}, {pin.get('lng'):.4f})" if pin else None
        })
        
        logger.info("=" * 100)
        logger.info(f"🔤🔤🔤 RECEIVED NATURAL LANGUAGE QUERY: '{natural_query}' 🔤🔤🔤")
        logger.info(f"🆔 Session ID: {session_id}")
        logger.info(f"🔬 Pipeline Trace ID: {pipeline_session_id}")
        logger.info(f"📦 Full Request Body Keys: {list(req_body.keys())}")
        logger.info("=" * 100)
        
        # ========================================================================
        # NORMAL STAC SEARCH ROUTING
        # ========================================================================
        # Vision analysis now handled by dedicated /api/geoint/vision endpoint
        logger.info("📍 Proceeding with normal STAC search routing")
        
        # Check for pin parameter
        if pin:
            pin_lat = pin.get('lat')
            pin_lng = pin.get('lng')
            logger.info(f"📍 Pin detected: ({pin_lat:.4f}, {pin_lng:.4f})")
        
        has_satellite_data = req_body.get("has_satellite_data", False)
        query_lower = natural_query.lower().strip()
        
        # Continue with regular STAC search flow
        router_action = None
        
        # ========================================================================
        # 🚦 ROUTER AGENT: Intelligent Query Classification and Routing
        # ========================================================================
        # RouterAgent classifies queries and routes them to the appropriate handler.
        #
        # Action Types:
        # - navigate_to (fly_to): Pan map to location (no STAC search, immediate response)
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
                logger.info("🚦 Invoking RouterAgent for query classification...")
                router_action = await router_agent.route_query(
                    query=natural_query,
                    session_id=session_id,
                    has_screenshot=bool(req_body.get("imagery_base64"))
                )
                
                logger.info(f"🚦 RouterAgent decision: {router_action.get('action_type', 'unknown')}")
                log_pipeline_step(pipeline_session_id, "ROUTER_AGENT", "OUTPUT", {
                    "action_type": router_action.get("action_type"),
                    "needs_stac": router_action.get("needs_stac_search", False),
                    "needs_vision": router_action.get("needs_vision_analysis", False)
                })
                
                # ================================================================
                # HANDLE NAVIGATE_TO ACTION (fly_to): Map-only navigation (no STAC search)
                # ================================================================
                if router_action.get("action_type") == "navigate_to" or router_action.get("action_type") == "fly_to":
                    # Get location from router action, or fall back to original query for bare locations
                    location = router_action.get("location") or router_action.get("original_query", "")
                    zoom_level = router_action.get("zoom_level", 12)
                    
                    logger.info(f"🗺️ NAVIGATE_TO ACTION: Navigating to '{location}' at zoom {zoom_level}")
                    
                    # Resolve location to coordinates using location_resolver
                    from location_resolver import EnhancedLocationResolver
                    resolver = EnhancedLocationResolver()
                    
                    try:
                        bbox = await resolver.resolve_location_to_bbox(location)
                        if bbox and len(bbox) == 4:
                            # Calculate center from bbox [west, south, east, north]
                            center_lng = (bbox[0] + bbox[2]) / 2
                            center_lat = (bbox[1] + bbox[3]) / 2
                            
                            logger.info(f"✅ Location resolved: {location} → ({center_lat:.4f}, {center_lng:.4f})")
                            
                            # ============================================================
                            # 📍 UPDATE SESSION CONTEXT: Store bbox for follow-up queries
                            # ============================================================
                            # When user navigates to a location, we store the bbox so that
                            # follow-up queries like "show me Sentinel tiles" will use this location
                            # ============================================================
                            if router_agent and session_id:
                                navigate_context = {
                                    "last_bbox": bbox,
                                    "last_location": location,
                                    "has_rendered_map": False,  # No imagery yet, just navigation
                                    "query_count": router_agent.tools.session_contexts.get(session_id, {}).get("query_count", 0) + 1
                                }
                                router_agent.update_session_context(session_id, navigate_context)
                                logger.info(f"📍 Updated session context with navigate_to location: {location}, bbox: {bbox}")
                            
                            return {
                                "success": True,
                                "action": "navigate_to",
                                "response": f"Navigating to {location}. You can explore the area on the map, or ask for satellite imagery like 'Show me Sentinel-2 imagery here'.",
                                "user_response": f"Navigating to {location}. You can explore the area on the map, or ask for satellite imagery like 'Show me Sentinel-2 imagery here'.",
                                "fly_to": {
                                    "latitude": center_lat,
                                    "longitude": center_lng,
                                    "zoom": zoom_level,
                                    "bbox": bbox,
                                    "location_name": location
                                },
                                "processing_type": "map_navigation",
                                "timestamp": datetime.utcnow().isoformat()
                            }
                        else:
                            logger.warning(f"⚠️ Could not resolve location '{location}', falling through to STAC search")
                            # Fall through to existing STAC flow
                    except Exception as loc_error:
                        logger.error(f"❌ Location resolution failed: {loc_error}")
                        # Fall through to existing STAC flow
                
            except Exception as router_error:
                logger.warning(f"⚠️ RouterAgent failed: {router_error}, falling back to legacy classification")
                router_action = None
        
        # PHASE 0: EARLY QUERY INTENT CLASSIFICATION
        classification = None
        early_contextual_response = None
        translator = None
        vision_task = None  # For parallel processing of hybrid queries
        
        # ========================================================================
        # 🔀 ROUTER AGENT → CLASSIFICATION BRIDGE
        # ========================================================================
        # If RouterAgent provided a stac_search action, convert it to classification
        # format for compatibility with existing STAC flow.
        # NOTE: Vision analysis is handled by explicit vision mode (not RouterAgent).
        # ========================================================================
        if router_action and router_action.get("action_type") == "stac_search":
            logger.info(f"🔀 Converting RouterAgent 'stac_search' to classification format")
            
            classification = {
                "intent_type": "stac",
                "confidence": 0.95,
                "needs_satellite_data": True,
                "needs_vision_analysis": False,
                "needs_contextual_info": False,
                "reasoning": "RouterAgent routed to STAC search",
                "router_action": router_action
            }
        
        logger.info(f"🔍 SEMANTIC_KERNEL_AVAILABLE: {SEMANTIC_KERNEL_AVAILABLE}")
        if SEMANTIC_KERNEL_AVAILABLE and global_translator:
            try:
                translator = global_translator
                
                # ========================================================================
                # 🚀 QUICK START QUERY OPTIMIZATION
                # ========================================================================
                # Skip expensive AI classification for pre-defined demo queries
                # Provides ~3-5 second speedup for quick start button clicks
                # ========================================================================
                quickstart_classification = get_quickstart_classification(natural_query)
                quickstart_location = get_quickstart_location(natural_query)
                
                if quickstart_classification and quickstart_location:
                    logger.info(f"🚀 QUICK START QUERY DETECTED: '{natural_query}'")
                    logger.info(f"   Pre-computed: collection={quickstart_location['collections']}, location={quickstart_location['location']}")
                    classification = quickstart_classification
                    # Store location data for later use in STAC search
                    quickstart_data = quickstart_location
                else:
                    quickstart_data = None
                
                # ========================================================================
                # 🧠 UNIFIED INTENT CLASSIFICATION - Single GPT-5 call
                # ========================================================================
                # Intent Types: vision | stac | hybrid | contextual
                # - vision: Analyze currently visible imagery (no new data loading)
                # - stac: Load new satellite imagery only (no analysis)
                # - hybrid: Load new imagery AND analyze it (sequential operation)
                # - contextual: Information/education only (no map interaction)
                # ========================================================================
                
                # ========================================================================
                # 🚦 SKIP CLASSIFICATION IF ROUTER AGENT OR QUICKSTART ALREADY DECIDED
                # ========================================================================
                if classification and (classification.get("router_action") or classification.get("is_quickstart")):
                    if classification.get("is_quickstart"):
                        logger.info("⏭️ Skipping classification - Quick start query with pre-computed result")
                    else:
                        logger.info("⏭️ Skipping legacy classification - RouterAgent already provided classification")
                else:
                    # ========================================================================
                    # 🎯 PRE-CLASSIFICATION KEYWORD OVERRIDE: Factual/Informational Questions
                    # ========================================================================
                    # PROBLEM: GPT classification is unreliable for factual questions like
                    # "What is the highest peak in Denver?" - GPT sees "Denver" + "peak" and
                    # thinks user wants to SEE elevation data, not just GET AN ANSWER.
                    # 
                    # SOLUTION: Hard keyword detection BEFORE classification for common patterns:
                    # - "what is the", "what's the", "which is the"
                    # - "how tall", "how high", "how deep", "how long", "how wide"
                    # - "when was/did", "where is the" (location of named entity)
                    # - NO "show/display/load" keywords present
                    # - NO vision/map context keywords present (follow-up queries)
                    # ========================================================================
                    query_lower = natural_query.lower().strip()
                    
                    factual_question_patterns = [
                        "what is the", "what's the", "which is the", "where is the",
                        "how tall", "how high", "how deep", "how long", "how wide",
                        "how many", "when was", "when did", "who", "why",
                        "tell me about", "explain", "describe the", "what are the"
                    ]
                    
                    visualization_keywords = ["show", "display", "load", "see", "view", "map", "imagery", "image"]
                    
                    # ========================================================================
                    # 🔍 FOLLOW-UP / VISION CONTEXT KEYWORDS
                    # ========================================================================
                    # These indicate user is asking about current view, NOT a factual question:
                    # - "adjacent to", "near", "on the map", "the map"
                    # - "in this", "this area", "this region"
                    # ========================================================================
                    vision_context_keywords = [
                        "adjacent to", "near the", "on the map", "the map",
                        "in this", "this area", "this region", "this location",
                        "the river", "the lake", "the city", "the coast",
                        "what city", "what river", "what lake", "what mountain"
                    ]
                    
                    has_factual_pattern = any(pattern in query_lower for pattern in factual_question_patterns)
                    has_visualization = any(keyword in query_lower for keyword in visualization_keywords)
                    has_vision_context = any(keyword in query_lower for keyword in vision_context_keywords)
                    
                    # Force contextual ONLY if: factual pattern AND no visualization AND no vision context
                    force_contextual = has_factual_pattern and not has_visualization and not has_vision_context
                    
                    if force_contextual:
                        logger.info("🎯 KEYWORD OVERRIDE: Factual question detected → Forcing contextual mode")
                        logger.info(f"   Pattern detected: {[p for p in factual_question_patterns if p in query_lower]}")
                        classification = {
                            'intent_type': 'contextual',
                            'confidence': 0.98,
                            'needs_satellite_data': False,
                            'needs_contextual_info': True,
                            'needs_vision_analysis': False,
                            'modules': [],
                            'reasoning': 'Keyword override: Factual question without visualization keywords'
                        }
                    elif has_vision_context:
                        logger.info("🔍 KEYWORD OVERRIDE: Vision/follow-up context detected → Forcing vision mode")
                        logger.info(f"   Vision context detected: {[k for k in vision_context_keywords if k in query_lower]}")
                        classification = {
                            'intent_type': 'vision',
                            'confidence': 0.97,
                            'needs_satellite_data': False,
                            'needs_contextual_info': False,
                            'needs_vision_analysis': True,
                            'modules': [],
                            'reasoning': 'Keyword override: Follow-up/vision context detected'
                        }
                    else:
                        logger.info("🧠 Performing unified query intent classification...")
                        classification = await translator.classify_query_intent_unified(natural_query, session_id)
                        
                intent_type = classification.get('intent_type', 'stac')  # Default to STAC query
                confidence = classification.get('confidence', 0)
                modules_to_execute = classification.get('modules', [])
                
                logger.info(f"🎯 UNIFIED CLASSIFICATION RESULT:")
                logger.info(f"   Query: '{natural_query}'")
                logger.info(f"   Intent: {intent_type}")
                logger.info(f"   Confidence: {confidence:.2f}")
                logger.info(f"   Modules: {modules_to_execute}")
                logger.info(f"   Needs satellite data: {classification.get('needs_satellite_data', False)}")
                logger.info(f"   Needs contextual info: {classification.get('needs_contextual_info', False)}")
                logger.info(f"   Needs vision analysis: {classification.get('needs_vision_analysis', False)}")
                
                # 🔬 TRACE: Classification result
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
                # 🖼️ CHAT VISION ANALYSIS - Priority Detection
                # ========================================================================
                # STRATEGY: Check vision keywords FIRST before expensive classification
                # This prevents classification from overriding obvious vision queries
                # Example: "What bodies of water are in this image?" should NOT trigger STAC search
                # ========================================================================
                
                # STEP 1: Fast vision keyword detection (runs in <1ms vs ~500-1000ms for classification)
                from agents import get_vision_agent  # EnhancedVisionAgent with 5 tools
                vision_agent = get_vision_agent()
                conversation_history = req_body.get('conversation_history', []) or req_body.get('messages', [])
                
                # Still use chat_vision_analyzer for keyword detection (it's fast)
                from geoint.chat_vision_analyzer import get_chat_vision_analyzer
                chat_vision_detector = get_chat_vision_analyzer()
                needs_vision = chat_vision_detector.should_use_vision(natural_query, conversation_history)
                
                if needs_vision:
                    logger.info("🔍 Vision query detected by KEYWORD/CONTEXT matching (priority check)")
                else:
                    # STEP 2: Fallback to classification if keywords didn't match
                    # This catches edge cases where user doesn't use explicit vision keywords
                    needs_vision = classification.get('needs_vision_analysis', False)
                    if needs_vision:
                        logger.info("🔍 Vision query detected by GPT CLASSIFICATION (fallback check)")
                
                # ========================================================================
                # 🚀 PARALLEL PROCESSING: Vision + Data for Hybrid Queries
                # ========================================================================
                # For hybrid queries that need both vision analysis AND STAC data,
                # we can run them in parallel to save ~5-8 seconds
                # ========================================================================
                
                if needs_vision:
                    logger.info("🖼️ VISION QUERY DETECTED: User is asking about visible imagery")
                    
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
                        logger.info(f"📋 Session context for Vision Agent: {list(session_context.keys())}")
                        
                        # Merge session collections with current collection
                        session_collections = session_context.get('last_collections', [])
                        if session_collections and not collections_list:
                            collections_list = session_collections
                        
                        # Get STAC items from session for raster analysis
                        stac_items_from_session = session_context.get('last_stac_items', [])
                        if stac_items_from_session:
                            logger.info(f"📦 Retrieved {len(stac_items_from_session)} STAC items from session for vision agent")
                        
                        # Use session bbox if no current bounds
                        if not map_bounds and session_context.get('last_bbox'):
                            bbox = session_context['last_bbox']
                            map_bounds = {
                                'west': bbox[0], 'south': bbox[1],
                                'east': bbox[2], 'north': bbox[3],
                                'center_lat': (bbox[1] + bbox[3]) / 2,
                                'center_lng': (bbox[0] + bbox[2]) / 2
                            }
                            logger.info(f"📍 Using session bbox for Vision Agent: {session_context.get('last_location')}")
                    
                    # Convert collection to list for Vision Agent (typically one collection per query)
                    if current_collection and current_collection not in collections_list:
                        collections_list = [current_collection] + collections_list
                    
                    # Log vision context availability
                    logger.info(f"📸 Map screenshot available: {bool(imagery_base64)}")
                    logger.info(f"🛰️ Satellite data loaded: {has_satellite_data}")
                    logger.info(f"🗺️ Map bounds available: {bool(map_bounds)}")
                    
                    # Check if this is a HYBRID query (vision + data)
                    needs_data = classification.get('needs_satellite_data', False)
                    is_hybrid_vision = needs_vision and needs_data
                    
                    if is_hybrid_vision:
                        logger.info("🔀 HYBRID VISION + DATA QUERY: Will run vision + STAC in PARALLEL for optimal performance")
                    
                    if map_bounds or imagery_url or imagery_base64:
                        try:
                            # For hybrid queries, we'll start vision analysis but continue to STAC
                            # Both will run in parallel (vision task created, STAC search proceeds)
                            vision_task = None
                            
                            if is_hybrid_vision:
                                # Create vision agent task (runs in background)
                                logger.info("⚡ Starting Vision Agent task (parallel execution)...")
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
                                logger.info("🔄 Vision Agent task created, continuing to STAC data retrieval (parallel)...")
                            else:
                                # Pure vision query - invoke Vision Agent and return immediately
                                logger.info("🤖 Invoking Vision Agent for pure vision query")
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
                                # 🔍 DEBUG: Log vision_result to trace issues
                                # ================================================================
                                logger.info(f"🔍 Vision Agent returned: {type(vision_result)}")
                                if vision_result:
                                    logger.info(f"   Keys: {list(vision_result.keys())}")
                                    logger.info(f"   Response: '{str(vision_result.get('response', ''))[:100]}...'")
                                    logger.info(f"   Analysis: '{str(vision_result.get('analysis', ''))[:100]}...'")
                                
                                # Check for response (or analysis as fallback)
                                response_text = vision_result.get("response") or vision_result.get("analysis") if vision_result else None
                                
                                if response_text:
                                    logger.info("✅ Vision Agent analysis completed")
                                    logger.info(f"   Cached: {vision_result.get('cached', False)}")
                                    
                                    # ================================================================
                                    # VISION AGENT TRACING: Log tool usage for debugging
                                    # ================================================================
                                    tools_used = vision_result.get("tools_used", [])
                                    tool_calls = vision_result.get("tool_calls", [])
                                    logger.info(f"🔧 Vision Agent tools used: {tools_used}")
                                    
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
                                    # 🚨 VISION AGENT FAILED - Return error, DON'T fall through to STAC
                                    # ================================================================
                                    logger.warning(f"⚠️ Vision Agent returned empty response. Result: {vision_result}")
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
                            logger.warning(f"⚠️ Chat vision analysis failed: {e}, returning error...")
                            import traceback
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
                            
                            # 🔍 DEBUG: Log vision_result
                            logger.info(f"🔍 Vision Agent (LLM mode) returned: {type(vision_result)}")
                            if vision_result:
                                logger.info(f"   Keys: {list(vision_result.keys())}")
                                logger.info(f"   Response: '{str(vision_result.get('response', ''))[:100]}...'")
                            
                            # Check for response (or analysis as fallback)
                            response_text = vision_result.get("response") or vision_result.get("analysis") if vision_result else None
                            
                            if response_text:
                                logger.info("✅ Vision Agent (LLM mode) completed")
                                
                                # ================================================================
                                # VISION AGENT TRACING: Log tool usage for debugging
                                # ================================================================
                                tools_used = vision_result.get("tools_used", [])
                                tool_calls = vision_result.get("tool_calls", [])
                                logger.info(f"🔧 Vision Agent (LLM mode) tools used: {tools_used}")
                                
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
                                # 🚨 VISION AGENT LLM MODE FAILED - Return helpful message
                                # ================================================================
                                logger.warning(f"⚠️ Vision Agent (LLM mode) returned empty. Result: {vision_result}")
                                
                                # For "what is on the map" without screenshot, give a helpful response
                                return {
                                    "success": True,
                                    "response": "I can see you're asking about what's on the map. I can see satellite imagery is displayed. Could you ask a more specific question about what you'd like to know, such as 'What city is shown?' or 'What features can you identify?'",
                                    "processing_type": "vision_agent_no_context",
                                    "timestamp": datetime.utcnow().isoformat()
                                }
                        except Exception as e:
                            logger.warning(f"⚠️ Vision Agent LLM fallback failed: {e}")
                            import traceback
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
                    logger.info("💬 CONTEXTUAL REQUEST: Skipping STAC search, generating educational response...")
                    try:
                        contextual_response = await asyncio.wait_for(
                            translator.generate_contextual_earth_science_response(
                                natural_query, 
                                classification, 
                                {"success": True, "results": {"features": []}}  # Empty STAC response for contextual-only
                            ),
                            timeout=30.0
                        )
                        
                        if contextual_response and contextual_response.get("message"):
                            logger.info("✅ Generated contextual response successfully")
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
                        logger.warning(f"⚠️ Contextual response generation failed: {e}, proceeding with STAC search...")
                
            except Exception as e:
                logger.error(f"❌ Early classification failed: {e}")
                classification = None
        
        # PHASE 1: SEMANTIC TRANSLATION TO STAC PARAMETERS
        # ========================================================================
        # ⚙️ CONDITIONAL COLLECTION MAPPING: Only run for STAC and Hybrid queries
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
                logger.info(f"⏭️ Skipping collection mapping for {intent_type} query (no STAC search needed)")
        
        if not skip_collection_mapping:
            if not SEMANTIC_KERNEL_AVAILABLE:
                logger.warning("⚠️ Semantic Kernel not available, using fallback processing")
                
                # Fallback: Simple collection detection (like Router Function App)
                collections = detect_collections(natural_query)
                stac_params = {
                    "collections": collections,
                    "limit": 20,  # PERFORMANCE: Reduced from 100 to 20 for faster queries (3-5s improvement)
                    "original_query": natural_query
                }
                
                if collections:
                    stac_query = build_stac_query(stac_params)
                    logger.info(f"🔧 Built fallback STAC query: {json.dumps(stac_query, indent=2)}")
                
            elif SEMANTIC_KERNEL_AVAILABLE and translator:
                try:
                    logger.info("=" * 100)
                    logger.info("🤖🤖🤖 STARTING MULTI-AGENT TRANSLATION PIPELINE 🤖🤖🤖")
                    logger.info(f"📝 Query: '{natural_query}'")
                    logger.info(f"📍 Pin Location: {pin}")
                    
                    # ========================================================================
                    # 📍 SESSION BBOX: Fallback location for queries without explicit location
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
                                logger.info(f"📍 Session fallback available: {session_location} bbox={session_bbox}")
                        except AttributeError:
                            logger.debug("📍 No session context available (router_agent.tools.session_contexts not found)")
                    
                    # If router explicitly said use_current_location, prioritize it
                    if router_action and router_action.get("use_current_location"):
                        logger.info(f"📍 Router explicitly set use_current_location=True")
                    
                    logger.info("=" * 100)
                    
                    logger.info("🔄 Translating natural language to STAC parameters...")
                    
                    # ========================================================================
                    # 🚀 QUICK START OPTIMIZATION: Skip expensive translation for demo queries
                    # ========================================================================
                    # For the 22 quick start queries, we have pre-computed collections + bbox.
                    # This saves ~3-5 seconds by skipping AI classification + geocoding.
                    # ========================================================================
                    if quickstart_data:
                        logger.info(f"🚀 Using pre-computed STAC params for quick start query")
                        stac_params = {
                            'collections': quickstart_data['collections'],
                            'bbox': quickstart_data['bbox'],
                            'datetime': quickstart_data.get('datetime'),
                            'location_name': quickstart_data['location'],
                            'is_quickstart': True
                        }
                        logger.info(f"   Collections: {stac_params['collections']}")
                        logger.info(f"   Bbox: {stac_params['bbox']}")
                    else:
                        # Use the semantic translator's translate_query method with pin and session_bbox fallback
                        stac_params = await translator.translate_query(natural_query, pin_location=pin, session_bbox=session_bbox)
                    
                    # ========================================================================
                    # 🚨 LOCATION VALIDATION: Check if location is required but missing
                    # ========================================================================
                    if stac_params and stac_params.get('error') == 'LOCATION_REQUIRED':
                        logger.warning(f"⚠️ Location required but not found in query")
                        return {
                            "success": False,
                            "error": "LOCATION_REQUIRED",
                            "response": stac_params.get('message', 'Please specify a location for your search.'),
                            "suggestions": stac_params.get('suggestions', []),
                            "timestamp": datetime.utcnow().isoformat()
                        }
                    # ========================================================================
                    
                    if stac_params and stac_params.get('collections'):
                        logger.info(f"✅ Translation successful: {len(stac_params.get('collections', []))} collections selected")
                        
                        # 🔬 TRACE: Semantic translation result
                        log_pipeline_step(pipeline_session_id, "SEMANTIC_TRANSLATION", "OUTPUT", {
                            "collections": stac_params.get('collections', []),
                            "bbox": stac_params.get('bbox'),
                            "datetime": stac_params.get('datetime'),
                            "location_name": stac_params.get('location_name', 'N/A')
                        })
                        
                        # Build STAC query from semantic analysis (like Router Function App)
                        stac_query = build_stac_query(stac_params)
                        logger.info(f"🔧 Built STAC query from params: {json.dumps(stac_query, indent=2)}")
                        
                    else:
                        logger.warning(f"⚠️ Translation did not produce valid STAC parameters. Got: {stac_params}")
                        
                        # 🔬 TRACE: Translation failed
                        log_pipeline_step(pipeline_session_id, "SEMANTIC_TRANSLATION", "ERROR", {
                            "error": "No valid collections returned",
                            "raw_params": str(stac_params)[:200]
                        })
                        
                except Exception as e:
                    logger.error(f"❌ Semantic translation failed: {e}", exc_info=True)
                    logger.error(f"❌ Full traceback: {traceback.format_exc()}")
                    stac_params = None
                    stac_query = None
        
        # PHASE 2: EXECUTE STAC SEARCH (if we have a valid query)
        stac_response = {"results": {"type": "FeatureCollection", "features": []}}
        features = []
        
        # 📊 DIAGNOSTICS: Track filtering stages for helpful error messages
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
                logger.info("🌐 Executing STAC search...")
                
                # 🔍 PIPELINE LOG: STAC Search Input
                log_pipeline_step(pipeline_session_id, "STAC_SEARCH", "INPUT", {
                    "collections": stac_query.get("collections"),
                    "bbox": stac_query.get("bbox"),
                    "datetime": stac_query.get("datetime"),
                    "filter": stac_query.get("filter")
                })
                
                # Determine which STAC endpoint to use (intelligent routing from Router Function App)
                stac_endpoint = translator.determine_stac_source(natural_query, stac_params)
                logger.info(f"📡 STAC source determined: {stac_endpoint}")
                
                # Pass original_query for smart deduplication (removes duplicate grid cells)
                stac_response = await execute_direct_stac_search(stac_query, stac_endpoint, original_query=natural_query)
                
                if stac_response.get("success"):
                    raw_features = stac_response.get("results", {}).get("features", [])
                    search_diagnostics["raw_count"] = len(raw_features)
                    logger.info(f"✅ STAC search completed: {len(raw_features)} raw features found")
                    
                    # 🔍 PIPELINE LOG: STAC Search Output
                    log_pipeline_step(pipeline_session_id, "STAC_SEARCH", "OUTPUT", {
                        "feature_count": len(raw_features),
                        "first_feature_id": raw_features[0].get("id") if raw_features else None,
                        "first_feature_bbox": raw_features[0].get("bbox") if raw_features else None
                    })
                    
                    # 🔍 MODIS BBOX FILTERING: MODIS STAC API returns tiles outside requested bbox
                    # MODIS uses sinusoidal grid (h/v tiles), so bbox filter isn't strict in PC STAC API
                    # Filter out tiles whose center is outside requested bbox to prevent showing
                    # Arizona/Texas tiles when user requested California
                    collections = stac_query.get('collections', [])
                    is_modis = any(col.startswith('modis-') for col in collections)
                    requested_bbox = stac_query.get("bbox")
                    
                    if is_modis and requested_bbox and raw_features:
                        logger.info(f"🗺️  MODIS BBOX FILTER: Checking {len(raw_features)} tiles against requested bbox")
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
                                logger.debug(f"   ❌ Filtered out tile with center ({tile_center_lon:.2f}, {tile_center_lat:.2f}) outside bbox")
                        
                        logger.info(f"✅ MODIS BBOX FILTER: Kept {len(filtered_features)}/{len(raw_features)} tiles within requested bbox")
                        raw_features = filtered_features
                        search_diagnostics["raw_count"] = len(raw_features)
                        search_diagnostics["modis_bbox_filtered"] = True
                    
                    # 🔍 NO SPATIAL PRE-FILTERING: Agent 3 handles spatial coverage intelligently
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
                        logger.info(f"⏭️ Skipping spatial pre-filter: Agent 3 will ensure coverage from {len(raw_features)} tiles")
                        
                        # ☁️ CLIENT-SIDE CLOUD COVER FILTERING: Safety net in case STAC API ignored the filter
                        # Extract cloud cover limit from query parameters OR detect from original query keywords
                        cloud_cover_limit = None
                        query_filter = stac_query.get("query", {})
                        logger.info(f"🔍 DEBUG: Client-side check - stac_query.get('query') = {query_filter}")
                        
                        # Check both eo:cloud_cover (Sentinel-2, Landsat) and cloud_cover (HLS)
                        for prop_name in ["eo:cloud_cover", "cloud_cover"]:
                            if prop_name in query_filter:
                                cloud_cover_filter = query_filter[prop_name]
                                logger.info(f"🔍 DEBUG: Found {prop_name} in query_filter: {cloud_cover_filter}")
                                if "lte" in cloud_cover_filter:
                                    cloud_cover_limit = cloud_cover_filter["lte"]
                                elif "lt" in cloud_cover_filter:
                                    cloud_cover_limit = cloud_cover_filter["lt"]
                                break
                            else:
                                logger.info(f"🔍 DEBUG: {prop_name} NOT in query_filter")
                        
                        # 🔧 FALLBACK: Keyword detection if no cloud filter in query parameters
                        # This catches cases where the cloud filter wasn't propagated through the pipeline
                        if cloud_cover_limit is None and natural_query:
                            query_lower = natural_query.lower()
                            low_cloud_keywords = ['low cloud', 'no cloud', 'clear', 'cloudless', 
                                                  'minimal cloud', 'cloud-free', 'without clouds',
                                                  'clear sky', 'clear skies', 'no clouds']
                            if any(kw in query_lower for kw in low_cloud_keywords):
                                cloud_cover_limit = 25
                                logger.info(f"🔧 FALLBACK: Detected low cloud keywords in query, applying {cloud_cover_limit}% filter")
                        
                        logger.info(f"🔍 DEBUG: Final cloud_cover_limit = {cloud_cover_limit}")
                        
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
                                        logger.info(f"☁️ Cloud filter relaxed: {original_cloud_limit}% → {threshold}% (found {len(filtered_features)} tiles)")
                                        search_diagnostics["cloud_relaxation"] = f"{original_cloud_limit}% -> {threshold}%"
                                    else:
                                        logger.info(f"☁️ After cloud cover filtering (≤{threshold}%): {len(filtered_features)} features kept")
                                    break
                        
                        # 🎯 TILE SELECTION: Use STAC API ordering (sorted by datetime desc)
                        # When no datetime is specified, STAC API returns results sorted by most recent first
                        # This is more efficient than GPT-5 selection and respects user's implicit "latest" intent
                        logger.info(f"📋 Using STAC API ordering (results already sorted by datetime desc)")
                        
                        # Use all spatially filtered features (already ordered by recency from STAC API)
                        features = spatially_filtered_features
                        search_diagnostics["final_count"] = len(features)
                        search_diagnostics["tile_selection_method"] = "stac_api_ordering"
                        logger.info(f"✅ Using {len(features)} tiles from STAC API (pre-sorted by datetime desc)")
                        
                        # Update stac_response with filtered results
                        stac_response["results"]["features"] = features
                    else:
                        features = raw_features
                        search_diagnostics["spatial_filtered_count"] = len(raw_features)
                        search_diagnostics["final_count"] = len(features)
                        logger.info("⚠️ Skipping spatial filtering and tile ranking (no translator or bbox)")
                    
                    # Determine failure stage if no results
                    if search_diagnostics["final_count"] == 0:
                        if search_diagnostics["raw_count"] == 0:
                            search_diagnostics["failure_stage"] = "stac_api"
                        elif search_diagnostics["spatial_filtered_count"] == 0:
                            search_diagnostics["failure_stage"] = "spatial_filter"
                        else:
                            search_diagnostics["failure_stage"] = "tile_selection"
                        
                        # 🆕 TRY ALTERNATIVE QUERIES: Automatically find available alternatives
                        logger.info("🔄 No results found - attempting to find alternatives with relaxed filters...")
                        alternative_result = await try_alternative_queries(
                            natural_query,
                            stac_query,
                            stac_params,
                            translator,
                            stac_endpoint,
                            requested_bbox
                        )
                        
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
                            
                            logger.info(f"✅ Found {len(features)} alternative results: {alternative_result.get('explanation')}")
                        else:
                            logger.info("❌ No alternatives found - will generate empty result response")
                else:
                    logger.error(f"❌ STAC search failed: {stac_response.get('error', 'Unknown error')}")
                    search_diagnostics["failure_stage"] = "stac_error"
                    
            except Exception as e:
                logger.error(f"❌ STAC search execution error: {e}")
                stac_response = {"results": {"type": "FeatureCollection", "features": []}}
                search_diagnostics["failure_stage"] = "exception"
        
        # ========================================================================
        # PHASE 3.4: EXECUTE GEOINT ANALYSIS (Legacy - for backward compatibility)
        # ========================================================================
        geoint_results = None
        
        if stac_params and stac_params.get('geoint_processing') and GEOINT_AVAILABLE and geoint_executor and features:
            try:
                logger.info("🔬 Query requires GEOINT analysis - executing analytical processing...")
                logger.info(f"📊 GEOINT intent detected: {stac_params.get('analysis_intent', {})}")
                
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
                    logger.info("✅ GEOINT analysis completed successfully")
                    logger.info(f"📈 Analysis results preview: {list(geoint_results.get('results', {}).keys())}")
                    
                    # Log key metrics for debugging
                    if analysis_type == 'terrain_analysis':
                        elevation_stats = geoint_results.get('results', {}).get('elevation_statistics', {})
                        if elevation_stats:
                            logger.info(f"🏔️ Elevation: min={elevation_stats.get('min_elevation'):.1f}m, "
                                      f"max={elevation_stats.get('max_elevation'):.1f}m, "
                                      f"mean={elevation_stats.get('mean_elevation'):.1f}m")
                            peak_loc = elevation_stats.get('peak_location', {})
                            if peak_loc:
                                logger.info(f"📍 Peak location: ({peak_loc.get('latitude'):.4f}, "
                                          f"{peak_loc.get('longitude'):.4f}) @ {peak_loc.get('elevation'):.1f}m")
                    
                    elif analysis_type == 'mobility_analysis':
                        mobility_zones = geoint_results.get('results', {}).get('mobility_zones', {})
                        if mobility_zones:
                            go_pct = mobility_zones.get('go_zones', {}).get('percentage', 0)
                            logger.info(f"🚗 Mobility: {go_pct:.1f}% accessible terrain")
                else:
                    logger.warning(f"⚠️ GEOINT analysis completed but returned no results or failed")
                    
            except Exception as e:
                logger.error(f"❌ GEOINT analysis execution failed: {str(e)}", exc_info=True)
                geoint_results = None
        elif stac_params and stac_params.get('geoint_processing'):
            logger.warning("⚠️ GEOINT processing requested but prerequisites not met:")
            logger.warning(f"   - GEOINT_AVAILABLE: {GEOINT_AVAILABLE}")
            logger.warning(f"   - geoint_executor: {geoint_executor is not None}")
            logger.warning(f"   - features: {len(features) if features else 0}")
        
        # PHASE 3: GENERATE RESPONSE MESSAGE
        # 🔍 DEBUG: Log state before response generation to diagnose "no matches" bug
        logger.info(f"🔍 RESPONSE GENERATION DEBUG:")
        logger.info(f"   - features count: {len(features) if features else 0}")
        logger.info(f"   - stac_response features: {len(stac_response.get('results', {}).get('features', []))}")
        logger.info(f"   - SEMANTIC_KERNEL_AVAILABLE: {SEMANTIC_KERNEL_AVAILABLE}")
        logger.info(f"   - translator: {translator is not None}")
        logger.info(f"   - stac_query: {stac_query is not None}")
        
        # 🔧 SAFETY NET: Ensure features variable is synchronized with stac_response
        # This fixes a bug where features could be empty but stac_response has data
        stac_response_features = stac_response.get('results', {}).get('features', [])
        if not features and stac_response_features:
            logger.warning(f"⚠️ MISMATCH DETECTED: features is empty but stac_response has {len(stac_response_features)} features!")
            logger.warning(f"   Synchronizing features from stac_response to prevent 'no matches' bug")
            features = stac_response_features
            search_diagnostics["final_count"] = len(features)
        
        if SEMANTIC_KERNEL_AVAILABLE and translator and features:
            try:
                logger.info("📝 Generating contextual response message...")
                
                # ========================================================================
                # 🚀 AWAIT PARALLEL VISION TASK (if hybrid query)
                # ========================================================================
                # If we started a vision task in parallel with STAC search,
                # now is the time to wait for it to complete before combining results
                # ========================================================================
                vision_result = None
                if 'vision_task' in locals() and vision_task is not None:
                    try:
                        logger.info("⏳ Awaiting parallel vision analysis to complete...")
                        vision_result = await vision_task
                        if vision_result and vision_result.get("analysis"):
                            early_contextual_response = vision_result["analysis"]
                            logger.info("✅ Parallel vision analysis completed and ready for combination")
                        else:
                            logger.warning("⚠️ Vision task completed but no analysis returned")
                    except Exception as e:
                        logger.error(f"❌ Parallel vision task failed: {e}")
                        early_contextual_response = None
                
                # Check if we're showing alternative results
                if search_diagnostics.get("alternative_used"):
                    # 🆕 Generate special message explaining what alternative was shown
                    logger.info("💡 Generating alternative result explanation...")
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
                        logger.info("🔀 Combining vision analysis with STAC data response")
                        response_message = f"""**Visual Analysis:**
{early_contextual_response}

---

**Data Results:**
{response_message}"""
                
                logger.info("✅ Contextual response message generated successfully")
            except Exception as e:
                logger.error(f"❌ Response generation failed: {e}")
                response_message = generate_fallback_response(natural_query, features, stac_query.get("collections", []) if stac_query else [])
        elif not features and stac_query and SEMANTIC_KERNEL_AVAILABLE and translator:
            # 🆕 ENHANCED: Use GPT to generate context-aware response for empty results
            # GPT analyzes the specific failure point and provides intelligent, actionable suggestions
            try:
                logger.info(f"🤖 Generating GPT-powered empty result response (failure stage: {search_diagnostics.get('failure_stage')})")
                response_message = await translator.generate_empty_result_response(
                    natural_query, 
                    stac_query,
                    stac_query.get("collections", []), 
                    search_diagnostics
                )
                logger.info("✅ GPT-generated empty result response created")
            except Exception as e:
                logger.error(f"❌ GPT empty result generation failed, using rule-based fallback: {e}")
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
            logger.info("⚠️ No STAC query generated - using generic fallback")
            response_message = "I can help you find Earth science data, but I need more specific information about the location, time period, or type of imagery you're looking for."
        
        # 🗺️ Generate optimized tile URLs for collections that need seamless multi-tile coverage
        # Multi-tile rendering is for: DEM, MODIS composites, global coverage collections
        # Single-tile rendering is for: Optical imagery (Sentinel-2, HLS, Landsat) where we want the BEST image
        all_tile_urls = []
        all_bboxes = []  # ✅ Collect all bboxes for union calculation
        mosaic_result = None  # 🌍 NEW: Mosaic tilejson result for seamless coverage
        collections = stac_query.get("collections", []) if stac_query else []
        collection_id = collections[0].lower() if collections else ""
        
        # 🔍 DEBUG: Log what collections are in the features vs what was requested
        if features:
            feature_collections = list(set(f.get("collection", "unknown") for f in features))
            logger.info(f"🔍 COLLECTION DEBUG: Requested={collections}, Features contain={feature_collections}")
            if set(feature_collections) != set(collections):
                logger.warning(f"⚠️ MISMATCH: STAC returned different collections than requested!")
        
        # ========================================================================
        # 🌍 MOSAIC SERVICE: RE-ENABLED FOR OPTICAL IMAGERY
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
            logger.info(f"🌍 MOSAIC: Enabling mosaic for optical collection {collection_id}")
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
                    logger.info(f"✅ MOSAIC: Successfully registered mosaic for {collection_id}")
                else:
                    logger.warning(f"⚠️ MOSAIC: Registration failed for {collection_id}, will use item tiles")
            except Exception as e:
                logger.warning(f"⚠️ MOSAIC: Error registering mosaic: {e}")
                mosaic_result = None
        else:
            mosaic_result = None
            if not needs_mosaic:
                logger.info(f"🗺️ MOSAIC: Skipping mosaic for {collection_id} (not an optical collection)")
        
        # 🗺️ TILE RENDERING: Generate individual tile URLs as fallback or supplement
        # The STAC query already returns features that cover the query bbox
        # We generate tile URLs for all features (up to 20) to ensure full area coverage
        # 🎨 OPTIMIZATION: Generate optimized URLs for all features
        if features and len(features) > 0:
            # Process up to 20 features for full bbox coverage
            top_features = features[:20]
            logger.info(f"🗺️ Generating tile URLs for {len(top_features)} features (of {len(features)} total) for {collection_id}")
            
            for feature in top_features:
                tilejson_asset = feature.get("assets", {}).get("tilejson", {})
                if tilejson_asset and "href" in tilejson_asset:
                    feature_bbox = feature.get("bbox")
                    
                    # ✅ VALIDATION: Skip features with invalid bbox (prevents Azure Maps null value errors)
                    if not feature_bbox or len(feature_bbox) != 4:
                        logger.warning(f"⚠️ Skipping feature {feature.get('id')} - invalid bbox: {feature_bbox}")
                        continue
                    
                    # ✅ VALIDATION: Ensure all bbox values are numbers (not None)
                    if any(v is None or not isinstance(v, (int, float)) for v in feature_bbox):
                        logger.warning(f"⚠️ Skipping feature {feature.get('id')} - bbox contains null values: {feature_bbox}")
                        continue
                    
                    collection_id = feature.get("collection", collections[0] if collections else "unknown")
                    
                    # 🎨 Apply quality optimization to tilejson URL
                    original_url = tilejson_asset["href"]
                    
                    # 🛡️ EXPRESSION-BASED COLLECTIONS: Keep original STAC tilejson URL
                    # Collections like alos-palsar-mosaic use expressions (HH;HV;HH/HV) with multiple
                    # rescale values. The STAC tilejson already has the correct rendering params.
                    # Modifying the URL would strip the multi-rescale values and break rendering.
                    expression_collections = ["alos-palsar-mosaic", "sentinel-1-grd", "sentinel-1-rtc"]
                    if collection_id in expression_collections and "expression=" in original_url:
                        logger.info(f"🛡️ Keeping original STAC tilejson for expression-based collection {collection_id}")
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
                        
                        logger.info(f"🎨 Optimized tile URL for {feature.get('id')}: {quality_params}")
                    else:
                        optimized_url = original_url
                        logger.info(f"⚠️ No quality params generated for {feature.get('id')}")
                    
                    all_tile_urls.append({
                        "item_id": feature.get("id"),
                        "bbox": feature_bbox,
                        "tilejson_url": optimized_url  # ✨ Use optimized URL
                    })
                    
                    # ✅ Collect bbox for union calculation
                    if feature_bbox and len(feature_bbox) == 4:
                        all_bboxes.append(feature_bbox)
            
            # Calculate skipped features (features with invalid bbox)
            skipped_count = len(top_features) - len(all_tile_urls)
            
            if all_tile_urls:
                logger.info(f"🗺️ Generated {len(all_tile_urls)} tile URLs for bbox coverage (skipped {skipped_count} with invalid bbox)")
                
                # 🔍 PIPELINE LOG: Tile URLs Output
                log_pipeline_step(pipeline_session_id, "TILE_URLS", "OUTPUT", {
                    "tile_count": len(all_tile_urls),
                    "skipped_invalid_bbox": skipped_count,
                    "tile_ids": [t.get("item_id") for t in all_tile_urls[:5]],  # First 5 for brevity
                    "has_more": len(all_tile_urls) > 5
                })
                
                # ✅ Calculate union bbox covering ALL tiles
                if all_bboxes:
                    union_bbox = [
                        min(bbox[0] for bbox in all_bboxes),  # min lon (west)
                        min(bbox[1] for bbox in all_bboxes),  # min lat (south)
                        max(bbox[2] for bbox in all_bboxes),  # max lon (east)
                        max(bbox[3] for bbox in all_bboxes)   # max lat (north)
                    ]
                    logger.info(f"🗺️ Union bbox calculated: {union_bbox}")
                    logger.info(f"   Coverage: {union_bbox[2] - union_bbox[0]:.2f}° × {union_bbox[3] - union_bbox[1]:.2f}°")
                    
                    # 🔍 PIPELINE LOG: Union BBox
                    log_pipeline_step(pipeline_session_id, "UNION_BBOX", "OUTPUT", {
                        "bbox": union_bbox,
                        "width_deg": round(union_bbox[2] - union_bbox[0], 2),
                        "height_deg": round(union_bbox[3] - union_bbox[1], 2)
                    })
                    
                    # ✅ Update stac_params with union bbox for response metadata
                    if stac_params:
                        stac_params["bbox"] = union_bbox
                        logger.info(f"✅ Updated stac_params bbox to union: {union_bbox}")

        
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
                "all_tile_urls": all_tile_urls if all_tile_urls else None,  # ✨ Individual tile URLs for multi-tile rendering
                # 🌍 NEW: Mosaic tilejson for seamless composited coverage
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
                # 🔬 INSTANT PIPELINE TRACE - Visible in browser console!
                "pipeline_trace": {
                    "session_id": pipeline_session_id,
                    "steps": get_pipeline_trace(pipeline_session_id)
                }
            }
        }
        
        # 🔬 TRACE: Final response summary
        log_pipeline_step(pipeline_session_id, "RESPONSE", "OUTPUT", {
            "success": True,
            "total_tiles": len(all_tile_urls) if all_tile_urls else 0,
            "total_features": len(features),
            "has_mosaic": mosaic_result is not None,
            "collections": stac_query.get("collections", []) if stac_query else []
        })
        
        logger.info("✅ Unified query processing completed successfully")
        
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
                    "assets": {k: {"href": v.get("href")} for k, v in (f.get("assets") or {}).items()}
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
            logger.info(f"🗺️ Updated session context: has_rendered_map=True, collections={stac_render_context['last_collections']}, stac_items={len(stac_items_for_vision)}")
        
        
        return complete_response
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ Unified query processor error: {str(e)}")
        logger.error(traceback.format_exc())
        raise HTTPException(status_code=500, detail=f"Query processing failed: {str(e)}")

@app.post("/api/stac-search")
async def stac_search(request: Request):
    """Direct STAC search endpoint for backwards compatibility (ported from Router Function App)"""
    try:
        logger.info("🔍 Direct STAC search endpoint called")
        
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
        logger.info("🛰️ VEDA STAC search endpoint called")
        
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
        logger.info("🔧 Structured search endpoint called")
        logger.info("="*100)
        logger.info("🔧🔧🔧 POST /api/structured-search ENDPOINT HIT 🔧🔧🔧")
        logger.info("="*100)
        
        req_body = await request.json()
        if not req_body:
            raise HTTPException(status_code=400, detail="Request body required")
        
        collection = req_body.get('collection')
        location = req_body.get('location')
        datetime_single = req_body.get('datetime')
        datetime_start = req_body.get('datetime_start')
        datetime_end = req_body.get('datetime_end')
        
        logger.info(f"📦 Structured search params:")
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
            logger.error("❌ Semantic translator not initialized")
            raise HTTPException(
                status_code=500,
                detail="Semantic translator not initialized. Please try again."
            )
        
        # ========================================================================
        # 🤖 USE FULL MULTI-AGENT PIPELINE FOR STRUCTURED SEARCH
        # ========================================================================
        # Build a natural language query from structured parameters to leverage
        # the full agent pipeline (collection validation, datetime parsing, 
        # spatial coverage, rendering config, etc.)
        # ========================================================================
        
        logger.info("🤖 Converting structured parameters to natural language for agent pipeline")
        
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
        logger.info(f"📝 Constructed natural language query: '{natural_query}'")
        
        # Use the semantic translator's translate_query method (FULL AGENT PIPELINE)
        logger.info("🔄 Running full multi-agent translation pipeline...")
        stac_params = await global_translator.translate_query(natural_query, pin_location=None)
        
        # Check if translation was successful
        if not stac_params or not stac_params.get('collections'):
            logger.error(f"❌ Agent pipeline failed to produce valid STAC parameters")
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
        
        logger.info(f"✅ Structured search complete: {num_items} items found")
        
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
        
        logger.info(f"🔄 {message}")
        
        return {
            "status": "success",
            "message": message,
            "session_id": conversation_id,
            "timestamp": datetime.utcnow().isoformat()
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ Session reset failed: {e}")
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
    - Location resolution: build_stac_query_agent → bbox extraction (same as regular queries)
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
        logger.info("=" * 100)
        logger.info("📊 COMPARISON QUERY PROCESSING STARTED")
        logger.info("=" * 100)
        
        data = await request.json()
        user_query = data.get("query", "")
        
        logger.info(f"📝 User Query: '{user_query}'")
        logger.info(f"📦 Request Data: {data}")
        
        if not user_query:
            logger.error("❌ No query provided in request")
            raise HTTPException(status_code=400, detail="Query is required")
        
        logger.info(f"✅ Query validation passed")
        
        # Use global semantic_translator instance
        global semantic_translator
        if not semantic_translator:
            logger.error("❌ Semantic translator not initialized!")
            raise HTTPException(status_code=500, detail="Semantic translator not initialized")
        
        logger.info("✅ Semantic translator instance verified")
        
        # ========================================================================
        # STEP 1: Collection Selection (REUSE existing agent)
        # ========================================================================
        logger.info("")
        logger.info("=" * 80)
        logger.info("STEP 1: COLLECTION SELECTION")
        logger.info("=" * 80)
        logger.info(f"🤖 Calling collection_mapping_agent with query: '{user_query}'")
        
        collections = await semantic_translator.collection_mapping_agent(user_query)
        
        logger.info(f"✅ Collection selection completed")
        logger.info(f"📊 Number of collections: {len(collections)}")
        logger.info(f"📋 Collections: {collections}")
        
        if not collections:
            logger.warning("⚠️ No collections returned from collection_mapping_agent")
        
        # ========================================================================
        # STEP 2: Location + Spatial Context (REUSE existing agent)
        # ========================================================================
        logger.info("")
        logger.info("=" * 80)
        logger.info("STEP 2: LOCATION RESOLUTION")
        logger.info("=" * 80)
        logger.info(f"🤖 Calling build_stac_query_agent with query: '{user_query}'")
        logger.info(f"📋 Collections passed to agent: {collections}")
        
        stac_query = await semantic_translator.build_stac_query_agent(user_query, collections)
        
        logger.info(f"✅ Location resolution completed")
        logger.info(f"📦 STAC Query Result: {stac_query}")
        
        bbox = stac_query.get("bbox")
        location_name = stac_query.get("location_name", "Unknown location")
        
        logger.info(f"📍 Location Name: {location_name}")
        logger.info(f"📦 Bounding Box: {bbox}")
        
        if not bbox:
            logger.error(f"❌ No bbox returned from build_stac_query_agent")
            logger.error(f"❌ STAC Query was: {stac_query}")
            raise HTTPException(
                status_code=400,
                detail=f"Could not resolve location from query: '{user_query}'"
            )
        
        # Extract center point from bbox [west, south, east, north]
        lng = (bbox[0] + bbox[2]) / 2  # Average of west and east
        lat = (bbox[1] + bbox[3]) / 2  # Average of south and north
        
        logger.info(f"✅ Center coordinates calculated")
        logger.info(f"📍 Latitude: {lat:.6f}")
        logger.info(f"📍 Longitude: {lng:.6f}")
        logger.info(f"📦 Full Bbox: [W:{bbox[0]:.4f}, S:{bbox[1]:.4f}, E:{bbox[2]:.4f}, N:{bbox[3]:.4f}]")
        
        # ========================================================================
        # STEP 3: Temporal Extraction (NEW comparison mode for dual dates)
        # ========================================================================
        logger.info("")
        logger.info("=" * 80)
        logger.info("STEP 3: DUAL-DATE EXTRACTION (COMPARISON MODE)")
        logger.info("=" * 80)
        logger.info(f"🤖 Calling datetime_translation_agent with mode='comparison'")
        logger.info(f"📝 Query: '{user_query}'")
        logger.info(f"📋 Collections: {collections}")
        
        datetime_result = await semantic_translator.datetime_translation_agent(
            query=user_query,
            collections=collections,
            mode="comparison"  # NEW: Returns {"before": "...", "after": "...", "explanation": "..."}
        )
        
        logger.info(f"✅ Datetime extraction completed")
        logger.info(f"📅 Datetime Result: {datetime_result}")
        
        if not datetime_result:
            logger.error("❌ datetime_translation_agent returned None or empty result")
            raise HTTPException(
                status_code=400,
                detail="Could not extract timeframes from query. Please specify time periods (e.g., 'between 2023 and 2024')."
            )
        
        if "before" not in datetime_result or "after" not in datetime_result:
            logger.error(f"❌ Missing 'before' or 'after' in datetime result: {datetime_result}")
            raise HTTPException(
                status_code=400,
                detail="Could not extract before/after timeframes from query. Please specify time periods (e.g., 'between 2023 and 2024')."
            )
        
        before_date = datetime_result["before"]
        after_date = datetime_result["after"]
        explanation = datetime_result.get("explanation", "")
        
        logger.info(f"✅ Date extraction successful")
        logger.info(f"📅 Before Date: {before_date}")
        logger.info(f"📅 After Date: {after_date}")
        logger.info(f"� Explanation: {explanation}")
        
        # ========================================================================
        # STEP 4: Determine Primary Collection for Raster Analysis
        # ========================================================================
        logger.info("")
        logger.info("=" * 80)
        logger.info("STEP 4: PRIMARY COLLECTION SELECTION")
        logger.info("=" * 80)
        logger.info(f"📋 Available collections: {collections}")
        # ========================================================================
        # STEP 4: Determine Primary Collection for Raster Analysis
        # ========================================================================
        logger.info("")
        logger.info("=" * 80)
        logger.info("STEP 4: PRIMARY COLLECTION SELECTION")
        logger.info("=" * 80)
        logger.info(f"📋 Available collections: {collections}")
        # Select the most relevant collection for quantitative raster download
        # Priority: specialized data > optical imagery
        primary_collection = None
        aspect = "general change"
        
        if collections:
            # Priority order for raster analysis
            priority_map = {
                "modis-14A1-061": "wildfire activity",  # Fire intensity
                "cop-dem-glo-30": "terrain/elevation",   # Elevation data
                "cop-dem-glo-90": "terrain/elevation",
                "alos-dem": "terrain/elevation",
                "sentinel-2-l2a": "optical imagery",     # Multi-spectral
                "landsat-c2-l2": "optical imagery"
            }
            
            logger.info(f"🎯 Checking priority collections...")
            # Find first matching priority collection
            for priority_collection, priority_aspect in priority_map.items():
                if priority_collection in collections:
                    primary_collection = priority_collection
                    aspect = priority_aspect
                    logger.info(f"✅ Found priority match: {priority_collection} → {priority_aspect}")
                    break
            
            # Fallback: use first collection
            if not primary_collection and collections:
                primary_collection = collections[0]
                aspect = "general change"
                logger.info(f"⚠️ No priority match, using first collection: {primary_collection}")
        else:
            logger.warning("⚠️ No collections available for primary selection")
        
        logger.info(f"✅ Primary collection selected: {primary_collection}")
        logger.info(f"🎯 Analysis aspect: {aspect}")
        
        # ========================================================================
        # FINAL RESULT
        # ========================================================================
        logger.info("")
        logger.info("=" * 80)
        logger.info("COMPARISON QUERY PROCESSING COMPLETED")
        logger.info("=" * 80)
        
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
        
        logger.info(f"📊 Final Result:")
        logger.info(f"   Location: {location_name} ({lat:.4f}, {lng:.4f})")
        logger.info(f"   Bbox: {bbox}")
        logger.info(f"   Before: {before_date}")
        logger.info(f"   After: {after_date}")
        logger.info(f"   Collections: {collections}")
        logger.info(f"   Primary: {primary_collection}")
        logger.info(f"   Aspect: {aspect}")
        logger.info("=" * 100)
        
        return result
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error("=" * 100)
        logger.error("❌ COMPARISON QUERY PROCESSING FAILED")
        logger.error("=" * 100)
        logger.exception(f"❌ Exception occurred: {e}")
        logger.error(f"❌ Exception type: {type(e).__name__}")
        logger.error(f"❌ Exception message: '{str(e)}'")
        logger.error(f"❌ Exception repr: {repr(e)}")
        logger.error("=" * 100)
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
    
    Request body:
    {
        "latitude": float,
        "longitude": float,
        "screenshot": str (optional - base64 screenshot),
        "user_query": str (optional - user context),
        "user_context": str (optional - legacy field name)
    }
    """
    try:
        logger.info("🎖️ GEOINT Mobility endpoint called")
        
        # Parse request body
        request_data = await request.json()
        latitude = request_data.get("latitude")
        longitude = request_data.get("longitude")
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
        
        # Call mobility_analysis_agent (new agent-based architecture)
        from geoint.agents import mobility_analysis_agent
        
        analysis_result = await mobility_analysis_agent(
            latitude=latitude,
            longitude=longitude,
            screenshot_base64=screenshot_base64,
            user_query=user_query,
            include_vision=True
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
        logger.error(f"❌ GEOINT Mobility Analysis failed: {e}")
        logger.error(traceback.format_exc())
        raise HTTPException(
            status_code=500,
            detail=f"GEOINT mobility analysis failed: {str(e)}"
        )

# ============================================================================
# 🧠 GEOINT MODULE-SPECIFIC ENDPOINTS
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
        logger.info(f"🏔️ [{request_id}] ============================================================")
        logger.info(f"🏔️ [{request_id}] TERRAIN ENDPOINT CALLED")
        logger.info(f"🏔️ [{request_id}] ============================================================")
        logger.info(f"🏔️ [{request_id}] Request method: {request.method}")
        logger.info(f"🏔️ [{request_id}] Request URL: {request.url}")
        logger.info(f"🏔️ [{request_id}] Client: {request.client}")
        
        # Parse request body
        logger.info(f"🏔️ [{request_id}] Parsing request body...")
        request_data = await request.json()
        logger.info(f"🏔️ [{request_id}] ✅ Request body parsed successfully")
        logger.info(f"🏔️ [{request_id}] Request keys: {list(request_data.keys())}")
        
        latitude = request_data.get("latitude")
        longitude = request_data.get("longitude")
        screenshot = request_data.get("screenshot")
        user_query = request_data.get("user_query") or request_data.get("user_context")
        radius_miles = request_data.get("radius_miles", 5.0)
        session_id = request_data.get("session_id")  # NEW: For follow-up questions
        
        screenshot_size = len(screenshot) if screenshot else 0
        logger.info(f"🏔️ [{request_id}] Screenshot size: {screenshot_size} chars ({screenshot_size / 1024:.1f} KB)")
        logger.info(f"🏔️ [{request_id}] Session ID: {session_id or 'NEW SESSION'}")
        
        # ===== CRITICAL DEBUG: Screenshot validation =====
        if screenshot:
            logger.info(f"🏔️ [{request_id}] Screenshot received: YES")
            logger.info(f"🏔️ [{request_id}] Screenshot starts with: {screenshot[:50]}")
            
            # Check if it has data URL prefix (should be removed by frontend)
            if screenshot.startswith('data:image'):
                logger.warning(f"🏔️ [{request_id}] ⚠️ Screenshot has data URL prefix (will be handled)")
            else:
                logger.info(f"🏔️ [{request_id}] Screenshot is pure base64 (correct format)")
                
            # Validate minimum size (empty canvas produces very small PNGs)
            if screenshot_size < 5000:
                logger.warning(f"🏔️ [{request_id}] ⚠️ Screenshot is very small ({screenshot_size} chars) - may be blank canvas!")
            else:
                logger.info(f"🏔️ [{request_id}] Screenshot size looks good (>{screenshot_size / 1024:.1f}KB)")
        else:
            logger.warning(f"🏔️ [{request_id}] ⚠️ NO SCREENSHOT PROVIDED - will use STAC fallback")
        # ===== END CRITICAL DEBUG =====
        
        # Validate required parameters
        logger.info(f"🏔️ [{request_id}] Validating parameters...")
        if latitude is None or longitude is None:
            logger.error(f"🏔️ [{request_id}] ❌ Missing required parameters")
            raise HTTPException(status_code=400, detail="latitude and longitude are required")
        
        # Validate coordinates
        if not (-90 <= latitude <= 90):
            logger.error(f"🏔️ [{request_id}] ❌ Invalid latitude: {latitude}")
            raise HTTPException(status_code=400, detail=f"Invalid latitude: {latitude}")
        if not (-180 <= longitude <= 180):
            logger.error(f"🏔️ [{request_id}] ❌ Invalid longitude: {longitude}")
            raise HTTPException(status_code=400, detail=f"Invalid longitude: {longitude}")
        
        logger.info(f"🏔️ [{request_id}] ✅ Parameters valid")
        logger.info(f"🏔️ [{request_id}] Coordinates: ({latitude}, {longitude})")
        logger.info(f"🏔️ [{request_id}] Radius: {radius_miles} miles")
        logger.info(f"🏔️ [{request_id}] User query: {user_query}")
        
        import time
        agent_start = time.time()
        
        # ========================================================================
        # DECISION: Use TerrainAgent (with memory) if session_id provided OR user_query exists
        # Otherwise use one-shot terrain_analysis_agent for initial analysis
        # ========================================================================
        
        if session_id or user_query:
            # Use the REAL TerrainAgent with conversation memory
            logger.info(f"🏔️ [{request_id}] ============================================================")
            logger.info(f"🏔️ [{request_id}] USING TERRAIN AGENT (with memory and tools)")
            logger.info(f"🏔️ [{request_id}] ============================================================")
            
            from geoint.terrain_agent import get_terrain_agent
            agent = get_terrain_agent()
            
            # Create session_id if not provided (for new conversations)
            if not session_id:
                session_id = str(uuid.uuid4())
                logger.info(f"🏔️ [{request_id}] Created new session: {session_id}")
            
            # Build the message for the agent
            if user_query:
                message = user_query
            else:
                message = "Provide a comprehensive terrain analysis of this location including elevation, slope, and terrain classification."
            
            # Call the agent
            import asyncio
            try:
                result = await asyncio.wait_for(
                    agent.chat(
                        session_id=session_id,
                        user_message=message,
                        latitude=latitude,
                        longitude=longitude,
                        screenshot_base64=screenshot,
                        radius_km=radius_miles * 1.609  # Convert miles to km
                    ),
                    timeout=240.0
                )
            except asyncio.TimeoutError:
                agent_elapsed = time.time() - agent_start
                logger.error(f"🏔️ [{request_id}] ❌ AGENT TIMEOUT after {agent_elapsed:.1f}s")
                raise HTTPException(
                    status_code=504,
                    detail=f"Terrain analysis timed out after {agent_elapsed:.1f}s. Please try again."
                )
            
            agent_elapsed = time.time() - agent_start
            logger.info(f"🏔️ [{request_id}] ✅ TERRAIN AGENT COMPLETED ({agent_elapsed:.2f}s)")
            
            # Check if agent signaled exit mode
            if result.get("tool_calls"):
                for tool_call in result["tool_calls"]:
                    if tool_call.get("tool") == "exit_analysis_mode":
                        logger.info(f"🏔️ [{request_id}] 🚪 Agent requested EXIT_GEOINT_MODE")
                        return {
                            "status": "exit_mode",
                            "action": "EXIT_GEOINT_MODE",
                            "reprocess_query": result.get("response", user_query),
                            "session_id": session_id,
                            "timestamp": datetime.utcnow().isoformat()
                        }
            
            return {
                "status": "success",
                "result": {
                    "analysis": result.get("response", ""),
                    "tool_calls": result.get("tool_calls", []),
                    "message_count": result.get("message_count", 1)
                },
                "session_id": session_id,  # Return for follow-up questions
                "timestamp": datetime.utcnow().isoformat()
            }
        
        else:
            # LEGACY: Use one-shot terrain_analysis_agent (no memory)
            logger.info(f"🏔️ [{request_id}] ============================================================")
            logger.info(f"🏔️ [{request_id}] USING LEGACY ONE-SHOT AGENT (no memory)")
            logger.info(f"🏔️ [{request_id}] ============================================================")
            
            from geoint.agents import terrain_analysis_agent
            
            import asyncio
            try:
                analysis_result = await asyncio.wait_for(
                    terrain_analysis_agent(
                        latitude=latitude,
                        longitude=longitude,
                        screenshot_base64=screenshot,
                        user_query=user_query,
                        radius_miles=radius_miles
                    ),
                    timeout=240.0
                )
            except asyncio.TimeoutError:
                agent_elapsed = time.time() - agent_start
                logger.error(f"🏔️ [{request_id}] ❌ AGENT TIMEOUT after {agent_elapsed:.1f}s")
                raise HTTPException(
                    status_code=504,
                    detail=f"Terrain analysis timed out after {agent_elapsed:.1f}s. Please try again."
                )
            
            agent_elapsed = time.time() - agent_start
            logger.info(f"🏔️ [{request_id}] ✅ TERRAIN AGENT COMPLETED ({agent_elapsed:.2f}s)")
            
            # Generate a session_id for potential follow-ups
            session_id = str(uuid.uuid4())
            
            return {
                "status": "success",
                "result": analysis_result,
                "session_id": session_id,  # Client can use this for follow-up questions
                "timestamp": datetime.utcnow().isoformat()
            }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"🏔️ [{request_id}] ============================================================")
        logger.error(f"🏔️ [{request_id}] ❌ TERRAIN ENDPOINT FAILED")
        logger.error(f"🏔️ [{request_id}] ============================================================")
        logger.error(f"🏔️ [{request_id}] Error: {e}")
        logger.error(f"🏔️ [{request_id}] Traceback:")
        logger.error(traceback.format_exc())
        raise HTTPException(
            status_code=500,
            detail=f"Terrain analysis failed: {str(e)}"
        )


@app.post("/api/geoint/terrain/chat")
async def geoint_terrain_chat(request: Request):
    """
    🤖 GEOINT Terrain Agent Chat - Multi-turn conversation with memory
    
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
        logger.info(f"💬 [{request_id}] ============================================================")
        logger.info(f"💬 [{request_id}] TERRAIN AGENT CHAT ENDPOINT")
        logger.info(f"💬 [{request_id}] ============================================================")
        
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
        
        logger.info(f"💬 [{request_id}] Session: {session_id}")
        logger.info(f"💬 [{request_id}] Message: {message[:100]}...")
        logger.info(f"💬 [{request_id}] Location: ({latitude}, {longitude})")
        logger.info(f"💬 [{request_id}] Screenshot: {'Yes (' + str(len(screenshot)) + ' chars)' if screenshot else 'No'}")
        if screenshot:
            logger.info(f"💬 [{request_id}] Screenshot starts with: {screenshot[:60]}...")
        
        # Get the terrain agent
        from geoint.terrain_agent import get_terrain_agent
        agent = get_terrain_agent()
        
        # Process the message
        import time
        start_time = time.time()
        
        result = await agent.chat(
            session_id=session_id,
            user_message=message,
            latitude=latitude,
            longitude=longitude,
            screenshot_base64=screenshot,
            radius_km=radius_km
        )
        
        elapsed = time.time() - start_time
        logger.info(f"💬 [{request_id}] ✅ Agent responded in {elapsed:.2f}s")
        logger.info(f"💬 [{request_id}] Tool calls: {len(result.get('tool_calls', []))}")
        
        return {
            "status": "success",
            **result,
            "timestamp": datetime.utcnow().isoformat()
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"💬 [{request_id}] ❌ Chat endpoint failed: {e}")
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
        logger.info(f"👁️ [{request_id}] ============================================================")
        logger.info(f"👁️ [{request_id}] VISION ENDPOINT CALLED")
        logger.info(f"👁️ [{request_id}] ============================================================")
        
        # Parse request body
        request_data = await request.json()
        logger.info(f"👁️ [{request_id}] Request keys: {list(request_data.keys())}")
        
        latitude = request_data.get("latitude")
        longitude = request_data.get("longitude")
        screenshot = request_data.get("screenshot")
        user_query = request_data.get("user_query") or request_data.get("user_context")
        radius_miles = request_data.get("radius_miles", 5.0)
        session_id = request_data.get("session_id")
        
        # 👁️ NEW: Accept tile_urls and collection directly from frontend
        tile_urls_from_request = request_data.get("tile_urls", [])
        collection_from_request = request_data.get("collection")
        map_bounds_from_request = request_data.get("map_bounds")
        # 📊 NEW: Accept STAC items with assets directly from frontend for NDVI/raster analysis
        stac_items_from_request = request_data.get("stac_items", [])
        
        screenshot_size = len(screenshot) if screenshot else 0
        logger.info(f"👁️ [{request_id}] Screenshot: {screenshot_size / 1024:.1f} KB")
        logger.info(f"👁️ [{request_id}] Session ID: {session_id or 'NEW SESSION'}")
        logger.info(f"👁️ [{request_id}] User query: {user_query}")
        logger.info(f"👁️ [{request_id}] Tile URLs from request: {len(tile_urls_from_request)}")
        logger.info(f"👁️ [{request_id}] STAC items from request: {len(stac_items_from_request)}")
        logger.info(f"👁️ [{request_id}] Collection from request: {collection_from_request}")
        
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
        
        logger.info(f"👁️ [{request_id}] Coordinates: ({latitude}, {longitude})")
        logger.info(f"👁️ [{request_id}] Radius: {radius_miles} miles")
        
        import time
        agent_start = time.time()
        
        # Get Vision Agent (SK Agent with memory and vision tools)
        from agents import get_vision_agent
        vision_agent = get_vision_agent()
        
        # Create session_id if not provided
        if not session_id:
            session_id = str(uuid.uuid4())
            logger.info(f"👁️ [{request_id}] Created new session: {session_id}")
        
        # Build the message for the agent
        if not user_query:
            user_query = "Analyze this location. What can you identify from the imagery?"
        
        # Gather STAC context - prefer request data over session context
        # Use bounds from request if provided, otherwise build from coordinates
        if map_bounds_from_request:
            map_bounds = map_bounds_from_request
            # Ensure center coordinates are present
            if 'center_lat' not in map_bounds:
                map_bounds['center_lat'] = latitude
            if 'center_lng' not in map_bounds:
                map_bounds['center_lng'] = longitude
        else:
            map_bounds = {
                'center_lat': latitude,
                'center_lng': longitude
            }
        
        # Get STAC context - prefer request data, fallback to session context
        collections_list = []
        stac_items_from_session = []
        tile_urls_for_agent = tile_urls_from_request  # Direct from frontend
        
        # Use collection from request if provided
        if collection_from_request:
            collections_list = [collection_from_request]
        
        # 📊 PREFER STAC items from request (frontend has them with assets)
        # Only fallback to session context if request didn't provide STAC items
        if stac_items_from_request:
            stac_items_from_session = stac_items_from_request
            logger.info(f"👁️ [{request_id}] Using {len(stac_items_from_request)} STAC items from request (with assets for NDVI)")
        elif router_agent and session_id:
            # Fallback: Try to get STAC items from session context
            session_context = router_agent.tools.session_contexts.get(session_id, {})
            if not collections_list:
                collections_list = session_context.get('last_collections', [])
            stac_items_from_session = session_context.get('last_stac_items', [])
            logger.info(f"👁️ [{request_id}] Loaded session context: collections={collections_list}, stac_items={len(stac_items_from_session)}")
        
        logger.info(f"👁️ [{request_id}] Tile URLs for agent: {len(tile_urls_for_agent)}")
        logger.info(f"👁️ [{request_id}] STAC Items from session: {len(stac_items_from_session)}")
        logger.info(f"👁️ [{request_id}] Collections: {collections_list}")
        
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
                    conversation_history=[]
                ),
                timeout=240.0
            )
        except asyncio.TimeoutError:
            agent_elapsed = time.time() - agent_start
            logger.error(f"👁️ [{request_id}] ❌ AGENT TIMEOUT after {agent_elapsed:.1f}s")
            raise HTTPException(
                status_code=504,
                detail=f"Vision analysis timed out after {agent_elapsed:.1f}s. Please try again."
            )
        
        agent_elapsed = time.time() - agent_start
        logger.info(f"👁️ [{request_id}] ✅ VISION AGENT COMPLETED ({agent_elapsed:.2f}s)")
        
        response_text = result.get("response") or result.get("analysis")
        
        if not response_text:
            logger.warning(f"👁️ [{request_id}] Empty response from vision agent")
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
        logger.error(f"👁️ [{request_id}] ❌ VISION ENDPOINT FAILED")
        logger.error(f"👁️ [{request_id}] Error: {e}")
        logger.error(traceback.format_exc())
        raise HTTPException(
            status_code=500,
            detail=f"Vision analysis failed: {str(e)}"
        )


@app.post("/api/geoint/vision/chat")
async def geoint_vision_chat(request: Request):
    """
    🤖 GEOINT Vision Agent Chat - Multi-turn conversation with memory
    
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
        logger.info(f"💬 [{request_id}] VISION CHAT endpoint called")
        
        request_data = await request.json()
        session_id = request_data.get("session_id")
        message = request_data.get("message")
        latitude = request_data.get("latitude")
        longitude = request_data.get("longitude")
        screenshot = request_data.get("screenshot")
        
        # 👁️ NEW: Accept tile_urls and collection from frontend
        tile_urls_from_request = request_data.get("tile_urls", [])
        collection_from_request = request_data.get("collection")
        # 📊 NEW: Accept STAC items with assets from frontend for NDVI/raster analysis
        stac_items_from_request = request_data.get("stac_items", [])
        
        if not session_id:
            raise HTTPException(status_code=400, detail="session_id is required for chat")
        
        if not message:
            raise HTTPException(status_code=400, detail="message is required")
        
        logger.info(f"💬 [{request_id}] Session: {session_id}")
        logger.info(f"💬 [{request_id}] Message: {message[:100]}")
        logger.info(f"💬 [{request_id}] Tile URLs from request: {len(tile_urls_from_request)}")
        logger.info(f"💬 [{request_id}] STAC items from request: {len(stac_items_from_request)}")
        # 🔍 DETAILED STAC ITEM LOGGING
        if stac_items_from_request:
            for i, item in enumerate(stac_items_from_request[:2]):
                logger.info(f"💬 [{request_id}] STAC item {i}: id={item.get('id', 'unknown')}, collection={item.get('collection', 'unknown')}, assets={list(item.get('assets', {}).keys())[:5]}")
        logger.info(f"💬 [{request_id}] Collection from request: {collection_from_request}")
        
        from agents import get_vision_agent
        vision_agent = get_vision_agent()
        
        # Prepare context
        map_bounds = None
        if latitude and longitude:
            map_bounds = {
                'center_lat': latitude,
                'center_lng': longitude
            }
        
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
        
        # 📊 CRITICAL: Prefer STAC items from request (has fresh assets/band URLs for NDVI)
        final_stac_items = stac_items_from_request if stac_items_from_request else stac_items_from_session
        logger.info(f"💬 [{request_id}] Using {len(final_stac_items)} STAC items for analysis (request: {len(stac_items_from_request)}, session: {len(stac_items_from_session)})")
        
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
                conversation_history=[]
            ),
            timeout=120.0
        )
        
        logger.info(f"💬 [{request_id}] ✅ Vision chat completed")
        
        return {
            "status": "success",
            "result": {
                "response": result.get("response") or result.get("analysis"),
                "tools_used": result.get("tools_used", [])
            },
            "session_id": session_id,
            "timestamp": datetime.utcnow().isoformat()
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"💬 [{request_id}] ❌ Vision chat failed: {e}")
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
    🏗️ GEOINT Building Damage Assessment
    
    Structure damage assessment using GPT-5 Vision and satellite imagery.
    Analyzes building structural integrity, damage patterns, and safety assessment.
    
    Request body:
    {
        "latitude": float,
        "longitude": float,
        "user_context": str (optional)
    }
    
    Returns:
    {
        "status": "success",
        "damage_assessment": dict,
        "severity_level": str,
        "recommendations": list[str],
        "timestamp": str
    }
    """
    try:
        body = await request.json()
        latitude = body.get("latitude")
        longitude = body.get("longitude")
        user_context = body.get("user_context", "")
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
        
        # Call building_damage_agent (new agent-based architecture)
        from geoint.agents import building_damage_agent
        
        analysis_result = await building_damage_agent(
            latitude=latitude,
            longitude=longitude,
            screenshot_base64=screenshot,
            user_query=user_context,
            radius_miles=radius_miles
        )
        
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
        logger.info("=" * 100)
        logger.info("📊 COMPARISON ANALYSIS ENDPOINT CALLED")
        logger.info("=" * 100)
        
        body = await request.json()
        
        logger.info(f"📦 Request body keys: {list(body.keys())}")
        
        user_query = body.get("user_query")
        latitude = body.get("latitude")
        longitude = body.get("longitude")
        before_date = body.get("before_date")
        after_date = body.get("after_date")
        
        # Debug logging for mode detection
        logger.info(f"🔍 Mode detection inputs:")
        logger.info(f"   user_query: '{user_query}' (truthy: {bool(user_query)})")
        logger.info(f"   before_date: '{before_date}' (truthy: {bool(before_date)})")
        logger.info(f"   after_date: '{after_date}' (truthy: {bool(after_date)})")
        logger.info(f"   Condition: user_query and not (before_date and after_date) = {bool(user_query and not (before_date and after_date))}")
        
        # ================================================================
        # MODE 1: QUERY-BASED COMPARISON (new flow)
        # User provides natural language query, we parse and execute
        # ================================================================
        if user_query and not (before_date and after_date):
            logger.info(f"🔍 QUERY MODE: Parsing query for comparison parameters...")
            logger.info(f"💬 User query: {user_query}")
            
            try:
                from geoint.comparison_agent import get_comparison_agent
                comparison_agent = get_comparison_agent()
                
                result = await comparison_agent.handle_query(
                    user_query=user_query,
                    latitude=latitude,
                    longitude=longitude,
                    session_id=body.get("session_id")
                )
                
                logger.info(f"✅ Comparison agent returned: status={result.get('status')}")
                
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
                logger.error(f"❌ Query mode failed: {e}", exc_info=True)
                return {
                    "status": "error",
                    "message": f"Comparison query processing failed: {str(e)}",
                    "timestamp": datetime.utcnow().isoformat()
                }
        
        # ================================================================
        # MODE 2: SCREENSHOT-BASED COMPARISON (legacy flow)
        # Requires pre-parsed dates and optional screenshots
        # ================================================================
        logger.info(f"📸 SCREENSHOT MODE: Using provided dates and screenshots...")
        
        before_screenshot = body.get("before_screenshot")
        after_screenshot = body.get("after_screenshot")
        before_metadata = body.get("before_metadata")
        after_metadata = body.get("after_metadata")
        comparison_aspect = body.get("comparison_aspect")
        collection_id = body.get("collection_id")
        download_rasters = body.get("download_rasters", True)
        
        logger.info(f"📍 Location: ({latitude}, {longitude})")
        logger.info(f"📅 Before Date: {before_date}")
        logger.info(f"📅 After Date: {after_date}")
        logger.info(f"📸 Before Screenshot: {'Provided' if before_screenshot else 'None'} ({len(before_screenshot) if before_screenshot else 0} chars)")
        logger.info(f"📸 After Screenshot: {'Provided' if after_screenshot else 'None'} ({len(after_screenshot) if after_screenshot else 0} chars)")
        logger.info(f"📊 Before Metadata: {'Provided' if before_metadata else 'None'}")
        logger.info(f"📊 After Metadata: {'Provided' if after_metadata else 'None'}")
        logger.info(f"💬 User Query: {user_query}")
        logger.info(f"🎯 Comparison Aspect: {comparison_aspect}")
        logger.info(f"📋 Collection ID: {collection_id}")
        logger.info(f"⬇️  Download Rasters: {download_rasters}")
        
        # Validation
        logger.info("🔍 Validating required parameters...")
        
        if not all([latitude, longitude, before_date, after_date]):
            logger.error("❌ Missing required parameters")
            logger.error(f"   latitude: {latitude}")
            logger.error(f"   longitude: {longitude}")
            logger.error(f"   before_date: {before_date}")
            logger.error(f"   after_date: {after_date}")
            raise HTTPException(status_code=400, detail="Missing required parameters: latitude, longitude, before_date, after_date")
        
        if not (-90 <= latitude <= 90):
            logger.error(f"❌ Invalid latitude: {latitude}")
            raise HTTPException(status_code=400, detail=f"Invalid latitude: {latitude}")
        
        if not (-180 <= longitude <= 180):
            logger.error(f"❌ Invalid longitude: {longitude}")
            raise HTTPException(status_code=400, detail=f"Invalid longitude: {longitude}")
        
        # Screenshots are optional if raster download is enabled with collection_id
        has_screenshots = before_screenshot and after_screenshot
        can_download_rasters = download_rasters and collection_id
        
        logger.info(f"✅ Has screenshots: {has_screenshots}")
        logger.info(f"✅ Can download rasters: {can_download_rasters}")
        
        if not has_screenshots and not can_download_rasters:
            logger.error("❌ Neither screenshots nor raster data source provided")
            raise HTTPException(
                status_code=400, 
                detail="Either screenshots (before_screenshot + after_screenshot) OR raster data (collection_id + download_rasters=true) must be provided"
            )
        
        logger.info("✅ All validation checks passed")
        logger.info("")
        logger.info("🤖 Calling comparison_analysis_agent...")
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
        
        logger.info("=" * 100)
        logger.info("✅ COMPARISON ANALYSIS COMPLETED SUCCESSFULLY")
        logger.info("=" * 100)
        logger.info(f"📊 Result keys: {list(analysis_result.keys()) if isinstance(analysis_result, dict) else 'Not a dict'}")
        if isinstance(analysis_result, dict):
            logger.info(f"   - text length: {len(analysis_result.get('text', ''))} chars")
            logger.info(f"   - images_used: {analysis_result.get('images_used', 0)}")
            logger.info(f"   - raster_analysis_included: {analysis_result.get('raster_analysis_included', False)}")
        logger.info("")
        
        return {
            "status": "success",
            "result": analysis_result,
            "timestamp": datetime.utcnow().isoformat()
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error("=" * 100)
        logger.error("❌ COMPARISON ENDPOINT FAILED")
        logger.error("=" * 100)
        logger.error(f"Exception type: {type(e).__name__}")
        logger.error(f"Exception message: {str(e)}")
        logger.error(f"Exception repr: {repr(e)}")
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
        if not all([latitude, longitude, start_date, end_date]):
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
