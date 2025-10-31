# Deploy Earth Copilot Infrastructure
# This script deploys the complete infrastructure including VNet, Container Apps, and supporting services

param(
    [Parameter(Mandatory=$false)]
    [string]$ResourceGroup = "earthcopilot-rg",
    
    [Parameter(Mandatory=$false)]
    [string]$Location = "eastus2"
)

Write-Host "Earth Copilot Infrastructure Deployment" -ForegroundColor Green
Write-Host "=======================================" -ForegroundColor Green

$resourceGroupName = $ResourceGroup
$location = $Location
$deploymentName = "earth-copilot-$(Get-Date -Format 'yyyyMMdd-HHmmss')"

Write-Host "`nDeployment Configuration:" -ForegroundColor Yellow
Write-Host "Resource Group: $resourceGroupName" -ForegroundColor White
Write-Host "Location: $location" -ForegroundColor White
Write-Host "Deployment Name: $deploymentName" -ForegroundColor White

# Check if already signed in to Azure
Write-Host "`nChecking Azure authentication..." -ForegroundColor Cyan
$currentAccount = az account show 2>$null
if ($LASTEXITCODE -ne 0) {
    Write-Host "Please sign in to Azure..." -ForegroundColor Yellow
    az login
    if ($LASTEXITCODE -ne 0) {
        Write-Host "Failed to sign in to Azure" -ForegroundColor Red
        exit 1
    }
}

Write-Host "Authenticated with Azure" -ForegroundColor Green

# Create resource group if it doesn't exist
Write-Host "`nCreating resource group..." -ForegroundColor Cyan
az group create --name $resourceGroupName --location $location
if ($LASTEXITCODE -eq 0) {
    Write-Host "Resource group '$resourceGroupName' ready" -ForegroundColor Green
} else {
    Write-Host "Failed to create resource group" -ForegroundColor Red
    exit 1
}

# Deploy the infrastructure
Write-Host "`nDeploying infrastructure..." -ForegroundColor Cyan
Write-Host "This may take several minutes..." -ForegroundColor Yellow

az deployment group create `
    --resource-group $resourceGroupName `
    --template-file "infra/main.bicep" `
    --parameters "infra/main.parameters.json" `
    --name $deploymentName

if ($LASTEXITCODE -eq 0) {
    Write-Host "Infrastructure deployment completed successfully!" -ForegroundColor Green
    
    Write-Host "`nDeployed Resources (East US 2):" -ForegroundColor Yellow
    Write-Host "Core Infrastructure:" -ForegroundColor Cyan
    Write-Host "  • Virtual Network: earthcopilot-vnet (10.0.0.0/16) - with custom DNS" -ForegroundColor White
    Write-Host "  • Container Apps Environment: VNet-integrated with Log Analytics" -ForegroundColor White
    Write-Host "  • Container App: earthcopilot-api (Backend API)" -ForegroundColor White
    Write-Host "  • Container Registry: earthcopilotregistry" -ForegroundColor White
    Write-Host "  • App Service: earthcopilot-web-ui (Frontend)" -ForegroundColor White
    Write-Host "  • App Service Plan: F1 tier" -ForegroundColor White
    Write-Host ""
    Write-Host "AI & Data Services:" -ForegroundColor Cyan
    Write-Host "  • Azure AI Foundry: GPT-4o/GPT-5 deployments" -ForegroundColor White
    Write-Host "  • Azure AI Search: STAC metadata indexing" -ForegroundColor White
    Write-Host "  • Azure Maps: Geocoding and map tiles" -ForegroundColor White
    Write-Host "  • Storage Account: Data and logs" -ForegroundColor White
    Write-Host "  • Key Vault: Secrets management" -ForegroundColor White
    Write-Host "  • Application Insights: Monitoring" -ForegroundColor White
    Write-Host "  • Log Analytics: Centralized logging" -ForegroundColor White
    
    Write-Host "`nInfrastructure is ready!" -ForegroundColor Green
    Write-Host "Next steps:" -ForegroundColor Yellow
    Write-Host "1. Run './collect-env-vars.ps1' to collect environment variables" -ForegroundColor White
    Write-Host "2. Deploy backend: cd earth-copilot\container-app; .\deploy-backend.ps1" -ForegroundColor White
    Write-Host "3. Deploy frontend: cd earth-copilot\web-ui; .\deploy-frontend.ps1" -ForegroundColor White
    Write-Host "4. Or deploy both: cd earth-copilot; .\deploy-all.ps1" -ForegroundColor White
    
} else {
    Write-Host "Infrastructure deployment failed" -ForegroundColor Red
    Write-Host "Please check the error messages above and try again." -ForegroundColor Yellow
    exit 1
}