"""
Unified Router+STAC Function with Complete Natural Language Processing
Handles all 126+ Microsoft Planetary Computer collections with intelligent routing
"""

import json
import logging
import os
import sys
import traceback
import asyncio
from datetime import datetime, timedelta
from typing import Dict, Any, List, Optional, Tuple
import aiohttp
from dotenv import load_dotenv

import azure.functions as func
from azure.functions import HttpRequest, HttpResponse

# Load environment variables from .env file
env_path = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), '.env')
load_dotenv(env_path)

# Configure enhanced debug logging with more detailed format
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(name)s - %(levelname)s - %(funcName)s:%(lineno)d - %(message)s',
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler('function_debug.log') if os.path.exists('.') else logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)

# Startup diagnostics
logger.info("=" * 60)
logger.info("🚀 UNIFIED ROUTER+STAC FUNCTION STARTING UP")
logger.info("=" * 60)
logger.info(f"📍 Working directory: {os.getcwd()}")
logger.info(f"📍 Script location: {__file__}")
logger.info(f"📍 Python path: {sys.path[:3]}...")  # Show first 3 entries

# Debug: Check if environment variables are loaded
logger.info(f"🔧 Environment file path: {env_path}")
logger.info(f"🔧 Environment file exists: {os.path.exists(env_path)}")
logger.info(f"🔧 AZURE_OPENAI_ENDPOINT: {'✓ Set' if os.getenv('AZURE_OPENAI_ENDPOINT') else '✗ Not Set'}")
logger.info(f"🔧 AZURE_OPENAI_API_KEY: {'✓ Set (***' + str(os.getenv('AZURE_OPENAI_API_KEY', ''))[-4:] + ')' if os.getenv('AZURE_OPENAI_API_KEY') else '✗ Not Set'}")
logger.info(f"🔧 AZURE_OPENAI_DEPLOYMENT_NAME: {os.getenv('AZURE_OPENAI_DEPLOYMENT_NAME', 'Not Set')}")

# Import Semantic Kernel translator
logger.info("📦 Importing Semantic Kernel translator...")
try:
    from semantic_translator import SemanticQueryTranslator
    SEMANTIC_KERNEL_AVAILABLE = True
    logger.info("✅ Semantic Kernel translator imported successfully")
except ImportError as e:
    SEMANTIC_KERNEL_AVAILABLE = False
    logger.error(f"❌ Semantic Kernel import failed: {e}")
    logger.error(f"❌ Current working directory: {os.getcwd()}")
    logger.error(f"❌ Files in current directory: {os.listdir('.')}")
    if os.path.exists('semantic_translator'):
        logger.error(f"❌ Files in semantic_translator: {os.listdir('semantic_translator')}")
except Exception as e:
    SEMANTIC_KERNEL_AVAILABLE = False
    logger.error(f"❌ Unexpected error importing Semantic Kernel: {e}")
    logger.error(f"❌ Full traceback: {traceback.format_exc()}")

# Import STAC functionality
logger.info("📦 Importing STAC collection profiles...")
try:
    from collection_profiles import COLLECTION_PROFILES
    STAC_PROFILES_AVAILABLE = True
    logger.info(f"✅ STAC Collection profiles imported - {len(COLLECTION_PROFILES)} collections available")
except ImportError as e:
    STAC_PROFILES_AVAILABLE = False
    logger.error(f"❌ STAC Collection profiles import failed: {e}")
except Exception as e:
    STAC_PROFILES_AVAILABLE = False
    logger.error(f"❌ Unexpected error importing STAC profiles: {e}")
    logger.error(f"❌ Full traceback: {traceback.format_exc()}")

# Initialize Function App
logger.info("🔧 Creating Function App instance...")
try:
    app = func.FunctionApp()
    logger.info("✅ Function App instance created successfully")
except Exception as e:
    logger.error(f"❌ Failed to create Function App: {e}")
    logger.error(f"❌ Full traceback: {traceback.format_exc()}")
    raise

def calculate_center_from_bbox(bbox: Optional[List[float]]) -> Optional[List[float]]:
    """Calculate center point from bounding box [west, south, east, north]"""
    if not bbox or len(bbox) != 4:
        return None
    west, south, east, north = bbox
    center_lon = (west + east) / 2
    center_lat = (south + north) / 2
    return [center_lon, center_lat]

def calculate_zoom_level(bbox: Optional[List[float]]) -> int:
    """Calculate appropriate zoom level based on bounding box size"""
    if not bbox or len(bbox) != 4:
        return 10
    west, south, east, north = bbox
    width = abs(east - west)
    height = abs(north - south)
    max_dimension = max(width, height)
    
    # Simple zoom calculation - larger areas need lower zoom
    if max_dimension > 10:
        return 5
    elif max_dimension > 5:
        return 6
    elif max_dimension > 2:
        return 7
    elif max_dimension > 1:
        return 8
    elif max_dimension > 0.5:
        return 9
    elif max_dimension > 0.1:
        return 10
    else:
        return 11

