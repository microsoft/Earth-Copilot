"""Unit tests for the new _framework / mcp_runtime primitives.

These tests don't require any external services — they use in-memory
fakes for the MCP underlying client and a stub LLM. Hermetic.
"""
from __future__ import annotations

import asyncio
from typing import Any

import pytest

from _framework import FanOutExecutor, merge_with_trace
from _framework.executors import CriticExecutor, CriticVerdict, PlannerExecutor
from mcp_runtime import (
    PermissionTier,
    TracedMcpClient,
    classify_tool,
    reset_listener,
    set_listener,
)
from mcp_runtime.trace_bus import emit as emit_trace


# ---------------------------------------------------------------------------
# permission tier classifier
# ---------------------------------------------------------------------------

@pytest.mark.parametrize(
    "tool,expected",
    [
        ("delete_personal_collection", PermissionTier.DESTRUCTIVE),
        ("personal_collection_delete", PermissionTier.DESTRUCTIVE),
        ("bulk_ingest_stac_items", PermissionTier.DESTRUCTIVE),
        ("batch_ingest_stac_items", PermissionTier.DESTRUCTIVE),
        ("replace_personal_collection_thumbnail", PermissionTier.DESTRUCTIVE),
        ("create_personal_stac_collection", PermissionTier.WRITE),
        ("configure_collection_mosaic_definitions", PermissionTier.WRITE),
        ("ingest_stac_item", PermissionTier.WRITE),
        ("list_mpc_stac_collections", PermissionTier.READ),
        ("get_personal_collection_details", PermissionTier.READ),
        ("search_stac_items", PermissionTier.READ),
        ("some_unknown_tool", PermissionTier.READ),
    ],
)
def test_classify_tool(tool, expected):
    assert classify_tool(tool) is expected


# ---------------------------------------------------------------------------
# TracedMcpClient
# ---------------------------------------------------------------------------

class _FakeMpc:
    """In-memory MCP underlying client."""

    def __init__(self):
        self.calls: list[tuple[str, dict]] = []

    async def search_stac_items(self, **kwargs):
        self.calls.append(("search_stac_items", kwargs))
        return {"items": [{"id": "abc"}]}

    async def call_raw(self, tool: str, args: dict):
        self.calls.append((tool, args))
        return {"ok": True, "tool": tool}


@pytest.mark.asyncio
async def test_traced_client_records_read_call_with_summary():
    fake = _FakeMpc()
    client = TracedMcpClient(server_id="test", underlying=fake)

    result = await client.call("search_stac_items", {"collection": "s2"})

    assert result == {"items": [{"id": "abc"}]}
    assert len(client.buffer) == 1
    entry = client.buffer[0]
    assert entry.tier is PermissionTier.READ
    assert entry.ok is True
    assert entry.latency_ms is not None and entry.latency_ms >= 0
    assert entry.response_summary and "items" in entry.response_summary


@pytest.mark.asyncio
async def test_traced_client_falls_back_to_call_raw():
    fake = _FakeMpc()
    client = TracedMcpClient(server_id="test", underlying=fake)
    out = await client.call("get_personal_collection_details", {"id": "x"})
    assert out == {"ok": True, "tool": "get_personal_collection_details"}


@pytest.mark.asyncio
async def test_traced_client_blocks_destructive_when_confirm_denies():
    fake = _FakeMpc()

    async def deny(_entry):
        return False

    client = TracedMcpClient(server_id="test", underlying=fake, confirm=deny)
    with pytest.raises(PermissionError):
        await client.call("delete_personal_collection", {"id": "x"})
    assert fake.calls == []  # never reached the underlying
    assert client.buffer[0].error == "denied_by_user"


@pytest.mark.asyncio
async def test_traced_client_allows_write_when_confirm_approves():
    fake = _FakeMpc()
    approvals = []

    async def approve(entry):
        approvals.append(entry.tool)
        return True

    client = TracedMcpClient(server_id="test", underlying=fake, confirm=approve)
    out = await client.call("create_personal_stac_collection", {"name": "x"})
    assert out["ok"] is True
    assert approvals == ["create_personal_stac_collection"]


@pytest.mark.asyncio
async def test_traced_client_records_error_and_propagates():
    class _Boom:
        async def explode(self, **_):
            raise RuntimeError("kaboom")

    client = TracedMcpClient(server_id="test", underlying=_Boom())
    with pytest.raises(RuntimeError):
        await client.call("explode", {})
    entry = client.buffer[0]
    assert entry.ok is False
    assert "kaboom" in (entry.error or "")


# ---------------------------------------------------------------------------
# trace bus + SSE merge
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_trace_bus_emits_to_registered_listener_only():
    received: list[dict] = []

    async def listener(evt):
        received.append(evt)

    token = set_listener(listener)
    try:
        await emit_trace({"type": "tool_call", "tool": "foo"})
    finally:
        reset_listener(token)
    await emit_trace({"type": "tool_call", "tool": "after"})  # no listener

    assert received == [{"type": "tool_call", "tool": "foo"}]


