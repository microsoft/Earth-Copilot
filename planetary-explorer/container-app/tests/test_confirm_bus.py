"""Tests for `mcp_runtime.confirm_bus` and the SSE-driven confirmation flow.

The interactive-confirmation feature pauses any WRITE or DESTRUCTIVE MCP
tool call until the UI POSTs `/api/mcp/confirm/{trace_id}`. These tests
exercise the broker primitives directly (so we don't pay the cost of
spinning up a full agent) plus an end-to-end FastAPI test that proves
the POST endpoint resolves a pending future.
"""
from __future__ import annotations

import asyncio
import os

import pytest
from fastapi import FastAPI, HTTPException
from starlette.requests import Request


# --- broker primitives --------------------------------------------------------


@pytest.mark.asyncio
async def test_request_and_resolve_round_trip():
    from mcp_runtime import (
        request_confirmation,
        resolve_confirmation,
        reset_confirm_bus_for_tests,
    )

    await reset_confirm_bus_for_tests()
    trace_id = "trace-approve-1"

    async def _approve_after_a_tick() -> bool:
        await asyncio.sleep(0)
        return await resolve_confirmation(trace_id=trace_id, approved=True, note="ok")

    resolved_task = asyncio.create_task(_approve_after_a_tick())
    approved, note = await request_confirmation(
        trace_id=trace_id,
        server_id="mpc_pro",
        tool="create_personal_stac_collection",
        args={"name": "x"},
        tier="write",
        timeout=5.0,
    )
    assert approved is True
    assert note == "ok"
    assert await resolved_task is True


@pytest.mark.asyncio
async def test_resolve_unknown_returns_false():
    from mcp_runtime import resolve_confirmation, reset_confirm_bus_for_tests

    await reset_confirm_bus_for_tests()
    assert await resolve_confirmation(trace_id="nope", approved=True) is False


@pytest.mark.asyncio
async def test_timeout_is_denial():
    from mcp_runtime import request_confirmation, reset_confirm_bus_for_tests

    await reset_confirm_bus_for_tests()
    approved, note = await request_confirmation(
        trace_id="trace-timeout",
        server_id="mpc_pro",
        tool="delete_personal_collection",
        args={},
        tier="destructive",
        timeout=0.05,
    )
    assert approved is False
    assert note == "timeout"


@pytest.mark.asyncio
async def test_request_emits_trace_event():
    from mcp_runtime import (
        request_confirmation,
        resolve_confirmation,
        reset_confirm_bus_for_tests,
        set_listener,
        reset_listener,
    )

    await reset_confirm_bus_for_tests()
    captured: list[dict] = []

    async def _listener(evt: dict) -> None:
        captured.append(evt)

    token = set_listener(_listener)
    try:
        trace_id = "trace-evt"

        async def _resolve_soon():
            await asyncio.sleep(0)
            await resolve_confirmation(trace_id=trace_id, approved=False)

        asyncio.create_task(_resolve_soon())
        approved, _ = await request_confirmation(
            trace_id=trace_id,
            server_id="mpc_pro",
            tool="ingest_stac_item",
            args={"a": 1},
            tier="write",
            timeout=5.0,
        )
    finally:
        reset_listener(token)
    assert approved is False
    types = [e.get("type") for e in captured]
    assert "confirm_request" in types
    assert "confirm_resolved" in types
    req = next(e for e in captured if e["type"] == "confirm_request")
    assert req["trace_id"] == "trace-evt"
    assert req["tool"] == "ingest_stac_item"
    assert req["tier"] == "write"


# --- TracedMcpClient gating ---------------------------------------------------


@pytest.mark.asyncio
async def test_traced_client_blocks_until_approved(monkeypatch):
    """A WRITE tool call must wait for the broker before dispatching."""
    from mcp_runtime import (
        TracedMcpClient,
        resolve_confirmation,
        reset_confirm_bus_for_tests,
    )

    await reset_confirm_bus_for_tests()
    monkeypatch.setenv("MCP_REQUIRE_CONFIRM", "1")

    class _Underlying:
        def __init__(self) -> None:
            self.calls: list[tuple] = []

        async def call_raw(self, tool: str, args: dict) -> dict:
            self.calls.append((tool, args))
            return {"ok": True}

    underlying = _Underlying()
    client = TracedMcpClient(server_id="mpc_pro", underlying=underlying)

    # Catch the trace_id by listening to the trace bus.
    from mcp_runtime import set_listener, reset_listener

    captured_trace_id: dict[str, str] = {}

    async def _listener(evt: dict) -> None:
        if evt.get("type") == "confirm_request":
            captured_trace_id["id"] = evt["trace_id"]

    token = set_listener(_listener)
    try:
        async def _approve_when_pending():
            for _ in range(50):
                tid = captured_trace_id.get("id")
                if tid:
                    await resolve_confirmation(trace_id=tid, approved=True)
                    return
                await asyncio.sleep(0.01)

        approve_task = asyncio.create_task(_approve_when_pending())
        result = await client.call("ingest_stac_item", {"item": "foo"})
    finally:
        reset_listener(token)
    await approve_task

    assert result == {"ok": True}
    assert underlying.calls == [("ingest_stac_item", {"item": "foo"})]


