"""Tests for the Resilience planner's MCP-backed tools.

These tools degrade gracefully when the MPC Pro MCP sidecar is not
enabled, which is the default in CI. We verify both paths:

1. Sidecar unavailable -> tool returns ``{"error": ...}`` and never
   raises.
2. Sidecar available (faked via monkeypatch) -> tool emits trace
   events through the bus and returns a typed payload with
   ``provenance``.

The schema invariant test in ``test_resilience_planner_tools.py``
already enforces that every new tool has both a schema entry and a
dispatch entry, so adding tools here only validates behaviour.
"""
from __future__ import annotations

import os

import pytest

os.environ["RESILIENCE_FORCE_SEED"] = "1"

from agents.resilience import tools  # noqa: E402  (after env)
from mcp_runtime import reset_listener, set_listener  # noqa: E402


# ---------------------------------------------------------------------------
# Invariants — confirm schema + dispatch wiring landed for the new tools
# ---------------------------------------------------------------------------

@pytest.mark.parametrize(
    "name",
    ["list_mpc_stac_collections", "search_mpc_stac_items", "get_mpc_collection_details"],
)
def test_mcp_tool_registered_in_schemas_and_dispatch(name):
    schema_names = {s["function"]["name"] for s in tools.TOOL_SCHEMAS}
    assert name in schema_names
    assert name in tools.TOOL_DISPATCH


# ---------------------------------------------------------------------------
# Default path — agents reach the public MPC STAC catalogue, not Pro.
# We monkeypatch ``from_mpc_public`` to return a fake so we exercise the
# routing decision + tracing without hitting the network.
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_agent_does_not_require_mpc_pro_sidecar(monkeypatch):
    """With Pro disabled, the planner still gets working tools via public."""
    monkeypatch.delenv("USE_MPC_MCP", raising=False)
    monkeypatch.delenv("MPC_MCP_URL", raising=False)
    monkeypatch.delenv("RESILIENCE_AGENT_USE_MPC_PRO", raising=False)

    from mcp_runtime import TracedMcpClient

    fake = _FakeMpc()
    monkeypatch.setattr(
        TracedMcpClient,
        "from_mpc_public",
        classmethod(lambda cls, **kw: TracedMcpClient(server_id="mpc_public", underlying=fake, **kw)),
    )

    out = await tools.list_mpc_stac_collections()
    assert "error" not in out
    assert out["collections"][0]["id"] == "sentinel-2-l2a"
    # Provenance should advertise the public backend.
    assert out["provenance"][0]["source"] == "mpc_public_stac"


@pytest.mark.asyncio
async def test_pro_opt_in_uses_pro_when_available(monkeypatch):
    """Setting RESILIENCE_AGENT_USE_MPC_PRO=1 routes through Pro."""
    monkeypatch.setenv("RESILIENCE_AGENT_USE_MPC_PRO", "1")
    from mcp_runtime import TracedMcpClient

    pro_fake = _FakeMpc()
    public_fake = _FakeMpc()
    monkeypatch.setattr(
        TracedMcpClient,
        "from_mpc_pro",
        classmethod(lambda cls, **kw: TracedMcpClient(server_id="mpc_pro", underlying=pro_fake, **kw)),
    )
    monkeypatch.setattr(
        TracedMcpClient,
        "from_mpc_public",
        classmethod(lambda cls, **kw: TracedMcpClient(server_id="mpc_public", underlying=public_fake, **kw)),
    )

    await tools.list_mpc_stac_collections()
    assert pro_fake.calls and not public_fake.calls


@pytest.mark.asyncio
async def test_pro_opt_in_falls_back_to_public_when_pro_unavailable(monkeypatch):
    """If Pro is requested but the sidecar is off, public still works."""
    monkeypatch.setenv("RESILIENCE_AGENT_USE_MPC_PRO", "1")
    from mcp_runtime import TracedMcpClient

    public_fake = _FakeMpc()
    monkeypatch.setattr(TracedMcpClient, "from_mpc_pro", classmethod(lambda cls, **kw: None))
    monkeypatch.setattr(
        TracedMcpClient,
        "from_mpc_public",
        classmethod(lambda cls, **kw: TracedMcpClient(server_id="mpc_public", underlying=public_fake, **kw)),
    )

    out = await tools.list_mpc_stac_collections()
    assert "error" not in out
    assert public_fake.calls


