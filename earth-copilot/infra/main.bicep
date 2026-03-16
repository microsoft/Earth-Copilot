targetScope = 'subscription'

@minLength(1)
@maxLength(64)
@description('Name of the environment that will be used to name resources')
param environmentName string

@minLength(1)
@description('Primary location for all resources')
param location string

@description('Container image name')
param containerImage string = ''

@description('Azure OpenAI API Key')
@secure()
param azureOpenAiApiKey string = ''

@description('Azure OpenAI Endpoint')
param azureOpenAiEndpoint string = ''

@description('OpenAI API Key (fallback)')
@secure()
param openAiApiKey string = ''

// Authentication parameters
@description('Enable Microsoft Entra (Azure AD) authentication')
param enableAuthentication bool = false

@description('Microsoft Entra Client ID (Application ID)')
param microsoftEntraClientId string = ''

@description('Microsoft Entra Tenant ID')
param microsoftEntraTenantId string = ''

@description('Microsoft Entra Client Secret')
@secure()
param microsoftEntraClientSecret string = ''

// AI Services parameters
@description('Cloud environment: Commercial or Government')
@allowed(['Commercial', 'Government'])
param cloudEnvironment string = 'Commercial'

@description('Deploy Azure AI Foundry (OpenAI) with GPT-4 model')
param deployAIFoundry bool = true

@description('Deploy GPT-5 model (requires GlobalStandard quota — set false if unavailable)')
param deployGpt5 bool = true

// Bot Service parameters (Teams integration)
@description('Deploy Azure Bot Service for Teams chat integration')
param deployBotService bool = false

@description('Microsoft App ID for the Bot (from Entra App Registration)')
param microsoftBotAppId string = ''

@description('Microsoft App Password (client secret) for the Bot')
@secure()
param microsoftBotAppPassword string = ''

// Private Networking
@description('Deploy with private endpoints (disables public access, creates VNet, DNS zones, and PEs). Private by default.')
param enablePrivateEndpoints bool = true

@description('Set to true to restore a soft-deleted Cognitive Services account (e.g. after a failed or torn-down deployment)')
param restoreSoftDeletedAccount bool = false

var abbrs = loadJsonContent('./abbreviations.json')
var resourceToken = toLower(uniqueString(subscription().id, environmentName, location))
var tags = {
  'azd-env-name': environmentName
  'azd-app-name': 'earth-copilot'
}

resource rg 'Microsoft.Resources/resourceGroups@2022-09-01' = {
  name: 'rg-${environmentName}'
  location: location
  tags: tags
}

// ═══════════════════════════════════════════════════════════════════
// NETWORKING (conditional — only deployed when enablePrivateEndpoints = true)
// ═══════════════════════════════════════════════════════════════════

module networking './shared/networking.bicep' = if (enablePrivateEndpoints) {
  name: 'networking'
  scope: rg
  params: {
    location: location
    tags: tags
    vnetName: 'vnet-${resourceToken}'
  }
}

module privateDnsZones './shared/private-dns-zones.bicep' = if (enablePrivateEndpoints) {
  name: 'private-dns-zones'
  scope: rg
  params: {
    tags: tags
    vnetId: networking.?outputs.?vnetId ?? ''
    cloudEnvironment: cloudEnvironment
  }
}

// ═══════════════════════════════════════════════════════════════════
// SHARED SERVICES
// ═══════════════════════════════════════════════════════════════════

module monitoring './shared/monitoring.bicep' = {
  name: 'monitoring'
  scope: rg
  params: {
    location: location
    tags: tags
    logAnalyticsName: '${abbrs.operationalInsightsWorkspaces}${resourceToken}'
    applicationInsightsName: deployAIFoundry ? '${abbrs.insightsComponents}${resourceToken}' : ''
  }
}

module registry './shared/registry.bicep' = {
  name: 'registry'
  scope: rg
  params: {
    location: location
    tags: tags
    name: '${abbrs.containerRegistryRegistries}${resourceToken}'
    enablePrivateEndpoints: enablePrivateEndpoints
  }
}

module appsEnv './shared/apps-env.bicep' = {
  name: 'apps-env'
  scope: rg
  params: {
    name: '${abbrs.appManagedEnvironments}${resourceToken}'
    location: location
    tags: tags
    logAnalyticsWorkspaceName: monitoring.outputs.logAnalyticsWorkspaceName
    // VNet integration for OUTBOUND traffic: Container App can reach PE-locked services
    // (ACR, AI Services, Key Vault, Storage) via the VNet instead of public internet.
    // internal = false so the Container App has a public FQDN for the React SPA.
    infrastructureSubnetId: enablePrivateEndpoints ? (networking.?outputs.?containerAppsSubnetId ?? '') : ''
    internal: false
  }
}

// Storage Account (required for AI Foundry Hub)
module storage './shared/storage.bicep' = if (deployAIFoundry) {
  name: 'storage'
  scope: rg
  params: {
    name: '${abbrs.storageStorageAccounts}${resourceToken}'
    location: location
    tags: tags
    enablePrivateEndpoints: enablePrivateEndpoints
  }
}

