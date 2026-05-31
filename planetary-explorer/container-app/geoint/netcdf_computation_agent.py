"""
NetCDF Computation Agent — Azure AI Agent Service with Advanced Climate Analysis Tools

Extends the extreme weather agent with tools for time-series extraction, area statistics,
anomaly detection, trend analysis, and a safe expression calculator.

Uses the same Azure AI Agent Service pattern (AgentsClient, AsyncFunctionTool, ToolSet)
so it integrates cleanly into the existing pipeline.
"""

import json
import logging
import os
from datetime import datetime
from typing import Any, Dict, List, Optional

from azure.identity import DefaultAzureCredential
from cloud_config import cloud_cfg

logger = logging.getLogger(__name__)

NETCDF_COMPUTATION_AGENT_INSTRUCTIONS = """You are a Climate Computation Agent with advanced analysis capabilities.
You can extract time-series data, compute spatial statistics over areas, detect anomalies between time periods, compute long-term trends, and run derived calculations.

## Available Tools

### Discovery
- **discover_datasets**: Find which datasets and variables are available for a topic. Call this FIRST if unsure which variable to use.

### Point Sampling (inherited from climate agent)
- **get_temperature_projection**: Point temperature (°F) — max, min, mean
- **get_precipitation_projection**: Point precipitation (mm/day) with multi-model ensemble
- **get_wind_projection**: Wind speed (m/s) with Beaufort scale
- **get_humidity_projection**: Relative and specific humidity
- **get_radiation_projection**: Solar and longwave radiation (W/m²)
- **get_climate_overview**: All variables at once (fastest for general queries)
- **compare_climate_scenarios**: SSP2-4.5 vs SSP5-8.5 comparison

### Time-Series
- **sample_timeseries**: Extract monthly or seasonal time series for a variable at a point for a given year. Returns per-period mean/max/min. Use for seasonal patterns ("when is the hottest month?", "monsoon timing").

### Area Statistics
- **sample_area_stats**: Compute spatial statistics (mean, min, max, std, percentiles) across a bounding box. Use when the question is about a region, state, or metro area rather than a single point.

### Change Analysis
- **compute_anomaly**: Compute the change between a baseline year and a target year. Use for "how much will X increase by 2050?" questions. Returns absolute and percent change.
- **compute_trend**: Fit a linear trend across multiple decades. Use for "is it getting hotter?", "long-term precipitation trends" questions. Returns slope per decade, R², and confidence rating.

### Calculator
- **calculate_derived**: Evaluate a math expression with named variables. Use to combine tool outputs — e.g., compute annual precipitation from daily rate: `precip_mm_day * 365.25`. Supports +, -, *, /, **, abs(), round(), sqrt(), etc.

## Workflow

1. **Understand the question** — What variable? What location? Point or area? Single year or trend?
2. **Call discover_datasets** if you're unsure which variable maps to the user's question
3. **Choose the right tool**:
   - Single point, single year → get_*_projection or get_climate_overview
   - Seasonal pattern → sample_timeseries with aggregation="monthly" or "seasonal"
   - Region/area → sample_area_stats with a bounding box
   - Change over time → compute_anomaly (2 years) or compute_trend (multi-decade)
   - Derived value → calculate_derived with variables from previous tool outputs
4. **Synthesize the answer** — Put numbers in context, explain what they mean

## CRITICAL RULES
- **ALWAYS extract lat/lon from [Location Context]** and pass to tools
- **Max 3 tool calls per message** — combine when possible
- **Use get_climate_overview for general questions** — it's one call for all variables
- **For trends, use compute_trend** — don't manually call multiple years
- **For bounding boxes** — approximate city/region sizes:
  - Small city: ±0.1° (~11 km)
  - Large city: ±0.25° (~28 km)
  - Metro area: ±0.5° (~55 km)
  - State: use actual boundaries (lookup if needed)

## Response Format
1. **Location & Context**: Name the place, state what was asked
2. **Data Results**: Present the numbers with units
3. **Interpretation**: What do these numbers mean practically?
4. **Summary**: Direct answer to the user's specific question, citing actual data values

Data source: NASA NEX-GDDP-CMIP6 (0.25° grid, 2015-2100).
Keep responses factual and concise. No generic climate disclaimers.
"""


class NetCDFComputationAgentSession:
    """Represents a conversation session with the computation agent."""

    def __init__(self, session_id: str, latitude: float, longitude: float, thread_id: str):
        self.session_id = session_id
        self.latitude = latitude
        self.longitude = longitude
        self.thread_id = thread_id
        self.created_at = datetime.utcnow()
        self.last_activity = datetime.utcnow()
        self.message_count = 0

    def update_location(self, latitude: float, longitude: float):
        self.latitude = latitude
        self.longitude = longitude
        self.last_activity = datetime.utcnow()


