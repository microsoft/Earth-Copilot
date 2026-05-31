"""Mosaic / search-based tile rendering for MPC Pro (GeoCatalog).

Per-item tilejson covers only one STAC item's footprint -- e.g. a single
Sentinel-2 MGRS granule is ~110x110 km, so a "Show me Sentinel-2 fire
images of California" answer that attaches one item's tilejson renders a
tiny patch and the rest of the viewport gets HTTP 424 (Failed Dependency)
from the upstream tiler. The titiler-pgstac mosaic API solves this by
registering a STAC search and returning a single tilejson whose tiles are
seamlessly composited from every matching item.

Microsoft Planetary Computer Pro inherits the same titiler-pgstac data
plane. We probe ``{data}/mosaic/register`` first (matches public PC) and
fall back to ``{data}/searches/register`` (newer titiler-pgstac), caching
which path worked per-process.

This module mirrors :mod:`hybrid_rendering_system.register_mosaic_search`
but talks to the AAD-protected Pro data API and synthesizes a same-origin
tilejson whose ``tiles[0]`` template routes through ``/api/pro/tile/``
(see :func:`fastapi_app.pro_tile_proxy`) so the browser stays anonymous.
"""

from __future__ import annotations

import json
import logging
import os
import time
from typing import Any, Dict, List, Optional, Tuple
import hashlib

import aiohttp

from pro_stac_client import (
    PRO_API_VERSION,
    _auth_headers,
    get_pro_data_base,
)

logger = logging.getLogger(__name__)


# Per-process cache of which mosaic-register path actually works on the
# configured GeoCatalog data plane. We probe ``mosaic/register`` first
# (matches public PC) and fall back to ``searches/register`` if the Pro
# instance is on a newer titiler-pgstac. A negative cache (None) is set
# when both 404 so we don't keep probing.
_REGISTER_PATH_PROBE_ORDER: Tuple[str, ...] = ("mosaic/register", "searches/register")
_register_path_cache: Optional[str] = None
_register_path_unavailable: bool = False


# Cache of (cache_key) -> (search_id, register_path, timestamp). We re-use
# the search_id for repeated identical queries (same collections + bbox +
# datetime + filters) so we don't hammer ``/mosaic/register`` on every
# repeat user query.
_MOSAIC_TTL_SECONDS = 600.0  # 10 minutes
_search_cache: Dict[str, Tuple[str, str, float]] = {}


def _cache_key(
    collections: List[str],
    bbox: Optional[List[float]],
    datetime_range: Optional[str],
    item_ids: Optional[List[str]],
    extra_filters: Optional[Dict[str, Any]],
) -> str:
    """Deterministic cache key for a mosaic registration."""
    payload = json.dumps(
        {
            "c": sorted(collections or []),
            "b": [round(float(x), 4) for x in (bbox or [])],
            "d": datetime_range or "",
            "i": sorted(item_ids or []),
            "f": extra_filters or {},
        },
        sort_keys=True,
        default=str,
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:24]


