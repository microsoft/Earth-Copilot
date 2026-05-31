"""Tool catalogue for the Resilience PlannerExecutor.

Each function here is a *deterministic* operation the LLM planner can
choose to invoke. The planner's job is to compose them into an answer;
the tools' job is to be cheap, well-typed, and side-effect free so the
plan is reproducible.

Three categories:

  1. **Reuse the standard workflow** — ``run_standard_assessment`` calls
     the existing fan-out/fan-in DAG end-to-end. Used by the planner
     when a query reduces to "score these facilities".
  2. **Single-step queries** — ``query_facilities``, ``search_playbooks``
     hit the lakehouse / AI Search without touching weather or scoring.
  3. **Investigative ops** — ``simulate_outage``, ``compare_periods``,
     ``find_similar_facilities`` answer the counterfactual / comparison
     questions the deterministic DAG can't.

Every tool returns a dict with a ``provenance`` field so the critic can
verify citations end-to-end. Errors surface as ``{"error": "..."}`` so
the planner can decide to retry or change tack rather than the whole
workflow exploding.
"""

from __future__ import annotations

import logging
import os
from collections import deque
from typing import Any

from .data_loader import load_bcp_playbooks, load_registry
from .messages import ALL_HAZARDS
from .workflow import assess_resilience

try:  # Optional: only available when the MPC Pro MCP sidecar is enabled.
    from mcp_runtime import TracedMcpClient
except Exception:  # noqa: BLE001
    TracedMcpClient = None  # type: ignore[assignment]

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────────────────
# Category 1 — Reuse the deterministic workflow
# ─────────────────────────────────────────────────────────────────────────
async def run_standard_assessment(
    *,
    region_filter: str | None = None,
    horizon_days: int = 7,
    hazards: list[str] | None = None,
    user_query: str | None = None,
) -> dict[str, Any]:
    """Run the existing fan-out/fan-in workflow as a single tool call.

    The planner uses this when the user's question reduces to "what's the
    risk for region X over N days?". Returns the full dossier shape.
    """
    try:
        return await assess_resilience(
            user_assertion=user_query or "Resilience assessment requested by planner.",
            region_filter=region_filter,
            horizon_days=horizon_days,
            hazards=tuple(hazards) if hazards else ALL_HAZARDS,
            user_query=user_query,
        )
    except Exception as exc:  # noqa: BLE001 — surfaced to the planner
        logger.exception("[RESILIENCE.tool] run_standard_assessment failed")
        return {"error": f"standard assessment failed: {exc}"}


# ─────────────────────────────────────────────────────────────────────────
# Category 2 — Single-step lookups
# ─────────────────────────────────────────────────────────────────────────
async def query_facilities(
    *,
    region_filter: str | None = None,
    facility_type: str | None = None,
    min_criticality: float | None = None,
) -> dict[str, Any]:
    """Read the facility registry without running any scoring.

    Useful when the planner just needs the inventory ("list all TX
    fabs") before deciding what to do next.
    """
    df, _edges, source = await load_registry(
        user_assertion="planner.query_facilities", region_filter=region_filter
    )
    if facility_type:
        df = df[df["type"].astype(str).str.lower() == facility_type.lower()]
    if min_criticality is not None:
        df = df[df["criticality"].astype(float) >= float(min_criticality)]
    return {
        "facilities": df.to_dict(orient="records"),
        "count": int(len(df)),
        "provenance": [{"source": "facility_registry", "lakehouse": source, "rows": int(len(df))}],
    }


async def search_playbooks(
    *,
    query: str,
    hazards: list[str] | None = None,
    region: str | None = None,
) -> dict[str, Any]:
    """Pull BCP playbooks by hazard + region (Delta-backed filter).

    Returns up to 5 playbooks ranked by recency. The planner uses this
    when the user asks "what's the playbook for X?" without needing a
    full risk assessment.
    """
    df, source = await load_bcp_playbooks(user_assertion="planner.search_playbooks")
    if hazards:
        wanted = {h.lower() for h in hazards}
        df = df[df["hazards"].apply(lambda hs: bool(set(map(str.lower, hs or [])) & wanted))]
    if region:
        df = df[df["region"].astype(str).str.upper() == region.upper()]
    rows = df.sort_values("last_reviewed", ascending=False).head(5).to_dict(orient="records")
    return {
        "playbooks": rows,
        "count": len(rows),
        "query": query,
        "provenance": [{"source": "bcp_playbooks", "lakehouse": source, "rows": int(len(df))}],
    }


