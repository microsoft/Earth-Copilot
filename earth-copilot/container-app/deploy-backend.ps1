# Earth Copilot Backend Deployment Script
# Deploys the Container App (backend API) to Azure
# Auto-discovers resources from Azure subscription

param(
    [Parameter(Mandatory=$false)]
    [string]$ResourceGroup = "",
    
    [Parameter(Mandatory=$false)]
    [string]$ContainerAppName = "",
    
    [Parameter(Mandatory=$false)]
    [string]$Registry = "",
    
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

# ========================================
# AUTO-DISCOVER RESOURCES IF NOT PROVIDED
# ========================================
Write-Host ""
Write-Host "[Discovering Azure Resources]" -ForegroundColor Cyan

# Find resource group if not provided
if ([string]::IsNullOrEmpty($ResourceGroup)) {
    Write-Host "   Looking for Earth Copilot resource group..." -ForegroundColor Gray
    
    # Try to find resource group with earthcopilot in the name
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
        # Prefer the API container app if multiple exist
        $appList = $containerApps -split "`n"
        $apiApp = $appList | Where-Object { $_ -match "api" } | Select-Object -First 1
        if ($apiApp) {
            $ContainerAppName = $apiApp.Trim()
        } else {
            $ContainerAppName = $appList[0].Trim()
        }
        Write-Host "[OK] Found Container App: $ContainerAppName" -ForegroundColor Green
    } else {
        Write-Host "[ERROR] Could not find Container App in resource group '$ResourceGroup'." -ForegroundColor Red
        Write-Host "   Please specify -ContainerAppName parameter or deploy infrastructure first." -ForegroundColor Yellow
        exit 1
    }
} else {
    Write-Host "[OK] Using provided Container App: $ContainerAppName" -ForegroundColor Green
}

# Find Container Registry if not provided
if ([string]::IsNullOrEmpty($Registry)) {
    Write-Host "   Looking for Container Registry in $ResourceGroup..." -ForegroundColor Gray
    
    $registries = az acr list --resource-group $ResourceGroup --query "[].name" -o tsv 2>$null
    
    if ($registries) {
        $Registry = ($registries -split "`n")[0].Trim()
        Write-Host "[OK] Found Container Registry: $Registry" -ForegroundColor Green
    } else {
        Write-Host "[ERROR] Could not find Container Registry in resource group '$ResourceGroup'." -ForegroundColor Red
        Write-Host "   Please specify -Registry parameter or deploy infrastructure first." -ForegroundColor Yellow
        exit 1
    }
} else {
    Write-Host "[OK] Using provided Container Registry: $Registry" -ForegroundColor Green
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

# ======================================================================
# CRITICAL FIX: Save environment variables BEFORE updating the image
# Azure Container Apps resets env vars when updating the image directly
# ======================================================================
Write-Host "[Saving current environment variables...]" -ForegroundColor Yellow
$currentEnvJson = az containerapp show `
    --name $ContainerAppName `
    --resource-group $ResourceGroup `
    --query "properties.template.containers[0].env" `
    -o json 2>$null

$currentEnv = @{}
if ($currentEnvJson) {
    $envArray = $currentEnvJson | ConvertFrom-Json
    foreach ($env in $envArray) {
        if ($env.value) {
            $currentEnv[$env.name] = $env.value
        }
    }
}

# Extract critical values with defaults
$azureOpenAiEndpoint = if ($currentEnv["AZURE_OPENAI_ENDPOINT"]) { $currentEnv["AZURE_OPENAI_ENDPOINT"] } else { "" }
$useManagedIdentity = if ($currentEnv["USE_MANAGED_IDENTITY"] -eq "true") { "true" } else { "true" }

Write-Host "   AZURE_OPENAI_ENDPOINT: $azureOpenAiEndpoint" -ForegroundColor Gray
Write-Host "   USE_MANAGED_IDENTITY: $useManagedIdentity" -ForegroundColor Gray
Write-Host ""

try {
    # ======================================================================
    # CRITICAL FIX: Update image AND env vars in ONE atomic operation
    # This prevents 503 errors from race condition between image update
    # and env var restoration. Azure creates a single new revision with both.
    # ======================================================================
    Write-Host "[Updating Container App with image AND environment variables (atomic)]" -ForegroundColor Cyan
    
    # Get additional env vars to preserve
    $port = if ($currentEnv["PORT"]) { $currentEnv["PORT"] } else { "8080" }
    $stacUrl = if ($currentEnv["STAC_API_URL"]) { $currentEnv["STAC_API_URL"] } else { "https://planetarycomputer.microsoft.com/api/stac/v1" }
    $corsOrigins = if ($currentEnv["CORS_ORIGINS"]) { $currentEnv["CORS_ORIGINS"] } else { "*" }
    $appInsightsCs = if ($currentEnv["APPLICATION_INSIGHTS_CONNECTION_STRING"]) { $currentEnv["APPLICATION_INSIGHTS_CONNECTION_STRING"] } else { "" }
    $azureMapsKey = if ($currentEnv["AZURE_MAPS_SUBSCRIPTION_KEY"]) { $currentEnv["AZURE_MAPS_SUBSCRIPTION_KEY"] } else { "" }
    
    # Build env vars array - only include non-empty values
    $envVars = @(
        "PORT=$port",
        "STAC_API_URL=$stacUrl",
        "CORS_ORIGINS=$corsOrigins",
        "AZURE_OPENAI_ENDPOINT=$azureOpenAiEndpoint",
        "USE_MANAGED_IDENTITY=$useManagedIdentity"
    )
    
    if ($appInsightsCs) {
        $envVars += "APPLICATION_INSIGHTS_CONNECTION_STRING=$appInsightsCs"
    }
    if ($azureMapsKey) {
        $envVars += "AZURE_MAPS_SUBSCRIPTION_KEY=$azureMapsKey"
    }
    
    # Single atomic update: image + all env vars together
    az containerapp update `
        --name $ContainerAppName `
        --resource-group $ResourceGroup `
        --image "$Registry.azurecr.io/earthcopilot-api:$imageTag" `
        --set-env-vars @envVars `
        --output none
    
    if ($LASTEXITCODE -ne 0) {
        throw "Container App update failed"
    }
    
    Write-Host "[OK] Image and environment variables updated atomically" -ForegroundColor Green
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
