"""Live, cached, embedding-aware inventory of STAC collections.

This module is **Phase 1** of the dynamic-collection-discovery rollout
documented in ``documentation/MCPProobjective.md``. It exposes a single
``CollectionIndex`` singleton that knows what collections actually exist
on the configured public Planetary Computer catalog and (optionally) the
configured MPC Pro / GeoCatalog instance.

The selector that consumes this index (``select_collection``) lives in
``collection_selector.py`` and is wired in behind the
``COLLECTION_SELECTOR=v2`` feature flag. Phase 1 does **not** change any
existing routing behavior -- it only stands up the inventory + lookup
primitives and a ``/api/_debug/collection-index`` endpoint so we can
prove the data is correct before flipping the flag.

Design summary (from MCPProobjective.md):

  * Source A: ``GET {public_stac}/collections``  (anonymous)
  * Source B: ``GET {pro_stac}/collections``     (AAD, via pro_stac_client)
  * TTL: ``COLLECTION_INDEX_TTL_SECONDS`` (default 900s = 15 min)
  * Per-collection cached fields:
      id, title, description, keywords, renders, extent, source,
      embedding (optional)
  * API:
      lookup_exact(token, mode)  -> id | None  (live-inventory check, no regex)
      search(query, mode, k=8)   -> [Candidate]  (semantic or lexical)
      get(id, mode)              -> CollectionMeta | None
      snapshot(mode)             -> list[CollectionMeta]

Embeddings are **opt-in**: if ``AZURE_OPENAI_EMBEDDING_DEPLOYMENT`` is
unset (or the call fails), ``search()`` falls back to a deterministic
lexical scorer (tokenized Jaccard + keyword/id overlap) so the index
remains useful in unit tests and offline dev. The selector treats both
paths identically -- it just consumes ranked candidates.

This module **never** consults a hardcoded keyword table or regex.
The only string-matching it does is against the live inventory.
"""

from __future__ import annotations

import asyncio
import logging
import math
import os
import re
import time
from dataclasses import dataclass, field
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

import aiohttp

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Public types
# ---------------------------------------------------------------------------

Mode = str  # Literal["public", "pro"]; kept as str for py3.7 compatibility.

_VALID_MODES = ("public", "pro")


@dataclass(frozen=True)
class CollectionMeta:
    """Snapshot of one STAC collection as the selector sees it.

    Frozen so it can be safely shared across coroutines and stored in
    the immutable per-mode snapshot dicts. ``embedding`` is ``None``
    when embedding mode is disabled or the call failed for this row.
    """

    id: str
    title: str
    description: str
    keywords: Tuple[str, ...]
    render_presets: Tuple[str, ...]
    source: Mode  # "public" or "pro"
    raw: Dict[str, Any] = field(default_factory=dict, repr=False)
    embedding: Optional[Tuple[float, ...]] = field(default=None, repr=False)

    def short(self) -> Dict[str, Any]:
        """JSON-safe summary suitable for the debug endpoint and logs."""
        return {
            "id": self.id,
            "title": self.title,
            "description": (self.description or "")[:240],
            "keywords": list(self.keywords),
            "render_presets": list(self.render_presets),
            "source": self.source,
            "has_embedding": self.embedding is not None,
        }


@dataclass
class Candidate:
    """One ranked result from ``CollectionIndex.search``."""

    meta: CollectionMeta
    score: float
    method: str  # "semantic" | "lexical"


# ---------------------------------------------------------------------------
# Tokenization (the only string-matching done here; live-data only)
# ---------------------------------------------------------------------------

_TOKEN_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]*")


def _tokenize(text: str) -> List[str]:
    if not text:
        return []
    return [t.lower() for t in _TOKEN_RE.findall(text)]


def _token_set(text: str) -> set[str]:
    return {t for t in _tokenize(text) if len(t) > 1}


# ---------------------------------------------------------------------------
# Snapshot (immutable per-refresh data)
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class _Snapshot:
    refreshed_at: float
    by_mode: Dict[Mode, Tuple[CollectionMeta, ...]]
    by_id: Dict[Mode, Dict[str, CollectionMeta]]
    errors: Dict[Mode, Optional[str]]

    @classmethod
    def empty(cls) -> "_Snapshot":
        return cls(
            refreshed_at=0.0,
            by_mode={m: tuple() for m in _VALID_MODES},
            by_id={m: {} for m in _VALID_MODES},
            errors={m: "not refreshed yet" for m in _VALID_MODES},
        )

    def is_fresh(self, ttl: float) -> bool:
        return self.refreshed_at > 0 and (time.time() - self.refreshed_at) < ttl


