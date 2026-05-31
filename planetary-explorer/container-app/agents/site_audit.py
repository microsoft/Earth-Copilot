"""
Site audit — produces a regulator-grade dossier for a single proposed AI
data center location.

Core question:  given (lat, lng, claimed_mw), is this site viable?

Integrates ALL THREE data sources of the GeoAI Accelerator in a single
determination — that integration is the point of the demo:

    Fabric Lakehouse  →  power / water / parcel / competition (Delta tables)
    Planetary Computer →  hazards & terrain (raster sampling, io-lulc + cop-dem)
    Azure AI Search    →  permitting precedent (regulator + facility documents)

Each dimension produces a 0-100 score plus structured evidence rows; the
audit returns a weighted overall score and a flat evidence list with a
`kind` discriminator so the agent can render inline citations.

Reads the 5 Delta tables we materialized in OneLake directly via the
deltalake library + OBO storage token (no SQL endpoint, no DAX, no Spark).
DataFrames are cached in-process for 1 hour.
"""

from __future__ import annotations

import asyncio
import logging
import math
import os
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

import pandas as pd
from deltalake import DeltaTable

import fabric_client
import weather_client

logger = logging.getLogger(__name__)

# ──────────────────────────────────────────────────────────────────────────────
# Configuration
# ──────────────────────────────────────────────────────────────────────────────

STORAGE_SCOPE = "https://storage.azure.com/.default"

# Override via env vars in container app. Empty defaults force operators to
# wire FABRIC_LAKEHOUSE_WORKSPACE_ID / FABRIC_LAKEHOUSE_ID per environment.
DEFAULT_WORKSPACE_ID = os.getenv("FABRIC_LAKEHOUSE_WORKSPACE_ID", "")
DEFAULT_LAKEHOUSE_ID = os.getenv("FABRIC_LAKEHOUSE_ID", "")
ONELAKE_REGION = os.getenv("FABRIC_ONELAKE_REGION", "westus")

# ──────────────────────────────────────────────────────────────────────────────
# Auto-resume: wake a paused Fabric F-SKU capacity on demand
# ──────────────────────────────────────────────────────────────────────────────
# When a query hits an OneLake table on a paused/suspended capacity, deltalake
# returns an error containing "CapacityIdNotAvailable" (or similar). Rather
# than failing the user request, we issue an ARM `resume` against the capacity,
# poll until Active, then retry the read once. This keeps the F2 effectively
# always-warm without paying for it when idle — provided the operator sets up
# the Azure-side auto-pause (Fabric portal → Capacity settings).
#
# The container's Managed Identity must have `Microsoft.Fabric/capacities/resume/action`
# on the capacity scope (Contributor is sufficient).
FABRIC_CAPACITY_SUB = os.getenv("FABRIC_CAPACITY_SUB", "")
FABRIC_CAPACITY_RG = os.getenv("FABRIC_CAPACITY_RG", "")
FABRIC_CAPACITY_NAME = os.getenv("FABRIC_CAPACITY_NAME", "")
_CAPACITY_PAUSED_MARKERS = (
    "CapacityIdNotAvailable",
    "CapacityNotActive",
    "Fabric capacity",
    "Suspended",
    "Paused",
)
_RESUME_POLL_INTERVAL_S = 5.0
_RESUME_POLL_TIMEOUT_S = 120.0
_RESUME_LOCK = asyncio.Lock()

# Read radii (miles)
GRID_HV_RADIUS_MI = 10.0
PARCEL_MATCH_RADIUS_MI = 5.0
COMPETITION_RADIUS_MI = 50.0
WATER_SEARCH_RADIUS_MI = 50.0

# Cache: { table_name: (loaded_at_epoch, dataframe) }
_TABLE_CACHE: dict[str, tuple[float, pd.DataFrame]] = {}
# Parallel cache of the Delta snapshot version that produced each cached
# DataFrame, populated alongside ``_TABLE_CACHE``. Surfaced in the audit's
# ``data_provenance`` so citations are reproducible (each Fabric table row
# pins the exact snapshot the audit was computed against). Kept as a
# separate dict so the public ``_load_table`` return signature stays
# ``pd.DataFrame`` and other callers (e.g. ``site_intel.executors``) don't
# need to change.
_TABLE_VERSIONS: dict[str, int | None] = {}
_CACHE_TTL_SECONDS = 3600
_CACHE_LOCK = asyncio.Lock()


# ──────────────────────────────────────────────────────────────────────────────
# Geometry helpers
# ──────────────────────────────────────────────────────────────────────────────

EARTH_RADIUS_MI = 3958.7613


def _haversine_mi(
    lat1: float, lon1: float, lat2: pd.Series, lon2: pd.Series
) -> pd.Series:
    """Great-circle distance from a point to a vector of points, in miles."""
    lat1_r = math.radians(lat1)
    lon1_r = math.radians(lon1)
    lat2_r = pd.Series(lat2).astype(float).map(math.radians)
    lon2_r = pd.Series(lon2).astype(float).map(math.radians)
    dlat = lat2_r - lat1_r
    dlon = lon2_r - lon1_r
    a = (
        (dlat / 2).map(math.sin) ** 2
        + math.cos(lat1_r) * lat2_r.map(math.cos) * (dlon / 2).map(math.sin) ** 2
    )
    return 2 * EARTH_RADIUS_MI * a.clip(0, 1).map(math.sqrt).map(math.asin)


# ──────────────────────────────────────────────────────────────────────────────
# Delta table loading
# ──────────────────────────────────────────────────────────────────────────────