@pytest.mark.asyncio
async def test_merge_with_trace_interleaves_tool_events_with_source_events():
    fake = _FakeMpc()
    client = TracedMcpClient(server_id="test", underlying=fake)

    async def source():
        yield {"type": "start"}
        # an MCP call mid-stream should produce two trace events
        await client.call("search_stac_items", {"collection": "s2"})
        yield {"type": "end"}

    events = [e async for e in merge_with_trace(source())]
    types = [e["type"] for e in events]
    assert "start" in types
    assert "end" in types
    assert types.count("tool_call") == 1
    assert types.count("tool_result") == 1
    # ordering: tool_call must precede tool_result
    assert types.index("tool_call") < types.index("tool_result")


@pytest.mark.asyncio
async def test_merge_with_trace_propagates_source_errors():
    async def boomer():
        yield {"type": "ok"}
        raise ValueError("source-failed")

    with pytest.raises(ValueError, match="source-failed"):
        async for _ in merge_with_trace(boomer()):
            pass


# ---------------------------------------------------------------------------
# FanOutExecutor
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_fan_out_runs_concurrently_and_returns_per_item_results():
    async def work(x):
        await asyncio.sleep(0.05)
        if x == 3:
            raise RuntimeError("bad")
        return x * 2

    results = await FanOutExecutor.run([1, 2, 3, 4], work, timeout_sec=5)

    assert len(results) == 4
    by_item = {r.item: r for r in results}
    assert by_item[1].ok and by_item[1].result == 2
    assert by_item[2].ok and by_item[2].result == 4
    assert by_item[4].ok and by_item[4].result == 8
    assert by_item[3].ok is False and "bad" in (by_item[3].error or "")


@pytest.mark.asyncio
async def test_fan_out_honours_concurrency_cap():
    in_flight = 0
    peak = 0
    lock = asyncio.Lock()

    async def work(x):
        nonlocal in_flight, peak
        async with lock:
            in_flight += 1
            peak = max(peak, in_flight)
        await asyncio.sleep(0.02)
        async with lock:
            in_flight -= 1
        return x

    await FanOutExecutor.run(list(range(20)), work, timeout_sec=5, max_concurrency=3)
    assert peak <= 3


@pytest.mark.asyncio
async def test_fan_out_per_item_timeout_is_recorded():
    async def slow(_):
        await asyncio.sleep(1)

    results = await FanOutExecutor.run([1], slow, timeout_sec=0.05)
    assert results[0].ok is False
    assert results[0].error and "timeout" in results[0].error.lower()


# ---------------------------------------------------------------------------
# Executors (Planner / Critic) — verified with stub LLM
# ---------------------------------------------------------------------------

class _StubLlm:
    def __init__(self, payload: str):
        self.payload = payload
        self.calls = 0

    async def chat(self, messages, **kwargs):
        self.calls += 1

        class _Msg:
            def __init__(self, c):
                self.content = c

        class _Choice:
            def __init__(self, c):
                self.message = _Msg(c)

        class _Rsp:
            def __init__(self, c):
                self.choices = [_Choice(c)]

        return _Rsp(self.payload)


class _DemoPlanner(PlannerExecutor[str, dict, dict, dict]):
    async def build_plan(self, payload):
        return {"steps": [{"i": 1}, {"i": 2}, {"i": 3}]}

    def plan_steps(self, plan):
        return plan["steps"]

    async def run_step(self, step):
        return {"i": step["i"], "doubled": step["i"] * 2}


@pytest.mark.asyncio
async def test_planner_executor_runs_steps_and_envelopes_results():
    p = _DemoPlanner(llm=_StubLlm("{}"))  # llm unused by this subclass
    result = await p.run("anything")
    assert result.plan["steps"][0]["i"] == 1
    assert len(result.step_results) == 3
    assert {r.result["doubled"] for r in result.step_results} == {2, 4, 6}
    assert result.latency_ms >= 0


class _DemoCritic(CriticExecutor[str]):
    async def prompt(self, payload):
        return [{"role": "user", "content": payload}]


@pytest.mark.asyncio
async def test_critic_executor_parses_json_verdict():
    c = _DemoCritic(llm=_StubLlm('{"ok": true, "score": 0.9, "rationale": "fine"}'))
    v = await c.evaluate("input")
    assert isinstance(v, CriticVerdict)
    assert v.ok is True
    assert v.score == 0.9
    assert v.rationale == "fine"


@pytest.mark.asyncio
async def test_critic_executor_returns_unparseable_verdict_on_bad_json():
    c = _DemoCritic(llm=_StubLlm("not json at all"), max_retries=0)
    v = await c.evaluate("input")
    assert v.ok is False
    assert v.rationale and "unparseable" in v.rationale
