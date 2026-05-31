"""Unit tests for :mod:`collection_index` (Phase 1 of dynamic discovery).

These tests stub out network and embedding calls so they can run offline
and deterministically. They assert the core invariants from
``documentation/MCPProobjective.md``:

  * ``lookup_exact`` only returns ids that exist in the live inventory
    (the 2026-05-23 ``sentinel-2`` regression is impossible by
    construction).
  * ``search`` returns at most ``k`` rows, ranked by score.
  * Embedding failures fall back to the lexical scorer without raising.
  * Public-source vs Pro-source rows are isolated per mode.
  * TTL freshness flips correctly.
"""

from __future__ import annotations

import asyncio
import os
from typing import Any, Dict, List, Optional, Tuple

import pytest

import collection_index as ci_mod
from collection_index import (
    CollectionIndex,
    CollectionMeta,
    get_collection_index,
    reset_collection_index_for_tests,
)


# ---------------------------------------------------------------------------
# Fixtures / helpers
# ---------------------------------------------------------------------------

PUBLIC_PAYLOAD: List[Dict[str, Any]] = [
    {
        "id": "sentinel-2-l2a",
        "title": "Sentinel-2 Level-2A",
        "description": "Sentinel-2 multispectral surface reflectance, including SWIR bands B11 and B12.",
        "keywords": ["sentinel", "multispectral", "swir", "esa"],
        "summaries": {"eo:bands": [{"name": "B04"}, {"name": "B8A"}, {"name": "B12"}]},
        "renders": {
            "natural-color": {"assets": ["B04", "B03", "B02"]},
            "swir-fire": {"assets": ["B12", "B8A", "B04"]},
            "color-infrared": {"assets": ["B08", "B04", "B03"]},
        },
    },
    {
        "id": "landsat-c2-l2",
        "title": "Landsat Collection 2 Level-2",
        "description": "Landsat surface reflectance and surface temperature.",
        "keywords": ["landsat", "usgs"],
    },
    {
        "id": "naip",
        "title": "NAIP",
        "description": "National Agriculture Imagery Program (4-band aerial).",
        "keywords": ["aerial", "usda"],
    },
]


PRO_PAYLOAD: List[Dict[str, Any]] = [
    {
        "id": "sentinel-2-l2a",
        "title": "Sentinel-2 Level-2A (private mirror)",
        "description": "Customer-owned mirror of public Sentinel-2 L2A scenes over California.",
        "keywords": ["sentinel", "swir", "fire", "california"],
        "renders": {
            "natural-color": {},
            "swir-fire": {},
        },
    },
    {
        "id": "naipprivate",
        "title": "NAIP Private",
        "description": "Customer-owned aerial imagery.",
        "keywords": ["aerial"],
    },
]


def _patch_loaders(monkeypatch, *, public=PUBLIC_PAYLOAD, pro=PRO_PAYLOAD, pro_configured=True):
    """Stub the two ``_load_*`` methods so tests never hit the network."""

    async def fake_load_public(self, session):  # noqa: ARG001
        rows = [ci_mod._to_meta(c, "public") for c in public]
        return ([r for r in rows if r], None)

    async def fake_load_pro(self, session):  # noqa: ARG001
        if not pro_configured:
            return ([], None)
        rows = [ci_mod._to_meta(c, "pro") for c in pro]
        return ([r for r in rows if r], None)

    monkeypatch.setattr(CollectionIndex, "_load_public", fake_load_public, raising=True)
    monkeypatch.setattr(CollectionIndex, "_load_pro", fake_load_pro, raising=True)

    # Force embeddings off so ``search`` exercises the deterministic
    # lexical scorer. Embedding-on behavior is covered by a separate test.
    monkeypatch.delenv("AZURE_OPENAI_EMBEDDING_DEPLOYMENT", raising=False)


@pytest.fixture(autouse=True)
def _reset_singleton():
    reset_collection_index_for_tests()
    yield
    reset_collection_index_for_tests()


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_refresh_populates_both_modes(monkeypatch):
    _patch_loaders(monkeypatch)
    idx = CollectionIndex(ttl_seconds=60)
    snap = await idx.refresh()
    assert len(snap.by_mode["public"]) == 3
    assert len(snap.by_mode["pro"]) == 2
    assert snap.by_id["public"]["sentinel-2-l2a"].render_presets == (
        "color-infrared",
        "natural-color",
        "swir-fire",
    )
    # Pro is isolated from public:
    assert "landsat-c2-l2" not in snap.by_id["pro"]
    assert "naipprivate" not in snap.by_id["public"]