def _table_uri(table: str, workspace_id: str, lakehouse_id: str) -> str:
    return (
        f"abfss://{workspace_id}@onelake.dfs.fabric.microsoft.com/"
        f"{lakehouse_id}/Tables/{table}"
    )


def _is_capacity_paused_error(exc: BaseException) -> bool:
    msg = str(exc)
    return any(marker in msg for marker in _CAPACITY_PAUSED_MARKERS)


async def _resume_capacity_if_configured() -> bool:
    """Issue ARM resume against the configured Fabric capacity and poll for Active.

    Returns True if the capacity is now Active (already or after resume),
    False if env vars are unset or the resume failed. Single-flight via
    `_RESUME_LOCK` so a thundering herd of paused-table reads triggers exactly
    one ARM call.
    """
    if not (FABRIC_CAPACITY_SUB and FABRIC_CAPACITY_RG and FABRIC_CAPACITY_NAME):
        logger.warning(
            "[SITE_AUDIT] capacity paused error but FABRIC_CAPACITY_{SUB,RG,NAME} not set; "
            "cannot auto-resume"
        )
        return False

    import httpx
    import fabric_client  # local import to avoid circular at module load

    async with _RESUME_LOCK:
        cred = await fabric_client._get_credential()
        # azure-identity.aio credentials expose get_token(...) as a coroutine.
        arm_token = await cred.get_token(
            "https://management.azure.com/.default"
        )
        base = (
            f"https://management.azure.com/subscriptions/{FABRIC_CAPACITY_SUB}"
            f"/resourceGroups/{FABRIC_CAPACITY_RG}"
            f"/providers/Microsoft.Fabric/capacities/{FABRIC_CAPACITY_NAME}"
        )
        headers = {"Authorization": f"Bearer {arm_token.token}"}
        params = {"api-version": "2023-11-01"}
        async with httpx.AsyncClient(timeout=30.0) as client:
            # Skip resume if already Active
            try:
                r = await client.get(base, headers=headers, params=params)
                if r.status_code == 200 and r.json().get("properties", {}).get("state") == "Active":
                    logger.info("[SITE_AUDIT] capacity %s already Active", FABRIC_CAPACITY_NAME)
                    return True
            except Exception as e:  # noqa: BLE001
                logger.warning("[SITE_AUDIT] capacity GET failed: %s", e)

            logger.info("[SITE_AUDIT] resuming capacity %s …", FABRIC_CAPACITY_NAME)
            try:
                r = await client.post(f"{base}/resume", headers=headers, params=params)
                if r.status_code not in (200, 202):
                    logger.error(
                        "[SITE_AUDIT] resume POST returned %s: %s",
                        r.status_code, r.text[:300],
                    )
                    return False
            except Exception as e:  # noqa: BLE001
                logger.error("[SITE_AUDIT] resume POST failed: %s", e)
                return False

            # Poll until Active
            deadline = time.time() + _RESUME_POLL_TIMEOUT_S
            while time.time() < deadline:
                await asyncio.sleep(_RESUME_POLL_INTERVAL_S)
                try:
                    r = await client.get(base, headers=headers, params=params)
                    state = r.json().get("properties", {}).get("state") if r.status_code == 200 else None
                    logger.info("[SITE_AUDIT] capacity poll state=%s", state)
                    if state == "Active":
                        # Give OneLake a few seconds to pick up the resumed compute
                        await asyncio.sleep(5)
                        return True
                except Exception as e:  # noqa: BLE001
                    logger.warning("[SITE_AUDIT] capacity poll failed: %s", e)
            logger.error("[SITE_AUDIT] capacity did not reach Active within %ss", _RESUME_POLL_TIMEOUT_S)
            return False


async def _load_table(
    table: str,
    user_assertion: str,
    workspace_id: str,
    lakehouse_id: str,
) -> pd.DataFrame:
    """Load a Delta table from OneLake as a pandas DataFrame, with TTL cache.

    Each user request triggers a fresh OBO exchange (the storage token has its
    own expiry). The DataFrame itself is cached by table name across requests.
    """
    async with _CACHE_LOCK:
        cached = _TABLE_CACHE.get(table)
        if cached and (time.time() - cached[0]) < _CACHE_TTL_SECONDS:
            return cached[1]

        token = await fabric_client.exchange_user_token(user_assertion, STORAGE_SCOPE)

        # deltalake reads are blocking; run in a thread.
        def _read() -> tuple[pd.DataFrame, int | None]:
            dt = DeltaTable(
                _table_uri(table, workspace_id, lakehouse_id),
                storage_options={
                    "bearer_token": token,
                    "use_fabric_endpoint": "true",
                },
            )
            try:
                ver: int | None = int(dt.version())
            except Exception:  # noqa: BLE001 — version is best-effort metadata
                ver = None
            return dt.to_pandas(), ver

        try:
            df, version = await asyncio.to_thread(_read)
        except Exception as exc:  # noqa: BLE001 — narrow via marker scan
            if not _is_capacity_paused_error(exc):
                raise
            logger.warning(
                "[SITE_AUDIT] table %s read hit paused capacity (%s); attempting auto-resume",
                table, type(exc).__name__,
            )
            resumed = await _resume_capacity_if_configured()
            if not resumed:
                raise
            # Refresh OBO token (the previous one may now be near expiry) and retry once.
            token = await fabric_client.exchange_user_token(user_assertion, STORAGE_SCOPE)
            df, version = await asyncio.to_thread(_read)
        _TABLE_CACHE[table] = (time.time(), df)
        _TABLE_VERSIONS[table] = version
        logger.info(
            "[SITE_AUDIT] loaded Delta table %s: %d rows (v=%s)",
            table, len(df), version,
        )
        return df
