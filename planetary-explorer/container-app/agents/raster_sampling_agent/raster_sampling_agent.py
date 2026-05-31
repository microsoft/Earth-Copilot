"""
RasterSamplingAgent — designated agent for "what is the value at this pin?"
queries on a loaded STAC raster.

Single tool: `agents.vision_tools.sample_raster_value`. Calls TiTiler `/point`
under the hood. Returns the value with units (NDVI, SST, elevation, FRP, ...).

Public entry point: `RasterSamplingAgent.run(payload)` returning a
`RasterSamplingResult`. The pipeline `RasterSamplingAnalyzer` delegates to
this agent so the surface area looks like every other Layer-2 agent.
"""

from __future__ import annotations

import logging
import time
from typing import Optional

from .raster_sampling_models import RasterSamplingInput, RasterSamplingResult

logger = logging.getLogger(__name__)


_KNOWN_DATA_TYPES = {
    "sst", "temperature", "elevation", "ndvi", "burn", "fire", "water",
    "snow", "sar", "biomass", "reflectance", "climate", "auto",
}


class RasterSamplingAgent:
    """Designated agent for raster point-sampling."""

    async def run(self, payload: RasterSamplingInput) -> RasterSamplingResult:
        started = time.time()
        try:
            from agents.vision_tools import (
                sample_raster_value,
                set_session_context,
            )
        except Exception as exc:  # pragma: no cover
            logger.warning("[RASTER_SAMPLING_AGENT] import failed: %s", exc)
            return RasterSamplingResult(
                success=False,
                error=f"import_error: {exc}",
                pin=payload.pin,
                elapsed_ms=int((time.time() - started) * 1000),
            )

        # Build the map_bounds dict the legacy helper expects.
        bounds: dict = {}
        if payload.bbox:
            west, south, east, north = payload.bbox
            bounds.update({
                "north": north,
                "south": south,
                "east": east,
                "west": west,
                "center_lat": (south + north) / 2,
                "center_lng": (west + east) / 2,
            })
        lat, lng = payload.pin
        bounds["pin_lat"] = lat
        bounds["pin_lng"] = lng
        bounds.setdefault("center_lat", lat)
        bounds.setdefault("center_lng", lng)

        data_type = (payload.data_type or "auto").strip().lower() or "auto"
        if data_type not in _KNOWN_DATA_TYPES:
            data_type = "auto"

        try:
            set_session_context(
                screenshot_base64=payload.screenshot_b64,
                map_bounds=bounds,
                stac_items=list(payload.stac_items),
                loaded_collections=list(payload.loaded_collections),
                tile_urls=list(payload.tile_urls),
            )
            raw: str = sample_raster_value(data_type=data_type)
        except Exception as exc:
            logger.warning("[RASTER_SAMPLING_AGENT] sample_raster_value failed: %s", exc)
            return RasterSamplingResult(
                success=False,
                error=f"{type(exc).__name__}: {exc}",
                pin=payload.pin,
                data_type=data_type,
                elapsed_ms=int((time.time() - started) * 1000),
            )

        text = (raw or "").strip()
        # Helper returns sentences starting with "No ..." when it can't sample.
        success = bool(text) and not text.lower().startswith("no ")

        sources = [{"title": cid, "kind": "raster"} for cid in payload.loaded_collections[:3]]

        return RasterSamplingResult(
            success=success,
            answer=text,
            raw_value=text,
            data_type=data_type,
            pin=payload.pin,
            loaded_collections=list(payload.loaded_collections),
            sources=sources,
            confidence=0.9 if success else 0.2,
            structured={
                "data_type": data_type,
                "pin": list(payload.pin),
                "loaded_collections": list(payload.loaded_collections),
            },
            elapsed_ms=int((time.time() - started) * 1000),
        )


_singleton: Optional[RasterSamplingAgent] = None


def get_raster_sampling_agent() -> RasterSamplingAgent:
    global _singleton
    if _singleton is None:
        _singleton = RasterSamplingAgent()
    return _singleton
