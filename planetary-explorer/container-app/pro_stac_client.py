"""Shared AAD-aware STAC client for MPC Pro / GeoCatalog.

The public Planetary Computer STAC API is anonymous. MPC Pro
(``*.geocatalog.spatio.azure.com``) requires:

  - an AAD bearer token, audience ``https://geocatalog.spatio.azure.com``
  - the ``?api-version=2025-04-30-preview`` query string on every
    data-plane call

This module centralizes both concerns so callers don't have to
re-implement auth in every file. Tokens are cached for ~55 minutes
(AAD tokens are typically valid for 60).

Usage::

    from pro_stac_client import is_pro_url, pro_get, pro_post

    if is_pro_url(url):
        payload = await pro_get(session, url)
    else:
        async with session.get(url) as r:
            payload = await r.json()
"""

from __future__ import annotations

import asyncio
import logging
import os
import time
from typing import Any, Dict, Optional
from urllib.parse import urlparse, urlencode, parse_qsl

import aiohttp

logger = logging.getLogger(__name__)

PRO_HOST_SUFFIX = ".geocatalog.spatio.azure.com"
PRO_AUDIENCE = "https://geocatalog.spatio.azure.com"
PRO_API_VERSION = "2025-04-30-preview"

_token_cache: Dict[str, tuple[str, float]] = {}
_token_lock = asyncio.Lock()


def is_pro_url(url: str) -> bool:
    """True if the URL targets an MPC Pro / GeoCatalog instance."""
    if not url:
        return False
    try:
        host = (urlparse(url).hostname or "").lower()
    except Exception:
        return False
    return host.endswith(PRO_HOST_SUFFIX)


def _ensure_api_version(url: str) -> str:
    """Append ``?api-version=...`` unless already present."""
    parsed = urlparse(url)
    qs = dict(parse_qsl(parsed.query, keep_blank_values=True))
    if "api-version" in qs:
        return url
    qs["api-version"] = PRO_API_VERSION
    new_query = urlencode(qs)
    return parsed._replace(query=new_query).geturl()


async def _acquire_token() -> str:
    """Return a cached or freshly-acquired bearer token for the Pro audience.

    Includes a single retry with linear backoff because the very first
    AAD call after a cold-start container can transiently fail (DNS,
    IMDS warm-up). Subsequent calls hit the in-memory cache.
    """
    now = time.time()
    cached = _token_cache.get(PRO_AUDIENCE)
    if cached and cached[1] - now > 60:
        return cached[0]

    async with _token_lock:
        cached = _token_cache.get(PRO_AUDIENCE)
        if cached and cached[1] - now > 60:
            return cached[0]

        # DefaultAzureCredential supports managed identity in ACA, az-cli
        # locally, env-var SP, etc. Import lazily so unit tests can run
        # without azure-identity installed.
        from azure.identity.aio import DefaultAzureCredential

        last_err: Optional[Exception] = None
        for attempt in range(2):
            cred = DefaultAzureCredential()
            try:
                token = await cred.get_token(f"{PRO_AUDIENCE}/.default")
                _token_cache[PRO_AUDIENCE] = (token.token, token.expires_on)
                logger.info(
                    "[PRO-STAC] AAD token acquired (attempt=%d, expires in %ds)",
                    attempt + 1,
                    int(token.expires_on - now),
                )
                return token.token
            except Exception as exc:  # transient AAD/IMDS hiccups
                last_err = exc
                logger.warning(
                    "[PRO-STAC] AAD token acquisition failed (attempt %d/2): %s",
                    attempt + 1,
                    exc,
                )
            finally:
                try:
                    await cred.close()
                except Exception:
                    pass
            # 0.5s linear backoff between attempts
            if attempt == 0:
                await asyncio.sleep(0.5)

        # Both attempts failed -- bubble up the original error.
        assert last_err is not None
        raise last_err


async def _auth_headers() -> Dict[str, str]:
    tok = await _acquire_token()
    return {"Authorization": f"Bearer {tok}"}