# STAC Search Integration Functions
def detect_collections(query: str, context: Optional[Dict[str, Any]] = None) -> List[str]:
    """Detect relevant collections based on query content and context"""
    query_lower = query.lower()
    detected_collections = []
    
    # High-priority exact matches
    collection_keywords = {
        "sentinel-2": ["sentinel-2", "sentinel 2", "s2"],
        "sentinel-1": ["sentinel-1", "sentinel 1", "s1", "sar", "radar"],
        "landsat": ["landsat", "landsat-c2"],
        "modis": ["modis", "terra", "aqua"],
        "cop-dem": ["elevation", "dem", "topography", "altitude", "cop-dem"],
        "naip": ["naip", "aerial", "high resolution"],
        "era5": ["weather", "climate", "era5", "temperature", "precipitation"]
    }
    
    for collection_pattern, keywords in collection_keywords.items():
        if any(keyword in query_lower for keyword in keywords):
            if collection_pattern == "sentinel-2":
                detected_collections.append("sentinel-2-l2a")
            elif collection_pattern == "sentinel-1":
                detected_collections.append("sentinel-1-grd")
            elif collection_pattern == "landsat":
                detected_collections.append("landsat-c2-l2")
            elif collection_pattern == "cop-dem":
                detected_collections.extend(["cop-dem-glo-30", "cop-dem-glo-90"])
            elif collection_pattern == "era5":
                detected_collections.extend(["era5-pds", "era5-land"])
            else:
                detected_collections.append(collection_pattern)
    
    # If no specific collections detected, use general-purpose defaults
    if not detected_collections:
        detected_collections = ["sentinel-2-l2a", "landsat-c2-l2"]
    
    return list(set(detected_collections))  # Remove duplicates

def infer_collections_from_context(query: str, location: Optional[str] = None, temporal: Optional[str] = None) -> List[str]:
    """Infer collections based on query context and requirements"""
    query_lower = query.lower()
    collections = []
    
    # Disaster/emergency context
    if any(term in query_lower for term in ['disaster', 'hurricane', 'flood', 'fire', 'damage', 'emergency']):
        collections.extend(['sentinel-1-grd', 'sentinel-2-l2a', 'landsat-c2-l2'])
    
    # Environmental monitoring
    elif any(term in query_lower for term in ['environmental', 'vegetation', 'forest', 'agriculture', 'crop']):
        collections.extend(['sentinel-2-l2a', 'modis-13q1-061', 'landsat-c2-l2'])
    
    # Urban/infrastructure
    elif any(term in query_lower for term in ['urban', 'city', 'building', 'infrastructure']):
        collections.extend(['sentinel-2-l2a', 'naip', 'landsat-c2-l2'])
    
    # Default: comprehensive optical coverage
    else:
        collections = ['sentinel-2-l2a', 'landsat-c2-l2']
    
    return collections

def build_stac_query(entities: Dict[str, Any]) -> Dict[str, Any]:
    """Build STAC API query from extracted entities"""
    query = {}
    
    # Collections
    collections = entities.get('collections', [])
    if not collections:
        # Fallback collection detection
        original_query = entities.get('original_query', '')
        collections = detect_collections(original_query, entities)
    
    if collections:
        query['collections'] = collections[:5]  # Limit to avoid overly broad searches
    
    # Spatial extent
    if entities.get('bbox'):
        query['bbox'] = entities['bbox']
    
    # Temporal extent  
    if entities.get('datetime'):
        query['datetime'] = entities['datetime']
    
    # Additional query parameters
    query['limit'] = entities.get('limit', 100)
    
    # Cloud cover filter for optical collections
    if any(col in ['sentinel-2-l2a', 'landsat-c2-l2'] for col in collections):
        if 'query' not in query:
            query['query'] = {}
        query['query']['eo:cloud_cover'] = {"lte": 30}  # Default cloud cover limit
    
    return query

