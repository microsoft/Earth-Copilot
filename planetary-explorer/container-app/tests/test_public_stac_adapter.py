"""Unit tests for :class:`mcp_runtime.PublicStacAdapter`.

We don't hit the network — instead we wire an :class:`httpx.AsyncClient`
with a :class:`httpx.MockTransport` and assert request shape + response
parsing.
"""
from __future__ import annotations

import json

import httpx
import pytest

from mcp_runtime import PublicStacAdapter


def _mock_transport():
    captured = {}

    def _handler(request: httpx.Request) -> httpx.Response:
        captured["method"] = request.method
        captured["url"] = str(request.url)
        body = request.content.decode() if request.content else ""
        captured["body"] = json.loads(body) if body else None

        if request.url.path.endswith("/collections"):
            return httpx.Response(
                200,
                json={
                    "collections": [
                        {"id": "sentinel-2-l2a", "title": "Sentinel-2 L2A", "description": "x" * 500},
                        {"id": "naip", "title": "NAIP", "description": "USDA NAIP"},
                    ]
                },
            )
        if request.url.path.endswith("/search"):
            return httpx.Response(
                200,
                json={
                    "features": [
                        {
                            "id": "S2A_xyz",
                            "collection": "sentinel-2-l2a",
                            "properties": {"datetime": "2024-06-01T00:00:00Z"},
                            "bbox": [-100, 30, -99, 31],
                        }
                    ]
                },
            )
        if "/collections/" in request.url.path:
            cid = request.url.path.rsplit("/", 1)[-1]
            return httpx.Response(200, json={"id": cid, "extent": {"spatial": {}}})
        return httpx.Response(404)

    return httpx.MockTransport(_handler), captured


@pytest.mark.asyncio
async def test_list_collections_trims_description_and_returns_count():
    transport, _ = _mock_transport()
    async with httpx.AsyncClient(transport=transport) as client:
        adapter = PublicStacAdapter(client=client)
        out = await adapter.list_mpc_stac_collections()
    assert out["count"] == 2
    ids = [c["id"] for c in out["collections"]]
    assert "sentinel-2-l2a" in ids
    # Description should be trimmed to 240 chars.
    assert len(out["collections"][0]["description"]) <= 240


@pytest.mark.asyncio
async def test_search_items_posts_correct_payload():
    transport, captured = _mock_transport()
    async with httpx.AsyncClient(transport=transport) as client:
        adapter = PublicStacAdapter(client=client)
        out = await adapter.search_mpc_items(
            collection="sentinel-2-l2a",
            bbox=[-100.0, 30.0, -99.0, 31.0],
            datetime="2024-01-01/2024-12-31",
            limit=5,
        )
    assert captured["method"] == "POST"
    assert captured["url"].endswith("/search")
    assert captured["body"]["collections"] == ["sentinel-2-l2a"]
    assert captured["body"]["bbox"] == [-100.0, 30.0, -99.0, 31.0]
    assert captured["body"]["datetime"] == "2024-01-01/2024-12-31"
    assert captured["body"]["limit"] == 5
    assert out["count"] == 1
    assert out["items"][0]["id"] == "S2A_xyz"


@pytest.mark.asyncio
async def test_get_collection_json_uses_collection_id():
    transport, captured = _mock_transport()
    async with httpx.AsyncClient(transport=transport) as client:
        adapter = PublicStacAdapter(client=client)
        out = await adapter.get_mpc_collection_json(collection_id="naip")
    assert captured["method"] == "GET"
    assert captured["url"].endswith("/collections/naip")
    assert out["id"] == "naip"


@pytest.mark.asyncio
async def test_get_collection_json_returns_error_when_id_missing():
    adapter = PublicStacAdapter()
    out = await adapter.get_mpc_collection_json()
    assert "error" in out
    await adapter.aclose()


@pytest.mark.asyncio
async def test_from_mpc_public_factory_always_returns_a_client():
    """The public factory never returns None — public catalogue has no gates."""
    from mcp_runtime import TracedMcpClient

    client = TracedMcpClient.from_mpc_public()
    assert client is not None
    assert client.server_id == "mpc_public"
    await client.underlying.aclose()
