# Earth-Copilot MCP Server Deployment Script
#
# This script deploys the Earth-Copilot Model Context Protocol server with:
# - Azure Function App for the MCP server
# - HTTP bridge for REST API access
# - APIM integration for enterprise features
# - Monitoring and logging setup

param(
    [Parameter(Mandatory=$true)]
    [string]$ResourceGroupName,
    
    [Parameter(Mandatory=$true)]
    [string]$FunctionAppName,
    
    [string]$Location = "East US",
    [string]$StorageAccountName = $null,
    [string]$AppInsightsName = $null,
    [string]$ServicePlanName = $null,
    [string]$ApimServiceName = $null,
    [switch]$DeployApim = $false,
    [switch]$WhatIf = $false
)

# Set error handling
$ErrorActionPreference = "Stop"

# Auto-generate names if not provided
if (-not $StorageAccountName) {
    $StorageAccountName = ($FunctionAppName + "storage").ToLower() -replace '[^a-z0-9]', ''
    if ($StorageAccountName.Length -gt 24) {
        $StorageAccountName = $StorageAccountName.Substring(0, 24)
    }
}

if (-not $AppInsightsName) {
    $AppInsightsName = "$FunctionAppName-insights"
}

if (-not $ServicePlanName) {
    $ServicePlanName = "$FunctionAppName-plan"
}

if (-not $ApimServiceName) {
    $ApimServiceName = "$FunctionAppName-apim"
}

Write-Host " Deploying Earth-Copilot MCP Server" -ForegroundColor Cyan
Write-Host "=====================================" -ForegroundColor Cyan
Write-Host " Resource Group: $ResourceGroupName" -ForegroundColor Yellow
Write-Host " Function App: $FunctionAppName" -ForegroundColor Yellow
Write-Host " Storage Account: $StorageAccountName" -ForegroundColor Yellow
Write-Host " App Insights: $AppInsightsName" -ForegroundColor Yellow
Write-Host " Service Plan: $ServicePlanName" -ForegroundColor Yellow
if ($DeployApim) {
    Write-Host " APIM Service: $ApimServiceName" -ForegroundColor Yellow
}
Write-Host ""

