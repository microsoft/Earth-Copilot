#  Testing Deployed MCP Server

This guide shows you how to test your Earth Copilot MCP Server once it's deployed to Azure Container Apps.

##  Prerequisites

- Deployed MCP Server URL (e.g., `https://earth-copilot-mcp.azurecontainerapps.io`)
- Python 3.8+ installed locally
- `requests` library (`pip install requests`)

---

##  Quick Deployment to Azure Container Apps

### Step 1: Build and Push Docker Image

```powershell
# Navigate to MCP server directory
cd earth-copilot/mcp-server

# Set variables
$RESOURCE_GROUP = "earth-copilot-rg"
$ACR_NAME = "earthcopilotacr"
$IMAGE_NAME = "earth-copilot-mcp"
$IMAGE_TAG = "latest"

# Login to Azure
az login

# Create Azure Container Registry (if not exists)
az acr create `
  --resource-group $RESOURCE_GROUP `
  --name $ACR_NAME `
  --sku Basic `
  --location "East US"

# Build and push image
az acr build `
  --registry $ACR_NAME `
  --image "${IMAGE_NAME}:${IMAGE_TAG}" `
  --file Dockerfile `
  .
```

### Step 2: Deploy to Container Apps

```powershell
# Create Container Apps environment (if not exists)
az containerapp env create `
  --name earth-copilot-env `
  --resource-group $RESOURCE_GROUP `
  --location "East US"

# Enable admin credentials for ACR
az acr update --name $ACR_NAME --admin-enabled true

# Get ACR credentials
$ACR_SERVER = az acr show --name $ACR_NAME --query loginServer -o tsv
$ACR_USERNAME = az acr credential show --name $ACR_NAME --query username -o tsv
$ACR_PASSWORD = az acr credential show --name $ACR_NAME --query "passwords[0].value" -o tsv

# Deploy Container App
az containerapp create `
  --name earth-copilot-mcp `
  --resource-group $RESOURCE_GROUP `
  --environment earth-copilot-env `
  --image "${ACR_SERVER}/${IMAGE_NAME}:${IMAGE_TAG}" `
  --target-port 8080 `
  --ingress external `
  --registry-server $ACR_SERVER `
  --registry-username $ACR_USERNAME `
  --registry-password $ACR_PASSWORD `
  --env-vars `
    "EARTH_COPILOT_BASE_URL=https://your-backend.azurecontainerapps.io" `
    "GEOINT_SERVICE_URL=https://your-geoint.azurecontainerapps.io" `
    "MCP_SERVER_MODE=production" `
  --cpu 0.5 `
  --memory 1.0Gi `
  --min-replicas 1 `
  --max-replicas 3

# Get the deployed URL
$MCP_URL = az containerapp show `
  --name earth-copilot-mcp `
  --resource-group $RESOURCE_GROUP `
  --query properties.configuration.ingress.fqdn `
  -o tsv

Write-Host " MCP Server deployed at: https://$MCP_URL" -ForegroundColor Green
```

---

##  Testing Your Deployed MCP Server

### Test 1: Health Check

```powershell
# PowerShell
$MCP_URL = "https://earth-copilot-mcp.azurecontainerapps.io"
Invoke-WebRequest -Uri "$MCP_URL/" -Method GET | Select-Object -ExpandProperty Content
```

```bash
# Bash/Linux
curl https://earth-copilot-mcp.azurecontainerapps.io/
```

**Expected Output:**
```json
{
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
```

### Test 2: List Available Tools

```powershell
# PowerShell
Invoke-WebRequest -Uri "$MCP_URL/tools/list" -Method POST | ConvertFrom-Json | ConvertTo-Json -Depth 10
```

```bash
# Bash/Linux
curl -X POST https://earth-copilot-mcp.azurecontainerapps.io/tools/list
```

**Expected Output:**
```json
{
  "tools": [
    {
      "name": "analyze_satellite_imagery",
      "description": "Analyze satellite imagery for specific locations and timeframes"
    },
    {
      "name": "terrain_analysis",
      "description": "Perform geospatial terrain analysis"
    },
    {
      "name": "comparison_analysis",
      "description": "Compare satellite imagery across time periods"
    }
  ]
}
```

### Test 3: List Available Resources

```powershell
# PowerShell
Invoke-WebRequest -Uri "$MCP_URL/resources/list" -Method POST | ConvertFrom-Json | ConvertTo-Json -Depth 10
```

