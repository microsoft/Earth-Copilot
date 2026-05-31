"""MAF :class:`Executor` wrappers for the Resilience workflow.

Topology (mirrors the docstring in ``__init__.py``):

    ResilienceQuery
        │
        ▼
    RetrievalExecutor
        │  fan-out
        ├──► WeatherExecutor       (Open-Meteo forecasts + hazard scoring,
        │                           emits HazardForecast per hazard via
        │                           multiple ctx.send_message calls)
        ├──► SupplyGraphExecutor   (waits for HazardForecasts via a shared
        │                           buffer; actually receives a copy of the
        │                           FacilityRegistry to know edges)
        └──► ContextExecutor       (Azure AI Search BCP docs)
        │  fan-in
        ▼
    AggregatorExecutor

To keep the MVP simple, ``WeatherExecutor`` does both forecast retrieval
and hazard scoring (Open-Meteo is fast and the scoring is cheap). A v2
would split scoring per hazard for parallelism.
"""

from __future__ import annotations

import asyncio
import logging
import os
from typing import Any

logger = logging.getLogger(__name__)

# ── Agent Framework imports (graceful fallback) ──────────────────────────
try:
    from agent_framework import (  # type: ignore
        Executor,
        WorkflowContext,
        handler,
    )
    AGENT_FRAMEWORK_AVAILABLE = True
except Exception as exc:  # pragma: no cover
    logger.info("agent_framework not available (%s); resilience executors are stubs", exc)
    AGENT_FRAMEWORK_AVAILABLE = False
    Executor = object  # type: ignore
    handler = lambda f: f  # type: ignore  # noqa: E731

    class WorkflowContext:  # type: ignore
        """Stand-in so type hints resolve at import time."""

# Try to import the Fabric AI Search adapter — optional at MVP.
try:
    import fabric_client  # type: ignore
    FABRIC_CLIENT_AVAILABLE = True
except Exception as exc:  # pragma: no cover
    logger.info("fabric_client not available (%s); resilience context executor will skip AI Search", exc)
    fabric_client = None  # type: ignore
    FABRIC_CLIENT_AVAILABLE = False

from .data_loader import DEFAULT_LAKEHOUSE_ID, DEFAULT_WORKSPACE_ID, load_bcp_playbooks, load_registry
from .messages import (
    ALL_HAZARDS,
    ContextSnippets,
    FacilityRegistry,
    HazardForecast,
    ResilienceQuery,
    SupplyImpact,
)
from .risk_scoring import SCORERS
from .weather import fetch_forecasts

# Search index that holds the BCP / playbook docs. Override per-env.
BCP_SEARCH_INDEX = os.getenv("RESILIENCE_BCP_SEARCH_INDEX", "planetary-explorer-resilience-docs")


# ──────────────────────────────────────────────────────────────────────────
# Retrieval
# ──────────────────────────────────────────────────────────────────────────
class RetrievalExecutor(Executor):  # type: ignore[misc]
    """Loads the facility + supply-edge registry once, then fans out."""

    def __init__(self, id: str = "retrieval") -> None:
        if AGENT_FRAMEWORK_AVAILABLE:
            super().__init__(id=id)
        self.id = id

    if AGENT_FRAMEWORK_AVAILABLE:
        @handler  # type: ignore
        async def on_message(
            self,
            query: ResilienceQuery,
            ctx: "WorkflowContext[FacilityRegistry]",
        ) -> None:
            facilities, edges, source = await load_registry(
                user_assertion=query.user_assertion,
                workspace_id=query.workspace_id,
                lakehouse_id=query.lakehouse_id,
                region_filter=query.region_filter,
            )
            bundle = FacilityRegistry(
                query=query,
                facilities=facilities,
                supply_edges=edges,
                data_source=source,
                workspace_id=query.workspace_id or DEFAULT_WORKSPACE_ID,
                lakehouse_id=query.lakehouse_id or DEFAULT_LAKEHOUSE_ID,
            )
            await ctx.send_message(bundle)


