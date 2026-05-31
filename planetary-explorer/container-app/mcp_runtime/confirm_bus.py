"""Process-local broker for MCP write/destructive confirmations.

Backend agents pause for explicit approval before WRITE or DESTRUCTIVE
tools fire. The flow is:

1. :class:`TracedMcpClient` classifies a tool, sees tier != READ, and
   calls :func:`request_confirmation(trace_id, tool, args, tier)`.
2. The broker registers an :class:`asyncio.Event` keyed by ``trace_id``
   and emits a ``confirm_request`` trace event so the UI can render a
   card.
3. The UI POSTs ``/api/mcp/confirm`` with ``{trace_id, approved}``.
   The HTTP handler calls :func:`resolve_confirmation(trace_id, approved)``
   which records the outcome and sets the event.
4. :func:`request_confirmation` returns ``approved``; ``TracedMcpClient``
   either dispatches the tool or raises ``PermissionError``.

Times out after :data:`DEFAULT_CONFIRM_TIMEOUT_SECONDS`; treats timeout
as denial so a dropped UI never deadlocks an agent turn.

The broker is process-local on purpose — every backend replica owns
its own pending set. Routing the confirm POST to the right replica is
the affinity layer's problem; Container Apps' sticky sessions handle
this for the streaming SSE channel which originates the request.
"""
from __future__ import annotations

import asyncio
import logging
import os
from dataclasses import dataclass, field
from typing import Any

from .trace_bus import emit as emit_trace


logger = logging.getLogger(__name__)


def _default_timeout() -> float:
    try:
        return float(os.getenv("MCP_CONFIRM_TIMEOUT_SECONDS", "120"))
    except (TypeError, ValueError):
        return 120.0


DEFAULT_CONFIRM_TIMEOUT_SECONDS = _default_timeout()


@dataclass
class _PendingConfirm:
    event: asyncio.Event = field(default_factory=asyncio.Event)
    approved: bool | None = None
    note: str | None = None


_pending: dict[str, _PendingConfirm] = {}
_lock = asyncio.Lock()


async def request_confirmation(
    *,
    trace_id: str,
    server_id: str,
    tool: str,
    args: dict[str, Any],
    tier: str,
    turn_id: str | None = None,
    timeout: float | None = None,
) -> tuple[bool, str | None]:
    """Block until the UI resolves this confirmation (or the timeout fires).

    Returns ``(approved, note)``. ``note`` is an operator-supplied
    reason string if provided in the resolve POST, else ``None``.
    """
    async with _lock:
        if trace_id in _pending:
            # Defensive: a duplicate request for the same trace is a
            # programmer error. Treat it as "the prior pending wins".
            pending = _pending[trace_id]
        else:
            pending = _PendingConfirm()
            _pending[trace_id] = pending

    # Surface the request to whatever SSE channel is currently listening.
    await emit_trace(
        {
            "type": "confirm_request",
            "trace_id": trace_id,
            "turn_id": turn_id,
            "server_id": server_id,
            "tool": tool,
            "args": args,
            "tier": tier,
        }
    )

    wait_timeout = timeout if timeout is not None else DEFAULT_CONFIRM_TIMEOUT_SECONDS
    try:
        await asyncio.wait_for(pending.event.wait(), timeout=wait_timeout)
    except asyncio.TimeoutError:
        async with _lock:
            _pending.pop(trace_id, None)
        await emit_trace(
            {
                "type": "confirm_resolved",
                "trace_id": trace_id,
                "approved": False,
                "reason": "timeout",
            }
        )
        return False, "timeout"

    async with _lock:
        _pending.pop(trace_id, None)
    await emit_trace(
        {
            "type": "confirm_resolved",
            "trace_id": trace_id,
            "approved": bool(pending.approved),
            "reason": pending.note,
        }
    )
    return bool(pending.approved), pending.note


async def resolve_confirmation(*, trace_id: str, approved: bool, note: str | None = None) -> bool:
    """Resolve a pending confirmation. Returns ``True`` if there was a
    matching pending entry; ``False`` if it had already timed out or
    was never requested."""
    async with _lock:
        pending = _pending.get(trace_id)
        if pending is None:
            return False
        pending.approved = approved
        pending.note = note
        pending.event.set()
    return True


def pending_count() -> int:
    """Diagnostics helper — number of in-flight confirmations."""
    return len(_pending)


async def reset_for_tests() -> None:
    """Clear pending state. Tests only."""
    async with _lock:
        _pending.clear()
