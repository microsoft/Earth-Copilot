# Redeploy MCP Server to Azure Container Apps
# This script rebuilds and redeploys the MCP server with updated configuration
# 
# USAGE: .\redeploy-mcp-server.ps1 -ResourceGroup "rg-earthcopilot"
#
# Prerequisites:
#   - Azure CLI installed and authenticated
#   - Existing deployment via QUICK_DEPLOY.md

param(
    [string]$ResourceGroup = "rg-earthcopilot"
)

Write-Host "🚀 Redeploying Earth Copilot MCP Server..." -ForegroundColor Cyan

# Discover resource names dynamically
Write-Host "🔍 Discovering resources in $ResourceGroup..." -ForegroundColor Yellow

$ACR_NAME = az acr list --resource-group $ResourceGroup --query "[0].name" -o tsv
$CONTAINER_APP_NAME = az containerapp list --resource-group $ResourceGroup --query "[?contains(name, 'mcp')].name | [0]" -o tsv
$BACKEND_URL = az containerapp list --resource-group $ResourceGroup --query "[?contains(name, 'api')].properties.configuration.ingress.fqdn | [0]" -o tsv

if (-not $ACR_NAME) {
    Write-Host "❌ No Container Registry found in $ResourceGroup. Run deployment first." -ForegroundColor Red
    exit 1
}

Write-Host "  ACR: $ACR_NAME" -ForegroundColor Gray
Write-Host "  MCP Container App: $CONTAINER_APP_NAME" -ForegroundColor Gray
Write-Host "  Backend URL: https://$BACKEND_URL" -ForegroundColor Gray

$IMAGE_NAME = "earth-copilot-mcp"
$IMAGE_TAG = "latest"

# Navigate to MCP server directory
Set-Location -Path "$PSScriptRoot\..\earth-copilot\mcp-server"

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
    --resource-group $ResourceGroup `
    --set-env-vars "EARTH_COPILOT_BASE_URL=https://$BACKEND_URL"

if ($LASTEXITCODE -ne 0) {
    Write-Host "❌ Container app update failed!" -ForegroundColor Red
    exit 1
}

Write-Host "✅ Container app updated successfully" -ForegroundColor Green

Write-Host "⏳ Step 3: Waiting for deployment..." -ForegroundColor Yellow
Start-Sleep -Seconds 15

Write-Host "🧪 Step 4: Testing MCP server..." -ForegroundColor Yellow

# Get MCP URL dynamically
$MCP_FQDN = az containerapp show --name $CONTAINER_APP_NAME --resource-group $ResourceGroup --query "properties.configuration.ingress.fqdn" -o tsv
$MCP_URL = "https://$MCP_FQDN"

try {
    $response = Invoke-WebRequest -Uri "$MCP_URL/health" -Method Get -ErrorAction Stop
    Write-Host "✅ MCP Server is healthy!" -ForegroundColor Green
} catch {
    Write-Host "⚠️  Health check failed, but deployment may still be in progress" -ForegroundColor Yellow
}

Write-Host ""
Write-Host "🎉 Deployment complete!" -ForegroundColor Green
Write-Host "MCP Server URL: $MCP_URL" -ForegroundColor Cyan
Write-Host "Backend URL: https://$BACKEND_URL" -ForegroundColor Cyan
Write-Host ""
Write-Host "Test with:" -ForegroundColor Yellow
Write-Host 'python query_earth_copilot.py "Show me HLS images of Seattle"' -ForegroundColor White

# Return to original directory
Set-Location -Path $PSScriptRoot\..
