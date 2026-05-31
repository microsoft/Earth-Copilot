"""Process-local pubsub for MCP trace events.

The chat SSE routes register a listener at the start of a request and
unregister at the end. :class:`TracedMcpClient` emits ``tool_call`` and
``tool_result`` events into the currently-registered listener (resolved
through :mod:`contextvars` so concurrent requests stay isolated).

If no listener is registered, emission is a no-op — so the rest of the
codebase pays nothing for tracing when no UI is attached.
"""
from __future__ import annotations

import contextvars
import logging
from typing import Any, Awaitable, Callable

logger = logging.getLogger(__name__)

TraceListener = Callable[[dict[str, Any]], Awaitable[None]]

_current_listener: contextvars.ContextVar[TraceListener | None] = contextvars.ContextVar(
    "mcp_trace_listener", default=None
)


def set_listener(listener: TraceListener | None) -> contextvars.Token:
    """Register a listener for the current async context. Returns a
    token that must be passed to :func:`reset_listener` to clean up."""
    return _current_listener.set(listener)


def reset_listener(token: contextvars.Token) -> None:
    _current_listener.reset(token)


async def emit(event: dict[str, Any]) -> None:
    """Best-effort emit. Listener exceptions are swallowed so a broken
    UI consumer never breaks an agent turn."""
    listener = _current_listener.get()
    if listener is None:
        return
    try:
        await listener(event)
    except Exception:  # noqa: BLE001
        logger.debug("trace listener raised; ignoring", exc_info=True)
