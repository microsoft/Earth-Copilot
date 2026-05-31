"""AnalystAgent — single Azure AI Agent Service agent for all Layer-2 analysis.

This replaces the AnalysisRouter + Orchestrator + Synthesizer + 9-analyzer
registry with one ReAct agent that picks tools from the catalog in
``tools.py``.

Public API
----------
* ``AnalystAgent`` — class with ``async run(request) -> SynthesizedResponse``
* ``get_analyst_agent()`` — module-level singleton accessor

Architecture
------------
* Lazy initialization (no Agent Service calls at import time)
* One agent definition; per-session thread (mirrors EnhancedVisionAgent
  pattern)
* Tools read shared state via the session ContextVar in
  ``session_context.py``
* Fail-open: any uncaught exception returns a SynthesizedResponse with
  ``success=False`` and a graceful error message — never crashes the
  dispatch caller.
"""

from __future__ import annotations

import asyncio
import logging
import os
import time
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Lazy import of Azure SDK — keep dev environments without Azure usable.
# ---------------------------------------------------------------------------

try:
    from azure.identity.aio import DefaultAzureCredential  # type: ignore

    _AZURE_AVAILABLE = True
except Exception as _az_exc:  # pragma: no cover
    logger.warning(
        "azure.identity not available (%s); AnalystAgent will fail-open with a fallback response.",
        _az_exc,
    )
    _AZURE_AVAILABLE = False
    DefaultAzureCredential = None  # type: ignore


# ---------------------------------------------------------------------------
# Per-session thread tracking
# ---------------------------------------------------------------------------


@dataclass
class AnalystThread:
    session_id: str
    thread_id: Optional[str] = None


# ---------------------------------------------------------------------------
# AnalystAgent
# ---------------------------------------------------------------------------


