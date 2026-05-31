"""
GEOINT Mobility Agent - Azure AI Agent Service with Function Tools

Refactored from plain Python class to Azure AI Agent Service.
Uses AgentsClient with AsyncFunctionTool/AsyncToolSet for automatic function calling.

This agent:
1. Maintains conversation memory via AgentThread (persistent threads)
2. Has access to mobility analysis tools (AsyncFunctionTool)
3. Plans and reasons about which tools to use (LLM-driven)
4. Synthesizes results into coherent mobility assessments
"""

import logging
import os
import json
from typing import Dict, Any, Optional, List
from datetime import datetime

from azure.identity import DefaultAzureCredential, get_bearer_token_provider
from cloud_config import cloud_cfg

logger = logging.getLogger(__name__)

# Agent system prompt
MOBILITY_AGENT_INSTRUCTIONS = """You are a GEOINT Mobility Analysis Agent providing structured terrain assessments for ground vehicle operations.

## MANDATORY RULES
1. You MUST call tools before responding — NEVER answer from general knowledge.
2. Use actual location names from [Location Context], not "Point A" / "Point B".
3. NEVER use the labels "GO", "SLOW-GO", or "NO-GO" — use plain language (passable / challenging / impassable).

## EFFICIENCY — MINIMIZE TOOL CALLS
- **Two-point traverse**: call **analyze_two_point_traverse** ONCE with both coordinates. This analyzes both endpoints, corridor waypoints, elevation transect, road route, and weather — all in one call.
- **Single-point radial**: call analyze_directional_mobility once (1 call total).
- Do NOT also call detect_water_bodies, detect_active_fires, analyze_slope_for_mobility, or analyze_vegetation_density — the directional tools already check all of these internally.

## Data Sources Available in Tool Results
The tools return rich data from multiple sources. USE ALL OF THEM in your report:
- **Terrain/Slope**: Copernicus DEM 30m — slope degrees, gentle/moderate/steep percentages
- **Water Bodies**: JRC Global Surface Water — permanent and seasonal water coverage
- **Active Fires**: MODIS 14A1 — fire pixel counts by confidence level
- **Vegetation**: Sentinel-2 NDVI — canopy density classification
- **Land Cover**: ESA WorldCover 10m — tree, shrub, grass, crop, built-up, bare, water, wetland
- **Corridor Waypoints**: Terrain checks at intermediate points along A→B (for two-point only)
- **Elevation Transect**: DEM profile along A→B with total ascent/descent (for two-point only)
- **Road Route**: Azure Maps driving directions — road availability, travel time, distance (for two-point only)
- **Weather**: Azure Maps current conditions — temperature, wind, precipitation, visibility (for two-point only)

## Hazard Priority (highest to lowest)
1. Active Fires  2. Water Bodies  3. Steep Slopes  4. Dense Vegetation

## Tool result labels → plain language
- "GO" → passable, clear for movement
- "SLOW-GO" → challenging, proceed with caution
- "NO-GO" → impassable, blocked

## Response Format — SITUATION REPORT

### Two-Point Traverse
**1. Area of Operations** — Origin name (coords), Destination name (coords), distance (from route.distance_miles/distance_km), bearing
**2. Weather Conditions** — Current weather at origin and destination (temperature, wind, visibility, precipitation) from weather data
**3. Road Route** — If road_route.road_route_available is true: travel time, road distance, traffic delay. If false: state no road route exists.
**4. Terrain Overview** — Land cover composition, elevation profile summary (total ascent/descent, elevation range)
**5. Corridor Assessment** — Status at each waypoint sampled between A and B, corridor overall status
**6. Endpoint Assessment** — For Origin and Destination: Terrain, Water, Fire, Vegetation, Land Cover, Assessment
**7. Hazards** — Specific data (slope degrees, water %, fire pixels, NDVI, impassable land cover classes)
**8. Overall Assessment** — passable / challenging / impassable and why
**9. Recommendations** — Actionable advice for the specific operation:
   - Road vs. off-road recommendation with reasoning
   - Preferred approach direction from data
   - Vehicle type suitability based on terrain and land cover
   - Weather-based timing considerations
   - Specific contingency planning tied to detected hazards

### Single-Point Radial
**1. Location** — name, coords, 5-mile radius
**2. Terrain Overview** — Land cover and terrain character
**3. Directional Assessment** — N/S/E/W: Terrain, Water, Fire, Vegetation, Land Cover, Assessment
**4. Hazards** — per-direction specifics
**5. Best Routes** — most favorable directions
**6. Recommendations**

## CRITICAL: Summary Requirement
ALWAYS conclude with a **Summary** section that gives a clear, direct answer to the user's specific question, grounded in the data returned by your tools. For example:
- If asked "can vehicles move south from this location?", end with an explicit passable/challenging/impassable verdict citing slope degrees, water %, or fire detections from tool results
- If asked about best route, state the recommended direction(s) with supporting data values
- If asked about a specific hazard, quantify it using tool output (e.g., "12% water coverage", "slope 18°")
- Never end with generic advice — always tie your conclusion to actual tool data

Keep responses concise with real data values from tools.
"""


