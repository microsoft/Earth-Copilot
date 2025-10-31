# Earth Copilot Backend Deployment Script
# Deploys the Container App (backend API) to Azure

param(
    [Parameter(Mandatory=$false)]
    [string]$ResourceGroup = "earthcopilot-rg",
    
    [Parameter(Mandatory=$false)]
    [string]$ContainerAppName = "earthcopilot-api",
    
    [Parameter(Mandatory=$false)]
    [string]$Registry = "earthcopilotregistry",
    
    [Parameter(Mandatory=$false)]
    [switch]$SkipBuild = $false,
    
    [Parameter(Mandatory=$false)]
    [switch]$ShowDetails = $false
)

$ErrorActionPreference = "Stop"

Write-Host "========================================" -ForegroundColor Cyan
Write-Host "EARTH COPILOT BACKEND DEPLOYMENT" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""

# Get script directory (container-app folder)
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$ProjectRoot = Split-Path -Parent $ScriptDir  # earth-copilot folder
$RepoRoot = Split-Path -Parent $ProjectRoot   # repository root

Write-Host "[Directories]" -ForegroundColor Yellow
Write-Host "   Script:  $ScriptDir" -ForegroundColor Gray
Write-Host "   Project: $ProjectRoot" -ForegroundColor Gray
Write-Host "   Repo:    $RepoRoot" -ForegroundColor Gray
Write-Host ""

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

if (-not $SkipBuild) {
    # Build and push Docker image
    Write-Host ""
    Write-Host "[Building Docker image]" -ForegroundColor Cyan
    Write-Host "   Registry: $Registry.azurecr.io" -ForegroundColor Gray
    Write-Host "   Image: earthcopilot-api" -ForegroundColor Gray
    Write-Host ""
    
    $timestamp = Get-Date -Format "yyyyMMddHHmmss"
    $imageTag = $timestamp
    
    Write-Host "========================================" -ForegroundColor Cyan
    Write-Host "STEP 1/3: BUILDING DOCKER IMAGE IN AZURE" -ForegroundColor Cyan
    Write-Host "========================================" -ForegroundColor Cyan
    Write-Host "[Building image with tag: $imageTag]" -ForegroundColor Yellow
    Write-Host "[NOTE] This will take 3-5 minutes. Progress updates every 15 seconds..." -ForegroundColor Yellow
    Write-Host ""
    
    # Change to repository root for correct build context
    Push-Location $RepoRoot
    
    try {
        # Start build with --no-wait to avoid interactive prompts
        Write-Host "[Starting ACR build...]" -ForegroundColor Cyan
        az acr build `
            --registry $Registry `
            --image "earthcopilot-api:$imageTag" `
            --image "earthcopilot-api:latest" `
            --file "earth-copilot/container-app/Dockerfile.complete" `
            --no-wait `
            earth-copilot/
        
        if ($LASTEXITCODE -ne 0) {
            throw "ACR build start failed"
        }
        
        Write-Host "[OK] Build started in Azure Container Registry" -ForegroundColor Green
        Write-Host ""
        
        # Poll for completion
        Write-Host "[Monitoring build progress...]" -ForegroundColor Cyan
        $maxWaitSeconds = 600  # 10 minutes max
        $elapsedSeconds = 0
        $buildComplete = $false
        
        while ($elapsedSeconds -lt $maxWaitSeconds) {
            Start-Sleep -Seconds 15
            $elapsedSeconds += 15
            
            # Get latest build run
            $runs = az acr task list-runs --registry $Registry --top 1 --output json | ConvertFrom-Json
            $latestRun = $runs[0]
            
            $status = $latestRun.status
            $runId = $latestRun.runId
            
            $minutes = [math]::Floor($elapsedSeconds / 60)
            $seconds = $elapsedSeconds % 60
            
            if ($status -eq "Succeeded") {
                Write-Host "[OK] Build completed successfully! (Run: $runId, Time: ${minutes}m ${seconds}s)" -ForegroundColor Green
                $buildComplete = $true
                break
            } elseif ($status -eq "Failed") {
                throw "Build failed (Run: $runId)"
            } elseif ($status -eq "Running") {
                Write-Host "[${minutes}m ${seconds}s] Build in progress... (Run: $runId)" -ForegroundColor Yellow
            } else {
                Write-Host "[${minutes}m ${seconds}s] Build status: $status (Run: $runId)" -ForegroundColor Gray
            }
        }
        
        if (-not $buildComplete) {
            throw "Build timed out after $maxWaitSeconds seconds"
        }
        
        Write-Host ""
        
    } catch {
        Write-Host "[ERROR] Build failed: $_" -ForegroundColor Red
        Pop-Location
        exit 1
    } finally {
        Pop-Location
    }
} else {
    Write-Host ""
    Write-Host "[SKIP] Skipping build (using existing latest tag)" -ForegroundColor Yellow
    $imageTag = "latest"
}

