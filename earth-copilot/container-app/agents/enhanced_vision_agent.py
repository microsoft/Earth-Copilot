"""
Enhanced Vision Agent - Azure AI Agent Service

Refactored from Semantic Kernel ChatCompletionAgent to Azure AI Agent Service.
Uses AgentsClient with FunctionTool/ToolSet for automatic function calling.

This agent:
1. Maintains conversation memory via AgentThread (persistent threads)
2. Has access to 13 vision analysis tools via FunctionTool
3. Uses LLM-driven tool selection (replaces forced keyword routing)
4. Sets module-level session context for standalone tool functions
"""

import logging
import os
import re
import json
from dataclasses import dataclass, field
from typing import Dict, Any, Optional, List, Tuple
from datetime import datetime, timedelta

from azure.identity import DefaultAzureCredential, get_bearer_token_provider

logger = logging.getLogger(__name__)


# ============================================================================
# COLLECTION -> RASTER DATA_TYPE MAPPING (all 72 PC collections)
# ============================================================================
# Maps collection ID patterns to the correct `sample_raster_value(data_type=...)`
# parameter. Used by the deterministic pre-sampling check to bypass LLM tool
# selection when the user asks a measurable-value question.
#
# Order matters: more specific patterns MUST come before generic ones.
# Each entry is (substring_to_match, data_type, human_label).
# ============================================================================

COLLECTION_RASTER_MAP: List[Tuple[str, str, str]] = [
    # -- SST / Ocean Temperature --
    ("noaa-cdr-sea-surface-temperature", "sst", "Sea Surface Temperature"),
    ("sst", "sst", "Sea Surface Temperature"),

    # -- Land Surface Temperature (MODIS 11, 21) --
    ("modis-11a1", "sst", "Land Surface Temperature"),
    ("modis-11a2", "sst", "Land Surface Temperature"),
    ("modis-21a2", "sst", "Land Surface Temperature"),

    # -- Elevation / DEM --
    ("cop-dem-glo-30", "elevation", "Elevation"),
    ("cop-dem-glo-90", "elevation", "Elevation"),
    ("alos-dem", "elevation", "Elevation"),
    ("nasadem", "elevation", "Elevation"),
    ("3dep-seamless", "elevation", "Elevation"),
    ("3dep-lidar-dsm", "elevation", "Digital Surface Model"),
    ("3dep-lidar-dtm", "elevation", "Digital Terrain Model"),
    ("3dep-lidar-dtm-native", "elevation", "Digital Terrain Model"),
    ("3dep-lidar-hag", "lidar", "Height Above Ground"),
    ("3dep-lidar-intensity", "lidar", "LiDAR Intensity"),
    ("3dep-lidar-classification", "lidar", "LiDAR Classification"),
    ("3dep-lidar-pointsourceid", "lidar", "LiDAR Point Source"),
    ("3dep-lidar-returns", "lidar", "LiDAR Returns"),

    # -- Fire / Burn --
    ("modis-14a1", "fire", "Active Fire"),
    ("modis-14a2", "fire", "Active Fire"),
    ("modis-64a1", "fire", "Burned Area"),
    ("mtbs", "fire", "Burn Severity"),

    # -- Snow / Ice --
    ("modis-10a1", "snow", "Snow Cover"),
    ("modis-10a2", "snow", "Snow Cover"),

    # -- Vegetation / NDVI / LAI / GPP / NPP / ET --
    ("modis-13a1", "vegetation", "NDVI (500m)"),
    ("modis-13q1", "vegetation", "NDVI (250m)"),
    ("modis-15a2h", "vegetation", "LAI/FPAR"),
    ("modis-15a3h", "vegetation", "LAI/FPAR (8-day)"),
    ("modis-16a3gf", "vegetation", "Evapotranspiration"),
    ("modis-17a2h", "vegetation", "GPP"),
    ("modis-17a2hgf", "vegetation", "GPP (gap-filled)"),
    ("modis-17a3hgf", "vegetation", "NPP"),

    # -- Optical / Multispectral (NDVI-capable) --
    ("sentinel-2", "ndvi", "Optical Imagery"),
    ("hls2-l30", "ndvi", "HLS Landsat"),
    ("hls2-s30", "ndvi", "HLS Sentinel"),
    ("landsat-c2-l2", "ndvi", "Landsat Collection 2 L2"),
    ("landsat-c2-l1", "ndvi", "Landsat Collection 2 L1"),
    ("naip", "ndvi", "NAIP Aerial"),
    ("aster", "ndvi", "ASTER Multispectral"),

    # -- Surface Reflectance / BRDF --
    ("modis-43a4", "reflectance", "BRDF/NBAR"),
    ("modis-09a1", "reflectance", "Surface Reflectance (8-day)"),
    ("modis-09q1", "reflectance", "Surface Reflectance (250m)"),

    # -- SAR / Radar --
    ("sentinel-1-grd", "sar", "SAR GRD"),
    ("sentinel-1-rtc", "sar", "SAR RTC"),
    ("alos-palsar", "sar", "ALOS PALSAR"),

    # -- Water --
    ("jrc-gsw", "water", "Water Occurrence"),

    # -- Biomass --
    ("chloris-biomass", "biomass", "Above-ground Biomass"),

    # -- Land Cover (classification — no numeric sampling, use domain tool) --
    ("esa-worldcover", "landcover", "Land Cover"),
    ("esa-cci-lc", "landcover", "Land Cover (ESA CCI)"),
    ("io-lulc-annual-v02", "landcover", "Land Use/Land Cover"),
    ("io-lulc-9-class", "landcover", "Land Use/Land Cover"),
    ("io-lulc", "landcover", "Land Use/Land Cover"),
    ("usda-cdl", "landcover", "Cropland Data Layer"),
    ("drcog-lulc", "landcover", "Land Use/Land Cover"),
    ("nrcan-landcover", "landcover", "Land Cover (Canada)"),
    ("noaa-c-cap", "landcover", "Coastal Land Cover"),
    ("chesapeake-lc-13", "landcover", "Land Cover (Chesapeake)"),
    ("chesapeake-lc-7", "landcover", "Land Cover (Chesapeake)"),
    ("chesapeake-lu", "landcover", "Land Use (Chesapeake)"),
    ("usgs-gap", "landcover", "GAP Land Cover"),
    ("usgs-lcmap-conus", "landcover", "Land Cover (LCMAP)"),
    ("usgs-lcmap-hawaii", "landcover", "Land Cover (Hawaii)"),
    ("alos-fnf-mosaic", "landcover", "Forest/Non-Forest"),

    # -- Climate Projections (NetCDF — not COG, limited raster sampling) --
    ("nasa-nex-gddp-cmip6", "climate", "Climate Projection (CMIP6)"),
    ("nex-gddp", "climate", "Climate Projection (NEX-GDDP)"),

    # -- Precipitation --
    ("noaa-mrms-qpe", "auto", "Precipitation"),

    # -- Climate Normals --
    ("noaa-climate-normals", "auto", "Climate Normals"),
    ("noaa-nclimgrid", "auto", "Climate Grid"),

    # -- Thematic (non-raster or specialized) --
    ("hrea", "auto", "Electricity Access"),
    ("hgb", "auto", "Gap Habitat"),
    ("mobi", "auto", "Biodiversity Importance"),
    ("io-biodiversity", "auto", "Biodiversity"),
    ("ms-buildings", "auto", "Building Footprints"),
]

