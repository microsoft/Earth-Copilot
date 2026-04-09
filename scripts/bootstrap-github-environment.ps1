# Bootstrap GitHub Environment for Earth Copilot Deployment (PowerShell)
#
# This script creates/updates a GitHub environment with variables and secrets
# for automated deployment via GitHub Actions.
#
# Usage:
#   .\scripts\bootstrap-github-environment.ps1 -ConfigFile <path> [-Repo <owner/repo>]
#
# Example:
#   .\scripts\bootstrap-github-environment.ps1 -ConfigFile .github\environment-config-dev.yml -Repo "microsoft/Earth-Copilot"
#

param(
    [Parameter(Mandatory=$true)]
    [string]$ConfigFile,
    
    [Parameter(Mandatory=$false)]
    [string]$Repo = ""
)

$ErrorActionPreference = "Stop"

# Check prerequisites
function Test-Prerequisites {
    Write-Host "Checking prerequisites..." -ForegroundColor Cyan
    
    # Check for gh CLI
    if (-not (Get-Command gh -ErrorAction SilentlyContinue)) {
        Write-Host "[ERROR] GitHub CLI (gh) is not installed" -ForegroundColor Red
        Write-Host "Install from: https://cli.github.com/" -ForegroundColor Yellow
        exit 1
    }
    
    # Check for yq (PowerShell-yaml as alternative)
    if (-not (Get-Command yq -ErrorAction SilentlyContinue)) {
        Write-Host "[WARNING] yq not found. Installing PowerShell-yaml module..." -ForegroundColor Yellow
        Install-Module -Name powershell-yaml -Force -Scope CurrentUser
    }
    
    # Check gh authentication
    $authStatus = gh auth status 2>&1
    if ($LASTEXITCODE -ne 0) {
        Write-Host "[ERROR] GitHub CLI is not authenticated" -ForegroundColor Red
        Write-Host "Run: gh auth login" -ForegroundColor Yellow
        exit 1
    }
    
    Write-Host "[SUCCESS] All prerequisites met" -ForegroundColor Green
}

# Parse config file
function Read-ConfigFile {
    param([string]$Path)
    
    if (-not (Test-Path $Path)) {
        Write-Host "[ERROR] Config file not found: $Path" -ForegroundColor Red
        exit 1
    }
    
    Write-Host "Parsing configuration from: $Path" -ForegroundColor Cyan
    
    # Read YAML file
    Import-Module powershell-yaml
    $config = Get-Content $Path -Raw | ConvertFrom-Yaml
    
    # Extract values
    $script:ENV_NAME = $config.environment.name
    $script:ENV_DESCRIPTION = $config.environment.description
    $script:REQUIRE_APPROVAL = $config.environment.requireApproval
    
    $script:AZURE_SUBSCRIPTION_ID = $config.variables.AZURE_SUBSCRIPTION_ID
    $script:AZURE_RESOURCE_GROUP = $config.variables.AZURE_RESOURCE_GROUP
    $script:AZURE_LOCATION = $config.variables.AZURE_LOCATION
    $script:ENVIRONMENT_NAME = $config.variables.ENVIRONMENT_NAME
    
    $script:DEPLOY_AI_SEARCH = if ($config.variables.DEPLOY_AI_SEARCH) { $config.variables.DEPLOY_AI_SEARCH } else { "false" }
    $script:SKIP_MODELS = if ($config.variables.SKIP_MODELS) { $config.variables.SKIP_MODELS } else { "false" }
    $script:ENABLE_AUTHENTICATION = if ($config.variables.ENABLE_AUTHENTICATION) { $config.variables.ENABLE_AUTHENTICATION } else { "false" }
    
    Write-Host "[SUCCESS] Configuration parsed successfully" -ForegroundColor Green
    Write-Host "  Environment: $ENV_NAME" -ForegroundColor Gray
    Write-Host "  Subscription: $AZURE_SUBSCRIPTION_ID" -ForegroundColor Gray
    Write-Host "  Resource Group: $AZURE_RESOURCE_GROUP" -ForegroundColor Gray
    Write-Host "  Location: $AZURE_LOCATION" -ForegroundColor Gray
}

