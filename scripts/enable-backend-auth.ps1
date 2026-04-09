# Enable Entra ID Authentication for Earth Copilot Backend
# This script helps you configure authentication parameters for the backend API

param(
    [Parameter(Mandatory=$true, HelpMessage="Application (Client) ID from your App Registration")]
    [string]$ClientId,
    
    [Parameter(Mandatory=$true, HelpMessage="Directory (Tenant) ID")]
    [string]$TenantId,
    
    [Parameter(Mandatory=$true, HelpMessage="Client Secret value")]
    [string]$ClientSecret,
    
    [Parameter(Mandatory=$false)]
    [string]$EnvironmentName = "earthcopilot",
    
    [Parameter(Mandatory=$false)]
    [switch]$DeployAfterConfig
)

Write-Host "========================================" -ForegroundColor Cyan
Write-Host "Enable Backend API Authentication" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""

# Validate inputs
if ([string]::IsNullOrWhiteSpace($ClientId)) {
    Write-Host "[FAIL] ERROR: Client ID is required" -ForegroundColor Red
    exit 1
}

if ([string]::IsNullOrWhiteSpace($TenantId)) {
    Write-Host "[FAIL] ERROR: Tenant ID is required" -ForegroundColor Red
    exit 1
}

if ([string]::IsNullOrWhiteSpace($ClientSecret)) {
    Write-Host "[FAIL] ERROR: Client Secret is required" -ForegroundColor Red
    exit 1
}

Write-Host "[LIST] Configuration:" -ForegroundColor Yellow
Write-Host "   Environment: $EnvironmentName"
Write-Host "   Client ID: $ClientId"
Write-Host "   Tenant ID: $TenantId"
Write-Host "   Client Secret: ****** (hidden)"
Write-Host ""

# Find .azure directory
$azureDir = Join-Path $PSScriptRoot ".azure"
$envDir = Join-Path $azureDir $EnvironmentName

if (-not (Test-Path $envDir)) {
    Write-Host "[WARN]  Environment directory not found: $envDir" -ForegroundColor Yellow
    Write-Host "   Creating directory..." -ForegroundColor Yellow
    New-Item -ItemType Directory -Path $envDir -Force | Out-Null
}

# Create or update .env file
$envFile = Join-Path $envDir ".env"
$envContent = @()

# Read existing .env if it exists
if (Test-Path $envFile) {
    Write-Host "[PAGE] Reading existing .env file..." -ForegroundColor Cyan
    $existingLines = Get-Content $envFile
    
    # Keep non-auth related lines
    foreach ($line in $existingLines) {
        if ($line -notmatch "^(ENABLE_AUTHENTICATION|MICROSOFT_ENTRA)") {
            $envContent += $line
        }
    }
}

# Add authentication configuration
Write-Host "[EDIT]  Adding authentication configuration..." -ForegroundColor Cyan
$envContent += ""
$envContent += "# Backend API Authentication (Entra ID)"
$envContent += "ENABLE_AUTHENTICATION=true"
$envContent += "MICROSOFT_ENTRA_CLIENT_ID=$ClientId"
$envContent += "MICROSOFT_ENTRA_TENANT_ID=$TenantId"
$envContent += "MICROSOFT_ENTRA_CLIENT_SECRET=$ClientSecret"

# Write to file
$envContent | Set-Content -Path $envFile -Force
Write-Host "[OK] Authentication configuration saved to: $envFile" -ForegroundColor Green
Write-Host ""

# Also update azd environment
Write-Host "[TOOL] Setting azd environment variables..." -ForegroundColor Cyan
try {
    azd env set ENABLE_AUTHENTICATION true 2>&1 | Out-Null
    azd env set MICROSOFT_ENTRA_CLIENT_ID $ClientId 2>&1 | Out-Null
    azd env set MICROSOFT_ENTRA_TENANT_ID $TenantId 2>&1 | Out-Null
    azd env set MICROSOFT_ENTRA_CLIENT_SECRET $ClientSecret --no-prompt 2>&1 | Out-Null
    Write-Host "[OK] azd environment variables set" -ForegroundColor Green
} catch {
    Write-Host "[WARN]  Could not set azd environment variables (azd may not be configured)" -ForegroundColor Yellow
}

Write-Host ""
Write-Host "========================================" -ForegroundColor Green
Write-Host "[OK] Authentication Configuration Complete!" -ForegroundColor Green
Write-Host "========================================" -ForegroundColor Green
Write-Host ""

Write-Host "[NOTE] Next Steps:" -ForegroundColor Yellow
Write-Host "   1. Verify your App Registration is configured correctly:"
Write-Host "      - Redirect URI: https://earthcopilot-api.*.azurecontainerapps.io/.auth/login/aad/callback" -ForegroundColor Gray
Write-Host "      - API permissions: User.Read, email, openid, profile" -ForegroundColor Gray
Write-Host "      - Exposed API scope: api://$ClientId/access_as_user" -ForegroundColor Gray
Write-Host ""
Write-Host "   2. Deploy the backend to apply authentication:" -ForegroundColor Yellow
Write-Host "      cd earth-copilot" -ForegroundColor Cyan
Write-Host "      .\deploy-all.ps1 -Target 'backend'" -ForegroundColor Cyan
Write-Host ""

if ($DeployAfterConfig) {
    Write-Host "[LAUNCH] Deploying backend with authentication enabled..." -ForegroundColor Yellow
    Write-Host ""
    
    $deployScript = Join-Path $PSScriptRoot "deploy-all.ps1"
    if (Test-Path $deployScript) {
        & $deployScript -Target "backend"
    } else {
        Write-Host "[FAIL] ERROR: Deploy script not found: $deployScript" -ForegroundColor Red
        exit 1
    }
}

Write-Host ""
Write-Host "[LOCK] After deployment, your backend API will require Entra ID authentication!" -ForegroundColor Green
Write-Host ""
