"""MAF :class:`Executor` wrappers around the deterministic scoring
functions defined in :mod:`agents.site_audit`.

Each executor is a thin (~15 line) shim that:

1. Receives a :class:`RetrievalBundle` (Fabric DataFrames pre-loaded by
   :class:`RetrievalExecutor`).
2. Calls the matching ``_score_*`` function from ``agents.site_audit``.
3. Emits a :class:`DimensionResult` which the aggregator collects.

When ``agent_framework`` isn't importable (lean dev envs / CI smoke runs)
each class degrades to a plain ``object`` so the module still imports;
callers must check :func:`workflow.is_available` before invoking
:func:`workflow.audit_site_v2`.
"""

from __future__ import annotations

import asyncio
import logging
import os
import time
from datetime import datetime, timezone
from typing import Any

logger = logging.getLogger(__name__)

# ── Agent Framework imports (graceful fallback) ──────────────────────────────
try:
    from agent_framework import (  # type: ignore
        Executor,
        WorkflowContext,
        handler,
    )
    from typing_extensions import Never  # type: ignore
    AGENT_FRAMEWORK_AVAILABLE = True
except Exception as exc:  # pragma: no cover
    logger.info("agent_framework not available (%s); site_intel executors are stubs", exc)
    AGENT_FRAMEWORK_AVAILABLE = False
    Executor = object  # type: ignore
    handler = lambda f: f  # type: ignore  # noqa: E731

    class WorkflowContext:  # type: ignore
        """Stand-in so type hints resolve at import time."""

    Never = None  # type: ignore

# Re-use the legacy scoring functions and data loaders verbatim — v1 and v2
# must produce identical numbers, which is the parity guarantee that lets us
# A/B the feature flag in production.
from agents.site_audit import (  # noqa: E402
    _MPC_ANCHOR_COLLECTIONS,
    _load_table,
    _score_competition,
    _score_hazards_with_mpc,
    _score_parcel_match,
    _score_power,
    _score_precedent_with_search,
    _score_water,
    DEFAULT_LAKEHOUSE_ID,
    DEFAULT_WORKSPACE_ID,
)

from .messages import DimensionResult, PlannedSpec, RetrievalBundle, SiteSpec


# ──────────────────────────────────────────────────────────────────────────────
# Confidence scoring
# ──────────────────────────────────────────────────────────────────────────────
# Cheap heuristic: confidence is a function of how much evidence the
# deterministic scorer was able to attach. We expose it as a 3-bucket label
# (``low``/``medium``/``high``) so the UI can render it without having to
# reason about per-source quality.
def _confidence_from_evidence(evidence: list[Any], threshold_low: int = 1, threshold_high: int = 3) -> str:
    n = len(evidence) if evidence else 0
    if n == 0:
        return "low"
    if n < threshold_high:
        return "medium"
    return "high"


def _confidence_from_rows(row_count: int) -> str:
    """Fabric-table-based confidence — used by the lakehouse scorers when
    their evidence list is empty (e.g., no nearby substations) but the table
    itself was retrieved successfully."""
    if row_count <= 0:
        return "low"
    if row_count < 100:
        return "medium"
    return "high"


def _skipped(dim: str) -> DimensionResult:
    """Stub :class:`DimensionResult` for dimensions the planner deselected.

    Returned by scorers when their dimension is not in
    ``bundle.active_dimensions``. Aggregator filters these out of the
    weighted overall.
    """
    return DimensionResult(
        dimension=dim,
        score=None,
        summary=f"Skipped — planner did not select '{dim}' for this query.",
        evidence=[],
        provenance=[],
        skipped=True,
    )


# ──────────────────────────────────────────────────────────────────────────────
# RetrievalBundle cache
# ──────────────────────────────────────────────────────────────────────────────
# The four Fabric Delta tables are workspace-wide and effectively static
# within a session — re-loading them on every audit pin is wasteful (each
# load is a Lakehouse SQL endpoint round-trip plus pandas materialization).
# A small in-process LRU keyed by (workspace, lakehouse, assertion-prefix)
# and bounded by TTL eliminates the duplicate I/O without making the cache
# stale across deploys (process restart clears it).
import time  # noqa: E402

_RETRIEVAL_CACHE_TTL_SECONDS = int(os.getenv("SITE_INTEL_CACHE_TTL", "600"))
_RETRIEVAL_CACHE_MAX = 16
_RETRIEVAL_CACHE: dict[tuple[str, str, str], tuple[float, tuple[Any, Any, Any, Any]]] = {}


