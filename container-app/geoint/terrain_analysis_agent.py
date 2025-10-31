"""
GEOINT Terrain Analysis Agent using GPT-5 Vision

This agent uses GPT-5's multimodal capabilities to analyze satellite imagery
and provide natural language descriptions of terrain features within a specified
radius of pin coordinates.

Analysis includes:
- Bodies of water (rivers, lakes, ponds, coastal areas)
- Vegetation types and density
- Roads and infrastructure
- Urban vs rural characteristics
- Terrain features (hills, valleys, plains)
- Land use patterns
"""

from typing import Dict, Any, Optional, List
import logging
import os
import base64
from io import BytesIO
import aiohttp
from openai import AzureOpenAI
import planetary_computer

logger = logging.getLogger(__name__)


class TerrainAnalysisAgent:
    """
    Analyzes terrain features using GPT-5 Vision on satellite imagery.
    Provides natural language descriptions of what's visible in the area.
    """
    
    def __init__(self):
        """Initialize the terrain analysis agent with Azure OpenAI."""
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
        
        logger.info(f"✅ TerrainAnalysisAgent initialized with deployment: {self.deployment_name} (timeout: 180s)")
    
    async def analyze_terrain(
        self,
        latitude: float,
        longitude: float,
        radius_miles: float = 5.0,
        user_query: Optional[str] = None,
        specific_features: Optional[List[str]] = None,
        screenshot_base64: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Analyze terrain features using satellite imagery and GPT-5 Vision.
        Can use either a provided screenshot or fetch imagery from STAC.
        
        Args:
            latitude: Center point latitude
            longitude: Center point longitude
            radius_miles: Analysis radius in miles (default 5)
            user_query: Optional specific user question
            specific_features: Optional list of specific features to focus on
            screenshot_base64: Optional base64-encoded screenshot from frontend
            
        Returns:
            Dict containing:
            - analysis: str - Natural language terrain description
            - features_identified: List[str] - Key features found
            - imagery_metadata: Dict - Info about imagery used
            - confidence: float - Analysis confidence score
        """
        try:
            logger.info("=" * 80)
            logger.info("🌍 TERRAIN ANALYSIS STARTED")
            logger.info("=" * 80)
            logger.info(f"📍 Coordinates: ({latitude:.6f}, {longitude:.6f})")
            logger.info(f"📏 Radius: {radius_miles} miles")
            logger.info(f"📝 User Query: {user_query if user_query else 'None'}")
            logger.info(f"🎯 Specific Features: {specific_features if specific_features else 'None'}")
            logger.info(f"📸 Screenshot Provided: {'Yes' if screenshot_base64 else 'No'}")
            logger.info("=" * 80)
            
            # If screenshot provided, use it directly
            if screenshot_base64:
                logger.info("✅ Using provided screenshot for analysis")
                result = await self._analyze_with_screenshot(
                    screenshot_base64=screenshot_base64,
                    latitude=latitude,
                    longitude=longitude,
                    user_query=user_query,
                    specific_features=specific_features
                )
                
                logger.info("=" * 80)
                logger.info("✅ TERRAIN ANALYSIS COMPLETED (Screenshot Method)")
                logger.info("=" * 80)
                logger.info(f"📊 Analysis Length: {len(result.get('analysis', ''))} characters")
                logger.info(f"🏷️  Features Found: {len(result.get('features_identified', []))}")
                logger.info(f"🎯 Confidence: {result.get('confidence', 0.0):.2f}")
                logger.info("=" * 80)
                
                return result
            
            # Otherwise, use shared vision analyzer to fetch imagery
            logger.info("🛰️ Fetching satellite imagery for analysis (STAC fallback)")
            from geoint.vision_analyzer import get_vision_analyzer
            
            vision_analyzer = get_vision_analyzer()
            
            # Perform vision analysis with terrain-specific prompts
            vision_result = await vision_analyzer.analyze_location_with_vision(
                latitude=latitude,
                longitude=longitude,
                module_type="terrain",
                radius_miles=radius_miles,
                user_query=user_query,
                additional_context=None
            )
            
            logger.info("=" * 80)
            logger.info("✅ TERRAIN ANALYSIS COMPLETED (STAC Imagery Method)")
            logger.info("=" * 80)
            logger.info(f"📊 Analysis Length: {len(vision_result.get('visual_analysis', ''))} characters")
            logger.info(f"🏷️  Features Found: {len(vision_result.get('features_identified', []))}")
            logger.info(f"🎯 Confidence: {vision_result.get('confidence', 0.0):.2f}")
            logger.info("=" * 80)
            
            # Return in the expected format (rename visual_analysis to analysis for compatibility)
            return {
                "analysis": vision_result.get("visual_analysis", ""),
                "features_identified": vision_result.get("features_identified", []),
                "imagery_metadata": vision_result.get("imagery_metadata", {}),
                "confidence": vision_result.get("confidence", 0.0),
                "location": vision_result.get("location", {})
            }
            
        except Exception as e:
            logger.error("=" * 80)
            logger.error("❌ TERRAIN ANALYSIS FAILED")
            logger.error("=" * 80)
            logger.error(f"🚨 Error Type: {type(e).__name__}")
            logger.error(f"🚨 Error Message: {str(e)}")
            logger.error(f"📍 Location: ({latitude:.6f}, {longitude:.6f})")
            logger.error(f"🔧 Screenshot Mode: {'Yes' if screenshot_base64 else 'No (STAC fallback)'}")
            logger.error("=" * 80)
            import traceback
            logger.error("📋 Full Traceback:")
            logger.error(traceback.format_exc())
            logger.error("=" * 80)
            
            return {
                "analysis": f"Terrain analysis failed: {str(e)}",
                "features_identified": [],
                "imagery_metadata": {},
                "confidence": 0.0
            }
    
    async def _analyze_with_screenshot(
        self,
        screenshot_base64: str,
        latitude: float,
        longitude: float,
        user_query: Optional[str],
        specific_features: Optional[List[str]]
    ) -> Dict[str, Any]:
        """
        Analyze terrain using a provided screenshot from the frontend.
        
        Args:
            screenshot_base64: Base64-encoded PNG screenshot from map
            latitude: Pin location latitude
            longitude: Pin location longitude
            user_query: User's query
            specific_features: Specific features to focus on
            
        Returns:
            Analysis results dictionary
        """
        try:
            logger.info(f"🖼️ Analyzing screenshot at ({latitude}, {longitude})")
            
            # Validate screenshot is not empty
            if not screenshot_base64 or len(screenshot_base64) < 100:
                logger.error(f"❌ Screenshot is empty or too small: {len(screenshot_base64) if screenshot_base64 else 0} chars")
                raise ValueError("Screenshot is empty or invalid")
            
            # Remove data URL prefix if present
            if screenshot_base64.startswith('data:image'):
                logger.info("📸 Removing data URL prefix from screenshot...")
                screenshot_base64 = screenshot_base64.split(',', 1)[1]
            
            # Validate base64 content
            logger.info(f"📸 Screenshot validation: {len(screenshot_base64)} base64 chars")
            
            # Try to decode to verify it's valid base64
            try:
                import base64
                decoded = base64.b64decode(screenshot_base64)
                logger.info(f"✅ Screenshot is valid base64 ({len(decoded)} bytes decoded)")
                
                # Check if it's actually a PNG
                if decoded[:8] != b'\x89PNG\r\n\x1a\n':
                    logger.warning(f"⚠️ Decoded data doesn't look like PNG. First 20 bytes: {decoded[:20]}")
                else:
                    logger.info("✅ Confirmed: Screenshot is valid PNG format")
                    
                # Additional check: PNG files that are mostly black/empty are very small
                # A blank canvas PNG is typically < 5KB, real map screenshots are > 50KB
                if len(decoded) < 5000:
                    logger.warning(f"⚠️ Screenshot is suspiciously small ({len(decoded)} bytes) - likely a blank/black canvas")
                    logger.warning("   This is a known Azure Maps WebGL issue (preserveDrawingBuffer=false)")
                    logger.warning("   Continuing with analysis, but GPT-5 may report the image as blank...")
                    
            except Exception as decode_error:
                logger.error(f"❌ Screenshot base64 decode failed: {decode_error}")
                raise ValueError(f"Invalid base64 screenshot data: {decode_error}")
            
            # Build comprehensive analysis prompt
            system_prompt = """You are an expert geospatial intelligence analyst specializing in terrain analysis from satellite imagery.

**CRITICAL INSTRUCTION**: You MUST analyze the actual map image provided. Do NOT say the image is blank unless you truly cannot see anything.

Analyze the provided map screenshot and provide a comprehensive terrain analysis focusing on ALL of the following characteristics:

**Elevation & Topography:**
- Terrain elevation patterns (flat, hilly, mountainous)
- Landforms (valleys, ridges, plateaus, slopes)
- Topographic features visible

**Vegetation:**
- Vegetation types (forests, grasslands, agricultural fields, shrubland)
- Vegetation density and health
- Seasonal characteristics if visible

**Water Bodies:**
- Rivers, streams, lakes, ponds, reservoirs
- Coastal features if present
- Wetlands or marshes

**Urban vs Rural Classification:**
- Settlement density (urban, suburban, rural, wilderness)
- Infrastructure development level
- Building patterns and road networks

**Soil & Land Surface:**
- Soil type indicators (color, texture visible from above)
- Land use patterns (agricultural, developed, natural)
- Surface characteristics

**Landforms & Geography:**
- Major landforms present
- Geographic context
- Notable natural features

**IMPORTANT**: If you can see a map with terrain features, roads, or any geographic details, describe what you actually see. Only report "blank" if the image is truly empty or corrupted.

Provide your analysis relative to the PIN LOCATION marked on the map (if visible). Focus on describing the area immediately surrounding the pin and within the visible map extent."""

            user_prompt = f"""Analyze this map screenshot centered at coordinates ({latitude:.6f}, {longitude:.6f}).

**First, confirm you can see the map image.** Then analyze the terrain characteristics visible in the image.

The pin marker (if visible) shows the exact location of interest. Analyze the terrain characteristics in relation to this location.

"""
            
            if user_query:
                user_prompt += f"User's specific question: {user_query}\n\n"
            
            if specific_features and len(specific_features) > 0:
                user_prompt += f"Pay special attention to: {', '.join(specific_features)}\n\n"
            
            user_prompt += """Provide a detailed, structured analysis covering:
1. **Overview**: General terrain characteristics
2. **Elevation & Landforms**: Topographic features
3. **Vegetation**: Plant cover and types
4. **Water Features**: Any water bodies present
5. **Development**: Urban/rural classification
6. **Soil & Surface**: Land surface characteristics
7. **Notable Features**: Any distinctive landmarks or features

Be specific and detailed in your analysis."""

            # Call GPT-5 Vision with detailed logging
            logger.info("=" * 80)
            logger.info("🤖 GPT-5 VISION API CALL - TERRAIN ANALYSIS")
            logger.info("=" * 80)
            logger.info(f"📍 Location: ({latitude:.6f}, {longitude:.6f})")
            logger.info(f"🔧 Model: {self.deployment_name}")
            logger.info(f"📝 User Query: {user_query if user_query else 'None'}")
            logger.info(f"📸 Screenshot Size: {len(screenshot_base64)} characters (base64)")
            logger.info(f"⚙️  Parameters: max_completion_tokens=5000, temperature=1.0")
            logger.info("=" * 80)
            
            try:
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
                                        "url": f"data:image/png;base64,{screenshot_base64}",
                                        "detail": "high"
                                    }
                                }
                            ]
                        }
                    ],
                    max_completion_tokens=5000,  # Increased for GPT-5 reasoning model
                    temperature=1.0  # GPT-5 requires default temperature=1.0
                )
                
                logger.info("=" * 80)
                logger.info("✅ GPT-5 VISION API RESPONSE RECEIVED")
                logger.info("=" * 80)
                logger.info(f"📊 Usage - Prompt Tokens: {response.usage.prompt_tokens}")
                logger.info(f"📊 Usage - Completion Tokens: {response.usage.completion_tokens}")
                logger.info(f"📊 Usage - Total Tokens: {response.usage.total_tokens}")
                if hasattr(response.usage, 'reasoning_tokens'):
                    logger.info(f"🧠 Reasoning Tokens: {response.usage.completion_tokens_details.reasoning_tokens if response.usage.completion_tokens_details else 'N/A'}")
                logger.info(f"🎭 Response Finish Reason: {response.choices[0].finish_reason}")
                logger.info("=" * 80)
                
            except Exception as api_error:
                logger.error("=" * 80)
                logger.error("❌ GPT-5 VISION API CALL FAILED")
                logger.error("=" * 80)
                logger.error(f"🚨 Error Type: {type(api_error).__name__}")
                logger.error(f"🚨 Error Message: {str(api_error)}")
                if hasattr(api_error, 'status_code'):
                    logger.error(f"🚨 HTTP Status: {api_error.status_code}")
                if hasattr(api_error, 'response'):
                    logger.error(f"🚨 Response Body: {api_error.response}")
                logger.error("=" * 80)
                import traceback
                logger.error(traceback.format_exc())
                raise
            
            analysis_text = response.choices[0].message.content
            
            # Extract key features from analysis
            features_identified = self._extract_features(analysis_text)
            
            logger.info(f"✅ Screenshot analysis completed ({len(analysis_text)} characters)")
            logger.info(f"   Features identified: {', '.join(features_identified[:5])}")
            
            return {
                "analysis": analysis_text,
                "features_identified": features_identified,
                "imagery_metadata": {
                    "source": "Frontend Map Screenshot",
                    "coordinates": f"{latitude:.6f}, {longitude:.6f}"
                },
                "confidence": 0.90,  # High confidence for direct screenshot
                "location": {
                    "latitude": latitude,
                    "longitude": longitude
                }
            }
            
        except Exception as e:
            logger.error(f"❌ Screenshot analysis failed: {e}")
            import traceback
            logger.error(traceback.format_exc())
            raise
    
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
            
            # Search for recent Sentinel-2 imagery
            from datetime import datetime, timedelta
            from pystac_client import Client
            
            catalog = Client.open(
                self.stac_endpoint,
                modifier=planetary_computer.sign_inplace
            )
            
            # Search for imagery from last 60 days with minimal cloud cover
            search = catalog.search(
                collections=["sentinel-2-l2a"],
                bbox=bbox,
                datetime=f"{(datetime.now() - timedelta(days=60)).isoformat()}Z/{datetime.now().isoformat()}Z",
                query={"eo:cloud_cover": {"lt": 20}}  # Less than 20% cloud cover
            )
            
            items = list(search.items())
            
            if not items:
                logger.warning("No recent Sentinel-2 imagery found")
                return None, {}
            
            # Get most recent item
            item = sorted(items, key=lambda x: x.datetime, reverse=True)[0]
            
            logger.info(f"📸 Found imagery from {item.datetime}")
            logger.info(f"   Cloud cover: {item.properties.get('eo:cloud_cover', 'unknown')}%")
            
            # Get RGB composite tile URL
            # We'll use the Planetary Computer's tile server
            tile_url = f"https://planetarycomputer.microsoft.com/api/data/v1/item/preview.png?collection=sentinel-2-l2a&item={item.id}&assets=visual&width=512&height=512"
            
            # Sign the URL
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
    
    async def _analyze_image_with_gpt5_vision(
        self,
        image_bytes: bytes,
        latitude: float,
        longitude: float,
        radius_miles: float,
        user_query: Optional[str],
        specific_features: Optional[List[str]],
        image_metadata: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Analyze satellite image using GPT-5 Vision API.
        """
        try:
            logger.info("🤖 Analyzing image with GPT-5 Vision...")
            
            # Encode image to base64
            base64_image = base64.b64encode(image_bytes).decode('utf-8')
            
            # Build analysis prompt
            system_prompt = """You are a geospatial intelligence analyst specializing in satellite imagery interpretation. 
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

            user_prompt = f"""Analyze this satellite image centered at coordinates ({latitude}, {longitude}) covering approximately {radius_miles} miles radius.

Image metadata:
- Source: {image_metadata.get('source', 'Unknown')}
- Date: {image_metadata.get('date', 'Unknown')}
- Resolution: {image_metadata.get('resolution', 'Unknown')}
"""
            
            if user_query:
                user_prompt += f"\nUser's specific question: {user_query}"
            
            if specific_features:
                user_prompt += f"\nPay special attention to: {', '.join(specific_features)}"
            
            user_prompt += "\n\nProvide a detailed analysis in a structured format with clear sections."
            
            # Call GPT-5 Vision
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
                                    "url": f"data:image/png;base64,{base64_image}",
                                    "detail": "high"
                                }
                            }
                        ]
                    }
                ],
                max_completion_tokens=5000,  # Increased for GPT-5 reasoning model
                temperature=1.0  # GPT-5 requires default temperature=1.0
            )
            
            analysis_text = response.choices[0].message.content
            
            # Extract key features (simple keyword extraction)
            features_identified = self._extract_features(analysis_text)
            
            logger.info(f"✅ GPT-5 Vision analysis completed ({len(analysis_text)} characters)")
            logger.info(f"   Features identified: {', '.join(features_identified[:5])}")
            
            return {
                "analysis": analysis_text,
                "features_identified": features_identified,
                "imagery_metadata": image_metadata,
                "confidence": 0.90,  # GPT-5 Vision has high confidence
                "location": {
                    "latitude": latitude,
                    "longitude": longitude,
                    "radius_miles": radius_miles
                }
            }
            
        except Exception as e:
            logger.error(f"Error analyzing image with GPT-5 Vision: {e}")
            import traceback
            logger.error(traceback.format_exc())
            raise
    
    def _extract_features(self, analysis_text: str) -> List[str]:
        """Extract key features mentioned in the analysis."""
        features = []
        
        # Common terrain features to look for
        feature_keywords = [
            "water", "river", "lake", "pond", "ocean", "sea", "stream",
            "forest", "trees", "vegetation", "grassland", "agriculture",
            "road", "highway", "building", "urban", "city", "town",
            "mountain", "hill", "valley", "plain", "terrain",
            "bridge", "infrastructure", "development", "residential",
            "commercial", "industrial", "wetland", "marsh", "coastal"
        ]
        
        text_lower = analysis_text.lower()
        
        for keyword in feature_keywords:
            if keyword in text_lower:
                features.append(keyword.title())
        
        return list(set(features))  # Remove duplicates
