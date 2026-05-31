"""Traced MCP client.

Wraps :class:`mcp_catalog_client.MpcMcpClient` (and, in the future, any
other MCP server registered in the registry) with a per-turn trace
buffer. Every ``call(tool, args)`` produces a :class:`TraceEntry` that
can be surfaced by the chat stream as a ``tool_call`` / ``tool_result``
event — enabling the future tool-trace UI without changing the agent
code that uses it.

This is **opt-in**: existing call sites that use
``mcp_catalog_client.MpcMcpClient`` directly emit no traces and behave
exactly as before. New code (Forecast Agent, Curator Agent) should
import :class:`TracedMcpClient` instead.

Permission tiers
----------------
Every tool is classified as one of:

* ``read``       — safe, no confirmation required
* ``write``      — creates / modifies user-owned resources, future UI will
                   ask for one-click confirmation
* ``destructive``— deletes / overwrites, future UI will require typed
                   confirmation

Classification is currently a static name-pattern map; the eventual
``TracedMcpClient.confirm`` hook is where the UI's confirmation card
will be wired in (see backlog item #1).
"""
from __future__ import annotations

import asyncio
import logging
import re
import time
import uuid
from dataclasses import asdict, dataclass, field
from enum import Enum
from typing import Any, Awaitable, Callable


logger = logging.getLogger(__name__)


class PermissionTier(str, Enum):
    READ = "read"
    WRITE = "write"
    DESTRUCTIVE = "destructive"


# Static tier map keyed off tool-name regex. Patterns are intentionally
# conservative — anything not matched falls through to READ.
_TIER_PATTERNS: tuple[tuple[re.Pattern[str], PermissionTier], ...] = (
    (re.compile(r"^delete_|_delete$"), PermissionTier.DESTRUCTIVE),
    (re.compile(r"^bulk_ingest_|^batch_ingest_"), PermissionTier.DESTRUCTIVE),
    (re.compile(r"^replace_"), PermissionTier.DESTRUCTIVE),
    (re.compile(r"^create_|^configure_|^ingest_"), PermissionTier.WRITE),
)


def classify_tool(tool: str) -> PermissionTier:
    for pat, tier in _TIER_PATTERNS:
        if pat.search(tool):
            return tier
    return PermissionTier.READ


@dataclass
class TraceEntry:
    """One row in the per-turn trace buffer."""

    trace_id: str
    turn_id: str
    server_id: str
    tool: str
    args: dict[str, Any]
    tier: PermissionTier
    started_at: float
    finished_at: float | None = None
    latency_ms: int | None = None
    ok: bool | None = None
    response_summary: str | None = None
    error: str | None = None
    extras: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["tier"] = self.tier.value
        return d


_ConfirmHook = Callable[[TraceEntry], Awaitable[bool]]


async def _autoconfirm(_entry: TraceEntry) -> bool:
    """Trivial confirm hook used when no broker is configured —
    auto-approves. Kept as a default for unit tests and call sites that
    inject their own hook."""
    return True


async def _broker_confirm(entry: TraceEntry) -> bool:
    """Default production confirm hook — routes through
    :mod:`mcp_runtime.confirm_bus` so the UI can render a card and the
    user can approve / deny before the tool dispatches.

    Falls back to auto-approval when ``MCP_REQUIRE_CONFIRM=0`` so the
    feature can be turned off per-deploy without code changes.
    """
    import os

    if os.getenv("MCP_REQUIRE_CONFIRM", "1").lower() not in ("1", "true", "yes", "on"):
        return True
    from .confirm_bus import request_confirmation

    approved, _note = await request_confirmation(
        trace_id=entry.trace_id,
        server_id=entry.server_id,
        tool=entry.tool,
        args=entry.args,
        tier=entry.tier.value,
        turn_id=entry.turn_id,
    )
    return approved


