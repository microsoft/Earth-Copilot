"""
ClarifierDecider Executor.

Thin wrapper that exposes `ClarifierAgent.decide()` as an
`agent_framework.Executor` so the clarifier can be composed into a larger
WorkflowBuilder graph (mirrors PostgresSQL-GraphRAG's QueryRouteDetector).

The container-app currently invokes the ClarifierAgent directly per
HTTP request. This file exists so the agent is plug-compatible with
`WorkflowBuilder` if/when we later add multi-step workflows
(e.g. clarifier → router → executor → synthesizer).
"""

from __future__ import annotations

import logging
from typing import Optional

logger = logging.getLogger(__name__)

try:
    from agent_framework import (  # type: ignore
        Executor,
        WorkflowBuilder,
        WorkflowContext,
        handler,
    )
    from typing_extensions import Never  # type: ignore
    _AGENT_FRAMEWORK_AVAILABLE = True
except Exception as e:  # pragma: no cover - optional dependency
    logger.info(f"agent_framework not available ({e}); ClarifierDecider will be a stub.")
    _AGENT_FRAMEWORK_AVAILABLE = False
    Executor = object  # type: ignore
    handler = lambda f: f  # type: ignore  # noqa: E731

    class WorkflowContext:  # type: ignore
        """Stand-in so type hints below resolve at import time."""

    Never = None  # type: ignore

from ...clarifier_agent import get_clarifier_agent
from ...clarifier_models import ClarifierDecision, ClarifierInput


class ClarifierDecider(Executor):  # type: ignore[misc]
    """Executor that runs the ClarifierAgent and emits a ClarifierDecision."""

    def __init__(self, id: str = "clarifier_decider"):
        if _AGENT_FRAMEWORK_AVAILABLE:
            super().__init__(id=id)
        self.id = id
        self.agent = get_clarifier_agent()
        logger.info(f"Initialized ClarifierDecider with id: {id}")

    async def decide(self, payload: ClarifierInput) -> ClarifierDecision:
        """Direct invocation path (no workflow context)."""
        return await self.agent.decide(payload)

    if _AGENT_FRAMEWORK_AVAILABLE:
        @handler  # type: ignore
        async def on_message(
            self,
            payload: "ClarifierInput",
            ctx: "WorkflowContext[Never, ClarifierDecision]",
        ) -> None:
            decision = await self.agent.decide(payload)
            await ctx.yield_output(decision)


def build_clarifier_workflow():
    """Build a single-node workflow exposing the ClarifierDecider."""
    if not _AGENT_FRAMEWORK_AVAILABLE:
        raise RuntimeError(
            "agent_framework is not installed; cannot build a workflow. "
            "Use ClarifierAgent.decide() directly instead."
        )
    decider = ClarifierDecider()
    return WorkflowBuilder(start_executor=decider).build()  # type: ignore[arg-type]


_DECIDER_SINGLETON: Optional[ClarifierDecider] = None


def get_clarifier_decider() -> ClarifierDecider:
    """Return a process-wide singleton ClarifierDecider Executor."""
    global _DECIDER_SINGLETON
    if _DECIDER_SINGLETON is None:
        _DECIDER_SINGLETON = ClarifierDecider()
    return _DECIDER_SINGLETON
