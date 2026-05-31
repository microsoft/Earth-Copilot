"""Contracts: round-trip serialization, defaults, forward-ref resolution."""

from __future__ import annotations

from pipeline.contracts import (
    ActionDecision,
    AnalysisPlan,
    AnalysisRequest,
    AnalysisStep,
    AnalyzerResult,
    Source,
    SynthesizedResponse,
    Visualization,
)


def test_source_defaults():
    s = Source(title="t")
    assert s.kind == "doc"
    assert s.uri is None
    assert s.score is None


def test_visualization_kinds():
    v = Visualization(kind="raster_layer", spec={"url": "x"})
    assert v.spec["url"] == "x"


def test_analysis_request_defaults_and_grounding_forward_ref():
    req = AnalysisRequest(question="q", session_id="s")
    assert req.grounding == []
    # Forward ref to AnalyzerResult should resolve via model_rebuild()
    grounded = req.model_copy(
        update={"grounding": [AnalyzerResult(analyzer="x", answer="hi")]}
    )
    assert grounded.grounding[0].analyzer == "x"


def test_analyzer_result_defaults():
    r = AnalyzerResult(analyzer="a")
    assert r.success is True
    assert r.confidence == 0.0
    assert r.warnings == []
    assert r.error is None


def test_analysis_plan_is_empty():
    assert AnalysisPlan().is_empty()
    assert not AnalysisPlan(steps=[AnalysisStep(analyzer="x")]).is_empty()


def test_action_decision_literal():
    d = ActionDecision(action="ANALYZE")
    assert d.action == "ANALYZE"
    assert d.confidence == 0.0


def test_synthesized_response_roundtrip():
    s = SynthesizedResponse(answer="hi", sources=[Source(title="t")])
    dumped = s.model_dump()
    restored = SynthesizedResponse(**dumped)
    assert restored.answer == "hi"
    assert restored.sources[0].title == "t"
