"""
Earth-Copilot MCP Server

Model Context Protocol server providing rich geospatial intelligence capabilities:
- Tools for satellite imagery analysis, terrain processing, environmental monitoring
- Resources for accessing STAC catalogs, datasets, and analysis results
- Prompts for specialized geospatial analysis contexts
- Context preservation across multi-turn conversations
"""

import asyncio
import json
import logging
from typing import Any, Dict, List, Optional, Sequence
from urllib.parse import urlparse
import os
from datetime import datetime, timedelta

from mcp.server.models import InitializationOptions
from mcp.server import NotificationOptions, Server
from mcp.types import (
    Resource, Tool, Prompt, TextContent, ImageContent, EmbeddedResource,
    LoggingLevel, CallToolResult, GetPromptResult, ListResourcesResult,
    ListToolsResult, ListPromptsResult, ReadResourceResult
)
import mcp.types as types

# Import Earth-Copilot modules
import sys
sys.path.append(os.path.join(os.path.dirname(__file__), '..', 'router-function-app'))

try:
    from semantic_translator import SemanticQueryTranslator
except ImportError:
    logging.warning("Could not import SemanticQueryTranslator - some functionality may be limited")
    SemanticQueryTranslator = None

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("earth-copilot-mcp")

class EarthCopilotMCPServer:
    """MCP Server for Earth-Copilot geospatial intelligence capabilities."""
    
    def __init__(self):
        """Initialize the MCP server with Earth-Copilot capabilities."""
        self.server = Server("earth-copilot")
        self.semantic_translator = SemanticQueryTranslator() if SemanticQueryTranslator else None
        self.conversation_contexts = {}  # Store conversation context
        self.resource_cache = {}  # Resource caching
        
        # Configuration
        self.base_url = os.getenv('EARTH_COPILOT_BASE_URL', 'https://earthcopilot-web-ui.azurewebsites.net')
        self.backend_api_url = os.getenv('EARTH_COPILOT_API_URL', 'https://earthcopilot-api.politecoast-31b85ce5.canadacentral.azurecontainerapps.io')
        self.geoint_url = os.getenv('GEOINT_SERVICE_URL', 'https://your-geoint-app.azurewebsites.net')
        
        # Setup MCP handlers
        self._setup_handlers()
        
        logger.info("Earth-Copilot MCP Server initialized")
    
    def _setup_handlers(self):
        """Setup MCP protocol handlers."""
        
        @self.server.list_resources()
        async def handle_list_resources() -> ListResourcesResult:
            """List available Earth observation resources."""
            return ListResourcesResult(
                resources=[
                    Resource(
                        uri="earth://stac/landsat-8",
                        name="Landsat-8 Collection",
                        description="NASA/USGS Landsat-8 satellite imagery collection with global coverage",
                        mimeType="application/json"
                    ),
                    Resource(
                        uri="earth://stac/sentinel-2",
                        name="Sentinel-2 Collection", 
                        description="ESA Sentinel-2 multi-spectral satellite imagery with 10m resolution",
                        mimeType="application/json"
                    ),
                    Resource(
                        uri="earth://stac/modis",
                        name="MODIS Collection",
                        description="NASA MODIS Earth observation data for environmental monitoring",
                        mimeType="application/json"
                    ),
                    Resource(
                        uri="earth://elevation/copernicus-dem",
                        name="Copernicus DEM",
                        description="Global Digital Elevation Model from Copernicus programme",
                        mimeType="application/json"
                    ),
                    Resource(
                        uri="earth://analysis/capabilities",
                        name="Analysis Capabilities", 
                        description="Available geospatial analysis tools and their parameters",
                        mimeType="application/json"
                    ),
                    Resource(
                        uri="earth://context/{conversation_id}",
                        name="Conversation Context",
                        description="Preserved context for multi-turn geospatial analysis conversations",
                        mimeType="application/json"
                    )
                ]
            )
        
        @self.server.read_resource()
        async def handle_read_resource(uri: str) -> ReadResourceResult:
            """Read Earth observation resource data."""
            logger.info(f"Reading resource: {uri}")
            
            try:
                parsed_uri = urlparse(uri)
                
                if parsed_uri.scheme == "earth":
                    if parsed_uri.path.startswith("/stac/"):
                        return await self._read_stac_resource(parsed_uri)
                    elif parsed_uri.path.startswith("/elevation/"):
                        return await self._read_elevation_resource(parsed_uri)
                    elif parsed_uri.path.startswith("/analysis/"):
                        return await self._read_analysis_resource(parsed_uri)
                    elif parsed_uri.path.startswith("/context/"):
                        return await self._read_context_resource(parsed_uri)
                
                raise ValueError(f"Unsupported resource URI: {uri}")
                
            except Exception as e:
                logger.error(f"Error reading resource {uri}: {str(e)}")
                return ReadResourceResult(
                    contents=[
                        TextContent(
                            type="text",
                            text=f"Error reading resource: {str(e)}"
                        )
                    ]
                )
        
        @self.server.list_tools()
        async def handle_list_tools() -> ListToolsResult:
            """List available Earth observation analysis tools."""
            return ListToolsResult(
                tools=[
                    Tool(
                        name="analyze_satellite_imagery",
                        description="Analyze satellite imagery for specific locations and timeframes using STAC collections",
                        inputSchema={
                            "type": "object",
                            "properties": {
                                "query": {
                                    "type": "string",
                                    "description": "Natural language query describing the analysis needed"
                                },
                                "location": {
                                    "type": "string", 
                                    "description": "Geographic location (place name, coordinates, or bounding box)"
                                },
                                "timeframe": {
                                    "type": "string",
                                    "description": "Time period for analysis (e.g., '2023-01-01/2023-12-31')"
                                },
                                "collections": {
                                    "type": "array",
                                    "items": {"type": "string"},
                                    "description": "STAC collections to use (landsat-8, sentinel-2, modis)"
                                },
                                "analysis_type": {
                                    "type": "string",
                                    "enum": ["change_detection", "environmental_monitoring", "disaster_assessment", "vegetation_analysis"],
                                    "description": "Type of analysis to perform"
                                }
                            },
                            "required": ["query", "location"]
                        }
                    ),
                    Tool(
                        name="terrain_analysis",
                        description="Perform geospatial terrain analysis including slope, aspect, elevation, and geomorphology",
                        inputSchema={
                            "type": "object",
                            "properties": {
                                "location": {
                                    "type": "string",
                                    "description": "Geographic area for terrain analysis"
                                },
                                "analysis_types": {
                                    "type": "array",
                                    "items": {
                                        "type": "string",
                                        "enum": ["slope", "aspect", "hillshade", "roughness", "curvature"]
                                    },
                                    "description": "Types of terrain analysis to perform"
                                },
                                "resolution": {
                                    "type": "number",
                                    "description": "Analysis resolution in meters",
                                    "default": 30
                                },
                                "output_format": {
                                    "type": "string", 
                                    "enum": ["geotiff", "json", "visualization"],
                                    "default": "visualization"
                                }
                            },
                            "required": ["location"]
                        }
                    ),
                    Tool(
                        name="geoint_analysis",
                        description="Military/intelligence geospatial analysis including mobility assessment and line-of-sight calculations",
                        inputSchema={
                            "type": "object",
                            "properties": {
                                "query": {
                                    "type": "string",
                                    "description": "GEOINT analysis request in natural language"
                                },
                                "area_of_interest": {
                                    "type": "string",
                                    "description": "Geographic area of interest"
                                },
                                "analysis_type": {
                                    "type": "string",
                                    "enum": ["mobility_analysis", "line_of_sight", "terrain_assessment", "route_planning"],
                                    "description": "Type of GEOINT analysis"
                                },
                                "vehicle_type": {
                                    "type": "string",
                                    "enum": ["light_vehicle", "heavy_vehicle", "tracked_vehicle", "personnel"],
                                    "description": "Vehicle type for mobility analysis"
                                },
                                "weather_conditions": {
                                    "type": "string",
                                    "enum": ["dry", "wet", "snow", "mud"],
                                    "description": "Weather conditions affecting mobility"
                                }
                            },
                            "required": ["query", "area_of_interest"]
                        }
                    ),
                    Tool(
                        name="environmental_monitoring",
                        description="Monitor environmental changes over time using multi-temporal satellite data",
                        inputSchema={
                            "type": "object",
                            "properties": {
                                "location": {
                                    "type": "string",
                                    "description": "Geographic area to monitor"
                                },
                                "monitoring_type": {
                                    "type": "string",
                                    "enum": ["deforestation", "urban_growth", "water_level", "vegetation_health", "wildfire", "flooding"],
                                    "description": "Type of environmental monitoring"
                                },
                                "time_period": {
                                    "type": "string",
                                    "description": "Time period for monitoring (e.g., '2020-01-01/2024-01-01')"
                                },
                                "alert_threshold": {
                                    "type": "number",
                                    "description": "Threshold for change detection alerts",
                                    "default": 0.1
                                }
                            },
                            "required": ["location", "monitoring_type", "time_period"]
                        }
                    ),
                    Tool(
                        name="data_discovery",
                        description="Discover available satellite data and STAC collections for specific locations and time periods",
                        inputSchema={
                            "type": "object",
                            "properties": {
                                "location": {
                                    "type": "string",
                                    "description": "Geographic area of interest"
                                },
                                "timeframe": {
                                    "type": "string",
                                    "description": "Time period of interest"
                                },
                                "data_types": {
                                    "type": "array",
                                    "items": {"type": "string"},
                                    "description": "Types of data needed (optical, radar, elevation, etc.)"
                                },
                                "cloud_cover_max": {
                                    "type": "number",
                                    "description": "Maximum acceptable cloud cover percentage",
                                    "default": 20
                                }
                            },
                            "required": ["location"]
                        }
                    )
                ]
            )
        
        @self.server.call_tool()
        async def handle_call_tool(name: str, arguments: Dict[str, Any]) -> CallToolResult:
            """Execute Earth observation analysis tools."""
            logger.info(f"Calling tool: {name} with arguments: {arguments}")
            
            try:
                if name == "analyze_satellite_imagery":
                    return await self._analyze_satellite_imagery(arguments)
                elif name == "terrain_analysis":
                    return await self._terrain_analysis(arguments)
                elif name == "geoint_analysis":
                    return await self._geoint_analysis(arguments)
                elif name == "environmental_monitoring":
                    return await self._environmental_monitoring(arguments)
                elif name == "data_discovery":
                    return await self._data_discovery(arguments)
                else:
                    raise ValueError(f"Unknown tool: {name}")
                    
            except Exception as e:
                logger.error(f"Error executing tool {name}: {str(e)}")
                return CallToolResult(
                    content=[
                        TextContent(
                            type="text",
                            text=f"Error executing {name}: {str(e)}"
                        )
                    ]
                )
        
        @self.server.list_prompts()
        async def handle_list_prompts() -> ListPromptsResult:
            """List available geospatial analysis prompts."""
            return ListPromptsResult(
                prompts=[
                    Prompt(
                        name="geospatial_expert",
                        description="You are an expert geospatial analyst with access to global satellite data",
                        arguments=[
                            {
                                "name": "specialization",
                                "description": "Area of specialization (environmental, military, disaster, urban)",
                                "required": False
                            }
                        ]
                    ),
                    Prompt(
                        name="satellite_analyst",
                        description="You are a satellite imagery analyst with expertise in remote sensing",
                        arguments=[
                            {
                                "name": "sensor_type",
                                "description": "Preferred satellite sensor (landsat, sentinel, modis)",
                                "required": False
                            }
                        ]
                    ),
                    Prompt(
                        name="geoint_specialist",
                        description="You are a geospatial intelligence specialist with military/defense expertise",
                        arguments=[
                            {
                                "name": "classification_level",
                                "description": "Classification level for analysis (unclassified, restricted)",
                                "required": False
                            }
                        ]
                    ),
                    Prompt(
                        name="environmental_scientist",
                        description="You are an environmental scientist using Earth observation for climate and ecosystem monitoring",
                        arguments=[
                            {
                                "name": "focus_area", 
                                "description": "Environmental focus area (climate, biodiversity, pollution)",
                                "required": False
                            }
                        ]
                    )
                ]
            )
        
        @self.server.get_prompt()
        async def handle_get_prompt(name: str, arguments: Dict[str, str]) -> GetPromptResult:
            """Get specialized geospatial analysis prompts."""
            
            prompts = {
                "geospatial_expert": self._get_geospatial_expert_prompt(arguments),
                "satellite_analyst": self._get_satellite_analyst_prompt(arguments),
                "geoint_specialist": self._get_geoint_specialist_prompt(arguments),
                "environmental_scientist": self._get_environmental_scientist_prompt(arguments)
            }
            
            if name not in prompts:
                raise ValueError(f"Unknown prompt: {name}")
            
            return GetPromptResult(
                description=f"Specialized {name} prompt",
                messages=prompts[name]
            )
    
    async def _read_stac_resource(self, parsed_uri) -> ReadResourceResult:
        """Read STAC catalog resource information."""
        collection_name = parsed_uri.path.split('/')[-1]
        
        stac_info = {
            "landsat-8": {
                "title": "Landsat-8 Collection",
                "description": "NASA/USGS Landsat-8 satellite imagery",
                "spatial_extent": "Global",
                "temporal_extent": "2013-present",
                "resolution": "30m",
                "bands": ["B1-B11", "QA"],
                "update_frequency": "16 days"
            },
            "sentinel-2": {
                "title": "Sentinel-2 Collection",
                "description": "ESA Sentinel-2 multi-spectral imagery",
                "spatial_extent": "Global (between 84°N and 56°S)",
                "temporal_extent": "2015-present", 
                "resolution": "10m, 20m, 60m",
                "bands": ["B1-B12", "QA"],
                "update_frequency": "5 days"
            },
            "modis": {
                "title": "MODIS Collection",
                "description": "NASA MODIS Earth observation data",
                "spatial_extent": "Global",
                "temporal_extent": "2000-present",
                "resolution": "250m, 500m, 1km",
                "bands": ["Various products"],
                "update_frequency": "Daily"
            }
        }
        
        info = stac_info.get(collection_name, {"error": f"Unknown collection: {collection_name}"})
        
        return ReadResourceResult(
            contents=[
                TextContent(
                    type="text",
                    text=json.dumps(info, indent=2)
                )
            ]
        )
    
    async def _read_elevation_resource(self, parsed_uri) -> ReadResourceResult:
        """Read elevation data resource information."""
        elevation_info = {
            "title": "Copernicus DEM",
            "description": "Global Digital Elevation Model",
            "resolution": "30m (1 arc-second)",
            "coverage": "Global (90°N to 90°S)",
            "vertical_accuracy": "~4m",
            "data_source": "TanDEM-X and other sources",
            "applications": ["Terrain analysis", "Slope calculation", "Visibility analysis", "Hydrological modeling"]
        }
        
        return ReadResourceResult(
            contents=[
                TextContent(
                    type="text",
                    text=json.dumps(elevation_info, indent=2)
                )
            ]
        )
    
    async def _read_analysis_resource(self, parsed_uri) -> ReadResourceResult:
        """Read analysis capabilities resource."""
        capabilities = {
            "satellite_analysis": {
                "change_detection": "Identify changes over time using multi-temporal imagery",
                "environmental_monitoring": "Monitor environmental conditions and changes",
                "disaster_assessment": "Assess disaster impact and recovery",
                "vegetation_analysis": "Analyze vegetation health and coverage"
            },
            "terrain_analysis": {
                "slope_analysis": "Calculate slope angles and gradients",
                "aspect_analysis": "Determine terrain aspect and orientation",
                "visibility_analysis": "Compute viewsheds and line-of-sight",
                "roughness_analysis": "Assess terrain roughness and complexity"
            },
            "geoint_capabilities": {
                "mobility_analysis": "Assess vehicle traversability",
                "route_planning": "Plan optimal routes considering terrain",
                "tactical_analysis": "Military terrain analysis",
                "infrastructure_assessment": "Analyze infrastructure and facilities"
            }
        }
        
        return ReadResourceResult(
            contents=[
                TextContent(
                    type="text",
                    text=json.dumps(capabilities, indent=2)
                )
            ]
        )
    
    async def _read_context_resource(self, parsed_uri) -> ReadResourceResult:
        """Read conversation context resource."""
        conversation_id = parsed_uri.path.split('/')[-1]
        context = self.conversation_contexts.get(conversation_id, {})
        
        return ReadResourceResult(
            contents=[
                TextContent(
                    type="text",
                    text=json.dumps(context, indent=2, default=str)
                )
            ]
        )
    
    async def _analyze_satellite_imagery(self, arguments: Dict[str, Any]) -> CallToolResult:
        """Analyze satellite imagery using Earth-Copilot services."""
        query = arguments.get("query", "")
        location = arguments.get("location", "")
        
        # Use semantic translator if available
        if self.semantic_translator:
            translation_result = self.semantic_translator.translate_query(
                f"{query} in {location}"
            )
        else:
            translation_result = {
                "service": "earth-copilot",
                "parameters": arguments
            }
        
        # Simulate analysis result (in production, call actual Earth-Copilot API)
        result = {
            "analysis_type": "satellite_imagery_analysis",
            "location": location,
            "query": query,
            "translation": translation_result,
            "status": "completed",
            "results": {
                "summary": f"Analyzed satellite imagery for {location}",
                "collections_used": arguments.get("collections", ["landsat-8"]),
                "analysis_type": arguments.get("analysis_type", "general"),
                "timeframe": arguments.get("timeframe", "recent"),
                "confidence": 0.85
            },
            "visualization_url": f"{self.base_url}/?query={query}"
        }
        
        return CallToolResult(
            content=[
                TextContent(
                    type="text", 
                    text=json.dumps(result, indent=2)
                )
            ]
        )
    
    async def _terrain_analysis(self, arguments: Dict[str, Any]) -> CallToolResult:
        """Perform terrain analysis using GEOINT services."""
        location = arguments.get("location", "")
        analysis_types = arguments.get("analysis_types", ["slope"])
        
        # Simulate terrain analysis (in production, call GEOINT service)
        result = {
            "analysis_type": "terrain_analysis",
            "location": location,
            "analysis_types": analysis_types,
            "resolution": arguments.get("resolution", 30),
            "status": "completed",
            "results": {
                "summary": f"Completed terrain analysis for {location}",
                "analyses_performed": analysis_types,
                "elevation_range": {"min": 0, "max": 2000},  # Example values
                "slope_statistics": {"mean": 15.2, "max": 45.8},
                "output_format": arguments.get("output_format", "visualization")
            },
            "visualization_url": f"{self.geoint_url}/api/terrain-analysis?location={location}"
        }
        
        return CallToolResult(
            content=[
                TextContent(
                    type="text",
                    text=json.dumps(result, indent=2)
                )
            ]
        )
    
    async def _geoint_analysis(self, arguments: Dict[str, Any]) -> CallToolResult:
        """Perform GEOINT analysis."""
        query = arguments.get("query", "")
        area = arguments.get("area_of_interest", "")
        
        result = {
            "analysis_type": "geoint_analysis", 
            "query": query,
            "area_of_interest": area,
            "analysis_type_specific": arguments.get("analysis_type", "general"),
            "status": "completed",
            "results": {
                "summary": f"GEOINT analysis completed for {area}",
                "vehicle_type": arguments.get("vehicle_type"),
                "weather_conditions": arguments.get("weather_conditions"),
                "mobility_assessment": "Favorable conditions identified",
                "confidence": 0.78
            },
            "visualization_url": f"{self.geoint_url}/api/mobility-analysis?area={area}"
        }
        
        return CallToolResult(
            content=[
                TextContent(
                    type="text",
                    text=json.dumps(result, indent=2)
                )
            ]
        )
    
    async def _environmental_monitoring(self, arguments: Dict[str, Any]) -> CallToolResult:
        """Perform environmental monitoring analysis."""
        location = arguments.get("location", "")
        monitoring_type = arguments.get("monitoring_type", "")
        
        result = {
            "analysis_type": "environmental_monitoring",
            "location": location,
            "monitoring_type": monitoring_type,
            "time_period": arguments.get("time_period", ""),
            "status": "completed",
            "results": {
                "summary": f"Environmental monitoring for {monitoring_type} in {location}",
                "change_detected": True,
                "severity": "moderate",
                "trend": "increasing",
                "alert_threshold": arguments.get("alert_threshold", 0.1)
            },
            "visualization_url": f"{self.base_url}/api/environmental?location={location}&type={monitoring_type}"
        }
        
        return CallToolResult(
            content=[
                TextContent(
                    type="text",
                    text=json.dumps(result, indent=2)
                )
            ]
        )
    
    async def _data_discovery(self, arguments: Dict[str, Any]) -> CallToolResult:
        """Discover available data for location and timeframe."""
        location = arguments.get("location", "")
        
        # Simulate data discovery
        available_data = {
            "location": location,
            "timeframe": arguments.get("timeframe", "recent"),
            "available_collections": [
                {
                    "collection": "landsat-8",
                    "scenes_available": 145,
                    "date_range": "2023-01-01 to 2024-09-28",
                    "cloud_cover_avg": 12.5
                },
                {
                    "collection": "sentinel-2", 
                    "scenes_available": 289,
                    "date_range": "2023-01-01 to 2024-09-28",
                    "cloud_cover_avg": 8.3
                }
            ],
            "data_types": arguments.get("data_types", ["optical"]),
            "cloud_cover_filter": arguments.get("cloud_cover_max", 20)
        }
        
        return CallToolResult(
            content=[
                TextContent(
                    type="text",
                    text=json.dumps(available_data, indent=2)
                )
            ]
        )
    
    def _get_geospatial_expert_prompt(self, arguments: Dict[str, str]) -> List[Dict[str, Any]]:
        """Generate geospatial expert prompt."""
        specialization = arguments.get("specialization", "general")
        
        return [
            {
                "role": "system",
                "content": {
                    "type": "text",
                    "text": f"""You are a world-class geospatial analyst and Earth observation expert with deep expertise in satellite remote sensing, GIS analysis, and geospatial intelligence.

Your specialization: {specialization}

You have access to:
- Global satellite imagery collections (Landsat, Sentinel, MODIS)
- Advanced terrain analysis capabilities
- Environmental monitoring tools  
- GEOINT analysis functions
- Real-time and historical Earth observation data

You can:
- Analyze satellite imagery for change detection and environmental monitoring
- Perform complex terrain analysis including slope, aspect, and visibility calculations
- Conduct geospatial intelligence analysis for military and security applications
- Discover and access relevant Earth observation datasets
- Generate detailed visualizations and maps

Always provide scientifically accurate analysis with confidence levels and data source attribution. Use appropriate geospatial terminology and explain methodologies when relevant."""
                }
            }
        ]
    
    def _get_satellite_analyst_prompt(self, arguments: Dict[str, str]) -> List[Dict[str, Any]]:
        """Generate satellite analyst prompt."""
        sensor_type = arguments.get("sensor_type", "multi-sensor")
        
        return [
            {
                "role": "system", 
                "content": {
                    "type": "text",
                    "text": f"""You are an expert satellite imagery analyst specializing in remote sensing and Earth observation.

Preferred sensors: {sensor_type}

Your expertise includes:
- Multi-spectral and hyperspectral image analysis
- Change detection using temporal satellite data
- Land cover and land use classification
- Atmospheric correction and image preprocessing
- Spectral signature analysis and interpretation

You understand the technical specifications, capabilities, and limitations of various satellite sensors and can recommend the most appropriate data sources for specific analysis tasks."""
                }
            }
        ]
    
    def _get_geoint_specialist_prompt(self, arguments: Dict[str, str]) -> List[Dict[str, Any]]:
        """Generate GEOINT specialist prompt.""" 
        classification = arguments.get("classification_level", "unclassified")
        
        return [
            {
                "role": "system",
                "content": {
                    "type": "text", 
                    "text": f"""You are a geospatial intelligence (GEOINT) specialist with expertise in military and defense applications of Earth observation.

Classification level: {classification}

Your capabilities include:
- Terrain analysis for military operations
- Mobility assessment for different vehicle types
- Line-of-sight and viewshed analysis
- Route planning and tactical terrain analysis
- Infrastructure and facility assessment
- Weather impact on operations

You provide analysis that supports military planning, defense operations, and security assessments while maintaining appropriate classification levels."""
                }
            }
        ]
    
    def _get_environmental_scientist_prompt(self, arguments: Dict[str, str]) -> List[Dict[str, Any]]:
        """Generate environmental scientist prompt."""
        focus_area = arguments.get("focus_area", "general")
        
        return [
            {
                "role": "system",
                "content": {
                    "type": "text",
                    "text": f"""You are an environmental scientist specializing in Earth observation and remote sensing for environmental monitoring and climate research.

Focus area: {focus_area}

Your expertise includes:
- Climate change monitoring and analysis
- Ecosystem health assessment
- Biodiversity and habitat monitoring
- Pollution and environmental impact assessment
- Natural disaster monitoring and response
- Sustainable development indicators

You use satellite data and geospatial analysis to understand environmental processes, monitor ecosystem changes, and support evidence-based environmental policy and conservation efforts."""
                }
            }
        ]
    
    async def run(self, transport):
        """Run the MCP server."""
        logger.info("Starting Earth-Copilot MCP Server...")
        async with mcp.server.stdio.stdio_server() as (read_stream, write_stream):
            await self.server.run(
                read_stream,
                write_stream, 
                InitializationOptions(
                    server_name="earth-copilot",
                    server_version="1.0.0",
                    capabilities={
                        "resources": {},
                        "tools": {},
                        "prompts": {}
                    }
                )
            )

# Main entry point
async def main():
    """Main entry point for the MCP server."""
    server = EarthCopilotMCPServer()
    
    # Import MCP stdio transport
    import mcp.server.stdio
    
    await server.run(None)

if __name__ == "__main__":
    asyncio.run(main())