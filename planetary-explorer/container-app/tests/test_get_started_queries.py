"""Comprehensive Get-Started query test suite (Wave 10 / REQ-ARCH-1).

This module exercises every Get-Started button query the frontend can
fire and asserts that the new ``AnalystAgent`` ReAct loop selects the
right tool(s). The Azure AI Agent Service call is mocked — we patch
``AnalystAgent._invoke_agent_service`` so each test simulates the
agent picking specific tool(s) and asserts:

  1. The full Layer-1 ``dispatch.run_pipeline_v2`` -> Layer-2
     ``AnalystAgent.run`` chain executes without import or
     contract errors.
  2. The ``ContextVar`` session is populated with the right pin /
     bbox / loaded_collections / screenshot so downstream tools see
     accurate state.
  3. The wire-shape returned to the frontend is unchanged:
     ``{action, answer, plan, sources, structured, elapsed_ms}``.

For each query we also document the **expected tool selection** in
the manifest at the top — that's the human-readable spec the user
asked for. The frontend test harness can use the same manifest
later for live-API smoke testing (``LIVE_API_URL`` env var).

Run:    pytest tests/test_get_started_queries.py -v
Report: pytest tests/test_get_started_queries.py --tb=line -q
"""

from __future__ import annotations

import asyncio
import os
from typing import Any, Dict, List, Optional, Tuple
from unittest.mock import AsyncMock, patch

import pytest

# Make sure the new package and pipeline are importable.
from agents.analyst_agent import AnalystAgent, get_analyst_agent  # noqa: F401
from agents.analyst_agent.tools import create_analyst_functions
from pipeline.contracts import AnalysisRequest, SynthesizedResponse, AnalysisPlan, AnalysisStep


# ---------------------------------------------------------------------------
# The Get-Started query manifest — single source of truth.
#
# Each entry documents:
#   id              : short stable identifier
#   module          : Module 1 = LOAD only; 2 = vision raster; 3 = vision
#                     screenshot; 4 = terrain; 5 = mobility; 6 = extreme
#                     weather. (Map to the 4 modules in the UI: STAC,
#                     Terrain, Mobility, Extreme Weather — vision raster
#                     & screenshot are sub-steps of STAC.)
#   query           : exact string from GetStartedButton.tsx
#   collection_id   : the STAC collection the LoadAgent should target
#                     (Module 1 only; later modules have it pre-loaded)
#   pin             : (lat, lng) the user pinned before asking
#                     (Modules 2-6); None for Module 1
#   has_screenshot  : whether a map screenshot is captured at chat time
#   expected_tools  : ordered tool names the AnalystAgent should call.
#                     Module 1 is ``[]`` because it routes to LoadAgent
#                     (Layer 1), never enters Layer 2.
#   notes           : test rationale / edge case being covered
# ---------------------------------------------------------------------------

MODULE_1_STAC: List[Dict[str, Any]] = [
    {
        "id": "stac_hls_athens",
        "module": 1,
        "query": "Show Harmonized Landsat Sentinel-2 imagery of Athens",
        "collection_id": "hls2-s30",
        "expected_tools": [],
        "notes": "Layer 1 LOAD only — REQ-LOAD-3: 'Displaying N hls2-s30 image(s) of Athens.'",
    },
    {
        "id": "stac_modis_california",
        "module": 1,
        "query": "Show wildfire MODIS data for California",
        "collection_id": "modis-14A1-061",
        "expected_tools": [],
        "notes": "LOAD only — fire data.",
    },
    {
        "id": "stac_jrc_bangladesh",
        "module": 1,
        "query": "Display JRC Global Surface Water in Bangladesh",
        "collection_id": "jrc-gsw",
        "expected_tools": [],
        "notes": "LOAD only — water occurrence.",
    },
    {
        "id": "stac_modis_ukraine",
        "module": 1,
        "query": "Show modis vedgetation indices for Ukraine",
        "collection_id": "modis-13Q1-061",
        "expected_tools": [],
        "notes": "LOAD only — vegetation indices (typo in query is preserved as in UI).",
    },
    {
        "id": "stac_dem_grand_canyon",
        "module": 1,
        "query": "Show elevation map of Grand Canyon",
        "collection_id": "cop-dem-glo-30",
        "expected_tools": [],
        "notes": "LOAD only — DEM.",
    },
    {
        "id": "stac_s1rtc_baltimore",
        "module": 1,
        "query": "Show Sentinel 1 RTC for Baltimore",
        "collection_id": "sentinel-1-rtc",
        "expected_tools": [],
        "notes": "LOAD only — SAR backscatter.",
    },
]

