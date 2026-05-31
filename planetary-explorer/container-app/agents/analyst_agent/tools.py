"""Tool functions for AnalystAgent.

Each tool wraps an existing Analyzer (or underlying agent) without
rewriting its internals. Tools read session context from the
ContextVar (set by AnalystAgent before the agent run), rebuild the
appropriate AnalysisRequest, call analyzer.analyze(), and return a
JSON-serializable dict.

All tools are async. Naming follows the catalog in REQ-ARCH-1.
"""

from __future__ import annotations

import logging
import time
from typing import Any, Dict, List, Optional

from .session_context import get_session

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _build_request(question_override: Optional[str] = None, hint: Optional[str] = None):
    """Rebuild an AnalysisRequest from the ContextVar snapshot."""
    from pipeline.contracts import AnalysisRequest

    s = get_session()
    return AnalysisRequest(
        question=question_override or s.question,
        session_id=s.session_id,
        pin=s.pin,
        pins=list(s.pins),
        bbox=s.bbox,
        location_name=s.location_name,
        time_range=s.time_range,
        loaded_collections=list(s.loaded_collections),
        loaded_collections_meta=list(s.loaded_collections_meta),
        has_screenshot=s.has_screenshot,
        screenshot_url=s.screenshot_url,
        screenshot_b64=s.screenshot_b64,
        rendered_layers=[],
        stac_items=list(s.stac_items),
        tile_urls=list(s.tile_urls),
        history=list(s.history),
        grounding=[],  # AnalystAgent owns chaining via tool sequence, not grounding field
        hint=hint or s.hint,
    )


def _result_to_dict(result) -> Dict[str, Any]:
    """Convert an AnalyzerResult to a tool-return dict (JSON-safe)."""
    try:
        d = result.model_dump()
    except AttributeError:
        d = dict(result) if isinstance(result, dict) else {"answer": str(result)}
    # Trim screenshots / large blobs from sources if any
    return {
        "analyzer": d.get("analyzer"),
        "success": d.get("success", True),
        "answer": d.get("answer", ""),
        "structured": d.get("structured", {}),
        "sources": d.get("sources", []),
        "confidence": d.get("confidence", 0.0),
        "error": d.get("error"),
        "elapsed_ms": d.get("elapsed_ms", 0),
    }


def _record_evidence(tool_name: str, payload: Dict[str, Any]) -> None:
    s = get_session()
    s.evidence.append({"tool": tool_name, "payload": payload})


# ---------------------------------------------------------------------------
# KNOWLEDGE TOOLS
# ---------------------------------------------------------------------------


async def search_graphrag(query: str, mode: str = "auto") -> Dict[str, Any]:
    """Search the indexed corpus (papers, methodology, docs) via GraphRAG.

    Args:
        query: The user's question, rephrased for retrieval if helpful.
        mode: One of "vector", "cypher", "sql", "auto". Use "auto" unless
              you have a specific reason.
    """
    # Per-request toggle: when the UI has disabled GraphRAG, short-circuit
    # so the agent never spends a sidecar round-trip. The evidence record
    # is omitted intentionally — a "skip" should not show up as a source.
    from .session_context import get_session
    if not get_session().use_graphrag:
        logger.info("[ANALYST] search_graphrag skipped — disabled by request flag")
        return {
            "success": False,
            "skipped": True,
            "reason": "graphrag_disabled_by_user",
            "answer": "",
            "sources": [],
        }

    from pipeline.analyzers.graphrag_analyzer import GraphRAGAnalyzer

    started = time.time()
    try:
        analyzer = GraphRAGAnalyzer()
        req = _build_request(question_override=query, hint=mode if mode != "auto" else None)
        result = await analyzer.analyze(req)
        out = _result_to_dict(result)
        _record_evidence("search_graphrag", out)
        return out
    except Exception as e:
        logger.exception("search_graphrag failed")
        return {"success": False, "error": str(e), "elapsed_ms": int((time.time() - started) * 1000)}


async def general_earth_qa(question: str) -> Dict[str, Any]:
    """Conceptual Earth-science fallback when no spatial tool fits.

    Use this for definitional or "what is X" questions when no map
    context disambiguates.
    """
    from pipeline.analyzers.llm_only_analyzer import LLMOnlyAnalyzer

    started = time.time()
    try:
        analyzer = LLMOnlyAnalyzer()
        req = _build_request(question_override=question)
        result = await analyzer.analyze(req)
        out = _result_to_dict(result)
        _record_evidence("general_earth_qa", out)
        return out
    except Exception as e:
        logger.exception("general_earth_qa failed")
        return {"success": False, "error": str(e), "elapsed_ms": int((time.time() - started) * 1000)}


