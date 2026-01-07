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
@description('Deploy Azure AI Foundry (OpenAI) with GPT-4 model')
param deployAIFoundry bool = true

@description('Deploy Azure AI Services (multi-service)')
param deployAIServices bool = true

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

module monitoring './shared/monitoring.bicep' = {
  name: 'monitoring'
  scope: rg
  params: {
    location: location
    tags: tags
    logAnalyticsName: '${abbrs.operationalInsightsWorkspaces}${resourceToken}'
    applicationInsightsName: '${abbrs.insightsComponents}${resourceToken}'
  }
}

module registry './shared/registry.bicep' = {
  name: 'registry'
  scope: rg
  params: {
    location: location
    tags: tags
    name: '${abbrs.containerRegistryRegistries}${resourceToken}'
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
  }
}

// Azure AI Foundry (OpenAI) with GPT-4 model
module aiFoundry './shared/ai-foundry.bicep' = if (deployAIFoundry) {
  name: 'ai-foundry'
  scope: rg
  params: {
    name: '${abbrs.cognitiveServicesAccounts}foundry-${resourceToken}'
    location: location
    tags: tags
    deployModels: true
  }
}

// Azure AI Services (multi-service cognitive services)
module aiServices './shared/ai-services.bicep' = if (deployAIServices) {
  name: 'ai-services'
  scope: rg
  params: {
    name: '${abbrs.cognitiveServicesAccounts}services-${resourceToken}'
    location: location
    tags: tags
  }
}

// Reference the deployed AI Foundry to get the key (only when deploying web with AI Foundry)
resource aiFoundryRef 'Microsoft.CognitiveServices/accounts@2023-05-01' existing = if (deployAIFoundry && !empty(containerImage)) {
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
    applicationInsightsName: monitoring.outputs.applicationInsightsName
    imageName: containerImage
    // Get API key and endpoint from deployed AI Foundry, or fall back to provided parameters
    azureOpenAiApiKey: deployAIFoundry ? aiFoundryRef.listKeys().key1 : azureOpenAiApiKey
    azureOpenAiEndpoint: deployAIFoundry ? aiFoundry.outputs.endpoint : azureOpenAiEndpoint
    openAiApiKey: openAiApiKey
    enableAuthentication: enableAuthentication
    microsoftEntraClientSecret: microsoftEntraClientSecret
  }
  dependsOn: [
    aiFoundry
  ]
}

output AZURE_LOCATION string = location
output AZURE_CONTAINER_REGISTRY_ENDPOINT string = registry.outputs.loginServer
output AZURE_CONTAINER_REGISTRY_NAME string = registry.outputs.name
output AZURE_CONTAINER_APPS_ENVIRONMENT_NAME string = appsEnv.outputs.name
output AZURE_CONTAINER_APP_NAME string = web.?outputs.?name ?? ''
output AZURE_CONTAINER_APP_URL string = web.?outputs.?uri ?? ''
output AZURE_APPLICATION_INSIGHTS_NAME string = monitoring.outputs.applicationInsightsName

// AI Foundry outputs
output AZURE_AI_FOUNDRY_NAME string = aiFoundry.?outputs.?name ?? ''
output AZURE_AI_FOUNDRY_ENDPOINT string = aiFoundry.?outputs.?endpoint ?? ''

// AI Services outputs
output AZURE_AI_SERVICES_NAME string = aiServices.?outputs.?name ?? ''
output AZURE_AI_SERVICES_ENDPOINT string = aiServices.?outputs.?endpoint ?? ''