# Create or update GitHub environment
function New-GitHubEnvironment {
    param([string]$Repository)
    
    Write-Host "Creating/updating GitHub environment: $ENV_NAME" -ForegroundColor Cyan
    
    # Create/update environment
    $apiCall = "repos/$Repository/environments/$ENV_NAME"
    
    try {
        gh api -X PUT $apiCall 2>$null
        Write-Host "[SUCCESS] Environment created/updated: $ENV_NAME" -ForegroundColor Green
    } catch {
        Write-Host "[ERROR] Failed to create environment: $_" -ForegroundColor Red
        exit 1
    }
}

# Set environment variables
function Set-EnvironmentVariables {
    param([string]$Repository)
    
    Write-Host "Setting environment variables..." -ForegroundColor Cyan
    
    $variables = @{
        "AZURE_SUBSCRIPTION_ID" = $AZURE_SUBSCRIPTION_ID
        "AZURE_RESOURCE_GROUP" = $AZURE_RESOURCE_GROUP
        "AZURE_LOCATION" = $AZURE_LOCATION
        "ENVIRONMENT_NAME" = $ENVIRONMENT_NAME
        "DEPLOY_AI_SEARCH" = $DEPLOY_AI_SEARCH
        "SKIP_MODELS" = $SKIP_MODELS
        "ENABLE_AUTHENTICATION" = $ENABLE_AUTHENTICATION
    }
    
    foreach ($varName in $variables.Keys) {
        $varValue = $variables[$varName]
        Write-Host "Setting $varName..." -ForegroundColor Gray
        
        try {
            # Try update first
            gh api -X PUT "repos/$Repository/environments/$ENV_NAME/variables/$varName" `
                -f name="$varName" `
                -f value="$varValue" 2>$null
        } catch {
            # Create if update fails
            gh api -X POST "repos/$Repository/environments/$ENV_NAME/variables" `
                -f name="$varName" `
                -f value="$varValue" 2>$null
        }
    }
    
    Write-Host "[SUCCESS] All variables set successfully" -ForegroundColor Green
}

# Set environment secrets
function Set-EnvironmentSecrets {
    param([string]$Repository)
    
    Write-Host "Setting up environment secrets..." -ForegroundColor Cyan
    Write-Host ""
    Write-Host "[WARNING] You will be prompted to enter secret values." -ForegroundColor Yellow
    Write-Host ""
    
    # AZURE_CREDENTIALS
    Write-Host "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━" -ForegroundColor Yellow
    Write-Host "AZURE_CREDENTIALS" -ForegroundColor Blue
    Write-Host "This is the service principal JSON for Azure authentication."
    Write-Host ""
    Write-Host "To create, run:"
    Write-Host "  az ad sp create-for-rbac ``" -ForegroundColor Gray
    Write-Host "    --name 'sp-earthcopilot-$ENV_NAME' ``" -ForegroundColor Gray
    Write-Host "    --role Contributor ``" -ForegroundColor Gray
    Write-Host "    --scopes /subscriptions/$AZURE_SUBSCRIPTION_ID ``" -ForegroundColor Gray
    Write-Host "    --sdk-auth" -ForegroundColor Gray
    Write-Host ""
    Write-Host "Paste the entire JSON output below (press Enter on empty line when done):" -ForegroundColor Yellow
    Write-Host "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━" -ForegroundColor Yellow
    
    $jsonLines = @()
    do {
        $line = Read-Host
        if ($line) { $jsonLines += $line }
    } while ($line)
    
    $AZURE_CREDENTIALS = $jsonLines -join "`n"
    
    if ([string]::IsNullOrWhiteSpace($AZURE_CREDENTIALS)) {
        Write-Host "[ERROR] AZURE_CREDENTIALS cannot be empty" -ForegroundColor Red
        exit 1
    }
    
    # Validate JSON
    try {
        $AZURE_CREDENTIALS | ConvertFrom-Json | Out-Null
    } catch {
        Write-Host "[ERROR] AZURE_CREDENTIALS is not valid JSON" -ForegroundColor Red
        exit 1
    }
    
    Write-Host "Setting AZURE_CREDENTIALS secret..." -ForegroundColor Gray
    $AZURE_CREDENTIALS | gh secret set AZURE_CREDENTIALS --repo $Repository --env $ENV_NAME
    
    Write-Host "[SUCCESS] AZURE_CREDENTIALS set successfully" -ForegroundColor Green
    
    # Optional: Authentication secrets
    if ($ENABLE_AUTHENTICATION -eq "true") {
        Write-Host ""
        Write-Host "Authentication is enabled. Setting up Entra ID secrets..." -ForegroundColor Cyan
        
        $ENTRA_CLIENT_ID = Read-Host "Microsoft Entra Client ID"
        $ENTRA_TENANT_ID = Read-Host "Microsoft Entra Tenant ID"
        $ENTRA_CLIENT_SECRET = Read-Host "Microsoft Entra Client Secret" -AsSecureString
        $ENTRA_CLIENT_SECRET_TEXT = [System.Runtime.InteropServices.Marshal]::PtrToStringAuto(
            [System.Runtime.InteropServices.Marshal]::SecureStringToBSTR($ENTRA_CLIENT_SECRET)
        )
        
        $ENTRA_CLIENT_ID | gh secret set MICROSOFT_ENTRA_CLIENT_ID --repo $Repository --env $ENV_NAME
        $ENTRA_TENANT_ID | gh secret set MICROSOFT_ENTRA_TENANT_ID --repo $Repository --env $ENV_NAME
        $ENTRA_CLIENT_SECRET_TEXT | gh secret set MICROSOFT_ENTRA_CLIENT_SECRET --repo $Repository --env $ENV_NAME
        
        Write-Host "[SUCCESS] Authentication secrets set successfully" -ForegroundColor Green
    }
}