# ---------------------------------------------------------------------------
# VISION / MAP TOOLS
# ---------------------------------------------------------------------------


async def describe_map_screenshot(question: str) -> Dict[str, Any]:
    """Run GPT-5 Vision over the user's current map screenshot.

    Best for "what's visible", "describe this area", land cover, urban
    structure, vegetation patterns. Requires a screenshot or a loaded
    raster (one of the two will be auto-derived from session context).
    """
    from pipeline.analyzers.vision_analyzer import VisionAnalyzer

    started = time.time()
    try:
        analyzer = VisionAnalyzer()
        req = _build_request(question_override=question)
        if not analyzer.can_run(req):
            return {
                "success": False,
                "error": "vision tool needs a loaded raster or a screenshot",
                "elapsed_ms": int((time.time() - started) * 1000),
            }
        result = await analyzer.analyze(req)
        out = _result_to_dict(result)
        _record_evidence("describe_map_screenshot", out)
        return out
    except Exception as e:
        logger.exception("describe_map_screenshot failed")
        return {"success": False, "error": str(e), "elapsed_ms": int((time.time() - started) * 1000)}


# ---------------------------------------------------------------------------
# RASTER VALUE TOOLS
# ---------------------------------------------------------------------------


async def sample_raster_value(question: str) -> Dict[str, Any]:
    """Sample the actual pixel value from the loaded raster at the pinned location.

    Requires a pin AND a loaded raster collection. Use for "what is the
    SST/elevation/NDVI here", "what value at this point", etc.
    """
    from pipeline.analyzers.raster_sampling_analyzer import RasterSamplingAnalyzer

    started = time.time()
    try:
        analyzer = RasterSamplingAnalyzer()
        req = _build_request(question_override=question)
        if not analyzer.can_run(req):
            return {
                "success": False,
                "error": "sample_raster_value needs a pin and a loaded raster",
                "elapsed_ms": int((time.time() - started) * 1000),
            }
        result = await analyzer.analyze(req)
        out = _result_to_dict(result)
        _record_evidence("sample_raster_value", out)
        return out
    except Exception as e:
        logger.exception("sample_raster_value failed")
        return {"success": False, "error": str(e), "elapsed_ms": int((time.time() - started) * 1000)}


async def get_collection_metadata(collection_id: str) -> Dict[str, Any]:
    """Look up asset type / domain / sample STAC scenes for a collection.

    Use this before sampling if you're unsure whether a collection is
    a COG raster vs NetCDF time series, or whether scenes exist for a
    given location. (REQ-ANALYZE-3 collection-awareness.)
    """
    s = get_session()
    # Try to find the collection in the loaded meta first
    for meta in s.loaded_collections_meta:
        if meta.get("id") == collection_id or meta.get("collection") == collection_id:
            out = {
                "success": True,
                "collection_id": collection_id,
                "metadata": meta,
                "loaded_in_session": True,
            }
            _record_evidence("get_collection_metadata", out)
            return out
    out = {
        "success": True,
        "collection_id": collection_id,
        "metadata": None,
        "loaded_in_session": False,
        "note": "Collection not currently loaded. Frontend would need to LOAD it first.",
    }
    _record_evidence("get_collection_metadata", out)
    return out


# ---------------------------------------------------------------------------
# TERRAIN / MOBILITY TOOLS
# ---------------------------------------------------------------------------


async def get_terrain_stats(question: str) -> Dict[str, Any]:
    """Elevation, slope, aspect, flat-area analysis from Copernicus DEM.

    Requires a pin. Use for landing-zone, site-suitability, slope-based
    questions.
    """
    from pipeline.analyzers.terrain_analyzer import TerrainAnalyzer

    started = time.time()
    try:
        analyzer = TerrainAnalyzer()
        req = _build_request(question_override=question)
        if not analyzer.can_run(req):
            return {
                "success": False,
                "error": "get_terrain_stats needs a pin",
                "elapsed_ms": int((time.time() - started) * 1000),
            }
        result = await analyzer.analyze(req)
        out = _result_to_dict(result)
        _record_evidence("get_terrain_stats", out)
        return out
    except Exception as e:
        logger.exception("get_terrain_stats failed")
        return {"success": False, "error": str(e), "elapsed_ms": int((time.time() - started) * 1000)}