# ─────────────────────────────────────────────────────────────────────────
# Category 3 — Investigative / counterfactual ops
# ─────────────────────────────────────────────────────────────────────────
async def simulate_outage(
    *,
    facility_id: str,
    days: int = 5,
    max_hops: int = 3,
) -> dict[str, Any]:
    """What happens if ``facility_id`` goes offline for ``days`` days?

    Multi-hop BFS over ``supply_edges`` computing the blast radius and
    weekly volume at risk. Goes beyond the standard DAG's 1-hop view.
    """
    fac_df, edges_df, registry_source = await load_registry(
        user_assertion="planner.simulate_outage"
    )

    # Adjacency list: src -> [(dst, kind, weekly_volume, lead_time)]
    adj: dict[str, list[dict[str, Any]]] = {}
    for _, e in edges_df.iterrows():
        adj.setdefault(str(e["src_facility_id"]), []).append({
            "dst": str(e["dst_facility_id"]),
            "kind": e.get("kind"),
            "weekly_volume": int(e.get("weekly_volume") or 0),
            "lead_time_days": int(e.get("lead_time_days") or 0),
        })

    visited: dict[str, int] = {facility_id: 0}
    queue: deque[tuple[str, int]] = deque([(facility_id, 0)])
    impacts: list[dict[str, Any]] = []
    while queue:
        node, hop = queue.popleft()
        if hop >= max_hops:
            continue
        for edge in adj.get(node, []):
            dst = edge["dst"]
            if dst in visited:
                continue
            visited[dst] = hop + 1
            # Lead time gates the impact — if buffer > outage days, no hit.
            at_risk = edge["weekly_volume"] * (days / 7.0)
            buffered = edge["lead_time_days"] >= days
            impacts.append({
                "facility_id": dst,
                "hops_from_source": hop + 1,
                "edge_kind": edge["kind"],
                "weekly_volume_at_risk": round(at_risk, 1),
                "buffered_by_lead_time": buffered,
            })
            queue.append((dst, hop + 1))

    # Hydrate names.
    name_lookup = dict(zip(fac_df["facility_id"].astype(str), fac_df["name"].astype(str)))
    for row in impacts:
        row["name"] = name_lookup.get(row["facility_id"], row["facility_id"])

    return {
        "source_facility_id": facility_id,
        "source_name": name_lookup.get(facility_id, facility_id),
        "outage_days": days,
        "max_hops": max_hops,
        "total_downstream": len(impacts),
        "total_weekly_volume_at_risk": round(sum(r["weekly_volume_at_risk"] for r in impacts), 1),
        "impacts": impacts,
        "provenance": [
            {"source": "supply_edges", "lakehouse": registry_source, "rows": int(len(edges_df))},
            {"source": "facility_registry", "lakehouse": registry_source, "rows": int(len(fac_df))},
        ],
    }