**Expected Output:**
```json
{
  "resources": [
    {
      "uri": "earth://stac/landsat-8",
      "name": "Landsat-8 Collection",
      "description": "NASA/USGS Landsat-8 satellite imagery"
    },
    {
      "uri": "earth://stac/sentinel-2",
      "name": "Sentinel-2 Collection",
      "description": "ESA Sentinel-2 multi-spectral satellite imagery"
    }
  ]
}
```

### Test 4: Read a Resource

```powershell
# PowerShell
$body = @{
    uri = "earth://stac/sentinel-2"
} | ConvertTo-Json

Invoke-WebRequest -Uri "$MCP_URL/resources/read" -Method POST -Body $body -ContentType "application/json" | ConvertFrom-Json
```

```bash
# Bash/Linux
curl -X POST https://earth-copilot-mcp.azurecontainerapps.io/resources/read \
  -H "Content-Type: application/json" \
  -d '{"uri": "earth://stac/sentinel-2"}'
```

### Test 5: Execute Terrain Analysis Tool

```powershell
# PowerShell
$body = @{
    name = "terrain_analysis"
    arguments = @{
        location = "Mount Rainier, Washington"
        analysis_types = @("elevation", "slope", "aspect")
        resolution = 30
    }
} | ConvertTo-Json

Invoke-WebRequest -Uri "$MCP_URL/tools/call" -Method POST -Body $body -ContentType "application/json" | ConvertFrom-Json
```

```bash
# Bash/Linux
curl -X POST https://earth-copilot-mcp.azurecontainerapps.io/tools/call \
  -H "Content-Type: application/json" \
  -d '{
    "name": "terrain_analysis",
    "arguments": {
      "location": "Mount Rainier, Washington",
      "analysis_types": ["elevation", "slope", "aspect"],
      "resolution": 30
    }
  }'
```

### Test 6: Satellite Imagery Analysis

```powershell
# PowerShell
$body = @{
    name = "analyze_satellite_imagery"
    arguments = @{
        query = "Show me recent wildfire activity"
        location = "California"
        timeframe = "2024-10-01/2024-10-31"
        collections = @("sentinel-2", "landsat-8")
        cloud_cover_max = 20
    }
} | ConvertTo-Json

Invoke-WebRequest -Uri "$MCP_URL/tools/call" -Method POST -Body $body -ContentType "application/json" | ConvertFrom-Json
```

---

##  Python Test Script for Deployed Server

Save this as `test_deployed_mcp.py`:

