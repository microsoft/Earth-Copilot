"""Facility + supply-edge data loaders.

Tries to load the two reference tables from the Fabric Lakehouse; falls
back to bundled seed JSON when the lakehouse tables don't exist yet (the
MVP is meant to be runnable before the Fabric tables are provisioned).

Tables expected once Fabric is provisioned:

  - ``facilities``    columns: facility_id (str), name, type, lat, lng, region,
                               city, criticality (0-1), heat_threshold_f,
                               cooling_water_m3_per_day, headcount, notes
  - ``supply_edges``  columns: src_facility_id, dst_facility_id, kind,
                               lead_time_days, weekly_volume

A future iteration will replace ``_load_seed`` with the same
``deltalake.DeltaTable(...).to_pandas()`` path that Site Intel uses
(see ``agents.site_audit._load_table``). The contract — the columns each
DataFrame must carry — is set here.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
from pathlib import Path
from typing import Any

import pandas as pd

logger = logging.getLogger(__name__)

_SEED_DIR = Path(__file__).resolve().parent / "seed_data"
_FACILITIES_SEED = _SEED_DIR / "facilities.json"
_EDGES_SEED = _SEED_DIR / "supply_edges.json"
_BCP_SEED = _SEED_DIR / "bcp_playbooks.json"

# Default Fabric coordinates fall through to site_audit's so a single
# workspace can host both modules' tables. Override per-env via env vars.
DEFAULT_WORKSPACE_ID = os.getenv(
    "RESILIENCE_FABRIC_WORKSPACE_ID",
    os.getenv("FABRIC_LAKEHOUSE_WORKSPACE_ID", ""),
)
DEFAULT_LAKEHOUSE_ID = os.getenv(
    "RESILIENCE_FABRIC_LAKEHOUSE_ID",
    os.getenv("FABRIC_LAKEHOUSE_ID", ""),
)

def _force_seed() -> bool:
    """Read the force-seed flag at call time so tests + ops can flip it live."""
    return os.getenv("RESILIENCE_FORCE_SEED", "0").lower() in ("1", "true", "yes", "on")


def _load_seed() -> tuple[pd.DataFrame, pd.DataFrame]:
    """Synchronous seed loader — bundled JSON files."""
    with open(_FACILITIES_SEED, "r", encoding="utf-8") as f:
        facilities = pd.DataFrame(json.load(f))
    with open(_EDGES_SEED, "r", encoding="utf-8") as f:
        edges = pd.DataFrame(json.load(f))
    return facilities, edges


async def _try_load_from_fabric(
    user_assertion: str,
    workspace_id: str,
    lakehouse_id: str,
) -> tuple[pd.DataFrame, pd.DataFrame] | None:
    """Best-effort Fabric Lakehouse load.

    Returns ``None`` (without raising) if the tables don't exist or the
    deltalake import fails — caller falls back to seed data.
    """
    try:
        from agents.site_audit import _load_table  # reuse existing path
    except Exception as exc:  # noqa: BLE001
        logger.info("[RESILIENCE] could not import site_audit._load_table: %s", exc)
        return None

    try:
        facilities, edges = await asyncio.gather(
            _load_table("facilities", user_assertion, workspace_id, lakehouse_id),
            _load_table("supply_edges", user_assertion, workspace_id, lakehouse_id),
        )
        return facilities, edges
    except Exception as exc:  # noqa: BLE001 — missing tables are expected pre-provision
        logger.info("[RESILIENCE] Fabric load failed (%s); using seed data", exc)
        return None


async def load_registry(
    *,
    user_assertion: str,
    workspace_id: str | None = None,
    lakehouse_id: str | None = None,
    region_filter: str | None = None,
) -> tuple[pd.DataFrame, pd.DataFrame, str]:
    """Load facilities + supply_edges, with Fabric → seed fallback.

    Returns ``(facilities_df, edges_df, source)`` where ``source`` is
    ``"fabric"`` or ``"seed"``. Region filter is applied after the load
    so the workspace doesn't have to hold per-region tables.
    """
    ws = workspace_id or DEFAULT_WORKSPACE_ID
    lh = lakehouse_id or DEFAULT_LAKEHOUSE_ID

    facilities: pd.DataFrame | None = None
    edges: pd.DataFrame | None = None
    source = "seed"

    if not _force_seed():
        fabric_result = await _try_load_from_fabric(user_assertion, ws, lh)
        if fabric_result is not None:
            facilities, edges = fabric_result
            source = "fabric"

    if facilities is None or edges is None:
        # Pandas IO is sync but fast (small JSON); offload to thread anyway
        # so the event loop isn't blocked on disk on cold start.
        facilities, edges = await asyncio.to_thread(_load_seed)
        source = "seed"

    if region_filter:
        rf = region_filter.upper()
        if "region" in facilities.columns:
            facilities = facilities[facilities["region"].astype(str).str.upper() == rf].reset_index(drop=True)

    logger.info(
        "[RESILIENCE] registry loaded: facilities=%d edges=%d source=%s region=%s",
        len(facilities), len(edges), source, region_filter or "*",
    )
    return facilities, edges, source


# ─────────────────────────────────────────────────────────────────────────
# BCP playbooks loader (Fabric Delta table → seed JSON fallback)
# ─────────────────────────────────────────────────────────────────────────
def _load_bcp_seed() -> pd.DataFrame:
    """Synchronous seed loader for BCP playbooks."""
    with open(_BCP_SEED, "r", encoding="utf-8") as f:
        return pd.DataFrame(json.load(f))


async def load_bcp_playbooks(
    *,
    user_assertion: str | None = None,
    workspace_id: str | None = None,
    lakehouse_id: str | None = None,
    hazards: list[str] | tuple[str, ...] | None = None,
    facility_ids: list[str] | tuple[str, ...] | None = None,
    region_filter: str | None = None,
) -> tuple[pd.DataFrame, str]:
    """Load the BCP playbook table; Fabric → seed fallback.

    Returns ``(playbooks_df, source)``. Filters are applied after the load
    so we can share one materialized table across regions.

    Filtering semantics (best-effort, OR-combined):
        - ``hazards``: keep rows where any hazard intersects the row's
          ``hazards`` list column.
        - ``facility_ids``: keep rows where any id intersects the row's
          ``facility_hint`` list column **OR** the row has no facility hint
          (treated as broadly applicable).
        - ``region_filter``: exact case-insensitive match on ``region``.
    """
    ws = workspace_id or DEFAULT_WORKSPACE_ID
    lh = lakehouse_id or DEFAULT_LAKEHOUSE_ID

    playbooks: pd.DataFrame | None = None
    source = "seed"

    if not _force_seed() and user_assertion:
        try:
            from agents.site_audit import _load_table  # reuse OBO Delta reader
            playbooks = await _load_table("bcp_playbooks", user_assertion, ws, lh)
            source = "fabric"
        except Exception as exc:  # noqa: BLE001 — missing table is expected pre-provision
            logger.info("[RESILIENCE] Fabric bcp_playbooks load failed (%s); using seed", exc)
            playbooks = None

    if playbooks is None:
        playbooks = await asyncio.to_thread(_load_bcp_seed)
        source = "seed"

    if region_filter and "region" in playbooks.columns:
        rf = region_filter.upper()
        playbooks = playbooks[
            playbooks["region"].astype(str).str.upper() == rf
        ].reset_index(drop=True)

    if hazards:
        wanted_h = {h.lower() for h in hazards}
        def _row_hazards(v: Any) -> set[str]:
            if isinstance(v, (list, tuple)):
                return {str(h).lower() for h in v}
            if isinstance(v, str):
                return {v.lower()}
            return set()
        if "hazards" in playbooks.columns:
            mask = playbooks["hazards"].apply(lambda v: bool(_row_hazards(v) & wanted_h))
            playbooks = playbooks[mask].reset_index(drop=True)

    if facility_ids:
        wanted_f = {str(f) for f in facility_ids}
        def _row_facilities(v: Any) -> set[str]:
            if isinstance(v, (list, tuple)):
                return {str(f) for f in v}
            if isinstance(v, str):
                return {v}
            return set()
        if "facility_hint" in playbooks.columns:
            mask = playbooks["facility_hint"].apply(
                lambda v: (not _row_facilities(v)) or bool(_row_facilities(v) & wanted_f)
            )
            playbooks = playbooks[mask].reset_index(drop=True)

    logger.info(
        "[RESILIENCE] bcp_playbooks loaded: rows=%d source=%s hazards=%s facilities=%s",
        len(playbooks), source, list(hazards or []), len(facility_ids or []),
    )
    return playbooks, source
