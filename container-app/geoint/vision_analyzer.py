"""
Shared GPT-5 Vision Analysis Utility for GEOINT Modules

This module provides a reusable vision analysis capability that can be used
by all GEOINT modules (Terrain Analysis, Mobility Analysis, Building Damage).

Key Features:
- Fetches satellite imagery from Planetary Computer (Sentinel-2 RGB)
- Encodes images for GPT-5 Vision API
- Provides module-specific analysis prompts
- Returns structured analysis results
"""

from typing import Dict, Any, Optional, List, Literal
import logging
import os
import base64
from io import BytesIO
import aiohttp
from openai import AzureOpenAI
import planetary_computer
from datetime import datetime, timedelta
from pystac_client import Client

logger = logging.getLogger(__name__)

# Type for analysis modules
ModuleType = Literal["terrain", "mobility", "building_damage"]


class VisionAnalyzer:
    """
    Shared GPT-5 Vision analyzer for satellite imagery analysis.
    Can be used by any GEOINT module to add visual analysis capability.
    """
    
    def __init__(self):
        """Initialize the vision analyzer with Azure OpenAI."""
        # Support both AZURE_OPENAI_API_KEY and AZURE_OPENAI_KEY
        api_key = os.getenv("AZURE_OPENAI_API_KEY") or os.getenv("AZURE_OPENAI_KEY")
        api_version = os.getenv("AZURE_OPENAI_API_VERSION", "2025-01-01-preview")
        endpoint = os.getenv("AZURE_OPENAI_ENDPOINT")
        
        self.client = AzureOpenAI(
            api_key=api_key,
            api_version=api_version,
            azure_endpoint=endpoint,
            timeout=180.0  # 3 minute timeout for vision API calls
        )
        
        # Use GPT-5 deployment name
        self.deployment_name = os.getenv("AZURE_OPENAI_DEPLOYMENT_NAME", "gpt-5")
        self.stac_endpoint = "https://planetarycomputer.microsoft.com/api/stac/v1"
        
        logger.info(f"✅ VisionAnalyzer initialized with deployment: {self.deployment_name} (timeout: 180s)")
    
    async def analyze_location_with_vision(
        self,
        latitude: float,
        longitude: float,
        module_type: ModuleType,
        radius_miles: float = 5.0,
        user_query: Optional[str] = None,
        additional_context: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        Analyze a location using GPT-5 Vision on satellite imagery.
        
        Args:
            latitude: Center point latitude
            longitude: Center point longitude
            module_type: Which module is requesting analysis ("terrain", "mobility", "building_damage")
            radius_miles: Analysis radius in miles (default 5)
            user_query: Optional specific user question
            additional_context: Optional additional context from module-specific analysis
            
        Returns:
            Dict containing:
            - visual_analysis: str - Natural language description from GPT-5
            - features_identified: List[str] - Key features found
            - imagery_metadata: Dict - Info about imagery used
            - confidence: float - Analysis confidence score
        """
        try:
            logger.info(f"🔍 Starting vision analysis for {module_type} at ({latitude}, {longitude})")
            
            # Calculate bounding box
            radius_deg = radius_miles / 69.0
            bbox = [
                longitude - radius_deg,
                latitude - radius_deg,
                longitude + radius_deg,
                latitude + radius_deg
            ]
            
            # Fetch satellite imagery
            image_data, image_metadata = await self._fetch_satellite_image(
                bbox, latitude, longitude
            )
            
            if not image_data:
                return {
                    "visual_analysis": "Unable to retrieve satellite imagery for this location. The area may be obscured by clouds or outside available coverage.",
                    "features_identified": [],
                    "imagery_metadata": {},
                    "confidence": 0.0
                }
            
            # Analyze with GPT-5 Vision using module-specific prompt
            analysis_result = await self._analyze_image_with_vision(
                image_data=image_data,
                latitude=latitude,
                longitude=longitude,
                radius_miles=radius_miles,
                module_type=module_type,
                user_query=user_query,
                additional_context=additional_context,
                image_metadata=image_metadata
            )
            
            logger.info(f"✅ Vision analysis completed for {module_type}")
            
            return analysis_result
            
        except Exception as e:
            logger.error(f"❌ Vision analysis failed: {e}")
            return {
                "visual_analysis": f"Vision analysis failed: {str(e)}",
                "features_identified": [],
                "imagery_metadata": {},
                "confidence": 0.0
            }
    
    async def _fetch_satellite_image(
        self,
        bbox: List[float],
        center_lat: float,
        center_lon: float
    ) -> tuple[Optional[bytes], Dict[str, Any]]:
        """
        Fetch RGB satellite imagery from Sentinel-2 via Planetary Computer.
        
        Returns:
            Tuple of (image_bytes, metadata_dict)
        """
        try:
            logger.info("🛰️ Fetching Sentinel-2 imagery...")
            
            catalog = Client.open(
                self.stac_endpoint,
                modifier=planetary_computer.sign_inplace
            )
            
            # Search for recent imagery with minimal cloud cover
            search = catalog.search(
                collections=["sentinel-2-l2a"],
                bbox=bbox,
                datetime=f"{(datetime.now() - timedelta(days=60)).isoformat()}Z/{datetime.now().isoformat()}Z",
                query={"eo:cloud_cover": {"lt": 20}}
            )
            
            items = list(search.items())
            
            if not items:
                logger.warning("No recent Sentinel-2 imagery found")
                return None, {}
            
            # Get most recent item
            item = sorted(items, key=lambda x: x.datetime, reverse=True)[0]
            
            logger.info(f"📸 Found imagery from {item.datetime}")
            logger.info(f"   Cloud cover: {item.properties.get('eo:cloud_cover', 'unknown')}%")
            
            # Get RGB composite tile (512x512 pixels)
            tile_url = f"https://planetarycomputer.microsoft.com/api/data/v1/item/preview.png?collection=sentinel-2-l2a&item={item.id}&assets=visual&width=512&height=512"
            signed_tile_url = planetary_computer.sign_url(tile_url)
            
            # Fetch the image
            async with aiohttp.ClientSession() as session:
                async with session.get(signed_tile_url) as response:
                    if response.status == 200:
                        image_bytes = await response.read()
                        
                        metadata = {
                            "source": "Sentinel-2 L2A",
                            "date": item.datetime.isoformat(),
                            "cloud_cover": item.properties.get('eo:cloud_cover', 'unknown'),
                            "item_id": item.id,
                            "resolution": "10m RGB"
                        }
                        
                        logger.info(f"✅ Successfully fetched {len(image_bytes)} bytes of imagery")
                        return image_bytes, metadata
                    else:
                        logger.error(f"Failed to fetch tile: {response.status}")
                        return None, {}
            
        except Exception as e:
            logger.error(f"Error fetching satellite image: {e}")
            import traceback
            logger.error(traceback.format_exc())
            return None, {}
    
    async def _analyze_image_with_vision(
        self,
        image_data: bytes,
        latitude: float,
        longitude: float,
        radius_miles: float,
        module_type: ModuleType,
        user_query: Optional[str],
        additional_context: Optional[Dict[str, Any]],
        image_metadata: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Analyze satellite image using GPT-5 Vision with module-specific prompts.
        """
        import time
        
        try:
            logger.info(f"🤖 Analyzing image with GPT-5 Vision for {module_type}...")
            
            # Encode image to base64
            logger.info("📸 Encoding image to base64...")
            start_encode = time.time()
            base64_image = base64.b64encode(image_data).decode('utf-8')
            encode_time = time.time() - start_encode
            logger.info(f"✅ Image encoded in {encode_time:.2f}s ({len(base64_image)} chars)")
            
            # Build module-specific prompts
            logger.info("📝 Building prompts...")
            start_prompt = time.time()
            system_prompt, user_prompt = self._build_prompts(
                module_type=module_type,
                latitude=latitude,
                longitude=longitude,
                radius_miles=radius_miles,
                user_query=user_query,
                additional_context=additional_context,
                image_metadata=image_metadata
            )
            prompt_time = time.time() - start_prompt
            logger.info(f"✅ Prompts built in {prompt_time:.2f}s")
            
            # Call GPT-5 Vision
            logger.info("🧠 Calling GPT-5 Vision API (this may take 30-120 seconds)...")
            start_api = time.time()
            response = self.client.chat.completions.create(
                model=self.deployment_name,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {
                        "role": "user",
                        "content": [
                            {"type": "text", "text": user_prompt},
                            {
                                "type": "image_url",
                                "image_url": {
                                    "url": f"data:image/png;base64,{base64_image}"
                                }
                            }
                        ]
                    }
                ],
                max_completion_tokens=1500,
                temperature=1.0  # GPT-5 requires default temperature=1.0
            )
            api_time = time.time() - start_api
            logger.info(f"✅ GPT-5 Vision API completed in {api_time:.2f}s")
            
            analysis_text = response.choices[0].message.content
            
            # Extract features based on module type
            features_identified = self._extract_features(analysis_text, module_type)
            
            total_time = encode_time + prompt_time + api_time
            logger.info(f"✅ GPT-5 analysis completed ({len(analysis_text)} characters)")
            logger.info(f"   Features identified: {', '.join(features_identified[:5])}")
            logger.info(f"⏱️  Total time: {total_time:.2f}s (encode: {encode_time:.1f}s, prompt: {prompt_time:.1f}s, API: {api_time:.1f}s)")
            
            return {
                "visual_analysis": analysis_text,
                "features_identified": features_identified,
                "imagery_metadata": image_metadata,
                "confidence": 0.85,
                "location": {
                    "latitude": latitude,
                    "longitude": longitude,
                    "radius_miles": radius_miles
                }
            }
            
        except Exception as e:
            logger.error(f"Error analyzing image with GPT-5: {e}")
            import traceback
            logger.error(traceback.format_exc())
            raise
    
    def _build_prompts(
        self,
        module_type: ModuleType,
        latitude: float,
        longitude: float,
        radius_miles: float,
        user_query: Optional[str],
        additional_context: Optional[Dict[str, Any]],
        image_metadata: Dict[str, Any]
    ) -> tuple[str, str]:
        """
        Build module-specific system and user prompts for GPT-5 Vision.
        
        Returns:
            Tuple of (system_prompt, user_prompt)
        """
        
        # Base image description
        base_context = f"""Analyze this satellite image centered at coordinates ({latitude}, {longitude}) covering approximately {radius_miles} miles radius.

Image metadata:
- Source: {image_metadata.get('source', 'Unknown')}
- Date: {image_metadata.get('date', 'Unknown')}
- Resolution: {image_metadata.get('resolution', 'Unknown')}
"""
        
        if module_type == "terrain":
            system_prompt = """You are a geospatial intelligence analyst specializing in satellite imagery interpretation for terrain analysis. 

Analyze the provided satellite image and describe the terrain features visible within the area.

Focus on:
- Bodies of water (rivers, lakes, ponds, coastal areas, wetlands)
- Vegetation types and density (forests, grasslands, agricultural areas)
- Infrastructure (roads, buildings, bridges)
- Urban vs rural characteristics
- Terrain features (hills, valleys, plains, mountains)
- Land use patterns
- Any notable features or landmarks

Provide a clear, structured analysis that would be useful for intelligence purposes."""
            
            user_prompt = base_context
            if user_query:
                user_prompt += f"\nUser's specific question: {user_query}"
            user_prompt += "\n\nProvide a detailed terrain analysis in a structured format with clear sections."
        
        elif module_type == "mobility":
            system_prompt = """You are a military terrain analyst specializing in mobility and trafficability assessment from satellite imagery.

Analyze the provided satellite image for mobility considerations relevant to ground vehicle movement.

Focus on:
- Terrain trafficability (flat vs rough terrain, obstacles)
- Water obstacles (rivers, lakes, wetlands that impede movement)
- Vegetation density (dense forests that restrict mobility vs open areas)
- Road networks and their condition
- Urban areas (restrict movement but provide infrastructure)
- Slope indicators (shadows, terrain texture)
- Barriers to movement (cliffs, dense construction, water bodies)
- Mobility corridors (clear paths for vehicle movement)

Provide a tactical assessment focused on GO / SLOW-GO / NO-GO areas based on visual analysis."""
            
            user_prompt = base_context
            
            # Add context from algorithmic analysis if available
            if additional_context:
                user_prompt += "\n\nAlgorithmic terrain data analysis results:\n"
                if additional_context.get("water_detected"):
                    user_prompt += "- Water bodies detected via SAR analysis\n"
                if additional_context.get("steep_slopes"):
                    user_prompt += f"- Steep slopes detected: {additional_context.get('slope_summary', '')}\n"
                if additional_context.get("vegetation_dense"):
                    user_prompt += "- Dense vegetation detected via NDVI analysis\n"
                if additional_context.get("active_fires"):
                    user_prompt += "- Active fires detected in the area\n"
            
            if user_query:
                user_prompt += f"\nUser's specific question: {user_query}"
            
            user_prompt += "\n\nProvide a mobility assessment focusing on vehicle trafficability and movement corridors."
        
        elif module_type == "building_damage":
            system_prompt = """You are a damage assessment analyst specializing in building and infrastructure damage evaluation from satellite imagery.

Analyze the provided satellite image for signs of building damage, structural deterioration, or disaster impact.

Focus on:
- Building structural integrity (intact vs damaged roofs, walls)
- Debris patterns indicating collapse or damage
- Displacement of structures
- Fire damage indicators (burn scars, charred areas)
- Flood damage indicators (water staining, debris accumulation)
- Infrastructure damage (roads, bridges, utilities)
- Comparison patterns (if multiple timeframes visible)
- Damage severity levels (No damage, Minor, Major, Destroyed)

Provide a structured damage assessment with specific observations about building conditions."""
            
            user_prompt = base_context
            
            # Add context from CNN analysis if available (future)
            if additional_context and additional_context.get("cnn_analysis"):
                user_prompt += "\n\nAutomated damage detection results:\n"
                user_prompt += f"- {additional_context.get('cnn_analysis', '')}\n"
            
            if user_query:
                user_prompt += f"\nUser's specific question: {user_query}"
            
            user_prompt += "\n\nProvide a building damage assessment with severity classifications and specific observations."
        
        else:
            # Generic fallback
            system_prompt = "You are a satellite imagery analyst. Analyze the provided image and describe what you observe."
            user_prompt = base_context
        
        return system_prompt, user_prompt
    
    def _extract_features(self, analysis_text: str, module_type: ModuleType) -> List[str]:
        """
        Extract key features mentioned in the analysis based on module type.
        """
        features = []
        text_lower = analysis_text.lower()
        
        # Module-specific keywords
        if module_type == "terrain":
            keywords = [
                "water", "river", "lake", "pond", "ocean", "sea", "stream",
                "forest", "trees", "vegetation", "grassland", "agriculture",
                "road", "highway", "building", "urban", "city", "town",
                "mountain", "hill", "valley", "plain", "terrain",
                "bridge", "infrastructure", "development", "residential",
                "commercial", "industrial", "wetland", "marsh", "coastal"
            ]
        
        elif module_type == "mobility":
            keywords = [
                "water obstacle", "river", "lake", "wetland",
                "dense vegetation", "forest", "jungle",
                "road network", "highway", "path", "trail",
                "urban area", "buildings", "city",
                "open terrain", "flat area", "cleared area",
                "steep slope", "hill", "mountain",
                "mobility corridor", "movement route",
                "barrier", "obstacle", "impassable"
            ]
        
        elif module_type == "building_damage":
            keywords = [
                "damaged building", "collapsed structure", "intact building",
                "debris", "rubble", "destruction",
                "fire damage", "burn scar", "charred",
                "flood damage", "water damage",
                "roof damage", "structural damage",
                "minor damage", "major damage", "destroyed",
                "displacement", "foundation damage"
            ]
        
        else:
            keywords = []
        
        # Extract matching features
        for keyword in keywords:
            if keyword in text_lower:
                features.append(keyword.title())
        
        return list(set(features))  # Remove duplicates


# Singleton instance for reuse
_vision_analyzer_instance = None

def get_vision_analyzer() -> VisionAnalyzer:
    """
    Get or create a singleton VisionAnalyzer instance.
    """
    global _vision_analyzer_instance
    if _vision_analyzer_instance is None:
        _vision_analyzer_instance = VisionAnalyzer()
    return _vision_analyzer_instance