# ──────────────────────────────────────────────────────────────────────────
# Weather + hazard scoring
# ──────────────────────────────────────────────────────────────────────────
class WeatherExecutor(Executor):  # type: ignore[misc]
    """Fetches Open-Meteo forecasts and scores each requested hazard.

    Emits one :class:`HazardForecast` per hazard via repeated
    ``ctx.send_message`` calls; the aggregator fan-in collects all of them.
    """

    def __init__(self, id: str = "weather") -> None:
        if AGENT_FRAMEWORK_AVAILABLE:
            super().__init__(id=id)
        self.id = id

    if AGENT_FRAMEWORK_AVAILABLE:
        @handler  # type: ignore
        async def on_message(
            self,
            bundle: FacilityRegistry,
            ctx: "WorkflowContext[HazardForecast]",
        ) -> None:
            facilities = bundle.facilities
            query = bundle.query
            if facilities.empty:
                for hz in query.hazards:
                    await ctx.send_message(HazardForecast(hazard=hz, facility_risk={}, skipped=True))
                return

            points = [
                {"facility_id": row["facility_id"], "lat": row["lat"], "lng": row["lng"]}
                for _, row in facilities.iterrows()
            ]
            include_aqi = "wildfire" in query.hazards
            forecasts = await fetch_forecasts(
                points, horizon_days=query.horizon_days, include_aqi=include_aqi,
            )
            by_id = {f.facility_id: f for f in forecasts}

            for hz in query.hazards:
                scorer = SCORERS.get(hz)
                if scorer is None:
                    logger.warning("[RESILIENCE] unknown hazard %s; skipping", hz)
                    await ctx.send_message(HazardForecast(hazard=hz, facility_risk={}, skipped=True))
                    continue

                risk: dict[str, dict[str, Any]] = {}
                evidence: list[dict[str, Any]] = []
                for _, row in facilities.iterrows():
                    fid = str(row["facility_id"])
                    fc = by_id.get(fid)
                    if fc is None:
                        continue
                    res = scorer(fc, row)
                    risk[fid] = res
                    if res.get("score") and res["score"] >= 25:
                        evidence.append({
                            "facility_id": fid,
                            "name": row.get("name", fid),
                            "hazard": hz,
                            "score": res["score"],
                            "severity": res["severity"],
                            "peak_value": res.get("peak_value"),
                            "peak_day": res.get("peak_day"),
                            "summary": res.get("summary"),
                        })

                await ctx.send_message(HazardForecast(
                    hazard=hz,
                    facility_risk=risk,
                    evidence=evidence,
                    provenance=[{
                        "source": "open-meteo",
                        "endpoint": "forecast" + (",air-quality" if include_aqi else ""),
                        "horizon_days": query.horizon_days,
                        "facilities_scored": len(risk),
                    }],
                ))


# ──────────────────────────────────────────────────────────────────────────
# Supply-graph propagation
# ──────────────────────────────────────────────────────────────────────────
class SupplyGraphExecutor(Executor):  # type: ignore[misc]
    """Builds the supply-impact view of the registry.

    The MVP propagates risk one hop: if facility ``X`` is at-risk under
    hazard ``H``, every downstream facility ``Y`` (edge ``X → Y``) gets
    listed as ``impacted_by[Y] += {src: X, hazard: H, ...}``. The dashboard
    then renders the upstream chain for each at-risk facility.

    A future iteration will do multi-hop propagation with decay (more
    interesting visually but the same data contract).

    This executor doesn't actually need the hazard scores up front — it
    only needs the registry to build the *structural* impact map. The
    aggregator overlays the live hazard scores at emit time.
    """

    def __init__(self, id: str = "supply_graph") -> None:
        if AGENT_FRAMEWORK_AVAILABLE:
            super().__init__(id=id)
        self.id = id

    if AGENT_FRAMEWORK_AVAILABLE:
        @handler  # type: ignore
        async def on_message(
            self,
            bundle: FacilityRegistry,
            ctx: "WorkflowContext[SupplyImpact]",
        ) -> None:
            edges = bundle.supply_edges
            # Cite both the facility registry AND the supply-edge table so
            # the dossier provenance lists every Fabric table the workflow
            # touched (mirrors Site Intel's per-table citations).
            registry_row = {
                "source": "facility_registry",
                "lakehouse": bundle.data_source,
                "rows": int(len(bundle.facilities)),
            }
            impacted_by: dict[str, list[dict[str, Any]]] = {}
            downstream_of: dict[str, list[dict[str, Any]]] = {}

            if edges.empty:
                await ctx.send_message(SupplyImpact(
                    impacted_by={}, downstream_of={},
                    provenance=[
                        registry_row,
                        {"source": "supply_edges", "lakehouse": bundle.data_source, "rows": 0},
                    ],
                ))
                return

            facility_ids = set(bundle.facilities["facility_id"].astype(str).tolist())
            for _, edge in edges.iterrows():
                src = str(edge.get("src_facility_id"))
                dst = str(edge.get("dst_facility_id"))
                if src not in facility_ids or dst not in facility_ids:
                    # Edge connects to a filtered-out facility; ignore.
                    continue
                edge_meta = {
                    "src_id": src,
                    "dst_id": dst,
                    "kind": edge.get("kind"),
                    "lead_time_days": edge.get("lead_time_days"),
                    "weekly_volume": edge.get("weekly_volume"),
                }
                impacted_by.setdefault(dst, []).append({k: v for k, v in edge_meta.items() if k != "dst_id"})
                downstream_of.setdefault(src, []).append({k: v for k, v in edge_meta.items() if k != "src_id"})

            await ctx.send_message(SupplyImpact(
                impacted_by=impacted_by,
                downstream_of=downstream_of,
                provenance=[
                    registry_row,
                    {
                        "source": "supply_edges",
                        "lakehouse": bundle.data_source,
                        "rows": int(len(edges)),
                    },
                ],
            ))


