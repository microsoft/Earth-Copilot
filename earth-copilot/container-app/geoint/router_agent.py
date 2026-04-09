"""
Router Agent - Semantic Kernel Agent for Query Classification and Routing

This agent replaces the old LLM wrapper classification with a true agentic approach.
It observes session context and decides how to handle each query using tools.

Query Types Handled:
1. MAP_ONLY - Fly to location without loading imagery
2. STAC_SEARCH - Load satellite imagery from STAC catalog  
3. CONTEXTUAL - Answer questions using chat context and vision (follow-ups)
4. HYBRID - Load imagery AND analyze it (combines STAC + Vision)

Architecture:
- Uses Semantic Kernel ChatCompletionAgent (consistent with TerrainAgent)
- Has tools it can invoke to inspect context and route queries
- Maintains per-session ChatHistory for conversation memory
- Wraps existing semantic_translator and vision_agent functions
"""

import logging
import os
import re
from typing import Dict, Any, Optional, List, Annotated
from datetime import datetime, timedelta
import asyncio
import json

from semantic_kernel import Kernel
from semantic_kernel.agents import ChatCompletionAgent
from semantic_kernel.connectors.ai.open_ai import AzureChatCompletion
from semantic_kernel.connectors.ai.function_choice_behavior import FunctionChoiceBehavior
from semantic_kernel.contents.chat_history import ChatHistory
from semantic_kernel.contents.chat_message_content import ChatMessageContent
from semantic_kernel.contents.utils.author_role import AuthorRole
from semantic_kernel.functions import kernel_function
from azure.identity import DefaultAzureCredential, get_bearer_token_provider
from cloud_config import cloud_cfg

# Import comprehensive collection keywords from CollectionMapper
try:
    from collection_name_mapper import CollectionMapper
    _collection_mapper = CollectionMapper()
    # Get all keywords from the mapper
    COLLECTION_KEYWORDS = set(_collection_mapper.keyword_map.keys())
    logging.info(f" Loaded {len(COLLECTION_KEYWORDS)} collection keywords from CollectionMapper")
except Exception as e:
    logging.warning(f" Could not load CollectionMapper: {e}")
    COLLECTION_KEYWORDS = set()

# Import comprehensive location list from LocationResolver  
try:
    from location_resolver import EnhancedLocationResolver
    LOCATION_NAMES = set(EnhancedLocationResolver.STORED_LOCATIONS.keys())
    logging.info(f" Loaded {len(LOCATION_NAMES)} location names from LocationResolver")
except Exception as e:
    logging.warning(f" Could not load LocationResolver locations: {e}")
    LOCATION_NAMES = set()

logger = logging.getLogger(__name__)


# ============================================================================
# ROUTER AGENT SYSTEM PROMPT
# ============================================================================