def _build_search_body(
    collections: List[str],
    bbox: Optional[List[float]],
    datetime_range: Optional[str],
    item_ids: Optional[List[str]] = None,
    extra_filters: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Build a CQL2-JSON STAC search body suitable for /mosaic/register."""
    body: Dict[str, Any] = {
        "collections": list(collections or []),
        "filter-lang": "cql2-json",
    }
    cql_args: List[Dict[str, Any]] = []

    if bbox and len(bbox) == 4:
        cql_args.append(
            {
                "op": "s_intersects",
                "args": [
                    {"property": "geometry"},
                    {
                        "type": "Polygon",
                        "coordinates": [
                            [
                                [bbox[0], bbox[1]],
                                [bbox[2], bbox[1]],
                                [bbox[2], bbox[3]],
                                [bbox[0], bbox[3]],
                                [bbox[0], bbox[1]],
                            ]
                        ],
                    },
                ],
            }
        )

    if datetime_range:
        if "/" in datetime_range:
            start_dt, end_dt = datetime_range.split("/", 1)
        else:
            start_dt = end_dt = datetime_range
        cql_args.append(
            {
                "op": "t_intersects",
                "args": [
                    {"property": "datetime"},
                    {"interval": [start_dt, end_dt]},
                ],
            }
        )

    if item_ids:
        # Prefer registering exactly the items the agent already resolved
        # so the mosaic matches the chat answer's item count even if the
        # bbox / datetime range would otherwise pull in extra granules.
        cql_args.append(
            {
                "op": "in",
                "args": [{"property": "id"}, list(item_ids)],
            }
        )

    if extra_filters and "eo:cloud_cover" in extra_filters:
        cc = extra_filters["eo:cloud_cover"]
        if isinstance(cc, dict) and "lt" in cc:
            cql_args.append({"op": "<", "args": [{"property": "eo:cloud_cover"}, cc["lt"]]})
        elif isinstance(cc, dict) and "lte" in cc:
            cql_args.append({"op": "<=", "args": [{"property": "eo:cloud_cover"}, cc["lte"]]})

    if cql_args:
        body["filter"] = {"op": "and", "args": cql_args} if len(cql_args) > 1 else cql_args[0]

    return body


async def _post_register(
    session: aiohttp.ClientSession,
    base: str,
    path: str,
    body: Dict[str, Any],
    timeout: float = 20.0,
) -> Tuple[int, Optional[Dict[str, Any]], str]:
    """POST to ``{base}/{path}?api-version=...`` with AAD bearer.

    Returns ``(status, json_or_none, text_preview)``. The text preview is
    truncated to 300 chars and is only consumed for log lines; callers
    decide what to do with the status.
    """
    headers = await _auth_headers()
    headers["Content-Type"] = "application/json"
    url = f"{base.rstrip('/')}/{path}?api-version={PRO_API_VERSION}"
    try:
        async with session.post(
            url, json=body, headers=headers, timeout=aiohttp.ClientTimeout(total=timeout)
        ) as resp:
            status = resp.status
            text = await resp.text()
            data: Optional[Dict[str, Any]] = None
            if status < 400:
                try:
                    data = json.loads(text)
                except Exception:
                    data = None
            return status, data, text[:300]
    except Exception as exc:
        logger.debug("[PRO-MOSAIC] _post_register network error %s: %s", url, exc)
        return -1, None, str(exc)[:300]


async def register_pro_mosaic_search(
    collections: List[str],
    *,
    bbox: Optional[List[float]] = None,
    datetime_range: Optional[str] = None,
    item_ids: Optional[List[str]] = None,
    extra_filters: Optional[Dict[str, Any]] = None,
) -> Optional[Tuple[str, str]]:
    """Register a STAC search against the Pro data plane's mosaic API.

    Returns ``(search_id, register_path)`` on success, ``None`` on failure
    (network error, 4xx/5xx, or both probe paths return 404). The
    ``register_path`` is the relative URL segment that worked
    (``"mosaic/register"`` or ``"searches/register"``); callers must use
    the matching tile path layout when synthesizing tilejson URLs.
    """
    global _register_path_cache, _register_path_unavailable

    if not collections:
        logger.warning("[PRO-MOSAIC] register: no collections provided")
        return None

    pro_data_base = get_pro_data_base()
    if not pro_data_base:
        logger.info("[PRO-MOSAIC] register: MPC Pro not configured (no data base URL)")
        return None

    if _register_path_unavailable:
        # Both paths failed previously this process; don't keep probing.
        return None

    cache_key = _cache_key(collections, bbox, datetime_range, item_ids, extra_filters)
    cached = _search_cache.get(cache_key)
    if cached:
        sid, rpath, ts = cached
        if (time.time() - ts) < _MOSAIC_TTL_SECONDS:
            logger.info(
                "[PRO-MOSAIC] cache hit %s -> %s (path=%s)", cache_key, sid[:16], rpath
            )
            return sid, rpath

    body = _build_search_body(collections, bbox, datetime_range, item_ids, extra_filters)

    paths_to_try: Tuple[str, ...]
    if _register_path_cache:
        paths_to_try = (_register_path_cache,)
    else:
        paths_to_try = _REGISTER_PATH_PROBE_ORDER

    async with aiohttp.ClientSession() as session:
        last_status = -1
        last_preview = ""
        for path in paths_to_try:
            status, data, preview = await _post_register(session, pro_data_base, path, body)
            last_status = status
            last_preview = preview

            if 200 <= status < 300 and isinstance(data, dict):
                search_id = (
                    data.get("searchid")
                    or data.get("search_id")
                    or data.get("id")
                )
                if not search_id:
                    logger.warning(
                        "[PRO-MOSAIC] %s returned %d but no search_id in body: %s",
                        path, status, preview,
                    )
                    continue
                _register_path_cache = path
                _search_cache[cache_key] = (search_id, path, time.time())
                logger.info(
                    "[PRO-MOSAIC] registered via %s -> search_id=%s collections=%s",
                    path, str(search_id)[:16], collections,
                )
                return search_id, path

            # 404 / 405 -> try next probe path.
            if status in (404, 405):
                logger.info(
                    "[PRO-MOSAIC] %s -> %d, will try next probe path", path, status
                )
                continue

            # Any other non-2xx is a hard failure for this request; don't
            # also try the alternate probe path (likely same upstream
            # error). Return None and log.
            logger.warning(
                "[PRO-MOSAIC] %s -> %d body=%s", path, status, preview
            )
            return None

    # Both probe paths exhausted without success.
    if last_status in (404, 405):
        # Permanently disable for this process -- the data plane simply
        # doesn't expose a mosaic endpoint.
        _register_path_unavailable = True
        logger.warning(
            "[PRO-MOSAIC] no mosaic endpoint available on this GeoCatalog "
            "(last status=%d preview=%s); per-item rendering will be used.",
            last_status, last_preview,
        )
    return None


def build_pro_mosaic_tilejson_proxy_url(
    *,
    search_id: str,
    register_path: str,
    collection_id: str,
    render_params: List[str],
    tile_matrix: str = "WebMercatorQuad",
) -> str:
    """Build the same-origin /api/pro/mosaic/tilejson URL the SPA hits.

    The SPA fetches this URL; the backend ``pro_mosaic_tilejson_proxy``
    route synthesizes a TileJSON 2.2.0 document whose ``tiles[]`` template
    routes through ``/api/pro/tile/...``.
    """
    api_public_base = (os.getenv("API_PUBLIC_BASE_URL") or "").rstrip("/")
    base = (
        f"{api_public_base}/api/pro/mosaic/tilejson"
        if api_public_base
        else "/api/pro/mosaic/tilejson"
    )
    parts = [
        f"search_id={search_id}",
        f"collection={collection_id}",
        # ``register_path`` tells the proxy which tile-path layout to emit
        # -- ``mosaic/{search_id}/...`` vs ``searches/{search_id}/...``.
        # Pass it through so the proxy doesn't need its own probe cache.
        f"register_path={register_path}",
        f"tileMatrixSetId={tile_matrix}",
    ]
    parts.extend(render_params or [])
    return f"{base}?{'&'.join(parts)}"


async def get_pro_mosaic_tilejson(
    *,
    collection_id: str,
    bbox: Optional[List[float]] = None,
    datetime_range: Optional[str] = None,
    item_ids: Optional[List[str]] = None,
    render_params: Optional[List[str]] = None,
) -> Optional[Dict[str, Any]]:
    """One-shot helper: register the search and return the SPA payload.

    Returns ``{"tilejson_url", "search_id", "collection", "is_mosaic":
    True, "register_path"}`` -- shape matches what
    ``hybrid_rendering_system.get_mosaic_tilejson_url`` produces for the
    public PC path so :class:`MapView` can stay path-agnostic.
    """
    result = await register_pro_mosaic_search(
        collections=[collection_id],
        bbox=bbox,
        datetime_range=datetime_range,
        item_ids=item_ids,
    )
    if not result:
        return None
    search_id, register_path = result

    proxy_url = build_pro_mosaic_tilejson_proxy_url(
        search_id=search_id,
        register_path=register_path,
        collection_id=collection_id,
        render_params=render_params or [],
    )
    return {
        "tilejson_url": proxy_url,
        "search_id": search_id,
        "collection": collection_id,
        "is_mosaic": True,
        "register_path": register_path,
    }
