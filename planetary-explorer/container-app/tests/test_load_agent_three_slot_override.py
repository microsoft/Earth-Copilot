"""Regression tests for the LoadAgent three-slot structural override.

These lock in the user-reported repros where the LLM kept emitting
``action='clarify'`` for fully-specified LOAD requests:

  * "Show MTBS burn severity for California in 2017"
    (asked statewide-vs-county + classified-vs-dNBR)
  * "Show me chloris biomass for the Amazon rainforest"
    (asked which Amazon extent + which AGB layer)

The structural fix says: if (a) Layer-1 / payload supplies a location,
AND (b) the LLM itself extracted a ``stac_query`` or candidate (proving
it parsed a data noun), AND (c) time is present OR intent is snapshot
(latest-available default), then force ``action='execute'`` regardless
of what the LLM said. This is keyword-free.
"""

from __future__ import annotations

import json
import os
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

os.environ.setdefault("AZURE_OPENAI_ENDPOINT", "https://example.invalid")

from agents.load_agent.load_agent import LoadAgent
from agents.load_agent.load_agent_models import (
    DatetimeSlot,
    LoadAgentInput,
    LoadPlan,
    LocationSlot,
)


def _llm_clarify_plan_dict(
    stac_query: str,
    top_collection_id: str | None = None,
    intent: str = "snapshot",
) -> dict:
    """Build a LoadPlan dict that mimics the buggy LLM behavior: clarify with
    a populated stac_query (proof it understood the data noun)."""
    candidates = []
    if top_collection_id:
        candidates = [
            {"id": top_collection_id, "title": top_collection_id, "reason": "ranked"}
        ]
    return {
        "intent": intent,
        "location": {"name": None, "suggested_bbox": None, "needs_geocoding": False},
        "datetime": {"ambiguous": False, "range": None, "suggestions": []},
        "collection_candidates": candidates,
        "deliverable": "single_layer",
        "action": "clarify",
        "stac_query": stac_query,
        "chat_summary": "Loading imagery. Which variant did you want?",
        "clarification_question": "Which variant did you want?",
        "options": ["A", "B"],
    }


async def _run_with_mocked_llm(
    payload: LoadAgentInput, mocked_plan_dict: dict
) -> LoadPlan:
    """Run LoadAgent.plan() with the LLM client patched to return our dict."""
    agent = LoadAgent()
    fake_client = MagicMock()
    fake_choice = MagicMock()
    fake_choice.message.content = json.dumps(mocked_plan_dict)
    fake_response = MagicMock()
    fake_response.choices = [fake_choice]
    fake_client.chat.completions.create = AsyncMock(return_value=fake_response)
    with patch.object(agent, "_get_client", return_value=fake_client), patch(
        "agents.load_agent.load_agent._fetch_catalog_candidates",
        new=AsyncMock(return_value=[]),
    ):
        return await agent.plan(payload)


@pytest.mark.asyncio
async def test_override_fires_for_mtbs_california_2017():
    """Repro: 'Show MTBS burn severity for California in 2017' must execute."""
    payload = LoadAgentInput(
        query="Show MTBS burn severity for California in 2017",
        location_name="California",
    )
    mocked = _llm_clarify_plan_dict(stac_query="mtbs", top_collection_id="mtbs")
    plan = await _run_with_mocked_llm(payload, mocked)
    assert plan.action == "execute", (
        f"three-slot override should have fired; got clarify with "
        f"question={plan.clarification_question!r}"
    )
    assert plan.clarification_question is None
    assert plan.stac_query


@pytest.mark.asyncio
async def test_override_fires_for_chloris_amazon_no_time():
    """Repro: 'Show me chloris biomass for the Amazon rainforest'.

    No time in the query. Snapshot intent defaults to latest-available.
    Must execute — NOT clarify on which Amazon extent / which AGB layer.
    """
    payload = LoadAgentInput(
        query="Show me chloris biomass for the Amazon rainforest",
        location_name="Amazon rainforest",
    )
    mocked = _llm_clarify_plan_dict(
        stac_query="chloris biomass", top_collection_id="chloris-biomass"
    )
    plan = await _run_with_mocked_llm(payload, mocked)
    assert plan.action == "execute", (
        f"snapshot intent without explicit time should still execute; got "
        f"clarify with question={plan.clarification_question!r}"
    )
    assert plan.stac_query


@pytest.mark.asyncio
async def test_override_holds_when_llm_extracted_only_candidate_no_stac_query():
    """LLM emitted a candidate but no stac_query string. Still counts as
    'family signal present' because candidates are the LLM's own ranking."""
    payload = LoadAgentInput(
        query="Show me chloris biomass for the Amazon rainforest",
        location_name="Amazon rainforest",
    )
    mocked = _llm_clarify_plan_dict(
        stac_query="", top_collection_id="chloris-biomass"
    )
    plan = await _run_with_mocked_llm(payload, mocked)
    assert plan.action == "execute"


@pytest.mark.asyncio
async def test_override_does_NOT_fire_when_location_missing():
    """No location → clarify is legitimate."""
    payload = LoadAgentInput(
        query="Show me chloris biomass",
        location_name=None,
    )
    mocked = _llm_clarify_plan_dict(stac_query="chloris biomass")
    plan = await _run_with_mocked_llm(payload, mocked)
    assert plan.action == "clarify"


@pytest.mark.asyncio
async def test_override_does_NOT_fire_when_data_noun_missing():
    """No stac_query AND no candidates AND no keyword AND no catalog match
    → the LLM had nothing to work with, clarify is legitimate."""
    payload = LoadAgentInput(
        query="What's at this location?",
        location_name="California",
    )
    mocked = _llm_clarify_plan_dict(stac_query="", top_collection_id=None)
    plan = await _run_with_mocked_llm(payload, mocked)
    assert plan.action == "clarify"


@pytest.mark.asyncio
async def test_temporal_change_still_requires_time():
    """For temporal_change intent, time IS required — clarify is legitimate
    when dates aren't provided."""
    payload = LoadAgentInput(
        query="Compare chloris biomass over time in the Amazon",
        location_name="Amazon rainforest",
    )
    mocked = _llm_clarify_plan_dict(
        stac_query="chloris biomass",
        top_collection_id="chloris-biomass",
        intent="temporal_change",
    )
    plan = await _run_with_mocked_llm(payload, mocked)
    assert plan.action == "clarify"
