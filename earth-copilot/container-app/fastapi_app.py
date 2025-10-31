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

# Import Earth Copilot modules
from semantic_translator import SemanticQueryTranslator
from titiler_config import get_tile_scale  # Legacy tile scale function
from hybrid_rendering_system import HybridRenderingSystem  # 🎨 Comprehensive rendering system
from tile_selector import TileSelector  # 🎯 Smart tile selection and ranking

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

# Import collection profiles for STAC search
try:
    from collection_profiles import COLLECTION_PROFILES, check_collection_coverage
    STAC_PROFILES_AVAILABLE = True
    logging.info(f"✅ Collection profiles loaded: {len(COLLECTION_PROFILES)} collections available")
except ImportError as e:
    COLLECTION_PROFILES = {}
    def check_collection_coverage(collection_id: str, bbox: list) -> dict:
        return {"covered": True, "message": "Coverage check not available"}
    STAC_PROFILES_AVAILABLE = False
    logging.warning(f"⚠️ Collection profiles not available: {e}")

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

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
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

# Global variables for components
semantic_translator = None
global_translator = None  # For session management

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

async def execute_direct_stac_search(stac_query: Dict[str, Any], stac_endpoint: str = "planetary_computer") -> Dict[str, Any]:
    """Execute STAC search against specified endpoint (Planetary Computer or VEDA)"""
    try:
        stac_url = STAC_ENDPOINTS.get(stac_endpoint, STAC_ENDPOINTS["planetary_computer"])
        logger.info(f"🌐 Using STAC endpoint: {stac_endpoint} -> {stac_url}")
        
        logger.info(f"🔍 Executing direct STAC search: {json.dumps(stac_query, indent=2)}")
        
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
                    
                    logger.info(f"✅ STAC search successful: {len(features)} features found")
                    
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
                    
                    result = {
                        "success": True,
                        "results": {
                            "type": "FeatureCollection",
                            "features": enhanced_features
                        },
                        "search_metadata": {
                            "total_found": len(features),
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
    global semantic_translator, global_translator, SEMANTIC_KERNEL_AVAILABLE
    global terrain_analyzer, mobility_classifier, los_calculator, geoint_utils, GEOINT_AVAILABLE
    
    logger.info("🚀 EARTH COPILOT CONTAINER STARTING UP")
    logger.info("=" * 60)
    
    try:
        # Initialize Semantic Translator components with environment variables
        azure_openai_endpoint = os.getenv("AZURE_OPENAI_ENDPOINT", "")
        azure_openai_api_key = os.getenv("AZURE_OPENAI_API_KEY", "")
        azure_openai_deployment = os.getenv("AZURE_OPENAI_DEPLOYMENT_NAME", "gpt-5")
        
        logger.info(f"🔐 Environment check - Endpoint: {'✓' if azure_openai_endpoint else '✗'}, Key: {'✓' if azure_openai_api_key else '✗'}, Model: {azure_openai_deployment}")
        
        if azure_openai_endpoint and azure_openai_api_key:
            semantic_translator = SemanticQueryTranslator(
                azure_openai_endpoint=azure_openai_endpoint,
                azure_openai_api_key=azure_openai_api_key,
                model_name=azure_openai_deployment
            )
            global_translator = semantic_translator  # For session management
            SEMANTIC_KERNEL_AVAILABLE = True
            logger.info("✅ Earth Copilot API initialized successfully with Semantic Translator")
        else:
            logger.warning("⚠️ Azure OpenAI credentials not provided - running in limited mode")
            semantic_translator = None
            global_translator = None
            SEMANTIC_KERNEL_AVAILABLE = False
            
        # GEOINT endpoints use lazy imports - no initialization needed here
        logger.info("✅ GEOINT endpoints ready (lazy import mode)")

        
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
    
    # Remove duplicates while preserving order
    seen = set()
    unique_collections = []
    for collection in detected_collections:
        if collection not in seen and collection in COLLECTION_PROFILES:
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
                            selected_features = TileSelector.select_best_tiles(
                                features=alt_features,
                                query_bbox=requested_bbox,
                                collections=alt_query.get("collections"),
                                max_tiles=20,
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
                                selected_features = TileSelector.select_best_tiles(
                                    features=alt_features,
                                    query_bbox=requested_bbox,
                                    collections=alt_query.get("collections"),
                                    max_tiles=20,
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
    # Example: HLS → Sentinel-2 → Landsat
    original_collections = original_stac_query.get("collections", [])
    alternative_collection_sets = []
    
    if any("hls" in c.lower() for c in original_collections):
        alternative_collection_sets.append({
            "collections": ["sentinel-2-l2a"],
            "name": "Sentinel-2"
        })
        alternative_collection_sets.append({
            "collections": ["landsat-c2-l2"],
            "name": "Landsat"
        })
    elif any("sentinel" in c.lower() for c in original_collections):
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
                        selected_features = TileSelector.select_best_tiles(
                            features=alt_features,
                            query_bbox=requested_bbox,
                            collections=alt_query.get("collections"),
                            max_tiles=20,
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
    
    Special handling for MODIS collections: Skip datetime filter since MODIS items
    have datetime=null and only respond to bbox queries.
    """
    query = {}
    
    # Add collections
    if stac_params.get('collections'):
        query['collections'] = stac_params['collections']
    
    # Check if any MODIS collections are in the query
    collections = stac_params.get('collections', [])
    is_modis = any(col.startswith('modis-') for col in collections)
    
    # Add temporal filter (skip for MODIS - they have datetime=null)
    if stac_params.get('datetime') and not is_modis:
        query['datetime'] = stac_params['datetime']
    elif is_modis and stac_params.get('datetime'):
        logger.info(f"🔧 Skipping datetime filter for MODIS collection (MODIS items have datetime=null)")
    
    # Add spatial filter (bbox) - required for MODIS!
    if stac_params.get('bbox'):
        query['bbox'] = stac_params['bbox']
    
    # Add limit
    query['limit'] = stac_params.get('limit', 100)
    
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
    Clean tilejson URLs in STAC features using collection-specific rules.
    
    Uses HybridRenderingSystem to apply data-type-aware parameter removal:
    - Optical imagery: Removes nodata=0, assets=visual, asset_bidx
    - SAR imagery: Removes nodata, asset_bidx  
    - Elevation: Removes nodata, asset_bidx
    - Other types: Removes asset_bidx only
    
    This ensures proper rendering for each collection's unique characteristics.
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
            logger.info(f"🧹 Processing feature {i+1}/{len(features)}: {feature.get('id', 'unknown')} (collection: {collection_id})")
            
            # Create a deep copy to avoid modifying the original
            cleaned_feature = feature.copy()
            
            # Check if feature has assets
            if "assets" in cleaned_feature and cleaned_feature["assets"]:
                logger.info(f"🧹 Feature {feature.get('id', 'unknown')} has assets: {list(cleaned_feature['assets'].keys())}")
                cleaned_assets = {}
                for asset_name, asset_data in cleaned_feature["assets"].items():
                    cleaned_asset = asset_data.copy()
                    
                    # Clean tilejson asset URL if it exists
                    if asset_name == "tilejson" and "href" in cleaned_asset:
                        original_url = cleaned_asset["href"]
                        logger.info(f"🧹 Found tilejson URL in {feature.get('id', 'unknown')}: {original_url}")
                        
                        # Use HybridRenderingSystem for collection-specific cleaning
                        cleaned_url = HybridRenderingSystem.clean_stac_tilejson_url(original_url, collection_id)
                        
                        if cleaned_url != original_url:
                            cleaned_asset["href"] = cleaned_url
                            logger.info(f"🧹 ✅ Cleaned tilejson URL for {collection_id}: {feature.get('id', 'unknown')}")
                            logger.info(f"🧹    Original: {original_url}")
                            logger.info(f"🧹    Cleaned:  {cleaned_url}")
                        else:
                            logger.info(f"🧹 No cleaning needed for {collection_id}")
                    
                    cleaned_assets[asset_name] = cleaned_asset
                
                cleaned_feature["assets"] = cleaned_assets
            else:
                logger.info(f"🧹 Feature {feature.get('id', 'unknown')} has no assets or empty assets")
            
            cleaned_features.append(cleaned_feature)
        
        # Return cleaned results
        cleaned_results = stac_results.copy()
        cleaned_results["features"] = cleaned_features
        logger.info(f"🧹 ✅ URL cleaning completed. Processed {len(cleaned_features)} features")
        return cleaned_results
        
    except Exception as e:
        logger.error(f"🧹 ❌ Error cleaning tilejson URLs: {e}")
        logger.exception("Full exception details:")
        # Return original results if cleaning fails
        return stac_results

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
        basic_status = {
            "semantic_kernel": SEMANTIC_KERNEL_AVAILABLE,
            "geoint": GEOINT_AVAILABLE,
            "azure_openai_endpoint": bool(os.getenv("AZURE_OPENAI_ENDPOINT")),
            "azure_openai_api_key": bool(os.getenv("AZURE_OPENAI_API_KEY")),
            "azure_openai_deployment": bool(os.getenv("AZURE_OPENAI_DEPLOYMENT_NAME")),
            "azure_maps_key": bool(os.getenv("AZURE_MAPS_SUBSCRIPTION_KEY"))
        }
        
        # Test Azure OpenAI connectivity
        logger.info("🏥 HEALTH CHECK: Testing Azure OpenAI connectivity...")
        try:
            if SEMANTIC_KERNEL_AVAILABLE and semantic_translator:
                azure_openai_endpoint = os.getenv("AZURE_OPENAI_ENDPOINT")
                azure_openai_api_key = os.getenv("AZURE_OPENAI_API_KEY")
                model_name = os.getenv("AZURE_OPENAI_DEPLOYMENT_NAME", "gpt-5")
                
                logger.info(f"🏥 Azure OpenAI Config Check - Endpoint: {'✓' if azure_openai_endpoint else '✗'}, API Key: {'✓' if azure_openai_api_key else '✗'}, Model: {model_name}")
                
                if all([azure_openai_endpoint, azure_openai_api_key, model_name]):
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
                            "troubleshooting": "Verify deployment exists and is running in Azure OpenAI Studio",
                            "last_tested": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                        }
                        logger.error("❌ Azure OpenAI connectivity test FAILED - service not responding")
                        all_healthy = False
                else:
                    missing_vars = []
                    if not azure_openai_endpoint: missing_vars.append("AZURE_OPENAI_ENDPOINT")
                    if not azure_openai_api_key: missing_vars.append("AZURE_OPENAI_API_KEY")
                    if not model_name: missing_vars.append("AZURE_OPENAI_DEPLOYMENT_NAME")
                    
                    connectivity_tests["azure_openai"] = {
                        "status": "misconfigured",
                        "message": f"❌ Missing required environment variables: {', '.join(missing_vars)}",
                        "troubleshooting": "Set the missing environment variables in your .env file or container configuration",
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
            
            if azure_maps_key:
                # Test Azure Maps SEARCH API (geocoding) - this is what location resolution uses!
                maps_test_url = f"https://atlas.microsoft.com/search/address/json?api-version=1.0&query=New%20York&subscription-key={azure_maps_key}"
                
                async with aiohttp.ClientSession() as session:
                    async with session.get(maps_test_url, timeout=aiohttp.ClientTimeout(total=10)) as response:
                        if response.status == 200:
                            connectivity_tests["azure_maps"] = {
                                "status": "connected",
                                "message": "✅ Azure Maps Geocoding API is accessible and responding",
                                "service": "Azure Maps Search API (Location Resolution)",
                                "last_tested": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                            }
                            logger.info("✅ Azure Maps Geocoding API connectivity test PASSED")
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
            else:
                connectivity_tests["azure_maps"] = {
                    "status": "misconfigured",
                    "message": "❌ Azure Maps key NOT configured",
                    "troubleshooting": "Set AZURE_MAPS_SUBSCRIPTION_KEY environment variable",
                    "impact": "⚠️ CRITICAL: Location resolution will fail - all queries with locations will fail"
                }
                logger.warning("⚠️ CRITICAL: Azure Maps key not found - location resolution disabled")
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

@app.get("/api/colormaps")
async def list_colormaps():
    """
    Get list of all available TiTiler colormaps.
    
    Returns:
        List of colormap names available from TiTiler/Planetary Computer
    """
    try:
        from colormap_service import get_colormap_service
        
        service = await get_colormap_service()
        colormaps = await service.list_available_colormaps()
        
        return {
            "success": True,
            "colormaps": colormaps,
            "count": len(colormaps),
            "timestamp": datetime.utcnow().isoformat()
        }
        
    except Exception as e:
        logger.error(f"❌ Error fetching colormaps: {str(e)}")
        return {
            "success": False,
            "error": str(e),
            "colormaps": ["terrain", "viridis", "plasma"]  # Fallback defaults
        }

@app.get("/api/colormaps/{colormap_name}")
async def get_colormap(colormap_name: str):
    """
    Get RGB color values for a specific colormap from TiTiler.
    
    Args:
        colormap_name: Name of the colormap (e.g., 'terrain', 'viridis')
    
    Returns:
        Colormap data with RGB values and CSS gradient string
    """
    try:
        from colormap_service import get_colormap_service
        
        service = await get_colormap_service()
        colormap_data = await service.get_colormap_definition(colormap_name)
        
        if colormap_data:
            # Generate CSS gradient for frontend
            css_gradient = service.colormap_to_css_gradient(colormap_data, orientation="vertical")
            
            return {
                "success": True,
                "colormap_name": colormap_name,
                "colormap_data": colormap_data,
                "css_gradient": css_gradient,
                "timestamp": datetime.utcnow().isoformat()
            }
        else:
            raise HTTPException(status_code=404, detail=f"Colormap '{colormap_name}' not found")
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ Error fetching colormap '{colormap_name}': {str(e)}")
        raise HTTPException(status_code=500, detail=f"Failed to fetch colormap: {str(e)}")

@app.get("/api/colormaps/collection/{collection_id}")
async def get_collection_colormap(collection_id: str):
    """
    Get the appropriate colormap for a specific STAC collection.
    
    Args:
        collection_id: STAC collection ID (e.g., 'cop-dem-glo-30')
    
    Returns:
        Colormap data tailored to the collection type (DEM, vegetation, temperature, etc.)
    """
    try:
        from colormap_service import fetch_collection_colormap
        
        result = await fetch_collection_colormap(collection_id)
        
        # Always return a valid JSON response, even on failure
        if not result or not result.get("success"):
            logger.warning(f"⚠️ Colormap fetch failed for '{collection_id}', returning default")
            return JSONResponse(
                status_code=200,  # Return 200 instead of 404 to prevent client errors
                content={
                    "success": False,
                    "colormap_name": "terrain",
                    "colormap_data": None,
                    "css_gradient": "",
                    "error": f"Colormap not available for collection '{collection_id}'",
                    "timestamp": datetime.utcnow().isoformat()
                }
            )
        
        result["timestamp"] = datetime.utcnow().isoformat()
        return result
        
    except Exception as e:
        logger.error(f"❌ Error fetching colormap for collection '{collection_id}': {str(e)}")
        # Return error as JSON response instead of raising HTTPException
        return JSONResponse(
            status_code=200,  # Return 200 with error details
            content={
                "success": False,
                "colormap_name": "terrain",
                "colormap_data": None,
                "css_gradient": "",
                "error": str(e),
                "timestamp": datetime.utcnow().isoformat()
            }
        )

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
                
            logger.info(f"📥 Container received request: {json.dumps(req_body, indent=2)}")
            
        except Exception as json_error:
            logger.error(f"JSON parsing error: {json_error}")
            raise HTTPException(
                status_code=400,
                detail=f"Invalid JSON data: {str(json_error)}"
            )
        
        natural_query = req_body.get('query', 'No query provided')
        session_id = req_body.get('session_id') or req_body.get('conversation_id')
        pin = req_body.get('pin')  # Optional pin parameter {lat, lng}
        
        logger.info("=" * 100)
        logger.info(f"🔤🔤🔤 RECEIVED NATURAL LANGUAGE QUERY: '{natural_query}' 🔤🔤🔤")
        logger.info(f"🆔 Session ID: {session_id}")
        logger.info(f"📦 Full Request Body Keys: {list(req_body.keys())}")
        logger.info("=" * 100)
        
        # Check for pin parameter and log it
        if pin:
            pin_lat = pin.get('lat')
            pin_lng = pin.get('lng')
            logger.info(f"📍 Pin detected: ({pin_lat:.4f}, {pin_lng:.4f})")
            logger.info("🎯 Location priority: PIN coordinates will override query text location")
        else:
            logger.info("🎯 Location priority: Will extract location from query text")
        
        # PHASE 0: EARLY QUERY INTENT CLASSIFICATION
        classification = None
        early_contextual_response = None
        translator = None
        vision_task = None  # For parallel processing of hybrid queries
        
        logger.info(f"🔍 SEMANTIC_KERNEL_AVAILABLE: {SEMANTIC_KERNEL_AVAILABLE}")
        if SEMANTIC_KERNEL_AVAILABLE and global_translator:
            try:
                translator = global_translator
                
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
                # ========================================================================
                query_lower = natural_query.lower().strip()
                
                factual_question_patterns = [
                    "what is the", "what's the", "which is the", "where is the",
                    "how tall", "how high", "how deep", "how long", "how wide",
                    "how many", "when was", "when did", "who", "why",
                    "tell me about", "explain", "describe the", "what are the"
                ]
                
                visualization_keywords = ["show", "display", "load", "see", "view", "map", "imagery", "image"]
                
                has_factual_pattern = any(pattern in query_lower for pattern in factual_question_patterns)
                has_visualization = any(keyword in query_lower for keyword in visualization_keywords)
                
                force_contextual = has_factual_pattern and not has_visualization
                
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
                from geoint.chat_vision_analyzer import get_chat_vision_analyzer
                chat_vision = get_chat_vision_analyzer()
                conversation_history = req_body.get('conversation_history', []) or req_body.get('messages', [])
                needs_vision = chat_vision.should_use_vision(natural_query, conversation_history)
                
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
                    current_collection = req_body.get('current_collection')  # Collection ID
                    has_satellite_data = req_body.get('has_satellite_data', False)  # Flag if STAC imagery loaded
                    conversation_history = req_body.get('conversation_history', []) or req_body.get('messages', [])
                    
                    # Log vision context availability
                    logger.info(f"📸 Map screenshot available: {bool(imagery_base64)}")
                    logger.info(f"🛰️ Satellite data loaded: {has_satellite_data}")
                    logger.info(f"🗺️ Map bounds available: {bool(map_bounds)}")
                    
                    # Get chat vision analyzer (imported above)
                    from geoint.chat_vision_analyzer import get_chat_vision_analyzer
                    chat_vision = get_chat_vision_analyzer()
                    
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
                                # Create vision analysis task (runs in background)
                                logger.info("⚡ Starting vision analysis task (parallel execution)...")
                                vision_task = asyncio.create_task(
                                    chat_vision.analyze_visible_imagery(
                                        query=natural_query,
                                        map_bounds=map_bounds or {},
                                        imagery_url=imagery_url,
                                        collection_id=current_collection,
                                        conversation_history=conversation_history,
                                        imagery_base64=imagery_base64
                                    )
                                )
                                # Don't await yet - let it run in parallel with STAC search
                                logger.info("🔄 Vision task created, continuing to STAC data retrieval (parallel)...")
                            else:
                                # Pure vision query - run and return immediately
                                vision_result = await chat_vision.analyze_visible_imagery(
                                    query=natural_query,
                                    map_bounds=map_bounds or {},
                                    imagery_url=imagery_url,
                                    collection_id=current_collection,
                                    conversation_history=conversation_history,
                                    imagery_base64=imagery_base64
                                )
                                
                                if vision_result and vision_result.get("analysis"):
                                    logger.info("✅ Chat vision analysis completed")
                                    return {
                                        "success": True,
                                        "response": vision_result["analysis"],
                                        "vision_analysis": vision_result,
                                        "processing_type": "chat_vision",
                                        "timestamp": datetime.utcnow().isoformat()
                                    }
                        except Exception as e:
                            logger.warning(f"⚠️ Chat vision analysis failed: {e}, proceeding with normal flow...")
                            vision_task = None
                    else:
                        logger.info("ℹ️ Vision query detected but no map context provided (user may need to load imagery first)")
                        # Return helpful message
                        return {
                            "success": True,
                            "response": "I'd be happy to analyze the imagery for you! However, I need you to have some satellite imagery loaded on the map first. Could you:\n\n1. Load some imagery (e.g., 'Show me HLS imagery of Seattle')\n2. Then ask me to analyze what's visible\n\nOr if you meant to ask about a specific location, please let me know the location and what you'd like to know about it!",
                            "processing_type": "vision_query_needs_imagery",
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
                    "limit": 100,
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
                    logger.info("=" * 100)
                    
                    logger.info("🔄 Translating natural language to STAC parameters...")
                    
                    # Use the semantic translator's translate_query method with pin support
                    stac_params = await translator.translate_query(natural_query, pin_location=pin)
                    
                    if stac_params and stac_params.get('collections'):
                        logger.info(f"✅ Translation successful: {len(stac_params.get('collections', []))} collections selected")
                        
                        # Build STAC query from semantic analysis (like Router Function App)
                        stac_query = build_stac_query(stac_params)
                        logger.info(f"🔧 Built STAC query from params: {json.dumps(stac_query, indent=2)}")
                        
                    else:
                        logger.warning(f"⚠️ Translation did not produce valid STAC parameters. Got: {stac_params}")
                        
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
        
        if stac_query:
            try:
                logger.info("🌐 Executing STAC search...")
                
                # Determine which STAC endpoint to use (intelligent routing from Router Function App)
                stac_endpoint = translator.determine_stac_source(natural_query, stac_params)
                logger.info(f"📡 STAC source determined: {stac_endpoint}")
                
                stac_response = await execute_direct_stac_search(stac_query, stac_endpoint)
                
                if stac_response.get("success"):
                    raw_features = stac_response.get("results", {}).get("features", [])
                    search_diagnostics["raw_count"] = len(raw_features)
                    logger.info(f"✅ STAC search completed: {len(raw_features)} raw features found")
                    
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
                        # Extract cloud cover limit and collection from query
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
                        
                        logger.info(f"🔍 DEBUG: Extracted cloud_cover_limit = {cloud_cover_limit}")
                        
                        # Get collection ID for property name lookup
                        collections = stac_query.get("collections", [])
                        primary_collection = collections[0] if collections else None
                        
                        # Apply client-side cloud cover filtering with collection-specific property names
                        if cloud_cover_limit is not None:
                            cloud_filtered_results = translator._filter_stac_results_by_cloud_cover(
                                {"features": spatially_filtered_features},
                                max_cloud_cover=cloud_cover_limit,
                                collection_id=primary_collection  # Pass collection for property name lookup
                            )
                            spatially_filtered_features = cloud_filtered_results.get("features", [])
                            search_diagnostics["cloud_filtered_count"] = len(spatially_filtered_features)
                            logger.info(f"☁️ After cloud cover filtering (≤{cloud_cover_limit}%): {len(spatially_filtered_features)} features kept")
                        
                        # 🎯 AGENT 4: GPT-5 TILE SELECTION (Always use intelligent selection)
                        # Always use GPT-5 for consistent, high-quality tile selection
                        logger.info(f"🤖 Using AGENT 4 (GPT-5) for intelligent tile selection...")
                        
                        try:
                            # Use GPT-5 agent for all tile selection
                            # Priorities: 1) Highest resolution, 2) Full coverage, 3) Query alignment
                            features = await translator.tile_selector_agent(
                                stac_features=spatially_filtered_features,
                                query=natural_query,
                                collection_ids=stac_query.get("collections", []),
                                bbox=requested_bbox
                            )
                            search_diagnostics["final_count"] = len(features)
                            search_diagnostics["tile_selection_method"] = "gpt5_smart_path"
                            logger.info(f"✅ AGENT 4 (GPT-5): Selected {len(features)} optimal tiles")
                        except Exception as agent_error:
                            logger.error(f"❌ GPT-5 tile selection failed: {agent_error}, falling back to legacy selection")
                            # Emergency fallback to legacy TileSelector
                            features = TileSelector.select_best_tiles(
                                features=spatially_filtered_features,
                                query_bbox=requested_bbox,
                                collections=stac_query.get("collections"),
                                max_tiles=50,
                                query=natural_query
                            )
                            search_diagnostics["final_count"] = len(features)
                            search_diagnostics["tile_selection_method"] = "legacy_emergency_fallback"
                            logger.info(f"⭐ Emergency fallback: {len(features)} tiles selected")
                        
                        # Update stac_response with intelligently selected results
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
        
        # 🗺️ Generate optimized tile URLs for ALL collections (not just elevation)
        # This uses the HybridRenderingSystem to provide optimal parameters for 113+ STAC collections
        all_tile_urls = []
        all_bboxes = []  # ✅ Collect all bboxes for union calculation
        collections = stac_query.get("collections", []) if stac_query else []
        
        # 🎨 OPTIMIZATION: Generate optimized URLs for ALL features with tilejson assets
        # This ensures proper rescale, colormap, resampling for every collection type
        if features and len(features) > 0:
            # Extract tilejson URLs from all features for seamless coverage
            for feature in features:
                tilejson_asset = feature.get("assets", {}).get("tilejson", {})
                if tilejson_asset and "href" in tilejson_asset:
                    feature_bbox = feature.get("bbox")
                    collection_id = feature.get("collection", collections[0] if collections else "unknown")
                    
                    # 🎨 Apply quality optimization to tilejson URL
                    original_url = tilejson_asset["href"]
                    
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
            
            if all_tile_urls:
                logger.info(f"🗺️ Multi-tile DEM detected: {len(all_tile_urls)} tiles for seamless coverage")
                
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
                "all_tile_urls": all_tile_urls if all_tile_urls else None  # ✨ NEW: All tile URLs for multi-tile rendering
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
                }
            }
        }
        
        logger.info("✅ Unified query processing completed successfully")
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
    GEOINT Terrain Analysis - Thin wrapper around terrain_analysis_agent
    
    Visual terrain feature analysis using GPT-5 Vision.
    
    Request body:
    {
        "latitude": float,
        "longitude": float,
        "screenshot": str (optional - base64 screenshot),
        "user_query": str (optional - user context),
        "user_context": str (optional - legacy field name),
        "radius_miles": float (optional - defaults to 5.0)
    }
    """
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
        
        screenshot_size = len(screenshot) if screenshot else 0
        logger.info(f"🏔️ [{request_id}] Screenshot size: {screenshot_size} chars")
        
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
        
        # Call terrain_analysis_agent (new agent-based architecture)
        logger.info(f"🏔️ [{request_id}] Importing terrain_analysis_agent...")
        from geoint.agents import terrain_analysis_agent
        logger.info(f"🏔️ [{request_id}] ✅ Import successful")
        
        logger.info(f"🏔️ [{request_id}] Calling terrain_analysis_agent...")
        analysis_result = await terrain_analysis_agent(
            latitude=latitude,
            longitude=longitude,
            screenshot_base64=screenshot,
            user_query=user_query,
            radius_miles=radius_miles
        )
        
        logger.info(f"🏔️ [{request_id}] ✅ Terrain agent completed successfully")
        logger.info(f"🏔️ [{request_id}] Result keys: {list(analysis_result.keys()) if isinstance(analysis_result, dict) else 'N/A'}")
        
        return {
            "status": "success",
            "result": analysis_result,
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
    
    Accepts:
    - latitude, longitude: Location coordinates
    - before_date, after_date: ISO datetime strings
    - before_screenshot, after_screenshot: Base64-encoded map screenshots
    - before_metadata, after_metadata: Optional imagery metadata
    - user_query: Original user question
    - comparison_aspect: What to focus on (e.g., "wildfire activity")
    - collection_id: (NEW) STAC collection for raster analysis (e.g., "modis-14A1-061")
    - download_rasters: (NEW) Whether to download actual raster data (default: True)
    
    The agent will analyze both map screenshots AND actual raster data (if collection_id provided)
    to provide comprehensive temporal change analysis combining visual and quantitative insights.
    """
    try:
        logger.info("=" * 100)
        logger.info("📊 COMPARISON ANALYSIS ENDPOINT CALLED")
        logger.info("=" * 100)
        
        body = await request.json()
        
        logger.info(f"📦 Request body keys: {list(body.keys())}")
        
        latitude = body.get("latitude")
        longitude = body.get("longitude")
        before_date = body.get("before_date")
        after_date = body.get("after_date")
        before_screenshot = body.get("before_screenshot")
        after_screenshot = body.get("after_screenshot")
        before_metadata = body.get("before_metadata")
        after_metadata = body.get("after_metadata")
        user_query = body.get("user_query")
        comparison_aspect = body.get("comparison_aspect")
        collection_id = body.get("collection_id")  # NEW: for raster download
        download_rasters = body.get("download_rasters", True)  # NEW: default True
        
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
