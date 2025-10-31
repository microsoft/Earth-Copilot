# Earth-Copilot Model Context Protocol (MCP) Implementation

This document describes the complete Model Context Protocol (MCP) implementation for Earth-Copilot, providing rich geospatial intelligence capabilities through a standardized interface.

## Overview

The Earth-Copilot MCP server transforms the existing geospatial analysis capabilities into a rich, context-aware service that can be consumed by AI agents, orchestrators, and applications using the Model Context Protocol standard.

### Key Benefits vs Traditional Tool Approach

| Feature | Traditional Tool | MCP Implementation |
|---------|------------------|-------------------|
| **Context Sharing** | ❌ Stateless, no memory | ✅ Rich context across conversations |
| **Resource Access** | ❌ Limited to parameters | ✅ Direct access to STAC catalogs, datasets |
| **Discovery** | ❌ Static tool definitions | ✅ Dynamic capability discovery |
| **Conversation Flow** | ❌ Single request-response | ✅ Multi-turn analysis workflows |
| **Data Integration** | ❌ External data handling | ✅ Built-in resource management |
| **Specialized Prompts** | ❌ Generic responses | ✅ Domain-specific expert prompts |

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                    Azure API Management                     │
│  ┌─────────────────┐ ┌─────────────────┐ ┌──────────────┐  │
│  │  Authentication │ │   Rate Limiting │ │   Caching    │  │
│  │   & Security    │ │   & Quotas      │ │ & Analytics  │  │
│  └─────────────────┘ └─────────────────┘ └──────────────┘  │
└─────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────┐
│              Earth-Copilot MCP Server                      │
│  ┌─────────────────┐ ┌─────────────────┐ ┌──────────────┐  │
│  │   MCP Protocol  │ │  HTTP Bridge    │ │ Context Mgmt │  │
│  │    Handler      │ │   (FastAPI)     │ │   & State    │  │
│  └─────────────────┘ └─────────────────┘ └──────────────┘  │
└─────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────┐
│               Earth-Copilot Core Services                  │
│  ┌─────────────────┐ ┌─────────────────┐ ┌──────────────┐  │
│  │  Router Function│ │  GEOINT Service │ │ STAC Catalogs│  │
│  │      App        │ │   Function App  │ │ & Datasets   │  │
│  └─────────────────┘ └─────────────────┘ └──────────────┘  │
└─────────────────────────────────────────────────────────────┘
```

## MCP Capabilities

### 1. Tools (Analysis Functions)

**analyze_satellite_imagery**
- Description: Analyze satellite imagery for specific locations and timeframes using STAC collections
- Parameters: query, location, timeframe, collections, analysis_type
- Returns: Analysis results with visualization URLs

**terrain_analysis**
- Description: Perform geospatial terrain analysis including slope, aspect, elevation
- Parameters: location, analysis_types, resolution, output_format
- Returns: Terrain analysis data and maps

**geoint_analysis**
- Description: Military/intelligence geospatial analysis including mobility and line-of-sight
- Parameters: query, area_of_interest, analysis_type, vehicle_type, weather_conditions
- Returns: GEOINT analysis results

**environmental_monitoring**
- Description: Monitor environmental changes over time using multi-temporal satellite data
- Parameters: location, monitoring_type, time_period, alert_threshold
- Returns: Environmental change analysis

**data_discovery**
- Description: Discover available satellite data and STAC collections
- Parameters: location, timeframe, data_types, cloud_cover_max
- Returns: Available datasets and metadata

### 2. Resources (Data Access)

**earth://stac/{collection}**
- Access to STAC catalog information
- Collections: landsat-8, sentinel-2, modis
- Provides metadata, coverage, update frequency

**earth://elevation/copernicus-dem**
- Global Digital Elevation Model access
- 30m resolution, global coverage
- Supports terrain analysis workflows

**earth://analysis/capabilities**
- Dynamic analysis capability discovery
- Available tools and their parameters
- Performance characteristics

**earth://context/{conversation_id}**
- Conversation context preservation
- Previous analysis results
- User preferences and history

### 3. Prompts (Specialized Contexts)

**geospatial_expert**
- Expert geospatial analyst persona
- Specialization parameter (environmental, military, disaster, urban)
- Deep remote sensing knowledge

**satellite_analyst**
- Satellite imagery analysis specialist
- Sensor type preference (landsat, sentinel, modis)
- Technical sensor expertise

**geoint_specialist**
- Geospatial intelligence expert
- Classification level handling
- Military/defense focus

**environmental_scientist**
- Environmental monitoring specialist
- Focus area parameter (climate, biodiversity, pollution)
- Conservation and policy expertise

## Implementation Components

### 1. MCP Server (`server.py`)

Core MCP protocol implementation with:
- JSON-RPC 2.0 protocol handling
- Tool execution management
- Resource access control
- Prompt generation
- Context preservation

### 2. HTTP Bridge (`mcp_bridge.py`)

FastAPI-based HTTP adapter providing:
- REST API endpoints for MCP functionality
- OpenAPI/Swagger documentation
- Standard HTTP status codes and error handling
- CORS support for web applications

### 3. APIM Integration

Azure API Management configuration with:
- OAuth 2.0 / JWT authentication
- Rate limiting and quotas per subscription
- Response caching for performance
- Circuit breaker patterns
- Comprehensive monitoring and analytics

## Deployment Options

### Option 1: Standalone MCP Server
```bash
# Install dependencies
pip install -r requirements.txt

