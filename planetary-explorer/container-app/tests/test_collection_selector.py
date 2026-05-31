"""Unit tests for :mod:`collection_selector` (Phase 2).

The selector pipeline is exercised end-to-end against a stubbed
:class:`CollectionIndex` so we never touch the network or AOAI. The
LLM stage is monkey-patched per-test: each test asserts which stage
(``exact`` | ``llm`` | ``fallback`` | ``none``) the selector took, and
that the final id is always in the live inventory.

Critical regression coverage (from MCPProobjective.md):

  * The 2026-05-23 ``"sentinel-2"`` token-collision bug:
    ``select_collection("Show Sentinel-2 SWIR fire ...", mode)`` must
    return ``sentinel-2-l2a`` (never the lookalike ``"sentinel-2"``).
  * ``COLLECTION_SELECTOR=off`` keeps ``record_shadow_decision`` dormant.
  * ``COLLECTION_SELECTOR=shadow`` runs the selector but the caller can
    still ignore the returned ``Selection``.
"""

from __future__ import annotations

import asyncio
from typing import Any, Dict, List

import pytest

import collection_index as ci_mod
import collection_selector as cs_mod
from collection_index import (
    CollectionIndex,
    reset_collection_index_for_tests,
)
from collection_selector import (
    Selection,
    record_shadow_decision,
    select_collection,
    selector_mode,
)


PUBLIC_PAYLOAD: List[Dict[str, Any]] = [
    {
        "id": "sentinel-2-l2a",
        "title": "Sentinel-2 Level-2A",
        "description": "Sentinel-2 multispectral surface reflectance including SWIR bands B11/B12.",
        "keywords": ["sentinel", "multispectral", "swir", "esa"],
        "renders": {
            "natural-color": {},
            "swir-fire": {},
            "color-infrared": {},
        },
    },
    {
        "id": "landsat-c2-l2",
        "title": "Landsat Collection 2 Level-2",
        "description": "Landsat surface reflectance.",
        "keywords": ["landsat", "usgs"],
        "renders": {"natural-color": {}},
    },
    {
        "id": "naip",
        "title": "NAIP",
        "description": "National Agriculture Imagery Program 4-band aerial imagery.",
        "keywords": ["aerial"],
    },
]

PRO_PAYLOAD: List[Dict[str, Any]] = [
    {
        "id": "sentinel-2-l2a",
        "title": "Sentinel-2 L2A (private mirror)",
        "description": "Customer mirror of public Sentinel-2 L2A.",
        "keywords": ["sentinel", "swir", "fire"],
        "renders": {"natural-color": {}, "swir-fire": {}},
    },
    {
        "id": "naipprivate",
        "title": "NAIP Private",
        "description": "Customer aerial imagery.",
        "renders": {"natural-color": {}},
    },
]


def _patch_index(monkeypatch):
    async def fake_load_public(self, session):  # noqa: ARG001
        rows = [ci_mod._to_meta(c, "public") for c in PUBLIC_PAYLOAD]
        return ([r for r in rows if r], None)

    async def fake_load_pro(self, session):  # noqa: ARG001
        rows = [ci_mod._to_meta(c, "pro") for c in PRO_PAYLOAD]
        return ([r for r in rows if r], None)

    monkeypatch.setattr(CollectionIndex, "_load_public", fake_load_public, raising=True)
    monkeypatch.setattr(CollectionIndex, "_load_pro", fake_load_pro, raising=True)
    monkeypatch.delenv("AZURE_OPENAI_EMBEDDING_DEPLOYMENT", raising=False)


@pytest.fixture(autouse=True)
def _reset():
    reset_collection_index_for_tests()
    yield
    reset_collection_index_for_tests()


# ---------------------------------------------------------------------------
# Stage A -- exact-id passthrough
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_exact_id_in_query_wins(monkeypatch):
    _patch_index(monkeypatch)
    sel = await select_collection(
        "please show me sentinel-2-l2a tiles over Napa",
        "public",
        allow_llm=False,
    )
    assert sel.stage == "exact"
    assert sel.collection_id == "sentinel-2-l2a"
    assert sel.render_preset in {"natural-color", "swir-fire", "color-infrared"}


@pytest.mark.asyncio
async def test_lookalike_token_does_not_short_circuit(monkeypatch):
    """The 2026-05-23 regression: 'sentinel-2' must fall through to Stage B."""
    _patch_index(monkeypatch)
    sel = await select_collection(
        "Show Sentinel-2 SWIR fire imagery over California on May 20, 2026",
        "public",
        allow_llm=False,
    )
    # Without LLM, Stage D picks top-1 lexical -- which is sentinel-2-l2a.
    assert sel.collection_id == "sentinel-2-l2a"
    # The stage MUST NOT be 'exact', because 'sentinel-2' is not a live id.
    assert sel.stage != "exact"
    # SWIR-fire preset comes through via the default-preset heuristic.
    assert sel.render_preset == "swir-fire"


