"""
Terrain analyzer — wraps the existing TerrainAgent (Semantic Kernel agent
with DEM/slope/aspect/flat-area tools + GPT-5 Vision).
"""

from __future__ import annotations

import logging
import time
import uuid
from typing import ClassVar

from ..analyzer_protocol import Analyzer
from ..contracts import AnalysisRequest, AnalyzerResult

logger = logging.getLogger(__name__)


class TerrainAnalyzer(Analyzer):
    id: ClassVar[str] = "terrain"
    description: ClassVar[str] = (
        "Elevation / slope / aspect / flat-area analysis from Copernicus DEM "
        "with optional GPT-5 Vision interpretation. Returns quantitative "
        "terrain metrics around a pin."
    )
    when_to_use: ClassVar[str] = (
        "Questions about elevation, slope, ruggedness, landing-zone "
        "suitability, watershed, or 'is this terrain flat'. Requires a pin."
    )
    requires: ClassVar[tuple[str, ...]] = ("pin",)

    async def analyze(self, request: AnalysisRequest) -> AnalyzerResult:
        started = time.time()
        if not request.pin:
            return AnalyzerResult(
                analyzer=self.id,
                success=False,
                error="missing_pin",
                elapsed_ms=int((time.time() - started) * 1000),
            )
        lat, lng = request.pin

        try:
            from geoint.terrain_agent import get_terrain_agent
        except Exception as exc:  # pragma: no cover
            return AnalyzerResult(
                analyzer=self.id,
                success=False,
                error=f"import_error: {exc}",
                elapsed_ms=int((time.time() - started) * 1000),
            )

        agent = get_terrain_agent()
        sid = request.session_id or f"terrain_{uuid.uuid4().hex[:8]}"
        message = (
            request.question
            or "Analyze the terrain at this location. What are the key features?"
        )

        try:
            result = await agent.analyze(
                session_id=sid,
                user_message=message,
                latitude=lat,
                longitude=lng,
                screenshot_base64=request.screenshot_b64,
                radius_km=8.05,  # ~5 mi default
            )
        except Exception as exc:
            logger.warning("[TERRAIN] analyze failed: %s", exc)
            return AnalyzerResult(
                analyzer=self.id,
                success=False,
                error=f"{type(exc).__name__}: {exc}",
                elapsed_ms=int((time.time() - started) * 1000),
            )

        answer = result.get("response") or ""
        tool_calls = result.get("tool_calls") or []
        return AnalyzerResult(
            analyzer=self.id,
            success=bool(answer),
            answer=answer,
            structured={"tool_calls": tool_calls, "session_id": sid},
            confidence=0.85 if tool_calls else 0.7,
            elapsed_ms=int((time.time() - started) * 1000),
        )