```python
"""
Test script for deployed Earth Copilot MCP Server
Run: python test_deployed_mcp.py <YOUR_MCP_URL>
Example: python test_deployed_mcp.py https://earth-copilot-mcp.azurecontainerapps.io
"""

import requests
import json
import sys
from datetime import datetime

class DeployedMCPTester:
    def __init__(self, base_url):
        self.base_url = base_url.rstrip('/')
        self.session = requests.Session()
        self.test_results = []
    
    def test_health(self):
        """Test 1: Health check"""
        print("\n" + "="*70)
        print("TEST 1: Health Check")
        print("="*70)
        
        try:
            response = self.session.get(f"{self.base_url}/")
            response.raise_for_status()
            
            data = response.json()
            print(" PASSED - Server is healthy")
            print(f"   Service: {data.get('service')}")
            print(f"   Version: {data.get('version')}")
            
            self.test_results.append(("Health Check", True, None))
            return True
        except Exception as e:
            print(f" FAILED - {str(e)}")
            self.test_results.append(("Health Check", False, str(e)))
            return False
    
    def test_tools_list(self):
        """Test 2: List available tools"""
        print("\n" + "="*70)
        print("TEST 2: List Available Tools")
        print("="*70)
        
        try:
            response = self.session.post(f"{self.base_url}/tools/list")
            response.raise_for_status()
            
            data = response.json()
            tools = data.get('tools', [])
            
            print(f" PASSED - Found {len(tools)} tools:")
            for tool in tools:
                print(f"    {tool['name']}")
                print(f"      {tool['description'][:80]}...")
            
            self.test_results.append(("List Tools", True, None))
            return tools
        except Exception as e:
            print(f" FAILED - {str(e)}")
            self.test_results.append(("List Tools", False, str(e)))
            return []
    
    def test_resources_list(self):
        """Test 3: List available resources"""
        print("\n" + "="*70)
        print("TEST 3: List Available Resources")
        print("="*70)
        
        try:
            response = self.session.post(f"{self.base_url}/resources/list")
            response.raise_for_status()
            
            data = response.json()
            resources = data.get('resources', [])
            
            print(f" PASSED - Found {len(resources)} resources:")
            for resource in resources:
                print(f"    {resource['name']}")
                print(f"      URI: {resource['uri']}")
            
            self.test_results.append(("List Resources", True, None))
            return resources
        except Exception as e:
            print(f" FAILED - {str(e)}")
            self.test_results.append(("List Resources", False, str(e)))
            return []
    
    def test_read_resource(self, uri="earth://stac/sentinel-2"):
        """Test 4: Read a specific resource"""
        print("\n" + "="*70)
        print(f"TEST 4: Read Resource - {uri}")
        print("="*70)
        
        try:
            response = self.session.post(
                f"{self.base_url}/resources/read",
                json={"uri": uri}
            )
            response.raise_for_status()
            
            data = response.json()
            print(" PASSED - Resource data retrieved")
            print(f"   Data preview: {str(data)[:200]}...")
            
            self.test_results.append(("Read Resource", True, None))
            return data
        except Exception as e:
            print(f" FAILED - {str(e)}")
            self.test_results.append(("Read Resource", False, str(e)))
            return None
    
    def test_terrain_analysis(self):
        """Test 5: Execute terrain analysis tool"""
        print("\n" + "="*70)
        print("TEST 5: Terrain Analysis Tool")
        print("="*70)
        
        try:
            response = self.session.post(
                f"{self.base_url}/tools/call",
                json={
                    "name": "terrain_analysis",
                    "arguments": {
                        "location": "Grand Canyon, Arizona",
                        "analysis_types": ["elevation", "slope"],
                        "resolution": 30
                    }
                }
            )
            response.raise_for_status()
            
            data = response.json()
            print(" PASSED - Terrain analysis executed")
            print(f"   Result preview: {str(data)[:300]}...")
            
            self.test_results.append(("Terrain Analysis", True, None))
            return data
        except Exception as e:
            print(f" FAILED - {str(e)}")
            self.test_results.append(("Terrain Analysis", False, str(e)))
            return None
    
    def test_satellite_analysis(self):
        """Test 6: Execute satellite imagery analysis"""
        print("\n" + "="*70)
        print("TEST 6: Satellite Imagery Analysis")
        print("="*70)
        
        try:
            response = self.session.post(
                f"{self.base_url}/tools/call",
                json={
                    "name": "analyze_satellite_imagery",
                    "arguments": {
                        "query": "Recent satellite data",
                        "location": "Seattle, Washington",
                        "timeframe": "2024-10-01/2024-10-31",
                        "collections": ["sentinel-2"]
                    }
                }
            )
            response.raise_for_status()
            
            data = response.json()
            print(" PASSED - Satellite analysis executed")
            print(f"   Result preview: {str(data)[:300]}...")
            
            self.test_results.append(("Satellite Analysis", True, None))
            return data
        except Exception as e:
            print(f" FAILED - {str(e)}")
            self.test_results.append(("Satellite Analysis", False, str(e)))
            return None
    
    def test_api_documentation(self):
        """Test 7: Check API documentation endpoint"""
        print("\n" + "="*70)
        print("TEST 7: API Documentation")
        print("="*70)
        
        try:
            response = self.session.get(f"{self.base_url}/docs")
            response.raise_for_status()
            
            print(" PASSED - API documentation accessible")
            print(f"   URL: {self.base_url}/docs")
            
            self.test_results.append(("API Documentation", True, None))
            return True
        except Exception as e:
            print(f" FAILED - {str(e)}")
            self.test_results.append(("API Documentation", False, str(e)))
            return False
    
    def print_summary(self):
        """Print test summary"""
        print("\n" + "="*70)
        print(" TEST SUMMARY")
        print("="*70)
        
        passed = sum(1 for _, success, _ in self.test_results if success)
        failed = len(self.test_results) - passed
        
        print(f"\n Passed: {passed}")
        print(f" Failed: {failed}")
        print(f" Success Rate: {(passed/len(self.test_results)*100):.1f}%")
        
        if failed > 0:
            print("\n Failed Tests:")
            for name, success, error in self.test_results:
                if not success:
                    print(f"   - {name}: {error}")
        
        print("\n" + "="*70)
        return passed == len(self.test_results)

def main():
    if len(sys.argv) < 2:
        print("Usage: python test_deployed_mcp.py <MCP_SERVER_URL>")
        print("Example: python test_deployed_mcp.py https://earth-copilot-mcp.azurecontainerapps.io")
        sys.exit(1)
    
    mcp_url = sys.argv[1]
    
    print("\n" + "="*70)
    print(" Earth Copilot MCP Server - Deployment Tests")
    print("="*70)
    print(f" Testing: {mcp_url}")
    print(f" Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    
    tester = DeployedMCPTester(mcp_url)
    
    # Run all tests
    if not tester.test_health():
        print("\n Server health check failed. Exiting.")
        sys.exit(1)
    
    tester.test_tools_list()
    tester.test_resources_list()
    tester.test_read_resource()
    tester.test_terrain_analysis()
    tester.test_satellite_analysis()
    tester.test_api_documentation()
    
    # Print summary
    all_passed = tester.print_summary()
    
    print("\n Next Steps:")
    print("   1. Open API docs: " + mcp_url + "/docs")
    print("   2. Test interactive UI in browser")
    print("   3. Integrate with GitHub Copilot or Claude Desktop")
    print("   4. Monitor logs in Azure Portal")
    
    sys.exit(0 if all_passed else 1)

if __name__ == "__main__":
    main()
```

