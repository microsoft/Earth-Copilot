"""
Mobility analyzer — wraps the existing GeointMobilityAgent (GO/SLOW-GO/NO-GO
trafficability classification with optional A->B routing).
"""

from __future__ import annotations

import logging
import time
from typing import ClassVar

from ..analyzer_protocol import Analyzer
from ..contracts import AnalysisRequest, AnalyzerResult

logger = logging.getLogger(__name__)


class MobilityAnalyzer(Analyzer):
    id: ClassVar[str] = "mobility"
    description: ClassVar[str] = (
        "Trafficability assessment from terrain + land-cover. Produces "
        "GO/SLOW-GO/NO-GO classification, slope analysis, water-body "
        "detection, and (when GPT-5 Vision is enabled) interpretive notes."
    )
    when_to_use: ClassVar[str] = (
        "Questions about traversability, route planning, off-road access, "
        "or 'can a vehicle/unit cross this terrain'. Requires a pin."
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
            from geoint.mobility_agent import get_mobility_agent
        except Exception as exc:  # pragma: no cover
            return AnalyzerResult(
                analyzer=self.id,
                success=False,
                error=f"import_error: {exc}",
                elapsed_ms=int((time.time() - started) * 1000),
            )

        agent = get_mobility_agent()
        try:
            result = await agent.analyze_mobility(
                latitude=lat,
                longitude=lng,
                user_context=request.question,
                include_vision_analysis=bool(
                    request.screenshot_b64 or request.has_screenshot
                ),
                screenshot_base64=request.screenshot_b64,
            )
        except Exception as exc:
            logger.warning("[MOBILITY] analyze_mobility failed: %s", exc)
            return AnalyzerResult(
                analyzer=self.id,
                success=False,
                error=f"{type(exc).__name__}: {exc}",
                elapsed_ms=int((time.time() - started) * 1000),
            )

        # Mobility agent returns rich structured data; keep it all under
        # `structured` and compose a compact answer for the synthesizer.
        answer = (
            result.get("vision_analysis")
            or result.get("analysis")
            or result.get("summary")
            or ""
        )
        zones = result.get("mobility_zones") or {}
        if not answer and zones:
            go = zones.get("go_zones", {}).get("percentage", 0)
            slow = zones.get("slow_go_zones", {}).get("percentage", 0)
            no = zones.get("no_go_zones", {}).get("percentage", 0)
            answer = (
                f"Mobility classification: {go:.0f}% GO, {slow:.0f}% SLOW-GO, "
                f"{no:.0f}% NO-GO around ({lat:.4f}, {lng:.4f})."
            )

        return AnalyzerResult(
            analyzer=self.id,
            success=bool(answer or zones),
            answer=answer,
            structured={
                k: v
                for k, v in result.items()
                if k
                in (
                    "mobility_zones",
                    "slope_analysis",
                    "water_bodies",
                    "roads",
                    "trafficability_map",
                )
            },
            confidence=0.8,
            elapsed_ms=int((time.time() - started) * 1000),
        )