# Deploy to Container App
Write-Host "========================================" -ForegroundColor Cyan
Write-Host "STEP 2/3: DEPLOYING TO CONTAINER APP" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
Write-Host "   Resource Group: $ResourceGroup" -ForegroundColor Gray
Write-Host "   Container App: $ContainerAppName" -ForegroundColor Gray
Write-Host "   Image Tag: $imageTag" -ForegroundColor Gray
Write-Host ""

try {
    Write-Host "[Updating Container App with new image...]" -ForegroundColor Cyan
    az containerapp update `
        --name $ContainerAppName `
        --resource-group $ResourceGroup `
        --image "$Registry.azurecr.io/earthcopilot-api:$imageTag" `
        --output none
    
    if ($LASTEXITCODE -ne 0) {
        throw "Container App update failed"
    }
    
    Write-Host "[OK] Deployment initiated successfully" -ForegroundColor Green
    
} catch {
    Write-Host "[ERROR] Deployment failed: $_" -ForegroundColor Red
    exit 1
}

# Wait for deployment to stabilize
Write-Host ""
Write-Host "========================================" -ForegroundColor Cyan
Write-Host "STEP 3/3: VERIFYING DEPLOYMENT" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
Write-Host "[Waiting for deployment to stabilize (30 seconds)]" -ForegroundColor Yellow
Start-Sleep -Seconds 30

# Get Container App details
Write-Host ""
Write-Host "[Container App Status]" -ForegroundColor Cyan
try {
    $appDetails = az containerapp show `
        --name $ContainerAppName `
        --resource-group $ResourceGroup `
        --output json | ConvertFrom-Json
    
    $fqdn = $appDetails.properties.configuration.ingress.fqdn
    $status = $appDetails.properties.runningStatus
    $latestRevision = $appDetails.properties.latestRevisionName
    
    Write-Host "   Status: $status" -ForegroundColor $(if ($status -eq "Running") { "Green" } else { "Yellow" })
    Write-Host "   Latest Revision: $latestRevision" -ForegroundColor Gray
    Write-Host "   URL: https://$fqdn" -ForegroundColor Gray
    
    # Health check
    Write-Host ""
    Write-Host "[Performing health check]" -ForegroundColor Cyan
    try {
        $response = Invoke-WebRequest -Uri "https://$fqdn/api/health" -Method GET -UseBasicParsing -ErrorAction Stop
        if ($response.StatusCode -eq 200) {
            Write-Host "[OK] Health check PASSED - API is responding" -ForegroundColor Green
        } else {
            Write-Host "[WARN] Health check returned status: $($response.StatusCode)" -ForegroundColor Yellow
        }
    } catch {
        Write-Host "[WARN] Health check failed - API may still be starting up" -ForegroundColor Yellow
        Write-Host "   Error: $_" -ForegroundColor Gray
    }
    
} catch {
    Write-Host "[WARN] Could not retrieve Container App details" -ForegroundColor Yellow
}

Write-Host ""
Write-Host "========================================" -ForegroundColor Green
Write-Host "BACKEND DEPLOYMENT COMPLETE!" -ForegroundColor Green
Write-Host "========================================" -ForegroundColor Green
Write-Host ""
Write-Host "Backend API URL: https://$fqdn" -ForegroundColor Cyan
Write-Host "View logs: az containerapp logs show --name $ContainerAppName --resource-group $ResourceGroup --follow" -ForegroundColor Gray
Write-Host ""
