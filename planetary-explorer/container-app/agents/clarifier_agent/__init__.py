"""
Clarifier Agent — Layer-0 conversational router.

Mirrors the agent_framework pattern used by PostgresSQL-GraphRAG's
QueryRouteDetector: an Executor wrapping a single structured-output LLM
call, with a thin WorkflowBuilder wrapper for composability.

Public surface:
    >>> agent = ClarifierAgent()
    >>> decision = await agent.decide(
    ...     query="flooding",
    ...     has_rendered_map=False,
    ...     has_screenshot=False,
    ...     has_last_bbox=False,
    ...     pending_clarification=False,
    ...     prior_router_action=None,
    ... )
    >>> decision.action          # "clarify"
    >>> decision.missing_slot    # "intent"
    >>> decision.user_response   # "Here's what I can help you with..."
    >>> decision.options         # ["Go to a place", ...]
"""

from .clarifier_models import ClarifierDecision, ClarifierInput
from .clarifier_agent import ClarifierAgent, get_clarifier_agent

# Optional Microsoft Agent Framework Executor wrapper. Imported here so the
# call site can use it without reaching deep into the Executors/ subpackage.
# When agent_framework is not installed, ClarifierDecider degrades to a thin
# pass-through class that still exposes `decide()`.
from .Executors.ClarifierDecider.clarifier_decider import (  # noqa: E402
    ClarifierDecider,
    build_clarifier_workflow,
    get_clarifier_decider,
)

__all__ = [
    "ClarifierAgent",
    "ClarifierDecider",
    "ClarifierDecision",
    "ClarifierInput",
    "build_clarifier_workflow",
    "get_clarifier_agent",
    "get_clarifier_decider",
]
