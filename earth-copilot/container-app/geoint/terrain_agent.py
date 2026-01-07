"""
Terrain Agent - A Real Semantic Kernel Agent with Memory and Tools

This is a proper AI agent that:
1. Maintains conversation memory across follow-up questions
2. Has access to terrain analysis tools it can call dynamically
3. Plans and reasons about which tools to use
4. Synthesizes results into coherent answers
"""

import logging
import os
from typing import Dict, Any, Optional, List
from datetime import datetime
import asyncio

from semantic_kernel import Kernel
from semantic_kernel.agents import ChatCompletionAgent
from semantic_kernel.connectors.ai.open_ai import AzureChatCompletion
from semantic_kernel.connectors.ai.function_choice_behavior import FunctionChoiceBehavior
from semantic_kernel.contents.chat_history import ChatHistory
from semantic_kernel.contents.chat_message_content import ChatMessageContent
from semantic_kernel.contents.utils.author_role import AuthorRole
from azure.identity import DefaultAzureCredential, get_bearer_token_provider

logger = logging.getLogger(__name__)

# Agent system prompt
TERRAIN_AGENT_INSTRUCTIONS = """You are a Geospatial Intelligence (GEOINT) Terrain Analysis Agent.

Your role is to analyze terrain and answer questions about geographic locations using DEM (Digital Elevation Model) data and visual analysis from satellite imagery.

## Available Tools:
- **get_elevation_analysis**: Get elevation data (min, max, mean in meters) and terrain classification (flat/hilly/mountainous)
- **get_slope_analysis**: Analyze terrain steepness, traversability, and percentage of flat/moderate/steep areas
- **get_aspect_analysis**: Determine slope direction (N, S, E, W, etc.) and sun exposure
- **find_flat_areas**: Locate flat areas suitable for landing zones, construction, or camps
- **exit_analysis_mode**: Call this when the user's question is NOT about terrain analysis

## Visual Analysis (Automatic)
A [Visual Analysis of Current Map View] section is automatically included in your context when a map screenshot is available. This provides:
- Land use and urban development patterns
- Vegetation and land cover assessment
- Water features identification
- Notable landmarks and geographic features

**Use this visual analysis to provide comprehensive responses about vegetation, water bodies, urban areas, and land cover.**

## CRITICAL: Tool Parameters
Each message includes [Location Context] with:
- Coordinates: (latitude, longitude) - USE THESE VALUES when calling any terrain tool
- Analysis radius: X km - USE THIS as the radius_km parameter

**ALWAYS extract the latitude, longitude, and radius from the context and pass them to tools.**
Example: If context shows "Coordinates: (45.123456, -120.654321)" and "Analysis radius: 5 km", call:
  get_elevation_analysis(latitude=45.123456, longitude=-120.654321, radius_km=5.0)

## Guidelines:
1. **Always call DEM tools** for elevation, slope, and aspect - these provide accurate quantitative data
2. **Use Visual Analysis** for vegetation, water bodies, urban areas, roads, and land use patterns
3. **Combine both sources** - DEM data for terrain metrics + visual analysis for land cover
4. **Be specific** - Include actual numbers (elevations in meters, slope percentages, etc.)
5. **Remember context** - Reference previous analysis in follow-up questions

## When to call exit_analysis_mode
Call the exit_analysis_mode tool ONLY when the user asks about:
- Satellite imagery datasets (e.g., "Show me Landsat imagery", "Get Sentinel-2 data")
- A completely different location (e.g., "Now show me Tokyo")
- Weather, news, or general knowledge unrelated to the current terrain or map
- Map layer changes or dataset requests (e.g., "Switch to thermal data")

Do NOT call exit_analysis_mode for:
- "What about the slopes on the north side?"
- "Is there water nearby?"
- "How steep is it to the east?"
- **"What is on the map?"** - Answer using the Visual Analysis section
- **"What do you see?"** - Answer using the Visual Analysis section
- **"Describe what's visible"** - Answer using the Visual Analysis section
- Any question about what's visible, land cover, features, or characteristics of the current location

**IMPORTANT: You have full access to visual analysis of the map. Use it to answer ANY question about what's visible, what features exist, or what the area looks like. Do NOT exit just because a question mentions 'map' or 'image' - you can answer those!**

## Response Format:
1. **Terrain Overview**: ALWAYS start with the location name (from Location Context) followed by a summary of the overall terrain character. Example: "**Mount Parnassus, Central Greece** features predominantly mountainous terrain..."
2. **Elevation & Topography**: Include min/max/mean elevation, terrain type from tools
3. **Slope & Traversability**: Steepness data, percentage flat/steep, traversability assessment
4. **Land Cover & Features**: Use visual analysis for vegetation, water, urban areas

**CRITICAL: Always use the Location name from the [Location Context] at the start of your response. Never respond with just coordinates like "(38.652708, 22.155403)" - always use the resolved location name.**

**Keep responses factual and concise. Do NOT include:**
- "Actionable Insights" or recommendation sections
- Summary paragraphs at the end restating what was said
- Suggestions for development, agriculture, or other uses
"""

