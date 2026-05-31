"""
Convenience bootstrap for the v2 pipeline (Wave 10 / REQ-ARCH-1).

After the Layer-2 ReAct refactor, the pipeline's composition root is
much smaller: dispatch only needs the Layer-1 :class:`ActionRouterExecutor`.
The Layer-2 single :class:`AnalystAgent` (Azure AI Agent Service) is a
self-contained singleton accessed via
``agents.analyst_agent.get_analyst_agent()``.

``build_default_pipeline()`` is preserved as a thin shim returning the
old 4-tuple so existing call sites keep working during the transition;
the orchestrator / registry / analysis_router slots are ``None``. New
code should depend on :func:`get_action_router` instead.
"""

from __future__ import annotations

import logging
from functools import lru_cache

from .action_router import ActionRouter
from .executors import ActionRouterExecutor

logger = logging.getLogger(__name__)


@lru_cache(maxsize=1)
def get_action_router() -> ActionRouterExecutor:
    """Return the singleton ActionRouterExecutor (Layer 1 classifier)."""
    logger.info("[PIPELINE] v2 Layer-1 ActionRouterExecutor ready (Wave 10)")
    return ActionRouterExecutor(router=ActionRouter())


@lru_cache(maxsize=1)
def build_default_pipeline():
    """Back-compat shim returning the old 4-tuple shape.

    After Wave 10, only the first element (the ActionRouter) is meaningful;
    the other three slots are ``None``. Callers should migrate to
    :func:`get_action_router`.
    """
    return get_action_router(), None, None, None