def _cache_key(assertion: str, ws: str, lh: str) -> tuple[str, str, str]:
    # Hash the assertion so we don't keep raw tokens in memory; the prefix is
    # enough to scope per-user without leaking anything.
    import hashlib
    return (
        hashlib.sha256((assertion or "").encode("utf-8")).hexdigest()[:16],
        ws,
        lh,
    )


def _cache_get(key: tuple[str, str, str]) -> tuple[Any, Any, Any, Any] | None:
    entry = _RETRIEVAL_CACHE.get(key)
    if entry is None:
        return None
    inserted_at, frames = entry
    if time.time() - inserted_at > _RETRIEVAL_CACHE_TTL_SECONDS:
        _RETRIEVAL_CACHE.pop(key, None)
        return None
    return frames


def _cache_put(key: tuple[str, str, str], frames: tuple[Any, Any, Any, Any]) -> None:
    if len(_RETRIEVAL_CACHE) >= _RETRIEVAL_CACHE_MAX:
        # Drop oldest entry (cheapest possible eviction; cache is tiny).
        oldest = min(_RETRIEVAL_CACHE.items(), key=lambda kv: kv[1][0])[0]
        _RETRIEVAL_CACHE.pop(oldest, None)
    _RETRIEVAL_CACHE[key] = (time.time(), frames)


# ──────────────────────────────────────────────────────────────────────────────
# Retrieval — start of the graph; loads the four Fabric Delta tables in
# parallel and fans the bundle out to all six scorers.
# ──────────────────────────────────────────────────────────────────────────────
class RetrievalExecutor(Executor):  # type: ignore[misc]
    """Loads the four Fabric Lakehouse tables concurrently.

    Mirrors the first ``asyncio.gather`` block of :func:`agents.site_audit.audit_site`
    but emits the resulting frames as a single :class:`RetrievalBundle` so the
    six scoring executors don't each re-read the lakehouse.
    """

    def __init__(self, id: str = "retrieval") -> None:
        if AGENT_FRAMEWORK_AVAILABLE:
            super().__init__(id=id)
        self.id = id

    if AGENT_FRAMEWORK_AVAILABLE:
        @handler  # type: ignore
        async def on_message(
            self,
            planned: PlannedSpec,
            ctx: "WorkflowContext[RetrievalBundle]",
        ) -> None:
            spec = planned.spec
            ws = spec.workspace_id or DEFAULT_WORKSPACE_ID
            lh = spec.lakehouse_id or DEFAULT_LAKEHOUSE_ID

            key = _cache_key(spec.user_assertion, ws, lh)
            cached = _cache_get(key)
            if cached is not None:
                logger.info("[RETRIEVAL] cache hit for ws=%s lh=%s", ws, lh)
                sites, power, water, dcs = cached
            else:
                logger.info("[RETRIEVAL] cache miss; loading 4 Fabric tables")
                sites, power, water, dcs = await asyncio.gather(
                    _load_table("candidate_sites", spec.user_assertion, ws, lh),
                    _load_table("power_infrastructure", spec.user_assertion, ws, lh),
                    _load_table("water_assets", spec.user_assertion, ws, lh),
                    _load_table("existing_data_centers", spec.user_assertion, ws, lh),
                )
                _cache_put(key, (sites, power, water, dcs))

            bundle = RetrievalBundle(
                spec=spec,
                sites=sites,
                power=power,
                water=water,
                dcs=dcs,
                workspace_id=ws,
                lakehouse_id=lh,
                active_dimensions=set(planned.active_dimensions),
                weights=dict(planned.weights),
                planner_reasoning=planned.planner_reasoning,
                planner_engine=planned.planner_engine,
            )
            await ctx.send_message(bundle)


# ──────────────────────────────────────────────────────────────────────────────
# Six scoring executors — each wraps one existing ``_score_*`` function and
# emits a DimensionResult. They all subscribe to RetrievalBundle so the
# framework fans the bundle to all of them in parallel.
# ──────────────────────────────────────────────────────────────────────────────
class GridExecutor(Executor):  # type: ignore[misc]
    """Power / grid scoring — wraps :func:`_score_power`."""

    def __init__(self, id: str = "grid") -> None:
        if AGENT_FRAMEWORK_AVAILABLE:
            super().__init__(id=id)
        self.id = id

    if AGENT_FRAMEWORK_AVAILABLE:
        @handler  # type: ignore
        async def on_message(
            self,
            bundle: RetrievalBundle,
            ctx: "WorkflowContext[DimensionResult]",
        ) -> None:
            if "power" not in bundle.active_dimensions:
                await ctx.send_message(_skipped("power"))
                return
            dim = _score_power(
                bundle.spec.lat,
                bundle.spec.lng,
                bundle.spec.claimed_mw,
                bundle.power,
            )
            await ctx.send_message(DimensionResult(
                dimension="power",
                score=dim.score,
                summary=dim.summary,
                evidence=dim.evidence,
                provenance=[{"source": "fabric_lakehouse", "table": "power_infrastructure",
                             "rows": int(len(bundle.power))}],
            ))


