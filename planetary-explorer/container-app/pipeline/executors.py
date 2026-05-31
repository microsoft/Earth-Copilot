"""Microsoft Agent Framework executor wrapper for the Layer-1 ActionRouter.

After Wave 10 / REQ-ARCH-1, the legacy ``AnalysisRouterExecutor`` and
``OrchestratorExecutor`` are gone — Layer 2 is now the single
:class:`agents.analyst_agent.AnalystAgent`. Only the ActionRouter wrapper
remains, because dispatch still uses it as the Layer-1 classifier.

When ``agent_framework`` is not installed (lean dev environments), the
class degrades to a plain object whose ``route()`` method works
identically.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Optional

from .action_router import ActionRouter
from .contracts import ActionDecision, AnalysisRequest

logger = logging.getLogger(__name__)

try:
    from agent_framework import (  # type: ignore
        Executor,
        WorkflowContext,
        handler,
    )

    _AGENT_FRAMEWORK_AVAILABLE = True
except Exception as _af_exc:  # pragma: no cover - optional dependency
    logger.info(
        "agent_framework not available (%s); ActionRouterExecutor will be a "
        "plain pass-through.",
        _af_exc,
    )
    _AGENT_FRAMEWORK_AVAILABLE = False
    Executor = object  # type: ignore
    handler = lambda f: f  # type: ignore  # noqa: E731

    class WorkflowContext:  # type: ignore
        """Stand-in so type hints below resolve at import time."""


# ---------------------------------------------------------------------------
# Envelope (kept for any caller that imports it).
# ---------------------------------------------------------------------------


@dataclass
class PipelineMessage:
    """Typed message threaded through Layer-1. After Wave 10 the
    ``plan`` and ``response`` slots are unused; preserved for source
    compatibility with any external caller that pickles this dataclass."""

    request: AnalysisRequest
    decision: Optional[ActionDecision] = None
    plan: object = None
    response: object = None


# ---------------------------------------------------------------------------
# ActionRouterExecutor.
# ---------------------------------------------------------------------------


class ActionRouterExecutor(Executor):  # type: ignore[misc]
    """Executor wrapping :class:`ActionRouter` for the v2 dispatch hot path."""

    def __init__(
        self,
        router: ActionRouter | None = None,
        id: str = "action_router",
    ) -> None:
        if _AGENT_FRAMEWORK_AVAILABLE:
            super().__init__(id=id)
        self.id = id
        self.router = router or ActionRouter()
        logger.info("Initialized ActionRouterExecutor id=%s", id)

    async def route(
        self,
        query: str,
        loaded_collections: list[str] | None = None,
        has_pin: bool = False,
        has_screenshot: bool = False,
    ) -> ActionDecision:
        return await self.router.route(
            query=query,
            loaded_collections=loaded_collections,
            has_pin=has_pin,
            has_screenshot=has_screenshot,
        )

    if _AGENT_FRAMEWORK_AVAILABLE:
        @handler  # type: ignore
        async def on_message(
            self,
            msg: "PipelineMessage",
            ctx: "WorkflowContext[PipelineMessage]",
        ) -> None:
            req = msg.request
            decision = await self.router.route(
                query=req.question,
                loaded_collections=req.loaded_collections or [],
                has_pin=bool(req.pin),
                has_screenshot=bool(req.screenshot_b64 or req.has_screenshot),
            )
            msg.decision = decision
            await ctx.send_message(msg)


# ---------------------------------------------------------------------------
# Singleton accessor (back-compat).
# ---------------------------------------------------------------------------


_ACTION_ROUTER_EXECUTOR_SINGLETON: Optional[ActionRouterExecutor] = None


def get_action_router_executor() -> ActionRouterExecutor:
    global _ACTION_ROUTER_EXECUTOR_SINGLETON
    if _ACTION_ROUTER_EXECUTOR_SINGLETON is None:
        _ACTION_ROUTER_EXECUTOR_SINGLETON = ActionRouterExecutor()
    return _ACTION_ROUTER_EXECUTOR_SINGLETON
