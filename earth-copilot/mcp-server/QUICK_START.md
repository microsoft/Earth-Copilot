# 🚀 Quick Start Guide - Earth Copilot MCP Server

Get your Earth Copilot MCP server running in 5 minutes!

---

## ⚡ 5-Minute Setup

### Step 1: Prerequisites ✅

**Required:**
- Python 3.8+ installed
- Git installed
- Earth Copilot backend deployed (or running locally)

**Optional (for production):**
- Azure account
- Azure CLI installed

**Check your setup:**
```bash
python --version    # Should be 3.8+
git --version       # Any recent version
```

---

### Step 2: Clone & Install 📦

```bash
# Clone the repository
git clone https://github.com/microsoft/Earth-Copilot
cd Earth-Copilot/earth-copilot/mcp-server

# Install dependencies
pip install -r requirements.txt

# Note: If MCP SDK installation fails, try:
# pip install git+https://github.com/anthropics/model-context-protocol-sdk-python.git
```

---

### Step 3: Configure 🔧

```bash
# Copy example config
cp .env.example .env

# Edit .env with your values
# Windows:
notepad .env
# Mac/Linux:
nano .env
```

**Minimal configuration:**
```bash
# .env
EARTH_COPILOT_BASE_URL=https://your-earth-copilot-backend.azurewebsites.net
MCP_SERVER_MODE=development
HOST=127.0.0.1
PORT=8080
```

---

### Step 4: Run 🏃

**Option A: Local Development (stdio transport)**
```bash
python server.py
```

**Option B: HTTP Server (for web apps)**
```bash
# Start FastAPI bridge
uvicorn mcp_bridge:app --reload --host 127.0.0.1 --port 8080

# Server will be at: http://localhost:8080
# API docs at: http://localhost:8080/docs
```

**Option C: Background Service**
```bash
# Windows (PowerShell)
Start-Process python -ArgumentList "server.py" -WindowStyle Hidden

# Mac/Linux
nohup python server.py > logs/mcp-server.log 2>&1 &
```

---

### Step 5: Test 🧪

```bash
# Test tool discovery
curl -X POST http://localhost:8080/tools/list

# Expected output:
# {
#   "tools": [
#     {"name": "analyze_satellite_imagery", ...},
#     {"name": "terrain_analysis", ...},
#     ...
#   ]
# }

# Test tool execution
curl -X POST http://localhost:8080/tools/call \
  -H "Content-Type: application/json" \
  -d '{
    "name": "data_discovery",
    "arguments": {
      "location": "San Francisco, CA",
      "timeframe": "2024-01-01/2024-01-31"
    }
  }'
```

**Success!** 🎉 Your MCP server is running!

---

## 🔌 Connect Your AI Assistant

### Claude Desktop

1. Open Claude Desktop config:
   - **Windows**: `%APPDATA%\Claude\claude_desktop_config.json`
   - **Mac**: `~/Library/Application Support/Claude/claude_desktop_config.json`

2. Add configuration:
```json
{
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
```

3. Restart Claude Desktop

4. Test:
```
You: Can you see the earth-copilot MCP server?
Claude: Yes! I can see 5 tools, 6 resources, and 4 prompts...
```

### VS Code / GitHub Copilot

1. Create `.vscode/settings.json` in your project:
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

2. Reload VS Code window

---

## 📝 Example Queries

Once connected, try these queries:

### 1. Wildfire Detection
```
Show me active wildfires in California from the past week
```

### 2. Terrain Analysis
```
Analyze the terrain slope and aspect of Mount Rainier
```

### 3. Change Detection
```
Show me deforestation in the Amazon rainforest from 2020 to 2024
```

### 4. Data Discovery
```
What Sentinel-2 data is available for Seattle with low cloud cover?
```

### 5. Environmental Monitoring
```
Monitor water quality changes in the Great Lakes over the past year
```

---

## 🌐 Deploy to Production (Azure)

### Option 1: Azure Container Apps (Recommended)

```powershell
# 1. Login to Azure
az login

# 2. Create Container Apps environment (if not exists)
az containerapp env create `
  --name earth-copilot-env `
  --resource-group earth-copilot-rg `
  --location "East US"

# 3. Deploy MCP server
az containerapp create `
  --name earth-copilot-mcp `
  --resource-group earth-copilot-rg `
  --environment earth-copilot-env `
  --image mcr.microsoft.com/azuredocs/containerapps-helloworld:latest `
  --target-port 8080 `
  --ingress external `
  --min-replicas 1 `
  --max-replicas 10

# 4. Configure backend URLs
az containerapp update `
  --name earth-copilot-mcp `
  --resource-group earth-copilot-rg `
  --set-env-vars `
    EARTH_COPILOT_BASE_URL=https://your-backend-container.azurecontainerapps.io `
    GEOINT_SERVICE_URL=https://your-geoint-container.azurecontainerapps.io

# 5. Get your endpoint
# Output: https://earth-copilot-mcp.azurecontainerapps.io
```

### Option 2: Azure Container Instance

```bash
# 1. Build Docker image
docker build -t earth-copilot-mcp .

# 2. Push to Azure Container Registry
az acr login --name yourregistry
docker tag earth-copilot-mcp yourregistry.azurecr.io/earth-copilot-mcp
docker push yourregistry.azurecr.io/earth-copilot-mcp

# 3. Deploy to Container Instance
az container create \
  --resource-group earth-copilot-rg \
  --name earth-copilot-mcp \
  --image yourregistry.azurecr.io/earth-copilot-mcp \
  --dns-name-label earth-copilot-mcp \
  --ports 80 \
  --environment-variables \
    EARTH_COPILOT_BASE_URL=https://your-backend.azurewebsites.net \
    PORT=80