class WaterExecutor(Executor):  # type: ignore[misc]
    """Water / cooling scoring — wraps :func:`_score_water`."""

    def __init__(self, id: str = "water") -> None:
        if AGENT_FRAMEWORK_AVAILABLE:
            super().__init__(id=id)
        self.id = id

    if AGENT_FRAMEWORK_AVAILABLE:
        @handler  # type: ignore
        async def on_message(
            self,
            bundle: RetrievalBundle,
            ctx: "WorkflowContext[DimensionResult]",
        ) -> None:
            if "water" not in bundle.active_dimensions:
                await ctx.send_message(_skipped("water"))
                return
            dim = _score_water(bundle.spec.lat, bundle.spec.lng, bundle.water)
            await ctx.send_message(DimensionResult(
                dimension="water",
                score=dim.score,
                summary=dim.summary,
                evidence=dim.evidence,
                provenance=[{"source": "fabric_lakehouse", "table": "water_assets",
                             "rows": int(len(bundle.water))}],
            ))


class CompetitionExecutor(Executor):  # type: ignore[misc]
    """Competition scoring — wraps :func:`_score_competition`."""

    def __init__(self, id: str = "competition") -> None:
        if AGENT_FRAMEWORK_AVAILABLE:
            super().__init__(id=id)
        self.id = id

    if AGENT_FRAMEWORK_AVAILABLE:
        @handler  # type: ignore
        async def on_message(
            self,
            bundle: RetrievalBundle,
            ctx: "WorkflowContext[DimensionResult]",
        ) -> None:
            if "competition" not in bundle.active_dimensions:
                await ctx.send_message(_skipped("competition"))
                return
            dim = _score_competition(bundle.spec.lat, bundle.spec.lng, bundle.dcs)
            await ctx.send_message(DimensionResult(
                dimension="competition",
                score=dim.score,
                summary=dim.summary,
                evidence=dim.evidence,
                provenance=[{"source": "fabric_lakehouse", "table": "existing_data_centers",
                             "rows": int(len(bundle.dcs))}],
            ))


class LandExecutor(Executor):  # type: ignore[misc]
    """Parcel-match scoring — wraps :func:`_score_parcel_match`."""

    def __init__(self, id: str = "land") -> None:
        if AGENT_FRAMEWORK_AVAILABLE:
            super().__init__(id=id)
        self.id = id

    if AGENT_FRAMEWORK_AVAILABLE:
        @handler  # type: ignore
        async def on_message(
            self,
            bundle: RetrievalBundle,
            ctx: "WorkflowContext[DimensionResult]",
        ) -> None:
            if "parcel_match" not in bundle.active_dimensions:
                await ctx.send_message(_skipped("parcel_match"))
                return
            dim = _score_parcel_match(bundle.spec.lat, bundle.spec.lng, bundle.sites)
            await ctx.send_message(DimensionResult(
                dimension="parcel_match",
                score=dim.score,
                summary=dim.summary,
                evidence=dim.evidence,
                provenance=[{"source": "fabric_lakehouse", "table": "candidate_sites",
                             "rows": int(len(bundle.sites))}],
            ))


class HazardExecutor(Executor):  # type: ignore[misc]
    """Hazards scoring via Planetary Computer raster sampling.

    Wraps :func:`_score_hazards_with_mpc`, which itself performs dynamic
    collection discovery via :class:`CollectionMapper` plus the two anchor
    collections (``io-lulc-9-class``, ``cop-dem-glo-30``).
    """

    def __init__(self, id: str = "hazard") -> None:
        if AGENT_FRAMEWORK_AVAILABLE:
            super().__init__(id=id)
        self.id = id

    if AGENT_FRAMEWORK_AVAILABLE:
        @handler  # type: ignore
        async def on_message(
            self,
            bundle: RetrievalBundle,
            ctx: "WorkflowContext[DimensionResult]",
        ) -> None:
            if "hazards" not in bundle.active_dimensions:
                await ctx.send_message(_skipped("hazards"))
                return
            dim = await _score_hazards_with_mpc(
                bundle.spec.lat, bundle.spec.lng, bundle.spec.user_query,
            )
            dynamic = [
                ev["collection"]
                for ev in dim.evidence
                if ev.get("kind") == "mpc_dynamic_match"
                and ev.get("item_id")
                and ev.get("collection")
            ]
            await ctx.send_message(DimensionResult(
                dimension="hazards",
                score=dim.score,
                summary=dim.summary,
                evidence=dim.evidence,
                provenance=[{
                    "source": "planetary_computer",
                    "collections": list(_MPC_ANCHOR_COLLECTIONS) + dynamic,
                    "dynamic_match_query": bundle.spec.user_query,
                }],
            ))


