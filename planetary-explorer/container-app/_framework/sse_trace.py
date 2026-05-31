"""SSE helper — merge an agent's event stream with live MCP trace events.

Usage from a FastAPI streaming route::

    async def _sse():
        async for event in merge_with_trace(agent_stream(...)):
            yield f"data: {json.dumps(event, default=str)}\\n\\n"

Trace events surface as ``{"type": "tool_call", ...}`` and
``{"type": "tool_result", ...}``; the agent's own events pass through
unchanged. If the underlying ``TracedMcpClient`` is not used, the merged
stream is identical to the input stream — i.e. zero behavioural change
for routes that haven't migrated yet.
"""
from __future__ import annotations

import asyncio
from typing import Any, AsyncIterator

from mcp_runtime.trace_bus import reset_listener, set_listener


async def merge_with_trace(
    source: AsyncIterator[dict[str, Any]],
) -> AsyncIterator[dict[str, Any]]:
    """Yield items from ``source`` interleaved with MCP trace events.

    Both streams are funneled through an :class:`asyncio.Queue`; the
    source is consumed in a background task so trace events emitted
    mid-await still flush promptly.
    """
    queue: asyncio.Queue[tuple[str, Any]] = asyncio.Queue()

    async def _listener(event: dict[str, Any]) -> None:
        await queue.put(("trace", event))

    async def _drain_source() -> None:
        try:
            async for evt in source:
                await queue.put(("event", evt))
        except Exception as exc:  # noqa: BLE001
            await queue.put(("error", exc))
        finally:
            await queue.put(("done", None))

    token = set_listener(_listener)
    task = asyncio.create_task(_drain_source())
    try:
        while True:
            kind, payload = await queue.get()
            if kind == "done":
                return
            if kind == "error":
                raise payload  # type: ignore[misc]
            yield payload  # trace event or agent event, both dicts
    finally:
        reset_listener(token)
        if not task.done():
            task.cancel()
            try:
                await task
            except (asyncio.CancelledError, Exception):  # noqa: BLE001
                pass
