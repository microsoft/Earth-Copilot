"""
Comparison analyzer — produces a structured delta / contrast across two or
more locations. Designed to run AFTER `raster_sampling` (which samples each
pin and folds its result into `grounding`), or stand-alone over `pins` /
location names extracted by the planner via the `hint` field.

Behavior:
  * If `request.grounding` already contains one or more raster_sampling
    results (one entry per sampled pin), the analyzer reads those numeric
    values and produces a deterministic structured comparison plus an
    LLM-written short narrative.
  * Otherwise, if `request.pins` has >= 2 entries and a raster is loaded,
    the analyzer attempts to sample each pin in-process via the legacy
    `vision_tools.sample_raster_value` helper.
  * If neither path produces >= 2 numeric values, returns success=False
    with a graceful message — the orchestrator continues.

Returns:
  structured = {
    "metric_name": str | None,
    "unit": str | None,
    "samples": [ {"label": str, "lat": float, "lng": float, "value": float}, ... ],
    "delta": float | None,        # (b - a) when exactly two samples
    "max_label": str | None,
    "min_label": str | None,
  }
"""

from __future__ import annotations

import logging
import time
from typing import Any, ClassVar

from .._aoai import fast_deployment, get_aoai_client
from ..analyzer_protocol import Analyzer
from ..contracts import AnalysisRequest, AnalyzerResult

logger = logging.getLogger(__name__)


_NARRATIVE_SYSTEM = """You write a 2-3 sentence comparison between sampled
raster values at multiple locations. Be quantitative. Reference the metric
name and unit. If a delta is provided, lead with it. Do not invent numbers
beyond the supplied samples."""


def _samples_from_grounding(request: AnalysisRequest) -> list[dict[str, Any]]:
    """Extract per-pin samples from upstream raster_sampling results."""
    samples: list[dict[str, Any]] = []
    metric: str | None = None
    unit: str | None = None
    for r in request.grounding:
        if r.analyzer != "raster_sampling" or not r.success:
            continue
        s = r.structured or {}
        # raster_sampling typically populates structured with at least
        # {value, unit, lat, lng, metric/asset_name}.
        val = s.get("value") if isinstance(s.get("value"), (int, float)) else None
        if val is None:
            continue
        lat = s.get("lat") or s.get("pin_lat")
        lng = s.get("lng") or s.get("pin_lng")
        samples.append(
            {
                "label": s.get("label") or s.get("location_name") or f"({lat:.3f},{lng:.3f})"
                if lat is not None and lng is not None
                else "?",
                "lat": lat,
                "lng": lng,
                "value": float(val),
            }
        )
        metric = metric or s.get("metric") or s.get("asset_name") or s.get("variable")
        unit = unit or s.get("unit")
    return samples, metric, unit  # type: ignore[return-value]


async def _sample_pins_inline(
    request: AnalysisRequest,
) -> tuple[list[dict[str, Any]], str | None, str | None]:
    """Fallback path when the planner did not run raster_sampling first."""
    if len(request.pins) < 2 or not request.loaded_collections:
        return [], None, None
    try:
        from agents.vision_tools import sample_raster_value, set_session_context  # type: ignore
    except Exception as exc:  # pragma: no cover
        logger.warning("[COMPARISON] vision_tools unavailable: %s", exc)
        return [], None, None

    samples: list[dict[str, Any]] = []
    metric: str | None = None
    unit: str | None = None
    for lat, lng in request.pins[:5]:
        try:
            set_session_context(
                request.session_id,
                map_bounds={"pin_lat": lat, "pin_lng": lng},
                stac_items=request.stac_items,
                tile_urls=request.tile_urls,
            )
            sampled = await sample_raster_value()  # type: ignore[misc]
            if not isinstance(sampled, dict) or not sampled.get("success"):
                continue
            val = sampled.get("value")
            if not isinstance(val, (int, float)):
                continue
            samples.append(
                {
                    "label": f"({lat:.3f},{lng:.3f})",
                    "lat": lat,
                    "lng": lng,
                    "value": float(val),
                }
            )
            metric = metric or sampled.get("metric") or sampled.get("asset_name")
            unit = unit or sampled.get("unit")
        except Exception as exc:  # noqa: BLE001
            logger.info("[COMPARISON] inline sample failed at %s,%s: %s", lat, lng, exc)
    return samples, metric, unit


