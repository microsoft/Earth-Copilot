"""
ContextualDecider Executor — wraps ContextualAgent.run() as an
agent_framework.Executor. Mirrors the other Decider patterns; degrades
to a plain pass-through when agent_framework is not installed.
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
except Exception as e:  # pragma: no cover
    logger.info(
        f"agent_framework not available ({e}); ContextualDecider will be a stub."
    )
    _AGENT_FRAMEWORK_AVAILABLE = False
    Executor = object  # type: ignore
    handler = lambda f: f  # type: ignore  # noqa: E731

    class WorkflowContext:  # type: ignore
        """Stand-in so type hints below resolve at import time."""

    Never = None  # type: ignore

from ...contextual_agent import get_contextual_agent
from ...contextual_models import ContextualInput, ContextualResult


class ContextualDecider(Executor):  # type: ignore[misc]
    def __init__(self, id: str = "contextual_decider"):
        if _AGENT_FRAMEWORK_AVAILABLE:
            super().__init__(id=id)
        self.id = id
        self.agent = get_contextual_agent()
        logger.info(f"Initialized ContextualDecider with id: {id}")

    async def run(self, payload: ContextualInput) -> ContextualResult:
        return await self.agent.run(payload)

    if _AGENT_FRAMEWORK_AVAILABLE:
        @handler  # type: ignore
        async def on_message(
            self,
            payload: "ContextualInput",
            ctx: "WorkflowContext[Never, ContextualResult]",
        ) -> None:
            result = await self.agent.run(payload)
            await ctx.yield_output(result)


def build_contextual_workflow():
    if not _AGENT_FRAMEWORK_AVAILABLE:
        raise RuntimeError(
            "agent_framework is not installed; cannot build a workflow. "
            "Use ContextualAgent.run() directly instead."
        )
    decider = ContextualDecider()
    return WorkflowBuilder(start_executor=decider).build()  # type: ignore[arg-type]


_DECIDER_SINGLETON: Optional[ContextualDecider] = None


def get_contextual_decider() -> ContextualDecider:
    global _DECIDER_SINGLETON
    if _DECIDER_SINGLETON is None:
        _DECIDER_SINGLETON = ContextualDecider()
    return _DECIDER_SINGLETON