ROUTER_AGENT_INSTRUCTIONS = """You are a Router Agent for an Earth observation system.

Your job is to analyze user queries and ROUTE them to the correct handler by calling the appropriate tool.

## ROUTING DECISION PROCESS

ALWAYS call tools to gather context and execute actions. Never just respond with text.

### Step 1: Get Session Context
FIRST call `get_session_context` to understand:
- Does the user have a map already rendered (`has_rendered_map`)?
- What location are they viewing (`last_location`, `last_bbox`)?
- What collections are displayed (`last_collections`)?
- What was their previous query (`last_query`)?

### Step 2: Analyze Query Type
Based on the query and context, determine the type:

1. **MAP_ONLY** - User wants to navigate to a location WITHOUT loading satellite/data imagery
   - Keywords: "show me", "go to", "fly to", "take me to", "zoom to"
   - **BARE LOCATION NAMES**: Just a place name like "Grand Canyon", "Tokyo", "Paris" = MAP_ONLY
   - NO collection/data keywords (Sentinel, Landsat, elevation, terrain, DEM, etc.)
   - NO analysis keywords (analyze, describe, identify, what is)
   - Examples: "Show me Paris", "Go to Tokyo", "Fly to Denver", "Grand Canyon", "Amazon rainforest"
   - **NOT MAP_ONLY**: "Show elevation map of X", "Show terrain of X", "Show Sentinel of X"
   -> Call `navigate_to_location`

2. **STAC_SEARCH** - User wants to LOAD satellite/geospatial data imagery
   - Keywords: "show me [collection/data] of", "load", "display imagery", "get data"
   - Contains collection names (Sentinel, Landsat, HLS, MODIS, NAIP)
   - OR contains data type keywords (elevation, terrain, DEM, topography)
   - OR contains disaster/event types (flood, wildfire, hurricane)
   - Examples: "Show me Sentinel-2 of Seattle", "Load HLS data for California",
     **"Show elevation map of Grand Canyon"**, "Display terrain of Alps"
   -> Call `search_and_render_stac`
   
   **CRITICAL: FOLLOW-UP STAC QUERIES**
   If user asks for satellite imagery WITHOUT specifying a location (e.g., "show me Sentinel tiles",
   "load Landsat data", "get MODIS imagery here") AND `last_bbox` or `last_location` exists in context:
   - Set `use_current_location=true` to use the current map viewport
   - This ensures we search at the location they already navigated to
   - Example flow: User says "Show me Kansas" -> flies to Kansas -> then says "show me Sentinel-2" 
     -> search_and_render_stac(query="show me Sentinel-2", session_id=..., use_current_location=true)

3. **VISION ANALYSIS** - User asks about what's VISIBLE on the map OR temporal comparisons
   - Keywords: "here", "this", "visible", "in this image", "what do you see", "describe"
   - The word "here" or "this" strongly indicates the user is asking about the CURRENT MAP VIEW
   - Questions like "what is the main body of water HERE?" need vision analysis
   - If `has_rendered_map` is true AND user asks about features/objects, use vision
   - **TEMPORAL COMPARISONS**: Questions about changes over time need vision analysis
     - Keywords: "change between", "compare", "before and after", "vs", "difference over time",
       "how did X change", "what happened between", "seasonal changes", "temporal"
     - Example: "How did vegetation change in Athens between June and December 2025?"
     - Example: "Compare surface reflectance before and after the fire"
     - Example: "What's the difference in snow cover between winter and summer?"
   - Examples: 
     * "What is the main body of water here?" -> VISION (asking about visible map)
     * "What river is this?" -> VISION (asking about visible feature)
     * "Describe what you see" -> VISION
     * "What features are visible?" -> VISION
     * "How did X change between date1 and date2?" -> VISION (temporal comparison)
   -> Call `answer_with_vision`

4. **CONTEXTUAL** - Pure educational/factual questions NOT about the visible map
   - Questions about concepts, science, or facts that don't reference visible imagery
   - NO map-referential words like "here", "this", "visible", "in the image"
   - Examples:
     * "How do hurricanes form?" -> CONTEXTUAL (educational)
     * "What is NDVI?" -> CONTEXTUAL (concept explanation)
     * "What is the tallest building in the world?" -> CONTEXTUAL (factual, not about map)
   -> Call `answer_contextual_question`

   **CRITICAL DISTINCTION**: 
   - "What is the main river in Bangladesh?" with NO map context -> CONTEXTUAL (factual)
   - "What is the main body of water HERE?" with map showing Bangladesh -> VISION (needs to look at map)

5. **HYBRID** - User wants to LOAD imagery AND get analysis
   - Combines STAC keywords + analysis keywords
   - Keywords: "show me X and describe", "load X and analyze", "display X and explain"
   - Examples: "Show me flood damage in Houston and describe it"
   -> Call `search_and_analyze`

## CRITICAL RULES

1. **ALWAYS call `get_session_context` first** to understand current state
2. **Simple location queries without collection names = MAP_ONLY**
   - "Show me Paris" -> navigate_to_location (NOT stac search)
3. **Follow-up STAC queries (no explicit location) = use_current_location=true**
   - If last_bbox exists and user asks for imagery without new location, use current location
   - "Show me Sentinel tiles" (after navigating) -> search_and_render_stac with use_current_location=true
4. **"HERE" or "THIS" = VISION ANALYSIS** (when has_rendered_map or has_screenshot is true)
   - Keywords like "here", "this", "visible", "in this image" indicate the user wants to
     know about what's on the current map - ALWAYS use answer_with_vision
   - Example: "What is the main body of water here?" -> answer_with_vision (NOT contextual)
5. **Follow-up vision questions use existing context**
   - If has_rendered_map=true and user asks about features, use answer_with_vision
6. **Never respond with just text** - always route through a tool
7. **Check for collection keywords** before deciding STAC vs MAP_ONLY

## MAP-REFERENTIAL KEYWORDS (trigger answer_with_vision)
"here", "this", "visible", "in this image", "in the image", "on the map",
"what do you see", "describe this", "what is that", "identify this"
When these appear AND (has_rendered_map=true OR has_screenshot=true), use vision.

## TEMPORAL COMPARISON KEYWORDS (trigger answer_with_vision for temporal analysis)
"change between", "compare", "before and after", "vs", "difference", "over time",
"how did X change", "what happened between", "seasonal", "temporal", "year over year",
"month to month", "between [date] and [date]"
When these appear, route to answer_with_vision - the Vision Agent has a compare_temporal tool.

## COLLECTION/DATA KEYWORDS (trigger STAC_SEARCH - these indicate user wants to LOAD data)
**Satellite Collections**: Sentinel-2, Sentinel, Landsat, HLS, MODIS, NAIP, Copernicus, NEX-GDDP-CMIP6
**Elevation/Terrain**: elevation, DEM, terrain, topography, height map, slope, relief
**Disaster/Events**: flood, wildfire, fire, hurricane, disaster, damage, storm
**Climate/Weather**: climate projection, CMIP6, NEX-GDDP, extreme weather, climate scenario, SSP585, SSP245, temperature projection
**Spectral/Analysis**: vegetation, NDVI, thermal, infrared, SAR, NIR, false color
**Data Types**: tiles, imagery, satellite, data, map (when combined with data type like "elevation map")

**CRITICAL**: "elevation map", "terrain map", "DEM" = STAC_SEARCH for cop-dem-glo-30
- "Show elevation map of Grand Canyon" -> search_and_render_stac (NOT navigate_to_location)
- "Show terrain data for Alps" -> search_and_render_stac
- "Display topography of Himalayas" -> search_and_render_stac

## ANALYSIS KEYWORDS (trigger vision analysis if combined with map-referential keywords)
analyze, describe, identify, explain, assess, features, what is

## CONTEXTUAL FOLLOW-UP QUESTIONS (trigger answer_contextual_question OR answer_with_vision)
After imagery is displayed (has_rendered_map=true), users may ask follow-up questions:
- "What is the highest peak?" -> If asking about VISIBLE features, use answer_with_vision
- "What is the highest peak in the world?" -> General knowledge, use answer_contextual_question
- "How was this canyon formed?" -> Educational + map context, use answer_contextual_question

**DISTINCTION**:
- If question references visible map ("here", "this", "in the image") -> answer_with_vision
- If question is general knowledge/educational -> answer_contextual_question
- Both can use conversation context to understand what area user is asking about
"""


# ============================================================================
# ROUTER AGENT TOOLS
# ============================================================================