async def execute_direct_stac_search(stac_query: Dict[str, Any]) -> Dict[str, Any]:
    """Execute STAC search directly against Microsoft Planetary Computer"""
    try:
        pc_stac_url = "https://planetarycomputer.microsoft.com/api/stac/v1/search"
        
        logger.info(f"🔍 Executing direct STAC search: {json.dumps(stac_query, indent=2)}")
        
        timeout = aiohttp.ClientTimeout(total=30)
        
        logger.info(f"🌐 Making HTTP POST request to: {pc_stac_url}")
        logger.info(f"📦 Request payload: {json.dumps(stac_query, indent=2)}")
        
        async with aiohttp.ClientSession(timeout=timeout) as session:
            logger.info("🔗 Opening HTTP session...")
            async with session.post(pc_stac_url, json=stac_query) as response:
                logger.info(f"📡 Received HTTP response: {response.status}")
                
                if response.status == 200:
                    stac_response = await response.json()
                    features = stac_response.get('features', [])
                    
                    logger.info(f"✅ STAC search successful: {len(features)} features found")
                    logger.info(f"📊 First feature ID: {features[0].get('id', 'unknown') if features else 'none'}")
                    
                    # Enhance features with visualization metadata
                    enhanced_features = enhance_results_with_visualization_metadata(features)
                    
                    return {
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
                else:
                    error_text = await response.text()
                    logger.error(f"❌ STAC API error {response.status}: {error_text}")
                    logger.error(f"🌐 Request URL: {pc_stac_url}")
                    logger.error(f"📦 Request payload: {json.dumps(stac_query, indent=2)}")
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

def enhance_results_with_visualization_metadata(features: List[Dict]) -> List[Dict]:
    """Enhance STAC features with visualization metadata"""
    enhanced_features = []
    
    for feature in features:
        collection = feature.get('collection', '')
        
        # Add visualization hints
        viz_metadata = {
            "visualization_type": "raster",
            "rendering_hints": {}
        }
        
        if collection in COLLECTION_PROFILES if STAC_PROFILES_AVAILABLE else {}:
            profile = COLLECTION_PROFILES[collection]
            viz_metadata["rendering_hints"] = profile.get("rendering", {})
            viz_metadata["description"] = profile.get("description", "")
        
        # Add to feature properties
        feature.setdefault("properties", {})["visualization"] = viz_metadata
        enhanced_features.append(feature)
    
    return enhanced_features

def generate_fallback_response(query: str, features: List[Dict], collections: List[str]) -> str:
    """Generate a fallback response when Semantic Kernel response generation fails"""
    try:
        num_features = len(features)
        
        if num_features == 0:
            return f"I searched for '{query}' but didn't find any matching data. Try adjusting your location, time period, or data type."
        
        # Enhanced response construction with more detail
        response_parts = []
        
        # Opening statement with more context
        if num_features == 1:
            response_parts.append(f"I found 1 high-quality satellite image matching your query for '{query}'.")
        else:
            response_parts.append(f"I found {num_features} satellite images matching your query for '{query}'.")
        
        # Extract useful information from features
        if features:
            # Get cloud cover information
            cloud_covers = []
            dates = []
            for feature in features[:10]:  # Check first 10 features
                props = feature.get('properties', {})
                if 'eo:cloud_cover' in props:
                    cloud_covers.append(props['eo:cloud_cover'])
                if 'datetime' in props:
                    dates.append(props['datetime'][:10])
            
            # Add cloud cover summary
            if cloud_covers:
                avg_cloud = sum(cloud_covers) / len(cloud_covers)
                clear_images = len([cc for cc in cloud_covers if cc < 20])
                if clear_images > 0:
                    response_parts.append(f"The satellite imagery is quite clear, with {clear_images} out of {min(len(cloud_covers), num_features)} images having less than 20% cloud cover, averaging about {avg_cloud:.0f}% cloud cover overall.")
                else:
                    response_parts.append(f"The images have an average cloud cover of {avg_cloud:.0f}%.")
            
            # Add temporal information
            if dates:
                unique_dates = sorted(list(set(dates)))
                if len(unique_dates) == 1:
                    response_parts.append(f"The data is from {unique_dates[0]}.")
                elif len(unique_dates) <= 3:
                    response_parts.append(f"The data spans from {unique_dates[0]} to {unique_dates[-1]}.")
                else:
                    response_parts.append(f"The data covers multiple dates from {unique_dates[0]} to {unique_dates[-1]}.")
        
        # Data sources with more descriptive names
        if collections:
            clean_collections = [c for c in collections if c != 'unknown']
            if clean_collections:
                collection_descriptions = {
                    'sentinel-2-l2a': 'Sentinel-2 (high-resolution 10m optical)',
                    'landsat-c2-l2': 'Landsat (30m optical with thermal)',
                    'modis-09A1-061': 'MODIS (daily global coverage)',
                    'sentinel-1-grd': 'Sentinel-1 SAR (radar, all-weather)'
                }
                described_collections = [collection_descriptions.get(c, c) for c in clean_collections]
                
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

@app.route(route="health", methods=["GET"])
def health_check(req: func.HttpRequest) -> func.HttpResponse:
    """Health check endpoint with comprehensive diagnostics"""
    logger.info("🏥 HEALTH CHECK: Endpoint called")
    
    try:
        # Get current timestamp
        current_time = datetime.now().strftime("%m/%d/%Y %I:%M:%S %p")
        logger.info(f"🏥 HEALTH CHECK: Current time: {current_time}")
        
        # Check dependencies
        logger.info("🏥 HEALTH CHECK: Checking dependencies...")
        dependencies_status = {
            "semantic_kernel": SEMANTIC_KERNEL_AVAILABLE,
            "stac_profiles": STAC_PROFILES_AVAILABLE,
            "azure_openai_endpoint": bool(os.getenv("AZURE_OPENAI_ENDPOINT")),
            "azure_openai_api_key": bool(os.getenv("AZURE_OPENAI_API_KEY")),
            "azure_openai_deployment": bool(os.getenv("AZURE_OPENAI_DEPLOYMENT_NAME"))
        }
        
        logger.info(f"🏥 HEALTH CHECK: Dependencies: {dependencies_status}")
        
        # Check collection profiles count
        collections_count = len(COLLECTION_PROFILES) if STAC_PROFILES_AVAILABLE else 0
        logger.info(f"🏥 HEALTH CHECK: Collections available: {collections_count}")
        
        response = {
            "status": "healthy",
            "timestamp": current_time,
            "message": "Unified Router+STAC Function is running",
            "services": dependencies_status,
            "collections_available": collections_count,
            "endpoints": {
                "health": "/api/health",
                "query": "/api/query", 
                "stac_search": "/api/stac-search"
            }
        }
        
        logger.info("✅ HEALTH CHECK: All checks passed")
        return func.HttpResponse(
            json.dumps(response, indent=2),
            status_code=200,
            headers={
                "Content-Type": "application/json",
                "Access-Control-Allow-Origin": "*"
            }
        )
        
    except Exception as e:
        logger.error(f"❌ HEALTH CHECK: Error occurred: {e}")
        logger.error(f"❌ HEALTH CHECK: Traceback: {traceback.format_exc()}")
        
        error_response = {
            "status": "unhealthy",
            "timestamp": datetime.now().strftime("%m/%d/%Y %I:%M:%S %p"),
            "error": str(e),
            "service": "Unified Router+STAC Function"
        }
        
        return func.HttpResponse(
            json.dumps(error_response, indent=2),
            status_code=500,
            headers={
                "Content-Type": "application/json",
                "Access-Control-Allow-Origin": "*"
            }
        )

@app.route(route="query", methods=["POST"])
async def unified_query_processor(req: func.HttpRequest) -> func.HttpResponse:
    """
    Unified query processor that combines Router Function logic with direct STAC search
    This keeps the original router logic and adds STAC search at the end
    """
    try:
        logger.info("🚀 Unified query processor started")
        
        # Parse request
        try:
            req_body = req.get_json()
            if not req_body:
                raise ValueError("Request body is empty")
                
            logger.info(f"📥 Router received request: {json.dumps(req_body, indent=2)}")
            
        except Exception as json_error:
            logger.error(f"JSON parsing error: {json_error}")
            return func.HttpResponse(
                json.dumps({
                    "success": False,
                    "error": "Invalid JSON",
                    "message": f"HTTP request does not contain valid JSON data: {str(json_error)}",
                    "timestamp": datetime.utcnow().isoformat()
                }),
                status_code=400,
                headers={
                    "Content-Type": "application/json",
                    "Access-Control-Allow-Origin": "*"
                }
            )
        
        natural_query = req_body.get('query', 'No query provided')
        
        logger.info(f"🔤 Received natural language query: {natural_query}")
        
        # PHASE 0: EARLY QUERY INTENT CLASSIFICATION
        # Classify the query first to determine if we need STAC search or just contextual analysis
        classification = None
        early_contextual_response = None
        translator = None  # Will be reused if initialized
        
        logger.info(f"🔍 SEMANTIC_KERNEL_AVAILABLE: {SEMANTIC_KERNEL_AVAILABLE}")
        if SEMANTIC_KERNEL_AVAILABLE:
            try:
                # Get Azure OpenAI credentials for early classification
                azure_openai_endpoint = os.getenv("AZURE_OPENAI_ENDPOINT")
                azure_openai_api_key = os.getenv("AZURE_OPENAI_API_KEY")
                model_name = os.getenv("AZURE_OPENAI_DEPLOYMENT_NAME", "gpt-5")
                
                logger.info(f"🔐 Early classification env check - Endpoint: {'✓' if azure_openai_endpoint else '✗'}, Key: {'✓' if azure_openai_api_key else '✗'}, Model: {model_name}")
                
                if all([azure_openai_endpoint, azure_openai_api_key, model_name]):
                    logger.info("🧠 Performing early query intent classification...")
                    
                    # Initialize Semantic Kernel translator for classification
                    translator = SemanticQueryTranslator(
                        str(azure_openai_endpoint),
                        str(azure_openai_api_key),
                        str(model_name)
                    )
                    
                    # Classify query intent early
                    classification = await translator.classify_query_intent(natural_query)
                    intent_type = classification.get('intent_type', 'geospatial_data_search')
                    confidence = classification.get('confidence', 0)
                    
                    logger.info(f"🎯 QUERY PROCESSING FLOW:")
                    logger.info(f"   Query: '{natural_query}'")
                    logger.info(f"   Classification: {intent_type}")
                    logger.info(f"   Confidence: {confidence:.2f}")
                    logger.info(f"   Needs satellite data: {classification.get('needs_satellite_data', False)}")
                    logger.info(f"   Needs contextual info: {classification.get('needs_contextual_info', False)}")
                    
                    # If it's pure contextual analysis with high confidence, skip STAC search
                    if intent_type == "contextual_analysis" and confidence > 0.8:
                        logger.info("🌍 HIGH-CONFIDENCE CONTEXTUAL: Skipping STAC search, generating direct response...")
                        try:
                            # Generate contextual response without STAC data
                            contextual_response = await asyncio.wait_for(
                                translator.generate_contextual_earth_science_response(
                                    natural_query, 
                                    classification, 
                                    {"success": True, "results": {"features": []}}  # Empty STAC response
                                ),
                                timeout=25.0
                            )
                            early_contextual_response = contextual_response
                            logger.info("✅ Direct contextual analysis completed successfully")
                        except Exception as e:
                            logger.warning(f"⚠️ Early contextual analysis failed: {e}, will proceed with STAC search")
                            early_contextual_response = None
                else:
                    logger.warning(f"⚠️ Missing environment variables for early classification")
                            
            except Exception as e:
                logger.warning(f"⚠️ Early classification failed: {e}, proceeding with normal flow")
                classification = None
        
        # If we got an early contextual response, return it directly
        if early_contextual_response:
            logger.info("🏁 Returning early contextual analysis response")
            
            return func.HttpResponse(
                json.dumps({
                    "success": True,
                    "message": early_contextual_response.get("message", "Analysis completed."),
                    "query_type": "contextual_earth_science",
                    "confidence": classification.get('confidence', 0.8) if classification else 0.8,
                    "map_data": early_contextual_response.get("map_data"),
                    "classification": classification,
                    "timestamp": datetime.utcnow().isoformat(),
                    "processing_mode": "direct_contextual_analysis"
                }),
                status_code=200,
                headers={
                    "Content-Type": "application/json",
                    "Access-Control-Allow-Origin": "*"
                }
            )
        
        # PHASE 1: SEMANTIC KERNEL PROCESSING (Original Router Logic)
        if not SEMANTIC_KERNEL_AVAILABLE:
            logger.warning("⚠️ Semantic Kernel not available, using fallback processing")
            
            # Fallback: Simple collection detection
            collections = detect_collections(natural_query)
            stac_params = {
                "collections": collections,
                "limit": 100,
                "original_query": natural_query
            }
            
        else:
            logger.info("🧠 Starting Semantic Kernel processing...")
            
            # Reuse translator if already initialized, otherwise create new one
            if translator is None:
                # Get Azure OpenAI credentials
                azure_openai_endpoint = os.getenv("AZURE_OPENAI_ENDPOINT")
                azure_openai_api_key = os.getenv("AZURE_OPENAI_API_KEY")
                model_name = os.getenv("AZURE_OPENAI_DEPLOYMENT_NAME", "gpt-5")
                
                logger.info(f"🔐 Checking Azure OpenAI credentials...")
                logger.info(f"🔐 Endpoint: {'✓' if azure_openai_endpoint else '✗'}")
                logger.info(f"🔐 API Key: {'✓' if azure_openai_api_key else '✗'}")
                logger.info(f"🔐 Model: {model_name}")
                
                if not all([azure_openai_endpoint, azure_openai_api_key, model_name]):
                    error_msg = f"Azure OpenAI credentials not configured properly: endpoint={bool(azure_openai_endpoint)}, key={bool(azure_openai_api_key)}, model={bool(model_name)}"
                    logger.error(f"❌ {error_msg}")
                    raise ValueError(error_msg)
                
                # Initialize Semantic Kernel translator - ensure strings are not None
                logger.info("🤖 Initializing Semantic Kernel translator...")
                translator = SemanticQueryTranslator(
                    str(azure_openai_endpoint),
                    str(azure_openai_api_key),
                    str(model_name)
                )
                logger.info("✅ Semantic Kernel translator initialized")
            else:
                logger.info("♻️ Reusing already initialized Semantic Kernel translator")
            
            logger.info("🤖 Translating query with Semantic Kernel...")
            
            # Translate natural language to STAC parameters
            stac_params = await translator.translate_query(natural_query)
            logger.info(f"📋 SK translation result: {json.dumps(stac_params, indent=2)}")
        
        # PHASE 2: DIRECT STAC SEARCH (Added STAC Functionality) 
        logger.info("🔍 Starting direct STAC search...")
        
        # Build STAC query from semantic analysis
        stac_query = build_stac_query(stac_params)
        logger.info(f"📊 Built STAC query: {json.dumps(stac_query, indent=2)}")
        
        # Execute direct STAC search
        stac_response = await execute_direct_stac_search(stac_query)
        
        # Debug STAC response to understand data types
        logger.info(f"📊 STAC SEARCH RESULTS:")
        if stac_response and stac_response.get('success'):
            features = stac_response.get('results', {}).get('features', [])
            logger.info(f"   Found {len(features)} features")
            
            # Analyze collection types and data types
            if features:
                collections = set()
                data_types = set()
                for feature in features[:3]:  # Sample first 3 features
                    collection = feature.get('collection', 'unknown')
                    collections.add(collection)
                    
                    # Identify data type based on collection
                    if 'elevation' in collection or 'dem' in collection:
                        data_types.add('elevation')
                    elif 'fire' in collection or '14A' in collection:
                        data_types.add('fire_detection')
                    elif 'vegetation' in collection or '13' in collection:
                        data_types.add('vegetation')
                    elif 'climate' in collection or 'era5' in collection:
                        data_types.add('climate')
                    elif 'landsat' in collection or 'sentinel' in collection:
                        data_types.add('optical_satellite')
                    else:
                        data_types.add('other')
                
                logger.info(f"   Collections: {list(collections)}")
                logger.info(f"   Data types detected: {list(data_types)}")
        else:
            logger.warning(f"   STAC search failed or returned no results")
        
        # PHASE 3: ENHANCED RESPONSE GENERATION WITH QUERY CLASSIFICATION
        logger.info("🧠 Starting enhanced response generation with query classification...")
        
        # Step 1: Use existing classification or classify the query intent if not done already
        if classification is None and SEMANTIC_KERNEL_AVAILABLE and translator:
            try:
                logger.info("🔍 Classifying query intent...")
                classification = await translator.classify_query_intent(natural_query)
                logger.info(f"📊 Query classified as: {classification.get('intent_type', 'unknown')} (confidence: {classification.get('confidence', 0)})")
            except Exception as e:
                logger.warning(f"⚠️ Query classification failed: {e}, using fallback classification")
                classification = {
                    "intent_type": "geospatial_data_search",
                    "needs_satellite_data": True,
                    "needs_contextual_info": False,
                    "confidence": 0.5
                }
        elif classification is not None:
            logger.info(f"📊 Using early classification: {classification.get('intent_type', 'unknown')} (confidence: {classification.get('confidence', 0)})")
        
        if classification is None:
            # Fallback classification when SK not available
            classification = {
                "intent_type": "geospatial_data_search",
                "needs_satellite_data": True,
                "needs_contextual_info": False,
                "confidence": 0.5
            }
        
        # Step 2: Generate appropriate response based on classification
        response_message = ""
        query_type = "unknown"
        map_data = None
        
        if stac_response.get("success"):
            logger.info("✅ STAC search successful, generating response based on query intent...")
            
            features = stac_response.get("results", {}).get("features", [])
            collections_found = list(set(f.get('collection', 'unknown') for f in features))
            
            # Generate response based on intent type
            intent_type = classification.get("intent_type", "geospatial_data_search")
            
            if intent_type == "contextual_analysis" and SEMANTIC_KERNEL_AVAILABLE and translator:
                # Generate comprehensive contextual analysis
                try:
                    logger.info("🌍 Generating contextual Earth science analysis...")
                    contextual_response = await asyncio.wait_for(
                        translator.generate_contextual_earth_science_response(natural_query, classification, stac_response),
                        timeout=25.0
                    )
                    response_message = contextual_response.get("message", "Analysis completed.")
                    query_type = "contextual_earth_science"
                    map_data = contextual_response.get("map_data")
                    logger.info(f"✅ Contextual analysis completed: {response_message[:100]}...")
                    
                except Exception as e:
                    logger.error(f"❌ Contextual analysis failed: {e}, using intelligent STAC response")
                    # Fallback to intelligent STAC response
                    try:
                        if translator:
                            user_response = await translator.generate_intelligent_response(natural_query, stac_response)
                            response_message = user_response.get("message", "Analysis completed successfully.")
                            query_type = "intelligent_analysis_fallback"
                        else:
                            response_message = generate_fallback_response(natural_query, features, collections_found)
                            query_type = "basic_fallback"
                    except:
                        response_message = generate_fallback_response(natural_query, features, collections_found)
                        query_type = "basic_fallback"
                        
            elif intent_type == "hybrid" and SEMANTIC_KERNEL_AVAILABLE and translator:
                # Generate hybrid response (contextual + satellite data)
                try:
                    logger.info("🔄 Generating hybrid contextual + satellite data response...")
                    contextual_response = await asyncio.wait_for(
                        translator.generate_contextual_earth_science_response(natural_query, classification, stac_response),
                        timeout=25.0
                    )
                    response_message = contextual_response.get("message", "Analysis completed.")
                    query_type = "hybrid_analysis"
                    map_data = contextual_response.get("map_data")
                    logger.info(f"✅ Hybrid analysis completed: {response_message[:100]}...")
                    
                except Exception as e:
                    logger.error(f"❌ Hybrid analysis failed: {e}, using intelligent STAC response")
                    try:
                        if translator:
                            user_response = await translator.generate_intelligent_response(natural_query, stac_response)
                            response_message = user_response.get("message", "Analysis completed successfully.")
                            query_type = "intelligent_analysis_fallback"
                        else:
                            response_message = generate_fallback_response(natural_query, features, collections_found)
                            query_type = "basic_fallback"
                    except:
                        response_message = generate_fallback_response(natural_query, features, collections_found)
                        query_type = "basic_fallback"
                        
            else:
                # Traditional STAC-focused response
                if SEMANTIC_KERNEL_AVAILABLE and translator:
                    try:
                        logger.info("🤖 Starting traditional STAC-focused response generation...")
                        user_response = await asyncio.wait_for(
                            translator.generate_intelligent_response(natural_query, stac_response),
                            timeout=20.0
                        )
                        response_message = user_response.get("message", "Analysis completed successfully.")
                        query_type = "intelligent_analysis"
                        logger.info(f"✅ STAC response generation completed: {response_message[:100]}...")
                        
                    except asyncio.TimeoutError:
                        logger.warning("⏰ STAC response generation timed out, using enhanced fallback")
                        response_message = generate_fallback_response(natural_query, features, collections_found)
                        query_type = "timeout_fallback"
                        
                    except Exception as e:
                        logger.error(f"❌ STAC response generation failed: {e}, using enhanced fallback")
                        response_message = generate_fallback_response(natural_query, features, collections_found)
                        query_type = "error_fallback"
                else:
                    logger.info("🔄 Semantic Kernel not available, using enhanced fallback response")
                    response_message = generate_fallback_response(natural_query, features, collections_found)
                    query_type = "no_sk_fallback"
            
            # Prepare map data if not already set
            if not map_data:
                map_data = {
                    "features": features,
                    "bbox": stac_query.get("bbox"),
                    "bounds": stac_query.get("bbox"),
                    "center": calculate_center_from_bbox(stac_query.get("bbox")) if stac_query.get("bbox") else None,
                    "zoom_level": calculate_zoom_level(stac_query.get("bbox")) if stac_query.get("bbox") else 10
                }
            
            complete_response = {
                "success": True,
                "response": response_message,
                "data": {
                    "stac_results": stac_response.get("results", {}),
                    "search_metadata": {
                        "total_items": len(features),
                        "collections_searched": stac_query.get("collections", []),
                        "spatial_extent": stac_query.get("bbox"),
                        "temporal_range": stac_query.get("datetime"),
                        "search_timestamp": datetime.utcnow().isoformat()
                    },
                    "map_data": map_data,
                    "query_classification": {
                        "intent_type": classification.get("intent_type"),
                        "needs_satellite_data": classification.get("needs_satellite_data"),
                        "needs_contextual_info": classification.get("needs_contextual_info"),
                        "location_focus": classification.get("location_focus"),
                        "confidence": classification.get("confidence")
                    }
                },
                "translation_metadata": {
                    "original_query": natural_query,
                    "translated_params": stac_params,
                    "stac_query": stac_query,
                    "response_type": query_type,
                    "translation_timestamp": datetime.utcnow().isoformat()
                },
                "debug": {
                    "semantic_translator": {
                        "selected_collections": stac_query.get("collections", []),
                        "location_info": {
                            "bbox": stac_query.get("bbox"),
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
        else:
            # STAC search failed
            logger.warning("⚠️ STAC search failed, providing query analysis")
            
            error_msg = stac_response.get("error", "Unknown STAC error")
            response_message = f"I successfully analyzed your query '{natural_query}', but encountered an error searching the data catalog: {error_msg}"
            
            complete_response = {
                "success": False,
                "response": response_message,
                "data": {
                    "stac_results": {"type": "FeatureCollection", "features": []},
                    "search_metadata": {
                        "total_items": 0,
                        "collections_searched": stac_query.get("collections", []),
                        "search_timestamp": datetime.utcnow().isoformat(),
                        "error": error_msg
                    }
                },
                "translation_metadata": {
                    "original_query": natural_query,
                    "translated_params": stac_params,
                    "stac_query": stac_query,
                    "translation_timestamp": datetime.utcnow().isoformat()
                }
            }

        logger.info("🏁 Query processing completed successfully")
        
        return func.HttpResponse(
            json.dumps(complete_response),
            status_code=200,
            headers={
                "Content-Type": "application/json",
                "Access-Control-Allow-Origin": "*",
                "Access-Control-Allow-Methods": "GET, POST, OPTIONS", 
                "Access-Control-Allow-Headers": "Content-Type, Authorization"
            }
        )
        
    except Exception as e:
        logger.error(f"❌ Error in unified query processor: {e}")
        return func.HttpResponse(
            json.dumps({
                "success": False,
                "error": str(e),
                "response": f"I encountered an error processing your query: {str(e)}. Please check that all services are configured correctly.",
                "timestamp": datetime.utcnow().isoformat()
            }),
            status_code=500,
            headers={
                "Content-Type": "application/json",
                "Access-Control-Allow-Origin": "*"
            }
        )

@app.route(route="stac-search", methods=["POST"])
async def stac_search_endpoint(req: func.HttpRequest) -> func.HttpResponse:
    """Direct STAC search endpoint for backwards compatibility"""
    try:
        logger.info("🔍 Direct STAC search endpoint called")
        
        req_body = req.get_json()
        if not req_body:
            return func.HttpResponse(
                json.dumps({"error": "Request body required"}),
                status_code=400,
                headers={"Content-Type": "application/json", "Access-Control-Allow-Origin": "*"}
            )
        
        # Execute STAC search
        stac_response = await execute_direct_stac_search(req_body)
        
        return func.HttpResponse(
            json.dumps(stac_response),
            status_code=200 if stac_response.get("success") else 500,
            headers={
                "Content-Type": "application/json",
                "Access-Control-Allow-Origin": "*"
            }
        )
        
    except Exception as e:
        logger.error(f"STAC search endpoint error: {e}")
        return func.HttpResponse(
            json.dumps({"success": False, "error": str(e)}),
            status_code=500,
            headers={
                "Content-Type": "application/json",
                "Access-Control-Allow-Origin": "*"
            }
        )

# VEDA INTEGRATION DISABLED: Commenting out VEDA private-search endpoint
# This endpoint was interfering with the original semantic translator → STAC workflow
# To restore original functionality, VEDA features are disabled

# @app.route(route="private-search", methods=["POST"])
# async def private_search_endpoint(req: func.HttpRequest) -> func.HttpResponse:
#     """Private data search endpoint using VEDA AI Search POC"""
#     try:
#         logger.info("🔍 Private data search endpoint called")
#         
#         req_body = req.get_json()
#         if not req_body:
#             return func.HttpResponse(
#                 json.dumps({"success": False, "error": "Request body required"}),
#                 status_code=400,
#                 headers={"Content-Type": "application/json", "Access-Control-Allow-Origin": "*"}
#             )
#         
#         query = req_body.get("query", "")
#         if not query:
#             return func.HttpResponse(
#                 json.dumps({"success": False, "error": "Query parameter required"}),
#                 status_code=400,
#                 headers={"Content-Type": "application/json", "Access-Control-Allow-Origin": "*"}
#             )
#         
#         logger.info(f"🔍 Private search query: {query}")
#         
#         # Import and initialize VEDA Search Agent
#         try:
#             import sys
#             import os
#             veda_search_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'ai-search', 'veda_search_poc')
#             if veda_search_path not in sys.path:
#                 sys.path.append(veda_search_path)
#             
#             from agent import VEDASearchAgent
#             
#             # Initialize AI Search agent
#             agent = VEDASearchAgent()
#             result = await asyncio.wait_for(agent.process_query(query), timeout=30.0)
#             
#             logger.info(f"✅ VEDA Search completed: {len(result.get('collections', []))} collections found")
#             
#             return func.HttpResponse(
#                 json.dumps({
#                     "success": True,
#                     "data": result,
#                     "source": "veda_ai_search",
#                     "message": result.get("answer", "Search completed successfully"),
#                     "collections": result.get("collections", []),
#                     "timestamp": datetime.utcnow().isoformat()
#                 }),
#                 status_code=200,
#                 headers={
#                     "Content-Type": "application/json",
#                     "Access-Control-Allow-Origin": "*"
#                 }
#             )
#             
#         except ImportError as e:
#             logger.error(f"❌ Failed to import VEDA Search Agent: {e}")
#             return func.HttpResponse(
#                 json.dumps({
#                     "success": False,
#                     "error": "VEDA AI Search not available",
#                     "message": f"Could not initialize VEDA Search Agent: {str(e)}"
#                 }),
#                 status_code=500,
#                 headers={"Content-Type": "application/json", "Access-Control-Allow-Origin": "*"}
#             )
#         except asyncio.TimeoutError:
#             logger.error("❌ VEDA Search timeout")
#             return func.HttpResponse(
#                 json.dumps({
#                     "success": False,
#                     "error": "Search timeout",
#                     "message": "VEDA search took too long to complete. Please try a simpler query."
#                 }),
#                 status_code=408,
#                 headers={"Content-Type": "application/json", "Access-Control-Allow-Origin": "*"}
#             )
#         except Exception as e:
#             logger.error(f"❌ VEDA Search error: {e}")
#             return func.HttpResponse(
#                 json.dumps({
#                     "success": False,
#                     "error": str(e),
#                     "message": f"VEDA search failed: {str(e)}"
#                 }),
#                 status_code=500,
#                 headers={"Content-Type": "application/json", "Access-Control-Allow-Origin": "*"}
#             )
#         
#     except Exception as e:
#         logger.error(f"❌ Private search endpoint error: {e}")
#         return func.HttpResponse(
#             json.dumps({"success": False, "error": str(e)}),
#             status_code=500,
#             headers={
#                 "Content-Type": "application/json",
#                 "Access-Control-Allow-Origin": "*"
#             }
#         )

# VEDA private-search endpoint disabled - returns 410 Gone
    return func.HttpResponse(
        json.dumps({
            "success": False,
            "error": "VEDA Search Disabled",
            "message": "VEDA AI Search has been disabled to restore original semantic translator workflow. Use the main /query endpoint instead.",
            "timestamp": datetime.utcnow().isoformat()
        }),
        status_code=410,  # Gone
        headers={
            "Content-Type": "application/json",
            "Access-Control-Allow-Origin": "*"
        }
    )

# VEDA INTEGRATION DISABLED: Commenting out VEDA private-collections endpoint
# This endpoint was interfering with the original semantic translator → STAC workflow

# @app.route(route="private-collections", methods=["GET"])
# async def private_collections_endpoint(req: func.HttpRequest) -> func.HttpResponse:
#     """Get available VEDA collections for dropdown"""
#     try:
#         logger.info("📂 Private collections endpoint called")
#         
#         # Import and get collections from VEDA Search
#         try:
#             import sys
#             import os
#             veda_search_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'ai-search', 'veda_search_poc')
#             if veda_search_path not in sys.path:
#                 sys.path.append(veda_search_path)
#             
#             from agent import VEDASearchAgent
#             
#             # Initialize AI Search agent and get collections
#             agent = VEDASearchAgent()
#             collections = await asyncio.wait_for(agent.get_available_collections(), timeout=10.0)
#             
#             logger.info(f"✅ Retrieved {len(collections)} VEDA collections")
#             
#             return func.HttpResponse(
#                 json.dumps({
#                     "success": True,
#                     "collections": collections,
#                     "total": len(collections),
#                     "timestamp": datetime.utcnow().isoformat()
#                 }),
#                 status_code=200,
#                 headers={
#                     "Content-Type": "application/json",
#                     "Access-Control-Allow-Origin": "*"
#                 }
#             )
#             
#         except ImportError as e:
#             logger.error(f"❌ Failed to import VEDA Search Agent: {e}")
#             # Return fallback collections
#             fallback_collections = [
#                 {"id": "barc-thomasfire", "title": "Burn Area Reflectance Classification for Thomas Fire", "description": "BARC from BAER program for Thomas fire, 2017"},
#                 {"id": "blizzard-era5-pressure", "title": "Blizzard ERA5 Surface Pressure", "description": "Surface pressure from ERA5 during blizzard events"},
#                 {"id": "blizzard-era5-2m-temp", "title": "Blizzard ERA5 2m Temperature", "description": "2m temperature from ERA5 during blizzard events"},
#                 {"id": "bangladesh-landcover-2001-2020", "title": "Bangladesh Land Cover (2001-2020)", "description": "MODIS-based land cover classification maps"}
#             ]
#             return func.HttpResponse(
#                 json.dumps({
#                     "success": True,
#                     "collections": fallback_collections,
#                     "total": len(fallback_collections),
#                     "source": "fallback",
#                     "timestamp": datetime.utcnow().isoformat()
#                 }),
#                 status_code=200,
#                 headers={"Content-Type": "application/json", "Access-Control-Allow-Origin": "*"}
#             )
#         except Exception as e:
#             logger.error(f"❌ VEDA Collections error: {e}")
#             return func.HttpResponse(
#                 json.dumps({
#                     "success": False,
#                     "error": str(e),
#                     "message": f"Failed to retrieve VEDA collections: {str(e)}"
#                 }),
#                 status_code=500,
#                 headers={"Content-Type": "application/json", "Access-Control-Allow-Origin": "*"}
#             )
#         
#     except Exception as e:
#         logger.error(f"❌ Private collections endpoint error: {e}")
#         return func.HttpResponse(
#             json.dumps({"success": False, "error": str(e)}),
#             status_code=500,
#             headers={
#                 "Content-Type": "application/json",
#                 "Access-Control-Allow-Origin": "*"
#             }
#         )

# VEDA private-collections endpoint disabled - returns 410 Gone
    return func.HttpResponse(
        json.dumps({
            "success": False,
            "error": "VEDA Collections Disabled",
            "message": "VEDA AI collections endpoint has been disabled to restore original semantic translator workflow.",
            "timestamp": datetime.utcnow().isoformat()
        }),
        status_code=410,  # Gone
        headers={
            "Content-Type": "application/json",
            "Access-Control-Allow-Origin": "*"
        }
    )

# Startup completion message
logger.info("=" * 60)
logger.info("🎉 UNIFIED ROUTER+STAC FUNCTION INITIALIZATION COMPLETE")
logger.info("🎉 Ready to handle requests on all endpoints:")
logger.info("🎉   GET  /api/health             - Health check and diagnostics")
logger.info("🎉   POST /api/query              - Unified natural language query processing")
logger.info("🎉   POST /api/stac-search        - Direct STAC search")
logger.info("🎉   POST /api/private-search     - VEDA AI Search POC")
logger.info("🎉   GET  /api/private-collections - VEDA collections for dropdown")
logger.info("=" * 60)
