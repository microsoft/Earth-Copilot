"""Offline unit tests for :mod:`mcp_catalog_client`.

These cover the parts of the client that do not require an actual MCP
sidecar: the inert-by-default contract, the response-shape coercion
helpers, and the structured-content unwrap path. A live integration test
against the MPC Pro MCP sidecar is exercised separately under
``tests/live_*`` and is gated on environment variables.
"""
from __future__ import annotations

import os
from typing import Any
from unittest.mock import AsyncMock, patch

import pytest

import mcp_catalog_client as mod


@pytest.fixture(autouse=True)
def _isolate_singleton(monkeypatch: pytest.MonkeyPatch) -> None:
    """Ensure each test starts with a fresh client + env."""
    monkeypatch.delenv("USE_MPC_MCP", raising=False)
    monkeypatch.delenv("MPC_MCP_URL", raising=False)
    monkeypatch.delenv("MPC_MCP_API_KEY", raising=False)
    mod._client_singleton = None
    yield
    mod._client_singleton = None


# ---------------------------------------------------------------------------
# Inert-by-default contract
# ---------------------------------------------------------------------------


class TestInertByDefault:
    def test_is_enabled_false_without_flag(self) -> None:
        """No flag, no URL -> disabled."""
        assert mod.is_enabled() is False

    def test_is_enabled_false_with_flag_but_no_url(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Flag alone is not enough; URL must also be set."""
        monkeypatch.setenv("USE_MPC_MCP", "true")
        assert mod.is_enabled() is False

    def test_is_enabled_false_with_url_but_no_flag(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """URL alone is not enough; operator must opt in via flag."""
        monkeypatch.setenv("MPC_MCP_URL", "https://example.invalid")
        assert mod.is_enabled() is False

    def test_is_enabled_true_with_both(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("USE_MPC_MCP", "true")
        monkeypatch.setenv("MPC_MCP_URL", "https://example.invalid")
        assert mod.is_enabled() is True

    @pytest.mark.parametrize("value", ["1", "true", "TRUE", "yes", "on"])
    def test_flag_accepts_common_truthy_values(
        self, monkeypatch: pytest.MonkeyPatch, value: str
    ) -> None:
        monkeypatch.setenv("USE_MPC_MCP", value)
        monkeypatch.setenv("MPC_MCP_URL", "https://example.invalid")
        assert mod.is_enabled() is True

    @pytest.mark.parametrize("value", ["0", "false", "no", "off", "", "maybe"])
    def test_flag_rejects_other_values(
        self, monkeypatch: pytest.MonkeyPatch, value: str
    ) -> None:
        monkeypatch.setenv("USE_MPC_MCP", value)
        monkeypatch.setenv("MPC_MCP_URL", "https://example.invalid")
        assert mod.is_enabled() is False


class TestUnconfiguredClientRaises:
    @pytest.mark.asyncio
    async def test_call_tool_raises_when_no_url(self) -> None:
        client = mod.MpcMcpClient(url="")
        assert client.configured is False
        with pytest.raises(mod.MpcMcpUnavailable):
            await client._call_tool("list_personal_stac_collections", {})


# ---------------------------------------------------------------------------
# Coercion helpers -- these are the resilience layer between the upstream
# tool's exact response shape and what LoadAgent expects.
# ---------------------------------------------------------------------------


class TestCoerceCollectionList:
    def test_bare_list(self) -> None:
        result = mod._coerce_collection_list(
            [
                {"id": "sentinel2-fire", "title": "Sentinel-2 Fire"},
                {"id": "naip-2021", "description": "NAIP 2021"},
            ]
        )
        assert [c["id"] for c in result] == ["sentinel2-fire", "naip-2021"]
        assert result[0]["title"] == "Sentinel-2 Fire"
        assert result[1]["title"] == "naip-2021"  # falls back to id

    def test_collections_envelope(self) -> None:
        result = mod._coerce_collection_list(
            {"collections": [{"id": "sentinel-2-l2a"}]}
        )
        assert result == [
            {"id": "sentinel-2-l2a", "title": "sentinel-2-l2a", "description": ""}
        ]

    def test_items_envelope(self) -> None:
        result = mod._coerce_collection_list({"items": [{"id": "naip"}]})
        assert result and result[0]["id"] == "naip"

    def test_collection_id_field_alias(self) -> None:
        """Some tools emit ``collection_id`` instead of ``id``."""
        result = mod._coerce_collection_list(
            [{"collection_id": "sentinel2-fire", "title": "Fire"}]
        )
        assert result == [
            {"id": "sentinel2-fire", "title": "Fire", "description": ""}
        ]

    def test_drops_items_without_id(self) -> None:
        result = mod._coerce_collection_list(
            [{"title": "nameless"}, {"id": "ok"}]
        )
        assert [c["id"] for c in result] == ["ok"]

    def test_handles_garbage_input(self) -> None:
        for bad in (None, "string", 42, {"unrelated": "shape"}, [None, 1, "s"]):
            assert mod._coerce_collection_list(bad) == []


class TestCoerceBool:
    @pytest.mark.parametrize(
        "value,expected",
        [
            (True, True),
            (False, False),
            ({"exists": True}, True),
            ({"exists": False}, False),
            ({"found": True}, True),
            ({"result": True}, True),
            ({"unrelated": "x"}, False),
            ("true", True),
            ("yes", True),
            ("1", True),
            ("false", False),
            ("", False),
            (None, False),
            (1, True),
            (0, False),
        ],
    )
    def test_various_shapes(self, value: Any, expected: bool) -> None:
        assert mod._coerce_bool(value) is expected


class TestFirstText:
    def test_extracts_from_typed_blocks(self) -> None:
        class FakeBlock:
            text = "hello"

        class FakeResult:
            content = [FakeBlock()]

        assert mod._first_text(FakeResult()) == "hello"

    def test_extracts_from_dict_blocks(self) -> None:
        class FakeResult:
            content = [{"type": "text", "text": "world"}]

        assert mod._first_text(FakeResult()) == "world"

    def test_returns_none_when_no_text_block(self) -> None:
        class FakeResult:
            content = [{"type": "image", "data": "..."}]

        assert mod._first_text(FakeResult()) is None

    def test_returns_none_for_empty(self) -> None:
        class FakeResult:
            content = []

        assert mod._first_text(FakeResult()) is None


# ---------------------------------------------------------------------------
# Tool dispatch: when the session is mocked, the typed wrappers should
# coerce results correctly, surface "tool not available" cleanly, and
# turn ``isError=True`` responses into MpcMcpUnavailable.
# ---------------------------------------------------------------------------


def _fake_tool_result(*, payload_json: str = "", is_error: bool = False) -> Any:
    """Build an object that quacks like ``CallToolResult`` enough for the
    client's unwrap path."""

    class _Block:
        type = "text"
        text = payload_json

    class _Result:
        isError = is_error
        structuredContent = None
        content = [_Block()] if payload_json else []

    return _Result()


class TestToolDispatch:
    @pytest.mark.asyncio
    async def test_list_personal_collections_happy_path(self) -> None:
        client = mod.MpcMcpClient(url="https://example.invalid")

        fake_session = AsyncMock()
        fake_session.call_tool = AsyncMock(
            return_value=_fake_tool_result(
                payload_json='{"collections": [{"id": "sentinel2-fire", "title": "Fire"}]}'
            )
        )
        client._session = fake_session
        client._available_tools = {"list_personal_stac_collections"}

        result = await client.list_personal_collections()
        assert result == [
            {"id": "sentinel2-fire", "title": "Fire", "description": ""}
        ]
        fake_session.call_tool.assert_awaited_once_with(
            "list_personal_stac_collections", {}
        )

    @pytest.mark.asyncio
    async def test_unknown_tool_fails_fast(self) -> None:
        client = mod.MpcMcpClient(url="https://example.invalid")
        client._session = AsyncMock()
        client._available_tools = {"list_mpc_stac_collections"}  # no ``personal``

        with pytest.raises(mod.MpcMcpUnavailable, match="not advertised"):
            await client.list_personal_collections()

    @pytest.mark.asyncio
    async def test_iserror_response_raises_unavailable(self) -> None:
        client = mod.MpcMcpClient(url="https://example.invalid")
        client._session = AsyncMock()
        client._session.call_tool = AsyncMock(
            return_value=_fake_tool_result(
                payload_json="auth failed", is_error=True
            )
        )
        client._available_tools = {"check_personal_collection_exists"}

        with pytest.raises(mod.MpcMcpUnavailable, match="returned error"):
            await client.check_personal_collection_exists("sentinel2-fire")

    @pytest.mark.asyncio
    async def test_structured_content_wins_over_text(self) -> None:
        client = mod.MpcMcpClient(url="https://example.invalid")

        class _Result:
            isError = False
            structuredContent = {"collections": [{"id": "naip"}]}
            content = [{"type": "text", "text": "ignored"}]

        client._session = AsyncMock()
        client._session.call_tool = AsyncMock(return_value=_Result())
        client._available_tools = {"list_personal_stac_collections"}

        result = await client.list_personal_collections()
        assert result == [
            {"id": "naip", "title": "naip", "description": ""}
        ]


# ---------------------------------------------------------------------------
# Singleton lifecycle
# ---------------------------------------------------------------------------


class TestSingleton:
    def test_get_client_returns_same_instance(self) -> None:
        a = mod.get_client()
        b = mod.get_client()
        assert a is b

    @pytest.mark.asyncio
    async def test_shutdown_clears_singleton(self) -> None:
        mod.get_client()  # create
        await mod.shutdown()
        # New get_client() must produce a fresh instance.
        assert mod._client_singleton is None
