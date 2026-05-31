"""
GEOINT Comparison Agent - Azure AI Agent Service with Function Tools

Refactored from plain Python class to Azure AI Agent Service.
Uses AgentsClient with AsyncFunctionTool/AsyncToolSet for automatic function calling.

This agent:
1. Maintains conversation memory via AgentThread (persistent threads)
2. Has access to temporal comparison tools (AsyncFunctionTool)
3. Plans and reasons about which tools to use (LLM-driven)
4. Synthesizes results into coherent before/after analysis reports
"""

import logging
import os
import json
from typing import Dict, Any, Optional, List
from datetime import datetime

from azure.identity import DefaultAzureCredential, get_bearer_token_provider
from cloud_config import cloud_cfg

logger = logging.getLogger(__name__)

COMPARISON_AGENT_INSTRUCTIONS = """You are a GEOINT Temporal Comparison Agent specializing in before/after satellite imagery analysis for change detection.

Your role is to compare satellite imagery across two time periods and analyze what has changed at a given location.

## MANDATORY RULE — ALWAYS CALL TOOLS FIRST
You MUST call **compare_temporal_imagery** (or **search_stac_for_period**) BEFORE making ANY statement about data availability.
NEVER say "no data", "unavailable", "0 scenes", or suggest alternative datasets without first executing a tool call.
Your training data does NOT reflect real-time STAC catalog contents — only the tools can determine what imagery exists.

## Available Tools:

- **compare_temporal_imagery**: Compare satellite imagery between two time periods. Executes dual STAC queries and returns before/after tile URLs for map display with scene counts and metadata.
- **search_stac_for_period**: Search the STAC catalog for available imagery in a specific time period and location. Returns matching scenes with dates and cloud cover.
- **analyze_comparison_imagery**: Analyze visual differences between before and after imagery using AI vision. Call this AFTER compare_temporal_imagery to provide an AI-powered description of changes.

## Analysis Types Supported (use these as the analysis_type parameter):
- **surface reflectance**: Overall reflectance changes (default)
- **vegetation** or **ndvi**: Vegetation health and cover changes
- **water** or **flood**: Water body extent changes
- **snow**: Snow cover changes
- **fire**: Fire/wildfire activity (MODIS thermal detection)
- **sar** or **radar**: SAR radar imagery (Sentinel-1, works day/night/through clouds)

## Collections Available:
- sentinel-2-l2a / sentinel / sentinel-2: Optical imagery (10m, cloud-filtered)
- landsat-c2-l2 / landsat: Landsat optical (30m)
- hls2-l30 / hls: Harmonized Landsat Sentinel (30m)
- jrc-gsw / water: Water occurrence
- modis-10A1-061 / snow: Snow cover
- modis-14A1-061 / fire / modis fire / wildfire: Fire detection (MODIS thermal)
- sentinel-1-rtc / sentinel-1 / sar / radar: SAR radar imagery (works through clouds)
- sentinel-1-grd: SAR Ground Range Detected

## IMPORTANT - analysis_type Mapping:
When users mention "MODIS fire", "fire activity", "wildfire", or "burned area", use analysis_type="fire".
When users mention "Sentinel-1", "SAR", or "radar", use analysis_type="sar".
Always pass one of: surface reflectance, vegetation, ndvi, water, flood, snow, fire, sar, radar, or a direct collection ID.

## CRITICAL: Location Handling
When coordinates are provided in the [Location Context] section, pass them directly as the `location` parameter.
For example, if context says "Coordinates: (39.752679, -121.600299)", use location="39.752679, -121.600299".
The tool accepts both named locations AND coordinate strings.

## CRITICAL: Parsing User Queries
Users will ask questions like:
- "Compare HLS imagery of Beirut from July 2020 and September 2020"
- "Show Sentinel-2 imagery of Paradise, CA from October 2018 and January 2019"
- "Compare vegetation in the Amazon from January 2019 and January 2023"

Extract: location, before_period, after_period, collection/analysis_type from the query.

## Workflow:
1. Call **compare_temporal_imagery** with location, before_period, after_period, and analysis_type
2. If tile_urls are returned for both periods, call **analyze_comparison_imagery** with those URLs to provide AI analysis of differences
3. Combine the results into a comprehensive response

## Response Format:
1. **Location**: Name and coordinates
2. **Time Periods**: Before and after dates with available scene counts
3. **Change Analysis**: AI-powered observations about what changed
4. **Instructions**: Remind user to use the BEFORE/AFTER toggle buttons on the map
5. **Summary**: ALWAYS conclude with a **Summary** section that gives a clear, direct answer to the user's specific question, grounded in the data returned by your tools. For example:
   - If asked "did vegetation recover after the fire?", end with an explicit yes/no citing scene counts, NDVI changes, or visual differences from tool results
   - If asked about flood extent changes, state the magnitude and direction of change with data from tool output
   - If asked to compare before and after, summarize the key difference in one concrete, data-backed statement
   - Never end with generic observations — always tie your conclusion to actual tool data

## Visual Context
If a [Visual Analysis of Current Map View] section is provided, use it to:
- Reference visible landmarks, urban areas, coastlines, or infrastructure when describing changes
- Ground your change analysis in what is visible on the map
- Note any features that may be relevant to the comparison (e.g., flood-prone areas, burned regions)

Keep responses factual and concise.
"""


