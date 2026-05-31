"""Unit tests for the Resilience planner's tool catalogue.

The planner LLM is not exercised here — only the deterministic tools
backing it. Each test forces seed-mode so the run is hermetic.

Covers:
  * tool dispatch table matches the schema list
  * simulate_outage walks the supply graph and aggregates volume
  * compare_periods diffs two assessment runs (skipped when MAF absent)
  * find_similar_facilities filters by type + criticality bucket
  * query_facilities applies registry filters without scoring
  * search_playbooks filters by hazard + region

Mark `compare_periods` and `run_standard_assessment` with an
`agent_framework` availability guard — they boot the full workflow.
"""

from __future__ import annotations

import os

import pytest

os.environ["RESILIENCE_FORCE_SEED"] = "1"

from agents.resilience import tools  # noqa: E402  (after env)


# ─────────────────────────────────────────────────────────────────────────
# Catalogue invariants
# ─────────────────────────────────────────────────────────────────────────
def test_tool_schemas_and_dispatch_match() -> None:
    """Every advertised schema has a callable, and vice versa."""
    schema_names = {s["function"]["name"] for s in tools.TOOL_SCHEMAS}
    dispatch_names = set(tools.TOOL_DISPATCH)
    assert schema_names == dispatch_names, (
        f"schema vs dispatch drift: missing dispatch={schema_names - dispatch_names} "
        f"missing schema={dispatch_names - schema_names}"
    )


# ─────────────────────────────────────────────────────────────────────────
# query_facilities — pure registry read
# ─────────────────────────────────────────────────────────────────────────
@pytest.mark.asyncio
async def test_query_facilities_region_filter() -> None:
    """region_filter=TX returns 10 seed rows; CA returns zero."""
    tx = await tools.query_facilities(region_filter="TX")
    assert tx["count"] == 10
    assert all(f["region"] == "TX" for f in tx["facilities"])
    assert tx["provenance"][0]["source"] == "facility_registry"

    ca = await tools.query_facilities(region_filter="CA")
    assert ca["count"] == 0


@pytest.mark.asyncio
async def test_query_facilities_type_and_criticality() -> None:
    """type=fab + min_criticality keeps only the most critical fabs."""
    res = await tools.query_facilities(facility_type="fab", min_criticality=0.8)
    assert res["count"] >= 1
    for f in res["facilities"]:
        assert f["type"] == "fab"
        assert float(f["criticality"]) >= 0.8


# ─────────────────────────────────────────────────────────────────────────
# search_playbooks
# ─────────────────────────────────────────────────────────────────────────
@pytest.mark.asyncio
async def test_search_playbooks_hazard_filter() -> None:
    res = await tools.search_playbooks(query="heat dome", hazards=["heat"], region="TX")
    assert res["count"] >= 1
    for pb in res["playbooks"]:
        haz_lower = {h.lower() for h in pb.get("hazards") or []}
        assert "heat" in haz_lower


# ─────────────────────────────────────────────────────────────────────────
# simulate_outage — the headline counterfactual
# ─────────────────────────────────────────────────────────────────────────
@pytest.mark.asyncio
async def test_simulate_outage_walks_supply_graph() -> None:
    """Houston Port has known downstream edges in the seed graph."""
    res = await tools.simulate_outage(
        facility_id="tx-dc-houston-01", days=5, max_hops=3
    )
    assert res["source_facility_id"] == "tx-dc-houston-01"
    assert res["total_downstream"] >= 1
    # Every impact row should carry the metadata the planner needs.
    for row in res["impacts"]:
        assert "hops_from_source" in row
        assert 1 <= row["hops_from_source"] <= 3
        assert "weekly_volume_at_risk" in row
        assert isinstance(row["buffered_by_lead_time"], bool)
    # Provenance covers both tables we read.
    sources = {p["source"] for p in res["provenance"]}
    assert {"facility_registry", "supply_edges"} <= sources


@pytest.mark.asyncio
async def test_simulate_outage_respects_max_hops() -> None:
    """max_hops=1 should never return a row past hop 1."""
    res = await tools.simulate_outage(
        facility_id="tx-fab-austin-01", days=3, max_hops=1
    )
    for row in res["impacts"]:
        assert row["hops_from_source"] == 1


@pytest.mark.asyncio
async def test_simulate_outage_unknown_source_returns_empty() -> None:
    """An unknown source facility produces an empty impact list, not an error."""
    res = await tools.simulate_outage(
        facility_id="nonexistent-facility-xyz", days=5
    )
    assert res["total_downstream"] == 0
    assert res["impacts"] == []


# ─────────────────────────────────────────────────────────────────────────
# find_similar_facilities
# ─────────────────────────────────────────────────────────────────────────
@pytest.mark.asyncio
async def test_find_similar_facilities_same_type() -> None:
    res = await tools.find_similar_facilities(
        reference_id="tx-fab-austin-01", same_type=True
    )
    assert "matches" in res
    # Should not include the reference itself.
    assert all(m["facility_id"] != "tx-fab-austin-01" for m in res["matches"])
    # All matches share the reference's type when same_type=True.
    assert all(m["type"] == res["reference"]["type"] for m in res["matches"])
    # Similarity score is in [0, 1].
    for m in res["matches"]:
        assert 0.0 <= m["similarity"] <= 1.0


@pytest.mark.asyncio
async def test_find_similar_facilities_unknown_id_returns_error() -> None:
    """Errors surface as {error: ...} so the planner can recover."""
    res = await tools.find_similar_facilities(reference_id="not-a-real-id")
    assert "error" in res


# ─────────────────────────────────────────────────────────────────────────
# run_standard_assessment + compare_periods — guarded by MAF availability
# ─────────────────────────────────────────────────────────────────────────
def _maf_available() -> bool:
    try:
        from agents.resilience.workflow import is_available
        return bool(is_available())
    except Exception:
        return False


@pytest.mark.asyncio
@pytest.mark.skipif(not _maf_available(), reason="agent_framework not installed")
async def test_run_standard_assessment_seed_mode() -> None:
    """Smoke: tool reaches the existing workflow and returns the dossier."""
    res = await tools.run_standard_assessment(
        region_filter="TX", horizon_days=3, hazards=["heat"],
        user_query="planner smoke test"
    )
    assert "facilities" in res
    assert "provenance" in res
    assert res.get("error") is None


@pytest.mark.asyncio
@pytest.mark.skipif(not _maf_available(), reason="agent_framework not installed")
async def test_compare_periods_returns_diffs() -> None:
    res = await tools.compare_periods(
        region_filter="TX", hazards=["heat"],
        horizon_a_days=3, horizon_b_days=7,
        label_a="short", label_b="long",
    )
    assert "diffs" in res
    assert res["n_facilities"] >= 1
    # Diff rows have the labelled scores.
    sample = res["diffs"][0]
    assert "short_score" in sample
    assert "long_score" in sample
    assert "delta" in sample