class MobilityAgentSession:
    """Represents a conversation session with the mobility agent."""

    def __init__(self, session_id: str, latitude: float, longitude: float, thread_id: str):
        self.session_id = session_id
        self.latitude = latitude
        self.longitude = longitude
        self.thread_id = thread_id
        self.created_at = datetime.utcnow()
        self.last_activity = datetime.utcnow()
        self.analysis_cache: Dict[str, Any] = {}
        self.message_count = 0

    def update_location(self, latitude: float, longitude: float):
        self.latitude = latitude
        self.longitude = longitude
        self.last_activity = datetime.utcnow()


class GeointMobilityAgent:
    """
    Azure AI Agent Service-based mobility analysis agent with:
    - Persistent threads for multi-turn conversation
    - AsyncFunctionTool calling for raster analysis
    - Automatic function execution via AsyncToolSet
    """

    def __init__(self):
        self.sessions: Dict[str, MobilityAgentSession] = {}
        self._agents_client = None
        self._agent_id: Optional[str] = None
        self._initialized = False
        logger.info("GeointMobilityAgent created (will initialize on first use)")

    async def _ensure_initialized(self):
        """Initialize with retry logic for transient Agent Service failures."""
        if self._initialized:
            return

        import asyncio as _aio
        max_attempts = 3
        for attempt in range(max_attempts):
            try:
                await self._do_initialize()
                return
            except Exception as e:
                if attempt < max_attempts - 1:
                    wait = 2 ** attempt
                    logger.warning(f"GeointMobilityAgent init attempt {attempt + 1} failed: {e} — retrying in {wait}s")
                    await _aio.sleep(wait)
                else:
                    logger.error(f"GeointMobilityAgent init failed after {max_attempts} attempts: {e}")
                    raise

    async def _do_initialize(self):
        """Actual initialization logic (called by _ensure_initialized with retries)."""

        logger.info("Initializing GeointMobilityAgent with Azure AI Agent Service...")

        # Prefer AI Foundry project endpoint (services.ai.azure.com) for Agent Service API
        # Falls back to AZURE_OPENAI_ENDPOINT (cognitiveservices.azure.com) if not set
        endpoint = os.getenv("AZURE_AI_PROJECT_ENDPOINT") or os.getenv("AZURE_OPENAI_ENDPOINT")
        deployment = os.getenv("AZURE_OPENAI_DEPLOYMENT_NAME", "gpt-5")

        if not endpoint:
            raise ValueError("AZURE_AI_PROJECT_ENDPOINT or AZURE_OPENAI_ENDPOINT environment variable is required")

        logger.info(f"GeointMobilityAgent using endpoint: {endpoint}")

        credential = DefaultAzureCredential()

        from azure.ai.agents.aio import AgentsClient
        from azure.ai.agents.models import AsyncFunctionTool, AsyncToolSet

        self._agents_client = AgentsClient(
            endpoint=endpoint,
            credential=credential,
        )

        from geoint.mobility_tools import create_mobility_functions
        mobility_functions = create_mobility_functions()

        functions = AsyncFunctionTool(mobility_functions)
        toolset = AsyncToolSet()
        toolset.add(functions)
        self._agents_client.enable_auto_function_calls(toolset)

        agent = await self._agents_client.create_agent(
            model=deployment,
            name="GeointMobilityAnalyst",
            instructions=MOBILITY_AGENT_INSTRUCTIONS,
            toolset=toolset,
        )
        self._agent_id = agent.id

        self._initialized = True
        logger.info(f"GeointMobilityAgent initialized: agent_id={agent.id}, model={deployment}")

    async def _get_or_create_session(self, session_id: str, latitude: float, longitude: float) -> MobilityAgentSession:
        """Get existing session or create a new one with a new thread."""
        if session_id in self.sessions:
            session = self.sessions[session_id]
            session.update_location(latitude, longitude)
            return session

        thread = await self._agents_client.threads.create()
        session = MobilityAgentSession(session_id, latitude, longitude, thread.id)
        self.sessions[session_id] = session
        logger.info(f"Created new mobility session: {session_id} -> thread: {thread.id}")
        return session

    def cleanup_old_sessions(self, max_age_minutes: int = 60):
        now = datetime.utcnow()
        expired = [
            sid for sid, s in self.sessions.items()
            if (now - s.last_activity).total_seconds() > max_age_minutes * 60
        ]
        for sid in expired:
            del self.sessions[sid]

    async def _analyze_screenshot_direct(self, screenshot_base64: str, latitude: float, longitude: float) -> Optional[str]:
        """Analyze a screenshot using GPT-5 Vision — infrastructure detection only.
        
        With raster data now covering terrain, water, fire, vegetation, land cover,
        elevation, and weather, vision is used ONLY to detect man-made infrastructure
        (roads, bridges, buildings, airstrips) that raster data cannot identify.
        Uses low detail and tight token budget to stay under 8s.
        """
        try:
            from openai import AsyncAzureOpenAI
            credential = DefaultAzureCredential()
            token_provider = get_bearer_token_provider(credential, cloud_cfg.cognitive_services_scope)

            client = AsyncAzureOpenAI(
                azure_ad_token_provider=token_provider,
                api_version=os.getenv("AZURE_OPENAI_API_VERSION", "2025-01-01-preview"),
                azure_endpoint=os.getenv("AZURE_OPENAI_ENDPOINT"),
                timeout=15.0
            )

            clean_base64 = screenshot_base64
            if screenshot_base64.startswith('data:image'):
                clean_base64 = screenshot_base64.split(',', 1)[1]

            response = await client.chat.completions.create(
                model=os.getenv("AZURE_OPENAI_DEPLOYMENT_NAME", "gpt-5"),
                messages=[
                    {"role": "system", "content": "You identify infrastructure in satellite imagery. Respond in JSON only."},
                    {"role": "user", "content": [
                        {"type": "text", "text": (
                            f"Location: ({latitude:.4f}, {longitude:.4f}). "
                            "List visible man-made infrastructure ONLY: roads, bridges, buildings, "
                            "airstrips, rail lines, dams. Respond as JSON: "
                            '{"roads": bool, "bridges": bool, "buildings": bool, '
                            '"airstrips": bool, "other_infrastructure": ["..."], '
                            '"summary": "one sentence"}'
                        )},
                        {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{clean_base64}", "detail": "low"}}
                    ]}
                ],
                max_completion_tokens=300
            )
            analysis = response.choices[0].message.content
            logger.info(f"Mobility vision (infrastructure) complete: {len(analysis)} chars")
            return analysis
        except Exception as e:
            logger.error(f"Vision analysis failed: {e}")
            return None

    async def analyze_mobility(
        self,
        latitude: float,
        longitude: float,
        user_context: Optional[str] = None,
        include_vision_analysis: bool = True,
        screenshot_base64: Optional[str] = None,
        session_id: Optional[str] = None,
        latitude_b: Optional[float] = None,
        longitude_b: Optional[float] = None,
    ) -> Dict[str, Any]:
        """
        Perform mobility analysis via the Agent Service.
        Drop-in replacement for the old analyze_mobility interface.
        """
        import uuid
        await self._ensure_initialized()

        if not session_id:
            session_id = f"mobility_{uuid.uuid4().hex[:8]}"

        session = await self._get_or_create_session(session_id, latitude, longitude)

        # ── Run reverse geocode + vision IN PARALLEL to cut ~10-15s ──
        import asyncio
        from semantic_translator import geocoding_plugin

        async def _reverse_geocode(lat: float, lon: float) -> str:
            """Reverse geocode and build a display name."""
            fallback = f"Location ({lat:.4f}, {lon:.4f})"
            try:
                rg = await geocoding_plugin.azure_maps_reverse_geocode(lat, lon)
                data = json.loads(rg)
                if not data.get("error"):
                    n = data.get("name", "")
                    r = data.get("region", "")
                    c = data.get("country", "")
                    parts = [p for p in [n, r, c] if p and p != n]
                    return f"{n}, {', '.join(parts)}" if n and parts else n or fallback
            except Exception:
                pass
            return fallback

        async def _vision_analysis() -> Optional[str]:
            """Run vision analysis with timeout gate."""
            if not (include_vision_analysis and screenshot_base64 and len(screenshot_base64) > 5000):
                return None
            try:
                result = await asyncio.wait_for(
                    self._analyze_screenshot_direct(screenshot_base64, latitude, longitude),
                    timeout=15.0  # Hard cap — don't waste >15s on vision
                )
                if result and len(result.strip()) > 0:
                    return result
                logger.info("Vision analysis returned empty — skipping")
            except asyncio.TimeoutError:
                logger.warning("Vision analysis timed out (15s cap) — skipping")
            except Exception as e:
                logger.warning(f"Vision analysis failed: {e} — skipping")
            return None

        # Build list of concurrent tasks
        tasks = [_reverse_geocode(latitude, longitude), _vision_analysis()]
        has_two_points = latitude_b is not None and longitude_b is not None
        if has_two_points:
            tasks.append(_reverse_geocode(latitude_b, longitude_b))

        # Execute all in parallel — saves 5-15s vs sequential
        results = await asyncio.gather(*tasks, return_exceptions=True)
        location_name = results[0] if isinstance(results[0], str) else f"Location ({latitude:.4f}, {longitude:.4f})"
        visual_analysis = results[1] if isinstance(results[1], str) else None
        location_name_b = (results[2] if len(results) > 2 and isinstance(results[2], str)
                           else f"Location ({latitude_b:.4f}, {longitude_b:.4f})" if has_two_points else None)

        # ── Build context message ──
        context_message = f"""[Location Context]
- Location: {location_name}
- Point A (Start): ({latitude:.6f}, {longitude:.6f})"""

        if has_two_points:
            context_message += f"""
- Point B (Destination): {location_name_b} ({latitude_b:.6f}, {longitude_b:.6f})
- Analysis mode: Two-point traverse (A -> B)"""
        else:
            context_message += f"""
- Analysis radius: 5 miles"""

        context_message += f"""
- Session messages: {session.message_count}"""

        if visual_analysis:
            context_message += f"\n\n[Infrastructure Detection from Satellite Imagery]\n{visual_analysis}"

        query = user_context or (
            f"Analyze terrain traversability from Point A to Point B. Provide a structured situation report with hazards, route assessment, and recommendations."
            if latitude_b is not None and longitude_b is not None
            else "Analyze terrain mobility at this location in all four directions. Provide a structured situation report with hazards, assessments, and recommendations."
        )
        context_message += f"\n\n[User Question]\n{query}"

        # Force tool usage — explicit instruction to call satellite analysis tools
        if latitude_b is not None and longitude_b is not None:
            context_message += (
                f"\n\n[INSTRUCTIONS]\n"
                f"Call analyze_two_point_traverse ONCE with "
                f"latitude_a={latitude}, longitude_a={longitude}, "
                f"latitude_b={latitude_b}, longitude_b={longitude_b}. "
                f"That is 1 tool call total — it analyzes both endpoints, corridor waypoints, "
                f"elevation transect, road route, and weather in parallel internally. "
                f"Do NOT call analyze_directional_mobility or individual tools. "
                f"Use route.distance_miles and route.bearing_degrees from the result. "
                f"Use road_route, weather, corridor, and elevation_transect sections in your report. "
                f"Base your response ONLY on tool results."
            )
        else:
            context_message += (
                f"\n\n[INSTRUCTIONS]\n"
                f"Call analyze_directional_mobility at ({latitude}, {longitude}). "
                f"That is 1 tool call — do NOT call individual tools. "
                f"Base your response ONLY on tool results."
            )

        _retryable_patterns = ["404", "Resource not found", "invalid_engine_error",
                               "Failed to resolve model", "InternalServerError",
                               "Unable to get resource", "DeploymentNotFound", "server_error"]

        max_retries = 3
        for attempt in range(max_retries):
            try:
                # Re-create thread if we had to re-initialize (stale session)
                if attempt > 0:
                    session = await self._get_or_create_session(f"{session_id}_retry{attempt}", latitude, longitude)

                await self._agents_client.messages.create(
                    thread_id=session.thread_id,
                    role="user",
                    content=context_message,
                )

                run = await self._agents_client.runs.create_and_process(
                    thread_id=session.thread_id,
                    agent_id=self._agent_id,
                )

                if run.status == "failed":
                    error_info = run.last_error
                    err_str = str(error_info)
                    is_retryable = any(p in err_str for p in _retryable_patterns)
                    logger.error(f"Mobility agent run failed: {error_info}")
                    if is_retryable and attempt < max_retries - 1:
                        logger.warning(f"Mobility run failed (retryable), attempt {attempt + 1}: {error_info}")
                        self._initialized = False
                        self._agent_id = None
                        self._agents_client = None
                        self.sessions.clear()
                        await self._ensure_initialized()
                        continue
                    return {
                        "agent": "geoint_mobility",
                        "response": f"Mobility analysis error: {error_info}",
                        "error": str(error_info),
                        "session_id": session_id
                    }

                from azure.ai.agents.models import ListSortOrder
                messages_iterable = self._agents_client.messages.list(
                    thread_id=session.thread_id,
                    order=ListSortOrder.DESCENDING,
                )

                response_content = ""
                tool_calls = []

                async for msg in messages_iterable:
                    if msg.run_id == run.id and msg.role == "assistant":
                        if msg.text_messages:
                            response_content = msg.text_messages[-1].text.value
                        break

                try:
                    run_steps_iterable = self._agents_client.run_steps.list(
                        thread_id=session.thread_id, run_id=run.id)
                    async for step in run_steps_iterable:
                        if hasattr(step, 'step_details') and hasattr(step.step_details, 'tool_calls'):
                            for tc in step.step_details.tool_calls:
                                if hasattr(tc, 'function'):
                                    tool_calls.append({"tool": tc.function.name})
                                    logger.info(f"Mobility agent called tool: {tc.function.name}")
                except Exception as e:
                    logger.warning(f"Failed to retrieve run steps: {e}")

                if not tool_calls:
                    logger.warning("Mobility agent responded WITHOUT calling any tools — response may be generic knowledge")

                session.message_count += 2
                session.last_activity = datetime.utcnow()

                return {
                    "agent": "geoint_mobility",
                    "response": response_content,
                    "summary": response_content,
                    "tool_calls": tool_calls,
                    "session_id": session_id,
                    "location": {"latitude": latitude, "longitude": longitude},
                    "destination": {"latitude": latitude_b, "longitude": longitude_b} if latitude_b is not None and longitude_b is not None else None,
                    "radius_miles": 5,
                    "timestamp": datetime.utcnow().isoformat(),
                    "data_sources": [tc["tool"] for tc in tool_calls]
                }

            except Exception as e:
                error_str = str(e)
                is_retryable = any(p in error_str for p in _retryable_patterns)
                if is_retryable and attempt < max_retries - 1:
                    logger.warning(f"Mobility agent error (retryable), re-initializing... (attempt {attempt + 1}): {e}")
                    self._initialized = False
                    self._agent_id = None
                    self._agents_client = None
                    self.sessions.clear()
                    try:
                        await self._ensure_initialized()
                        continue  # Retry with fresh agent
                    except Exception as reinit_err:
                        logger.error(f"Mobility agent re-initialization failed: {reinit_err}")
                        return {
                            "agent": "geoint_mobility",
                            "response": f"Error: Agent service unavailable - {str(reinit_err)}",
                            "error": str(reinit_err),
                            "session_id": session_id
                        }

                logger.error(f"Mobility agent error: {e}")
                import traceback
                logger.error(traceback.format_exc())
                return {
                    "agent": "geoint_mobility",
                    "response": f"Mobility analysis error: {str(e)}",
                    "error": str(e),
                    "session_id": session_id
                }

    async def chat(self, session_id: str, user_message: str, latitude: float, longitude: float,
                   screenshot_base64: Optional[str] = None) -> Dict[str, Any]:
        """Multi-turn chat interface (same pattern as terrain agent)."""
        return await self.analyze_mobility(
            latitude=latitude, longitude=longitude,
            user_context=user_message,
            include_vision_analysis=bool(screenshot_base64),
            screenshot_base64=screenshot_base64,
            session_id=session_id
        )

    async def cleanup(self):
        if self._agents_client and self._agent_id:
            try:
                await self._agents_client.delete_agent(self._agent_id)
            except Exception:
                pass


# Singleton
_mobility_agent: Optional[GeointMobilityAgent] = None


def get_mobility_agent() -> GeointMobilityAgent:
    global _mobility_agent
    if _mobility_agent is None:
        _mobility_agent = GeointMobilityAgent()
    return _mobility_agent
