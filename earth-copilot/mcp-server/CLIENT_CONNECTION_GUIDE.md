#  Client Connection Guide

This guide shows you how to connect various AI assistants and applications to your Earth Copilot MCP server.

---

##  Table of Contents

1. [Claude Desktop](#1-claude-desktop)
2. [VS Code with GitHub Copilot](#2-vs-code-with-github-copilot)
3. [Custom Python Client](#3-custom-python-client)
4. [Custom TypeScript Client](#4-custom-typescript-client)
5. [REST API Integration](#5-rest-api-integration)
6. [Testing Your Connection](#6-testing-your-connection)

---

## 1. Claude Desktop

### Prerequisites
- Claude Desktop app installed
- Earth Copilot MCP server running

### Configuration

**For Local MCP Server (stdio transport):**

1. Locate your Claude Desktop config file:
   - **macOS**: `~/Library/Application Support/Claude/claude_desktop_config.json`
   - **Windows**: `%APPDATA%\Claude\claude_desktop_config.json`
   - **Linux**: `~/.config/Claude/claude_desktop_config.json`

2. Add your MCP server configuration:

```json
{
  "mcpServers": {
    "earth-copilot": {
      "command": "python",
      "args": [
        "C:\\Users\\YourUser\\Earth-Copilot\\earth-copilot\\mcp-server\\server.py"
      ],
      "env": {
        "EARTH_COPILOT_BASE_URL": "https://your-backend.azurewebsites.net",
        "GEOINT_SERVICE_URL": "https://your-geoint.azurewebsites.net",
        "LOG_LEVEL": "INFO"
      }
    }
  }
}
```

**For Remote MCP Server (HTTP transport):**

```json
{
  "mcpServers": {
    "earth-copilot": {
      "url": "https://your-mcp-server.azurewebsites.net",
      "headers": {
        "Ocp-Apim-Subscription-Key": "your-subscription-key"
      }
    }
  }
}
```

3. Restart Claude Desktop

4. Test the connection:

```
You: Can you see the earth-copilot MCP server?

Claude: Yes! I can see the earth-copilot MCP server with the following capabilities:

Tools:
- analyze_satellite_imagery
- terrain_analysis
- geoint_analysis
- environmental_monitoring
- data_discovery

Resources:
- earth://stac/* (STAC catalog access)
- earth://elevation/* (DEM data)
- earth://analysis/capabilities
- earth://context/* (conversation context)

Prompts:
- geospatial_expert
- satellite_analyst
- geoint_specialist
- environmental_scientist

What would you like to analyze?
```

### Example Usage

```
You: Show me recent wildfire activity in California using MODIS data

Claude: *Calls analyze_satellite_imagery tool*
I found 22 active fire detections in California from MODIS data over the past 7 days...
[Displays map visualization]

You: What's the terrain like in those areas?

Claude: *Calls terrain_analysis tool with context from previous query*
The affected areas have steep terrain with slopes averaging 25-35 degrees...
```

---

## 2. VS Code with GitHub Copilot

### Prerequisites
- VS Code installed
- GitHub Copilot extension installed
- Earth Copilot MCP server running

### Configuration

**Method 1: Workspace Settings**

1. Create `.vscode/settings.json` in your project:

```json
{
  "github.copilot.advanced": {
    "mcpServers": {
      "earth-copilot": {
        "type": "http",
        "url": "https://your-mcp-server.azurewebsites.net",
        "headers": {
          "Ocp-Apim-Subscription-Key": "${APIM_KEY}"
        }
      }
    }
  }
}
```

2. Add API key to environment:
```bash
# Windows (PowerShell)
$env:APIM_KEY = "your-subscription-key"

# macOS/Linux
export APIM_KEY="your-subscription-key"
```

**Method 2: User Settings (Global)**

1. Open VS Code Settings (Ctrl+,)
2. Search for "github.copilot.advanced"
3. Edit `settings.json`:

```json
{
  "github.copilot.advanced": {
    "mcpServers": {
      "earth-copilot": {
        "command": "python",
        "args": ["C:\\path\\to\\earth-copilot\\mcp-server\\server.py"],
        "env": {
          "EARTH_COPILOT_BASE_URL": "https://your-backend.azurewebsites.net"
        }
      }
    }
  }
}
```

### Example Usage

**In Python file:**
```python
# Get Sentinel-2 imagery of Seattle with low cloud cover
# Copilot: *Calls Earth Copilot MCP server*

import httpx

async def get_seattle_imagery():
    # Generated code using MCP server context
    response = await client.call_tool(
        "analyze_satellite_imagery",
        {
            "query": "Sentinel-2 imagery of Seattle",
            "location": "Seattle, WA",
            "timeframe": "2024-10-01/2024-10-31",
            "collections": ["sentinel-2"],
            "cloud_cover_max": 10
        }
    )
    return response
```

**In Jupyter Notebook:**
```python
# Get terrain analysis for Mount Rainier
# Copilot: *Generates code using Earth Copilot MCP tools*

from earth_copilot_client import EarthCopilotClient

client = EarthCopilotClient()
terrain = client.analyze_terrain(
    location="Mount Rainier, WA",
    analysis_types=["slope", "aspect", "hillshade"],
    resolution=30
)
```

---

## 3. Custom Python Client

### Installation

```bash
pip install mcp httpx pydantic
```

### Implementation

**Basic Client:**

```python
import asyncio
import httpx
from typing import Dict, Any, List

class EarthCopilotMCPClient:
    def __init__(self, base_url: str, api_key: str = None):
        self.base_url = base_url.rstrip('/')
        self.headers = {
            "Content-Type": "application/json"
        }
        if api_key:
            self.headers["Ocp-Apim-Subscription-Key"] = api_key
    
    async def list_tools(self) -> List[Dict[str, Any]]:
        """List all available tools"""
        async with httpx.AsyncClient() as client:
            response = await client.post(
                f"{self.base_url}/tools/list",
                headers=self.headers
            )
            response.raise_for_status()
            return response.json()["tools"]
    
    async def call_tool(
        self, 
        tool_name: str, 
        arguments: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Execute a tool"""
        async with httpx.AsyncClient(timeout=120.0) as client:
            response = await client.post(
                f"{self.base_url}/tools/call",
                headers=self.headers,
                json={
                    "name": tool_name,
                    "arguments": arguments
                }
            )
            response.raise_for_status()
            return response.json()
    
    async def read_resource(self, uri: str) -> str:
        """Read a resource"""
        async with httpx.AsyncClient() as client:
            response = await client.post(
                f"{self.base_url}/resources/read",
                headers=self.headers,
                json={"uri": uri}
            )
            response.raise_for_status()
            return response.json()["contents"][0]["text"]
    
    async def get_prompt(
        self, 
        prompt_name: str, 
        arguments: Dict[str, Any] = None
    ) -> str:
        """Get a specialized prompt"""
        async with httpx.AsyncClient() as client:
            response = await client.post(
                f"{self.base_url}/prompts/get",
                headers=self.headers,
                json={
                    "name": prompt_name,
                    "arguments": arguments or {}
                }
            )
            response.raise_for_status()
            return response.json()["messages"][0]["content"]["text"]


# Usage Example
async def main():
    # Initialize client
    client = EarthCopilotMCPClient(
        base_url="https://your-mcp-server.azurewebsites.net",
        api_key="your-subscription-key"
    )
    
    # List available tools
    tools = await client.list_tools()
    print(f"Available tools: {[t['name'] for t in tools]}")
    
    # Analyze satellite imagery
    result = await client.call_tool(
        "analyze_satellite_imagery",
        {
            "query": "Show me wildfires in California",
            "location": "California",
            "timeframe": "2024-08-01/2024-08-31",
            "collections": ["modis"]
        }
    )
    print(f"Analysis result: {result}")
    
    # Read STAC resource
    sentinel_info = await client.read_resource("earth://stac/sentinel-2")
    print(f"Sentinel-2 info: {sentinel_info}")
    
    # Get expert prompt
    expert_context = await client.get_prompt(
        "geospatial_expert",
        {"specialization": "environmental"}
    )
    print(f"Expert context: {expert_context}")

if __name__ == "__main__":
    asyncio.run(main())
```

**Advanced Client with Error Handling:**

```python
import asyncio
import httpx
from typing import Dict, Any, Optional
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class EarthCopilotMCPClientAdvanced:
    def __init__(
        self, 
        base_url: str, 
        api_key: Optional[str] = None,
        timeout: int = 120,
        max_retries: int = 3
    ):
        self.base_url = base_url.rstrip('/')
        self.timeout = timeout
        self.max_retries = max_retries
        self.headers = {"Content-Type": "application/json"}
        if api_key:
            self.headers["Ocp-Apim-Subscription-Key"] = api_key
    
    async def _make_request(
        self, 
        endpoint: str, 
        data: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Make HTTP request with retry logic"""
        url = f"{self.base_url}{endpoint}"
        
        for attempt in range(self.max_retries):
            try:
                async with httpx.AsyncClient(timeout=self.timeout) as client:
                    logger.info(f"Request to {endpoint} (attempt {attempt + 1})")
                    response = await client.post(
                        url,
                        headers=self.headers,
                        json=data
                    )
                    response.raise_for_status()
                    return response.json()
            
            except httpx.HTTPStatusError as e:
                logger.error(f"HTTP error {e.response.status_code}: {e.response.text}")
                if attempt == self.max_retries - 1:
                    raise
                await asyncio.sleep(2 ** attempt)  # Exponential backoff
            
            except httpx.RequestError as e:
                logger.error(f"Request error: {str(e)}")
                if attempt == self.max_retries - 1:
                    raise
                await asyncio.sleep(2 ** attempt)
    
    async def analyze_satellite_imagery(
        self,
        query: str,
        location: str,
        timeframe: str,
        collections: List[str] = None,
        cloud_cover_max: int = 30
    ) -> Dict[str, Any]:
        """High-level satellite imagery analysis"""
        return await self._make_request(
            "/tools/call",
            {
                "name": "analyze_satellite_imagery",
                "arguments": {
                    "query": query,
                    "location": location,
                    "timeframe": timeframe,
                    "collections": collections or ["sentinel-2", "landsat"],
                    "cloud_cover_max": cloud_cover_max
                }
            }
        )
    
    async def analyze_terrain(
        self,
        location: str,
        analysis_types: List[str] = None,
        resolution: int = 30
    ) -> Dict[str, Any]:
        """Terrain analysis"""
        return await self._make_request(
            "/tools/call",
            {
                "name": "terrain_analysis",
                "arguments": {
                    "location": location,
                    "analysis_types": analysis_types or ["slope", "aspect"],
                    "resolution": resolution
                }
            }
        )

# Usage
async def demo():
    client = EarthCopilotMCPClientAdvanced(
        base_url="https://your-mcp-server.azurewebsites.net",
        api_key="your-key"
    )
    
    # Analyze wildfires
    wildfire_result = await client.analyze_satellite_imagery(
        query="Active wildfires",
        location="California",
        timeframe="2024-08-01/2024-08-31",
        collections=["modis"]
    )
    
    # Analyze terrain
    terrain_result = await client.analyze_terrain(
        location="Grand Canyon, Arizona",
        analysis_types=["slope", "hillshade", "aspect"],
        resolution=30
    )
    
    print(f"Wildfire analysis: {wildfire_result}")
    print(f"Terrain analysis: {terrain_result}")

asyncio.run(demo())
```

---

## 4. Custom TypeScript Client

### Installation

```bash
npm install @modelcontextprotocol/sdk axios
```

### Implementation

**Basic Client:**

```typescript
import axios, { AxiosInstance } from 'axios';

interface Tool {
  name: string;
  description: string;
  inputSchema: object;
}

interface ToolCallRequest {
  name: string;
  arguments: Record<string, any>;
}

interface ResourceRequest {
  uri: string;
}

class EarthCopilotMCPClient {
  private client: AxiosInstance;

  constructor(baseUrl: string, apiKey?: string) {
    this.client = axios.create({
      baseURL: baseUrl,
      timeout: 120000,
      headers: {
        'Content-Type': 'application/json',
        ...(apiKey && { 'Ocp-Apim-Subscription-Key': apiKey }),
      },
    });
  }

  async listTools(): Promise<Tool[]> {
    const response = await this.client.post('/tools/list');
    return response.data.tools;
  }

  async callTool(name: string, args: Record<string, any>): Promise<any> {
    const response = await this.client.post('/tools/call', {
      name,
      arguments: args,
    });
    return response.data;
  }

  async readResource(uri: string): Promise<string> {
    const response = await this.client.post('/resources/read', { uri });
    return response.data.contents[0].text;
  }

  async getPrompt(name: string, args: Record<string, any> = {}): Promise<string> {
    const response = await this.client.post('/prompts/get', {
      name,
      arguments: args,
    });
    return response.data.messages[0].content.text;
  }
}

// Usage Example
async function main() {
  const client = new EarthCopilotMCPClient(
    'https://your-mcp-server.azurewebsites.net',
    'your-subscription-key'
  );

  // List tools
  const tools = await client.listTools();
  console.log('Available tools:', tools.map(t => t.name));

  // Analyze satellite imagery
  const result = await client.callTool('analyze_satellite_imagery', {
    query: 'Show me wildfires in California',
    location: 'California',
    timeframe: '2024-08-01/2024-08-31',
    collections: ['modis'],
  });
  console.log('Analysis result:', result);

  // Read STAC resource
  const sentinelInfo = await client.readResource('earth://stac/sentinel-2');
  console.log('Sentinel-2 info:', sentinelInfo);
}

main();
```

**React Integration:**

```typescript
import React, { useState, useEffect } from 'react';
import { EarthCopilotMCPClient } from './earthCopilotClient';

const SatelliteAnalysis: React.FC = () => {
  const [client] = useState(
    () => new EarthCopilotMCPClient(
      process.env.REACT_APP_MCP_SERVER_URL!,
      process.env.REACT_APP_APIM_KEY
    )
  );
  const [result, setResult] = useState<any>(null);
  const [loading, setLoading] = useState(false);

  const analyzeWildfires = async () => {
    setLoading(true);
    try {
      const data = await client.callTool('analyze_satellite_imagery', {
        query: 'Active wildfires',
        location: 'California',
        timeframe: '2024-08-01/2024-08-31',
        collections: ['modis'],
      });
      setResult(data);
    } catch (error) {
      console.error('Analysis failed:', error);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div>
      <button onClick={analyzeWildfires} disabled={loading}>
        {loading ? 'Analyzing...' : 'Analyze Wildfires'}
      </button>
      
      {result && (
        <div>
          <h3>Analysis Result</h3>
          <pre>{JSON.stringify(result, null, 2)}</pre>
        </div>
      )}
    </div>
  );
};

export default SatelliteAnalysis;
```

---

## 5. REST API Integration

### Direct HTTP Calls

**Using curl:**

```bash
# List tools
curl -X POST https://your-mcp-server.azurewebsites.net/tools/list \
  -H "Content-Type: application/json" \
  -H "Ocp-Apim-Subscription-Key: your-key"

# Call tool
curl -X POST https://your-mcp-server.azurewebsites.net/tools/call \
  -H "Content-Type: application/json" \
  -H "Ocp-Apim-Subscription-Key: your-key" \
  -d '{
    "name": "analyze_satellite_imagery",
    "arguments": {
      "query": "Wildfires in California",
      "location": "California",
      "timeframe": "2024-08-01/2024-08-31"
    }
  }'

# Read resource
curl -X POST https://your-mcp-server.azurewebsites.net/resources/read \
  -H "Content-Type: application/json" \
  -H "Ocp-Apim-Subscription-Key: your-key" \
  -d '{"uri": "earth://stac/sentinel-2"}'
```

**Using PowerShell:**

```powershell
# Set variables
$baseUrl = "https://your-mcp-server.azurewebsites.net"
$apiKey = "your-subscription-key"
$headers = @{
    "Content-Type" = "application/json"
    "Ocp-Apim-Subscription-Key" = $apiKey
}

# List tools
$toolsResponse = Invoke-RestMethod `
    -Uri "$baseUrl/tools/list" `
    -Method Post `
    -Headers $headers

Write-Host "Available tools: $($toolsResponse.tools | ForEach-Object { $_.name })"

# Call tool
$analysisBody = @{
    name = "analyze_satellite_imagery"
    arguments = @{
        query = "Wildfires in California"
        location = "California"
        timeframe = "2024-08-01/2024-08-31"
        collections = @("modis")
    }
} | ConvertTo-Json -Depth 10

$analysisResponse = Invoke-RestMethod `
    -Uri "$baseUrl/tools/call" `
    -Method Post `
    -Headers $headers `
    -Body $analysisBody

Write-Host "Analysis result: $($analysisResponse | ConvertTo-Json -Depth 10)"
```

---

## 6. Testing Your Connection

### Health Check

```bash
# Test if server is running
curl https://your-mcp-server.azurewebsites.net/health

# Expected response:
# {"status": "healthy", "version": "1.0.0"}
```

### Test Tool Discovery

```python
import asyncio
from earth_copilot_client import EarthCopilotMCPClient

async def test_connection():
    client = EarthCopilotMCPClient(
        base_url="https://your-mcp-server.azurewebsites.net",
        api_key="your-key"
    )
    
    # Test 1: List tools
    print("Test 1: Listing tools...")
    tools = await client.list_tools()
    assert len(tools) == 5, f"Expected 5 tools, got {len(tools)}"
    print(" Tool discovery successful")
    
    # Test 2: Read resource
    print("\nTest 2: Reading STAC resource...")
    info = await client.read_resource("earth://stac/sentinel-2")
    assert "Sentinel-2" in info, "Resource content invalid"
    print(" Resource access successful")
    
    # Test 3: Call tool
    print("\nTest 3: Calling analyze_satellite_imagery...")
    result = await client.call_tool(
        "analyze_satellite_imagery",
        {
            "query": "Test query",
            "location": "San Francisco, CA",
            "timeframe": "2024-01-01/2024-01-31"
        }
    )
    assert result is not None, "Tool execution failed"
    print(" Tool execution successful")
    
    print("\n All tests passed!")

asyncio.run(test_connection())
```

### Troubleshooting Connection Issues

**Issue: Connection refused**
```bash
# Check if server is running
netstat -an | grep 8080  # Linux/Mac
netstat -an | findstr 8080  # Windows

# Check server logs
tail -f logs/mcp-server.log
```

**Issue: Authentication failed**
```bash
# Verify API key
curl -X POST https://your-mcp-server.azurewebsites.net/tools/list \
  -H "Ocp-Apim-Subscription-Key: your-key" \
  -v  # Verbose output shows HTTP status

# Check APIM subscription
az apim subscription show \
  --resource-group your-rg \
  --service-name your-apim \
  --subscription-id your-sub-id
```

**Issue: Timeout**
```python
# Increase timeout
client = EarthCopilotMCPClient(
    base_url="https://your-mcp-server.azurewebsites.net",
    timeout=300  # 5 minutes
)
```

---

## 🆘 Support

If you encounter issues:
1. Check server logs: `tail -f logs/mcp-server.log`
2. Verify environment variables in `.env`
3. Test with `curl` to isolate client issues
4. Review [MCP Implementation Guide](MCP_IMPLEMENTATION_GUIDE.md)
5. Open issue on GitHub

---

**Next Steps:**
- Test your client connection
- Build your first geospatial AI application
- Share your integration examples with the community!
