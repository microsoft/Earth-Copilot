# Deployment Script with Detailed Logging
param(
    [string]$ResourceGroup = "earthcopilot-rg",
    [string]$AcrName = "earthcopilotregistry",
    [string]$ContainerAppName = "earth-copilot-mcp",
    [string]$EnvironmentName = "earthcopilot-env-vnet",
    [string]$Location = "canadacentral"
)

$ErrorActionPreference = "Stop"

function Write-Step {
    param([string]$Message, [string]$Status = "Info")
    $timestamp = Get-Date -Format "HH:mm:ss"
    switch ($Status) {
        "Start" { Write-Host "[$timestamp] >> $Message" -ForegroundColor Cyan }
        "Success" { Write-Host "[$timestamp] OK $Message" -ForegroundColor Green }
        "Error" { Write-Host "[$timestamp] ERROR $Message" -ForegroundColor Red }
        "Warning" { Write-Host "[$timestamp] WARN $Message" -ForegroundColor Yellow }
        default { Write-Host "[$timestamp] INFO $Message" -ForegroundColor Gray }
    }
}

Write-Host "`n╔════════════════════════════════════════════════════════╗" -ForegroundColor Cyan
Write-Host "║  Earth Copilot MCP Server - Azure Deployment          ║" -ForegroundColor Cyan
Write-Host "╚════════════════════════════════════════════════════════╝`n" -ForegroundColor Cyan

Write-Step "Configuration:" "Info"
Write-Host "  Resource Group: $ResourceGroup"
Write-Host "  ACR: $AcrName"
Write-Host "  Container App: $ContainerAppName"
Write-Host "  Environment: $EnvironmentName"
Write-Host "  Location: $Location`n"