async def get_mobility_path(question: str) -> Dict[str, Any]:
    """GO / SLOW-GO / NO-GO trafficability classification from terrain + land cover.

    Requires a pin. Use for "can I drive across", "best route",
    trafficability, off-road mobility.
    """
    from pipeline.analyzers.mobility_analyzer import MobilityAnalyzer

    started = time.time()
    try:
        analyzer = MobilityAnalyzer()
        req = _build_request(question_override=question)
        if not analyzer.can_run(req):
            return {
                "success": False,
                "error": "get_mobility_path needs a pin",
                "elapsed_ms": int((time.time() - started) * 1000),
            }
        result = await analyzer.analyze(req)
        out = _result_to_dict(result)
        _record_evidence("get_mobility_path", out)
        return out
    except Exception as e:
        logger.exception("get_mobility_path failed")
        return {"success": False, "error": str(e), "elapsed_ms": int((time.time() - started) * 1000)}


# ---------------------------------------------------------------------------
# CLIMATE TOOLS
# ---------------------------------------------------------------------------


async def get_extreme_weather_projection(question: str) -> Dict[str, Any]:
    """Future climate projections from NASA NEX-GDDP-CMIP6.

    Requires a pin. Covers SSP2-4.5 vs SSP5-8.5 scenarios, temperature
    / precipitation / wind / humidity by future year.
    """
    from pipeline.analyzers.extreme_weather_analyzer import ExtremeWeatherAnalyzer

    started = time.time()
    try:
        analyzer = ExtremeWeatherAnalyzer()
        req = _build_request(question_override=question)
        if not analyzer.can_run(req):
            return {
                "success": False,
                "error": "get_extreme_weather_projection needs a pin",
                "elapsed_ms": int((time.time() - started) * 1000),
            }
        result = await analyzer.analyze(req)
        out = _result_to_dict(result)
        _record_evidence("get_extreme_weather_projection", out)
        return out
    except Exception as e:
        logger.exception("get_extreme_weather_projection failed")
        return {"success": False, "error": str(e), "elapsed_ms": int((time.time() - started) * 1000)}


async def compute_netcdf_trend(question: str) -> Dict[str, Any]:
    """Quantitative point-sampling + time-series anomaly / linear trend over NetCDF.

    Requires a pin. Use for "trend over time", "anomaly relative to
    baseline", "rolling mean" questions.
    """
    from pipeline.analyzers.netcdf_computation_analyzer import NetcdfComputationAnalyzer

    started = time.time()
    try:
        analyzer = NetcdfComputationAnalyzer()
        req = _build_request(question_override=question)
        if not analyzer.can_run(req):
            return {
                "success": False,
                "error": "compute_netcdf_trend needs a pin",
                "elapsed_ms": int((time.time() - started) * 1000),
            }
        result = await analyzer.analyze(req)
        out = _result_to_dict(result)
        _record_evidence("compute_netcdf_trend", out)
        return out
    except Exception as e:
        logger.exception("compute_netcdf_trend failed")
        return {"success": False, "error": str(e), "elapsed_ms": int((time.time() - started) * 1000)}


# ---------------------------------------------------------------------------
# TEMPORAL COMPARISON TOOL (closes G9)
# ---------------------------------------------------------------------------