class TerrainAgentSession:
    """Represents a conversation session with the terrain agent."""
    
    def __init__(self, session_id: str, latitude: float, longitude: float):
        self.session_id = session_id
        self.latitude = latitude
        self.longitude = longitude
        self.chat_history = ChatHistory()
        self.created_at = datetime.utcnow()
        self.last_activity = datetime.utcnow()
        self.analysis_cache: Dict[str, Any] = {}  # Cache tool results
        
    def update_location(self, latitude: float, longitude: float):
        """Update the session's focus location."""
        self.latitude = latitude
        self.longitude = longitude
        self.last_activity = datetime.utcnow()
        
    def add_user_message(self, content: str):
        """Add a user message to history."""
        self.chat_history.add_user_message(content)
        self.last_activity = datetime.utcnow()
        
    def add_assistant_message(self, content: str):
        """Add an assistant message to history."""
        self.chat_history.add_assistant_message(content)
        self.last_activity = datetime.utcnow()


class TerrainAgent:
    """
    A Semantic Kernel-based terrain analysis agent with:
    - Persistent memory per session
    - Tool calling for raster analysis
    - Multi-turn conversation support
    """
    
    def __init__(self):
        """Initialize the terrain agent with Semantic Kernel."""
        self.kernel = Kernel()
        self.sessions: Dict[str, TerrainAgentSession] = {}
        self._agent: Optional[ChatCompletionAgent] = None
        self._initialized = False
        
        logger.info("🤖 TerrainAgent created (will initialize on first use)")
    
    async def _ensure_initialized(self):
        """Lazy initialization of the agent."""
        if self._initialized:
            return
            
        logger.info("🔧 Initializing TerrainAgent with Semantic Kernel...")
        
        # Set up Azure OpenAI service
        endpoint = os.getenv("AZURE_OPENAI_ENDPOINT")
        deployment = os.getenv("AZURE_OPENAI_DEPLOYMENT_NAME", "gpt-4o")
        api_version = os.getenv("AZURE_OPENAI_API_VERSION", "2025-01-01-preview")
        
        # Use Managed Identity
        credential = DefaultAzureCredential()
        token_provider = get_bearer_token_provider(
            credential, "https://cognitiveservices.azure.com/.default"
        )
        
        # Create Azure OpenAI chat completion service
        chat_service = AzureChatCompletion(
            deployment_name=deployment,
            endpoint=endpoint,
            api_version=api_version,
            ad_token_provider=token_provider,
            service_id="terrain_chat"
        )
        
        self.kernel.add_service(chat_service)
        
        # Add terrain analysis tools as a plugin
        from geoint.terrain_tools import TerrainAnalysisTools
        terrain_tools = TerrainAnalysisTools()
        self.kernel.add_plugin(terrain_tools, plugin_name="terrain")
        
        # Create the agent with function calling enabled
        self._agent = ChatCompletionAgent(
            kernel=self.kernel,
            name="TerrainAnalyst",
            instructions=TERRAIN_AGENT_INSTRUCTIONS,
            function_choice_behavior=FunctionChoiceBehavior.Auto()
        )
        
        self._initialized = True
        logger.info(f"✅ TerrainAgent initialized with {len(self.kernel.plugins)} plugins")
    
    def get_or_create_session(
        self, 
        session_id: str,
        latitude: float,
        longitude: float
    ) -> TerrainAgentSession:
        """Get existing session or create a new one."""
        if session_id in self.sessions:
            session = self.sessions[session_id]
            session.update_location(latitude, longitude)
            return session
        
        session = TerrainAgentSession(session_id, latitude, longitude)
        self.sessions[session_id] = session
        logger.info(f"📝 Created new session: {session_id}")
        return session
    
    def cleanup_old_sessions(self, max_age_minutes: int = 60):
        """Remove sessions older than max_age_minutes."""
        now = datetime.utcnow()
        expired = [
            sid for sid, session in self.sessions.items()
            if (now - session.last_activity).total_seconds() > max_age_minutes * 60
        ]
        for sid in expired:
            del self.sessions[sid]
            logger.info(f"🗑️ Cleaned up expired session: {sid}")
    
    async def _analyze_screenshot_direct(
        self,
        screenshot_base64: str,
        latitude: float,
        longitude: float
    ) -> Optional[str]:
        """
        Directly analyze a screenshot using GPT-4 Vision.
        
        This runs BEFORE the agent invoke to ensure visual analysis
        is always available in the agent's context.
        """
        try:
            from openai import AzureOpenAI
            from azure.identity import DefaultAzureCredential, get_bearer_token_provider
            import base64
            
            logger.info(f"👁️ Running direct vision analysis at ({latitude:.4f}, {longitude:.4f})")
            
            # Log screenshot info for debugging
            logger.info(f"📸 Screenshot base64 length: {len(screenshot_base64)} chars")
            logger.info(f"📸 Screenshot starts with: {screenshot_base64[:50]}...")
            
            credential = DefaultAzureCredential()
            token_provider = get_bearer_token_provider(
                credential, "https://cognitiveservices.azure.com/.default"
            )
            
            client = AzureOpenAI(
                azure_ad_token_provider=token_provider,
                api_version=os.getenv("AZURE_OPENAI_API_VERSION", "2025-01-01-preview"),
                azure_endpoint=os.getenv("AZURE_OPENAI_ENDPOINT"),
                timeout=120.0
            )
            
            # Clean base64 if needed
            clean_base64 = screenshot_base64
            if screenshot_base64.startswith('data:image'):
                clean_base64 = screenshot_base64.split(',', 1)[1]
                logger.info(f"📸 Stripped data URI prefix, new length: {len(clean_base64)}")
            
            # Validate base64 can be decoded
            try:
                decoded = base64.b64decode(clean_base64)
                logger.info(f"📸 Base64 decoded successfully: {len(decoded)} bytes")
                # Check for JPEG/PNG magic bytes
                if decoded[:2] == b'\xff\xd8':
                    logger.info("📸 Image format: JPEG (valid)")
                elif decoded[:4] == b'\x89PNG':
                    logger.info("📸 Image format: PNG (valid)")
                else:
                    logger.warning(f"📸 Unknown image format, first bytes: {decoded[:10]}")
            except Exception as decode_error:
                logger.error(f"❌ Base64 decode failed: {decode_error}")
            
            # Comprehensive terrain-focused vision prompt
            vision_prompt = f"""Analyze this satellite/map image for terrain and geospatial intelligence.

Location: Approximately ({latitude:.4f}, {longitude:.4f})

Provide a comprehensive analysis covering:

1. **Land Use & Urban Development**:
   - Urban vs rural areas (buildings, roads, infrastructure)
   - Settlement patterns and density
   - Major roads, highways, or transportation corridors

2. **Vegetation & Land Cover**:
   - Forest, grassland, agricultural areas
   - Vegetation health and density (green vs brown areas)
   - Parks, golf courses, or managed green spaces

3. **Water Features**:
   - Rivers, streams, lakes, ponds, reservoirs
   - Wetlands or flood-prone areas
   - Coastal features if applicable

4. **Terrain Features**:
   - Hills, valleys, ridges visible in the imagery
   - Flat areas suitable for development or operations
   - Notable geographic features

5. **Notable Observations**:
   - Any distinctive landmarks or features
   - Areas of interest for further analysis

Be specific and quantitative where possible (e.g., "approximately 60% urban development")."""
            
            response = client.chat.completions.create(
                model=os.getenv("AZURE_OPENAI_DEPLOYMENT_NAME", "gpt-4o"),
                messages=[
                    {
                        "role": "system",
                        "content": "You are an expert geospatial analyst specializing in terrain analysis and satellite imagery interpretation. Provide detailed, actionable intelligence."
                    },
                    {
                        "role": "user",
                        "content": [
                            {"type": "text", "text": vision_prompt},
                            {
                                "type": "image_url",
                                "image_url": {"url": f"data:image/jpeg;base64,{clean_base64}", "detail": "high"}
                            }
                        ]
                    }
                ],
                max_tokens=1500
            )
            
            analysis = response.choices[0].message.content
            logger.info(f"✅ Vision analysis complete: {len(analysis)} chars")
            return analysis
            
        except Exception as e:
            logger.error(f"❌ Direct vision analysis failed: {e}")
            import traceback
            logger.error(traceback.format_exc())
            return f"Visual analysis unavailable: {str(e)}"
    
    async def chat(
        self,
        session_id: str,
        user_message: str,
        latitude: float,
        longitude: float,
        screenshot_base64: Optional[str] = None,
        radius_km: float = 5.0
    ) -> Dict[str, Any]:
        """
        Process a user message and return agent response.
        
        Args:
            session_id: Unique session identifier for memory
            user_message: The user's question or command
            latitude: Current focus latitude
            longitude: Current focus longitude
            screenshot_base64: Optional screenshot for visual analysis
            radius_km: Analysis radius in km
            
        Returns:
            Dict with response, tool_calls, and session info
        """
        await self._ensure_initialized()
        
        # Get or create session
        session = self.get_or_create_session(session_id, latitude, longitude)
        
        # ========================================================================
        # � REVERSE GEOCODE TO GET LOCATION NAME
        # ========================================================================
        # Always resolve coordinates to a human-readable location name
        # This ensures responses include meaningful place names, not just coordinates
        # ========================================================================
        location_name = None
        try:
            from semantic_translator import geocoding_plugin
            reverse_geocode_result = await geocoding_plugin.azure_maps_reverse_geocode(latitude, longitude)
            import json
            geocode_data = json.loads(reverse_geocode_result)
            if not geocode_data.get("error"):
                # Build a readable location name from the components
                name = geocode_data.get("name", "")
                region = geocode_data.get("region", "")
                country = geocode_data.get("country", "")
                
                # Create a clean location string
                parts = [p for p in [name, region, country] if p and p != name]
                if name:
                    location_name = f"{name}, {', '.join(parts)}" if parts else name
                else:
                    location_name = geocode_data.get("freeform", f"Location ({latitude:.4f}, {longitude:.4f})")
                
                logger.info(f"📍 Resolved location: ({latitude}, {longitude}) → {location_name}")
            else:
                location_name = f"Location ({latitude:.4f}, {longitude:.4f})"
                logger.warning(f"📍 Reverse geocode failed, using coordinates: {location_name}")
        except Exception as e:
            location_name = f"Location ({latitude:.4f}, {longitude:.4f})"
            logger.warning(f"📍 Reverse geocode exception, using coordinates: {e}")
        
        # ========================================================================
        # 👁️ PRE-ANALYZE SCREENSHOT WITH GPT-4 VISION
        # ========================================================================
        # Always run vision analysis on screenshot BEFORE invoking the agent
        # This ensures visual context is always available in the agent's context
        # ========================================================================
        visual_analysis = None
        if screenshot_base64:
            visual_analysis = await self._analyze_screenshot_direct(screenshot_base64, latitude, longitude)
            session.analysis_cache["visual_analysis"] = visual_analysis
            logger.info(f"👁️ Pre-analyzed screenshot: {len(visual_analysis) if visual_analysis else 0} chars")
        
        # Build context-enriched message with location name and visual analysis included
        context_message = f"""[Location Context]
- Location: {location_name}
- Coordinates: ({latitude:.6f}, {longitude:.6f})
- Analysis radius: {radius_km} km
- Session messages: {len(session.chat_history.messages)}"""
        
        # Include visual analysis directly in context so agent can use it
        if visual_analysis:
            context_message += f"""

[Visual Analysis of Current Map View]
{visual_analysis}"""
        
        context_message += f"""

[User Question]
{user_message}"""
        
        # Add user message to history
        session.add_user_message(context_message)
        
        logger.info(f"💬 Session {session_id}: Processing '{user_message[:50]}...'")
        
        try:
            # Invoke the agent
            tool_calls = []
            response_parts = []  # Accumulate all response parts
            
            async for response_item in self._agent.invoke(session.chat_history):
                # Handle both AgentResponseItem and ChatMessageContent
                message = response_item
                if hasattr(response_item, 'message'):
                    message = response_item.message
                
                if isinstance(message, ChatMessageContent):
                    logger.debug(f"📨 Message role: {message.role}, content length: {len(message.content or '')}")
                    
                    # Collect assistant response content
                    if message.role == AuthorRole.ASSISTANT and message.content:
                        response_parts.append(message.content)
                    
                    # Track tool calls from message items
                    if hasattr(message, 'items'):
                        for item in message.items:
                            # Log item type for debugging
                            item_type = type(item).__name__
                            logger.debug(f"🔍 Item type: {item_type}, attrs: {dir(item)[:10]}")
                            
                            # Check for FunctionResultContent (tool result)
                            if hasattr(item, 'function_name') or hasattr(item, 'name'):
                                tool_name = getattr(item, 'function_name', None) or getattr(item, 'name', 'unknown')
                                tool_result = getattr(item, 'result', None)
                                
                                # Parse result if it's a dict-like string
                                result_parsed = tool_result
                                if isinstance(tool_result, str) and tool_result.startswith('{'):
                                    try:
                                        import json
                                        result_parsed = json.loads(tool_result)
                                    except:
                                        pass
                                
                                tool_calls.append({
                                    "tool": tool_name,
                                    "result": result_parsed if isinstance(result_parsed, dict) else str(tool_result)[:500] if tool_result else None
                                })
                                logger.info(f"🔧 Tool called: {tool_name}")
                                
                                # Special handling for exit_analysis_mode
                                if tool_name == "exit_analysis_mode":
                                    logger.info(f"🚪 EXIT DETECTED: exit_analysis_mode tool was called")
                                    logger.info(f"🚪 Tool result: {tool_result}")
            
            # Combine all response parts (the final one should be the complete analysis)
            response_content = response_parts[-1] if response_parts else ""
            
            # Add assistant response to history
            session.add_assistant_message(response_content)
            
            logger.info(f"✅ Agent response ({len(response_content)} chars, {len(tool_calls)} tool calls)")
            
            return {
                "response": response_content,
                "tool_calls": tool_calls,
                "session_id": session_id,
                "message_count": len(session.chat_history.messages),
                "location": {"latitude": latitude, "longitude": longitude}
            }
            
        except Exception as e:
            logger.error(f"❌ Agent error: {e}")
            import traceback
            logger.error(traceback.format_exc())
            
            return {
                "response": f"I encountered an error analyzing this location: {str(e)}",
                "error": str(e),
                "session_id": session_id
            }
    
    async def get_session_history(self, session_id: str) -> List[Dict[str, str]]:
        """Get conversation history for a session."""
        if session_id not in self.sessions:
            return []
        
        session = self.sessions[session_id]
        history = []
        
        for msg in session.chat_history.messages:
            history.append({
                "role": msg.role.value if hasattr(msg.role, 'value') else str(msg.role),
                "content": msg.content or ""
            })
        
        return history
    
    async def clear_session(self, session_id: str) -> bool:
        """Clear a session's memory."""
        if session_id in self.sessions:
            del self.sessions[session_id]
            logger.info(f"🗑️ Cleared session: {session_id}")
            return True
        return False


# Singleton instance
_terrain_agent: Optional[TerrainAgent] = None


def get_terrain_agent() -> TerrainAgent:
    """Get the singleton TerrainAgent instance."""
    global _terrain_agent
    if _terrain_agent is None:
        _terrain_agent = TerrainAgent()
    return _terrain_agent