async def pro_get(
    session: aiohttp.ClientSession,
    url: str,
    *,
    timeout: float = 30.0,
) -> Dict[str, Any]:
    """GET an MPC Pro STAC endpoint with AAD auth + api-version.

    Raises aiohttp exceptions on transport failures. Returns the parsed
    JSON body on any HTTP status. On non-2xx, injects ``status`` into
    the returned dict so callers can branch on auth/validation failures
    without having to inspect the raw response object.
    """
    final = _ensure_api_version(url)
    headers = await _auth_headers()
    async with session.get(final, headers=headers, timeout=aiohttp.ClientTimeout(total=timeout)) as r:
        try:
            body = await r.json()
        except aiohttp.ContentTypeError:
            text = await r.text()
            return {"__non_json__": True, "status": r.status, "body": text[:2000]}
        if not (200 <= r.status < 300) and isinstance(body, dict):
            body.setdefault("status", r.status)
        return body


async def pro_post(
    session: aiohttp.ClientSession,
    url: str,
    json_body: Dict[str, Any],
    *,
    timeout: float = 30.0,
) -> Dict[str, Any]:
    """POST JSON to an MPC Pro STAC endpoint with AAD auth + api-version.

    Non-2xx responses have ``status`` injected into the JSON body for
    diagnostic propagation.
    """
    final = _ensure_api_version(url)
    headers = await _auth_headers()
    headers["Content-Type"] = "application/json"
    async with session.post(
        final, headers=headers, json=json_body, timeout=aiohttp.ClientTimeout(total=timeout)
    ) as r:
        try:
            body = await r.json()
        except aiohttp.ContentTypeError:
            text = await r.text()
            return {"__non_json__": True, "status": r.status, "body": text[:2000]}
        if not (200 <= r.status < 300) and isinstance(body, dict):
            body.setdefault("status", r.status)
        return body


async def pro_list_collections(
    session: aiohttp.ClientSession,
    *,
    timeout: float = 30.0,
) -> list[Dict[str, Any]]:
    """Fetch all collections from the configured Pro catalog.

    Returns an empty list when ``MPC_PRO_STAC_URL`` is unset or the
    call fails. Safe to call from background paths -- never raises.
    """
    base = get_pro_stac_base()
    if not base:
        return []
    try:
        payload = await pro_get(session, f"{base}/collections", timeout=timeout)
    except Exception as exc:  # network / auth failure
        logger.warning("[PRO-STAC] list_collections failed: %s", exc)
        return []
    cols = payload.get("collections") if isinstance(payload, dict) else None
    return cols if isinstance(cols, list) else []


# Cached collection-id list (TTL ~5 min) for prompt injection.
_collection_ids_cache: tuple[float, list[str]] = (0.0, [])

# Cached full collection inventory (id + title + description) used by the
# Pro collection-id remapper. Separate from the id-only cache because the
# remapper needs the human-readable text for substring/keyword matching.
_collection_inventory_cache: tuple[float, list[Dict[str, Any]]] = (0.0, [])


async def get_pro_collections_cached(ttl_seconds: float = 300.0) -> list[Dict[str, Any]]:
    """Return the full Pro collection inventory (cached, ~5 min TTL).

    Each entry is a dict with at least ``id`` and the source ``title`` /
    ``description`` when present, so callers can do fuzzy matching of
    public-PC collection ids against the customer's GeoCatalog
    vocabulary without paying an HTTP round-trip per chat turn.

    Returns an empty list when Pro is unconfigured or the catalog call
    fails -- callers must treat that as "no remap data available".
    """
    global _collection_inventory_cache
    now = time.time()
    cached_at, inv = _collection_inventory_cache
    if inv and (now - cached_at) < ttl_seconds:
        return inv
    if not get_pro_stac_base():
        return []
    async with aiohttp.ClientSession() as session:
        cols = await pro_list_collections(session)
    inv = [c for c in cols if isinstance(c, dict) and c.get("id")]
    _collection_inventory_cache = (now, inv)
    return inv