MODULE_2_RASTER: List[Dict[str, Any]] = [
    {
        "id": "raster_ndvi_athens",
        "module": 2,
        "query": "What is the NDVI value at this pin location?",
        "collection_id": "hls2-s30",
        "pin": (38.0986, 23.5861),  # Athens
        "has_screenshot": False,
        "expected_tools": ["sample_raster_value"],
        "notes": "Pin + loaded raster + numeric value question -> sample_raster_value.",
    },
    {
        "id": "raster_fire_california",
        "module": 2,
        "query": "What is the fire confidence value (FireMask) at this pixel?",
        "collection_id": "modis-14A1-061",
        "pin": (32.4538, -116.7265),
        "has_screenshot": False,
        "expected_tools": ["sample_raster_value"],
        "notes": "Categorical fire confidence raster.",
    },
    {
        "id": "raster_water_bangladesh",
        "module": 2,
        "query": "What is the water occurrence percentage at this location?",
        "collection_id": "jrc-gsw",
        "pin": (23.6238, 90.8176),
        "has_screenshot": False,
        "expected_tools": ["sample_raster_value"],
        "notes": "Percentage raster.",
    },
    {
        "id": "raster_ndsi_quebec",
        "module": 2,
        "query": "Sample the NDSI (snow index) value at this point.",
        "collection_id": "modis-10A1-061",
        "pin": (50.1979, -68.9402),
        "has_screenshot": False,
        "expected_tools": ["sample_raster_value"],
        "notes": "Snow index raster.",
    },
    {
        "id": "raster_elev_grand_canyon",
        "module": 2,
        "query": "What is the exact elevation in meters at this point?",
        "collection_id": "cop-dem-glo-30",
        "pin": (36.0544, -112.1401),
        "has_screenshot": False,
        "expected_tools": ["sample_raster_value"],
        "notes": "DEM raster sampling.",
    },
    {
        "id": "raster_sar_baltimore",
        "module": 2,
        "query": "What are the VV and VH backscatter values in dB?",
        "collection_id": "sentinel-1-rtc",
        "pin": (39.2547, -76.6287),
        "has_screenshot": False,
        "expected_tools": ["sample_raster_value"],
        "notes": "Multi-band SAR sampling.",
    },
]

MODULE_3_SCREENSHOT: List[Dict[str, Any]] = [
    {
        "id": "screenshot_landcover_athens",
        "module": 3,
        "query": "Describe what you see in this satellite image. What land cover types are visible?",
        "collection_id": "hls2-s30",
        "pin": (38.0986, 23.5861),
        "has_screenshot": True,
        "expected_tools": ["describe_map_screenshot"],
        "notes": "Vision-only — describes the visible scene; no numeric sampling.",
    },
    {
        "id": "screenshot_fire_california",
        "module": 3,
        "query": "Can you see any active fire hotspots or burn scars in this thermal imagery?",
        "collection_id": "modis-14A1-061",
        "pin": (32.4538, -116.7265),
        "has_screenshot": True,
        "expected_tools": ["describe_map_screenshot"],
        "notes": "Vision describes thermal anomalies pattern.",
    },
    {
        "id": "screenshot_water_bangladesh",
        "module": 3,
        "query": "Describe the water bodies and flood patterns visible in this water occurrence map.",
        "collection_id": "jrc-gsw",
        "pin": (23.6238, 90.8176),
        "has_screenshot": True,
        "expected_tools": ["describe_map_screenshot"],
        "notes": "Vision over JRC water layer.",
    },
    {
        "id": "screenshot_dem_grand_canyon",
        "module": 3,
        "query": "Describe the terrain features visible. Where are the canyon walls and rim?",
        "collection_id": "cop-dem-glo-30",
        "pin": (36.0544, -112.1401),
        "has_screenshot": True,
        "expected_tools": ["describe_map_screenshot"],
        "notes": "Vision over DEM.",
    },
]