class AnalystAgent:
    """Single ReAct agent that owns all of Layer 2."""

    def __init__(self) -> None:
        self._agents_client = None
        self._agent_id: Optional[str] = None
        self._initialized = False
        self._init_lock = asyncio.Lock()
        self._threads: Dict[str, AnalystThread] = {}
        self._max_init_retries = 2
        logger.info("AnalystAgent created (lazy init on first use)")

    # ------------------------------------------------------------------
    # Initialization
    # ------------------------------------------------------------------

    async def _ensure_initialized(self) -> None:
        if self._initialized:
            return
        async with self._init_lock:
            if self._initialized:
                return
            last_error: Optional[Exception] = None
            for attempt in range(self._max_init_retries + 1):
                try:
                    if attempt > 0:
                        wait = 2**attempt
                        logger.info(
                            "[ANALYST] init retry %d/%d after %ds",
                            attempt + 1,
                            self._max_init_retries + 1,
                            wait,
                        )
                        await asyncio.sleep(wait)
                    await self._do_initialize()
                    return
                except Exception as e:
                    last_error = e
                    logger.warning(
                        "[ANALYST] init attempt %d failed: %s", attempt + 1, e
                    )
                    self._agents_client = None
                    self._agent_id = None
                    self._initialized = False
            assert last_error is not None
            raise last_error

    async def _do_initialize(self) -> None:
        if not _AZURE_AVAILABLE:
            raise RuntimeError("azure.identity not installed")

        from azure.ai.agents.aio import AgentsClient  # type: ignore
        from azure.ai.agents.models import AsyncFunctionTool, AsyncToolSet  # type: ignore

        endpoint = os.getenv("AZURE_AI_PROJECT_ENDPOINT") or os.getenv(
            "AZURE_OPENAI_ENDPOINT"
        )
        deployment = os.getenv("AZURE_OPENAI_DEPLOYMENT_NAME", "gpt-5")
        if not endpoint:
            raise ValueError(
                "AZURE_AI_PROJECT_ENDPOINT or AZURE_OPENAI_ENDPOINT must be set"
            )

        from .analyst_prompt import ANALYST_AGENT_INSTRUCTIONS
        from .tools import create_analyst_functions

        credential = DefaultAzureCredential()
        self._agents_client = AgentsClient(endpoint=endpoint, credential=credential)

        functions = AsyncFunctionTool(create_analyst_functions())
        toolset = AsyncToolSet()
        toolset.add(functions)
        self._agents_client.enable_auto_function_calls(toolset)

        agent = await self._agents_client.create_agent(
            model=deployment,
            name="PlanetaryExplorerAnalyst",
            instructions=ANALYST_AGENT_INSTRUCTIONS,
            toolset=toolset,
        )
        self._agent_id = agent.id
        self._initialized = True
        logger.info(
            "AnalystAgent initialized: agent_id=%s model=%s", agent.id, deployment
        )

    # ------------------------------------------------------------------
    # Thread management
    # ------------------------------------------------------------------

    async def _get_or_create_thread(self, session_id: str) -> AnalystThread:
        existing = self._threads.get(session_id)
        if existing and existing.thread_id:
            return existing
        await self._ensure_initialized()
        thread = await self._agents_client.threads.create()  # type: ignore[union-attr]
        rec = AnalystThread(session_id=session_id, thread_id=thread.id)
        self._threads[session_id] = rec
        logger.info("[ANALYST] thread %s -> %s", session_id, thread.id)
        return rec

    # ------------------------------------------------------------------
    # Main entry
    # ------------------------------------------------------------------

    async def run(self, request) -> "SynthesizedResponse":
        """Run the ReAct loop for a single AnalysisRequest.

        Returns a SynthesizedResponse that's drop-in compatible with the
        old Orchestrator + Synthesizer output (so layer1_agents.AnalyzeAgent
        doesn't need to change its caller contract).
        """
        from pipeline.contracts import (
            AnalysisPlan,
            SynthesizedResponse,
            Source,
            Visualization,
        )
        from .session_context import AnalystSession, clear_session, get_session, set_session

        started = time.time()

        # Populate the ContextVar so tools see the session.
        # ``use_graphrag`` / ``stac_mode`` ride on the request via the
        # request.options dict-style attributes when present (set by
        # AnalyzeAgent before delegation). Default to permissive "on".
        _use_graphrag = bool(getattr(request, "use_graphrag", True))
        _stac_mode = str(getattr(request, "stac_mode", "public") or "public")
        sess = AnalystSession(
            question=request.question,
            session_id=request.session_id,
            pin=request.pin,
            pins=list(request.pins),
            bbox=request.bbox,
            location_name=request.location_name,
            time_range=request.time_range,
            loaded_collections=list(request.loaded_collections),
            loaded_collections_meta=list(request.loaded_collections_meta),
            screenshot_b64=request.screenshot_b64,
            screenshot_url=request.screenshot_url,
            has_screenshot=request.has_screenshot,
            stac_items=list(request.stac_items),
            tile_urls=list(request.tile_urls),
            history=list(request.history),
            hint=request.hint,
            use_graphrag=_use_graphrag,
            stac_mode=_stac_mode,
        )
        set_session(sess)

        try:
            answer, tool_calls, evidence = await self._invoke_agent_service(request)
        except Exception as e:
            logger.exception("[ANALYST] run failed, returning fallback response")
            answer = self._fallback_answer(request, str(e))
            tool_calls = []
            evidence = []

        # Aggregate sources from tool evidence
        sources: List[Source] = []
        seen = set()
        for ev in evidence:
            for src in (ev.get("payload") or {}).get("sources", []) or []:
                key = (src.get("title"), src.get("uri"))
                if key in seen:
                    continue
                seen.add(key)
                try:
                    sources.append(Source(**src))
                except Exception:
                    pass

        # Detect a clarify short-circuit
        structured_by_tool: Dict[str, Any] = {}
        clarify_payload: Optional[Dict[str, Any]] = None
        for ev in evidence:
            tool_name = ev.get("tool")
            payload = ev.get("payload") or {}
            if tool_name == "ask_user_to_clarify":
                clarify_payload = payload
            if tool_name:
                structured_by_tool[tool_name] = payload

        if clarify_payload:
            structured_by_tool["clarify"] = clarify_payload

        # Build a degenerate plan record for back-compat with callers that
        # still serialize ``plan``. The plan is just the sequence of tools
        # that actually ran.
        try:
            from pipeline.contracts import AnalysisStep
            plan_steps = [
                AnalysisStep(
                    analyzer=ev.get("tool", "unknown"),
                    hint=None,
                    rationale="ReAct tool call",
                    parallel_with_previous=False,
                )
                for ev in evidence
                if ev.get("tool")
            ]
            plan = AnalysisPlan(steps=plan_steps, reasoning="AnalystAgent ReAct", confidence=0.9)
        except Exception:
            plan = None  # type: ignore

        clear_session()

        elapsed_ms = int((time.time() - started) * 1000)
        return SynthesizedResponse(
            answer=answer,
            sources=sources,
            visualizations=[],  # tools currently don't emit visualizations
            structured=structured_by_tool,
            plan=plan,
            elapsed_ms=elapsed_ms,
        )

    # ------------------------------------------------------------------
    # Agent Service invocation
    # ------------------------------------------------------------------

    async def _invoke_agent_service(self, request):
        """Send message, run, collect assistant text + tool-call evidence."""
        from azure.ai.agents.models import ListSortOrder  # type: ignore

        await self._ensure_initialized()
        assert self._agents_client is not None and self._agent_id is not None

        thread = await self._get_or_create_thread(request.session_id)

        augmented = self._build_message(request)

        run = None
        for attempt in range(3):
            try:
                if attempt > 0:
                    await asyncio.sleep(2**attempt)
                    new_thread = await self._agents_client.threads.create()
                    self._threads[request.session_id] = AnalystThread(
                        session_id=request.session_id, thread_id=new_thread.id
                    )
                    thread = self._threads[request.session_id]

                await self._agents_client.messages.create(
                    thread_id=thread.thread_id,
                    role="user",
                    content=augmented,
                )
                run = await self._agents_client.runs.create_and_process(
                    thread_id=thread.thread_id,
                    agent_id=self._agent_id,
                )
                break
            except Exception as e:
                logger.warning("[ANALYST] run attempt %d failed: %s", attempt + 1, e)
                if attempt == 2:
                    raise

        if run is None:
            raise RuntimeError("Agent Service run returned None")
        if run.status == "failed":
            raise RuntimeError(f"Agent Service run failed: {run.last_error}")

        # Extract assistant response
        answer = ""
        messages = self._agents_client.messages.list(
            thread_id=thread.thread_id,
            order=ListSortOrder.DESCENDING,
        )
        async for msg in messages:
            if msg.run_id != run.id:
                continue
            if msg.role == "assistant" and msg.text_messages:
                answer = msg.text_messages[-1].text.value
                break

        # Extract tool-call names (evidence shape comes from the ContextVar)
        tool_calls: List[str] = []
        run_steps = self._agents_client.run_steps.list(
            thread_id=thread.thread_id,
            run_id=run.id,
        )
        async for step in run_steps:
            details = getattr(step, "step_details", None)
            if details and hasattr(details, "tool_calls"):
                for tc in details.tool_calls or []:
                    fn = getattr(tc, "function", None)
                    if fn and getattr(fn, "name", None):
                        tool_calls.append(fn.name)

        # Tools recorded their results on the session ContextVar
        from .session_context import get_session
        evidence = list(get_session().evidence)
        return answer, tool_calls, evidence

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _build_message(self, request) -> str:
        ctx_lines: List[str] = []
        if request.location_name:
            ctx_lines.append(f"- location_name: {request.location_name}")
        if request.pin:
            ctx_lines.append(f"- pin: lat={request.pin[0]:.5f}, lng={request.pin[1]:.5f}")
        if request.bbox:
            ctx_lines.append(f"- bbox: {request.bbox}")
        if request.loaded_collections:
            ctx_lines.append(
                f"- loaded_collections: {', '.join(request.loaded_collections)}"
            )
        if request.has_screenshot or request.screenshot_b64:
            ctx_lines.append("- screenshot: available")
        if request.time_range:
            ctx_lines.append(
                f"- time_range: {request.time_range} "
                f"(window of data already LOADED on the map — samplable, "
                f"not a hard constraint)"
            )
        if request.history:
            # Last 3 turns max, condensed
            tail = request.history[-3:]
            ctx_lines.append(f"- recent_history: {len(tail)} turn(s)")

        ctx_block = "\n".join(ctx_lines) if ctx_lines else "- (no map state)"

        return (
            f"[Session Context]\n{ctx_block}\n\n"
            f"[User Question]\n{request.question}"
        )

    def _fallback_answer(self, request, err: str) -> str:
        # Last-resort message when Agent Service is unreachable.
        return (
            "I couldn't complete the analysis right now — the Planetary Explorer "
            f"analyst service was unavailable ({err[:120]}). Please retry; "
            "if the problem persists, check the AZURE_AI_PROJECT_ENDPOINT and "
            "managed-identity configuration."
        )


# ---------------------------------------------------------------------------
# Singleton accessor
# ---------------------------------------------------------------------------


_SINGLETON: Optional[AnalystAgent] = None


def get_analyst_agent() -> AnalystAgent:
    global _SINGLETON
    if _SINGLETON is None:
        _SINGLETON = AnalystAgent()
    return _SINGLETON
