"""Forecast Agent workflow — MAF path + direct (non-MAF) fallback."""
from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import asdict
from typing import Any

from connectors.weather import Capability, ForecastQuery as ProviderQuery
from connectors.weather.registry import get_registry

from .ensemble import build_dossier
from .messages import ForecastAgentQuery, ProviderResult
from .router import RoutingDecision, route

logger = logging.getLogger(__name__)

try:
    from agent_framework import WorkflowBuilder  # type: ignore
    AGENT_FRAMEWORK_AVAILABLE = True
except Exception as exc:  # pragma: no cover
    logger.info("agent_framework not available (%s); forecast MAF workflow disabled", exc)
    AGENT_FRAMEWORK_AVAILABLE = False
    WorkflowBuilder = None  # type: ignore


from .executors import (
    AGENT_FRAMEWORK_AVAILABLE as _EXECUTORS_OK,
    AggregatorExecutor,
    PlannerExecutor,
    ProviderExecutor,
)


def is_available() -> bool:
    return AGENT_FRAMEWORK_AVAILABLE and _EXECUTORS_OK


def _provider_ids_for_build() -> list[str]:
    """All currently-configured provider ids, in registry order."""
    return [p.provider_id for p in get_registry().all]


def _build_workflow(query: ForecastAgentQuery, started_at: float):
    if not is_available():
        raise RuntimeError("MAF not available; use forecast_direct instead.")
    pids = _provider_ids_for_build()
    if not pids:
        raise RuntimeError(
            "No weather providers configured. Set one or more of "
            "AURORA_ENDPOINT_URL, EARTH2_FCN_ENDPOINT_URL, "
            "MAI_WEATHER_ENDPOINT_URL before running the forecast workflow."
        )

    planner = PlannerExecutor()
    provider_executors = [ProviderExecutor(pid) for pid in pids]
    aggregator = AggregatorExecutor(query=query, started_at=started_at)

    builder = WorkflowBuilder(start_executor=planner)  # type: ignore[call-arg]
    builder = builder.add_fan_out_edges(planner, provider_executors)
    builder = builder.add_fan_in_edges(provider_executors, aggregator)
    return builder.build()


# ── Public entry points ──────────────────────────────────────────────────
async def forecast(query: ForecastAgentQuery) -> dict[str, Any]:
    """Run the MAF workflow. Falls back to direct path when MAF missing."""
    if not is_available():
        return await forecast_direct(query)
    started = time.perf_counter()
    workflow = _build_workflow(query, started_at=started)
    result = await workflow.run(query)
    outputs = result.get_outputs()
    if not outputs:
        raise RuntimeError(
            "Forecast workflow completed with no outputs — aggregator did not "
            "yield_output. Check executor logs."
        )
    return outputs[-1]


async def forecast_direct(query: ForecastAgentQuery) -> dict[str, Any]:
    """Non-MAF code path — calls providers in parallel via asyncio.gather.

    Used when ``agent_framework`` is not installed. Produces an identical
    dossier shape so the API contract is preserved.
    """
    started = time.perf_counter()
    registry = get_registry()
    decision = await route(query, registry.all)
    providers = [registry.get(pid) for pid in decision.provider_ids]
    providers = [p for p in providers if p is not None]

    if not providers:
        dossier = build_dossier(
            query, results=[],
            workflow_ms=int((time.perf_counter() - started) * 1000),
            routing=decision.as_dict(),
        )
        d = asdict(dossier)
        d["note"] = (
            "No weather providers configured. Set one or more of "
            "AURORA_ENDPOINT_URL, EARTH2_FCN_ENDPOINT_URL, "
            "MAI_WEATHER_ENDPOINT_URL to enable the Forecast Agent."
        )
        return d

    pquery = ProviderQuery(
        lat=query.lat,
        lon=query.lon,
        lead_hours=query.lead_hours,
        variables=tuple(query.variables),
        grid_size=query.grid_size,
        required_capabilities=decision.required_capabilities or (Capability.GLOBAL,),
    )

    async def _one(p):
        t0 = time.perf_counter()
        try:
            bundle = await p.forecast(pquery)
            return ProviderResult(
                provider_id=p.provider_id, vendor=p.vendor,
                bundle=bundle,
                latency_ms=int((time.perf_counter() - t0) * 1000),
            )
        except Exception as exc:  # noqa: BLE001
            logger.warning("provider %s failed: %s", p.provider_id, exc)
            return ProviderResult(
                provider_id=p.provider_id, vendor=p.vendor,
                bundle=None, error=str(exc),
                latency_ms=int((time.perf_counter() - t0) * 1000),
            )

    results = await asyncio.gather(*[_one(p) for p in providers])
    dossier = build_dossier(
        query, results=list(results),
        workflow_ms=int((time.perf_counter() - started) * 1000),
        routing=decision.as_dict(),
    )
    return asdict(dossier)