# ──────────────────────────────────────────────────────────────────────────
# BCP / playbook context
# ──────────────────────────────────────────────────────────────────────────
class ContextExecutor(Executor):  # type: ignore[misc]
    """Pulls relevant BCP / playbook snippets from Azure AI Search.

    The MVP issues a single broad query for the active hazards + region;
    a v2 will issue one query per at-risk facility filtered by
    ``facility_id``. The current shape is good enough for the dashboard
    panel "Recommended actions".

    Gracefully degrades to an empty result when AI Search isn't
    configured — the rest of the workflow still completes.
    """

    def __init__(self, id: str = "context") -> None:
        if AGENT_FRAMEWORK_AVAILABLE:
            super().__init__(id=id)
        self.id = id

    if AGENT_FRAMEWORK_AVAILABLE:
        @handler  # type: ignore
        async def on_message(
            self,
            bundle: FacilityRegistry,
            ctx: "WorkflowContext[ContextSnippets]",
        ) -> None:
            query = bundle.query
            hazards = ", ".join(query.hazards)
            region = query.region_filter or ""
            user_q = query.user_query or ""
            q = " ".join(filter(None, [user_q, hazards, region, "business continuity playbook"]))

            docs_by_facility: dict[str, list[dict[str, Any]]] = {}
            provenance: list[dict[str, Any]] = []

            if not FABRIC_CLIENT_AVAILABLE or fabric_client is None:
                await ctx.send_message(ContextSnippets(
                    docs_by_facility={},
                    provenance=[{"source": "ai_search", "skipped": "fabric_client unavailable"}],
                ))
                return

            try:
                # Temporarily override the env so the shared search_documents
                # call hits the resilience index without touching site_intel's.
                prev_index = os.environ.get("FABRIC_DOC_SEARCH_INDEX")
                os.environ["FABRIC_DOC_SEARCH_INDEX"] = BCP_SEARCH_INDEX
                try:
                    hits = await fabric_client.search_documents(
                        user_assertion=query.user_assertion,
                        workspace_id=bundle.workspace_id or "",
                        query=q,
                        top_k=8,
                    )
                finally:
                    if prev_index is None:
                        os.environ.pop("FABRIC_DOC_SEARCH_INDEX", None)
                    else:
                        os.environ["FABRIC_DOC_SEARCH_INDEX"] = prev_index
            except Exception as exc:  # noqa: BLE001 — degrade, don't fail
                logger.info("[RESILIENCE] AI Search BCP lookup failed: %s", exc)
                hits = []
                provenance.append({"source": "ai_search", "error": str(exc)})

            # Bucket hits to facilities. Hits may carry a ``facility_id``
            # metadata field (when indexed that way) or none at all — in
            # which case we attach them to the "*" wildcard bucket and the
            # aggregator broadcasts.
            for h in hits:
                fid = h.get("facility_id") or "*"
                docs_by_facility.setdefault(str(fid), []).append(h)

            provenance.append({
                "source": "ai_search",
                "index": BCP_SEARCH_INDEX,
                "hits": int(len(hits)),
                "query": q,
            })

            # ── Fabric Lakehouse fallback ─────────────────────────────────
            # If AI Search returned nothing (or isn't configured yet), pull
            # the Resilience BCP playbooks straight from the Fabric
            # `bcp_playbooks` Delta table. The table degrades further to
            # the bundled seed JSON when the Delta table doesn't exist —
            # so the workflow always has *some* recommendation surface.
            if not hits:
                try:
                    facility_ids = list(bundle.facilities["facility_id"].astype(str)) if not bundle.facilities.empty else None
                    pb_df, pb_source = await load_bcp_playbooks(
                        user_assertion=query.user_assertion,
                        workspace_id=bundle.workspace_id,
                        lakehouse_id=bundle.lakehouse_id,
                        hazards=list(query.hazards),
                        facility_ids=facility_ids,
                        region_filter=query.region_filter,
                    )
                    for _, row in pb_df.iterrows():
                        snippet = row.get("summary") or row.get("trigger") or ""
                        doc = {
                            "id": row.get("playbook_id"),
                            "title": row.get("title"),
                            "snippet": snippet,
                            "score": None,
                            "facility_id": None,
                        }
                        hint = row.get("facility_hint")
                        if isinstance(hint, (list, tuple)) and hint:
                            for fid in hint:
                                docs_by_facility.setdefault(str(fid), []).append(doc)
                        else:
                            docs_by_facility.setdefault("*", []).append(doc)
                    provenance.append({
                        "source": "bcp_playbooks",
                        "lakehouse": pb_source,
                        "rows": int(len(pb_df)),
                    })
                except Exception as exc:  # noqa: BLE001 — degrade gracefully
                    logger.info("[RESILIENCE] bcp_playbooks fallback failed: %s", exc)
                    provenance.append({"source": "bcp_playbooks", "error": str(exc)})

            await ctx.send_message(ContextSnippets(
                docs_by_facility=docs_by_facility,
                provenance=provenance,
            ))


