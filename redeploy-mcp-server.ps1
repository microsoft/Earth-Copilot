# Redeploy MCP Server to Azure Container Apps
# This script rebuilds and redeploys the MCP server with updated configuration

param(
    [Parameter(Mandatory=$false)]
    [string]$ResourceGroup = "earthcopilot-rg",
    
    [Parameter(Mandatory=$false)]
    [string]$ContainerAppName = "earth-copilot-mcp",
    
    [Parameter(Mandatory=$false)]
    [string]$AcrName = "earthcopilotregistry",
    
    [Parameter(Mandatory=$false)]
    [string]$ImageName = "earth-copilot-mcp",
    
    [Parameter(Mandatory=$false)]
    [string]$ImageTag = "latest"
)

Write-Host "🚀 Redeploying Earth Copilot MCP Server..." -ForegroundColor Cyan

# Configuration
$RESOURCE_GROUP = $ResourceGroup
$CONTAINER_APP_NAME = $ContainerAppName
$ACR_NAME = $AcrName
$IMAGE_NAME = $ImageName
$IMAGE_TAG = $ImageTag

# Navigate to MCP server directory
Set-Location -Path "$PSScriptRoot\earth-copilot\mcp-server"

Write-Host "📦 Step 1: Building Docker image..." -ForegroundColor Yellow

# Build the Docker image
az acr build --registry $ACR_NAME `
    --image "${IMAGE_NAME}:${IMAGE_TAG}" `
    --file Dockerfile `
    .

if ($LASTEXITCODE -ne 0) {
    Write-Host "❌ Docker build failed!" -ForegroundColor Red
    exit 1
}

Write-Host "✅ Docker image built successfully" -ForegroundColor Green

Write-Host "🔄 Step 2: Updating Container App..." -ForegroundColor Yellow

# Update the container app to use the new image
az containerapp update `
    --name $CONTAINER_APP_NAME `
    --resource-group $RESOURCE_GROUP `
    --set-env-vars "EARTH_COPILOT_BASE_URL=https://earthcopilot-web-ui.azurewebsites.net"

if ($LASTEXITCODE -ne 0) {
    Write-Host "❌ Container app update failed!" -ForegroundColor Red
    exit 1
}

Write-Host "✅ Container app updated successfully" -ForegroundColor Green

Write-Host "⏳ Step 3: Waiting for deployment..." -ForegroundColor Yellow
Start-Sleep -Seconds 15

Write-Host "🧪 Step 4: Testing MCP server..." -ForegroundColor Yellow

# Test the health endpoint
$MCP_URL = "https://earth-copilot-mcp.politecoast-31b85ce5.canadacentral.azurecontainerapps.io"
try {
    $response = Invoke-WebRequest -Uri "$MCP_URL/health" -Method Get -ErrorAction Stop
    Write-Host "✅ MCP Server is healthy!" -ForegroundColor Green
} catch {
    Write-Host "⚠️  Health check failed, but deployment may still be in progress" -ForegroundColor Yellow
}

Write-Host ""
Write-Host "🎉 Deployment complete!" -ForegroundColor Green
Write-Host "MCP Server URL: $MCP_URL" -ForegroundColor Cyan
Write-Host "Frontend URL: https://earthcopilot-web-ui.azurewebsites.net" -ForegroundColor Cyan
Write-Host ""
Write-Host "Test with:" -ForegroundColor Yellow
Write-Host 'python query_earth_copilot.py "Show me HLS images of Seattle"' -ForegroundColor White

# Return to original directory
Set-Location -Path $PSScriptRoot