class TracedMcpClient:
    """Wrap an underlying MCP client with per-turn tracing + permission tiers.

    The ``underlying`` argument must expose ``await call(tool, args)``
    returning a JSON-serialisable response. Today the only real
    implementation is :class:`mcp_catalog_client.MpcMcpClient`; a thin
    adapter is exposed via :meth:`from_mpc_pro`.
    """

    def __init__(
        self,
        server_id: str,
        underlying: Any,
        *,
        turn_id: str | None = None,
        confirm: _ConfirmHook = _broker_confirm,
    ) -> None:
        self.server_id = server_id
        self.underlying = underlying
        self.turn_id = turn_id or str(uuid.uuid4())
        self.confirm = confirm
        self._buffer: list[TraceEntry] = []
        self._lock = asyncio.Lock()

    @classmethod
    def from_mpc_pro(
        cls,
        *,
        turn_id: str | None = None,
        confirm: _ConfirmHook = _broker_confirm,
    ) -> "TracedMcpClient | None":
        """Convenience factory bound to the MPC Pro sidecar.

        Returns ``None`` if the sidecar is not enabled, so callers can
        cleanly fall back to the legacy path.
        """
        try:
            from mcp_catalog_client import get_client, is_enabled
        except Exception:  # noqa: BLE001
            return None
        if not is_enabled():
            return None
        return cls(server_id="mpc_pro", underlying=get_client(), turn_id=turn_id, confirm=confirm)

    @classmethod
    def from_mpc_public(
        cls,
        *,
        turn_id: str | None = None,
        confirm: _ConfirmHook = _broker_confirm,
    ) -> "TracedMcpClient":
        """Factory bound to the **public** MPC STAC API.

        Unlike :meth:`from_mpc_pro`, this never returns ``None`` — the
        public catalogue requires no sidecar, no auth, and is always
        reachable. Use this for agent reasoning over public geospatial
        data; reserve :meth:`from_mpc_pro` for direct chat queries that
        opted in to Pro and for private personal-collection access.
        """
        from .public_stac_adapter import PublicStacAdapter

        return cls(
            server_id="mpc_public",
            underlying=PublicStacAdapter(),
            turn_id=turn_id,
            confirm=confirm,
        )

    @classmethod
    def for_agent_geospatial(
        cls,
        *,
        turn_id: str | None = None,
        confirm: _ConfirmHook = _broker_confirm,
    ) -> "TracedMcpClient":
        """Default backend for agent reasoning over geospatial data.

        Always returns a working client: public MPC. Agents should call
        this, not :meth:`from_mpc_pro`, unless they specifically need
        Pro-only capabilities (personal collections, ingest, mosaic
        configuration, etc.).
        """
        return cls.from_mpc_public(turn_id=turn_id, confirm=confirm)

    @property
    def buffer(self) -> list[TraceEntry]:
        """Snapshot of trace entries collected so far this turn."""
        return list(self._buffer)

    async def call(
        self,
        tool: str,
        args: dict[str, Any] | None = None,
        *,
        summary_max: int = 280,
    ) -> Any:
        """Invoke ``tool`` on the underlying server with full tracing."""
        args = dict(args or {})
        tier = classify_tool(tool)
        entry = TraceEntry(
            trace_id=str(uuid.uuid4()),
            turn_id=self.turn_id,
            server_id=self.server_id,
            tool=tool,
            args=args,
            tier=tier,
            started_at=time.time(),
        )
        async with self._lock:
            self._buffer.append(entry)

        # Surface a `tool_call` event to any subscribed SSE listener.
        from .trace_bus import emit as _trace_emit

        await _trace_emit({"type": "tool_call", **entry.to_dict()})

        # Permission gate. WRITE / DESTRUCTIVE go through the confirm
        # hook; READ is always allowed. The default hook auto-approves;
        # the UI will replace it once confirmation cards land.
        if tier is not PermissionTier.READ:
            approved = await self.confirm(entry)
            if not approved:
                entry.ok = False
                entry.error = "denied_by_user"
                entry.finished_at = time.time()
                entry.latency_ms = int((entry.finished_at - entry.started_at) * 1000)
                raise PermissionError(f"User denied {tier.value} call to {tool}")

        try:
            # ``MpcMcpClient`` exposes one method per tool, not a generic
            # call(). Resolve dynamically so the registry stays agnostic.
            method = getattr(self.underlying, tool, None)
            if method is None and hasattr(self.underlying, "call_raw"):
                result = await self.underlying.call_raw(tool, args)
            elif method is not None:
                result = await method(**args)
            else:
                raise AttributeError(
                    f"underlying MCP client has no method or call_raw for tool {tool!r}"
                )
        except Exception as exc:  # noqa: BLE001
            entry.ok = False
            entry.error = f"{type(exc).__name__}: {exc}"
            entry.finished_at = time.time()
            entry.latency_ms = int((entry.finished_at - entry.started_at) * 1000)
            await _trace_emit({"type": "tool_result", **entry.to_dict()})
            raise
        else:
            entry.ok = True
            entry.finished_at = time.time()
            entry.latency_ms = int((entry.finished_at - entry.started_at) * 1000)
            try:
                preview = str(result)
            except Exception:  # noqa: BLE001
                preview = "<unprintable>"
            entry.response_summary = preview[:summary_max]
            await _trace_emit({"type": "tool_result", **entry.to_dict()})
            return result
