# Simple Deploy Script for Earth Copilot MCP Server
param(
    [string]$ResourceGroup = "earth-copilot-rg",
    [string]$Location = "eastus",
    [string]$AcrName = "earthcopilotacr",
    [string]$ContainerAppName = "earth-copilot-mcp",
    [string]$EnvironmentName = "earth-copilot-env"
)

$ErrorActionPreference = "Stop"

Write-Host "`n=== Earth Copilot MCP Server Deployment ===" -ForegroundColor Cyan
Write-Host "Resource Group: $ResourceGroup" -ForegroundColor Yellow
Write-Host "Container App: $ContainerAppName`n" -ForegroundColor Yellow

# Login check
Write-Host "Checking Azure authentication..." -ForegroundColor Yellow
try {
    $account = az account show --output json | ConvertFrom-Json
    Write-Host "Logged in as: $($account.user.name)`n" -ForegroundColor Green
} catch {
    Write-Host "Not logged in. Running 'az login'..." -ForegroundColor Yellow
    az login
}

# Create resource group
Write-Host "Setting up resource group..." -ForegroundColor Yellow
$rgExists = az group exists --name $ResourceGroup
if ($rgExists -eq "false") {
    az group create --name $ResourceGroup --location $Location --output none
    Write-Host "Resource group created`n" -ForegroundColor Green
} else {
    Write-Host "Resource group exists`n" -ForegroundColor Green
}

# Create ACR
Write-Host "Setting up Azure Container Registry..." -ForegroundColor Yellow
$acrExists = az acr show --name $AcrName --resource-group $ResourceGroup 2>$null
if (-not $acrExists) {
    az acr create --resource-group $ResourceGroup --name $AcrName --sku Basic --location $Location --admin-enabled true --output none
    Write-Host "ACR created`n" -ForegroundColor Green
} else {
    Write-Host "ACR exists`n" -ForegroundColor Green
    az acr update --name $AcrName --admin-enabled true --output none
}

# Build and push image
Write-Host "Building Docker image (this may take a few minutes)..." -ForegroundColor Yellow
az acr build --registry $AcrName --image "earth-copilot-mcp:latest" --file Dockerfile . --output table

if ($LASTEXITCODE -ne 0) {
    Write-Host "Image build failed" -ForegroundColor Red
    exit 1
}
Write-Host "Image built and pushed`n" -ForegroundColor Green

# Get ACR credentials
Write-Host "Retrieving ACR credentials..." -ForegroundColor Yellow
$acrServer = az acr show --name $AcrName --query loginServer -o tsv
$acrUsername = az acr credential show --name $AcrName --query username -o tsv
$acrPassword = az acr credential show --name $AcrName --query "passwords[0].value" -o tsv
Write-Host "Credentials retrieved`n" -ForegroundColor Green

# Create Container Apps environment
Write-Host "Setting up Container Apps environment..." -ForegroundColor Yellow
$envExists = az containerapp env show --name $EnvironmentName --resource-group $ResourceGroup 2>$null
if (-not $envExists) {
    az containerapp env create --name $EnvironmentName --resource-group $ResourceGroup --location $Location --output none
    Write-Host "Environment created`n" -ForegroundColor Green
} else {
    Write-Host "Environment exists`n" -ForegroundColor Green
}

# Deploy Container App
Write-Host "Deploying Container App..." -ForegroundColor Yellow

$appExists = az containerapp show --name $ContainerAppName --resource-group $ResourceGroup 2>$null

if (-not $appExists) {
    az containerapp create `
        --name $ContainerAppName `
        --resource-group $ResourceGroup `
        --environment $EnvironmentName `
        --image "${acrServer}/earth-copilot-mcp:latest" `
        --target-port 8080 `
        --ingress external `
        --registry-server $acrServer `
        --registry-username $acrUsername `
        --registry-password $acrPassword `
        --env-vars "MCP_SERVER_MODE=production" "EARTH_COPILOT_BASE_URL=http://localhost:8000" "GEOINT_SERVICE_URL=http://localhost:8001" `
        --cpu 0.5 `
        --memory 1.0Gi `
        --min-replicas 1 `
        --max-replicas 3 `
        --output none
} else {
    az containerapp update `
        --name $ContainerAppName `
        --resource-group $ResourceGroup `
        --image "${acrServer}/earth-copilot-mcp:latest" `
        --output none
}

if ($LASTEXITCODE -ne 0) {
    Write-Host "Deployment failed" -ForegroundColor Red
    exit 1
}
Write-Host "Container App deployed`n" -ForegroundColor Green

# Get endpoint URL
Write-Host "Retrieving endpoint..." -ForegroundColor Yellow
$mcpUrl = az containerapp show --name $ContainerAppName --resource-group $ResourceGroup --query properties.configuration.ingress.fqdn -o tsv
$mcpUrl = "https://$mcpUrl"

Write-Host "`n=== DEPLOYMENT SUCCESSFUL ===" -ForegroundColor Green
Write-Host "MCP Server URL: $mcpUrl" -ForegroundColor Cyan
Write-Host "`nAPI Docs: $mcpUrl/docs" -ForegroundColor Gray
Write-Host "`nTest with:`npython test_deployed_mcp.py $mcpUrl`n" -ForegroundColor Gray

# Save deployment info
@{
    timestamp = (Get-Date -Format "yyyy-MM-dd HH:mm:ss")
    resourceGroup = $ResourceGroup
    containerApp = $ContainerAppName
    mcpUrl = $mcpUrl
} | ConvertTo-Json | Out-File "deployment-info.json" -Encoding UTF8

Write-Host "Deployment info saved to: deployment-info.json`n" -ForegroundColor Gray