# ============================================================================
# VALUE-QUESTION KEYWORDS  (used for TONE CONTROL, not gating)
# ============================================================================
# When these patterns match, the pre-sampled raster value is injected with
# forceful wording ("use this data, do NOT guess from colors").  When they
# don't match, the value is still injected but with softer wording so the
# agent can decide whether to surface it.  Pre-sampling itself is ALWAYS
# triggered when raster-capable data is loaded — no regex gate.
# ============================================================================

VALUE_QUESTION_PATTERNS = [
    # Direct value requests — "what is the X"
    r"what is the (?:sea surface |surface |land surface )?temperature",
    r"what(?:'s| is) the (?:elevation|altitude|height)",
    r"what(?:'s| is) the (?:ndvi|evi|vegetation index|greenness)",
    r"what(?:'s| is) the (?:value|reading|measurement)",
    r"what(?:'s| is) the (?:snow|ice) (?:cover|extent)",
    r"what(?:'s| is) the (?:fire|thermal|burn|frp|maxfrp)",
    r"what(?:'s| is) the (?:water|flood|inundation)",
    r"what(?:'s| is) the (?:biomass|carbon)",
    r"what(?:'s| is) the (?:backscatter|radar|sar)",
    r"what(?:'s| is) the (?:reflectance|albedo)",
    r"what(?:'s| is) the (?:precipitation|rainfall|rain)",
    r"what(?:'s| is) the (?:projected|climate|cmip6)",
    r"(?:projected|climate projection|cmip6) (?:temperature|precipitation|wind|humidity)",
    r"what(?:'s| is) the (?:land cover|land use)",
    r"what(?:'s| is) the (?:slope|aspect|steepness)",
    r"what(?:'s| is) the (?:evapotranspiration|et\b)",
    r"what(?:'s| is) the (?:lai|leaf area|fpar)",
    r"what(?:'s| is) the (?:gpp|npp|productivity)",
    # Plural form — "what are the X values"
    r"what are the (?:ndvi|evi|temperature|elevation|fire|snow|water|biomass|sar|backscatter|reflectance|lai|gpp|npp|frp|maxfrp|vv|vh|hh|hv|polarization|raster|projected|climate)",
    # Temperature/elevation/NDVI/FRP at location
    r"(?:temperature|elevation|ndvi|evi|sst|lst|frp|maxfrp|fire radiative) (?:at|of|for|near|in|here)",
    r"(?:at|of|for|near|in) (?:this|that|the|my) (?:location|point|spot|pin|coordinate|field|area|site)",
    # How hot/cold/high/deep
    r"how (?:hot|cold|warm|cool) is",
    r"how (?:high|tall|deep|low) is",
    # Measure/sample/extract/read/get — broad verb patterns
    r"(?:measure|sample|extract|read|get|tell me|give me|show me|report) .*(?:value|temperature|elevation|ndvi|evi|data|frp|maxfrp|fire radiative|raster|pixel|measurement|reading|reflectance|brdf|band)",
    r"sample (?:the )?(?:fire|frp|maxfrp|ndvi|evi|temperature|elevation|raster|pixel|value|reflectance|brdf|band)",
    # "in celsius/fahrenheit/meters/feet"
    r"in (?:celsius|fahrenheit|kelvin|meters|feet|degrees)",
    # Numeric expectation
    r"(?:exact|actual|precise|numeric|quantitative) (?:value|temperature|elevation|measurement|reading)",
    # Domain-specific asks that imply numeric sampling
    r"fire radiative power",
    r"radiative power",
    r"maxfrp",
    r"pixel value",
    r"raster value",
    r"data value",
    r"(?:ndvi|evi|ndwi|lai|fpar|gpp|npp) (?:value|index|at|for|here)",
    r"(?:tasmax|tasmin|\btas\b|sfcwind|\bpr\b|hurs|huss|rlds|rsds)",
    r"(?:projected|projection) .*(?:value|temperature|precipitation|wind|humidity|radiation)",
]

_VALUE_QUESTION_RE = re.compile("|".join(VALUE_QUESTION_PATTERNS), re.IGNORECASE)


def _detect_raster_data_type(collections: List[str]) -> Optional[Tuple[str, str]]:
    """
    Given loaded collection IDs, return the best (data_type, human_label) for
    sample_raster_value, or None if no mapping exists.
    """
    if not collections:
        return None
    for coll in collections:
        coll_lower = coll.lower()
        for pattern, data_type, label in COLLECTION_RASTER_MAP:
            if pattern in coll_lower:
                return (data_type, label)
    return None


def _is_value_question(query: str) -> bool:
    """Return True if the user query is asking for a measurable numeric value."""
    return bool(_VALUE_QUESTION_RE.search(query))


# ============================================================================
# VISION AGENT SYSTEM PROMPT
# ============================================================================

