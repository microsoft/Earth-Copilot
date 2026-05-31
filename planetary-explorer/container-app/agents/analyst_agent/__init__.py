"""AnalystAgent — Layer 2 ReAct agent (REQ-ARCH-1).

Single Azure AI Agent Service agent with a tool catalog that replaces:
- pipeline/analysis_router.py
- pipeline/orchestrator.py
- pipeline/synthesizer.py
- pipeline/analyzer_registry.py
- pipeline/analyzers/*.py wrappers
- pipeline/layer2_agents.py
- pipeline/bootstrap.py (composition root)

The underlying domain agents (EnhancedVisionAgent, TerrainAgent,
GeointMobilityAgent, ExtremeWeatherAgent, NetCDFComputationAgent,
RasterSamplingAgent, ContextualAgent, ChatVisionAnalyzer) are unchanged
and are wrapped by tool functions in ``tools.py``.
"""

from .analyst_agent import AnalystAgent, get_analyst_agent

__all__ = ["AnalystAgent", "get_analyst_agent"]
