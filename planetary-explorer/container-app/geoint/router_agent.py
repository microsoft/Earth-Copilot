"""
Router Agent - Heuristic + LLM-assisted query classification and routing.

Wave 4 retired the Semantic Kernel ChatCompletionAgent that previously drove
this module. The kernel-function tools were dead code (route_query produced
the action dict directly via heuristics + two narrow LLM helpers, never
delegating to the agent). This module now uses direct
`AsyncAzureOpenAI` calls via `pipeline._aoai.get_aoai_client()` and the
shared `SessionContextStore`.

Public API preserved for backward compatibility with `fastapi_app.py`:
- `RouterAgent` class
- `RouterAgent.tools.session_contexts`  (dict-like, backed by SessionContextStore)
- `RouterAgent.update_session_context(session_id, context)`
- `RouterAgent.route_query(query, session_id, has_screenshot)`
- `RouterAgent.set_semantic_translator(translator)`
- `RouterAgent.set_vision_agent(agent)`
- `get_router_agent()` singleton accessor
"""

from __future__ import annotations

import json
import logging
import os
import re
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)


# ============================================================================
# COLLECTION / LOCATION VOCABULARIES (loaded once at import)
# ============================================================================

try:
    from collection_name_mapper import CollectionMapper

    _collection_mapper = CollectionMapper()
    COLLECTION_KEYWORDS = set(_collection_mapper.keyword_map.keys())
    logger.info(
        f" Loaded {len(COLLECTION_KEYWORDS)} collection keywords from CollectionMapper"
    )
except Exception as e:
    logger.warning(f" Could not load CollectionMapper: {e}")
    COLLECTION_KEYWORDS = set()

try:
    from location_resolver import EnhancedLocationResolver

    LOCATION_NAMES = set(EnhancedLocationResolver.STORED_LOCATIONS.keys())
    logger.info(f" Loaded {len(LOCATION_NAMES)} location names from LocationResolver")
except Exception as e:
    logger.warning(f" Could not load LocationResolver locations: {e}")
    LOCATION_NAMES = set()


# ============================================================================
# ROUTER AGENT TOOLS - backing storage for session context
# ============================================================================
#
# Historically `tools.session_contexts` was a plain dict bolted onto the
# Semantic Kernel plugin object so its kernel_function methods could share
# state. Wave 4 moved the actual storage into `pipeline.session_store`. We
# expose it here as a property so legacy code that does
#     router_agent.tools.session_contexts.get(sid, {})
#     router_agent.tools.session_contexts[sid]["foo"] = ...
# keeps working unchanged.
# ============================================================================

class RouterAgentTools:
    """Thin shim around the shared SessionContextStore."""

    def __init__(self) -> None:
        from pipeline.session_store import get_session_store
        self._store = get_session_store()
        self.semantic_translator = None
        self.vision_agent = None

    # Mutable dict view - legacy code reads/writes through this attribute.
    @property
    def session_contexts(self) -> Dict[str, Dict[str, Any]]:
        return self._store.raw

    def set_semantic_translator(self, translator: Any) -> None:
        self.semantic_translator = translator

    def set_vision_agent(self, agent: Any) -> None:
        self.vision_agent = agent

    def update_session_context(self, session_id: str, context: Dict[str, Any]) -> None:
        merged = self._store.update(session_id, context)
        logger.info(
            f" RouterTools: session {session_id[:8]}... has_rendered_map="
            f"{merged.get('has_rendered_map')} has_screenshot={merged.get('has_screenshot')}"
        )


# ============================================================================
# ROUTER AGENT
# ============================================================================

