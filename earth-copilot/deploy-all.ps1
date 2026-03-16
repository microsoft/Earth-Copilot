# Earth Copilot Master Deployment Script
# Deploys both backend (Container App) and frontend (App Service) to Azure
# Auto-discovers resources from Azure subscription

param(
    [Parameter(Mandatory=$false)]
    [string]$ResourceGroup = "",
    
    [Parameter(Mandatory=$false)]
    [string]$ContainerAppName = "",
    
    [Parameter(Mandatory=$false)]
    [string]$AppServiceName = "",
    
    [Parameter(Mandatory=$false)]
    [string]$Registry = "",
    
    [Parameter(Mandatory=$false)]
    [ValidateSet("both", "backend", "frontend")]
    [string]$Target = "both",
    
    [Parameter(Mandatory=$false)]
    [switch]$SkipBuild = $false,
    
    [Parameter(Mandatory=$false)]
    [switch]$SkipBackend = $false,
    
    [Parameter(Mandatory=$false)]
    [switch]$SkipFrontend = $false,
    
    [Parameter(Mandatory=$false)]
    [switch]$ShowDetails = $false
)

$ErrorActionPreference = "Stop"
$ProgressPreference = "Continue"

Write-Host ""
Write-Host "============================================" -ForegroundColor Magenta
Write-Host " EARTH COPILOT MASTER DEPLOYMENT SCRIPT" -ForegroundColor Magenta
Write-Host "============================================" -ForegroundColor Magenta
Write-Host ""

# Get script directory
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$BackendDir = Join-Path $ScriptDir "container-app"
$FrontendDir = Join-Path $ScriptDir "web-ui"

# Check Azure CLI
Write-Host "[Checking Azure CLI]" -ForegroundColor Cyan
try {
    $azVersion = az version --output json | ConvertFrom-Json
    Write-Host "[OK] Azure CLI version: $($azVersion.'azure-cli')" -ForegroundColor Green
} catch {
    Write-Host "[ERROR] Azure CLI not found. Please install from https://aka.ms/installazurecliwindows" -ForegroundColor Red
    exit 1
}

# Check if logged in to Azure
Write-Host "[Checking Azure login]" -ForegroundColor Cyan
try {
    $account = az account show 2>$null | ConvertFrom-Json
    Write-Host "[OK] Logged in as: $($account.user.name)" -ForegroundColor Green
    Write-Host "   Subscription: $($account.name)" -ForegroundColor Gray
} catch {
    Write-Host "[ERROR] Not logged in to Azure. Running 'az login'..." -ForegroundColor Yellow
    az login
}

# ========================================
# AUTO-DISCOVER RESOURCES IF NOT PROVIDED
# ========================================
Write-Host ""
Write-Host "[Discovering Azure Resources]" -ForegroundColor Cyan

# Find resource group if not provided
if ([string]::IsNullOrEmpty($ResourceGroup)) {
    Write-Host "   Looking for Earth Copilot resource group..." -ForegroundColor Gray
    
    $groups = az group list --query "[?contains(name, 'earthcopilot') || contains(name, 'earth-copilot')].name" -o tsv 2>$null
    
    if ($groups) {
        $ResourceGroup = ($groups -split "`n")[0].Trim()
        Write-Host "[OK] Found resource group: $ResourceGroup" -ForegroundColor Green
    } else {
        Write-Host "[ERROR] Could not find Earth Copilot resource group." -ForegroundColor Red
        Write-Host "   Please specify -ResourceGroup parameter or create infrastructure first." -ForegroundColor Yellow
        exit 1
    }
} else {
    Write-Host "[OK] Using provided resource group: $ResourceGroup" -ForegroundColor Green
}

# Find Container App if not provided
if ([string]::IsNullOrEmpty($ContainerAppName)) {
    Write-Host "   Looking for Container App in $ResourceGroup..." -ForegroundColor Gray
    
    $containerApps = az containerapp list --resource-group $ResourceGroup --query "[].name" -o tsv 2>$null
    
    if ($containerApps) {
        $appList = $containerApps -split "`n"
        $apiApp = $appList | Where-Object { $_ -match "api" } | Select-Object -First 1
        if ($apiApp) {
            $ContainerAppName = $apiApp.Trim()
        } else {
            $ContainerAppName = $appList[0].Trim()
        }
        Write-Host "[OK] Found Container App: $ContainerAppName" -ForegroundColor Green
    } else {
        Write-Host "[WARN] Could not find Container App in resource group '$ResourceGroup'." -ForegroundColor Yellow
        if ($Target -eq "backend" -or $Target -eq "both") {
            Write-Host "   Backend deployment will fail without Container App." -ForegroundColor Yellow
        }
    }
} else {
    Write-Host "[OK] Using provided Container App: $ContainerAppName" -ForegroundColor Green
}

