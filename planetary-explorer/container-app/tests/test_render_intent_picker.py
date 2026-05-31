"""Tests for the intent-aware STAC ``renders`` preset picker.

These cover the Step-1 fix that solves the white-tile bug for thematic
queries against multi-band optical collections (e.g. "Sentinel-2 fire
images of California" picking the SWIR preset instead of the default
true-color preset). The picker is intentionally driven only by token
matches against preset key/title/description text plus a tiny generic
synonym map — there are no hardcoded ``(collection, keyword) -> preset``
tables to maintain.
"""

from __future__ import annotations

from hybrid_rendering_system import (
    _pick_preset,
    _pick_preset_by_intent,
    _score_preset,
    _tokenize_query,
)


# A renders block shaped like Public PC ``sentinel-2-l2a`` (subset).
S2_RENDERS = {
    "natural-color": {
        "title": "Natural color",
        "description": "True-color RGB composite using bands B04, B03, B02.",
        "assets": ["B04", "B03", "B02"],
        "rescale": [[0, 4000], [0, 4000], [0, 4000]],
    },
    "swir": {
        "title": "False Color (SWIR / Fire & Burn Scars)",
        "description": "SWIR false-color B12/B11/B8A — highlights active fire and burn scars.",
        "assets": ["B12", "B11", "B8A"],
        "rescale": [[0, 6000], [0, 6000], [0, 4000]],
    },
    "ndvi": {
        "title": "Normalized Difference Vegetation Index",
        "description": "Vegetation greenness index from NIR and Red bands.",
        "assets": ["B08", "B04"],
        "expression": "(B08-B04)/(B08+B04)",
    },
    "agriculture": {
        "title": "Agriculture",
        "description": "Vegetation health composite using B11, B08, B02.",
        "assets": ["B11", "B08", "B02"],
    },
}


def test_fire_query_picks_swir_preset():
    key, preset, matched = _pick_preset_by_intent(S2_RENDERS, "Show Sentinel-2 fire images of California")
    assert key == "swir", f"expected swir preset for fire query, got {key!r}"
    assert preset["assets"] == ["B12", "B11", "B8A"]
    assert matched is True


def test_burn_scar_query_picks_swir_preset():
    key, _, matched = _pick_preset_by_intent(S2_RENDERS, "burned area Paradise CA")
    assert key == "swir"
    assert matched is True


def test_vegetation_query_picks_ndvi_or_agriculture():
    key, _, matched = _pick_preset_by_intent(S2_RENDERS, "vegetation index over the Amazon")
    # Both ndvi and agriculture match; ndvi scores higher on key+title.
    assert key in {"ndvi", "agriculture"}
    assert matched is True


def test_empty_query_falls_back_to_default_or_first():
    # No "default" key in this fixture -> first dict-valued key wins.
    key, _, matched = _pick_preset_by_intent(S2_RENDERS, "")
    assert key == "natural-color"
    assert matched is False


def test_none_query_falls_back_to_default_or_first():
    key, _, matched = _pick_preset_by_intent(S2_RENDERS, None)
    assert key == "natural-color"
    assert matched is False


def test_default_key_wins_when_present_and_no_signal():
    renders = {
        "default": {"title": "Default", "assets": ["visual"]},
        "swir": {"title": "SWIR", "assets": ["B12", "B11", "B8A"]},
    }
    key, _, matched = _pick_preset_by_intent(renders, "satellite data")
    assert key == "default"
    assert matched is False


def test_query_with_no_intent_signal_falls_back():
    # No preset has tokens matching "elevation"; tier-3 returns default-or-first.
    key, _, matched = _pick_preset_by_intent(S2_RENDERS, "elevation contours")
    assert key == "natural-color"
    assert matched is False


def test_pick_preset_legacy_default_or_first():
    # Backward-compat path used by callers that don't pass a query.
    key, _ = _pick_preset(S2_RENDERS)
    assert key == "natural-color"


def test_tokenizer_strips_stopwords_and_expands_synonyms():
    toks = _tokenize_query("Show me the fire images of California")
    assert "fire" in toks
    assert "swir" in toks  # synonym expansion
    assert "burn" in toks  # synonym expansion
    assert "show" not in toks  # stopword
    assert "the" not in toks


def test_score_weights_key_above_title_above_description():
    preset = {"title": "fire", "description": "fire fire fire"}
    # Key contains "fire" -> 3, title contains "fire" -> 2, desc has 3 "fire" -> 3.
    # _score_preset uses substring containment (not count) so desc adds only 1.
    s = _score_preset("fire-preset", preset, ["fire"])
    assert s == 3 + 2 + 1


def test_empty_renders_returns_none():
    key, preset, matched = _pick_preset_by_intent({}, "fire")
    assert key is None and preset is None
    assert matched is False