# ──────────────────────────────────────────────────────────────────────────────
# Per-dimension scoring
# ──────────────────────────────────────────────────────────────────────────────


@dataclass
class DimensionResult:
    """One axis of the audit: a 0-100 score + the raw evidence rows that produced it."""

    score: float                  # 0 (worst) — 100 (best)
    summary: str                  # one-line human explanation
    evidence: list[dict[str, Any]]   # rows pulled from the Lakehouse

    def as_dict(self) -> dict[str, Any]:
        return {
            "score": round(self.score, 1),
            "summary": self.summary,
            "evidence": self.evidence,
        }


def _score_power(
    lat: float, lng: float, claimed_mw: float, power_df: pd.DataFrame
) -> DimensionResult:
    """Power score = function of distance to nearest substation + HV transmission density."""
    if power_df.empty:
        return DimensionResult(0.0, "no power infrastructure data available", [])

    df = power_df.copy()
    df["distance_mi"] = _haversine_mi(lat, lng, df["latitude"], df["longitude"])

    subs = df[df["type"] == "substation"].nsmallest(5, "distance_mi")
    nearest_sub = subs.iloc[0] if not subs.empty else None

    hv_lines = df[
        (df["type"] == "transmission_line") & (df["distance_mi"] <= GRID_HV_RADIUS_MI)
    ]
    line_count = len(hv_lines)
    max_voltage = hv_lines["voltage_kv"].max() if not hv_lines.empty else 0

    # Score: 50 pts for substation proximity, 30 pts for HV-line density, 20 pts for max voltage
    if nearest_sub is None:
        sub_score = 0
    else:
        d = float(nearest_sub["distance_mi"])
        sub_score = max(0.0, 50 - 5 * d)        # full 50 at <1 mi, zero at 10 mi

    line_score = min(30.0, line_count * 5)       # 6 lines = full
    voltage_score = min(20.0, (max_voltage or 0) / 765 * 20)  # 765 kV = full

    score = sub_score + line_score + voltage_score

    if nearest_sub is not None:
        summary = (
            f"nearest substation {nearest_sub.get('name') or 'unnamed'} "
            f"({nearest_sub['distance_mi']:.1f} mi, "
            f"{nearest_sub.get('voltage_kv') or '?'} kV); "
            f"{line_count} HV transmission line(s) within {GRID_HV_RADIUS_MI:.0f} mi"
        )
    else:
        summary = "no substation found in dataset"

    evidence: list[dict[str, Any]] = []
    if nearest_sub is not None:
        evidence.append({
            "kind": "nearest_substation",
            "asset_id": nearest_sub.get("asset_id"),
            "name": nearest_sub.get("name"),
            "voltage_kv": nearest_sub.get("voltage_kv"),
            "distance_mi": round(float(nearest_sub["distance_mi"]), 2),
            "owner_utility": nearest_sub.get("owner_utility"),
            "source_url": nearest_sub.get("source_url"),
        })
    if not hv_lines.empty:
        top_lines = hv_lines.nlargest(3, "voltage_kv")
        evidence.extend({
            "kind": "hv_transmission",
            "asset_id": r.get("asset_id"),
            "voltage_kv": r.get("voltage_kv"),
            "distance_mi": round(float(r["distance_mi"]), 2),
            "owner_utility": r.get("owner_utility"),
            "source_url": r.get("source_url"),
        } for _, r in top_lines.iterrows())

    return DimensionResult(score, summary, evidence)


def _score_water(
    lat: float, lng: float, water_df: pd.DataFrame
) -> DimensionResult:
    """Water score = nearest active USGS gage within 50 mi; closer = better."""
    if water_df.empty:
        return DimensionResult(0.0, "no water assets in dataset", [])

    df = water_df.copy()
    df["distance_mi"] = _haversine_mi(lat, lng, df["latitude"], df["longitude"])
    nearby = df[df["distance_mi"] <= WATER_SEARCH_RADIUS_MI].nsmallest(5, "distance_mi")
    if nearby.empty:
        return DimensionResult(
            10.0,
            f"no active water gage within {WATER_SEARCH_RADIUS_MI:.0f} mi — water sourcing risk",
            [],
        )

    nearest = nearby.iloc[0]
    d = float(nearest["distance_mi"])
    # Full 100 at <2 mi, linear decay to 30 at 50 mi
    score = max(30.0, 100 - (d - 2) * (70 / 48))
    summary = (
        f"nearest USGS gage {nearest.get('name', 'unnamed')} "
        f"({d:.1f} mi, type={nearest.get('type')})"
    )
    evidence = [{
        "kind": "nearest_water",
        "asset_id": r.get("asset_id"),
        "name": r.get("name"),
        "type": r.get("type"),
        "distance_mi": round(float(r["distance_mi"]), 2),
        "huc_code": r.get("huc_code"),
        "source_url": r.get("source_url"),
    } for _, r in nearby.iterrows()]
    return DimensionResult(score, summary, evidence)


