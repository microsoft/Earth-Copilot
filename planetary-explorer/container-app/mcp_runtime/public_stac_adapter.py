"""Adapter that exposes the **public** Microsoft Planetary Computer STAC
API behind the same method surface our :class:`TracedMcpClient` already
uses for the MPC Pro MCP sidecar.

Why this exists
---------------
The Resilience planner (and other agents) only need read-only catalogue
operations — list collections, search items, fetch a collection's JSON.
All three are available on the **public** STAC API at
``https://planetarycomputer.microsoft.com/api/stac/v1`` with no auth, no
license, no sidecar. This adapter lets every agent reach those tools
through ``TracedMcpClient`` so trace events still fire, **without**
requiring the MPC Pro sidecar to be enabled.

MPC Pro remains the right backend for: direct chat queries when the
"MPC Pro" toggle is on, and for personal / private collection access in
the data catalogue. For everything else (agent reasoning over public
collections), this adapter is the default.

Method shape mirrors the public Pro MCP server so the call sites are
identical: ``await client.call("list_mpc_stac_collections", {})``,
``await client.call("search_mpc_items", {...})``, etc.
"""
from __future__ import annotations

import logging
import os
from typing import Any

import httpx


logger = logging.getLogger(__name__)


DEFAULT_PUBLIC_STAC_BASE = "https://planetarycomputer.microsoft.com/api/stac/v1"


class PublicStacAdapter:
    """Thin async HTTP adapter for the public MPC STAC API.

    Exposes one ``async`` method per tool, matching the names used by
    the MPC Pro MCP server so :class:`TracedMcpClient` can dispatch to
    either backend transparently.
    """

    def __init__(
        self,
        base_url: str | None = None,
        *,
        client: httpx.AsyncClient | None = None,
        timeout: float = 20.0,
    ) -> None:
        self.base_url = (base_url or os.getenv("MPC_PUBLIC_STAC_URL") or DEFAULT_PUBLIC_STAC_BASE).rstrip("/")
        self._owns_client = client is None
        self._client = client or httpx.AsyncClient(timeout=timeout)

    async def aclose(self) -> None:
        if self._owns_client:
            await self._client.aclose()

    # ------------------------------------------------------------------
    # Tool-shaped methods. Names match the MPC Pro MCP server so callers
    # can swap underlying implementations without rewriting prompts.
    # ------------------------------------------------------------------

    async def list_mpc_stac_collections(self, **_: Any) -> dict[str, Any]:
        """Return ``{"collections": [...]}`` shaped like the MCP server."""
        resp = await self._client.get(f"{self.base_url}/collections")
        resp.raise_for_status()
        body = resp.json()
        collections = body.get("collections", []) if isinstance(body, dict) else []
        # Trim each collection payload to what the planner actually uses
        # so trace summaries stay readable.
        trimmed = [
            {
                "id": c.get("id"),
                "title": c.get("title"),
                "description": (c.get("description") or "")[:240],
                "keywords": c.get("keywords") or [],
            }
            for c in collections
            if isinstance(c, dict)
        ]
        return {"collections": trimmed, "count": len(trimmed)}

    async def search_mpc_items(
        self,
        *,
        collection: str | None = None,
        collections: list[str] | None = None,
        bbox: list[float] | None = None,
        datetime: str | None = None,
        limit: int = 10,
        **extra: Any,
    ) -> dict[str, Any]:
        """POST ``/search`` with the standard STAC parameters."""
        payload: dict[str, Any] = {"limit": int(limit)}
        if collections:
            payload["collections"] = collections
        elif collection:
            payload["collections"] = [collection]
        if bbox:
            payload["bbox"] = bbox
        if datetime:
            payload["datetime"] = datetime
        # Forward any additional STAC params the caller passes through.
        for k, v in extra.items():
            if v is not None and k not in payload:
                payload[k] = v

        resp = await self._client.post(f"{self.base_url}/search", json=payload)
        resp.raise_for_status()
        body = resp.json() if resp.content else {}
        features = body.get("features", []) if isinstance(body, dict) else []
        # Return a slim view — the LLM only needs ids/datetimes/bboxes
        # to cite. Asset URLs can be fetched on demand.
        items = [
            {
                "id": f.get("id"),
                "collection": f.get("collection"),
                "datetime": (f.get("properties") or {}).get("datetime"),
                "bbox": f.get("bbox"),
            }
            for f in features
            if isinstance(f, dict)
        ]
        return {"items": items, "count": len(items)}

    async def get_mpc_collection_json(
        self,
        *,
        collection_id: str | None = None,
        collection: str | None = None,
        **_: Any,
    ) -> dict[str, Any]:
        """Fetch one collection's full JSON document."""
        cid = collection_id or collection
        if not cid:
            return {"error": "collection_id is required"}
        resp = await self._client.get(f"{self.base_url}/collections/{cid}")
        resp.raise_for_status()
        return resp.json()
