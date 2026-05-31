"""Tests for the Phase 3 symmetric render helper.

Covers:
  * ``read_renders`` returns a config for a named preset on a collection.
  * ``read_renders`` returns None for unknown presets / missing renders.
  * ``HybridRenderingSystem.get_render_config(..., explicit_preset=...)``
    short-circuits the heuristic stack (Source -1) and produces the
    same config in Public and Pro modes when both catalogs publish the
    same preset name.
"""

from __future__ import annotations

from typing import Any, Dict, Optional

import pytest

import hybrid_rendering_system as hrs
from hybrid_rendering_system import HybridRenderingSystem, read_renders


PUBLIC_S2 = {
    "id": "sentinel-2-l2a",
    "renders": {
        "natural-color": {
            "assets": ["B04", "B03", "B02"],
            "color_formula": "Gamma RGB 2.7 Saturation 1.5",
        },
        "swir-fire": {
            "assets": ["B12", "B8A", "B04"],
            "color_formula": "Gamma RGB 2.7 Saturation 1.4",
        },
    },
}

PRO_S2 = {
    "id": "sentinel-2-l2a",
    "renders": {
        "natural-color": {
            "assets": ["B04", "B03", "B02"],
            "color_formula": "Gamma RGB 2.7 Saturation 1.5",
        },
        "swir-fire": {
            "assets": ["B12", "B8A", "B04"],
            "color_formula": "Gamma RGB 2.7 Saturation 1.4",
        },
    },
}


def _patch_catalog(monkeypatch, public=PUBLIC_S2, pro=PRO_S2):
    """Stub the per-mode catalog fetchers + clear the renders cache."""

    def fake_pub(collection_id: str) -> Optional[Dict[str, Any]]:
        return public if public and public.get("id") == collection_id else None

    def fake_pro(collection_id: str) -> Optional[Dict[str, Any]]:
        return pro if pro and pro.get("id") == collection_id else None

    monkeypatch.setattr(hrs, "_fetch_pub_doc", fake_pub, raising=True)
    monkeypatch.setattr(hrs, "_fetch_pro_doc", fake_pro, raising=True)
    hrs._STAC_RENDERS_CACHE.clear()


def test_read_renders_returns_named_preset(monkeypatch):
    _patch_catalog(monkeypatch)
    cfg = read_renders("sentinel-2-l2a", "swir-fire", is_pro=False)
    assert cfg is not None
    assert cfg.assets == ["B12", "B8A", "B04"]
    assert "v2-explicit-preset" in (cfg.notes or "")


def test_read_renders_pro_mode_uses_private_catalog(monkeypatch):
    """When is_pro=True the helper reads the Pro renders block."""
    pro_only = {
        "id": "sentinel-2-l2a",
        "renders": {"swir-fire": {"assets": ["X12", "X8A", "X04"]}},
    }
    _patch_catalog(monkeypatch, public=PUBLIC_S2, pro=pro_only)
    cfg = read_renders("sentinel-2-l2a", "swir-fire", is_pro=True)
    assert cfg is not None
    assert cfg.assets == ["X12", "X8A", "X04"]


def test_read_renders_unknown_preset_returns_none(monkeypatch):
    _patch_catalog(monkeypatch)
    assert read_renders("sentinel-2-l2a", "not-a-preset", is_pro=False) is None


def test_read_renders_empty_preset_name_returns_none(monkeypatch):
    _patch_catalog(monkeypatch)
    assert read_renders("sentinel-2-l2a", None, is_pro=False) is None
    assert read_renders("sentinel-2-l2a", "", is_pro=False) is None


def test_read_renders_missing_collection_returns_none(monkeypatch):
    _patch_catalog(monkeypatch, public=None, pro=None)
    assert read_renders("does-not-exist", "swir-fire", is_pro=False) is None


def test_get_render_config_honors_explicit_preset(monkeypatch):
    """SOURCE -1 wins over EXPLICIT_RENDER_CONFIGS and intent matching."""
    _patch_catalog(monkeypatch)
    cfg = HybridRenderingSystem.get_render_config(
        "sentinel-2-l2a",
        query_context="natural color over Napa",  # would normally pick natural-color
        is_pro=False,
        explicit_preset="swir-fire",  # selector said swir-fire -- this must win
    )
    assert cfg is not None
    assert cfg.assets == ["B12", "B8A", "B04"]


def test_get_render_config_explicit_preset_symmetric_pro_public(monkeypatch):
    """Same preset name + same renders block ⇒ same config in both modes."""
    _patch_catalog(monkeypatch)
    pub_cfg = HybridRenderingSystem.get_render_config(
        "sentinel-2-l2a", is_pro=False, explicit_preset="swir-fire",
    )
    pro_cfg = HybridRenderingSystem.get_render_config(
        "sentinel-2-l2a", is_pro=True, explicit_preset="swir-fire",
    )
    assert pub_cfg is not None and pro_cfg is not None
    assert pub_cfg.assets == pro_cfg.assets
    assert pub_cfg.color_formula == pro_cfg.color_formula


def test_get_render_config_falls_through_when_preset_missing(monkeypatch):
    """If the explicit preset isn't on the renders block, fall through to legacy tiers."""
    only_natural = {
        "id": "sentinel-2-l2a",
        "renders": {"natural-color": {"assets": ["B04", "B03", "B02"]}},
    }
    _patch_catalog(monkeypatch, public=only_natural, pro=only_natural)
    cfg = HybridRenderingSystem.get_render_config(
        "sentinel-2-l2a",
        query_context="natural color",
        is_pro=False,
        explicit_preset="swir-fire",  # not in this renders block
    )
    # Falls through to whatever the legacy stack returns -- importantly,
    # it does NOT raise. EXPLICIT_RENDER_CONFIGS or pc_rendering_config
    # may still return a config; we only assert non-explosion + that the
    # returned config (if any) lacks the v2-explicit marker.
    if cfg is not None:
        assert "v2-explicit-preset" not in (cfg.notes or "")
