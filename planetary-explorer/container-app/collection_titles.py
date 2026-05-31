"""In-memory cache of STAC collection id -> human-readable title.

Used by the post-render chat summary in fastapi_app.py to describe what
is on the map ("Displaying 12 HLS Sentinel-2 (HLSS30 v2.0) images of
Moscow ...") using the canonical title from the upstream STAC catalog
rather than a hand-curated dict that drifts when MPC renames a
collection.

Sources, in priority order:
  1. Microsoft Planetary Computer  -- ``cloud_cfg.stac_catalog_url`` (public)
  2. MPC Pro / GeoCatalog          -- ``MPC_PRO_STAC_URL`` env var, optional

Both are queried in parallel at startup. The fetch is non-blocking from
the perspective of request handling: lookups always return immediately
from the in-memory dict, and the dict is pre-seeded from a tiny
``_BOOTSTRAP_TITLES`` dict so it is never empty even before the first
refresh completes.

A single background task refreshes every ``_TTL_SECONDS`` (24h by
default) so collection renames in MPC propagate within a day. Any error
during refresh is logged and ignored -- the previous cache stays live.

This module is intentionally dependency-light: only ``aiohttp`` (already
a runtime dep) and ``cloud_cfg``.
"""

from __future__ import annotations

import asyncio
import logging
import os
import time
from typing import Dict, Iterable, Optional, Tuple

import aiohttp

logger = logging.getLogger(__name__)


# Conservative offline default. Used only until the first refresh
# completes (~one HTTP round-trip after process start). Keeping it small
# on purpose -- the live fetch returns 100+ collections within a second.
_BOOTSTRAP_TITLES: Dict[str, str] = {
    "sentinel-2-l2a": "Sentinel-2 Level-2A",
    "sentinel-1-rtc": "Sentinel-1 RTC",
    "sentinel-1-grd": "Sentinel-1 GRD",
    "landsat-c2-l2": "Landsat Collection 2 Level-2",
    "landsat-c2-l1": "Landsat Collection 2 Level-1",
    "hls2-l30": "Harmonized Landsat Sentinel-2 (HLS) v2.0, Landsat",
    "hls2-s30": "Harmonized Landsat Sentinel-2 (HLS) v2.0, Sentinel-2",
    "naip": "NAIP aerial imagery",
    "cop-dem-glo-30": "Copernicus DEM (30m)",
    "cop-dem-glo-90": "Copernicus DEM (90m)",
    "nasadem": "NASADEM",
    "io-lulc-9-class": "Esri IO Land Cover (9-class)",
    "io-lulc-annual-v02": "Esri IO Land Cover (annual)",
    "esa-worldcover": "ESA WorldCover",
    "ms-buildings": "Microsoft Building Footprints",
}


_TTL_SECONDS = int(os.getenv("STAC_TITLES_TTL_SECONDS", "86400"))  # 24h
_FETCH_TIMEOUT_SECONDS = float(os.getenv("STAC_TITLES_FETCH_TIMEOUT", "8"))

# Two isolated caches -- one per STAC mode. Earlier versions merged both
# catalogs into a single dict, which let the MPC Pro title for shared
# collection ids (e.g. ``sentinel-2-l2a`` -- ingested into GeoCatalog as
# "Sentinel-2 Level-2A (Private mirror)") leak into Public-mode chat
# responses. The fix is structural: Public lookups never see Pro titles
# and vice versa.
_titles_public: Dict[str, str] = dict(_BOOTSTRAP_TITLES)
_titles_pro: Dict[str, str] = {}
_last_refresh: float = 0.0
_refresh_lock = asyncio.Lock()
_background_task: Optional[asyncio.Task] = None

_VALID_MODES = ("public", "pro")


def _normalize_mode(mode: Optional[str]) -> str:
    m = (mode or "public").lower()
    return m if m in _VALID_MODES else "public"


def get_title(collection_id: Optional[str], mode: Optional[str] = "public") -> str:
    """Return a friendly title for *collection_id* in the given *mode*.

    The two STAC sources are kept isolated so a Pro-mode-only quirk
    (``"... (Private mirror)"`` suffixes, custom ingest titles) cannot
    bleed into Public-mode responses.

    Resolution order:
      1. For Pro lookups against a collection id that ALSO exists in the
         Public catalog, prefer Public's title. Shared ids represent the
         same dataset and should render the same in both modes; Pro
         operators occasionally add suffixes at ingest time that are not
         meaningful to end users.
      2. The mode-specific cache.
      3. The raw id.
      4. ``"satellite imagery"`` for empty input.
    """
    if not collection_id:
        return "satellite imagery"
    m = _normalize_mode(mode)
    if m == "pro":
        shared = _titles_public.get(collection_id)
        if shared:
            return shared
        return _titles_pro.get(collection_id, collection_id)
    return _titles_public.get(collection_id, collection_id)


def get_titles(
    collection_ids: Iterable[Optional[str]],
    mode: Optional[str] = "public",
) -> Dict[str, str]:
    """Bulk variant of :func:`get_title`. Preserves input ordering."""
    return {cid: get_title(cid, mode) for cid in collection_ids if cid}


def cache_size() -> int:
    """Number of cached titles (sum across modes)."""
    return len(_titles_public) + len(_titles_pro)


def last_refresh_age_seconds() -> Optional[float]:
    """Seconds since the last successful refresh, or ``None`` if never."""
    if _last_refresh == 0.0:
        return None
    return max(0.0, time.time() - _last_refresh)


