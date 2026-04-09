"""
GEOINT Building Damage Assessment Tools for Azure AI Agent Service

Standalone functions for building damage analysis, compatible with
Azure AI Agent Service FunctionTool.

Usage:
    from geoint.building_damage_tools import create_building_damage_functions
    functions = create_building_damage_functions()
    tool = AsyncFunctionTool(functions)
"""

import logging
import json
import asyncio
import concurrent.futures
import os
import base64
from typing import Dict, Any, Set, Callable, Optional

logger = logging.getLogger(__name__)

# ── Module-level screenshot context ──────────────────────────────────────
# Set by building_damage_agent.py before an agent run so tools can use
# the user's high-res map screenshot instead of fetching 10 m Sentinel-2.
_current_screenshot_base64: Optional[str] = None
_current_latitude: Optional[float] = None
_current_longitude: Optional[float] = None


def set_screenshot_context(screenshot_base64: Optional[str],
                           latitude: Optional[float] = None,
                           longitude: Optional[float] = None) -> None:
    """Store the user's current map screenshot for tool use."""
    global _current_screenshot_base64, _current_latitude, _current_longitude
    _current_screenshot_base64 = screenshot_base64
    _current_latitude = latitude
    _current_longitude = longitude
    if screenshot_base64:
        logger.info(f"Screenshot context set ({len(screenshot_base64)} chars) at ({latitude}, {longitude})")
    else:
        logger.info("Screenshot context cleared")


def clear_screenshot_context() -> None:
    """Clear screenshot context after agent run completes."""
    global _current_screenshot_base64, _current_latitude, _current_longitude
    _current_screenshot_base64 = None
    _current_latitude = None
    _current_longitude = None


def _analyze_screenshot_with_vision_sync(screenshot_base64: str, latitude: float,
                                          longitude: float, user_query: str) -> Dict:
    """Analyze the user's map screenshot with GPT-5 Vision (sync wrapper).

    Uses the high-resolution screenshot the user is actually looking at
    instead of fetching low-res Sentinel-2 imagery.
    """
    from openai import AzureOpenAI
    from azure.identity import DefaultAzureCredential, get_bearer_token_provider
    from cloud_config import cloud_cfg

    credential = DefaultAzureCredential()
    token_provider = get_bearer_token_provider(credential, cloud_cfg.cognitive_services_scope)

    client = AzureOpenAI(
        azure_ad_token_provider=token_provider,
        api_version=os.getenv("AZURE_OPENAI_API_VERSION", "2025-01-01-preview"),
        azure_endpoint=os.getenv("AZURE_OPENAI_ENDPOINT"),
        timeout=60.0,
    )

    clean_base64 = screenshot_base64
    if screenshot_base64.startswith("data:image"):
        clean_base64 = screenshot_base64.split(",", 1)[1]

    system_prompt = (
        "You are a damage assessment analyst specializing in building and infrastructure "
        "damage evaluation from aerial and satellite imagery.\n\n"
        "Analyze the provided image for signs of building damage, structural deterioration, "
        "or disaster impact. Focus on:\n"
        "- Building structural integrity (intact vs damaged roofs, walls)\n"
        "- Debris patterns indicating collapse or damage\n"
        "- Fire damage indicators (burn scars, charred areas)\n"
        "- Flood damage indicators (water staining, debris accumulation)\n"
        "- Infrastructure damage (roads, bridges, utilities)\n"
        "- Construction activity vs. destruction\n"
        "- Damage severity levels (No Damage, Minor, Major, Destroyed)\n\n"
        "Provide specific observations about what you see in the image."
    )

    user_prompt = (
        f"Analyze this image at ({latitude:.4f}, {longitude:.4f}) for building damage.\n"
        f"User question: {user_query}\n\n"
        "Provide a structured damage assessment with severity classification and "
        "specific observations about building conditions visible in the image."
    )

    response = client.chat.completions.create(
        model=os.getenv("AZURE_OPENAI_DEPLOYMENT_NAME", "gpt-5"),
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": [
                {"type": "text", "text": user_prompt},
                {"type": "image_url", "image_url": {
                    "url": f"data:image/png;base64,{clean_base64}",
                    "detail": "high",
                }},
            ]},
        ],
        max_completion_tokens=1500,
        temperature=1.0,
    )

    analysis = response.choices[0].message.content
    logger.info(f"Screenshot vision analysis complete: {len(analysis)} chars")

    return {
        "visual_analysis": analysis,
        "features_identified": [],
        "imagery_metadata": {
            "source": "User map screenshot",
            "resolution": "High (user's current zoom level)",
            "note": "Analyzed from the user's current map view, not Sentinel-2",
        },
        "confidence": 0.90,
    }