# Run MCP server
python server.py
```

### Option 2: HTTP Bridge for Web Integration
```bash
# Run FastAPI bridge
uvicorn mcp_bridge:app --host 0.0.0.0 --port 8080
```

### Option 3: Azure Function App (Recommended)
```powershell
# Deploy to Azure with APIM
.\deploy-mcp-server.ps1 -ResourceGroupName "earth-copilot-rg" -FunctionAppName "earth-copilot-mcp" -DeployApim
```

## API Endpoints (HTTP Bridge)

### MCP Protocol Endpoints
- `POST /tools/list` - List available tools
- `POST /tools/call` - Execute a tool
- `POST /resources/list` - List available resources
- `POST /resources/read` - Read resource data
- `POST /prompts/list` - List available prompts
- `POST /prompts/get` - Get prompt content

### High-Level Analysis Endpoints
- `POST /analysis/satellite` - Satellite imagery analysis
- `POST /analysis/terrain` - Terrain analysis
- `POST /analysis/geoint` - GEOINT analysis

### Utility Endpoints
- `GET /health` - Health check
- `GET /` - Service information
- `GET /docs` - API documentation

## Integration Examples

### MCP Client Integration
```typescript
// Connect to MCP server
const mcpClient = new MCPClient("https://earth-copilot-mcp.azurewebsites.net");

// List available tools
const tools = await mcpClient.listTools();

// Execute terrain analysis
const result = await mcpClient.callTool("terrain_analysis", {
    location: "Grand Canyon, Arizona",
    analysis_types: ["slope", "aspect", "hillshade"],
    resolution: 30
});

// Access STAC resources
const landsatInfo = await mcpClient.readResource("earth://stac/landsat-8");
```

### REST API Integration
```typescript
// Direct HTTP API calls
const response = await fetch("https://earth-copilot-mcp.azurewebsites.net/analysis/terrain", {
    method: "POST",
    headers: {
        "Content-Type": "application/json",
        "Ocp-Apim-Subscription-Key": "your-api-key"
    },
    body: JSON.stringify({
        query: "Analyze terrain slope for vehicle mobility",
        location: "Afghanistan mountains",
        context: {
            vehicle_type: "heavy_vehicle",
            weather: "dry"
        }
    })
});

const analysis = await response.json();
```

### Agent Framework Integration
```python
# Register Earth-Copilot as MCP sub-agent
earth_copilot_agent = {
    "name": "Earth-Copilot",
    "type": "mcp_server",
    "endpoint": "https://earth-copilot-mcp.azurewebsites.net",
    "capabilities": [
        "satellite_imagery_analysis",
        "terrain_analysis", 
        "environmental_monitoring",
        "geospatial_intelligence"
    ]
}

# Route geospatial queries to Earth-Copilot
async def route_query(query: str):
    if is_geospatial_query(query):
        return await earth_copilot_agent.process(query)
    else:
        return await main_agent.process(query)
```

## Configuration

### Environment Variables
```bash
# MCP Server Configuration
MCP_SERVER_MODE=production
EARTH_COPILOT_BASE_URL=https://your-earth-copilot.azurewebsites.net
GEOINT_SERVICE_URL=https://your-geoint-app.azurewebsites.net

