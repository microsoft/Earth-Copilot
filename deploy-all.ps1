# Earth Copilot Master Deployment Script
# Deploys both backend (Container App) and frontend (App Service) to Azure

param(
    [Parameter(Mandatory=$false)]
    [string]$ResourceGroup = "earthcopilot-rg",
    
    [Parameter(Mandatory=$false)]
    [string]$ContainerAppName = "earthcopilot-api",
    
    [Parameter(Mandatory=$false)]
    [string]$AppServiceName = "earthcopilot-web-ui",
    
    [Parameter(Mandatory=$false)]
    [string]$Registry = "earthcopilotregistry",
    
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

Write-Host " Deployment Configuration:" -ForegroundColor Yellow
Write-Host "   Target: $Target" -ForegroundColor Gray
Write-Host "   Resource Group: $ResourceGroup" -ForegroundColor Gray
Write-Host "   Backend: $ContainerAppName [Container App]" -ForegroundColor Gray
Write-Host "   Frontend: $AppServiceName [App Service]" -ForegroundColor Gray
Write-Host "   Registry: $Registry.azurecr.io" -ForegroundColor Gray
Write-Host ""
Write-Host "⏱️  Started at: $(Get-Date -Format 'HH:mm:ss')" -ForegroundColor Gray
Write-Host ""

# Determine what to deploy based on Target and Skip flags
$deployBackend = ($Target -eq "both" -or $Target -eq "backend") -and -not $SkipBackend
$deployFrontend = ($Target -eq "both" -or $Target -eq "frontend") -and -not $SkipFrontend

if (-not $deployBackend -and -not $deployFrontend) {
    Write-Host "⚠️  Nothing to deploy! Both backend and frontend are skipped." -ForegroundColor Yellow
    exit 0
}

Write-Host " Deployment Plan:" -ForegroundColor Cyan
if ($deployBackend) {
    Write-Host "   ✓ Backend [Container App]" -ForegroundColor Green
} else {
    Write-Host "   ✗ Backend [skipped]" -ForegroundColor Gray
}
if ($deployFrontend) {
    Write-Host "   ✓ Frontend [App Service]" -ForegroundColor Green
} else {
    Write-Host "   ✗ Frontend [skipped]" -ForegroundColor Gray
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
        Write-Host "❌ Backend deployment script not found: $backendScript" -ForegroundColor Red
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
            Write-Host "[$(Get-Date -Format 'HH:mm:ss')] ✅ Backend deployment completed successfully" -ForegroundColor Green
        } else {
            throw "Backend deployment returned non-zero exit code: $LASTEXITCODE"
        }
        
    } catch {
        Write-Host ""
        Write-Host "[$(Get-Date -Format 'HH:mm:ss')] ❌ Backend deployment failed: $_" -ForegroundColor Red
        Write-Host ""
        
        if ($Target -eq "both") {
            Write-Host "[$(Get-Date -Format 'HH:mm:ss')] ⚠️  Continuing with frontend deployment despite backend failure..." -ForegroundColor Yellow
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
        Write-Host "❌ Frontend deployment script not found: $frontendScript" -ForegroundColor Red
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
            Write-Host "[$(Get-Date -Format 'HH:mm:ss')] ✅ Frontend deployment completed successfully" -ForegroundColor Green
        } else {
            throw "Frontend deployment returned non-zero exit code: $LASTEXITCODE"
        }
        
    } catch {
        Write-Host ""
        Write-Host "[$(Get-Date -Format 'HH:mm:ss')] ❌ Frontend deployment failed: $_" -ForegroundColor Red
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
Write-Host "⏱️  Started:  $(Get-Date $startTime -Format 'HH:mm:ss')" -ForegroundColor Gray
Write-Host "⏱️  Finished: $(Get-Date $endTime -Format 'HH:mm:ss')" -ForegroundColor Gray
Write-Host "⏱️  Duration: $durationStr" -ForegroundColor Gray
Write-Host ""

if ($deployBackend) {
    if ($backendSuccess) {
        Write-Host "✅ Backend: DEPLOYED" -ForegroundColor Green
        
        try {
            $appDetails = az containerapp show `
                --name $ContainerAppName `
                --resource-group $ResourceGroup `
                --output json | ConvertFrom-Json
            
            $fqdn = $appDetails.properties.configuration.ingress.fqdn
            Write-Host "    URL: https://$fqdn" -ForegroundColor Cyan
            Write-Host "    Revision: $($appDetails.properties.latestRevisionName)" -ForegroundColor Gray
        } catch {
            Write-Host "   ⚠️  Could not retrieve backend URL" -ForegroundColor Yellow
        }
    } else {
        Write-Host "❌ Backend: FAILED" -ForegroundColor Red
    }
    Write-Host ""
}

if ($deployFrontend) {
    if ($frontendSuccess) {
        Write-Host "✅ Frontend: DEPLOYED" -ForegroundColor Green
        
        try {
            $appService = az webapp show `
                --name $AppServiceName `
                --resource-group $ResourceGroup `
                --output json | ConvertFrom-Json
            
            Write-Host "    URL: https://$($appService.defaultHostName)" -ForegroundColor Cyan
        } catch {
            Write-Host "   ⚠️  Could not retrieve frontend URL" -ForegroundColor Yellow
        }
    } else {
        Write-Host "❌ Frontend: FAILED" -ForegroundColor Red
    }
    Write-Host ""
}

Write-Host "============================================" -ForegroundColor Magenta

# Exit with appropriate code
if (($deployBackend -and -not $backendSuccess) -or ($deployFrontend -and -not $frontendSuccess)) {
    Write-Host ""
    Write-Host "⚠️  Some deployments failed. Please review the output above." -ForegroundColor Yellow
    exit 1
} else {
    Write-Host ""
    Write-Host " All deployments completed successfully!" -ForegroundColor Green
    exit 0
}