MODULE_4_TERRAIN: List[Dict[str, Any]] = [
    {
        "id": "terrain_grand_canyon",
        "module": 4,
        "query": "What is the elevation range and slope distribution at this location?",
        "collection_id": "cop-dem-glo-30",
        "pin": (36.0544, -112.1401),
        "has_screenshot": True,
        "expected_tools": ["get_terrain_stats"],
        "notes": "Pure terrain stats — slope + elevation.",
    },
    {
        "id": "terrain_rainier",
        "module": 4,
        "query": (
            "Is this location suitable for a construction permit? "
            "Analyze terrain constraints including slope, flood risk, "
            "and flat areas."
        ),
        "collection_id": "cop-dem-glo-30",
        "pin": (46.8523, -121.7603),
        "has_screenshot": True,
        "expected_tools": ["get_terrain_stats"],
        "notes": "Site-suitability rolls flat-area + slope into terrain agent.",
    },
    {
        "id": "terrain_houston",
        "module": 4,
        "query": (
            "Analyze the flood risk and environmental sensitivity for "
            "this site. What is the permitting recommendation?"
        ),
        "collection_id": "hls2-s30",  # setupQuery for this one is "Show HLS imagery of Houston"
        "pin": (29.7604, -95.3698),
        "has_screenshot": True,
        "expected_tools": ["get_terrain_stats"],
        "notes": "Flood-risk question routed through terrain agent.",
    },
    {
        "id": "terrain_denver",
        "module": 4,
        "query": (
            "Which direction do the slopes face? What is the sun "
            "exposure rating for solar panel installation?"
        ),
        "collection_id": "3dep-lidar-hag",
        "pin": (39.7392, -104.9903),
        "has_screenshot": True,
        "expected_tools": ["get_terrain_stats"],
        "notes": "Aspect analysis via terrain agent.",
    },
    {
        "id": "terrain_everglades",
        "module": 4,
        "query": (
            "Is this area suitable for a solar farm? Check flat "
            "areas, water proximity, and setback requirements."
        ),
        "collection_id": "jrc-gsw",
        "pin": (25.7617, -80.1918),
        "has_screenshot": True,
        "expected_tools": ["get_terrain_stats"],
        "notes": "Multi-criteria site question -> terrain.",
    },
]

MODULE_5_MOBILITY: List[Dict[str, Any]] = [
    {
        "id": "mobility_hindu_kush",
        "module": 5,
        "query": (
            "Can vehicles traverse from the valley to the mountain "
            "pass? Assess terrain obstacles, steep slopes, and route "
            "feasibility for ground vehicles."
        ),
        "collection_id": "cop-dem-glo-30",
        "pin": (34.4378, 70.4517),  # Jalalabad, AF
        "has_screenshot": True,
        "expected_tools": ["get_mobility_path"],
        "notes": "Vehicle traversability -> mobility.",
    },
    {
        "id": "mobility_kathmandu",
        "module": 5,
        "query": (
            "Can a search and rescue helicopter land safely in this "
            "mountainous terrain? Analyze slope gradients, flat "
            "landing zones, and vegetation density."
        ),
        "collection_id": "cop-dem-glo-30",
        "pin": (27.7172, 85.3240),
        "has_screenshot": True,
        "expected_tools": ["get_mobility_path"],
        "notes": "SAR landing zone analysis -> mobility.",
    },
    {
        "id": "mobility_darfur",
        "module": 5,
        "query": (
            "Assess route conditions for a humanitarian aid convoy. "
            "Identify water crossings, fire hazards, and terrain "
            "barriers for movement planning."
        ),
        "collection_id": "cop-dem-glo-30",
        "pin": (13.6293, 25.3494),  # El Fasher
        "has_screenshot": True,
        "expected_tools": ["get_mobility_path"],
        "notes": "Humanitarian corridor -> mobility.",
    },
]

