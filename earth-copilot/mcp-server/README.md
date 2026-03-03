# 🌍 Earth Copilot MCP Server - Template & Deployment Guide

## 📘 What is MCP (Model Context Protocol)?

**Model Context Protocol (MCP)** is a standard protocol developed by Anthropic that enables AI assistants (like Claude, GitHub Copilot, or custom agents) to interact with external services in a rich, context-aware manner.

### Why MCP vs Traditional APIs?

| Feature | Traditional REST API | MCP Server |
|---------|---------------------|------------|
| **Context** | ❌ Stateless, no memory | ✅ Multi-turn conversations with preserved context |
| **Discovery** | ❌ Static OpenAPI specs | ✅ Dynamic capability discovery |
| **Resources** | ❌ Manual data fetching | ✅ Direct access to datasets/catalogs |
| **Prompts** | ❌ Generic responses | ✅ Domain-specific expert personas |
| **Integration** | Manual code for each AI | Standard protocol works with all MCP clients |

---

## 🏗️ Architecture Overview

### The MCP Request/Response Flow

```
┌──────────────────────────────────────────────────────────────────┐
│ 1. CLIENT (GitHub Copilot in VS Code)                            │
│    User in Copilot Chat: "Show me the most recent satellite      │
│    data of NYC"                                                  │
└────────────────┬─────────────────────────────────────────────────┘
                 │
                 │ Sends MCP Request:
                 │ {
                 │   "method": "tools/call",
                 │   "params": {
                 │     "name": "analyze_satellite_imagery",
                 │     "arguments": {
                 │       "query": "most recent satellite data",
                 │       "location": "New York City, NY",
                 │       "timeframe": "2025-10-01/2025-10-29"
                 │     }
                 │   }
                 │ }
                 │
┌────────────────▼─────────────────────────────────────────────────┐
│ 2. HOST/TRANSPORT (VS Code MCP Extension)                        │
│    - Receives JSON-RPC message from Copilot                      │
│    - Handles authentication (if HTTP)                            │
│    - Routes to Earth Copilot MCP server                          │
└────────────────┬─────────────────────────────────────────────────┘
                 │
                 │
┌────────────────▼─────────────────────────────────────────────────┐
│ 3. SERVER (Earth Copilot MCP Server)                             │
│    ┌─────────────────────────────────────────────────────────┐   │
│    │ server.py                                               │   │
│    │ - Parses MCP request                                    │   │
│    │ - Validates parameters (location: NYC, timeframe)       │   │
│    │ - Calls analyze_satellite_imagery handler               │   │
│    └──────────────┬──────────────────────────────────────────┘   │
│                   │                                              │
│                   │ HTTP POST to Container App                   │
│                   │                                              │
│    ┌──────────────▼──────────────────────────────────────────┐   │
│    │ Earth Copilot FastAPI Container App                     │   │
│    │ - /api/query endpoint                                   │   │
│    │ - Agent 1-5 processing pipeline                         │   │
│    │ - STAC API queries (Sentinel-2, Landsat-9)              │   │
│    │ - Returns STAC metadata (no map rendering)              │   │
│    └──────────────┬──────────────────────────────────────────┘   │
│                   │                                              │
│    ┌──────────────▼──────────────────────────────────────────┐   │
│    │ MCP Server Formats Response                             │   │
│    │ ❌ NO map UI (MCP context - no web frontend)           │   │
│    │ ✅ Text summaries (dataset names, dates, metadata)     │   │
│    │ ✅ Image URLs (static map previews, thumbnails)        │   │
│    │ ✅ Clickable links (open in browser, download)         │   │
│    │ ✅ Structured data (JSON for follow-up queries)        │   │
│    └─────────────────────────────────────────────────────────┘   │
└────────────────┬─────────────────────────────────────────────────┘
                 │
                 │ Returns MCP Response:
                 │ {
                 │   "result": {
                 │     "content": [
                 │       {
                 │         "type": "text",
                 │         "text": "Found recent satellite data for NYC:\n
                 │                  • Sentinel-2: Oct 27, 2025 (5% clouds)\n
                 │                  • Landsat-9: Oct 25, 2025 (12% clouds)\n
                 │                  📊 View static map: [Preview URL]"
                 │       },
                 │       {
                 │         "type": "image",
                 │         "data": "https://titiler.../preview.png",
                 │         "mimeType": "image/png"
                 │       },
                 │       {
                 │         "type": "resource",
                 │         "resource": {
                 │           "uri": "earth://stac/sentinel-2/...",
                 │           "mimeType": "application/json"
                 │         }
                 │       }
                 │     ]
                 │   }
                 │ }
                 │
┌────────────────▼─────────────────────────────────────────────────┐
│ 4. CLIENT (GitHub Copilot displays result in VS Code)           │
│    ┌─────────────────────────────────────────────────────────┐   │
│    │ 🤖 GitHub Copilot Chat Panel                           │   │
│    │                                                         │   │
│    │ I found recent satellite data for New York City:       │   │
│    │                                                         │   │
│    │ **Sentinel-2** (Oct 27, 2025)                          │   │
│    │ • Cloud cover: 5%                                       │   │
│    │ • Resolution: 10m                                       │   │
│    │ • Bands: RGB + NIR                                      │   │
│    │                                                         │   │
│    │ [Static Map Preview Image Displayed]                   │   │
│    │                                                         │   │
│    │ **Landsat-9** (Oct 25, 2025)                           │   │
│    │ • Cloud cover: 12%                                      │   │
│    │ • Resolution: 30m                                       │   │
│    │                                                         │   │
│    │ 🔗 Open interactive map in browser                      │   │
│    │ 🔗 Download GeoTIFF                                     │   │
│    │                                                         │   │
│    │ Would you like me to analyze these images?             │   │
│    └─────────────────────────────────────────────────────────┘   │
│                                                                  │
│    📝 Note: MCP context = chat-based interface only              │
│       • No interactive map widget in VS Code                     │
│       • Static map images embedded in chat                       │
│       • Links to open full Earth Copilot web UI                 │
│                                                                  │
│    User can ask follow-up questions:                             │
│    "Show me the Sentinel-2 image"                                │
│    "Analyze vegetation in Central Park"                          │
│    "Compare these dates for change detection"                    │
└──────────────────────────────────────────────────────────────────┘
```