class RouterAgentTools:
    """
    Tools for the Router Agent to inspect context and route queries.
    
    These wrap existing functionality (semantic_translator, vision_agent)
    without breaking any existing code.
    """
    
    def __init__(self):
        """Initialize with references to existing components (set later)."""
        self.semantic_translator = None
        self.vision_agent = None
        self.session_contexts = {}  # session_id -> context dict
        self._pending_action = None  # Stores the action to execute after routing
        logger.info(" RouterAgentTools initialized")
    
    def set_semantic_translator(self, translator):
        """Set the semantic translator reference."""
        self.semantic_translator = translator
    
    def set_vision_agent(self, agent):
        """Set the vision agent reference."""
        self.vision_agent = agent
    
    def update_session_context(self, session_id: str, context: Dict[str, Any]):
        """Update session context (called from fastapi_app). Merges with existing context."""
        existing = self.session_contexts.get(session_id, {})
        # Merge: preserve existing values, update with new values
        existing.update(context)
        self.session_contexts[session_id] = existing
        logger.info(f" RouterTools: Updated session context for {session_id[:8]}...: has_rendered_map={existing.get('has_rendered_map')}, has_screenshot={existing.get('has_screenshot')}")
    
    def get_pending_action(self) -> Optional[Dict[str, Any]]:
        """Get and clear the pending action."""
        action = self._pending_action
        self._pending_action = None
        return action
    
    # ========================================================================
    # TOOL 1: Get Session Context
    # ========================================================================
    
    @kernel_function(
        name="get_session_context",
        description="Get current session context including rendered map state, location, and previous queries. ALWAYS call this first before making routing decisions."
    )
    def get_session_context(
        self,
        session_id: Annotated[str, "The session ID to get context for"]
    ) -> str:
        """Get session context for routing decisions."""
        context = self.session_contexts.get(session_id, {})
        
        result = {
            "session_id": session_id,
            "has_rendered_map": context.get("has_rendered_map", False),
            "last_location": context.get("last_location"),
            "last_collections": context.get("last_collections", []),
            "last_bbox": context.get("last_bbox"),
            "query_count": context.get("query_count", 0),
            "has_screenshot": context.get("has_screenshot", False)
        }
        
        # Include last query for context
        queries = context.get("queries", [])
        if queries:
            result["last_query"] = queries[-1].get("query", "")
        
        logger.info(f" [TOOL] get_session_context: {json.dumps(result, default=str)}")
        return json.dumps(result, default=str)
    
    # ========================================================================
    # TOOL 2: Fly to Location (MAP_ONLY)
    # ========================================================================
    
    @kernel_function(
        name="navigate_to_location",
        description="Pan/navigate the map to a location WITHOUT loading satellite imagery. Use for simple 'show me [place]' queries or bare location names that don't mention specific satellite collections or analysis."
    )
    def navigate_to_location(
        self,
        location: Annotated[str, "The location name to navigate to (city, country, landmark)"],
        zoom_level: Annotated[int, "Zoom level (1-18, default 12)"] = 12
    ) -> str:
        """Route query to map-only action (navigate to location)."""
        logger.info(f" [TOOL] navigate_to_location: {location}, zoom={zoom_level}")
        
        self._pending_action = {
            "action_type": "navigate_to",
            "location": location,
            "zoom_level": zoom_level,
            "needs_stac_search": False,
            "needs_vision_analysis": False
        }
        
        return json.dumps({
            "status": "routed",
            "action": "navigate_to",
            "location": location,
            "message": f"Navigating to {location} at zoom level {zoom_level}"
        })
    
    # ========================================================================
    # TOOL 3: Search and Render STAC (STAC_SEARCH)
    # ========================================================================
    
    @kernel_function(
        name="search_and_render_stac",
        description="""Search STAC catalog and render satellite imagery on the map.
        
Use when user requests specific satellite data or imagery for a location.

IMPORTANT: For follow-up queries where user asks for imagery at the current map location
(e.g., "show me Sentinel tiles here", "load Landsat data", "get MODIS imagery")
set use_current_location=true to use the last known map viewport/bbox.

This ensures that if user navigated somewhere first and then asks for imagery,
we search that location instead of trying to extract a new location from the query."""
    )
    def search_and_render_stac(
        self,
        query: Annotated[str, "The full user query about satellite imagery to search for"],
        session_id: Annotated[str, "The session ID for context lookup"],
        location: Annotated[str, "The location name if explicitly mentioned in the query"] = None,
        use_current_location: Annotated[bool, "Set to true if user wants imagery for CURRENT map view (follow-up query without new location)"] = False
    ) -> str:
        """Route query to STAC search and tile rendering."""
        logger.info(f" [TOOL] search_and_render_stac: query='{query}', location={location}, use_current_location={use_current_location}")
        
        # Check for current location/bbox from session context if no explicit location
        current_bbox = None
        current_location = None
        if use_current_location or location is None:
            session_context = self.session_contexts.get(session_id, {})
            current_bbox = session_context.get("last_bbox")
            current_location = session_context.get("last_location")
            logger.info(f" [TOOL] Session context - last_bbox: {current_bbox}, last_location: {current_location}")
        
        self._pending_action = {
            "action_type": "stac_search",
            "original_query": query,
            "location": location,
            "use_current_location": use_current_location,
            "current_bbox": current_bbox,  # Pass current bbox for follow-up queries
            "current_location": current_location,  # Pass current location name
            "needs_stac_search": True,
            "needs_vision_analysis": False
        }
        
        message = f"Searching STAC catalog for: {query}"
        if use_current_location and current_bbox:
            message = f"Searching STAC catalog for {query} at current map location"
        
        return json.dumps({
            "status": "routed",
            "action": "stac_search",
            "query": query,
            "use_current_location": use_current_location,
            "message": message
        })
    
    # ========================================================================
    # TOOL 4: Answer with Vision (CONTEXTUAL - for imagery)
    # ========================================================================
    
    @kernel_function(
        name="answer_with_vision",
        description="Analyze the currently visible map imagery to answer user's question. Use when user asks about what's visible, features in the image, or follow-up questions about displayed imagery."
    )
    def answer_with_vision(
        self,
        question: Annotated[str, "The user's question about the visible imagery"],
        use_screenshot: Annotated[bool, "Whether to capture/use map screenshot"] = True
    ) -> str:
        """Route query to vision analysis."""
        logger.info(f" [TOOL] answer_with_vision: question='{question}'")
        
        self._pending_action = {
            "action_type": "vision_analysis",
            "question": question,
            "use_screenshot": use_screenshot,
            "needs_stac_search": False,
            "needs_vision_analysis": True
        }
        
        return json.dumps({
            "status": "routed",
            "action": "vision_analysis",
            "question": question,
            "message": f"Analyzing visible imagery to answer: {question}"
        })
    
    # ========================================================================
    # TOOL 5: Answer Contextual Question (CONTEXTUAL - educational)
    # ========================================================================
    
    @kernel_function(
        name="answer_contextual_question",
        description="Answer educational or informational questions that don't require imagery. Use for 'how does X work', 'what is Y', explanations about Earth science concepts."
    )
    def answer_contextual_question(
        self,
        question: Annotated[str, "The user's educational or informational question"]
    ) -> str:
        """Route query to contextual/educational response."""
        logger.info(f" [TOOL] answer_contextual_question: question='{question}'")
        
        self._pending_action = {
            "action_type": "contextual",
            "question": question,
            "needs_stac_search": False,
            "needs_vision_analysis": False,
            "needs_contextual_response": True
        }
        
        return json.dumps({
            "status": "routed",
            "action": "contextual",
            "question": question,
            "message": f"Generating educational response for: {question}"
        })
    
    # ========================================================================
    # TOOL 6: Hybrid Query (STAC + Vision)
    # ========================================================================
    
    @kernel_function(
        name="search_and_analyze",
        description="""Search for satellite imagery AND analyze it.
        
Use when user wants to both load new imagery and get analysis/description of it in the same request.

IMPORTANT: For follow-up queries where user asks for imagery at the current map location,
set use_current_location=true to use the last known map viewport/bbox."""
    )
    def search_and_analyze(
        self,
        search_query: Annotated[str, "The query for STAC search (what imagery to load)"],
        analysis_question: Annotated[str, "What to analyze/describe about the imagery"],
        session_id: Annotated[str, "The session ID for context lookup"],
        use_current_location: Annotated[bool, "Set to true if user wants imagery for CURRENT map view"] = False
    ) -> str:
        """Route query to hybrid STAC + Vision flow."""
        logger.info(f" [TOOL] search_and_analyze: search='{search_query}', analyze='{analysis_question}', use_current_location={use_current_location}")
        
        # Check for current location/bbox from session context
        current_bbox = None
        current_location = None
        if use_current_location:
            session_context = self.session_contexts.get(session_id, {})
            current_bbox = session_context.get("last_bbox")
            current_location = session_context.get("last_location")
            logger.info(f" [TOOL] Session context - last_bbox: {current_bbox}, last_location: {current_location}")
        
        self._pending_action = {
            "action_type": "hybrid",
            "search_query": search_query,
            "analysis_question": analysis_question,
            "use_current_location": use_current_location,
            "current_bbox": current_bbox,
            "current_location": current_location,
            "needs_stac_search": True,
            "needs_vision_analysis": True
        }
        
        return json.dumps({
            "status": "routed",
            "action": "hybrid",
            "search_query": search_query,
            "analysis_question": analysis_question,
            "message": f"Loading imagery and analyzing: {analysis_question}"
        })


