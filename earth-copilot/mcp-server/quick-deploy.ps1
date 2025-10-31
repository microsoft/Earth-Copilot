# Quick Deploy Script for Earth Copilot MCP Server to Azure Container Apps
# This script automates the deployment process

param(
    [Parameter(Mandatory=$false)]
    [string]$ResourceGroup = "earth-copilot-rg",
    
    [Parameter(Mandatory=$false)]
    [string]$Location = "eastus",
    
    [Parameter(Mandatory=$false)]
    [string]$AcrName = "earthcopilotacr",
    
    [Parameter(Mandatory=$false)]
    [string]$ContainerAppName = "earth-copilot-mcp",
    
    [Parameter(Mandatory=$false)]
    [string]$EnvironmentName = "earth-copilot-env",
    
    [Parameter(Mandatory=$false)]
    [string]$EarthCopilotBackendUrl = "",
    
    [Parameter(Mandatory=$false)]
    [string]$GeointServiceUrl = "",
    
    [switch]$SkipBuild = $false
)

$ErrorActionPreference = "Stop"

Write-Host @"

╔══════════════════════════════════════════════════════════════╗
║  🌍 Earth Copilot MCP Server - Azure Deployment            ║
╚══════════════════════════════════════════════════════════════╝

"@ -ForegroundColor Cyan

# Check Azure CLI
Write-Host "🔍 Checking prerequisites..." -ForegroundColor Yellow
try {
    $azVersion = az version --output json | ConvertFrom-Json
    Write-Host "✅ Azure CLI version: $($azVersion.'azure-cli')" -ForegroundColor Green
} catch {
    Write-Host "❌ Azure CLI not found. Please install: https://aka.ms/installazurecli" -ForegroundColor Red
    exit 1
}

# Login check
Write-Host "🔐 Checking Azure authentication..." -ForegroundColor Yellow
try {
    $account = az account show --output json | ConvertFrom-Json
    Write-Host "✅ Logged in as: $($account.user.name)" -ForegroundColor Green
    Write-Host "   Subscription: $($account.name)" -ForegroundColor Gray
} catch {
    Write-Host "⚠️  Not logged in. Running 'az login'..." -ForegroundColor Yellow
    az login
}

# Create resource group
Write-Host "`n📦 Setting up resource group..." -ForegroundColor Yellow
$rgExists = az group exists --name $ResourceGroup
if ($rgExists -eq "false") {
    Write-Host "   Creating resource group: $ResourceGroup" -ForegroundColor Gray
    az group create --name $ResourceGroup --location $Location --output none
    Write-Host "✅ Resource group created" -ForegroundColor Green
} else {
    Write-Host "✅ Resource group exists" -ForegroundColor Green
}

# Create ACR
Write-Host "`n🐳 Setting up Azure Container Registry..." -ForegroundColor Yellow
$acrExists = az acr show --name $AcrName --resource-group $ResourceGroup 2>$null
if (-not $acrExists) {
    Write-Host "   Creating ACR: $AcrName" -ForegroundColor Gray
    az acr create `
        --resource-group $ResourceGroup `
        --name $AcrName `
        --sku Basic `
        --location $Location `
        --admin-enabled true `
        --output none
    Write-Host "✅ ACR created" -ForegroundColor Green
} else {
    Write-Host "✅ ACR exists" -ForegroundColor Green
    # Ensure admin is enabled
    az acr update --name $AcrName --admin-enabled true --output none
}

# Build and push image
if (-not $SkipBuild) {
    Write-Host "`n🔨 Building Docker image..." -ForegroundColor Yellow
    Write-Host "   This may take a few minutes..." -ForegroundColor Gray
    
    $imageName = "earth-copilot-mcp"
    $imageTag = (Get-Date -Format "yyyyMMdd-HHmmss")
    
    az acr build `
        --registry $AcrName `
        --image "${imageName}:${imageTag}" `
        --image "${imageName}:latest" `
        --file Dockerfile `
        . `
        --output table
    
    if ($LASTEXITCODE -eq 0) {
        Write-Host "✅ Image built and pushed" -ForegroundColor Green
    } else {
        Write-Host "❌ Image build failed" -ForegroundColor Red
        exit 1
    }
} else {
    Write-Host "`n⏭️  Skipping image build (using existing latest)" -ForegroundColor Yellow
}