def _score_competition(
    lat: float, lng: float, dc_df: pd.DataFrame
) -> DimensionResult:
    """Lower density of existing data centers = higher score (less grid competition)."""
    if dc_df.empty:
        return DimensionResult(50.0, "existing-DC dataset empty", [])

    df = dc_df.copy()
    df["distance_mi"] = _haversine_mi(lat, lng, df["latitude"], df["longitude"])
    nearby = df[df["distance_mi"] <= COMPETITION_RADIUS_MI].nsmallest(20, "distance_mi")
    n = len(nearby)
    # 0 nearby → 100 (uncongested); 10+ → 30 (saturated)
    score = max(30.0, 100 - n * 7)
    summary = (
        f"{n} existing data center(s) within {COMPETITION_RADIUS_MI:.0f} mi"
    )
    evidence = [{
        "kind": "competing_dc",
        "facility_id": r.get("facility_id"),
        "operator": r.get("operator"),
        "distance_mi": round(float(r["distance_mi"]), 2),
        "source_url": r.get("source_url"),
    } for _, r in nearby.head(5).iterrows()]
    return DimensionResult(score, summary, evidence)


def _score_parcel_match(
    lat: float, lng: float, sites_df: pd.DataFrame
) -> DimensionResult:
    """Bonus axis: any EPA-screened brownfield within 5 mi means permitting head-start."""
    if sites_df.empty:
        return DimensionResult(50.0, "no EPA candidate sites in dataset", [])

    df = sites_df.copy()
    df["distance_mi"] = _haversine_mi(lat, lng, df["latitude"], df["longitude"])
    near = df[df["distance_mi"] <= PARCEL_MATCH_RADIUS_MI].nsmallest(3, "distance_mi")
    if near.empty:
        return DimensionResult(
            50.0,
            f"no EPA-screened brownfield within {PARCEL_MATCH_RADIUS_MI:.0f} mi",
            [],
        )
    closest = near.iloc[0]
    score = 100.0 if closest["distance_mi"] <= 1 else 80.0
    summary = (
        f"EPA-screened parcel {closest.get('name')} ({closest['parcel_acres']:.0f} ac, "
        f"{closest['distance_mi']:.1f} mi)"
    )
    evidence = [{
        "kind": "epa_parcel",
        "site_id": r.get("site_id"),
        "name": r.get("name"),
        "parcel_acres": r.get("parcel_acres"),
        "distance_mi": round(float(r["distance_mi"]), 2),
        "screening_status": r.get("screening_status"),
        "source_url": r.get("source_url"),
    } for _, r in near.iterrows()]
    return DimensionResult(score, summary, evidence)


# ──────────────────────────────────────────────────────────────────────────────
# Public entry point
# ──────────────────────────────────────────────────────────────────────────────


# ── MPC raster sampling (Source 2: Planetary Computer) ────────────────────────
#
# We read two collections at the audit point:
#   • io-lulc-9-class      — 10 m Sentinel-2-derived land cover (Esri 2017-).
#                            Class codes 1=water 2=trees 4=flooded_veg 5=crops
#                            7=built 8=bare 9=snow 11=rangeland.
#   • cop-dem-glo-30        — Copernicus 30 m global DEM (elevation in meters).
#
# Strategy: STAC search at the point, take the most-recent item, sign with
# `planetary_computer.sign()` so the COG href is presigned, open with rasterio
# and read the single pixel under (lat, lng). All blocking I/O runs in a
# thread; this keeps the MPC sampling parallel to the Lakehouse loads.

LULC_CLASS_NAMES = {
    1: "water", 2: "trees", 4: "flooded_vegetation", 5: "crops",
    7: "built_area", 8: "bare_ground", 9: "snow_ice", 10: "clouds",
    11: "rangeland",
}


# Always-on MPC anchor collections that drive the hazards score. Dynamic
# collections discovered from the user query are layered on top as evidence.
#   io-lulc-9-class — land cover (Esri 10 m, derived from Sentinel-2)
#   cop-dem-glo-30  — Copernicus 30 m DEM (elevation)
#   jrc-gsw         — JRC Global Surface Water (occurrence band, % of
#                     time the pixel was water 1984-present). Acts as a
#                     flood/permanent-water proxy that's far more honest
#                     than thresholding the DEM alone.
_MPC_ANCHOR_COLLECTIONS = ("io-lulc-9-class", "cop-dem-glo-30", "jrc-gsw")
# Cap dynamic discovery so a single audit can't blow up the STAC catalog.
_MAX_DYNAMIC_COLLECTIONS = 5


def _discover_dynamic_collections(user_query: str | None) -> list[str]:
    """Use the deterministic CollectionMapper to find MPC collections that
    match the user's question and are worth probing alongside the always-on
    LULC + DEM anchors. Returns at most ``_MAX_DYNAMIC_COLLECTIONS`` ids,
    excluding the anchors themselves and de-duplicated.
    """
    if not user_query or not user_query.strip():
        return []
    try:
        from collection_name_mapper import find_collections  # type: ignore
    except Exception as exc:  # noqa: BLE001
        logger.warning("[SITE_AUDIT] CollectionMapper unavailable: %s", exc)
        return []
    try:
        ids = find_collections(user_query) or []
    except Exception as exc:  # noqa: BLE001
        logger.warning("[SITE_AUDIT] find_collections failed: %s", exc)
        return []
    skip = set(_MPC_ANCHOR_COLLECTIONS)
    out: list[str] = []
    seen: set[str] = set()
    for cid in ids:
        if not cid or cid in skip or cid in seen:
            continue
        seen.add(cid)
        out.append(cid)
        if len(out) >= _MAX_DYNAMIC_COLLECTIONS:
            break
    return out


