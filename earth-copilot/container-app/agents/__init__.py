"""
Agents Package for Earth Copilot Container App

This package contains agents for AI-powered analysis tasks:
- EnhancedVisionAgent: Azure AI Agent Service agent with 13 vision tools for analyzing
  satellite imagery, answering contextual questions, and providing quantitative analysis.

Refactored from Semantic Kernel to Azure AI Agent Service (AgentsClient + FunctionTool).

Tools available in EnhancedVisionAgent:
1. analyze_screenshot - GPT-5 vision analysis of map screenshot
2. analyze_raster - Quantitative analysis (elevation, NDVI, SST, etc.)
3. analyze_vegetation - MODIS/optical vegetation analysis
4. analyze_fire - Fire detection and burn severity
5. analyze_land_cover - Land cover classification
6. analyze_snow - Snow/ice cover analysis
7. analyze_sar - SAR/radar analysis
8. analyze_water - Water occurrence and flood detection
9. analyze_biomass - Above-ground biomass analysis
10. sample_raster_value - Extract pixel value at a point
11. query_knowledge - Educational/contextual LLM responses
12. identify_features - Identify geographic features
13. compare_temporal - Temporal change detection
"""

from .enhanced_vision_agent import EnhancedVisionAgent, VisionAgent, get_vision_agent, get_enhanced_vision_agent

__all__ = [
    "EnhancedVisionAgent",
    "VisionAgent",  # Backwards compatibility alias
    "get_vision_agent",
    "get_enhanced_vision_agent",
]