# ──────────────────────────────────────────────────────────────────────────
# Aggregator
# ──────────────────────────────────────────────────────────────────────────
class AggregatorExecutor(Executor):  # type: ignore[misc]
    """Fan-in node — composes the final dossier from all upstream emits."""

    def __init__(self, query: ResilienceQuery, id: str = "aggregator") -> None:
        if AGENT_FRAMEWORK_AVAILABLE:
            super().__init__(id=id)
        self.id = id
        self._query = query

    if AGENT_FRAMEWORK_AVAILABLE:
        @handler  # type: ignore
        async def on_message(
            self,
            messages: list[Any],
            # Aggregator is terminal — no downstream send_message; the dossier
            # is published as a workflow output via ``ctx.yield_output(...)``.
            # The second type param (``W_OutT``) on ``WorkflowContext`` is the
            # workflow-output type; ``OutT`` is unused here.
            ctx: "WorkflowContext[Any, dict[str, Any]]",
        ) -> None:
            hazards: dict[str, HazardForecast] = {}
            supply: SupplyImpact | None = None
            context: ContextSnippets | None = None
            for msg in messages:
                if isinstance(msg, HazardForecast):
                    hazards[msg.hazard] = msg
                elif isinstance(msg, SupplyImpact):
                    supply = msg
                elif isinstance(msg, ContextSnippets):
                    context = msg

            dossier = _build_dossier(self._query, hazards, supply, context)
            # MUST be yield_output — send_message from a terminal node is
            # dropped by MAF ("No outgoing edges found for executor aggregator;
            # dropping messages.") so the workflow completes with zero outputs.
            await ctx.yield_output(dossier)