# Find App Service if not provided
if ([string]::IsNullOrEmpty($AppServiceName)) {
    Write-Host "   Looking for App Service in $ResourceGroup..." -ForegroundColor Gray
    
    $appServices = az webapp list --resource-group $ResourceGroup --query "[].name" -o tsv 2>$null
    
    if ($appServices) {
        $AppServiceName = ($appServices -split "`n")[0].Trim()
        Write-Host "[OK] Found App Service: $AppServiceName" -ForegroundColor Green
    } else {
        Write-Host "[WARN] Could not find App Service in resource group '$ResourceGroup'." -ForegroundColor Yellow
        if ($Target -eq "frontend" -or $Target -eq "both") {
            Write-Host "   Frontend deployment will fail without App Service." -ForegroundColor Yellow
        }
    }
} else {
    Write-Host "[OK] Using provided App Service: $AppServiceName" -ForegroundColor Green
}

# Find Container Registry if not provided
if ([string]::IsNullOrEmpty($Registry)) {
    Write-Host "   Looking for Container Registry in $ResourceGroup..." -ForegroundColor Gray
    
    $registries = az acr list --resource-group $ResourceGroup --query "[].name" -o tsv 2>$null
    
    if ($registries) {
        $Registry = ($registries -split "`n")[0].Trim()
        Write-Host "[OK] Found Container Registry: $Registry" -ForegroundColor Green
    } else {
        Write-Host "[WARN] Could not find Container Registry in resource group '$ResourceGroup'." -ForegroundColor Yellow
        if ($Target -eq "backend" -or $Target -eq "both") {
            Write-Host "   Backend deployment will fail without Container Registry." -ForegroundColor Yellow
        }
    }
} else {
    Write-Host "[OK] Using provided Container Registry: $Registry" -ForegroundColor Green
}

Write-Host ""
Write-Host " Deployment Configuration:" -ForegroundColor Yellow
Write-Host "   Target: $Target" -ForegroundColor Gray
Write-Host "   Resource Group: $ResourceGroup" -ForegroundColor Gray
Write-Host "   Backend: $ContainerAppName [Container App]" -ForegroundColor Gray
Write-Host "   Frontend: $AppServiceName [App Service]" -ForegroundColor Gray
Write-Host "   Registry: $Registry.azurecr.io" -ForegroundColor Gray
Write-Host ""
Write-Host "[TIME]  Started at: $(Get-Date -Format 'HH:mm:ss')" -ForegroundColor Gray
Write-Host ""

# Determine what to deploy based on Target and Skip flags
$deployBackend = ($Target -eq "both" -or $Target -eq "backend") -and -not $SkipBackend
$deployFrontend = ($Target -eq "both" -or $Target -eq "frontend") -and -not $SkipFrontend

if (-not $deployBackend -and -not $deployFrontend) {
    Write-Host "[WARN]  Nothing to deploy! Both backend and frontend are skipped." -ForegroundColor Yellow
    exit 0
}

Write-Host " Deployment Plan:" -ForegroundColor Cyan
if ($deployBackend) {
    Write-Host "   [OK] Backend [Container App]" -ForegroundColor Green
} else {
    Write-Host "   [FAIL] Backend [skipped]" -ForegroundColor Gray
}
if ($deployFrontend) {
    Write-Host "   [OK] Frontend [App Service]" -ForegroundColor Green
} else {
    Write-Host "   [FAIL] Frontend [skipped]" -ForegroundColor Gray
}
Write-Host ""

# Track deployment results
$backendSuccess = $false
$frontendSuccess = $false
$startTime = Get-Date

# Deploy Backend
if ($deployBackend) {
    Write-Host ""
    Write-Host "============================================" -ForegroundColor Cyan
    Write-Host " DEPLOYING BACKEND" -ForegroundColor Cyan
    Write-Host "============================================" -ForegroundColor Cyan
    Write-Host ""
    
    $backendScript = Join-Path $BackendDir "deploy-backend.ps1"
    
    if (-not (Test-Path $backendScript)) {
        Write-Host "[FAIL] Backend deployment script not found: $backendScript" -ForegroundColor Red
        exit 1
    }
    
    try {
        $params = @{
            ResourceGroup = $ResourceGroup
            ContainerAppName = $ContainerAppName
            Registry = $Registry
        }
        
        if ($SkipBuild) {
            $params.Add("SkipBuild", $true)
        }
        
        if ($ShowDetails) {
            $params.Add("ShowDetails", $true)
        }
        
        Write-Host "[$(Get-Date -Format 'HH:mm:ss')] Starting backend deployment..." -ForegroundColor Cyan
        & $backendScript @params
        
        if ($LASTEXITCODE -eq 0) {
            $backendSuccess = $true
            Write-Host ""
            Write-Host "[$(Get-Date -Format 'HH:mm:ss')] [OK] Backend deployment completed successfully" -ForegroundColor Green
        } else {
            throw "Backend deployment returned non-zero exit code: $LASTEXITCODE"
        }
        
    } catch {
        Write-Host ""
        Write-Host "[$(Get-Date -Format 'HH:mm:ss')] [FAIL] Backend deployment failed: $_" -ForegroundColor Red
        Write-Host ""
        
        if ($Target -eq "both") {
            Write-Host "[$(Get-Date -Format 'HH:mm:ss')] [WARN]  Continuing with frontend deployment despite backend failure..." -ForegroundColor Yellow
        } else {
            exit 1
        }
    }
}