# Main execution
function Main {
    # Detect repo if not provided
    if ([string]::IsNullOrWhiteSpace($Repo)) {
        if (Test-Path ".git") {
            $Repo = (gh repo view --json nameWithOwner -q .nameWithOwner 2>$null)
        }
        
        if ([string]::IsNullOrWhiteSpace($Repo)) {
            Write-Host "[ERROR] Could not detect repository. Please provide -Repo parameter." -ForegroundColor Red
            exit 1
        }
    }
    
    Write-Host "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━" -ForegroundColor Cyan
    Write-Host "  Earth Copilot GitHub Environment Bootstrap" -ForegroundColor Cyan
    Write-Host "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━" -ForegroundColor Cyan
    Write-Host "Repository: $Repo" -ForegroundColor Cyan
    Write-Host ""
    
    Test-Prerequisites
    Read-ConfigFile -Path $ConfigFile
    New-GitHubEnvironment -Repository $Repo
    Set-EnvironmentVariables -Repository $Repo
    Set-EnvironmentSecrets -Repository $Repo
    
    Write-Host ""
    Write-Host "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━" -ForegroundColor Green
    Write-Host "  Bootstrap Complete!" -ForegroundColor Green
    Write-Host "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━" -ForegroundColor Green
    Write-Host ""
    Write-Host "Next steps:" -ForegroundColor Cyan
    Write-Host "  1. Go to: https://github.com/$Repo/actions/workflows/deploy-infrastructure.yml" -ForegroundColor White
    Write-Host "  2. Click 'Run workflow'" -ForegroundColor White
    Write-Host "  3. Select environment: $ENV_NAME" -ForegroundColor White
    Write-Host "  4. Click 'Run workflow' button" -ForegroundColor White
    Write-Host ""
    Write-Host "The workflow will:" -ForegroundColor Cyan
    Write-Host "  [OK] Deploy infrastructure to Azure" -ForegroundColor White
    Write-Host "  [OK] Build and deploy backend container" -ForegroundColor White
    Write-Host "  [OK] Build and deploy frontend app" -ForegroundColor White
    Write-Host "  [OK] Store all secrets in Key Vault" -ForegroundColor White
    Write-Host ""
    Write-Host "[SUCCESS] Your Earth Copilot will be live in ~10-15 minutes!" -ForegroundColor Green
}

Main
