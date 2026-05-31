"""Integration smoke tests for the Resilience data loaders.

Runs end-to-end against the bundled seed JSON (``RESILIENCE_FORCE_SEED=1``)
so the test is hermetic — no Fabric, no Open-Meteo, no AI Search.

Verifies:
  * registry loads 10 facilities + 20 supply edges from seed
  * region filter narrows correctly
  * BCP playbooks load + hazard / facility / region filters work
"""

from __future__ import annotations

import os

import pytest

# Force seed mode BEFORE importing the module, since FORCE_SEED is captured
# at import time as a module-level constant.
os.environ["RESILIENCE_FORCE_SEED"] = "1"

from agents.resilience.data_loader import (  # noqa: E402  (import after env set)
    _force_seed,
    load_bcp_playbooks,
    load_registry,
)


def test_force_seed_env_flag_is_active() -> None:
    """Sanity: the env var we just set is actually honored."""
    assert _force_seed() is True


@pytest.mark.asyncio
async def test_load_registry_returns_seed() -> None:
    facilities, edges, source = await load_registry(user_assertion="")
    assert source == "seed"
    assert len(facilities) >= 10
    assert len(edges) >= 20
    for col in ("facility_id", "name", "lat", "lng", "region", "criticality"):
        assert col in facilities.columns
    for col in ("src_facility_id", "dst_facility_id", "kind"):
        assert col in edges.columns


@pytest.mark.asyncio
async def test_load_registry_region_filter() -> None:
    fac_all, _, _ = await load_registry(user_assertion="")
    fac_tx, _, _ = await load_registry(user_assertion="", region_filter="TX")
    assert len(fac_tx) <= len(fac_all)
    assert all(r.upper() == "TX" for r in fac_tx["region"].astype(str).tolist())


@pytest.mark.asyncio
async def test_load_bcp_playbooks_seed() -> None:
    pb, source = await load_bcp_playbooks()
    assert source == "seed"
    assert len(pb) >= 5
    for col in ("playbook_id", "title", "hazards", "facility_hint", "summary"):
        assert col in pb.columns


@pytest.mark.asyncio
async def test_load_bcp_playbooks_hazard_filter() -> None:
    heat_pb, _ = await load_bcp_playbooks(hazards=["heat"])
    fire_pb, _ = await load_bcp_playbooks(hazards=["wildfire"])
    assert len(heat_pb) >= 1
    assert len(fire_pb) >= 1
    # Each row in heat_pb must have 'heat' in its hazards list.
    for haz in heat_pb["hazards"].tolist():
        assert any(str(h).lower() == "heat" for h in haz)


@pytest.mark.asyncio
async def test_load_bcp_playbooks_facility_filter_admits_broad_playbooks() -> None:
    """Playbooks with empty facility_hint should pass the facility filter
    (treated as broadly-applicable). Playbooks with hints must intersect."""
    # Pick a real facility id from the loaded registry so the test stays
    # in sync with the seed JSON.
    facilities, _, _ = await load_registry(user_assertion="")
    real_id = str(facilities.iloc[0]["facility_id"])

    pb, _ = await load_bcp_playbooks(facility_ids=[real_id])
    assert len(pb) >= 1
    for hint in pb["facility_hint"].tolist():
        hint_list = hint if isinstance(hint, (list, tuple)) else []
        assert (not hint_list) or (real_id in hint_list)