@pytest.mark.asyncio
async def test_traced_client_raises_on_denial(monkeypatch):
    from mcp_runtime import (
        TracedMcpClient,
        resolve_confirmation,
        reset_confirm_bus_for_tests,
        set_listener,
        reset_listener,
    )

    await reset_confirm_bus_for_tests()
    monkeypatch.setenv("MCP_REQUIRE_CONFIRM", "1")

    class _Underlying:
        def __init__(self) -> None:
            self.calls: list[tuple] = []

        async def call_raw(self, tool: str, args: dict) -> dict:
            self.calls.append((tool, args))
            return {"ok": True}

    underlying = _Underlying()
    client = TracedMcpClient(server_id="mpc_pro", underlying=underlying)

    captured: dict[str, str] = {}

    async def _listener(evt: dict) -> None:
        if evt.get("type") == "confirm_request":
            captured["id"] = evt["trace_id"]

    token = set_listener(_listener)
    try:
        async def _deny():
            for _ in range(50):
                if "id" in captured:
                    await resolve_confirmation(trace_id=captured["id"], approved=False)
                    return
                await asyncio.sleep(0.01)

        deny_task = asyncio.create_task(_deny())
        with pytest.raises(PermissionError):
            await client.call("delete_personal_collection", {"id": "x"})
    finally:
        reset_listener(token)
    await deny_task

    assert underlying.calls == []  # never dispatched


@pytest.mark.asyncio
async def test_traced_client_skips_broker_for_read(monkeypatch):
    """READ tools bypass the broker entirely so the agent doesn't pause."""
    from mcp_runtime import TracedMcpClient, reset_confirm_bus_for_tests

    await reset_confirm_bus_for_tests()
    monkeypatch.setenv("MCP_REQUIRE_CONFIRM", "1")

    class _Underlying:
        async def call_raw(self, tool: str, args: dict) -> dict:
            return {"ok": True, "tool": tool}

    client = TracedMcpClient(server_id="mpc_pro", underlying=_Underlying())
    # `search_*` classifies as READ.
    result = await client.call("search_mpc_items", {"q": "x"})
    assert result["ok"] is True


@pytest.mark.asyncio
async def test_disable_flag_autoapproves(monkeypatch):
    """`MCP_REQUIRE_CONFIRM=0` must turn the feature off without code changes."""
    from mcp_runtime import TracedMcpClient, reset_confirm_bus_for_tests

    await reset_confirm_bus_for_tests()
    monkeypatch.setenv("MCP_REQUIRE_CONFIRM", "0")

    class _Underlying:
        async def call_raw(self, tool: str, args: dict) -> dict:
            return {"ok": True}

    client = TracedMcpClient(server_id="mpc_pro", underlying=_Underlying())
    result = await client.call("ingest_stac_item", {"i": 1})  # WRITE
    assert result == {"ok": True}


# --- FastAPI endpoint ---------------------------------------------------------


def _build_app():
    app = FastAPI()

    @app.post("/api/mcp/confirm/{trace_id}")
    async def _confirm(trace_id: str, request: Request):
        from mcp_runtime import resolve_confirmation
        body = await request.json() if request.headers.get("content-type", "").startswith("application/json") else {}
        approved = bool(body.get("approved", False))
        note = body.get("note")
        if note is not None and not isinstance(note, str):
            note = str(note)
        ok = await resolve_confirmation(trace_id=trace_id, approved=approved, note=note)
        if not ok:
            raise HTTPException(status_code=404, detail="no pending")
        return {"resolved": True, "trace_id": trace_id, "approved": approved}

    return app


@pytest.mark.asyncio
async def test_confirm_endpoint_unblocks_request():
    """End-to-end: simulate the SSE loop by issuing a confirmation request,
    then POSTing to the endpoint. The request_confirmation coroutine
    must resolve with the POSTed decision."""
    from httpx import ASGITransport, AsyncClient
    from mcp_runtime import request_confirmation, reset_confirm_bus_for_tests

    await reset_confirm_bus_for_tests()

    app = _build_app()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        trace_id = "trace-http-1"

        async def _waiter():
            return await request_confirmation(
                trace_id=trace_id,
                server_id="mpc_pro",
                tool="ingest_stac_item",
                args={},
                tier="write",
                timeout=5.0,
            )

        waiter = asyncio.create_task(_waiter())
        # Yield so the broker registers the pending entry.
        await asyncio.sleep(0.01)
        resp = await client.post(
            f"/api/mcp/confirm/{trace_id}",
            json={"approved": True, "note": "looks good"},
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body == {"resolved": True, "trace_id": trace_id, "approved": True}

        approved, note = await waiter
        assert approved is True
        assert note == "looks good"


@pytest.mark.asyncio
async def test_confirm_endpoint_404_for_unknown():
    from httpx import ASGITransport, AsyncClient
    from mcp_runtime import reset_confirm_bus_for_tests

    await reset_confirm_bus_for_tests()
    app = _build_app()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post(
            "/api/mcp/confirm/ghost", json={"approved": True}
        )
        assert resp.status_code == 404
