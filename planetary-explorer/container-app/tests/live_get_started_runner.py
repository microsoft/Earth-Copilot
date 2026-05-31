"""
Live Get-Started query runner.

Hits the deployed /api/query endpoint with every query from the Get-Started
panel and logs:
  - request payload
  - HTTP status + response action
  - parameter adherence for LOAD queries (collection_id, location_name, datetime)
  - the answer text (truncated)
  - which Layer-2 tool fired (if structured response exposes it)
  - pass / soft-fail / hard-fail per query

Outputs:
  - tests/live_results/run_<timestamp>.json     (full raw)
  - tests/live_results/run_<timestamp>.md       (markdown summary table)
  - prints a per-module pass/fail tally

Pass criteria (per user spec):
  - HTTP 200
  - non-empty answer / response
  - LOAD queries: collection_id matches expected; if datetime in query, response
    bbox/time_range reflects it; location_name matches the geocoded target
  - Layer-2 queries: response is non-empty and not a generic "I don't understand"
  - We DO NOT fail on tool-choice (LLM temperature). We just LOG the tool used.

Usage:
  $env:LIVE_API_URL = "https://ca-planetaryexplorer-dev-api.blackbeach-341b981f.eastus2.azurecontainerapps.io"
  python tests/live_get_started_runner.py
  python tests/live_get_started_runner.py --module M1   # subset
  python tests/live_get_started_runner.py --query stac_hls_athens   # single
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
import uuid
from dataclasses import dataclass, asdict, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import httpx


# ---------------------------------------------------------------------------
# Query Manifest
# ---------------------------------------------------------------------------
# Each case captures the exact Get-Started button text. For raster-sample /
# screenshot / terrain / mobility / extreme-weather cases we set `pin` to the
# center of the visible map after the LOAD step (or, for terrain/weather, the
# city itself).
#
# `expected` is a dict of soft assertions: keys we hope to see in the answer
# or structured payload. Missing keys are logged as "soft-fail" not hard-fail.

@dataclass
class QueryCase:
    id: str
    module: str
    query: str
    expected_collection: str | None = None   # STAC collection id (LOAD only)
    expected_location: str | None = None      # geocoded city/region
    expected_datetime: str | None = None      # ISO date or year if in query
    pin: dict | None = None                   # {lat, lng} for Layer-2
    load_first: str | None = None             # id of LOAD case to run first
    expected_tool: str | None = None          # AnalystAgent tool name
    notes: str = ""


# ---------- Module 1: STAC LOAD (Layer 1 only) ----------
M1_STAC = [
    # High-Resolution Imagery
    QueryCase("stac_hls_athens", "M1", "Show Harmonized Landsat Sentinel-2 imagery of Athens",
              expected_collection="hls2-s30", expected_location="Athens"),
    QueryCase("stac_hls_moscow_2024_11", "M1",
              "Show Harmonized Landsat Sentinel-2 (HLS) Version 2.0 images of Moscow from November 2024",
              expected_collection="hls2-s30", expected_location="Moscow",
              expected_datetime="2024-11"),
    QueryCase("stac_hls_dc", "M1", "Show HLS images of Washington DC",
              expected_collection="hls2-s30", expected_location="Washington"),
    # Fire
    QueryCase("stac_modis_california", "M1", "Show wildfire MODIS data for California",
              expected_collection="modis-14A1-061", expected_location="California"),
    QueryCase("stac_modis_australia_2025_06", "M1",
              "Show fire modis thermal anomalies daily activity for Australia from June 2025",
              expected_collection="modis-14A2-061", expected_location="Australia",
              expected_datetime="2025-06"),
    QueryCase("stac_mtbs_california_2017", "M1",
              "Show MTBS burn severity for California in 2017",
              expected_collection="mtbs", expected_location="California",
              expected_datetime="2017"),
    # Water
    QueryCase("stac_jrc_bangladesh", "M1", "Display JRC Global Surface Water in Bangladesh",
              expected_collection="jrc-gsw", expected_location="Bangladesh"),
    QueryCase("stac_modis_snow_quebec_2025_01", "M1",
              "Show modis snow cover daily for Quebec for January 2025",
              expected_collection="modis-10A1-061", expected_location="Quebec",
              expected_datetime="2025-01"),
    QueryCase("stac_sst_madagascar", "M1",
              "Show me Sea Surface Temperature near Madagascar",
              expected_collection="noaa-cdr-sea-surface-temperature-whoi",
              expected_location="Madagascar"),
    # Vegetation
    QueryCase("stac_modis_npp_sanjose", "M1",
              "Show modis net primary production for San Jose",
              expected_collection="modis-17A3HGF-061", expected_location="San Jose"),
    QueryCase("stac_chloris_amazon", "M1",
              "Show me chloris biomass for the Amazon rainforest",
              expected_collection="chloris-biomass", expected_location="Amazon"),
    QueryCase("stac_modis_vi_ukraine", "M1",
              "Show modis vedgetation indices for Ukraine",
              expected_collection="modis-13Q1-061", expected_location="Ukraine"),
    QueryCase("stac_cdl_florida", "M1",
              "Show USDA Cropland Data Layers (CDLs) for Florida",
              expected_collection="usda-cdl", expected_location="Florida"),
    QueryCase("stac_modis_brdf_mexico", "M1",
              "Show recent modis nadir BDRF adjusted reflectance for Mexico",
              expected_collection="modis-43A4-061", expected_location="Mexico"),
    # Elevation
    QueryCase("stac_dem_grand_canyon", "M1", "Show elevation map of Grand Canyon",
              expected_collection="cop-dem-glo-30", expected_location="Grand Canyon"),
    QueryCase("stac_alos_dem_galapagos", "M1",
              "Show ALOS World 3D-30m of Tomas de Berlanga",
              expected_collection="alos-dem", expected_location="Galapagos"),
    QueryCase("stac_hag_new_orleans", "M1",
              "Show USGS 3DEP Lidar Height above Ground for New Orleans",
              expected_collection="3dep-lidar-hag", expected_location="New Orleans"),
    QueryCase("stac_hag_denver", "M1",
              "Show USGS 3DEP Lidar Height above Ground for Denver, Colorado",
              expected_collection="3dep-lidar-hag", expected_location="Denver"),
    # Radar
    QueryCase("stac_s1rtc_baltimore", "M1", "Show Sentinel 1 RTC for Baltimore",
              expected_collection="sentinel-1-rtc", expected_location="Baltimore"),
    QueryCase("stac_alos_palsar_ecuador", "M1",
              "Show ALOS PALSAR Annual for Ecuador",
              expected_collection="alos-palsar-mosaic", expected_location="Ecuador"),
    QueryCase("stac_s1rtc_philippines", "M1",
              "Show Sentinel 1 Radiometrically Terrain Corrected (RTC) for Philippines",
              expected_collection="sentinel-1-rtc", expected_location="Philippines"),
]

# ---------- Module 2: Raster Sample ----------
# Pin = city centroid for the LOAD query.
M2_RASTER = [
    QueryCase("raster_ndvi_athens", "M2",
              "What is the NDVI value at this pin location?",
              pin={"lat": 37.9838, "lng": 23.7275},
              load_first="stac_hls_athens",
              expected_tool="sample_raster_value"),
    QueryCase("raster_reflectance_moscow", "M2",
              "Sample the surface reflectance bands at this location.",
              pin={"lat": 55.7558, "lng": 37.6173},
              load_first="stac_hls_moscow_2024_11",
              expected_tool="sample_raster_value"),
    QueryCase("raster_red_nir_dc", "M2",
              "What are the raster values for the red and NIR bands?",
              pin={"lat": 38.9072, "lng": -77.0369},
              load_first="stac_hls_dc",
              expected_tool="sample_raster_value"),
    QueryCase("raster_fire_california", "M2",
              "What is the fire confidence value (FireMask) at this pixel?",
              pin={"lat": 36.7783, "lng": -119.4179},
              load_first="stac_modis_california",
              expected_tool="sample_raster_value"),
    QueryCase("raster_frp_australia", "M2",
              "Sample the Fire Radiative Power (MaxFRP) at this location.",
              pin={"lat": -25.2744, "lng": 133.7751},
              load_first="stac_modis_australia_2025_06",
              expected_tool="sample_raster_value"),
    QueryCase("raster_mtbs_california", "M2",
              "What is the burn severity classification value at this point?",
              pin={"lat": 36.7783, "lng": -119.4179},
              load_first="stac_mtbs_california_2017",
              expected_tool="sample_raster_value"),
    QueryCase("raster_water_bangladesh", "M2",
              "What is the water occurrence percentage at this location?",
              pin={"lat": 23.6850, "lng": 90.3563},
              load_first="stac_jrc_bangladesh",
              expected_tool="sample_raster_value"),
    QueryCase("raster_ndsi_quebec", "M2",
              "Sample the NDSI (snow index) value at this point.",
              pin={"lat": 52.9399, "lng": -73.5491},
              load_first="stac_modis_snow_quebec_2025_01",
              expected_tool="sample_raster_value"),
    QueryCase("raster_sst_madagascar", "M2",
              "What is the sea surface temperature in Celsius at this ocean location?",
              pin={"lat": -18.7669, "lng": 46.8691},
              load_first="stac_sst_madagascar",
              expected_tool="sample_raster_value"),
    QueryCase("raster_npp_sanjose", "M2",
              "What is the Net Primary Production (NPP) value in kgC/m²/year at this location?",
              pin={"lat": 37.3382, "lng": -121.8863},
              load_first="stac_modis_npp_sanjose",
              expected_tool="sample_raster_value"),
    QueryCase("raster_chloris_amazon", "M2",
              "Sample the aboveground biomass value in tonnes/hectare at this forest location.",
              pin={"lat": -3.4653, "lng": -62.2159},
              load_first="stac_chloris_amazon",
              expected_tool="sample_raster_value"),
    QueryCase("raster_ndvi_ukraine", "M2",
              "What are the NDVI and EVI values at this agricultural field?",
              pin={"lat": 48.3794, "lng": 31.1656},
              load_first="stac_modis_vi_ukraine",
              expected_tool="sample_raster_value"),
    QueryCase("raster_cdl_florida", "M2",
              "What crop type code is at this location?",
              pin={"lat": 27.9944, "lng": -81.7603},
              load_first="stac_cdl_florida",
              expected_tool="sample_raster_value"),
    QueryCase("raster_brdf_mexico", "M2",
              "Sample the BRDF-adjusted reflectance values for bands 1-4.",
              pin={"lat": 23.6345, "lng": -102.5528},
              load_first="stac_modis_brdf_mexico",
              expected_tool="sample_raster_value"),
    QueryCase("raster_elev_grand_canyon", "M2",
              "What is the exact elevation in meters at this point?",
              pin={"lat": 36.1069, "lng": -112.1129},
              load_first="stac_dem_grand_canyon",
              expected_tool="sample_raster_value"),
    QueryCase("raster_alos_galapagos", "M2",
              "What is the ALOS DEM elevation value at this location?",
              pin={"lat": -0.7264, "lng": -90.3303},
              load_first="stac_alos_dem_galapagos",
              expected_tool="sample_raster_value"),
    QueryCase("raster_hag_new_orleans", "M2",
              "Sample the 3DEP LiDAR HAG raster. What is the height above ground in meters at this point?",
              pin={"lat": 29.9511, "lng": -90.0715},
              load_first="stac_hag_new_orleans",
              expected_tool="sample_raster_value"),
    QueryCase("raster_hag_denver", "M2",
              "Sample the LiDAR HAG raster. Is this a building (HAG > 3m) or ground level?",
              pin={"lat": 39.7392, "lng": -104.9903},
              load_first="stac_hag_denver",
              expected_tool="sample_raster_value"),
    QueryCase("raster_s1rtc_baltimore", "M2",
              "What are the VV and VH backscatter values in dB?",
              pin={"lat": 39.2904, "lng": -76.6122},
              load_first="stac_s1rtc_baltimore",
              expected_tool="sample_raster_value"),
    QueryCase("raster_palsar_ecuador", "M2",
              "Sample the HH and HV polarization values.",
              pin={"lat": -1.8312, "lng": -78.1834},
              load_first="stac_alos_palsar_ecuador",
              expected_tool="sample_raster_value"),
    QueryCase("raster_s1rtc_philippines", "M2",
              "What is the SAR backscatter at this location?",
              pin={"lat": 12.8797, "lng": 121.7740},
              load_first="stac_s1rtc_philippines",
              expected_tool="sample_raster_value"),
]

# ---------- Module 3: Screenshot / Vision describe ----------
# These need `imagery_base64`. We send a 1×1 transparent PNG to satisfy the
# field; the AnalystAgent's describe_map_screenshot tool should still fire even
# if the LLM can't see anything meaningful — the test is about routing.
M3_SCREENSHOT = [
    QueryCase("describe_hls_athens", "M3",
              "Describe what you see in this satellite image. What land cover types are visible?",
              pin={"lat": 37.9838, "lng": 23.7275},
              load_first="stac_hls_athens",
              expected_tool="describe_map_screenshot"),
    QueryCase("describe_hls_moscow", "M3",
              "What urban features can you identify in this image of Moscow?",
              pin={"lat": 55.7558, "lng": 37.6173},
              load_first="stac_hls_moscow_2024_11",
              expected_tool="describe_map_screenshot"),
    QueryCase("describe_hls_dc", "M3",
              "Describe the urban layout and green spaces visible in Washington DC.",
              pin={"lat": 38.9072, "lng": -77.0369},
              load_first="stac_hls_dc",
              expected_tool="describe_map_screenshot"),
    QueryCase("describe_fire_california", "M3",
              "Can you see any active fire hotspots or burn scars in this thermal imagery?",
              pin={"lat": 36.7783, "lng": -119.4179},
              load_first="stac_modis_california",
              expected_tool="describe_map_screenshot"),
    QueryCase("describe_fire_australia", "M3",
              "Describe the fire activity patterns visible in this thermal anomaly map.",
              pin={"lat": -25.2744, "lng": 133.7751},
              load_first="stac_modis_australia_2025_06",
              expected_tool="describe_map_screenshot"),
    QueryCase("describe_mtbs_burn_california", "M3",
              "What burn severity patterns do you see? Where are the most severely burned areas?",
              pin={"lat": 36.7783, "lng": -119.4179},
              load_first="stac_mtbs_california_2017",
              expected_tool="describe_map_screenshot"),
    QueryCase("describe_water_bangladesh", "M3",
              "Describe the water bodies and flood patterns visible in this water occurrence map.",
              pin={"lat": 23.6850, "lng": 90.3563},
              load_first="stac_jrc_bangladesh",
              expected_tool="describe_map_screenshot"),
    QueryCase("describe_snow_quebec", "M3",
              "What snow coverage patterns do you see? Are there any snow-free areas?",
              pin={"lat": 52.9399, "lng": -73.5491},
              load_first="stac_modis_snow_quebec_2025_01",
              expected_tool="describe_map_screenshot"),
    QueryCase("describe_sst_madagascar", "M3",
              "Describe the ocean temperature gradients visible. Where are the warmest/coldest waters?",
              pin={"lat": -18.7669, "lng": 46.8691},
              load_first="stac_sst_madagascar",
              expected_tool="describe_map_screenshot"),
    QueryCase("describe_npp_sanjose", "M3",
              "What vegetation productivity patterns do you see? Where is vegetation most productive?",
              pin={"lat": 37.3382, "lng": -121.8863},
              load_first="stac_modis_npp_sanjose",
              expected_tool="describe_map_screenshot"),
    QueryCase("describe_chloris_amazon", "M3",
              "Describe the biomass distribution visible. Where are the highest carbon stocks?",
              pin={"lat": -3.4653, "lng": -62.2159},
              load_first="stac_chloris_amazon",
              expected_tool="describe_map_screenshot"),
    QueryCase("describe_vi_ukraine", "M3",
              "Describe the vegetation health patterns. Which agricultural areas look most productive?",
              pin={"lat": 48.3794, "lng": 31.1656},
              load_first="stac_modis_vi_ukraine",
              expected_tool="describe_map_screenshot"),
    QueryCase("describe_cdl_florida", "M3",
              "What crop types and land use patterns can you identify in this agricultural map?",
              pin={"lat": 27.9944, "lng": -81.7603},
              load_first="stac_cdl_florida",
              expected_tool="describe_map_screenshot"),
    QueryCase("describe_brdf_mexico", "M3",
              "Describe the surface types visible in this reflectance image. Any notable features?",
              pin={"lat": 23.6345, "lng": -102.5528},
              load_first="stac_modis_brdf_mexico",
              expected_tool="describe_map_screenshot"),
    QueryCase("describe_dem_grand_canyon", "M3",
              "Describe the terrain features visible. Where are the canyon walls and rim?",
              pin={"lat": 36.1069, "lng": -112.1129},
              load_first="stac_dem_grand_canyon",
              expected_tool="describe_map_screenshot"),
    QueryCase("describe_alos_galapagos", "M3",
              "What volcanic and island terrain features can you identify in the Galapagos?",
              pin={"lat": -0.7264, "lng": -90.3303},
              load_first="stac_alos_dem_galapagos",
              expected_tool="describe_map_screenshot"),
    QueryCase("describe_hag_new_orleans", "M3",
              "What building heights and urban structures are visible in this LiDAR data?",
              pin={"lat": 29.9511, "lng": -90.0715},
              load_first="stac_hag_new_orleans",
              expected_tool="describe_map_screenshot"),
    QueryCase("describe_hag_denver", "M3",
              "Describe the building distribution and vegetation heights visible in Denver.",
              pin={"lat": 39.7392, "lng": -104.9903},
              load_first="stac_hag_denver",
              expected_tool="describe_map_screenshot"),
    QueryCase("describe_s1rtc_baltimore", "M3",
              "What surface types can you identify from the radar backscatter? Urban vs water areas?",
              pin={"lat": 39.2904, "lng": -76.6122},
              load_first="stac_s1rtc_baltimore",
              expected_tool="describe_map_screenshot"),
    QueryCase("describe_palsar_ecuador", "M3",
              "Describe the land cover patterns visible in this L-band radar image of Ecuador.",
              pin={"lat": -1.8312, "lng": -78.1834},
              load_first="stac_alos_palsar_ecuador",
              expected_tool="describe_map_screenshot"),
    QueryCase("describe_s1rtc_philippines", "M3",
              "What flood or water patterns can you identify in this radar imagery of the Philippines?",
              pin={"lat": 12.8797, "lng": 121.7740},
              load_first="stac_s1rtc_philippines",
              expected_tool="describe_map_screenshot"),
]

# ---------- Module 4 (Terrain), Module 5 (Mobility), Module 6 (Weather) ----------
# These queries come from the Vision/Terrain/Mobility/Weather panel in the user prompt.
# They are pin-based; no LOAD step required.

M4_TERRAIN = [
    QueryCase("terrain_grand_canyon", "M4",
              "What is the elevation and slope at this location?",
              pin={"lat": 36.1069, "lng": -112.1129},
              expected_tool="get_terrain_stats"),
    QueryCase("terrain_rainier", "M4",
              "Is this area flat enough for a helicopter landing zone?",
              pin={"lat": 46.8523, "lng": -121.7603},
              expected_tool="get_terrain_stats"),
    QueryCase("terrain_houston", "M4",
              "Is this low-lying area at flood risk?",
              pin={"lat": 29.7604, "lng": -95.3698},
              expected_tool="get_terrain_stats"),
]

M5_MOBILITY = [
    QueryCase("mobility_hindu_kush", "M5",
              "Can a vehicle traverse from here to the next valley?",
              pin={"lat": 34.4378, "lng": 70.4517},
              expected_tool="get_mobility_path"),
    QueryCase("mobility_kathmandu", "M5",
              "Identify suitable landing zones within 5 km of this pin.",
              pin={"lat": 27.7172, "lng": 85.3240},
              expected_tool="get_mobility_path"),
    QueryCase("mobility_darfur", "M5",
              "Plan a humanitarian corridor avoiding steep terrain.",
              pin={"lat": 13.6293, "lng": 25.3494},
              expected_tool="get_mobility_path"),
]

M6_WEATHER = [
    QueryCase("weather_bangkok_heat", "M6",
              "What are the projected daily maximum and minimum temperatures for Bangkok under the worst-case SSP585 scenario? Is extreme heat increasing?",
              pin={"lat": 13.7563, "lng": 100.5018},
              expected_tool="get_extreme_weather_projection"),
    QueryCase("weather_new_orleans_precip", "M6",
              "What is the projected annual precipitation and peak daily rainfall for New Orleans? How does this relate to coastal flood risk and storm surge?",
              pin={"lat": 29.9511, "lng": -90.0715},
              expected_tool="get_extreme_weather_projection"),
    QueryCase("weather_dhaka_monsoon", "M6",
              "What are the projected monsoon precipitation levels for Dhaka? Is peak daily rainfall increasing, and what does this mean for urban flooding?",
              pin={"lat": 23.8103, "lng": 90.4125},
              expected_tool="get_extreme_weather_projection"),
    QueryCase("weather_maputo_scenarios", "M6",
              "Compare the moderate (SSP245) and worst-case (SSP585) climate scenarios for Maputo. How do temperature and precipitation projections differ for this cyclone-prone coast?",
              pin={"lat": -25.9692, "lng": 32.5732},
              expected_tool="get_extreme_weather_projection"),
]

# Module 6's setup queries (geocode-only) — also worth validating
M6_SETUP = [
    QueryCase("setup_bangkok", "M1", "Bangkok, Thailand",
              expected_location="Bangkok"),
    QueryCase("setup_new_orleans", "M1", "New Orleans, Louisiana",
              expected_location="New Orleans"),
    QueryCase("setup_dhaka", "M1", "Dhaka, Bangladesh",
              expected_location="Dhaka"),
    QueryCase("setup_maputo", "M1", "Maputo, Mozambique",
              expected_location="Maputo"),
]

ALL_CASES = M1_STAC + M6_SETUP + M2_RASTER + M3_SCREENSHOT + M4_TERRAIN + M5_MOBILITY + M6_WEATHER


# ---------------------------------------------------------------------------
# 1x1 transparent PNG (base64) for screenshot module
# ---------------------------------------------------------------------------
TINY_PNG_B64 = (
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNkYAAAAAYAAjCB0C8AAAAASUVORK5CYII="
)


# ---------------------------------------------------------------------------
# Result types
# ---------------------------------------------------------------------------
@dataclass
class CaseResult:
    id: str
    module: str
    query: str
    request: dict
    http_status: int
    elapsed_ms: int
    action: str | None
    answer: str | None
    tool_used: str | None
    collection_id: str | None
    location_name: str | None
    datetime_used: str | None
    bbox: list | None
    structured_keys: list[str] = field(default_factory=list)
    error: str | None = None
    # Per-spec pass/fail buckets
    hard_passes: list[str] = field(default_factory=list)
    hard_fails: list[str] = field(default_factory=list)
    soft_fails: list[str] = field(default_factory=list)

    @property
    def passed(self) -> bool:
        return not self.hard_fails and self.http_status == 200


# ---------------------------------------------------------------------------
# Runner
# ---------------------------------------------------------------------------
def _extract_field(payload: Any, *keys: str) -> Any:
    """Walk dict for first matching key, depth-first."""
    if isinstance(payload, dict):
        for k in keys:
            if k in payload and payload[k] is not None:
                return payload[k]
        for v in payload.values():
            found = _extract_field(v, *keys)
            if found is not None:
                return found
    elif isinstance(payload, list):
        for item in payload:
            found = _extract_field(item, *keys)
            if found is not None:
                return found
    return None


def _flatten_keys(payload: Any, prefix: str = "", out: list[str] | None = None) -> list[str]:
    out = out if out is not None else []
    if isinstance(payload, dict):
        for k, v in payload.items():
            p = f"{prefix}.{k}" if prefix else k
            if isinstance(v, (dict, list)):
                _flatten_keys(v, p, out)
            else:
                out.append(p)
    return out


def _run_one(client: httpx.Client, base_url: str, case: QueryCase, session_id: str) -> CaseResult:
    body: dict = {
        "user_query": case.query,
        "session_id": session_id,
        "model": "gpt-5",
    }
    if case.pin:
        body["vision_pin"] = case.pin
    if case.module == "M3":
        body["imagery_base64"] = TINY_PNG_B64
        body["has_satellite_data"] = True
    elif case.load_first:
        body["has_satellite_data"] = True

    start = time.time()
    try:
        resp = client.post(f"{base_url}/api/query", json=body, timeout=120)
        elapsed_ms = int((time.time() - start) * 1000)
        try:
            payload = resp.json()
        except Exception:
            payload = {"_raw": resp.text[:2000]}
        http_status = resp.status_code
        error = None
    except Exception as e:
        elapsed_ms = int((time.time() - start) * 1000)
        payload = {}
        http_status = 0
        error = repr(e)

    action = _extract_field(payload, "action")
    answer = _extract_field(payload, "answer", "response", "chat_message", "message")
    if isinstance(answer, dict):
        answer = answer.get("text") or json.dumps(answer)[:500]
    if isinstance(answer, str):
        answer = answer.strip()

    tool_used = _extract_field(payload, "tool_used", "tool", "primary_tool")
    if not tool_used:
        # Look in plan / steps
        plan = _extract_field(payload, "plan")
        if isinstance(plan, dict):
            steps = plan.get("steps") or []
            if steps and isinstance(steps, list):
                tool_used = ",".join(
                    s.get("tool") or s.get("analyzer_id") or ""
                    for s in steps if isinstance(s, dict)
                )

    collection_id = _extract_field(payload, "collection_id", "collection")
    location_name = _extract_field(payload, "location_name", "location")
    datetime_used = _extract_field(payload, "datetime", "time_range", "date_range")
    if isinstance(datetime_used, dict):
        datetime_used = datetime_used.get("start") or json.dumps(datetime_used)
    bbox = _extract_field(payload, "bbox", "bounds")

    structured_keys = _flatten_keys(payload)[:50]

    res = CaseResult(
        id=case.id, module=case.module, query=case.query, request=body,
        http_status=http_status, elapsed_ms=elapsed_ms,
        action=str(action) if action is not None else None,
        answer=(answer[:600] if isinstance(answer, str) else None),
        tool_used=str(tool_used) if tool_used else None,
        collection_id=str(collection_id) if collection_id else None,
        location_name=str(location_name) if location_name else None,
        datetime_used=str(datetime_used) if datetime_used else None,
        bbox=bbox if isinstance(bbox, list) else None,
        structured_keys=structured_keys,
        error=error,
    )

    # ---- Validation ----
    if http_status != 200:
        res.hard_fails.append(f"http_{http_status}")
        if error:
            res.hard_fails.append("network_error")
        return res

    if not res.answer:
        res.hard_fails.append("empty_answer")
    else:
        res.hard_passes.append("nonempty_answer")

    if case.expected_collection:
        coll = (res.collection_id or "").lower()
        exp = case.expected_collection.lower()
        if exp in coll or coll in exp:
            res.hard_passes.append(f"collection={exp}")
        else:
            res.soft_fails.append(f"collection: expected~{exp} got={coll or '<none>'}")

    if case.expected_location:
        loc = (res.location_name or "").lower()
        # also try matching against the answer text
        answer_low = (res.answer or "").lower()
        target = case.expected_location.lower()
        if target in loc or target in answer_low:
            res.hard_passes.append(f"location~{target}")
        else:
            res.soft_fails.append(f"location: expected~{target} got={loc or '<none>'}")

    if case.expected_datetime:
        dt = (res.datetime_used or "")
        ans = (res.answer or "")
        if case.expected_datetime in dt or case.expected_datetime in ans:
            res.hard_passes.append(f"datetime~{case.expected_datetime}")
        else:
            res.soft_fails.append(f"datetime: expected~{case.expected_datetime} got={dt or '<none>'}")

    if case.expected_tool:
        tu = (res.tool_used or "").lower()
        if case.expected_tool.lower() in tu:
            res.hard_passes.append(f"tool={case.expected_tool}")
        else:
            res.soft_fails.append(f"tool: expected={case.expected_tool} got={tu or '<none>'}")

    return res


def _write_reports(results: list[CaseResult], out_dir: Path, run_id: str) -> tuple[Path, Path]:
    out_dir.mkdir(parents=True, exist_ok=True)
    json_path = out_dir / f"run_{run_id}.json"
    md_path = out_dir / f"run_{run_id}.md"

    json_path.write_text(
        json.dumps([asdict(r) for r in results], indent=2, default=str),
        encoding="utf-8",
    )

    # Markdown report
    by_mod: dict[str, list[CaseResult]] = {}
    for r in results:
        by_mod.setdefault(r.module, []).append(r)

    lines = [
        f"# Live Get-Started Run `{run_id}`",
        "",
        f"_Generated {datetime.now(timezone.utc).isoformat()}_",
        "",
        "## Summary",
        "",
        "| Module | Total | Passed | Hard-failed | Soft-fails |",
        "|---|---|---|---|---|",
    ]
    totals = [0, 0, 0, 0]
    for mod in sorted(by_mod.keys()):
        items = by_mod[mod]
        passed = sum(1 for r in items if r.passed)
        hardf = sum(1 for r in items if r.hard_fails)
        softf = sum(len(r.soft_fails) for r in items)
        totals[0] += len(items); totals[1] += passed; totals[2] += hardf; totals[3] += softf
        lines.append(f"| {mod} | {len(items)} | {passed} | {hardf} | {softf} |")
    lines.append(f"| **All** | **{totals[0]}** | **{totals[1]}** | **{totals[2]}** | **{totals[3]}** |")
    lines.append("")

    for mod in sorted(by_mod.keys()):
        lines.append(f"## {mod}")
        lines.append("")
        lines.append("| ID | Status | HTTP | Tool | Collection | Location | DateTime | Notes |")
        lines.append("|---|---|---|---|---|---|---|---|")
        for r in by_mod[mod]:
            status = "✅ PASS" if r.passed else "❌ FAIL"
            notes_parts = []
            if r.error:
                notes_parts.append(f"err={r.error[:80]}")
            if r.soft_fails:
                notes_parts.append("; ".join(r.soft_fails)[:200])
            notes = " / ".join(notes_parts) or "—"
            lines.append(
                f"| `{r.id}` | {status} | {r.http_status} | "
                f"`{r.tool_used or '—'}` | `{r.collection_id or '—'}` | "
                f"{r.location_name or '—'} | {r.datetime_used or '—'} | {notes} |"
            )
        lines.append("")
        # Detailed answers
        lines.append("<details><summary>Answers</summary>")
        lines.append("")
        for r in by_mod[mod]:
            lines.append(f"### `{r.id}` — _{r.elapsed_ms} ms_")
            lines.append(f"**Query:** {r.query}")
            lines.append("")
            lines.append("**Request:**")
            lines.append("```json")
            lines.append(json.dumps(r.request, indent=2))
            lines.append("```")
            lines.append("**Answer:**")
            lines.append("")
            lines.append(f"> {r.answer or '<empty>'}")
            lines.append("")
            if r.action:
                lines.append(f"_action_: `{r.action}`")
            if r.bbox:
                lines.append(f"_bbox_: `{r.bbox}`")
            lines.append("")
        lines.append("</details>")
        lines.append("")

    md_path.write_text("\n".join(lines), encoding="utf-8")
    return json_path, md_path


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--api", default=os.environ.get("LIVE_API_URL"),
                        help="Base URL of the deployed API")
    parser.add_argument("--module", default=None,
                        help="Run only this module (M1..M6)")
    parser.add_argument("--query", default=None,
                        help="Run only this query id")
    parser.add_argument("--limit", type=int, default=None,
                        help="Cap number of cases")
    args = parser.parse_args(argv)

    if not args.api:
        print("ERROR: --api or LIVE_API_URL is required", file=sys.stderr)
        return 2

    base_url = args.api.rstrip("/")
    cases = ALL_CASES
    if args.module:
        cases = [c for c in cases if c.module == args.module]
    if args.query:
        cases = [c for c in cases if c.id == args.query]
    if args.limit:
        cases = cases[: args.limit]

    if not cases:
        print("No cases match filter")
        return 1

    print(f"==> Running {len(cases)} cases against {base_url}")
    session_id = f"run-{uuid.uuid4().hex[:8]}"

    headers: dict[str, str] = {}
    token = os.environ.get("LIVE_API_TOKEN")
    if token:
        headers["Authorization"] = f"Bearer {token}"
        print(f"==> Using bearer token (len={len(token)})")

    results: list[CaseResult] = []
    with httpx.Client(verify=True, headers=headers) as client:
        for i, case in enumerate(cases, 1):
            # For Layer-2 cases that have a load_first, issue the LOAD first so
            # the session has loaded raster state (best-effort; we don't fail
            # the case if the LOAD itself errors).
            if case.load_first and not args.query:
                load_case = next((c for c in M1_STAC if c.id == case.load_first), None)
                if load_case is not None:
                    print(f"  [{i:3}/{len(cases)}] (priming) LOAD {load_case.id}")
                    _run_one(client, base_url, load_case, session_id)

            print(f"  [{i:3}/{len(cases)}] {case.module} {case.id}: {case.query[:70]}")
            r = _run_one(client, base_url, case, session_id)
            results.append(r)
            status = "PASS" if r.passed else "FAIL"
            print(f"        -> {status} http={r.http_status} tool={r.tool_used or '-'} "
                  f"coll={r.collection_id or '-'} loc={r.location_name or '-'}")
            if r.hard_fails:
                print(f"        hard: {r.hard_fails}")
            if r.soft_fails:
                print(f"        soft: {r.soft_fails}")

    run_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    out_dir = Path(__file__).parent / "live_results"
    json_path, md_path = _write_reports(results, out_dir, run_id)

    passed = sum(1 for r in results if r.passed)
    print()
    print("=" * 70)
    print(f"Total: {len(results)}  |  Passed: {passed}  |  Failed: {len(results) - passed}")
    print(f"JSON: {json_path}")
    print(f"Markdown: {md_path}")
    return 0 if passed == len(results) else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