async def _fetch_one(session: aiohttp.ClientSession, base_url: str, source: str) -> Dict[str, str]:
    """Hit ``{base_url}/collections`` and return ``{id: title}``.

    Returns an empty dict on any failure -- callers merge with the
    existing cache, so partial results never wipe known titles.

    For MPC Pro / GeoCatalog hosts, routes through
    :mod:`pro_stac_client` so the call carries an AAD bearer token and
    the required ``api-version`` query string.
    """
    if not base_url:
        return {}
    # Normalize: strip trailing slash + any trailing /search the legacy
    # STAC URL constants carry.
    url = base_url.rstrip("/")
    if url.endswith("/search"):
        url = url[: -len("/search")]
    url = f"{url}/collections"
    try:
        # MPC Pro requires AAD bearer + api-version; the public PC is anonymous.
        from pro_stac_client import is_pro_url, pro_get

        if is_pro_url(url):
            payload = await pro_get(session, url, timeout=_FETCH_TIMEOUT_SECONDS)
            if isinstance(payload, dict) and payload.get("__non_json__"):
                logger.warning(
                    "[STAC-TITLES] %s GET %s -> HTTP %d (non-JSON body)",
                    source, url, payload.get("status"),
                )
                return {}
        else:
            async with session.get(url, timeout=aiohttp.ClientTimeout(total=_FETCH_TIMEOUT_SECONDS)) as resp:
                if resp.status != 200:
                    logger.warning(
                        "[STAC-TITLES] %s GET %s -> HTTP %d", source, url, resp.status
                    )
                    return {}
                payload = await resp.json()
    except Exception as exc:
        logger.warning("[STAC-TITLES] %s fetch failed (%s): %s", source, url, exc)
        return {}

    raw_collections = []
    if isinstance(payload, dict):
        raw_collections = payload.get("collections") or []
    elif isinstance(payload, list):
        raw_collections = payload

    out: Dict[str, str] = {}
    for col in raw_collections:
        if not isinstance(col, dict):
            continue
        cid = col.get("id")
        title = col.get("title")
        if isinstance(cid, str) and isinstance(title, str) and title.strip():
            out[cid] = title.strip()
    logger.info("[STAC-TITLES] %s -> %d titles", source, len(out))
    return out


async def refresh_now(force: bool = False) -> Tuple[int, int]:
    """Fetch the latest catalog from MPC + MPC Pro and update the cache.

    Returns ``(added, total)``. Safe to call concurrently -- the lock
    guarantees only one in-flight refresh. Public and Pro titles are
    stored in separate caches so a Pro-ingest-time suffix on a shared
    collection id cannot leak into Public-mode chat responses.
    """
    global _titles_public, _titles_pro, _last_refresh

    async with _refresh_lock:
        if not force and last_refresh_age_seconds() is not None:
            age = last_refresh_age_seconds() or 0.0
            if age < _TTL_SECONDS:
                return (0, cache_size())

        # Resolve sources lazily so importing this module never triggers
        # cloud_config side-effects.
        try:
            from cloud_config import cloud_cfg  # type: ignore
            mpc_url = getattr(cloud_cfg, "stac_catalog_url", None) or ""
        except Exception:
            mpc_url = "https://planetarycomputer.microsoft.com/api/stac/v1"
        mpc_pro_url = (
            os.getenv("MPC_PRO_STAC_URL")
            or os.getenv("PC_DATA_API_URL")
            or os.getenv("STAC_API_URL")
            or ""
        )

        async with aiohttp.ClientSession() as session:
            public_result, pro_result = await asyncio.gather(
                _fetch_one(session, mpc_url, "MPC"),
                _fetch_one(session, mpc_pro_url, "MPC-Pro") if mpc_pro_url else _noop(),
                return_exceptions=True,
            )

        added = 0
        if isinstance(public_result, dict) and public_result:
            merged_public: Dict[str, str] = dict(_titles_public)  # keep bootstrap
            for cid, title in public_result.items():
                if merged_public.get(cid) != title:
                    added += 1
                merged_public[cid] = title
            _titles_public = merged_public

        if isinstance(pro_result, dict) and pro_result:
            merged_pro: Dict[str, str] = dict(_titles_pro)
            for cid, title in pro_result.items():
                if merged_pro.get(cid) != title:
                    added += 1
                merged_pro[cid] = title
            _titles_pro = merged_pro

        _last_refresh = time.time()
        logger.info(
            "[STAC-TITLES] refresh complete -- public=%d pro=%d (added/changed=%d)",
            len(_titles_public),
            len(_titles_pro),
            added,
        )
        return (added, cache_size())


async def _noop() -> Dict[str, str]:
    return {}


async def _background_refresher() -> None:
    """Run :func:`refresh_now` once per ``_TTL_SECONDS`` for the
    lifetime of the process."""
    while True:
        try:
            await refresh_now(force=True)
        except Exception as exc:  # pragma: no cover - defensive
            logger.warning("[STAC-TITLES] background refresh raised: %s", exc)
        try:
            await asyncio.sleep(_TTL_SECONDS)
        except asyncio.CancelledError:
            return


def start_background_refresh() -> None:
    """Idempotent: schedule the refresher on the running event loop.

    Called from FastAPI ``startup``. Does the first refresh inline-ish
    by creating a task -- the first lookup might still hit bootstrap
    titles (~few ms before the fetch returns), which is fine: by the
    time a real STAC search completes, the cache is warm.
    """
    global _background_task
    if _background_task is not None and not _background_task.done():
        return
    try:
        loop = asyncio.get_event_loop()
    except RuntimeError:
        return
    _background_task = loop.create_task(_background_refresher())
    logger.info(
        "[STAC-TITLES] background refresher scheduled (TTL=%ds, bootstrap=%d titles)",
        _TTL_SECONDS,
        cache_size(),
    )
