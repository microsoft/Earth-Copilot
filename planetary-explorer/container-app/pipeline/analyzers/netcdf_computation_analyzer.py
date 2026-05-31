"""
NetCDF computation analyzer — wraps the existing NetCDFComputationAgent
(point-sampling and aggregations over NetCDF/Zarr climate cubes).
"""

from __future__ import annotations

import logging
import time
import uuid
from typing import ClassVar

from ..analyzer_protocol import Analyzer
from ..contracts import AnalysisRequest, AnalyzerResult

logger = logging.getLogger(__name__)


class NetcdfComputationAnalyzer(Analyzer):
    id: ClassVar[str] = "netcdf_computation"
    description: ClassVar[str] = (
        "Quantitative computations over gridded NetCDF / Zarr cubes: "
        "point sampling, time-series anomalies, aggregations across "
        "ensembles or scenarios. Returns numeric arrays and tables."
    )
    when_to_use: ClassVar[str] = (
        "Questions that require computing values from gridded climate data "
        "(e.g. 'sample CMIP6 tasmax at this point in 2050', 'compare two "
        "scenarios', 'compute anomaly vs baseline'). Requires a pin."
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
            from geoint.netcdf_computation_agent import get_netcdf_computation_agent
        except Exception as exc:  # pragma: no cover
            return AnalyzerResult(
                analyzer=self.id,
                success=False,
                error=f"import_error: {exc}",
                elapsed_ms=int((time.time() - started) * 1000),
            )

        agent = get_netcdf_computation_agent()
        sid = request.session_id or f"netcdf_{uuid.uuid4().hex[:8]}"

        try:
            result = await agent.chat(
                session_id=sid,
                user_message=request.question,
                latitude=lat,
                longitude=lng,
                screenshot_base64=request.screenshot_b64,
            )
        except Exception as exc:
            logger.warning("[NETCDF] chat failed: %s", exc)
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
