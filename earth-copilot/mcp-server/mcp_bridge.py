"""
MCP-to-HTTP Bridge for Earth-Copilot

This module provides an HTTP API that bridges to the MCP (Model Context Protocol) server,
allowing standard HTTP clients to interact with Earth-Copilot's MCP capabilities.

This is particularly useful for:
- APIM integration
- Web application integration
- REST API consumers
- Testing and development
"""

from fastapi import FastAPI, HTTPException, Request, Depends
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from typing import Any, Dict, List, Optional, Union
import asyncio
import json
import logging
import os
import httpx
from datetime import datetime
import uuid

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("earth-copilot-mcp-bridge")

app = FastAPI(
    title="Earth-Copilot MCP Bridge",
    description="HTTP bridge to Earth-Copilot Model Context Protocol server",
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc"
)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Configure appropriately for production
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
    allow_headers=["*"],
)

# Configuration
MCP_SERVER_URL = os.getenv("MCP_SERVER_URL", "http://localhost:8000")
EARTH_COPILOT_BASE_URL = os.getenv("EARTH_COPILOT_BASE_URL", "https://earthcopilot-web-ui.azurewebsites.net")

# Pydantic models for API requests/responses
class MCPRequest(BaseModel):
    jsonrpc: str = Field(default="2.0", description="JSON-RPC version")
    id: str = Field(default_factory=lambda: str(uuid.uuid4()), description="Request ID")
    method: str = Field(description="MCP method name")
    params: Optional[Dict[str, Any]] = Field(default={}, description="Method parameters")

class MCPResponse(BaseModel):
    jsonrpc: str = "2.0"
    id: str
    result: Optional[Dict[str, Any]] = None
    error: Optional[Dict[str, Any]] = None

class ToolCallRequest(BaseModel):
    name: str = Field(description="Tool name to execute")
    arguments: Dict[str, Any] = Field(description="Tool arguments")

class ResourceRequest(BaseModel):
    uri: str = Field(description="Resource URI to read")

class PromptRequest(BaseModel):
    name: str = Field(description="Prompt name")
    arguments: Optional[Dict[str, str]] = Field(default={}, description="Prompt arguments")

class AnalysisRequest(BaseModel):
    query: str = Field(description="Natural language query")
    location: Optional[str] = Field(None, description="Geographic location")
    timeframe: Optional[str] = Field(None, description="Time period")
    analysis_type: Optional[str] = Field(None, description="Type of analysis")
    context: Optional[Dict[str, Any]] = Field(default={}, description="Additional context")