# ---------------------------------------------------------------------------
# Helpers to normalize STAC collection payloads
# ---------------------------------------------------------------------------

def _extract_render_presets(col: Dict[str, Any]) -> Tuple[str, ...]:
    """Extract the keys of the ``renders`` block on a STAC collection.

    MPC public puts the block at ``renders``. Older MPC public and some
    Pro collections put it at ``msft:render_options`` (legacy). We honor
    both. Returns an empty tuple when neither is present.
    """
    for key in ("renders", "msft:render_options"):
        block = col.get(key)
        if isinstance(block, dict) and block:
            return tuple(sorted(block.keys()))
    return tuple()


def _extract_keywords(col: Dict[str, Any]) -> Tuple[str, ...]:
    """Collect free-form keywords from common STAC locations.

    STAC 1.0 puts collection-level keywords at ``keywords`` (root) and
    sometimes inside ``summaries`` for band names etc. We union both so
    semantic-fallback retrieval has more signal.
    """
    out: List[str] = []
    kw = col.get("keywords")
    if isinstance(kw, list):
        out.extend([str(k) for k in kw if k])
    summaries = col.get("summaries")
    if isinstance(summaries, dict):
        for v in summaries.values():
            if isinstance(v, list):
                # Only include short scalar tokens (band names, classes), not
                # nested dicts/numbers, which add noise to lexical matching.
                out.extend([str(x) for x in v if isinstance(x, (str, int)) and str(x).strip()])
    # De-dup, lowercase, cap length to avoid blowing the embedding input.
    seen: set[str] = set()
    dedup: List[str] = []
    for k in out:
        s = str(k).strip().lower()
        if s and s not in seen:
            seen.add(s)
            dedup.append(s)
        if len(dedup) >= 64:
            break
    return tuple(dedup)


def _to_meta(col: Dict[str, Any], source: Mode) -> Optional[CollectionMeta]:
    cid = col.get("id")
    if not isinstance(cid, str) or not cid.strip():
        return None
    return CollectionMeta(
        id=cid.strip(),
        title=str(col.get("title") or cid).strip(),
        description=str(col.get("description") or "").strip(),
        keywords=_extract_keywords(col),
        render_presets=_extract_render_presets(col),
        source=source,
        raw=col,
        embedding=None,
    )


# ---------------------------------------------------------------------------
# Embedding helpers (opt-in, gated on env)
# ---------------------------------------------------------------------------

def _embedding_deployment() -> Optional[str]:
    """Return the AOAI embedding deployment name, or None to disable embeddings."""
    name = (os.getenv("AZURE_OPENAI_EMBEDDING_DEPLOYMENT") or "").strip()
    return name or None


def _build_embed_text(m: CollectionMeta) -> str:
    """Construct the text passed to the embedding model.

    Order matters for cosine: id and title carry the most signal, then a
    truncated description, then the keyword bag. We cap total length to
    keep token cost bounded across ~100 collections.
    """
    parts = [m.id, m.title]
    if m.description:
        parts.append(m.description[:600])
    if m.keywords:
        parts.append("keywords: " + ", ".join(m.keywords[:32]))
    if m.render_presets:
        parts.append("renders: " + ", ".join(m.render_presets))
    return "\n".join(parts)