// Key Vault (required for AI Foundry Hub)
module keyVault './shared/keyvault.bicep' = if (deployAIFoundry) {
  name: 'keyvault'
  scope: rg
  params: {
    name: '${abbrs.keyVaultVaults}${resourceToken}'
    location: location
    tags: tags
    enablePrivateEndpoints: enablePrivateEndpoints
  }
}

// Azure AI Foundry (OpenAI) with GPT-4 model + Agent Service Hub/Project
module aiFoundry './shared/ai-foundry.bicep' = if (deployAIFoundry) {
  name: 'ai-foundry'
  scope: rg
  params: {
    name: '${abbrs.cognitiveServicesAccounts}foundry-${resourceToken}'
    location: location
    tags: tags
    deployModels: true
    deployGpt5: deployGpt5
    deployAgentService: true
    hubName: '${abbrs.machineLearningServicesWorkspaces}hub-${resourceToken}'
    projectName: '${abbrs.machineLearningServicesWorkspaces}project-${resourceToken}'
    storageAccountId: storage.?outputs.?id ?? ''
    keyVaultId: keyVault.?outputs.?id ?? ''
    applicationInsightsId: monitoring.outputs.applicationInsightsId
    cloudEnvironment: cloudEnvironment
    enablePrivateEndpoints: enablePrivateEndpoints
    restoreSoftDeletedAccount: restoreSoftDeletedAccount
  }
}

// Azure Maps for geocoding and map rendering
// Note: Azure Maps is available in both Commercial and Government clouds
module maps './shared/maps.bicep' = {
  name: 'maps'
  scope: rg
  params: {
    name: '${abbrs.mapsAccounts}${resourceToken}'
    location: location
    tags: tags
  }
}

// ═══════════════════════════════════════════════════════════════════
// PRIVATE ENDPOINTS (conditional — only deployed when enablePrivateEndpoints = true)
// Each PE links an Azure service to the VNet and registers in its DNS zone
// ═══════════════════════════════════════════════════════════════════

module peRegistry './shared/private-endpoint.bicep' = if (enablePrivateEndpoints) {
  name: 'pe-registry'
  scope: rg
  params: {
    name: 'pe-cr-${resourceToken}'
    location: location
    tags: tags
    serviceResourceId: registry.outputs.id
    groupId: 'registry'
    subnetId: networking.?outputs.?privateEndpointsSubnetId ?? ''
    privateDnsZoneId: privateDnsZones.?outputs.?containerRegistryDnsZoneId ?? ''
  }
}

module peKeyVault './shared/private-endpoint.bicep' = if (enablePrivateEndpoints && deployAIFoundry) {
  name: 'pe-keyvault'
  scope: rg
  params: {
    name: 'pe-kv-${resourceToken}'
    location: location
    tags: tags
    serviceResourceId: keyVault.?outputs.?id ?? ''
    groupId: 'vault'
    subnetId: networking.?outputs.?privateEndpointsSubnetId ?? ''
    privateDnsZoneId: privateDnsZones.?outputs.?keyVaultDnsZoneId ?? ''
  }
}

module peStorageBlob './shared/private-endpoint.bicep' = if (enablePrivateEndpoints && deployAIFoundry) {
  name: 'pe-storage-blob'
  scope: rg
  params: {
    name: 'pe-st-blob-${resourceToken}'
    location: location
    tags: tags
    serviceResourceId: storage.?outputs.?id ?? ''
    groupId: 'blob'
    subnetId: networking.?outputs.?privateEndpointsSubnetId ?? ''
    privateDnsZoneId: privateDnsZones.?outputs.?storageBlobDnsZoneId ?? ''
  }
}

module peStorageFile './shared/private-endpoint.bicep' = if (enablePrivateEndpoints && deployAIFoundry) {
  name: 'pe-storage-file'
  scope: rg
  params: {
    name: 'pe-st-file-${resourceToken}'
    location: location
    tags: tags
    serviceResourceId: storage.?outputs.?id ?? ''
    groupId: 'file'
    subnetId: networking.?outputs.?privateEndpointsSubnetId ?? ''
    privateDnsZoneId: privateDnsZones.?outputs.?storageFileDnsZoneId ?? ''
  }
}

module peAiServices './shared/private-endpoint.bicep' = if (enablePrivateEndpoints && deployAIFoundry) {
  name: 'pe-ai-services'
  scope: rg
  params: {
    name: 'pe-ai-${resourceToken}'
    location: location
    tags: tags
    serviceResourceId: aiFoundry.?outputs.?id ?? ''
    groupId: 'account'
    subnetId: networking.?outputs.?privateEndpointsSubnetId ?? ''
    privateDnsZoneId: privateDnsZones.?outputs.?cognitiveServicesDnsZoneId ?? ''
    // OpenAI SDK resolves to *.openai.azure.com, Agent Service to *.services.ai.azure.com
    additionalDnsZoneIds: [
      privateDnsZones.?outputs.?openaiDnsZoneId ?? ''
      privateDnsZones.?outputs.?servicesAiDnsZoneId ?? ''
    ]
  }
}