# ──────────────────────────────────────────────────────────────────────────
# Dossier assembly — pulled out so it can be unit-tested without MAF.
# ──────────────────────────────────────────────────────────────────────────
def _build_dossier(
    query: ResilienceQuery,
    hazards: dict[str, HazardForecast],
    supply: SupplyImpact | None,
    context: ContextSnippets | None,
) -> dict[str, Any]:
    """Assemble the final JSON payload returned to the API caller.

    Output shape:
        {
          "input": {...query params...},
          "hazards": { hazard: { facility_id: {score, ...}, ... }, ... },
          "facilities": [
            {facility_id, name, lat, lng, type, region, overall_risk, severity,
             hazards: {heat: {...}, wildfire: {...}},
             upstream_at_risk: [ {src_id, hazards: [...], edge_kind, ...} ],
             playbooks: [ {title, snippet, score} ]}
          ],
          "summary": {
            "facilities_assessed": int,
            "at_risk_facilities": int,
            "top_risks": [ {facility_id, name, severity, primary_hazard} ],
            "data_source": "fabric" | "seed",
          },
          "provenance": [...],
          "engine": "maf_workflow_resilience_mvp"
        }
    """
    # Build the per-facility roll-up. We need facility metadata; pull it
    # from any hazard's facility_risk keys + supply impacted_by graph.
    facility_ids: set[str] = set()
    for hz in hazards.values():
        facility_ids.update(hz.facility_risk.keys())
    if supply:
        facility_ids.update(supply.impacted_by.keys())
        facility_ids.update(supply.downstream_of.keys())

    # We didn't carry the full registry into the aggregator (MAF fan-in
    # only delivers the fan-out outputs), so per-facility static metadata
    # (name/type/lat/lng/etc.) is pulled from the bundled seed file
    # synchronously here, and then overlaid by anything richer that
    # hazard evidence supplied.
    facilities_meta: dict[str, dict[str, Any]] = {}
    try:
        import json
        from pathlib import Path
        with open(Path(__file__).resolve().parent / "seed_data" / "facilities.json", "r", encoding="utf-8") as fh:
            for row in json.load(fh):
                facilities_meta[str(row["facility_id"])] = row
    except Exception as exc:  # noqa: BLE001
        logger.info("[RESILIENCE] facilities meta fallback failed: %s", exc)

    # Overlay names from hazard evidence (which is authoritative when
    # Fabric tables are richer than the seed file).
    for hz in hazards.values():
        for ev in hz.evidence:
            fid = str(ev.get("facility_id") or "")
            if not fid or fid in facilities_meta:
                continue
            facilities_meta[fid] = {"facility_id": fid, "name": ev.get("name") or fid}

    facilities_out: list[dict[str, Any]] = []
    for fid in sorted(facility_ids):
        meta = facilities_meta.get(fid, {"facility_id": fid, "name": fid})
        per_hazard: dict[str, Any] = {}
        max_score = 0.0
        primary_hazard: str | None = None
        for hz_name, hz in hazards.items():
            entry = hz.facility_risk.get(fid)
            if entry is None:
                continue
            per_hazard[hz_name] = entry
            if entry.get("score") is not None and entry["score"] > max_score:
                max_score = entry["score"]
                primary_hazard = hz_name

        severity = "low"
        if max_score >= 80:
            severity = "severe"
        elif max_score >= 55:
            severity = "high"
        elif max_score >= 25:
            severity = "moderate"

        upstream = (supply.impacted_by.get(fid, []) if supply else [])
        downstream = (supply.downstream_of.get(fid, []) if supply else [])

        playbooks: list[dict[str, Any]] = []
        if context:
            for h in context.docs_by_facility.get(fid, []):
                playbooks.append(_compact_doc(h))
            # Wildcard / broadcast bucket — include top 2 for context.
            for h in context.docs_by_facility.get("*", [])[:2]:
                playbooks.append(_compact_doc(h))

        facilities_out.append({
            "facility_id": fid,
            "name": meta.get("name"),
            "lat": meta.get("lat"),
            "lng": meta.get("lng"),
            "type": meta.get("type"),
            "region": meta.get("region"),
            "city": meta.get("city"),
            "criticality": meta.get("criticality"),
            "overall_risk": round(max_score, 1),
            "severity": severity,
            "primary_hazard": primary_hazard,
            "hazards": per_hazard,
            "upstream_at_risk": upstream,
            "downstream": downstream,
            "playbooks": playbooks,
        })

    # Sort by risk desc — UI wants the at-risk ones on top.
    facilities_out.sort(key=lambda f: f["overall_risk"], reverse=True)

    top_risks = [
        {
            "facility_id": f["facility_id"],
            "name": f["name"],
            "severity": f["severity"],
            "overall_risk": f["overall_risk"],
            "primary_hazard": f["primary_hazard"],
        }
        for f in facilities_out
        if f["overall_risk"] >= 25
    ][:5]

    provenance: list[dict[str, Any]] = []
    for hz in hazards.values():
        provenance.extend(hz.provenance)
    if supply:
        provenance.extend(supply.provenance)
    if context:
        provenance.extend(context.provenance)

    return {
        "input": {
            "region_filter": query.region_filter,
            "horizon_days": query.horizon_days,
            "hazards": list(query.hazards),
            "user_query": query.user_query,
        },
        "facilities": facilities_out,
        "hazards": {hz_name: hz.facility_risk for hz_name, hz in hazards.items()},
        "summary": {
            "facilities_assessed": len(facilities_out),
            "at_risk_facilities": sum(1 for f in facilities_out if f["overall_risk"] >= 25),
            "top_risks": top_risks,
        },
        "provenance": provenance,
        "engine": "maf_workflow_resilience_mvp",
    }


def _compact_doc(h: dict[str, Any]) -> dict[str, Any]:
    """Shrink an AI Search hit to the fields the dashboard renders."""
    title = h.get("title") or h.get("name") or h.get("id") or "Playbook"
    content = h.get("content") or h.get("chunk") or ""
    snippet = (content[:280] + "…") if len(content) > 280 else content
    return {
        "title": title,
        "snippet": snippet,
        "score": h.get("@search.score") or h.get("score"),
        "id": h.get("id"),
        "url": h.get("url"),
    }
