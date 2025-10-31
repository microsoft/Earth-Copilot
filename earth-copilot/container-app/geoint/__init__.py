"""
GEOINT (Geospatial Intelligence) Module

This module provides geospatial intelligence analysis capabilities through agent-based architecture.

Available Agents:
- terrain_analysis_agent - Visual terrain feature analysis using GPT-5 Vision
- mobility_analysis_agent - Pixel-based terrain trafficability assessment
- building_damage_agent - Structural damage analysis
- comparison_analysis_agent - Temporal change detection
- animation_generation_agent - Time-series visualization
- geoint_orchestrator - Coordinates multiple GEOINT analyses

Architecture:
All GEOINT functionality now follows agent-based pattern for consistency.
Each agent function returns Dict[str, Any] with "agent" key.

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

# Legacy class exports for backward compatibility
# NOTE: These are lazy-imported within their respective agent functions
# Importing them here would defeat the lazy loading strategy
# If you need the classes directly, import from their modules:
#   from geoint.mobility_agent import GeointMobilityAgent
#   from geoint.terrain_analysis_agent import TerrainAnalysisAgent
#   from geoint.building_damage_agent import BuildingDamageAgent

__all__ = [
    # Agent functions (preferred)
    'terrain_analysis_agent',
    'mobility_analysis_agent',
    'building_damage_agent',
    'comparison_analysis_agent',
    'animation_generation_agent',
    'geoint_orchestrator',
]

