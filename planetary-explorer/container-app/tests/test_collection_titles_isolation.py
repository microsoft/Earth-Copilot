"""Unit tests for mode-isolated collection title cache.

Public and Pro STAC catalogs sometimes publish the SAME collection id
(e.g. ``sentinel-2-l2a``) with different titles -- Pro operators often
append a suffix at ingest time (``"Sentinel-2 Level-2A (Private mirror)"``).
Earlier versions stored both sources in one dict, which let Pro titles
leak into Public-mode chat responses. These tests pin the isolated
behavior.
"""

from __future__ import annotations

import importlib

import pytest


@pytest.fixture
def titles_module():
    """Fresh import so module-level dicts start at known state."""
    import sys
    sys.modules.pop("collection_titles", None)
    mod = importlib.import_module("collection_titles")
    yield mod
    sys.modules.pop("collection_titles", None)


def _seed(mod, public, pro):
    mod._titles_public = dict(public)
    mod._titles_pro = dict(pro)


def test_public_lookup_only_sees_public_cache(titles_module):
    _seed(
        titles_module,
        public={"sentinel-2-l2a": "Sentinel-2 Level-2A"},
        pro={"sentinel-2-l2a": "Sentinel-2 Level-2A (Private mirror)"},
    )
    assert (
        titles_module.get_title("sentinel-2-l2a", "public")
        == "Sentinel-2 Level-2A"
    )


def test_pro_lookup_for_shared_id_prefers_public_title(titles_module):
    """Pro lookups of a collection that ALSO exists in Public should
    render the Public title -- shared ids = same dataset = same label,
    regardless of Pro-side ingest-time decorations."""
    _seed(
        titles_module,
        public={"sentinel-2-l2a": "Sentinel-2 Level-2A"},
        pro={"sentinel-2-l2a": "Sentinel-2 Level-2A (Private mirror)"},
    )
    assert (
        titles_module.get_title("sentinel-2-l2a", "pro")
        == "Sentinel-2 Level-2A"
    )


def test_pro_only_collection_uses_pro_title(titles_module):
    """A Pro-only id (no Public counterpart) falls through to the Pro
    cache as-is."""
    _seed(
        titles_module,
        public={"sentinel-2-l2a": "Sentinel-2 Level-2A"},
        pro={"naipprivate": "NAIP (Private)"},
    )
    assert titles_module.get_title("naipprivate", "pro") == "NAIP (Private)"


def test_pro_only_id_invisible_to_public_lookup(titles_module):
    _seed(
        titles_module,
        public={"sentinel-2-l2a": "Sentinel-2 Level-2A"},
        pro={"naipprivate": "NAIP (Private)"},
    )
    # No public entry -> returns raw id, not Pro title.
    assert titles_module.get_title("naipprivate", "public") == "naipprivate"


def test_unknown_id_returns_raw_id(titles_module):
    _seed(titles_module, public={}, pro={})
    assert titles_module.get_title("does-not-exist", "public") == "does-not-exist"
    assert titles_module.get_title("does-not-exist", "pro") == "does-not-exist"


def test_empty_id_returns_satellite_imagery(titles_module):
    assert titles_module.get_title(None, "public") == "satellite imagery"
    assert titles_module.get_title("", "pro") == "satellite imagery"


def test_invalid_mode_defaults_to_public(titles_module):
    _seed(
        titles_module,
        public={"sentinel-2-l2a": "Sentinel-2 Level-2A"},
        pro={"sentinel-2-l2a": "Sentinel-2 Level-2A (Private mirror)"},
    )
    # Garbage mode -> public path (safer default; Pro titles never leak).
    assert (
        titles_module.get_title("sentinel-2-l2a", "garbage")
        == "Sentinel-2 Level-2A"
    )
    assert (
        titles_module.get_title("sentinel-2-l2a", None)
        == "Sentinel-2 Level-2A"
    )