# ============================================================================
# ROUTER AGENT SESSION
# ============================================================================

class RouterAgentSession:
    """Represents a conversation session with the router agent."""
    
    def __init__(self, session_id: str):
        self.session_id = session_id
        self.chat_history = ChatHistory()
        self.created_at = datetime.utcnow()
        self.last_activity = datetime.utcnow()
        self.context = {}  # Stores session context
        
    def add_user_message(self, content: str):
        """Add a user message to history."""
        self.chat_history.add_user_message(content)
        self.last_activity = datetime.utcnow()
        
    def add_assistant_message(self, content: str):
        """Add an assistant message to history."""
        self.chat_history.add_assistant_message(content)
        self.last_activity = datetime.utcnow()
    
    def update_context(self, context: Dict[str, Any]):
        """Update session context."""
        self.context.update(context)


# ============================================================================
# ROUTER AGENT
# ============================================================================

class RouterAgent:
    """
    Semantic Kernel-based Router Agent.
    
    Replaces the old classify_query_intent_unified() LLM wrapper with
    a true agent that reasons about context and calls routing tools.
    """
    
    def __init__(self):
        """Initialize the router agent."""
        self.kernel = Kernel()
        self.tools = RouterAgentTools()
        self.sessions: Dict[str, RouterAgentSession] = {}
        self._agent: Optional[ChatCompletionAgent] = None
        self._initialized = False
        
        logger.info(" RouterAgent created (will initialize on first use)")
    
    async def _ensure_initialized(self):
        """Lazy initialization of the agent."""
        if self._initialized:
            return
            
        logger.info(" Initializing RouterAgent with Semantic Kernel...")
        
        # Set up Azure OpenAI service
        # Use FAST deployment (gpt-4o-mini) for routing — classification/extraction
        # tasks don't need GPT-5's deep reasoning, just fast structured output
        endpoint = os.getenv("AZURE_OPENAI_ENDPOINT")
        deployment = os.getenv("AZURE_OPENAI_FAST_DEPLOYMENT", "gpt-4o-mini")
        api_version = os.getenv("AZURE_OPENAI_API_VERSION", "2025-01-01-preview")
        
        # Use Managed Identity
        credential = DefaultAzureCredential()
        token_provider = get_bearer_token_provider(
            credential, cloud_cfg.cognitive_services_scope
        )
        
        # Create Azure OpenAI chat completion service
        chat_service = AzureChatCompletion(
            deployment_name=deployment,
            endpoint=endpoint,
            api_version=api_version,
            ad_token_provider=token_provider,
            service_id="router_chat"
        )
        
        self.kernel.add_service(chat_service)
        
        # Add router tools as a plugin
        self.kernel.add_plugin(self.tools, plugin_name="router")
        
        # Create the agent with function calling enabled
        self._agent = ChatCompletionAgent(
            kernel=self.kernel,
            name="RouterAgent",
            instructions=ROUTER_AGENT_INSTRUCTIONS,
            function_choice_behavior=FunctionChoiceBehavior.Auto()
        )
        
        self._initialized = True
        logger.info(f" RouterAgent initialized with {len(self.kernel.plugins)} plugins")
    
    def set_semantic_translator(self, translator):
        """Set the semantic translator for STAC operations."""
        self.tools.set_semantic_translator(translator)
    
    def set_vision_agent(self, agent):
        """Set the vision agent for vision analysis."""
        self.tools.set_vision_agent(agent)
    
    def get_or_create_session(self, session_id: str) -> RouterAgentSession:
        """Get existing session or create a new one."""
        if session_id in self.sessions:
            return self.sessions[session_id]
        
        session = RouterAgentSession(session_id)
        self.sessions[session_id] = session
        logger.info(f" Created new router session: {session_id}")
        return session
    
    def update_session_context(self, session_id: str, context: Dict[str, Any]):
        """Update session context for routing decisions."""
        self.tools.update_session_context(session_id, context)
        
        if session_id in self.sessions:
            self.sessions[session_id].update_context(context)
    
    
    async def route_query(
        self,
        query: str,
        session_id: str,
        has_screenshot: bool = False
    ) -> Dict[str, Any]:
        """
        Route a user query using LLM-based semantic classification.
        
        Uses an LLM to understand the query semantically, grounded in:
        - Available satellite data collections (from CollectionMapper)
        - Known geographic locations (from LocationResolver)
        
        ROUTING:
        | Location | Collection | -> Action        |
        |----------|------------|-----------------|
        |        |          | STAC_SEARCH     |
        |        |          | STAC_SEARCH     |
        |        |          | NAVIGATE_TO     |
        |        |          | VISION          |
        """
        logger.info(f" RouterAgent processing: '{query}'")
        
        # Update context
        if session_id in self.tools.session_contexts:
            self.tools.session_contexts[session_id]["has_screenshot"] = has_screenshot
        
        # ====================================================================
        #  GUARANTEED VISION ROUTING FOR ANALYTICAL FOLLOW-UP QUERIES
        # ====================================================================
        session_context = self.tools.session_contexts.get(session_id, {})
        has_rendered_map = session_context.get("has_rendered_map", False)
        
        logger.info(f" VISION CHECK: session_id={session_id[:8] if session_id else 'None'}...")
        logger.info(f" VISION CHECK: has_rendered_map={has_rendered_map}, has_screenshot={has_screenshot}")
        logger.info(f" VISION CHECK: full session_context keys={list(session_context.keys())}")
        
        # Check if this is an analytical query (asking about visible content)
        query_lower = query.lower().strip()
        
        # Keywords that indicate user is ANALYZING what's on screen (not loading new data)
        analytical_patterns = [
            # Direct questions about visible content
            "what is on", "what's on", "what do you see", "what can you see",
            "describe", "analyze", "explain what", "tell me about this",
            "what city", "what river", "what lake", "what mountain", "what country",
            "what is this", "what's this", "which city", "which country",
            "is this", "is that", "are these", "are those",
            # Asking about features in current view
            "what features", "what patterns", "what type of", "what kind of",
            "identify", "recognize", "detect",
            # Follow-up analytical questions
            "how about", "what about", "and the", "also",
            # Spatial analysis of current view
            "how much", "how many", "what percentage", "what area",
            "adjacent", "near", "next to", "surrounding",
        ]
        
        # Keywords that indicate user wants NEW data (not analysis)
        data_loading_patterns = [
            "show", "display", "load", "get", "fetch", "find",
            "imagery of", "data of", "data for", "imagery for",
            "satellite", "sentinel", "landsat", "hls", "modis",
        ]
        
        is_analytical = any(pattern in query_lower for pattern in analytical_patterns)
        wants_new_data = any(pattern in query_lower for pattern in data_loading_patterns)
        
        logger.info(f" PATTERN CHECK: is_analytical={is_analytical}, wants_new_data={wants_new_data}")
        logger.info(f" PATTERN CHECK: query_lower='{query_lower}'")
        
        # GUARANTEED VISION: If map has data AND query is analytical AND not asking for new data
        if (has_rendered_map or has_screenshot) and is_analytical and not wants_new_data:
            matched_patterns = [p for p in analytical_patterns if p in query_lower]
            logger.info(f" GUARANTEED VISION: Map has data + analytical query detected")
            logger.info(f"   has_rendered_map={has_rendered_map}, has_screenshot={has_screenshot}")
            logger.info(f"   Matched patterns: {matched_patterns[:3]}")
            return {
                "action_type": "vision_analysis",
                "original_query": query,
                "needs_stac_search": False,
                "needs_vision_analysis": True,
                "routing_reason": "guaranteed_vision_analytical_followup"
            }
        
        # ====================================================================
        # DETERMINISTIC LOCATION PRE-CHECK (before LLM)
        # ====================================================================
        # If the entire query IS a known location name, skip the LLM entirely.
        # This catches bare location names like "Australia", "Grand Canyon",
        # "Tokyo" that the LLM sometimes misclassifies as contextual.
        # ====================================================================
        query_cleaned = query_lower.strip().rstrip('?!.')
        
        # Strip common navigation prefixes to extract the location name
        # Order matters: check longer prefixes first ("show me " before "show ")
        nav_prefixes = [
            "go to ", "fly to ", "take me to ", "navigate to ",
            "zoom to ", "pan to ", "show me ", "show ", "where is ",
            "view ", "display ", "look at ",
        ]
        location_candidate = query_cleaned
        has_nav_prefix = False
        for prefix in nav_prefixes:
            if query_cleaned.startswith(prefix):
                location_candidate = query_cleaned[len(prefix):].strip()
                has_nav_prefix = True
                break
        
        # Normalize punctuation for matching: "san juan, puerto rico" -> "san juan puerto rico"
        location_candidate_normalized = re.sub(r'[,;:\-]+', ' ', location_candidate).strip()
        location_candidate_normalized = re.sub(r'\s+', ' ', location_candidate_normalized)
        
        # Check if the candidate matches a known location (try both raw and normalized)
        matched_location = None
        if location_candidate in LOCATION_NAMES:
            matched_location = location_candidate
        elif location_candidate_normalized != location_candidate and location_candidate_normalized in LOCATION_NAMES:
            matched_location = location_candidate_normalized
        
        if matched_location:
            logger.info(f"DETERMINISTIC MATCH: '{matched_location}' found in LOCATION_NAMES ({len(LOCATION_NAMES)} entries)")
            return {
                "action_type": "navigate_to",
                "original_query": query,
                "location": matched_location,
                "needs_stac_search": False,
                "needs_vision_analysis": False,
                "routing_reason": "deterministic_location_match"
            }
        
        # Check if the query contains any known collection keyword from the
        # comprehensive COLLECTION_KEYWORDS set (loaded from CollectionMapper).
        # This must be checked BEFORE the nav-prefix heuristic to prevent
        # queries like "Show USGS 3DEP Lidar for New Orleans" from being
        # misrouted to navigate_to with the full query as the location name.
        has_collection_keyword = any(
            re.search(r'\b' + re.escape(kw) + r'\b', query_lower)
            for kw in sorted(COLLECTION_KEYWORDS, key=len, reverse=True)
        ) if COLLECTION_KEYWORDS else False
        
        if has_nav_prefix and location_candidate and not has_collection_keyword:
            # Navigation verb + something that looks like a location (no collection keywords)
            # Route directly to navigate_to — the location resolver will geocode it
            logger.info(f"NAV PREFIX ROUTE: '{location_candidate}' not in stored locations, but has nav prefix -> navigate_to")
            return {
                "action_type": "navigate_to",
                "original_query": query,
                "location": location_candidate,
                "needs_stac_search": False,
                "needs_vision_analysis": False,
                "routing_reason": "nav_prefix_with_location"
            }
        
        # ====================================================================
        #  CLIMATE PROJECTION PRE-CHECK (before collection keyword match)
        # ====================================================================
        # Queries about future climate projections, SSP scenarios, or projected
        # climate variables should route to the ExtremeWeatherAgent (CMIP6 NetCDF
        # point-sampled data), NOT to STAC tile search. This pre-check catches
        # queries like "projected monsoon precipitation" before the deterministic
        # collection keyword match grabs "precipitation" and routes to NOAA MRMS.
        # ====================================================================
        climate_projection_indicators = [
            # SSP scenario references
            "ssp", "ssp1", "ssp2", "ssp3", "ssp5", "ssp126", "ssp245", "ssp370", "ssp585",
            "worst.case scenario", "middle of the road",
            # Projection / future framing
            "projected", "projection", "projections", "by 2030", "by 2040", "by 2050",
            "by 2060", "by 2070", "by 2080", "by 2090", "by 2100",
            "future climate", "climate projection", "climate change projection",
            "will temperature", "will precipitation", "will rainfall",
            "increasing", "is .+ increasing",
            # CMIP6 / NEX-GDDP references
            "cmip6", "cmip", "nex-gddp", "nexgddp", "climate model",
            # Extreme weather analysis phrasing
            "extreme heat", "extreme weather", "climate risk", "climate outlook",
            # Monsoon / seasonal climate questions (future-oriented)
            "monsoon", "monsoon precipitation", "monsoon season",
            # Combined climate + variable patterns
            "precipitation levels", "precipitation patterns", "rainfall patterns",
            "temperature trends", "warming trend", "heat wave",
            "flooding risk", "flood risk", "drought risk",
        ]
        
        is_climate_projection = any(
            re.search(r'\b' + re.escape(indicator) + r'\b', query_lower)
            if '.' not in indicator  # plain word match
            else re.search(indicator, query_lower)  # regex pattern
            for indicator in climate_projection_indicators
        )
        
        if is_climate_projection:
            # Extract location for the climate query
            detected_location = None
            for loc in LOCATION_NAMES:
                if loc.lower() in query_lower:
                    detected_location = loc
                    break
            
            if not detected_location:
                try:
                    loc_result = await self._extract_location_only(query)
                    if loc_result.get("has_location"):
                        detected_location = loc_result.get("location")
                except Exception:
                    pass
            
            logger.info(f" CLIMATE PROJECTION DETECTED: routing to extreme_weather (location: {detected_location})")
            return {
                "action_type": "extreme_weather",
                "original_query": query,
                "location": detected_location,
                "needs_stac_search": False,
                "needs_vision_analysis": False,
                "routing_reason": "climate_projection_detected"
            }

        # ====================================================================
        #  NETCDF COMPUTATION PRE-CHECK
        # ====================================================================
        # Advanced computation queries (trends, anomalies, time-series, area
        # stats, derived calculations) route to the NetCDF computation agent
        # which has all the climate tools PLUS new computation tools.
        # ====================================================================
        netcdf_computation_indicators = [
            "anomaly", "climate anomaly", "temperature anomaly",
            "trend analysis", "compute trend", "linear trend",
            "time series", "timeseries", "monthly breakdown",
            "seasonal pattern", "seasonal breakdown",
            "area statistics", "area stats", "spatial statistics",
            "bounding box", "region average", "regional average",
            "calculate", "compute", "annual total",
            "derived", "unit conversion",
        ]

        is_computation_query = any(
            re.search(r'\b' + re.escape(ind) + r'\b', query_lower)
            for ind in netcdf_computation_indicators
        )

        if is_computation_query:
            detected_location = None
            for loc in LOCATION_NAMES:
                if loc.lower() in query_lower:
                    detected_location = loc
                    break
            if not detected_location:
                try:
                    loc_result = await self._extract_location_only(query)
                    if loc_result.get("has_location"):
                        detected_location = loc_result.get("location")
                except Exception:
                    pass

            logger.info(f" NETCDF COMPUTATION DETECTED: routing to netcdf_computation (location: {detected_location})")
            return {
                "action_type": "netcdf_computation",
                "original_query": query,
                "location": detected_location,
                "needs_stac_search": False,
                "needs_vision_analysis": False,
                "routing_reason": "netcdf_computation_detected"
            }

        # ====================================================================
        # DETERMINISTIC COLLECTION PRE-CHECK (before LLM)
        # ====================================================================
        # If the query contains a known collection keyword from the keyword_map,
        # skip the LLM entirely and route directly to STAC_SEARCH. This prevents
        # the LLM from missing collection keywords that weren't in its sample.
        # ====================================================================
        matched_collection = None
        for kw in sorted(COLLECTION_KEYWORDS, key=len, reverse=True):
            # Check for whole-word match to avoid false positives
            if re.search(r'\b' + re.escape(kw) + r'\b', query_lower):
                matched_collection = kw
                break
        
        if matched_collection:
            # We found a collection keyword - extract location if present
            logger.info(f" DETERMINISTIC COLLECTION MATCH: '{matched_collection}' found in query")
            
            # Quick location extraction: check LOCATION_NAMES or rely on LLM for location only
            detected_location = None
            for loc in LOCATION_NAMES:
                if loc.lower() in query_lower:
                    detected_location = loc
                    break
            
            if not detected_location:
                # Try LLM for location extraction only
                try:
                    loc_result = await self._extract_location_only(query)
                    if loc_result.get("has_location"):
                        detected_location = loc_result.get("location")
                except Exception:
                    pass
            
            logger.info(f" DETERMINISTIC ROUTE -> STAC_SEARCH (collection: {matched_collection}, location: {detected_location})")
            return {
                "action_type": "stac_search",
                "original_query": query,
                "location": detected_location,
                "collection_hint": matched_collection,
                "use_current_location": not bool(detected_location),
                "needs_stac_search": True,
                "needs_vision_analysis": False,
                "routing_reason": "deterministic_collection_match"
            }
        
        # ====================================================================
        # BARE LOCATION HEURISTIC (before LLM)
        # ====================================================================
        # If the query is short, contains no collection/data/analytical keywords,
        # and looks like a place name (1-5 words, no question marks, no verbs),
        # route directly to navigate_to. This catches bare location names like
        # "Timbuktu", "Mount Fuji", "Rio de Janeiro" that aren't in LOCATION_NAMES.
        # The location_resolver will geocode them via Azure Maps API.
        # ====================================================================
        analytical_keywords = [
            "what", "how", "why", "describe", "analyze", "explain", "identify",
            "compare", "assess", "detect", "measure", "calculate",
        ]
        collection_data_keywords = [
            "sentinel", "landsat", "hls", "modis", "elevation", "dem",
            "terrain", "imagery", "images", "satellite", "data", "tiles", "fire",
            "snow", "vegetation", "ndvi", "temperature", "biomass",
            "land cover", "precipitation", "flood", "drought",
            "sar", "radar", "lidar", "optical",
            "naip", "aerial", "cop-dem", "aster", "viirs",
        ]
        word_count = len(location_candidate.split())
        has_analytical = any(kw in query_lower for kw in analytical_keywords)
        has_collection_data = any(kw in query_lower for kw in collection_data_keywords)
        is_question = '?' in query_cleaned
        
        if (word_count <= 6 and not has_analytical and not has_collection_data 
                and not is_question and location_candidate):
            logger.info(f"BARE LOCATION HEURISTIC: '{location_candidate}' ({word_count} words, no data/analytical keywords) -> navigate_to")
            return {
                "action_type": "navigate_to",
                "original_query": query,
                "location": location_candidate,
                "needs_stac_search": False,
                "needs_vision_analysis": False,
                "routing_reason": "bare_location_heuristic"
            }
        
        # ====================================================================
        # LLM-BASED SEMANTIC CLASSIFICATION
        # ====================================================================
        try:
            classification = await self._classify_query_with_llm(query)
            
            has_collection = classification.get("has_collection", False)
            detected_collection = classification.get("collection")
            has_location = classification.get("has_location", False)
            detected_location = classification.get("location")
            
            logger.info(f" LLM Classification: location={has_location}({detected_location}), collection={has_collection}({detected_collection})")
            
        except Exception as e:
            logger.warning(f" LLM classification failed: {e}, falling back to navigate_to if location-like")
            # If the query looks like it could be a location (no data keywords),
            # default to navigate_to instead of vision
            if not has_collection_data and not has_analytical:
                return {
                    "action_type": "navigate_to",
                    "original_query": query,
                    "location": location_candidate or query,
                    "needs_stac_search": False,
                    "needs_vision_analysis": False,
                    "routing_reason": "llm_failed_navigate_fallback",
                    "error": str(e)
                }
            return {
                "action_type": "vision_analysis",
                "original_query": query,
                "needs_stac_search": False,
                "needs_vision_analysis": True,
                "error": str(e)
            }
        
        # ====================================================================
        # Apply routing matrix based on LLM classification
        # ====================================================================
        if has_collection:
            # STAC search (with or without location)
            logger.info(f" ROUTE -> STAC_SEARCH (collection: {detected_collection})")
            return {
                "action_type": "stac_search",
                "original_query": query,
                "location": detected_location,
                "collection_hint": detected_collection,
                "use_current_location": not has_location,
                "needs_stac_search": True,
                "needs_vision_analysis": False
            }
        
        elif has_location:
            # Navigate to location (no collection)
            logger.info(f" ROUTE -> NAVIGATE_TO (location only: {detected_location})")
            return {
                "action_type": "navigate_to",
                "original_query": query,
                "location": detected_location,
                "needs_stac_search": False,
                "needs_vision_analysis": False
            }
        
        else:
            # VISION (no location, no collection)
            logger.info(f" ROUTE -> VISION (no location, no collection)")
            return {
                "action_type": "vision_analysis",
                "original_query": query,
                "needs_stac_search": False,
                "needs_vision_analysis": True
            }
    
    async def _classify_query_with_llm(self, query: str) -> Dict[str, Any]:
        """
        Use LLM to semantically classify the query using a structured collection
        catalog organized by category with descriptions.

        This is the FALLBACK classifier — queries with explicit collection keywords
        (e.g., "HLS", "Sentinel-2") are already caught by the deterministic
        pre-check. This LLM call handles implicit/conceptual queries like
        "show me drought conditions in California" or "vegetation health near Denver".
        """
        await self._ensure_initialized()
        
        location_samples = sorted(list(LOCATION_NAMES))[:50]
        
        classification_prompt = f"""You are a geospatial query router for an Earth observation system with satellite imagery.
Classify this query to determine if the user wants to LOAD DATA, NAVIGATE, or ask a QUESTION.

QUERY: "{query}"

## AVAILABLE DATA CATALOG (organized by category)

**Optical Satellite Imagery**: Sentinel-2, Landsat (Level 1 & 2), HLS (Harmonized Landsat-Sentinel), NAIP (aerial), MODIS surface reflectance, MODIS NBAR, ASTER
**SAR / Radar**: Sentinel-1 (RTC & GRD), ALOS PALSAR
**Elevation & Terrain**: Copernicus DEM (30m & 90m), NASADEM, ALOS DEM, USGS 3DEP LiDAR (DSM, DTM, HAG, classification, intensity, returns, seamless)
**Fire Detection**: MODIS thermal anomalies (daily & 8-day), MODIS burned area, MTBS burn severity
**Snow & Ice**: MODIS snow cover (daily & 8-day)
**Vegetation Indices**: MODIS NDVI/EVI (250m & 500m), MODIS LAI/FPAR, MODIS GPP/NPP, MODIS evapotranspiration
**Land Surface Temperature**: MODIS LST (daily & 8-day), MODIS emissivity
**Land Cover & Land Use**: ESA WorldCover, ESA CCI, IO/Esri LULC, USDA Cropland, DRCOG, NRCan, Chesapeake, USGS LCMAP, NOAA C-CAP, USGS GAP
**Biomass & Carbon**: Chloris biomass, Harmonized Global Biomass (HGB), ALOS Forest/Non-Forest
**Water**: JRC Global Surface Water
**Ocean & Climate**: NOAA Sea Surface Temperature, NOAA climate normals, NClimGrid
**Precipitation**: NOAA MRMS QPE (hourly & daily)
**Infrastructure**: Microsoft Building Footprints, HREA electricity access
**Biodiversity**: IO Biodiversity Intactness, MOBI (Map of Biodiversity Importance)

## CLASSIFICATION RULES

### STAC_SEARCH (has_collection: true)
User wants to LOAD satellite/geospatial data onto the map.
Set has_collection=true when the query mentions ANY of:
- A specific collection name (Sentinel, Landsat, HLS, MODIS, NAIP, etc.)
- A data type keyword (imagery, satellite, elevation, DEM, terrain, tiles, data)
- A phenomenon that maps to data (fire, snow, vegetation, NDVI, temperature, land cover, biomass, precipitation, flood, drought, deforestation)
- "Show" or "display" + a data concept (NOT just a place name)
Examples:
- "Show Sentinel-2 of Denver" -> STAC_SEARCH
- "Load HLS imagery for California" -> STAC_SEARCH
- "Show me vegetation health in Oregon" -> STAC_SEARCH (maps to NDVI)
- "Fire activity near LA" -> STAC_SEARCH (maps to MODIS fire)
- "Land cover of Seattle" -> STAC_SEARCH
- "Snow cover in the Rockies" -> STAC_SEARCH
- "Show me drought conditions in Texas" -> STAC_SEARCH (maps to vegetation/ET)

### NAVIGATE_TO (has_location: true, has_collection: false)
User wants to fly to a place WITHOUT loading data.
- Bare location names: "Paris", "Grand Canyon", "Tokyo"
- Navigation verbs: "Go to", "Fly to", "Show me [place]" (no data keywords)
- "Show Canada" -> NAVIGATE_TO (no data keyword, just a place)

### CONTEXTUAL (has_location: false, has_collection: false)
User asks an educational/factual question.
- "What is NDVI?", "How do hurricanes form?", "Tell me about climate change"
- Questions about concepts, NOT requests to load data

## CRITICAL: "Show" + data concept = STAC_SEARCH, NOT NAVIGATE_TO
- "Show me satellite images of Athens" -> STAC_SEARCH (has "satellite images")
- "Show me HLS images of Athens" -> STAC_SEARCH (has "HLS")  
- "Show me Athens" -> NAVIGATE_TO (no data concept, just a place)

## KNOWN LOCATIONS (sample):
{', '.join(location_samples)}
(Plus any geographic place name: cities, countries, regions, landmarks, etc.)

Respond with ONLY valid JSON (no markdown):
{{"has_collection": true/false, "collection": "matched concept or null", "has_location": true/false, "location": "place name or null"}}"""

        try:
            from semantic_kernel.contents.chat_history import ChatHistory
            
            classification_history = ChatHistory()
            classification_history.add_user_message(classification_prompt)
            
            # Get chat service and call without tools (pure classification)
            chat_service = self.kernel.get_service("router_chat")
            
            result = await chat_service.get_chat_message_content(
                chat_history=classification_history,
                settings=None
            )
            
            response_text = str(result).strip()
            logger.info(f" LLM classification response: {response_text}")
            
            # Parse JSON response - handle markdown code blocks if present
            if "```json" in response_text:
                response_text = response_text.split("```json")[1].split("```")[0].strip()
            elif "```" in response_text:
                response_text = response_text.split("```")[1].split("```")[0].strip()
            
            classification = json.loads(response_text)
            return classification
            
        except Exception as e:
            logger.error(f" LLM classification failed: {e}")
            raise
    
    async def _extract_location_only(self, query: str) -> Dict[str, Any]:
        """Extract just the location from a query using LLM."""
        await self._ensure_initialized()
        
        prompt = f"""Is there a geographic PLACE NAME in this query? 
        
Query: "{query}"

PLACE = city, country, region, landmark, mountain, river name, etc.
NOT a place: "here", "on the map", "this area", "the current view"

Respond with ONLY valid JSON:
{{"has_location": true/false, "location": "place name" or null}}"""

        try:
            from semantic_kernel.contents.chat_history import ChatHistory
            extraction_history = ChatHistory()
            extraction_history.add_user_message(prompt)
            
            chat_service = self.kernel.get_service("router_chat")
            result = await chat_service.get_chat_message_content(
                chat_history=extraction_history,
                settings=None
            )
            
            response_text = str(result).strip()
            if "```json" in response_text:
                response_text = response_text.split("```json")[1].split("```")[0].strip()
            elif "```" in response_text:
                response_text = response_text.split("```")[1].split("```")[0].strip()
            
            return json.loads(response_text)
        except Exception as e:
            logger.error(f" Location extraction failed: {e}")
            return {"has_location": False, "location": None}
    
    def cleanup_old_sessions(self, max_age_minutes: int = 60):
        """Remove sessions older than max_age_minutes."""
        now = datetime.utcnow()
        expired = [
            sid for sid, session in self.sessions.items()
            if (now - session.last_activity).total_seconds() > max_age_minutes * 60
        ]
        for sid in expired:
            del self.sessions[sid]
            if sid in self.tools.session_contexts:
                del self.tools.session_contexts[sid]
            logger.info(f" Cleaned up expired router session: {sid}")


# ============================================================================
# SINGLETON INSTANCE
# ============================================================================

_router_agent: Optional[RouterAgent] = None


def get_router_agent() -> RouterAgent:
    """Get the singleton RouterAgent instance."""
    global _router_agent
    if _router_agent is None:
        _router_agent = RouterAgent()
    return _router_agent