async def get_pro_collection_ids(ttl_seconds: float = 300.0) -> list[str]:
    """Return cached list of Pro collection ids. Empty when not configured.

    Hot path: LoadAgent prompt injection. We don't want to pay the cost
    of an HTTP round-trip per chat request, so cache for ~5 min. Errors
    are swallowed; callers fall back to the legacy public-collection
    flow when the list is empty.

    When the ``USE_MPC_MCP`` flag is on (and ``MPC_MCP_URL`` is set),
    the inventory is fetched via the MPC Pro MCP sidecar
    (:mod:`mcp_catalog_client`) instead of a direct STAC call. On any
    sidecar failure we fall back to the legacy direct path so a flaky
    sidecar never causes a routing outage. The cache is shared across
    both paths so flipping the flag doesn't cause a stampede.
    """
    global _collection_ids_cache
    now = time.time()
    cached_at, ids = _collection_ids_cache
    if ids and (now - cached_at) < ttl_seconds:
        return ids

    # MCP-first path -- gated on USE_MPC_MCP=true and MPC_MCP_URL set.
    try:
        import mcp_catalog_client as _mcp  # local import: keeps this file importable when SDK is absent
        if _mcp.is_enabled():
            try:
                cols = await _mcp.get_client().list_personal_collections()
                ids = [c["id"] for c in cols if isinstance(c, dict) and c.get("id")]
                _collection_ids_cache = (now, ids)
                logger.info(
                    "[pro_stac_client] get_pro_collection_ids via MCP sidecar: %d ids",
                    len(ids),
                )
                return ids
            except _mcp.MpcMcpUnavailable as mcp_exc:
                # Fail-open: log and fall through to the direct STAC path
                # so a sidecar hiccup never breaks routing.
                logger.warning(
                    "[pro_stac_client] MCP sidecar unavailable, falling back to direct STAC: %s",
                    mcp_exc,
                )
            except BaseException as mcp_exc:  # noqa: BLE001 - intentional
                # The MCP SDK uses anyio task groups whose cancel scopes
                # can raise ``BaseExceptionGroup`` / ``RuntimeError`` /
                # ``CancelledError`` that don't subclass ``Exception``.
                # We treat any failure as "sidecar unavailable" and fall
                # back so a flaky upstream never causes a 500 here.
                logger.warning(
                    "[pro_stac_client] MCP sidecar raised %s: %s -- falling back to direct STAC",
                    type(mcp_exc).__name__,
                    mcp_exc,
                )
    except ImportError:
        # mcp SDK not installed -- legacy path, fine.
        pass

    if not get_pro_stac_base():
        return []
    async with aiohttp.ClientSession() as session:
        cols = await pro_list_collections(session)
    ids = [c["id"] for c in cols if isinstance(c, dict) and c.get("id")]
    _collection_ids_cache = (now, ids)
    return ids


def get_pro_stac_base() -> Optional[str]:
    """Resolve the configured MPC Pro STAC base URL (no trailing slash, no /search).

    Honors ``MPC_PRO_STAC_URL`` first, then ``PC_DATA_API_URL`` (legacy),
    then ``STAC_API_URL`` if it happens to point at a Pro host. Returns
    ``None`` when no Pro endpoint is configured.
    """
    for var in ("MPC_PRO_STAC_URL", "PC_DATA_API_URL", "STAC_API_URL"):
        v = (os.getenv(var) or "").strip()
        if v and is_pro_url(v):
            url = v.rstrip("/")
            if url.endswith("/search"):
                url = url[: -len("/search")]
            return url
    return None


def get_pro_data_base() -> Optional[str]:
    """Resolve the configured MPC Pro **data API** base URL (tiler).

    The Pro GeoCatalog exposes both:
      - STAC API at ``https://<catalog>/stac``
      - data API (TiTiler-compatible) at ``https://<catalog>/data``

    Per Microsoft's "Build a web application with Planetary Computer Pro"
    quickstart, the canonical tile URL is
    ``{catalog}/data/collections/{coll}/items/{item}/tiles/{z}/{x}/{y}@1x.png``
    -- there is no ``/data/v1`` path on GeoCatalog. Returns ``None``
    when no Pro endpoint is configured.
    """
    stac_base = get_pro_stac_base()
    if not stac_base:
        return None
    # Strip the trailing ``/stac`` segment to get the host root.
    root = stac_base[: -len("/stac")] if stac_base.endswith("/stac") else stac_base
    return f"{root.rstrip('/')}/data"


def feature_is_pro(feature: Dict[str, Any]) -> bool:
    """True when a STAC feature's ``self`` link points at a Pro GeoCatalog.

    Used to route tilejson generation: Pro features must hit the catalog's
    own data API (and our backend proxy), not the public PC tiler.
    """
    if not isinstance(feature, dict):
        return False
    for link in feature.get("links") or []:
        if not isinstance(link, dict):
            continue
        if (link.get("rel") or "").lower() == "self" and is_pro_url(link.get("href") or ""):
            return True
    return False
