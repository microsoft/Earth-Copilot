# Environment Variable Collection Script
# Run this after deploying your infrastructure to collect all required environment variables

Write-Host "Earth Copilot Environment Variable Collection" -ForegroundColor Green
Write-Host "=============================================" -ForegroundColor Green

$resourceGroupName = "earthcopilot-rg"
$webAppName = "earth-copilot-webapp"
$functionAppName = "router-function-app-standard"
$storageAccountName = "earthcopilotstorage"
$keyVaultName = "earthcopilot-keys"
$appInsightsName = "earth-copilot-insights"
$foundryServiceName = "earth-copilot-foundry"
$searchServiceName = "earth-copilot-search"
$mapsAccountName = "earth-copilot-maps"
$apimServiceName = "earth-copilot-apim"
$contentModerationName = "earth-copilot-moderation"

Write-Host "`nCollecting environment variables..." -ForegroundColor Yellow

# Create .env file
$envContent = @"
###############################################
# Azure AI Foundry Configuration - Foundry Hub GPT-5
# Primary model for Semantic Kernel queries and chat
###############################################
# TODO: Set these values from your Azure AI Foundry service
AZURE_FOUNDRY_ENDPOINT=https://earth-copilot-foundry.cognitiveservices.azure.com
AZURE_FOUNDRY_API_KEY=your-azure-foundry-api-key
AZURE_FOUNDRY_API_VERSION=2025-04-01-preview
AZURE_FOUNDRY_DEPLOYMENT_NAME=gpt-5

# Legacy OpenAI compatibility (pointing to Foundry)
AZURE_OPENAI_ENDPOINT=https://earth-copilot-foundry.cognitiveservices.azure.com
AZURE_OPENAI_API_KEY=your-azure-foundry-api-key
AZURE_OPENAI_API_VERSION=2025-04-01-preview
AZURE_OPENAI_DEPLOYMENT_NAME=gpt-5

# Alternative naming conventions for compatibility
AOAI_ENDPOINT=https://earth-copilot-foundry.cognitiveservices.azure.com
AOAI_KEY=your-azure-foundry-api-key
AOAI_DEPLOYMENT=gpt-5
AOAI_VERSION=2025-04-01-preview

# Foundry Hub Model Router (for intelligent routing)
FOUNDRY_MODEL_ROUTER=https://earth-copilot-foundry.cognitiveservices.azure.com/openai/deployments/gpt-5/chat/completions
FOUNDRY_HUB_KEY=your-azure-foundry-api-key
FOUNDRY_API_VERSION=2025-01-01-preview

"@

# Collect Azure AI Foundry configuration
Write-Host "Collecting Azure AI Foundry configuration..." -ForegroundColor Cyan
try {
    $foundryEndpoint = az cognitiveservices account show --name $foundryServiceName --resource-group $resourceGroupName --query "properties.endpoint" -o tsv 2>$null
    if ($foundryEndpoint) {
        $envContent += @"
# Azure AI Foundry Configuration (from deployed service)
AZURE_FOUNDRY_ENDPOINT=$foundryEndpoint
# TODO: Get API key from Azure portal or Key Vault
AZURE_FOUNDRY_API_KEY=your-azure-foundry-api-key
AZURE_FOUNDRY_DEPLOYMENT_NAME=gpt-5

# Legacy OpenAI compatibility (pointing to Foundry)
AZURE_OPENAI_ENDPOINT=$foundryEndpoint
AZURE_OPENAI_API_KEY=your-azure-foundry-api-key
AZURE_OPENAI_DEPLOYMENT_NAME=gpt-5

"@
        Write-Host "✓ Azure AI Foundry endpoint collected: $foundryEndpoint" -ForegroundColor Green
    } else {
        throw "Azure AI Foundry service not found"
    }
} catch {
    $envContent += @"
# Azure AI Foundry Configuration
# TODO: Set these values from your Azure AI Foundry service
AZURE_FOUNDRY_ENDPOINT=https://earth-copilot-foundry.cognitiveservices.azure.com
AZURE_FOUNDRY_API_KEY=your-azure-foundry-api-key
AZURE_FOUNDRY_DEPLOYMENT_NAME=gpt-5

# Legacy OpenAI compatibility (pointing to Foundry)
AZURE_OPENAI_ENDPOINT=https://earth-copilot-foundry.cognitiveservices.azure.com
AZURE_OPENAI_API_KEY=your-azure-foundry-api-key
AZURE_OPENAI_DEPLOYMENT_NAME=gpt-5

"@
    Write-Host "⚠ Azure AI Foundry service not found or not accessible" -ForegroundColor Yellow
}

