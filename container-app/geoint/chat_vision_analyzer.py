"""
Chat Vision Analyzer - GPT-5 Vision for Earth Copilot Chat Queries

This module enables GPT-5 Vision analysis for regular chat queries when users ask
about imagery visible on the map. It detects questions like:
- "What is in this image?"
- "Describe what you see"
- "What features are visible?"
- "Analyze the current view"

Works with any imagery source:
- HLS (Harmonized Landsat Sentinel)
- Sentinel-2
- Landsat
- NAIP
- Or any other satellite imagery displayed on the map

Key Differences from GEOINT Module Vision:
- GEOINT modules: Fetch their own Sentinel-2 imagery for specific analysis tasks
- Chat vision: Analyzes whatever imagery is currently visible on the user's map
- Chat vision: More conversational, follows up on previous queries
- Chat vision: Can answer specific user questions about visible features
"""

from typing import Dict, Any, Optional, List
import logging
import os
import base64
import aiohttp
from openai import AzureOpenAI
from urllib.parse import urlencode, parse_qs, urlparse
import planetary_computer

logger = logging.getLogger(__name__)


class ChatVisionAnalyzer:
    """
    Analyzes imagery visible on the map in response to conversational queries.
    Uses GPT-5 Vision to answer user questions about what they're seeing.
    """
    
    def __init__(self):
        """Initialize chat vision analyzer with Azure OpenAI."""
        self.client = AzureOpenAI(
            api_key=os.getenv("AZURE_OPENAI_API_KEY"),
            api_version=os.getenv("AZURE_OPENAI_API_VERSION", "2025-01-01-preview"),
            azure_endpoint=os.getenv("AZURE_OPENAI_ENDPOINT")
        )
        self.deployment_name = os.getenv("AZURE_OPENAI_DEPLOYMENT_NAME", "gpt-5")
        
        logger.info(f"✅ ChatVisionAnalyzer initialized with deployment: {self.deployment_name}")
    
    def should_use_vision(self, query: str, conversation_history: Optional[List[Dict]] = None) -> bool:
        """
        Detect if the user's query is asking about visible imagery.
        
        Args:
            query: User's natural language query
            conversation_history: Recent conversation messages for context
            
        Returns:
            True if vision analysis should be triggered
        """
        query_lower = query.lower()
        
        # Direct vision request keywords
        vision_keywords = [
            "what is in this image",
            "what do you see",
            "describe this image",
            "what's in the image",
            "analyze this image",
            "describe what you see",
            "what features are visible",
            "what can you see",
            "describe the imagery",
            "what does this show",
            "what am i looking at",
            "tell me about this image",
            "describe the current view",
            "what's on the map",
            "what is shown here",
            "identify features",
            "what's visible"
        ]
        
        # Check for direct matches
        for keyword in vision_keywords:
            if keyword in query_lower:
                logger.info(f"🔍 Vision query detected: '{keyword}' in '{query}'")
                return True
        
        # Check for follow-up questions (contextual)
        if conversation_history and len(conversation_history) > 0:
            # Recent message mentioned imagery/satellite data
            recent_context = " ".join([
                msg.get("content", "") for msg in conversation_history[-3:]
            ]).lower()
            
            if any(word in recent_context for word in ["image", "imagery", "satellite", "landsat", "sentinel", "hls"]):
                # User asking follow-up questions
                followup_patterns = [
                    "what about", "how about", "can you tell me",
                    "describe", "explain", "show me", "what", "where"
                ]
                if any(pattern in query_lower for pattern in followup_patterns):
                    logger.info(f"🔍 Contextual vision query detected (follow-up): '{query}'")
                    return True
        
        return False
    
    async def analyze_visible_imagery(
        self,
        query: str,
        map_bounds: Dict[str, float],
        imagery_url: Optional[str],
        collection_id: Optional[str],
        conversation_history: Optional[List[Dict]] = None,
        imagery_base64: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Analyze imagery visible on the map using GPT-5 Vision.
        
        Args:
            query: User's question about the imagery
            map_bounds: Current map view {north, south, east, west, center_lat, center_lng}
            imagery_url: URL to fetch the visible imagery (tile/preview)
            collection_id: Collection ID (hls, sentinel-2-l2a, etc.)
            conversation_history: Recent messages for context
            imagery_base64: Optional base64-encoded PNG screenshot from frontend
            
        Returns:
            Dict containing vision analysis and metadata
        """
        try:
            logger.info(f"🖼️ Analyzing visible imagery for query: '{query}'")
            logger.info(f"📍 Map center: ({map_bounds.get('center_lat')}, {map_bounds.get('center_lng')})")
            logger.info(f"🗺️ Collection: {collection_id}")
            
            # Check if frontend provided base64 screenshot (preferred method)
            image_data = None
            image_metadata = {
                "source": collection_id or "Unknown",
                "bounds": map_bounds
            }
            
            if imagery_base64:
                # Use base64 screenshot from frontend
                logger.info(f"📸 Using base64 screenshot from frontend")
                # Remove the data:image/png;base64, prefix if present
                if imagery_base64.startswith('data:image'):
                    imagery_base64 = imagery_base64.split(',', 1)[1]
                
                image_data = base64.b64decode(imagery_base64)
                image_metadata["source"] = "frontend_screenshot"
                logger.info(f"✅ Decoded {len(image_data)} bytes from base64 screenshot")
            else:
                # Fallback: Fetch the imagery currently visible on map
                image_data, image_metadata = await self._fetch_visible_imagery(
                    imagery_url, map_bounds, collection_id
                )
            
            if not image_data:
                return {
                    "analysis": "I'm unable to see the imagery you're referring to. Could you try asking about a specific location or re-load the imagery on the map?",
                    "needs_imagery": True,
                    "confidence": 0.0
                }
            
            # Analyze with GPT-5 Vision
            analysis_result = await self._analyze_with_gpt5(
                image_data=image_data,
                query=query,
                map_bounds=map_bounds,
                collection_id=collection_id,
                conversation_history=conversation_history,
                image_metadata=image_metadata
            )
            
            logger.info(f"✅ Chat vision analysis completed")
            
            return analysis_result
            
        except Exception as e:
            logger.error(f"❌ Chat vision analysis failed: {e}")
            return {
                "analysis": f"I encountered an error analyzing the imagery: {str(e)}",
                "error": str(e),
                "confidence": 0.0
            }
    
    async def _fetch_visible_imagery(
        self,
        imagery_url: Optional[str],
        map_bounds: Dict[str, float],
        collection_id: Optional[str]
    ) -> tuple[Optional[bytes], Dict[str, Any]]:
        """
        Fetch the imagery currently visible on the user's map.
        
        This could be:
        1. A preview/thumbnail URL provided by the frontend
        2. A TiTiler static map URL we construct from bounds
        3. Fallback to Sentinel-2 if no specific imagery URL
        """
        try:
            metadata = {
                "source": collection_id or "Unknown",
                "bounds": map_bounds
            }
            
            if imagery_url:
                # Use provided imagery URL (from frontend)
                logger.info(f"🛰️ Fetching imagery from provided URL...")
                
                # Sign the URL if it's from Planetary Computer
                if "planetarycomputer.microsoft.com" in imagery_url:
                    imagery_url = planetary_computer.sign_url(imagery_url)
                
                async with aiohttp.ClientSession() as session:
                    async with session.get(imagery_url, timeout=aiohttp.ClientTimeout(total=30)) as response:
                        if response.status == 200:
                            image_bytes = await response.read()
                            metadata["url"] = imagery_url
                            logger.info(f"✅ Fetched {len(image_bytes)} bytes from provided URL")
                            return image_bytes, metadata
                        else:
                            logger.warning(f"⚠️ Failed to fetch from provided URL: {response.status}")
            
            # Fallback: Construct TiTiler static map URL from bounds
            if map_bounds and collection_id:
                logger.info(f"🗺️ Constructing TiTiler static map from bounds...")
                static_map_url = self._build_static_map_url(map_bounds, collection_id)
                
                if static_map_url:
                    async with aiohttp.ClientSession() as session:
                        async with session.get(static_map_url, timeout=aiohttp.ClientTimeout(total=30)) as response:
                            if response.status == 200:
                                image_bytes = await response.read()
                                metadata["url"] = static_map_url
                                metadata["type"] = "static_map"
                                logger.info(f"✅ Fetched {len(image_bytes)} bytes from TiTiler static map")
                                return image_bytes, metadata
            
            # Last resort: Fetch Sentinel-2 for the area
            logger.info(f"🛰️ Fallback: Fetching Sentinel-2 for area...")
            from geoint.vision_analyzer import get_vision_analyzer
            vision_analyzer = get_vision_analyzer()
            
            center_lat = map_bounds.get('center_lat') or map_bounds.get('lat')
            center_lng = map_bounds.get('center_lng') or map_bounds.get('lng')
            
            if center_lat and center_lng:
                radius_deg = 0.1  # ~7 miles
                bbox = [
                    center_lng - radius_deg,
                    center_lat - radius_deg,
                    center_lng + radius_deg,
                    center_lat + radius_deg
                ]
                
                image_bytes, sentinel_metadata = await vision_analyzer._fetch_satellite_image(
                    bbox, center_lat, center_lng
                )
                
                if image_bytes:
                    metadata.update(sentinel_metadata)
                    metadata["type"] = "sentinel2_fallback"
                    return image_bytes, metadata
            
            logger.warning("⚠️ No imagery available to analyze")
            return None, metadata
            
        except Exception as e:
            logger.error(f"Error fetching visible imagery: {e}")
            return None, {}
    
    def _build_static_map_url(
        self,
        map_bounds: Dict[str, float],
        collection_id: str
    ) -> Optional[str]:
        """
        Build a TiTiler static map URL from map bounds.
        Returns a 512x512 PNG of the current view.
        """
        try:
            # This would need the specific item/asset info from the current map state
            # For now, return None and rely on frontend passing imagery_url
            # TODO: Implement if we want server-side static map generation
            return None
        except Exception as e:
            logger.error(f"Error building static map URL: {e}")
            return None
    
    async def _analyze_with_gpt5(
        self,
        image_data: bytes,
        query: str,
        map_bounds: Dict[str, float],
        collection_id: Optional[str],
        conversation_history: Optional[List[Dict]],
        image_metadata: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Analyze imagery with GPT-5 Vision in conversational context.
        """
        try:
            logger.info(f"🤖 Analyzing imagery with GPT-5 Vision (conversational mode)...")
            
            # Encode image to base64
            base64_image = base64.b64encode(image_data).decode('utf-8')
            
            # Build conversational prompt
            system_prompt = """You are Earth Copilot, an AI assistant specialized in analyzing satellite and Earth imagery. You're having a conversation with a user who is viewing satellite imagery on a map.

You have access to the imagery they're currently viewing. Answer their questions conversationally, describing what you see in the image and relating it to their previous questions if applicable.

Be specific about features you can identify:
- Geographic features (water bodies, terrain, vegetation)
- Human-made structures (buildings, roads, infrastructure)
- Land use patterns (urban, agricultural, natural)
- Environmental conditions (cloud cover, snow, flooding)
- Any notable or interesting features

If they ask "what is in this image?" give a comprehensive overview. If they ask specific questions, focus your answer on what they're asking about."""

            # Build user prompt with context
            user_prompt_parts = []
            
            # Add conversation context
            if conversation_history and len(conversation_history) > 0:
                user_prompt_parts.append("**Recent conversation context:**")
                for msg in conversation_history[-3:]:  # Last 3 messages
                    role = msg.get("role", "user")
                    content = msg.get("content", "")[:200]  # Truncate long messages
                    user_prompt_parts.append(f"- {role}: {content}")
                user_prompt_parts.append("")
            
            # Add map/imagery context
            user_prompt_parts.append(f"**Current imagery context:**")
            user_prompt_parts.append(f"- Location: {map_bounds.get('center_lat', 'N/A')}°N, {map_bounds.get('center_lng', 'N/A')}°E")
            user_prompt_parts.append(f"- Collection: {collection_id or 'Unknown'}")
            if image_metadata.get("source"):
                user_prompt_parts.append(f"- Source: {image_metadata['source']}")
            if image_metadata.get("date"):
                user_prompt_parts.append(f"- Date: {image_metadata['date'][:10]}")
            user_prompt_parts.append("")
            
            # Add user's question
            user_prompt_parts.append(f"**User's question:**")
            user_prompt_parts.append(query)
            
            user_prompt = "\n".join(user_prompt_parts)
            
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
                                    "url": f"data:image/png;base64,{base64_image}"
                                }
                            }
                        ]
                    }
                ],
                max_completion_tokens=1000,
                temperature=1.0  # GPT-5 requires default temperature=1.0
            )
            
            analysis_text = response.choices[0].message.content
            
            logger.info(f"✅ GPT-5 conversational analysis completed ({len(analysis_text)} characters)")
            
            return {
                "analysis": analysis_text,
                "imagery_metadata": image_metadata,
                "confidence": 0.85,
                "type": "chat_vision_analysis"
            }
            
        except Exception as e:
            logger.error(f"Error analyzing with GPT-5: {e}")
            import traceback
            logger.error(traceback.format_exc())
            raise


# Singleton instance
_chat_vision_analyzer_instance = None

def get_chat_vision_analyzer() -> ChatVisionAnalyzer:
    """Get or create singleton ChatVisionAnalyzer instance."""
    global _chat_vision_analyzer_instance
    if _chat_vision_analyzer_instance is None:
        _chat_vision_analyzer_instance = ChatVisionAnalyzer()
    return _chat_vision_analyzer_instance