def _run_vision_analysis_sync(latitude: float, longitude: float, module_type: str,
                               radius_miles: float, user_query: str) -> Dict:
    """Run the async VisionAnalyzer in a dedicated thread with its own event loop.

    This avoids conflicts with the Agent SDK's running event loop.
    """
    from geoint.vision_analyzer import get_vision_analyzer
    vision_analyzer = get_vision_analyzer()

    def _run():
        loop = asyncio.new_event_loop()
        try:
            return loop.run_until_complete(
                vision_analyzer.analyze_location_with_vision(
                    latitude=latitude,
                    longitude=longitude,
                    module_type=module_type,
                    radius_miles=radius_miles,
                    user_query=user_query,
                    additional_context=None,
                )
            )
        finally:
            loop.close()

    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
        return pool.submit(_run).result(timeout=180)


def assess_building_damage(latitude: float, longitude: float, radius_miles: float = 5.0) -> str:
    """Assess building damage at a location using the user's current map view or satellite imagery.
    Returns damage severity classification and structural integrity assessment.
    Use this when the user asks about building damage, structural damage, disaster impact, or damage assessment.

    :param latitude: Center latitude of the assessment area
    :param longitude: Center longitude of the assessment area
    :param radius_miles: Radius in miles for analysis area (default 5.0)
    :return: JSON string with damage assessment results including severity and visual analysis
    """
    try:
        # Prefer the user's high-res map screenshot over fetching 10 m Sentinel-2
        if _current_screenshot_base64 and len(_current_screenshot_base64) > 5000:
            logger.info("Using user's map screenshot for damage assessment (high-res)")
            vision_result = _analyze_screenshot_with_vision_sync(
                _current_screenshot_base64, latitude, longitude,
                "Assess building damage and structural integrity in this location",
            )
        else:
            logger.info("No screenshot available — falling back to Sentinel-2 imagery")
            vision_result = _run_vision_analysis_sync(
                latitude, longitude, "building_damage", radius_miles,
                "Assess building damage and structural integrity in this location",
            )
        return json.dumps({
            "location": {"latitude": latitude, "longitude": longitude},
            "radius_miles": radius_miles,
            "visual_assessment": vision_result.get("visual_analysis"),
            "features_identified": vision_result.get("features_identified", []),
            "imagery_metadata": vision_result.get("imagery_metadata", {}),
            "confidence": vision_result.get("confidence", 0.0),
            "methodology": vision_result.get("imagery_metadata", {}).get("note",
                "LLM Vision analysis of satellite imagery for structural damage indicators")
        })
    except Exception as e:
        logger.error(f"Building damage assessment failed: {e}")
        return json.dumps({
            "location": {"latitude": latitude, "longitude": longitude},
            "status": "error",
            "message": f"Unable to perform damage assessment: {str(e)}. Satellite imagery may not be available."
        })


def classify_damage_severity(latitude: float, longitude: float) -> str:
    """Classify damage severity at a location into standard categories:
    No Damage, Minor Damage, Major Damage, or Destroyed.
    Uses the user's current map view or satellite imagery.

    :param latitude: Center latitude of the assessment area
    :param longitude: Center longitude of the assessment area
    :return: JSON string with severity classification and confidence level
    """
    try:
        query = ("Classify the damage severity at this location. Use one of: "
                 "No Damage, Minor Damage, Major Damage, Destroyed. "
                 "Look for collapsed structures, debris, burn scars, water damage.")

        if _current_screenshot_base64 and len(_current_screenshot_base64) > 5000:
            logger.info("Using user's map screenshot for severity classification (high-res)")
            vision_result = _analyze_screenshot_with_vision_sync(
                _current_screenshot_base64, latitude, longitude, query,
            )
        else:
            logger.info("No screenshot available — falling back to Sentinel-2 imagery")
            vision_result = _run_vision_analysis_sync(
                latitude, longitude, "building_damage", 2.0, query,
            )
        return json.dumps({
            "location": {"latitude": latitude, "longitude": longitude},
            "visual_assessment": vision_result.get("visual_analysis"),
            "features_identified": vision_result.get("features_identified", []),
            "confidence": vision_result.get("confidence", 0.0),
            "categories": ["No Damage", "Minor Damage", "Major Damage", "Destroyed"],
            "methodology": vision_result.get("imagery_metadata", {}).get("note",
                "LLM Vision classification of satellite imagery")
        })
    except Exception as e:
        logger.error(f"Damage severity classification failed: {e}")
        return json.dumps({
            "location": {"latitude": latitude, "longitude": longitude},
            "status": "error",
            "message": f"Unable to classify damage severity: {str(e)}"
        })


def create_building_damage_functions() -> Set[Callable]:
    """Return the set of building damage tool functions for AsyncFunctionTool registration."""
    return {
        assess_building_damage,
        classify_damage_severity,
    }