def _sample_mpc_pixels_blocking(
    lat: float,
    lng: float,
    extra_collections: list[str] | None = None,
) -> dict[str, Any]:
    """Synchronous MPC raster sampling. Runs in a worker thread.

    Always probes the two anchor collections (LULC + DEM). When
    ``extra_collections`` is provided, performs a STAC search for each at
    the audit point and records item metadata as evidence; pixel sampling
    is skipped for dynamic matches because they may be vector,
    multi-band, or otherwise not point-sample-friendly.
    """
    import planetary_computer as pc
    from pystac_client import Client
    import rasterio

    catalog = Client.open("https://planetarycomputer.microsoft.com/api/stac/v1")
    point = {"type": "Point", "coordinates": [lng, lat]}

    out: dict[str, Any] = {}

    # — Land cover —
    try:
        s = catalog.search(
            collections=["io-lulc-9-class"], intersects=point, max_items=1
        )
        items = list(s.items())
        if items:
            it = pc.sign(items[0])
            asset = it.assets.get("data") or next(iter(it.assets.values()))
            with rasterio.open(asset.href) as ds:
                vals = list(ds.sample([(lng, lat)]))
            cls = int(vals[0][0]) if vals else 0
            out["lulc"] = {
                "class_code": cls,
                "class_name": LULC_CLASS_NAMES.get(cls, f"class_{cls}"),
                "collection": "io-lulc-9-class",
                "item_id": items[0].id,
                "item_datetime": items[0].datetime.isoformat() if items[0].datetime else None,
                "asset_href": asset.href.split("?", 1)[0],
            }
    except Exception as exc:  # noqa: BLE001 — non-fatal for the audit
        out["lulc_error"] = str(exc)[:200]

    # — Elevation —
    try:
        s = catalog.search(
            collections=["cop-dem-glo-30"], intersects=point, max_items=1
        )
        items = list(s.items())
        if items:
            it = pc.sign(items[0])
            asset = it.assets.get("data") or next(iter(it.assets.values()))
            with rasterio.open(asset.href) as ds:
                vals = list(ds.sample([(lng, lat)]))
            elev = float(vals[0][0]) if vals else None
            out["dem"] = {
                "elevation_m": round(elev, 1) if elev is not None else None,
                "collection": "cop-dem-glo-30",
                "item_id": items[0].id,
                "asset_href": asset.href.split("?", 1)[0],
            }
    except Exception as exc:  # noqa: BLE001
        out["dem_error"] = str(exc)[:200]

    # — Surface water occurrence (flood / permanent-water proxy) —
    # JRC Global Surface Water ``occurrence`` band: value 0-100 = % of
    # months a pixel was observed as water 1984-present. >50 means the
    # site is in permanent water; >10 means seasonally flooded.
    try:
        s = catalog.search(
            collections=["jrc-gsw"], intersects=point, max_items=1
        )
        items = list(s.items())
        if items:
            it = pc.sign(items[0])
            asset = (
                it.assets.get("occurrence")
                or it.assets.get("data")
                or next(iter(it.assets.values()))
            )
            with rasterio.open(asset.href) as ds:
                vals = list(ds.sample([(lng, lat)]))
            occ_raw = float(vals[0][0]) if vals else None
            # JRC uses 255 for "no data"; clamp anything >100 to None.
            occ = (
                round(occ_raw, 1)
                if occ_raw is not None and 0.0 <= occ_raw <= 100.0
                else None
            )
            out["surface_water"] = {
                "occurrence_pct": occ,
                "collection": "jrc-gsw",
                "item_id": items[0].id,
                "item_datetime": (
                    items[0].datetime.isoformat() if items[0].datetime else None
                ),
                "asset_href": asset.href.split("?", 1)[0],
            }
    except Exception as exc:  # noqa: BLE001
        out["surface_water_error"] = str(exc)[:200]

    # — Dynamic, query-driven collections —
    if extra_collections:
        matches: list[dict[str, Any]] = []
        for cid in extra_collections:
            try:
                s = catalog.search(
                    collections=[cid], intersects=point, max_items=1
                )
                items = list(s.items())
                if not items:
                    matches.append({
                        "collection": cid,
                        "item_id": None,
                        "note": "no items intersect the audit point",
                    })
                    continue
                it = items[0]
                matches.append({
                    "collection": cid,
                    "item_id": it.id,
                    "item_datetime": it.datetime.isoformat() if it.datetime else None,
                    "asset_keys": list(it.assets.keys())[:8],
                })
            except Exception as exc:  # noqa: BLE001
                matches.append({
                    "collection": cid,
                    "error": str(exc)[:200],
                })
        out["dynamic_matches"] = matches

    return out