# In-memory MCP client simulation (in production, use actual MCP client)
class MockMCPClient:
    """Mock MCP client for demonstration purposes."""
    
    def __init__(self):
        self.tools = [
            {
                "name": "analyze_satellite_imagery",
                "description": "Analyze satellite imagery for specific locations and timeframes",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "query": {"type": "string"},
                        "location": {"type": "string"},
                        "timeframe": {"type": "string"},
                        "collections": {"type": "array"},
                        "analysis_type": {"type": "string"}
                    },
                    "required": ["query", "location"]
                }
            },
            {
                "name": "terrain_analysis",
                "description": "Perform geospatial terrain analysis",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "location": {"type": "string"},
                        "analysis_types": {"type": "array"},
                        "resolution": {"type": "number"},
                        "output_format": {"type": "string"}
                    },
                    "required": ["location"]
                }
            },
            {
                "name": "geoint_analysis", 
                "description": "Military/intelligence geospatial analysis",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "query": {"type": "string"},
                        "area_of_interest": {"type": "string"},
                        "analysis_type": {"type": "string"},
                        "vehicle_type": {"type": "string"},
                        "weather_conditions": {"type": "string"}
                    },
                    "required": ["query", "area_of_interest"]
                }
            }
        ]
        
        self.resources = [
            {
                "uri": "earth://stac/landsat-8",
                "name": "Landsat-8 Collection",
                "description": "NASA/USGS Landsat-8 satellite imagery collection"
            },
            {
                "uri": "earth://stac/sentinel-2",
                "name": "Sentinel-2 Collection",
                "description": "ESA Sentinel-2 multi-spectral satellite imagery"
            },
            {
                "uri": "earth://elevation/copernicus-dem",
                "name": "Copernicus DEM",
                "description": "Global Digital Elevation Model"
            }
        ]
        
        self.prompts = [
            {
                "name": "geospatial_expert",
                "description": "You are an expert geospatial analyst",
                "arguments": [
                    {
                        "name": "specialization",
                        "description": "Area of specialization",
                        "required": False
                    }
                ]
            },
            {
                "name": "satellite_analyst",
                "description": "You are a satellite imagery analyst",
                "arguments": [
                    {
                        "name": "sensor_type",
                        "description": "Preferred satellite sensor",
                        "required": False
                    }
                ]
            }
        ]
    
    async def list_tools(self):
        """List available tools."""
        return {"tools": self.tools}
    
    async def call_tool(self, name: str, arguments: Dict[str, Any]):
        """Call a tool."""
        tool = next((t for t in self.tools if t["name"] == name), None)
        if not tool:
            raise ValueError(f"Tool not found: {name}")
        
        # Simulate tool execution
        result = {
            "tool": name,
            "arguments": arguments,
            "status": "completed",
            "timestamp": datetime.utcnow().isoformat(),
            "result": {
                "summary": f"Executed {name} with arguments {arguments}",
                "confidence": 0.85,
                "visualization_url": f"{EARTH_COPILOT_BASE_URL}/?query={arguments.get('query', '')}"
            }
        }
        
        return {"content": [{"type": "text", "text": json.dumps(result)}]}
    
    async def list_resources(self):
        """List available resources."""
        return {"resources": self.resources}
    
    async def read_resource(self, uri: str):
        """Read a resource."""
        resource = next((r for r in self.resources if r["uri"] == uri), None)
        if not resource:
            raise ValueError(f"Resource not found: {uri}")
        
        # Simulate resource data
        content = {
            "uri": uri,
            "name": resource["name"],
            "description": resource["description"],
            "data": f"Resource data for {uri}",
            "last_updated": datetime.utcnow().isoformat()
        }
        
        return {"contents": [{"type": "text", "text": json.dumps(content)}]}
    
    async def list_prompts(self):
        """List available prompts."""
        return {"prompts": self.prompts}
    
    async def get_prompt(self, name: str, arguments: Dict[str, str]):
        """Get a prompt."""
        prompt = next((p for p in self.prompts if p["name"] == name), None)
        if not prompt:
            raise ValueError(f"Prompt not found: {name}")
        
        # Generate prompt content based on name and arguments
        specialization = arguments.get("specialization", "general")
        sensor_type = arguments.get("sensor_type", "multi-sensor")
        
        if name == "geospatial_expert":
            content = f"You are a world-class geospatial analyst with expertise in {specialization} applications."
        elif name == "satellite_analyst":
            content = f"You are an expert satellite imagery analyst specializing in {sensor_type} data."
        else:
            content = f"You are a specialized analyst for {name}."
        
        return {
            "description": f"Specialized {name} prompt",
            "messages": [
                {
                    "role": "system",
                    "content": {"type": "text", "text": content}
                }
            ]
        }

# Initialize MCP client
mcp_client = MockMCPClient()

# API Routes

@app.get("/")
async def root():
    """API root endpoint."""
    return {
        "service": "Earth-Copilot MCP Bridge",
        "version": "1.0.0",
        "description": "HTTP bridge to Earth-Copilot Model Context Protocol server",
        "endpoints": {
            "tools": "/tools/",
            "resources": "/resources/",
            "prompts": "/prompts/",
            "analysis": "/analysis/",
            "docs": "/docs"
        }
    }

@app.get("/health")
async def health_check():
    """Health check endpoint."""
    return {
        "status": "healthy",
        "timestamp": datetime.utcnow().isoformat(),
        "mcp_server": MCP_SERVER_URL,
        "capabilities": ["tools", "resources", "prompts"]
    }

# MCP Tools Endpoints
@app.post("/tools/list")
async def list_tools():
    """List available MCP tools."""
    try:
        result = await mcp_client.list_tools()
        return JSONResponse(content=result)
    except Exception as e:
        logger.error(f"Error listing tools: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/tools/call")