# Get ACR credentials
Write-Host "`n🔑 Retrieving ACR credentials..." -ForegroundColor Yellow
$acrServer = az acr show --name $AcrName --query loginServer -o tsv
$acrUsername = az acr credential show --name $AcrName --query username -o tsv
$acrPassword = az acr credential show --name $AcrName --query "passwords[0].value" -o tsv
Write-Host "✅ Credentials retrieved" -ForegroundColor Green

# Create Container Apps environment
Write-Host "`n🏗️  Setting up Container Apps environment..." -ForegroundColor Yellow
$envExists = az containerapp env show --name $EnvironmentName --resource-group $ResourceGroup 2>$null
if (-not $envExists) {
    Write-Host "   Creating environment: $EnvironmentName" -ForegroundColor Gray
    az containerapp env create `
        --name $EnvironmentName `
        --resource-group $ResourceGroup `
        --location $Location `
        --output none
    Write-Host "✅ Environment created" -ForegroundColor Green
} else {
    Write-Host "✅ Environment exists" -ForegroundColor Green
}

# Deploy Container App
Write-Host "`n🚀 Deploying Container App..." -ForegroundColor Yellow

# Build environment variables
$envVars = @(
    "MCP_SERVER_MODE=production"
)

if ($EarthCopilotBackendUrl) {
    $envVars += "EARTH_COPILOT_BASE_URL=$EarthCopilotBackendUrl"
    Write-Host "   Backend URL: $EarthCopilotBackendUrl" -ForegroundColor Gray
} else {
    Write-Host "   ⚠️  No backend URL specified (using placeholder)" -ForegroundColor Yellow
    $envVars += "EARTH_COPILOT_BASE_URL=https://your-backend.azurecontainerapps.io"
}

if ($GeointServiceUrl) {
    $envVars += "GEOINT_SERVICE_URL=$GeointServiceUrl"
    Write-Host "   GEOINT URL: $GeointServiceUrl" -ForegroundColor Gray
}

$appExists = az containerapp show --name $ContainerAppName --resource-group $ResourceGroup 2>$null

if (-not $appExists) {
    Write-Host "   Creating new container app..." -ForegroundColor Gray
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
        --env-vars $envVars `
        --cpu 0.5 `
        --memory 1.0Gi `
        --min-replicas 1 `
        --max-replicas 3 `
        --output none
} else {
    Write-Host "   Updating existing container app..." -ForegroundColor Gray
    az containerapp update `
        --name $ContainerAppName `
        --resource-group $ResourceGroup `
        --image "${acrServer}/earth-copilot-mcp:latest" `
        --set-env-vars $envVars `
        --output none
}

if ($LASTEXITCODE -eq 0) {
    Write-Host "✅ Container App deployed" -ForegroundColor Green
} else {
    Write-Host "❌ Deployment failed" -ForegroundColor Red
    exit 1
}

# Get endpoint URL
Write-Host "`n📍 Retrieving endpoint..." -ForegroundColor Yellow
$mcpUrl = az containerapp show `
    --name $ContainerAppName `
    --resource-group $ResourceGroup `
    --query properties.configuration.ingress.fqdn `
    -o tsv

$mcpUrl = "https://$mcpUrl"

Write-Host @"

╔══════════════════════════════════════════════════════════════╗
║  ✅ DEPLOYMENT SUCCESSFUL!                                  ║
╚══════════════════════════════════════════════════════════════╝

🌐 MCP Server URL: $mcpUrl

📊 Quick Tests:
   Health:        curl $mcpUrl/
   API Docs:      $mcpUrl/docs
   Tools List:    curl -X POST $mcpUrl/tools/list

🧪 Run Full Test Suite:
   python test_deployed_mcp.py $mcpUrl

📊 View Logs:
   az containerapp logs show --name $ContainerAppName --resource-group $ResourceGroup --follow

🔧 Update Backend URLs:
   az containerapp update --name $ContainerAppName --resource-group $ResourceGroup --set-env-vars EARTH_COPILOT_BASE_URL=https://your-backend-url GEOINT_SERVICE_URL=https://your-geoint-url

"@ -ForegroundColor Green

# Save deployment info
$deploymentInfo = @{
    timestamp = (Get-Date -Format "yyyy-MM-dd HH:mm:ss")
    resourceGroup = $ResourceGroup
    containerApp = $ContainerAppName
    mcpUrl = $mcpUrl
    acrServer = $acrServer
    environment = $EnvironmentName
} | ConvertTo-Json

$deploymentInfo | Out-File -FilePath "deployment-info.json" -Encoding UTF8
Write-Host "💾 Deployment info saved to: deployment-info.json`n" -ForegroundColor Gray
