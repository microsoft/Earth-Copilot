"""
Agents Package for Earth Copilot Container App

This package contains agents for various AI-powered analysis tasks:
- EnhancedVisionAgent: Semantic Kernel agent with LLM-based tool selection for analyzing
  satellite imagery, answering contextual questions, and providing quantitative analysis.
  
Tools available in EnhancedVisionAgent:
1. analyze_screenshot - GPT-4o vision analysis of map screenshot
2. analyze_raster - Quantitative analysis (elevation, NDVI, etc.)
3. query_knowledge - Educational/contextual LLM responses
4. compare_locations - Compare features between areas
5. identify_features - Identify geographic features
"""

from .enhanced_vision_agent import EnhancedVisionAgent, VisionAgent, get_vision_agent, get_enhanced_vision_agent

__all__ = [
    "EnhancedVisionAgent",
    "VisionAgent",  # Backwards compatibility alias
    "get_vision_agent",
    "get_enhanced_vision_agent",
]
