"""
Vision analyzer — wraps the existing ChatVisionAnalyzer (GPT-5 Vision over
the user's current map view or a frontend-provided screenshot).

Strategy: the legacy ChatVisionAnalyzer already does the heavy lifting
(decoding base64, fetching tiles, calling GPT-5 Vision). This adapter only
translates `AnalysisRequest` -> its kwargs and `dict` -> `AnalyzerResult`.
"""

from __future__ import annotations

import logging
import time
from typing import ClassVar

from ..analyzer_protocol import Analyzer
from ..contracts import AnalysisRequest, AnalyzerResult

logger = logging.getLogger(__name__)


def _bounds_from_request(request: AnalysisRequest) -> dict[str, float]:
    """Build the map_bounds dict ChatVisionAnalyzer expects."""
    if request.bbox:
        west, south, east, north = request.bbox
        center_lat = (south + north) / 2
        center_lng = (west + east) / 2
    elif request.pin:
        center_lat, center_lng = request.pin
        # ~5km box around the pin so the legacy code has something to work with
        delta = 0.05
        north, south = center_lat + delta, center_lat - delta
        east, west = center_lng + delta, center_lng - delta
    else:
        return {}
    return {
        "north": north,
        "south": south,
        "east": east,
        "west": west,
        "center_lat": center_lat,
        "center_lng": center_lng,
    }


class VisionAnalyzer(Analyzer):
    id: ClassVar[str] = "vision"
    description: ClassVar[str] = (
        "DESCRIPTIVE GPT-5 Vision interpretation of the imagery currently "
        "visible on the user's map (or a frontend-provided screenshot). "
        "Identifies land cover, water, vegetation, urban structure, "
        "smoke/fire signs, flood extent, snow, etc. Does NOT return "
        "ground-truth numeric pixel values — for 'what is the value at "
        "this pin' style questions, schedule the `raster_sampling` "
        "analyzer instead (and optionally chain `vision` after it for "
        "context)."
    )
    when_to_use: ClassVar[str] = (
        "User asks 'what do you see', 'analyze this view', 'what's in the "
        "image', 'describe the area', 'interpret this collection', or "
        "otherwise requests interpretation of currently rendered imagery. "
        "Works with a frontend screenshot OR a loaded raster (in which case "
        "the analyzer constructs a TiTiler tile from bounds + collection)."
    )
    # Either a frontend screenshot OR a loaded raster is enough — the
    # legacy ChatVisionAnalyzer falls back to TiTiler when only bounds +
    # collection are present. We declare `loaded_raster` here because that
    # is what the orchestrator's `can_run` precheck enforces; the analyzer
    # itself happily uses a screenshot when one is provided.
    requires: ClassVar[tuple[str, ...]] = ("loaded_raster",)

    async def analyze(self, request: AnalysisRequest) -> AnalyzerResult:
        started = time.time()
        try:
            from geoint.chat_vision_analyzer import get_chat_vision_analyzer
        except Exception as exc:  # pragma: no cover
            logger.warning("[VISION] import failed: %s", exc)
            return AnalyzerResult(
                analyzer=self.id,
                success=False,
                error=f"import_error: {exc}",
                elapsed_ms=int((time.time() - started) * 1000),
            )

        analyzer = get_chat_vision_analyzer()
        bounds = _bounds_from_request(request)

        try:
            collection_id = (
                request.loaded_collections[0] if request.loaded_collections else None
            )
            result = await analyzer.analyze_visible_imagery(
                query=request.question,
                map_bounds=bounds,
                imagery_url=request.screenshot_url,
                collection_id=collection_id,
                conversation_history=request.history or None,
                imagery_base64=request.screenshot_b64,
            )
        except Exception as exc:
            logger.warning("[VISION] analyze_visible_imagery failed: %s", exc)
            return AnalyzerResult(
                analyzer=self.id,
                success=False,
                error=f"{type(exc).__name__}: {exc}",
                elapsed_ms=int((time.time() - started) * 1000),
            )

        answer = result.get("analysis") or ""
        confidence = float(result.get("confidence") or 0.0)
        success = bool(answer) and not result.get("error")

        structured = {
            k: v
            for k, v in result.items()
            if k in ("imagery_metadata", "type", "needs_imagery")
        }

        return AnalyzerResult(
            analyzer=self.id,
            success=success,
            answer=answer,
            structured=structured,
            confidence=confidence,
            error=result.get("error"),
            elapsed_ms=int((time.time() - started) * 1000),
        )
