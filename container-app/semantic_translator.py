# Copyright (c) Microsoft Corporation.
# Licensed under the MIT license.

import asyncio
import json
import logging
import math
import os
from typing import Dict, List, Any, Optional, Union
from datetime import datetime, timedelta
import aiohttp
import re
import time
import hashlib
import traceback

# Import the consolidated location resolver
from location_resolver import EnhancedLocationResolver

# Initialize logger first
logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)

# Import the TileSelector for intelligent limit calculation
try:
    from tile_selector import TileSelector
    TILE_SELECTOR_AVAILABLE = True
    logger.info("✅ TileSelector loaded - intelligent query limit calculation enabled")
except ImportError:
    TILE_SELECTOR_AVAILABLE = False
    logger.warning("⚠️ TileSelector not available - using hardcoded limits")

# Import Featured Collections list for prioritization
try:
    from hybrid_rendering_system import FEATURED_COLLECTIONS
    logger.info("✅ Featured Collections loaded - prioritization enabled")
except ImportError:
    FEATURED_COLLECTIONS = []
    logger.warning("⚠️ Featured Collections not available - no prioritization")

# Import unified collection profiles (SINGLE SOURCE OF TRUTH)
try:
    from collection_profiles import (
        COLLECTION_PROFILES,
        get_query_rules,
        generate_agent_query_knowledge,
        is_static_collection,
        is_composite_collection,
        supports_temporal_filtering,
        supports_cloud_filtering,
        uses_sortby_instead_of_datetime,
        get_ignored_parameters,
        get_cloud_cover_property
    )
    PROFILES_AVAILABLE = True
    logger.info("✅ Unified collection profiles loaded - single source of truth active")
except ImportError:
    COLLECTION_PROFILES = {}
    PROFILES_AVAILABLE = False
    logger.warning("⚠️ Collection profiles not available - using static mapping")
    
    # Fallback functions
    def generate_collection_knowledge_for_agent() -> str:
        return ""
    def is_static_collection(collection_id: str) -> bool:
        return collection_id in ["cop-dem-glo-30", "cop-dem-glo-90", "nasadem", "alos-dem"]
    def is_composite_collection(collection_id: str) -> bool:
        return "modis" in collection_id.lower()
    def supports_temporal_filtering(collection_id: str) -> bool:
        return not is_static_collection(collection_id)
    def supports_cloud_filtering(collection_id: str) -> bool:
        return not (is_static_collection(collection_id) or is_composite_collection(collection_id))
    def uses_sortby_instead_of_datetime(collection_id: str) -> bool:
        return is_composite_collection(collection_id)
    def get_ignored_parameters(collection_id: str) -> list:
        return []
    def validate_multi_collection_query(stac_query: dict) -> tuple:
        return True, {}
    def log_query_construction_strategy(collections: list, stac_query: dict, logger_instance=None):
        pass

# Import VEDA collection profiles for dual-source routing
try:
    from veda_collection_profiles import is_veda_query, get_veda_collections_for_query
    VEDA_PROFILES_AVAILABLE = True
    logger.info("✅ VEDA collection profiles loaded - dual-source routing enabled")
except ImportError:
    VEDA_PROFILES_AVAILABLE = False
    logger.warning("⚠️ VEDA collection profiles not available - using Planetary Computer only")
    
    # Fallback functions
    def is_veda_query(query: str) -> bool:
        return False
    
    def get_veda_collections_for_query(query: str) -> List[str]:
        return []

# Configure enhanced debug logging
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(name)s - %(levelname)s - %(funcName)s:%(lineno)d - %(message)s',
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler('semantic_translator_debug.log', mode='w')
    ]
)

# Semantic Kernel 1.37.0+ compatible imports for GPT-5 support
try:
    import semantic_kernel as sk
    from semantic_kernel import Kernel
    from semantic_kernel.connectors.ai.open_ai import AzureChatCompletion
    from semantic_kernel.connectors.ai.function_choice_behavior import FunctionChoiceBehavior
    from semantic_kernel.connectors.ai.chat_completion_client_base import ChatCompletionClientBase
    from semantic_kernel.contents.chat_history import ChatHistory
    from semantic_kernel.functions.kernel_arguments import KernelArguments
    from semantic_kernel.connectors.ai.open_ai.prompt_execution_settings.azure_chat_prompt_execution_settings import (
        AzureChatPromptExecutionSettings,
    )
    # Template classes for SK 1.37.0+
    from semantic_kernel.prompt_template.prompt_template_config import PromptTemplateConfig
    from semantic_kernel.prompt_template.input_variable import InputVariable
    from semantic_kernel.functions.kernel_function import KernelFunction
    SK_AVAILABLE = True
    logging.info(f"[OK] Semantic Kernel {sk.__version__} successfully imported with GPT-5 support")
except ImportError as e:
    SK_AVAILABLE = False
    logging.error(f"[ERROR] Semantic Kernel import failed: {e}")
    logging.error("This will prevent AI functionality - Earth Copilot requires Semantic Kernel")
    raise ImportError(f"Semantic Kernel is required for Earth Copilot functionality: {e}")
except Exception as e:
    SK_AVAILABLE = False
    logging.error(f"✗ Unexpected error loading Semantic Kernel: {e}")
    raise Exception(f"Critical error initializing Semantic Kernel: {e}")

logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)

class LocationCache:
    """In-memory location cache with TTL for performance optimization"""
    
    def __init__(self, ttl_hours: int = 24, max_entries: int = 500):
        self.cache = {}
        self.ttl_seconds = ttl_hours * 3600
        self.max_entries = max_entries
    
    def _generate_key(self, location_name: str, location_type: str) -> str:
        """Generate cache key for location"""
        key_string = f"{location_name.lower().strip()}:{location_type.lower()}"
        return hashlib.md5(key_string.encode()).hexdigest()
    
    def get(self, location_name: str, location_type: str) -> Optional[List[float]]:
        """Get cached location bbox"""
        key = self._generate_key(location_name, location_type)
        
        if key in self.cache:
            entry = self.cache[key]
            if time.time() - entry["timestamp"] < self.ttl_seconds:
                logger.info(f"Cache hit for location: {location_name}")
                return entry["bbox"]
            else:
                del self.cache[key]
        
        return None
    
    def set(self, location_name: str, location_type: str, bbox: List[float]):
        """Cache location bbox"""
        key = self._generate_key(location_name, location_type)
        
        if len(self.cache) >= self.max_entries:
            self._evict_oldest()
        
        self.cache[key] = {
            "bbox": bbox,
            "timestamp": time.time(),
            "location_name": location_name
        }
        logger.info(f"Cached location: {location_name}")
    
    def _evict_oldest(self):
        """Remove oldest cache entry"""
        if self.cache:
            oldest_key = min(self.cache.keys(), key=lambda k: self.cache[k]["timestamp"])
            del self.cache[oldest_key]