**How the User Sees the Response:**

The user types their question in the **VS Code Copilot Chat panel** (accessed via Ctrl+I or the chat icon). GitHub Copilot:

1. **Receives the query** from the user
2. **Identifies** that it needs satellite data (recognizes Earth Copilot MCP server capability)
3. **Calls the MCP server** using the appropriate tool
4. **Receives structured data** (dates, cloud cover, metadata, image URLs)
5. **Formats a chat response** in the VS Code chat window with:
   - ✅ **Text summaries** (natural language descriptions)
   - ✅ **Static map images** (embedded PNG/JPEG previews)
   - ✅ **Clickable links** (to open full Earth Copilot web UI, download data)
   - ✅ **Structured metadata** (for follow-up queries)
   - ❌ **NO interactive map UI** (VS Code Copilot Chat is text-based)
6. **Preserves context** so follow-up questions automatically reference the previous results

**Key Difference: MCP vs Web UI**

| Feature | Earth Copilot Web UI | MCP in VS Code Copilot |
|---------|---------------------|------------------------|
| **Interactive Map** | ✅ Leaflet/Azure Maps | ❌ Not available |
| **Map Rendering** | ✅ Dynamic tile layers | ❌ Static images only |
| **Chat Interface** | ✅ Custom chat panel | ✅ VS Code chat panel |
| **Static Previews** | ✅ Thumbnails | ✅ Embedded images |
| **Data Access** | ✅ Full STAC results | ✅ Full STAC results |
| **Follow-up Context** | ✅ Preserved | ✅ Preserved |
| **External Links** | ✅ Open datasets | ✅ Open in browser |

**Example MCP Response Content:**
- **Text**: "Found Sentinel-2 imagery for Seattle (Oct 27, 2025, 5% cloud cover)"
- **Image**: Static map preview PNG (via TiTiler or similar)
- **Links**: "Open interactive map in Earth Copilot web UI", "Download GeoTIFF"
- **Metadata**: JSON with STAC item details for programmatic access