async def _score_hazards_with_mpc(
    lat: float,
    lng: float,
    user_query: str | None = None,
) -> DimensionResult:
    """Hazards/suitability score from MPC land-cover + DEM rasters.

    We treat the audit point's LULC class as a coarse build-suitability signal:
    built/bare/crops/rangeland → ok; trees → moderate (clearing cost); water /
    flooded_vegetation → near-disqualifier (siting on water). DEM provides
    a flood-proxy: very low elevation (<5 m) docks the score.

    When ``user_query`` is provided, additional MPC collections are looked up
    via the deterministic ``CollectionMapper`` keyword router and probed at
    the audit point. Their item metadata is attached as evidence (kind
    ``mpc_dynamic_match``) without changing the score, so the dossier
    surfaces the full set of relevant raster sources.
    """
    extra = _discover_dynamic_collections(user_query)
    # Fan out MPC raster sampling and Open-Meteo climatology concurrently;
    # they're independent and both gate the hazards score.
    samples_task = asyncio.to_thread(_sample_mpc_pixels_blocking, lat, lng, extra)
    weather_task = weather_client.fetch_climate_indicators(lat, lng)
    samples, weather = await asyncio.gather(samples_task, weather_task)
    lulc = samples.get("lulc")
    dem = samples.get("dem")
    gsw = samples.get("surface_water")

    score = 70.0  # neutral default
    notes: list[str] = []
    evidence: list[dict[str, Any]] = []

    if lulc:
        cls = lulc["class_name"]
        # Suitability table (siting-team rule of thumb):
        suit = {
            "built_area": 90, "bare_ground": 85, "crops": 80, "rangeland": 75,
            "trees": 55, "snow_ice": 30, "flooded_vegetation": 15, "water": 5,
        }
        s = suit.get(cls, 60)
        score = float(s)
        notes.append(f"land cover at point: {cls}")
        evidence.append({"kind": "mpc_land_cover", **lulc})
    elif samples.get("lulc_error"):
        notes.append(f"land-cover read failed ({samples['lulc_error'][:60]})")

    if dem and dem.get("elevation_m") is not None:
        elev = dem["elevation_m"]
        notes.append(f"elevation {elev:.0f} m")
        evidence.append({"kind": "mpc_elevation", **dem})
        # Flood proxy: very low coastal elevation → cap at 60.
        if elev < 5:
            score = min(score, 60.0)
            notes.append("low elevation — coastal flood risk")
    elif samples.get("dem_error"):
        notes.append(f"DEM read failed ({samples['dem_error'][:60]})")

    # Surface-water occurrence cap. JRC GSW gives a far cleaner flood
    # signal than thresholding the DEM alone (it captures lakes,
    # reservoirs, river floodplains).
    if gsw and gsw.get("occurrence_pct") is not None:
        occ = gsw["occurrence_pct"]
        evidence.append({"kind": "mpc_surface_water", **gsw})
        if occ >= 50.0:
            score = min(score, 10.0)
            notes.append(
                f"site sits in permanent water (JRC occurrence {occ:.0f}%)"
            )
        elif occ >= 10.0:
            score = min(score, 45.0)
            notes.append(
                f"seasonal flood exposure (JRC occurrence {occ:.0f}%)"
            )
        else:
            notes.append(
                f"low historical surface-water exposure ({occ:.0f}%)"
            )
    elif samples.get("surface_water_error"):
        notes.append(
            f"surface-water read failed ({samples['surface_water_error'][:60]})"
        )

    # Open-Meteo climate cap. Translates 1 year of ERA5 daily summaries
    # into a hazard cap (extreme heat days, peak wind, very wet climate).
    if weather:
        evidence.append({"kind": "weather_climatology", **weather})
        climate_cap, climate_notes = weather_client.score_climate_impact(weather)
        if climate_cap < 100.0:
            score = min(score, climate_cap)
        notes.extend(climate_notes)

    # Dynamic collection discoveries (no score impact, evidence only).
    dyn_matched: list[str] = []
    for m in samples.get("dynamic_matches") or []:
        evidence.append({"kind": "mpc_dynamic_match", **m})
        if m.get("item_id"):
            dyn_matched.append(m["collection"])
    if dyn_matched:
        notes.append(
            f"query-matched MPC collections: {', '.join(dyn_matched)}"
        )

    summary = "; ".join(notes) if notes else "no MPC samples available"
    return DimensionResult(score, summary, evidence)


# ── Permitting precedent search (Source 3: Azure AI Search) ───────────────────


def _doc_distance_mi(doc: dict[str, Any], lat: float, lng: float) -> float | None:
    """Compute distance in miles from (lat, lng) to a doc's location field, if any."""
    loc = doc.get("location")
    if not isinstance(loc, dict):
        return None
    coords = loc.get("coordinates")
    if not coords or len(coords) < 2:
        return None
    try:
        d_lng, d_lat = float(coords[0]), float(coords[1])
    except (TypeError, ValueError):
        return None
    s = _haversine_mi(lat, lng, pd.Series([d_lat]), pd.Series([d_lng]))
    return float(s.iloc[0])


