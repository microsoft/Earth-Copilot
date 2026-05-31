"""
Planetary Explorer v2 Pipeline (Wave 10 / REQ-ARCH-1)
================================================

Layer 1 (ActionRouter):  decides WHAT TO DO  ->  NAVIGATE | LOAD | ANALYZE | LOAD_AND_ANALYZE
Layer 2 (AnalystAgent):  single Azure AI Agent Service ReAct agent with a
                         tool catalog (see ``agents/analyst_agent``).

The legacy ``AnalysisRouter`` / ``Orchestrator`` / ``Synthesizer`` and the
9-analyzer registry were removed in Wave 10. The underlying domain
agents (vision, terrain, mobility, ...) are now wrapped as tool functions
inside ``agents/analyst_agent/tools.py``.
"""

from .contracts import (
    Source,
    Visualization,
    AnalysisRequest,
    AnalyzerResult,
    AnalysisStep,
    AnalysisPlan,
    ActionDecision,
    SynthesizedResponse,
)
from .dispatch import run_pipeline_v2

__all__ = [
    "Source",
    "Visualization",
    "AnalysisRequest",
    "AnalyzerResult",
    "AnalysisStep",
    "AnalysisPlan",
    "ActionDecision",
    "SynthesizedResponse",
    "run_pipeline_v2",
]