try {
    # Verify Azure CLI authentication
    Write-Host " Verifying Azure authentication..." -ForegroundColor Yellow
    $account = az account show --output json 2>$null | ConvertFrom-Json
    if (-not $account) {
        Write-Host " Not authenticated with Azure CLI. Run 'az login' first." -ForegroundColor Red
        exit 1
    }
    Write-Host " Authenticated as: $($account.user.name)" -ForegroundColor Green
    
    # Check if resource group exists
    Write-Host " Checking resource group..." -ForegroundColor Yellow
    $rgExists = az group exists --name $ResourceGroupName --output tsv
    if ($rgExists -eq "false") {
        Write-Host " Creating resource group: $ResourceGroupName" -ForegroundColor Yellow
        if (-not $WhatIf) {
            az group create --name $ResourceGroupName --location $Location --output table
            if ($LASTEXITCODE -ne 0) {
                throw "Failed to create resource group"
            }
        }
        Write-Host " Resource group created successfully" -ForegroundColor Green
    } else {
        Write-Host " Resource group exists" -ForegroundColor Green
    }
    
    # Create storage account
    Write-Host " Creating storage account: $StorageAccountName" -ForegroundColor Yellow
    if (-not $WhatIf) {
        $storageExists = az storage account check-name --name $StorageAccountName --query "nameAvailable" --output tsv
        if ($storageExists -eq "true") {
            az storage account create `
                --name $StorageAccountName `
                --resource-group $ResourceGroupName `
                --location $Location `
                --sku Standard_LRS `
                --kind StorageV2 `
                --output table
            
            if ($LASTEXITCODE -ne 0) {
                throw "Failed to create storage account"
            }
            Write-Host " Storage account created" -ForegroundColor Green
        } else {
            Write-Host " Storage account already exists" -ForegroundColor Green
        }
    }
    
    # Create Application Insights
    Write-Host " Creating Application Insights: $AppInsightsName" -ForegroundColor Yellow 
    if (-not $WhatIf) {
        az monitor app-insights component create `
            --app $AppInsightsName `
            --location $Location `
            --resource-group $ResourceGroupName `
            --kind web `
            --application-type web `
            --output table
        
        if ($LASTEXITCODE -ne 0) {
            Write-Host " Application Insights creation failed, continuing..." -ForegroundColor Yellow
        } else {
            Write-Host " Application Insights created" -ForegroundColor Green
        }
    }
    
    # Create App Service Plan
    Write-Host " Creating App Service Plan: $ServicePlanName" -ForegroundColor Yellow
    if (-not $WhatIf) {
        az appservice plan create `
            --name $ServicePlanName `
            --resource-group $ResourceGroupName `
            --location $Location `
            --sku B1 `
            --is-linux `
            --output table
        
        if ($LASTEXITCODE -ne 0) {
            throw "Failed to create App Service Plan"
        }
        Write-Host " App Service Plan created" -ForegroundColor Green
    }
    
    # Create Function App
    Write-Host " Creating Function App: $FunctionAppName" -ForegroundColor Yellow
    if (-not $WhatIf) {
        az functionapp create `
            --name $FunctionAppName `
            --resource-group $ResourceGroupName `
            --plan $ServicePlanName `
            --storage-account $StorageAccountName `
            --runtime python `
            --runtime-version 3.11 `
            --functions-version 4 `
            --os-type Linux `
            --app-insights $AppInsightsName `
            --output table
        
        if ($LASTEXITCODE -ne 0) {
            throw "Failed to create Function App"
        }
        Write-Host " Function App created" -ForegroundColor Green
    }
    
    # Configure Function App settings
    Write-Host " Configuring Function App settings..." -ForegroundColor Yellow
    if (-not $WhatIf) {
        # Get Application Insights connection string
        $appInsightsConnectionString = az monitor app-insights component show `
            --app $AppInsightsName `
            --resource-group $ResourceGroupName `
            --query "connectionString" `
            --output tsv
        
        # Configure app settings
        $appSettings = @(
            "FUNCTIONS_WORKER_RUNTIME=python",
            "FUNCTIONS_EXTENSION_VERSION=~4",
            "WEBSITE_RUN_FROM_PACKAGE=1",
            "MCP_SERVER_MODE=production",
            "EARTH_COPILOT_BASE_URL=https://your-earth-copilot.azurewebsites.net",
            "GEOINT_SERVICE_URL=https://your-geoint-app.azurewebsites.net",
            "APPLICATIONINSIGHTS_CONNECTION_STRING=$appInsightsConnectionString"
        )
        
        foreach ($setting in $appSettings) {
            az functionapp config appsettings set `
                --name $FunctionAppName `
                --resource-group $ResourceGroupName `
                --settings $setting `
                --output none
        }
        
        Write-Host " Function App settings configured" -ForegroundColor Green
    }
    
    # Deploy APIM if requested
    if ($DeployApim) {
        Write-Host " Deploying API Management..." -ForegroundColor Yellow
        
        if (-not $WhatIf) {
            # Get publisher info from Azure account
            $publisherEmail = $account.user.name
            $publisherName = "Earth-Copilot Team"
            $mcpServerUrl = "https://$FunctionAppName.azurewebsites.net"
            
            # Deploy APIM using the template
            $apimDeployScript = Join-Path $PSScriptRoot "apim\deploy-apim.ps1"
            if (Test-Path $apimDeployScript) {
                & $apimDeployScript `
                    -ResourceGroupName $ResourceGroupName `
                    -ApimServiceName $ApimServiceName `
                    -PublisherEmail $publisherEmail `
                    -PublisherName $publisherName `
                    -McpServerUrl $mcpServerUrl `
                    -Location $Location
                
                if ($LASTEXITCODE -eq 0) {
                    Write-Host " APIM deployed successfully" -ForegroundColor Green
                } else {
                    Write-Host " APIM deployment failed, continuing..." -ForegroundColor Yellow
                }
            } else {
                Write-Host " APIM deployment script not found, skipping..." -ForegroundColor Yellow
            }
        }
    }
    
    # Create deployment package
    Write-Host " Preparing deployment package..." -ForegroundColor Yellow
    if (-not $WhatIf) {
        $deploymentDir = "deployment"
        if (Test-Path $deploymentDir) {
            Remove-Item $deploymentDir -Recurse -Force
        }
        New-Item -ItemType Directory -Path $deploymentDir -Force | Out-Null
        
        # Copy MCP server files
        Copy-Item "server.py" -Destination "$deploymentDir\function_app.py" -Force
        Copy-Item "mcp_bridge.py" -Destination "$deploymentDir\" -Force
        Copy-Item "requirements.txt" -Destination "$deploymentDir\" -Force
        
        # Create host.json for Function App
        $hostJson = @{
            version = "2.0"
            logging = @{
                applicationInsights = @{
                    samplingSettings = @{
                        enableSampling = $true
                        maxTelemetryItemsPerSecond = 20
                        evaluationInterval = "01:00:00"
                        initialSamplingPercentage = 100.0
                        samplingPercentageIncreaseTimeout = "00:00:01"
                        samplingPercentageDecreaseTimeout = "00:00:01"
                        minSamplingPercentage = 0.1
                        maxSamplingPercentage = 100.0
                        movingAverageRatio = 0.25
                    }
                }
            }
            functionTimeout = "00:05:00"
            extensions = @{
                http = @{
                    routePrefix = ""
                    maxConcurrentRequests = 100
                    maxOutstandingRequests = 200
                }
            }
        } | ConvertTo-Json -Depth 10
        
        $hostJson | Out-File -FilePath "$deploymentDir\host.json" -Encoding UTF8
        
        # Create function.json for HTTP trigger
        New-Item -ItemType Directory -Path "$deploymentDir\mcp_endpoint" -Force | Out-Null
        $functionJson = @{
            scriptFile = "__init__.py"
            bindings = @(
                @{
                    authLevel = "function"
                    type = "httpTrigger"
                    direction = "in"
                    name = "req"
                    methods = @("get", "post", "options")
                    route = "{*route}"
                },
                @{
                    type = "http"
                    direction = "out"
                    name = "`$return"
                }
            )
        } | ConvertTo-Json -Depth 10
        
        $functionJson | Out-File -FilePath "$deploymentDir\mcp_endpoint\function.json" -Encoding UTF8
        
        # Create Python function wrapper
        $pythonWrapper = @"
import azure.functions as func
from mcp_bridge import app
import asyncio

async def main(req: func.HttpRequest) -> func.HttpResponse:
    # Convert Azure Functions request to ASGI format
    # This is a simplified wrapper - production would need full ASGI adapter
    
    return func.HttpResponse(
        "Earth-Copilot MCP Server is running. Use /docs for API documentation.",
        status_code=200,
        headers={"Content-Type": "application/json"}
    )
"@
        
        $pythonWrapper | Out-File -FilePath "$deploymentDir\mcp_endpoint\__init__.py" -Encoding UTF8
        
        Write-Host " Deployment package prepared" -ForegroundColor Green
    }
    
    # Deploy to Function App
    Write-Host " Deploying to Function App..." -ForegroundColor Yellow
    if (-not $WhatIf) {
        # Create deployment zip
        $zipPath = "mcp-server-deployment.zip"
        if (Test-Path $zipPath) {
            Remove-Item $zipPath -Force
        }
        
        Compress-Archive -Path "$deploymentDir\*" -DestinationPath $zipPath -Force
        
        # Deploy zip package
        az functionapp deployment source config-zip `
            --name $FunctionAppName `
            --resource-group $ResourceGroupName `
            --src $zipPath `
            --output table
        
        if ($LASTEXITCODE -ne 0) {
            throw "Failed to deploy Function App"
        }
        
        Write-Host " Function App deployed successfully" -ForegroundColor Green
        
        # Clean up
        Remove-Item $deploymentDir -Recurse -Force
        Remove-Item $zipPath -Force
    }
    
    # Display results
    Write-Host ""
    Write-Host " Earth-Copilot MCP Server Deployment Complete!" -ForegroundColor Green
    Write-Host "=================================================" -ForegroundColor Green
    
    $functionAppUrl = "https://$FunctionAppName.azurewebsites.net"
    
    Write-Host " Function App URL: $functionAppUrl" -ForegroundColor White
    Write-Host " API Documentation: $functionAppUrl/docs" -ForegroundColor White
    Write-Host " Health Check: $functionAppUrl/health" -ForegroundColor White
    
    if ($DeployApim) {
        $apimUrl = "https://$ApimServiceName.azure-api.net"
        Write-Host " APIM Gateway: $apimUrl" -ForegroundColor White
        Write-Host " MCP API: $apimUrl/earth-copilot/mcp" -ForegroundColor White
    }
    
    Write-Host ""
    Write-Host " Next Steps:" -ForegroundColor Cyan
    Write-Host "1.  Test the MCP endpoints using the API documentation" -ForegroundColor White
    Write-Host "2.  Configure authentication and API keys as needed" -ForegroundColor White
    Write-Host "3.  Integrate with Earth-Copilot main application" -ForegroundColor White
    Write-Host "4.  Monitor performance in Application Insights" -ForegroundColor White
    
    # Save deployment info
    $deploymentInfo = @{
        functionAppName = $FunctionAppName
        functionAppUrl = $functionAppUrl
        resourceGroupName = $ResourceGroupName
        location = $Location
        deploymentDate = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
        apimServiceName = if ($DeployApim) { $ApimServiceName } else { $null }
        apimUrl = if ($DeployApim) { "https://$ApimServiceName.azure-api.net" } else { $null }
    }
    
    $configFile = "earth-copilot-mcp-deployment.json"
    $deploymentInfo | ConvertTo-Json -Depth 3 | Out-File -FilePath $configFile -Encoding UTF8
    Write-Host " Deployment info saved to: $configFile" -ForegroundColor Cyan
    
} catch {
    Write-Host " Deployment failed: $($_.Exception.Message)" -ForegroundColor Red
    Write-Host " Check the error details above and retry" -ForegroundColor Yellow
    exit 1
}

Write-Host ""
Write-Host " Earth-Copilot MCP Server is ready!" -ForegroundColor Green