# ---------------------------------------------------------------------------
# Stage B + D -- fallback (no LLM)
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_fallback_picks_top_lexical_candidate(monkeypatch):
    _patch_index(monkeypatch)
    sel = await select_collection(
        "I need landsat surface reflectance",
        "public",
        allow_llm=False,
    )
    assert sel.collection_id == "landsat-c2-l2"
    assert sel.stage == "fallback"


@pytest.mark.asyncio
async def test_no_candidates_returns_none(monkeypatch):
    _patch_index(monkeypatch)
    sel = await select_collection(
        "completely irrelevant gibberish xyzpqr",
        "public",
        allow_llm=False,
    )
    assert sel.collection_id is None
    assert sel.stage == "none"


@pytest.mark.asyncio
async def test_pro_mode_uses_pro_inventory_only(monkeypatch):
    _patch_index(monkeypatch)
    sel = await select_collection(
        "show NAIP private aerial imagery",
        "pro",
        allow_llm=False,
    )
    # naipprivate exists only in Pro inventory -- token won't exact-match
    # because the query uses a space, but Stage B retrieves it.
    assert sel.collection_id == "naipprivate"


@pytest.mark.asyncio
async def test_pro_exact_id_token(monkeypatch):
    _patch_index(monkeypatch)
    sel = await select_collection(
        "tile naipprivate over Sonoma",
        "pro",
        allow_llm=False,
    )
    assert sel.stage == "exact"
    assert sel.collection_id == "naipprivate"


# ---------------------------------------------------------------------------
# Stage C -- LLM pick (mocked)
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_llm_pick_overrides_lexical_top1(monkeypatch):
    """When the LLM picks a different (but valid) candidate, selector honors it."""
    _patch_index(monkeypatch)

    async def fake_llm_pick(query, mode, cands):
        # Pretend the LLM preferred landsat over sentinel for this query.
        return {
            "collection_id": "landsat-c2-l2",
            "render_preset": "natural-color",
            "rationale": "user mentioned landsat",
        }

    monkeypatch.setattr(cs_mod, "_llm_pick", fake_llm_pick, raising=True)
    sel = await select_collection(
        "swir fire scene from landsat or sentinel",
        "public",
        allow_llm=True,
    )
    assert sel.stage == "llm"
    assert sel.collection_id == "landsat-c2-l2"
    assert sel.render_preset == "natural-color"
    assert "landsat" in sel.rationale


@pytest.mark.asyncio
async def test_llm_hallucinated_id_is_rejected(monkeypatch):
    """Stage D guard: LLM returning an id not in candidates falls back to top-1."""
    _patch_index(monkeypatch)

    async def fake_llm_pick(query, mode, cands):
        return {
            "collection_id": "completely-fake-id",
            "render_preset": "natural-color",
            "rationale": "hallucination",
        }

    monkeypatch.setattr(cs_mod, "_llm_pick", fake_llm_pick, raising=True)
    sel = await select_collection(
        "sentinel SWIR fire california",
        "public",
        allow_llm=True,
    )
    assert sel.stage == "fallback"
    # Top-1 lexical hit for this query is sentinel-2-l2a.
    assert sel.collection_id == "sentinel-2-l2a"


@pytest.mark.asyncio
async def test_llm_invalid_preset_is_rewritten(monkeypatch):
    _patch_index(monkeypatch)

    async def fake_llm_pick(query, mode, cands):
        return {
            "collection_id": "sentinel-2-l2a",
            "render_preset": "not-a-real-preset",
            "rationale": "test",
        }

    monkeypatch.setattr(cs_mod, "_llm_pick", fake_llm_pick, raising=True)
    sel = await select_collection(
        "swir fire california sentinel",
        "public",
        allow_llm=True,
    )
    assert sel.collection_id == "sentinel-2-l2a"
    assert sel.render_preset in {"swir-fire", "natural-color", "color-infrared"}
    assert sel.render_preset != "not-a-real-preset"


# ---------------------------------------------------------------------------
# Shadow-mode recorder
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_record_shadow_decision_off_returns_none(monkeypatch):
    _patch_index(monkeypatch)
    monkeypatch.delenv("COLLECTION_SELECTOR", raising=False)
    out = await record_shadow_decision(
        "sentinel swir fire",
        "public",
        ["sentinel-2-l2a"],
    )
    assert out is None
    assert selector_mode() == "off"


@pytest.mark.asyncio
async def test_record_shadow_decision_shadow_runs_and_logs(monkeypatch):
    _patch_index(monkeypatch)
    monkeypatch.setenv("COLLECTION_SELECTOR", "shadow")
    logged: List[Dict[str, Any]] = []

    def fake_log(session_id, step, stage, data, elapsed_ms=None):
        logged.append({"step": step, "stage": stage, "data": data})

    out = await record_shadow_decision(
        "Show Sentinel-2 SWIR fire over California on May 20 2026",
        "public",
        ["sentinel-2"],  # the bad v1 pick
        log_fn=fake_log,
        session_id="t-session",
    )
    assert isinstance(out, Selection)
    assert out.collection_id == "sentinel-2-l2a"
    assert logged and logged[0]["step"] == "COLLECTION_SELECTOR"
    assert logged[0]["stage"] == "SHADOW"
    # The shadow log includes both v1 and v2 picks so a human can diff.
    payload = logged[0]["data"]
    assert payload["v1"] == ["sentinel-2"]
    assert payload["v2"]["collection_id"] == "sentinel-2-l2a"
    assert payload["diff"] != "match"


