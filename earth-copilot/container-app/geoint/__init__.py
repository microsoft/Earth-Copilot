"""
GEOINT (Geospatial Intelligence) Module

This module provides geospatial intelligence analysis capabilities through agent-based architecture.

Available Agents:
- TerrainAgent - Real SK agent with memory, tools, and multi-turn chat (NEW)
- ComparisonAgent - Temporal before/after comparison with dual STAC queries (NEW)
- terrain_analysis_agent - Visual terrain feature analysis using GPT-5 Vision (legacy)
- mobility_analysis_agent - Pixel-based terrain trafficability assessment
- building_damage_agent - Structural damage analysis
- comparison_analysis_agent - Temporal change detection
- animation_generation_agent - Time-series visualization
- geoint_orchestrator - Coordinates multiple GEOINT analyses

Available Tools (for TerrainAgent):
- get_elevation_analysis - DEM-based elevation stats
- get_slope_analysis - Terrain steepness
- get_aspect_analysis - Slope direction
- get_vegetation_index - NDVI calculation
- identify_water_bodies - NDWI water detection
- find_flat_areas - Landing zone identification

Architecture:
All GEOINT functionality now follows agent-based pattern for consistency.
The new TerrainAgent uses Semantic Kernel with proper tool calling and memory.
Each legacy agent function returns Dict[str, Any] with "agent" key.

IMPORTANT: Lazy imports are used throughout to avoid loading heavy dependencies
(like rasterio) until actually needed. This allows terrain analysis to work
without loading mobility analysis dependencies.
"""

from .agents import (
    terrain_analysis_agent,
    mobility_analysis_agent,
    building_damage_agent,
    comparison_analysis_agent,
    animation_generation_agent,
    geoint_orchestrator
)

# New agent with memory and tools
from .terrain_agent import TerrainAgent, get_terrain_agent

# Comparison agent for temporal before/after analysis
from .comparison_agent import ComparisonAgent, get_comparison_agent

# Legacy class exports for backward compatibility
# NOTE: These are lazy-imported within their respective agent functions
# Importing them here would defeat the lazy loading strategy
# If you need the classes directly, import from their modules:
#   from geoint.mobility_agent import GeointMobilityAgent
#   from geoint.terrain_analysis_agent import TerrainAnalysisAgent
#   from geoint.building_damage_agent import BuildingDamageAgent

# Router Agent for intelligent query classification
from .router_agent import RouterAgent, get_router_agent

__all__ = [
    # Agent functions (preferred)
    'terrain_analysis_agent',
    'mobility_analysis_agent',
    'building_damage_agent',
    'comparison_analysis_agent',
    'animation_generation_agent',
    'geoint_orchestrator',
    # New agents with memory
    'TerrainAgent',
    'get_terrain_agent',
    'RouterAgent',
    'get_router_agent',
]

