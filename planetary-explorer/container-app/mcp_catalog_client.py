"""MCP client for the MPC Pro MCP sidecar (Microsoft's ``geocatalog-mcp-server``).

Implemented against the official ``mcp`` Python SDK. The sidecar exposes
the upstream Microsoft Planetary Computer Pro MCP tool surface over a
streamable-HTTP transport; this module provides the typed wrappers that
LoadAgent, the collection-selector, and the future ingestion automation
consume. It is the single integration point between the Planetary Explorer
container-app and the MCP world.

Tool coverage
-------------

This file wraps the full 35-tool surface advertised by sidecar version
``MPC-MCP-1.0.9``, grouped by domain:

* **Personal GeoCatalog -- read**: ``list_personal_collections``,
  ``get_personal_collection_details``, ``get_personal_collection_json``,
  ``check_personal_collection_exists``.
* **Personal GeoCatalog -- lifecycle**:
  ``create_personal_stac_collection``, ``delete_personal_collection``,
  ``create_personal_collection_from_mpc``,
  ``create_and_ingest_personal_collection_from_mpc``.
* **Personal GeoCatalog -- items**: ``search_personal_collection_items``,
  ``delete_stac_item_in_personal_collection``.
* **Personal GeoCatalog -- configuration**:
  ``configure_personal_collection_render_options``,
  ``configure_collection_mosaic_definitions``,
  ``replace_personal_collection_thumbnail``,
  ``delete_personal_collection_thumbnail``.
* **Public MPC catalog**: ``list_mpc_collections``,
  ``get_mpc_collection_json``, ``check_mpc_collection_exists``,
  ``search_mpc_items``.
* **Generic STAC**: ``search_stac_items``.
* **Ingestion**: ``create_ingestion_source``, ``list_ingestion_sources``,
  ``get_ingestion_source_details``, ``delete_ingestion_source``,
  ``ingest_stac_item``, ``batch_ingest_stac_items``,
  ``bulk_ingest_stac_items``.
* **Async operations**: ``check_operation_status``,
  ``check_multiple_operations``.
* **Server / debug**: ``get_server_info``, ``list_available_tools``,
  ``generate_jsonrpc_initialize``, ``generate_jsonrpc_tool_call``.
* **Utilities**: ``download_spacenet_chips``, ``download_asset_from_url``.
* **Escape hatches**: ``call_mpc_tools`` (server-side dispatcher),
  ``call_raw`` (bypass the dispatcher entirely).

Design contract
---------------

* **Inert by default.** Until the operator sets ``USE_MPC_MCP=true`` and
  ``MPC_MCP_URL=https://...``, this module performs no network I/O and
  ``is_enabled()`` returns ``False``. Callers gate on :func:`is_enabled`
  before diverting from the legacy ``CollectionMapper`` /
  ``pro_stac_client`` paths.
* **Fail-open.** Every public coroutine catches transport / protocol
  errors and raises :class:`MpcMcpUnavailable`. Callers fall back to the
  legacy path. The chat experience never breaks because the sidecar is
  down.
* **One session per process.** The MCP ``initialize`` handshake and HTTP
  connection pool are reused across calls via a singleton; cold-start
  latency is paid once per worker.
* **Auto-injected GeoCatalog URL.** Every Pro-targeted tool requires
  ``geocatalog_url`` / ``geocatalog_uri``. The client resolves it once
  from ``MPC_PRO_STAC_URL`` (stripping a trailing ``/stac``) and
  inserts it into every Pro tool call via :meth:`MpcMcpClient._pro_args`.
  Public-MPC tools and generic STAC tools do not auto-inject.
* **No wire-protocol code here.** All JSON-RPC framing, content envelope
  unwrapping, and capability negotiation live in the upstream SDK. We
  only own the typed Python surface.
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
from contextlib import AsyncExitStack
from typing import Any, Dict, List, Optional

from mcp import ClientSession
from mcp.client.streamable_http import streamablehttp_client

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Public errors
# ---------------------------------------------------------------------------


class MpcMcpUnavailable(RuntimeError):
    """Raised when the sidecar cannot service a request.

    Callers MUST catch this and fall back to the legacy path. NEVER let
    it propagate to the user -- a down sidecar must not break chat
    turns. Covered scenarios:

    * The sidecar URL is not configured (``MPC_MCP_URL`` unset).
    * The HTTP transport fails (DNS, TCP, TLS, 5xx).
    * The ``initialize`` handshake fails.
    * A requested tool is not advertised by the server.
    * A tool call returns an error response.
    """


# ---------------------------------------------------------------------------
# Client
# ---------------------------------------------------------------------------


class MpcMcpClient:
    """Async client for the MPC Pro MCP sidecar.

    Lifecycle: one instance per process via :func:`get_client`. Holds a
    long-lived ``ClientSession`` that is lazily opened on first use and
    closed at interpreter shutdown via :meth:`close`. ``ClientSession``
    and ``streamablehttp_client`` are async context managers; we keep
    them open via :class:`AsyncExitStack` so subsequent calls reuse the
    same TCP connection and the same MCP session id.
    """

    # The MCP protocol version this client speaks. The SDK negotiates
    # backwards-compatible versions during ``initialize``; we hold a
    # constant here only for log diagnostics.
    PROTOCOL_VERSION = "2024-11-05"

    def __init__(
        self,
        url: Optional[str] = None,
        *,
        api_key: Optional[str] = None,
        request_timeout_seconds: float = 8.0,
    ) -> None:
        # Accept ``MPC_MCP_URL`` with or without a trailing ``/mcp``.
        # Operators get this wrong constantly and a doubled path
        # (``.../mcp/mcp``) used to silently 404 the entire handshake.
        raw = (url or os.getenv("MPC_MCP_URL") or "").strip().rstrip("/")
        if raw.endswith("/mcp"):
            raw = raw[: -len("/mcp")]
        self._url = raw
        self._api_key = api_key or os.getenv("MPC_MCP_API_KEY") or None
        self._request_timeout = request_timeout_seconds
        self._stack: Optional[AsyncExitStack] = None
        self._session: Optional[ClientSession] = None
        self._init_lock = asyncio.Lock()
        self._available_tools: set[str] = set()
        # Root URL of the GeoCatalog the sidecar should target. The MCP
        # tool schemas require ``geocatalog_url`` per call (the sidecar
        # itself is multi-tenant and treats its ``GEOCATALOG_URI`` env
        # var only as a fallback default). Derive from the API
        # container's own ``MPC_PRO_STAC_URL`` by stripping the
        # trailing ``/stac`` -- the sidecar handlers always re-append
        # ``/stac/...`` to whatever we pass.
        stac_url = (os.getenv("MPC_PRO_STAC_URL") or "").strip().rstrip("/")
        if stac_url.endswith("/stac"):
            stac_url = stac_url[: -len("/stac")]
        self._geocatalog_url = stac_url

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    @property
    def configured(self) -> bool:
        """``True`` when ``MPC_MCP_URL`` is set. Callers gate on this."""
        return bool(self._url)

    async def _ensure_session(self) -> ClientSession:
        """Open the streamable-HTTP transport + MCP session if needed.

        Thread-safe within the event loop: a single ``initialize`` runs
        even if multiple coroutines hit a cold client simultaneously.
        """
        if self._session is not None:
            return self._session
        async with self._init_lock:
            if self._session is not None:
                return self._session
            if not self.configured:
                raise MpcMcpUnavailable("MPC_MCP_URL not configured")

            headers: Dict[str, str] = {}
            if self._api_key:
                headers["X-API-Key"] = self._api_key

            stack = AsyncExitStack()
            try:
                # streamablehttp_client yields (read, write, get_session_id).
                # We don't need the session-id callback here -- the SDK
                # uses it internally for streaming notifications.
                read, write, _ = await stack.enter_async_context(
                    streamablehttp_client(
                        url=f"{self._url}/mcp",
                        headers=headers or None,
                    )
                )
                session = await stack.enter_async_context(ClientSession(read, write))
                await session.initialize()

                # Cache the advertised tool surface so individual calls
                # can fail fast with a clear error instead of waiting
                # for a server-side "method not found".
                tools = await session.list_tools()
                self._available_tools = {t.name for t in tools.tools}
                logger.info(
                    "[MCP] connected to %s, %d tools advertised: %s",
                    self._url,
                    len(self._available_tools),
                    ", ".join(sorted(self._available_tools)[:8])
                    + ("..." if len(self._available_tools) > 8 else ""),
                )

                self._stack = stack
                self._session = session
                return session
            except Exception as exc:
                await stack.aclose()
                raise MpcMcpUnavailable(
                    f"MCP session initialization failed: {exc}"
                ) from exc

    async def close(self) -> None:
        """Tear down the session and HTTP transport. Safe to call repeatedly."""
        stack, self._stack = self._stack, None
        self._session = None
        self._available_tools = set()
        if stack is not None:
            try:
                await stack.aclose()
            except Exception as exc:  # pragma: no cover -- shutdown only
                logger.warning("[MCP] error during close: %s", exc)

    # ------------------------------------------------------------------
    # Generic tool invocation
    # ------------------------------------------------------------------

    async def _call_tool(self, name: str, arguments: Dict[str, Any]) -> Any:
        """Invoke an MCP tool and return the unwrapped structured result.

        Most upstream tools return their payload as a single JSON-encoded
        text block in ``content``. We attempt to decode it; if it isn't
        JSON we return the raw text. Tools that set ``isError=True``
        raise :class:`MpcMcpUnavailable` so the caller can fall back.
        """
        try:
            session = await asyncio.wait_for(
                self._ensure_session(), timeout=self._request_timeout
            )
        except asyncio.TimeoutError as exc:
            raise MpcMcpUnavailable("MCP session init timed out") from exc

        if self._available_tools and name not in self._available_tools:
            raise MpcMcpUnavailable(
                f"MCP tool '{name}' not advertised by sidecar "
                f"(server exposes {len(self._available_tools)} tools)"
            )

        try:
            result = await asyncio.wait_for(
                session.call_tool(name, arguments),
                timeout=self._request_timeout,
            )
        except asyncio.TimeoutError as exc:
            raise MpcMcpUnavailable(f"MCP tool '{name}' timed out") from exc
        except Exception as exc:
            # SDK raises on transport / protocol failures; treat all as
            # "sidecar unavailable" so the legacy path runs.
            raise MpcMcpUnavailable(f"MCP tool '{name}' failed: {exc}") from exc

        if getattr(result, "isError", False):
            raise MpcMcpUnavailable(
                f"MCP tool '{name}' returned error: "
                f"{_first_text(result) or '<no detail>'}"
            )

        # Prefer structured content when the server provides it (MCP
        # spec >= 2025-06-18). Fall back to the single text-block JSON
        # pattern that the current MPC server uses.
        structured = getattr(result, "structuredContent", None)
        if structured:
            return structured
        text = _first_text(result)
        if text is None:
            return None
        try:
            return json.loads(text)
        except (ValueError, TypeError):
            return text

    # ------------------------------------------------------------------
    # Typed tool wrappers -- LoadAgent's surface area.
    # ------------------------------------------------------------------

    def _require_geocatalog_url(self) -> str:
        """Return the GeoCatalog root URL or raise ``MpcMcpUnavailable``.

        Every Pro-targeted MCP tool requires this argument. Failing
        fast here gives a clear log message instead of letting the
        sidecar return ``"geocatalog_url is required"``.
        """
        if not self._geocatalog_url:
            raise MpcMcpUnavailable(
                "MPC_PRO_STAC_URL is not configured; cannot resolve the "
                "GeoCatalog root URL required by the MCP sidecar."
            )
        return self._geocatalog_url

    def _pro_args(self, **extras: Any) -> Dict[str, Any]:
        """Build a Pro-tool argument dict with the GeoCatalog URL auto-injected.

        The upstream sidecar is inconsistent: some tool schemas spell
        the param ``geocatalog_url`` (with an L), others ``geocatalog_uri``
        (with an I). Passing both costs nothing and makes us tolerant
        of either version of the upstream binary. ``None`` values in
        ``extras`` are dropped so callers can use ``None`` as "omit".
        """
        gc = self._require_geocatalog_url()
        out: Dict[str, Any] = {"geocatalog_url": gc, "geocatalog_uri": gc}
        for k, v in extras.items():
            if v is not None:
                out[k] = v
        return out

    # ==================================================================
    # Personal GeoCatalog -- collection inventory & metadata
    # ==================================================================

    async def list_personal_collections(self) -> List[Dict[str, Any]]:
        """List collections in the configured Pro GeoCatalog.

        Returns a normalized list of ``{id, title, description}``.
        Empty list when Pro is not configured upstream.
        """
        result = await self._call_tool(
            "list_personal_stac_collections",
            self._pro_args(),
        )
        return _coerce_collection_list(result)

    async def get_personal_collection_details(
        self, collection_id: str, *, include_extended: bool = True
    ) -> Dict[str, Any]:
        """Return the full STAC + summary payload for one Pro collection.

        This is the *profile-driven selector* unlock: the response
        includes the collection's spatial / temporal extent, keywords,
        item_assets, summaries, render options, and mosaic definitions.
        Cache aggressively (extents change rarely).
        """
        result = await self._call_tool(
            "get_personal_collection_details",
            self._pro_args(
                collection_id=collection_id,
                include_extended=include_extended,
            ),
        )
        return result if isinstance(result, dict) else {}

    async def get_personal_collection_json(self, collection_id: str) -> Dict[str, Any]:
        """Return the raw STAC collection JSON (no summary wrapper)."""
        result = await self._call_tool(
            "get_personal_collection_json",
            self._pro_args(collection_id=collection_id),
        )
        return result if isinstance(result, dict) else {}

    async def check_personal_collection_exists(self, collection_id: str) -> bool:
        """Existence probe for a Pro collection. Safe-default ``False``."""
        result = await self._call_tool(
            "check_personal_collection_exists",
            self._pro_args(collection_id=collection_id),
        )
        return _coerce_bool(result)

    # ==================================================================
    # Personal GeoCatalog -- collection lifecycle (write)
    # ==================================================================

    async def create_personal_stac_collection(
        self,
        collection_id: str,
        *,
        title: Optional[str] = None,
        description: Optional[str] = None,
        license: Optional[str] = None,
        spatial_extent: Optional[List[float]] = None,
        temporal_extent_start: Optional[str] = None,
        temporal_extent_end: Optional[str] = None,
        keywords: Optional[List[str]] = None,
        providers: Optional[List[Dict[str, Any]]] = None,
        summaries: Optional[Dict[str, Any]] = None,
        item_assets: Optional[Dict[str, Any]] = None,
        stac_extensions: Optional[List[str]] = None,
        links: Optional[List[Dict[str, Any]]] = None,
        assets: Optional[Dict[str, Any]] = None,
        collection_path: Optional[str] = None,
        simple: bool = True,
    ) -> Dict[str, Any]:
        """Create a new STAC collection. Returns the creation result."""
        result = await self._call_tool(
            "create_personal_stac_collection",
            self._pro_args(
                collection_id=collection_id,
                title=title,
                description=description,
                license=license,
                spatial_extent=spatial_extent,
                temporal_extent_start=temporal_extent_start,
                temporal_extent_end=temporal_extent_end,
                keywords=keywords,
                providers=providers,
                summaries=summaries,
                item_assets=item_assets,
                stac_extensions=stac_extensions,
                links=links,
                assets=assets,
                collection_path=collection_path,
                simple=simple,
            ),
        )
        return result if isinstance(result, dict) else {"raw": result}

    async def delete_personal_collection(self, collection_id: str) -> Dict[str, Any]:
        """Delete a Pro collection. Irreversible; callers must confirm."""
        result = await self._call_tool(
            "delete_personal_collection",
            self._pro_args(collection_id=collection_id),
        )
        return result if isinstance(result, dict) else {"raw": result}

    async def create_personal_collection_from_mpc(
        self,
        *,
        source_collection_id: str,
        target_collection_id: Optional[str] = None,
        title: Optional[str] = None,
        description: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Clone a public MPC collection into the Pro GeoCatalog (metadata only)."""
        result = await self._call_tool(
            "create_personal_collection_from_mpc",
            self._pro_args(
                source_collection_id=source_collection_id,
                target_collection_id=target_collection_id,
                title=title,
                description=description,
            ),
        )
        return result if isinstance(result, dict) else {"raw": result}

    async def create_and_ingest_personal_collection_from_mpc(
        self,
        *,
        source_collection_id: str,
        target_collection_id: Optional[str] = None,
        bbox: Optional[List[float]] = None,
        datetime_range: Optional[str] = None,
        max_items: Optional[int] = None,
        title: Optional[str] = None,
        description: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Clone an MPC collection *and* bulk-ingest items in one call."""
        result = await self._call_tool(
            "create_and_ingest_personal_collection_from_mpc",
            self._pro_args(
                source_collection_id=source_collection_id,
                target_collection_id=target_collection_id,
                bbox=bbox,
                datetime_range=datetime_range,
                max_items=max_items,
                title=title,
                description=description,
            ),
        )
        return result if isinstance(result, dict) else {"raw": result}

    # ==================================================================
    # Personal GeoCatalog -- items
    # ==================================================================

    async def search_personal_collection_items(
        self,
        *,
        collection_id: str,
        bbox: Optional[List[float]] = None,
        datetime_range: Optional[str] = None,
        intersects: Optional[Dict[str, Any]] = None,
        ids: Optional[List[str]] = None,
        query: Optional[Dict[str, Any]] = None,
        limit: int = 10,
        sign_urls: bool = True,
    ) -> Dict[str, Any]:
        """STAC item search inside a Pro collection.

        Returns the raw tool payload: ``{status, items_found, items, ...}``.
        ``sign_urls=True`` makes asset hrefs immediately usable for
        downloading or tiling.
        """
        result = await self._call_tool(
            "search_personal_collection_items",
            self._pro_args(
                collection_id=collection_id,
                bbox=bbox,
                datetime_range=datetime_range,
                intersects=intersects,
                ids=ids,
                query=query,
                limit=limit,
                sign_urls=sign_urls,
            ),
        )
        return result if isinstance(result, dict) else {"raw": result}

    async def delete_stac_item_in_personal_collection(
        self, *, collection_id: str, item_id: str
    ) -> Dict[str, Any]:
        """Delete a single STAC item from a Pro collection."""
        result = await self._call_tool(
            "delete_stac_item_in_personal_collection",
            self._pro_args(collection_id=collection_id, item_id=item_id),
        )
        return result if isinstance(result, dict) else {"raw": result}

    # ==================================================================
    # Personal GeoCatalog -- visualization / configuration
    # ==================================================================

    async def configure_personal_collection_render_options(
        self,
        *,
        collection_id: str,
        render_options: Optional[List[Dict[str, Any]]] = None,
        source_collection_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Install render presets for the GeoCatalog Explorer / tile API.

        Either pass an explicit ``render_options`` list or copy from a
        public MPC collection via ``source_collection_id``.
        """
        result = await self._call_tool(
            "configure_personal_collection_render_options",
            self._pro_args(
                collection_id=collection_id,
                render_options=render_options,
                source_collection_id=source_collection_id,
            ),
        )
        return result if isinstance(result, dict) else {"raw": result}

    async def configure_collection_mosaic_definitions(
        self,
        *,
        collection_id: str,
        mosaic_definitions: Optional[List[Dict[str, Any]]] = None,
        source_collection_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Install mosaic filter rules for dynamic Explorer filtering."""
        result = await self._call_tool(
            "configure_collection_mosaic_definitions",
            self._pro_args(
                collection_id=collection_id,
                mosaic_definitions=mosaic_definitions,
                source_collection_id=source_collection_id,
            ),
        )
        return result if isinstance(result, dict) else {"raw": result}

    # ==================================================================
    # Personal GeoCatalog -- thumbnails
    # ==================================================================

    async def replace_personal_collection_thumbnail(
        self, *, collection_id: str, image_path: str
    ) -> Dict[str, Any]:
        """Upload (or replace) a collection's preview thumbnail PNG."""
        result = await self._call_tool(
            "replace_personal_collection_thumbnail",
            self._pro_args(collection_id=collection_id, image_path=image_path),
        )
        return result if isinstance(result, dict) else {"raw": result}

    async def delete_personal_collection_thumbnail(
        self, collection_id: str
    ) -> Dict[str, Any]:
        """Remove a collection's preview thumbnail."""
        result = await self._call_tool(
            "delete_personal_collection_thumbnail",
            self._pro_args(collection_id=collection_id),
        )
        return result if isinstance(result, dict) else {"raw": result}

    # ==================================================================
    # Public Microsoft Planetary Computer catalog
    # ==================================================================
    # These tools talk to the public planetarycomputer.microsoft.com
    # STAC and do *not* take a ``geocatalog_url`` argument.

    async def list_mpc_collections(self) -> List[Dict[str, Any]]:
        """List collections in the public Planetary Computer catalog."""
        result = await self._call_tool("list_mpc_stac_collections", {})
        return _coerce_collection_list(result)

    async def get_mpc_collection_json(self, collection_id: str) -> Dict[str, Any]:
        """Return the full STAC collection JSON for a public MPC dataset."""
        result = await self._call_tool(
            "get_mpc_collection_json",
            {"collection_id": collection_id},
        )
        return result if isinstance(result, dict) else {}

    async def check_mpc_collection_exists(self, collection_id: str) -> bool:
        """Existence probe for a public MPC collection."""
        result = await self._call_tool(
            "check_mpc_collection_exists",
            {"collection_id": collection_id},
        )
        return _coerce_bool(result)

    async def search_mpc_items(
        self,
        *,
        collection_id: str,
        bbox: Optional[List[float]] = None,
        datetime_range: Optional[str] = None,
        intersects: Optional[Dict[str, Any]] = None,
        query: Optional[Dict[str, Any]] = None,
        ids: Optional[List[str]] = None,
        limit: int = 10,
        save_to_disk: bool = False,
        output_dir: Optional[str] = None,
    ) -> Dict[str, Any]:
        """STAC item search against the public MPC catalog.

        Set ``save_to_disk=True`` to mirror item JSON locally (handy for
        offline dataset prep).
        """
        args: Dict[str, Any] = {
            "collection_id": collection_id,
            "limit": limit,
            "save_to_disk": save_to_disk,
        }
        if bbox is not None:
            args["bbox"] = bbox
        if datetime_range is not None:
            args["datetime_range"] = datetime_range
        if intersects is not None:
            args["intersects"] = intersects
        if query is not None:
            args["query"] = query
        if ids is not None:
            args["ids"] = ids
        if output_dir is not None:
            args["output_dir"] = output_dir
        result = await self._call_tool("search_mpc_items", args)
        return result if isinstance(result, dict) else {"raw": result}

    # ==================================================================
    # Generic STAC (any STAC API)
    # ==================================================================

    async def search_stac_items(
        self,
        *,
        stac_api_url: str,
        collection_id: Optional[str] = None,
        bbox: Optional[List[float]] = None,
        datetime_range: Optional[str] = None,
        intersects: Optional[Dict[str, Any]] = None,
        query: Optional[Dict[str, Any]] = None,
        ids: Optional[List[str]] = None,
        limit: int = 10,
    ) -> Dict[str, Any]:
        """STAC item search against an arbitrary STAC-API-compliant root."""
        args: Dict[str, Any] = {"stac_api_url": stac_api_url, "limit": limit}
        if collection_id is not None:
            args["collection_id"] = collection_id
        if bbox is not None:
            args["bbox"] = bbox
        if datetime_range is not None:
            args["datetime_range"] = datetime_range
        if intersects is not None:
            args["intersects"] = intersects
        if query is not None:
            args["query"] = query
        if ids is not None:
            args["ids"] = ids
        result = await self._call_tool("search_stac_items", args)
        return result if isinstance(result, dict) else {"raw": result}

    # ==================================================================
    # Ingestion (writes; require an ingestion source / managed identity)
    # ==================================================================

    async def create_ingestion_source(self, container_uri: str) -> Dict[str, Any]:
        """Register an Azure blob container as a GeoCatalog ingestion source."""
        result = await self._call_tool(
            "create_ingestion_source",
            self._pro_args(container_uri=container_uri),
        )
        return result if isinstance(result, dict) else {"raw": result}

    async def list_ingestion_sources(self) -> List[Dict[str, Any]]:
        """List all ingestion sources configured on the Pro GeoCatalog."""
        result = await self._call_tool("list_ingestion_sources", self._pro_args())
        if isinstance(result, dict):
            sources = result.get("sources") or result.get("value") or []
            return sources if isinstance(sources, list) else []
        return result if isinstance(result, list) else []

    async def get_ingestion_source_details(self, source_id: str) -> Dict[str, Any]:
        """Return the full record for one ingestion source."""
        result = await self._call_tool(
            "get_ingestion_source_details",
            self._pro_args(source_id=source_id),
        )
        return result if isinstance(result, dict) else {}

    async def delete_ingestion_source(self, source_id: str) -> Dict[str, Any]:
        """Remove an ingestion source (does not delete underlying blobs)."""
        result = await self._call_tool(
            "delete_ingestion_source",
            self._pro_args(source_id=source_id),
        )
        return result if isinstance(result, dict) else {"raw": result}

    async def ingest_stac_item(
        self, *, collection_id: str, item: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Ingest a single STAC item into a Pro collection.

        Returns the async operation handle (``operation_id``) when the
        upstream replies 202 Accepted.
        """
        result = await self._call_tool(
            "ingest_stac_item",
            self._pro_args(collection_id=collection_id, item=item),
        )
        return result if isinstance(result, dict) else {"raw": result}

    async def batch_ingest_stac_items(
        self,
        *,
        collection_id: str,
        items: List[Dict[str, Any]],
        poll_operations: bool = True,
    ) -> Dict[str, Any]:
        """Ingest many STAC items in one call. Poll-aware."""
        result = await self._call_tool(
            "batch_ingest_stac_items",
            self._pro_args(
                collection_id=collection_id,
                items=items,
                poll_operations=poll_operations,
            ),
        )
        return result if isinstance(result, dict) else {"raw": result}

    async def bulk_ingest_stac_items(
        self,
        *,
        target_collection_id: str,
        stac_api_url: str,
        source_collection_id: str,
        bbox: Optional[List[float]] = None,
        datetime_range: Optional[str] = None,
        max_items: int = 10,
    ) -> Dict[str, Any]:
        """Search a remote STAC API and bulk-ingest matched items.

        High-level convenience: one call mirrors a slice of an upstream
        STAC into the Pro GeoCatalog.
        """
        result = await self._call_tool(
            "bulk_ingest_stac_items",
            self._pro_args(
                target_collection_id=target_collection_id,
                stac_api_url=stac_api_url,
                source_collection_id=source_collection_id,
                bbox=bbox,
                datetime_range=datetime_range,
                max_items=max_items,
            ),
        )
        return result if isinstance(result, dict) else {"raw": result}

    # ==================================================================
    # Async operations (poll ingestion / deletion progress)
    # ==================================================================

    async def check_operation_status(self, operation_id: str) -> Dict[str, Any]:
        """Return the status of a single async GeoCatalog operation."""
        result = await self._call_tool(
            "check_operation_status",
            self._pro_args(operation_id=operation_id),
        )
        return result if isinstance(result, dict) else {}

    async def check_multiple_operations(
        self, operation_ids: List[str]
    ) -> Dict[str, Any]:
        """Status check for many operations in one round-trip."""
        result = await self._call_tool(
            "check_multiple_operations",
            self._pro_args(operation_ids=operation_ids),
        )
        return result if isinstance(result, dict) else {}

    # ==================================================================
    # Server introspection / debug
    # ==================================================================

    async def get_server_info(self) -> Dict[str, Any]:
        """Return MCP server metadata (name, version, capabilities)."""
        result = await self._call_tool("get_server_info", {})
        return result if isinstance(result, dict) else {}

    async def list_available_tools(self) -> List[Dict[str, Any]]:
        """List every tool the sidecar advertises (server-side authoritative).

        Useful for periodic conformance checks: ``set(self._available_tools)``
        is what *we* discovered at initialize time; this is what the
        upstream currently exposes.
        """
        result = await self._call_tool("list_available_tools", {})
        if isinstance(result, dict):
            tools = result.get("tools") or result.get("available_tools") or []
            return tools if isinstance(tools, list) else []
        return result if isinstance(result, list) else []

    async def generate_jsonrpc_initialize(self) -> Dict[str, Any]:
        """Return a canonical ``initialize`` JSON-RPC envelope (debug aid)."""
        result = await self._call_tool("generate_jsonrpc_initialize", {})
        return result if isinstance(result, dict) else {}

    async def generate_jsonrpc_tool_call(
        self,
        *,
        tool_name: str,
        arguments: Dict[str, Any],
        request_id: int = 2,
    ) -> Dict[str, Any]:
        """Return a canonical ``tools/call`` JSON-RPC envelope (debug aid)."""
        result = await self._call_tool(
            "generate_jsonrpc_tool_call",
            {
                "tool_name": tool_name,
                "arguments": arguments,
                "request_id": request_id,
            },
        )
        return result if isinstance(result, dict) else {}

    # ==================================================================
    # Utilities
    # ==================================================================

    async def download_spacenet_chips(
        self,
        *,
        start_chip: int = 990,
        end_chip: int = 1000,
        output_dir: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Download a slice of SpaceNet 5 training chips (Moscow AOI)."""
        args: Dict[str, Any] = {"start_chip": start_chip, "end_chip": end_chip}
        if output_dir is not None:
            args["output_dir"] = output_dir
        result = await self._call_tool("download_spacenet_chips", args)
        return result if isinstance(result, dict) else {"raw": result}

    async def download_asset_from_url(
        self, *, url: str, output_path: str
    ) -> Dict[str, Any]:
        """Download a (typically pre-signed) asset URL to local disk."""
        result = await self._call_tool(
            "download_asset_from_url",
            {"url": url, "output_path": output_path},
        )
        return result if isinstance(result, dict) else {"raw": result}

    # ==================================================================
    # Universal dispatcher (escape hatch)
    # ==================================================================

    async def call_mpc_tools(
        self, *, tool_name: str, tool_arguments: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Server-side dispatcher: invoke any registered tool by name.

        Lets newly-added upstream tools work without a client release.
        Prefer the typed wrappers above; reach for this only when the
        sidecar version is ahead of this file.
        """
        result = await self._call_tool(
            "call_mpc_tools",
            {"tool_name": tool_name, "tool_arguments": tool_arguments},
        )
        return result if isinstance(result, dict) else {"raw": result}

    async def call_raw(
        self, tool_name: str, arguments: Dict[str, Any]
    ) -> Any:
        """Lowest-level escape hatch: bypass both typed wrappers AND the
        sidecar's ``call_mpc_tools`` dispatcher. Useful for tools that
        don't fit any of the above signatures.

        Returns the raw unwrapped tool payload (whatever JSON the tool
        returned). Raises :class:`MpcMcpUnavailable` on transport error.
        """
        return await self._call_tool(tool_name, arguments)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _first_text(call_tool_result: Any) -> Optional[str]:
    """Return the text of the first ``TextContent`` block, if any."""
    content = getattr(call_tool_result, "content", None) or []
    for block in content:
        # The SDK exposes ``TextContent`` with ``.text``; tolerate dict
        # shapes for forward compatibility.
        text = getattr(block, "text", None)
        if text is None and isinstance(block, dict):
            if block.get("type") == "text":
                text = block.get("text")
        if isinstance(text, str):
            return text
    return None


def _coerce_collection_list(result: Any) -> List[Dict[str, Any]]:
    """Normalize the various shapes upstream tools return."""
    if isinstance(result, list):
        items = result
    elif isinstance(result, dict):
        items = result.get("collections") or result.get("items") or []
    else:
        items = []
    out: List[Dict[str, Any]] = []
    for it in items:
        if not isinstance(it, dict):
            continue
        cid = it.get("id") or it.get("collection_id")
        if not cid:
            continue
        out.append(
            {
                "id": cid,
                "title": it.get("title") or cid,
                "description": it.get("description", "") or "",
            }
        )
    return out


def _coerce_bool(result: Any) -> bool:
    """Normalize the various truthiness shapes upstream tools return.

    Safe default is **False**: when the response shape is unrecognized
    (e.g. a dict with no ``exists`` / ``found`` / ``result`` key), we
    treat it as "no" so the literal-id passthrough does not optimistically
    claim a collection is present when we can't actually tell.
    """
    if isinstance(result, bool):
        return result
    if isinstance(result, dict):
        for k in ("exists", "found", "result"):
            v = result.get(k)
            if isinstance(v, bool):
                return v
        # Unrecognized dict shape -- default to False rather than the
        # Python truthiness of "non-empty dict is truthy".
        return False
    if isinstance(result, str):
        return result.strip().lower() in {"true", "yes", "1"}
    if isinstance(result, (int, float)):
        return bool(result)
    return False


# ---------------------------------------------------------------------------
# Process-wide singleton
# ---------------------------------------------------------------------------


_client_singleton: Optional[MpcMcpClient] = None


def get_client() -> MpcMcpClient:
    """Return the process-wide MCP client.

    Construction is cheap (no I/O); the underlying MCP session is opened
    lazily on the first tool call.
    """
    global _client_singleton
    if _client_singleton is None:
        _client_singleton = MpcMcpClient()
    return _client_singleton


def is_enabled() -> bool:
    """Single source of truth for "are we using the MCP sidecar right now?".

    Returns ``True`` only when BOTH the operator has flipped
    ``USE_MPC_MCP=true`` AND ``MPC_MCP_URL`` is configured. Callers must
    check this before diverting from the legacy path; the inverse
    keeps the demo working when the sidecar is unreachable or not yet
    rolled out.

    We deliberately do *not* construct the singleton client here -- env
    is the source of truth, and short-circuiting on env keeps the
    enabled-check cheap and side-effect-free.
    """
    flag = (os.getenv("USE_MPC_MCP") or "").strip().lower()
    if flag not in {"1", "true", "yes", "on"}:
        return False
    return bool((os.getenv("MPC_MCP_URL") or "").strip())


async def shutdown() -> None:
    """Close the singleton client. Wire this into the FastAPI lifespan
    handler so the MCP session is released cleanly on container stop."""
    global _client_singleton
    if _client_singleton is not None:
        await _client_singleton.close()
        _client_singleton = None