---

##  Monitoring Your Deployed Server

### View Logs in Azure

```powershell
# Stream logs
az containerapp logs show `
  --name earth-copilot-mcp `
  --resource-group $RESOURCE_GROUP `
  --follow

# View recent logs
az containerapp logs show `
  --name earth-copilot-mcp `
  --resource-group $RESOURCE_GROUP `
  --tail 100
```

### Check Container App Status

```powershell
# Get container app details
az containerapp show `
  --name earth-copilot-mcp `
  --resource-group $RESOURCE_GROUP `
  --output table

# Check replicas
az containerapp revision list `
  --name earth-copilot-mcp `
  --resource-group $RESOURCE_GROUP `
  --output table
```

### Monitor Metrics

```powershell
# View metrics in Azure Portal
$MCP_RESOURCE_ID = az containerapp show `
  --name earth-copilot-mcp `
  --resource-group $RESOURCE_GROUP `
  --query id `
  -o tsv

# Open in portal
az monitor metrics list `
  --resource $MCP_RESOURCE_ID `
  --metric "Requests" `
  --output table
```

---

##  Troubleshooting

### Issue: Server returns 404

**Solution:** Check that ingress is configured correctly
```powershell
az containerapp ingress show `
  --name earth-copilot-mcp `
  --resource-group $RESOURCE_GROUP
```

### Issue: Tools fail to execute

**Solution:** Verify environment variables are set
```powershell
az containerapp show `
  --name earth-copilot-mcp `
  --resource-group $RESOURCE_GROUP `
  --query "properties.template.containers[0].env"
```

### Issue: Container app won't start

**Solution:** Check container logs for errors
```powershell
az containerapp logs show `
  --name earth-copilot-mcp `
  --resource-group $RESOURCE_GROUP `
  --tail 50
```

### Issue: High response times

**Solution:** Scale up resources
```powershell
az containerapp update `
  --name earth-copilot-mcp `
  --resource-group $RESOURCE_GROUP `
  --cpu 1.0 `
  --memory 2.0Gi
```

---

##  Additional Resources

- **Azure Container Apps Docs**: https://learn.microsoft.com/azure/container-apps/
- **MCP Specification**: https://modelcontextprotocol.io/
- **Earth Copilot Docs**: `../../documentation/`
- **FastAPI Docs**: https://fastapi.tiangolo.com/

---

##  Deployment Checklist

- [ ] Docker image built and pushed to ACR
- [ ] Container App deployed successfully
- [ ] Environment variables configured (backend URLs)
- [ ] Health check passes
- [ ] Tools list endpoint returns data
- [ ] At least one tool executes successfully
- [ ] Resources can be read
- [ ] API documentation accessible at `/docs`
- [ ] Logs show no errors
- [ ] Monitoring configured in Azure Portal

**Once all tests pass, your MCP server is ready for production use!** 