The response appears in the **Copilot Chat panel** as formatted markdown with embedded actions, making it easy for the user to explore the data without leaving VS Code.
```

---

### 🔗 MCP Tool-to-API Mapping

Each MCP tool corresponds to a specific backend API endpoint in the Earth Copilot Container App. All backend APIs are hosted in **Azure Container Apps** for scalability and reliability.

| MCP Tool | Backend API Endpoint | Status | Description |
|----------|---------------------|--------|-------------|
| `analyze_satellite_imagery` | `/api/query` | ✅ **Working** | General search box queries - routes through agent pipeline |
| `terrain_analysis` | `/api/geoint/terrain` | ✅ **Working** | Pin drop module #1 - terrain elevation, slope, aspect analysis |
| `comparison_analysis` | `/api/geoint/comparison` | ✅ **Working** | Pin drop module #4 - temporal change detection |
| `mobility_analysis` | `/api/geoint/mobility` | 🚧 **Coming Up** | Pin drop module #2 - trafficability and mobility assessment |
| `building_damage_analysis` | `/api/geoint/building-damage` | 🚧 **Coming Up** | Pin drop module #3 - structural damage detection |
| `animation_generation` | `/api/geoint/animation` | 🚧 **Coming Up** | Pin drop module #5 - time-lapse satellite animation |

**📖 Full Tool Definitions**: See the [MCP Capabilities](#-mcp-capabilities-explained) section below for complete parameter schemas and usage examples.

**What are MCP tools?** MCP tools are callable functions exposed by the MCP server that AI assistants can invoke. In Earth Copilot's implementation, each tool acts as a wrapper that calls a specific backend API endpoint in the Earth Copilot Container App. This 1:1 mapping keeps the architecture simple and maintainable.

For example: 

✅ analyze_satellite_imagery** 
Maps to:** `/api/query` (Main search box queries)

```json
{
  "name": "analyze_satellite_imagery",
  "description": "Analyze satellite imagery for specific locations and timeframes using STAC collections",
  "parameters": {
    "query": {
      "type": "string",
      "description": "Natural language query describing the analysis needed",
      "required": true
    },
    "location": {
      "type": "string",
      "description": "Geographic location (place name, coordinates, or bounding box)",
      "required": true
    },
    "timeframe": {
      "type": "string",
      "description": "Time period for analysis (e.g., '2023-01-01/2023-12-31')"
    },
    "collections": {
      "type": "array",
      "items": ["landsat-8", "sentinel-2", "modis"],
      "description": "STAC collections to use"
    },
    "analysis_type": {
      "type": "string",
      "enum": ["change_detection", "environmental_monitoring", "disaster_assessment", "vegetation_analysis"],
      "description": "Type of analysis to perform"
    }
  }
}
```
**Implementation**: ✅ Fully working - calls `/api/query` endpoint which routes through the agent pipeline (semantic translator, collection mapper, datetime translator, etc.)

---

## 🚀 Getting Started

### Quick Setup (5 minutes)

Want to get the MCP server running immediately? See the **[Quick Start Guide](QUICK_START.md)** for:
- Installation steps
- Basic configuration
- Running the server locally or in Azure
- Testing your deployment

### Deploy to Azure (15 minutes)

Ready to deploy to production? See the **[Deployment & Testing Guide](DEPLOYMENT_TESTING_GUIDE.md)** for:
- Docker containerization
- Azure Container Apps deployment
- Comprehensive testing suite
- Monitoring and troubleshooting

**Quick deploy:**
```powershell
cd earth-copilot/mcp-server
.\quick-deploy.ps1 -ResourceGroup "earth-copilot-rg" -EarthCopilotBackendUrl "https://your-backend.azurecontainerapps.io"
```

### Connect AI Clients

Once your server is running, connect your AI assistant. See the **[Client Connection Guide](CLIENT_CONNECTION_GUIDE.md)** for detailed instructions on:
- **Claude Desktop** - Chat with your satellite data
- **GitHub Copilot** - Geospatial intelligence in VS Code
- **Custom Python/TypeScript clients** - Build your own integrations
- **REST API** - HTTP-based access for any application

### Deployment Options Summary

| Option | Best For | Setup Time | Guide |
|--------|----------|------------|-------|
| **Local (stdio)** | Development, testing, VS Code | 5 min | [Quick Start](QUICK_START.md) |
| **HTTP Server** | Web apps, remote access | 10 min | [Quick Start](QUICK_START.md) |
| **Azure Container Apps** | Production, scalability | 15 min | [Deployment Scripts](deploy-mcp-server.ps1) |
| **Azure APIM** | Enterprise, multiple consumers | 30 min | [APIM Guide](apim/) |

---

## 🗂️ MCP Capabilities Explained

The Earth Copilot MCP Server exposes three types of capabilities to AI assistants:

### 1. **Tools** (Callable Actions)

See the [Tool-to-API Mapping](#-mcp-tool-to-api-mapping) table above for all 6 tools. Tools are functions the AI can call to perform analysis:
- `analyze_satellite_imagery` - Search and analyze satellite data
- `terrain_analysis` - Analyze terrain features (elevation, slope, aspect)
- `comparison_analysis` - Compare imagery across time periods
- `mobility_analysis`, `building_damage_analysis`, `animation_generation` - Coming up!

### 2. **Resources** (Direct Data Access)

Resources let AI assistants read data directly without calling a function. When an AI connects to this MCP server, it can:

- **Browse available resources** - List all 6 resources exposed by the server
- **Read STAC collection metadata** - Get details about Landsat-8, Sentinel-2, MODIS datasets
- **Access elevation data info** - Learn about Copernicus DEM specifications
- **Discover analysis capabilities** - See what tools and parameters are available
- **Retrieve conversation context** - Access previous queries for multi-turn conversations

**Available Resources:**

```typescript
// STAC satellite collections
earth://stac/sentinel-2      // ESA Sentinel-2 multi-spectral imagery (10m resolution)
earth://stac/landsat-8       // NASA/USGS Landsat-8 global coverage
earth://stac/modis           // NASA MODIS environmental monitoring