class ComparisonSession:
    """Represents a conversation session with the comparison agent."""

    def __init__(self, session_id: str, thread_id: str):
        self.session_id = session_id
        self.thread_id = thread_id
        self.created_at = datetime.utcnow()
        self.last_activity = datetime.utcnow()
        self.message_count = 0


class ComparisonAgent:
    """
    Azure AI Agent Service-based temporal comparison agent.
    """

    def __init__(self):
        self.sessions: Dict[str, ComparisonSession] = {}
        self._agents_client = None
        self._agent_id: Optional[str] = None
        self._initialized = False
        self.name = "geoint_comparison"
        logger.info("ComparisonAgent created (will initialize on first use)")

    async def _ensure_initialized(self):
        """Initialize with retry logic for transient Agent Service failures."""
        if self._initialized:
            return

        import asyncio
        max_attempts = 3
        for attempt in range(max_attempts):
            try:
                await self._do_initialize()
                return
            except Exception as e:
                if attempt < max_attempts - 1:
                    wait = 2 ** attempt
                    logger.warning(f"ComparisonAgent init attempt {attempt + 1} failed: {e} — retrying in {wait}s")
                    await asyncio.sleep(wait)
                else:
                    logger.error(f"ComparisonAgent init failed after {max_attempts} attempts: {e}")
                    raise

    async def _do_initialize(self):
        """Actual initialization logic (called by _ensure_initialized with retries)."""
        logger.info("Initializing ComparisonAgent with Azure AI Agent Service...")

        # Prefer AI Foundry project endpoint (services.ai.azure.com) for Agent Service API
        # Falls back to AZURE_OPENAI_ENDPOINT (cognitiveservices.azure.com) if not set
        endpoint = os.getenv("AZURE_AI_PROJECT_ENDPOINT") or os.getenv("AZURE_OPENAI_ENDPOINT")
        deployment = os.getenv("AZURE_OPENAI_DEPLOYMENT_NAME", "gpt-5")

        if not endpoint:
            raise ValueError("AZURE_AI_PROJECT_ENDPOINT or AZURE_OPENAI_ENDPOINT environment variable is required")

        logger.info(f"ComparisonAgent using endpoint: {endpoint}")

        credential = DefaultAzureCredential()

        from azure.ai.agents.aio import AgentsClient
        from azure.ai.agents.models import AsyncFunctionTool, AsyncToolSet

        self._agents_client = AgentsClient(
            endpoint=endpoint,
            credential=credential,
        )

        from geoint.comparison_tools import create_comparison_functions
        comparison_functions = create_comparison_functions()

        functions = AsyncFunctionTool(comparison_functions)
        toolset = AsyncToolSet()
        toolset.add(functions)
        self._agents_client.enable_auto_function_calls(toolset)

        agent = await self._agents_client.create_agent(
            model=deployment,
            name="GeointComparisonAnalyst",
            instructions=COMPARISON_AGENT_INSTRUCTIONS,
            toolset=toolset,
        )
        self._agent_id = agent.id

        self._initialized = True
        logger.info(f"ComparisonAgent initialized: agent_id={agent.id}, model={deployment}")

    async def _get_or_create_session(self, session_id: str) -> ComparisonSession:
        if session_id in self.sessions:
            session = self.sessions[session_id]
            session.last_activity = datetime.utcnow()
            return session

        thread = await self._agents_client.threads.create()
        session = ComparisonSession(session_id, thread.id)
        self.sessions[session_id] = session
        logger.info(f"Created new comparison session: {session_id} -> thread: {thread.id}")
        return session

    async def _analyze_screenshot_direct(
        self,
        screenshot_base64: str,
        latitude: float,
        longitude: float
    ) -> Optional[str]:
        """Pre-analyze a map screenshot using GPT-5 Vision for comparison context."""
        try:
            from openai import AsyncAzureOpenAI

            logger.info(f"Running visual analysis for comparison context at ({latitude:.4f}, {longitude:.4f})")

            credential = DefaultAzureCredential()
            token_provider = get_bearer_token_provider(
                credential, cloud_cfg.cognitive_services_scope
            )

            client = AsyncAzureOpenAI(
                azure_ad_token_provider=token_provider,
                api_version=os.getenv("AZURE_OPENAI_API_VERSION", "2025-01-01-preview"),
                azure_endpoint=os.getenv("AZURE_OPENAI_ENDPOINT"),
                timeout=120.0
            )

            clean_base64 = screenshot_base64
            if screenshot_base64.startswith('data:image'):
                clean_base64 = screenshot_base64.split(',', 1)[1]

            vision_prompt = f"""Analyze this satellite/map image for temporal comparison context.

Location: Approximately ({latitude:.4f}, {longitude:.4f})

Identify:
1. **Land Use**: Urban development, agricultural areas, natural features
2. **Water Features**: Rivers, lakes, coastline, potential flood zones
3. **Vegetation**: Forest, grassland, crop patterns
4. **Infrastructure**: Roads, buildings, airports, ports
5. **Change Indicators**: Any visible signs of recent change, construction, damage, or environmental shifts

Be specific and concise."""

            response = await client.chat.completions.create(
                model=os.getenv("AZURE_OPENAI_DEPLOYMENT_NAME", "gpt-5"),
                messages=[
                    {
                        "role": "system",
                        "content": "You are an expert geospatial analyst specializing in change detection and temporal comparison."
                    },
                    {
                        "role": "user",
                        "content": [
                            {"type": "text", "text": vision_prompt},
                            {
                                "type": "image_url",
                                "image_url": {"url": f"data:image/jpeg;base64,{clean_base64}", "detail": "high"}
                            }
                        ]
                    }
                ],
                max_completion_tokens=1500
            )

            analysis = response.choices[0].message.content
            logger.info(f"Comparison vision analysis complete: {len(analysis)} chars")
            return analysis

        except Exception as e:
            logger.error(f"Comparison vision analysis failed: {e}")
            return f"Visual analysis unavailable: {str(e)}"

    async def handle_query(
        self,
        user_query: str,
        latitude: Optional[float] = None,
        longitude: Optional[float] = None,
        session_id: Optional[str] = None,
        screenshot_base64: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Main entry point for comparison queries.
        Drop-in replacement for the old ComparisonAgent.handle_query interface.
        """
        import uuid

        # Handle empty / greeting queries
        if not user_query or user_query.strip().lower() in ["", "hi", "hello", "comparison", "start"]:
            return {
                "status": "prompt",
                "message": "Please specify the location, date range, and what you would like to compare.\n\nExample: *How did Miami Beach surface reflectance change between 01/2020 and 01/2025?*",
                "type": "comparison"
            }

        await self._ensure_initialized()

        if not session_id:
            session_id = f"comparison_{uuid.uuid4().hex[:8]}"

        session = await self._get_or_create_session(session_id)

        # Pre-analyze screenshot if provided (15s timeout gate)
        visual_analysis = None
        if screenshot_base64 and latitude is not None and longitude is not None:
            import asyncio
            try:
                result = await asyncio.wait_for(
                    self._analyze_screenshot_direct(screenshot_base64, latitude, longitude),
                    timeout=15.0
                )
                if result and len(result.strip()) > 0:
                    visual_analysis = result
                else:
                    logger.info("Vision analysis returned empty — skipping")
            except asyncio.TimeoutError:
                logger.warning("Vision analysis timed out (15s cap) — skipping")
            except Exception as e:
                logger.warning(f"Vision analysis failed: {e} — skipping")
            logger.info(f"Pre-analyzed screenshot for comparison: {len(visual_analysis) if visual_analysis else 0} chars")

        context_message = f"[User Question]\n{user_query}"
        if latitude is not None and longitude is not None:
            context_message = f"[Location Context]\n- Coordinates: ({latitude:.6f}, {longitude:.6f})\n\n{context_message}"

        if visual_analysis:
            context_message += f"\n\n[Visual Analysis of Current Map View]\n{visual_analysis}"

        _retryable_patterns = ["404", "Resource not found", "invalid_engine_error",
                               "Failed to resolve model", "InternalServerError",
                               "Unable to get resource", "DeploymentNotFound",
                               "server_error", "something went wrong"]

        max_retries = 3
        for attempt in range(max_retries):
            try:
                # Re-create thread if we had to re-initialize (stale session)
                if attempt > 0:
                    session = await self._get_or_create_session(f"{session_id}_retry{attempt}")

                # Reset tool output capture before the agent run
                from geoint.comparison_tools import reset_comparison_capture, get_last_comparison_result
                reset_comparison_capture()

                await self._agents_client.messages.create(
                    thread_id=session.thread_id, role="user", content=context_message)

                run = await self._agents_client.runs.create_and_process(
                    thread_id=session.thread_id, agent_id=self._agent_id)

                if run.status == "failed":
                    err_str = str(run.last_error)
                    is_retryable = any(p in err_str for p in _retryable_patterns)
                    if is_retryable and attempt < max_retries - 1:
                        logger.warning(f"Comparison run failed (retryable), attempt {attempt + 1}: {run.last_error}")
                        self._initialized = False
                        self._agent_id = None
                        self._agents_client = None
                        self.sessions.clear()
                        await self._ensure_initialized()
                        continue
                    return {"status": "error", "message": f"Comparison analysis error: {run.last_error}"}

                from azure.ai.agents.models import ListSortOrder
                messages_iterable = self._agents_client.messages.list(
                    thread_id=session.thread_id, order=ListSortOrder.DESCENDING)

                response_content = ""
                tool_calls = []
                comparison_data = None

                async for msg in messages_iterable:
                    if msg.run_id == run.id and msg.role == "assistant":
                        if msg.text_messages:
                            response_content = msg.text_messages[-1].text.value
                        break

                # Extract tool outputs to find comparison data (tile URLs, etc.)
                try:
                    run_steps_iterable = self._agents_client.run_steps.list(
                        thread_id=session.thread_id, run_id=run.id)
                    async for step in run_steps_iterable:
                        if hasattr(step, 'step_details') and hasattr(step.step_details, 'tool_calls'):
                            for tc in step.step_details.tool_calls:
                                if hasattr(tc, 'function'):
                                    tool_calls.append({"tool": tc.function.name})
                                    # Parse comparison tool output for tile URLs
                                    if tc.function.name == "compare_temporal_imagery" and tc.function.output:
                                        try:
                                            comparison_data = json.loads(tc.function.output)
                                        except Exception:
                                            pass
                except Exception as e:
                    logger.warning(f"Failed to extract tool outputs from run_steps: {e}")

                # Fallback: use module-level captured result if run_steps extraction failed
                if not comparison_data:
                    captured = get_last_comparison_result()
                    if captured and captured.get("status") == "success":
                        logger.info("Using captured tool output (run_steps extraction returned None)")
                        comparison_data = captured

                session.message_count += 2
                session.last_activity = datetime.utcnow()

                result = {
                    "status": "success",
                    "type": "comparison",
                    "analysis": response_content,
                    "tool_calls": tool_calls,
                    "session_id": session_id,
                    "timestamp": datetime.utcnow().isoformat()
                }

                # Merge comparison data if available (tile URLs, bbox, etc.)
                if comparison_data and comparison_data.get("status") == "success":
                    result.update({
                        "location": comparison_data.get("location"),
                        "bbox": comparison_data.get("bbox"),
                        "center": comparison_data.get("center"),
                        "before": comparison_data.get("before"),
                        "after": comparison_data.get("after"),
                        "collection": comparison_data.get("collection"),
                    })

                return result

            except Exception as e:
                error_str = str(e)
                is_retryable = any(p in error_str for p in _retryable_patterns)
                if is_retryable and attempt < max_retries - 1:
                    logger.warning(f"Comparison agent error (retryable), re-initializing... (attempt {attempt + 1}): {e}")
                    self._initialized = False
                    self._agent_id = None
                    self._agents_client = None
                    self.sessions.clear()
                    try:
                        await self._ensure_initialized()
                        continue  # Retry with fresh agent
                    except Exception as reinit_err:
                        logger.error(f"Comparison agent re-initialization failed: {reinit_err}")
                        return {"status": "error", "message": f"Agent service unavailable - {str(reinit_err)}"}

                logger.error(f"Comparison agent error: {e}")
                import traceback
                logger.error(traceback.format_exc())
                return {"status": "error", "message": f"Comparison analysis failed: {str(e)}"}

    async def chat(self, session_id: str, user_message: str,
                   latitude: Optional[float] = None, longitude: Optional[float] = None,
                   screenshot_base64: Optional[str] = None) -> Dict[str, Any]:
        return await self.handle_query(
            user_query=user_message,
            latitude=latitude, longitude=longitude,
            session_id=session_id,
            screenshot_base64=screenshot_base64
        )

    async def cleanup(self):
        if self._agents_client and self._agent_id:
            try:
                await self._agents_client.delete_agent(self._agent_id)
            except Exception:
                pass


# Singleton
_comparison_agent: Optional[ComparisonAgent] = None


def get_comparison_agent() -> ComparisonAgent:
    global _comparison_agent
    if _comparison_agent is None:
        _comparison_agent = ComparisonAgent()
    return _comparison_agent
