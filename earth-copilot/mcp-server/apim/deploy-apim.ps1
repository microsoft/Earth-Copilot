# Azure API Management Deployment Script for Earth-Copilot MCP Server
# 
# This script deploys Azure API Management with comprehensive policies for:
# - Authentication and authorization
# - Rate limiting and quotas
# - Caching and performance optimization
# - Monitoring and logging
# - Security headers and CORS
# - Circuit breaker patterns

param(
    [Parameter(Mandatory=$true)]
    [string]$ResourceGroupName,
    
    [Parameter(Mandatory=$true)]
    [string]$ApimServiceName,
    
    [Parameter(Mandatory=$true)]
    [string]$PublisherEmail,
    
    [Parameter(Mandatory=$true)]
    [string]$PublisherName,
    
    [Parameter(Mandatory=$true)]
    [string]$McpServerUrl,
    
    [string]$Location = "East US",
    [string]$Sku = "Developer",
    [string]$TemplateFile = "apim-template.json",
    [switch]$WhatIf = $false
)

# Set error handling
$ErrorActionPreference = "Stop"

Write-Host "🚀 Deploying Earth-Copilot MCP API Management" -ForegroundColor Cyan
Write-Host "===============================================" -ForegroundColor Cyan
Write-Host "📍 Resource Group: $ResourceGroupName" -ForegroundColor Yellow
Write-Host "🏷️ APIM Service: $ApimServiceName" -ForegroundColor Yellow
Write-Host "🔗 MCP Server URL: $McpServerUrl" -ForegroundColor Yellow
Write-Host "📧 Publisher: $PublisherName <$PublisherEmail>" -ForegroundColor Yellow
Write-Host "🏢 SKU: $Sku" -ForegroundColor Yellow
Write-Host ""

