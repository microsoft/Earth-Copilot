"""Tests for the planner's narrative-synthesis fallback.

The PlannerExecutor's `_ensure_narrative` pass guarantees that every
investigative dossier handed to the chat panel carries a human-readable
markdown answer in `dossier["narrative"]`, even when the main planner
loop under-fills the field. These tests verify both branches:

  * a dossier that already has a long narrative is returned untouched;
  * a dossier with a too-short narrative is synthesized via a single
    LLM call against compact evidence extracted from the dossier.
"""

from __future__ import annotations

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from agents.resilience.planner import (
    MIN_NARRATIVE_CHARS,
    PlannerExecutor,
    PlannerRequest,
)


@pytest.fixture
def sample_request() -> PlannerRequest:
    return PlannerRequest(
        user_query="Which TX fabs are exposed to the heat dome this week?",
        region_filter="TX",
        horizon_days=7,
        hazards=["heat"],
    )


@pytest.fixture
def sample_dossier_with_narrative() -> dict:
    return {
        "summary": "3 of 7 TX fabs at risk.",
        "narrative": (
            "Heat exposure is concentrated at the Austin and Round Rock fabs, where "
            "apparent temperatures peak above 108 °F on Thursday and Friday. Cooling "
            "water margins narrow but stay above the action threshold. Recommend "
            "pre-staging chillers at Round Rock; lead time is 2 days."
        ),
        "facilities": [],
        "provenance": [],
    }


@pytest.fixture
def sample_dossier_thin() -> dict:
    return {
        "summary": "Heat risk elevated.",
        "narrative": "Hot week ahead.",  # too short, triggers synthesis
        "facilities": [
            {
                "facility_id": "austin-fab-3",
                "name": "Austin Fab 3",
                "type": "fab",
                "region": "TX",
                "overall_risk": 78,
                "severity": "high",
                "hazards": {"heat": {"score": 78, "peak_value": 108}},
            }
        ],
        "provenance": [{"source": "facility_registry", "lakehouse": "fabric"}],
    }


@pytest.mark.asyncio
async def test_ensure_narrative_keeps_long_existing_narrative(
    sample_request, sample_dossier_with_narrative
):
    """When the planner already produced a real narrative, do not call the LLM."""
    executor = PlannerExecutor()
    with patch("agents.resilience.planner._get_aoai_client") as mock_client_fn:
        out = await executor._ensure_narrative(
            sample_request, dict(sample_dossier_with_narrative), trace=[]
        )
    # No client call — the narrative is long enough.
    mock_client_fn.assert_not_called()
    assert out["narrative"] == sample_dossier_with_narrative["narrative"]
    assert len(out["narrative"]) >= MIN_NARRATIVE_CHARS


@pytest.mark.asyncio
async def test_ensure_narrative_synthesises_when_thin(
    sample_request, sample_dossier_thin
):
    """When narrative is too short, run a synthesis pass and replace it."""
    synthesized = (
        "**Bottom line:** Austin Fab 3 is the most exposed Texas fab this week, "
        "hitting an apparent 108 °F on Thursday (risk 78/100, severity HIGH).\n\n"
        "- Cooling-water margins stay above the action threshold, but the\n"
        "  consecutive-day heat will compound throughput risk on the line.\n"
        "- Recommend pre-staging chillers at the Round Rock DC (lead time 2 days)."
    )
    fake_resp = SimpleNamespace(
        choices=[SimpleNamespace(message=SimpleNamespace(content=synthesized))]
    )
    fake_client = SimpleNamespace(
        chat=SimpleNamespace(
            completions=SimpleNamespace(create=AsyncMock(return_value=fake_resp))
        )
    )

    executor = PlannerExecutor()
    with patch(
        "agents.resilience.planner._get_aoai_client", return_value=fake_client
    ):
        out = await executor._ensure_narrative(
            sample_request,
            dict(sample_dossier_thin),
            trace=[
                {"hop": 0, "tool": "query_facilities", "args": {}, "result_keys": []},
                {
                    "hop": 1,
                    "tool": "list_mpc_stac_collections",
                    "args": {},
                    "result_keys": [],
                },
                {
                    "hop": 2,
                    "tool": "run_standard_assessment",
                    "args": {},
                    "result_keys": [],
                },
            ],
        )

    # Synthesized narrative replaced the thin one and is now substantial.
    assert out["narrative"] == synthesized
    assert len(out["narrative"]) >= MIN_NARRATIVE_CHARS
    # And the LLM was actually invoked exactly once.
    fake_client.chat.completions.create.assert_awaited_once()


@pytest.mark.asyncio
async def test_ensure_narrative_survives_llm_failure(
    sample_request, sample_dossier_thin
):
    """If the synthesis LLM call fails, fall back gracefully (no crash)."""
    executor = PlannerExecutor()
    with patch(
        "agents.resilience.planner._get_aoai_client",
        side_effect=RuntimeError("AOAI offline"),
    ):
        out = await executor._ensure_narrative(
            sample_request, dict(sample_dossier_thin), trace=[]
        )
    # Function must return a dossier with *some* narrative field present —
    # never raise. The thin original is preserved verbatim in this case.
    assert "narrative" in out
    assert isinstance(out["narrative"], str)
    assert out["narrative"]  # non-empty


def test_planner_system_prompt_mentions_both_grounding_sources():
    """The system prompt must teach the model about Fabric + MPC public so
    the contract documented in the chat / backlog is enforced in-prompt."""
    from agents.resilience.planner import PLANNER_SYSTEM

    p = PLANNER_SYSTEM
    # Fabric grounding cues
    assert "Fabric" in p
    assert "query_facilities" in p
    assert "run_standard_assessment" in p
    # MPC public grounding cues
    assert "Planetary Computer" in p
    assert "list_mpc_stac_collections" in p
    assert "search_mpc_stac_items" in p
    # Dynamic collection routing instruction
    assert "collection" in p.lower()
    # Chat-friendly output contract
    assert "narrative" in p
    assert "markdown" in p.lower()


def test_router_defaults_to_investigative():
    """The router must default to the planner path; deterministic DAG is opt-in."""
    from agents.resilience.planner import ROUTER_SYSTEM

    assert "investigative" in ROUTER_SYSTEM
    assert "Default to" in ROUTER_SYSTEM