async def compare_periods(
    *,
    region_filter: str | None = None,
    hazards: list[str] | None = None,
    horizon_a_days: int = 7,
    horizon_b_days: int = 7,
    label_a: str = "current",
    label_b: str = "alternate",
) -> dict[str, Any]:
    """Two assessments side-by-side, diffed by facility.

    The MVP uses the same forecast window for both — Open-Meteo's free
    tier doesn't expose historical dates — but the diff machinery is
    ready for an ERA5 hookup later. The planner uses it for
    "compared to last week" framing.
    """
    a = await run_standard_assessment(
        region_filter=region_filter, horizon_days=horizon_a_days, hazards=hazards
    )
    b = await run_standard_assessment(
        region_filter=region_filter, horizon_days=horizon_b_days, hazards=hazards
    )
    if "error" in a or "error" in b:
        return {"error": "comparison failed", "a": a.get("error"), "b": b.get("error")}

    by_id_a = {f["facility_id"]: f for f in a.get("facilities", [])}
    by_id_b = {f["facility_id"]: f for f in b.get("facilities", [])}
    diffs: list[dict[str, Any]] = []
    for fid in sorted(set(by_id_a) | set(by_id_b)):
        fa = by_id_a.get(fid, {})
        fb = by_id_b.get(fid, {})
        score_a = float(fa.get("overall_risk") or 0.0)
        score_b = float(fb.get("overall_risk") or 0.0)
        diffs.append({
            "facility_id": fid,
            "name": fa.get("name") or fb.get("name"),
            f"{label_a}_score": score_a,
            f"{label_b}_score": score_b,
            "delta": round(score_b - score_a, 1),
            "moved_severity": fa.get("severity") != fb.get("severity"),
        })
    diffs.sort(key=lambda d: abs(d["delta"]), reverse=True)
    return {
        "label_a": label_a,
        "label_b": label_b,
        "diffs": diffs[:10],
        "n_facilities": len(diffs),
        "provenance": (a.get("provenance") or []) + (b.get("provenance") or []),
    }


async def find_similar_facilities(
    *,
    reference_id: str,
    same_type: bool = True,
    same_region: bool = False,
) -> dict[str, Any]:
    """Return facilities that share key risk attributes with ``reference_id``.

    Used by the planner for "find me a Phoenix expansion site with the
    same risk profile as Austin". MVP just matches on
    ``type`` + ``criticality`` bucket; future versions could use embeddings.
    """
    df, _edges, source = await load_registry(user_assertion="planner.find_similar")
    ref_rows = df[df["facility_id"].astype(str) == reference_id]
    if ref_rows.empty:
        return {"error": f"unknown facility_id: {reference_id}"}
    ref = ref_rows.iloc[0]
    candidates = df[df["facility_id"].astype(str) != reference_id]
    if same_type:
        candidates = candidates[candidates["type"] == ref["type"]]
    if same_region:
        candidates = candidates[candidates["region"] == ref["region"]]
    ref_crit = float(ref.get("criticality") or 0.5)
    candidates = candidates.assign(
        similarity=candidates["criticality"].apply(
            lambda c: 1.0 - abs(float(c or 0.5) - ref_crit)
        )
    ).sort_values("similarity", ascending=False).head(5)
    return {
        "reference": {
            "facility_id": str(ref["facility_id"]),
            "name": str(ref["name"]),
            "type": str(ref["type"]),
            "criticality": ref_crit,
        },
        "matches": candidates[["facility_id", "name", "type", "region", "criticality", "similarity"]].to_dict(orient="records"),
        "provenance": [{"source": "facility_registry", "lakehouse": source, "rows": int(len(df))}],
    }