VISION_AGENT_INSTRUCTIONS = """You are a Geospatial Intelligence (GEOINT) Vision Analysis Agent specializing in satellite imagery analysis, environmental monitoring, and quantitative data extraction from Earth observation data.

## Available Tools (13 total):

### Visual Analysis
1. **analyze_screenshot(question)** - Analyze the map screenshot with GPT-5 Vision. Use for: visual features, patterns, colors, land cover identification, "what do you see", general map questions.
2. **identify_features(feature_type)** - Identify specific geographic features visible on the map. Use for: "what is that", rivers, mountains, cities, landmarks, roads.

### Quantitative Raster Analysis
3. **analyze_raster(metric_type)** - Get statistics from loaded raster data (elevation, NDVI, SST). Use for: quantitative analysis, statistics, overall metrics.
4. **sample_raster_value(data_type)** - Extract the ACTUAL pixel value at the pin/center location. Use for: "what is the value", "temperature at", "elevation at", point-specific measurements. **THIS IS THE MOST IMPORTANT TOOL FOR NUMERIC DATA.**

### Domain-Specific Analysis
5. **analyze_vegetation(analysis_type)** - MODIS vegetation products + optical NDVI. Use when: MODIS-13, HLS, Sentinel-2, Landsat data is loaded AND question is about vegetation/NDVI/EVI/LAI.
6. **analyze_fire(analysis_type)** - Fire detection and burn severity. Use when: MODIS-14, MTBS data is loaded AND question is about fires/burns.
7. **analyze_land_cover(analysis_type)** - Land cover classification. Use when: ESA WorldCover, CDL, IO-LULC data is loaded.
8. **analyze_snow(analysis_type)** - Snow/ice analysis. Use when: MODIS-10 data is loaded AND question is about snow/ice.
9. **analyze_sar(analysis_type)** - Radar/SAR analysis. Use when: Sentinel-1, ALOS PALSAR data is loaded.
10. **analyze_water(analysis_type)** - Water occurrence and flood detection. Use when: JRC-GSW, Sentinel-1 data is loaded.
11. **analyze_biomass(analysis_type)** - Above-ground biomass. Use when: CHLORIS data is loaded.

### Knowledge & Temporal
12. **query_knowledge(question)** - Answer educational/factual questions using LLM knowledge. Use for: "why", "explain", "how does", general knowledge questions.
13. **compare_temporal(location, time_period_1, time_period_2, analysis_focus)** - Compare satellite data between two time periods. Use for: change detection, before/after comparisons.

## CRITICAL TOOL SELECTION RULES:

### Data-to-Tool Matching (HIGHEST PRIORITY):
- **SST / sea surface temperature / ocean temperature data loaded** -> ALWAYS use `sample_raster_value(data_type='sst')`
- **DEM / elevation / cop-dem data loaded** -> Use `sample_raster_value(data_type='elevation')` for point values, `analyze_raster(metric_type='elevation')` for statistics
- **Sentinel-2 / HLS / Landsat loaded + NDVI question** -> Use `sample_raster_value(data_type='ndvi')` for point, `analyze_vegetation` for area
- **MODIS-13 loaded** -> Use `analyze_vegetation` or `sample_raster_value(data_type='vegetation')`
- **MODIS-14 / MTBS loaded** -> Use `analyze_fire` or `sample_raster_value(data_type='fire')`
- **JRC-GSW loaded** -> Use `analyze_water` or `sample_raster_value(data_type='water')`
- **MODIS-10 loaded** -> Use `analyze_snow` or `sample_raster_value(data_type='snow')`
- **Sentinel-1 / SAR loaded** -> Use `analyze_sar` or `sample_raster_value(data_type='sar')`

### When to use sample_raster_value:
- User asks for a specific VALUE at a location -> sample_raster_value
- User asks "what is the temperature/elevation/NDVI here" -> sample_raster_value
- Any loaded STAC data + question about its value -> sample_raster_value
- **DEFAULT when any raster data is loaded and the user asks about it**

### When to use analyze_screenshot:
- No specific data loaded but screenshot available
- User asks about visual appearance, colors, patterns
- General "what does this area look like" questions

### When to use query_knowledge:
- No data loaded AND question is educational/factual
- "Why is the ocean warm here?"
- Historical or scientific context questions

## Guidelines:
1. ALWAYS prefer tools that match the loaded data type
2. When STAC data is loaded, ALWAYS try sample_raster_value or the domain-specific tool
3. Include actual numeric values with units in your response
4. Interpret values (e.g., NDVI 0.7 = dense vegetation, SST 28°C = warm tropical water)
5. Be concise but informative — focus on answering the user's specific question
6. If a tool fails, explain what happened and suggest alternatives
7. **Summary**: ALWAYS conclude with a **Summary** section that gives a clear, direct answer to the user's specific question, grounded in the data returned by your tools. For example:
   - If asked "what is the temperature here?", end with the exact value and units from sample_raster_value (e.g., "The sea surface temperature at this location is 27.3°C")
   - If asked "what crop is growing here?", end with the identified land cover class from tool output
   - If asked about vegetation health, end with a clear healthy/stressed/sparse assessment citing the NDVI value
   - Never end with generic descriptions — always tie your conclusion to actual tool data
"""


# ============================================================================
# SESSION DATACLASS
# ============================================================================

@dataclass
class VisionSession:
    """Represents a conversation session with the vision agent."""
    session_id: str
    thread_id: Optional[str] = None  # Agent Service thread ID
    screenshot_base64: Optional[str] = None
    map_bounds: Optional[Dict[str, float]] = None
    loaded_collections: List[str] = field(default_factory=list)
    tile_urls: List[str] = field(default_factory=list)
    stac_items: List[Dict[str, Any]] = field(default_factory=list)
    last_analysis: Optional[str] = None
    conversation_history: List[Dict[str, str]] = field(default_factory=list)
    created_at: datetime = field(default_factory=datetime.utcnow)
    updated_at: datetime = field(default_factory=datetime.utcnow)

    def add_turn(self, role: str, content: str):
        """Add a conversation turn and trim to last 10."""
        self.conversation_history.append({"role": role, "content": content})
        self.updated_at = datetime.utcnow()
        if len(self.conversation_history) > 10:
            self.conversation_history = self.conversation_history[-10:]


# ============================================================================
# ENHANCED VISION AGENT (Agent Service)
# ============================================================================