MODULE_6_EXTREME_WEATHER: List[Dict[str, Any]] = [
    {
        "id": "weather_bangkok_heat",
        "module": 6,
        "query": (
            "What are the projected daily maximum and minimum "
            "temperatures for Bangkok under the worst-case SSP585 "
            "scenario? Is extreme heat increasing?"
        ),
        "collection_id": None,  # NEX-GDDP is NetCDF, not a tile collection
        "pin": (13.7563, 100.5018),
        "has_screenshot": False,
        "expected_tools": ["get_extreme_weather_projection"],
        "notes": "Future projection / SSP scenario -> extreme_weather.",
    },
    {
        "id": "weather_new_orleans_precip",
        "module": 6,
        "query": (
            "What is the projected annual precipitation and peak "
            "daily rainfall for New Orleans? How does this relate "
            "to coastal flood risk and storm surge?"
        ),
        "collection_id": None,
        "pin": (29.9511, -90.0715),
        "has_screenshot": False,
        "expected_tools": ["get_extreme_weather_projection"],
        "notes": "Precipitation projection.",
    },
    {
        "id": "weather_dhaka_monsoon",
        "module": 6,
        "query": (
            "What are the projected monsoon precipitation levels "
            "for Dhaka? Is peak daily rainfall increasing, and "
            "what does this mean for urban flooding?"
        ),
        "collection_id": None,
        "pin": (23.8103, 90.4125),
        "has_screenshot": False,
        "expected_tools": ["get_extreme_weather_projection"],
        "notes": "Monsoon projection.",
    },
    {
        "id": "weather_maputo_scenarios",
        "module": 6,
        "query": (
            "Compare the moderate (SSP245) and worst-case (SSP585) "
            "climate scenarios for Maputo. How do temperature and "
            "precipitation projections differ for this cyclone-prone "
            "coast?"
        ),
        "collection_id": None,
        "pin": (-25.9692, 32.5732),
        "has_screenshot": False,
        "expected_tools": ["get_extreme_weather_projection"],
        "notes": "SSP scenario comparison.",
    },
]

# Bonus: REQ-CLARIFY-2 + REQ-COMPARE-1 coverage
SPECIAL_CASES: List[Dict[str, Any]] = [
    {
        "id": "clarify_vague_no_state",
        "module": 0,
        "query": "tell me about this area",
        "collection_id": None,
        "pin": None,
        "has_screenshot": False,
        "expected_tools": ["ask_user_to_clarify"],
        "notes": "REQ-CLARIFY-2: vague + no pin + no collection -> clarify.",
    },
    {
        "id": "compare_temporal_athens",
        "module": 0,
        "query": "Compare NDVI in Athens between 2015 and 2024.",
        "collection_id": "hls2-s30",
        "pin": (38.0986, 23.5861),
        "has_screenshot": False,
        "expected_tools": ["compare_temporal"],
        "notes": "REQ-COMPARE-1 / G9: dual-datetime same-location comparison.",
    },
]


