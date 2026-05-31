"""
Extreme weather analyzer — wraps the existing ExtremeWeatherAgent
(NASA NEX-GDDP-CMIP6 climate projections via Azure AI Agent Service).
"""

from __future__ import annotations

import logging
import time
import uuid
from typing import ClassVar

from ..analyzer_protocol import Analyzer
from ..contracts import AnalysisRequest, AnalyzerResult, Source

logger = logging.getLogger(__name__)


class ExtremeWeatherAnalyzer(Analyzer):
    id: ClassVar[str] = "extreme_weather"
    description: ClassVar[str] = (
        "Future climate projections (temperature, precipitation, wind, "
        "humidity, radiation) from NASA NEX-GDDP-CMIP6, downscaled to "
        "~25 km. Supports SSP2-4.5 vs SSP5-8.5 scenario comparison."
    )
    when_to_use: ClassVar[str] = (
        "Questions about future climate, warming projections, change in "
        "precipitation, drought risk, scenario comparison. Requires a pin."
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
            from geoint.extreme_weather_agent import get_extreme_weather_agent
        except Exception as exc:  # pragma: no cover
            return AnalyzerResult(
                analyzer=self.id,
                success=False,
                error=f"import_error: {exc}",
                elapsed_ms=int((time.time() - started) * 1000),
            )

        agent = get_extreme_weather_agent()
        sid = request.session_id or f"climate_{uuid.uuid4().hex[:8]}"
        message = (
            request.question
            or "Provide a comprehensive climate projection overview for this location."
        )

        try:
            result = await agent.chat(
                session_id=sid,
                user_message=message,
                latitude=lat,
                longitude=lng,
                screenshot_base64=request.screenshot_b64,
            )
        except Exception as exc:
            logger.warning("[CLIMATE] chat failed: %s", exc)
            return AnalyzerResult(
                analyzer=self.id,
                success=False,
                error=f"{type(exc).__name__}: {exc}",
                elapsed_ms=int((time.time() - started) * 1000),
            )

        answer = result.get("response") or ""
        tool_calls = result.get("tool_calls") or []
        sources = [
            Source(
                title="NASA NEX-GDDP-CMIP6",
                uri="https://www.nccs.nasa.gov/services/data-collections/land-based-products/nex-gddp-cmip6",
                kind="dataset",
            )
        ]
        return AnalyzerResult(
            analyzer=self.id,
            success=bool(answer),
            answer=answer,
            structured={
                "tool_calls": tool_calls,
                "session_id": sid,
                "imagery_metadata": {
                    "source": "NASA NEX-GDDP-CMIP6",
                    "resolution": "0.25° (~25 km)",
                    "format": "NetCDF (point-sampled, no map tiles)",
                },
            },
            sources=sources,
            confidence=0.85 if tool_calls else 0.7,
            elapsed_ms=int((time.time() - started) * 1000),
        )