class RouterAgent:
    """Heuristic + LLM-assisted classifier producing the legacy action dict.

    No longer depends on Semantic Kernel. The two LLM helpers
    (`_classify_query_with_llm`, `_extract_location_only`) issue direct
    chat-completions calls via `pipeline._aoai.get_aoai_client()`.
    """

    def __init__(self) -> None:
        self.tools = RouterAgentTools()
        logger.info(" RouterAgent created (direct AOAI, no Semantic Kernel)")

    # -- accessor passthroughs ------------------------------------------------

    def set_semantic_translator(self, translator: Any) -> None:
        self.tools.set_semantic_translator(translator)

    def set_vision_agent(self, agent: Any) -> None:
        self.tools.set_vision_agent(agent)

    def update_session_context(self, session_id: str, context: Dict[str, Any]) -> None:
        self.tools.update_session_context(session_id, context)

    # -- AOAI wrappers --------------------------------------------------------

    def _deployment(self) -> str:
        # Routing/extraction only - use FAST deployment (gpt-4o-mini).
        return os.getenv("AZURE_OPENAI_FAST_DEPLOYMENT", "gpt-4o-mini")

    async def _chat_json(self, prompt: str) -> Dict[str, Any]:
        """Issue a single user-message chat completion expecting a JSON object."""
        from pipeline._aoai import get_aoai_client

        client = get_aoai_client()
        resp = await client.chat.completions.create(
            model=self._deployment(),
            messages=[{"role": "user", "content": prompt}],
            response_format={"type": "json_object"},
            temperature=0.0,
        )
        text = (resp.choices[0].message.content or "").strip()
        if "```json" in text:
            text = text.split("```json", 1)[1].split("```", 1)[0].strip()
        elif "```" in text:
            text = text.split("```", 1)[1].split("```", 1)[0].strip()
        return json.loads(text)

    # -- main routing entrypoint ---------------------------------------------

    async def route_query(
        self,
        query: str,
        session_id: str,
        has_screenshot: bool = False,
        has_pin: bool = False,
        has_satellite_data: bool = False,
    ) -> Dict[str, Any]:
        """Classify ``query`` and return a legacy router-action dict."""
        logger.info(
            f" RouterAgent processing: '{query}' (has_pin={has_pin} "
            f"has_satellite_data={has_satellite_data})"
        )

        # Update has_screenshot in session context if we already track this session
        if session_id in self.tools.session_contexts:
            self.tools.session_contexts[session_id]["has_screenshot"] = has_screenshot
            # Frontend's has_satellite_data flag is the authoritative signal that
            # tiles are currently rendered on the map. Promote it into the
            # session so the pin+map raster-sample pre-check fires reliably
            # even when the session hasn't been touched by a STAC turn yet
            # (e.g. after a container scale-out drops in-memory state).
            if has_satellite_data:
                self.tools.session_contexts[session_id]["has_rendered_map"] = True

        # ====================================================================
        # SMALL TALK / GREETING / IDENTITY PRE-CHECK
        # ====================================================================
        _q_norm = re.sub(r"[^\w\s]", "", query.lower()).strip()
        _q_tokens = _q_norm.split()
        _greeting_words = {
            "hi", "hii", "hiii", "hello", "helo", "helllo", "hellooo",
            "hey", "heya", "hiya", "yo", "sup", "howdy", "greetings",
            "gm", "gn", "morning", "afternoon", "evening",
            "good", "goodmorning", "goodafternoon", "goodevening",
            "namaste", "salaam", "salam", "hola", "bonjour", "ciao",
        }
        _thanks_words = {"thanks", "thx", "thankyou", "ty", "tysm", "appreciate"}
        _identity_phrases = (
            "who are you", "what are you", "what can you do",
            "what can i do", "what ca i do", "what cn i do",
            "wat can i do", "what i can do", "what could i do",
            "what should i do", "what do i do",
            "what do you do", "how do you work", "how does this work",
            "how does it work", "how to use", "how do i use",
            "what can this do", "what does this do",
            "help me", "help",
            "what is this", "whats this", "what's this", "what is geo ai",
            "what is geoai", "what is planetary explorer",
            "introduce yourself", "tell me about yourself",
            "show me what you can do", "show me how this works",
            "i need help", "im lost", "i'm lost", "im stuck", "i'm stuck",
            "where do i start", "how do i start", "getting started",
        )
        _ambiguous_short = {
            "help", "?", "what", "how", "info", "options", "menu",
            "guide", "start", "begin", "intro",
        }
        is_greeting = bool(_q_tokens) and (
            _q_tokens[0] in _greeting_words
            or (
                len(_q_tokens) >= 2
                and _q_tokens[0] == "good"
                and _q_tokens[1] in {"morning", "afternoon", "evening", "day"}
            )
        )
        is_thanks = bool(_q_tokens) and _q_tokens[0] in _thanks_words
        is_identity = (
            any(p in _q_norm for p in _identity_phrases)
            or _q_norm in _ambiguous_short
        )

        if is_greeting or is_thanks or is_identity:
            logger.info(f"SMALL TALK / IDENTITY DETECTED: '{query}' -> clarify(intent)")
            return {
                "action_type": "clarify",
                "original_query": query,
                "target_route": None,
                "missing_slot": "intent",
                "needs_stac_search": False,
                "needs_vision_analysis": False,
                "routing_reason": "small_talk_to_clarify",
            }

        # ====================================================================
        # GUARANTEED VISION FOR ANALYTICAL FOLLOW-UP QUERIES
        # ====================================================================
        session_context = self.tools.session_contexts.get(session_id, {})
        has_rendered_map = session_context.get("has_rendered_map", False)

        logger.info(
            f" VISION CHECK: session={session_id[:8] if session_id else 'None'}... "
            f"has_rendered_map={has_rendered_map} has_screenshot={has_screenshot}"
        )

        query_lower = query.lower().strip()

        analytical_patterns = [
            "what is on", "what's on", "what do you see", "what can you see",
            "describe", "analyze", "explain what", "tell me about this",
            "what city", "what river", "what lake", "what mountain", "what country",
            "what is this", "what's this", "which city", "which country",
            "is this", "is that", "are these", "are those",
            "what features", "what patterns", "what type of", "what kind of",
            "identify", "recognize", "detect",
            "how about", "what about", "and the", "also",
            "how much", "how many", "what percentage", "what area",
            "adjacent", "near", "next to", "surrounding",
            # Pin / point-sample phrasing
            "value here", "value at", "the value", "what value",
            "at this pin", "at this point", "at this location",
            "this pin", "this point", "this location", "here",
            "raster value", "pixel value", "sample",
        ]
        data_loading_patterns = [
            "show", "display", "load", "get", "fetch", "find",
            "imagery of", "data of", "data for", "imagery for",
            "satellite", "sentinel", "landsat", "hls", "modis",
        ]
        is_analytical = any(p in query_lower for p in analytical_patterns)
        wants_new_data = any(p in query_lower for p in data_loading_patterns)

        # ====================================================================
        # PIN + MAP = RASTER ANALYSIS
        # When the user has dropped a pin AND imagery is loaded, any question
        # that isn't explicitly asking for new data, isn't a climate
        # projection ("projected", "ssp", "future", "by 2050", ...), and
        # isn't a netCDF computation ("compute", "trend", "anomaly") is a
        # raster-sampling request. Route directly to vision_analysis so
        # enhanced_vision_agent can call sample_raster_value at the pin.
        # The climate / netcdf exclusion lets the dedicated pre-checks below
        # win for ExtremeWeatherAgent and netcdf_computation flows.
        # ====================================================================
        # Strong climate-projection signals only — words that unambiguously
        # describe forward-looking climate-model projections (CMIP6/NEX-GDDP).
        # Generic terms like "flood risk" or "drought risk" are intentionally
        # NOT here because they also appear in normal site/terrain analysis
        # (e.g. "Is this location suitable for a construction permit? Analyze
        # ... flood risk ..."). Those flow through the pin+map route to
        # vision_analysis terrain tools when a pin is dropped on DEM data.
        _climate_kw = (
            "projected", "projection", "ssp", "ssp126", "ssp245", "ssp370", "ssp585",
            "cmip6", "cmip", "nex-gddp", "nexgddp", "future climate",
            "by 2030", "by 2040", "by 2050", "by 2060", "by 2070", "by 2080",
            "by 2090", "by 2100", "monsoon", "extreme heat", "extreme weather",
            "climate risk", "climate outlook", "climate projection",
        )
        _compute_kw = (
            "anomaly", "trend analysis", "compute trend", "linear trend",
            "annual total",
        )
        _is_climate_like = any(k in query_lower for k in _climate_kw)
        _is_compute_like = any(k in query_lower for k in _compute_kw)

        if (
            has_pin
            and (has_rendered_map or has_screenshot)
            and not wants_new_data
            and not _is_climate_like
            and not _is_compute_like
        ):
            logger.info(
                f" PIN + MAP ROUTE: '{query}' -> vision_analysis (raster sample)"
            )
            return {
                "action_type": "vision_analysis",
                "original_query": query,
                "needs_stac_search": False,
                "needs_vision_analysis": True,
                "routing_reason": "pin_with_rendered_map_raster_sample",
            }

        if (
            (has_rendered_map or has_screenshot)
            and is_analytical
            and not wants_new_data
            and not _is_climate_like
            and not _is_compute_like
        ):
            matched_patterns = [p for p in analytical_patterns if p in query_lower]
            logger.info(
                f" GUARANTEED VISION: map+analytical (matched={matched_patterns[:3]})"
            )
            return {
                "action_type": "vision_analysis",
                "original_query": query,
                "needs_stac_search": False,
                "needs_vision_analysis": True,
                "routing_reason": "guaranteed_vision_analytical_followup",
            }

        # ====================================================================
        # DETERMINISTIC LOCATION PRE-CHECK
        # ====================================================================
        query_cleaned = query_lower.strip().rstrip("?!.")
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

        location_candidate_normalized = re.sub(r"[,;:\-]+", " ", location_candidate).strip()
        location_candidate_normalized = re.sub(r"\s+", " ", location_candidate_normalized)

        matched_location = None
        if location_candidate in LOCATION_NAMES:
            matched_location = location_candidate
        elif (
            location_candidate_normalized != location_candidate
            and location_candidate_normalized in LOCATION_NAMES
        ):
            matched_location = location_candidate_normalized

        if matched_location:
            logger.info(
                f"DETERMINISTIC LOCATION MATCH: '{matched_location}' "
                f"(LOCATION_NAMES has {len(LOCATION_NAMES)} entries)"
            )
            return {
                "action_type": "navigate_to",
                "original_query": query,
                "location": matched_location,
                "needs_stac_search": False,
                "needs_vision_analysis": False,
                "routing_reason": "deterministic_location_match",
            }

        has_collection_keyword = (
            any(
                re.search(r"\b" + re.escape(kw) + r"\b", query_lower)
                for kw in sorted(COLLECTION_KEYWORDS, key=len, reverse=True)
            )
            if COLLECTION_KEYWORDS
            else False
        )

        if has_nav_prefix and location_candidate and not has_collection_keyword:
            logger.info(
                f"NAV PREFIX ROUTE: '{location_candidate}' -> navigate_to"
            )
            return {
                "action_type": "navigate_to",
                "original_query": query,
                "location": location_candidate,
                "needs_stac_search": False,
                "needs_vision_analysis": False,
                "routing_reason": "nav_prefix_with_location",
            }

        # ====================================================================
        # CLIMATE PROJECTION PRE-CHECK
        # ====================================================================
        climate_projection_indicators = [
            "ssp", "ssp1", "ssp2", "ssp3", "ssp5",
            "ssp126", "ssp245", "ssp370", "ssp585",
            "worst.case scenario", "middle of the road",
            "projected", "projection", "projections",
            "by 2030", "by 2040", "by 2050", "by 2060",
            "by 2070", "by 2080", "by 2090", "by 2100",
            "future climate", "climate projection", "climate change projection",
            "will temperature", "will precipitation", "will rainfall",
            "increasing", "is .+ increasing",
            "cmip6", "cmip", "nex-gddp", "nexgddp", "climate model",
            "extreme heat", "extreme weather", "climate risk", "climate outlook",
            "monsoon", "monsoon precipitation", "monsoon season",
            "precipitation levels", "precipitation patterns", "rainfall patterns",
            "temperature trends", "warming trend", "heat wave",
            "flooding risk", "flood risk", "drought risk",
        ]
        is_climate_projection = any(
            re.search(r"\b" + re.escape(ind) + r"\b", query_lower)
            if "." not in ind
            else re.search(ind, query_lower)
            for ind in climate_projection_indicators
        )
        if is_climate_projection:
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
            logger.info(
                f" CLIMATE PROJECTION DETECTED: extreme_weather (location={detected_location})"
            )
            return {
                "action_type": "extreme_weather",
                "original_query": query,
                "location": detected_location,
                "needs_stac_search": False,
                "needs_vision_analysis": False,
                "routing_reason": "climate_projection_detected",
            }

        # ====================================================================
        # NETCDF COMPUTATION PRE-CHECK
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
            re.search(r"\b" + re.escape(ind) + r"\b", query_lower)
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
            logger.info(
                f" NETCDF COMPUTATION DETECTED: netcdf_computation (location={detected_location})"
            )
            return {
                "action_type": "netcdf_computation",
                "original_query": query,
                "location": detected_location,
                "needs_stac_search": False,
                "needs_vision_analysis": False,
                "routing_reason": "netcdf_computation_detected",
            }

        # ====================================================================
        # DETERMINISTIC COLLECTION PRE-CHECK
        # ====================================================================
        matched_collection = None
        for kw in sorted(COLLECTION_KEYWORDS, key=len, reverse=True):
            if re.search(r"\b" + re.escape(kw) + r"\b", query_lower):
                matched_collection = kw
                break

        if matched_collection:
            logger.info(f" DETERMINISTIC COLLECTION MATCH: '{matched_collection}'")
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
            logger.info(
                f" DETERMINISTIC ROUTE -> stac_search "
                f"(collection={matched_collection}, location={detected_location})"
            )
            return {
                "action_type": "stac_search",
                "original_query": query,
                "location": detected_location,
                "collection_hint": matched_collection,
                "use_current_location": not bool(detected_location),
                "needs_stac_search": True,
                "needs_vision_analysis": False,
                "routing_reason": "deterministic_collection_match",
            }

        # ====================================================================
        # BARE LOCATION HEURISTIC
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
        is_question = "?" in query_cleaned

        if (
            word_count <= 6
            and not has_analytical
            and not has_collection_data
            and not is_question
            and location_candidate
        ):
            logger.info(
                f"BARE LOCATION HEURISTIC: '{location_candidate}' "
                f"({word_count} words) -> navigate_to"
            )
            return {
                "action_type": "navigate_to",
                "original_query": query,
                "location": location_candidate,
                "needs_stac_search": False,
                "needs_vision_analysis": False,
                "routing_reason": "bare_location_heuristic",
            }

        # ====================================================================
        # LOAD-PATH HEURISTIC ROUTING (post-v2-handoff)
        # ====================================================================
        # Pipeline v2 owns all hierarchical routing (action_router +
        # layer2_clarifier_agent + analysis_router). This block fires only
        # when v2 has classified the turn as LOAD and handed off here for
        # STAC tile rendering. Use a deterministic best-effort heuristic;
        # no LLM call here — v2's ActionRouter already made one.
        # ====================================================================
        if has_pin or has_rendered_map or has_screenshot or has_collection_data:
            action_type = "vision_analysis"
            needs_vision = True
            needs_stac = False
            reason = "legacy_heuristic_pin_or_map"
        elif has_analytical:
            action_type = "contextual"
            needs_vision = False
            needs_stac = False
            reason = "legacy_heuristic_analytical_text"
        elif location_candidate:
            action_type = "navigate_to"
            needs_vision = False
            needs_stac = False
            reason = "legacy_heuristic_bare_location_fallback"
        else:
            action_type = "contextual"
            needs_vision = False
            needs_stac = False
            reason = "legacy_heuristic_default_contextual"

        logger.info(
            f" ROUTE -> {action_type} (legacy fallback, reason={reason})"
        )
        return {
            "action_type": action_type,
            "original_query": query,
            "location": location_candidate,
            "use_current_location": False,
            "needs_stac_search": needs_stac,
            "needs_vision_analysis": needs_vision,
            "routing_reason": reason,
        }

    # -- LLM helpers ----------------------------------------------------------

    async def _classify_query_with_llm(self, query: str) -> Dict[str, Any]:
        """[DEPRECATED] Catalog-aware classifier (collection vs location vs neither).

        Kept temporarily for backward compatibility with any external callers.
        New code should use the v2 pipeline (`pipeline.action_router.ActionRouter`
        + `agents.layer2_clarifier_agent.Layer2ClarifierAgent` +
        `pipeline.analysis_router.AnalysisRouter`) which returns a richer
        hierarchical decision (Layer-1 action + Layer-2 analyzer_kind /
        analyzer).
        """
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

