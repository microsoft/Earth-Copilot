"""
Raster sampling analyzer — extracts the actual numeric pixel value from a
loaded STAC raster at a pin location.

This is the v2 wrapper around the legacy `agents.vision_tools` helpers
(`sample_raster_value`, plus a fallback to `analyze_raster` for area
statistics). Kept as its own analyzer (separate from `vision`) so that:

  * `vision` stays focused on descriptive interpretation of imagery.
  * `raster_sampling` is selected by the AnalysisRouter for point-value
    questions ("what is the elevation here", "SST at this location",
    "NDVI value at the pin"), which is when GPT-5 Vision alone would
    otherwise hallucinate a number from coloring.

Resilience: if no raster is loaded, no pin is available, or the legacy
helper raises, the analyzer returns success=False with an explanation —
the orchestrator continues with the rest of the plan.
"""

from __future__ import annotations

import logging
import time
from typing import Any, ClassVar

from ..analyzer_protocol import Analyzer
from ..contracts import AnalysisRequest, AnalyzerResult, Source

logger = logging.getLogger(__name__)


def _bounds_from_request(request: AnalysisRequest) -> dict[str, float]:
    """Build the map_bounds dict the legacy session_context expects.

    `sample_raster_value` reads `pin_lat`/`pin_lng` from `map_bounds`, so
    we must populate that explicitly when only `request.pin` is set.
    """
    out: dict[str, float] = {}
    if request.bbox:
        west, south, east, north = request.bbox
        out.update(
            {
                "north": north,
                "south": south,
                "east": east,
                "west": west,
                "center_lat": (south + north) / 2,
                "center_lng": (west + east) / 2,
            }
        )
    if request.pin:
        lat, lng = request.pin
        out["pin_lat"] = lat
        out["pin_lng"] = lng
        out.setdefault("center_lat", lat)
        out.setdefault("center_lng", lng)
    return out


class RasterSamplingAnalyzer(Analyzer):
    id: ClassVar[str] = "raster_sampling"
    description: ClassVar[str] = (
        "Extracts the actual numeric pixel value from a loaded STAC raster "
        "at a pin location. Returns the value with its unit (e.g. SST in "
        "°C, elevation in m, NDVI dimensionless, FRP in MW). Use whenever "
        "the user asks for a value AT a point and a raster is loaded — "
        "this returns ground-truth numbers, unlike the descriptive vision "
        "analyzer."
    )
    when_to_use: ClassVar[str] = (
        "User asks for a numeric value at a location with a raster loaded "
        "and a pin dropped: 'what is the temperature here', 'sample the "
        "elevation', 'NDVI value at this point', 'SST at the pin', "
        "'reflectance at this location'."
    )
    requires: ClassVar[tuple[str, ...]] = ("pin", "loaded_raster")

    async def analyze(self, request: AnalysisRequest) -> AnalyzerResult:
        started = time.time()

        # Delegate to the designated RasterSamplingAgent (MAF Executor +
        # tool call). Keeps the pipeline analyzer surface stable while
        # giving the workload its own named agent in the diagram.
        try:
            from agents.raster_sampling_agent import (
                get_raster_sampling_agent,
                RasterSamplingInput,
            )
        except Exception as exc:  # pragma: no cover
            logger.warning("[RASTER_SAMPLING] agent import failed: %s", exc)
            return AnalyzerResult(
                analyzer=self.id,
                success=False,
                error=f"import_error: {exc}",
                elapsed_ms=int((time.time() - started) * 1000),
            )

        if not request.pin:
            return AnalyzerResult(
                analyzer=self.id,
                success=False,
                answer="Cannot sample raster value without a pin location.",
                error="missing_pin",
                elapsed_ms=int((time.time() - started) * 1000),
            )

        # Pick a sensible default data_type from the router hint.
        # The legacy helper accepts: sst, temperature, elevation, ndvi, burn,
        # fire, water, snow, sar, biomass, reflectance, climate, auto.
        data_type_raw = (request.hint or "auto").strip().lower() or "auto"
        # The Layer-2 clarifier hint format is
        # "layer2_clarifier_pick:<analyzer> kind=<kind>" — not a data_type.
        if data_type_raw.startswith("layer2_clarifier_pick"):
            data_type_raw = "auto"
        data_type = data_type_raw

        agent_input = RasterSamplingInput(
            question=request.question,
            pin=request.pin,
            bbox=request.bbox,
            loaded_collections=list(request.loaded_collections),
            stac_items=list(request.stac_items),
            tile_urls=list(request.tile_urls),
            screenshot_b64=request.screenshot_b64,
            data_type=data_type,  # type: ignore[arg-type]
        )
        result = await get_raster_sampling_agent().run(agent_input)

        sources: list[Source] = [
            Source(title=s.get("title", ""), kind=s.get("kind", "raster"))
            for s in result.sources
        ]

        return AnalyzerResult(
            analyzer=self.id,
            success=result.success,
            answer=result.answer,
            structured=result.structured,
            sources=sources,
            confidence=result.confidence,
            error=result.error,
            elapsed_ms=result.elapsed_ms or int((time.time() - started) * 1000),
        )
