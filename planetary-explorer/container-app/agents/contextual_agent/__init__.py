"""
Contextual Agent — designated agent for educational / general-knowledge
Earth-observation answers when no map state is required.

Replaces the diagram's "Text → contextual" box. Single LLM call with a
tight system prompt that scopes the model to Earth observation. Mirrors
the `agents/clarifier_agent/` package layout.

The pipeline `LLMOnlyAnalyzer` delegates to `ContextualAgent.run()` so the
v2 surface area is consistent with every other Layer-2 agent.
"""

from .contextual_models import ContextualInput, ContextualResult
from .contextual_agent import ContextualAgent, get_contextual_agent
from .Executors.ContextualDecider.contextual_decider import (  # noqa: E402
    ContextualDecider,
    build_contextual_workflow,
    get_contextual_decider,
)

__all__ = [
    "ContextualAgent",
    "ContextualDecider",
    "ContextualInput",
    "ContextualResult",
    "build_contextual_workflow",
    "get_contextual_agent",
    "get_contextual_decider",
]
