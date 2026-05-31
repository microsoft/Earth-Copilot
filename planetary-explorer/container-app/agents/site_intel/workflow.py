"""Site Intel MAF workflow — assembles the fan-out/fan-in graph and exposes
:func:`audit_site_v2`, the v2 drop-in for :func:`agents.site_audit.audit_site`.

Topology
--------
::

    Planner ──► Retrieval ──► (fan-out)
                                ├── GridExecutor       ──┐
                                ├── WaterExecutor      ──┤
                                ├── CompetitionExecutor ─┤   fan-in
                                ├── LandExecutor       ──┼───► Aggregator
                                ├── HazardExecutor     ──┤        │
                                ├── PrecedentExecutor  ──┤        ▼
                                └── MetaExecutor (sidecar)┘   Evidence
                                                                  │
                                                                  ▼
                                                              Review (yields)

API mirrors :func:`agents.site_audit.audit_site` so the FastAPI route can
swap implementations behind ``SITE_AUDIT_V2=1`` without changing its
response contract.
"""

from __future__ import annotations

import logging
from typing import Any, AsyncIterator

logger = logging.getLogger(__name__)

try:
    from agent_framework import WorkflowBuilder  # type: ignore
    AGENT_FRAMEWORK_AVAILABLE = True
except Exception as exc:  # pragma: no cover
    logger.info("agent_framework not available (%s); v2 disabled", exc)
    AGENT_FRAMEWORK_AVAILABLE = False
    WorkflowBuilder = None  # type: ignore

from agents.site_audit import DEFAULT_LAKEHOUSE_ID, DEFAULT_WORKSPACE_ID

from .executors import (
    AGENT_FRAMEWORK_AVAILABLE as _EXECUTORS_OK,
    AggregatorExecutor,
    CompetitionExecutor,
    GridExecutor,
    HazardExecutor,
    LandExecutor,
    MetaExecutor,
    PrecedentExecutor,
    RetrievalExecutor,
    WaterExecutor,
)
from .messages import SiteSpec
from .planner import PlannerExecutor
from .review import EvidenceExecutor, ReviewExecutor


def is_available() -> bool:
    """True when MAF is importable and the v2 path is safe to use."""
    return AGENT_FRAMEWORK_AVAILABLE and _EXECUTORS_OK


def _build_workflow(
    spec: SiteSpec,
    workspace_id: str,
    lakehouse_id: str,
):
    """Construct the per-request workflow graph.

    A fresh graph is built per audit because the aggregator carries
    per-run state (collected DimensionResults). Construction is cheap
    (~µs) — the cost is dominated by the lakehouse + MPC + AI Search
    calls inside the executors.
    """
    if not is_available():
        raise RuntimeError(
            "Microsoft Agent Framework not available; cannot build v2 workflow."
        )

    planner = PlannerExecutor()
    retrieval = RetrievalExecutor()
    grid = GridExecutor()
    water = WaterExecutor()
    competition = CompetitionExecutor()
    land = LandExecutor()
    hazard = HazardExecutor()
    precedent = PrecedentExecutor()
    meta = MetaExecutor()
    aggregator = AggregatorExecutor(
        spec=spec,
        workspace_id=workspace_id,
        lakehouse_id=lakehouse_id,
    )
    evidence = EvidenceExecutor()
    review = ReviewExecutor()

    # Fan-out includes the meta sidecar so the planner's weights/reasoning
    # ride into the fan-in via the same typed channel as the scorers.
    scorers_and_meta = [grid, water, competition, land, hazard, precedent, meta]

    builder = WorkflowBuilder(start_executor=planner)  # type: ignore[call-arg]
    builder = builder.add_edge(planner, retrieval)
    builder = builder.add_fan_out_edges(retrieval, scorers_and_meta)
    builder = builder.add_fan_in_edges(scorers_and_meta, aggregator)
    builder = builder.add_edge(aggregator, evidence)
    builder = builder.add_edge(evidence, review)
    return builder.build()