async def compare_temporal(
    collection: str,
    t1: str,
    t2: str,
) -> Dict[str, Any]:
    """Compare the same location + collection across two distinct time windows.

    This implements REQ-COMPARE-1 / closes G9. The tool:
      1. Confirms the user has a pin (or bbox) and a single collection target.
      2. Runs ``sample_raster_value`` twice (once with each time window
         in the hint) so the underlying RasterSamplingAgent picks the
         right STAC item per epoch.
      3. Returns a structured diff: {t1_value, t2_value, delta,
         percent_change, narrative}.

    Args:
        collection: The MPC collection id to compare (must match what's
                    loaded or what get_collection_metadata returned).
        t1: ISO date or year for the "before" window (e.g. "2015-06" or "2015").
        t2: ISO date or year for the "after" window.
    """
    from pipeline.analyzers.raster_sampling_analyzer import RasterSamplingAnalyzer

    started = time.time()
    s = get_session()

    if not s.pin and not s.bbox:
        return {
            "success": False,
            "needs_clarification": True,
            "missing_slot": "location",
            "error": "compare_temporal needs a pin or bbox to anchor both samples.",
        }

    # Sample at each epoch using the analyzer + a time-range hint.
    analyzer = RasterSamplingAnalyzer()

    async def _sample(epoch_label: str, when: str) -> Dict[str, Any]:
        from pipeline.contracts import AnalysisRequest

        req = AnalysisRequest(
            question=f"sample the value at the pin for {epoch_label} ({when})",
            session_id=s.session_id,
            pin=s.pin,
            pins=list(s.pins),
            bbox=s.bbox,
            location_name=s.location_name,
            time_range=(when, when),
            loaded_collections=[collection] if collection else list(s.loaded_collections),
            loaded_collections_meta=list(s.loaded_collections_meta),
            has_screenshot=False,
            screenshot_url=None,
            screenshot_b64=None,
            rendered_layers=[],
            stac_items=list(s.stac_items),
            tile_urls=list(s.tile_urls),
            history=[],
            grounding=[],
            hint=f"temporal_compare epoch={epoch_label} when={when}",
        )
        if not analyzer.can_run(req):
            return {"success": False, "error": f"raster_sampling can't run for {epoch_label}"}
        r = await analyzer.analyze(req)
        return _result_to_dict(r)

    r1 = await _sample("t1", t1)
    r2 = await _sample("t2", t2)

    def _value(r: Dict[str, Any]) -> Optional[float]:
        struct = r.get("structured") or {}
        v = struct.get("value")
        if isinstance(v, (int, float)):
            return float(v)
        return None

    v1 = _value(r1)
    v2 = _value(r2)
    delta = None
    pct = None
    if v1 is not None and v2 is not None:
        delta = v2 - v1
        pct = (delta / v1 * 100.0) if v1 != 0 else None

    narrative = ""
    if v1 is not None and v2 is not None:
        narrative = (
            f"At {s.location_name or 'the pinned location'}, "
            f"{collection} measured {v1:.3f} at {t1} and {v2:.3f} at {t2} "
            f"(delta = {delta:+.3f}"
            + (f", {pct:+.1f}%" if pct is not None else "")
            + ")."
        )
    else:
        narrative = (
            f"Could not extract numeric values for both epochs. "
            f"t1 result: {r1.get('error') or 'ok'}; t2 result: {r2.get('error') or 'ok'}."
        )

    out = {
        "success": v1 is not None and v2 is not None,
        "collection": collection,
        "t1": t1,
        "t2": t2,
        "t1_value": v1,
        "t2_value": v2,
        "delta": delta,
        "percent_change": pct,
        "narrative": narrative,
        "raw_t1": r1,
        "raw_t2": r2,
        "elapsed_ms": int((time.time() - started) * 1000),
    }
    _record_evidence("compare_temporal", out)
    return out


# ---------------------------------------------------------------------------
# CLARIFICATION TOOL (REQ-CLARIFY-2)
# ---------------------------------------------------------------------------


async def ask_user_to_clarify(
    chat_message: str,
    options: List[str],
    missing_slot: Optional[str] = None,
) -> Dict[str, Any]:
    """Ask the user a clarifying question. Use this whenever you can't
    pick a tool confidently or a required slot is missing.

    Args:
        chat_message: A conversational, user-facing message that explains
                      what you need and guides them on what they can do.
        options: 2-4 short suggestion chips to offer as quick replies.
        missing_slot: Optional name of the missing slot ("pin", "location",
                      "collection", "datetime", etc.).
    """
    out = {
        "action": "clarify",
        "chat_message": chat_message,
        "options": options or [],
        "missing_slot": missing_slot,
    }
    _record_evidence("ask_user_to_clarify", out)
    return out


# ---------------------------------------------------------------------------
# Tool registry — feed to AsyncFunctionTool
# ---------------------------------------------------------------------------


def create_analyst_functions():
    """Return the set of tool functions to register on the AnalystAgent.

    Order is the priority hint shown to the model in the tool list.
    """
    return {
        search_graphrag,
        general_earth_qa,
        describe_map_screenshot,
        sample_raster_value,
        get_collection_metadata,
        get_terrain_stats,
        get_mobility_path,
        get_extreme_weather_projection,
        compute_netcdf_trend,
        compare_temporal,
        ask_user_to_clarify,
    }
