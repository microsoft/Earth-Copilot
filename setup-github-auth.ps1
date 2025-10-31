# Azure Container App CI/CD Setup Script
# This script sets up the necessary Azure credentials for GitHub Actions

param(
    [Parameter(Mandatory=$true)]
    [string]$GitHubRepository = "microsoft/Earth-Copilot",
    
    [Parameter(Mandatory=$false)]
    [string]$ResourceGroup = "earthcopilot-rg",
    
    [Parameter(Mandatory=$false)]
    [string]$SubscriptionId
)

Write-Host "🔐 Setting up Azure authentication for GitHub Actions..." -ForegroundColor Green

# Get current subscription if not provided
if (-not $SubscriptionId) {
    $SubscriptionId = (az account show --query "id" -o tsv)
    Write-Host "Using current subscription: $SubscriptionId" -ForegroundColor Cyan
}

# Get tenant ID
$TenantId = (az account show --query "tenantId" -o tsv)
Write-Host "Tenant ID: $TenantId" -ForegroundColor Cyan

# Create or get service principal for GitHub Actions
$AppName = "earthcopilot-github-actions"
Write-Host "Creating service principal: $AppName..." -ForegroundColor Yellow

# Create the service principal
$SP = az ad sp create-for-rbac --name $AppName --role contributor --scopes "/subscriptions/$SubscriptionId/resourceGroups/$ResourceGroup" --json-auth | ConvertFrom-Json

if (-not $SP) {
    Write-Host "❌ Failed to create service principal" -ForegroundColor Red
    exit 1
}

Write-Host "✅ Service principal created successfully!" -ForegroundColor Green

# Create federated identity credential for GitHub Actions
Write-Host "Setting up federated identity credentials..." -ForegroundColor Yellow

$FederatedCredential = @{
    name = "github-actions-main"
    issuer = "https://token.actions.githubusercontent.com"
    subject = "repo:$GitHubRepository" + ":ref:refs/heads/main"
    audiences = @("api://AzureADTokenExchange")
}

$AppId = $SP.clientId
az ad app federated-credential create --id $AppId --parameters ($FederatedCredential | ConvertTo-Json -Depth 3)

if ($LASTEXITCODE -eq 0) {
    Write-Host "✅ Federated identity credential created successfully!" -ForegroundColor Green
} else {
    Write-Host "❌ Failed to create federated identity credential" -ForegroundColor Red
}

# Display the secrets that need to be added to GitHub
Write-Host ""
Write-Host "🔑 GitHub Secrets Configuration" -ForegroundColor Green
Write-Host "=================================" -ForegroundColor Green
Write-Host "Add these secrets to your GitHub repository settings:" -ForegroundColor Yellow
Write-Host ""
Write-Host "AZURE_CLIENT_ID: $($SP.clientId)" -ForegroundColor Cyan
Write-Host "AZURE_TENANT_ID: $TenantId" -ForegroundColor Cyan  
Write-Host "AZURE_SUBSCRIPTION_ID: $SubscriptionId" -ForegroundColor Cyan
Write-Host ""
Write-Host "🌐 GitHub Repository Settings URL:" -ForegroundColor Yellow
Write-Host "https://github.com/$GitHubRepository/settings/secrets/actions" -ForegroundColor Blue
Write-Host ""
Write-Host "📝 Next Steps:" -ForegroundColor Green
Write-Host "1. Go to the GitHub repository settings" -ForegroundColor White
Write-Host "2. Navigate to Secrets and variables > Actions" -ForegroundColor White
Write-Host "3. Add the three secrets listed above" -ForegroundColor White
Write-Host "4. Commit and push your code changes to trigger deployment" -ForegroundColor White