try {
    # Step 1: Azure Authentication
    Write-Step "Checking Azure authentication..." "Start"
    $account = az account show --output json 2>$null | ConvertFrom-Json
    if (-not $account) {
        Write-Step "Not authenticated. Please run 'az login'" "Error"
        exit 1
    }
    Write-Step "Authenticated as: $($account.user.name)" "Success"
    Write-Host "  Subscription: $($account.name)`n" -ForegroundColor Gray

    # Step 2: Verify Resource Group
    Write-Step "Verifying resource group..." "Start"
    $rgExists = az group exists --name $ResourceGroup
    if ($rgExists -eq "false") {
        Write-Step "Resource group '$ResourceGroup' not found!" "Error"
        exit 1
    }
    Write-Step "Resource group exists" "Success"

    # Step 3: Verify ACR
    Write-Step "Verifying Azure Container Registry..." "Start"
    $acr = az acr show --name $AcrName --resource-group $ResourceGroup 2>$null | ConvertFrom-Json
    if (-not $acr) {
        Write-Step "ACR '$AcrName' not found!" "Error"
        exit 1
    }
    Write-Step "ACR found: $($acr.loginServer)" "Success"

    # Step 4: Build Docker Image
    Write-Step "Building Docker image..." "Start"
    Write-Host "  Image: earth-copilot-mcp:latest" -ForegroundColor Gray
    Write-Host "  This will take 2-3 minutes...`n" -ForegroundColor Yellow
    
    $buildOutput = az acr build `
        --registry $AcrName `
        --image "earth-copilot-mcp:latest" `
        --file Dockerfile `
        . `
        2>&1
    
    if ($LASTEXITCODE -eq 0) {
        Write-Step "Image built and pushed successfully" "Success"
        
        # Get the build run ID from output
        $runId = ($buildOutput | Select-String "Run ID: (\w+)" | ForEach-Object { $_.Matches.Groups[1].Value })
        if ($runId) {
            Write-Host "  Build Run ID: $runId`n" -ForegroundColor Gray
        }
    } else {
        Write-Step "Image build failed!" "Error"
        Write-Host "`nBuild output:" -ForegroundColor Yellow
        Write-Host $buildOutput
        exit 1
    }

    # Step 5: Get ACR Credentials
    Write-Step "Retrieving ACR credentials..." "Start"
    $acrServer = az acr show --name $AcrName --query loginServer -o tsv
    $acrUsername = az acr credential show --name $AcrName --query username -o tsv
    $acrPassword = az acr credential show --name $AcrName --query "passwords[0].value" -o tsv
    Write-Step "Credentials retrieved" "Success"

    # Step 6: Verify Container Apps Environment
    Write-Step "Verifying Container Apps environment..." "Start"
    $env = az containerapp env show --name $EnvironmentName --resource-group $ResourceGroup 2>$null | ConvertFrom-Json
    if (-not $env) {
        Write-Step "Environment '$EnvironmentName' not found!" "Error"
        exit 1
    }
    Write-Step "Environment exists" "Success"

    # Step 7: Deploy/Update Container App
    Write-Step "Deploying Container App..." "Start"
    
    $appExists = az containerapp show --name $ContainerAppName --resource-group $ResourceGroup 2>$null
    
    if (-not $appExists) {
        Write-Host "  Creating new container app..." -ForegroundColor Gray
        
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
            --env-vars "MCP_SERVER_MODE=production" "EARTH_COPILOT_BASE_URL=http://localhost:8000" "GEOINT_SERVICE_URL=http://localhost:8001" `
            --cpu 0.5 `
            --memory 1.0Gi `
            --min-replicas 1 `
            --max-replicas 3 `
            --output none
    } else {
        Write-Host "  Updating existing container app..." -ForegroundColor Gray
        
        az containerapp update `
            --name $ContainerAppName `
            --resource-group $ResourceGroup `
            --image "${acrServer}/earth-copilot-mcp:latest" `
            --output none
    }
    
    if ($LASTEXITCODE -eq 0) {
        Write-Step "Container App deployed successfully" "Success"
    } else {
        Write-Step "Container App deployment failed!" "Error"
        exit 1
    }

    # Step 8: Get Endpoint URL
    Write-Step "Retrieving endpoint URL..." "Start"
    $mcpUrl = az containerapp show `
        --name $ContainerAppName `
        --resource-group $ResourceGroup `
        --query properties.configuration.ingress.fqdn `
        -o tsv
    
    $mcpUrl = "https://$mcpUrl"
    Write-Step "Endpoint URL retrieved" "Success"

    # Step 9: Test Deployment
    Write-Step "Testing deployment..." "Start"
    Start-Sleep -Seconds 5
    
    try {
        $response = Invoke-WebRequest -Uri "$mcpUrl/" -Method GET -TimeoutSec 10 -ErrorAction SilentlyContinue
        if ($response.StatusCode -eq 200) {
            Write-Step "Health check passed!" "Success"
        } else {
            Write-Step "Health check returned status: $($response.StatusCode)" "Warning"
        }
    } catch {
        Write-Step "Health check failed (server may still be starting)" "Warning"
        Write-Host "  Wait 30 seconds and try: $mcpUrl`n" -ForegroundColor Gray
    }

    # Success Summary
    Write-Host "`n╔════════════════════════════════════════════════════════╗" -ForegroundColor Green
    Write-Host "║  ✅ DEPLOYMENT SUCCESSFUL!                            ║" -ForegroundColor Green
    Write-Host "╚════════════════════════════════════════════════════════╝`n" -ForegroundColor Green

    Write-Host "🌐 MCP Server URL: $mcpUrl`n" -ForegroundColor Cyan

    Write-Host "📊 Next Steps:" -ForegroundColor Yellow
    Write-Host "  1. Test health: curl $mcpUrl/"
    Write-Host "  2. View API docs: $mcpUrl/docs"
    Write-Host "  3. Run tests: python test_deployed_mcp.py $mcpUrl"
    Write-Host "  4. View logs: az containerapp logs show --name $ContainerAppName --resource-group $ResourceGroup --follow"
    Write-Host ""

    # Save deployment info
    @{
        timestamp = (Get-Date -Format "yyyy-MM-dd HH:mm:ss")
        resourceGroup = $ResourceGroup
        containerApp = $ContainerAppName
        mcpUrl = $mcpUrl
        acrServer = $acrServer
        environment = $EnvironmentName
    } | ConvertTo-Json | Out-File "deployment-info.json" -Encoding UTF8

    Write-Host "Deployment info saved to: deployment-info.json`n" -ForegroundColor Gray

} catch {
    Write-Step "Deployment failed with error:" "Error"
    Write-Host $_.Exception.Message -ForegroundColor Red
    Write-Host $_.ScriptStackTrace -ForegroundColor Gray
    exit 1
}