async def _embed_texts(texts: Sequence[str]) -> List[Optional[List[float]]]:
    """Embed a batch of texts via Azure OpenAI. Returns ``None`` per item on failure.

    Embeddings are best-effort: any failure (no deployment, network error,
    rate limit) results in ``None`` for the affected rows; the selector
    then falls back to lexical scoring for those rows transparently.
    """
    deployment = _embedding_deployment()
    if not deployment or not texts:
        return [None] * len(texts)

    try:
        from openai import AsyncAzureOpenAI
    except Exception as exc:  # openai package missing in some test envs
        logger.warning("[COLLECTION-INDEX] openai SDK unavailable: %s", exc)
        return [None] * len(texts)

    endpoint = (os.getenv("AZURE_OPENAI_ENDPOINT") or "").strip()
    api_key = (os.getenv("AZURE_OPENAI_API_KEY") or "").strip()
    api_version = (os.getenv("AZURE_OPENAI_API_VERSION") or "2024-02-01").strip()
    if not endpoint:
        logger.info("[COLLECTION-INDEX] AZURE_OPENAI_ENDPOINT unset; skipping embeddings")
        return [None] * len(texts)

    client_kwargs: Dict[str, Any] = {
        "azure_endpoint": endpoint,
        "api_version": api_version,
    }
    if api_key:
        client_kwargs["api_key"] = api_key
    else:
        # Use AAD via DefaultAzureCredential when no key is configured.
        try:
            from azure.identity.aio import DefaultAzureCredential, get_bearer_token_provider
            cred = DefaultAzureCredential()
            client_kwargs["azure_ad_token_provider"] = get_bearer_token_provider(
                cred, "https://cognitiveservices.azure.com/.default"
            )
        except Exception as exc:
            logger.warning("[COLLECTION-INDEX] AOAI AAD provider unavailable: %s", exc)
            return [None] * len(texts)

    try:
        client = AsyncAzureOpenAI(**client_kwargs)
        # Single batched call; AOAI embedding endpoints accept arrays.
        resp = await client.embeddings.create(model=deployment, input=list(texts))
    except Exception as exc:
        logger.warning("[COLLECTION-INDEX] embedding call failed: %s", exc)
        return [None] * len(texts)

    out: List[Optional[List[float]]] = [None] * len(texts)
    try:
        for item in resp.data:
            idx = getattr(item, "index", None)
            vec = getattr(item, "embedding", None)
            if isinstance(idx, int) and 0 <= idx < len(out) and isinstance(vec, list):
                out[idx] = [float(x) for x in vec]
    except Exception as exc:
        logger.warning("[COLLECTION-INDEX] embedding response parse failed: %s", exc)
    return out


def _cosine(a: Sequence[float], b: Sequence[float]) -> float:
    if not a or not b or len(a) != len(b):
        return 0.0
    dot = 0.0
    na = 0.0
    nb = 0.0
    for x, y in zip(a, b):
        dot += x * y
        na += x * x
        nb += y * y
    if na <= 0 or nb <= 0:
        return 0.0
    return dot / math.sqrt(na * nb)


# ---------------------------------------------------------------------------
# Lexical fallback scorer (used when embedding is unavailable for a row)
# ---------------------------------------------------------------------------

def _lexical_score(query_tokens: set[str], m: CollectionMeta) -> float:
    """Cheap, deterministic relevance score on tokenized fields.

    Not a real BM25 -- just enough signal to rank candidates when
    embeddings are off (unit tests, dev without AOAI key, transient
    AOAI failures). Weights favor id/title hits over description/keyword
    hits because users name collections by their visible identifiers.
    """
    if not query_tokens:
        return 0.0
    id_tokens = _token_set(m.id) | _token_set(m.id.replace("-", " "))
    title_tokens = _token_set(m.title)
    desc_tokens = _token_set(m.description)
    kw_tokens = set(m.keywords) | {t for k in m.keywords for t in _tokenize(k)}

    def jacc(a: set[str], b: set[str]) -> float:
        if not a or not b:
            return 0.0
        u = a | b
        return len(a & b) / len(u) if u else 0.0

    return (
        4.0 * jacc(query_tokens, id_tokens)
        + 3.0 * jacc(query_tokens, title_tokens)
        + 1.5 * jacc(query_tokens, kw_tokens)
        + 1.0 * jacc(query_tokens, desc_tokens)
    )


# ---------------------------------------------------------------------------
# CollectionIndex
# ---------------------------------------------------------------------------