class ComparisonAnalyzer(Analyzer):
    id: ClassVar[str] = "comparison"
    description: ClassVar[str] = (
        "Compares numeric raster values across two or more pinned locations "
        "and produces a quantitative delta / max / min summary. Consumes "
        "raster_sampling grounding when present; otherwise samples each pin "
        "from the loaded raster in-process. Use for 'compare A and B', "
        "'which is hotter X or Y', and multi-pin questions."
    )
    when_to_use: ClassVar[str] = (
        "User asks to compare values across two or more locations or pins, "
        "or asks 'which of A/B is higher/lower/hotter/colder'."
    )
    requires: ClassVar[tuple[str, ...]] = ("loaded_raster",)

    def __init__(self, deployment: str | None = None) -> None:
        self._deployment = deployment or fast_deployment()

    def can_run(self, request: AnalysisRequest) -> bool:  # noqa: D401
        if not super().can_run(request):
            return False
        # Need either upstream samples or >= 2 pins.
        has_samples = any(
            r.analyzer == "raster_sampling" and r.success for r in request.grounding
        )
        if has_samples:
            return True
        return len(request.pins) >= 2

    async def analyze(self, request: AnalysisRequest) -> AnalyzerResult:
        started = time.time()

        samples, metric, unit = _samples_from_grounding(request)
        if len(samples) < 2:
            inline_samples, inline_metric, inline_unit = await _sample_pins_inline(request)
            if len(inline_samples) >= 2:
                samples = inline_samples
                metric = metric or inline_metric
                unit = unit or inline_unit

        if len(samples) < 2:
            return AnalyzerResult(
                analyzer=self.id,
                success=False,
                answer=(
                    "I need at least two sampled locations to compare. Drop "
                    "a second pin (or ask me to sample two specific places) "
                    "and try again."
                ),
                warnings=["insufficient_samples"],
                elapsed_ms=int((time.time() - started) * 1000),
            )

        sorted_samples = sorted(samples, key=lambda s: s["value"])
        min_s = sorted_samples[0]
        max_s = sorted_samples[-1]
        delta = max_s["value"] - min_s["value"] if len(samples) == 2 else None

        structured: dict[str, Any] = {
            "metric_name": metric,
            "unit": unit,
            "samples": samples,
            "delta": delta,
            "max_label": max_s["label"],
            "min_label": min_s["label"],
        }

        # Short LLM narrative — single chat completion. Falls back to a
        # deterministic template if the LLM call fails.
        try:
            client = get_aoai_client()
            user_payload = (
                f"Metric: {metric or 'value'} ({unit or 'unitless'})\n"
                f"Samples: {samples}\n"
                f"Delta (max-min): {delta}\n"
                f"User question: {request.question}"
            )
            resp = await client.chat.completions.create(
                model=self._deployment,
                messages=[
                    {"role": "system", "content": _NARRATIVE_SYSTEM},
                    {"role": "user", "content": user_payload},
                ],
                temperature=0.2,
            )
            narrative = (resp.choices[0].message.content or "").strip()
        except Exception as exc:  # noqa: BLE001
            logger.warning("[COMPARISON] narrative LLM failed: %s", exc)
            unit_str = f" {unit}" if unit else ""
            narrative = (
                f"{max_s['label']} is highest at {max_s['value']:.3f}{unit_str}; "
                f"{min_s['label']} is lowest at {min_s['value']:.3f}{unit_str}."
                + (f" Delta: {delta:.3f}{unit_str}." if delta is not None else "")
            )

        return AnalyzerResult(
            analyzer=self.id,
            success=True,
            answer=narrative,
            structured=structured,
            confidence=0.7,
            elapsed_ms=int((time.time() - started) * 1000),
        )