// Elevation data
earth://elevation/copernicus-dem  // Global Digital Elevation Model

// Server metadata
earth://analysis/capabilities     // List of available analysis tools
earth://context/{conversation_id} // Preserved context for multi-turn chat
```

**Example Usage:**
```
User: "What Sentinel-2 data is available?"

AI: *Reads resource earth://stac/sentinel-2*

AI: "Sentinel-2 provides 13 spectral bands at 10-60m resolution, 
     covering global land and coastal areas since 2015. The collection
     includes multispectral imagery optimized for land monitoring,
     with revisit time of 5 days at the equator..."
```

**How Resources Work:**
1. AI calls `list_resources()` to see what's available
2. AI picks a resource URI (e.g., `earth://stac/sentinel-2`)
3. AI calls `read_resource(uri)` to get the data
4. MCP server returns metadata as text/JSON without calling backend APIs

This is faster than tools because resources are **read-only metadata** that the MCP server can return immediately without backend processing.


---

## 🚀 Deployment Options (Step 1: Run the MCP Server)

**These options determine WHERE and HOW the MCP server itself runs.** Choose based on your environment and scale needs. The server must be running before AI clients can connect to it.

### Option 1: **Local Development** (stdio transport)

Best for: Testing, development, VS Code integration

```bash
# 1. Install dependencies
cd earth-copilot/mcp-server
pip install -r requirements.txt

# 2. Configure environment
cp .env.example .env
# Edit .env with your Earth Copilot backend URL

# 3. Run MCP server
python server.py

# 4. Connect from VS Code
# Add to VS Code settings.json:
{
  "mcp.servers": {
    "earth-copilot": {
      "command": "python",
      "args": ["server.py"],
      "cwd": "/path/to/earth-copilot/mcp-server"
    }
  }
}
```

### Option 2: **HTTP Server** (FastAPI bridge)

Best for: Web apps, REST API consumers, remote access

```bash
# 1. Run HTTP bridge
uvicorn mcp_bridge:app --host 0.0.0.0 --port 8080

# 2. Test with curl
curl -X POST http://localhost:8080/tools/list

# 3. Integrate with any HTTP client
fetch("http://localhost:8080/analysis/satellite", {
  method: "POST",
  headers: { "Content-Type": "application/json" },
  body: JSON.stringify({
    query: "Show me wildfires in California",
    location: "California",
    timeframe: "2024-08-01/2024-08-31"
  })
})
```

### Option 3: **Azure Container App** (Recommended for Production)

Best for: Enterprise deployment, scalability, security

```powershell
# 1. Deploy to Azure Container Apps
az containerapp create `
  --name earth-copilot-mcp `
  --resource-group earth-copilot-rg `
  --environment your-container-env `
  --image mcr.microsoft.com/azuredocs/containerapps-helloworld:latest `
  --target-port 8080 `
  --ingress external `
  --query properties.configuration.ingress.fqdn

# 2. Configure your backend URLs (Container App environment variables)
az containerapp update `
  --name earth-copilot-mcp `
  --resource-group earth-copilot-rg `
  --set-env-vars `
    EARTH_COPILOT_BASE_URL=https://your-backend-container.azurecontainerapps.io `
    GEOINT_SERVICE_URL=https://your-geoint-container.azurecontainerapps.io