### NAVIGATE_TO (has_location: true, has_collection: false)
User wants to fly to a place WITHOUT loading data.
- Bare location names: "Paris", "Grand Canyon", "Tokyo"
- Navigation verbs: "Go to", "Fly to", "Show me [place]" (no data keywords)

### CONTEXTUAL (has_location: false, has_collection: false)
User asks an educational/factual question with no place and no data type.

## CRITICAL: "Show" + data concept = STAC_SEARCH, NOT NAVIGATE_TO
- "Show me satellite images of Athens" -> STAC_SEARCH
- "Show me HLS images of Athens" -> STAC_SEARCH
- "Show me Athens" -> NAVIGATE_TO

## KNOWN LOCATIONS (sample):
{', '.join(location_samples)}
(Plus any geographic place name: cities, countries, regions, landmarks, etc.)

Respond with ONLY valid JSON (no markdown):
{{"has_collection": true/false, "collection": "matched concept or null", "has_location": true/false, "location": "place name or null"}}"""

        return await self._chat_json(classification_prompt)

    async def _extract_location_only(self, query: str) -> Dict[str, Any]:
        """Lightweight location extraction for queries that already match a vertical."""
        prompt = f"""Is there a geographic PLACE NAME in this query?

Query: "{query}"

PLACE = city, country, region, landmark, mountain, river name, etc.
NOT a place: "here", "on the map", "this area", "the current view"

Respond with ONLY valid JSON:
{{"has_location": true/false, "location": "place name" or null}}"""

        try:
            return await self._chat_json(prompt)
        except Exception as e:
            logger.error(f" Location extraction failed: {e}")
            return {"has_location": False, "location": None}


# ============================================================================
# SINGLETON
# ============================================================================

_router_agent: Optional[RouterAgent] = None


def get_router_agent() -> RouterAgent:
    global _router_agent
    if _router_agent is None:
        _router_agent = RouterAgent()
    return _router_agent