class EnhancedVisionAgent:
    """
    Azure AI Agent Service-based vision analysis agent.

    Replaces the Semantic Kernel ChatCompletionAgent with:
    - AgentsClient for agent creation and management
    - FunctionTool for 13 standalone tool functions
    - ToolSet with auto function calling
    - Agent threads for persistent conversation
    """

    def __init__(self):
        """Initialize the vision agent (lazy — actual setup on first use)."""
        self.sessions: Dict[str, VisionSession] = {}
        self.memory_ttl = timedelta(minutes=30)
        self._agents_client = None
        self._agent_id: Optional[str] = None
        self._initialized = False
        self._init_retries = 0
        self._max_init_retries = 2
        logger.info("EnhancedVisionAgent created (will initialize on first use)")

    async def _ensure_initialized(self):
        """Lazy initialization of Agent Service client and agent.
        
        Retries up to _max_init_retries times on transient Azure errors.
        Resets _initialized on failure so a fresh attempt is made next call.
        """
        if self._initialized:
            return

        import asyncio

        last_error = None
        for attempt in range(self._max_init_retries + 1):
            try:
                if attempt > 0:
                    wait_secs = 2 ** attempt  # 2s, 4s
                    logger.info(f"[RETRY] Agent Service init attempt {attempt + 1}/{self._max_init_retries + 1} after {wait_secs}s...")
                    await asyncio.sleep(wait_secs)

                await self._do_initialize()
                self._init_retries = 0
                return  # Success
            except Exception as e:
                last_error = e
                logger.warning(f"[RETRY] Agent Service init attempt {attempt + 1} failed: {e}")
                # Reset state so next attempt starts fresh
                self._agents_client = None
                self._agent_id = None
                self._initialized = False

        # All retries exhausted
        raise last_error

    async def _do_initialize(self):
        """Actual initialization logic (separated for retry wrapper)."""
        logger.info("Initializing EnhancedVisionAgent with Azure AI Agent Service...")

        endpoint = os.getenv("AZURE_AI_PROJECT_ENDPOINT") or os.getenv("AZURE_OPENAI_ENDPOINT")
        deployment = os.getenv("AZURE_OPENAI_DEPLOYMENT_NAME", "gpt-5")
        logger.info(f"Vision agent using endpoint: {endpoint[:50]}..." if endpoint else "No endpoint found")

        if not endpoint:
            raise ValueError("AZURE_AI_PROJECT_ENDPOINT or AZURE_OPENAI_ENDPOINT environment variable is required")

        # Use Managed Identity
        credential = DefaultAzureCredential()

        # Import Agent Service SDK
        from azure.ai.agents.aio import AgentsClient
        from azure.ai.agents.models import AsyncFunctionTool, AsyncToolSet

        # Create async AgentsClient
        self._agents_client = AgentsClient(
            endpoint=endpoint,
            credential=credential,
        )

        # Build vision tools as standalone functions for FunctionTool
        from agents.vision_tools import create_vision_functions
        vision_functions = create_vision_functions()

        # Create AsyncFunctionTool and AsyncToolSet with auto function calling
        functions = AsyncFunctionTool(vision_functions)
        toolset = AsyncToolSet()
        toolset.add(functions)
        self._agents_client.enable_auto_function_calls(toolset)

        # Create the agent
        agent = await self._agents_client.create_agent(
            model=deployment,
            name="VisionAnalyst",
            instructions=VISION_AGENT_INSTRUCTIONS,
            toolset=toolset,
        )
        self._agent_id = agent.id

        self._initialized = True
        logger.info(f"EnhancedVisionAgent initialized: agent_id={agent.id}, model={deployment}")

    async def _get_or_create_session(self, session_id: str) -> VisionSession:
        """Get existing session or create a new one with a new Agent Service thread."""
        if session_id in self.sessions:
            return self.sessions[session_id]

        await self._ensure_initialized()

        # Create a new Agent Service thread
        thread = await self._agents_client.threads.create()

        session = VisionSession(session_id=session_id, thread_id=thread.id)
        self.sessions[session_id] = session
        logger.info(f"Created vision session: {session_id} -> thread: {thread.id}")
        return session

    def update_session(self, session_id: str, **kwargs):
        """Update session context (screenshot, STAC items, map bounds, etc.)."""
        session = self.sessions.get(session_id)
        if session:
            for key, value in kwargs.items():
                if hasattr(session, key) and value is not None:
                    setattr(session, key, value)
            session.updated_at = datetime.utcnow()

    def get_or_create_session(self, session_id: str) -> VisionSession:
        """Synchronous version — get session or create a placeholder (thread created on analyze)."""
        if session_id not in self.sessions:
            self.sessions[session_id] = VisionSession(session_id=session_id)
        return self.sessions[session_id]

    async def analyze(
        self,
        user_query: str,
        session_id: str = "default",
        imagery_base64: Optional[str] = None,
        map_bounds: Optional[Dict[str, float]] = None,
        collections: Optional[List[str]] = None,
        tile_urls: Optional[List[str]] = None,
        stac_items: Optional[List[Dict[str, Any]]] = None,
        conversation_history: Optional[List[Dict]] = None,
        **kwargs
    ) -> Dict[str, Any]:
        """
        Analyze a user query with vision tools.

        Same interface as the previous SK-based agent for drop-in compatibility.
        """
        try:
            await self._ensure_initialized()

            # Get or create session with Agent Service thread
            session = await self._get_or_create_session(session_id)

            # Update session with new context
            if imagery_base64:
                session.screenshot_base64 = imagery_base64
            if map_bounds:
                session.map_bounds = map_bounds
            if collections:
                session.loaded_collections = collections
            if tile_urls:
                session.tile_urls = tile_urls
            if stac_items:
                # Trim to 5 most relevant items (pin-covering first, then closest)
                # to avoid slow iteration over 10+ tiles during raster sampling
                pin_lat = (map_bounds or {}).get('pin_lat') or (map_bounds or {}).get('center_lat')
                pin_lng = (map_bounds or {}).get('pin_lng') or (map_bounds or {}).get('center_lng')
                if pin_lat and pin_lng and len(stac_items) > 5:
                    def _covers_pin(item):
                        bbox = item.get('bbox')
                        if not bbox or len(bbox) < 4:
                            return True  # Keep items without bbox
                        return bbox[0] <= pin_lng <= bbox[2] and bbox[1] <= pin_lat <= bbox[3]
                    covering = [it for it in stac_items if _covers_pin(it)]
                    others = [it for it in stac_items if not _covers_pin(it)]
                    stac_items = (covering + others)[:5]
                    logger.info(f"Trimmed STAC items to {len(stac_items)} (covering pin: {len(covering)})")
                session.stac_items = stac_items

            # ================================================================
            # SET MODULE-LEVEL CONTEXT FOR STANDALONE TOOL FUNCTIONS
            # ================================================================
            from agents.vision_tools import set_session_context, get_tool_calls, clear_tool_calls

            set_session_context(
                screenshot_base64=session.screenshot_base64,
                map_bounds=session.map_bounds,
                stac_items=session.stac_items,
                loaded_collections=session.loaded_collections,
                tile_urls=session.tile_urls,
            )
            clear_tool_calls()

            # ================================================================
            # [LOCK] DETERMINISTIC RASTER PRE-SAMPLING  (ALWAYS-ON)
            # ================================================================
            # Whenever raster-capable data is loaded, we pre-sample the COG
            # pixel value at the pin location (~100 ms).  The result is
            # injected into the agent message so it has REAL data to work
            # with.  This completely removes the dependency on regex pattern-
            # matching to decide *whether* to sample — every possible user
            # phrasing is covered because we never skip the read.
            #
            # _is_value_question() is still called, but only to control the
            # *tone* of the injection (forceful vs. supplementary).  It no
            # longer gates whether sampling happens at all.
            # ================================================================
            pre_sampled_value = None     # successful raster data string
            pre_sample_failure = None    # failure explanation string
            is_value_q = _is_value_question(user_query)

            if session.loaded_collections and session.stac_items:
                raster_info = _detect_raster_data_type(session.loaded_collections)
                if raster_info:
                    data_type, data_label = raster_info
                    logger.info(
                        f"[LOCK] ALWAYS-ON PRE-SAMPLE: collection match -> "
                        f"data_type='{data_type}', label='{data_label}' "
                        f"(value_question={is_value_q})")

                    try:
                        from agents.vision_tools import sample_raster_value as _sample_fn
                        raw_result = _sample_fn(data_type=data_type)

                        # Classify: did sampling actually return a value?
                        _fail_indicators = [
                            'no values', 'no valid data', 'sampling returned no values',
                            'no data loaded', 'no stac items', 'no location',
                            'no coordinates', 'outside', 'masked',
                        ]
                        result_lower = (raw_result or '').lower()
                        if any(ind in result_lower for ind in _fail_indicators):
                            # Sampling ran but couldn't extract a value
                            pre_sample_failure = raw_result
                            logger.info(f"[LOCK] PRE-SAMPLE SOFT FAILURE: {raw_result[:200]}...")
                        else:
                            pre_sampled_value = raw_result
                            logger.info(f"[LOCK] PRE-SAMPLE SUCCESS: {raw_result[:200]}...")

                    except Exception as e:
                        pre_sample_failure = (
                            f"Raster sampling encountered an error: {e}. "
                            "This may be a temporary issue with the data service."
                        )
                        logger.warning(f"[WARN] Pre-sampling exception: {e}")
                else:
                    # Collection loaded but not in COLLECTION_RASTER_MAP
                    colls_str = ', '.join(session.loaded_collections)
                    pre_sample_failure = (
                        f"The loaded collection(s) ({colls_str}) are not yet mapped "
                        f"for automatic raster sampling. Visual analysis from the "
                        f"screenshot is available instead."
                    )
                    logger.info(f"[LOCK] PRE-SAMPLE SKIP: no raster map entry for {colls_str}")

            elif session.loaded_collections and not session.stac_items:
                # Collections but no STAC items — frontend didn't send them
                pre_sample_failure = (
                    "Satellite data is displayed on the map, but no STAC item "
                    "metadata was received for raster sampling. Visual analysis "
                    "from the screenshot is available instead."
                )
                logger.info("[LOCK] PRE-SAMPLE SKIP: no STAC items in session")

            # ================================================================
            # BUILD CONTEXT-ENRICHED MESSAGE
            # ================================================================
            context_parts = []

            # -- Pre-sampled raster value or failure explanation --
            if pre_sampled_value:
                if is_value_q:
                    # User is clearly asking for a numeric value -> strong wording
                    context_parts.append(
                        f"[RASTER DATA — ACTUAL SAMPLED VALUE]\n{pre_sampled_value}\n"
                        "The above is a REAL measurement extracted from the underlying Cloud Optimized GeoTIFF. "
                        "Use this data to answer the user's question. Do NOT call analyze_screenshot or guess from colors. "
                        "Interpret and explain the value in context (units, what it means for this location)."
                    )
                else:
                    # User may or may not want the number -> soft wording
                    context_parts.append(
                        f"[RASTER DATA — SAMPLED AT PIN]\n{pre_sampled_value}\n"
                        "The above measurement was automatically read from the Cloud Optimized GeoTIFF at the pin location. "
                        "If the user is asking about values, measurements, or data, use this real data instead of guessing from colors. "
                        "If the user is asking for a visual description or feature identification, you may focus on the screenshot instead."
                    )
            elif pre_sample_failure:
                # Sampling was attempted but failed — tell the agent why so it
                # can give the user a clear, actionable explanation.
                context_parts.append(
                    f"[RASTER SAMPLING ISSUE]\n{pre_sample_failure}\n"
                    "Explain the issue to the user succinctly (1-2 sentences). "
                    "If the failure is due to cloud cover or masked pixels, suggest moving the pin to a nearby visible area. "
                    "If the pin is outside the data extent, suggest placing it within the rendered tiles. "
                    "Do NOT suggest using external GIS software or Python — this platform can sample data directly."
                )

            # Screenshot availability
            if session.screenshot_base64:
                if pre_sampled_value and is_value_q:
                    # De-prioritize screenshot when user clearly wants a number
                    context_parts.append("[Screenshot] A map screenshot is also available, but prefer the sampled raster data above for numeric answers.")
                else:
                    context_parts.append("[Screenshot] A map screenshot is available for visual analysis.")

            # Loaded data + collection-specific hints (using comprehensive map)
            if session.loaded_collections:
                context_parts.append(f"[Loaded Data] Collections: {', '.join(session.loaded_collections)}")

                hints = set()
                for coll in session.loaded_collections:
                    raster_info = _detect_raster_data_type([coll])
                    if raster_info:
                        data_type, label = raster_info
                        hints.add(f"{label} -> use sample_raster_value(data_type='{data_type}')")
                if hints:
                    context_parts.append(f"[Data Hints] {'; '.join(hints)}")

            # Location
            if session.map_bounds:
                b = session.map_bounds
                pin_lat = b.get('pin_lat') or b.get('center_lat')
                pin_lng = b.get('pin_lng') or b.get('center_lng')
                if pin_lat and pin_lng:
                    context_parts.append(f"[Location] Pin: ({pin_lat:.4f}, {pin_lng:.4f})")
                    bbox_str = f"Bounds: W={b.get('west', 'N/A')}, S={b.get('south', 'N/A')}, E={b.get('east', 'N/A')}, N={b.get('north', 'N/A')}"
                    context_parts.append(f"[Map Bounds] {bbox_str}")

            # STAC item count
            if session.stac_items:
                context_parts.append(f"[STAC Items] {len(session.stac_items)} items loaded for analysis")

            # Frontend analysis_type hint (suppressed when pre-sampled data is already available)
            if not pre_sampled_value:
                analysis_type = kwargs.get('analysis_type')
                if analysis_type == 'raster':
                    context_parts.append("[Frontend Hint] RASTER analysis requested. Use sample_raster_value to extract numeric values.")
                elif analysis_type == 'screenshot':
                    context_parts.append("[Frontend Hint] SCREENSHOT analysis requested. Use analyze_screenshot.")

            context_str = "\n".join(context_parts) if context_parts else "[No map context available]"

            augmented_message = f"""[Context]
{context_str}

[User Question]
{user_query}"""

            logger.info(f"Vision session {session_id}: Processing '{user_query[:60]}...'")

            # ================================================================
            # FAST-PATH: Skip Agent Service when pre-sampling already has the answer
            # ================================================================
            # When the user asks a numeric value question AND pre-sampling
            # succeeded, we already have the real data.  Going through the
            # full Agent Service round-trip (30-90s) just to format the
            # answer is wasteful.  Instead, call the direct OpenAI fallback
            # which returns in ~5-10s.
            # ================================================================
            if pre_sampled_value and is_value_q:
                logger.info("[FAST-PATH] Pre-sampled value available + value question detected — skipping Agent Service")
                fast_result = await self._fallback_direct_openai(
                    user_query=user_query,
                    session=session,
                    session_id=session_id,
                    pre_sampled_value=pre_sampled_value,
                    pre_sample_failure=None,
                    is_value_q=True,
                )
                if fast_result:
                    fast_result["agent_mode"] = "fast_path_pre_sampled"
                    fast_result["tools_used"] = ["sample_raster_value_pre_sampled"]
                    return fast_result
                # GPT fallback failed — use template instead of Agent Service
                logger.warning("[FAST-PATH] Direct OpenAI fallback failed — using template response")
                template_response = (
                    f"Here are the raster data values sampled at the pin location:\n\n"
                    f"{pre_sampled_value}\n\n"
                    f"*Note: AI interpretation is temporarily unavailable. "
                    f"The values above are real measurements from the satellite data.*"
                )
                return {
                    "response": template_response,
                    "analysis": template_response,
                    "tools_used": ["sample_raster_value_template"],
                    "tool_calls": [],
                    "confidence": 0.7,
                    "session_id": session_id,
                    "agent_mode": "template_fallback",
                }

            # ================================================================
            # SEND MESSAGE AND PROCESS WITH AGENT SERVICE (with retry)
            # ================================================================
            import asyncio as _aio

            run = None
            for _attempt in range(3):
                try:
                    if _attempt > 0:
                        # Create a fresh thread for retry (previous may be corrupted)
                        logger.info(f"[RETRY] Agent Service run attempt {_attempt + 1}/3...")
                        await _aio.sleep(2 ** _attempt)
                        thread = await self._agents_client.threads.create()
                        session.thread_id = thread.id

                    await self._agents_client.messages.create(
                        thread_id=session.thread_id,
                        role="user",
                        content=augmented_message,
                    )

                    run = await self._agents_client.runs.create_and_process(
                        thread_id=session.thread_id,
                        agent_id=self._agent_id,
                    )
                    break  # Success — exit retry loop
                except Exception as _run_err:
                    logger.warning(f"[RETRY] Agent Service run attempt {_attempt + 1} error: {_run_err}")
                    if _attempt == 2:
                        # All retries exhausted — raise to trigger outer fallback
                        raise

            if run and run.status == "failed":
                logger.error(f"Vision agent run failed: {run.last_error}")
                logger.info("[SYNC] Agent Service run failed — falling back to direct Azure OpenAI Vision API")
                fallback_result = await self._fallback_direct_openai(
                    user_query=user_query,
                    session=session,
                    session_id=session_id,
                    pre_sampled_value=pre_sampled_value,
                    pre_sample_failure=pre_sample_failure,
                    is_value_q=is_value_q,
                )
                if fallback_result:
                    return fallback_result
                # If fallback also fails, try template with pre-sampled data
                if pre_sampled_value:
                    logger.info("[TEMPLATE] Agent run failed + fallback failed, using pre-sampled data")
                    template_response = (
                        f"Here are the raster data values sampled at the pin location:\n\n"
                        f"{pre_sampled_value}\n\n"
                        f"*Note: AI interpretation is temporarily unavailable. "
                        f"The values above are real measurements from the satellite data.*"
                    )
                    return {
                        "response": template_response,
                        "analysis": template_response,
                        "tools_used": ["sample_raster_value_template"],
                        "confidence": 0.7,
                        "session_id": session_id,
                        "agent_mode": "template_fallback",
                    }
                return {
                    "response": (
                        "I'm having trouble connecting to the analysis service right now. "
                        "Please try again in a moment."
                    ),
                    "analysis": "",
                    "tools_used": [],
                    "error": str(run.last_error),
                    "confidence": 0.0,
                    "session_id": session_id,
                }

            # ================================================================
            # EXTRACT RESPONSE FROM THREAD MESSAGES
            # ================================================================
            from azure.ai.agents.models import ListSortOrder

            messages_iterable = self._agents_client.messages.list(
                thread_id=session.thread_id,
                order=ListSortOrder.DESCENDING,
            )

            response_text = ""
            async for msg in messages_iterable:
                if msg.run_id == run.id and msg.role == "assistant":
                    if msg.text_messages:
                        response_text = msg.text_messages[-1].text.value
                    break

            # ================================================================
            # EXTRACT TOOL CALLS FROM RUN STEPS
            # ================================================================
            tools_used = []
            tool_call_details = get_tool_calls()  # From vision_tools module

            try:
                run_steps_iterable = self._agents_client.run_steps.list(
                    thread_id=session.thread_id,
                    run_id=run.id,
                )
                async for step in run_steps_iterable:
                    if hasattr(step, 'step_details') and hasattr(step.step_details, 'tool_calls'):
                        for tc in step.step_details.tool_calls:
                            if hasattr(tc, 'function'):
                                tools_used.append(tc.function.name)
                                logger.info(f"Vision tool called: {tc.function.name}")
            except Exception as e:
                logger.debug(f"Could not extract run steps: {e}")

            # Merge with module-level tool calls
            if not tools_used and tool_call_details:
                tools_used = [tc["tool"] for tc in tool_call_details]
            if not tools_used:
                tools_used = ["agent_auto"]

            # ================================================================
            # UPDATE SESSION AND RETURN
            # ================================================================
            session.last_analysis = response_text
            session.add_turn("user", user_query)
            session.add_turn("assistant", response_text)

            return {
                "response": response_text,
                "analysis": response_text,
                "tools_used": tools_used,
                "tool_calls": tool_call_details,
                "confidence": 0.9 if response_text else 0.5,
                "session_id": session_id,
                "agent_mode": "agent_service",
                "context": {
                    "has_screenshot": bool(session.screenshot_base64),
                    "collections": session.loaded_collections,
                    "map_bounds": session.map_bounds
                }
            }

        except Exception as e:
            logger.error(f"[FAIL] EnhancedVisionAgent.analyze error: {e}")
            import traceback
            logger.error(traceback.format_exc())

            # Fallback to direct Azure OpenAI when Agent Service is unavailable
            logger.info("[SYNC] Agent Service unavailable — falling back to direct Azure OpenAI Vision API")
            try:
                session = self.sessions.get(session_id)
                if not session:
                    # Create a minimal session for fallback (agent init may have failed before session creation)
                    session = VisionSession(session_id=session_id)
                    # Populate from kwargs that were passed to analyze()
                    session.screenshot_base64 = kwargs.get("imagery_base64") or imagery_base64
                    session.map_bounds = kwargs.get("map_bounds") or map_bounds
                    session.loaded_collections = kwargs.get("collections") or collections or []
                # Pass pre-sampled data if available (may have been set before the exception)
                fallback_result = await self._fallback_direct_openai(
                    user_query=user_query,
                    session=session,
                    session_id=session_id,
                    pre_sampled_value=locals().get('pre_sampled_value'),
                    pre_sample_failure=locals().get('pre_sample_failure'),
                    is_value_q=locals().get('is_value_q', False),
                )
                if fallback_result:
                    return fallback_result
            except Exception as fallback_err:
                logger.error(f"[FAIL] Fallback also failed: {fallback_err}")

            # ================================================================
            # LAST RESORT: Template-based response when we have pre-sampled data
            # ================================================================
            # If pre-sampling already extracted real raster data, we can
            # present it directly without any GPT call.  This prevents the
            # user seeing a raw Azure SDK error when the data is actually
            # available.
            _pre_val = locals().get('pre_sampled_value')
            _pre_fail = locals().get('pre_sample_failure')
            if _pre_val:
                logger.info("[TEMPLATE] Using pre-sampled data as template response (all GPT calls failed)")
                template_response = (
                    f"Here are the raster data values sampled at the pin location:\n\n"
                    f"{_pre_val}\n\n"
                    f"*Note: AI interpretation is temporarily unavailable. "
                    f"The values above are real measurements from the satellite data.*"
                )
                return {
                    "response": template_response,
                    "analysis": template_response,
                    "tools_used": ["sample_raster_value_template"],
                    "tool_calls": [],
                    "confidence": 0.7,
                    "session_id": session_id,
                    "agent_mode": "template_fallback",
                }
            elif _pre_fail:
                logger.info("[TEMPLATE] Returning sampling failure explanation (all GPT calls failed)")
                return {
                    "response": _pre_fail,
                    "analysis": _pre_fail,
                    "tools_used": [],
                    "tool_calls": [],
                    "confidence": 0.3,
                    "session_id": session_id,
                    "agent_mode": "template_fallback",
                }

            return {
                "response": (
                    "I'm having trouble connecting to the analysis service right now. "
                    "Please try again in a moment. If the issue persists, try refreshing the page."
                ),
                "analysis": "",
                "tools_used": [],
                "error": str(e),
                "confidence": 0.0,
                "session_id": session_id,
            }

    # ====================================================================
    # FALLBACK: Direct Azure OpenAI Vision API (when Agent Service fails)
    # ====================================================================

    async def _fallback_direct_openai(
        self,
        user_query: str,
        session: VisionSession,
        session_id: str,
        pre_sampled_value: Optional[str] = None,
        pre_sample_failure: Optional[str] = None,
        is_value_q: bool = False,
    ) -> Optional[Dict[str, Any]]:
        """
        Fallback to direct Azure OpenAI Chat Completions API with Vision.

        Called when the Agent Service is unavailable (404, network disabled, etc.).
        Sends the screenshot + user query directly to GPT-5 Vision without tools.
        If pre-sampled raster data is available, it is injected into the prompt.
        """
        import aiohttp

        endpoint = os.getenv("AZURE_OPENAI_ENDPOINT", "")
        # Fallback: try AZURE_AI_PROJECT_ENDPOINT if AZURE_OPENAI_ENDPOINT is not set
        # Azure AI Foundry project endpoints support the OpenAI chat completions API
        if not endpoint:
            endpoint = os.getenv("AZURE_AI_PROJECT_ENDPOINT", "")
            if endpoint:
                logger.info("[SYNC] Using AZURE_AI_PROJECT_ENDPOINT for fallback (AZURE_OPENAI_ENDPOINT not set)")
        deployment = os.getenv("AZURE_OPENAI_DEPLOYMENT_NAME", "gpt-5")
        api_key = os.getenv("AZURE_OPENAI_API_KEY", "")
        use_managed_identity = os.getenv("AZURE_OPENAI_USE_MANAGED_IDENTITY", "").lower() == "true"

        if not endpoint:
            logger.error("No AZURE_OPENAI_ENDPOINT for fallback")
            return None

        # Build auth headers
        headers = {"Content-Type": "application/json"}
        if use_managed_identity or not api_key:
            try:
                from cloud_config import cloud_cfg
                credential = DefaultAzureCredential()
                token = credential.get_token(cloud_cfg.cognitive_services_scope)
                headers["Authorization"] = f"Bearer {token.token}"
            except Exception as auth_err:
                logger.error(f"Fallback auth failed: {auth_err}")
                return None
        else:
            headers["api-key"] = api_key

        # Build context
        context_parts = []
        if session.loaded_collections:
            context_parts.append(f"Loaded satellite data: {', '.join(session.loaded_collections)}")
        if session.map_bounds:
            b = session.map_bounds
            pin_lat = b.get("pin_lat") or b.get("center_lat")
            pin_lng = b.get("pin_lng") or b.get("center_lng")
            if pin_lat and pin_lng:
                context_parts.append(f"Map center: ({pin_lat:.4f}, {pin_lng:.4f})")
                context_parts.append(
                    f"Bounds: W={b.get('west', 'N/A')}, S={b.get('south', 'N/A')}, "
                    f"E={b.get('east', 'N/A')}, N={b.get('north', 'N/A')}"
                )

        # Inject pre-sampled raster data into fallback context
        if pre_sampled_value:
            if is_value_q:
                context_parts.append(
                    f"\n[RASTER DATA — ACTUAL SAMPLED VALUE]\n{pre_sampled_value}\n"
                    "The above is a REAL measurement extracted from the underlying Cloud Optimized GeoTIFF. "
                    "Use this data to answer the user's question. Do NOT guess from colors. "
                    "Interpret and explain the value in context (units, what it means for this location)."
                )
            else:
                context_parts.append(
                    f"\n[RASTER DATA — SAMPLED AT PIN]\n{pre_sampled_value}\n"
                    "The above measurement was automatically read from the COG at the pin location. "
                    "Use this real data to answer instead of guessing from colors."
                )
        elif pre_sample_failure:
            context_parts.append(
                f"\n[RASTER SAMPLING ISSUE]\n{pre_sample_failure}\n"
                "Explain the issue to the user succinctly. "
                "Do NOT suggest using external GIS software or Python — this platform can sample data directly."
            )

        context_str = "\n".join(context_parts) if context_parts else "No additional context."

        if pre_sampled_value and is_value_q:
            system_prompt = (
                "You are a geospatial intelligence analyst. Real raster data has been sampled from the "
                "underlying Cloud Optimized GeoTIFF and is provided in the context. Use ONLY this real "
                "data to answer the user's question — do NOT make up values or give generic instructions. "
                "Interpret the values with proper units and explain what they mean for this location. "
                "Be concise but informative."
            )
        else:
            system_prompt = (
                "You are a geospatial intelligence analyst. Analyze the satellite/map imagery and "
                "answer the user's question. If a map screenshot is provided, describe what you see "
                "including terrain, land cover, water bodies, urban areas, and notable features. "
                "Be concise but informative."
            )

        user_content: list = [
            {"type": "text", "text": f"{context_str}\n\nUser question: {user_query}"}
        ]

        # Attach screenshot if available
        if session.screenshot_base64:
            user_content.append({
                "type": "image_url",
                "image_url": {
                    "url": f"data:image/png;base64,{session.screenshot_base64}",
                    "detail": "high",
                },
            })

        payload = {
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_content},
            ],
            "max_completion_tokens": 1500,
        }

        # Determine the correct URL (handle both Azure OpenAI and AI Foundry endpoints)
        url = f"{endpoint.rstrip('/')}/openai/deployments/{deployment}/chat/completions?api-version=2024-12-01-preview"

        logger.info(f"[SYNC] Fallback: calling {deployment} directly at {endpoint}")

        try:
            async with aiohttp.ClientSession() as http_session:
                async with http_session.post(
                    url,
                    headers=headers,
                    json=payload,
                    timeout=aiohttp.ClientTimeout(total=60),
                ) as resp:
                    if resp.status != 200:
                        error_text = await resp.text()
                        logger.error(f"Fallback API error {resp.status}: {error_text[:300]}")
                        return None

                    result = await resp.json()
                    analysis_text = result["choices"][0]["message"]["content"]

                    logger.info(f"[OK] Fallback vision analysis succeeded ({len(analysis_text)} chars)")

                    # Update session
                    session.last_analysis = analysis_text
                    session.add_turn("user", user_query)
                    session.add_turn("assistant", analysis_text)

                    return {
                        "response": analysis_text,
                        "analysis": analysis_text,
                        "tools_used": ["direct_openai_vision_fallback"],
                        "tool_calls": [],
                        "confidence": 0.8,
                        "session_id": session_id,
                        "agent_mode": "direct_openai_fallback",
                        "context": {
                            "has_screenshot": bool(session.screenshot_base64),
                            "collections": session.loaded_collections,
                            "map_bounds": session.map_bounds,
                        },
                    }
        except Exception as e:
            logger.error(f"[FAIL] Fallback direct OpenAI call failed: {e}")
            return None

    def cleanup_old_sessions(self, max_age_minutes: int = 30):
        """Remove sessions older than max_age_minutes."""
        now = datetime.utcnow()
        expired = [
            sid for sid, session in self.sessions.items()
            if (now - session.updated_at).total_seconds() > max_age_minutes * 60
        ]
        for sid in expired:
            del self.sessions[sid]
            logger.info(f"Cleaned up expired vision session: {sid}")

    async def cleanup(self):
        """Cleanup agent resources on shutdown."""
        if self._agents_client and self._agent_id:
            try:
                await self._agents_client.delete_agent(self._agent_id)
                logger.info(f"Deleted vision agent: {self._agent_id}")
            except Exception as e:
                logger.debug(f"Agent cleanup: {e}")


# ============================================================================
# SINGLETON AND ALIASES
# ============================================================================

_enhanced_vision_agent: Optional[EnhancedVisionAgent] = None


def get_enhanced_vision_agent() -> EnhancedVisionAgent:
    """Get the singleton EnhancedVisionAgent instance."""
    global _enhanced_vision_agent
    if _enhanced_vision_agent is None:
        _enhanced_vision_agent = EnhancedVisionAgent()
    return _enhanced_vision_agent


def get_vision_agent() -> EnhancedVisionAgent:
    """Alias for get_enhanced_vision_agent (backwards compatibility)."""
    return get_enhanced_vision_agent()


# Backwards compatibility alias
VisionAgent = EnhancedVisionAgent