# ---------------------------------------------------------------------------
# Live path — fake backend via TracedMcpClient injection
# ---------------------------------------------------------------------------

class _FakeMpc:
    def __init__(self):
        self.calls = []

    async def list_mpc_stac_collections(self):
        self.calls.append(("list_mpc_stac_collections", {}))
        return {"collections": [{"id": "sentinel-2-l2a"}]}

    async def search_mpc_items(self, **kwargs):
        self.calls.append(("search_mpc_items", kwargs))
        return {"items": [{"id": "S2A_xyz"}], "count": 1}

    async def get_mpc_collection_json(self, **kwargs):
        self.calls.append(("get_mpc_collection_json", kwargs))
        return {"id": kwargs.get("collection_id"), "extent": {"spatial": {}}}


@pytest.fixture
def fake_sidecar(monkeypatch):
    """Replace ``TracedMcpClient.from_mpc_public`` (the agent default)
    with a factory that returns a real ``TracedMcpClient`` wrapping an
    in-memory fake.
    """
    from mcp_runtime import TracedMcpClient

    fake = _FakeMpc()

    def _factory(*, turn_id=None, confirm=None):
        kwargs = {}
        if turn_id is not None:
            kwargs["turn_id"] = turn_id
        if confirm is not None:
            kwargs["confirm"] = confirm
        return TracedMcpClient(server_id="mpc_public", underlying=fake, **kwargs)

    monkeypatch.setattr(TracedMcpClient, "from_mpc_public", classmethod(lambda cls, **kw: _factory(**kw)))
    return fake


@pytest.mark.asyncio
async def test_list_collections_emits_trace_events_when_sidecar_present(fake_sidecar):
    events = []

    async def listener(evt):
        events.append(evt)

    token = set_listener(listener)
    try:
        out = await tools.list_mpc_stac_collections()
    finally:
        reset_listener(token)

    assert "collections" in out and out["collections"][0]["id"] == "sentinel-2-l2a"
    assert out["provenance"][0]["tool"] == "list_mpc_stac_collections"
    types = [e["type"] for e in events]
    assert types == ["tool_call", "tool_result"]
    assert events[0]["tool"] == "list_mpc_stac_collections"
    assert events[1]["ok"] is True


@pytest.mark.asyncio
async def test_search_items_passes_bbox_and_datetime_through(fake_sidecar):
    out = await tools.search_mpc_stac_items(
        collection="sentinel-2-l2a",
        bbox=[-100.0, 30.0, -99.0, 31.0],
        datetime_range="2024-01-01/2024-12-31",
        limit=5,
    )
    assert out["count"] == 1
    assert fake_sidecar.calls[0][0] == "search_mpc_items"
    args = fake_sidecar.calls[0][1]
    assert args["collection"] == "sentinel-2-l2a"
    assert args["bbox"] == [-100.0, 30.0, -99.0, 31.0]
    assert args["datetime"] == "2024-01-01/2024-12-31"
    assert args["limit"] == 5


@pytest.mark.asyncio
async def test_search_items_clamps_limit_into_valid_range(fake_sidecar):
    await tools.search_mpc_stac_items(collection="x", limit=999)
    assert fake_sidecar.calls[-1][1]["limit"] == 50
    await tools.search_mpc_stac_items(collection="x", limit=0)
    assert fake_sidecar.calls[-1][1]["limit"] == 1


@pytest.mark.asyncio
async def test_get_collection_details_uses_collection_id_arg(fake_sidecar):
    out = await tools.get_mpc_collection_details(collection="naip")
    assert out["id"] == "naip"
    assert fake_sidecar.calls[0] == ("get_mpc_collection_json", {"collection_id": "naip"})


@pytest.mark.asyncio
async def test_mcp_tool_returns_error_dict_when_sidecar_raises(fake_sidecar, monkeypatch):
    async def _boom(**_):
        raise RuntimeError("mcp connection lost")

    monkeypatch.setattr(fake_sidecar, "list_mpc_stac_collections", _boom)
    out = await tools.list_mpc_stac_collections()
    assert "error" in out
    assert "mcp connection lost" in out["error"]