async def audit_site_v2(
    *,
    user_assertion: str,
    lat: float,
    lng: float,
    claimed_mw: float,
    user_query: str | None = None,
    workspace_id: str | None = None,
    lakehouse_id: str | None = None,
) -> dict[str, Any]:
    """v2 implementation of :func:`agents.site_audit.audit_site` using a MAF
    :class:`WorkflowBuilder` graph (planner → fan-out → 6 scorers + meta →
    fan-in aggregator → evidence → review).

    Returns the same JSON shape as v1 plus ``engine: "maf_workflow_v2"``,
    ``planner: {...}``, ``skipped_dimensions: [...]``, and (when
    ``SITE_REVIEW=1``) a ``review: {...}`` block.
    """
    if not is_available():
        raise RuntimeError(
            "audit_site_v2 called but Microsoft Agent Framework is not "
            "installed. Set SITE_AUDIT_V2=0 or install agent-framework-core."
        )

    ws = workspace_id or DEFAULT_WORKSPACE_ID
    lh = lakehouse_id or DEFAULT_LAKEHOUSE_ID

    spec = SiteSpec(
        user_assertion=user_assertion,
        lat=lat,
        lng=lng,
        claimed_mw=claimed_mw,
        user_query=user_query,
        workspace_id=ws,
        lakehouse_id=lh,
    )

    workflow = _build_workflow(spec, ws, lh)
    result = await workflow.run(spec)
    outputs = result.get_outputs()
    if not outputs:
        raise RuntimeError(
            "MAF workflow completed with no outputs — review executor "
            "failed to yield a dossier. Check executor logs."
        )
    # ReviewExecutor yields exactly one (final, enriched) dossier.
    return outputs[-1]


async def audit_site_v2_stream(
    *,
    user_assertion: str,
    lat: float,
    lng: float,
    claimed_mw: float,
    user_query: str | None = None,
    workspace_id: str | None = None,
    lakehouse_id: str | None = None,
) -> AsyncIterator[dict[str, Any]]:
    """Streaming variant — yields ``{type, executor_id, payload?}`` events
    as the workflow progresses, ending with the final
    ``{type: "output", payload: <dossier>}`` event.

    Consumed by the SSE endpoint ``/api/sites/audit/stream`` so the UI can
    render dimension scores as they arrive instead of waiting for the
    whole graph to settle.
    """
    if not is_available():
        raise RuntimeError(
            "audit_site_v2_stream called but Microsoft Agent Framework is not "
            "installed. Set SITE_AUDIT_V2=0 or install agent-framework-core."
        )

    ws = workspace_id or DEFAULT_WORKSPACE_ID
    lh = lakehouse_id or DEFAULT_LAKEHOUSE_ID
    spec = SiteSpec(
        user_assertion=user_assertion,
        lat=lat,
        lng=lng,
        claimed_mw=claimed_mw,
        user_query=user_query,
        workspace_id=ws,
        lakehouse_id=lh,
    )
    workflow = _build_workflow(spec, ws, lh)

    async for event in workflow.run(spec, stream=True):  # type: ignore[union-attr]
        ev_type = getattr(event, "type", None) or event.__class__.__name__
        out: dict[str, Any] = {"type": str(ev_type)}
        # `executor_id` is a plain attribute on lifecycle/output/data events.
        # `source_executor_id` is a property that raises on non-request_info
        # events, so we explicitly do not touch it here.
        eid = getattr(event, "executor_id", None)
        if eid:
            out["executor_id"] = eid
        data = getattr(event, "data", None)
        if data is not None:
            # Dossiers come through as dicts; other payloads (DimensionResult,
            # RetrievalBundle) are dataclasses → render via repr for the
            # stream consumer.
            if isinstance(data, dict):
                out["payload"] = data
            else:
                out["payload_type"] = type(data).__name__
        details = getattr(event, "details", None)
        if details is not None:
            out["details"] = str(details)
        yield out
