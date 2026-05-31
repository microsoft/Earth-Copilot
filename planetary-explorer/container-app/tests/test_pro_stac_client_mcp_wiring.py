"""Tests for the MCP-first / legacy-fallback wiring in
``pro_stac_client.get_pro_collection_ids``.

Phase 2 invariant: when ``USE_MPC_MCP`` is on, the inventory comes from
:mod:`mcp_catalog_client`; on any ``MpcMcpUnavailable`` we fall back to
the existing direct-STAC path so routing never blocks on a flaky
sidecar. When the flag is off we use the legacy path as before.
"""
from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, patch

import pytest

import pro_stac_client as psc
import mcp_catalog_client as mcc


@pytest.fixture(autouse=True)
def _reset_caches_and_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("USE_MPC_MCP", raising=False)
    monkeypatch.delenv("MPC_MCP_URL", raising=False)
    # Both module caches must be cleared so each test starts cold.
    psc._collection_ids_cache = (0.0, [])
    psc._collection_inventory_cache = (0.0, [])
    mcc._client_singleton = None
    yield
    psc._collection_ids_cache = (0.0, [])
    psc._collection_inventory_cache = (0.0, [])
    mcc._client_singleton = None


class TestLegacyPathWhenFlagOff:
    """When USE_MPC_MCP is unset / false, we must NOT touch the MCP
    client and must use the direct STAC path."""

    @pytest.mark.asyncio
    async def test_uses_direct_stac_when_flag_off(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # Pretend Pro is configured directly.
        monkeypatch.setenv("MPC_PRO_STAC_URL", "https://example.geocatalog.spatio.azure.com")

        async def fake_pro_list(session: Any) -> list[dict]:  # noqa: ANN401
            return [{"id": "sentinel2-fire"}, {"id": "naip-2021"}]

        with patch.object(psc, "pro_list_collections", side_effect=fake_pro_list) as plc:
            # Spy the MCP client to make sure it's NOT consulted.
            with patch.object(mcc, "get_client") as mcp_get:
                ids = await psc.get_pro_collection_ids()

        assert ids == ["sentinel2-fire", "naip-2021"]
        plc.assert_awaited_once()
        mcp_get.assert_not_called()


class TestMcpPathWhenFlagOn:
    @pytest.mark.asyncio
    async def test_uses_mcp_when_flag_and_url_set(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("USE_MPC_MCP", "true")
        monkeypatch.setenv("MPC_MCP_URL", "https://sidecar.invalid")

        fake_client = AsyncMock()
        fake_client.list_personal_collections = AsyncMock(
            return_value=[
                {"id": "sentinel2-fire", "title": "Fire"},
                {"id": "naip-2021", "title": "NAIP"},
            ]
        )
        with patch.object(mcc, "get_client", return_value=fake_client):
            # Direct STAC must NOT be touched on the happy path.
            with patch.object(psc, "pro_list_collections") as plc:
                ids = await psc.get_pro_collection_ids()

        assert ids == ["sentinel2-fire", "naip-2021"]
        fake_client.list_personal_collections.assert_awaited_once()
        plc.assert_not_called()

    @pytest.mark.asyncio
    async def test_falls_back_to_direct_stac_on_mcp_failure(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("USE_MPC_MCP", "true")
        monkeypatch.setenv("MPC_MCP_URL", "https://sidecar.invalid")
        monkeypatch.setenv("MPC_PRO_STAC_URL", "https://example.geocatalog.spatio.azure.com")

        fake_client = AsyncMock()
        fake_client.list_personal_collections = AsyncMock(
            side_effect=mcc.MpcMcpUnavailable("sidecar offline")
        )

        async def fake_pro_list(session: Any) -> list[dict]:  # noqa: ANN401
            return [{"id": "sentinel2-fire"}]

        with patch.object(mcc, "get_client", return_value=fake_client):
            with patch.object(psc, "pro_list_collections", side_effect=fake_pro_list) as plc:
                ids = await psc.get_pro_collection_ids()

        assert ids == ["sentinel2-fire"]
        fake_client.list_personal_collections.assert_awaited_once()
        plc.assert_awaited_once()  # fell back

    @pytest.mark.asyncio
    async def test_cache_serves_subsequent_calls(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Phase 2 invariant: the cache is shared across MCP/legacy
        paths -- second call must NOT re-hit either backend."""
        monkeypatch.setenv("USE_MPC_MCP", "true")
        monkeypatch.setenv("MPC_MCP_URL", "https://sidecar.invalid")

        fake_client = AsyncMock()
        fake_client.list_personal_collections = AsyncMock(
            return_value=[{"id": "sentinel2-fire"}]
        )
        with patch.object(mcc, "get_client", return_value=fake_client):
            ids1 = await psc.get_pro_collection_ids()
            ids2 = await psc.get_pro_collection_ids()

        assert ids1 == ids2 == ["sentinel2-fire"]
        # Called exactly once across both invocations.
        assert fake_client.list_personal_collections.await_count == 1


class TestFlagSemantics:
    """USE_MPC_MCP alone is not enough -- MPC_MCP_URL must also be set.
    Belt-and-suspenders so a half-flipped env var doesn't break us."""

    @pytest.mark.asyncio
    async def test_flag_without_url_falls_back_to_direct(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("USE_MPC_MCP", "true")
        # URL intentionally not set.
        monkeypatch.setenv("MPC_PRO_STAC_URL", "https://example.geocatalog.spatio.azure.com")

        async def fake_pro_list(session: Any) -> list[dict]:  # noqa: ANN401
            return [{"id": "sentinel2-fire"}]

        with patch.object(mcc, "get_client") as mcp_get:
            with patch.object(psc, "pro_list_collections", side_effect=fake_pro_list):
                ids = await psc.get_pro_collection_ids()

        assert ids == ["sentinel2-fire"]
        mcp_get.assert_not_called()