try {
    # Verify Azure CLI authentication
    Write-Host "🔐 Verifying Azure authentication..." -ForegroundColor Yellow
    $account = az account show --output json 2>$null | ConvertFrom-Json
    if (-not $account) {
        Write-Host "❌ Not authenticated with Azure CLI. Run 'az login' first." -ForegroundColor Red
        exit 1
    }
    Write-Host "✅ Authenticated as: $($account.user.name)" -ForegroundColor Green
    Write-Host "📊 Subscription: $($account.name) ($($account.id))" -ForegroundColor Green
    
    # Check if resource group exists
    Write-Host "🏗️ Checking resource group..." -ForegroundColor Yellow
    $rgExists = az group exists --name $ResourceGroupName --output tsv
    if ($rgExists -eq "false") {
        Write-Host "📦 Creating resource group: $ResourceGroupName" -ForegroundColor Yellow
        az group create --name $ResourceGroupName --location $Location --output table
        if ($LASTEXITCODE -ne 0) {
            throw "Failed to create resource group"
        }
        Write-Host "✅ Resource group created successfully" -ForegroundColor Green
    } else {
        Write-Host "✅ Resource group exists" -ForegroundColor Green
    }
    
    # Validate template file
    Write-Host "📋 Validating ARM template..." -ForegroundColor Yellow
    if (-not (Test-Path $TemplateFile)) {
        throw "Template file not found: $TemplateFile"
    }
    
    # Prepare deployment parameters
    $deploymentParams = @{
        apimServiceName = $ApimServiceName
        publisherEmail = $PublisherEmail
        publisherName = $PublisherName
        sku = $Sku
        mcpServerUrl = $McpServerUrl
    }
    
    $parametersJson = $deploymentParams | ConvertTo-Json -Compress
    Write-Host "🔧 Deployment parameters prepared" -ForegroundColor Green
    
    if ($WhatIf) {
        Write-Host "🔍 Running What-If analysis..." -ForegroundColor Yellow
        az deployment group what-if `
            --resource-group $ResourceGroupName `
            --template-file $TemplateFile `
            --parameters $parametersJson `
            --output table
        
        Write-Host "✅ What-If analysis complete" -ForegroundColor Green
        return
    }
    
    # Deploy APIM
    Write-Host "🚀 Deploying API Management service..." -ForegroundColor Yellow
    Write-Host "⏱️ This may take 20-45 minutes for initial deployment..." -ForegroundColor Yellow
    
    $deploymentName = "earth-copilot-mcp-apim-$(Get-Date -Format 'yyyyMMdd-HHmmss')"
    
    $deploymentResult = az deployment group create `
        --resource-group $ResourceGroupName `
        --name $deploymentName `
        --template-file $TemplateFile `
        --parameters $parametersJson `
        --output json | ConvertFrom-Json
    
    if ($LASTEXITCODE -ne 0) {
        throw "APIM deployment failed"
    }
    
    Write-Host "✅ APIM deployment completed successfully!" -ForegroundColor Green
    
    # Extract deployment outputs
    $outputs = $deploymentResult.properties.outputs
    $apimGatewayUrl = $outputs.apimGatewayUrl.value
    $fullApiUrl = $outputs.fullApiUrl.value
    
    Write-Host ""
    Write-Host "📊 Deployment Summary" -ForegroundColor Cyan
    Write-Host "=====================" -ForegroundColor Cyan
    Write-Host "🏷️ APIM Service Name: $($outputs.apimServiceName.value)" -ForegroundColor White
    Write-Host "🌐 Gateway URL: $apimGatewayUrl" -ForegroundColor White
    Write-Host "🔗 MCP API URL: $fullApiUrl" -ForegroundColor White
    Write-Host "📋 API Path: $($outputs.mcpApiPath.value)" -ForegroundColor White
    
    # Configure additional APIM settings
    Write-Host ""
    Write-Host "🔧 Configuring additional APIM settings..." -ForegroundColor Yellow
    
    # Create products
    Write-Host "📦 Creating API products..." -ForegroundColor Gray
    az apim product create `
        --resource-group $ResourceGroupName `
        --service-name $ApimServiceName `
        --product-id "earth-copilot-starter" `
        --product-name "Earth-Copilot Starter" `
        --description "Starter plan for Earth-Copilot MCP API" `
        --subscription-required true `
        --approval-required false `
        --subscriptions-limit 10 `
        --state "published" `
        --output table
    
    az apim product create `
        --resource-group $ResourceGroupName `
        --service-name $ApimServiceName `
        --product-id "earth-copilot-professional" `
        --product-name "Earth-Copilot Professional" `
        --description "Professional plan for Earth-Copilot MCP API" `
        --subscription-required true `
        --approval-required true `
        --subscriptions-limit 100 `
        --state "published" `
        --output table
    
    # Associate API with products
    Write-Host "🔗 Associating API with products..." -ForegroundColor Gray
    az apim product api add `
        --resource-group $ResourceGroupName `
        --service-name $ApimServiceName `
        --product-id "earth-copilot-starter" `
        --api-id "earth-copilot-mcp-api" `
        --output table
    
    az apim product api add `
        --resource-group $ResourceGroupName `
        --service-name $ApimServiceName `
        --product-id "earth-copilot-professional" `
        --api-id "earth-copilot-mcp-api" `
        --output table
    
    # Create developer portal groups
    Write-Host "👥 Creating user groups..." -ForegroundColor Gray
    az apim group create `
        --resource-group $ResourceGroupName `
        --service-name $ApimServiceName `
        --group-id "earth-copilot-developers" `
        --display-name "Earth-Copilot Developers" `
        --description "Developers using Earth-Copilot MCP API" `
        --output table
    
    # Set up monitoring
    Write-Host "📊 Configuring monitoring..." -ForegroundColor Gray
    
    # Create Application Insights if not exists
    $appInsightsName = "$ApimServiceName-insights"
    Write-Host "📈 Creating Application Insights: $appInsightsName" -ForegroundColor Gray
    
    az monitor app-insights component create `
        --app $appInsightsName `
        --location $Location `
        --resource-group $ResourceGroupName `
        --kind "web" `
        --application-type "web" `
        --output table
    
    # Get Application Insights instrumentation key
    $instrumentationKey = az monitor app-insights component show `
        --app $appInsightsName `
        --resource-group $ResourceGroupName `
        --query "instrumentationKey" `
        --output tsv
    
    if ($instrumentationKey) {
        # Configure APIM logger
        Write-Host "📝 Configuring APIM logger..." -ForegroundColor Gray
        az apim logger create `
            --resource-group $ResourceGroupName `
            --service-name $ApimServiceName `
            --logger-id "earth-copilot-logger" `
            --logger-type "applicationInsights" `
            --description "Earth-Copilot MCP API Logger" `
            --credentials "instrumentationKey=$instrumentationKey" `
            --output table
    }
    
    Write-Host ""
    Write-Host "🎉 Earth-Copilot MCP APIM Setup Complete!" -ForegroundColor Green
    Write-Host "===========================================" -ForegroundColor Green
    
    # Display next steps
    Write-Host ""
    Write-Host "🔮 Next Steps:" -ForegroundColor Cyan
    Write-Host "1. 📝 Configure MCP server backend URL in APIM" -ForegroundColor White
    Write-Host "2. 🔑 Create API subscriptions for developers" -ForegroundColor White
    Write-Host "3. 🧪 Test MCP API endpoints:" -ForegroundColor White
    Write-Host "   - POST $fullApiUrl/tools/list" -ForegroundColor Gray
    Write-Host "   - POST $fullApiUrl/resources/list" -ForegroundColor Gray
    Write-Host "   - POST $fullApiUrl/prompts/list" -ForegroundColor Gray
    Write-Host "4. 📊 Monitor API usage in Application Insights" -ForegroundColor White
    Write-Host "5. 🔧 Customize rate limits and quotas as needed" -ForegroundColor White
    
    # Save configuration to file
    $config = @{
        apimServiceName = $outputs.apimServiceName.value
        gatewayUrl = $apimGatewayUrl
        mcpApiUrl = $fullApiUrl
        resourceGroupName = $ResourceGroupName
        location = $Location
        deploymentDate = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
    }
    
    $configFile = "earth-copilot-mcp-apim-config.json"
    $config | ConvertTo-Json -Depth 3 | Out-File -FilePath $configFile -Encoding UTF8
    Write-Host "💾 Configuration saved to: $configFile" -ForegroundColor Cyan
    
} catch {
    Write-Host "❌ Deployment failed: $($_.Exception.Message)" -ForegroundColor Red
    Write-Host "🔍 Check the error details above and retry" -ForegroundColor Yellow
    exit 1
}

Write-Host ""
Write-Host "✨ Earth-Copilot MCP APIM is ready for use!" -ForegroundColor Green