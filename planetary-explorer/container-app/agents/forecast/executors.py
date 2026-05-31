"""MAF executors for the Forecast Agent."""
from __future__ import annotations

import logging
import time
from typing import Any

from connectors.weather import (
    Capability,
    ForecastQuery as ProviderQuery,
    WeatherModelProvider,
)
from connectors.weather.registry import get_registry

from .ensemble import build_dossier
from .messages import (
    ForecastAgentQuery,
    ForecastDossier,
    ForecastPlan,
    ProviderResult,
)
from .router import RoutingDecision

logger = logging.getLogger(__name__)

try:
    from agent_framework import Executor, WorkflowContext, handler  # type: ignore
    AGENT_FRAMEWORK_AVAILABLE = True
except Exception as exc:  # pragma: no cover
    logger.info("agent_framework not available (%s); forecast executors are stubs", exc)
    AGENT_FRAMEWORK_AVAILABLE = False
    Executor = object  # type: ignore
    handler = lambda f: f  # type: ignore  # noqa: E731

    class WorkflowContext:  # type: ignore
        """Stand-in so type hints resolve at import time."""


def _to_provider_query(q: ForecastAgentQuery, caps: tuple[Capability, ...] | None = None) -> ProviderQuery:
    return ProviderQuery(
        lat=q.lat,
        lon=q.lon,
        lead_hours=q.lead_hours,
        variables=tuple(q.variables),
        grid_size=q.grid_size,
        required_capabilities=caps or (Capability.GLOBAL,),
    )


# ──────────────────────────────────────────────────────────────────────────
# Planner — decides which providers to call
# ──────────────────────────────────────────────────────────────────────────
class PlannerExecutor(Executor):  # type: ignore[misc]
    def __init__(self, id: str = "planner") -> None:
        if AGENT_FRAMEWORK_AVAILABLE:
            super().__init__(id=id)
        self.id = id

    if AGENT_FRAMEWORK_AVAILABLE:
        @handler  # type: ignore
        async def on_message(
            self,
            query: ForecastAgentQuery,
            ctx: "WorkflowContext[ForecastPlan]",
        ) -> None:
            registry = get_registry()
            providers = registry.select(required=(Capability.GLOBAL,))
            if query.requested_providers:
                wanted = set(query.requested_providers)
                providers = [p for p in providers if p.provider_id in wanted]
            ids = tuple(p.provider_id for p in providers)
            reason = (
                f"Configured providers supporting GLOBAL forecast: {list(ids)}"
                if ids
                else "No weather providers configured. Set one or more of "
                     "AURORA_ENDPOINT_URL, EARTH2_FCN_ENDPOINT_URL, "
                     "MAI_WEATHER_ENDPOINT_URL."
            )
            plan = ForecastPlan(query=query, provider_ids=ids, reason=reason)
            await ctx.send_message(plan)


# ──────────────────────────────────────────────────────────────────────────
# ProviderExecutor — invokes one provider and emits a ProviderResult
# ──────────────────────────────────────────────────────────────────────────
class ProviderExecutor(Executor):  # type: ignore[misc]
    """One-per-provider executor. We instantiate N of these at build time
    so each lives at a unique node in the graph."""

    def __init__(self, provider_id: str, id: str | None = None) -> None:
        if AGENT_FRAMEWORK_AVAILABLE:
            super().__init__(id=id or f"provider:{provider_id}")
        self.id = id or f"provider:{provider_id}"
        self._provider_id = provider_id

    if AGENT_FRAMEWORK_AVAILABLE:
        @handler  # type: ignore
        async def on_message(
            self,
            plan: ForecastPlan,
            ctx: "WorkflowContext[ProviderResult]",
        ) -> None:
            # Every fan-out branch MUST emit (avoid the add_fan_in_edges deadlock).
            provider: WeatherModelProvider | None = get_registry().get(self._provider_id)
            if provider is None:
                await ctx.send_message(ProviderResult(
                    provider_id=self._provider_id,
                    vendor="unknown",
                    bundle=None,
                    error="provider not in registry",
                ))
                return
            if self._provider_id not in plan.provider_ids:
                # Not selected for this query — emit empty so fan-in still fires.
                await ctx.send_message(ProviderResult(
                    provider_id=self._provider_id,
                    vendor=provider.vendor,
                    bundle=None,
                    error="skipped (not in plan)",
                ))
                return
            started = time.perf_counter()
            try:
                bundle = await provider.forecast(_to_provider_query(plan.query))
                elapsed = int((time.perf_counter() - started) * 1000)
                await ctx.send_message(ProviderResult(
                    provider_id=provider.provider_id,
                    vendor=provider.vendor,
                    bundle=bundle,
                    latency_ms=elapsed,
                ))
            except Exception as exc:  # noqa: BLE001
                elapsed = int((time.perf_counter() - started) * 1000)
                logger.warning("provider %s failed: %s", provider.provider_id, exc)
                await ctx.send_message(ProviderResult(
                    provider_id=provider.provider_id,
                    vendor=provider.vendor,
                    bundle=None,
                    error=str(exc),
                    latency_ms=elapsed,
                ))


# ──────────────────────────────────────────────────────────────────────────
# Aggregator — fan-in, build dossier, yield_output
# ──────────────────────────────────────────────────────────────────────────
class AggregatorExecutor(Executor):  # type: ignore[misc]
    def __init__(
        self,
        query: ForecastAgentQuery,
        started_at: float,
        decision: RoutingDecision | None = None,
        id: str = "aggregator",
    ) -> None:
        if AGENT_FRAMEWORK_AVAILABLE:
            super().__init__(id=id)
        self.id = id
        self._query = query
        self._started_at = started_at
        self._decision = decision

    if AGENT_FRAMEWORK_AVAILABLE:
        @handler  # type: ignore
        async def on_message(
            self,
            messages: list[Any],
            ctx: "WorkflowContext[Any, dict[str, Any]]",
        ) -> None:
            results = [m for m in messages if isinstance(m, ProviderResult)]
            # Drop "skipped" entries so the dossier reflects what was actually planned.
            results = [r for r in results if not (r.bundle is None and r.error == "skipped (not in plan)")]
            workflow_ms = int((time.perf_counter() - self._started_at) * 1000)
            routing = self._decision.as_dict() if self._decision is not None else {}
            dossier = build_dossier(
                self._query, results,
                workflow_ms=workflow_ms,
                routing=routing,
            )
            # Serialize dataclass -> dict for JSON-friendly output
            from dataclasses import asdict
            await ctx.yield_output(asdict(dossier))