async def _score_precedent_with_search(
    user_assertion: str,
    workspace_id: str,
    lat: float,
    lng: float,
    claimed_mw: float,
) -> DimensionResult:
    """Score = how much real permitting / interconnection precedent the corpus
    surfaces for a site like this one.

    We hit the Azure AI Search `permitting-docs` index with a natural-language
    query and select only retrieve-safe fields. Docs are ranked by relevance;
    for any with `location` set we attach a distance, and we soft-prefer
    nearby docs in the score.
    """
    # Generic utility / energy infrastructure permitting query — retrieves
    # relevant precedent across substation, transmission, generation, BESS,
    # and data-center filings in the `permitting-docs` index.
    query = f"{int(claimed_mw)} MW energy infrastructure interconnection permitting site approval"
    try:
        hits = await fabric_client.search_documents(
            user_assertion=user_assertion,
            workspace_id=workspace_id,
            query=query,
            top_k=8,
            select=[
                "id", "title", "source_url", "doc_date", "doc_type",
                "state", "location",
            ],
            semantic=True,
        )
    except fabric_client.FabricNotConfigured:
        # Permitting corpus not wired in this environment — fall back to a
        # neutral baseline rather than leaking env-var names into the UI.
        return DimensionResult(
            50.0,
            "no permitting precedent available for this site",
            [],
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning("[SITE_AUDIT] AI Search call failed: %s", exc)
        return DimensionResult(50.0, f"permitting search error: {exc}", [])

    if not hits:
        return DimensionResult(
            40.0,
            "no permitting precedent found in corpus",
            [],
        )

    evidence: list[dict[str, Any]] = []
    near_count = 0
    for h in hits:
        d = _doc_distance_mi(h, lat, lng)
        row = {
            "kind": "permitting_doc",
            "title": h.get("title"),
            "source_url": h.get("source_url"),
            "doc_type": h.get("doc_type"),
            "state": h.get("state"),
            "doc_date": h.get("doc_date"),
            "search_score": round(float(h.get("@search.score") or 0), 3),
            "distance_mi": round(d, 1) if d is not None else None,
        }
        if d is not None and d <= 200:
            near_count += 1
        evidence.append(row)

    # Score: 50 base + 5 per hit (max 30) + 5 per geo-near hit (max 20).
    score = min(100.0, 50 + 5 * len(hits) + 5 * near_count)
    summary = (
        f"{len(hits)} permitting precedent doc(s) (top: \"{hits[0].get('title')}\""
        + (f", {near_count} geo-tagged within 200 mi" if near_count else "")
        + ")"
    )
    return DimensionResult(score, summary, evidence)


# ──────────────────────────────────────────────────────────────────────────────
# Citation / provenance helpers
# ──────────────────────────────────────────────────────────────────────────────

# Public Planetary Computer (STAC + dataset pages). The site audit currently
# always reads from the public PC catalog in ``_sample_mpc_pixels_blocking``;
# if we ever route to MPC Pro / GeoCatalog here we should branch the source
# label and dataset URL accordingly to match the SourceChips convention
# ("MPC Pro" vs "Public PC").
_PC_PUBLIC_DATASET_BASE = "https://planetarycomputer.microsoft.com/dataset"
_PC_PUBLIC_STAC_BASE = "https://planetarycomputer.microsoft.com/api/stac/v1"


def _mpc_collection_rows(
    hazards_evidence: list[dict[str, Any]],
    user_query: str | None,
) -> list[dict[str, Any]]:
    """One provenance row per MPC collection actually used.

    Pulls item_id / item_datetime / asset_href from the hazards evidence so
    every collection citation pins to the exact STAC item that was sampled
    (anchor collections) or matched at the audit point (dynamic discovery).
    """
    by_collection: dict[str, dict[str, Any]] = {}

    # Anchors are surfaced as evidence rows with kind ``mpc_land_cover``
    # (io-lulc-9-class), ``mpc_elevation`` (cop-dem-glo-30), and
    # ``mpc_surface_water`` (jrc-gsw). Dynamic discoveries land as
    # ``mpc_dynamic_match``. We key by collection id.
    for ev in hazards_evidence:
        kind = ev.get("kind")
        cid = ev.get("collection")
        if not cid or kind not in (
            "mpc_land_cover",
            "mpc_elevation",
            "mpc_surface_water",
            "mpc_dynamic_match",
        ):
            continue
        role = "dynamic_match" if kind == "mpc_dynamic_match" else "anchor"
        row = by_collection.setdefault(
            cid,
            {
                "source": "planetary_computer",
                "catalog_label": "Public PC",
                "collection": cid,
                "role": role,
                "dataset_url": f"{_PC_PUBLIC_DATASET_BASE}/{cid}",
                "stac_collection_url": (
                    f"{_PC_PUBLIC_STAC_BASE}/collections/{cid}"
                ),
            },
        )
        if ev.get("item_id"):
            row["item_id"] = ev["item_id"]
            row["stac_item_url"] = (
                f"{_PC_PUBLIC_STAC_BASE}/collections/{cid}/items/{ev['item_id']}"
            )
        if ev.get("item_datetime"):
            row["item_datetime"] = ev["item_datetime"]
        if ev.get("asset_href"):
            row["asset_href"] = ev["asset_href"]
        if ev.get("note"):
            row["note"] = ev["note"]

    # Ensure the always-on anchors appear in the provenance list even when
    # their STAC search returned nothing (so the citation is honest about
    # what was queried, not just what landed a pixel).
    for cid in _MPC_ANCHOR_COLLECTIONS:
        if cid not in by_collection:
            by_collection[cid] = {
                "source": "planetary_computer",
                "catalog_label": "Public PC",
                "collection": cid,
                "role": "anchor",
                "dataset_url": f"{_PC_PUBLIC_DATASET_BASE}/{cid}",
                "stac_collection_url": (
                    f"{_PC_PUBLIC_STAC_BASE}/collections/{cid}"
                ),
                "note": "no items intersected the audit point",
            }

    # Stable order: anchors first (in declared order), then dynamic matches
    # alphabetically. Makes citation rendering deterministic.
    anchor_ids = list(_MPC_ANCHOR_COLLECTIONS)
    ordered = [by_collection[cid] for cid in anchor_ids if cid in by_collection]
    dyn = sorted(
        (r for cid, r in by_collection.items() if cid not in anchor_ids),
        key=lambda r: r["collection"],
    )
    ordered.extend(dyn)

    # Tack on the originating query so reviewers can replay dynamic
    # discovery without round-tripping through Log Analytics.
    if user_query and any(r.get("role") == "dynamic_match" for r in ordered):
        ordered.append({
            "source": "planetary_computer",
            "catalog_label": "Public PC",
            "kind": "dynamic_match_query",
            "user_query": user_query,
        })
    return ordered


def _build_provenance(
    *,
    fabric_tables: list[tuple[str, pd.DataFrame]],
    hazards_evidence: list[dict[str, Any]],
    user_query: str | None,
) -> list[dict[str, Any]]:
    """Assemble the audit's ``data_provenance`` list.

    Each entry is a citation: which source, which slice, and (where
    applicable) a URL the reviewer can open to verify. Fabric tables get
    Delta snapshot version + row count; MPC collections get one row each
    with item id and dataset URL; AI Search gets the index name.
    """
    out: list[dict[str, Any]] = []
    for table, df in fabric_tables:
        out.append({
            "source": "fabric_lakehouse",
            "table": table,
            "rows": int(len(df)),
            "delta_version": _TABLE_VERSIONS.get(table),
        })
    out.extend(_mpc_collection_rows(hazards_evidence, user_query))
    # Open-Meteo climate row — emitted only when the call succeeded so we
    # don't fabricate a citation. Mirrors the per-collection MPC pattern:
    # source + endpoint + citation_url so reviewers can replay the query.
    weather_ev = next(
        (e for e in hazards_evidence if e.get("kind") == "weather_climatology"),
        None,
    )
    if weather_ev:
        out.append({
            "source": "open_meteo",
            "catalog_label": "Open-Meteo (ERA5)",
            "endpoint": weather_ev.get("endpoint"),
            "model": weather_ev.get("model"),
            "reference_year": weather_ev.get("reference_year"),
            "citation_url": weather_ev.get("citation_url"),
            "docs_url": weather_ev.get("docs_url"),
        })
    out.append({
        "source": "azure_ai_search",
        "index": os.getenv("FABRIC_DOC_SEARCH_INDEX", "permitting-docs"),
    })
    return out


# ──────────────────────────────────────────────────────────────────────────────
# Public entry point
# ──────────────────────────────────────────────────────────────────────────────


async def audit_site(
    *,
    user_assertion: str,
    lat: float,
    lng: float,
    claimed_mw: float,
    user_query: str | None = None,
    workspace_id: str | None = None,
    lakehouse_id: str | None = None,
) -> dict[str, Any]:
    """Produce a structured siting dossier for (lat, lng, claimed_mw).

    Returns
    -------
    dict
        {
          "input": {...},
          "scores": {power, water, hazards, competition, parcel, overall},
          "summaries": {...},
          "evidence": [...],     # flat list across dimensions, with `kind`
          "data_provenance": [...]  # which Lakehouse tables were consulted
        }
    """
    ws = workspace_id or DEFAULT_WORKSPACE_ID
    lh = lakehouse_id or DEFAULT_LAKEHOUSE_ID

    # Run all six data calls concurrently:
    #   • 4 Delta tables from OneLake (Fabric)
    #   • 1 MPC raster sample (Planetary Computer)
    #   • 1 AI Search query    (Azure AI Search)
    sites, power, water, dcs, hazards_r, precedent_r = await asyncio.gather(
        _load_table("candidate_sites", user_assertion, ws, lh),
        _load_table("power_infrastructure", user_assertion, ws, lh),
        _load_table("water_assets", user_assertion, ws, lh),
        _load_table("existing_data_centers", user_assertion, ws, lh),
        _score_hazards_with_mpc(lat, lng, user_query),
        _score_precedent_with_search(user_assertion, ws, lat, lng, claimed_mw),
    )

    power_r = _score_power(lat, lng, claimed_mw, power)
    water_r = _score_water(lat, lng, water)
    competition_r = _score_competition(lat, lng, dcs)
    parcel_r = _score_parcel_match(lat, lng, sites)

    # Overall score: weighted average reflecting siting team priorities.
    # Power dominates because grid is the binding constraint; precedent is
    # included as a regulatory-confidence factor.
    weights = {
        "power": 0.35,
        "water": 0.15,
        "hazards": 0.15,
        "competition": 0.10,
        "parcel": 0.10,
        "precedent": 0.15,
    }
    overall = (
        power_r.score * weights["power"]
        + water_r.score * weights["water"]
        + hazards_r.score * weights["hazards"]
        + competition_r.score * weights["competition"]
        + parcel_r.score * weights["parcel"]
        + precedent_r.score * weights["precedent"]
    )

    return {
        "input": {"lat": lat, "lng": lng, "claimed_mw": claimed_mw},
        "scores": {
            "power": round(power_r.score, 1),
            "water": round(water_r.score, 1),
            "hazards": round(hazards_r.score, 1),
            "competition": round(competition_r.score, 1),
            "parcel_match": round(parcel_r.score, 1),
            "precedent": round(precedent_r.score, 1),
            "overall": round(overall, 1),
            "weights": weights,
        },
        "summaries": {
            "power": power_r.summary,
            "water": water_r.summary,
            "hazards": hazards_r.summary,
            "competition": competition_r.summary,
            "parcel_match": parcel_r.summary,
            "precedent": precedent_r.summary,
        },
        "evidence": (
            power_r.evidence
            + water_r.evidence
            + competition_r.evidence
            + parcel_r.evidence
            + hazards_r.evidence
            + precedent_r.evidence
        ),
        "data_provenance": _build_provenance(
            fabric_tables=[
                ("candidate_sites", sites),
                ("power_infrastructure", power),
                ("water_assets", water),
                ("existing_data_centers", dcs),
            ],
            hazards_evidence=hazards_r.evidence,
            user_query=user_query,
        ),
        "lakehouse": {"workspace_id": ws, "lakehouse_id": lh},
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }
