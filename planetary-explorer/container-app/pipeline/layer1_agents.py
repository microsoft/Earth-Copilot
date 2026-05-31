"""Layer-1 specialist agents — one per `ActionDecision.action`.

This module is the concrete realization of "Layer 1 as a multi-agent
system". The classifier (``ActionRouter`` -> ``ActionDecision``) decides
WHICH specialist runs; each specialist below OWNS its action end-to-end
and returns a canonical response dict.

Specialists
-----------
``NavigateAgent``         -- NAVIGATE         : geocode + bbox + center
``LoadSpecialistAgent``   -- LOAD             : delegates to the existing
                                                ``LoadAgent`` (slot fill +
                                                stac_query refinement)
``AnalyzeAgent``          -- ANALYZE          : Layer-2 clarifier ->
                                                AnalysisRouter ->
                                                Orchestrator
``LoadAndAnalyzeAgent``   -- LOAD_AND_ANALYZE : LoadAgent then AnalyzeAgent
                                                (closes ARCHITECTURE.md G4
                                                where LOAD planning was
                                                being skipped)

All four are real Microsoft Agent Framework ``Executor`` subclasses
(when ``agent_framework`` is installed). They expose two surfaces:

  1. ``async def run(decision, request, body) -> dict`` -- the
     direct-invocation path used by ``pipeline/dispatch.run_pipeline_v2``.
     This stays the hot path so behavior is unchanged when MAF is not
     installed (lean dev environments).
  2. ``@handler async def on_message(msg, ctx)`` -- the workflow-graph
     entry point used when these agents are wired into a
     ``WorkflowBuilder`` graph (next refactor wave).

Both surfaces share the same internal ``_run`` implementation so there
is exactly one source of truth per action.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from typing import Any, Dict, Optional

from .contracts import ActionDecision, AnalysisRequest

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# MAF base class (optional — degrades to plain object when not installed).
# Mirrors the import block in pipeline/executors.py so behavior is identical.
# ---------------------------------------------------------------------------

try:
    from agent_framework import (  # type: ignore
        Executor,
        WorkflowContext,
        handler,
    )

    _AGENT_FRAMEWORK_AVAILABLE = True
except Exception as _af_exc:  # pragma: no cover - optional dependency
    logger.info(
        "agent_framework not available (%s); layer1 agents will be plain "
        "Python classes (direct .run() path still works).",
        _af_exc,
    )
    _AGENT_FRAMEWORK_AVAILABLE = False
    Executor = object  # type: ignore
    handler = lambda f: f  # type: ignore  # noqa: E731

    class WorkflowContext:  # type: ignore
        """Stand-in so type hints resolve at import time."""


# ---------------------------------------------------------------------------
# Envelope. Matches pipeline/executors.PipelineMessage in spirit but adds
# the raw request body (so specialists can reach session_id /
# location_name / etc that aren't part of AnalysisRequest).
# ---------------------------------------------------------------------------


@dataclass
class Layer1Message:
    """Envelope threaded between ActionRouterAgent and the specialists."""

    request: AnalysisRequest
    body: Dict[str, Any]
    decision: Optional[ActionDecision] = None
    result: Optional[Dict[str, Any]] = None


# ---------------------------------------------------------------------------
# 1) NavigateAgent
# ---------------------------------------------------------------------------


class NavigateAgent(Executor):  # type: ignore[misc]
    """NAVIGATE specialist.

    Owns: location parsing, geocoding, bbox+center derivation, the
    user-facing chat message, and the ``navigate_to`` payload the frontend
    needs to fly the camera.

    Replaces what used to live as inline code in fastapi_app.py around
    the v2 NAVIGATE handler. Now the FastAPI layer just plumbs through
    ``result["navigate_to"]`` instead of recomputing it.
    """

    def __init__(self, id: str = "navigate_agent") -> None:
        if _AGENT_FRAMEWORK_AVAILABLE:
            super().__init__(id=id)
        self.id = id

    async def _resolve_bbox(self, location: str) -> Optional[list[float]]:
        """Geocode *location* to ``[west, south, east, north]`` WGS84."""
        try:
            from location_resolver import EnhancedLocationResolver  # local import to avoid heavy module load at import time
        except Exception as exc:
            logger.warning("[NAVIGATE_AGENT] location_resolver import failed: %s", exc)
            return None
        resolver = EnhancedLocationResolver()
        try:
            bbox = await resolver.resolve_location_to_bbox(location)
            if (not bbox or len(bbox) != 4) and hasattr(resolver, "_strategy_azure_maps"):
                bbox = await resolver._strategy_azure_maps(location)
            if bbox and len(bbox) == 4:
                return [float(b) for b in bbox]
        except Exception as exc:
            logger.warning("[NAVIGATE_AGENT] resolve failed for %r: %s", location, exc)
        return None

    @staticmethod
    def _display_name(location: str) -> str:
        if not location:
            return location
        # Preserve mixed-case strings (NYC, USA, etc.); title-case lower-only.
        return location if any(c.isupper() for c in location) else location.title()

    async def run(
        self,
        decision: ActionDecision,
        request: AnalysisRequest,
        body: Dict[str, Any],
    ) -> Dict[str, Any]:
        started = time.time()
        location = (
            (decision.location or "").strip()
            or (body.get("location_name") or "").strip()
            or request.question.strip()
            or "the requested location"
        )
        location_display = self._display_name(location)

        bbox = await self._resolve_bbox(location)
        navigate_to: Optional[Dict[str, Any]] = None
        if bbox is not None:
            center_lng = (bbox[0] + bbox[2]) / 2.0
            center_lat = (bbox[1] + bbox[3]) / 2.0
            navigate_to = {
                "latitude": center_lat,
                "longitude": center_lng,
                "zoom": 12,
                "bbox": bbox,
                "location_name": location_display,
            }
        else:
            logger.warning(
                "[NAVIGATE_AGENT] could not resolve %r; returning text-only response",
                location,
            )

        # Return the canonical NAVIGATE dict shape. fastapi_app passes
        # navigate_to straight through to the frontend.
        return {
            "pipeline_v2": True,
            "action": "NAVIGATE",
            "decision": decision.model_dump(),
            "answer": f"Navigating the map to {location_display}.",
            "navigate_to": navigate_to,
            "location_name": location_display,
            "elapsed_ms": int((time.time() - started) * 1000),
        }

    if _AGENT_FRAMEWORK_AVAILABLE:
        @handler  # type: ignore
        async def on_message(
            self,
            msg: "Layer1Message",
            ctx: "WorkflowContext[Layer1Message]",
        ) -> None:
            assert msg.decision is not None
            msg.result = await self.run(msg.decision, msg.request, msg.body)
            await ctx.send_message(msg)


# ---------------------------------------------------------------------------
# 2) LoadSpecialistAgent — thin adapter around the existing LoadAgent.
# ---------------------------------------------------------------------------


class LoadSpecialistAgent(Executor):  # type: ignore[misc]
    """LOAD specialist.

    Wraps the existing :class:`agents.load_agent.LoadAgent` so the
    Layer-1 multi-agent contract is uniform. The wrapped LoadAgent is a
    sibling that does its own LLM call to slot-fill (intent / location
    / collection / datetime / deliverable / chat_summary). On
    ``action='clarify'`` we emit a CLARIFY dict and the FastAPI layer
    suppresses STAC search; on ``action='execute'`` we emit a LOAD dict
    with ``stac_query`` and the chat summary.
    """

    def __init__(self, id: str = "load_specialist_agent") -> None:
        if _AGENT_FRAMEWORK_AVAILABLE:
            super().__init__(id=id)
        self.id = id

    async def run(
        self,
        decision: ActionDecision,
        request: AnalysisRequest,
        body: Dict[str, Any],
    ) -> Dict[str, Any]:
        started = time.time()
        try:
            from agents.load_agent import get_load_agent, LoadAgentInput
        except Exception as imp_exc:
            logger.warning("[LOAD_AGENT] import failed: %s", imp_exc)
            return self._fallback(started, decision, request, "import_failure")

        # Resolve Public/Pro routing for the prompt. body.stac_mode (from
        # the UI toggle) takes precedence; DEFAULT_STAC_MODE env is the
        # fallback. When the resolved mode is "pro" we also fetch the
        # cached list of Pro collection ids so the agent picks valid ones.
        import os as _os
        _stac_mode_raw = (body.get("stac_mode") if isinstance(body, dict) else None)
        _stac_mode = (_stac_mode_raw or _os.getenv("DEFAULT_STAC_MODE") or "public").lower()
        _pro_ids: list[str] = []
        if _stac_mode == "pro":
            try:
                from pro_stac_client import get_pro_collection_ids
                _pro_ids = await get_pro_collection_ids()
            except Exception as pro_exc:
                logger.warning("[LOAD_AGENT] fetching Pro collections failed: %s", pro_exc)

        try:
            # Clarification resume: when the FastAPI layer detects a
            # pending LOAD clarification from a prior turn, it stuffs the
            # prior context into body["_pending_load_clarification"].
            # Forward it into LoadAgentInput so the agent resolves the
            # ambiguity instead of re-asking.
            _pending_load = body.get("_pending_load_clarification") if isinstance(body, dict) else None
            _pending_load = _pending_load if isinstance(_pending_load, dict) else None
            load_plan = await get_load_agent().plan(
                LoadAgentInput(
                    query=request.question,
                    location_name=decision.location,
                    has_bbox=bool(request.bbox),
                    bbox=list(request.bbox) if request.bbox else None,
                    has_time_range=bool(request.time_range),
                    time_range=list(request.time_range) if request.time_range else None,
                    has_rendered_map=bool(request.loaded_collections),
                    loaded_collections=list(request.loaded_collections),
                    has_pin=bool(request.pin),
                    pin_lat=request.pin[0] if request.pin else None,
                    pin_lng=request.pin[1] if request.pin else None,
                    layer1_stac_query=decision.stac_query,
                    layer1_reasoning=decision.reasoning,
                    stac_mode=_stac_mode,
                    available_pro_collections=_pro_ids,
                    prior_query=(_pending_load or {}).get("prior_query"),
                    prior_clarification_question=(_pending_load or {}).get("question"),
                    prior_clarification_options=list((_pending_load or {}).get("options") or []),
                    prior_collection_candidates=list((_pending_load or {}).get("collection_candidates") or []),
                    prior_clarification_history=list((_pending_load or {}).get("history") or []),
                    clarification_round=int((_pending_load or {}).get("round") or 0),
                )
            )
        except Exception as plan_err:
            logger.warning("[LOAD_AGENT] plan failed: %r", plan_err)
            return self._fallback(started, decision, request, f"plan_error:{type(plan_err).__name__}")

        logger.info(
            "[LOAD_AGENT] action=%s intent=%s deliv=%s top=%s ambiguous_dt=%s",
            load_plan.action,
            load_plan.intent,
            load_plan.deliverable,
            (load_plan.collection_candidates[0].id if load_plan.collection_candidates else "<none>"),
            load_plan.datetime.ambiguous,
        )

        # ANTI-LOOP GUARD. The LLM has been instructed (load_agent_prompt.py
        # HARD CAP) to execute when clarification_round >= 2. Belt-and-
        # suspenders: if it ignored that instruction, override here so a
        # buggy prompt run can never trap the user in an infinite clarify
        # loop. We force action=execute, reuse the pinned collection, and
        # fall back to the user's prior_query / layer-1 stac_query for the
        # search payload.
        _round = int((_pending_load or {}).get("round") or 0)
        if load_plan.action == "clarify" and _round >= 2:
            from agents.load_agent.load_agent_models import CollectionCandidate
            _pinned_ids = list((_pending_load or {}).get("collection_candidates") or [])
            if not load_plan.collection_candidates and _pinned_ids:
                load_plan.collection_candidates = [
                    CollectionCandidate(id=_pinned_ids[0], title=_pinned_ids[0], rank=0, reason="pinned_from_prior_round")
                ]
            _forced_stac = (
                load_plan.stac_query
                or (load_plan.collection_candidates[0].id if load_plan.collection_candidates else None)
                or (_pending_load or {}).get("prior_query")
                or decision.stac_query
                or request.question
            )
            _coll = (
                load_plan.collection_candidates[0].id
                if load_plan.collection_candidates
                else "the requested collection"
            )
            _loc = decision.location or (load_plan.location.name if load_plan.location else None) or "the requested area"
            logger.warning(
                "[LOAD_AGENT] round=%d still clarify -> forcing execute "
                "(collection=%s, stac=%r)",
                _round, _coll, _forced_stac,
            )
            load_plan.action = "execute"
            load_plan.stac_query = str(_forced_stac) if _forced_stac else None
            load_plan.clarification_question = None
            load_plan.options = []
            load_plan.chat_summary = (
                f"Loading {_coll} over {_loc} with default options "
                "(after multiple clarifications, proceeding so we don't loop)."
            )
        structured: Dict[str, Any] = {"load_plan": load_plan.model_dump()}
        if load_plan.action == "clarify":
            return {
                "pipeline_v2": True,
                "action": "CLARIFY",
                "decision": decision.model_dump(),
                "answer": load_plan.chat_summary,
                "structured": {
                    **structured,
                    "clarify": True,
                    "missing_slot": (
                        "datetime" if load_plan.datetime.ambiguous else "load_plan"
                    ),
                    "options": load_plan.options,
                },
                "elapsed_ms": int((time.time() - started) * 1000),
            }
        effective_stac_query = (
            load_plan.stac_query or decision.stac_query or request.question
        )
        return {
            "pipeline_v2": True,
            "action": "LOAD",
            "decision": decision.model_dump(),
            "answer": load_plan.chat_summary,
            "structured": structured,
            "stac_query": effective_stac_query,
            "elapsed_ms": int((time.time() - started) * 1000),
        }

    @staticmethod
    def _fallback(
        started: float,
        decision: ActionDecision,
        request: AnalysisRequest,
        reason: str,
    ) -> Dict[str, Any]:
        loc = decision.location or "the requested area"
        sq = decision.stac_query or request.question
        return {
            "pipeline_v2": True,
            "action": "LOAD",
            "decision": decision.model_dump(),
            # REQ-LOAD-3: never echo the user's raw query. The final
            # chat reply is rebuilt post-render from actual rendered
            # features in fastapi_app.py; this is a placeholder for
            # paths that bypass that rebuild.
            "answer": f"Loading imagery for {loc}.",
            "structured": {"load_plan_fallback_reason": reason},
            "elapsed_ms": int((time.time() - started) * 1000),
        }

    if _AGENT_FRAMEWORK_AVAILABLE:
        @handler  # type: ignore
        async def on_message(
            self,
            msg: "Layer1Message",
            ctx: "WorkflowContext[Layer1Message]",
        ) -> None:
            assert msg.decision is not None
            msg.result = await self.run(msg.decision, msg.request, msg.body)
            await ctx.send_message(msg)


# ---------------------------------------------------------------------------
# 3) AnalyzeAgent — delegates to the Layer-2 multi-agent set.
# ---------------------------------------------------------------------------


class AnalyzeAgent(Executor):  # type: ignore[misc]
    """ANALYZE specialist.

    End-to-end ANALYZE turn. The actual planning + execution is delegated
    to :class:`pipeline.layer2_agents.Layer2AgentSet`, which is itself a
    multi-agent system (modality classifier + Text / Vision / Hybrid
    specialists). This agent's job is to:

      1. Map the Layer-1 action onto the Layer-2 ``target_route`` hint.
      2. Hand the request to ``Layer2AgentSet.run()``.
      3. Translate the result -- either a CLARIFY follow-up or a fully
         synthesized response -- into the canonical Layer-1 dict shape.
    """

    def __init__(
        self,
        layer2_agents=None,  # Deprecated since Wave 10 — kept for back-compat
        id: str = "analyze_agent",
    ) -> None:
        if _AGENT_FRAMEWORK_AVAILABLE:
            super().__init__(id=id)
        self.id = id
        # Wave 10: layer2 is now the single AnalystAgent (Azure AI Agent
        # Service), not the modality-classifier + Layer2AgentSet. We keep
        # the constructor parameter for source-compat with callers that
        # still pass it; it is ignored.
        self._layer2 = layer2_agents  # noqa: F841 — retained for back-compat

    async def run(
        self,
        decision: ActionDecision,
        request: AnalysisRequest,
        body: Dict[str, Any],
    ) -> Dict[str, Any]:
        started = time.time()
        # Use the focused analysis_question if the router rewrote it.
        if decision.analysis_question:
            request = request.model_copy(update={"question": decision.analysis_question})

        # ------------------------------------------------------------
        # Wave 10 (REQ-ARCH-1): delegate to the single AnalystAgent
        # (Azure AI Agent Service ReAct) instead of AnalysisRouter ->
        # Orchestrator -> Synthesizer.
        # ------------------------------------------------------------
        from agents.analyst_agent import get_analyst_agent

        response = await get_analyst_agent().run(request)

        # The AnalystAgent surfaces clarifications via a "clarify" key in
        # ``structured`` (set by the ask_user_to_clarify tool). Mirror the
        # legacy CLARIFY shape so the FastAPI handler keeps working.
        clarify = (response.structured or {}).get("clarify")
        if isinstance(clarify, dict) and clarify.get("action") == "clarify":
            return {
                "pipeline_v2": True,
                "action": "CLARIFY",
                "decision": decision.model_dump(),
                "answer": clarify.get("chat_message") or response.answer,
                "structured": {
                    "clarify": True,
                    "missing_slot": clarify.get("missing_slot"),
                    "options": clarify.get("options", []),
                    "analyzer_kind": "analyst_agent",
                    "analyzer": "analyst_agent",
                    "reasoning": "AnalystAgent requested clarification",
                },
                "elapsed_ms": int((time.time() - started) * 1000),
            }

        plan = response.plan
        logger.info(
            "[ANALYZE_AGENT] AnalystAgent tools=%s",
            [s.analyzer for s in plan.steps] if plan else ["<no-tools>"],
        )
        # Surface the tool sequence + data source for UI source chips.
        # `tools_used` is the ordered list of tool names the ReAct loop ran;
        # the frontend renders one chip per distinct tool. `data_source`
        # echoes the STAC mode for parity with the LOAD path.
        _tools_used = (
            [s.analyzer for s in plan.steps] if plan else []
        )
        _data_source = (
            "MPC Pro" if getattr(request, "stac_mode", "public") == "pro" else "Public PC"
        )
        return {
            "pipeline_v2": True,
            "action": decision.action,
            "decision": decision.model_dump(),
            "plan": plan.model_dump() if plan else None,
            "answer": response.answer,
            "sources": [s.model_dump() for s in response.sources],
            "visualizations": [v.model_dump() for v in response.visualizations],
            "structured": {
                **response.structured,
                "layer2_engine": "analyst_agent",
            },
            "tools_used": _tools_used,
            "data_source": _data_source,
            "elapsed_ms": int((time.time() - started) * 1000),
        }

    if _AGENT_FRAMEWORK_AVAILABLE:
        @handler  # type: ignore
        async def on_message(
            self,
            msg: "Layer1Message",
            ctx: "WorkflowContext[Layer1Message]",
        ) -> None:
            assert msg.decision is not None
            msg.result = await self.run(msg.decision, msg.request, msg.body)
            await ctx.send_message(msg)


# ---------------------------------------------------------------------------
# 4) LoadAndAnalyzeAgent — closes ARCHITECTURE.md G4.
# ---------------------------------------------------------------------------


class LoadAndAnalyzeAgent(Executor):  # type: ignore[misc]
    """LOAD_AND_ANALYZE specialist.

    Chains LoadAgent ahead of AnalyzeAgent so the LOAD half gets proper
    slot extraction (collection / datetime / deliverable) instead of
    being skipped — see ARCHITECTURE.md gap G4.

    Behavior:
      * If LoadAgent returns ``clarify``, short-circuit the analysis and
        return the CLARIFY dict (don't waste an analyzer call before the
        slot is filled).
      * Otherwise, enrich the AnalysisRequest with the agent's resolved
        ``stac_query`` (so the AnalysisRouter sees the same view the
        LOAD-side renderer will), then run AnalyzeAgent.
      * Stitch the LoadAgent's chat summary onto the front of the
        Analyze answer so the chat reflects both halves of the turn.
    """

    def __init__(
        self,
        load_agent: LoadSpecialistAgent,
        analyze_agent: AnalyzeAgent,
        id: str = "load_and_analyze_agent",
    ) -> None:
        if _AGENT_FRAMEWORK_AVAILABLE:
            super().__init__(id=id)
        self.id = id
        self._load = load_agent
        self._analyze = analyze_agent

    async def run(
        self,
        decision: ActionDecision,
        request: AnalysisRequest,
        body: Dict[str, Any],
    ) -> Dict[str, Any]:
        started = time.time()
        # Synthesize a LOAD-shaped decision for the LoadSpecialistAgent so
        # it slot-fills correctly. We keep the original action on the
        # outgoing dict for downstream consumers.
        load_decision = decision.model_copy(update={"action": "LOAD"})
        load_result = await self._load.run(load_decision, request, body)

        # If LoadAgent demands clarification, surface it. Don't proceed
        # to analysis until the user answers — analyzing the wrong layer
        # is worse than asking.
        if load_result.get("action") == "CLARIFY":
            load_result["elapsed_ms"] = int((time.time() - started) * 1000)
            return load_result

        # Enrich the request so AnalysisRouter sees the resolved STAC
        # query (closes the G4/G5 keyword-misrouting overlap).
        load_stac_query = load_result.get("stac_query")
        enriched_request = request
        if load_stac_query:
            enriched_request = request.model_copy(
                update={"hint": f"load_agent_stac_query:{load_stac_query}"}
            )

        analyze_result = await self._analyze.run(decision, enriched_request, body)

        # Stitch the LoadAgent chat summary onto the analyze answer so the
        # final chat reads as one coherent reply ("Loading X over Y. Y has
        # ...analysis...").
        load_summary = (load_result.get("answer") or "").strip()
        analyze_answer = (analyze_result.get("answer") or "").strip()
        if load_summary and analyze_answer:
            combined = f"{load_summary}\n\n{analyze_answer}"
        else:
            combined = analyze_answer or load_summary

        analyze_result["answer"] = combined
        # Carry the LoadAgent's stac_query and structured load_plan
        # through so the FastAPI tile renderer can use them.
        if load_stac_query:
            analyze_result["stac_query"] = load_stac_query
        merged_structured = dict(analyze_result.get("structured") or {})
        load_structured = load_result.get("structured") or {}
        if isinstance(load_structured, dict) and load_structured:
            merged_structured.setdefault("load_plan", load_structured.get("load_plan"))
        analyze_result["structured"] = merged_structured
        analyze_result["elapsed_ms"] = int((time.time() - started) * 1000)
        return analyze_result

    if _AGENT_FRAMEWORK_AVAILABLE:
        @handler  # type: ignore
        async def on_message(
            self,
            msg: "Layer1Message",
            ctx: "WorkflowContext[Layer1Message]",
        ) -> None:
            assert msg.decision is not None
            msg.result = await self.run(msg.decision, msg.request, msg.body)
            await ctx.send_message(msg)


# ---------------------------------------------------------------------------
# Composite dispatcher — picks the specialist based on ActionDecision.action.
# ---------------------------------------------------------------------------


class Layer1AgentSet:
    """Holds the four specialists and routes a decision to the right one.

    Used by ``pipeline/dispatch.run_pipeline_v2``. Constructed once via
    :func:`build_layer1_agents` and cached as a module-level singleton.
    """

    def __init__(
        self,
        navigate: NavigateAgent,
        load: LoadSpecialistAgent,
        analyze: AnalyzeAgent,
        load_and_analyze: LoadAndAnalyzeAgent,
    ) -> None:
        self.navigate = navigate
        self.load = load
        self.analyze = analyze
        self.load_and_analyze = load_and_analyze

    def for_action(self, action: str) -> Executor:
        """Return the specialist instance for *action*. Falls back to
        AnalyzeAgent for unknown actions (matches the router's fail-open
        default of ANALYZE)."""
        if action == "NAVIGATE":
            return self.navigate
        if action == "LOAD":
            return self.load
        if action == "LOAD_AND_ANALYZE":
            return self.load_and_analyze
        # ANALYZE or anything unexpected — analyze is the safe fallback.
        return self.analyze


_LAYER1_AGENTS_SINGLETON: Optional[Layer1AgentSet] = None


def build_layer1_agents(
    analysis_router,
    orchestrator,
    registry=None,
) -> Layer1AgentSet:
    """Wire the four Layer-1 specialists.

    AnalyzeAgent and LoadAndAnalyzeAgent share a single Layer-2 multi-agent
    set (modality classifier + Text/Vision/Hybrid specialists) built from
    *registry* and *orchestrator*. ``analysis_router`` is accepted for
    backward compatibility (some legacy callers pass it) but is no longer
    used directly -- each Layer-2 specialist owns its own filtered router.

    *registry* may be omitted by callers that don't have it handy; in that
    case we lazy-import ``build_default_pipeline`` to fetch it.
    """
    global _LAYER1_AGENTS_SINGLETON

    # Wave 10 (REQ-ARCH-1): no more Layer2AgentSet. AnalyzeAgent now
    # delegates directly to the singleton AnalystAgent (Azure AI Agent
    # Service). The legacy *analysis_router*, *orchestrator*, *registry*
    # parameters are accepted for source-compatibility with existing
    # callers (e.g. `dispatch.run_pipeline_v2`) but are no longer used.
    del analysis_router, orchestrator, registry  # explicit unused

    if _LAYER1_AGENTS_SINGLETON is not None:
        return _LAYER1_AGENTS_SINGLETON

    navigate = NavigateAgent()
    load = LoadSpecialistAgent()
    analyze = AnalyzeAgent()  # No layer2 dependency — uses AnalystAgent singleton
    load_and_analyze = LoadAndAnalyzeAgent(load_agent=load, analyze_agent=analyze)
    _LAYER1_AGENTS_SINGLETON = Layer1AgentSet(
        navigate=navigate,
        load=load,
        analyze=analyze,
        load_and_analyze=load_and_analyze,
    )
    logger.info(
        "[LAYER1] specialist set built: NavigateAgent, LoadSpecialistAgent, "
        "AnalyzeAgent, LoadAndAnalyzeAgent (MAF=%s) -> AnalystAgent (Wave 10)",
        _AGENT_FRAMEWORK_AVAILABLE,
    )
    return _LAYER1_AGENTS_SINGLETON