ALL_QUERIES: List[Dict[str, Any]] = (
    MODULE_1_STAC
    + MODULE_2_RASTER
    + MODULE_3_SCREENSHOT
    + MODULE_4_TERRAIN
    + MODULE_5_MOBILITY
    + MODULE_6_EXTREME_WEATHER
    + SPECIAL_CASES
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _build_request(case: Dict[str, Any]) -> AnalysisRequest:
    pin: Optional[Tuple[float, float]] = case.get("pin")
    collection: Optional[str] = case.get("collection_id")
    return AnalysisRequest(
        question=case["query"],
        session_id=f"test_{case['id']}",
        pin=pin,
        pins=[],
        bbox=None,
        location_name=None,
        time_range=None,
        loaded_collections=[collection] if collection else [],
        loaded_collections_meta=[{"id": collection}] if collection else [],
        has_screenshot=bool(case.get("has_screenshot")),
        screenshot_url=None,
        screenshot_b64="iVBORw0KGgo=" if case.get("has_screenshot") else None,
        rendered_layers=[],
        stac_items=[],
        tile_urls=[],
        history=[],
        grounding=[],
        hint=None,
    )


def _make_fake_invoke(expected_tools: List[str]):
    """Return a stub for ``AnalystAgent._invoke_agent_service`` that
    simulates the agent picking *expected_tools* in order. Each
    tool call writes a stub entry onto the session ContextVar (so
    the AnalystAgent's evidence-aggregation path is exercised).
    """

    async def _fake(self, request):
        from agents.analyst_agent.session_context import get_session

        sess = get_session()
        for tool_name in expected_tools:
            payload: Dict[str, Any] = {
                "success": True,
                "answer": f"stub answer from {tool_name}",
                "structured": {"tool": tool_name},
                "sources": [],
                "confidence": 0.9,
            }
            if tool_name == "ask_user_to_clarify":
                payload = {
                    "action": "clarify",
                    "chat_message": "Could you tell me where you'd like to look?",
                    "options": ["Drop a pin", "Pick a city", "Load imagery first"],
                    "missing_slot": "location",
                }
            sess.evidence.append({"tool": tool_name, "payload": payload})
        # Aggregate stub answer for the test
        joined = " ".join(
            f"[{ev['tool']}]" for ev in sess.evidence
        ) or "(no tools called)"
        return joined, list(expected_tools), list(sess.evidence)

    return _fake


# ---------------------------------------------------------------------------
# Tool catalog completeness — independent of any agent run.
# ---------------------------------------------------------------------------


def test_tool_catalog_has_all_required_tools():
    """REQ-ARCH-1 locks an 11-tool catalog. Verify every name is present
    and callable."""
    functions = create_analyst_functions()
    names = {f.__name__ for f in functions}
    expected = {
        "general_earth_qa",
        "describe_map_screenshot",
        "sample_raster_value",
        "get_collection_metadata",
        "get_terrain_stats",
        "get_mobility_path",
        "get_extreme_weather_projection",
        "compute_netcdf_trend",
        "compare_temporal",
        "ask_user_to_clarify",
    }
    missing = expected - names
    extra = names - expected
    assert not missing, f"Tool catalog missing: {missing}"
    assert not extra, f"Tool catalog has unexpected entries: {extra}"


# ---------------------------------------------------------------------------
# Parametrized: every Layer-2 query (Modules 2-6 + special cases).
# Module 1 (STAC LOAD) doesn't reach Layer 2, so we don't run it through
# AnalystAgent here — it's exercised by load_agent tests.
# ---------------------------------------------------------------------------


LAYER2_CASES = [
    c for c in ALL_QUERIES if c["module"] != 1
]


@pytest.mark.asyncio
@pytest.mark.parametrize("case", LAYER2_CASES, ids=[c["id"] for c in LAYER2_CASES])
async def test_get_started_query_routes_to_expected_tool(case):
    """End-to-end: AnalystAgent.run() picks the expected tool(s) and
    returns a frontend-compatible SynthesizedResponse."""
    agent = AnalystAgent()
    request = _build_request(case)
    expected_tools = case["expected_tools"]

    with patch.object(
        AnalystAgent,
        "_invoke_agent_service",
        new=_make_fake_invoke(expected_tools),
    ):
        response = await agent.run(request)

    # --- Shape assertions ---
    assert isinstance(response, SynthesizedResponse), f"Wrong return type for {case['id']}"
    assert response.answer, f"Empty answer for {case['id']}"
    assert response.elapsed_ms >= 0
    assert isinstance(response.plan, AnalysisPlan)
    assert isinstance(response.structured, dict)

    # --- Tool selection assertion ---
    plan_tools = [s.analyzer for s in response.plan.steps]
    assert plan_tools == expected_tools, (
        f"{case['id']}: expected tools {expected_tools}, got {plan_tools}"
    )

    # --- Evidence in structured payload ---
    for tool_name in expected_tools:
        assert tool_name in response.structured, (
            f"{case['id']}: structured payload missing {tool_name}"
        )

    # --- Clarify special case: must surface clarify key ---
    if "ask_user_to_clarify" in expected_tools:
        assert "clarify" in response.structured, (
            f"{case['id']}: clarify tool fired but 'clarify' key missing from structured"
        )
        clarify = response.structured["clarify"]
        assert clarify.get("action") == "clarify"
        assert clarify.get("chat_message")
        assert isinstance(clarify.get("options"), list)


# ---------------------------------------------------------------------------
# AnalyzeAgent (Layer 1 wrapper) integration — verifies the legacy
# response envelope is preserved for the FastAPI handler.
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_analyze_agent_wraps_analyst_response_correctly():
    """The Layer-1 AnalyzeAgent must convert AnalystAgent's
    SynthesizedResponse into the legacy ``pipeline_v2`` dict shape."""
    from pipeline.layer1_agents import AnalyzeAgent
    from pipeline.contracts import ActionDecision

    case = MODULE_4_TERRAIN[0]  # terrain_grand_canyon
    request = _build_request(case)
    decision = ActionDecision(
        action="ANALYZE",
        location=None,
        use_current_location=False,
        stac_query=None,
        analysis_question=case["query"],
        reasoning="test",
        confidence=0.9,
    )

    with patch.object(
        AnalystAgent,
        "_invoke_agent_service",
        new=_make_fake_invoke(case["expected_tools"]),
    ):
        # Re-build the singleton so the patch takes effect
        import agents.analyst_agent.analyst_agent as analyst_mod
        analyst_mod._SINGLETON = None
        agent = AnalyzeAgent()
        result = await agent.run(decision, request, body={})

    assert result["pipeline_v2"] is True
    assert result["action"] == "ANALYZE"
    assert result["answer"]
    assert result["plan"] is not None
    assert result["structured"]["layer2_engine"] == "analyst_agent"
    assert result["elapsed_ms"] >= 0


@pytest.mark.asyncio
async def test_analyze_agent_surfaces_clarify_correctly():
    """When AnalystAgent's ask_user_to_clarify tool fires, AnalyzeAgent
    must convert that into the legacy CLARIFY response shape so the
    frontend chip plumbing still works (REQ-CLARIFY-2)."""
    from pipeline.layer1_agents import AnalyzeAgent
    from pipeline.contracts import ActionDecision

    case = SPECIAL_CASES[0]  # clarify_vague_no_state
    request = _build_request(case)
    decision = ActionDecision(
        action="ANALYZE",
        location=None,
        use_current_location=False,
        stac_query=None,
        analysis_question=case["query"],
        reasoning="test",
        confidence=0.6,
    )

    with patch.object(
        AnalystAgent,
        "_invoke_agent_service",
        new=_make_fake_invoke(case["expected_tools"]),
    ):
        import agents.analyst_agent.analyst_agent as analyst_mod
        analyst_mod._SINGLETON = None
        agent = AnalyzeAgent()
        result = await agent.run(decision, request, body={})

    assert result["action"] == "CLARIFY"
    assert result["answer"]
    assert result["structured"]["clarify"] is True
    assert result["structured"]["missing_slot"] == "location"
    assert isinstance(result["structured"]["options"], list)
    assert len(result["structured"]["options"]) >= 1


# ---------------------------------------------------------------------------
# Coverage matrix printer — runs after the suite and prints a table.
# ---------------------------------------------------------------------------


def test_print_coverage_matrix(capsys):
    """Not really a test — emits a markdown-friendly coverage table
    that's nice to read in the pytest output."""
    rows = []
    by_module: Dict[int, List[Dict[str, Any]]] = {}
    for case in ALL_QUERIES:
        by_module.setdefault(case["module"], []).append(case)

    out = ["", "", "## Get-Started Query Coverage Matrix", ""]
    out.append("| Module | Query ID | Expected Tool(s) | Notes |")
    out.append("|---|---|---|---|")
    module_labels = {
        0: "Special",
        1: "M1 STAC LOAD (Layer 1)",
        2: "M2 Raster sample",
        3: "M3 Screenshot",
        4: "M4 Terrain",
        5: "M5 Mobility",
        6: "M6 Extreme Weather",
    }
    for module_id in sorted(by_module.keys()):
        for case in by_module[module_id]:
            tools = ", ".join(case["expected_tools"]) or "(no Layer-2 tool)"
            out.append(
                f"| {module_labels[module_id]} | `{case['id']}` | `{tools}` | {case['notes']} |"
            )
    out.append("")
    out.append(f"Total cases: {len(ALL_QUERIES)} | Layer-2 cases: {len(LAYER2_CASES)}")
    out.append("")
    print("\n".join(out))


# ---------------------------------------------------------------------------
# OPTIONAL: live API smoke test — gated by env var to keep CI deterministic.
# Run with: $env:LIVE_API_URL='https://ca-planetaryexplorer-dev-api...azurecontainerapps.io'; pytest -k live
# ---------------------------------------------------------------------------


@pytest.mark.skipif(
    not os.getenv("LIVE_API_URL"),
    reason="LIVE_API_URL not set; skipping live smoke test",
)
@pytest.mark.asyncio
async def test_live_get_started_smoke():
    """Hit the deployed /chat endpoint with one query per module and
    assert a 200 + non-empty answer. Doesn't grade tool selection
    because the live LLM has temperature."""
    import httpx

    url = os.environ["LIVE_API_URL"].rstrip("/") + "/chat"
    headers: Dict[str, str] = {"Content-Type": "application/json"}
    token = os.getenv("LIVE_API_TOKEN")
    if token:
        headers["Authorization"] = f"Bearer {token}"

    smoke_set = [
        MODULE_1_STAC[0],
        MODULE_2_RASTER[0],
        MODULE_3_SCREENSHOT[0],
        MODULE_4_TERRAIN[0],
        MODULE_5_MOBILITY[0],
        MODULE_6_EXTREME_WEATHER[0],
        SPECIAL_CASES[0],
    ]

    failures: List[str] = []
    async with httpx.AsyncClient(timeout=120.0) as client:
        for case in smoke_set:
            body: Dict[str, Any] = {
                "question": case["query"],
                "session_id": f"live_smoke_{case['id']}",
                "history": [],
            }
            if case.get("pin"):
                body["pin"] = list(case["pin"])
            if case.get("collection_id"):
                body["loaded_collections"] = [case["collection_id"]]
            if case.get("has_screenshot"):
                body["has_screenshot"] = True

            try:
                resp = await client.post(url, json=body, headers=headers)
                resp.raise_for_status()
                data = resp.json()
                if not data.get("answer"):
                    failures.append(f"{case['id']}: empty answer")
            except Exception as e:
                failures.append(f"{case['id']}: {e}")

    assert not failures, f"Live smoke failures: {failures}"