# Collect Azure AI Search configuration
Write-Host "Collecting Azure AI Search configuration..." -ForegroundColor Cyan
try {
    $searchEndpoint = az search service show --name $searchServiceName --resource-group $resourceGroupName --query "searchServiceEndpoint" -o tsv 2>$null
    if ($searchEndpoint) {
        $envContent += @"
# Azure AI Search Configuration
SEARCH_ENDPOINT=$searchEndpoint
# TODO: Get API key from Azure portal
SEARCH_API_KEY=your-search-api-key
SEARCH_INDEX_NAME=veda-mydata-index

"@
        Write-Host "✓ Azure AI Search endpoint collected: $searchEndpoint" -ForegroundColor Green
    } else {
        throw "Azure AI Search service not found"
    }
} catch {
    $envContent += @"
# Azure AI Search Configuration
# TODO: Set these values from your Azure AI Search service
SEARCH_ENDPOINT=your-search-endpoint
SEARCH_API_KEY=your-search-api-key
SEARCH_INDEX_NAME=veda-mydata-index

"@
    Write-Host "⚠ Azure AI Search service not found or not accessible" -ForegroundColor Yellow
}

# Collect Azure Maps configuration
Write-Host "Collecting Azure Maps configuration..." -ForegroundColor Cyan
try {
    # Try to get from Key Vault first
    $mapsKey = az keyvault secret show --vault-name $keyVaultName --name azure-maps-subscription-key --query value -o tsv 2>$null
    $mapsClientId = az keyvault secret show --vault-name $keyVaultName --name azure-maps-client-id --query value -o tsv 2>$null
    
    if (-not $mapsKey) {
        # If not in Key Vault, try to get from Maps account directly
        $mapsKey = az maps account keys list --account-name $mapsAccountName --resource-group $resourceGroupName --query "primaryKey" -o tsv 2>$null
    }
    
    if ($mapsKey) {
        $envContent += @"
# Azure Maps Configuration
AZURE_MAPS_SUBSCRIPTION_KEY=$mapsKey
AZURE_MAPS_CLIENT_ID=$mapsClientId

"@
        Write-Host "✓ Azure Maps configuration collected" -ForegroundColor Green
    } else {
        throw "Azure Maps configuration not found"
    }
} catch {
    $envContent += @"
# Azure Maps Configuration
# TODO: Set these values from your Azure Maps service
AZURE_MAPS_SUBSCRIPTION_KEY=your-azure-maps-subscription-key
AZURE_MAPS_CLIENT_ID=your-azure-maps-client-id

"@
    Write-Host "⚠ Azure Maps configuration not found" -ForegroundColor Yellow
}

# Collect API Management configuration
Write-Host "Collecting API Management configuration..." -ForegroundColor Cyan
try {
    $apimGatewayUrl = az apim show --name $apimServiceName --resource-group $resourceGroupName --query "gatewayUrl" -o tsv 2>$null
    $apimPortalUrl = az apim show --name $apimServiceName --resource-group $resourceGroupName --query "portalUrl" -o tsv 2>$null
    if ($apimGatewayUrl) {
        $envContent += @"
# API Management Configuration
APIM_GATEWAY_URL=$apimGatewayUrl
APIM_PORTAL_URL=$apimPortalUrl
# TODO: Get subscription keys from Azure portal
APIM_SUBSCRIPTION_KEY=your-apim-subscription-key

"@
        Write-Host "✓ API Management configuration collected" -ForegroundColor Green
    } else {
        throw "API Management service not found"
    }
} catch {
    $envContent += @"
# API Management Configuration
# TODO: Set these values from your API Management service
APIM_GATEWAY_URL=https://earth-copilot-apim.azure-api.net
APIM_PORTAL_URL=https://earth-copilot-apim.portal.azure-api.net
APIM_SUBSCRIPTION_KEY=your-apim-subscription-key

"@
    Write-Host "⚠ API Management service not found or not accessible" -ForegroundColor Yellow
}

# Collect Content Moderation configuration
Write-Host "Collecting Content Moderation configuration..." -ForegroundColor Cyan
try {
    $contentModerationEndpoint = az cognitiveservices account show --name $contentModerationName --resource-group $resourceGroupName --query "properties.endpoint" -o tsv 2>$null
    if ($contentModerationEndpoint) {
        $envContent += @"
# Content Moderation Configuration
CONTENT_MODERATION_ENDPOINT=$contentModerationEndpoint
# TODO: Get API key from Azure portal or Key Vault
CONTENT_MODERATION_API_KEY=your-content-moderation-api-key

"@
        Write-Host "✓ Content Moderation endpoint collected: $contentModerationEndpoint" -ForegroundColor Green
    } else {
        throw "Content Moderation service not found"
    }
} catch {
    $envContent += @"
# Content Moderation Configuration
# TODO: Set these values from your Content Moderation service
CONTENT_MODERATION_ENDPOINT=https://earth-copilot-moderation.cognitiveservices.azure.com
CONTENT_MODERATION_API_KEY=your-content-moderation-api-key

"@
    Write-Host "⚠ Content Moderation service not found or not accessible" -ForegroundColor Yellow
}

