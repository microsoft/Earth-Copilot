"""
RasterSamplingDecider Executor.

Thin wrapper that exposes `RasterSamplingAgent.run()` as an
`agent_framework.Executor` so the agent can be composed into a larger
WorkflowBuilder graph alongside the routers and other Layer-2 deciders.

Mirrors `ClarifierDecider` and `Layer2ClarifierDecider`. Falls back to a
plain pass-through when `agent_framework` is not installed.
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
        f"agent_framework not available ({e}); RasterSamplingDecider will be a stub."
    )
    _AGENT_FRAMEWORK_AVAILABLE = False
    Executor = object  # type: ignore
    handler = lambda f: f  # type: ignore  # noqa: E731

    class WorkflowContext:  # type: ignore
        """Stand-in so type hints below resolve at import time."""

    Never = None  # type: ignore

from ...raster_sampling_agent import get_raster_sampling_agent
from ...raster_sampling_models import RasterSamplingInput, RasterSamplingResult


class RasterSamplingDecider(Executor):  # type: ignore[misc]
    """Executor that runs the RasterSamplingAgent."""

    def __init__(self, id: str = "raster_sampling_decider"):
        if _AGENT_FRAMEWORK_AVAILABLE:
            super().__init__(id=id)
        self.id = id
        self.agent = get_raster_sampling_agent()
        logger.info(f"Initialized RasterSamplingDecider with id: {id}")

    async def run(self, payload: RasterSamplingInput) -> RasterSamplingResult:
        return await self.agent.run(payload)

    if _AGENT_FRAMEWORK_AVAILABLE:
        @handler  # type: ignore
        async def on_message(
            self,
            payload: "RasterSamplingInput",
            ctx: "WorkflowContext[Never, RasterSamplingResult]",
        ) -> None:
            result = await self.agent.run(payload)
            await ctx.yield_output(result)


def build_raster_sampling_workflow():
    if not _AGENT_FRAMEWORK_AVAILABLE:
        raise RuntimeError(
            "agent_framework is not installed; cannot build a workflow. "
            "Use RasterSamplingAgent.run() directly instead."
        )
    decider = RasterSamplingDecider()
    return WorkflowBuilder(start_executor=decider).build()  # type: ignore[arg-type]


_DECIDER_SINGLETON: Optional[RasterSamplingDecider] = None


def get_raster_sampling_decider() -> RasterSamplingDecider:
    global _DECIDER_SINGLETON
    if _DECIDER_SINGLETON is None:
        _DECIDER_SINGLETON = RasterSamplingDecider()
    return _DECIDER_SINGLETON