async def call_tool(request: ToolCallRequest):
    """Call an MCP tool."""
    try:
        result = await mcp_client.call_tool(request.name, request.arguments)
        return JSONResponse(content=result)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        logger.error(f"Error calling tool {request.name}: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

# MCP Resources Endpoints
@app.post("/resources/list")
async def list_resources():
    """List available MCP resources."""
    try:
        result = await mcp_client.list_resources()
        return JSONResponse(content=result)
    except Exception as e:
        logger.error(f"Error listing resources: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/resources/read")
async def read_resource(request: ResourceRequest):
    """Read an MCP resource."""
    try:
        result = await mcp_client.read_resource(request.uri)
        return JSONResponse(content=result)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        logger.error(f"Error reading resource {request.uri}: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

# MCP Prompts Endpoints  
@app.post("/prompts/list")
async def list_prompts():
    """List available MCP prompts."""
    try:
        result = await mcp_client.list_prompts()
        return JSONResponse(content=result)
    except Exception as e:
        logger.error(f"Error listing prompts: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/prompts/get")
async def get_prompt(request: PromptRequest):
    """Get an MCP prompt."""
    try:
        result = await mcp_client.get_prompt(request.name, request.arguments)
        return JSONResponse(content=result)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        logger.error(f"Error getting prompt {request.name}: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

# High-level Analysis Endpoints
@app.post("/analysis/satellite")
async def analyze_satellite_imagery(request: AnalysisRequest):
    """High-level satellite imagery analysis endpoint."""
    try:
        tool_args = {
            "query": request.query,
            "location": request.location,
            "timeframe": request.timeframe,
            "analysis_type": request.analysis_type or "general"
        }
        
        result = await mcp_client.call_tool("analyze_satellite_imagery", tool_args)
        return JSONResponse(content=result)
    except Exception as e:
        logger.error(f"Error in satellite analysis: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/analysis/terrain")
async def analyze_terrain(request: AnalysisRequest):
    """High-level terrain analysis endpoint."""
    try:
        tool_args = {
            "location": request.location or request.query,
            "analysis_types": ["slope", "aspect", "hillshade"],
            "resolution": 30,
            "output_format": "visualization"
        }
        
        result = await mcp_client.call_tool("terrain_analysis", tool_args)
        return JSONResponse(content=result)
    except Exception as e:
        logger.error(f"Error in terrain analysis: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/analysis/geoint")
async def geoint_analysis(request: AnalysisRequest):
    """High-level GEOINT analysis endpoint."""
    try:
        tool_args = {
            "query": request.query,
            "area_of_interest": request.location or "unspecified",
            "analysis_type": request.analysis_type or "general"
        }
        
        # Add context-specific parameters
        if request.context:
            tool_args.update(request.context)
        
        result = await mcp_client.call_tool("geoint_analysis", tool_args)
        return JSONResponse(content=result)
    except Exception as e:
        logger.error(f"Error in GEOINT analysis: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

# Generic MCP endpoint
@app.post("/mcp")
async def mcp_endpoint(request: MCPRequest):
    """Generic MCP endpoint for direct protocol access."""
    try:
        # Map MCP methods to internal functions
        if request.method == "tools/list":
            result = await mcp_client.list_tools()
        elif request.method == "tools/call":
            name = request.params.get("name")
            arguments = request.params.get("arguments", {})
            result = await mcp_client.call_tool(name, arguments)
        elif request.method == "resources/list":
            result = await mcp_client.list_resources()
        elif request.method == "resources/read":
            uri = request.params.get("uri")
            result = await mcp_client.read_resource(uri)
        elif request.method == "prompts/list":
            result = await mcp_client.list_prompts()
        elif request.method == "prompts/get":
            name = request.params.get("name")
            arguments = request.params.get("arguments", {})
            result = await mcp_client.get_prompt(name, arguments)
        else:
            raise ValueError(f"Unknown MCP method: {request.method}")
        
        return MCPResponse(id=request.id, result=result)
        
    except Exception as e:
        logger.error(f"Error processing MCP request {request.method}: {str(e)}")
        return MCPResponse(
            id=request.id,
            error={
                "code": -32000,
                "message": str(e)
            }
        )

# Error handlers
@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException):
    """Handle HTTP exceptions."""
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "error": {
                "code": exc.status_code,
                "message": exc.detail,
                "timestamp": datetime.utcnow().isoformat()
            }
        }
    )

@app.exception_handler(Exception)
async def general_exception_handler(request: Request, exc: Exception):
    """Handle general exceptions."""
    logger.error(f"Unhandled exception: {str(exc)}")
    return JSONResponse(
        status_code=500,
        content={
            "error": {
                "code": 500,
                "message": "Internal server error",
                "timestamp": datetime.utcnow().isoformat()
            }
        }
    )

if __name__ == "__main__":
    import uvicorn
    
    # Configuration
    host = os.getenv("HOST", "0.0.0.0")
    port = int(os.getenv("PORT", "8080"))
    
    logger.info(f"Starting Earth-Copilot MCP Bridge on {host}:{port}")
    
    uvicorn.run(
        "mcp_bridge:app",
        host=host,
        port=port,
        reload=True,
        log_level="info"
    )