module peAiHub './shared/private-endpoint.bicep' = if (enablePrivateEndpoints && deployAIFoundry) {
  name: 'pe-ai-hub'
  scope: rg
  params: {
    name: 'pe-hub-${resourceToken}'
    location: location
    tags: tags
    serviceResourceId: aiFoundry.?outputs.?hubId ?? ''
    groupId: 'amlworkspace'
    subnetId: networking.?outputs.?privateEndpointsSubnetId ?? ''
    privateDnsZoneId: privateDnsZones.?outputs.?mlWorkspaceDnsZoneId ?? ''
    additionalDnsZoneIds: [
      privateDnsZones.?outputs.?mlNotebooksDnsZoneId ?? ''
    ]
  }
}

// NOTE: Private endpoints for ML projects are NOT supported — Azure requires
// PE operations on the Hub only. The Hub PE covers the project as well.

// Reference the deployed AI Foundry to get the key (only when deploying web with AI Foundry)
resource aiFoundryRef 'Microsoft.CognitiveServices/accounts@2024-10-01' existing = if (deployAIFoundry && !empty(containerImage)) {
  name: '${abbrs.cognitiveServicesAccounts}foundry-${resourceToken}'
  scope: rg
}

// Only deploy web container app if containerImage is provided
// The backend job in CI/CD handles container deployment separately
module web './app/web.bicep' = if (!empty(containerImage)) {
  name: 'web'
  scope: rg
  params: {
    name: '${abbrs.appContainerApps}web-${resourceToken}'
    location: location
    tags: tags
    containerAppsEnvironmentName: appsEnv.outputs.name
    containerRegistryName: registry.outputs.name
    imageName: containerImage
    // Get API key and endpoint from deployed AI Foundry, or fall back to provided parameters
    azureOpenAiApiKey: deployAIFoundry ? aiFoundryRef!.listKeys().key1 : azureOpenAiApiKey
    azureOpenAiEndpoint: deployAIFoundry ? (aiFoundry.?outputs.?endpoint ?? '') : azureOpenAiEndpoint
    openAiApiKey: openAiApiKey
    // Azure Maps subscription key for geocoding
    azureMapsSubscriptionKey: maps.outputs.primaryKey
    enableAuthentication: enableAuthentication
    microsoftEntraClientSecret: microsoftEntraClientSecret
    // Cloud environment
    cloudEnvironment: cloudEnvironment
    // AI Agent Service project endpoint
    azureAiProjectEndpoint: deployAIFoundry ? (aiFoundry.?outputs.?agentProjectEndpoint ?? '') : ''
    // Teams Bot credentials
    microsoftBotAppId: microsoftBotAppId
    microsoftBotAppPassword: microsoftBotAppPassword
  }
}

// Azure Bot Service for Teams integration (requires App Registration)
module botService './shared/bot-service.bicep' = if (deployBotService && !empty(microsoftBotAppId) && !empty(containerImage)) {
  name: 'bot-service'
  scope: rg
  params: {
    name: 'bot-${resourceToken}'
    tags: tags
    microsoftAppId: microsoftBotAppId
    messagingEndpoint: '${web.?outputs.?uri ?? ''}/api/messages'
    tenantId: tenant().tenantId
  }
}

output AZURE_LOCATION string = location
output AZURE_CONTAINER_REGISTRY_ENDPOINT string = registry.outputs.loginServer
output AZURE_CONTAINER_REGISTRY_NAME string = registry.outputs.name
output AZURE_CONTAINER_APPS_ENVIRONMENT_NAME string = appsEnv.outputs.name
output AZURE_CONTAINER_APP_NAME string = web.?outputs.?name ?? ''
output AZURE_CONTAINER_APP_URL string = web.?outputs.?uri ?? ''
// AI Foundry outputs
output AZURE_AI_FOUNDRY_NAME string = aiFoundry.?outputs.?name ?? ''
output AZURE_AI_FOUNDRY_ENDPOINT string = aiFoundry.?outputs.?endpoint ?? ''

// AI Agent Service outputs
output AZURE_AI_HUB_NAME string = aiFoundry.?outputs.?hubName ?? ''
output AZURE_AI_PROJECT_NAME string = aiFoundry.?outputs.?projectName ?? ''
output AZURE_AI_PROJECT_ENDPOINT string = aiFoundry.?outputs.?agentProjectEndpoint ?? ''

// Azure Maps outputs
output AZURE_MAPS_NAME string = maps.outputs.name
output AZURE_MAPS_CLIENT_ID string = maps.outputs.clientId
@description('Azure Maps subscription key for geocoding API calls')
output AZURE_MAPS_SUBSCRIPTION_KEY string = maps.outputs.primaryKey

// Bot Service outputs
output AZURE_BOT_SERVICE_NAME string = botService.?outputs.?botServiceName ?? ''