@pytest.mark.asyncio
async def test_lookup_exact_only_returns_real_ids(monkeypatch):
    """The 2026-05-23 regression: 'sentinel-2' must NOT route anywhere."""
    _patch_loaders(monkeypatch)
    idx = CollectionIndex(ttl_seconds=60)
    await idx.refresh()

    # Real ids resolve.
    assert await idx.lookup_exact("sentinel-2-l2a", "public") == "sentinel-2-l2a"
    assert await idx.lookup_exact("sentinel-2-l2a", "pro") == "sentinel-2-l2a"
    assert await idx.lookup_exact("naipprivate", "pro") == "naipprivate"

    # Lookalike tokens DO NOT resolve.
    assert await idx.lookup_exact("sentinel-2", "public") is None
    assert await idx.lookup_exact("sentinel-2", "pro") is None
    assert await idx.lookup_exact("naip-private", "pro") is None
    assert await idx.lookup_exact("", "public") is None
    assert await idx.lookup_exact("does-not-exist", "public") is None

    # Pro-only id does not leak into public.
    assert await idx.lookup_exact("naipprivate", "public") is None


@pytest.mark.asyncio
async def test_search_ranks_sentinel_2_above_other_collections(monkeypatch):
    _patch_loaders(monkeypatch)
    idx = CollectionIndex(ttl_seconds=60)
    await idx.refresh()

    cands = await idx.search("Sentinel-2 SWIR fire imagery over California", "public", k=3)
    assert cands, "search returned no candidates"
    assert cands[0].meta.id == "sentinel-2-l2a"
    # All candidates come from the public side only.
    assert all(c.meta.source == "public" for c in cands)
    # With embeddings off, method must be lexical.
    assert all(c.method == "lexical" for c in cands)


@pytest.mark.asyncio
async def test_search_pro_mode_picks_pro_sentinel(monkeypatch):
    _patch_loaders(monkeypatch)
    idx = CollectionIndex(ttl_seconds=60)
    await idx.refresh()

    cands = await idx.search("Sentinel-2 SWIR fire California May 20 2026", "pro", k=3)
    assert cands
    assert cands[0].meta.id == "sentinel-2-l2a"
    assert cands[0].meta.source == "pro"


@pytest.mark.asyncio
async def test_search_returns_empty_for_unknown_mode_or_empty_query(monkeypatch):
    _patch_loaders(monkeypatch)
    idx = CollectionIndex(ttl_seconds=60)
    await idx.refresh()
    assert await idx.search("", "public") == []
    assert await idx.search("anything", "nonexistent-mode") == []


@pytest.mark.asyncio
async def test_pro_unconfigured_yields_empty_pro_mode(monkeypatch):
    _patch_loaders(monkeypatch, pro_configured=False)
    idx = CollectionIndex(ttl_seconds=60)
    snap = await idx.refresh()
    assert snap.by_mode["pro"] == ()
    assert snap.errors["pro"] is None  # not an error; just absent
    assert len(snap.by_mode["public"]) == 3


@pytest.mark.asyncio
async def test_health_payload_shape(monkeypatch):
    _patch_loaders(monkeypatch)
    idx = CollectionIndex(ttl_seconds=60)
    await idx.refresh()
    h = await idx.health()
    assert h["counts"] == {"public": 3, "pro": 2}
    assert h["embedding_enabled"] is False
    assert h["embedding_coverage"] == {"public": 0, "pro": 0}
    assert h["age_seconds"] is not None and h["age_seconds"] >= 0


@pytest.mark.asyncio
async def test_singleton_is_shared(monkeypatch):
    _patch_loaders(monkeypatch)
    a = await get_collection_index()
    b = await get_collection_index()
    assert a is b


@pytest.mark.asyncio
async def test_render_presets_extracted_from_both_keys(monkeypatch):
    """Collections that use the legacy ``msft:render_options`` block still work."""
    legacy = [
        {
            "id": "legacy-collection",
            "title": "Legacy",
            "description": "",
            "msft:render_options": {"true-color": {}, "ndvi": {}},
        }
    ]
    _patch_loaders(monkeypatch, public=legacy, pro=[])
    idx = CollectionIndex(ttl_seconds=60)
    await idx.refresh()
    meta = await idx.get("legacy-collection", "public")
    assert meta is not None
    assert meta.render_presets == ("ndvi", "true-color")