# Deploy Frontend
if ($deployFrontend) {
    Write-Host ""
    Write-Host "============================================" -ForegroundColor Cyan
    Write-Host " DEPLOYING FRONTEND" -ForegroundColor Cyan
    Write-Host "============================================" -ForegroundColor Cyan
    Write-Host ""
    
    $frontendScript = Join-Path $FrontendDir "deploy-frontend.ps1"
    
    if (-not (Test-Path $frontendScript)) {
        Write-Host "[FAIL] Frontend deployment script not found: $frontendScript" -ForegroundColor Red
        exit 1
    }
    
    try {
        $params = @{
            ResourceGroup = $ResourceGroup
            AppServiceName = $AppServiceName
        }
        
        if ($SkipBuild) {
            $params.Add("SkipBuild", $true)
        }
        
        if ($ShowDetails) {
            $params.Add("ShowDetails", $true)
        }
        
        Write-Host "[$(Get-Date -Format 'HH:mm:ss')] Starting frontend deployment..." -ForegroundColor Cyan
        & $frontendScript @params
        
        if ($LASTEXITCODE -eq 0) {
            $frontendSuccess = $true
            Write-Host ""
            Write-Host "[$(Get-Date -Format 'HH:mm:ss')] [OK] Frontend deployment completed successfully" -ForegroundColor Green
        } else {
            throw "Frontend deployment returned non-zero exit code: $LASTEXITCODE"
        }
        
    } catch {
        Write-Host ""
        Write-Host "[$(Get-Date -Format 'HH:mm:ss')] [FAIL] Frontend deployment failed: $_" -ForegroundColor Red
        Write-Host ""
        
        if (-not $backendSuccess) {
            exit 1
        }
    }
}

# Calculate deployment time
$endTime = Get-Date
$duration = $endTime - $startTime
$durationStr = "{0:mm}m {0:ss}s" -f $duration

# Final Summary
Write-Host ""
Write-Host "============================================" -ForegroundColor Magenta
Write-Host " DEPLOYMENT SUMMARY" -ForegroundColor Magenta
Write-Host "============================================" -ForegroundColor Magenta
Write-Host ""
Write-Host "[TIME]  Started:  $(Get-Date $startTime -Format 'HH:mm:ss')" -ForegroundColor Gray
Write-Host "[TIME]  Finished: $(Get-Date $endTime -Format 'HH:mm:ss')" -ForegroundColor Gray
Write-Host "[TIME]  Duration: $durationStr" -ForegroundColor Gray
Write-Host ""

if ($deployBackend) {
    if ($backendSuccess) {
        Write-Host "[OK] Backend: DEPLOYED" -ForegroundColor Green
        
        try {
            $appDetails = az containerapp show `
                --name $ContainerAppName `
                --resource-group $ResourceGroup `
                --output json | ConvertFrom-Json
            
            $fqdn = $appDetails.properties.configuration.ingress.fqdn
            Write-Host "    URL: https://$fqdn" -ForegroundColor Cyan
            Write-Host "    Revision: $($appDetails.properties.latestRevisionName)" -ForegroundColor Gray
        } catch {
            Write-Host "   [WARN]  Could not retrieve backend URL" -ForegroundColor Yellow
        }
    } else {
        Write-Host "[FAIL] Backend: FAILED" -ForegroundColor Red
    }
    Write-Host ""
}

if ($deployFrontend) {
    if ($frontendSuccess) {
        Write-Host "[OK] Frontend: DEPLOYED" -ForegroundColor Green
        
        try {
            $appService = az webapp show `
                --name $AppServiceName `
                --resource-group $ResourceGroup `
                --output json | ConvertFrom-Json
            
            Write-Host "    URL: https://$($appService.defaultHostName)" -ForegroundColor Cyan
        } catch {
            Write-Host "   [WARN]  Could not retrieve frontend URL" -ForegroundColor Yellow
        }
    } else {
        Write-Host "[FAIL] Frontend: FAILED" -ForegroundColor Red
    }
    Write-Host ""
}

Write-Host "============================================" -ForegroundColor Magenta

# Exit with appropriate code
if (($deployBackend -and -not $backendSuccess) -or ($deployFrontend -and -not $frontendSuccess)) {
    Write-Host ""
    Write-Host "[WARN]  Some deployments failed. Please review the output above." -ForegroundColor Yellow
    exit 1
} else {
    Write-Host ""
    Write-Host " All deployments completed successfully!" -ForegroundColor Green
    exit 0
}
