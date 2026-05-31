"""Unit tests for resilience snapshot helpers.

Pure-function tests for:
  * URL composition (build_snapshot_url): bbox padding, severity color
    mapping, single-facility fallback span, subscription-key placement.
  * SnapshotNotConfigured raised when AZURE_MAPS_SUBSCRIPTION_KEY is unset.
  * render_assessment_png against a mocked httpx transport (status path,
    happy path, empty-body path).

Tests deliberately do NOT hit Azure Maps — that's an integration concern.
"""

from __future__ import annotations

import httpx
import pytest

from agents.resilience.snapshot import (
    SnapshotNotConfigured,
    _bbox,
    _pin_spec,
    build_snapshot_url,
    render_assessment_png,
)


# ── helpers ──────────────────────────────────────────────────────────────


def _dossier(facilities=None) -> dict:
    return {
        "assessment_id": "00000000-0000-0000-0000-000000000001",
        "facilities": facilities or [],
    }


# ── _bbox ───────────────────────────────────────────────────────────────


def test_bbox_empty_falls_back_to_us():
    min_lon, min_lat, max_lon, max_lat = _bbox([])
    assert min_lon == -125.0 and max_lon == -66.0
    assert min_lat == 24.0 and max_lat == 50.0


def test_bbox_single_point_has_nonzero_span():
    bbox = _bbox([{"lat": 30.0, "lng": -97.0}])
    min_lon, min_lat, max_lon, max_lat = bbox
    assert max_lon > min_lon
    assert max_lat > min_lat


def test_bbox_pads_multi_point():
    pts = [
        {"lat": 30.0, "lng": -97.0},
        {"lat": 32.0, "lng": -95.0},
    ]
    min_lon, min_lat, max_lon, max_lat = _bbox(pts)
    # Original span lon=2, lat=2. Padding 10% each side → bbox at least 0.2 wider.
    assert min_lon < -97.0
    assert max_lon > -95.0
    assert min_lat < 30.0
    assert max_lat > 32.0


def test_bbox_ignores_invalid_coords():
    pts = [
        {"lat": "bad", "lng": -97.0},
        {"lat": 30.0, "lng": None},
    ]
    # No valid points → fallback bbox
    assert _bbox(pts) == (-125.0, 24.0, -66.0, 50.0)


# ── _pin_spec ───────────────────────────────────────────────────────────


def test_pin_spec_groups_by_severity():
    facilities = [
        {"facility_id": "F1", "lat": 30.0, "lng": -97.0, "severity": "severe"},
        {"facility_id": "F2", "lat": 31.0, "lng": -98.0, "severity": "severe"},
        {"facility_id": "F3", "lat": 32.0, "lng": -99.0, "severity": "low"},
    ]
    pins = _pin_spec(facilities)
    # Two severity buckets → two pins= params
    assert len(pins) == 2
    severe_spec = next(p for p in pins if "B91C1C" in p)
    low_spec = next(p for p in pins if "16A34A" in p)
    # Two coords in severe bucket, one in low
    assert severe_spec.count("'F") == 2
    assert low_spec.count("'F") == 1


def test_pin_spec_unknown_severity_uses_default_color():
    facilities = [{"facility_id": "X1", "lat": 30.0, "lng": -97.0, "severity": "atomic"}]
    pins = _pin_spec(facilities)
    assert len(pins) == 1
    assert "6B7280" in pins[0]


# ── build_snapshot_url ──────────────────────────────────────────────────


def test_build_snapshot_url_requires_subscription_key(monkeypatch):
    monkeypatch.delenv("AZURE_MAPS_SUBSCRIPTION_KEY", raising=False)
    with pytest.raises(SnapshotNotConfigured):
        build_snapshot_url(_dossier())


def test_build_snapshot_url_includes_expected_params(monkeypatch):
    monkeypatch.setenv("AZURE_MAPS_SUBSCRIPTION_KEY", "test-key")
    url = build_snapshot_url(
        _dossier(facilities=[
            {"facility_id": "F1", "lat": 30.0, "lng": -97.0, "severity": "high"},
        ]),
        width=800,
        height=600,
    )
    assert url.startswith("https://atlas.microsoft.com/map/static/png?")
    assert "api-version=2024-04-01" in url
    assert "width=800" in url
    assert "height=600" in url
    assert "tilesetId=microsoft.base.road" in url
    assert "subscription-key=test-key" in url
    assert "pins=" in url
    # Severity 'high' → orange F97316
    assert "F97316" in url


def test_build_snapshot_url_rejects_out_of_range_dimensions(monkeypatch):
    monkeypatch.setenv("AZURE_MAPS_SUBSCRIPTION_KEY", "k")
    with pytest.raises(ValueError):
        build_snapshot_url(_dossier(), width=100, height=600)
    with pytest.raises(ValueError):
        build_snapshot_url(_dossier(), width=600, height=4000)


# ── render_assessment_png ───────────────────────────────────────────────


@pytest.mark.asyncio
async def test_render_assessment_png_returns_bytes(monkeypatch):
    monkeypatch.setenv("AZURE_MAPS_SUBSCRIPTION_KEY", "test-key")

    fake_png = b"\x89PNG\r\n\x1a\n" + b"\x00" * 16

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/map/static/png"
        assert "subscription-key=test-key" in str(request.url)
        return httpx.Response(200, content=fake_png)

    transport = httpx.MockTransport(handler)

    # Patch httpx.AsyncClient to use our transport
    import agents.resilience.snapshot as snap

    real_client = httpx.AsyncClient

    def make_client(*args, **kwargs):
        kwargs["transport"] = transport
        return real_client(*args, **kwargs)

    monkeypatch.setattr(snap.httpx, "AsyncClient", make_client)

    result = await render_assessment_png(_dossier())
    assert result == fake_png


@pytest.mark.asyncio
async def test_render_assessment_png_raises_when_unconfigured(monkeypatch):
    monkeypatch.delenv("AZURE_MAPS_SUBSCRIPTION_KEY", raising=False)
    with pytest.raises(SnapshotNotConfigured):
        await render_assessment_png(_dossier())


@pytest.mark.asyncio
async def test_render_assessment_png_raises_on_http_error(monkeypatch):
    monkeypatch.setenv("AZURE_MAPS_SUBSCRIPTION_KEY", "test-key")

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(403, text="forbidden")

    import agents.resilience.snapshot as snap

    real_client = httpx.AsyncClient

    def make_client(*args, **kwargs):
        kwargs["transport"] = httpx.MockTransport(handler)
        return real_client(*args, **kwargs)

    monkeypatch.setattr(snap.httpx, "AsyncClient", make_client)

    with pytest.raises(httpx.HTTPStatusError):
        await render_assessment_png(_dossier())
