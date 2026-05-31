"""Static-map snapshot rendering for resilience dossiers.

Used by the M365 declarative agent: when a user asks "which TX facilities are
at risk?", the agent calls ``/api/resilience/assess`` to get a dossier, then
calls ``/api/resilience/snapshot?assessment_id=<id>`` to fetch a PNG it can
inline in an adaptive card.

Design notes
------------
- Implementation is **Azure Maps Static Image API** (`/map/static/png`). Pure
  HTTP, no system deps, no headless browser, no canvas in-process.
- Image composition is deterministic: same dossier → same URL → same bytes.
  Lets us cache aggressively by ``assessment_id`` upstream.
- Auth to Azure Maps uses a subscription key (``AZURE_MAPS_SUBSCRIPTION_KEY``).
  Storing this in Key Vault and referencing from Container Apps env is
  standard practice; the module never logs the key.
- If the key isn't configured, ``render_assessment_png`` raises
  :class:`SnapshotNotConfigured` — the endpoint surfaces that as 503.
"""
from __future__ import annotations

import logging
import os
from typing import Any

import httpx

logger = logging.getLogger(__name__)

AZURE_MAPS_ENDPOINT = os.getenv(
    "AZURE_MAPS_ENDPOINT", "https://atlas.microsoft.com"
).rstrip("/")
_API_VERSION = "2024-04-01"

# Marker colors by severity. Azure Maps `pins` syntax uses `iconType|color|...`;
# we use the built-in pin icons and set color per severity. Hex without `#`.
_SEVERITY_COLOR: dict[str, str] = {
    "severe": "B91C1C",      # red-700
    "high": "F97316",        # orange-500
    "moderate": "EAB308",    # yellow-500
    "low": "16A34A",         # green-600
}
_DEFAULT_COLOR = "6B7280"    # gray-500 (unknown severity)


class SnapshotNotConfigured(RuntimeError):
    """Raised when ``AZURE_MAPS_SUBSCRIPTION_KEY`` is not set."""


def _subscription_key() -> str:
    key = os.getenv("AZURE_MAPS_SUBSCRIPTION_KEY")
    if not key:
        raise SnapshotNotConfigured(
            "AZURE_MAPS_SUBSCRIPTION_KEY env var is not set; "
            "the resilience snapshot endpoint is unavailable."
        )
    return key


def _bbox(facilities: list[dict[str, Any]]) -> tuple[float, float, float, float]:
    """Compute a padded lon/lat bbox covering all facilities.

    Returns ``(min_lon, min_lat, max_lon, max_lat)`` with ~10% padding on
    each axis so pins don't sit on the image edge. Falls back to a wide
    view of the contiguous US if the input is empty or malformed.
    """
    pts = [
        (float(f["lng"]), float(f["lat"]))
        for f in facilities
        if isinstance(f.get("lat"), (int, float)) and isinstance(f.get("lng"), (int, float))
    ]
    if not pts:
        # Continental US fallback
        return (-125.0, 24.0, -66.0, 50.0)

    lons = [p[0] for p in pts]
    lats = [p[1] for p in pts]
    min_lon, max_lon = min(lons), max(lons)
    min_lat, max_lat = min(lats), max(lats)

    # Pad by 10% of the span on each axis, with a hard minimum so a single
    # facility doesn't produce a zero-area bbox.
    span_lon = max(max_lon - min_lon, 0.5)
    span_lat = max(max_lat - min_lat, 0.5)
    pad_lon = span_lon * 0.1
    pad_lat = span_lat * 0.1
    return (
        min_lon - pad_lon,
        min_lat - pad_lat,
        max_lon + pad_lon,
        max_lat + pad_lat,
    )


def _pin_spec(facilities: list[dict[str, Any]]) -> list[str]:
    """Build one Azure Maps `pins` query-string value per severity bucket.

    Azure Maps' pins parameter encodes: ``default|<style>||<lon> <lat> <label>``.
    All facilities of the same severity share one style spec; we emit one
    pins= query param per severity that appears in the dossier.
    """
    by_sev: dict[str, list[dict[str, Any]]] = {}
    for f in facilities:
        sev = (f.get("severity") or "low").lower()
        by_sev.setdefault(sev, []).append(f)

    params: list[str] = []
    for sev, items in by_sev.items():
        color = _SEVERITY_COLOR.get(sev, _DEFAULT_COLOR)
        # `default|co<HEX>` = standard pin shape with custom marker color.
        # `sc1.2` scales the marker; `lc<HEX>` sets label color (white).
        style = f"default|co{color}|sc1.2|lcFFFFFF"
        # Label = first 2 chars of facility id (most are FAB1, DC2 etc.)
        coords = " ".join(
            f"'{(f.get('facility_id') or '')[:3]}' {float(f['lng']):.5f} {float(f['lat']):.5f}"
            for f in items
            if isinstance(f.get("lat"), (int, float)) and isinstance(f.get("lng"), (int, float))
        )
        if coords:
            params.append(f"{style}||{coords}")
    return params


def build_snapshot_url(
    dossier: dict[str, Any],
    *,
    width: int = 1024,
    height: int = 768,
) -> str:
    """Compose the Azure Maps Static Image API URL for a dossier.

    Pure function — does not call out to Azure. Useful for unit-testing the
    URL composition without an HTTP mock.
    """
    if not 256 <= width <= 2048:
        raise ValueError("width must be in [256, 2048]")
    if not 256 <= height <= 2048:
        raise ValueError("height must be in [256, 2048]")

    facilities = dossier.get("facilities") or []
    min_lon, min_lat, max_lon, max_lat = _bbox(facilities)

    # The static endpoint accepts ?bbox=minLon,minLat,maxLon,maxLat. The
    # service auto-fits zoom to the bbox.
    params: list[tuple[str, str]] = [
        ("api-version", _API_VERSION),
        ("tilesetId", "microsoft.base.road"),
        ("bbox", f"{min_lon:.5f},{min_lat:.5f},{max_lon:.5f},{max_lat:.5f}"),
        ("width", str(width)),
        ("height", str(height)),
        ("subscription-key", _subscription_key()),
    ]
    for pin in _pin_spec(facilities):
        params.append(("pins", pin))

    # Build URL manually to preserve param order (subscription-key last).
    qs = "&".join(f"{k}={httpx.QueryParams({k: v})[k]}" for k, v in params)
    return f"{AZURE_MAPS_ENDPOINT}/map/static/png?{qs}"


async def render_assessment_png(
    dossier: dict[str, Any],
    *,
    width: int = 1024,
    height: int = 768,
    timeout_sec: float = 15.0,
) -> bytes:
    """Render a PNG snapshot for the given assessment dossier.

    Raises:
        SnapshotNotConfigured: ``AZURE_MAPS_SUBSCRIPTION_KEY`` not set.
        httpx.HTTPStatusError: Azure Maps returned non-200.
    """
    url = build_snapshot_url(dossier, width=width, height=height)
    async with httpx.AsyncClient(timeout=timeout_sec) as client:
        resp = await client.get(url)
    if resp.status_code != 200:
        # Strip subscription key from URL before logging.
        scrubbed = url.split("subscription-key=")[0] + "subscription-key=***"
        logger.warning(
            "[RESILIENCE.snapshot] Azure Maps returned %s for %s: %s",
            resp.status_code,
            scrubbed,
            resp.text[:300],
        )
        resp.raise_for_status()
    if not resp.content:
        raise RuntimeError("Azure Maps returned empty body")
    return resp.content
