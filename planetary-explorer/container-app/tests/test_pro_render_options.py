"""Tests for the GeoCatalog render-option helpers in :mod:`fastapi_app`.

These cover the MCP-driven path used by ``/api/pro/tilejson``:

  - ``_select_pro_render_option``: pick by name/id, or first entry.
  - ``_parse_pro_render_option``: split the stored ``options`` query
    string into ``(assets, asset_bidx, rescale, color_formula, extras)``.

The proxy prefers these over heuristic ``_infer_pro_render_defaults``,
so any new MPC Pro collection gets correct rendering as long as it has
render-options configured via the MCP ``configure_personal_collection
_render_options`` tool. No backend code change required.
"""

from __future__ import annotations

from fastapi_app import (
    _parse_pro_render_option,
    _select_pro_render_option,
)


# ---------- _select_pro_render_option ----------

def test_select_returns_none_for_empty_list():
    assert _select_pro_render_option([], None) is None
    assert _select_pro_render_option([], "Natural Color") is None


def test_select_returns_first_when_no_name_requested():
    opts = [{"name": "Natural Color", "options": "assets=visual"},
            {"name": "False Color", "options": "assets=B08"}]
    assert _select_pro_render_option(opts, None)["name"] == "Natural Color"


def test_select_matches_name_case_insensitive():
    opts = [{"name": "Natural Color", "options": "assets=visual"},
            {"name": "False Color", "options": "assets=B08"}]
    assert _select_pro_render_option(opts, "false color")["name"] == "False Color"
    assert _select_pro_render_option(opts, "  False Color  ")["name"] == "False Color"


def test_select_matches_id_when_name_missing():
    opts = [{"id": "ndvi", "options": "expression=(B08-B04)/(B08+B04)"}]
    assert _select_pro_render_option(opts, "NDVI")["id"] == "ndvi"


def test_select_falls_back_to_first_when_name_not_found():
    opts = [{"name": "Natural Color", "options": "assets=visual"},
            {"name": "False Color", "options": "assets=B08"}]
    assert _select_pro_render_option(opts, "SWIR")["name"] == "Natural Color"


# ---------- _parse_pro_render_option ----------

def test_parse_s2_natural_color():
    opt = {
        "name": "Natural Color",
        "options": (
            "assets=B04&assets=B03&assets=B02"
            "&color_formula=gamma+RGB+2.7,+saturation+1.5"
            "&rescale=0,3000"
        ),
    }
    assets, bidx, rescale, color, extras = _parse_pro_render_option(opt)
    assert assets == ["B04", "B03", "B02"]
    assert bidx == []
    assert rescale == "0,3000"
    assert color == "gamma+RGB+2.7,+saturation+1.5"
    assert extras == []


def test_parse_sentinel2_fire_swir():
    # The collection at issue: 3 single-band assets, no B04/B03/B02.
    # Heuristic inference would fall through to ``["B11"]`` with bogus
    # bidx -- the MCP-stored option is the source of truth.
    opt = {
        "name": "SWIR Fire",
        "options": "assets=B12&assets=B11&assets=B8A&rescale=0,4000",
    }
    assets, bidx, rescale, color, extras = _parse_pro_render_option(opt)
    assert assets == ["B12", "B11", "B8A"]
    assert bidx == []  # critical: no asset_bidx -> avoids titiler 424
    assert rescale == "0,4000"
    assert color is None
    assert extras == []


def test_parse_naip_with_bidx():
    opt = {
        "name": "RGB",
        "options": "assets=image&asset_bidx=image|1,2,3",
    }
    assets, bidx, rescale, color, extras = _parse_pro_render_option(opt)
    assert assets == ["image"]
    assert bidx == ["image|1,2,3"]
    assert rescale is None
    assert color is None
    assert extras == []


def test_parse_passes_through_colormap_and_expression():
    opt = {
        "name": "NDVI",
        "options": (
            "expression=(B08-B04)/(B08%2BB04)"
            "&rescale=-1,1"
            "&colormap_name=rdylgn"
            "&nodata=0"
        ),
    }
    assets, bidx, rescale, color, extras = _parse_pro_render_option(opt)
    assert assets == []
    assert bidx == []
    assert rescale == "-1,1"
    assert color is None
    # Extras are kept URL-encoded so they round-trip into the tile URL
    # without a second encoding pass mangling reserved characters.
    assert "expression=(B08-B04)/(B08%2BB04)" in extras
    assert "colormap_name=rdylgn" in extras
    assert "nodata=0" in extras


def test_parse_empty_options_string():
    opt = {"name": "Empty", "options": ""}
    assets, bidx, rescale, color, extras = _parse_pro_render_option(opt)
    assert assets == []
    assert bidx == []
    assert rescale is None
    assert color is None
    assert extras == []


def test_parse_missing_options_key():
    # Defensive: malformed entry shouldn't crash the proxy.
    assets, bidx, rescale, color, extras = _parse_pro_render_option({"name": "x"})
    assert assets == []
    assert bidx == []
    assert rescale is None
    assert color is None
    assert extras == []