# ─────────────────────────────────────────────────────────────────────────
# OpenAI function-calling schemas
# ─────────────────────────────────────────────────────────────────────────
# These are the tool descriptors handed to the LLM. Names match the
# Python callables above so the dispatcher can look them up by string.
TOOL_SCHEMAS: list[dict[str, Any]] = [
    {
        "type": "function",
        "function": {
            "name": "run_standard_assessment",
            "description": (
                "Score a region's facilities against the given hazards over the forecast horizon. "
                "Use for any question that boils down to 'what's the current risk?'."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "region_filter": {"type": "string", "description": "Region code, e.g. 'TX' or 'CA'. Omit to scan all."},
                    "horizon_days": {"type": "integer", "minimum": 1, "maximum": 14, "default": 7},
                    "hazards": {"type": "array", "items": {"type": "string", "enum": list(ALL_HAZARDS)}},
                    "user_query": {"type": "string"},
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "query_facilities",
            "description": "List facilities matching simple filters; does NOT score them.",
            "parameters": {
                "type": "object",
                "properties": {
                    "region_filter": {"type": "string"},
                    "facility_type": {"type": "string", "description": "fab | assembly | dc | packaging | rnd"},
                    "min_criticality": {"type": "number", "minimum": 0, "maximum": 1},
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "search_playbooks",
            "description": "Find BCP playbooks by hazard + region. No weather involved.",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string"},
                    "hazards": {"type": "array", "items": {"type": "string"}},
                    "region": {"type": "string"},
                },
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "simulate_outage",
            "description": (
                "Counterfactual: assume facility goes offline for N days; compute multi-hop "
                "downstream impact and weekly volume at risk."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "facility_id": {"type": "string"},
                    "days": {"type": "integer", "minimum": 1, "maximum": 30, "default": 5},
                    "max_hops": {"type": "integer", "minimum": 1, "maximum": 5, "default": 3},
                },
                "required": ["facility_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "compare_periods",
            "description": "Diff two assessment runs (e.g. current 7-day vs next-7-day window) by facility.",
            "parameters": {
                "type": "object",
                "properties": {
                    "region_filter": {"type": "string"},
                    "hazards": {"type": "array", "items": {"type": "string"}},
                    "horizon_a_days": {"type": "integer", "default": 7},
                    "horizon_b_days": {"type": "integer", "default": 7},
                    "label_a": {"type": "string", "default": "current"},
                    "label_b": {"type": "string", "default": "alternate"},
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "find_similar_facilities",
            "description": "Find facilities with similar type/criticality to a reference facility.",
            "parameters": {
                "type": "object",
                "properties": {
                    "reference_id": {"type": "string"},
                    "same_type": {"type": "boolean", "default": True},
                    "same_region": {"type": "boolean", "default": False},
                },
                "required": ["reference_id"],
            },
        },
    },
]


# Dispatch table — name -> async callable. The planner's tool-call loop
# uses this to invoke whatever the LLM picks.
TOOL_DISPATCH: dict[str, Any] = {
    "run_standard_assessment": run_standard_assessment,
    "query_facilities": query_facilities,
    "search_playbooks": search_playbooks,
    "simulate_outage": simulate_outage,
    "compare_periods": compare_periods,
    "find_similar_facilities": find_similar_facilities,
}


# ─────────────────────────────────────────────────────────────────────
# Category 4 — MCP-backed catalogue queries
# ─────────────────────────────────────────────────────────────────────
# These reach the Microsoft Planetary Computer catalogue through
# :class:`mcp_runtime.TracedMcpClient`. Each call surfaces as
# ``tool_call`` + ``tool_result`` SSE events when the request was
# served from a route wrapped with ``merge_with_trace``.
#
# Routing policy (agent reasoning):
#   * Default backend is **public** MPC STAC
#     (https://planetarycomputer.microsoft.com/api/stac/v1) via
#     :meth:`TracedMcpClient.from_mpc_public`. No auth, no sidecar,
#     always works.
#   * MPC **Pro** is reserved for (a) direct chat queries when the user
#     toggled the "MPC Pro" button on, and (b) data-catalogue private/
#     personal-collection queries. Agent reasoning never depends on it.
#   * Opt back into Pro for agent reasoning by setting
#     ``RESILIENCE_AGENT_USE_MPC_PRO=1``.
async def _traced_mcp_call(tool: str, args: dict[str, Any]) -> dict[str, Any]:
    """Shared helper — invoke ``tool`` with full tracing.

    Picks the backend per the routing policy above: public by default,
    Pro only when the agent is explicitly opted in **and** the sidecar
    is enabled.
    """
    if TracedMcpClient is None:
        return {"error": "mcp_runtime not available in this build"}

    client = None
    if os.getenv("RESILIENCE_AGENT_USE_MPC_PRO", "0").lower() in ("1", "true", "yes", "on"):
        client = TracedMcpClient.from_mpc_pro()
    if client is None:
        client = TracedMcpClient.from_mpc_public()
    backend = client.server_id  # "mpc_pro" or "mpc_public"
    try:
        result = await client.call(tool, args)
    except Exception as exc:  # noqa: BLE001
        logger.warning("[RESILIENCE.mcp] %s raised: %s", tool, exc)
        return {"error": f"{tool} raised: {exc}", "_mcp_backend": backend}
    if isinstance(result, dict):
        result.setdefault("_mcp_backend", backend)
        return result
    return {"value": result, "_mcp_backend": backend}


def _provenance_source(backend: str) -> str:
    return "mpc_public_stac" if backend == "mpc_public" else "mpc_pro_mcp"


async def list_mpc_stac_collections() -> dict[str, Any]:
    """List the STAC collections published by MPC Pro.

    Use this when the user asks 'what imagery is available?' or wants to
    discover collections to feed into a later assessment. Results are
    not cached at this layer — the MCP server has its own cache.
    """
    result = await _traced_mcp_call("list_mpc_stac_collections", {})
    if "error" in result:
        return result
    result.setdefault(
        "provenance",
        [{"source": _provenance_source(result.get("_mcp_backend", "")), "tool": "list_mpc_stac_collections"}],
    )
    return result


async def search_mpc_stac_items(
    *,
    collection: str,
    bbox: list[float] | None = None,
    datetime_range: str | None = None,
    limit: int = 10,
) -> dict[str, Any]:
    """Search items inside an MPC Pro STAC collection.

    Useful when the planner needs to confirm a facility has coverage,
    or to fetch a small sample of items for citation in the dossier.
    ``bbox`` is ``[minx, miny, maxx, maxy]`` in WGS84.
    """
    args: dict[str, Any] = {"collection": collection, "limit": max(1, min(limit, 50))}
    if bbox is not None:
        args["bbox"] = bbox
    if datetime_range is not None:
        args["datetime"] = datetime_range
    result = await _traced_mcp_call("search_mpc_items", args)
    if "error" in result:
        return result
    result.setdefault(
        "provenance",
        [{"source": _provenance_source(result.get("_mcp_backend", "")), "tool": "search_mpc_items", "collection": collection}],
    )
    return result


async def get_mpc_collection_details(*, collection: str) -> dict[str, Any]:
    """Fetch the full STAC collection JSON for one MPC Pro collection.

    Use when the planner needs spatial/temporal extent, asset table, or
    render options for an answer. Often paired with
    ``search_mpc_stac_items`` to verify coverage before citing data.
    """
    args = {"collection_id": collection}
    result = await _traced_mcp_call("get_mpc_collection_json", args)
    if "error" in result:
        return result
    result.setdefault(
        "provenance",
        [{"source": _provenance_source(result.get("_mcp_backend", "")), "tool": "get_mpc_collection_json", "collection": collection}],
    )
    return result


TOOL_SCHEMAS += [
    {
        "type": "function",
        "function": {
            "name": "list_mpc_stac_collections",
            "description": (
                "List STAC collections available in Microsoft Planetary Computer Pro. "
                "Use to discover what imagery exists before searching for items."
            ),
            "parameters": {"type": "object", "properties": {}},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "search_mpc_stac_items",
            "description": (
                "Search STAC items in a MPC Pro collection by bbox and/or datetime. "
                "Returns a small page (default 10, max 50). Use to confirm coverage "
                "for a facility location or to cite a specific scene."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "collection": {"type": "string", "description": "STAC collection id, e.g. 'sentinel-2-l2a'."},
                    "bbox": {
                        "type": "array",
                        "items": {"type": "number"},
                        "minItems": 4,
                        "maxItems": 4,
                        "description": "[minx, miny, maxx, maxy] in WGS84.",
                    },
                    "datetime_range": {
                        "type": "string",
                        "description": "RFC3339 interval, e.g. '2024-01-01/2024-12-31'.",
                    },
                    "limit": {"type": "integer", "minimum": 1, "maximum": 50, "default": 10},
                },
                "required": ["collection"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_mpc_collection_details",
            "description": (
                "Fetch the full STAC collection JSON (extent, assets, providers, "
                "render options) for one MPC Pro collection."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "collection": {"type": "string", "description": "STAC collection id."},
                },
                "required": ["collection"],
            },
        },
    },
]

TOOL_DISPATCH.update({
    "list_mpc_stac_collections": list_mpc_stac_collections,
    "search_mpc_stac_items": search_mpc_stac_items,
    "get_mpc_collection_details": get_mpc_collection_details,
})