@pytest.mark.asyncio
async def test_record_shadow_decision_v2_flag_returns_authoritative_pick(monkeypatch):
    _patch_index(monkeypatch)
    monkeypatch.setenv("COLLECTION_SELECTOR", "v2")
    out = await record_shadow_decision(
        "Show Sentinel-2 SWIR over California",
        "public",
        ["sentinel-2"],
    )
    assert isinstance(out, Selection)
    assert out.collection_id == "sentinel-2-l2a"
    assert selector_mode() == "v2"


# ---------------------------------------------------------------------------
# Phase 3 -- confidence + disambiguation
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_disambiguation_off_by_default(monkeypatch):
    """Without disambiguate=True (and env unset), selector keeps old behavior."""
    _patch_index(monkeypatch)
    monkeypatch.delenv("COLLECTION_SELECTOR_DISAMBIGUATE", raising=False)
    sel = await select_collection(
        "imagery",  # intentionally vague, low confidence
        "public",
        allow_llm=False,
    )
    assert sel.stage in {"fallback", "none"}
    assert sel.needs_confirmation is False
    assert sel.alternatives == ()


@pytest.mark.asyncio
async def test_disambiguation_fires_when_top_score_below_floor(monkeypatch):
    _patch_index(monkeypatch)
    # Force floor high enough that the vague-query lexical hit is below it.
    monkeypatch.setenv("COLLECTION_SELECTOR_CONFIDENCE_THRESHOLD", "0.99")
    sel = await select_collection(
        "imagery surface",
        "public",
        allow_llm=False,
        disambiguate=True,
    )
    assert sel.stage == "disambiguate"
    assert sel.needs_confirmation is True
    assert sel.collection_id is not None  # tentative top-1 still surfaced
    assert 1 <= len(sel.alternatives) <= 3
    ids = [a.collection_id for a in sel.alternatives]
    # Every alternative is a live id in the public inventory.
    assert all(i in {"sentinel-2-l2a", "landsat-c2-l2", "naip"} for i in ids)
    # Confidence reflects the actual top-1 score, not the floor.
    assert 0.0 <= sel.confidence < 0.99


@pytest.mark.asyncio
async def test_disambiguation_fires_on_tie(monkeypatch):
    _patch_index(monkeypatch)
    # Keep floor low so confidence test passes, but force a very tight tie threshold.
    monkeypatch.setenv("COLLECTION_SELECTOR_CONFIDENCE_THRESHOLD", "0.0")
    monkeypatch.setenv("COLLECTION_SELECTOR_TIE_THRESHOLD", "10.0")
    sel = await select_collection(
        "imagery surface",
        "public",
        allow_llm=False,
        disambiguate=True,
    )
    assert sel.stage == "disambiguate"
    assert "tie" in sel.reason
    assert len(sel.alternatives) >= 2


@pytest.mark.asyncio
async def test_disambiguation_skipped_for_exact_id(monkeypatch):
    """Stage A still wins instantly; user shouldn't be asked to confirm an exact id."""
    _patch_index(monkeypatch)
    monkeypatch.setenv("COLLECTION_SELECTOR_CONFIDENCE_THRESHOLD", "0.99")
    sel = await select_collection(
        "please show sentinel-2-l2a tiles",
        "public",
        allow_llm=False,
        disambiguate=True,
    )
    assert sel.stage == "exact"
    assert sel.collection_id == "sentinel-2-l2a"
    assert sel.needs_confirmation is False


@pytest.mark.asyncio
async def test_disambiguation_env_flag_enables_globally(monkeypatch):
    _patch_index(monkeypatch)
    monkeypatch.setenv("COLLECTION_SELECTOR_DISAMBIGUATE", "1")
    monkeypatch.setenv("COLLECTION_SELECTOR_CONFIDENCE_THRESHOLD", "0.99")
    sel = await select_collection(
        "imagery surface",
        "public",
        allow_llm=False,
        # Note: no disambiguate= kwarg; env flag should be picked up.
    )
    assert sel.stage == "disambiguate"
    assert sel.needs_confirmation is True


@pytest.mark.asyncio
async def test_selection_to_log_includes_phase3_fields(monkeypatch):
    _patch_index(monkeypatch)
    monkeypatch.setenv("COLLECTION_SELECTOR_CONFIDENCE_THRESHOLD", "0.99")
    sel = await select_collection(
        "imagery surface",
        "public",
        allow_llm=False,
        disambiguate=True,
    )
    payload = sel.to_log()
    assert "confidence" in payload
    assert "needs_confirmation" in payload
    assert "alternatives" in payload
    assert payload["needs_confirmation"] is True
    assert all("collection_id" in a and "title" in a for a in payload["alternatives"])
