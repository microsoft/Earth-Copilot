# Deploy Earth Copilot Infrastructure
# This script deploys the complete infrastructure including VNet, Container Apps, and supporting services
# Auto-discovers or creates resource group from Azure subscription

param(
    [Parameter(Mandatory=$false)]
    [string]$Location = "eastus2"
)

Write-Host "Earth Copilot Infrastructure Deployment" -ForegroundColor Green
Write-Host "=======================================" -ForegroundColor Green

$deploymentName = "earth-copilot-$(Get-Date -Format 'yyyyMMdd-HHmmss')"

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

# ========================================
# AUTO-DISCOVER OR CREATE RESOURCE GROUP
# ========================================
Write-Host "`nDeployment Configuration:" -ForegroundColor Yellow
Write-Host "Location: $Location" -ForegroundColor White
Write-Host "Deployment Name: $deploymentName" -ForegroundColor White
Write-Host "Note: main.bicep is subscription-scoped and will create resource group 'rg-earthcopilot' automatically." -ForegroundColor Gray

# Deploy the infrastructure
# main.bicep is subscription-scoped (creates its own resource group)
Write-Host "`nDeploying infrastructure (subscription-scoped)..." -ForegroundColor Cyan
Write-Host "This may take several minutes..." -ForegroundColor Yellow

az deployment sub create `
    --location $Location `
    --template-file "earth-copilot/infra/main.bicep" `
    --parameters "earth-copilot/infra/main.parameters.json" `
    --name $deploymentName

$ResourceGroup = "rg-earthcopilot"

if ($LASTEXITCODE -eq 0) {
    Write-Host "Infrastructure deployment completed successfully!" -ForegroundColor Green
    
    # Discover deployed resources
    Write-Host "`nDiscovering deployed resources..." -ForegroundColor Cyan
    
    $containerApp = az containerapp list --resource-group $ResourceGroup --query "[0].name" -o tsv 2>$null
    $appService = az webapp list --resource-group $ResourceGroup --query "[0].name" -o tsv 2>$null
    $registry = az acr list --resource-group $ResourceGroup --query "[0].name" -o tsv 2>$null
    
    Write-Host "`nDeployed Resources:" -ForegroundColor Yellow
    Write-Host "  - Resource Group: $ResourceGroup" -ForegroundColor White
    Write-Host "  - Container App: $containerApp" -ForegroundColor White
    Write-Host "  - App Service: $appService" -ForegroundColor White
    Write-Host "  - Container Registry: $registry" -ForegroundColor White
    
    Write-Host "`nInfrastructure is ready!" -ForegroundColor Green
    Write-Host "Next steps:" -ForegroundColor Yellow
    Write-Host "1. Deploy backend: cd earth-copilot\container-app; .\deploy-backend.ps1" -ForegroundColor White
    Write-Host "2. Deploy frontend: cd earth-copilot\web-ui; .\deploy-frontend.ps1" -ForegroundColor White
    Write-Host "3. Or deploy both: cd earth-copilot; .\deploy-all.ps1" -ForegroundColor White
    Write-Host ""
    Write-Host "Note: Scripts auto-discover resource names from Azure - no parameters needed!" -ForegroundColor Cyan
    
} else {
    Write-Host "Infrastructure deployment failed" -ForegroundColor Red
    Write-Host "Please check the error messages above and try again." -ForegroundColor Yellow
    exit 1
}