# 3. Get your endpoint
# Output: https://earth-copilot-mcp.azurecontainerapps.io
```

### Option 4: **Azure API Management** (Enterprise)

Best for: Multiple consumers, rate limiting, monetization

Adds:
- OAuth 2.0 authentication
- Rate limiting per subscriber
- Response caching
- Analytics dashboard
- Developer portal

```powershell
# Deploy APIM pointing to your Container App
cd apim
.\deploy-apim.ps1 `
  -ResourceGroupName "earth-copilot-rg" `
  -ApimServiceName "earth-copilot-api" `
  -PublisherEmail "admin@yourcompany.com" `
  -PublisherName "Your Company" `
  -McpServerUrl "https://earth-copilot-mcp.azurecontainerapps.io"

# Result:
# MCP Server: https://earth-copilot-mcp.azurecontainerapps.io
# APIM Gateway: https://earth-copilot-api.azure-api.net/earth-copilot/mcp
# Developer Portal: https://earth-copilot-api.developer.azure-api.net
```

---

## 🔌 Integration Examples (Step 2: Connect AI Clients)

**Once your MCP server is running (from Step 1), connect AI assistants to it.** These examples show how different AI clients discover and use your MCP server's capabilities.

### For GitHub Copilot

**What this does:** Enables GitHub Copilot in VS Code to call your MCP server for satellite data analysis.

Create `.github/copilot/mcp-servers.json`:

```json
{
  "earth-copilot": {
    "type": "http",
    "url": "https://my-earth-copilot-mcp.azurewebsites.net",
    "headers": {
      "Ocp-Apim-Subscription-Key": "${APIM_KEY}"
    }
  }
}
```

Then in VS Code:
```python
# User comment: "Get Sentinel-2 imagery of Seattle with low clouds"

# Copilot: *Calls MCP server via HTTP*
response = await earth_copilot_client.call_tool(
    "analyze_satellite_imagery",
    {
        "query": "Sentinel-2 imagery of Seattle",
        "location": "Seattle, WA",
        "timeframe": "2024-10-01/2024-10-31",
        "collections": ["sentinel-2"],
        "cloud_cover_max": 10
    }
)
```

### For Claude Desktop

**What this does:** Configures Claude Desktop app to use your MCP server for geospatial queries.

Create `claude_desktop_config.json`:

```json
{
  "mcpServers": {
    "earth-copilot": {
      "command": "python",
      "args": ["/path/to/earth-copilot/mcp-server/server.py"],
      "env": {
        "EARTH_COPILOT_BASE_URL": "https://your-backend.azurewebsites.net"
      }
    }
  }
}
```

Then in Claude Desktop:
```
You: Show me recent wildfire activity in California

Claude: *Uses analyze_satellite_imagery tool*
I found 22 active fire detections in California from MODIS data...
[Shows map visualization]

You: What's the terrain like in those areas?

Claude: *Uses terrain_analysis tool with context from previous query*
The affected areas have steep terrain with slopes averaging 25-35 degrees...
```

### For Custom Agent Framework

**What this does:** Shows how to build your own Python application that connects to the MCP server.

```python
from mcp_client import MCPClient

# Initialize MCP client
client = MCPClient("https://my-earth-copilot-mcp.azurewebsites.net")

# List available tools
tools = await client.list_tools()
print(f"Available tools: {[t.name for t in tools]}")

# Execute terrain analysis
result = await client.call_tool(
    "terrain_analysis",
    {
        "location": "Grand Canyon, Arizona",
        "analysis_types": ["slope", "aspect", "hillshade"],
        "resolution": 30
    }
)

# Access STAC resources
sentinel2_info = await client.read_resource("earth://stac/sentinel-2")
print(f"Sentinel-2 info: {sentinel2_info}")

# Use specialized prompt
expert_context = await client.get_prompt(
    "geospatial_expert",
    {"specialization": "environmental"}
)
# AI now has environmental geospatial expert persona
```

---

## 📁 Template Structure

```
earth-copilot/mcp-server/
├── server.py                 # Core MCP server implementation
├── mcp_bridge.py            # HTTP/REST adapter
├── requirements.txt          # Python dependencies
├── package.json             # MCP metadata and capabilities
├── .env.example             # Environment template
├── deploy-mcp-server.ps1    # Azure deployment script
├── MCP_IMPLEMENTATION_GUIDE.md  # Detailed docs
├── README.md                # This file
├── __init__.py              # Python module init
└── apim/
    ├── deploy-apim.ps1      # APIM deployment
    └── apim-template.json   # APIM ARM template
```