_reverse_geocode_cache: Dict[str, str] = {}


class NetCDFComputationAgent:
    """
    Azure AI Agent Service-based computation agent.

    Re-uses the same lazy init / retry / session pattern as ExtremeWeatherAgent
    but registers the extended computation toolset.
    """

    def __init__(self):
        self.sessions: Dict[str, NetCDFComputationAgentSession] = {}
        self._agents_client = None
        self._agent_id: Optional[str] = None
        self._initialized = False
        logger.info("NetCDFComputationAgent created (will initialize on first use)")

    async def _ensure_initialized(self):
        if self._initialized:
            return
        import asyncio

        last_error = None
        for attempt in range(3):
            try:
                if attempt > 0:
                    wait_secs = 2 ** attempt
                    logger.info(f"[RETRY] NetCDFComputationAgent init attempt {attempt + 1}/3 after {wait_secs}s...")
                    await asyncio.sleep(wait_secs)
                    self._agents_client = None
                    self._agent_id = None
                    self._initialized = False
                await self._do_initialize()
                return
            except Exception as e:
                last_error = e
                logger.warning(f"[RETRY] NetCDFComputationAgent init attempt {attempt + 1} failed: {e}")
        raise last_error

    async def _do_initialize(self):
        logger.info("Initializing NetCDFComputationAgent with Azure AI Agent Service...")

        endpoint = os.getenv("AZURE_AI_PROJECT_ENDPOINT") or os.getenv("AZURE_OPENAI_ENDPOINT")
        deployment = os.getenv("AZURE_OPENAI_DEPLOYMENT_NAME", "gpt-5")

        if not endpoint:
            raise ValueError("AZURE_AI_PROJECT_ENDPOINT or AZURE_OPENAI_ENDPOINT environment variable is required")

        credential = DefaultAzureCredential()

        from azure.ai.agents.aio import AgentsClient
        from azure.ai.agents.models import AsyncFunctionTool, AsyncToolSet

        self._agents_client = AgentsClient(
            endpoint=endpoint,
            credential=credential,
        )

        from geoint.netcdf_computation_tools import create_netcdf_computation_functions

        computation_functions = create_netcdf_computation_functions()

        functions = AsyncFunctionTool(computation_functions)
        toolset = AsyncToolSet()
        toolset.add(functions)
        self._agents_client.enable_auto_function_calls(toolset)

        agent = await self._agents_client.create_agent(
            model=deployment,
            name="NetCDFComputationAnalyst",
            instructions=NETCDF_COMPUTATION_AGENT_INSTRUCTIONS,
            toolset=toolset,
        )
        self._agent_id = agent.id
        self._initialized = True
        logger.info(f"NetCDFComputationAgent initialized: agent_id={agent.id}, model={deployment}")

    async def _get_or_create_session(
        self, session_id: str, latitude: float, longitude: float
    ) -> NetCDFComputationAgentSession:
        if session_id in self.sessions:
            session = self.sessions[session_id]
            session.update_location(latitude, longitude)
            return session

        thread = await self._agents_client.threads.create()
        session = NetCDFComputationAgentSession(session_id, latitude, longitude, thread.id)
        self.sessions[session_id] = session
        logger.info(f"Created new computation session: {session_id} -> thread: {thread.id}")
        return session

    def cleanup_old_sessions(self, max_age_minutes: int = 60):
        now = datetime.utcnow()
        expired = [
            sid
            for sid, s in self.sessions.items()
            if (now - s.last_activity).total_seconds() > max_age_minutes * 60
        ]
        for sid in expired:
            del self.sessions[sid]
            logger.info(f"Cleaned up expired computation session: {sid}")

    async def chat(
        self,
        session_id: str,
        user_message: str,
        latitude: float,
        longitude: float,
        screenshot_base64: Optional[str] = None,
        radius_km: float = 5.0,
    ) -> Dict[str, Any]:
        """Process a user message and return agent response."""
        await self._ensure_initialized()

        session = await self._get_or_create_session(session_id, latitude, longitude)

        # Reverse geocode for location name
        import asyncio
        from semantic_translator import geocoding_plugin

        geo_cache_key = f"{latitude:.4f}:{longitude:.4f}"
        location_name = _reverse_geocode_cache.get(geo_cache_key)
        if not location_name:
            try:
                rg = await geocoding_plugin.azure_maps_reverse_geocode(latitude, longitude)
                data = json.loads(rg)
                if not data.get("error"):
                    n = data.get("name", "")
                    r = data.get("region", "")
                    c = data.get("country", "")
                    parts = [p for p in [n, r, c] if p and p != n]
                    location_name = f"{n}, {', '.join(parts)}" if n and parts else n or f"({latitude:.4f}, {longitude:.4f})"
                else:
                    location_name = f"({latitude:.4f}, {longitude:.4f})"
            except Exception:
                location_name = f"({latitude:.4f}, {longitude:.4f})"
            _reverse_geocode_cache[geo_cache_key] = location_name

        context_message = f"""[Location Context]
- Location: {location_name}
- Coordinates: ({latitude:.6f}, {longitude:.6f})
- Default scenario: SSP5-8.5 (worst-case) — user can override
- Default year: 2030 — user can override
- Session messages: {session.message_count}

[User Question]
{user_message}"""

        logger.info(f"NetCDF Computation Session {session_id}: Processing '{user_message[:80]}...'")

        _retryable_patterns = [
            "404", "Resource not found", "invalid_engine_error",
            "Failed to resolve model", "InternalServerError",
            "Unable to get resource", "DeploymentNotFound",
            "server_error", "something went wrong",
        ]

        max_retries = 3
        for attempt in range(max_retries):
            try:
                if attempt > 0:
                    await asyncio.sleep(2 ** attempt)
                    session = await self._get_or_create_session(
                        f"{session_id}_retry{attempt}", latitude, longitude
                    )

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
                    error_text = str(run.last_error)
                    logger.error(f"Computation agent run failed: {error_text}")
                    is_retryable = any(p.lower() in error_text.lower() for p in _retryable_patterns)
                    if is_retryable and attempt < max_retries - 1:
                        logger.warning(f"Computation run failed (retryable), re-initializing... (attempt {attempt + 1})")
                        self._initialized = False
                        self._agent_id = None
                        self._agents_client = None
                        self.sessions.clear()
                        await self._ensure_initialized()
                        continue
                    return {
                        "response": f"Error analyzing climate data: {run.last_error}",
                        "error": str(run.last_error),
                        "session_id": session_id,
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

                # Extract tool call info
                try:
                    run_steps_iterable = self._agents_client.run_steps.list(
                        thread_id=session.thread_id,
                        run_id=run.id,
                    )
                    async for step in run_steps_iterable:
                        if hasattr(step, "step_details") and hasattr(step.step_details, "tool_calls"):
                            for tc in step.step_details.tool_calls:
                                if hasattr(tc, "function"):
                                    tool_name = tc.function.name
                                    tool_output = getattr(tc.function, "output", None)
                                    result_parsed = tool_output
                                    if isinstance(tool_output, str) and tool_output.startswith("{"):
                                        try:
                                            result_parsed = json.loads(tool_output)
                                        except Exception:
                                            pass
                                    tool_calls.append({
                                        "tool": tool_name,
                                        "result": result_parsed if isinstance(result_parsed, dict) else str(tool_output)[:500] if tool_output else None,
                                    })
                                    logger.info(f"Computation tool called: {tool_name}")
                except Exception as e:
                    logger.debug(f"Could not extract run steps: {e}")

                session.message_count += 2
                session.last_activity = datetime.utcnow()

                logger.info(f"Computation agent response ({len(response_content)} chars, {len(tool_calls)} tool calls)")
                return {
                    "response": response_content,
                    "tool_calls": tool_calls,
                    "session_id": session_id,
                    "message_count": session.message_count,
                    "location": {"latitude": latitude, "longitude": longitude},
                }

            except Exception as e:
                error_str = str(e)
                is_retryable = any(p.lower() in error_str.lower() for p in _retryable_patterns)
                if is_retryable and attempt < max_retries - 1:
                    logger.warning(f"Computation agent error (retryable): {error_str[:200]}, re-initializing...")
                    self._initialized = False
                    self._agent_id = None
                    self._agents_client = None
                    self.sessions.clear()
                    try:
                        await self._ensure_initialized()
                        continue
                    except Exception as reinit_err:
                        return {
                            "response": f"Error: Agent service unavailable - {reinit_err}",
                            "error": str(reinit_err),
                            "session_id": session_id,
                        }

                logger.error(f"Computation agent error: {e}")
                import traceback
                logger.error(traceback.format_exc())
                return {
                    "response": f"Error analyzing climate data: {e}",
                    "error": str(e),
                    "session_id": session_id,
                }


# ---------------------------------------------------------------------------
# Singleton accessor
# ---------------------------------------------------------------------------
_instance: Optional[NetCDFComputationAgent] = None


def get_netcdf_computation_agent() -> NetCDFComputationAgent:
    """Get or create the singleton NetCDFComputationAgent instance."""
    global _instance
    if _instance is None:
        _instance = NetCDFComputationAgent()
    return _instance
