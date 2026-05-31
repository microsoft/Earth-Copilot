"""Minimal :class:`Analyzer` base class.

After Wave 10 / REQ-ARCH-1, ``Analyzer`` is no longer the centerpiece
of Layer 2 — the :class:`AnalystAgent` ReAct loop has taken over. We
keep this protocol around because the existing analyzer wrappers in
``pipeline/analyzers/*.py`` (which are now invoked from tool functions
in ``agents/analyst_agent/tools.py``) all inherit from it. Their
implementations are unchanged.

Removed: the legacy ``description`` / ``when_to_use`` prompt-only fields,
the ``AnalyzerRegistry``, and anything the AnalysisRouter prompt used to
introspect. None of those mattered after the agent replaced the router.
"""

from __future__ import annotations

from typing import ClassVar, Tuple

from .contracts import AnalysisRequest, AnalyzerResult


class Analyzer:
    """Base class for the legacy analyzer wrappers used by AnalystAgent tools.

    Each subclass declares:
      * ``id`` — short name for logging/evidence
      * ``requires`` — optional tuple of feature flags (``"pin"``,
        ``"loaded_raster"``, ``"screenshot"``, ``"bbox"``,
        ``"time_range"``) the analyzer needs from the request

    and overrides ``analyze()``. ``can_run()`` defaults to a slot
    presence check.
    """

    id: ClassVar[str] = "base"
    requires: ClassVar[Tuple[str, ...]] = ()

    async def analyze(self, request: AnalysisRequest) -> AnalyzerResult:  # pragma: no cover
        raise NotImplementedError

    def can_run(self, request: AnalysisRequest) -> bool:
        for req in self.requires:
            if req == "pin" and not request.pin:
                return False
            if req == "loaded_raster" and not request.loaded_collections:
                return False
            if req == "screenshot" and not (
                request.screenshot_b64 or request.screenshot_url or request.has_screenshot
            ):
                return False
            if req == "bbox" and not request.bbox:
                return False
            if req == "time_range" and not request.time_range:
                return False
        return True