---

## ⚙️ Configuration Guide

### Environment Variables

Create `.env` file:

```bash
# Earth Copilot Backend
EARTH_COPILOT_BASE_URL=https://your-earth-copilot-backend.azurewebsites.net
GEOINT_SERVICE_URL=https://your-geoint-app.azurewebsites.net

# Azure Integration (for production)
APPLICATIONINSIGHTS_CONNECTION_STRING=InstrumentationKey=xxx
AZURE_CLIENT_ID=your-app-registration-id
AZURE_CLIENT_SECRET=your-secret
AZURE_TENANT_ID=your-tenant-id

# Server Configuration
MCP_SERVER_MODE=production  # or development
HOST=0.0.0.0
PORT=8080

# Optional: APIM
APIM_SUBSCRIPTION_KEY=your-subscription-key
```

---

## 🧪 Testing Your MCP Server

### 1. Test Tools Endpoint

```bash
# List available tools
curl -X POST http://localhost:8080/tools/list

# Expected output:
{
  "tools": [
    {
      "name": "analyze_satellite_imagery",
      "description": "Analyze satellite imagery...",
      "inputSchema": {...}
    },
    ...
  ]
}
```

### 2. Test Tool Execution

```bash
# Execute satellite analysis
curl -X POST http://localhost:8080/tools/call \
  -H "Content-Type: application/json" \
  -d '{
    "name": "analyze_satellite_imagery",
    "arguments": {
      "query": "Show me wildfires in California",
      "location": "California",
      "timeframe": "2024-08-01/2024-08-31"
    }
  }'

# Expected output:
{
  "result": {
    "content": [
      {
        "type": "text",
        "text": "Found 22 MODIS fire features in California..."
      },
      {
        "type": "image",
        "data": "https://titiler.../map.png"
      }
    ]
  }
}
```

### 3. Test Resources

```bash
# Read STAC collection info
curl -X POST http://localhost:8080/resources/read \
  -H "Content-Type: application/json" \
  -d '{
    "uri": "earth://stac/sentinel-2"
  }'

# Expected output:
{
  "contents": [
    {
      "type": "text",
      "text": "Sentinel-2 Level-2A Collection\nResolution: 10-60m\nCoverage: Global..."
    }
  ]
}
```

---

## 🎓 Tutorial: Create Your Own MCP Server Template

### Step 1: Clone This Template

```bash
# Clone Earth Copilot repo
git clone https://github.com/microsoft/Earth-Copilot
cd Earth-Copilot/earth-copilot/mcp-server

# Create your own MCP server folder
mkdir ../my-geospatial-mcp
cp -r * ../my-geospatial-mcp/
cd ../my-geospatial-mcp
```

### Step 2: Customize Your Tools

Edit `server.py`:

```python
# Add your custom tool
Tool(
    name="my_custom_analysis",
    description="My custom geospatial analysis",
    inputSchema={
        "type": "object",
        "properties": {
            "location": {"type": "string"},
            "custom_param": {"type": "string"}
        },
        "required": ["location"]
    }
)

# Add your custom tool handler
@self.server.call_tool()
async def handle_call_tool(name: str, arguments: dict):
    if name == "my_custom_analysis":
        return await self._my_custom_analysis(arguments)
```

### Step 3: Add Your Resources

```python
# Add custom resource
Resource(
    uri="myapp://data/custom-collection",
    name="My Custom Data",
    description="Description of my custom dataset",
    mimeType="application/json"
)

# Add custom resource handler
@self.server.read_resource()
async def handle_read_resource(uri: str):
    if uri.startswith("myapp://data/"):
        return await self._read_custom_data(uri)
```

### Step 4: Deploy Your MCP Server

```powershell
# Deploy to Azure Container Apps
az containerapp create `
  --name my-geospatial-mcp `
  --resource-group my-geospatial-rg `
  --environment my-container-env `
  --image your-registry.azurecr.io/my-geospatial-mcp:latest `
  --target-port 8080 `
  --ingress external
```

### Step 5: Share Your Template

```bash
# Create template package
cp server.py my-template/
cp mcp_bridge.py my-template/
cp requirements.txt my-template/
cp README.md my-template/

# Publish to GitHub
cd my-template
git init
git add .
git commit -m "Initial MCP server template"
git push origin main
```

