"""
GEOINT Building Damage Assessment Agent

This agent analyzes building damage using GPT-5 Vision on satellite imagery.
Future enhancements will include CNN-Siamese network integration for automated
damage detection and comparison analysis.

Analysis Components:
- Visual damage assessment via GPT-5 Vision
- Building structural integrity evaluation
- Damage severity classification (No damage, Minor, Major, Destroyed)
- Infrastructure impact assessment

Future Integration:
- CNN-Siamese network from /building-damage-assessment-cnn-siamese repo
- Pre/post disaster imagery comparison
- Automated building-level damage classification
"""

from typing import Dict, Any, Optional, List
import logging
from datetime import datetime

logger = logging.getLogger(__name__)


class BuildingDamageAgent:
    """
    GEOINT Building Damage Assessment Agent
    
    Analyzes building damage and structural integrity using:
    - GPT-5 Vision for visual damage assessment
    - Satellite imagery comparison (future: CNN-Siamese)
    - Damage severity classification
    """
    
    def __init__(self):
        """Initialize the Building Damage Agent."""
        self.name = "geoint_building_damage"
        self.radius_miles = 5  # Analysis radius from pin drop point
        
        logger.info("✅ BuildingDamageAgent initialized")
    
    async def analyze_building_damage(
        self,
        latitude: float,
        longitude: float,
        user_context: Optional[str] = None,
        include_vision_analysis: bool = True
    ) -> Dict[str, Any]:
        """
        Perform building damage assessment for a pinned location.
        
        Args:
            latitude: Pin drop latitude
            longitude: Pin drop longitude
            user_context: Optional context from chat
            include_vision_analysis: Whether to include GPT-5 Vision analysis (default True)
            
        Returns:
            Dict containing damage assessment results
        """
        logger.info(f"🏗️ Starting building damage analysis at ({latitude}, {longitude})")
        
        # GPT-5 Vision analysis
        vision_analysis = None
        if include_vision_analysis:
            logger.info("🔍 Performing GPT-5 Vision damage assessment...")
            try:
                from geoint.vision_analyzer import get_vision_analyzer
                
                vision_analyzer = get_vision_analyzer()
                
                vision_result = await vision_analyzer.analyze_location_with_vision(
                    latitude=latitude,
                    longitude=longitude,
                    module_type="building_damage",
                    radius_miles=self.radius_miles,
                    user_query="Assess building damage and structural integrity in this location",
                    additional_context=None
                )
                
                vision_analysis = vision_result
                logger.info("✅ Vision damage assessment completed")
                
            except Exception as e:
                logger.error(f"⚠️ Vision analysis failed: {e}")
                vision_analysis = None
        
        # Generate summary
        summary = self._generate_damage_summary(
            latitude, longitude, vision_analysis, user_context
        )
        
        result = {
            "agent": "geoint_building_damage",
            "location": {"latitude": latitude, "longitude": longitude},
            "radius_miles": self.radius_miles,
            "summary": summary,
            "timestamp": datetime.utcnow().isoformat(),
            "data_sources": [],
            "status": "vision_analysis_only"  # Will change when CNN-Siamese is integrated
        }
        
        # Add vision analysis if available
        if vision_analysis:
            result["vision_analysis"] = {
                "visual_assessment": vision_analysis.get("visual_analysis"),
                "features_identified": vision_analysis.get("features_identified", []),
                "imagery_metadata": vision_analysis.get("imagery_metadata", {}),
                "confidence": vision_analysis.get("confidence", 0.0)
            }
            if vision_analysis.get("imagery_metadata", {}).get("source"):
                result["data_sources"].append(f"{vision_analysis['imagery_metadata']['source']} (GPT-5 Vision)")
        
        return result
    
    def _generate_damage_summary(
        self,
        latitude: float,
        longitude: float,
        vision_analysis: Optional[Dict[str, Any]],
        user_context: Optional[str]
    ) -> str:
        """
        Generate natural language summary of damage assessment.
        """
        summary_parts = [
            f"## 🏗️ Building Damage Assessment",
            f"**Location:** {latitude:.4f}°N, {longitude:.4f}°E",
            f"**Analysis Radius:** {self.radius_miles} miles\n"
        ]
        
        if vision_analysis and vision_analysis.get("visual_analysis"):
            summary_parts.append(f"### 🔍 GPT-5 Visual Damage Assessment:\n")
            summary_parts.append(vision_analysis["visual_analysis"])
            
            if vision_analysis.get("features_identified"):
                summary_parts.append("")
                summary_parts.append(f"**Damage Indicators Identified:** {', '.join(vision_analysis['features_identified'])}")
            
            if vision_analysis.get("imagery_metadata"):
                meta = vision_analysis["imagery_metadata"]
                summary_parts.append("")
                summary_parts.append(f"**Imagery:** {meta.get('source', 'Unknown')} ({meta.get('date', 'Unknown')[:10]}, {meta.get('resolution', 'Unknown')})")
            
            summary_parts.append("")
            summary_parts.append(f"### Methodology:")
            summary_parts.append(f"✅ **GPT-5 Vision Analysis** - Visual interpretation of satellite imagery")
            summary_parts.append(f"- **Damage Indicators:** Structural collapse, debris patterns, burn scars, water damage")
            summary_parts.append(f"- **Severity Classification:** No damage, Minor, Major, Destroyed")
            summary_parts.append(f"- **Infrastructure Assessment:** Roads, bridges, utilities impact")
            
            summary_parts.append("")
            summary_parts.append(f"### 🚧 Future Enhancements:")
            summary_parts.append(f"- **CNN-Siamese Network** - Automated building-level damage detection")
            summary_parts.append(f"- **Pre/Post Comparison** - Temporal change detection analysis")
            summary_parts.append(f"- **xBD Dataset Integration** - Training on disaster imagery database")
        else:
            summary_parts.append(f"### ⚠️ Analysis Status:")
            summary_parts.append(f"Unable to perform visual damage assessment. Satellite imagery may not be available for this location.")
            summary_parts.append("")
            summary_parts.append(f"**Note:** Building damage assessment requires clear satellite imagery. The area may be:")
            summary_parts.append(f"- Obscured by clouds")
            summary_parts.append(f"- Outside coverage area")
            summary_parts.append(f"- Lacking recent imagery")
        
        return "\n".join(summary_parts)