# Azure Integration
APPLICATIONINSIGHTS_CONNECTION_STRING=your-connection-string
AZURE_CLIENT_ID=your-client-id
AZURE_CLIENT_SECRET=your-client-secret
AZURE_TENANT_ID=your-tenant-id

# HTTP Bridge Configuration
HOST=0.0.0.0
PORT=8080
```

### APIM Policies

**Authentication**
```xml
<validate-jwt header-name="Authorization">
    <openid-config url="https://login.microsoftonline.com/common/v2.0/.well-known/openid_configuration" />
    <audiences>
        <audience>api://earth-copilot</audience>
    </audiences>
</validate-jwt>
```

**Rate Limiting**
```xml
<rate-limit calls="1000" renewal-period="3600" />
<quota calls="10000" renewal-period="604800" />
```

**Caching**
```xml
<cache-lookup vary-by-developer="false" downstream-caching-type="none">
    <vary-by-query-parameter>*</vary-by-query-parameter>
</cache-lookup>
<cache-store duration="300" />
```

## Monitoring and Analytics

### Key Metrics
- **Request Volume**: Calls per hour/day
- **Response Times**: P50, P95, P99 latencies
- **Error Rates**: 4xx, 5xx error percentages
- **Tool Usage**: Most popular analysis types
- **Resource Access**: STAC catalog usage patterns
- **Geographic Distribution**: Request origins

### Application Insights Queries
```kusto
// Tool usage analysis
requests
| where url contains "/tools/call"
| extend toolName = tostring(customDimensions.tool_name)
| summarize count() by toolName, bin(timestamp, 1h)
| render timechart

// Performance monitoring
requests
| where url contains "/analysis/"
| summarize 
    avg(duration), 
    percentile(duration, 95),
    count() 
    by operation_Name, bin(timestamp, 1h)
| render timechart

// Error analysis
exceptions
| where cloud_RoleName == "earth-copilot-mcp"
| summarize count() by type, bin(timestamp, 1h)
| render timechart
```

## Security Considerations

### Authentication
- OAuth 2.0 / JWT token validation
- API key management through APIM subscriptions
- Role-based access control (RBAC)

### Data Protection
- HTTPS everywhere with TLS 1.2+
- Input validation and sanitization
- Output filtering for sensitive information

### Rate Limiting
- Per-subscription quotas
- Burst protection
- DDoS mitigation

### Audit Logging
- All API calls logged with user context
- Resource access tracking
- Error and security event logging

## Troubleshooting

### Common Issues

**MCP Server Not Responding**
```bash
# Check server logs
az functionapp logs tail --name earth-copilot-mcp --resource-group your-rg

# Verify configuration
az functionapp config appsettings list --name earth-copilot-mcp --resource-group your-rg
```

**APIM Authentication Errors**
```bash
# Check JWT token
curl -H "Authorization: Bearer your-token" https://your-apim.azure-api.net/earth-copilot/mcp/health

# Verify subscription key
curl -H "Ocp-Apim-Subscription-Key: your-key" https://your-apim.azure-api.net/earth-copilot/mcp/health
```

**Performance Issues**
- Check Application Insights for slow requests
- Monitor STAC API response times
- Verify caching configuration
- Scale Function App plan if needed

## Best Practices

### MCP Integration
1. **Use context preservation** for multi-step analysis workflows
2. **Leverage specialized prompts** for domain expertise
3. **Access resources directly** instead of parameter passing
4. **Handle errors gracefully** with fallback strategies

### Performance Optimization
1. **Enable caching** for repeated queries
2. **Use async operations** for concurrent processing
3. **Implement circuit breakers** for external dependencies
4. **Monitor and tune** based on usage patterns

### Development
1. **Test locally** with HTTP bridge before deployment
2. **Use What-If** deployment for validation
3. **Implement comprehensive logging** for debugging
4. **Version API** for backward compatibility

## Future Enhancements

### Planned Features
- **Real-time data streaming** for continuous monitoring
- **Collaborative analysis** with shared contexts
- **Advanced caching** with intelligent invalidation
- **Plugin architecture** for custom analysis types
- **Multi-language support** for international users

### Integration Roadmap
- **GitHub Copilot integration** for geospatial code generation
- **Microsoft 365 integration** for document and presentation creation
- **Power BI integration** for advanced visualization
- **Azure Digital Twins integration** for 3D modeling

The Earth-Copilot MCP implementation provides a powerful, standards-based approach to geospatial intelligence that scales from simple tool calls to complex multi-agent orchestration scenarios.