---

## 🔐 Security Best Practices

### 1. **Authentication**

For HTTP deployments, always use authentication:

```python
# In mcp_bridge.py
from fastapi import Depends, HTTPException, Header

async def verify_api_key(x_api_key: str = Header()):
    if x_api_key != os.getenv("API_KEY"):
        raise HTTPException(status_code=401, detail="Invalid API key")
    return x_api_key

# Protect endpoints
@app.post("/tools/call", dependencies=[Depends(verify_api_key)])
async def call_tool(request: ToolCallRequest):
    ...
```

### 2. **Rate Limiting**

Use APIM or implement custom rate limiting:

```python
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address

limiter = Limiter(key_func=get_remote_address)
app.state.limiter = limiter

@app.post("/tools/call")
@limiter.limit("100/minute")
async def call_tool(request: Request, tool_request: ToolCallRequest):
    ...
```

### 3. **Input Validation**

Always validate user inputs:

```python
from pydantic import BaseModel, Field, validator

class AnalysisRequest(BaseModel):
    query: str = Field(..., max_length=500)
    location: str = Field(..., max_length=200)
    
    @validator('query')
    def validate_query(cls, v):
        # Prevent injection attacks
        if any(char in v for char in ['<', '>', ';', '&']):
            raise ValueError("Invalid characters in query")
        return v
```

---

## 📊 Monitoring & Analytics

### Application Insights Integration

```python
# In server.py
from opencensus.ext.azure.log_exporter import AzureLogHandler
import logging

# Configure logging
logger = logging.getLogger(__name__)
logger.addHandler(AzureLogHandler(
    connection_string=os.getenv('APPLICATIONINSIGHTS_CONNECTION_STRING')
))

# Log tool calls
logger.info(f"Tool called: {tool_name}", extra={
    'custom_dimensions': {
        'tool': tool_name,
        'arguments': arguments,
        'user_id': user_id
    }
})
```

### Key Metrics to Track

```kusto
// Tool usage analysis
requests
| where url contains "/tools/call"
| extend toolName = tostring(customDimensions.tool)
| summarize count() by toolName, bin(timestamp, 1h)
| render timechart

// Performance monitoring
requests
| summarize 
    avg(duration), 
    percentile(duration, 95),
    count() 
    by operation_Name
```

---

## 🆘 Troubleshooting

### Common Issues

**Issue: MCP server not responding**
```bash
# Check if server is running
curl http://localhost:8080/health

# Check logs
tail -f logs/mcp-server.log
```

**Issue: Tool execution fails**
```python
# Add detailed error logging
try:
    result = await execute_tool(name, arguments)
except Exception as e:
    logger.error(f"Tool execution failed: {str(e)}", exc_info=True)
    raise
```

**Issue: Resource not found**
```python
# Verify resource URI format
logger.info(f"Attempting to read resource: {uri}")
parsed = urlparse(uri)
logger.info(f"Parsed URI - scheme: {parsed.scheme}, path: {parsed.path}")
```

---

## 📚 Additional Resources

- **MCP Specification**: https://modelcontextprotocol.io/
- **Earth Copilot Docs**: `../documentation/`
- **STAC Collections**: `../documentation/data_collections/STAC_COLLECTIONS.md`
- **Agent System**: `../documentation/app_workflow/AGENT_SYSTEM_OVERVIEW.md`

---

## 💡 Use Cases

### 1. **Claude Desktop Integration**
Users chat with Claude to analyze satellite imagery without leaving the desktop app.

### 2. **VS Code Extension**
Developers get geospatial code suggestions powered by real satellite data.

### 3. **Custom Agent Orchestration**
Multi-agent systems route geospatial queries to Earth Copilot MCP server.

### 4. **Automated Workflows**
CI/CD pipelines use MCP server for environmental compliance checks.

### 5. **Research & Education**
Students access Earth observation data through conversational interfaces.

---

## 🚀 Next Steps

1. **Deploy the template** to your Azure subscription
2. **Connect** your AI assistant (Claude/Copilot)
3. **Test** with example queries
4. **Customize** tools for your use case
5. **Share** your MCP server with others!

---

**Questions?** Check the [MCP Implementation Guide](MCP_IMPLEMENTATION_GUIDE.md) or open an issue on GitHub.

**License:** MIT  
**Maintainer:** Earth Copilot Team