# Collect Storage Account information
Write-Host "Collecting Storage Account information..." -ForegroundColor Cyan
try {
    $storageKey = az storage account keys list --resource-group $resourceGroupName --account-name $storageAccountName --query "[0].value" -o tsv 2>$null
    if ($storageKey) {
        $envContent += @"
# Storage Configuration
STORAGE_ACCOUNT_NAME=$storageAccountName
STORAGE_ACCOUNT_KEY=$storageKey
STORAGE_CONTAINER_NAME=earth-copilot-data

"@
        Write-Host "✓ Storage Account configuration collected" -ForegroundColor Green
    } else {
        throw "Storage account not found"
    }
} catch {
    $envContent += @"
# Storage Configuration
# TODO: Set these values from your Azure Storage Account
STORAGE_ACCOUNT_NAME=$storageAccountName
STORAGE_ACCOUNT_KEY=your-storage-account-key
STORAGE_CONTAINER_NAME=earth-copilot-data

"@
    Write-Host "⚠ Storage Account configuration not found" -ForegroundColor Yellow
}

# Collect Application Insights information
Write-Host "Collecting Application Insights information..." -ForegroundColor Cyan
try {
    $appInsightsConnectionString = az monitor app-insights component show --app $appInsightsName --resource-group $resourceGroupName --query connectionString -o tsv 2>$null
    $appInsightsInstrumentationKey = az monitor app-insights component show --app $appInsightsName --resource-group $resourceGroupName --query instrumentationKey -o tsv 2>$null
    
    if ($appInsightsConnectionString) {
        $envContent += @"
# Application Insights Configuration
APPLICATIONINSIGHTS_CONNECTION_STRING=$appInsightsConnectionString
APPINSIGHTS_INSTRUMENTATIONKEY=$appInsightsInstrumentationKey

"@
        Write-Host "✓ Application Insights configuration collected" -ForegroundColor Green
    } else {
        throw "Application Insights not found"
    }
} catch {
    $envContent += @"
# Application Insights Configuration
# TODO: Set these values from your Application Insights service
APPLICATIONINSIGHTS_CONNECTION_STRING=your-app-insights-connection-string
APPINSIGHTS_INSTRUMENTATIONKEY=your-app-insights-instrumentation-key

"@
    Write-Host "⚠ Application Insights configuration not found" -ForegroundColor Yellow
}

# Get Web App URL
Write-Host "Collecting Web App information..." -ForegroundColor Cyan
try {
    $webAppUrl = az webapp show --name $webAppName --resource-group $resourceGroupName --query defaultHostName -o tsv 2>$null
    if ($webAppUrl) {
        $envContent += @"
# Web App Configuration
WEB_APP_URL=https://$webAppUrl

"@
        Write-Host "✓ Web App URL collected: https://$webAppUrl" -ForegroundColor Green
    }
} catch {
    Write-Host "⚠ Web App information not found" -ForegroundColor Yellow
}

# Get Function App URL
Write-Host "Collecting Function App information..." -ForegroundColor Cyan
try {
    $functionAppUrl = az functionapp show --name $functionAppName --resource-group $resourceGroupName --query defaultHostName -o tsv 2>$null
    if ($functionAppUrl) {
        $envContent += @"
# Function App Configuration
FUNCTION_APP_URL=https://$functionAppUrl

"@
        Write-Host "✓ Function App URL collected: https://$functionAppUrl" -ForegroundColor Green
    }
} catch {
    Write-Host "⚠ Function App information not found" -ForegroundColor Yellow
}

# Add remaining static configuration
$envContent += @"
# Azure AI Search Configuration (Optional)
# TODO: Set these values if you're using Azure AI Search
SEARCH_ENDPOINT=your-search-endpoint
SEARCH_API_KEY=your-search-api-key
SEARCH_INDEX_NAME=veda-mydata-index

# STAC Configuration  
PLANETARY_COMPUTER_STAC_URL=https://planetarycomputer.microsoft.com/api/stac/v1
STAC_API_URL=https://planetarycomputer.microsoft.com/api/stac/v1

# Application Settings
APP_NAME=Earth Copilot
APP_VERSION=2.0.0
DEBUG=false

# Server Configuration
PORT=8080
ALLOW_CORS=1
ALLOWED_ORIGINS=http://localhost:3000,http://127.0.0.1:3000,http://localhost:8080,http://127.0.0.1:8080,http://localhost:5173,http://127.0.0.1:5173
CORS_ORIGINS=http://localhost:3000,http://localhost:5173,http://localhost:8080,http://localhost:8000,http://127.0.0.1:3000,http://127.0.0.1:8080
"@

# Write .env file
$envContent | Out-File -FilePath ".env" -Encoding UTF8
Write-Host "`n✓ Environment variables written to .env file" -ForegroundColor Green

# Also write to React UI .env file
$reactEnvContent = @"
# React UI Environment Variables
VITE_API_BASE_URL=https://$functionAppUrl
VITE_AZURE_MAPS_SUBSCRIPTION_KEY=$mapsKey
VITE_AZURE_MAPS_CLIENT_ID=$mapsClientId
"@

$reactEnvContent | Out-File -FilePath "earth-copilot/web-ui/.env" -Encoding UTF8
Write-Host "✓ React UI environment variables written to earth-copilot/web-ui/.env" -ForegroundColor Green

Write-Host "`n🎉 Environment variable collection complete!" -ForegroundColor Green
Write-Host "📝 Please review the .env files and update any TODO items with your actual values." -ForegroundColor Yellow
Write-Host "🔑 Don't forget to set your Azure OpenAI and other API keys!" -ForegroundColor Yellow