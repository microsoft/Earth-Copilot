"""
LLM-only analyzer — educational/general-knowledge fallback.

Used when no specialized analyzer fits the question (e.g. "explain how MODIS
detects active fires"). Issues a single chat completion with a tight system
prompt that scopes the model to Earth observation topics.
"""

from __future__ import annotations

import logging
import time
from typing import ClassVar

from .._aoai import fast_deployment, get_aoai_client
from ..analyzer_protocol import Analyzer
from ..contracts import AnalysisRequest, AnalyzerResult

logger = logging.getLogger(__name__)


_SYSTEM_PROMPT = """You are an Earth observation subject-matter expert. Answer
the user's question accurately and concisely. Stay within Earth observation,
remote sensing, geospatial analysis, and adjacent science. If you don't know
or the question is out of scope, say so plainly.

Do not invent dataset names, sensor specs, or numeric thresholds. If you
reference a methodology, name the source (paper, agency, standard) at a
high level."""


class LLMOnlyAnalyzer(Analyzer):
    id: ClassVar[str] = "llm_only"
    description: ClassVar[str] = (
        "General-knowledge Earth-observation answers using only the LLM. "
        "No external data lookups, no map state required. Use this as the "
        "fallback when no specialized analyzer fits."
    )
    when_to_use: ClassVar[str] = (
        "Educational questions, definitions, or general explanations that do "
        "not need authoritative documents or pixel-level data."
    )
    requires: ClassVar[tuple[str, ...]] = ()

    async def analyze(self, request: AnalysisRequest) -> AnalyzerResult:
        started = time.time()

        # Delegate to the designated ContextualAgent (MAF Executor) so the
        # diagram's "Text → contextual" box has its own named agent.
        try:
            from agents.contextual_agent import (
                get_contextual_agent,
                ContextualInput,
            )
        except Exception as exc:  # pragma: no cover
            logger.warning("[LLM_ONLY] agent import failed: %s", exc)
            return AnalyzerResult(
                analyzer=self.id,
                success=False,
                error=f"import_error: {exc}",
                elapsed_ms=int((time.time() - started) * 1000),
            )

        result = await get_contextual_agent().run(
            ContextualInput(
                question=request.question,
                hint=request.hint,
                history=list(request.history or []),
            )
        )

        return AnalyzerResult(
            analyzer=self.id,
            success=result.success,
            answer=result.answer,
            confidence=result.confidence,
            error=result.error,
            elapsed_ms=result.elapsed_ms or int((time.time() - started) * 1000),
        )
