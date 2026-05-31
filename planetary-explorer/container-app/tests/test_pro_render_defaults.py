"""Tests for ``_infer_pro_render_defaults`` in :mod:`fastapi_app`.

The helper picks TiTiler ``assets``/``asset_bidx``/``rescale``/
``color_formula`` defaults for the ``/api/pro/tilejson`` proxy when the
caller doesn't supply them. Without this inference, every MPC Pro item
that isn't NAIP-shaped renders as white tiles (the legacy default was
``assets=image&asset_bidx=image|1,2,3``).
"""

from __future__ import annotations

from fastapi_app import _infer_pro_render_defaults, _PRO_RGB_COLOR_FORMULA


def _item(assets: dict) -> dict:
    return {"assets": assets, "bbox": [-122, 37, -121, 38]}


def test_s2_collection_with_raw_bands_returns_rgb_and_rescale():
    item = _item({"B04": {}, "B03": {}, "B02": {}, "B08": {}})
    assets, bidx, rescale, color = _infer_pro_render_defaults(
        collection_id="sentinel2-fire", item_doc=item
    )
    assert assets == ["B04", "B03", "B02"]
    # Each S2 band asset is single-band -> no asset_bidx.
    assert bidx == []
    assert rescale == "0,3000"
    assert color == _PRO_RGB_COLOR_FORMULA


def test_s2_collection_falls_back_to_visual_when_no_raw_bands():
    item = _item({"visual": {}, "thumbnail": {}})
    assets, bidx, rescale, color = _infer_pro_render_defaults(
        collection_id="sentinel-2-l2a-private", item_doc=item
    )
    assert assets == ["visual"]
    assert bidx == ["visual|1,2,3"]
    assert rescale is None
    assert color is None


def test_landsat_collection_uses_named_rgb_with_30000_rescale():
    item = _item({"red": {}, "green": {}, "blue": {}, "nir08": {}})
    assets, bidx, rescale, color = _infer_pro_render_defaults(
        collection_id="landsat-private", item_doc=item
    )
    assert assets == ["red", "green", "blue"]
    assert bidx == []
    assert rescale == "0,30000"
    assert color == _PRO_RGB_COLOR_FORMULA


def test_hls_collection_with_b_bands_uses_s2_rescale():
    item = _item({"B04": {}, "B03": {}, "B02": {}})
    assets, bidx, rescale, _ = _infer_pro_render_defaults(
        collection_id="hls2-s30-private", item_doc=item
    )
    assert assets == ["B04", "B03", "B02"]
    assert rescale == "0,3000"
    assert bidx == []


def test_naip_shape_falls_through_to_image_with_bidx():
    item = _item({"image": {}, "metadata": {}})
    assets, bidx, rescale, color = _infer_pro_render_defaults(
        collection_id="naip-private", item_doc=item
    )
    assert assets == ["image"]
    assert bidx == ["image|1,2,3"]
    assert rescale is None
    assert color is None


def test_unknown_collection_with_visual_asset_prefers_visual():
    item = _item({"visual": {}, "data": {}})
    assets, bidx, _, _ = _infer_pro_render_defaults(
        collection_id="custom-org-collection", item_doc=item
    )
    assert assets == ["visual"]
    assert bidx == ["visual|1,2,3"]


def test_unknown_collection_with_only_data_asset_uses_first_match():
    item = _item({"data": {}, "metadata": {}})
    assets, bidx, _, _ = _infer_pro_render_defaults(
        collection_id="custom-org-collection", item_doc=item
    )
    assert assets == ["data"]
    assert bidx == ["data|1,2,3"]


def test_no_item_doc_falls_back_to_legacy_image_default():
    assets, bidx, rescale, color = _infer_pro_render_defaults(
        collection_id="anything", item_doc=None
    )
    assert assets == ["image"]
    assert bidx == ["image|1,2,3"]
    assert rescale is None
    assert color is None


def test_item_with_no_assets_falls_back_to_legacy_default():
    assets, bidx, _, _ = _infer_pro_render_defaults(
        collection_id="anything", item_doc={"bbox": [0, 0, 1, 1]}
    )
    assert assets == ["image"]
    assert bidx == ["image|1,2,3"]


def test_case_insensitive_asset_lookup():
    # Some catalogs publish lower-cased band keys (``b04`` instead of ``B04``).
    item = _item({"b04": {}, "b03": {}, "b02": {}})
    assets, bidx, rescale, _ = _infer_pro_render_defaults(
        collection_id="sentinel2-custom", item_doc=item
    )
    # Returns the original-cased keys from the item.
    assert assets == ["b04", "b03", "b02"]
    assert bidx == []
    assert rescale == "0,3000"