class CollectionIndex:
    """Singleton inventory of public + Pro STAC collections.

    Use :func:`get_collection_index` to obtain the shared instance. The
    singleton is lazily refreshed: first call awaits an initial load,
    subsequent calls return the cached snapshot until the TTL elapses,
    then trigger a background refresh.
    """

    def __init__(self, *, ttl_seconds: Optional[float] = None) -> None:
        self._ttl = float(
            ttl_seconds
            if ttl_seconds is not None
            else os.getenv("COLLECTION_INDEX_TTL_SECONDS") or 900.0
        )
        self._snapshot: _Snapshot = _Snapshot.empty()
        self._lock = asyncio.Lock()
        self._refresh_task: Optional[asyncio.Task] = None

    # ----- public API ------------------------------------------------------

    async def ensure_loaded(self) -> _Snapshot:
        """Block-load on first call; otherwise return the cached snapshot.

        After the cache goes stale, returns the stale snapshot immediately
        and kicks off a background refresh -- callers never block on TTL
        rollover.
        """
        snap = self._snapshot
        if snap.refreshed_at == 0.0:
            async with self._lock:
                if self._snapshot.refreshed_at == 0.0:
                    self._snapshot = await self._refresh_now()
            return self._snapshot
        if not snap.is_fresh(self._ttl):
            self._kick_background_refresh()
        return snap

    async def refresh(self) -> _Snapshot:
        """Force-refresh the snapshot synchronously. Used by tests + admin."""
        async with self._lock:
            self._snapshot = await self._refresh_now()
        return self._snapshot

    async def snapshot(self, mode: Optional[Mode] = None) -> List[CollectionMeta]:
        """Return all known collections (optionally restricted to one mode)."""
        snap = await self.ensure_loaded()
        if mode is None:
            return [m for ms in snap.by_mode.values() for m in ms]
        return list(snap.by_mode.get(mode, ()))

    async def get(self, collection_id: str, mode: Mode) -> Optional[CollectionMeta]:
        snap = await self.ensure_loaded()
        return snap.by_id.get(mode, {}).get(collection_id)

    async def lookup_exact(self, token: str, mode: Mode) -> Optional[str]:
        """Return ``token`` iff it is a real id in the live inventory for ``mode``.

        No regex, no prefix guesses, no normalization beyond case-folding.
        ``"sentinel-2"`` returns None (not a real id); ``"sentinel-2-l2a"``
        returns ``"sentinel-2-l2a"`` (real id).
        """
        if not token:
            return None
        snap = await self.ensure_loaded()
        by_id = snap.by_id.get(mode, {})
        if token in by_id:
            return token
        # Case-insensitive fallback (STAC ids are conventionally lower-case
        # but this protects against minor casing drift in user queries).
        lo = token.lower()
        for cid in by_id:
            if cid.lower() == lo:
                return cid
        return None

    async def search(
        self,
        query: str,
        mode: Mode,
        *,
        k: int = 8,
    ) -> List[Candidate]:
        """Return the top-``k`` collections ranked by relevance to ``query``.

        Uses cosine over cached embeddings when available; otherwise falls
        back to lexical Jaccard on tokenized fields. Mixed-mode (some rows
        embedded, others not) is supported: each row is scored by whichever
        method it has data for, then ranked by the resulting numeric score.
        Embedding scores and lexical scores are NOT normalized against each
        other -- if you depend on cross-row comparability, run with
        embeddings on for all rows (production) or off for all (tests).
        """
        snap = await self.ensure_loaded()
        rows = snap.by_mode.get(mode, ())
        if not rows or not query:
            return []

        # Try to embed the query when any row has an embedding to compare against.
        any_embedded = any(r.embedding is not None for r in rows)
        query_vec: Optional[List[float]] = None
        if any_embedded:
            embeds = await _embed_texts([query])
            query_vec = embeds[0] if embeds else None

        q_tokens = _token_set(query)
        results: List[Candidate] = []
        for r in rows:
            if query_vec is not None and r.embedding is not None:
                score = _cosine(query_vec, r.embedding)
                method = "semantic"
            else:
                score = _lexical_score(q_tokens, r)
                method = "lexical"
            if score > 0:
                results.append(Candidate(meta=r, score=score, method=method))

        results.sort(key=lambda c: c.score, reverse=True)
        return results[:k]

    async def health(self) -> Dict[str, Any]:
        """Return a small dict describing the current snapshot for /api/_debug."""
        snap = await self.ensure_loaded()
        return {
            "refreshed_at": snap.refreshed_at,
            "age_seconds": (time.time() - snap.refreshed_at) if snap.refreshed_at else None,
            "ttl_seconds": self._ttl,
            "counts": {m: len(snap.by_mode.get(m, ())) for m in _VALID_MODES},
            "errors": dict(snap.errors),
            "embedding_enabled": _embedding_deployment() is not None,
            "embedding_coverage": {
                m: sum(1 for c in snap.by_mode.get(m, ()) if c.embedding is not None)
                for m in _VALID_MODES
            },
        }

    # ----- internals -------------------------------------------------------

    def _kick_background_refresh(self) -> None:
        if self._refresh_task and not self._refresh_task.done():
            return
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            return
        self._refresh_task = loop.create_task(self._background_refresh())

    async def _background_refresh(self) -> None:
        try:
            async with self._lock:
                self._snapshot = await self._refresh_now()
        except Exception as exc:
            logger.warning("[COLLECTION-INDEX] background refresh failed: %s", exc)

    async def _refresh_now(self) -> _Snapshot:
        """Fetch both catalogs, normalize, embed, return a new snapshot.

        Errors per-source are isolated: a failure to reach Pro never
        breaks the public inventory, and vice versa.
        """
        t0 = time.time()
        async with aiohttp.ClientSession() as session:
            public_task = asyncio.create_task(self._load_public(session))
            pro_task = asyncio.create_task(self._load_pro(session))
            (public_rows, public_err) = await public_task
            (pro_rows, pro_err) = await pro_task

        # Embed all rows in one batched call when possible.
        all_rows = list(public_rows) + list(pro_rows)
        embeds: List[Optional[List[float]]] = []
        if all_rows and _embedding_deployment():
            try:
                embeds = await _embed_texts([_build_embed_text(r) for r in all_rows])
            except Exception as exc:
                logger.warning("[COLLECTION-INDEX] embedding batch failed: %s", exc)
                embeds = [None] * len(all_rows)
        else:
            embeds = [None] * len(all_rows)

        # Re-materialize meta records with embeddings attached (frozen dataclass).
        enriched: List[CollectionMeta] = []
        for r, vec in zip(all_rows, embeds):
            enriched.append(
                CollectionMeta(
                    id=r.id,
                    title=r.title,
                    description=r.description,
                    keywords=r.keywords,
                    render_presets=r.render_presets,
                    source=r.source,
                    raw=r.raw,
                    embedding=tuple(vec) if vec else None,
                )
            )

        by_mode: Dict[Mode, Tuple[CollectionMeta, ...]] = {m: tuple() for m in _VALID_MODES}
        by_id: Dict[Mode, Dict[str, CollectionMeta]] = {m: {} for m in _VALID_MODES}
        for r in enriched:
            by_mode[r.source] = by_mode[r.source] + (r,)
            by_id[r.source][r.id] = r

        snap = _Snapshot(
            refreshed_at=time.time(),
            by_mode=by_mode,
            by_id=by_id,
            errors={"public": public_err, "pro": pro_err},
        )
        logger.info(
            "[COLLECTION-INDEX] refreshed in %.2fs (public=%d, pro=%d, embeddings=%s)",
            time.time() - t0,
            len(by_mode["public"]),
            len(by_mode["pro"]),
            sum(1 for r in enriched if r.embedding is not None),
        )
        return snap

    async def _load_public(
        self, session: aiohttp.ClientSession
    ) -> Tuple[List[CollectionMeta], Optional[str]]:
        """Load the public STAC catalog (anonymous GET)."""
        try:
            from cloud_config import cloud_cfg
            base = cloud_cfg.stac_catalog_url.rstrip("/")
        except Exception as exc:
            return ([], f"cloud_config import failed: {exc}")
        url = f"{base}/collections"
        try:
            async with session.get(url, timeout=aiohttp.ClientTimeout(total=30.0)) as r:
                if not (200 <= r.status < 300):
                    return ([], f"GET {url} -> {r.status}")
                payload = await r.json()
        except Exception as exc:
            return ([], f"GET {url} failed: {exc}")
        cols = payload.get("collections") if isinstance(payload, dict) else None
        if not isinstance(cols, list):
            return ([], "public payload missing 'collections' list")
        out: List[CollectionMeta] = []
        for c in cols:
            if isinstance(c, dict):
                meta = _to_meta(c, "public")
                if meta:
                    out.append(meta)
        return (out, None)

    async def _load_pro(
        self, session: aiohttp.ClientSession
    ) -> Tuple[List[CollectionMeta], Optional[str]]:
        """Load the Pro catalog via the shared AAD-aware client. Empty when unconfigured."""
        try:
            from pro_stac_client import get_pro_stac_base, pro_list_collections
        except Exception as exc:
            return ([], f"pro_stac_client import failed: {exc}")
        if not get_pro_stac_base():
            return ([], None)  # Pro not configured -- not an error
        try:
            cols = await pro_list_collections(session)
        except Exception as exc:
            return ([], f"pro_list_collections failed: {exc}")
        out: List[CollectionMeta] = []
        for c in cols:
            if isinstance(c, dict):
                meta = _to_meta(c, "pro")
                if meta:
                    out.append(meta)
        return (out, None)


# ---------------------------------------------------------------------------
# Module-level singleton
# ---------------------------------------------------------------------------

_singleton_lock = asyncio.Lock()
_singleton: Optional[CollectionIndex] = None


async def get_collection_index() -> CollectionIndex:
    """Return the process-wide :class:`CollectionIndex` (lazy)."""
    global _singleton
    if _singleton is None:
        async with _singleton_lock:
            if _singleton is None:
                _singleton = CollectionIndex()
                await _singleton.ensure_loaded()
    return _singleton


def reset_collection_index_for_tests() -> None:
    """Drop the cached singleton. Tests only -- do not call from app code."""
    global _singleton
    _singleton = None


__all__ = [
    "CollectionIndex",
    "CollectionMeta",
    "Candidate",
    "get_collection_index",
    "reset_collection_index_for_tests",
]