class SemanticQueryTranslator:
    """Enhanced query translator using Semantic Kernel with GPT-5 for intelligent entity extraction and contextual Earth science analysis"""
    
    def __init__(self, azure_openai_endpoint: str, azure_openai_api_key: str, model_name: str):
        if not SK_AVAILABLE:
            raise ImportError("Semantic Kernel is not available")
        
        # Store configuration for lazy initialization (GPT-5 optimized)
        self.azure_openai_endpoint = azure_openai_endpoint
        self.azure_openai_api_key = azure_openai_api_key
        self.model_name = model_name
        
        # STAC API endpoints
        self.stac_endpoints = {
            "planetary_computer": "https://planetarycomputer.microsoft.com/api/stac/v1/search",
            "veda": "https://openveda.cloud/api/stac/search"
        }
        
        # Kernel will be initialized lazily on first use
        self.kernel = None
        self._kernel_initialized = False
        
        # Initialize consolidated location resolver
        self.location_resolver = EnhancedLocationResolver()
        
        # Initialize location cache (kept for compatibility)
        self.location_cache = LocationCache()
        
        # 🧠 CONVERSATION CONTEXT MANAGEMENT
        self.conversation_contexts = {}  # conversation_id -> context data
        
        logger.info("✓ Using consolidated EnhancedLocationResolver (Azure Maps → Nominatim → Azure OpenAI)")
        
        # Initialize STAC query checker (disabled for streamlined version)
        self.query_checker = None  # Disabled for streamlined version
        
        # Comprehensive collection mappings 
        self.collection_mappings = {
            # Disaster response collections
            "disaster": {
                "hurricane": {
                    "primary": ["sentinel-1-grd", "sentinel-2-l2a"],
                    "secondary": ["landsat-c2-l2", "naip", "hls-s30"],
                    "thermal": []
                },
                "wildfire": {
                    "primary": ["modis-14A1-061", "modis-14A2-061", "viirs-14A1-001"],  # Validated working collections
                    "secondary": ["modis-MCD64A1-061", "sentinel-2-l2a", "landsat-c2-l2"],  # Burned area + optical
                    "thermal": ["modis-14A1-061", "modis-14A2-061", "viirs-14A1-001"]  # All thermal anomaly collections
                },
                "flood": {
                    "primary": ["sentinel-1-grd"],
                    "secondary": ["sentinel-2-l2a", "hls-s30"],
                    "thermal": []
                },
                "earthquake": {
                    "primary": ["sentinel-1-grd", "cop-dem-glo-30"],
                    "secondary": ["sentinel-2-l2a", "nasadem"],
                    "thermal": []
                }
            },
            
            # Agricultural and vegetation analysis
            "agriculture": {
                "crop_monitoring": ["modis-13Q1-061", "hls-l30", "hls-s30", "sentinel-2-l2a"],
                "crop_classification": ["usda-cdl", "sentinel-2-l2a", "landsat-c2-l2"],
                "irrigation": ["sentinel-1-grd", "sentinel-2-l2a"],
                "yield_estimation": ["modis-13Q1-061", "landsat-c2-l2"]
            },
            
            # Climate and weather analysis
            "climate": {
                "weather_patterns": ["era5-pds", "era5-land", "daymet-daily-na"],
                "precipitation": ["gpm-imerg-hhr", "era5-pds"],
                "temperature": ["era5-pds", "era5-land", "daymet-daily-na"],
                "thermal_infrared": ["landsat-c2-l2", "modis-14A1-061"],
                "snow_cover": ["modis-10A1-061", "viirs-snow-cover"]
            },
            
            # Environmental monitoring
            "environment": {
                "land_cover": ["esa-worldcover", "io-lulc-annual-v02", "usda-cdl"],
                "deforestation": ["sentinel-2-l2a", "landsat-c2-l2", "modis-13Q1-061"],
                "water_quality": ["sentinel-2-l2a", "landsat-c2-l2"],
                "air_quality": ["sentinel-5p-l2", "tropomi-no2"]
            },
            
            # Ocean and marine
            "ocean": {
                "sea_surface_temperature": ["modis-sst"],
                "ocean_color": ["modis-oc"],
                "coastal_monitoring": ["sentinel-2-l2a", "naip", "landsat-c2-l2"]
            },
            
            # Urban and infrastructure
            "urban": {
                "city_development": ["naip", "sentinel-2-l2a", "landsat-c2-l2"],
                "infrastructure": ["sentinel-1-grd", "naip", "sentinel-2-l2a"],
                "population_mapping": ["naip", "sentinel-2-l2a"]
            },
            
            # Terrain and topography
            "terrain": {
                "elevation": ["cop-dem-glo-30", "cop-dem-glo-90", "nasadem"],
                "slope_analysis": ["cop-dem-glo-30", "nasadem"],
                "watershed": ["cop-dem-glo-30", "cop-dem-glo-90"]
            }
        }
        
        # For backwards compatibility, keep disaster_collections as a reference
        self.disaster_collections = self.collection_mappings["disaster"]
        
        logger.info("✓ SemanticQueryTranslator created with comprehensive collection mappings and enhanced Earth science capabilities")
    
    # 🧠 CONVERSATION CONTEXT MANAGEMENT METHODS
    def get_conversation_context(self, conversation_id: str) -> Dict[str, Any]:
        """Get conversation context for a session"""
        if conversation_id not in self.conversation_contexts:
            self.conversation_contexts[conversation_id] = {
                "session_id": conversation_id,
                "query_count": 0,
                "queries": [],
                "responses": [],
                "last_map_data": None,
                "last_location": None,
                "last_collections": [],
                "last_bbox": None,
                "context_topics": [],
                "session_start": datetime.now(),
                "has_rendered_map": False
            }
        return self.conversation_contexts[conversation_id]
    
    def update_conversation_context(self, conversation_id: str, query: str, response_data: Dict[str, Any]) -> None:
        """Update conversation context with new query and response"""
        context = self.get_conversation_context(conversation_id)
        
        context["query_count"] += 1
        
        # Store the actual user query and assistant response for chat history
        user_message = query
        assistant_response = response_data.get("message", "")
        
        context["queries"].append({
            "query": query,
            "timestamp": datetime.now(),
            "query_number": context["query_count"]
        })
        
        context["responses"].append({
            "response": response_data,
            "timestamp": datetime.now(),
            "query_number": context["query_count"]
        })
        
        # Store chat history for context-aware responses
        context.setdefault("chat_history", [])
        context["chat_history"].append({
            "role": "user", 
            "content": user_message,
            "timestamp": datetime.now()
        })
        context["chat_history"].append({
            "role": "assistant", 
            "content": assistant_response,
            "timestamp": datetime.now()
        })
        
        # Keep only the last 10 exchanges (20 messages) to manage memory
        if len(context["chat_history"]) > 20:
            context["chat_history"] = context["chat_history"][-20:]
        
        # Update map-related context if response contains map data
        if response_data.get("data", {}).get("features"):
            context["has_rendered_map"] = True
            context["last_map_data"] = response_data.get("data")
            context["last_bbox"] = response_data.get("data", {}).get("bbox")
            
            # Extract collections used
            features = response_data.get("data", {}).get("features", [])
            collections = list(set(f.get("collection", "") for f in features if f.get("collection")))
            context["last_collections"] = collections
        
        # Track location context
        location_focus = response_data.get("location_focus") or self._extract_location_from_query(query)
        if location_focus:
            context["last_location"] = location_focus
        
        # Track contextual topics
        query_type = response_data.get("query_type", "")
        if query_type not in context["context_topics"]:
            context["context_topics"].append(query_type)
        
        logger.info(f"🧠 Updated conversation context for {conversation_id}: {context['query_count']} queries, {len(context.get('chat_history', []))} messages in history")

    def get_recent_chat_history(self, conversation_id: str, max_exchanges: int = 3) -> str:
        """Get recent chat history formatted for context"""
        context = self.get_conversation_context(conversation_id)
        chat_history = context.get("chat_history", [])
        
        if not chat_history:
            return ""
        
        # Get the last N exchanges (N*2 messages since each exchange has user + assistant)
        recent_messages = chat_history[-(max_exchanges * 2):]
        
        formatted_history = []
        for message in recent_messages:
            role = "User" if message["role"] == "user" else "Assistant"
            content = message["content"][:200] + "..." if len(message["content"]) > 200 else message["content"]
            formatted_history.append(f"{role}: {content}")
        
        return "\n".join(formatted_history)

    def reset_conversation_context(self, conversation_id: str) -> None:
        """Reset/clear conversation context for session restart"""
        if conversation_id in self.conversation_contexts:
            del self.conversation_contexts[conversation_id]
            logger.info(f"🔄 Reset conversation context for {conversation_id}")

    def is_follow_up_query(self, conversation_id: str, query: str) -> bool:
        """Determine if this is a follow-up query - automatically true for any query after the first"""
        context = self.get_conversation_context(conversation_id)
        
        # First query is never a follow-up
        if context["query_count"] == 0:
            return False
        
        # All subsequent queries are follow-ups unless session is refreshed
        is_follow_up = True
        
        logger.info(f"🔍 Follow-up analysis for '{query}': query_count={context['query_count']}, is_follow_up={is_follow_up}")
        
        return is_follow_up
    
    def determine_stac_source(self, query: str, entities: Dict[str, Any]) -> str:
        """Determine whether to use Planetary Computer or VEDA STAC API based on query characteristics"""
        query_lower = query.lower()
        
        # Use VEDA collection profiles for intelligent routing
        if is_veda_query(query):
            matched_collections = get_veda_collections_for_query(query)
            if matched_collections:
                logger.info(f"🧪 Query routed to VEDA STAC: {query} -> Collections: {matched_collections}")
                return "veda"
        
        # Additional VEDA indicators not in profiles
        additional_veda_indicators = [
            "specialized research", "nasa research", "climate model", "scientific study",
            "historical analysis", "static dataset", "research data"
        ]
        
        if any(indicator in query_lower for indicator in additional_veda_indicators):
            logger.info(f"🧪 Research-based routing to VEDA STAC: {query}")
            return "veda"
        
        # Check for real-time/operational indicators that suggest Planetary Computer
        pc_indicators = [
            "recent", "latest", "current", "real-time", "today", "yesterday",
            "sentinel", "landsat", "monitoring", "live", "operational",
            "time series", "temporal analysis", "change detection"
        ]
        
        if any(indicator in query_lower for indicator in pc_indicators):
            logger.info(f"🛰️ Operational-based routing to Planetary Computer STAC: {query}")
            return "planetary_computer"
        
        # Default to reliable Planetary Computer for general queries
        logger.info(f"🛰️ Default routing to Planetary Computer STAC: {query}")
        return "planetary_computer"
    
    def get_veda_collections_for_query(self, query: str) -> List[str]:
        """Get specific VEDA collections that match the query"""
        return get_veda_collections_for_query(query)
    
    def build_veda_stac_query(self, entities: Dict[str, Any], bbox: Optional[List[float]]) -> Dict[str, Any]:
        """Build STAC query specifically for VEDA collections (no datetime filters)"""
        query_text = entities.get("original_query", "").lower()
        
        # Get VEDA collections based on query
        veda_collections = self.get_veda_collections_for_query(query_text)
        
        # If no specific collections found, try to map to VEDA categories
        if not veda_collections:
            if any(term in query_text for term in ["fire", "burn", "wildfire"]):
                veda_collections = ["barc-thomasfire"]
            elif any(term in query_text for term in ["land cover", "vegetation"]):
                veda_collections = ["bangladesh-landcover-2001-2020"]
            elif any(term in query_text for term in ["weather", "climate", "era5"]):
                veda_collections = ["blizzard-era5-2m-temp", "blizzard-era5-10m-wind"]
            elif any(term in query_text for term in ["blizzard", "storm"]):
                veda_collections = ["blizzard-count", "blizzard-alley"]
        
        # Build VEDA query (no datetime - they're static datasets)
        stac_query = {
            "collections": veda_collections[:3] if veda_collections else ["bangladesh-landcover-2001-2020"],
            "limit": 10  # VEDA has fewer items per collection
        }
        
        # Add bbox if available
        if bbox:
            stac_query["bbox"] = bbox
        
        logger.info(f"📊 Built VEDA STAC query: {stac_query}")
        return stac_query
    
    def _extract_location_from_query(self, query: str) -> Optional[str]:
        """Extract location from query text (basic implementation)"""
        # Simple location extraction - could be enhanced with NER
        query_lower = query.lower()
        
        # Look for common location patterns
        location_patterns = [
            r'\bin\s+([A-Z][a-zA-Z\s]+?)(?:\s+(?:area|region|city|county|state|country))?(?:\s|$|\?|\.)',
            r'\bof\s+([A-Z][a-zA-Z\s]+?)(?:\s+(?:area|region|city|county|state|country))?(?:\s|$|\?|\.)',
            r'^([A-Z][a-zA-Z\s]+?)(?:\s+(?:area|region|city|county|state|country))?(?:\s|$|\?|\.)'
        ]
        
        import re
        for pattern in location_patterns:
            match = re.search(pattern, query)
            if match:
                location = match.group(1).strip()
                if len(location) > 2 and location not in ['Show', 'Tell', 'What', 'How', 'Why']:
                    return location
        
        return None

    async def classify_query_intent_unified(self, query: str, conversation_id: str = None) -> Dict[str, Any]:
        """
        🎯 UNIFIED INTENT CLASSIFIER (Replaces Agent 0 + Agent 0.5)
        
        Single GPT-5 call that determines query intent and routing.
        
        Intent Types (4):
        - vision: Analyze CURRENTLY VISIBLE imagery (no new data loading)
        - stac: Load NEW satellite imagery only (no analysis)
        - hybrid: Load NEW imagery AND analyze it (sequential: load → analyze)
        - contextual: Information/education only (no map interaction)
        
        Benefits over separate calls:
        - 50% faster (one GPT call vs two)
        - 50% cheaper (half the API costs)
        - Better context (GPT sees full picture)
        - No conflicts (single source of truth)
        
        Returns:
            Dict with unified classification:
            {
                "intent_type": str,  # vision | stac | hybrid | contextual
                "needs_satellite_data": bool,
                "needs_vision_analysis": bool,
                "needs_contextual_info": bool,
                "confidence": float,
                "reasoning": str,
                "query": str
            }
        """
        try:
            # Get conversation context if available
            context_info = ""
            if conversation_id:
                context = self.get_conversation_context(conversation_id)
                recent_history = self.get_recent_chat_history(conversation_id)
                
                if recent_history:
                    context_info = f"""
**CONVERSATION CONTEXT:**
Recent chat history:
{recent_history}

Current location focus: {context.get('last_location', 'None')}
Data currently displayed: {'Yes' if context.get('has_rendered_map') else 'No'}
"""

            prompt = f"""You are an expert at classifying Earth observation queries.

Analyze this query and classify it into one of 4 intent types.

**INTENT TYPES:**

1. **vision**: Analyze CURRENTLY VISIBLE imagery (no new data loading)
   - User asks about what's already displayed on the map
   - Keywords: "in this image", "what's visible", "describe this", "what do you see", "can you see"
   - Examples: 
     * "What bodies of water are in this image?"
     * "Describe the land cover visible"
     * "Are there any urban areas visible?"
     * "Identify features in this view"
   - Characteristics: NO loading/showing new data, analyzing existing view
   - Requires: Screenshot of current map, NO new STAC search

2. **stac**: Load NEW satellite imagery (visualization only, no analysis)
   - User wants to see/display/show satellite data without analysis
   - Keywords: "show me", "load", "display", "find imagery", "get data for"
   - Examples:
     * "Show me Seattle"
     * "Load Sentinel-2 imagery of NYC"
     * "Display HLS data for California"
     * "Find Landsat scenes from last week"
   - Characteristics: ONLY visualization request, NO analysis/description needed
   - Requires: STAC search + map rendering

3. **hybrid**: Load NEW imagery AND analyze it
   - User wants to load satellite data AND get analysis/description of it
   - Keywords: Combines loading words + analysis words in same query
   - Examples:
     * "Show me Seattle and describe the coastline"
     * "Display wildfire damage in California and explain what happened"
     * "Load Manhattan and identify the parks"
     * "Show Amazon rainforest and assess deforestation"
     * "Get imagery of Tokyo and analyze urban heat"
   - Characteristics: Requests BOTH new data loading AND analysis
   - Requires: STAC search + map render + vision analysis (sequential)

4. **contextual**: Information/education only (no map, no imagery)
   - User asks for information, definitions, explanations, FACTUAL QUESTIONS, or HISTORICAL IMPACT QUESTIONS
   - Keywords: "how", "what is", "explain", "why", "define", "tell me about", "what causes", "what/which/where is the", "how was/were", "what was the impact"
   - Examples:
     * "How do hurricanes form?"
     * "What is NDVI?"
     * "Explain urban heat islands"
     * "Why do wildfires spread?"
     * "What is the highest peak in Colorado?" (factual question, no imagery needed)
     * "Which state has the most tornadoes?" (factual question, no imagery needed)
     * "Where is Mount Everest located?" (factual question, no imagery needed)
     * "How was NYC impacted by Hurricane Sandy?" (historical impact question, no current imagery needed)
     * "What was the damage from the 2011 Japan tsunami?" (historical question, no map needed)
     * "Tell me about the Yellowstone fires" (historical/educational, no imagery needed)
   - Characteristics: Pure informational/factual/historical request, NO "show/display/load" keywords, past tense indicates historical inquiry
   - Requires: GPT response only (can reference historical facts without showing maps)

{context_info}

**Query:** "{query}"

**⚠️ CRITICAL: Check query tense FIRST before anything else!**
- If query uses PAST TENSE (was/were/did/had) and NO "show/display/load" → ALWAYS classify as **contextual**
- Historical questions about past events = contextual (informational), NOT geospatial (visualization)
- Example: "How was NYC impacted by Hurricane Sandy?" = contextual (past event, informational)
- Example: "Show me Hurricane Sandy damage in NYC" = stac (visualization request)

**CRITICAL DECISION LOGIC:**

1. **PAST TENSE CHECK (HIGHEST PRIORITY):**
   - "was/were/did/had" + NO "show/display/load" → **contextual** (historical inquiry)
   - Past disaster events + location = contextual (asking about what happened, not visualizing)
   
2. **VISUALIZATION KEYWORDS:**
   - "in this image" / "what's visible" / "can you see" → **vision**
   - "show/load/display" ONLY (no analysis words) → **stac**
   - "show/load/display" AND "describe/analyze/explain/identify" → **hybrid**
   
3. **INFORMATIONAL KEYWORDS:**
   - "how/what is/explain/why/which/where is the" (NO "show/display/load") → **contextual**

4. **IMPORTANT:**
   - **Location + Disaster does NOT mean geospatial** if past tense or no "show" keyword
   - Check for "show/display/load" keywords first before assuming visualization needed!

**Return ONLY valid JSON (no markdown, no explanations):**

{{
  "intent_type": "vision|stac|hybrid|contextual",
  "needs_satellite_data": true/false,
  "needs_vision_analysis": true/false,
  "needs_contextual_info": true/false,
  "confidence": 0.0-1.0,
  "reasoning": "Brief explanation of classification"
}}

**EXAMPLES:**

Query: "What bodies of water are in this image?"
Response: {{"intent_type": "vision", "needs_satellite_data": false, "needs_vision_analysis": true, "needs_contextual_info": false, "confidence": 0.98, "reasoning": "Keyword 'in this image' indicates analyzing current view"}}

Query: "Show me Seattle"
Response: {{"intent_type": "stac", "needs_satellite_data": true, "needs_vision_analysis": false, "needs_contextual_info": false, "confidence": 0.95, "reasoning": "Only requests displaying imagery, no analysis mentioned"}}

Query: "Show me Seattle and describe the coastline"
Response: {{"intent_type": "hybrid", "needs_satellite_data": true, "needs_vision_analysis": true, "needs_contextual_info": false, "confidence": 0.93, "reasoning": "Requests both loading Seattle imagery AND describing features"}}

Query: "Display wildfire damage in California and explain what happened"
Response: {{"intent_type": "hybrid", "needs_satellite_data": true, "needs_vision_analysis": true, "needs_contextual_info": true, "confidence": 0.90, "reasoning": "Requests loading imagery, vision analysis, and contextual explanation"}}

Query: "How do hurricanes form?"
Response: {{"intent_type": "contextual", "needs_satellite_data": false, "needs_vision_analysis": false, "needs_contextual_info": true, "confidence": 0.97, "reasoning": "Educational question, no map or imagery needed"}}

Query: "Load Manhattan and identify the parks"
Response: {{"intent_type": "hybrid", "needs_satellite_data": true, "needs_vision_analysis": true, "needs_contextual_info": false, "confidence": 0.92, "reasoning": "Requests loading new imagery and identifying features"}}

Query: "Describe what you see"
Response: {{"intent_type": "vision", "needs_satellite_data": false, "needs_vision_analysis": true, "needs_contextual_info": false, "confidence": 0.96, "reasoning": "Asks to describe current visible imagery"}}

Query: "What is NDVI and how is it calculated?"
Response: {{"intent_type": "contextual", "needs_satellite_data": false, "needs_vision_analysis": false, "needs_contextual_info": true, "confidence": 0.95, "reasoning": "Educational question about concepts"}}

Query: "What is the highest peak in Colorado?"
Response: {{"intent_type": "contextual", "needs_satellite_data": false, "needs_vision_analysis": false, "needs_contextual_info": true, "confidence": 0.96, "reasoning": "Factual question about location - no 'show/display/load' keywords, user wants information not imagery"}}

Query: "Where is Mount Rainier located?"
Response: {{"intent_type": "contextual", "needs_satellite_data": false, "needs_vision_analysis": false, "needs_contextual_info": true, "confidence": 0.97, "reasoning": "Factual location question - no visualization requested"}}

Query: "How was NYC impacted by Hurricane Sandy?"
Response: {{"intent_type": "contextual", "needs_satellite_data": false, "needs_vision_analysis": false, "needs_contextual_info": true, "confidence": 0.94, "reasoning": "Historical impact question with past tense - user wants information about what happened, not current imagery"}}

Query: "Show me the damage from Hurricane Sandy in NYC"
Response: {{"intent_type": "stac", "needs_satellite_data": true, "needs_vision_analysis": false, "needs_contextual_info": false, "confidence": 0.93, "reasoning": "Contains 'show me' keyword - user wants to visualize/load imagery"}}
"""
            
            # Use Semantic Kernel for classification
            result = await self.kernel.invoke_prompt(
                prompt=prompt,
                function_name="classify_query_unified",
                plugin_name="classification"
            )
            
            content = self._extract_clean_content_from_sk_result(result).strip()
            
            # Clean JSON markers
            if '```json' in content:
                content = content.split('```json')[1].split('```')[0].strip()
            elif '```' in content:
                content = content.split('```')[1].split('```')[0].strip()
            
            # Parse JSON response
            classification = json.loads(content)
            
            # Add query to classification for downstream use
            classification['query'] = query
            
            logger.info(f"🎯 UNIFIED INTENT CLASSIFIER: {classification['intent_type']}")
            logger.info(f"   Satellite data needed: {classification.get('needs_satellite_data')}")
            logger.info(f"   Vision analysis needed: {classification.get('needs_vision_analysis')}")
            logger.info(f"   Contextual info needed: {classification.get('needs_contextual_info')}")
            logger.info(f"   Confidence: {classification.get('confidence', 0)}")
            logger.info(f"   Reasoning: {classification.get('reasoning', 'N/A')}")
            
            return classification
                
        except json.JSONDecodeError as e:
            logger.error(f"❌ Unified intent classifier JSON parsing failed: {e}")
            logger.error(f"Raw content: {content[:500]}")
            # Fallback to old method
            return await self.classify_query_intent_fallback(query, conversation_id)
        except Exception as e:
            logger.error(f"❌ Unified intent classifier failed: {e}", exc_info=True)
            # Fallback to old method
            return await self.classify_query_intent_fallback(query, conversation_id)
    
    async def classify_query_intent_fallback(self, query: str, conversation_id: str = None) -> Dict[str, Any]:
        """
        Fallback intent classifier when unified method fails.
        
        Uses simpler classification without module detection.
        """
        try:
            # Get conversation context if available
            context_info = ""
            if conversation_id:
                context = self.get_conversation_context(conversation_id)
                recent_history = self.get_recent_chat_history(conversation_id)
                
                if recent_history:
                    context_info = f"""
**CONVERSATION CONTEXT:**
Recent chat history:
{recent_history}

Current location focus: {context.get('last_location', 'None')}
Data currently displayed: {'Yes' if context.get('has_rendered_map') else 'No'}
"""

            prompt = f"""Classify this Earth observation query considering the conversation context:

**map_only_request**: User wants ONLY geospatial data displayed on map (NO analysis, pure visualization)
- Examples: "Show me Seattle", "Satellite images of Tokyo", "Display imagery of Paris"
- Also includes follow-up questions like: "Show me more recent data", "What about the area to the north?"

**chat_only_request**: User wants information/analysis WITHOUT any map rendering
- Examples: "How do hurricanes form?", "What causes wildfires?", "Explain climate change impacts"
- Examples: "Quantify the impact of Hurricane Sandy on NYC" (historical analysis, no map needed)
- Also includes follow-up questions like: "What does this mean?", "Why is that happening?", "Tell me more"

**hybrid_request**: User wants BOTH map display AND analytical chat response
- Examples: "Show wildfire damage and explain causes", "Display flood extent and analyze impact"
- Examples: "Show me NYC after Hurricane Sandy and explain what happened"
- GEOINT queries: ANY terrain analysis, mobility assessment, damage evaluation with map

{context_info}

Return only: map_only_request, chat_only_request, or hybrid_request

Query: "{query}"
"""
            
            # Use Semantic Kernel for classification
            result = await self.kernel.invoke_prompt(
                prompt=prompt,
                function_name="classify_query",
                plugin_name="classification"
            )
            
            intent = self._extract_clean_content_from_sk_result(result).strip().lower()
            logger.info(f"🤖 GPT classified query '{query}' as: {intent}")
            
            # Return in expected format with auto-detected modules
            if intent == 'map_only_request':
                classification_result = {
                    "intent_type": "map_only_request",
                    "needs_satellite_data": True,
                    "needs_contextual_info": False,
                    "modules_required": [{"name": "map_display", "priority": 10, "config": {}}],
                    "confidence": 0.95,
                    "query": query
                }
            elif intent == 'chat_only_request':
                classification_result = {
                    "intent_type": "chat_only_request",
                    "needs_satellite_data": False,
                    "needs_contextual_info": True,
                    "modules_required": [],
                    "confidence": 0.95,
                    "query": query
                }
            else:  # hybrid_request
                classification_result = {
                    "intent_type": "hybrid_request",
                    "needs_satellite_data": True,
                    "needs_contextual_info": True,
                    "modules_required": [{"name": "map_display", "priority": 10, "config": {}}],
                    "confidence": 0.90,
                    "query": query
                }
            
            logger.info(f"🎯 Fallback classification result: {classification_result}")
            return classification_result
                
        except Exception as e:
            logger.error(f"❌ Fallback classification failed: {e}")
            # Default to hybrid since most disaster/impact queries need both map and context
            return {
                "intent_type": "hybrid",
                "needs_satellite_data": True,
                "needs_contextual_info": True,
                "modules_required": [{"name": "map_display", "priority": 10, "config": {}}],
                "confidence": 0.5,
                "query": query,
                "fallback_reason": "GPT classification failed, defaulting to hybrid"
            }

    async def classify_query_intent_old_complex(self, query: str, conversation_id: str = None) -> Dict[str, Any]:
        """OLD COMPLEX METHOD - Classify query to determine if it needs STAC data search or contextual Earth science analysis"""
        
        logger.debug(f"🚀 QUERY CLASSIFICATION: Starting for '{query}' (conversation: {conversation_id})")
        
        # 🧠 CONVERSATION CONTEXT ANALYSIS
        context = None
        is_first_query = True
        is_follow_up = False
        
        if conversation_id:
            context = self.get_conversation_context(conversation_id)
            is_first_query = context["query_count"] == 0
            is_follow_up = self.is_follow_up_query(conversation_id, query)
            
            logger.info(f"🧠 Conversation context: first_query={is_first_query}, follow_up={is_follow_up}, map_rendered={context.get('has_rendered_map', False)}")
        
        # 🎯 ENHANCED CLASSIFICATION LOGIC
        
        # First query: Default to geospatial_data_search with contextual info
        if is_first_query:
            logger.info("🗺️ FIRST QUERY: Defaulting to geospatial_data_search with contextual analysis")
            return {
                "intent_type": "hybrid",  # Show map AND provide context for first queries
                "needs_satellite_data": True,
                "needs_contextual_info": True,
                "location_focus": self._extract_location_from_query(query),
                "temporal_focus": None,
                "disaster_or_event": None,
                "confidence": 0.95,
                "reasoning": "First query in conversation - showing map with contextual analysis"
            }
        
        # Follow-up query: Pure contextual analysis (no new STAC search)
        if is_follow_up:
            logger.info("💭 FOLLOW-UP QUERY: Pure contextual analysis, no new map rendering")
            return {
                "intent_type": "contextual_analysis",
                "needs_satellite_data": False,  # Reuse existing map data
                "needs_contextual_info": True,
                "location_focus": context.get("last_location"),
                "temporal_focus": None,
                "disaster_or_event": None,
                "confidence": 0.90,
                "reasoning": "Follow-up query - contextual analysis only"
            }
        
        # Ensure kernel is initialized
        await self._ensure_kernel_initialized()
        
        if not self._kernel_initialized or self.kernel is None:
            logger.warning("Semantic Kernel not available, defaulting to hybrid")
            return {
                "intent_type": "hybrid",
                "needs_satellite_data": True,
                "needs_contextual_info": True,
                "confidence": 0.5,
                "fallback_reason": "Semantic Kernel not available"
            }
        
        try:
            # Create classification prompt
            classification_prompt = """
            You are an Earth science query classifier. Analyze the query and determine the appropriate response type for an Earth observation system that displays satellite data on maps.

            Return ONLY a valid JSON object with this exact structure:
            {
                "intent_type": "map_only_request|chat_only_request|hybrid_request",
                "needs_satellite_data": true/false,
                "needs_contextual_info": true/false,
                "response_style": "brief_data_specs|detailed_analysis|hybrid",
                "location_focus": "specific_location_name or null",
                "temporal_focus": "specific_time_period or null", 
                "disaster_or_event": "disaster/event_name or null",
                "confidence": 0.0-1.0
            }
            
            Classification Rules:

            **MAP_ONLY_REQUEST** (Brief responses about data being displayed):
            - User wants to SEE, VIEW, DISPLAY, or SHOW satellite data on a map
            - Simple requests for visualization without asking for analysis or impacts
            - Response should be 1-2 sentences describing the data specifications
            - Examples: "show me satellite images of Seattle", "display Landsat data for California", "view elevation data", "find fire detection data", "get MODIS imagery"
            - Keywords: "show", "display", "view", "find", "get", "satellite", "images", "data", "map", "elevation", "climate", "fire", "vegetation"

            **CHAT_ONLY_REQUEST** (Detailed analysis without map data):
            - Questions about HOW, WHY, WHAT regarding impacts, effects, science, or analysis
            - Requests for explanations, interpretations, or educational content
            - NO need for new satellite data visualization
            - Response should be 1-3 paragraphs with bullet points for key findings
            - Examples: "How do hurricanes form?", "What causes wildfire spread?", "Explain earthquake impacts", "Why did the disaster occur?"

            **HYBRID_REQUEST** (Both map data AND analysis):
            - Requests that want BOTH visualization AND analysis/explanation
            - User asks to see data AND understand impacts/context
            - Response should start with brief data specs, then detailed analysis
            - Examples: "show satellite images of Hurricane Katrina and explain the impact", "display fire data and analyze the damage", "view Seattle data and explain urban development"
            - Look for: "show...and explain", "display...and tell me", "find...and analyze"

            Query to classify: "{{$query}}"
            """
            
            # Create prompt configuration for SK 1.36.2
            prompt_config = PromptTemplateConfig(
                template=classification_prompt,
                name="classify_query",
                description="Classify user query for Earth Copilot",
                template_format="semantic-kernel",
                input_variables=[
                    InputVariable(name="query", description="The user's query to classify")
                ]
            )
            
            # Execute classification using SK 1.36.2 invoke_prompt
            arguments = KernelArguments(query=query)
            result = await asyncio.wait_for(
                self.kernel.invoke_prompt(
                    prompt=classification_prompt,
                    function_name="classify_query",
                    plugin_name="semantic_translator",
                    arguments=arguments,
                    prompt_template_config=prompt_config
                ),
                timeout=30.0
            )
            
            # Parse the JSON response
            content = str(result.value) if hasattr(result, 'value') else str(result)
            content = content.strip()
            
            # CRITICAL FIX: If result is wrapped in ChatMessageContent/TextContent, extract the actual text
            if content.startswith('[ChatMessageContent') or content.startswith('[TextContent'):
                import re
                text_match = re.search(r"text='([^']+)'", content) or re.search(r'text="([^"]+)"', content)
                if text_match:
                    content = text_match.group(1)
            
            # Clean up the response to extract JSON
            if '```json' in content:
                content = content.split('```json')[1].split('```')[0]
            elif '```' in content:
                content = content.split('```')[1].split('```')[0]
            
            classification = json.loads(content)
            
            # Validate required fields - default to hybrid if incomplete
            required_fields = ['intent_type', 'needs_satellite_data', 'needs_contextual_info', 'confidence']
            for field in required_fields:
                if field not in classification:
                    logger.warning(f"Missing field {field} in classification, defaulting to hybrid")
                    return {
                        "intent_type": "hybrid",
                        "needs_satellite_data": True,
                        "needs_contextual_info": True,
                        "confidence": 0.5,
                        "fallback_reason": f"Missing field: {field}"
                    }
            
            logger.info(f"Query classified as: {classification['intent_type']} (confidence: {classification['confidence']})")
            return classification
            
        except Exception as e:
            logger.error(f"Query classification failed: {e}, defaulting to hybrid")
            return {
                "intent_type": "hybrid",
                "needs_satellite_data": True,
                "needs_contextual_info": True,
                "confidence": 0.5,
                "fallback_reason": f"Classification failed: {str(e)}"
            }
    

        
    async def _ensure_kernel_initialized(self):
        """Lazy initialization of the Semantic Kernel with proper error handling"""
        logger.info("� _ensure_kernel_initialized() called")
        logger.info(f"   Current state: _kernel_initialized={self._kernel_initialized}")
        
        if self._kernel_initialized:
            logger.info(f"   ✅ Kernel already initialized, returning")
            return
            
        try:
            logger.info(f"   🔄 Starting kernel initialization...")
            logger.info(f"   Azure OpenAI Endpoint: {self.azure_openai_endpoint}")
            logger.info(f"   Model Name: {self.model_name}")
            logger.info(f"   API Key present: {bool(self.azure_openai_api_key)}")
            logger.info(f"   API Key length: {len(self.azure_openai_api_key) if self.azure_openai_api_key else 0} chars")
            
            self.kernel = Kernel()
            logger.info(f"   ✅ Kernel object created")
            
            # Add Azure OpenAI service with optimal GPT-5 configuration for SK 1.37.0+
            # Use stable API version that works well with GPT-5
            base_url = f"{self.azure_openai_endpoint}/openai" if not self.azure_openai_endpoint.endswith('/openai') else self.azure_openai_endpoint
            logger.info(f"   Base URL: {base_url}")
            
            azure_chat_service = AzureChatCompletion(
                deployment_name=self.model_name,
                api_key=self.azure_openai_api_key,
                base_url=base_url,
                api_version="2024-10-21",  # Stable API version with full GPT-5 support
                service_id="chat-completion"  # Explicitly set service ID
            )
            logger.info(f"   ✅ AzureChatCompletion service created")
            
            self.kernel.add_service(azure_chat_service)
            logger.info(f"   ✅ Service added to kernel")
            
            self._kernel_initialized = True
            logger.info(f"   ✅ Kernel initialization SUCCESSFUL!")
            logger.info(f"   ✓ Semantic Kernel initialized with {self.model_name} at {base_url} (API v2024-10-21)")
            
        except Exception as e:
            logger.error(f"   ❌ Kernel initialization FAILED!")
            logger.error(f"   Exception type: {type(e).__name__}")
            logger.error(f"   Exception message: {str(e)}")
            logger.error(f"   Traceback:")
            logger.error(traceback.format_exc())
            # Raise error - require proper Azure OpenAI connection
            self.kernel = None
            self._kernel_initialized = False
    
    async def test_connection(self) -> bool:
        """Test connection to Azure OpenAI model for health check"""
        try:
            logger.info(f"🔍 Testing Azure OpenAI {self.model_name} connectivity...")
            await self._ensure_kernel_initialized()
            
            if not self.kernel:
                return False
            
            # Create a simple test prompt
            test_prompt = "Test connection - respond with 'OK'"
            
            # Create chat history for testing
            from semantic_kernel.contents import ChatHistory
            chat_history = ChatHistory()
            chat_history.add_user_message(test_prompt)
            
            # Get the chat completion service
            chat_completion = self.kernel.get_service("chat-completion")
            
            # Test with minimal settings and timeout
            from semantic_kernel.connectors.ai.open_ai import AzureChatPromptExecutionSettings
            execution_settings = AzureChatPromptExecutionSettings(
                temperature=1.0,  # GPT-5 requires default temperature=1.0
                max_completion_tokens=200,  # Increased for GPT-5 reasoning models (reasoning tokens count toward limit)
                service_id="chat-completion"
            )
            
            # Try to get a response with timeout
            response = await asyncio.wait_for(
                chat_completion.get_chat_message_content(
                    chat_history=chat_history,
                    settings=execution_settings,
                    kernel=self.kernel
                ),
                timeout=30.0  # 30 second timeout for GPT models
            )
            
            # Check if we got a valid response
            # GPT-5 reasoning models may return response with usage data but empty content
            # This is normal - the model is working, just using reasoning tokens internally
            if response:
                if response.content:
                    logger.info(f"✅ Azure OpenAI {self.model_name} connectivity test successful: {response.content[:50]}...")
                else:
                    logger.info(f"✅ Azure OpenAI {self.model_name} connectivity test successful (reasoning model response)")
                return True
            else:
                logger.warning("⚠️ Azure OpenAI responded but with no response object")
                return False
                
        except Exception as e:
            logger.error(f"❌ Azure OpenAI connectivity test failed: {e}")
            logger.error(f"❌ Full traceback: {traceback.format_exc()}")
            return False
                
        except asyncio.TimeoutError:
            logger.error("❌ Azure OpenAI connectivity test timed out")
            return False
        except Exception as e:
            logger.error(f"❌ Azure OpenAI connectivity test failed: {e}")
            return False
    
    # ========================================================================
    # COLLECTION MAPPING AGENT: Intelligently select relevant STAC collections
    # ========================================================================
    
    async def collection_mapping_agent(self, query: str) -> List[str]:
        """
        🤖 COLLECTION MAPPING AGENT: Use GPT to intelligently select relevant collections
        
        This agent maps user queries to appropriate STAC collections by:
        - Understanding query intent (elevation, fire, optical imagery, etc.)
        - Matching to collection capabilities from COLLECTION_PROFILES
        - Handling both explicit mentions ("Landsat") and implicit ("satellite images")
        
        Returns:
            List of collection IDs (e.g., ["cop-dem-glo-30", "sentinel-2-l2a"])
        """
        
        logger.info("=" * 80)
        logger.info(f"🤖 AGENT 1 START: Collection Mapping for query: '{query}'")
        logger.info("=" * 80)
        
        await self._ensure_kernel_initialized()
        
        logger.info(f"🔍 AGENT 1 DEBUG: Kernel initialized? {self._kernel_initialized}")
        logger.info(f"🔍 AGENT 1 DEBUG: Kernel object exists? {self.kernel is not None}")
        
        if not self._kernel_initialized or self.kernel is None:
            logger.warning("⚠️ AGENT 1: Kernel not initialized - falling back to keyword-based selection")
            fallback_result = self._select_collections_fallback(query)
            logger.info(f"🔄 AGENT 1 FALLBACK: Returned {len(fallback_result)} collections: {fallback_result}")
            return fallback_result
        
        try:
            logger.info("🔧 AGENT 1: Building collection catalog...")
            # Build comprehensive collection catalog from COLLECTION_PROFILES
            collection_catalog = self._build_comprehensive_collection_catalog()
            logger.info(f"✅ AGENT 1: Collection catalog built ({len(collection_catalog)} characters)")
            
            prompt = f"""You are a satellite data expert. Analyze the user's query and select the most relevant STAC collections.

{collection_catalog}

USER QUERY: "{query}"

==============================================================================
CRITICAL: KEYWORD MATCHING RULES (Check these FIRST before anything else!)
==============================================================================

🔴 RULE #1 - SAR/RADAR DETECTION (HIGHEST PRIORITY):
If query contains ANY of these words: "SAR", "radar", "Sentinel-1", "Sentinel 1", "synthetic aperture"
   → MUST return ["sentinel-1-grd"]
   
   WHY: SAR is a specific radar technology. Users asking for SAR NEVER want optical imagery.
   
   Examples:
   - "Get SAR data for Seattle" → ["sentinel-1-grd"]
   - "Show me radar imagery" → ["sentinel-1-grd"]  
   - "SAR flood detection" → ["sentinel-1-grd"]
   - "low cloud SAR data" → ["sentinel-1-grd"] (even if mentions cloud, SAR doesn't use cloud filters)

🟡 RULE #2 - OTHER PLATFORM NAMES:
   - "HLS" or "Harmonized Landsat Sentinel" → ["hls2-l30", "hls2-s30"]
   - "Landsat" → ["landsat-c2-l2"]
   - "Sentinel-2" or "Sentinel 2" → ["sentinel-2-l2a"]
   - "MODIS" → appropriate MODIS collection based on use case
   - "NAIP" → ["naip"]
   - "Copernicus DEM" or "COP-DEM" → ["cop-dem-glo-30"]

🟢 RULE #3 - USE CASE MATCHING (Only if no platform name in query):
   - "elevation", "DEM", "terrain" → ["cop-dem-glo-30", "nasadem"]
   - "fire", "wildfire", "thermal" → ["modis-14A1-061", "modis-MCD64A1-061"]
   - "flood", "water", "inundation" → ["sentinel-1-grd", "sentinel-2-l2a"] (SAR + optical)
   - "vegetation", "NDVI", "agriculture" → ["modis-13Q1-061", "sentinel-2-l2a"]
   - "satellite imagery" (generic) → ["sentinel-2-l2a", "landsat-c2-l2"]

==============================================================================
STEP-BY-STEP PROCESS:
==============================================================================
1. Check if query contains "SAR", "radar", "Sentinel-1" → If YES, return ["sentinel-1-grd"]
2. Check if query contains other platform names (HLS, Landsat, Sentinel-2, etc.) → If YES, return those
3. If no platform names, match use case keywords → Return appropriate collections
4. Default for generic "satellite imagery" → ["sentinel-2-l2a", "landsat-c2-l2"]

==============================================================================
MORE EXAMPLES:
==============================================================================
"Get SAR radar data for Seattle" → ["sentinel-1-grd"]
"Show me Sentinel-1 imagery of Alaska" → ["sentinel-1-grd"]
"I need radar data" → ["sentinel-1-grd"]
"SAR flood detection" → ["sentinel-1-grd"]
"Satellite imagery of Boston" → ["sentinel-2-l2a", "landsat-c2-l2"]
"HLS data for California" → ["hls2-l30", "hls2-s30"]
"Elevation data for Colorado" → ["cop-dem-glo-30"]
"Wildfire thermal analysis" → ["modis-14A1-061"]

==============================================================================
IMPORTANT CONSTRAINTS:
==============================================================================
- Return 1-3 collections maximum (don't overselect)
- Use exact collection IDs from AVAILABLE COLLECTIONS above
- SAR/radar queries ALWAYS get sentinel-1-grd, NEVER optical collections

Return ONLY a JSON array of collection IDs. No explanations.
Format: ["collection-id-1", "collection-id-2"]"""

            logger.info("🔧 AGENT 1: Creating execution settings...")
            # Execute with Semantic Kernel
            from semantic_kernel.functions.kernel_arguments import KernelArguments
            from semantic_kernel.connectors.ai.open_ai.prompt_execution_settings.azure_chat_prompt_execution_settings import AzureChatPromptExecutionSettings
            
            execution_settings = AzureChatPromptExecutionSettings(
                service_id="chat-completion",
                temperature=1.0,  # GPT-5 requires default temperature=1.0
                max_completion_tokens=500
            )
            logger.info(f"✅ AGENT 1: Execution settings created (temp=1.0, max_completion_tokens=500)")
            
            arguments = KernelArguments(settings=execution_settings)
            logger.info(f"✅ AGENT 1: KernelArguments created")
            
            logger.info(f"🚀 AGENT 1: Calling kernel.invoke_prompt() with query: '{query[:100]}...'")
            logger.info(f"🚀 AGENT 1: Prompt length: {len(prompt)} characters")
            
            result = await asyncio.wait_for(
                self.kernel.invoke_prompt(
                    prompt=prompt,
                    function_name="select_collections",
                    plugin_name="collection_selector",
                    arguments=arguments
                ),
                timeout=30.0
            )
            
            logger.info(f"✅ AGENT 1: kernel.invoke_prompt() completed successfully")
            logger.info(f"🔍 AGENT 1: Result type: {type(result)}")
            logger.info(f"🔍 AGENT 1: Result has 'value' attr? {hasattr(result, 'value')}")
            
            # Extract result - handle Semantic Kernel response objects properly
            if hasattr(result, 'value'):
                content = str(result.value)
                logger.info(f"📄 AGENT 1: Extracted content from result.value")
            else:
                content = str(result)
                logger.info(f"📄 AGENT 1: Extracted content from str(result)")
            
            # CRITICAL FIX: If result is wrapped in ChatMessageContent/TextContent, extract the actual text
            # This happens when SK returns a list of content objects instead of plain text
            if content.startswith('[ChatMessageContent') or content.startswith('[TextContent'):
                logger.info(f"🔧 AGENT 1: Detected wrapped SK content, extracting text...")
                # Extract text from the content object(s)
                # Pattern: text='["collection-id"]' or text="[\"collection-id\"]"
                import re
                text_match = re.search(r"text='([^']+)'", content) or re.search(r'text="([^"]+)"', content)
                if text_match:
                    content = text_match.group(1)
                    logger.info(f"✅ AGENT 1: Extracted text content: {content[:100]}")
                else:
                    logger.error(f"❌ AGENT 1: Failed to extract text from wrapped content")
                    logger.error(f"   Content preview: {content[:200]}")
                    raise ValueError(f"Could not extract text from SK response")
            
            logger.info(f"📄 AGENT 1: Raw GPT Response (first 500 chars):")
            logger.info(f"   {content[:500]}")
            logger.info(f"📄 AGENT 1: Raw GPT Response (last 100 chars):")
            logger.info(f"   ...{content[-100:]}")
            logger.info(f"📄 AGENT 1: Total response length: {len(content)} characters")
            
            logger.info(f"🔧 AGENT 1: Attempting to parse JSON...")
            # Parse JSON response
            try:
                collections = json.loads(content.strip())
                logger.info(f"✅ AGENT 1: JSON parsed successfully")
            except json.JSONDecodeError as e:
                logger.error(f"❌ AGENT 1: JSON parse error: {e}")
                logger.error(f"❌ AGENT 1: Failed content: {content}")
                raise ValueError(f"GPT returned invalid JSON: {e}")
            
            logger.info(f"🔍 AGENT 1: Parsed result type: {type(collections)}")
            logger.info(f"🔍 AGENT 1: Parsed result value: {collections}")
            
            if not isinstance(collections, list):
                logger.error(f"❌ AGENT 1: Result is not a list! Type: {type(collections)}")
                raise ValueError("Agent returned non-list response")
            
            logger.info(f"✅ AGENT 1: Result is a valid list with {len(collections)} items")
            logger.info(f"🔍 AGENT 1: Collections before validation: {collections}")
            
            # Validate collections against known collections
            KNOWN_COLLECTIONS = {
                "sentinel-2-l2a", "sentinel-1-grd", "sentinel-1-rtc",
                "landsat-c2-l2", "hls2-l30", "hls2-s30",  # ✅ Correct IDs from collection_profiles.py
                "cop-dem-glo-30", "cop-dem-glo-90", "nasadem",
                "modis-14A1-061", "modis-14A2-061", "modis-MCD64A1-061",
                "modis-13Q1-061", "modis-13A1-061", "modis-09A1-061",
                "modis-09Q1-061", "modis-10A1-061", "modis-10A2-061",
                "modis-11A1-061", "modis-15A2H-061", "modis-17A2H-061", "modis-17A3HGF-061",
                "naip", "3dep-seamless", "alos-dem", "alos-palsar-mosaic",
                "aster-l1t", "era5-pds", "goes-cmi", "goes-glm",
                "ms-buildings", "noaa-climate-normals-gridded",  # ✅ Fixed: ms-buildings (was microsoft-buildings)
                "noaa-climate-normals-netcdf", "us-census"
                # Removed: mur-sst, worldpop (no longer in STAC API)
            }
            
            # If COLLECTION_PROFILES is loaded, use it as the source of truth
            if PROFILES_AVAILABLE and COLLECTION_PROFILES:
                KNOWN_COLLECTIONS = set(COLLECTION_PROFILES.keys())
                logger.info(f"🔍 AGENT 1: Using COLLECTION_PROFILES as source of truth ({len(KNOWN_COLLECTIONS)} collections)")
            else:
                logger.info(f"🔍 AGENT 1: Using hardcoded KNOWN_COLLECTIONS ({len(KNOWN_COLLECTIONS)} collections)")
            
            valid_collections = [c for c in collections if c in KNOWN_COLLECTIONS]
            invalid_collections = [c for c in collections if c not in KNOWN_COLLECTIONS]
            
            if invalid_collections:
                logger.warning(f"⚠️ AGENT 1: Found {len(invalid_collections)} invalid collections: {invalid_collections}")
            
            if not valid_collections:
                logger.error(f"❌ AGENT 1: No valid collections found!")
                logger.error(f"   GPT returned: {collections}")
                logger.error(f"   Valid options are: {sorted(KNOWN_COLLECTIONS)[:20]}... ({len(KNOWN_COLLECTIONS)} total)")
                logger.info(f"🔄 AGENT 1: Falling back to keyword-based selection")
                fallback_result = self._select_collections_fallback(query)
                logger.info(f"✅ AGENT 1 FALLBACK: Returned {len(fallback_result)} collections: {fallback_result}")
                return fallback_result
            
            logger.info(f"✅ AGENT 1 SUCCESS: Selected {len(valid_collections)} valid collections: {valid_collections}")
            logger.info("=" * 80)
            return valid_collections
            
        except Exception as e:
            logger.error(f"❌ AGENT 1 EXCEPTION: {type(e).__name__}: {str(e)}")
            logger.error(f"❌ AGENT 1 TRACEBACK:")
            logger.error(traceback.format_exc())
            logger.info(f"� AGENT 1: Falling back to keyword-based selection")
            fallback_result = self._select_collections_fallback(query)
            logger.info(f"✅ AGENT 1 FALLBACK: Returned {len(fallback_result)} collections: {fallback_result}")
            logger.info("=" * 80)
            return fallback_result
    
    def _build_comprehensive_collection_catalog(self) -> str:
        """Build comprehensive collection catalog from COLLECTION_PROFILES with rich context"""
        
        if not PROFILES_AVAILABLE or not COLLECTION_PROFILES:
            logger.warning("⚠️ COLLECTION_PROFILES not available, using hardcoded catalog")
            # Fallback to hardcoded catalog if profiles not loaded
            return self._get_hardcoded_collection_catalog()
        
        catalog = ["AVAILABLE COLLECTIONS (with capabilities and use cases):"]
        catalog.append("=" * 80)
        
        # Group collections by category for better organization
        categories = {}
        for collection_id, profile in COLLECTION_PROFILES.items():
            category = profile.get("category", "other")
            if category not in categories:
                categories[category] = []
            categories[category].append((collection_id, profile))
        
        # Process each category
        category_order = ["optical", "elevation", "radar", "agriculture", "weather", "other"]
        
        for category in category_order:
            if category not in categories:
                continue
            
            catalog.append(f"\n{category.upper()} COLLECTIONS:")
            catalog.append("-" * 80)
            
            for collection_id, profile in sorted(categories[category], key=lambda x: x[0]):
                name = profile.get("name", collection_id)
                resolution = profile.get("resolution", "varies")
                platform = profile.get("platform", "")
                usage = profile.get("usage", "")
                
                # Get query rules and capabilities
                query_rules = profile.get("query_rules", {})
                description = query_rules.get("description", "")
                agent_guidance = query_rules.get("agent_guidance", "")
                capabilities = query_rules.get("capabilities", {})
                
                # Build capability tags
                caps = []
                if capabilities.get("cloud_filtering"):
                    caps.append("cloud-filtering")
                if capabilities.get("temporal_filtering"):
                    caps.append("time-series")
                if capabilities.get("static_data"):
                    caps.append("static/DEM")
                if capabilities.get("composite_data"):
                    caps.append("composite")
                
                caps_str = f"[{', '.join(caps)}]" if caps else ""
                
                # Build collection entry
                entry = f"- {collection_id}: {name}"
                if platform:
                    entry += f" ({platform})"
                entry += f" - {resolution}"
                if caps_str:
                    entry += f" {caps_str}"
                if description:
                    entry += f"\n  Description: {description}"
                if usage:
                    entry += f"\n  Use cases: {usage}"
                if agent_guidance:
                    entry += f"\n  Note: {agent_guidance}"
                
                catalog.append(entry)
        
        return "\n".join(catalog)
    
    def _get_hardcoded_collection_catalog(self) -> str:
        """Fallback hardcoded collection catalog when COLLECTION_PROFILES not available"""
        return """AVAILABLE COLLECTIONS (with capabilities and use cases):
================================================================================

OPTICAL COLLECTIONS:
--------------------------------------------------------------------------------
- sentinel-2-l2a: Sentinel-2 optical (10-60m) - land cover, vegetation, general imagery
- landsat-c2-l2: Landsat optical (30m) - historical archive, thermal bands, change detection
- hls2-l30: Harmonized Landsat-Sentinel L30 (30m) - analysis-ready, consistent processing
- hls2-s30: Harmonized Landsat-Sentinel S30 (30m) - analysis-ready, consistent processing  
- naip: NAIP aerial imagery (0.6-1m) - very high resolution, US-only

ELEVATION COLLECTIONS:
--------------------------------------------------------------------------------
- cop-dem-glo-30: Copernicus DEM (30m) - global elevation, terrain analysis
- cop-dem-glo-90: Copernicus DEM (90m) - global elevation, broad terrain
- nasadem: NASA DEM (30m) - high-quality global elevation

RADAR COLLECTIONS:
--------------------------------------------------------------------------------
- sentinel-1-grd: Sentinel-1 SAR (cloud-penetrating) - flood detection, all-weather
- sentinel-1-rtc: Sentinel-1 SAR terrain-corrected - enhanced radar

AGRICULTURE/VEGETATION COLLECTIONS:
--------------------------------------------------------------------------------
- modis-13Q1-061: MODIS vegetation indices - NDVI/EVI for crop monitoring
- modis-13A1-061: MODIS vegetation 16-day composite - agriculture monitoring
- modis-09A1-061: MODIS surface reflectance 8-day composite

FIRE/THERMAL COLLECTIONS:
--------------------------------------------------------------------------------
- modis-14A1-061: MODIS thermal anomalies daily - active fire detection
- modis-14A2-061: MODIS thermal 8-day composite - fire detection
- modis-MCD64A1-061: MODIS burned area - wildfire mapping

WEATHER COLLECTIONS:
--------------------------------------------------------------------------------
- era5-pds: ERA5 reanalysis - comprehensive weather patterns"""
    
    def _build_collection_catalog_for_agent(self) -> str:
        """Build a concise catalog of collections for Collection Mapping Agent"""
        
        if not PROFILES_AVAILABLE:
            return "Limited collection information available"
        
        catalog_lines = []
        for collection_id, profile in COLLECTION_PROFILES.items():
            name = profile.get("name", collection_id)
            category = profile.get("category", "unknown")
            resolution = profile.get("resolution", "")
            
            # Get key capabilities
            rules = profile.get("query_rules", {})
            caps = rules.get("capabilities", {})
            
            caps_text = ""
            if caps.get("static_data"):
                caps_text = "(Static DEM/Elevation)"
            elif caps.get("composite_data"):
                caps_text = "(Composite/Aggregated)"
            elif category == "optical":
                caps_text = "(Optical Imagery)"
            elif category == "radar":
                caps_text = "(SAR/Radar)"
            elif "fire" in collection_id or "thermal" in collection_id:
                caps_text = "(Fire/Thermal Detection)"
            
            catalog_lines.append(f"- {collection_id}: {name} {caps_text} [{category}, {resolution}]")
        
        return "\n".join(catalog_lines[:50])  # Limit to 50 collections to fit in prompt
    
    def _select_collections_fallback(self, query: str) -> List[str]:
        """Fallback keyword-based collection selection"""
        
        query_lower = query.lower()
        
        # CRITICAL: Check for SAR/radar FIRST (highest priority)
        if any(keyword in query_lower for keyword in ["sar", "radar", "sentinel-1", "sentinel 1", "synthetic aperture"]):
            logger.info(f"🛰️ SAR/RADAR DETECTED in query: {query_lower}")
            return ["sentinel-1-grd"]
        
        # Explicit platform mentions (exact matches)
        if any(keyword in query_lower for keyword in ["hls", "harmonized"]):
            logger.info(f"🛰️ HLS PLATFORM DETECTED in query: {query_lower}")
            return ["hls2-l30", "hls2-s30"]  # ✅ Correct IDs from collection_profiles.py
        if "landsat" in query_lower:
            return ["landsat-c2-l2"]
        if "sentinel-2" in query_lower or "sentinel 2" in query_lower:
            return ["sentinel-2-l2a"]
        if "naip" in query_lower:
            return ["naip"]
        if "modis" in query_lower:
            if any(w in query_lower for w in ["fire", "thermal", "burn", "hotspot"]):
                return ["modis-14A1-061", "modis-MCD64A1-061"]
            if any(w in query_lower for w in ["vegetation", "ndvi", "evi", "crop", "agriculture"]):
                return ["modis-13Q1-061"]
            return ["modis-09A1-061"]
        
        # Topic-based selection (use cases)
        if any(w in query_lower for w in ["elevation", "dem", "terrain", "topography", "slope", "altitude"]):
            return ["cop-dem-glo-30", "nasadem"]
        if any(w in query_lower for w in ["fire", "wildfire", "thermal", "burn", "hotspot"]):
            return ["modis-14A1-061", "modis-MCD64A1-061"]
        if any(w in query_lower for w in ["snow", "snow cover", "ice", "glacier"]):
            return ["sentinel-2-l2a", "landsat-c2-l2"]  # Optical for snow detection
        if any(w in query_lower for w in ["flood", "water", "inundation"]):
            return ["sentinel-1-grd", "sentinel-2-l2a"]  # SAR + optical
        if any(w in query_lower for w in ["vegetation", "ndvi", "crop", "agriculture", "forest"]):
            return ["modis-13Q1-061", "sentinel-2-l2a"]
        if any(w in query_lower for w in ["land cover", "land use", "classification"]):
            return ["esa-worldcover", "sentinel-2-l2a"]
        if any(w in query_lower for w in ["weather", "temperature", "precipitation", "climate"]):
            return ["daymet-daily-na", "era5-pds"]
        
        # Default to versatile optical
        return ["sentinel-2-l2a", "landsat-c2-l2"]
    
    # ========================================================================
    # AGENT 2: STAC QUERY BUILDER
    # ========================================================================
    
    async def build_stac_query_agent(self, query: str, collections: List[str]) -> Dict[str, Any]:
        """
        🤖 AGENT 2: Build complete STAC query using two-step process
        
        Step 1: Extract location_name from query (if present)
        Step 2: Build STAC query parameters (datetime, filters, etc.)
        Step 3: Resolve location_name to bbox coordinates
        Step 4: Combine into final STAC query
        
        Returns:
            Complete STAC query dict ready for API
        """
        
        await self._ensure_kernel_initialized()
        
        print(f"🚨 DEBUG: After _ensure_kernel_initialized() - _kernel_initialized={self._kernel_initialized}, kernel={self.kernel is not None}")
        
        if not self._kernel_initialized or self.kernel is None:
            print(f"❌🚨 DEBUG: KERNEL NOT INITIALIZED! Using fallback basic query builder")
            print(f"   _kernel_initialized: {self._kernel_initialized}")
            print(f"   self.kernel: {self.kernel}")
            logger.warning("⚠️ Kernel not initialized - using basic query builder")
            return await self._build_stac_query_basic(query, collections)
        
        try:
            print(f"🚨🚨🚨 DEBUG: AGENT 2 STARTING - Query: '{query}', Collections: {collections}")
            logger.info("=" * 100)
            logger.info(f"🤖🤖🤖 AGENT 2 START: STAC Query Building Agent")
            logger.info(f"📝 Query: '{query}'")
            logger.info(f"📚 Collections: {collections}")
            logger.info(f"🔧 Collections Count: {len(collections) if collections else 0}")
            logger.info("=" * 100)
            
            # ========================================================================
            # 🚀 PERFORMANCE OPTIMIZATION: Parallel Agent Execution
            # ========================================================================
            # STEP 1-3: Run location, datetime, and cloud filtering agents IN PARALLEL
            # These agents don't depend on each other, so we can run them concurrently
            # This reduces latency from ~3 sequential calls to ~1 parallel call
            logger.info(f"🤖 AGENT 2 STEPS 1-3: Running location, datetime, and cloud agents IN PARALLEL...")
            print(f"🚀 DEBUG: AGENT 2 - Starting PARALLEL execution of 3 agents")
            
            # Run all three agents concurrently
            entities_task = self.location_extraction_agent(query)
            datetime_task = self.datetime_translation_agent(query, collections)
            cloud_task = self.cloud_filtering_agent(query, collections)
            
            # Wait for all to complete
            entities, datetime_range, cloud_filter = await asyncio.gather(
                entities_task,
                datetime_task,
                cloud_task
            )
            
            print(f"✅ DEBUG: AGENT 2 - PARALLEL execution complete")
            
            # Extract location from entities
            location = entities.get("location", {})
            location_name = location.get("name")
            
            if location_name:
                logger.info(f"📍 AGENT 2: Location extracted: '{location_name}' (type: {location.get('type')}, confidence: {location.get('confidence')})")
                print(f"✅ DEBUG: AGENT 2 STEP 1 SUCCESS - Location: '{location_name}'")
            else:
                logger.info(f"📍 AGENT 2: No location found in query")
                print(f"ℹ️ DEBUG: AGENT 2 STEP 1 - No location in query")
            
            if datetime_range:
                logger.info(f"✅ Datetime translation: {datetime_range}")
                print(f"✅ DEBUG: AGENT 2.2 SUCCESS - Datetime: {datetime_range}")
            else:
                logger.info(f"ℹ️ No datetime filter (will get most recent or use sortby)")
                print(f"ℹ️ DEBUG: AGENT 2.2 - No datetime filter")
            
            if cloud_filter:
                logger.info(f"✅ Cloud filter: {cloud_filter}")
                print(f"✅ DEBUG: AGENT 2.3 SUCCESS - Cloud filter determined")
            else:
                logger.info(f"ℹ️ No cloud filter")
                print(f"ℹ️ DEBUG: AGENT 2.3 - No cloud filtering")
            
            # STEP 4: Build STAC query parameters (PURE FUNCTION - No GPT)
            logger.info(f"🔧 UTILITY: Building STAC parameters (deterministic)")
            print(f"🔧 DEBUG: Building STAC parameters")
            stac_query = await self._build_stac_parameters(query, collections, entities, datetime_range)
            print(f"✅ DEBUG: STAC parameters built")
            
            # STEP 5: Apply cloud filter if determined by agent
            if cloud_filter:
                filter_dict = cloud_filter.get("filter", {})
                if filter_dict:
                    if "query" not in stac_query:
                        stac_query["query"] = {}
                    stac_query["query"].update(filter_dict)
                    logger.info(f"✅ Applied cloud filter: {filter_dict}")
                    print(f"✅ DEBUG: Cloud filter applied to STAC query")
            
            # STEP 6: Resolve location to bbox if present
            # STEP 6: Resolve location to bbox if present
            if location_name:
                logger.info(f"🔧 UTILITY: Resolving '{location_name}' to coordinates...")
                print(f"🔧 DEBUG: STEP 6 - Resolving location to bbox")
                bbox = await self.resolve_location_to_bbox(location_name, "region")
                
                if bbox and self._validate_bbox(bbox):
                    stac_query["bbox"] = bbox
                    stac_query["location_name"] = location_name  # Keep for reference
                    logger.info(f"✅ Resolved '{location_name}' → bbox: {bbox}")
                    print(f"✅ DEBUG: STEP 6 SUCCESS - bbox: {bbox}")
                else:
                    logger.error(f"❌ Failed to resolve '{location_name}' to coordinates")
                    logger.error(f"⚠️ Check API keys: Azure Maps, Google Maps, Mapbox")
                    print(f"❌🚨 DEBUG: STEP 6 FAILED - Could not resolve bbox")
                    raise ValueError(f"Unable to resolve location '{location_name}'. Check API keys.")
            else:
                print(f"ℹ️ DEBUG: STEP 6 SKIPPED - No location to resolve")
            
            logger.info(f"✅ AGENT 2 Complete - 3-Agent Architecture Success")
            print(f"✅ DEBUG: AGENT 2 COMPLETE")
            print(f"  - Agent 2.1 (Location): {'✅' if location_name else 'ℹ️ skipped'}")
            print(f"  - Agent 2.2 (Datetime): {'✅' if datetime_range else 'ℹ️ skipped'}")
            print(f"  - Agent 2.3 (Cloud): {'✅' if cloud_filter else 'ℹ️ skipped'}")
            print(f"  - Final STAC query: {stac_query}")
            return stac_query
            
        except Exception as e:
            print(f"❌🚨 DEBUG: AGENT 2 EXCEPTION CAUGHT!")
            print(f"❌🚨 Exception type: {type(e).__name__}")
            print(f"❌🚨 Exception message: {str(e)}")
            print(f"❌🚨 Traceback: {traceback.format_exc()}")
            logger.error(f"❌ AGENT 2 failed: {e}")
            logger.error(f"❌ Full exception details: {traceback.format_exc()}")
            logger.info("📋 Falling back to basic query builder")
            return await self._build_stac_query_basic(query, collections)
    
    async def location_extraction_agent(self, query: str) -> Dict[str, Any]:
        """
        🤖 AGENT 2.1: GPT-powered location extraction agent
        
        Extracts location entities from natural language queries.
        This agent handles:
        - City names: "Seattle", "NYC"
        - Regions: "Pacific Northwest", "Gulf Coast"  
        - States/Countries: "California", "Turkey"
        - Landmarks: "Grand Canyon", "Mount Rainier"
        - Routes: "Denver to Colorado Springs" → primary location
        - Complex: "50km around Houston" → center point
        
        NOTE: Temporal extraction is now handled by datetime_translation_agent.
        Collection selection is handled by collection_mapping_agent (Agent 1).
        
        Args:
            query: User's natural language query
            
        Returns:
            Dict with 'location' entity:
            {
                "location": {"name": "Seattle", "type": "city", "confidence": 0.9}
            }
        """
        
        logger.info("=" * 100)
        logger.info(f"🤖🤖🤖 AGENT 2.1 START: Location Extraction Agent")
        logger.info(f"📝 Query to analyze: '{query}'")
        logger.info("=" * 100)

        # Ensure kernel is initialized before use
        await self._ensure_kernel_initialized()
        
        logger.info("=" * 100)
        logger.info(f"🤖🤖🤖 AGENT 2.1 START: Location Extraction Agent")
        logger.info(f"📝 Query to analyze: '{query}'")
        logger.info("=" * 100)
        
        if not self.kernel:
            logger.error("=" * 100)
            logger.error("❌❌❌ AGENT 2.1 CRITICAL: Kernel initialization failed, cannot extract location")
            logger.error("=" * 100)
            return {"location": None}

        # CRITICAL FIX: Use f-string for direct query injection instead of template variables
        # This ensures the actual query text is sent to GPT-5, not the literal "{{$query}}" string
        entity_extraction_prompt = f"""You are an expert at extracting location information from satellite imagery queries.

Extract location information from this query and return ONLY a valid JSON object:

{{
    "location": {{
        "name": "string or null",
        "type": "city|state|country|region|landmark",
        "confidence": 0.0
    }}
}}

CRITICAL EXTRACTION RULES:
1. **ALWAYS extract country names**: Ukraine, France, Japan, India, Brazil, Canada, Australia, etc.
2. **Extract from descriptive phrases**: "Ukraine farmland" → "Ukraine", "France vineyards" → "France", "Japan coastline" → "Japan"
3. **Geographic entities take priority**: Country/state/city names override descriptive terms (farmland, forests, coastline)
4. **For routes**: "Denver to Colorado Springs" → Extract primary location "Denver" or "Colorado"
5. **For regions**: "Pacific Northwest", "Mediterranean", "Great Lakes region"
6. **For landmarks**: "Grand Canyon", "Mount Everest", "Great Barrier Reef"
7. **Confidence scores**: 0.9-1.0 for explicit names, 0.7-0.9 for implied locations, 0.0 for no location

EXAMPLES - INTERNATIONAL COUNTRIES:

Query: "Harmonized Landsat Satellite images of Ukraine farmland"
Response: {{"location": {{"name": "Ukraine", "type": "country", "confidence": 0.95}}}}

Query: "Show me France vineyards"
Response: {{"location": {{"name": "France", "type": "country", "confidence": 0.95}}}}

Query: "Satellite data for Japan coastline"
Response: {{"location": {{"name": "Japan", "type": "country", "confidence": 0.95}}}}

Query: "India agricultural regions"
Response: {{"location": {{"name": "India", "type": "country", "confidence": 0.95}}}}

Query: "Show me Turkey earthquake damage"
Response: {{"location": {{"name": "Turkey", "type": "country", "confidence": 0.9}}}}

EXAMPLES - US LOCATIONS:

Query: "Show me satellite imagery of NYC"
Response: {{"location": {{"name": "NYC", "type": "city", "confidence": 0.9}}}}

Query: "Satellite imagery of California"
Response: {{"location": {{"name": "California", "type": "state", "confidence": 0.9}}}}

Query: "Show elevation profile from Denver to Colorado Springs"
Response: {{"location": {{"name": "Denver", "type": "city", "confidence": 0.8}}}}

Query: "Recent satellite data for Seattle"
Response: {{"location": {{"name": "Seattle", "type": "city", "confidence": 0.9}}}}

EXAMPLES - NO LOCATION:

Query: "Show me imagery from last year"
Response: {{"location": {{"name": null, "type": null, "confidence": 0.0}}}}

Query to analyze: {query}

Return only the JSON object. No explanations or additional text."""

        try:
            from semantic_kernel.functions.kernel_arguments import KernelArguments
            from semantic_kernel.connectors.ai.open_ai.prompt_execution_settings.azure_chat_prompt_execution_settings import AzureChatPromptExecutionSettings
            
            # Execution settings
            execution_settings = AzureChatPromptExecutionSettings(
                service_id="chat-completion",
                temperature=1.0,  # GPT-5 requires default temperature=1.0
                max_completion_tokens=500
            )

            # Execute using simplified invoke_prompt (no template needed with f-string)
            arguments = KernelArguments(settings=execution_settings)
            
            logger.info(f"🔍 Sending location extraction prompt to GPT-5...")
            logger.info(f"🔍 Prompt preview (first 200 chars): {entity_extraction_prompt[:200]}...")
            
            result = await asyncio.wait_for(
                self.kernel.invoke_prompt(
                    prompt=entity_extraction_prompt,
                    function_name="extract_entities",
                    plugin_name="semantic_translator",
                    arguments=arguments
                ),
                timeout=20.0
            )

            # Extract and clean response from SK result (Semantic Kernel 1.37.0+)
            if hasattr(result, 'value'):
                # SK returns FunctionResult with .value attribute
                if isinstance(result.value, list) and len(result.value) > 0:
                    # List of ChatMessageContent objects
                    content = str(result.value[0].content)
                else:
                    content = str(result.value)
            elif hasattr(result, 'content'):
                # Direct ChatMessageContent object
                content = str(result.content)
            elif isinstance(result, list) and len(result) > 0:
                # List of ChatMessageContent objects returned directly
                content = str(result[0].content)
            elif hasattr(result, 'result'):
                content = str(result.result)
            else:
                content = str(result)
            
            content = content.strip()
            
            # 🔍 DEBUG: Log raw GPT-5 response
            logger.info(f"🔍 DEBUG: Raw GPT-5 response (first 500 chars): {content[:500]}")
            print(f"🔍 DEBUG: ===== RAW GPT-5 RESPONSE =====")
            print(content[:1000] if len(content) > 1000 else content)
            print(f"🔍 DEBUG: ================================")
            
            # Clean JSON markers
            if '```json' in content:
                content = content.split('```json')[1].split('```')[0].strip()
            elif '```' in content:
                content = content.split('```')[1].split('```')[0].strip()
            
            # 🔍 DEBUG: Log cleaned content before parsing
            logger.info(f"🔍 DEBUG: Cleaned content before JSON parse: {content[:500]}")
            print(f"🔍 DEBUG: Cleaned content: {content}")
            
            # Parse JSON
            entities = json.loads(content)
            
            # 🔍 DEBUG: Log parsed entities structure
            logger.info(f"🔍 DEBUG: Parsed entities: {json.dumps(entities, indent=2)}")
            print(f"🔍 DEBUG: ===== PARSED ENTITIES =====")
            print(json.dumps(entities, indent=2))
            print(f"🔍 DEBUG: ===========================")
            
            # Log extracted entities
            location = entities.get("location", {})
            temporal = entities.get("temporal", {})
            
            if location.get("name"):
                logger.info(f"📍 Location: {location.get('name')} ({location.get('type')}, confidence: {location.get('confidence')})")
                print(f"✅ DEBUG: Entity extraction - Location: {location.get('name')}")
            
            if temporal.get("year") or temporal.get("month") or temporal.get("relative"):
                logger.info(f"🗓️ Temporal: year={temporal.get('year')}, month={temporal.get('month')}, relative={temporal.get('relative')}")
                print(f"✅ DEBUG: Entity extraction - Temporal: {temporal}")
            
            return entities

        except json.JSONDecodeError as e:
            logger.error(f"❌ JSON parsing failed: {e}")
            logger.error(f"Raw content: {content[:500]}")
            print(f"❌🚨 DEBUG: JSON parsing failed!")
            print(f"❌🚨 Error: {e}")
            print(f"❌🚨 Raw content: {content[:500]}")
            return {
                "location": {"name": None, "type": None, "confidence": 0.0},
                "temporal": {},
                "disaster": {},
                "damage_indicators": {},
                "analysis_intent": {}
            }
        except Exception as e:
            logger.error(f"❌ Entity extraction failed: {type(e).__name__}: {e}")
            logger.error(f"Full traceback: {traceback.format_exc()}")
            print(f"❌🚨 DEBUG: Entity extraction EXCEPTION!")
            print(f"❌🚨 Exception: {type(e).__name__}: {e}")
            print(f"❌🚨 Traceback: {traceback.format_exc()}")
            return {
                "location": {"name": None, "type": None, "confidence": 0.0},
                "temporal": {},
                "disaster": {},
                "damage_indicators": {},
                "analysis_intent": {}
            }
    
    # ============================================================================
    # AGENT 4: TILE SELECTOR - HELPER FUNCTIONS (Conditional Logic)
    # ============================================================================
    
    def _calculate_bbox_area_km2(self, bbox: List[float]) -> float:
        """
        Calculate the area of a bounding box in square kilometers.
        
        Args:
            bbox: [west, south, east, north] in degrees
        
        Returns:
            Area in square kilometers
        """
        from geopy.distance import geodesic
        
        west, south, east, north = bbox
        
        # Calculate width at the center latitude
        center_lat = (south + north) / 2
        width_km = geodesic((center_lat, west), (center_lat, east)).km
        
        # Calculate height
        height_km = geodesic((south, west), (north, west)).km
        
        # Approximate area (not perfect for large regions, but sufficient)
        area_km2 = width_km * height_km
        
        return area_km2
    
    def _should_use_agent_selector(
        self,
        tile_count: int,
        bbox: List[float],
        query: str
    ) -> bool:
        """
        Determine if we should use the intelligent GPT-5 agent for tile selection
        or the fast rule-based function.
        
        Strategy:
        - Use simple function (fast path) for few tiles
        - Use GPT-5 agent (smart path) for many tiles or complex queries
        
        Args:
            tile_count: Number of tiles returned from STAC
            bbox: Bounding box [west, south, east, north]
            query: User's natural language query
        
        Returns:
            True if agent should be used, False for simple function
        """
        # Calculate area of interest
        bbox_area_km2 = self._calculate_bbox_area_km2(bbox)
        
        # Base thresholds by area size
        SMALL_AREA_THRESHOLD = 100  # km² (e.g., city-sized area)
        MEDIUM_AREA_THRESHOLD = 1000  # km² (e.g., county-sized area)
        
        # Adaptive tile count thresholds
        if bbox_area_km2 < SMALL_AREA_THRESHOLD:
            # Small area: Use agent if > 10 tiles
            tile_threshold = 10
        elif bbox_area_km2 < MEDIUM_AREA_THRESHOLD:
            # Medium area: Use agent if > 20 tiles
            tile_threshold = 20
        else:
            # Large area: Use agent if > 50 tiles
            tile_threshold = 50
        
        # Check for complex query keywords that benefit from intelligent selection
        complex_keywords = [
            'best', 'clearest', 'least cloud', 'most cloud', 'highest quality',
            'most recent', 'before', 'after', 'compare', 'change', 'cleanest',
            'optimal', 'perfect', 'ideal', 'specific date'
        ]
        has_complex_query = any(keyword in query.lower() for keyword in complex_keywords)
        
        # Decision logic
        if tile_count < tile_threshold and not has_complex_query:
            logger.info(f"🚀 FAST PATH: Using rule-based selector (tiles: {tile_count}, threshold: {tile_threshold}, area: {bbox_area_km2:.1f}km²)")
            return False  # Use simple function (fast path)
        else:
            logger.info(f"🤖 SMART PATH: Using GPT-5 agent (tiles: {tile_count}, threshold: {tile_threshold}, area: {bbox_area_km2:.1f}km², complex_query: {has_complex_query})")
            return True   # Use agent (smart path)
    
    # ============================================================================
    # AGENT 4: TILE SELECTOR AGENT (GPT-Powered Intelligent Tile Selection)
    # ============================================================================
    
    async def tile_selector_agent(
        self,
        stac_features: List[Dict],
        query: str,
        collection_ids: List[str],
        bbox: List[float]
    ) -> List[Dict]:
        """
        AGENT 3: Intelligent tile selection using GPT-5
        
        Priorities:
        1. HIGHEST RESOLUTION: Select tiles from highest resolution collections
        2. FULL COVERAGE: Ensure 100% spatial coverage of requested area
        3. QUERY ALIGNMENT: Respect user's cloud cover, date, and other criteria
        
        Returns: Optimized subset of tiles (5-50 tiles) for static map rendering
        """
        
        logger.info("=" * 80)
        logger.info(f"🎯 AGENT 3 (TILE SELECTOR): Starting intelligent tile selection")
        logger.info(f"   Input: {len(stac_features)} tiles from {len(collection_ids)} collections")
        logger.info(f"   Query: {query[:100]}...")
        logger.info(f"   Collections: {collection_ids}")
        
        try:
            # Quick validation
            if not stac_features:
                logger.warning("⚠️ AGENT 3: No tiles to select from, returning empty list")
                return []
            
            # Step 1: Extract resolution information for each collection
            logger.info(f"📊 AGENT 3 STEP 1: Analyzing collection resolutions...")
            collection_resolutions = {}
            for coll_id in collection_ids:
                profile = COLLECTION_PROFILES.get(coll_id, {})
                res_str = profile.get("resolution", "unknown")
                res_meters = self._parse_resolution(res_str)
                collection_resolutions[coll_id] = {
                    "resolution_str": res_str,
                    "resolution_m": res_meters
                }
                logger.info(f"   {coll_id}: {res_str} ({res_meters}m)")
            
            # Find highest resolution
            best_resolution = min([v["resolution_m"] for v in collection_resolutions.values()])
            logger.info(f"   🏆 Best resolution: {best_resolution}m")
            
            # Step 2: Calculate AOI characteristics
            logger.info(f"🗺️ AGENT 3 STEP 2: Analyzing area of interest...")
            aoi_area_km2 = self._calculate_area(bbox)
            tile_limit = self._determine_tile_limit(bbox, query)
            coverage_info = self._check_spatial_coverage(stac_features, bbox)
            
            logger.info(f"   AOI area: {aoi_area_km2:.2f} km²")
            logger.info(f"   Tile limit: {tile_limit} tiles")
            logger.info(f"   Coverage: {coverage_info.get('coverage_percent', 0):.1f}%")
            logger.info(f"   Intersecting tiles: {coverage_info.get('intersecting_tiles', 0)}/{len(stac_features)}")
            
            # Step 3: Prepare data summary for GPT
            logger.info(f"📝 AGENT 3 STEP 3: Preparing data for GPT analysis...")
            
            # Group tiles by collection
            tiles_by_collection = {}
            for feature in stac_features:
                coll = feature.get("collection", "unknown")
                if coll not in tiles_by_collection:
                    tiles_by_collection[coll] = []
                tiles_by_collection[coll].append(feature)
            
            # Create summary of available tiles
            tile_summary = []
            for coll, tiles in tiles_by_collection.items():
                res_info = collection_resolutions.get(coll, {})
                tile_summary.append({
                    "collection": coll,
                    "resolution": res_info.get("resolution_str", "unknown"),
                    "resolution_m": res_info.get("resolution_m", 1000),
                    "tile_count": len(tiles),
                    "sample_tiles": tiles[:3]  # First 3 for GPT analysis
                })
            
            # Sort by resolution (best first)
            tile_summary.sort(key=lambda x: x["resolution_m"])
            
            logger.info(f"   Prepared summary for {len(tile_summary)} collections")
            
            # Step 4: Call GPT-5 for intelligent selection
            logger.info(f"🤖 AGENT 3 STEP 4: Calling GPT-5 for tile selection...")
            
            try:
                await self._initialize_kernel()
                
                # Build GPT prompt
                prompt = f"""You are an expert satellite imagery selection agent. Your task is to select the OPTIMAL tiles for visualization.

QUERY: "{query}"

AREA OF INTEREST:
- Bounding Box: [{bbox[0]:.4f}, {bbox[1]:.4f}, {bbox[2]:.4f}, {bbox[3]:.4f}]
- Area: {aoi_area_km2:.2f} km²
- Target Tile Limit: {tile_limit} tiles

AVAILABLE TILES:
{json.dumps(tile_summary, indent=2)}

🎯 TOP PRIORITIES (MANDATORY):
1. **HIGHEST RESOLUTION ONLY** - Select tiles EXCLUSIVELY from the {best_resolution}m resolution collection
   - DO NOT mix resolutions
   - If lower resolution tiles are needed for coverage, still prioritize highest resolution tiles
   
2. **FULL AREA COVERAGE** - Selected tiles MUST completely cover the bounding box
   - Check that tile bboxes collectively cover [{bbox[0]:.4f}, {bbox[1]:.4f}, {bbox[2]:.4f}, {bbox[3]:.4f}]
   - NO GAPS allowed in spatial coverage
   - Prefer fewer high-res tiles over more low-res tiles

3. **SINGLE TIME SNAPSHOT** - All tiles must be from the SAME acquisition date/time
   - NO temporal overlap or mixing of dates
   - Choose the most recent available acquisition time
   
4. **QUERY-SPECIFIC REQUIREMENTS** - Consider user's specific needs:
   - Cloud cover preferences (if mentioned: "clear", "low cloud", etc.)
   - Temporal requirements (if date/time specified)
   - Quality indicators from query context

SELECTION RULES:
✅ MUST: Use only highest resolution tiles ({best_resolution}m)
✅ MUST: Ensure 100% spatial coverage of area of interest
✅ MUST: Select tiles from single acquisition datetime
✅ SHOULD: Minimize number of tiles (fewer is better if coverage complete)
✅ SHOULD: Respect cloud cover preferences from query
✅ SHOULD: Choose most recent acquisition time available
❌ NEVER: Mix different resolutions
❌ NEVER: Leave gaps in spatial coverage
❌ NEVER: Mix tiles from different acquisition times

IMPORTANT - TEMPORAL SELECTION RULES:
- **User specified datetime** (e.g., "September 2024"): Select most recent tiles WITHIN that datetime range
- **User did NOT specify datetime** (e.g., "show me NYC"): Select most recent tiles OVERALL
- **Multiple tiles at same datetime**: Always pick the LAST/MOST RECENT one
- **NEVER mix tiles from different dates/times** (causes overlapping tiles!)
- If tiles have different acquisition times, pick the MOST RECENT time, then select ONLY tiles from that time

RETURN FORMAT:
Return ONLY a JSON array of selected tile IDs in this exact format:
["collection-id/tile-id-1", "collection-id/tile-id-2", ...]

Example: ["sentinel-2-l2a/S2A_MSIL2A_20241001T123456", "sentinel-2-l2a/S2A_MSIL2A_20241001T123457"]

IMPORTANT: 
- Return ONLY the JSON array, no explanatory text
- Include the collection ID prefix in each tile ID
- Select tiles that fully cover the bounding box
- Prioritize quality over quantity"""

                execution_settings = AzureChatPromptExecutionSettings(
                    max_completion_tokens=2000,
                    temperature=1.0,  # GPT-5 requires default temperature=1.0
                    top_p=0.95
                )
                
                # Create chat history
                chat_history = ChatHistory()
                chat_history.add_system_message("You are an expert satellite imagery selection agent. Return ONLY valid JSON arrays.")
                chat_history.add_user_message(prompt)
                
                # Get chat completion service
                chat_completion = self.kernel.get_service(type=ChatCompletionClientBase)
                
                # Get GPT response
                result = await chat_completion.get_chat_message_content(
                    chat_history=chat_history,
                    settings=execution_settings,
                    kernel=self.kernel
                )
                
                # Extract tile IDs from response
                response_text = str(result) if result else ""
                logger.info(f"   GPT response length: {len(response_text)} chars")
                logger.info(f"   GPT response preview: {response_text[:200]}...")
                
                # Parse JSON response
                selected_tile_ids = self._extract_tile_ids_from_gpt_response(response_text)
                
                if not selected_tile_ids:
                    logger.warning(f"⚠️ AGENT 3: GPT returned no tile IDs, falling back to rule-based")
                    return await self._rule_based_tile_selector(
                        stac_features, query, collection_ids, bbox, tile_limit, best_resolution
                    )
                
                logger.info(f"✅ AGENT 3 GPT: Selected {len(selected_tile_ids)} tile IDs")
                
                # Map tile IDs back to features
                selected_features = []
                for feature in stac_features:
                    feature_id = feature.get("id", "")
                    collection = feature.get("collection", "")
                    full_id = f"{collection}/{feature_id}"
                    
                    if full_id in selected_tile_ids or feature_id in selected_tile_ids:
                        selected_features.append(feature)
                
                if not selected_features:
                    logger.warning(f"⚠️ AGENT 3: Could not map tile IDs to features, falling back")
                    return await self._rule_based_tile_selector(
                        stac_features, query, collection_ids, bbox, tile_limit, best_resolution
                    )
                
                logger.info(f"✅ AGENT 3 SUCCESS: Selected {len(selected_features)} tiles")
                logger.info(f"   Coverage: {len(selected_features)}/{tile_limit} tiles")
                logger.info("=" * 80)
                return selected_features
                
            except Exception as gpt_error:
                logger.error(f"❌ AGENT 3 GPT ERROR: {type(gpt_error).__name__}: {str(gpt_error)}")
                logger.error(f"   Falling back to rule-based selector")
                return await self._rule_based_tile_selector(
                    stac_features, query, collection_ids, bbox, tile_limit, best_resolution
                )
        
        except Exception as e:
            logger.error(f"❌ AGENT 3 EXCEPTION: {type(e).__name__}: {str(e)}")
            logger.error(f"❌ AGENT 3 TRACEBACK:")
            logger.error(traceback.format_exc())
            logger.warning(f"⚠️ AGENT 3: Critical error, falling back to rule-based")
            
            # Emergency fallback
            tile_limit = self._determine_tile_limit(bbox, query)
            return await self._rule_based_tile_selector(
                stac_features, query, collection_ids, bbox, tile_limit, 30.0
            )
    
    def _extract_tile_ids_from_gpt_response(self, response_text: str) -> List[str]:
        """Extract tile IDs from GPT response (handles various formats)"""
        try:
            # Try direct JSON parse
            if response_text.strip().startswith("["):
                return json.loads(response_text.strip())
            
            # Try to find JSON array in response
            json_match = re.search(r'\[.*?\]', response_text, re.DOTALL)
            if json_match:
                return json.loads(json_match.group(0))
            
            # Try to extract quoted strings
            tile_ids = re.findall(r'"([^"]+)"', response_text)
            if tile_ids:
                return tile_ids
            
            logger.warning(f"⚠️ Could not extract tile IDs from GPT response")
            return []
            
        except Exception as e:
            logger.error(f"❌ Error parsing GPT tile IDs: {e}")
            return []
    
    async def _rule_based_tile_selector(
        self,
        stac_features: List[Dict],
        query: str,
        collection_ids: List[str],
        bbox: List[float],
        tile_limit: int,
        best_resolution_m: float
    ) -> List[Dict]:
        """
        RULE-BASED FALLBACK: Simple, reliable tile selection
        
        Strategy:
        1. Filter to highest resolution collection only
        2. Sort by datetime (most recent first)
        3. Filter by spatial intersection with bbox
        4. Take top N tiles up to limit
        """
        
        logger.info("🔄 AGENT 3 FALLBACK: Using rule-based tile selection")
        
        try:
            # Step 1: Filter to highest resolution tiles
            high_res_tiles = []
            for feature in stac_features:
                coll = feature.get("collection", "")
                if coll in collection_ids:
                    profile = COLLECTION_PROFILES.get(coll, {})
                    res_str = profile.get("resolution", "1000m")
                    res_m = self._parse_resolution(res_str)
                    
                    # Allow tiles within 20% of best resolution
                    if res_m <= best_resolution_m * 1.2:
                        high_res_tiles.append(feature)
            
            logger.info(f"   Filtered to {len(high_res_tiles)} high-resolution tiles")
            
            if not high_res_tiles:
                high_res_tiles = stac_features  # Fallback: use all
            
            # Step 2: Filter by spatial intersection
            west, south, east, north = bbox
            intersecting_tiles = []
            
            for feature in high_res_tiles:
                feature_bbox = feature.get("bbox")
                if not feature_bbox or len(feature_bbox) != 4:
                    continue
                
                fw, fs, fe, fn = feature_bbox
                
                # Check if bboxes intersect
                if not (fe < west or fw > east or fn < south or fs > north):
                    intersecting_tiles.append(feature)
            
            logger.info(f"   Filtered to {len(intersecting_tiles)} spatially intersecting tiles")
            
            if not intersecting_tiles:
                intersecting_tiles = high_res_tiles  # Fallback
            
            # Step 3: Group by acquisition datetime and select SINGLE timepoint
            # RULE: Always pick most recent datetime, whether user specified or not
            from collections import defaultdict
            
            tiles_by_datetime = defaultdict(list)
            
            def get_datetime(feature):
                try:
                    dt_str = feature.get("properties", {}).get("datetime", "")
                    if dt_str:
                        dt = datetime.fromisoformat(dt_str.replace("Z", "+00:00"))
                        # Round to nearest hour to group tiles from same acquisition
                        return dt.replace(minute=0, second=0, microsecond=0)
                    return datetime.min
                except:
                    return datetime.min
            
            # Group tiles by datetime
            for feature in intersecting_tiles:
                dt = get_datetime(feature)
                tiles_by_datetime[dt].append(feature)
            
            logger.info(f"   Found {len(tiles_by_datetime)} different acquisition times")
            
            # TEMPORAL SELECTION LOGIC:
            # 1. If user specified datetime → tiles are already filtered by Agent 2
            # 2. Pick MOST RECENT datetime from available tiles
            # 3. If multiple tiles at same datetime → sort by ID and take last
            
            if tiles_by_datetime:
                most_recent_time = max(tiles_by_datetime.keys())
                selected_time_tiles = tiles_by_datetime[most_recent_time]
                
                logger.info(f"   Most recent acquisition: {most_recent_time}")
                logger.info(f"   Tiles from that time: {len(selected_time_tiles)}")
                
                # Sort tiles by ID (deterministic ordering) and acquisition time
                # This ensures if there are multiple tiles at exact same datetime,
                # we consistently pick the "last" one (alphabetically last ID)
                selected_time_tiles.sort(
                    key=lambda f: (
                        get_datetime(f),  # Primary: datetime
                        f.get("id", "")   # Secondary: tile ID (last alphabetically)
                    ),
                    reverse=True  # Most recent first
                )
                
                logger.info(f"   Sorted {len(selected_time_tiles)} tiles by datetime (most recent first)")
            else:
                selected_time_tiles = intersecting_tiles
            
            # Step 4: Apply limit to tiles from single timepoint
            # Take first N tiles (which are already sorted by most recent)
            selected = selected_time_tiles[:tile_limit]
            
            logger.info(f"✅ AGENT 3 FALLBACK: Selected {len(selected)} tiles")
            if selected:
                first_tile_dt = get_datetime(selected[0])
                logger.info(f"   Single acquisition time: {first_tile_dt}")
                logger.info(f"   Tile IDs: {[f.get('id', 'unknown')[:30] + '...' for f in selected[:3]]}")
            logger.info(f"   (Highest resolution + most recent + full coverage + NO temporal overlap)")
            
            return selected
            
        except Exception as e:
            logger.error(f"❌ FALLBACK ERROR: {e}, returning limited original list")
            return stac_features[:min(tile_limit, len(stac_features))]
    
    async def _build_stac_parameters(self, query: str, collections: List[str], entities: Optional[Dict[str, Any]] = None, datetime_range: Optional[str] = None) -> Dict[str, Any]:
        """
        🔧 UTILITY: Build STAC query parameters (DETERMINISTIC - No GPT)
        
        This is now a pure function that assembles STAC parameters from resolved components.
        All ambiguity has been handled by upstream agents:
        - Collections: Selected by collection_mapping_agent (Agent 1)
        - Datetime: Resolved by datetime_translation_agent (Agent 2.2)
        - Cloud filter: Determined by cloud_filtering_agent (Agent 2.3)
        - Location: Extracted by location_extraction_agent (Agent 2.1)
        
        Args:
            query: User's natural language query (for reference)
            collections: Selected collection IDs
            entities: Extracted entities (for context)
            datetime_range: Pre-resolved ISO 8601 datetime or None
        
        Returns:
            Dict with STAC query parameters
        """
        
        # 🔍 DEBUG: Log input parameters
        logger.info(f"� UTILITY: _build_stac_parameters (deterministic)")
        logger.info(f"� Collections: {collections}")
        logger.info(f"� Datetime range: {datetime_range}")
        print(f"� DEBUG: ===== BUILD STAC PARAMETERS (PURE FUNCTION) =====")
        print(f"� DEBUG: Collections: {collections}")
        print(f"� DEBUG: Datetime: {datetime_range}")
        
        # Build base parameters
        stac_query = {
            "collections": collections,
            "sortby": [{"field": "datetime", "direction": "desc"}]
        }
        
        # Add datetime if provided (already validated by datetime_translation_agent)
        if datetime_range:
            stac_query["datetime"] = datetime_range
            logger.info(f"✅ Added datetime: {datetime_range}")
            print(f"✅ Datetime added: {datetime_range}")
        else:
            logger.info(f"ℹ️ No datetime filter (will return most recent)")
            print(f"ℹ️ No datetime filter")
        
        # Always query 100 tiles - GPT-5 will select the best ones
        # This provides enough options for intelligent selection while keeping queries fast
        stac_query["limit"] = 100
        
        logger.info(f"✅ Query limit: 100 (GPT-5 will select best tiles)")
        print(f"✅ Limit: 100 tiles for GPT-5 selection")
        
        # 🔍 DEBUG: Log final parameters
        logger.info(f"� STAC parameters built (deterministic): {stac_query}")
        print(f"� DEBUG: ===== BUILT STAC PARAMETERS =====")
        print(json.dumps(stac_query, indent=2))
        print(f"� DEBUG: ====================================")
        
        return stac_query
    
    async def _add_cloud_filtering_to_query(self, stac_query: Dict[str, Any], query: str, entities: Dict[str, Any], collections: List[str]) -> None:
        """
        Add cloud filtering to STAC query ONLY if user explicitly mentions cloud cover.
        
        This method:
        1. Detects EXPLICIT cloud cover mentions (low/medium/high cloud, clear, cloudy, etc.)
        2. Checks if selected collections support cloud filtering
        3. Adds filter only if both conditions are met
        4. Logs warning if user requests cloud filtering for non-supporting collections
        
        Modifies stac_query in-place by adding to the 'query' dict.
        """
        # Import collection profile helpers
        from collection_profiles import (
            supports_cloud_filtering,
            get_cloud_cover_property
        )
        
        # Detect EXPLICIT cloud cover intent (returns None if no explicit mention)
        cloud_intent = await self._detect_cloud_cover_intent(query)
        
        if cloud_intent is None:
            # No explicit cloud mention - do not add filter
            logger.info(f"[Cloud Filter] No explicit cloud mention in query - skipping filter")
            return
        
        cloud_limit = cloud_intent["threshold"]
        reasoning = cloud_intent["reasoning"]
        logger.info(f"[Cloud Filter] {reasoning} - threshold: {cloud_limit}%")
        
        # Check which collections support cloud filtering
        cloud_filterable_collections = [c for c in collections if supports_cloud_filtering(c)]
        non_filterable_collections = [c for c in collections if not supports_cloud_filtering(c)]
        
        logger.info(f"[Cloud Filter] Filterable collections: {cloud_filterable_collections}")
        if non_filterable_collections:
            logger.info(f"[Cloud Filter] Non-filterable collections: {non_filterable_collections}")
        
        # If user requested cloud filtering but NO collections support it
        if len(cloud_filterable_collections) == 0:
            warning_msg = (
                f"Note: Cloud cover filtering requested ({cloud_limit}% threshold), "
                f"but the selected collections do not support cloud cover metadata. "
                f"Collections selected: {', '.join(collections)}. "
                f"These collections either use radar (SAR), are elevation data (DEM), "
                f"or are pre-processed composites where clouds have already been removed."
            )
            logger.warning(f"[Cloud Filter] {warning_msg}")
            
            # Store warning for response generation
            entities['cloud_filter_unavailable'] = {
                'requested_threshold': cloud_limit,
                'collections': collections,
                'warning_message': warning_msg
            }
            return
        
        # Add cloud filter to query
        if 'query' not in stac_query:
            stac_query['query'] = {}
        
        query_filters = stac_query['query']
        
        # Use the FIRST cloud-filterable collection to determine property name
        primary_collection = cloud_filterable_collections[0]
        prop_name = get_cloud_cover_property(primary_collection)
        
        if prop_name:
            # Build filter: {"eo:cloud_cover": {"lt": 25}}
            filter_value = {"lt": cloud_limit}
            query_filters[prop_name] = filter_value
            logger.info(f"[Cloud Filter] ✅ ADDED: {prop_name} < {cloud_limit}% for {primary_collection}")
            
            # If some collections don't support filtering, log mixed collection warning
            if non_filterable_collections:
                logger.warning(
                    f"[Cloud Filter] Mixed collections: filter applied to "
                    f"{cloud_filterable_collections} but NOT {non_filterable_collections}"
                )
        else:
            logger.error(f"[Cloud Filter] Failed to get property name for collection {primary_collection}")
    
    def _build_collection_rules_for_agent(self, collections: List[str]) -> str:
        """Build collection rules summary for Agent 2"""
        
        if not PROFILES_AVAILABLE:
            return "Limited collection rules available"
        
        rules_lines = []
        for collection_id in collections:
            if collection_id not in COLLECTION_PROFILES:
                continue
            
            profile = COLLECTION_PROFILES[collection_id]
            rules = profile.get("query_rules", {})
            caps = rules.get("capabilities", {})
            
            rules_text = f"\n{collection_id}:"
            
            if caps.get("static_data"):
                rules_text += "\n  - Type: STATIC (DEM/Elevation data)"
                rules_text += "\n  - Rule: NEVER use datetime"
                rules_text += "\n  - Rule: ONLY use bbox and limit"
            elif caps.get("composite_data"):
                rules_text += "\n  - Type: COMPOSITE (Pre-aggregated)"
                rules_text += "\n  - Rule: Use sortby instead of datetime"
                rules_text += "\n  - Rule: NO cloud_cover filter (already filtered)"
            else:
                rules_text += "\n  - Type: DYNAMIC (Time-series)"
                rules_text += "\n  - Rule: CAN use datetime"
                if caps.get("supports_cloud_cover"):
                    rules_text += "\n  - Rule: CAN use cloud_cover filter"
            
            rules_lines.append(rules_text)
        
        return "\n".join(rules_lines)
    
    async def _extract_location_name(self, query: str) -> Optional[str]:
        """
        DEPRECATED: Extract location name from query using keyword pattern matching
        
        This function is NO LONGER USED as of 2025-10-09.
        Location extraction is now handled by Agent 2 (GPT-5) which provides
        both location_name and bbox in its response.
        
        Keeping this function for backwards compatibility, but it should be
        removed in future cleanup.
        
        Historical context:
        - Originally created as workaround when Agent 2 was told NOT to include bbox
        - Used fragile regex patterns that failed on many query phrasings
        - Replaced by letting GPT-5 do natural language understanding
        """
        
        # Simple location extraction - look for common patterns
        query_lower = query.lower()
        
        # Try to extract location name
        location_keywords = ["in ", "at ", "of ", "for ", "near "]
        location_name = None
        
        for keyword in location_keywords:
            if keyword in query_lower:
                # Extract text after keyword
                idx = query_lower.find(keyword)
                after_keyword = query[idx + len(keyword):].strip()
                
                # Extract location name: take up to the first punctuation or question word
                # Skip articles like "the"
                words = after_keyword.split()
                location_parts = []
                for word in words:
                    # Stop at punctuation or question words
                    if word.lower() in ["?", "!", ".", ",", "what", "when", "where", "how", "why"]:
                        break
                    # Skip articles
                    if word.lower() in ["the", "a", "an"]:
                        continue
                    location_parts.append(word)
                    # Take up to 3 words for compound names (e.g., "Grand Canyon National")
                    if len(location_parts) >= 3:
                        break
                
                if location_parts:
                    location_name = " ".join(location_parts)
                    break
        
        if not location_name:
            # Try common place names as fallback
            places = ["grand canyon", "california", "seattle", "houston", "florida", "texas", "yosemite", "yellowstone"]
            for place in places:
                if place in query_lower:
                    location_name = place.title()
                    break
        
        if location_name:
            logger.info(f"📍 Extracted location name from query: '{location_name}'")
        else:
            logger.warning(f"⚠️ Could not extract location from query: '{query}'")
        
        return location_name
    
    async def _build_stac_query_basic(self, query: str, collections: List[str]) -> Dict[str, Any]:
        """Fallback basic STAC query builder with location resolution"""
        
        logger.warning("⚠️ Using fallback basic query builder (kernel not initialized)")
        
        stac_query = {
            "collections": collections,
            "limit": 100  # Changed from 1000 to 100 for better performance
        }
        
        # Check if static collection
        is_static = any(is_static_collection(c) for c in collections)
        
        if not is_static:
            # Add recent datetime for dynamic collections
            stac_query["datetime"] = "2023-01-01/.."
            stac_query["sortby"] = [{"field": "datetime", "direction": "desc"}]
        
        # CRITICAL FIX: Attempt basic location extraction even in fallback mode
        # This prevents returning 1000 global tiles for location-specific queries
        try:
            location_name = await self._extract_location_basic(query)
            if location_name:
                logger.info(f"📍 Fallback: Attempting to resolve '{location_name}' to bbox")
                bbox = await self.resolve_location_to_bbox(location_name, "region")
                if bbox and self._validate_bbox(bbox):
                    stac_query["bbox"] = bbox
                    stac_query["location_name"] = location_name
                    logger.info(f"✅ Fallback: Resolved '{location_name}' → bbox: {bbox}")
                else:
                    logger.warning(f"⚠️ Fallback: Could not resolve '{location_name}' to bbox")
        except Exception as e:
            logger.warning(f"⚠️ Fallback location extraction failed: {e}")
        
        return stac_query
    
    # ========================================================================
    # LOCATION RESOLUTION
    # ========================================================================
    
    def _extract_json_safely(self, content: str) -> Dict[str, Any]:
        """Enhanced JSON extraction with multiple parsing strategies"""
        
        content = content.strip()
        
        # Strategy 1: Direct JSON parsing
        try:
            return json.loads(content)
        except json.JSONDecodeError:
            pass
        
        # Strategy 2: Extract JSON from markdown code blocks
        json_patterns = [
            r'```json\s*(\{.*?\})\s*```',
            r'```\s*(\{.*?\})\s*```',
            r'(\{[^{}]*(?:\{[^{}]*\}[^{}]*)*\})',
        ]
        
        for pattern in json_patterns:
            matches = re.findall(pattern, content, re.DOTALL | re.IGNORECASE)
            for match in matches:
                try:
                    # Clean up the match
                    cleaned = re.sub(r'\\n', '\n', match)
                    cleaned = re.sub(r'\\"', '"', cleaned)
                    return json.loads(cleaned)
                except (json.JSONDecodeError, TypeError):
                    continue
        
        # Strategy 3: Line-by-line JSON reconstruction
        lines = content.split('\n')
        json_lines = []
        in_json = False
        
        for line in lines:
            line = line.strip()
            if line.startswith('{'):
                in_json = True
                json_lines = [line]
            elif in_json:
                json_lines.append(line)
                if line.endswith('}') and len(json_lines) > 1:
                    try:
                        json_content = '\n'.join(json_lines)
                        return json.loads(json_content)
                    except json.JSONDecodeError:
                        continue
        
        # Strategy 4: Extract from ChatMessageContent format
        if 'ChatMessageContent' in content or 'content=' in content:
            content_patterns = [
                r"content=['\"]([^'\"]*)['\"]",
                r"content='([^']*)'",
                r'content="([^"]*)"',
                r"message=ChatCompletionMessage\(content='([^']*)'",
            ]
            
            for pattern in content_patterns:
                match = re.search(pattern, content)
                if match:
                    extracted_content = match.group(1)
                    # Unescape content
                    extracted_content = extracted_content.replace('\\"', '"').replace('\\n', '\n')
                    try:
                        return json.loads(extracted_content)
                    except json.JSONDecodeError:
                        continue
        
        # Strategy 5: Build JSON from extracted components
        logger.warning("All JSON extraction strategies failed, using component extraction")
        return self._extract_components_from_text(content)
    
    def _extract_components_from_text(self, content: str) -> Dict[str, Any]:
        """Extract individual components when JSON parsing fails completely"""
        
        # Use regex to extract key information
        location_match = re.search(r'(?:location|place|area)["\']?\s*:\s*["\']?([^,\n"\']+)', content, re.IGNORECASE)
        disaster_match = re.search(r'(?:disaster|event|type)["\']?\s*:\s*["\']?([^,\n"\']+)', content, re.IGNORECASE)
        year_match = re.search(r'(?:year)["\']?\s*:\s*["\']?(\d{4})', content, re.IGNORECASE)
        month_match = re.search(r'(?:month)["\']?\s*:\s*["\']?(\d{1,2})', content, re.IGNORECASE)
        
        # Build basic structure
        result = {
            "location": {
                "name": location_match.group(1).strip() if location_match else None,
                "type": "region",
                "confidence": 0.6 if location_match else 0.1
            },
            "temporal": {
                "year": year_match.group(1) if year_match else None,
                "month": f"{int(month_match.group(1)):02d}" if month_match else None,
                "season": None,
                "relative": None,
                "confidence": 0.5 if year_match or month_match else 0.1
            },
            "disaster": {
                "type": disaster_match.group(1).strip().lower() if disaster_match else None,
                "name": None,
                "confidence": 0.6 if disaster_match else 0.1
            },
            "damage_indicators": {
                "blue_tarp": False,
                "structural_damage": False,
                "flooding": False,
                "fire_damage": False,
                "debris": False,
                "confidence": 0.1
            },
            "analysis_intent": {
                "type": "general_imagery",
                "urgency": "low", 
                "confidence": 0.1
            }
        }
        
        logger.warning(f"Used component extraction for parsing: {result}")
        return result
        
        # Handle escaped newlines first
        content = content.replace('\\n', '\n').replace('\\"', '"')
        
        # Strategy 1: Direct JSON parsing
        try:
            return json.loads(content)
        except json.JSONDecodeError:
            pass
        
        # Strategy 2: Find JSON block with newlines
        patterns = [
            r'\{[^{}]*(?:\{[^{}]*\}[^{}]*)*\}',  # Better nested JSON handling
            r'```json\s*(\{.*?\})\s*```',  # Markdown JSON block
            r'```\s*(\{.*?\})\s*```'  # Generic code block
        ]
        
        for pattern in patterns:
            matches = re.findall(pattern, content, re.DOTALL | re.MULTILINE)
            for match in matches:
                try:
                    # Clean the match
                    clean_match = match.strip()
                    return json.loads(clean_match)
                except json.JSONDecodeError:
                    continue
        
        # Strategy 3: Extract using braces (improved for multiline)
        start_idx = content.find('{')
        if start_idx != -1:
            brace_count = 0
            end_idx = -1
            in_string = False
            escape_next = False
            
            for i in range(start_idx, len(content)):
                char = content[i]
                
                if escape_next:
                    escape_next = False
                    continue
                
                if char == '\\':
                    escape_next = True
                    continue
                
                if char == '"' and not escape_next:
                    in_string = not in_string
                    continue
                
                if not in_string:
                    if char == '{':
                        brace_count += 1
                    elif char == '}':
                        brace_count -= 1
                        if brace_count == 0:
                            end_idx = i + 1
                            break
            
            if end_idx != -1:
                try:
                    json_str = content[start_idx:end_idx]
                    return json.loads(json_str)
                except json.JSONDecodeError as e:
                    logger.warning(f"JSON parse error: {e}, JSON: {json_str[:200]}")
        
        raise ValueError(f"Could not extract valid JSON from response: {content[:200]}...")
    
    def _validate_entities(self, entities: Dict[str, Any], query: str = "") -> Dict[str, Any]:
        """Validate and sanitize extracted entities"""
        
        # Add the original query for collection selection logic
        entities["original_query"] = query
        
        # Ensure all required top-level keys exist
        required_keys = ["location", "temporal", "disaster", "damage_indicators", "analysis_intent"]
        for key in required_keys:
            if key not in entities:
                entities[key] = {}
        
        # Validate confidence scores
        for section in entities.values():
            if isinstance(section, dict) and "confidence" in section:
                conf = section.get("confidence", 0.0)
                if not isinstance(conf, (int, float)) or conf < 0 or conf > 1:
                    section["confidence"] = 0.5  # Default confidence
        
        # Validate and enhance temporal information
        temporal = entities.get("temporal", {})
        if temporal.get("year"):
            try:
                year = int(temporal["year"])
                if year < 1900 or year > 2030:
                    temporal["year"] = None
            except (ValueError, TypeError):
                temporal["year"] = None
        
        return entities
    
    def _resolve_temporal_to_datetime(self, entities: Optional[Dict[str, Any]], collections: List[str]) -> Optional[str]:
        """
        🗓️ Convert temporal entities to ISO 8601 datetime range for STAC API
        
        This is an INTERNAL helper method for build_stac_query_agent().
        Separates temporal resolution from STAC query building for cleaner architecture.
        
        Args:
            entities: Extracted entities with temporal info (from _extract_location_and_temporal)
            collections: List of collection IDs (to determine if temporal filtering applies)
        
        Returns:
            ISO 8601 datetime range string (e.g., "2025-06-01/2025-06-30") or None
        
        Examples:
            - Year + Month: "2025-06-01/2025-06-30"
            - Year only: "2025-01-01/2025-12-31"
            - Relative "recent": "2025-09-17/2025-10-17" (last 30 days)
            - No temporal info: None (get most recent)
        """
        
        # 🔍 DEBUG: Log input parameters
        logger.info(f"🔍 DEBUG: _resolve_temporal_to_datetime called")
        logger.info(f"🔍 DEBUG: Collections: {collections}")
        logger.info(f"🔍 DEBUG: Entities: {entities}")
        print(f"🔍 DEBUG: _resolve_temporal_to_datetime - Collections: {collections}")
        print(f"🔍 DEBUG: _resolve_temporal_to_datetime - Entities: {json.dumps(entities, indent=2) if entities else 'None'}")
        
        # Check if any collections support temporal filtering
        # Static collections (DEM) and composites (MODIS) don't use datetime
        static_collections = ["cop-dem-glo-30", "cop-dem-glo-90", "3dep-seamless", "alos-dem"]
        composite_collections = ["modis-09Q1-061", "modis-11A2-061", "modis-13Q1-061", "modis-14A2-061", "modis-43A4-061", "modis-MCD64A1-061"]
        
        all_static = all(c in static_collections for c in collections)
        all_composite = all(c in composite_collections for c in collections)
        
        if all_static:
            logger.info("🗓️ Static collections (DEM) → No datetime filter")
            print("🗓️ DEBUG: Static collections detected - no datetime filter needed")
            return None
        
        if all_composite:
            logger.info("🗓️ Composite collections (MODIS) → No datetime filter (use sortby instead)")
            print("🗓️ DEBUG: Composite collections detected - no datetime filter needed")
            return None
        
        # Extract temporal info from entities
        if not entities or not entities.get("temporal"):
            logger.info("🗓️ No temporal entities extracted → No datetime filter (will return most recent)")
            print("🗓️ DEBUG: No temporal entities found - will return most recent data")
            return None
        
        temporal = entities.get("temporal", {})
        year = temporal.get("year")
        month = temporal.get("month")
        relative = temporal.get("relative")
        
        # 🔍 DEBUG: Log extracted temporal values
        logger.info(f"🔍 DEBUG: Extracted temporal values - year: {year}, month: {month}, relative: {relative}")
        print(f"🔍 DEBUG: Temporal values extracted:")
        print(f"  - year: {year}")
        print(f"  - month: {month}")
        print(f"  - relative: {relative}")
        
        import calendar
        from datetime import datetime, timedelta
        
        # Case 1: Specific month and year
        if year and month:
            # 🔍 DEBUG: Log Case 1 entry
            logger.info(f"🔍 DEBUG: Entering Case 1 (Year + Month): year={year}, month={month}")
            print(f"🔍 DEBUG: Case 1 (Year + Month) - year={year}, month={month}")
            
            try:
                year_int = int(year)
                month_int = int(month)
                
                # 🔍 DEBUG: Log conversion results
                logger.info(f"🔍 DEBUG: Converted to integers - year_int={year_int}, month_int={month_int}")
                print(f"🔍 DEBUG: Converted values - year_int={year_int}, month_int={month_int}")
                
                last_day = calendar.monthrange(year_int, month_int)[1]
                
                # 🔍 DEBUG: Log last day calculation
                logger.info(f"🔍 DEBUG: Last day of {calendar.month_name[month_int]} {year_int}: {last_day}")
                print(f"🔍 DEBUG: Last day of month: {last_day}")
                
                datetime_range = f"{year_int}-{month_int:02d}-01/{year_int}-{month_int:02d}-{last_day}"
                
                logger.info(f"🗓️ Resolved temporal: {calendar.month_name[month_int]} {year_int} → {datetime_range}")
                
                # 🔍 DEBUG: Log final result
                logger.info(f"🔍 DEBUG: Case 1 RESULT - datetime_range: {datetime_range}")
                print(f"🔍 DEBUG: Case 1 RESULT - datetime_range: {datetime_range}")
                print(f"  ✅ Start: {year_int}-{month_int:02d}-01")
                print(f"  ✅ End: {year_int}-{month_int:02d}-{last_day}")
                
                return datetime_range
            except (ValueError, TypeError) as e:
                logger.warning(f"⚠️ Failed to parse year={year}, month={month}: {e}")
                print(f"⚠️ ERROR: Failed to parse year={year}, month={month}: {e}")
                return None
        
        # Case 2: Year only
        if year:
            # 🔍 DEBUG: Log Case 2 entry
            logger.info(f"🔍 DEBUG: Entering Case 2 (Year only): year={year}")
            print(f"🔍 DEBUG: Case 2 (Year only) - year={year}")
            
            try:
                year_int = int(year)
                
                logger.info(f"🔍 DEBUG: Converted year to int: {year_int}")
                print(f"🔍 DEBUG: Year as int: {year_int}")
                
                datetime_range = f"{year_int}-01-01/{year_int}-12-31"
                
                logger.info(f"🗓️ Resolved temporal: Year {year_int} → {datetime_range}")
                
                # 🔍 DEBUG: Log final result
                logger.info(f"🔍 DEBUG: Case 2 RESULT - datetime_range: {datetime_range}")
                print(f"🔍 DEBUG: Case 2 RESULT - datetime_range: {datetime_range}")
                print(f"  ✅ Full year: {year_int}")
                
                return datetime_range
            except (ValueError, TypeError) as e:
                logger.warning(f"⚠️ Failed to parse year={year}: {e}")
                print(f"⚠️ ERROR: Failed to parse year={year}: {e}")
                return None
        
        # Case 3: Month only (current year)
        if month:
            # 🔍 DEBUG: Log Case 3 entry
            logger.info(f"🔍 DEBUG: Entering Case 3 (Month only): month={month}")
            print(f"🔍 DEBUG: Case 3 (Month only) - month={month}")
            
            try:
                current_year = datetime.now().year
                month_int = int(month)
                
                logger.info(f"🔍 DEBUG: Using current year {current_year}, month_int={month_int}")
                print(f"🔍 DEBUG: Current year: {current_year}, month_int: {month_int}")
                
                last_day = calendar.monthrange(current_year, month_int)[1]
                datetime_range = f"{current_year}-{month_int:02d}-01/{current_year}-{month_int:02d}-{last_day}"
                
                logger.info(f"🗓️ Resolved temporal: {calendar.month_name[month_int]} (current year) → {datetime_range}")
                
                # 🔍 DEBUG: Log final result
                logger.info(f"🔍 DEBUG: Case 3 RESULT - datetime_range: {datetime_range}")
                print(f"🔍 DEBUG: Case 3 RESULT - datetime_range: {datetime_range}")
                
                return datetime_range
            except (ValueError, TypeError) as e:
                logger.warning(f"⚠️ Failed to parse month={month}: {e}")
                print(f"⚠️ ERROR: Failed to parse month={month}: {e}")
                return None
        
        # Case 4: Relative time (e.g., "recent")
        if relative == "recent":
            # 🔍 DEBUG: Log Case 4 entry
            logger.info(f"🔍 DEBUG: Entering Case 4 (Relative 'recent')")
            print(f"🔍 DEBUG: Case 4 (Relative 'recent') - last 30 days")
            
            end_date = datetime.now()
            start_date = end_date - timedelta(days=30)
            
            logger.info(f"🔍 DEBUG: Date range - start: {start_date}, end: {end_date}")
            print(f"🔍 DEBUG: Start date: {start_date}, End date: {end_date}")
            
            datetime_range = f"{start_date.strftime('%Y-%m-%d')}/{end_date.strftime('%Y-%m-%d')}"
            
            logger.info(f"🗓️ Resolved temporal: Recent (last 30 days) → {datetime_range}")
            
            # 🔍 DEBUG: Log final result
            logger.info(f"🔍 DEBUG: Case 4 RESULT - datetime_range: {datetime_range}")
            print(f"🔍 DEBUG: Case 4 RESULT - datetime_range: {datetime_range}")
            
            return datetime_range
        
        # Case 5: No usable temporal info
        logger.info("🗓️ No usable temporal info → No datetime filter")
        print("🔍 DEBUG: Case 5 - No usable temporal info, returning None")
        return None
    
    async def datetime_translation_agent(
        self, 
        query: str, 
        collections: List[str],
        mode: str = "single"
    ) -> Optional[Union[str, Dict[str, Any]]]:
        """
        🤖 AGENT 2.5: GPT-powered datetime translation agent (EXTENDED for comparison mode)
        
        Converts natural language temporal expressions to ISO 8601 datetime ranges.
        Supports TWO modes:
        - "single": Returns one datetime range (existing behavior, default)
        - "comparison": Returns two datetime ranges (before/after for temporal comparison)
        
        This agent understands:
        - Specific dates: "October 2024", "June 15, 2023"
        - Relative time: "recent", "last month", "two weeks ago"
        - Quarters: "Q3 2024", "first quarter of 2023"
        - Seasons: "summer 2024", "early spring"
        - Ranges: "January to March 2024"
        - Comparisons: "January 1st vs January 3rd", "2023 to 2025"
        
        Args:
            query: User's natural language query
            collections: Selected collection IDs (to determine if temporal filtering applies)
            mode: "single" (default) or "comparison"
        
        Returns:
            If mode="single": str (e.g., "2024-10-01/2024-10-31") or None
            If mode="comparison": dict (e.g., {"before": "2025-01-01/...", "after": "2025-01-03/...", "explanation": "..."}) or None
        """
        
        # 🔍 Ensure kernel is initialized first
        await self._ensure_kernel_initialized()
        
        # 🔍 DEBUG: Log agent invocation
        logger.info(f"🤖 AGENT 2.5: datetime_translation_agent invoked (mode={mode})")
        print(f"🤖 DEBUG: ===== DATETIME TRANSLATION AGENT (MODE: {mode.upper()}) =====")
        print(f"🤖 DEBUG: Query: {query}")
        print(f"🤖 DEBUG: Collections: {collections}")
        
        # Validate mode
        if mode not in ["single", "comparison"]:
            logger.error(f"❌ Invalid mode: {mode}. Must be 'single' or 'comparison'")
            raise ValueError(f"Invalid mode: {mode}. Must be 'single' or 'comparison'")
        
        # Check if collections support temporal filtering
        static_collections = ["cop-dem-glo-30", "cop-dem-glo-90", "3dep-seamless", "alos-dem"]
        composite_collections = ["modis-09Q1-061", "modis-11A2-061", "modis-13Q1-061", "modis-14A2-061", "modis-43A4-061", "modis-MCD64A1-061"]
        
        all_static = all(c in static_collections for c in collections)
        
        # ✅ CRITICAL FIX: Allow datetime filtering if ANY collection is NOT composite
        # This handles mixed collections like ["modis-14A1-061" (daily), "modis-MCD64A1-061" (8-day)]
        has_non_composite = any(c not in composite_collections and c not in static_collections for c in collections)
        
        if all_static:
            logger.info("🗓️ Static collections (DEM) → No datetime filter")
            print("🗓️ DEBUG: Static collections - no datetime needed")
            return None
        
        # ✅ ONLY skip datetime if ALL collections are composite AND user didn't specify a year/date
        if not has_non_composite:
            logger.info("🗓️ All composite collections → No datetime filter")
            print("🗓️ DEBUG: Composite collections - no datetime needed")
            return None
        
        # Get current date for context
        from datetime import datetime
        current_date = datetime.now().strftime("%Y-%m-%d")
        current_year = datetime.now().year
        
        # Build mode-specific GPT prompt
        if mode == "single":
            datetime_prompt = self._build_single_datetime_prompt(current_date, current_year, query)
        else:  # mode == "comparison"
            datetime_prompt = self._build_comparison_datetime_prompt(current_date, current_year, query)
        
        try:
            from semantic_kernel.functions.kernel_arguments import KernelArguments
            from semantic_kernel.connectors.ai.open_ai.prompt_execution_settings.azure_chat_prompt_execution_settings import AzureChatPromptExecutionSettings
            
            execution_settings = AzureChatPromptExecutionSettings(
                service_id="chat-completion",
                temperature=1.0,  # GPT-5 requires default temperature=1.0
                max_completion_tokens=400 if mode == "comparison" else 200  # More tokens for comparison mode
            )
            
            arguments = KernelArguments(query=query, settings=execution_settings)
            
            result = await asyncio.wait_for(
                self.kernel.invoke_prompt(
                    prompt=datetime_prompt,
                    function_name=f"translate_datetime_{mode}",
                    plugin_name="datetime_agent",
                    arguments=arguments
                ),
                timeout=15.0
            )
            
            # Extract content from SK result
            if hasattr(result, 'value'):
                content = str(result.value[0].content) if isinstance(result.value, list) else str(result.value)
            else:
                content = str(result)
            
            content = content.strip()
            
            # 🔍 DEBUG: Log raw GPT response
            logger.info(f"🔍 DEBUG: Raw datetime agent response: {content}")
            print(f"🔍 DEBUG: Raw response: {content}")
            
            # Clean JSON markers
            if '```json' in content:
                content = content.split('```json')[1].split('```')[0].strip()
            elif '```' in content:
                content = content.split('```')[1].split('```')[0].strip()
            
            # Parse response based on mode
            response = json.loads(content)
            
            if mode == "single":
                return self._parse_single_datetime_response(response)
            else:  # mode == "comparison"
                return self._parse_comparison_datetime_response(response)
            
        except json.JSONDecodeError as e:
            logger.error(f"❌ Datetime agent JSON parse error: {e}")
            logger.error(f"Raw content: {content}")
            print(f"❌ ERROR: JSON parse failed - {e}")
            return None
            
        except Exception as e:
            logger.error(f"❌ Datetime translation failed: {e}")
            print(f"❌ ERROR: Datetime agent failed - {e}")
            return None
    
    def _build_single_datetime_prompt(self, current_date: str, current_year: int, query: str) -> str:
        """Build GPT prompt for single datetime extraction (existing behavior)."""
        return f"""You are an expert at converting natural language temporal expressions to ISO 8601 datetime ranges for satellite imagery queries.

CURRENT DATE: {current_date}
CURRENT YEAR: {current_year}

TASK: Extract any temporal information from the query and convert it to ISO 8601 format: "YYYY-MM-DD/YYYY-MM-DD"

CRITICAL RULES FOR YEAR/MONTH EXTRACTION:
1. **YEAR ONLY** (e.g., "2024", "from 2024", "in 2024"): Return FULL YEAR range
   - "2024" → "2024-01-01/2024-12-31"
   - "from 2024" → "2024-01-01/2024-12-31"
   - "in 2023" → "2023-01-01/2023-12-31"
   
2. **MONTH AND YEAR** (e.g., "October 2024", "September 2023"): Return FULL MONTH range
   - "October 2024" → "2024-10-01/2024-10-31"
   - "September 2023" → "2023-09-01/2023-09-30"
   - "June 2025" → "2025-06-01/2025-06-30"

3. **RELATIVE TIME** (calculate from current date):
   - "recent" → last 30 days
   - "last month" → previous calendar month
   - "last year" → previous calendar year
   - "two weeks ago" → 14 days before current date

4. **QUARTERS**: Q1=Jan-Mar, Q2=Apr-Jun, Q3=Jul-Sep, Q4=Oct-Dec
   - "Q3 2023" → "2023-07-01/2023-09-30"

5. **SEASONS**: Spring=Mar-May, Summer=Jun-Aug, Fall=Sep-Nov, Winter=Dec-Feb
   - "summer 2024" → "2024-06-01/2024-08-31"

6. **SPECIFIC DATES**: Convert both start and end dates
   - "October 29, 2012" → "2012-10-29/2012-10-30" (single day)
   - "near October 29, 2012" → "2012-10-20/2012-11-07" (±9 days window)
   - "around June 15, 2024" → "2024-06-10/2024-06-20" (±5 days window)

7. **NO TEMPORAL INFO**: Return "none"

⚠️ IMPORTANT: Extract the ACTUAL year mentioned, not the current year!
- "from 2024" means 2024, NOT {current_year}
- "in 2023" means 2023, NOT {current_year}

EXAMPLES:
Query: "Show me California wildfire modis data from 2024"
Response: {{"datetime_range": "2024-01-01/2024-12-31", "explanation": "Year only: 2024 (full year)"}}

Query: "Show me satellite imagery of NYC from October 2024"
Response: {{"datetime_range": "2024-10-01/2024-10-31", "explanation": "Month and year: October 2024"}}

Query: "Show me data from 2023"
Response: {{"datetime_range": "2023-01-01/2023-12-31", "explanation": "Year only: 2023 (full year)"}}

Query: "Recent satellite data for Seattle"
Response: {{"datetime_range": "2025-09-29/2025-10-29", "explanation": "Recent = last 30 days from {current_date}"}}

Query: "Show me imagery from Q3 2023"
Response: {{"datetime_range": "2023-07-01/2023-09-30", "explanation": "Q3 2023 = July-September 2023"}}

Query: "Elevation data for Colorado"
Response: {{"datetime_range": "none", "explanation": "No temporal information specified"}}

Query: "Show me summer 2024 imagery"
Response: {{"datetime_range": "2024-06-01/2024-08-31", "explanation": "Summer 2024 = June-August 2024"}}

Query: "Show images near October 29, 2012"
Response: {{"datetime_range": "2012-10-20/2012-11-07", "explanation": "'near October 29, 2012' = ±9 days window around specific date"}}

Query: "Atlantic City on October 29, 2012"
Response: {{"datetime_range": "2012-10-29/2012-10-30", "explanation": "Specific date: October 29, 2012 (single day)"}}

USER QUERY: "{query}"

Return ONLY a JSON object with "datetime_range" and "explanation". No additional text."""
    
    def _build_comparison_datetime_prompt(self, current_date: str, current_year: int, query: str) -> str:
        """Build GPT prompt for comparison datetime extraction (dual dates)."""
        return f"""You are an expert at extracting TWO separate temporal periods from natural language queries for before/after satellite imagery comparisons.

CURRENT DATE: {current_date}
CURRENT YEAR: {current_year}

TASK: Extract TWO distinct time periods (BEFORE and AFTER) from the query and convert both to ISO 8601 format.

RULES:
1. Identify the TWO time periods being compared:
   - Explicit: "January 1st vs January 3rd" → Extract both dates
   - Implicit: "from 2023 to 2025" → Decide if this is a range or two snapshots
   - ISO format: "2023-01-15 to 2024-01-15" → Use exact dates provided
2. For ISO date formats (YYYY-MM-DD), preserve the exact dates:
   - "2023-01-15 to 2024-01-15" → before: "2023-01-15/2023-01-16", after: "2024-01-15/2024-01-16"
   - "from 2023-01-15 to 2024-01-15" → Same as above (interpret as two snapshots)
3. For day-specific comparisons: Use tight date ranges (e.g., "2025-01-01/2025-01-02" for Jan 1)
4. For ambiguous ranges without specific dates (e.g., "2023 to 2025"):
   - BEFORE = Start period (e.g., "2023-01-01/2023-12-31" for full year 2023)
   - AFTER = End period (e.g., "2025-01-01/2025-12-31" for full year 2025)
   - Set "needs_clarification": true if too ambiguous
5. Handle temporal aggregation:
   - "Summer 2023 vs Summer 2025" → Two separate 3-month periods
   - "October 2024 vs December 2024" → Two separate month periods
6. Return "needs_clarification" if the query is too ambiguous (user needs to refine)

EXAMPLES:

Query: "Compare wildfire activity in Southern California between January 1st and January 3rd, 2025"
Response: {{
    "before": "2025-01-01/2025-01-02",
    "after": "2025-01-03/2025-01-04",
    "explanation": "Before: Jan 1, 2025 | After: Jan 3, 2025"
}}

Query: "Show me methane emissions over the Permian Basin from 2023 to 2025"
Response: {{
    "needs_clarification": true,
    "suggestion": "Please specify exact time periods. Do you want to compare a specific season or month? (e.g., 'Summer 2023 vs Summer 2025')",
    "fallback_before": "2023-01-01/2023-12-31",
    "fallback_after": "2025-01-01/2025-12-31",
    "explanation": "Ambiguous range - using full years as fallback"
}}

Query: "Analyze sea level change along the Atlantic coast between 2015 and 2025"
Response: {{
    "before": "2015-01-01/2015-12-31",
    "after": "2025-01-01/2025-12-31",
    "explanation": "Decade-long comparison using full year periods"
}}

Query: "Compare summer 2023 fire activity to summer 2025"
Response: {{
    "before": "2023-06-01/2023-08-31",
    "after": "2025-06-01/2025-08-31",
    "explanation": "Before: Summer 2023 (Jun-Aug) | After: Summer 2025 (Jun-Aug)"
}}

Query: "Show me fire spread from August 1 to August 15, 2024"
Response: {{
    "before": "2024-08-01/2024-08-02",
    "after": "2024-08-14/2024-08-16",
    "explanation": "Before: Aug 1, 2024 | After: Aug 15, 2024"
}}

Query: "Compare data from 2023-01-15 to 2024-01-15"
Response: {{
    "before": "2023-01-15/2023-01-16",
    "after": "2024-01-15/2024-01-16",
    "explanation": "Before: January 15, 2023 | After: January 15, 2024"
}}

USER QUERY: "{query}"

Return ONLY a JSON object with "before", "after", and "explanation". If ambiguous, include "needs_clarification", "suggestion", and fallback dates."""
    
    def _parse_single_datetime_response(self, response: Dict[str, Any]) -> Optional[str]:
        """Parse single datetime mode response (existing behavior)."""
        datetime_range = response.get("datetime_range")
        explanation = response.get("explanation", "")
        
        # 🔍 DEBUG: Log parsed response
        logger.info(f"🔍 DEBUG: Parsed datetime_range: {datetime_range}")
        logger.info(f"🔍 DEBUG: Explanation: {explanation}")
        print(f"🔍 DEBUG: Datetime range: {datetime_range}")
        print(f"🔍 DEBUG: Explanation: {explanation}")
        
        if datetime_range == "none" or not datetime_range:
            logger.info("🗓️ No temporal info → No datetime filter")
            print("🗓️ DEBUG: No temporal info found")
            return None
        
        logger.info(f"✅ Datetime translation: {datetime_range} ({explanation})")
        print(f"✅ DEBUG: AGENT 2.5 SUCCESS - {datetime_range}")
        print(f"🤖 DEBUG: =====================================")
        
        return datetime_range
    
    def _parse_comparison_datetime_response(self, response: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Parse comparison datetime mode response (dual dates)."""
        
        # Check if clarification is needed
        if response.get("needs_clarification"):
            logger.warning(f"⚠️ Ambiguous temporal query - clarification needed")
            print(f"⚠️ WARNING: Ambiguous temporal query")
            print(f"💡 Suggestion: {response.get('suggestion')}")
            
            # Use fallback dates if provided
            before = response.get("fallback_before")
            after = response.get("fallback_after")
            explanation = response.get("explanation", "Using fallback periods")
            
            if not before or not after:
                logger.error("❌ No fallback dates provided for ambiguous query")
                print("❌ ERROR: Cannot extract dates from ambiguous query")
                return None
            
            result = {
                "before": before,
                "after": after,
                "explanation": explanation,
                "needs_clarification": True,
                "suggestion": response.get("suggestion")
            }
        else:
            # Extract explicit before/after dates
            before = response.get("before")
            after = response.get("after")
            explanation = response.get("explanation", "")
            
            if not before or not after:
                logger.error("❌ Missing before or after datetime in comparison response")
                print("❌ ERROR: Missing before or after datetime")
                return None
            
            result = {
                "before": before,
                "after": after,
                "explanation": explanation,
                "needs_clarification": False
            }
        
        # 🔍 DEBUG: Log parsed response
        logger.info(f"🔍 DEBUG: Parsed BEFORE: {result['before']}")
        logger.info(f"🔍 DEBUG: Parsed AFTER: {result['after']}")
        logger.info(f"🔍 DEBUG: Explanation: {result['explanation']}")
        print(f"🔍 DEBUG: BEFORE: {result['before']}")
        print(f"🔍 DEBUG: AFTER: {result['after']}")
        print(f"🔍 DEBUG: Explanation: {result['explanation']}")
        
        if result.get("needs_clarification"):
            print(f"⚠️ CLARIFICATION NEEDED: {result.get('suggestion')}")
        
        logger.info(f"✅ Comparison datetime translation complete")
        print(f"✅ DEBUG: AGENT 2.5 SUCCESS (COMPARISON MODE)")
        print(f"🤖 DEBUG: =====================================")
        
        return result
    
    async def cloud_filtering_agent(self, query: str, collections: List[str]) -> Optional[Dict[str, Any]]:
        """
        🤖 AGENT 2.3: GPT-powered cloud filtering agent
        
        Detects EXPLICIT cloud cover mentions and builds appropriate STAC filter.
        This agent:
        1. Detects explicit cloud cover intent (clear, cloudless, cloudy, etc.)
        2. Determines appropriate threshold (25%, 50%, 75%)
        3. Checks collection support for cloud filtering
        4. Returns filter dict or None
        
        Args:
            query: User's natural language query
            collections: Selected collection IDs
        
        Returns:
            Dict with cloud filter or None if no explicit mention
            {
                "filter": {"eo:cloud_cover": {"lt": 25}},
                "threshold": 25,
                "reasoning": "User requested clear imagery",
                "applicable_collections": ["sentinel-2-l2a"]
            }
        """
        
        # 🔍 DEBUG: Log agent invocation
        logger.info(f"🤖 AGENT 2.3: cloud_filtering_agent invoked")
        print(f"🤖 DEBUG: ===== CLOUD FILTERING AGENT =====")
        print(f"🤖 DEBUG: Query: {query}")
        print(f"🤖 DEBUG: Collections: {collections}")
        
        # Import collection profile helpers
        from collection_profiles import supports_cloud_filtering, get_cloud_cover_property
        
        # Check which collections support cloud filtering
        filterable = [c for c in collections if supports_cloud_filtering(c)]
        non_filterable = [c for c in collections if not supports_cloud_filtering(c)]
        
        if not filterable:
            logger.info(f"☁️ No collections support cloud filtering: {collections}")
            print(f"☁️ DEBUG: No cloud-filterable collections")
            return None
        
        # Build GPT prompt for cloud intent detection
        cloud_prompt = f"""You are an expert at detecting cloud cover preferences in satellite imagery queries.

TASK: Determine if the user EXPLICITLY mentions cloud cover preferences, and if so, what threshold.

USER QUERY: "{query}"

EXPLICIT CLOUD MENTIONS:
- **Low/Clear**: "clear", "cloudless", "no clouds", "cloud-free", "clear sky", "minimal clouds"
  → Threshold: 25% (show only imagery with <25% cloud cover)

- **Medium**: "some clouds", "partly cloudy", "moderate clouds", "partial clouds"
  → Threshold: 50% (show imagery with <50% cloud cover)

- **High/Cloudy**: "cloudy", "overcast", "lots of clouds", "heavy clouds", "very cloudy"
  → Threshold: 75% (show imagery with <75% cloud cover)

- **No Mention**: User does NOT mention clouds at all
  → Return "none" (do not filter by cloud cover)

IMPORTANT:
- ONLY detect EXPLICIT mentions of cloud-related terms
- Do NOT infer cloud preferences from disaster type, urgency, or location
- If no cloud terms found, return "none"

EXAMPLES:

Query: "Show me clear satellite imagery of Seattle"
Response: {{"cloud_intent": "low", "threshold": 25, "reasoning": "User explicitly requested 'clear' imagery"}}

Query: "Show me satellite data for NYC"
Response: {{"cloud_intent": "none", "threshold": null, "reasoning": "No explicit cloud mention"}}

Query: "Show me cloudy imagery of the storm"
Response: {{"cloud_intent": "high", "threshold": 75, "reasoning": "User explicitly requested 'cloudy' imagery"}}

Return ONLY a JSON object with "cloud_intent", "threshold", and "reasoning". No additional text."""

        try:
            from semantic_kernel.functions.kernel_arguments import KernelArguments
            from semantic_kernel.connectors.ai.open_ai.prompt_execution_settings.azure_chat_prompt_execution_settings import AzureChatPromptExecutionSettings
            
            execution_settings = AzureChatPromptExecutionSettings(
                service_id="chat-completion",
                temperature=1.0,  # GPT-5 requires default temperature=1.0
                max_completion_tokens=150
            )
            
            arguments = KernelArguments(query=query, settings=execution_settings)
            
            result = await asyncio.wait_for(
                self.kernel.invoke_prompt(
                    prompt=cloud_prompt,
                    function_name="detect_cloud_intent",
                    plugin_name="cloud_agent",
                    arguments=arguments
                ),
                timeout=10.0
            )
            
            # Extract content
            if hasattr(result, 'value'):
                content = str(result.value[0].content) if isinstance(result.value, list) else str(result.value)
            else:
                content = str(result)
            
            content = content.strip()
            
            # 🔍 DEBUG: Log raw response
            logger.info(f"🔍 DEBUG: Raw cloud agent response: {content}")
            print(f"🔍 DEBUG: Raw response: {content}")
            
            # Clean JSON markers
            if '```json' in content:
                content = content.split('```json')[1].split('```')[0].strip()
            elif '```' in content:
                content = content.split('```')[1].split('```')[0].strip()
            
            # Parse response
            response = json.loads(content)
            cloud_intent = response.get("cloud_intent")
            threshold = response.get("threshold")
            reasoning = response.get("reasoning", "")
            
            # 🔍 DEBUG: Log parsed response
            logger.info(f"🔍 DEBUG: Cloud intent: {cloud_intent}, threshold: {threshold}")
            print(f"🔍 DEBUG: Intent: {cloud_intent}, Threshold: {threshold}")
            
            if cloud_intent == "none" or not threshold:
                logger.info(f"☁️ No explicit cloud mention → No filter")
                print(f"☁️ DEBUG: No cloud filtering needed")
                return None
            
            # Build cloud filter
            primary_collection = filterable[0]
            prop_name = get_cloud_cover_property(primary_collection)
            
            if not prop_name:
                logger.error(f"❌ Cannot get cloud property for {primary_collection}")
                return None
            
            cloud_filter = {
                "filter": {prop_name: {"lt": threshold}},
                "threshold": threshold,
                "reasoning": reasoning,
                "applicable_collections": filterable,
                "non_applicable_collections": non_filterable
            }
            
            logger.info(f"✅ Cloud filter: {prop_name} < {threshold}% ({reasoning})")
            print(f"✅ DEBUG: AGENT 2.3 SUCCESS - Cloud filter created")
            print(f"  - Property: {prop_name}")
            print(f"  - Threshold: < {threshold}%")
            print(f"  - Applies to: {filterable}")
            if non_filterable:
                print(f"  - Cannot apply to: {non_filterable}")
            print(f"🤖 DEBUG: ===================================")
            
            return cloud_filter
            
        except json.JSONDecodeError as e:
            logger.error(f"❌ Cloud agent JSON parse error: {e}")
            print(f"❌ ERROR: JSON parse failed - {e}")
            return None
            
        except Exception as e:
            logger.error(f"❌ Cloud filtering agent failed: {e}")
            print(f"❌ ERROR: Cloud agent failed - {e}")
            return None
    
    async def resolve_location_to_bbox(self, location_name: str, location_type: str = "region") -> Optional[List[float]]:
        """
        🎯 Use consolidated EnhancedLocationResolver
        
        Strategy order (via EnhancedLocationResolver):
        1. Predefined regions (highest accuracy)
        2. Azure Maps API (primary)  
        3. Mapbox (geographic specialist)
        4. Google Maps (comprehensive)
        5. Nominatim (fallback)
        
        Returns: [west, south, east, north] bounding box or None
        """
        logger.info(f"🔍 Resolving location via consolidated resolver: '{location_name}' (type: {location_type})")
        
        if not location_name:
            return None
        
        try:
            # Use the consolidated location resolver
            bbox = await self.location_resolver.resolve_location_to_bbox(location_name, location_type)
            
            if bbox:
                logger.info(f"✅ Consolidated resolver resolved: {location_name} → {bbox}")
                # Cache the result for performance
                self.location_cache.set(location_name, location_type, bbox)
                return bbox
            else:
                logger.warning(f"❌ Consolidated resolver could not resolve: {location_name}")
                return None
                
        except Exception as e:
            logger.error(f"❌ Error in consolidated location resolver for {location_name}: {e}")
            return None
    
    def _validate_bbox(self, bbox: List[float]) -> bool:
        """
        Validate bounding box coordinates
        
        Args:
            bbox: [west, south, east, north]
            
        Returns:
            True if valid, False otherwise
        """
        if not bbox or len(bbox) != 4:
            logger.warning(f"❌ Invalid bbox format: {bbox}")
            return False
        
        west, south, east, north = bbox
        
        # Check for None or NaN values
        if any(coord is None or coord != coord for coord in bbox):  # coord != coord checks for NaN
            logger.warning(f"❌ Bbox contains None or NaN: {bbox}")
            return False
        
        # Validate coordinate ranges
        if not (-180 <= west <= 180 and -180 <= east <= 180):
            logger.warning(f"❌ Invalid longitude range: west={west}, east={east}")
            return False
        
        if not (-90 <= south <= 90 and -90 <= north <= 90):
            logger.warning(f"❌ Invalid latitude range: south={south}, north={north}")
            return False
        
        # Ensure west < east and south < north (handle dateline crossing)
        if west >= east and not (west > 0 and east < 0):  # Allow dateline crossing
            logger.warning(f"❌ Invalid bbox: west ({west}) >= east ({east})")
            return False
        
        if south >= north:
            logger.warning(f"❌ Invalid bbox: south ({south}) >= north ({north})")
            return False
        
        logger.debug(f"✅ Bbox validation passed: {bbox}")
        return True
    
    async def _resolve_via_nominatim(self, location_name: str) -> Optional[List[float]]:
        """Use Nominatim (OpenStreetMap) API as fallback"""
        try:
            import aiohttp
            async with aiohttp.ClientSession() as session:
                url = "https://nominatim.openstreetmap.org/search"
                params = {
                    "q": location_name,
                    "format": "json",
                    "limit": 1,
                    "addressdetails": 1
                }
                headers = {"User-Agent": "EarthCopilot/1.0"}
                
                timeout = aiohttp.ClientTimeout(total=10)
                async with session.get(url, params=params, headers=headers, timeout=timeout) as response:
                    if response.status == 200:
                        data = await response.json()
                        if data:
                            result = data[0]
                            lat = float(result["lat"])
                            lon = float(result["lon"])
                            
                            # Convert to bounding box (add small buffer)
                            buffer = 0.1  # degrees
                            bbox = [lon - buffer, lat - buffer, lon + buffer, lat + buffer]
                            
                            logger.info(f"🗺️ Nominatim resolved {location_name}: {bbox}")
                            return bbox
        except Exception as e:
            logger.warning(f"Nominatim failed for {location_name}: {e}")
        return None
    
    async def _resolve_via_azure_maps(self, location_name: str) -> Optional[List[float]]:
        """Use Azure Maps API as fallback"""
        azure_maps_key = os.getenv("AZURE_MAPS_SUBSCRIPTION_KEY")
        if not azure_maps_key:
            logger.info("Azure Maps API key not available, skipping Azure Maps resolution")
            return None
            
        try:
            import aiohttp
            async with aiohttp.ClientSession() as session:
                url = "https://atlas.microsoft.com/search/address/json"
                params = {
                    "api-version": "1.0",
                    "subscription-key": azure_maps_key,
                    "query": location_name,
                    "limit": 1
                }
                
                timeout = aiohttp.ClientTimeout(total=15)
                async with session.get(url, params=params, timeout=timeout) as response:
                    if response.status == 200:
                        data = await response.json()
                        if data.get("results"):
                            result = data["results"][0]
                            
                            # Azure Maps returns viewport in different format
                            if "viewport" in result:
                                viewport = result["viewport"]
                                bbox = [
                                    viewport["topLeftPoint"]["lon"],
                                    viewport["btmRightPoint"]["lat"],
                                    viewport["btmRightPoint"]["lon"],
                                    viewport["topLeftPoint"]["lat"]
                                ]
                            else:
                                # Fallback to position with buffer
                                position = result["position"]
                                lat, lon = position["lat"], position["lon"]
                                buffer = 0.1
                                bbox = [lon - buffer, lat - buffer, lon + buffer, lat + buffer]
                            
                            logger.info(f"🗺️ Azure Maps resolved {location_name}: {bbox}")
                            return bbox
                    else:
                        logger.warning(f"Azure Maps API error {response.status}: {await response.text()}")
        except Exception as e:
            logger.warning(f"Azure Maps failed for {location_name}: {e}")
        return None
    
    async def _resolve_via_mapbox(self, location_name: str) -> Optional[List[float]]:
        """Use Mapbox Geocoding API as fallback"""
        mapbox_token = os.getenv("MAPBOX_ACCESS_TOKEN")
        if not mapbox_token:
            logger.info("Mapbox API token not available, skipping Mapbox resolution")
            return None
            
        try:
            import aiohttp
            async with aiohttp.ClientSession() as session:
                url = f"https://api.mapbox.com/geocoding/v5/mapbox.places/{location_name}.json"
                params = {"access_token": mapbox_token, "limit": 1}
                
                timeout = aiohttp.ClientTimeout(total=10)
                async with session.get(url, params=params, timeout=timeout) as response:
                    if response.status == 200:
                        data = await response.json()
                        if data.get("features"):
                            feature = data["features"][0]
                            if "bbox" in feature:
                                bbox = feature["bbox"]
                            else:
                                # Fallback to center coordinates with buffer
                                coords = feature["geometry"]["coordinates"]
                                lon, lat = coords[0], coords[1]
                                buffer = 0.1
                                bbox = [lon - buffer, lat - buffer, lon + buffer, lat + buffer]
                            
                            logger.info(f"🗺️ Mapbox resolved {location_name}: {bbox}")
                            return bbox
        except Exception as e:
            logger.warning(f"Mapbox failed for {location_name}: {e}")
        return None
    
    async def _resolve_via_semantic_kernel(self, location_name: str, location_type: str) -> Optional[List[float]]:
        """Use Azure OpenAI directly for geographic location resolution with enhanced debugging"""
        
        logger.info(f"🔧 SEMANTIC KERNEL DEBUG: Starting location resolution for '{location_name}'")
        
        # Ensure kernel is initialized
        await self._ensure_kernel_initialized()
        
        if not self._kernel_initialized:
            logger.error(f"❌ Azure OpenAI not available for location resolution: {location_name}")
            return None
        
        try:
            # 🎯 PURE API-BASED location resolution prompt (NO hardcoded coordinates)
            location_prompt = f"""You are a geographic expert with access to comprehensive global geographic knowledge. 

Analyze the location: {location_name}

Return ONLY valid JSON with precise bounding box coordinates based on your geographic knowledge:

Format: {{"bbox": [west_longitude, south_latitude, east_longitude, north_latitude], "confidence": 0.0_to_1.0}}

Guidelines:
- Use your comprehensive geographic knowledge to determine accurate coordinates
- Return bounding box in [west, south, east, north] format (decimal degrees)
- West/East: longitude values (-180 to +180, negative = west, positive = east)  
- South/North: latitude values (-90 to +90, negative = south, positive = north)
- Confidence: 0.9 for well-known places, 0.7 for regions, 0.5 for less certain locations
- Ensure west < east and south < north
- For cities: tight bounding box around urban area
- For states/provinces: encompass the full administrative boundary
- For countries: include the main territory boundaries

Location to analyze: {location_name}"""

            # Use Azure OpenAI directly with enhanced strategies
            azure_openai_endpoint = self.azure_openai_endpoint
            azure_openai_api_key = self.azure_openai_api_key
            model_name = self.model_name
            
            headers = {
                "Content-Type": "application/json",
                "api-key": azure_openai_api_key
            }
            
            # 🔄 Strategy 1: JSON mode with pure geographic knowledge
            payload_json = {
                "messages": [
                    {
                        "role": "system",
                        "content": "You are a geographic expert with comprehensive global knowledge. Return ONLY valid JSON with accurate bounding box coordinates for any requested location worldwide."
                    },
                    {
                        "role": "user",
                        "content": f"Provide accurate geographic bounding box coordinates for: {location_name}\n\nFormat: {{\"bbox\": [west_longitude, south_latitude, east_longitude, north_latitude], \"confidence\": confidence_score}}\n\nUse your geographic knowledge to determine precise coordinates."
                    }
                ],
                "max_completion_tokens": 150,
                "temperature": 0.0,
                "response_format": {"type": "json_object"}
            }
            
            # 🔄 Strategy 2: Simple structured prompt  
            payload_simple = {
                "messages": [
                    {
                        "role": "user",
                        "content": location_prompt
                    }
                ],
                "max_completion_tokens": 100,
                "temperature": 0.0
            }
            
            strategies = [
                ("JSON Mode", payload_json),
                ("Simple Prompt", payload_simple)
            ]
            
            async with aiohttp.ClientSession() as session:
                url = f"{azure_openai_endpoint}/openai/deployments/{model_name}/chat/completions?api-version=2024-06-01"
                timeout = aiohttp.ClientTimeout(total=30)
                
                # 🔄 Try multiple strategies in order
                for strategy_name, payload in strategies:
                    try:
                        logger.info(f"🔄 Trying location resolution strategy: {strategy_name} for {location_name}")
                        
                        async with session.post(url, headers=headers, json=payload, timeout=timeout) as response:
                            logger.info(f"🌐 Azure OpenAI response status: {response.status} for {strategy_name}")
                            
                            if response.status == 200:
                                result = await response.json()
                                
                                # Enhanced response processing
                                if "choices" in result and result["choices"]:
                                    content = result["choices"][0]["message"]["content"]
                                    logger.info(f"🔍 Raw Azure OpenAI content ({strategy_name}): '{content}'")
                                    
                                    # Check if response is empty
                                    if not content or content.strip() == "":
                                        logger.warning(f"⚠️ Empty response from Azure OpenAI for {location_name} with {strategy_name}")
                                        continue  # Try next strategy
                                        
                                    # Enhanced JSON parsing
                                    try:
                                        # Clean up any markdown formatting
                                        cleaned_content = content.strip()
                                        if '```json' in cleaned_content:
                                            cleaned_content = cleaned_content.split('```json')[1].split('```')[0]
                                        elif '```' in cleaned_content:
                                            cleaned_content = cleaned_content.split('```')[1].split('```')[0]
                                        
                                        cleaned_content = cleaned_content.strip()
                                        logger.info(f"🧹 Cleaned content: '{cleaned_content}'")
                                        
                                        if not cleaned_content:
                                            logger.warning(f"⚠️ Content empty after cleaning for {location_name} with {strategy_name}")
                                            continue  # Try next strategy
                                        
                                        location_data = json.loads(cleaned_content)
                                        bbox = location_data.get('bbox')
                                        confidence = location_data.get('confidence', 0.0)
                                        
                                        logger.info(f"🔍 Parsed JSON - bbox: {bbox}, confidence: {confidence}")
                                        
                                        if bbox and len(bbox) == 4 and confidence > 0.5:
                                            west, south, east, north = bbox
                                            
                                            # Validate coordinates
                                            if (-180 <= west <= 180 and -180 <= east <= 180 and 
                                                -90 <= south <= 90 and -90 <= north <= 90 and
                                                west < east and south < north):
                                                
                                                logger.info(f"✅ Azure OpenAI successfully resolved {location_name}: {bbox} (confidence: {confidence:.2f}, strategy: {strategy_name})")
                                                return bbox
                                            else:
                                                logger.warning(f"⚠️ Invalid coordinates from Azure OpenAI for {location_name}: {bbox} (strategy: {strategy_name})")
                                        else:
                                            logger.warning(f"⚠️ Low confidence or invalid bbox from Azure OpenAI for {location_name}: {location_data} (strategy: {strategy_name})")
                                            
                                    except json.JSONDecodeError as e:
                                        logger.error(f"❌ Failed to parse Azure OpenAI response for {location_name} with {strategy_name}: '{cleaned_content}'")
                                        logger.error(f"JSON error: {e}")
                                        continue  # Try next strategy
                                else:
                                    logger.warning(f"⚠️ No choices in Azure OpenAI response for {location_name} with {strategy_name}")
                            else:
                                error_text = await response.text()
                                logger.error(f"❌ Azure OpenAI API error {response.status} for {strategy_name}: {error_text}")
                                continue  # Try next strategy
                                
                    except asyncio.TimeoutError:
                        logger.error(f"⏰ Azure OpenAI timeout resolving {location_name} with {strategy_name}")
                        continue  # Try next strategy
                    except Exception as e:
                        logger.error(f"❌ Azure OpenAI error resolving {location_name} with {strategy_name}: {e}")
                        continue  # Try next strategy
                
                # All strategies failed
                logger.error(f"❌ ALL Azure OpenAI strategies failed for {location_name}")
            
        except Exception as e:
            logger.error(f"❌ Critical error in Azure OpenAI resolution for {location_name}: {e}")
        
        return None
    
    # No more predefined regions or Nominatim fallbacks - pure Semantic Kernel approach
    
    def select_collections(self, entities: Dict[str, Any]) -> List[str]:
        """
        🚀 ENHANCED: Dynamic collection selection using collection profiles
        
        This method now dynamically maps queries to collections using:
        1. Explicit satellite platform detection (HIGHEST PRIORITY)
        2. Specific data type detection (fire, elevation, etc.)
        3. Default to satellite imagery for general queries
        4. Collection profiles metadata (if available)
        5. Fallback to static mappings
        """
        
        collections = []
        query_text = entities.get("original_query", "").lower()
        analysis_intent = entities.get("analysis_intent", {}).get("type", "")
        analysis_intent = entities.get("analysis_intent", {}).get("type", "")
        
        # 🛰️ EXPLICIT SATELLITE PLATFORM DETECTION (HIGHEST PRIORITY)
        if "landsat" in query_text:
            logger.info(f"🛰️ LANDSAT PLATFORM DETECTED in query: {query_text}")
            return ["landsat-c2-l2"]
        
        if "sentinel-2" in query_text or ("sentinel" in query_text and "sar" not in query_text and "radar" not in query_text):
            logger.info(f"🛰️ SENTINEL-2 OPTICAL PLATFORM DETECTED in query: {query_text}")
            return ["sentinel-2-l2a"]
        
        if "sentinel-1" in query_text or ("sentinel" in query_text and any(keyword in query_text for keyword in ["sar", "radar"])):
            logger.info(f"🛰️ SENTINEL-1 SAR PLATFORM DETECTED in query: {query_text}")
            return ["sentinel-1-grd"]
        
        if "modis" in query_text:
            logger.info(f"🛰️ MODIS PLATFORM DETECTED in query: {query_text}")
            # Context-specific MODIS collections
            if any(fire_word in query_text for fire_word in ["fire", "thermal", "anomal", "heat", "burn"]):
                return ["modis-14A1-061", "modis-14A2-061"]
            elif any(veg_word in query_text for veg_word in ["vegetation", "ndvi", "greenness"]):
                return ["modis-13Q1-061", "modis-13A1-061"]
            else:
                return ["modis-09A1-061"]  # General MODIS optical
        
        if "aster" in query_text:
            logger.info(f"🛰️ ASTER PLATFORM DETECTED in query: {query_text}")
            return ["aster-l1t"]
        
        if "goes" in query_text:
            logger.info(f"🛰️ GOES PLATFORM DETECTED in query: {query_text}")
            return ["goes-cmi"]
        
        if any(keyword in query_text for keyword in ["hls", "harmonized"]):
            logger.info(f"🛰️ HLS PLATFORM DETECTED in query: {query_text}")
            return ["hls2-s30", "hls2-l30"]  # Harmonized Landsat Sentinel
        
        if "naip" in query_text or "high resolution" in query_text:
            logger.info(f"🛰️ NAIP HIGH-RES PLATFORM DETECTED in query: {query_text}")
            return ["naip"]
        
        # 🛰️ ENHANCED SATELLITE DATA DETECTION (includes various satellite data requests)
        satellite_keywords = [
            "satellite map", "satellite imagery", "satellite data", "satellite image",
            "optical imagery", "rgb", "true color", "earth observation", "remote sensing"
        ]
        if any(keyword in query_text for keyword in satellite_keywords):
            logger.info(f"🛰️ Detected satellite data query: {query_text}")
            # Prioritize best satellite collections: Landsat (proven working) + Sentinel-2
            return self._get_dynamic_collections_by_category("optical") or ["landsat-c2-l2", "sentinel-2-l2a", "naip"]
        
        # 🔥 MODIS SPECIFIC: Check for MODIS keywords first (highest priority)
        if "modis" in query_text:
            logger.info(f"🔥 MODIS SPECIFIC DETECTED in query: {query_text}")
            if any(fire_word in query_text for fire_word in ["fire", "thermal", "anomal", "heat", "burn"]):
                logger.info("🔥 MODIS fire/thermal detected - using MODIS fire collections")
                return ["modis-14A1-061", "modis-14A2-061", "modis-MCD64A1-061"]
            elif "ndvi" in query_text:
                logger.info("🌿 MODIS NDVI specifically detected")
                return ["modis-13Q1-061", "modis-13A1-061"]  # Only NDVI collections for NDVI queries
            elif any(veg_word in query_text for veg_word in ["vegetation", "greenness", "leaf"]):
                logger.info("🌿 MODIS vegetation detected")
                return ["modis-13Q1-061", "modis-13A1-061", "modis-15A2H-061", "modis-17A2H-061"]
            elif any(temp_word in query_text for temp_word in ["temperature", "lst", "surface temperature"]):
                logger.info("🌡️ MODIS land surface temperature detected")
                return ["modis-11A1-061"]
            elif any(snow_word in query_text for snow_word in ["snow", "ice", "snow cover"]):
                logger.info("❄️ MODIS snow/ice detected")
                return ["modis-10A1-061", "modis-10A2-061"]
            elif any(reflectance_word in query_text for reflectance_word in ["reflectance", "surface reflectance", "optical"]):
                logger.info("🌍 MODIS surface reflectance detected")
                return ["modis-09A1-061", "modis-09Q1-061"]
            else:
                logger.info("🔥 General MODIS query - defaulting to fire collections")
                return ["modis-14A1-061", "modis-14A2-061", "modis-MCD64A1-061"]
        
        # 🔥 THERMAL: Check for thermal infrared keywords (Landsat specific)
        if any(thermal_word in query_text for thermal_word in ["thermal", "infrared", "lwir"]) and "landsat" in query_text:
            logger.info(f"🔥 LANDSAT THERMAL INFRARED DETECTED in query: {query_text}")
            return ["landsat-c2-l2"]
        
        # 🏔️ ELEVATION/DEM: Check for elevation keywords (highest priority after thermal)
        elevation_keywords = ["elevation", "dem", "topography", "terrain", "altitude", "height", "slope", "contour"]
        if any(elev_word in query_text for elev_word in elevation_keywords):
            logger.info(f"🏔️ ELEVATION/DEM DETECTED in query: {query_text}")
            return self._get_dynamic_collections_by_category("elevation") or ["cop-dem-glo-30", "cop-dem-glo-90", "nasadem"]
        
        # 🔥 FIRE/WILDFIRE detection (non-MODIS)
        if any(keyword in query_text for keyword in ["fire", "wildfire", "burn"]) and "modis" not in query_text:
            logger.info(f"🔥 General fire detection (non-MODIS): {query_text}")
            return self._get_dynamic_collections_by_category("fire") or ["modis-14A1-061", "modis-14A2-061", "viirs-14A1-001"]
        
        # 🌊 WATER/FLOOD detection  
        if any(keyword in query_text for keyword in ["flood", "water", "inundation", "hurricane"]):
            return self._get_dynamic_collections_by_category("sar") or ["sentinel-1-grd", "sentinel-2-l2a"]
        
        # 🌿 NDVI SPECIFIC detection (highest priority for NDVI queries)
        if "ndvi" in query_text:
            logger.info(f"🌿 NDVI SPECIFIC DETECTED in query: {query_text}")
            return ["modis-13Q1-061", "modis-13A1-061"]  # Only NDVI collections for NDVI queries
        
        # 🌿 VEGETATION detection (general vegetation analysis)
        if any(keyword in query_text for keyword in ["vegetation", "forest", "agriculture", "crop"]):
            collections = self._get_dynamic_collections_by_category("vegetation") or ["sentinel-2-l2a", "landsat-c2-l2", "modis-13Q1-061"]
            return self._prioritize_featured_collections(collections)
        
        # 🌡️ CLIMATE/WEATHER detection
        if any(keyword in query_text for keyword in ["climate", "weather", "temperature", "precipitation", "rain"]):
            collections = self._get_dynamic_collections_by_category("climate") or ["era5-pds", "era5-land", "daymet-daily-na"]
            return self._prioritize_featured_collections(collections)
        
        # 🌊 OCEAN detection
        if any(keyword in query_text for keyword in ["ocean", "sea", "marine", "coastal"]):
            collections = self._get_dynamic_collections_by_category("ocean") or ["modis-oc", "modis-sst", "sentinel-2-l2a"]
            return self._prioritize_featured_collections(collections)
        
        # ❄️ SNOW/ICE detection
        if any(keyword in query_text for keyword in ["snow", "ice", "glacier"]):
            collections = self._get_dynamic_collections_by_category("snow") or ["modis-10A1-061", "viirs-snow-cover"]
            return self._prioritize_featured_collections(collections)
        
        # 🌬️ AIR QUALITY detection
        if any(keyword in query_text for keyword in ["air quality", "pollution", "emission", "aerosol"]):
            collections = self._get_dynamic_collections_by_category("air_quality") or ["sentinel-5p-l2", "tropomi-no2"]
            return self._prioritize_featured_collections(collections)
        
        # 🌍 DEFAULT TO SATELLITE IMAGERY for general geographic queries
        logger.info(f"🛰️ No specific data type detected - defaulting to satellite imagery for query: {query_text}")
        collections = self._get_dynamic_collections_by_category("optical") or ["landsat-c2-l2", "sentinel-2-l2a", "naip"]
        return self._prioritize_featured_collections(collections)
    
    def _prioritize_featured_collections(self, collections: List[str]) -> List[str]:
        """
        🌟 Prioritize Featured Datasets for optimal rendering quality
        
        Sorts collections to put Featured Datasets first, ensuring:
        - Better rendering quality (95-100% vs 60-80%)
        - Faster tile selection
        - More vivid and accurate visualization
        
        Args:
            collections: List of collection IDs to prioritize
            
        Returns:
            Sorted list with featured collections first
        """
        if not FEATURED_COLLECTIONS:
            return collections
        
        # Separate featured from non-featured
        featured = [c for c in collections if c in FEATURED_COLLECTIONS]
        non_featured = [c for c in collections if c not in FEATURED_COLLECTIONS]
        
        # Featured collections first, then non-featured
        prioritized = featured + non_featured
        
        if featured:
            logger.info(f"🌟 Prioritized {len(featured)} featured collections: {featured}")
            if non_featured:
                logger.info(f"📊 Also included {len(non_featured)} non-featured collections: {non_featured}")
        
        return prioritized
    
    def _get_dynamic_collections_by_category(self, category: str) -> Optional[List[str]]:
        """
        🎯 Dynamic collection selection using collection profiles
        
        Args:
            category: Category to search for (optical, sar, elevation, etc.)
            
        Returns:
            List of collection IDs matching the category
        """
        if not PROFILES_AVAILABLE:
            logger.debug(f"Collection profiles not available, using static mapping for {category}")
            return None
        
        matching_collections = []
        
        # Search through collection profiles to find matching categories
        for collection_id, profile in COLLECTION_PROFILES.items():
            profile_category = profile.get("category", "").lower()
            
            # Direct category match
            if profile_category == category.lower():
                matching_collections.append(collection_id)
            
            # Special category mappings
            elif category == "thermal" and "thermal" in profile.get("visualization", {}).get("assets", {}):
                matching_collections.append(collection_id)
            elif category == "elevation" and profile_category in ["dem", "elevation", "topography"]:
                matching_collections.append(collection_id)
            elif category == "fire" and (profile_category == "fire" and "modis" in collection_id):
                matching_collections.append(collection_id)
            elif category == "vegetation" and profile_category in ["vegetation", "ndvi", "land_cover"]:
                matching_collections.append(collection_id)
            elif category == "climate" and profile_category in ["climate", "weather", "meteorological"]:
                matching_collections.append(collection_id)
            elif category == "ocean" and profile_category in ["ocean", "marine", "sea"]:
                matching_collections.append(collection_id)
            elif category == "snow" and profile_category in ["snow", "ice", "cryosphere"]:
                matching_collections.append(collection_id)
            elif category == "air_quality" and profile_category in ["atmospheric", "air_quality", "pollution"]:
                matching_collections.append(collection_id)
        
        if matching_collections:
            logger.info(f"✅ Dynamic mapping found {len(matching_collections)} collections for {category}: {matching_collections[:5]}")
            # Prioritize featured collections in dynamic results
            prioritized = self._prioritize_featured_collections(matching_collections)
            return prioritized[:5]  # Limit to top 5 collections (featured first)
        else:
            logger.debug(f"No dynamic collections found for category: {category}")
            return None
            collections = ["landsat-c2-l2"]  # Only Landsat for thermal infrared
            logger.info(f"🔥 Selected thermal collections: {collections}")
            return collections[:3]  # Early return for thermal infrared
        
        # 🏔️ ELEVATION/DEM: Check for elevation keywords first (highest priority after thermal)
        elevation_keywords = ["elevation", "dem", "topography", "terrain", "altitude", "height", "slope", "contour"]
        if any(elev_word in query_text for elev_word in elevation_keywords):
            logger.info(f"🏔️ ELEVATION/DEM DETECTED in query: {query_text}")
            collections = ["cop-dem-glo-30", "cop-dem-glo-90", "nasadem", "3dep-seamless"]
            logger.info(f"🏔️ Selected elevation collections: {collections}")
            return collections[:3]  # Early return for elevation data
        
        # Match to comprehensive collection categories and subcategories
        for category, config in self.collection_mappings.items():
            # Check subcategory names as keywords (e.g., "thermal_infrared", "wildfire", etc.)
            for subcategory, subcollections in config.items():
                # Convert subcategory name to searchable keywords
                subcategory_keywords = subcategory.replace("_", " ").split()
                if any(keyword in query_text for keyword in subcategory_keywords):
                    logger.debug(f"Found {category}->{subcategory} match for keywords: {subcategory_keywords}")
                    if isinstance(subcollections, list):
                        collections.extend(subcollections)
                    elif isinstance(subcollections, dict):
                        # Handle nested structure like disaster categories
                        collections.extend(subcollections.get("primary", []))
                        if analysis_intent in ["impact_assessment", "damage_analysis"]:
                            collections.extend(subcollections.get("secondary", []))
                    break
            if collections:  # If we found a match, stop searching
                break
        
        # Handle specific damage indicators and refinements
        damage_indicators = entities.get("damage_indicators", {})
        
        if damage_indicators.get("blue_tarp"):
            # Very high resolution needed - prioritize
            collections = ["naip", "sentinel-2-l2a"] + collections
        
        if damage_indicators.get("flooding"):
            # SAR is critical for flood detection
            if "sentinel-1-grd" not in collections:
                collections.insert(0, "sentinel-1-grd")
        
        if damage_indicators.get("fire_damage"):
            # Thermal detection is key
            thermal_collections = ["modis-14A1-061", "modis-14A2-061", "modis-MCD64A1-061"]
            collections = thermal_collections + collections
        
        # Analysis intent refinements for high-resolution needs
        if analysis_intent in ["impact_assessment", "damage_analysis", "detailed_monitoring"]:
            # Ensure high-resolution optical data is available
            if not any(col in collections for col in ["sentinel-2-l2a", "naip"]):
                collections.insert(0, "sentinel-2-l2a")
        
        # Remove duplicates while preserving priority order
        seen = set()
        unique_collections = []
        for collection in collections:
            if collection not in seen:
                seen.add(collection)
                unique_collections.append(collection)
        
        # Default collections if none selected
        if not unique_collections:
            unique_collections = ["sentinel-2-l2a", "landsat-c2-l2"]
        
        # Limit to reasonable number for performance
        return unique_collections[:3]
    
    def _calculate_spatial_overlap(self, bbox1: List[float], bbox2: List[float]) -> float:
        """Calculate the percentage overlap between two bounding boxes
        
        This is critical for spatial filtering: we want to know if a tile/image (bbox2)
        is meaningfully inside the requested region (bbox1).
        
        KEY FIX: Calculate overlap as percentage of the TILE area (bbox2), not the 
        requested region (bbox1). Otherwise, a tile fully inside California shows only 
        2-3% overlap because California is huge compared to a single tile!
        
        Args:
            bbox1: [west, south, east, north] - requested region (e.g., California)
            bbox2: [west, south, east, north] - STAC result bbox (e.g., HLS tile)
            
        Returns:
            Float between 0.0-1.0 representing what fraction of the TILE overlaps the requested region
        """
        if not bbox1 or not bbox2 or len(bbox1) != 4 or len(bbox2) != 4:
            return 0.0
            
        # Calculate intersection bounds
        west = max(bbox1[0], bbox2[0])
        south = max(bbox1[1], bbox2[1]) 
        east = min(bbox1[2], bbox2[2])
        north = min(bbox1[3], bbox2[3])
        
        # No overlap if intersection is invalid
        if west >= east or south >= north:
            return 0.0
            
        # Calculate areas
        intersection_area = (east - west) * (north - south)
        tile_area = (bbox2[2] - bbox2[0]) * (bbox2[3] - bbox2[1])  # FIX: Use tile area, not requested area
        
        if tile_area <= 0:
            return 0.0
            
        # Return overlap as percentage of TILE area (what fraction of the tile is inside the requested region)
        overlap = intersection_area / tile_area
        return min(overlap, 1.0)  # Cap at 100%
    
    def _filter_stac_results_by_spatial_overlap(self, stac_results: Dict[str, Any], 
                                               requested_bbox: Optional[List[float]], 
                                               min_overlap: float = 0.1) -> Dict[str, Any]:
        """Filter STAC results to only include those with meaningful spatial overlap
        
        Args:
            stac_results: STAC API response with features
            requested_bbox: The user's requested geographic region
            min_overlap: Minimum overlap percentage (0.1 = 10%)
            
        Returns:
            Filtered STAC results with only relevant features
        """
        if not requested_bbox or not stac_results.get('features'):
            return stac_results
            
        logger.info(f"🔍 Filtering STAC results for spatial overlap with {requested_bbox}")
        
        filtered_features = []
        total_features = len(stac_results['features'])
        
        for feature in stac_results['features']:
            feature_bbox = feature.get('bbox')
            if not feature_bbox:
                continue
                
            overlap = self._calculate_spatial_overlap(requested_bbox, feature_bbox)
            
            if overlap >= min_overlap:
                logger.debug(f"✅ Including feature {feature.get('id', 'unknown')} with {overlap:.1%} overlap")
                filtered_features.append(feature)
            else:
                logger.debug(f"❌ Filtering out feature {feature.get('id', 'unknown')} with {overlap:.1%} overlap")
        
        filtered_count = len(filtered_features)
        logger.info(f"🎯 Spatial filtering: {filtered_count}/{total_features} features kept (min {min_overlap:.1%} overlap)")
        
        # Create filtered results
        filtered_results = dict(stac_results)
        filtered_results['features'] = filtered_features
        
        return filtered_results
    
    def _filter_stac_results_by_cloud_cover(self, stac_results: Dict[str, Any], 
                                            max_cloud_cover: Optional[int] = None,
                                            collection_id: Optional[str] = None) -> Dict[str, Any]:
        """
        Client-side cloud cover filtering as a safety net.
        
        Even if STAC API accepts the cloud cover filter in the query, some collections
        might ignore it or use different property names. This ensures we always filter
        results to match user's cloud cover intent.
        
        Uses collection_profiles to intelligently determine the correct property name
        for each collection, avoiding blind trial-and-error.
        
        Args:
            stac_results: STAC API response with features
            max_cloud_cover: Maximum cloud cover percentage (0-100), None to skip filtering
            collection_id: Optional collection ID to lookup correct property name
            
        Returns:
            Filtered STAC results with only features meeting cloud cover requirement
        """
        if max_cloud_cover is None or not stac_results.get('features'):
            return stac_results
        
        logger.info(f"☁️ Client-side cloud cover filtering: ≤{max_cloud_cover}%")
        
        # Import collection profile helper
        from collection_profiles import get_cloud_cover_property
        
        # Build prioritized list of property names to check
        property_names_to_try = []
        
        # If collection specified, try its specific property name first
        if collection_id:
            collection_prop = get_cloud_cover_property(collection_id)
            if collection_prop:
                property_names_to_try.append(collection_prop)
                logger.debug(f"ℹ️ Collection {collection_id} uses property: {collection_prop}")
        
        # Add common variants as fallback
        for prop in ['eo:cloud_cover', 'cloud_cover', 'cloudCover', 'CLOUD_COVER']:
            if prop not in property_names_to_try:
                property_names_to_try.append(prop)
        
        filtered_features = []
        total_features = len(stac_results['features'])
        cloud_covers = []
        
        for feature in stac_results['features']:
            props = feature.get('properties', {})
            
            # Try property names in priority order
            cloud_cover = None
            found_property = None
            for prop_name in property_names_to_try:
                if prop_name in props:
                    cloud_cover = props[prop_name]
                    found_property = prop_name
                    break
            
            # If no cloud cover metadata, assume it passes (SAR, DEM, etc. don't have cloud cover)
            if cloud_cover is None:
                logger.debug(f"ℹ️ No cloud cover metadata for feature {feature.get('id', 'unknown')}, including by default")
                filtered_features.append(feature)
                continue
            
            cloud_covers.append(cloud_cover)
            
            # Filter based on threshold
            if cloud_cover <= max_cloud_cover:
                logger.debug(f"✅ Including feature {feature.get('id', 'unknown')} with {cloud_cover}% cloud cover")
                filtered_features.append(feature)
            else:
                logger.debug(f"❌ Filtering out feature {feature.get('id', 'unknown')} with {cloud_cover}% cloud cover (exceeds {max_cloud_cover}%)")
        
        filtered_count = len(filtered_features)
        
        # Log statistics
        if cloud_covers:
            avg_cloud = sum(cloud_covers) / len(cloud_covers)
            min_cloud = min(cloud_covers)
            max_cloud = max(cloud_covers)
            logger.info(f"☁️ Cloud cover stats: avg={avg_cloud:.1f}%, min={min_cloud:.1f}%, max={max_cloud:.1f}%")
        
        logger.info(f"🎯 Cloud cover filtering: {filtered_count}/{total_features} features kept (≤{max_cloud_cover}%)")
        
        # Create filtered results
        filtered_results = dict(stac_results)
        filtered_results['features'] = filtered_features
        
        return filtered_results

    async def _detect_cloud_cover_intent(self, query_text: str) -> Optional[Dict[str, Any]]:
        """
        Detect EXPLICIT cloud cover mentions in user query.
        
        ONLY returns a threshold if user explicitly mentions cloud cover terms.
        Does NOT infer cloud preferences from urgency, disaster type, or analysis intent.
        
        Returns:
            Dict with threshold and reasoning if explicit cloud mention found, None otherwise
            - threshold: int (0-100, percentage for eo:cloud_cover filter)
            - reasoning: str (explanation)
        """
        
        query_lower = query_text.lower()
        
        # EXPLICIT low cloud / clear sky requests → 25% or less
        if any(term in query_lower for term in [
            'low cloud', 'no cloud', 'clear', 'cloudless', 
            'minimal cloud', 'cloud-free', 'without clouds',
            'clear sky', 'clear skies', 'no clouds'
        ]):
            return {
                "threshold": 25, 
                "reasoning": "User explicitly requested low cloud/clear imagery"
            }
        
        # EXPLICIT medium cloud requests → around 50%
        elif any(term in query_lower for term in [
            'medium cloud', 'some cloud', 'partly cloudy', 
            'moderate cloud', 'partial cloud', 'some clouds'
        ]):
            return {
                "threshold": 50, 
                "reasoning": "User explicitly requested medium cloud coverage"
            }
        
        # EXPLICIT high cloud / cloudy requests → 75% or more
        elif any(term in query_lower for term in [
            'cloudy', 'overcast', 'high cloud', 'heavy cloud',
            'with clouds', 'lots of clouds', 'very cloudy'
        ]):
            return {
                "threshold": 75, 
                "reasoning": "User explicitly requested high cloud/cloudy imagery"
            }
        
        # NO explicit cloud mention → return None (do not add cloud filter)
        else:
            return None
    
    async def translate_query(self, natural_query: str, pin_location: Optional[Dict[str, float]] = None) -> Dict[str, Any]:
        """
        Main translation method with comprehensive error handling and GEOINT routing.
        
        Location Priority Logic:
        1. If pin_location provided AND query contains new location → Use query location (clear pin)
        2. If pin_location provided AND query has NO new location → Use pin coordinates
        3. If no pin_location → Extract location from query text
        
        Args:
            natural_query: User's natural language query
            pin_location: Optional pin coordinates {'lat': float, 'lng': float}
        
        Returns:
            Dictionary with STAC parameters and processing metadata
        """
        
        # Initialize analysis variable at the start to prevent scope issues
        analysis = {"needs_clarification": False, "quality_score": 0.8}
        
        try:
            # ========================================================================
            # 🚀 PERFORMANCE OPTIMIZATION: Parallel Classification and Collection Mapping
            # ========================================================================
            # These two agents are independent - classification determines intent,
            # collection mapping determines data sources. Running them in parallel
            # reduces latency by ~50%
            logger.info("🚀 Running classification and collection mapping IN PARALLEL...")
            
            classification_task = self.classify_query_intent_unified(natural_query)
            collection_task = self.collection_mapping_agent(natural_query)
            
            classification, collections = await asyncio.gather(
                classification_task,
                collection_task
            )
            
            logger.info(f"✅ PARALLEL PHASE 1 complete:")
            logger.info(f"   - Classification: intent_type={classification.get('intent_type')}, modules={classification.get('modules', [])}")
            logger.info(f"   - Collections: Selected {len(collections)} collection(s)")
            
            # ========================================================================
            # 🤖 AGENT 2: Build STAC query with collection-specific rules
            # ========================================================================
            
            # AGENT 2: Build STAC query with collection-specific rules
            logger.info("🤖 Starting AGENT 2: STAC Query Building")
            stac_query = await self.build_stac_query_agent(natural_query, collections)
            logger.info(f"✅ AGENT 2 complete: Built STAC query")
            
            # ========================================================================
            # Extract bbox and location_name from Agent 2's response
            # ========================================================================
            
            bbox = stac_query.get("bbox")
            location_name = stac_query.get("location_name")  # Agent 2 now provides this
            
            # === PIN LOCATION PRIORITY LOGIC ===
            query_has_location = (bbox is not None)
            
            if pin_location and query_has_location:
                # User specified NEW location in query → clear pin, use query location
                logger.info(f"⚠️ New location detected in query - pin will be overridden")
                logger.info(f"📍 Using query location instead of pin")
                pin_location = None  # Clear pin
            
            if pin_location:
                # Pin is active and no new location in query → use pin coordinates
                lat = pin_location['lat']
                lng = pin_location['lng']
                location_name = f"Pin location ({lat:.4f}, {lng:.4f})"
                bbox = self._create_pin_bbox(lat, lng, radius_miles=5)
                
                logger.info(f"📍 Using pin coordinates: {location_name}")
                logger.info(f"📦 Pin bbox (5mi radius): {bbox}")
                
                # Override agent's bbox with pin bbox
                stac_query["bbox"] = bbox
            
            # ========================================================================
            # Create entities dict for compatibility with downstream code
            # ========================================================================
            
            # Build minimal entities structure for GEOINT and other legacy code
            entities = {
                "location": {
                    "name": location_name,
                    "type": "region",
                    "confidence": 0.9
                },
                "temporal": {},
                "disaster": {},
                "damage_indicators": {},
                "analysis_intent": {},
                "original_query": natural_query,
                "collections": collections,
                "stac_query": stac_query
            }
            
            if pin_location:
                entities['pin_location'] = {
                    'lat': pin_location['lat'],
                    'lng': pin_location['lng'],
                    'bbox': bbox,
                    'radius_miles': 50
                }
            
            # ========================================================================
            # Handle module-based processing based on unified classification
            # ========================================================================
            
            # Check if any modules should be executed (GEOINT or map display)
            modules_to_execute = classification.get('modules', [])
            if modules_to_execute:
                logger.info(f"🎯 Classification identified {len(modules_to_execute)} module(s): {modules_to_execute}")
                
                # Determine if GEOINT processing is needed
                geoint_modules = [m for m in modules_to_execute if m.startswith('geoint_')]
                if geoint_modules:
                    logger.info(f"🎯 GEOINT modules detected: {geoint_modules}")
                    logger.info(f"🎯 FORCING HYBRID MODE for GEOINT query")
                    
                    # Flag for GEOINT enhancement (for downstream compatibility)
                    entities['geoint_processing'] = {
                        'analysis_type': geoint_modules[0].replace('geoint_', ''),
                        'modules': geoint_modules,
                        'confidence': classification.get('confidence', 0.8)
                    }
                    entities['force_hybrid'] = True
                    entities['analysis_intent'] = {
                        'type': 'geoint_analysis',
                        'subtype': geoint_modules[0].replace('geoint_', ''),
                        'urgency': 'high' if 'emergency' in natural_query.lower() else 'medium',
                        'confidence': classification.get('confidence', 0.8)
                    }
                    logger.info("📊 Processing GEOINT query with hybrid STAC + Analysis approach")
            
            # ========================================================================
            # Extract datetime_range for downstream compatibility
            # ========================================================================
            
            datetime_range = stac_query.get("datetime")
            
            # ========================================================================
            # Determine data source (VEDA vs Planetary Computer)
            # ========================================================================
            
            data_source = self.determine_stac_source(natural_query, entities)
            
            if data_source == "veda":
                # Build VEDA-specific query (override agent's query for VEDA)
                stac_query = self.build_veda_stac_query(entities, bbox)
                stac_query["data_source"] = "veda"
                logger.info("🌍 Using VEDA STAC source")
            else:
                # Agent 2 already built the query - just add data source flag
                stac_query["data_source"] = "planetary_computer"
                logger.info("🌍 Using Planetary Computer STAC source")
            
            # ========================================================================
            # Query completeness analysis (optional)
            # ========================================================================
            
            clarification_questions = []
            analysis = {"needs_clarification": False, "quality_score": 0.8}
            
            if self.query_checker:
                analysis = self.query_checker.analyze_query_completeness(entities, stac_query, natural_query)
                
                # Generate clarification questions if query quality is poor
                if analysis["needs_clarification"]:
                    clarification_questions = self.query_checker.generate_clarification_questions(analysis, natural_query)
            
            # ========================================================================
            # Calculate overall confidence
            # ========================================================================
            
            overall_confidence = 0.9  # High confidence with new agent system
            
            # Build result
            # Build location_info dict from extracted data
            location_info = {
                "name": location_name if location_name else stac_query.get("location_name"),
                "bbox": bbox
            }
            
            result = {
                **stac_query,
                "confidence": overall_confidence,
                "reasoning": self._build_reasoning(entities, location_info),
                "extracted_entities": entities,
                "translation_method": "semantic_kernel",
                "analysis": analysis,
                "clarification_questions": clarification_questions,
                "needs_clarification": analysis["needs_clarification"]
            }
            
            # 🎯 Add GEOINT processing information if this is a hybrid query
            geoint_processing = entities.get('geoint_processing')
            if geoint_processing:
                logger.info(f"🗺️ Adding GEOINT processing metadata for {geoint_processing['analysis_type']}")
                
                # Add GEOINT metadata to the result
                result['geoint_analysis'] = {
                    'required': True,
                    'analysis_type': geoint_processing['analysis_type'],
                    'confidence': geoint_processing['confidence'],
                    'detection_method': geoint_processing['detection_method'],
                    'parameters': self._extract_geoint_parameters(natural_query, geoint_processing['analysis_type']),
                    'recommended_collections': self._get_geoint_recommended_collections(geoint_processing['analysis_type'])
                }
                
                # Modify the reasoning to indicate hybrid processing
                result['reasoning'] = f"{result['reasoning']} + GEOINT {geoint_processing['analysis_type']} analysis"
                
                # Ensure elevation data collections are included for GEOINT processing
                current_collections = result.get('collections', [])
                elevation_collections = ['cop-dem-glo-30', 'nasadem', 'cop-dem-glo-90']
                
                # Add elevation collections if not already present and relevant for the analysis
                if geoint_processing['analysis_type'] in ['terrain_analysis', 'mobility_analysis', 'line_of_sight', 'elevation_profile']:
                    for elev_collection in elevation_collections:
                        if elev_collection not in current_collections:
                            current_collections.append(elev_collection)
                            logger.info(f"📊 Added elevation collection for GEOINT: {elev_collection}")
                    
                    result['collections'] = current_collections
                
                logger.info(f"✅ Hybrid STAC + GEOINT query prepared: {len(current_collections)} collections + {geoint_processing['analysis_type']} analysis")
            
            logger.info(f"Translation successful with confidence {overall_confidence:.2f}")
            return result
            
        except Exception as e:
            logger.error(f"Translation failed: {e}")
            
            # Enhanced error response with context preservation
            error_context = {
                "original_query": natural_query,
                "error_type": type(e).__name__,
                "error_message": str(e),
                "attempted_extraction": "Translation failed - try rephrasing your query",
                "suggestions": []
            }
            
            # Add specific suggestions based on error type
            if "location" in str(e).lower():
                error_context["suggestions"].append("Try specifying a more well-known location (e.g., 'California', 'Houston, Texas')")
            if "timeout" in str(e).lower():
                error_context["suggestions"].append("The service is experiencing delays. Please try again in a moment.")
            if "json" in str(e).lower() or "parse" in str(e).lower():
                error_context["suggestions"].append("There was an issue processing your query. Try rephrasing with simpler terms.")
            
            # Always provide helpful suggestions
            if not error_context["suggestions"]:
                error_context["suggestions"] = [
                    "Try being more specific about the location and time period",
                    "Use common location names (cities, states, countries)",
                    "Specify the type of disaster or analysis you need"
                ]
            
            raise Exception(f"Semantic translation failed with context: {json.dumps(error_context, indent=2)}")
    
    def _build_reasoning(self, entities: Dict[str, Any], location_info: Dict[str, Any]) -> str:
        """Build human-readable reasoning for the translation"""
        
        parts = []
        
        disaster_type = entities.get("disaster", {}).get("type")
        if disaster_type:
            parts.append(f"{disaster_type} analysis")
        
        location_name = location_info.get("name")
        if location_name:
            parts.append(f"for {location_name}")
        
        temporal = entities.get("temporal", {})
        if temporal.get("year"):
            parts.append(f"in {temporal['year']}")
        elif temporal.get("season"):
            parts.append(f"during {temporal['season']}")
        
        if not parts:
            parts.append("general satellite imagery analysis")
        
        return "Semantic Kernel extraction: " + " ".join(parts)
    
    def _prepare_geoint_summary(self, geoint_results: Dict[str, Any]) -> str:
        """
        Format GEOINT analysis results for inclusion in GPT-4 response generation prompt.
        
        This method extracts numerical metrics and analysis results to enable
        context-aware chat responses with specific measurements and statistics.
        
        Example: Instead of "Here is elevation data" → "The highest peak is 2,500m at North Rim"
        """
        if not geoint_results or not geoint_results.get('success'):
            return "No GEOINT analysis results available"
        
        analysis_type = geoint_results.get('analysis_type', 'unknown')
        results = geoint_results.get('results', {})
        
        summary_parts = []
        
        if analysis_type == 'terrain_analysis':
            # Extract elevation statistics
            elevation_stats = results.get('elevation_statistics', {})
            if elevation_stats:
                min_elev = elevation_stats.get('min_elevation', 0)
                max_elev = elevation_stats.get('max_elevation', 0)
                mean_elev = elevation_stats.get('mean_elevation', 0)
                
                summary_parts.append(f"- Elevation range: {min_elev:.1f}m to {max_elev:.1f}m (mean: {mean_elev:.1f}m)")
                
                # Peak location
                peak_loc = elevation_stats.get('peak_location', {})
                if peak_loc:
                    peak_lat = peak_loc.get('latitude', 0)
                    peak_lon = peak_loc.get('longitude', 0)
                    peak_elev = peak_loc.get('elevation', 0)
                    summary_parts.append(f"- Highest peak: {peak_elev:.1f}m at ({peak_lat:.4f}°, {peak_lon:.4f}°)")
            
            # Slope analysis
            slope_analysis = results.get('slope_analysis', {})
            if slope_analysis:
                mean_slope = slope_analysis.get('mean_slope', 0)
                max_slope = slope_analysis.get('max_slope', 0)
                summary_parts.append(f"- Slope: mean {mean_slope:.1f}°, max {max_slope:.1f}°")
                
                slope_classes = slope_analysis.get('slope_classes', {})
                if slope_classes:
                    class_strs = [f"{name}: {data.get('percentage', 0):.1f}%" 
                                 for name, data in slope_classes.items() if data.get('percentage', 0) > 5]
                    if class_strs:
                        summary_parts.append(f"- Slope distribution: {', '.join(class_strs)}")
            
            # Roughness
            roughness = results.get('roughness_index')
            if roughness:
                summary_parts.append(f"- Terrain roughness index: {roughness:.2f}")
        
        elif analysis_type == 'mobility_analysis':
            # Extract mobility zones
            mobility_zones = results.get('mobility_zones', {})
            if mobility_zones:
                go_zones = mobility_zones.get('go_zones', {})
                slow_go = mobility_zones.get('slow_go_zones', {})
                no_go = mobility_zones.get('no_go_zones', {})
                
                if go_zones:
                    summary_parts.append(f"- Accessible terrain (Go zones): {go_zones.get('percentage', 0):.1f}% ({go_zones.get('area_km2', 0):.1f} km²)")
                if slow_go:
                    summary_parts.append(f"- Reduced mobility (Slow-Go): {slow_go.get('percentage', 0):.1f}% ({slow_go.get('area_km2', 0):.1f} km²)")
                if no_go:
                    summary_parts.append(f"- Impassable terrain (No-Go): {no_go.get('percentage', 0):.1f}% ({no_go.get('area_km2', 0):.1f} km²)")
            
            recommended_routes = results.get('recommended_routes', [])
            if recommended_routes:
                summary_parts.append(f"- Recommended routes: {', '.join(recommended_routes)}")
        
        elif analysis_type == 'elevation_profile':
            # Extract profile statistics
            statistics = results.get('statistics', {})
            if statistics:
                min_elev = statistics.get('min_elevation', 0)
                max_elev = statistics.get('max_elevation', 0)
                ascent = statistics.get('total_ascent', 0)
                descent = statistics.get('total_descent', 0)
                
                summary_parts.append(f"- Elevation profile: {min_elev:.1f}m to {max_elev:.1f}m")
                summary_parts.append(f"- Total ascent: {ascent:.1f}m, descent: {descent:.1f}m")
            
            profile_path = results.get('profile_path', {})
            if profile_path:
                num_samples = profile_path.get('num_samples', 0)
                summary_parts.append(f"- Profile samples: {num_samples} points")
        
        elif analysis_type == 'line_of_sight':
            observer = results.get('observer_location', {})
            if observer:
                obs_lat = observer.get('latitude', 0)
                obs_lon = observer.get('longitude', 0)
                obs_height = observer.get('height_agl', 0)
                summary_parts.append(f"- Observer: ({obs_lat:.4f}°, {obs_lon:.4f}°) @ {obs_height}m AGL")
            
            viewshed = results.get('viewshed_analysis', {})
            if viewshed:
                visible_area = viewshed.get('visible_area_km2', 0)
                visible_pct = viewshed.get('visible_percentage', 0)
                summary_parts.append(f"- Visible area: {visible_area:.1f} km² ({visible_pct:.1f}%)")
        
        if not summary_parts:
            return f"GEOINT {analysis_type} analysis completed (no detailed metrics available)"
        
        return "\n".join(summary_parts)

    
    async def generate_contextual_earth_science_response(self, natural_query: str, classification: Dict[str, Any], stac_response: Optional[Dict[str, Any]] = None, geoint_results: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """Generate comprehensive contextual Earth science response with optional satellite data integration and GEOINT analysis results"""
        
        # Ensure kernel is initialized
        await self._ensure_kernel_initialized()
        
        if not self._kernel_initialized or self.kernel is None:
            return await self._fallback_contextual_response(natural_query, classification, stac_response)
        
        try:
            # Create classification-based prompt (uses the 3-template system!)
            response_prompt = self._create_response_generation_prompt(classification)
            
            # Prepare data summary for the template system
            stac_data_summary = self._prepare_stac_data_summary(
                stac_response.get("results", {}).get("features", []) if stac_response else [],
                stac_response.get("results", {}) if stac_response else {}
            )
            
            # � ADD CLOUD FILTER WARNING if user requested cloud filtering but collections don't support it
            if classification.get('cloud_filter_unavailable'):
                cloud_warning = classification['cloud_filter_unavailable']
                warning_text = f"\n\n**⚠️ IMPORTANT NOTE ABOUT CLOUD COVER:**\nThe user requested imagery with ≤{cloud_warning['requested_threshold']}% cloud cover, but the selected collections ({', '.join(cloud_warning['collections'])}) do not have cloud cover metadata. {cloud_warning['reason']}. The search returned results without cloud filtering. In your response, explain this limitation clearly and suggest alternative collections if cloud-free imagery is important (e.g., Sentinel-2, Landsat, or HLS)."
                stac_data_summary = f"{stac_data_summary}{warning_text}"
                logger.info(f"📝 Added cloud filter warning to response context")
            
            # �🔬 INTEGRATE GEOINT ANALYSIS RESULTS INTO RESPONSE CONTEXT
            if geoint_results and geoint_results.get('success'):
                logger.info("📊 Integrating GEOINT analysis results into response context")
                geoint_summary = self._prepare_geoint_summary(geoint_results)
                stac_data_summary = f"{stac_data_summary}\n\n**GEOINT ANALYSIS RESULTS:**\n{geoint_summary}"
                logger.info(f"✅ Enhanced context with GEOINT metrics")
            
            # Get conversation context if available  
            conversation_context = ""
            
            # Generate response using the 3-template system
            response_content = await self._generate_response_with_sk(
                response_prompt,
                natural_query,
                stac_data_summary,
                conversation_context
            )
            
            # Determine map data if available
            map_data = None
            if stac_response and stac_response.get("success"):
                features = stac_response.get("results", {}).get("features", [])
                if features:
                    map_data = {
                        "features": features,
                        "bbox": self._extract_bbox_from_features(features),
                        "center": self._calculate_center_from_features(features),
                        "zoom": self._calculate_appropriate_zoom(features)
                    }
            
            return {
                "message": response_content,
                "query_type": "contextual_earth_science",
                "has_satellite_data": stac_response is not None and stac_response.get("success", False),
                "has_contextual_analysis": True,
                "map_data": map_data,
                "location_focus": classification.get("location_focus"),
                "temporal_focus": classification.get("temporal_focus"),
                "disaster_or_event": classification.get("disaster_or_event")
            }
            
        except Exception as e:
            logger.error(f"Contextual Earth science response generation failed: {e}")
            return await self._fallback_contextual_response(natural_query, classification, stac_response)
    
    async def generate_empty_result_response(
        self, 
        natural_query: str, 
        stac_query: Dict[str, Any],
        collections: List[str],
        diagnostics: Dict[str, Any]
    ) -> str:
        """
        🆕 Generate intelligent, context-aware response for empty results using GPT.
        
        Analyzes the specific failure point (STAC API, spatial filter, tile selection)
        and provides actionable, query-specific recommendations.
        
        Args:
            natural_query: Original user query
            stac_query: The STAC query that was executed (with all filters)
            collections: List of collections searched
            diagnostics: {
                "raw_count": int,              # Results from STAC API
                "spatial_filtered_count": int, # After spatial overlap filter
                "final_count": int,            # After tile selection
                "failure_stage": str           # Where it failed
            }
        
        Returns:
            Natural language response with specific suggestions
        """
        # Ensure kernel is initialized
        await self._ensure_kernel_initialized()
        
        if not self._kernel_initialized or self.kernel is None:
            logger.warning("⚠️ Semantic Kernel not available for empty result response, using fallback")
            return self._fallback_empty_result_response(natural_query, stac_query, collections, diagnostics)
        
        try:
            logger.info("🤖 Generating GPT-powered empty result response")
            
            # Build diagnostic context for GPT
            diagnostic_context = self._build_diagnostic_context(natural_query, stac_query, collections, diagnostics)
            
            # Create prompt for empty result analysis
            empty_result_prompt = self._create_empty_result_prompt()
            
            # Generate response using Semantic Kernel
            response_content = await self._generate_empty_result_with_sk(
                empty_result_prompt,
                natural_query,
                diagnostic_context
            )
            
            logger.info("✅ GPT-generated empty result response created")
            return response_content
            
        except Exception as e:
            logger.error(f"❌ GPT empty result generation failed: {e}")
            return self._fallback_empty_result_response(natural_query, stac_query, collections, diagnostics)
    
    async def generate_alternative_result_response(
        self,
        natural_query: str,
        classification: Dict[str, Any],
        stac_response: Dict[str, Any],
        original_filters: Dict[str, Any],
        alternative_filters: Dict[str, Any],
        explanation: str,
        geoint_results: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        🆕 Generate response explaining that alternative results are being shown.
        
        This is called when the original query returned no results, but we successfully
        found alternatives by relaxing filters (cloud cover, date range, collections).
        
        Args:
            natural_query: Original user query
            classification: Query classification
            stac_response: STAC response with alternative features
            original_filters: What user originally requested
            alternative_filters: What was actually used to find results
            explanation: Technical explanation of what was changed
            geoint_results: Optional GEOINT analysis results
        
        Returns:
            Dict with message explaining the alternative results shown
        """
        # Ensure kernel is initialized
        await self._ensure_kernel_initialized()
        
        if not self._kernel_initialized or self.kernel is None:
            return await self._fallback_alternative_response(
                natural_query, stac_response, original_filters, alternative_filters, explanation
            )
        
        try:
            logger.info("💡 Generating GPT-powered alternative result explanation...")
            
            # Build context for GPT
            alternative_context = self._build_alternative_context(
                natural_query,
                original_filters,
                alternative_filters,
                explanation,
                stac_response.get("results", {}).get("features", [])
            )
            
            # Create prompt for alternative result explanation
            alternative_prompt = self._create_alternative_result_prompt()
            
            # Prepare data summary
            stac_data_summary = self._prepare_stac_data_summary(
                stac_response.get("results", {}).get("features", []),
                stac_response.get("results", {})
            )
            
            # Add GEOINT results if available
            if geoint_results and geoint_results.get('success'):
                geoint_summary = self._prepare_geoint_summary(geoint_results)
                stac_data_summary = f"{stac_data_summary}\n\n**GEOINT ANALYSIS RESULTS:**\n{geoint_summary}"
            
            # Generate response using Semantic Kernel
            response_content = await self._generate_alternative_with_sk(
                alternative_prompt,
                natural_query,
                alternative_context,
                stac_data_summary
            )
            
            logger.info("✅ GPT-generated alternative result explanation created")
            
            return {
                "message": response_content,
                "query_type": "alternative_results",
                "has_satellite_data": True,
                "showing_alternatives": True,
                "original_filters": original_filters,
                "alternative_filters": alternative_filters
            }
            
        except Exception as e:
            logger.error(f"❌ GPT alternative explanation generation failed: {e}")
            return await self._fallback_alternative_response(
                natural_query, stac_response, original_filters, alternative_filters, explanation
            )
    
    def _create_alternative_result_prompt(self) -> str:
        """Create prompt template for GPT to explain alternative results"""
        
        return """
        You are an expert Earth observation specialist helping users understand why their exact search didn't work, 
        but showing them the best available alternative instead.
        
        **YOUR TASK:** Explain clearly and naturally what the user originally requested, why it wasn't available, 
        and what you're showing them instead.
        
        **RESPONSE STRUCTURE:**
        1. Brief acknowledgment of original request (1 sentence)
        2. Clear explanation of why exact request wasn't available (1-2 sentences)
        3. Explanation of what alternative is being shown and why it's still valuable (1-2 sentences)
        4. Optional: Brief description of the data being displayed (use data summary)
        
        **TONE GUIDELINES:**
        - Be transparent and honest about the substitution
        - Frame the alternative positively (it's still valuable!)
        - Keep it conversational and helpful
        - Don't apologize excessively - be solution-oriented
        - Use "I'm showing you..." not "I found..." (emphasize proactive help)
        
        **FORMATTING:**
        - Keep response to 2-3 short paragraphs maximum
        - Use natural language, not bullet points
        - Integrate technical details smoothly
        
        **IMPORTANT:**
        - Make it clear this is a substitution, not the exact request
        - Explain the specific change (cloud threshold, date range, collection)
        - Emphasize the data quality/usefulness of the alternative
        
        **USER QUERY:** {{$user_query}}
        
        **ALTERNATIVE CONTEXT:** {{$alternative_context}}
        
        **DATA SUMMARY:** {{$data_summary}}
        
        Generate a clear, helpful explanation of the alternative results being shown:
        """
    
    def _build_alternative_context(
        self,
        natural_query: str,
        original_filters: Dict[str, Any],
        alternative_filters: Dict[str, Any],
        explanation: str,
        features: List[Dict]
    ) -> str:
        """Build context explaining what alternative was used"""
        
        context_parts = []
        
        context_parts.append(f"**What user originally requested:**")
        
        # Original filters
        if original_filters.get("cloud_cover"):
            context_parts.append(f"  - Cloud cover: <{original_filters['cloud_cover']}%")
        if original_filters.get("datetime"):
            context_parts.append(f"  - Date range: {original_filters['datetime']}")
        if original_filters.get("collections"):
            context_parts.append(f"  - Collections: {', '.join(original_filters['collections'])}")
        
        context_parts.append(f"\n**Why original request had no results:**")
        context_parts.append(f"  {explanation}")
        
        context_parts.append(f"\n**What alternative is being shown instead:**")
        
        # Alternative filters
        if alternative_filters.get("cloud_cover") and alternative_filters["cloud_cover"] != original_filters.get("cloud_cover"):
            context_parts.append(f"  - Cloud cover: <{alternative_filters['cloud_cover']}% (relaxed from <{original_filters.get('cloud_cover')}%)")
        
        if alternative_filters.get("datetime") and alternative_filters["datetime"] != original_filters.get("datetime"):
            days_expanded = alternative_filters.get("days_expanded", "")
            if days_expanded:
                context_parts.append(f"  - Date range: Expanded to {days_expanded} days")
            else:
                context_parts.append(f"  - Date range: {alternative_filters['datetime']}")
        
        if alternative_filters.get("collections") and alternative_filters["collections"] != original_filters.get("collections"):
            context_parts.append(f"  - Collections: {', '.join(alternative_filters['collections'])} (changed from {', '.join(original_filters.get('collections', []))})")
        
        # Feature summary
        context_parts.append(f"\n**Alternative results found:**")
        context_parts.append(f"  - {len(features)} satellite images")
        
        if features:
            dates = [f.get("properties", {}).get("datetime", "") for f in features if f.get("properties", {}).get("datetime")]
            if dates:
                earliest = min(dates)[:10]
                latest = max(dates)[:10]
                if earliest == latest:
                    context_parts.append(f"  - Date: {earliest}")
                else:
                    context_parts.append(f"  - Date range: {earliest} to {latest}")
        
        return "\n".join(context_parts)
    
    async def _generate_alternative_with_sk(
        self,
        prompt_template: str,
        user_query: str,
        alternative_context: str,
        data_summary: str
    ) -> str:
        """Generate alternative result explanation using Semantic Kernel"""
        
        try:
            # Create prompt configuration
            prompt_config = PromptTemplateConfig(
                template=prompt_template,
                name="generate_alternative_result_response",
                template_format="semantic-kernel",
                input_variables=[
                    InputVariable(name="user_query", description="The user's original query"),
                    InputVariable(name="alternative_context", description="Context about what alternative is being shown"),
                    InputVariable(name="data_summary", description="Summary of the alternative data being displayed")
                ]
            )
            
            # Create function
            alternative_function = KernelFunction.from_prompt(
                prompt_template_config=prompt_config,
                function_name="generate_alternative_result_response",
                plugin_name="semantic_translator"
            )
            
            # Execute with timeout
            arguments = KernelArguments(
                user_query=user_query,
                alternative_context=alternative_context,
                data_summary=data_summary
            )
            
            result = await asyncio.wait_for(
                self.kernel.invoke(alternative_function, arguments=arguments),
                timeout=20.0
            )
            
            # Extract response content
            response_content = self._extract_clean_content_from_sk_result(result)
            
            # Validate content
            if not response_content or response_content.strip() == "":
                logger.warning("Empty content returned from GPT for alternative, using fallback")
                return f"I couldn't find exactly what you requested, but I'm showing you similar imagery that's available for this location."
            
            # Clean up response - handle both single and double quotes
            response_content = response_content.strip()
            # Remove double-double quotes: ""content""
            if response_content.startswith('""') and response_content.endswith('""'):
                response_content = response_content[2:-2]
            # Remove single quotes: "content"
            elif response_content.startswith('"') and response_content.endswith('"'):
                response_content = response_content[1:-1]
            
            return response_content
            
        except Exception as e:
            logger.error(f"Alternative explanation SK generation failed: {e}")
            raise
    
    async def _fallback_alternative_response(
        self,
        natural_query: str,
        stac_response: Dict[str, Any],
        original_filters: Dict[str, Any],
        alternative_filters: Dict[str, Any],
        explanation: str
    ) -> Dict[str, Any]:
        """Fallback alternative explanation when GPT unavailable"""
        
        features = stac_response.get("results", {}).get("features", [])
        
        # Build simple explanation
        message_parts = []
        message_parts.append(f"I couldn't find imagery exactly matching your request")
        
        # Explain what changed
        if alternative_filters.get("cloud_cover") and alternative_filters["cloud_cover"] != original_filters.get("cloud_cover"):
            message_parts.append(f"with <{original_filters.get('cloud_cover')}% cloud cover")
        
        message_parts.append(f", but I'm showing you {len(features)} similar images")
        
        if alternative_filters.get("cloud_cover"):
            message_parts.append(f"with up to {alternative_filters['cloud_cover']}% cloud cover instead")
        
        message_parts.append(".")
        
        return {
            "message": " ".join(message_parts),
            "query_type": "alternative_results",
            "has_satellite_data": True,
            "showing_alternatives": True,
            "fallback_used": True
        }
    
    def _create_empty_result_prompt(self) -> str:
        """Create prompt template for GPT-powered empty result responses"""
        
        return """
        You are an expert Earth observation data specialist helping users understand why their satellite imagery search returned no results.
        
        **YOUR TASK:** Analyze the search diagnostics and provide a clear, helpful explanation with specific, actionable recommendations.
        
        **RESPONSE GUIDELINES:**
        - Start with a brief explanation of what was searched and why it returned no results
        - Provide 2-4 specific, actionable suggestions (use bullet points with •)
        - Be encouraging and solution-oriented
        - Use concrete values from the diagnostics (date ranges, cloud thresholds, collection names)
        - Keep response concise (2-3 short paragraphs maximum)
        
        **FORMATTING:**
        - Brief introduction (1-2 sentences)
        - **Suggestions:** section with bullet points
        - Each suggestion should be specific and actionable
        
        **IMPORTANT CONTEXT AWARENESS:**
        - If failure_stage is "stac_api": No data exists matching the filters → suggest relaxing constraints
        - If failure_stage is "tile_selection": Data exists but failed quality/cloud thresholds → suggest relaxing quality filters
        - Consider the specific filters used (datetime range, cloud cover, collections)
        - Tailor suggestions to the user's original intent
        
        **USER QUERY:** {{$user_query}}
        
        **DIAGNOSTIC INFORMATION:** {{$diagnostic_context}}
        
        Generate a helpful response explaining why no results were found and how to adjust the search:
        """
    
    def _build_diagnostic_context(
        self,
        natural_query: str,
        stac_query: Dict[str, Any],
        collections: List[str],
        diagnostics: Dict[str, Any]
    ) -> str:
        """Build detailed diagnostic context for GPT to analyze"""
        
        context_parts = []
        
        # Failure stage analysis
        failure_stage = diagnostics.get("failure_stage", "unknown")
        raw_count = diagnostics.get("raw_count", 0)
        spatial_count = diagnostics.get("spatial_filtered_count", 0)
        final_count = diagnostics.get("final_count", 0)
        
        context_parts.append(f"**Failure Stage:** {failure_stage}")
        context_parts.append(f"**Results at each stage:**")
        context_parts.append(f"  - STAC API returned: {raw_count} images")
        context_parts.append(f"  - After spatial filtering: {spatial_count} images")
        context_parts.append(f"  - After tile selection: {final_count} images")
        
        # Collections searched
        if collections:
            context_parts.append(f"\n**Collections searched:** {', '.join(collections)}")
        
        # DateTime filter analysis
        datetime_str = stac_query.get("datetime", "")
        if datetime_str:
            context_parts.append(f"\n**Date range:** {datetime_str}")
            if "/" in datetime_str:
                try:
                    start, end = datetime_str.split("/")
                    start_date = start[:10] if len(start) >= 10 else start
                    end_date = end[:10] if len(end) >= 10 else end
                    
                    # Calculate duration
                    from datetime import datetime as dt
                    start_dt = dt.fromisoformat(start_date)
                    end_dt = dt.fromisoformat(end_date)
                    days = (end_dt - start_dt).days
                    
                    context_parts.append(f"  Duration: {days} days ({start_date} to {end_date})")
                except:
                    pass
        
        # Cloud cover filter analysis
        query_filter = stac_query.get("filter", {})
        if "eo:cloud_cover" in str(query_filter):
            context_parts.append(f"\n**Cloud cover filter:** Active (likely <10% or <20% threshold)")
            # Try to extract exact threshold
            filter_str = str(query_filter)
            if "10" in filter_str:
                context_parts.append("  Threshold: <10% (very strict - clear imagery only)")
            elif "20" in filter_str:
                context_parts.append("  Threshold: <20% (moderate - mostly clear)")
        
        # Bounding box (spatial context)
        bbox = stac_query.get("bbox")
        if bbox:
            # Calculate area (approximate)
            width = abs(bbox[2] - bbox[0])
            height = abs(bbox[3] - bbox[1])
            area = width * height
            
            context_parts.append(f"\n**Search area:** {width:.2f}° × {height:.2f}° (area: {area:.2f} sq degrees)")
            
            # Provide context on area size
            if area < 0.1:
                context_parts.append("  Size: Very small area (city-level)")
            elif area < 1.0:
                context_parts.append("  Size: Small area (county/region-level)")
            elif area < 10.0:
                context_parts.append("  Size: Medium area (state-level)")
            else:
                context_parts.append("  Size: Large area (multi-state/country-level)")
        
        # Query intent hints
        query_lower = natural_query.lower()
        intent_hints = []
        
        if any(term in query_lower for term in ["recent", "latest", "current"]):
            intent_hints.append("User wants RECENT data")
        if any(term in query_lower for term in ["clear", "cloudless", "low cloud"]):
            intent_hints.append("User wants CLEAR imagery")
        if any(term in query_lower for term in ["high res", "detailed", "resolution"]):
            intent_hints.append("User wants HIGH RESOLUTION")
        
        if intent_hints:
            context_parts.append(f"\n**User intent:** {', '.join(intent_hints)}")
        
        return "\n".join(context_parts)
    
    async def _generate_empty_result_with_sk(
        self,
        prompt_template: str,
        user_query: str,
        diagnostic_context: str
    ) -> str:
        """Generate empty result response using Semantic Kernel"""
        
        try:
            # Create prompt configuration
            prompt_config = PromptTemplateConfig(
                template=prompt_template,
                name="generate_empty_result_response",
                template_format="semantic-kernel",
                input_variables=[
                    InputVariable(name="user_query", description="The user's original query"),
                    InputVariable(name="diagnostic_context", description="Diagnostic information about the search failure")
                ]
            )
            
            # Create function
            empty_result_function = KernelFunction.from_prompt(
                prompt_template_config=prompt_config,
                function_name="generate_empty_result_response",
                plugin_name="semantic_translator"
            )
            
            # Execute with timeout
            arguments = KernelArguments(
                user_query=user_query,
                diagnostic_context=diagnostic_context
            )
            
            result = await asyncio.wait_for(
                self.kernel.invoke(empty_result_function, arguments=arguments),
                timeout=20.0
            )
            
            # Extract response content
            response_content = self._extract_clean_content_from_sk_result(result)
            
            # Validate content
            if not response_content or response_content.strip() == "":
                logger.warning("Empty content returned from GPT, using fallback")
                return "I searched for satellite data but didn't find any matching your criteria. Try adjusting your search parameters or date range."
            
            # Clean up response - handle both single and double quotes
            response_content = response_content.strip()
            # Remove double-double quotes: ""content""
            if response_content.startswith('""') and response_content.endswith('""'):
                response_content = response_content[2:-2]
            # Remove single quotes: "content"
            elif response_content.startswith('"') and response_content.endswith('"'):
                response_content = response_content[1:-1]
            
            return response_content
            
        except Exception as e:
            logger.error(f"Empty result SK generation failed: {e}")
            raise
    
    def _fallback_empty_result_response(
        self,
        natural_query: str,
        stac_query: Dict[str, Any],
        collections: List[str],
        diagnostics: Dict[str, Any]
    ) -> str:
        """Fallback empty result response when GPT is unavailable (rule-based)"""
        
        raw_count = diagnostics.get("raw_count", 0)
        spatial_count = diagnostics.get("spatial_filtered_count", 0)
        failure_stage = diagnostics.get("failure_stage", "unknown")
        
        # Use simple rule-based responses as fallback
        if raw_count == 0:
            return (
                f"I searched for satellite data related to '{natural_query}', "
                "but didn't find any available imagery matching your criteria. "
                "Try expanding your date range, relaxing cloud cover filters, or checking if the location is correct."
            )
        elif spatial_count == 0:
            return (
                f"I found {raw_count} satellite images in the catalog, but none had sufficient coverage of your requested area. "
                "Try expanding your search area or choosing a nearby location with better coverage."
            )
        else:
            return (
                f"I found {spatial_count} satellite images covering your area, but they didn't meet quality thresholds. "
                "Try relaxing quality filters or accepting imagery with higher cloud cover."
            )
    
    def _create_contextual_analysis_prompt(self) -> str:
        """Create prompt for comprehensive Earth science contextual analysis"""
        
        return """
        You are an expert Earth scientist with deep knowledge across Earth observation, environmental science, climate science, geology, oceanography, atmospheric science, and remote sensing. You provide scientifically accurate, well-explained answers about Earth systems, phenomena, and data.

        **CORE PRINCIPLES:**
        - Provide scientifically accurate information grounded in established research
        - Explain complex concepts in clear, accessible language
        - Include relevant quantitative data (measurements, statistics, dates) when available
        - Connect concepts to real-world observations and implications
        - When satellite data is available, explain what it reveals about the topic
        - Acknowledge uncertainty or limitations when appropriate

        **RESPONSE GUIDELINES:**
        - Keep responses to 2-3 paragraphs maximum for readability
        - Use bullet points for lists of key facts, processes, or findings
        - Include specific examples to illustrate concepts
        - Use precise scientific terminology with brief explanations
        - Professional tone with clear, accessible language
        - NO section headings or excessive formatting

        **TOPIC COVERAGE:**
        Answer questions about any Earth science topic including:
        - Natural phenomena (weather, climate, ocean currents, geological processes, ecosystems)
        - Earth observation (satellite capabilities, remote sensing, data analysis)
        - Environmental topics (land use, deforestation, urbanization, pollution, water resources)
        - Natural hazards (earthquakes, volcanoes, floods, droughts, wildfires, hurricanes)
        - Climate science (climate change, greenhouse gases, carbon cycles, temperature trends)
        - Planetary processes (plate tectonics, erosion, sedimentation, atmospheric circulation)
        - Scientific analysis (data interpretation, trends, spatial patterns, temporal changes)

        **USER QUERY:** {{$user_query}}
        **AVAILABLE DATA:** {{$context_data}}

        Generate a scientifically accurate, well-explained response to the user's question:
        """
    
    def _prepare_contextual_analysis_data(self, query: str, classification: Dict[str, Any], stac_response: Optional[Dict[str, Any]]) -> str:
        """Prepare context data for comprehensive Earth science analysis"""
        
        context_parts = []
        
        # Add classification context
        intent_type = classification.get("intent_type", "unknown")
        context_parts.append(f"Query type: {intent_type}")
        
        if classification.get("location_focus"):
            context_parts.append(f"Location focus: {classification['location_focus']}")
        
        if classification.get("temporal_focus"):
            context_parts.append(f"Time period: {classification['temporal_focus']}")
        
        if classification.get("disaster_or_event"):
            context_parts.append(f"Event/Disaster: {classification['disaster_or_event']}")
        
        # Add satellite data context if available
        if stac_response and stac_response.get("success"):
            features = stac_response.get("results", {}).get("features", [])
            if features:
                collections = list(set(f.get("collection", "unknown") for f in features))
                context_parts.append(f"Available satellite data: {len(features)} images from {', '.join(collections)}")
                
                # Add temporal info from satellite data
                dates = [f.get("properties", {}).get("datetime", "") for f in features if f.get("properties", {}).get("datetime")]
                if dates:
                    earliest = min(dates)[:10]
                    latest = max(dates)[:10]
                    if earliest == latest:
                        context_parts.append(f"Satellite data date: {earliest}")
                    else:
                        context_parts.append(f"Satellite data period: {earliest} to {latest}")
        else:
            context_parts.append("No satellite data available for this analysis")
        
        return "; ".join(context_parts)
    
    async def _generate_contextual_response_with_sk(self, prompt_template: str, user_query: str, context_data: str) -> str:
        """Generate contextual response using Semantic Kernel"""
        
        try:
            # Create prompt configuration
            prompt_config = PromptTemplateConfig(
                template=prompt_template,
                name="generate_contextual_response",
                template_format="semantic-kernel",
                input_variables=[
                    InputVariable(name="user_query", description="The user's natural language query"),
                    InputVariable(name="context_data", description="Contextual data for Earth science analysis")
                ]
            )
            
            # Create function
            contextual_function = KernelFunction.from_prompt(
                prompt_template_config=prompt_config,
                function_name="generate_contextual_response",
                plugin_name="semantic_translator"
            )
            
            # Execute with timeout
            arguments = KernelArguments(
                user_query=user_query,
                context_data=context_data
            )
            
            result = await asyncio.wait_for(
                self.kernel.invoke(contextual_function, arguments=arguments),
                timeout=25.0
            )
            
            # Extract response content using the same robust method as other SK calls
            response_content = self._extract_clean_content_from_sk_result(result)
            
            # Validate content
            if not response_content or response_content.strip() == "":
                logger.warning("Empty contextual content returned from SK, using fallback")
                return f"I found relevant information about your query: {user_query}. Please check the data visualization for details."
            
            # Clean up response - handle both single and double quotes
            response_content = response_content.strip()
            # Remove double-double quotes: ""content""
            if response_content.startswith('""') and response_content.endswith('""'):
                response_content = response_content[2:-2]
            # Remove single quotes: "content"
            elif response_content.startswith('"') and response_content.endswith('"'):
                response_content = response_content[1:-1]
            
            return response_content
            
        except Exception as e:
            logger.error(f"Contextual response generation with SK failed: {e}")
            raise
    
    async def _fallback_contextual_response(self, query: str, classification: Dict[str, Any], stac_response: Optional[Dict[str, Any]]) -> Dict[str, Any]:
        """Generate contextual response using direct Azure OpenAI HTTP call when Semantic Kernel fails"""
        
        try:
            # Use direct HTTP call to Azure OpenAI instead of hardcoded responses
            response_content = await self._direct_llm_call_for_contextual_analysis(query, classification, stac_response)
            
            return {
                "message": response_content,
                "query_type": "direct_llm_contextual",
                "has_satellite_data": stac_response is not None and stac_response.get("success", False),
                "has_contextual_analysis": True,
                "location_focus": classification.get("location_focus"),
                "fallback_used": False,  # Not a fallback anymore, it's a direct LLM call
                "method": "direct_azure_openai_http"
            }
            
        except Exception as e:
            logger.error(f"Direct LLM call failed: {e}")
            # Last resort: minimal response indicating the system should call LLM
            return {
                "message": f"I apologize, but I'm having technical difficulties generating a detailed analysis right now. However, I can see this is a question about {query}. Please try again in a moment as the system should provide a comprehensive, AI-generated response about the impacts and analysis you're asking about.",
                "query_type": "error_fallback", 
                "has_satellite_data": False,
                "has_contextual_analysis": False,
                "error": str(e),
                "fallback_used": True
            }
    
    async def _direct_llm_call_for_contextual_analysis(self, query: str, classification: Dict[str, Any], stac_response: Optional[Dict[str, Any]]) -> str:
        """Make direct HTTP call to Azure OpenAI for contextual analysis when Semantic Kernel fails"""
        
        import aiohttp
        import json
        
        # Prepare context data
        context_info = []
        if classification.get("location_focus"):
            context_info.append(f"Location: {classification['location_focus']}")
        if classification.get("disaster_or_event"):
            context_info.append(f"Event type: {classification['disaster_or_event']}")
        if stac_response and stac_response.get("success"):
            features = stac_response.get("results", {}).get("features", [])
            context_info.append(f"Satellite data: {len(features)} images available")
        
        context_text = "; ".join(context_info) if context_info else "General Earth science query"
        
        # Create concise prompt for direct LLM call
        system_prompt = """You are an expert Earth scientist with comprehensive knowledge across Earth observation, environmental science, climate science, geology, oceanography, atmospheric science, and remote sensing. You provide scientifically accurate, well-explained answers to questions about Earth systems, phenomena, and data.

CORE PRINCIPLES:
- Provide scientifically accurate information grounded in established research
- Explain complex concepts in clear, accessible language
- Include relevant quantitative data (measurements, statistics, dates) when available
- ALWAYS specify exact parameters when referencing data: specific dates, location names, cloud cover percentages, collection names
- Connect concepts to real-world observations and implications
- Acknowledge uncertainty or limitations when appropriate
- DO NOT use quotation marks around your entire response
- DO NOT make subjective quality comments like "excellent clarity", "ensuring quality", "good visibility"

RESPONSE FORMAT:
- Keep responses to 2-3 paragraphs maximum for readability
- Use bullet points for lists of key facts, processes, or findings
- Include specific examples to illustrate concepts
- Use precise scientific terminology with brief explanations
- Maintain a professional yet conversational tone
- State facts only - no editorial comments about quality or suitability

TOPIC COVERAGE (examples):
- Natural phenomena: Weather patterns, climate, ocean currents, geological processes, ecosystems
- Earth observation: Satellite capabilities, remote sensing techniques, data analysis methods
- Environmental topics: Land use change, deforestation, urbanization, pollution, water resources
- Natural hazards: Earthquakes, volcanoes, floods, droughts, wildfires, hurricanes
- Climate science: Climate change, greenhouse gases, carbon cycles, temperature trends
- Planetary processes: Plate tectonics, erosion, sedimentation, atmospheric circulation
- Scientific analysis: Data interpretation, trend analysis, spatial patterns, temporal changes

Keep your response focused, informative, and directly relevant to the user's question."""

        user_prompt = f"Context: {context_text}\n\nUser Question: {query}\n\nProvide a comprehensive, educational response:"
        
        # Prepare the request
        headers = {
            "Content-Type": "application/json",
            "api-key": self.azure_openai_api_key
        }
        
        payload = {
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt}
            ],
            "max_completion_tokens": 800,  # Reduced to encourage concise responses
            "temperature": 0.7,
            "top_p": 0.9
        }
        
        url = f"{self.azure_openai_endpoint}/openai/deployments/{self.model_name}/chat/completions?api-version=2024-02-01"
        
        # Make the HTTP request
        timeout = aiohttp.ClientTimeout(total=30)
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.post(url, headers=headers, json=payload) as response:
                if response.status == 200:
                    result = await response.json()
                    return result["choices"][0]["message"]["content"].strip()
                else:
                    error_text = await response.text()
                    raise Exception(f"Azure OpenAI API call failed: {response.status} - {error_text}")
    
    def _extract_bbox_from_features(self, features: List[Dict]) -> Optional[List[float]]:
        """Extract bounding box from STAC features"""
        if not features:
            return None
        
        # Get bbox from first feature or calculate from all features
        if features[0].get("bbox"):
            return features[0]["bbox"]
        
        # Calculate bbox from all feature geometries
        lons, lats = [], []
        for feature in features:
            if feature.get("geometry") and feature["geometry"].get("coordinates"):
                coords = feature["geometry"]["coordinates"]
                if feature["geometry"]["type"] == "Polygon":
                    for coord_pair in coords[0]:
                        lons.append(coord_pair[0])
                        lats.append(coord_pair[1])
        
        if lons and lats:
            return [min(lons), min(lats), max(lons), max(lats)]
        
        return None
    
    def _calculate_center_from_features(self, features: List[Dict]) -> Optional[List[float]]:
        """Calculate center point from STAC features"""
        bbox = self._extract_bbox_from_features(features)
        if bbox and len(bbox) == 4:
            west, south, east, north = bbox
            return [(west + east) / 2, (south + north) / 2]
        return None
    
    def _calculate_appropriate_zoom(self, features: List[Dict]) -> int:
        """Calculate appropriate zoom level based on feature coverage"""
        bbox = self._extract_bbox_from_features(features)
        if not bbox or len(bbox) != 4:
            return 10
        
        west, south, east, north = bbox
        width = abs(east - west)
        height = abs(north - south)
        max_dimension = max(width, height)
        
        # Zoom calculation based on area size
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
    
    # ============================================================================
    # TILE SELECTION HELPERS (Agent 3 Support)
    # ============================================================================
    
    def _parse_resolution(self, res_str: str) -> float:
        """
        Parse resolution string to numeric meters
        
        Handles formats:
        - "10m" -> 10.0
        - "10-60m" -> 10.0 (best resolution in range)
        - "1km" -> 1000.0
        - "0.6-1m" -> 0.6
        """
        try:
            res_lower = res_str.lower().strip()
            
            # Handle kilometer units
            if "km" in res_lower:
                nums = re.findall(r'[\d.]+', res_lower)
                if nums:
                    return float(nums[0]) * 1000
            
            # Handle meter units (with or without 'm')
            nums = re.findall(r'[\d.]+', res_lower)
            if nums:
                # If range (e.g., "10-60"), return best (lowest number)
                return float(nums[0])
            
            # Fallback: couldn't parse
            logger.warning(f"⚠️ Could not parse resolution: {res_str}, defaulting to 1000m")
            return 1000.0
            
        except Exception as e:
            logger.error(f"❌ Error parsing resolution '{res_str}': {e}")
            return 1000.0
    
    def _calculate_area(self, bbox: List[float]) -> float:
        """
        Calculate approximate area of bounding box in km²
        
        Uses simple approximation (good enough for tile selection)
        """
        if not bbox or len(bbox) != 4:
            return 0.0
        
        west, south, east, north = bbox
        
        # Width in degrees
        width_deg = abs(east - west)
        # Height in degrees
        height_deg = abs(north - south)
        
        # Approximate km per degree (varies by latitude)
        # At equator: ~111km per degree
        # Use average latitude for more accuracy
        avg_lat = (south + north) / 2
        km_per_deg_lon = 111.32 * abs(math.cos(math.radians(avg_lat)))
        km_per_deg_lat = 111.32
        
        # Calculate area
        width_km = width_deg * km_per_deg_lon
        height_km = height_deg * km_per_deg_lat
        area_km2 = width_km * height_km
        
        return area_km2
    
    def _determine_tile_limit(self, bbox: List[float], query: str) -> int:
        """
        Determine context-aware tile limit based on AOI size and query intent
        
        Strategy:
        - Small AOI (city): 5-15 tiles
        - Medium AOI (region): 10-25 tiles  
        - Large AOI (state): 20-40 tiles
        - Continental: 30-50 tiles
        - Adjust for query keywords (latest, time-series, etc.)
        """
        area_km2 = self._calculate_area(bbox)
        query_lower = query.lower()
        
        # Base limit on area
        if area_km2 < 100:  # City-scale (~10km x 10km)
            base_limit = 10
        elif area_km2 < 1000:  # Regional (~30km x 30km)
            base_limit = 20
        elif area_km2 < 10000:  # State-scale (~100km x 100km)
            base_limit = 30
        elif area_km2 < 100000:  # Large state/small country
            base_limit = 40
        else:  # Continental
            base_limit = 50
        
        # Adjust for query intent
        if any(word in query_lower for word in ["latest", "recent", "current", "now"]):
            # User wants most recent only
            return max(5, min(base_limit // 2, 15))
        elif any(word in query_lower for word in ["time series", "timeseries", "change", "historical"]):
            # User wants temporal coverage
            return min(base_limit * 2, 100)
        elif any(word in query_lower for word in ["detailed", "high resolution", "high res"]):
            # User wants quality over quantity
            return max(5, min(base_limit // 2, 20))
        else:
            return base_limit
    
    def _check_spatial_coverage(self, features: List[Dict], bbox: List[float]) -> Dict[str, Any]:
        """
        Check how well features cover the requested bounding box
        
        Returns:
        - coverage_percent: 0-100 indicating coverage
        - gaps: List of uncovered areas
        - overlap: Degree of tile overlap
        """
        if not features or not bbox:
            return {"coverage_percent": 0.0, "gaps": [], "overlap": "none"}
        
        # Simple heuristic: count tiles that intersect with bbox
        west, south, east, north = bbox
        bbox_area = self._calculate_area(bbox)
        
        intersecting_tiles = 0
        for feature in features:
            feature_bbox = feature.get("bbox")
            if not feature_bbox or len(feature_bbox) != 4:
                continue
            
            fw, fs, fe, fn = feature_bbox
            
            # Check if bboxes intersect
            if not (fe < west or fw > east or fn < south or fs > north):
                intersecting_tiles += 1
        
        # Rough coverage estimate
        if not features:
            coverage_percent = 0.0
        else:
            # More tiles = better coverage (rough approximation)
            coverage_percent = min(100.0, (intersecting_tiles / max(1, len(features) // 2)) * 100)
        
        return {
            "coverage_percent": coverage_percent,
            "intersecting_tiles": intersecting_tiles,
            "total_tiles": len(features)
        }
    
    def _prepare_stac_data_summary(self, features: List[Dict], collection_summary: Dict[str, Any]) -> Dict[str, Any]:
        """Prepare comprehensive summary of STAC data for LLM analysis"""
        
        if not features:
            return {
                "has_data": False,
                "total_images": 0,
                "collections": [],
                "temporal_coverage": "No data available",
                "quality_summary": "No images found"
            }
        
        # Basic statistics
        total_images = len(features)
        collections = list(set(f.get("collection", "unknown") for f in features))
        
        # Temporal analysis - handle both standard datetime and composite datasets
        dates = [f.get("properties", {}).get("datetime", "") for f in features if f.get("properties", {}).get("datetime")]
        temporal_coverage = "Unknown"
        
        if dates:
            earliest = min(dates)[:10] if dates else "Unknown"
            latest = max(dates)[:10] if dates else "Unknown"
            if earliest == latest:
                temporal_coverage = f"Single date: {earliest}"
            else:
                temporal_coverage = f"Date range: {earliest} to {latest}"
        else:
            # For composite products (MODIS fire, vegetation), extract date from item ID
            # Example: MYD14A1.A2025033.h08v05.061 → Day 033 of 2025
            item_ids = [f.get("id", "") for f in features if f.get("id")]
            if item_ids and any("A202" in item_id or "A201" in item_id for item_id in item_ids):
                # Extract year.day format from MODIS item IDs
                modis_dates = []
                for item_id in item_ids:
                    if ".A" in item_id:
                        try:
                            # Extract AYYYYDDD format (e.g., A2025033)
                            date_part = item_id.split(".A")[1][:7]  # A2025033
                            year = int(date_part[:4])
                            day_of_year = int(date_part[4:7])
                            
                            # Convert day of year to date
                            from datetime import datetime, timedelta
                            date_obj = datetime(year, 1, 1) + timedelta(days=day_of_year - 1)
                            modis_dates.append(date_obj.strftime("%Y-%m-%d"))
                        except:
                            pass
                
                if modis_dates:
                    earliest = min(modis_dates)
                    latest = max(modis_dates)
                    if earliest == latest:
                        temporal_coverage = f"Single date: {earliest}"
                    else:
                        temporal_coverage = f"Date range: {earliest} to {latest}"
        
        # Quality analysis
        cloud_covers = [
            f.get("properties", {}).get("eo:cloud_cover") 
            for f in features 
            if f.get("properties", {}) and f.get("properties", {}).get("eo:cloud_cover") is not None
        ]
        
        quality_summary = "Quality data not available"
        if cloud_covers:
            avg_cloud = sum(cloud_covers) / len(cloud_covers)
            clear_images = len([c for c in cloud_covers if c < 20])
            quality_summary = f"Average cloud cover: {avg_cloud:.1f}%, Clear images (<20% clouds): {clear_images}/{len(cloud_covers)}"
        
        # Platform analysis with fallback to collection-based mapping
        platforms_from_stac = list(set(
            f.get("properties", {}).get("platform", None) 
            for f in features 
            if f.get("properties", {}) and f.get("properties", {}).get("platform")
        ))
        
        # Fallback: Map collections to their platforms if platform property not available
        platform_fallback_map = {
            "naip": "USDA NAIP",
            "sentinel-2-l2a": "ESA Sentinel-2",
            "sentinel-1-grd": "ESA Sentinel-1",
            "sentinel-1-rtc": "ESA Sentinel-1",
            "landsat-c2-l2": "USGS Landsat",
            "landsat-8-c2-l2": "USGS Landsat-8",
            "landsat-9-c2-l2": "USGS Landsat-9",
            "hls-l30": "NASA HLS (Landsat)",
            "hls-s30": "NASA HLS (Sentinel-2)",
            "modis-14A1-061": "NASA MODIS",
            "modis-14A2-061": "NASA MODIS",
            "modis-MCD64A1-061": "NASA MODIS",
            "modis-13Q1-061": "NASA MODIS",
            "cop-dem-glo-30": "ESA Copernicus DEM",
            "cop-dem-glo-90": "ESA Copernicus DEM",
            "nasadem": "NASA DEM"
        }
        
        platforms = platforms_from_stac if platforms_from_stac else [
            platform_fallback_map.get(coll, coll) for coll in collections
        ]
        
        # Geographic coverage (if bbox available)
        geographic_coverage = "Global coverage possible"
        if features and features[0].get("bbox"):
            bbox = features[0]["bbox"]
            geographic_coverage = f"Bounding box: {bbox[0]:.2f}, {bbox[1]:.2f}, {bbox[2]:.2f}, {bbox[3]:.2f}"
        
        return {
            "has_data": True,
            "total_images": total_images,
            "collections": collections,
            "platforms": platforms,
            "temporal_coverage": temporal_coverage,
            "quality_summary": quality_summary,
            "geographic_coverage": geographic_coverage,
            "collection_details": self._get_collection_details(collections),
            "sample_features": features[:3] if features else []  # First 3 for detailed analysis
        }
    
    def _get_collection_details(self, collections: List[str]) -> Dict[str, str]:
        """Get human-readable descriptions of satellite collections"""
        
        collection_descriptions = {
            "sentinel-2-l2a": "Sentinel-2 optical imagery (10-60m resolution)",
            "sentinel-1-grd": "Sentinel-1 synthetic aperture radar (SAR) data",
            "landsat-c2-l2": "Landsat optical and thermal infrared imagery (30m resolution)",
            "hls-l30": "Harmonized Landsat Sentinel-2 L30 (30m resolution)",
            "hls-s30": "Harmonized Landsat Sentinel-2 S30 (30m resolution)",
            "modis-14A1-061": "MODIS thermal anomalies and fire detection data",
            "modis-14A2-061": "MODIS thermal anomalies 8-day composite",
            "modis-MCD64A1-061": "MODIS burned area product",
            "naip": "NAIP aerial imagery (0.6-1m resolution)",
            "cop-dem-glo-30": "Copernicus 30m digital elevation model",
            "cop-dem-glo-90": "Copernicus 90m digital elevation model",
            "nasadem": "NASA DEM 30m global elevation data",
            "sentinel-1-rtc": "Sentinel-1 radiometrically terrain corrected SAR",
            "era5-pds": "ERA5 reanalysis weather data",
            "daymet-daily-na": "Daymet daily weather data North America",
            "esa-worldcover": "ESA WorldCover global land cover classification",
            "modis-13Q1-061": "MODIS vegetation indices"
        }
        
        return {
            collection: collection_descriptions.get(collection, f"{collection} satellite data")
            for collection in collections
        }
    
    def _create_brief_map_data_prompt(self) -> str:
        """Create brief prompt for simple map data requests"""
        return """
        You are a geospatial data specialist. The system IS CURRENTLY DISPLAYING data on the map.

        Provide a VERY BRIEF response (1-2 sentences maximum) describing the data being displayed:
        
        **CRITICAL REQUIREMENTS (you must include ALL of these):**
        1. Number of datasets/images (from DATASET field in data summary)
        2. Collection name (from DATA TYPES field) - use the full collection ID
        3. Data type description (e.g., "aerial imagery", "optical imagery", "thermal data")
        4. Location name (extract from user query or bbox)
        5. Date range (from DATE RANGE field) - use EXACT dates shown, NOT "dates not provided"
        6. Cloud cover (from DATA QUALITY field) - if applicable, otherwise omit
        7. Satellite platform (from SATELLITES field) - if available, otherwise use collection name
        
        **FORMAT:**
        "Displaying [number] [data type description] from [collection ID] for [location] captured on [date info], with [cloud cover info if applicable]."
        
        **EXAMPLES:**
        - "Displaying 8 optical images from landsat-c2-l2 for Seattle captured between June 15 - August 22, 2025, with average cloud cover of 12%."
        - "Displaying 30 thermal anomaly datasets from modis-14A1-061 for Los Angeles County captured between February 2 - 26, 2025."
        - "Displaying 1 optical image from sentinel-2-l2a for New York City captured on October 21, 2025, with 0% cloud cover."
        - "Displaying 1 aerial imagery from naip for New York City captured on September 1, 2023."
        
        **RULES:**
        - DO NOT use quotation marks around your response
        - DO NOT say "dates not provided" - extract dates from DATE RANGE field
        - DO NOT make quality judgments ("excellent", "good")
        - Use present tense: "Displaying...", "Showing..."
        - State facts only from the data summary provided

        **USER QUERY:** {{$user_query}}
        **DATA BEING DISPLAYED:** {{$data_summary}}
        **CONVERSATION CONTEXT:** {{$conversation_context}}

        Brief description:
        """

    def _create_detailed_analysis_prompt(self) -> str:
        """Create detailed prompt for analytical requests"""
        return """
        You are an Earth science specialist providing detailed analysis based on the conversation context.

        Provide comprehensive analysis with:
        - 1-3 paragraphs of detailed insights
        - Bullet points for key findings
        - Scientific explanations and implications  
        - Actionable information
        - ALWAYS include exact parameters when referencing data: specific dates, location names, cloud cover percentages, collection names
        - DO NOT use quotation marks around your response
        - DO NOT make subjective quality comments like "excellent", "ensuring clarity", "good quality"
        - Reference previous discussion points when relevant

        **USER QUERY:** {{$user_query}}
        **CONTEXT DATA:** {{$data_summary}}
        **CONVERSATION CONTEXT:** {{$conversation_context}}

        Detailed analysis:
        """

    def _create_hybrid_response_prompt(self) -> str:
        """Create prompt for combined data display + analysis"""
        return """
        You are a geospatial data specialist. The system IS DISPLAYING data on the map.

        Provide a hybrid response combining brief data description with detailed analysis:
        
        1. FIRST: Brief data description (1-2 sentences maximum):
           - Use present tense: "Displaying...", "Showing...", "The map shows..."
           - Mention data type, source, and date range ONLY
           - Include number of datasets/images
           - ALWAYS include exact parameters: specific dates (not date ranges unless showing range), location name, cloud cover percentage if applicable, collection name
           - DO NOT use quotation marks around your entire response
           - DO NOT mention data quality, resolution, coverage suitability, or make subjective comments like "excellent", "ensuring clarity", "good quality"
        
        2. THEN: Address the user's question with detailed analysis:
           - Provide comprehensive insights and explanations
           - Use bullet points for key findings when appropriate
           - Include scientific context and implications
           - Offer actionable information related to the query
           - Reference conversation context when relevant
           - State facts only - no editorial comments about quality

        **USER QUERY:** {{$user_query}}
        **DATA BEING DISPLAYED:** {{$data_summary}}
        **CONVERSATION CONTEXT:** {{$conversation_context}}

        Response:
        """

    def _create_response_generation_prompt(self, classification: Dict[str, Any] = None) -> str:
        """Create appropriate prompt based on classification"""
        if not classification:
            return self._create_brief_map_data_prompt()
            
        intent_type = classification.get('intent_type', 'stac')
        
        # Map intent types to response prompts
        # - vision: Analyze currently visible imagery → Not used in this method (handled separately)
        # - stac: Load new satellite imagery only → Brief data specs
        # - hybrid: Load new imagery AND analyze it → Hybrid response (data + analysis)
        # - contextual: Information/education only → Detailed analysis
        if intent_type in ['stac', 'map_only_request', 'map_data_request']:  # Legacy names for backwards compatibility
            return self._create_brief_map_data_prompt()
        elif intent_type in ['contextual', 'chat_only_request', 'contextual_analysis']:  # Legacy names for backwards compatibility
            return self._create_detailed_analysis_prompt()
        elif intent_type in ['hybrid', 'hybrid_request']:  # Legacy name for backwards compatibility
            return self._create_hybrid_response_prompt()
        else:
            return self._create_brief_map_data_prompt()  # Default fallback
    
    async def _generate_response_with_sk(self, prompt_template: str, user_query: str, data_summary: Dict[str, Any], conversation_context: str = "") -> str:
        """Generate response using Semantic Kernel with the prepared data and conversation context"""
        
        try:
            # Create prompt template configuration for SK 1.36.2
            prompt_config = PromptTemplateConfig(
                template=prompt_template,
                name="generate_response",
                description="Generate response based on user query, data summary, and conversation context",
                template_format="semantic-kernel",
                input_variables=[
                    InputVariable(name="user_query", description="The user's natural language query"),
                    InputVariable(name="data_summary", description="Comprehensive analysis of the STAC data found"),
                    InputVariable(name="conversation_context", description="Recent conversation history for context")
                ]
            )
            
            # Prepare data summary as formatted text for the LLM
            formatted_data_summary = self._format_data_summary_for_llm(data_summary)
            
            # Execute using SK 1.36.2 invoke_prompt
            arguments = KernelArguments(
                user_query=user_query,
                data_summary=formatted_data_summary,
                conversation_context=conversation_context or "No previous conversation context."
            )
            result = await self.kernel.invoke_prompt(
                prompt=prompt_template,
                function_name="generate_response",
                plugin_name="semantic_translator",
                arguments=arguments,
                prompt_template_config=prompt_config
            )
            
            # Extract response content with comprehensive fallback handling
            content = self._extract_clean_content_from_sk_result(result)
            
            # Final validation and cleanup
            if not content or content.strip() == "":
                logger.warning("Empty content returned from Semantic Kernel, using fallback")
                return f"Found {data_summary.get('total_images', 0)} satellite images for your query."
            
            # Clean and return the response
            cleaned_content = content.strip().replace('\\n', '\n').replace('\\"', '"')
            logger.info(f"Generated intelligent response: {cleaned_content[:200]}...")
            
            return cleaned_content
            
        except Exception as e:
            logger.error(f"SK response generation failed: {e}")
            raise Exception(f"Failed to generate intelligent response: {e}")
    
    def _extract_clean_content_from_sk_result(self, result) -> str:
        """Extract clean text content from Semantic Kernel result with comprehensive error handling"""
        
        if not result:
            return ""
        
        # Method 1: Direct value extraction (most common path)
        if hasattr(result, 'value') and result.value:
            # Check if it's a simple string
            if isinstance(result.value, str):
                return result.value
            
            # Check for ChatMessageContent structure
            if hasattr(result.value, 'inner_content'):
                if hasattr(result.value.inner_content, 'content'):
                    return str(result.value.inner_content.content)
                elif hasattr(result.value.inner_content, 'text'):
                    return str(result.value.inner_content.text)
            
            # Check for direct content attribute
            if hasattr(result.value, 'content'):
                if isinstance(result.value.content, str):
                    return result.value.content
                elif hasattr(result.value.content, 'text'):
                    return str(result.value.content.text)
            
            # Check for items collection
            if hasattr(result.value, 'items') and result.value.items:
                for item in result.value.items:
                    if hasattr(item, 'text') and item.text:
                        return str(item.text)
                    elif hasattr(item, 'content') and item.content:
                        return str(item.content)
        
        # Method 2: String parsing for debug objects that leaked through
        result_str = str(result)
        if 'ChatMessageContent' in result_str or 'ChatCompletion' in result_str:
            import re
            # Comprehensive regex patterns to extract content
            patterns = [
                r"content='([^']*)'",           # Single quotes
                r'content="([^"]*)"',           # Double quotes  
                r"content=([^,\]\)]+)",         # Unquoted content
                r"text='([^']*)'",              # Text field single quotes
                r'text="([^"]*)"',              # Text field double quotes
                r"message='([^']*)'",           # Message field
                r'message="([^"]*)"',           # Message field double quotes
                r"'text':\s*'([^']*)'",         # JSON-like structure
                r'"text":\s*"([^"]*)"',         # JSON-like structure
                r"content=ChatCompletionMessage\(content='([^']*)'",  # Nested structure
            ]
            
            for pattern in patterns:
                match = re.search(pattern, result_str, re.DOTALL)
                if match:
                    extracted = match.group(1).strip()
                    if extracted and len(extracted) > 10:  # Ensure it's meaningful content
                        logger.info(f"Extracted content via regex: {pattern}")
                        return extracted
        
        # Method 3: Last resort - return string representation if it looks like normal text
        result_str = str(result)
        if result_str and not any(debug_marker in result_str for debug_marker in ['ChatMessageContent', 'ChatCompletion', 'inner_content=', 'role=', 'function_call=']):
            return result_str
        
        # If all else fails, return empty string to trigger fallback
        logger.warning(f"Could not extract clean content from SK result: {type(result)} - {str(result)[:200]}")
        return ""
    
    def _format_data_summary_for_llm(self, data_summary: Dict[str, Any]) -> str:
        """Format the data summary with detailed technical specifications for map data responses"""
        
        if not data_summary.get("has_data", False):
            return "No satellite data was found for this query. The search returned zero results."
        
        # Build detailed summary focusing on data characteristics for map visualization
        summary_parts = []
        
        # Image count and basic info
        total_images = data_summary.get('total_images', 0)
        summary_parts.append(f"DATASET: {total_images} satellite images available for map display")
        
        # Satellite platforms and sensors (more specific than collections)
        if data_summary.get("platforms"):
            platforms_text = ", ".join(data_summary["platforms"])
            summary_parts.append(f"SATELLITES: {platforms_text}")
        
        # Time range with specific dates
        if data_summary.get("temporal_coverage"):
            summary_parts.append(f"DATE RANGE: {data_summary['temporal_coverage']}")
        
        # Data quality details (cloud cover, resolution, etc.)
        if data_summary.get("quality_summary"):
            summary_parts.append(f"DATA QUALITY: {data_summary['quality_summary']}")
        
        # Cloud cover statistics if available
        if data_summary.get("cloud_coverage"):
            summary_parts.append(f"CLOUD COVER: {data_summary['cloud_coverage']}")
        
        # Resolution details
        if data_summary.get("resolution"):
            summary_parts.append(f"RESOLUTION: {data_summary['resolution']}")
        
        # Geographic coverage
        if data_summary.get("geographic_coverage"):
            summary_parts.append(f"COVERAGE AREA: {data_summary['geographic_coverage']}")
        
        # Collection types with descriptions
        if data_summary.get("collections"):
            summary_parts.append("DATA TYPES:")
            collection_details = data_summary.get("collection_details", {})
            for collection in data_summary["collections"]:
                description = collection_details.get(collection, f"{collection} dataset")
                summary_parts.append(f"- {collection}: {description}")
        
        # Processing level or data characteristics
        if data_summary.get("processing_level"):
            summary_parts.append(f"PROCESSING: {data_summary['processing_level']}")
        
        return "\n".join(summary_parts)

    # =============================================================================
    # PIN LOCATION HELPER METHODS
    # =============================================================================
    
    def _create_pin_bbox(self, lat: float, lng: float, radius_miles: float = 50) -> List[float]:
        """
        Create bounding box around pin with specified radius.
        
        Args:
            lat: Latitude in decimal degrees
            lng: Longitude in decimal degrees
            radius_miles: Radius in miles (default 50 for GEOINT analysis)
        
        Returns:
            [west, south, east, north] bbox in EPSG:4326
        """
        import math
        
        radius_km = radius_miles * 1.60934  # Convert miles to km
        
        # Approximate degrees per km (varies by latitude)
        lat_offset = radius_km / 111.0  # 1° latitude ≈ 111 km
        lng_offset = radius_km / (111.0 * math.cos(math.radians(lat)))  # Adjust for latitude
        
        west = lng - lng_offset
        south = lat - lat_offset
        east = lng + lng_offset
        north = lat + lat_offset
        
        return [west, south, east, north]

    # =============================================================================
    # GEOINT INTELLIGENCE ROUTING AND PROCESSING
    # =============================================================================
    
    async def _detect_geoint_intent(self, query: str) -> Optional[Dict[str, Any]]:
        """
        Detect GEOINT-specific queries using GPT-4 powered intelligence analysis.
        
        Args:
            query: Natural language query to analyze
            
        Returns:
            Dict with GEOINT intent details or None if not a GEOINT query
        """
        try:
            # Ensure kernel is initialized for GPT-4 analysis
            await self._ensure_kernel_initialized()
            
            if not self._kernel_initialized or self.kernel is None:
                # Fallback to simple keyword detection if GPT-4 unavailable
                logger.warning("🎯 GPT-4 unavailable, using fallback keyword detection for GEOINT")
                return self._detect_geoint_intent_fallback(query)
            
            # Create GPT-4 GEOINT classification prompt
            geoint_classification_prompt = """
You are a GEOINT (Geospatial Intelligence) analysis expert. Analyze the user's query to determine if it requires specialized geospatial intelligence processing with analytical calculations.

**GEOINT vs Regular Map Queries:**

GEOINT queries require ANALYTICAL PROCESSING (calculations, measurements, assessments):
- Terrain analysis with slope/gradient calculations
- Mobility assessments with traversability classifications
- Line-of-sight and viewshed computations
- Elevation profiles with distance/height measurements
- Route planning with terrain considerations
- Emergency response accessibility analysis
- Vehicle/personnel movement assessments

Regular map queries just want to SEE satellite/imagery data:
- "Show me imagery of [location]"
- "Display Sentinel-2/Landsat/SAR data"
- "Get satellite images of [place]"
- "Recent imagery of [area]"

**GEOINT Analysis Types:**

**terrain_analysis**: Calculate terrain characteristics
- Intent: Analyze slope, aspect, gradient, roughness, steepness
- Indicators: Words like "analyze", "calculate", "measure", "assess" + terrain features
- Examples: 
  * "Analyze terrain slope near Fort Carson"
  * "Calculate terrain roughness in mountains"
  * "What is the gradient of this hillside?"
  * "Assess terrain steepness for construction"

**mobility_analysis**: Assess vehicle/personnel traversability
- Intent: Evaluate movement capability, accessibility, route feasibility
- Indicators: Questions about movement, access, traversability, passability, routes
- Context: Emergency response, military operations, evacuation, rescue, convoy planning
- Examples:
  * "Can vehicles access this flood zone?"
  * "Evaluate emergency response accessibility"
  * "Assess mobility for convoy movement"
  * "Is this terrain traversable for trucks?"
  * "Analyze evacuation route feasibility"
  * "Vehicle accessibility for rescue operations"
  * "Can tanks cross this terrain?"

**line_of_sight**: Calculate visibility and viewshed
- Intent: Determine what is visible from a position
- Indicators: Words like "visibility", "can I see", "line of sight", "viewshed", "observation"
- Examples:
  * "Calculate line of sight from observation post"
  * "What can be seen from this hilltop?"
  * "Viewshed analysis for surveillance"
  * "Is there line of sight between A and B?"

**elevation_profile**: Generate elevation cross-sections
- Intent: Show elevation changes along a path/route
- Indicators: "Elevation profile", "cross-section", "terrain profile along [path]"
- Examples:
  * "Elevation profile from Denver to Colorado Springs"
  * "Show terrain cross-section along this route"
  * "Elevation changes along the highway"

**CRITICAL DECISION RULES:**

1. If query asks for CALCULATIONS, ASSESSMENTS, or ANALYSIS → GEOINT
2. If query asks about MOVEMENT, ACCESS, TRAVERSABILITY → mobility_analysis
3. If query asks about EMERGENCY RESPONSE, EVACUATION, RESCUE → mobility_analysis
4. If query just wants to SEE/DISPLAY imagery → NOT GEOINT
5. Words like "analyze", "assess", "evaluate", "calculate", "determine" → GEOINT
6. Words like "show", "display", "get", "imagery", "satellite" → NOT GEOINT

**Response Format:**

If GEOINT analysis is needed:
{
  "is_geoint": true,
  "analysis_type": "terrain_analysis|mobility_analysis|line_of_sight|elevation_profile",
  "confidence": 0.1-1.0,
  "reasoning": "Brief explanation of why this requires analytical processing",
  "military_context": true/false
}

If NOT GEOINT (regular map/satellite data request):
{
  "is_geoint": false,
  "reasoning": "Brief explanation of why this is just imagery display"
}

**Query to analyze:** "{{$query}}"

**Instructions:** Return ONLY the JSON object. No markdown formatting, no explanations, no additional text.
"""
            
            # Execute GPT-4 classification
            arguments = KernelArguments(query=query)
            result = await asyncio.wait_for(
                self.kernel.invoke_prompt(
                    prompt=geoint_classification_prompt,
                    function_name="classify_geoint",
                    plugin_name="geoint_classifier",
                    arguments=arguments
                ),
                timeout=15.0
            )
            
            # Parse the JSON response
            content = self._extract_clean_content_from_sk_result(result)
            content = content.strip()
            
            # Clean up the response to extract JSON
            if '```json' in content:
                content = content.split('```json')[1].split('```')[0]
            elif '```' in content:
                content = content.split('```')[1].split('```')[0]
            
            try:
                classification = json.loads(content)
            except json.JSONDecodeError as e:
                logger.error(f"❌ Failed to parse GEOINT classification JSON: {e}")
                logger.error(f"Raw content: {content}")
                return self._detect_geoint_intent_fallback(query)
            
            # Validate and process GPT-4 result
            if not classification.get('is_geoint', False):
                logger.info(f"🎯 GPT-4: Not a GEOINT query - {classification.get('reasoning', 'No reason provided')}")
                return None
            
            analysis_type = classification.get('analysis_type')
            confidence = classification.get('confidence', 0.8)
            reasoning = classification.get('reasoning', 'GPT-4 classified as GEOINT')
            military_context = classification.get('military_context', False)
            
            logger.info(f"🎯 GPT-4 GEOINT detection: {analysis_type} (confidence: {confidence})")
            logger.info(f"🎯 Reasoning: {reasoning}")
            
            return {
                'intent_type': analysis_type,
                'analysis_type': analysis_type,
                'confidence': confidence,
                'reasoning': reasoning,
                'military_context': military_context,
                'detection_method': 'gpt4_analysis'
            }
            
        except asyncio.TimeoutError:
            logger.error("❌ GEOINT classification timeout, using fallback")
            return self._detect_geoint_intent_fallback(query)
        except Exception as e:
            logger.error(f"❌ Error in GPT-4 GEOINT detection: {str(e)}")
            return self._detect_geoint_intent_fallback(query)
    
    def _detect_geoint_intent_fallback(self, query: str) -> Optional[Dict[str, Any]]:
        """
        Fallback GEOINT detection using keyword matching when GPT-4 is unavailable.
        """
        try:
            query_lower = query.lower()
            
            # Define GEOINT intent patterns (original keyword-based approach)
            geoint_patterns = {
                'terrain_analysis': {
                    'keywords': ['slope', 'terrain', 'elevation', 'topography', 'hillshade', 'aspect', 'gradient', 'contour'],
                    'phrases': ['terrain analysis', 'slope analysis', 'elevation profile', 'topographic analysis', 'terrain roughness'],
                    'analysis_type': 'terrain_analysis'
                },
                'mobility_analysis': {
                    'keywords': ['mobility', 'traversability', 'vehicle', 'route', 'passable', 'impassable', 'movement', 'accessibility', 'access', 'emergency response', 'evacuation', 'convoy'],
                    'phrases': ['mobility analysis', 'vehicle mobility', 'terrain mobility', 'route planning', 'traversability assessment', 'vehicle accessibility', 'emergency access', 'flood access', 'rescue access'],
                    'analysis_type': 'mobility_analysis'
                },
                'line_of_sight': {
                    'keywords': ['visibility', 'line of sight', 'viewshed', 'observation', 'visible', 'hidden', 'obstruction'],
                    'phrases': ['line of sight', 'line-of-sight', 'visibility analysis', 'viewshed analysis', 'observation post'],
                    'analysis_type': 'line_of_sight'
                },
                'elevation_profile': {
                    'keywords': ['elevation profile', 'cross section', 'profile', 'transect'],
                    'phrases': ['elevation profile', 'cross-section', 'terrain profile', 'elevation transect'],
                    'analysis_type': 'elevation_profile'
                }
            }
            
            # Check for GEOINT patterns
            for intent_type, patterns in geoint_patterns.items():
                # Check exact phrases first (higher confidence)
                for phrase in patterns['phrases']:
                    if phrase in query_lower:
                        logger.info(f"🎯 GEOINT phrase match: '{phrase}' -> {intent_type}")
                        return {
                            'intent_type': intent_type,
                            'analysis_type': patterns['analysis_type'],
                            'confidence': 0.9,
                            'matched_phrase': phrase,
                            'detection_method': 'fallback_phrase_match'
                        }
                
                # Check keywords (medium confidence)
                keyword_matches = sum(1 for keyword in patterns['keywords'] if keyword in query_lower)
                if keyword_matches >= 1:
                    confidence = min(0.8, 0.4 + (keyword_matches * 0.2))
                    logger.info(f"🎯 GEOINT keyword match: {keyword_matches} keywords -> {intent_type}")
                    return {
                        'intent_type': intent_type,
                        'analysis_type': patterns['analysis_type'],
                        'confidence': confidence,
                        'matched_keywords': keyword_matches,
                        'detection_method': 'fallback_keyword_match'
                    }
            
            # Check for military/tactical context that might indicate GEOINT needs
            military_indicators = ['tactical', 'military', 'defense', 'surveillance', 'reconnaissance', 'intel', 'mission']
            geoint_context = ['terrain', 'visibility', 'mobility', 'elevation', 'obstacle', 'cover']
            
            military_matches = sum(1 for indicator in military_indicators if indicator in query_lower)
            geoint_matches = sum(1 for context in geoint_context if context in query_lower)
            
            if military_matches >= 1 and geoint_matches >= 1:
                logger.info(f"🎯 Military GEOINT context detected: {military_matches} military + {geoint_matches} geoint terms")
                return {
                    'intent_type': 'military_geoint',
                    'analysis_type': 'terrain_analysis',  # Default to terrain analysis
                    'confidence': 0.7,
                    'matched_military': military_matches,
                    'matched_geoint': geoint_matches,
                    'detection_method': 'fallback_context_match'
                }
            
            return None
            
        except Exception as e:
            logger.error(f"❌ Error in fallback GEOINT intent detection: {str(e)}")
            return None
    
    async def _route_to_geoint_service(self, query: str, geoint_intent: Dict[str, Any]) -> Dict[str, Any]:
        """
        Route GEOINT queries to the appropriate specialized service.
        
        Args:
            query: Original natural language query
            geoint_intent: Detected GEOINT intent information
            
        Returns:
            Dict containing GEOINT service routing information
        """
        try:
            logger.info(f"🎯 Routing to GEOINT service: {geoint_intent['analysis_type']}")
            
            # Extract location information for GEOINT analysis
            entities = await self.extract_entities(query)
            location_info = entities.get("location", {})
            location_name = location_info.get("name")
            
            # Resolve location to bounding box if available
            bbox = None
            if location_name:
                bbox = await self.resolve_location_to_bbox(
                    location_name, 
                    location_info.get("type", "region")
                )
                logger.info(f"📍 GEOINT location resolved: {location_name} -> {bbox}")
            
            # Extract additional parameters for GEOINT analysis
            geoint_params = self._extract_geoint_parameters(query, geoint_intent['analysis_type'])
            
            # Build GEOINT service request
            geoint_request = {
                'service_type': 'geoint',
                'analysis_type': geoint_intent['analysis_type'],
                'query': query,
                'bbox': bbox,
                'location_info': location_info,
                'parameters': geoint_params,
                'intent_confidence': geoint_intent['confidence'],
                'detection_method': geoint_intent['detection_method'],
                'extracted_entities': entities
            }
            
            # Add specific routing information based on analysis type
            if geoint_intent['analysis_type'] == 'terrain_analysis':
                geoint_request['recommended_resolution'] = 30  # meters
                geoint_request['analysis_options'] = ['slope', 'aspect', 'hillshade', 'roughness']
                
            elif geoint_intent['analysis_type'] == 'mobility_analysis':
                geoint_request['vehicle_type'] = geoint_params.get('vehicle_type', 'ground')
                geoint_request['weather_condition'] = geoint_params.get('weather_condition', 'dry')
                
            elif geoint_intent['analysis_type'] == 'line_of_sight':
                geoint_request['observer_height'] = geoint_params.get('observer_height', 1.75)
                geoint_request['target_height'] = geoint_params.get('target_height', 1.75)
                
            elif geoint_intent['analysis_type'] == 'elevation_profile':
                geoint_request['sample_distance'] = geoint_params.get('sample_distance', 100)
            
            logger.info(f"✅ GEOINT service routing completed: {geoint_intent['analysis_type']}")
            
            return geoint_request
            
        except Exception as e:
            logger.error(f"❌ Error routing to GEOINT service: {str(e)}")
            return {
                'error': f"GEOINT routing failed: {str(e)}",
                'service_type': 'geoint',
                'analysis_type': geoint_intent.get('analysis_type', 'unknown'),
                'fallback_to_stac': True
            }
    
    def _extract_geoint_parameters(self, query: str, analysis_type: str) -> Dict[str, Any]:
        """
        Extract specific parameters for GEOINT analysis from the query.
        
        Args:
            query: Natural language query
            analysis_type: Type of GEOINT analysis to perform
            
        Returns:
            Dict containing extracted parameters
        """
        try:
            query_lower = query.lower()
            params = {}
            
            # Common parameter extraction
            if 'vehicle' in query_lower:
                if any(vehicle in query_lower for vehicle in ['tank', 'armor', 'tracked']):
                    params['vehicle_type'] = 'tracked_vehicle'
                elif any(vehicle in query_lower for vehicle in ['truck', 'wheeled', 'humvee']):
                    params['vehicle_type'] = 'light_vehicle'
                elif 'heavy' in query_lower:
                    params['vehicle_type'] = 'heavy_vehicle'
                else:
                    params['vehicle_type'] = 'light_vehicle'
            
            # Weather condition extraction
            weather_terms = {
                'wet': ['wet', 'rain', 'rainy', 'precipitation'],
                'snow': ['snow', 'snowy', 'winter'],
                'mud': ['mud', 'muddy'],
                'dry': ['dry', 'clear', 'sunny']
            }
            
            for condition, terms in weather_terms.items():
                if any(term in query_lower for term in terms):
                    params['weather_condition'] = condition
                    break
            
            # Height/elevation parameter extraction
            import re
            height_pattern = r'(\d+(?:\.\d+)?)\s*(?:m|meter|meters|ft|feet|foot)'
            height_matches = re.findall(height_pattern, query_lower)
            
            if height_matches:
                height_value = float(height_matches[0])
                # Convert feet to meters if needed
                if any(unit in query_lower for unit in ['ft', 'feet', 'foot']):
                    height_value *= 0.3048
                
                if 'observer' in query_lower or 'eye' in query_lower:
                    params['observer_height'] = height_value
                elif 'target' in query_lower:
                    params['target_height'] = height_value
                else:
                    params['observer_height'] = height_value
            
            # Resolution parameter extraction
            resolution_pattern = r'(\d+)\s*(?:m|meter|meters)?\s*resolution'
            resolution_matches = re.findall(resolution_pattern, query_lower)
            if resolution_matches:
                params['resolution'] = int(resolution_matches[0])
            
            logger.info(f"🔧 Extracted GEOINT parameters: {params}")
            return params
            
        except Exception as e:
            logger.error(f"❌ Parameter extraction failed: {str(e)}")
            return {}
    
    def _get_geoint_recommended_collections(self, analysis_type: str) -> List[str]:
        """
        Get recommended STAC collections for different GEOINT analysis types.
        
        Args:
            analysis_type: Type of GEOINT analysis
            
        Returns:
            List of recommended STAC collection IDs
        """
        collection_mapping = {
            'terrain_analysis': ['cop-dem-glo-30', 'nasadem', 'cop-dem-glo-90'],
            'mobility_analysis': ['cop-dem-glo-30', 'sentinel-1-grd', 'landsat-c2-l2'],
            'line_of_sight': ['cop-dem-glo-30', 'nasadem'],
            'elevation_profile': ['cop-dem-glo-30', 'nasadem', 'cop-dem-glo-90']
        }
        
        return collection_mapping.get(analysis_type, ['cop-dem-glo-30'])


# =============================================================================
# STANDALONE WRAPPER FUNCTIONS FOR BACKWARD COMPATIBILITY
# =============================================================================

async def process_query_with_openai(query: str) -> Dict[str, Any]:
    """
    Standalone function wrapper for processing queries with Azure OpenAI
    
    This function provides backward compatibility for code that expects
    a standalone process_query_with_openai function.
    
    Args:
        query: Natural language query to process
        
    Returns:
        Dictionary containing STAC query and extracted entities
    """
    try:
        logger.info(f"🔍 Processing standalone query: '{query}'")
        
        # Get configuration from environment
        endpoint = os.getenv('AZURE_OPENAI_ENDPOINT')
        api_key = os.getenv('AZURE_OPENAI_API_KEY') 
        model = os.getenv('AZURE_OPENAI_DEPLOYMENT_NAME', os.getenv('AZURE_OPENAI_MODEL_NAME', 'gpt-5'))
        
        if not endpoint or not api_key:
            logger.error("❌ Missing Azure OpenAI configuration")
            return {
                "error": "Missing Azure OpenAI configuration",
                "required_env_vars": ["AZURE_OPENAI_ENDPOINT", "AZURE_OPENAI_API_KEY"]
            }
        
        logger.info(f"✅ Using Azure OpenAI endpoint: {endpoint}")
        logger.info(f"✅ Using model: {model}")
        
        # Initialize translator and process query
        translator = SemanticQueryTranslator(endpoint, api_key, model)
        result = await translator.translate_query(query)
        
        logger.info(f"✅ Successfully processed query via standalone function")
        return result
        
    except Exception as e:
        logger.error(f"❌ Error in standalone process_query_with_openai: {e}")
        return {
            "error": str(e),
            "query": query,
            "function": "process_query_with_openai"
        }


def process_query_with_openai_sync(query: str) -> Dict[str, Any]:
    """
    Synchronous wrapper for the async process_query_with_openai function
    
    This allows calling the function without async/await syntax.
    
    Args:
        query: Natural language query to process
        
    Returns:
        Dictionary containing STAC query and extracted entities
    """
    try:
        logger.info(f"🔄 Running synchronous wrapper for: '{query}'")
        result = asyncio.run(process_query_with_openai(query))
        return result
    except Exception as e:
        logger.error(f"❌ Error in synchronous wrapper: {e}")
        return {
            "error": str(e),
            "query": query,
            "function": "process_query_with_openai_sync"
        }


# For module-level access without instantiation
async def create_semantic_translator() -> SemanticQueryTranslator:
    """
    Factory function to create a configured SemanticQueryTranslator instance
    
    Returns:
        Configured SemanticQueryTranslator instance
    """
    endpoint = os.getenv('AZURE_OPENAI_ENDPOINT')
    api_key = os.getenv('AZURE_OPENAI_API_KEY')
    model = os.getenv('AZURE_OPENAI_DEPLOYMENT_NAME', os.getenv('AZURE_OPENAI_MODEL_NAME', 'gpt-5'))
    
    if not endpoint or not api_key:
        raise ValueError("Missing required Azure OpenAI configuration")
    
    return SemanticQueryTranslator(endpoint, api_key, model)