class PrecedentExecutor(Executor):  # type: ignore[misc]
    """Precedent scoring via Azure AI Search — wraps :func:`_score_precedent_with_search`."""

    def __init__(self, id: str = "precedent") -> None:
        if AGENT_FRAMEWORK_AVAILABLE:
            super().__init__(id=id)
        self.id = id

    if AGENT_FRAMEWORK_AVAILABLE:
        @handler  # type: ignore
        async def on_message(
            self,
            bundle: RetrievalBundle,
            ctx: "WorkflowContext[DimensionResult]",
        ) -> None:
            if "precedent" not in bundle.active_dimensions:
                await ctx.send_message(_skipped("precedent"))
                return
            import os
            dim = await _score_precedent_with_search(
                bundle.spec.user_assertion,
                bundle.workspace_id,
                bundle.spec.lat,
                bundle.spec.lng,
                bundle.spec.claimed_mw,
            )
            await ctx.send_message(DimensionResult(
                dimension="precedent",
                score=dim.score,
                summary=dim.summary,
                evidence=dim.evidence,
                provenance=[{
                    "source": "azure_ai_search",
                    "index": os.getenv("FABRIC_DOC_SEARCH_INDEX", "permitting-docs"),
                }],
            ))


# ──────────────────────────────────────────────────────────────────────────────
# Meta — tiny sidecar executor that fans out from RetrievalBundle alongside
# the six scorers and carries the planner's chosen weights / reasoning into
# the fan-in. Encoded as a sentinel :class:`DimensionResult` with
# ``dimension == "_meta"`` so it travels through the same typed channel.
# ──────────────────────────────────────────────────────────────────────────────
class MetaExecutor(Executor):  # type: ignore[misc]
    """Forwards planner metadata to the aggregator via the fan-in channel.

    A separate executor (rather than stuffing this onto one of the real
    scorers) keeps the responsibility clear and lets the aggregator pull
    weights/reasoning out of the batch by dimension name.
    """

    def __init__(self, id: str = "meta") -> None:
        if AGENT_FRAMEWORK_AVAILABLE:
            super().__init__(id=id)
        self.id = id

    if AGENT_FRAMEWORK_AVAILABLE:
        @handler  # type: ignore
        async def on_message(
            self,
            bundle: RetrievalBundle,
            ctx: "WorkflowContext[DimensionResult]",
        ) -> None:
            await ctx.send_message(DimensionResult(
                dimension="_meta",
                score=None,
                summary=bundle.planner_reasoning,
                evidence=[],
                provenance=[{
                    "source": "planner",
                    "engine": bundle.planner_engine,
                    "active_dimensions": sorted(bundle.active_dimensions),
                    "weights": bundle.weights,
                    "reasoning": bundle.planner_reasoning,
                }],
                skipped=True,
            ))


# ──────────────────────────────────────────────────────────────────────────────
# Aggregator — fan-in of all 6 DimensionResults; assembles the same JSON
# contract as :func:`agents.site_audit.audit_site` so the web UI is unchanged.
# ──────────────────────────────────────────────────────────────────────────────

# Same weights as v1. Kept in this module so the planner agent (added later)
# can override per-request without touching v1.
DEFAULT_WEIGHTS: dict[str, float] = {
    "power": 0.35,
    "water": 0.15,
    "hazards": 0.15,
    "competition": 0.10,
    "parcel": 0.10,
    "precedent": 0.15,
}


