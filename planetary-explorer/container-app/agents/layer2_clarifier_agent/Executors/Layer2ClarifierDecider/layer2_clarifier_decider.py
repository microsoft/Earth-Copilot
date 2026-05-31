"""
Layer2ClarifierDecider Executor.

Wraps `Layer2ClarifierAgent.decide()` as an `agent_framework.Executor` so it
can be composed into a WorkflowBuilder graph alongside the Layer-1 clarifier
and the v2 ActionRouter / AnalysisRouter executors.

Mirrors `ClarifierDecider` exactly. Falls back to a thin pass-through when
`agent_framework` is not installed (lean dev envs).
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
        f"agent_framework not available ({e}); Layer2ClarifierDecider will be a stub."
    )
    _AGENT_FRAMEWORK_AVAILABLE = False
    Executor = object  # type: ignore
    handler = lambda f: f  # type: ignore  # noqa: E731

    class WorkflowContext:  # type: ignore
        """Stand-in so type hints below resolve at import time."""

    Never = None  # type: ignore

from ...layer2_clarifier_agent import get_layer2_clarifier_agent
from ...layer2_clarifier_models import Layer2ClarifierDecision, Layer2ClarifierInput


class Layer2ClarifierDecider(Executor):  # type: ignore[misc]
    """Executor that runs the Layer2ClarifierAgent."""

    def __init__(self, id: str = "layer2_clarifier_decider"):
        if _AGENT_FRAMEWORK_AVAILABLE:
            super().__init__(id=id)
        self.id = id
        self.agent = get_layer2_clarifier_agent()
        logger.info(f"Initialized Layer2ClarifierDecider with id: {id}")

    async def decide(self, payload: Layer2ClarifierInput) -> Layer2ClarifierDecision:
        return await self.agent.decide(payload)

    if _AGENT_FRAMEWORK_AVAILABLE:
        @handler  # type: ignore
        async def on_message(
            self,
            payload: "Layer2ClarifierInput",
            ctx: "WorkflowContext[Never, Layer2ClarifierDecision]",
        ) -> None:
            decision = await self.agent.decide(payload)
            await ctx.yield_output(decision)


def build_layer2_clarifier_workflow():
    if not _AGENT_FRAMEWORK_AVAILABLE:
        raise RuntimeError(
            "agent_framework is not installed; cannot build a workflow. "
            "Use Layer2ClarifierAgent.decide() directly instead."
        )
    decider = Layer2ClarifierDecider()
    return WorkflowBuilder(start_executor=decider).build()  # type: ignore[arg-type]


_DECIDER_SINGLETON: Optional[Layer2ClarifierDecider] = None


def get_layer2_clarifier_decider() -> Layer2ClarifierDecider:
    global _DECIDER_SINGLETON
    if _DECIDER_SINGLETON is None:
        _DECIDER_SINGLETON = Layer2ClarifierDecider()
    return _DECIDER_SINGLETON