```

### Option 3: Azure Web App

```bash
# 1. Create App Service plan
az appservice plan create \
  --name earth-copilot-plan \
  --resource-group earth-copilot-rg \
  --sku B1 \
  --is-linux

# 2. Create Web App
az webapp create \
  --resource-group earth-copilot-rg \
  --plan earth-copilot-plan \
  --name earth-copilot-mcp \
  --runtime "PYTHON:3.11"

# 3. Configure environment
az webapp config appsettings set \
  --resource-group earth-copilot-rg \
  --name earth-copilot-mcp \
  --settings \
    EARTH_COPILOT_BASE_URL=https://your-backend.azurewebsites.net

# 4. Deploy code
az webapp up \
  --resource-group earth-copilot-rg \
  --name earth-copilot-mcp
```

---

## 🔐 Add Security (Production)

### API Key Authentication

```python
# In mcp_bridge.py
from fastapi import Header, HTTPException

async def verify_api_key(x_api_key: str = Header()):
    if x_api_key != os.getenv("API_KEY"):
        raise HTTPException(status_code=401, detail="Invalid API key")
    return x_api_key

@app.post("/tools/call", dependencies=[Depends(verify_api_key)])
async def call_tool(request: ToolCallRequest):
    ...
```

### Azure API Management (Enterprise)

```powershell
# Deploy APIM pointing to your Container App
cd apim
.\deploy-apim.ps1 `
  -ResourceGroupName "earth-copilot-rg" `
  -ApimServiceName "earth-copilot-api" `
  -PublisherEmail "admin@yourcompany.com" `
  -PublisherName "Your Company" `
  -McpServerUrl "https://earth-copilot-mcp.azurecontainerapps.io"

# APIM provides:
# - OAuth 2.0 authentication
# - Rate limiting (100 requests/minute per subscriber)
# - Response caching
# - Analytics dashboard
# - Developer portal
```

---

## 🔍 Verify Deployment

```bash
# Test production endpoint
curl -X POST https://earth-copilot-mcp.azurecontainerapps.io/tools/list

# Check health
curl https://earth-copilot-mcp.azurecontainerapps.io/health

# View logs (Azure Container Apps)
az containerapp logs show \
  --name earth-copilot-mcp \
  --resource-group earth-copilot-rg \
  --follow
```

---

## 🐛 Troubleshooting

### Server won't start

```bash
# Check Python version
python --version  # Must be 3.8+

# Check dependencies
pip list | grep -E "mcp|fastapi|httpx"

# Check environment variables
python -c "import os; print(os.getenv('EARTH_COPILOT_BASE_URL'))"

# View detailed errors
python server.py --log-level DEBUG
```

### Connection errors

```bash
# Test backend connectivity
curl https://your-backend-container.azurecontainerapps.io/api/health

# Check firewall rules
# Ensure MCP server can reach backend (no firewall blocking)

# Test local server
curl http://localhost:8080/health
```

### Claude Desktop not connecting

```bash
# Verify config path
# Windows: %APPDATA%\Claude\claude_desktop_config.json
# Mac: ~/Library/Application Support/Claude/claude_desktop_config.json

# Check JSON syntax
python -m json.tool claude_desktop_config.json

# Restart Claude Desktop completely
# Windows: Task Manager > End Task
# Mac: Activity Monitor > Force Quit
```

### Tool execution fails

```bash
# Check backend logs (Container Apps)
az containerapp logs show \
  --name your-backend-container \
  --resource-group your-rg \
  --follow

# Test backend directly
curl -X POST https://your-backend-container.azurecontainerapps.io/api/query \
  -H "Content-Type: application/json" \
  -d '{"query": "test query", "location": "test"}'

# Enable debug logging
# In .env:
LOG_LEVEL=DEBUG
ENABLE_DETAILED_LOGGING=true
```

---

## 📚 Next Steps

### 1. **Customize Tools**
- Edit `server.py` to add your own analysis tools
- See [MCP Implementation Guide](MCP_IMPLEMENTATION_GUIDE.md)

### 2. **Add Resources**
- Expose your own data catalogs
- Connect to custom STAC APIs

### 3. **Integrate with Apps**
- See [Client Connection Guide](CLIENT_CONNECTION_GUIDE.md)
- Build Python/TypeScript/REST clients

### 4. **Monitor & Scale**
- Set up Application Insights
- Configure auto-scaling in Azure
- Add rate limiting and caching

### 5. **Share Your Template**
- Fork the repository
- Customize for your use case
- Share with the community!

---

## 🆘 Get Help

- **Documentation**: [README.md](README.md)
- **Implementation Guide**: [MCP_IMPLEMENTATION_GUIDE.md](MCP_IMPLEMENTATION_GUIDE.md)
- **Client Examples**: [CLIENT_CONNECTION_GUIDE.md](CLIENT_CONNECTION_GUIDE.md)
- **STAC Collections**: [../documentation/data_collections/STAC_COLLECTIONS.md](../documentation/data_collections/STAC_COLLECTIONS.md)
- **GitHub Issues**: https://github.com/microsoft/Earth-Copilot/issues

---

## ✨ You're Ready!

Your Earth Copilot MCP server is now:
- ✅ Running locally or in Azure
- ✅ Connected to your AI assistant
- ✅ Exposing 5 analysis tools
- ✅ Providing access to 6 data resources
- ✅ Offering 4 expert prompts

**Start analyzing satellite imagery with natural language!** 🌍🛰️🤖