class AggregatorExecutor(Executor):  # type: ignore[misc]
    """Fan-in node that receives all DimensionResults (6 scorers + the
    ``_meta`` sidecar) in one batched call and forwards the assembled
    dossier downstream to the Evidence/Review chain.

    MAF's :meth:`WorkflowBuilder.add_fan_in_edges` collects every upstream
    output and delivers them as a single ``list[T]`` to the target's
    handler, so the aggregator's handler signature is
    ``on_message(self, dims: list[DimensionResult], ctx)`` and it
    completes in one invocation.
    """

    def __init__(
        self,
        spec: SiteSpec,
        workspace_id: str,
        lakehouse_id: str,
        weights: dict[str, float] | None = None,
        id: str = "aggregator",
    ) -> None:
        if AGENT_FRAMEWORK_AVAILABLE:
            super().__init__(id=id)
        self.id = id
        self._spec = spec
        self._ws = workspace_id
        self._lh = lakehouse_id
        self._default_weights = weights or DEFAULT_WEIGHTS
        self._collected: dict[str, DimensionResult] = {}

    if AGENT_FRAMEWORK_AVAILABLE:
        @handler  # type: ignore
        async def on_message(
            self,
            dims: list[DimensionResult],
            ctx: "WorkflowContext[dict[str, Any]]",
        ) -> None:
            for d in dims:
                self._collected[d.dimension] = d
            # Pull planner metadata out of the batch before assembling.
            meta = self._collected.pop("_meta", None)
            await ctx.send_message(self._build_dossier(meta))

    def _build_dossier(self, meta: DimensionResult | None) -> dict[str, Any]:
        """Assemble the same JSON shape as ``site_audit.audit_site`` returns,
        with planner metadata appended when present."""
        c = self._collected
        # Resolve effective weights — planner override if it ran, else default.
        if meta and meta.provenance:
            weights = dict(meta.provenance[0].get("weights") or self._default_weights)
            planner_engine = meta.provenance[0].get("engine", "default")
            planner_reasoning = meta.provenance[0].get("reasoning", "")
            active_dims = set(meta.provenance[0].get("active_dimensions") or [])
        else:
            weights = dict(self._default_weights)
            planner_engine = "default"
            planner_reasoning = ""
            active_dims = {d.dimension for d in c.values() if not d.skipped}

        # Map dimension keys → weight keys (parcel_match -> parcel)
        weighted_keys = {
            "power": "power",
            "water": "water",
            "hazards": "hazards",
            "competition": "competition",
            "parcel_match": "parcel",
            "precedent": "precedent",
        }
        # Sum weights only over dimensions that actually produced a score, then
        # re-normalize so the overall is a pure weighted mean of the survivors.
        active_weight_sum = sum(
            weights.get(wk, 0.0)
            for dim, wk in weighted_keys.items()
            if dim in c and not c[dim].skipped and c[dim].score is not None
        )
        if active_weight_sum > 0:
            overall = sum(
                (c[dim].score or 0.0) * weights.get(wk, 0.0) / active_weight_sum
                for dim, wk in weighted_keys.items()
                if dim in c and not c[dim].skipped and c[dim].score is not None
            )
        else:
            overall = 0.0

        # Merge provenance, deduping the planetary_computer entry (which can
        # appear once from the Hazard executor) onto the same shape v1 emits.
        provenance: list[dict[str, Any]] = []
        for dim_name in ("parcel_match", "power", "water", "competition", "hazards", "precedent"):
            if dim_name in c and not c[dim_name].skipped:
                provenance.extend(c[dim_name].provenance)

        # Concatenate evidence in v1's order for parity.
        evidence: list[dict[str, Any]] = []
        for dim_name in ("power", "water", "competition", "parcel_match", "hazards", "precedent"):
            if dim_name in c and not c[dim_name].skipped:
                evidence.extend(c[dim_name].evidence)

        def _score(dim: str) -> float | None:
            d = c.get(dim)
            if d is None or d.skipped or d.score is None:
                return None
            return round(d.score, 1)

        dossier: dict[str, Any] = {
            "input": {
                "lat": self._spec.lat,
                "lng": self._spec.lng,
                "claimed_mw": self._spec.claimed_mw,
            },
            "scores": {
                "power": _score("power"),
                "water": _score("water"),
                "hazards": _score("hazards"),
                "competition": _score("competition"),
                "parcel_match": _score("parcel_match"),
                "precedent": _score("precedent"),
                "overall": round(overall, 1),
                "weights": weights,
            },
            "summaries": {
                dim: c[dim].summary for dim in c if not c[dim].skipped
            },
            "skipped_dimensions": sorted(
                d.dimension for d in c.values() if d.skipped
            ),
            "evidence": evidence,
            "data_provenance": provenance,
            "lakehouse": {"workspace_id": self._ws, "lakehouse_id": self._lh},
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "engine": "maf_workflow_v2",
            "planner": {
                "engine": planner_engine,
                "reasoning": planner_reasoning,
                "active_dimensions": sorted(active_dims),
            },
        }
        return dossier
