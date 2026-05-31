"""Resilience MAF workflow — assembles the fan-out/fan-in graph and exposes
:func:`assess_resilience` (plus a streaming variant).

Topology
--------
::

    Retrieval ──► (fan-out)
                    ├── WeatherExecutor      ──┐
                    ├── SupplyGraphExecutor  ──┤   fan-in
                    └── ContextExecutor      ──┴───► Aggregator
"""

from __future__ import annotations

import logging
from typing import Any, AsyncIterator

logger = logging.getLogger(__name__)

try:
    from agent_framework import WorkflowBuilder  # type: ignore
    AGENT_FRAMEWORK_AVAILABLE = True
except Exception as exc:  # pragma: no cover
    logger.info("agent_framework not available (%s); resilience workflow disabled", exc)
    AGENT_FRAMEWORK_AVAILABLE = False
    WorkflowBuilder = None  # type: ignore

from .executors import (
    AGENT_FRAMEWORK_AVAILABLE as _EXECUTORS_OK,
    AggregatorExecutor,
    ContextExecutor,
    RetrievalExecutor,
    SupplyGraphExecutor,
    WeatherExecutor,
)
from .messages import ALL_HAZARDS, ResilienceQuery


def is_available() -> bool:
    """True when MAF is importable and the resilience module is safe to use."""
    return AGENT_FRAMEWORK_AVAILABLE and _EXECUTORS_OK


def _build_workflow(query: ResilienceQuery):
    """Construct a fresh workflow graph for one assessment.

    A new graph is built per request because the aggregator carries
    per-run state. Construction is microsecond-cheap — cost is dominated
    by the Open-Meteo + Fabric + AI Search calls inside the executors.
    """
    if not is_available():
        raise RuntimeError(
            "Microsoft Agent Framework not available; cannot build resilience workflow."
        )

    retrieval = RetrievalExecutor()
    weather = WeatherExecutor()
    supply = SupplyGraphExecutor()
    context = ContextExecutor()
    aggregator = AggregatorExecutor(query=query)

    fanout = [weather, supply, context]

    builder = WorkflowBuilder(start_executor=retrieval)  # type: ignore[call-arg]
    builder = builder.add_fan_out_edges(retrieval, fanout)
    builder = builder.add_fan_in_edges(fanout, aggregator)
    return builder.build()


async def assess_resilience(
    *,
    user_assertion: str,
    region_filter: str | None = None,
    horizon_days: int = 7,
    hazards: tuple[str, ...] | list[str] | None = None,
    user_query: str | None = None,
    workspace_id: str | None = None,
    lakehouse_id: str | None = None,
) -> dict[str, Any]:
    """Run a resilience assessment over the (filtered) facility registry.

    Returns the dossier JSON described in :func:`executors._build_dossier`.
    """
    if not is_available():
        raise RuntimeError(
            "assess_resilience called but Microsoft Agent Framework is not "
            "installed. Set RESILIENCE_MVP=0 or install agent-framework-core."
        )

    hazards_tuple: tuple[str, ...] = tuple(hazards) if hazards else ALL_HAZARDS

    query = ResilienceQuery(
        user_assertion=user_assertion,
        region_filter=region_filter,
        horizon_days=horizon_days,
        hazards=hazards_tuple,
        user_query=user_query,
        workspace_id=workspace_id,
        lakehouse_id=lakehouse_id,
    )

    workflow = _build_workflow(query)
    result = await workflow.run(query)
    outputs = result.get_outputs()
    if not outputs:
        raise RuntimeError(
            "MAF workflow completed with no outputs — aggregator failed to "
            "emit a dossier. Check executor logs."
        )
    return outputs[-1]


async def assess_resilience_stream(
    *,
    user_assertion: str,
    region_filter: str | None = None,
    horizon_days: int = 7,
    hazards: tuple[str, ...] | list[str] | None = None,
    user_query: str | None = None,
    workspace_id: str | None = None,
    lakehouse_id: str | None = None,
) -> AsyncIterator[dict[str, Any]]:
    """Streaming variant — yields workflow lifecycle events as JSON dicts.

    Same contract as ``site_intel.audit_site_v2_stream``: emits one event
    per executor lifecycle transition; the final ``output`` event carries
    the dossier.
    """
    if not is_available():
        raise RuntimeError(
            "assess_resilience_stream called but Microsoft Agent Framework "
            "is not installed."
        )

    hazards_tuple: tuple[str, ...] = tuple(hazards) if hazards else ALL_HAZARDS

    query = ResilienceQuery(
        user_assertion=user_assertion,
        region_filter=region_filter,
        horizon_days=horizon_days,
        hazards=hazards_tuple,
        user_query=user_query,
        workspace_id=workspace_id,
        lakehouse_id=lakehouse_id,
    )

    workflow = _build_workflow(query)

    async for event in workflow.run(query, stream=True):  # type: ignore[union-attr]
        ev_type = getattr(event, "type", None) or event.__class__.__name__
        out: dict[str, Any] = {"type": str(ev_type)}
        eid = getattr(event, "executor_id", None)
        if eid:
            out["executor_id"] = eid
        data = getattr(event, "data", None)
        if data is not None:
            if isinstance(data, dict):
                out["payload"] = data
            else:
                out["payload_type"] = type(data).__name__
        details = getattr(event, "details", None)
        if details is not None:
            out["details"] = str(details)
        yield out
