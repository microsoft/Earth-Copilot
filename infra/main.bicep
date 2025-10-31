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
    applicationInsightsName: monitoring.outputs.applicationInsightsName
    logAnalyticsWorkspaceName: monitoring.outputs.logAnalyticsWorkspaceName
  }
}

module web './app/web.bicep' = {
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
    azureOpenAiApiKey: azureOpenAiApiKey
    azureOpenAiEndpoint: azureOpenAiEndpoint
    openAiApiKey: openAiApiKey
    enableAuthentication: enableAuthentication
    microsoftEntraClientId: microsoftEntraClientId
    microsoftEntraTenantId: microsoftEntraTenantId
    microsoftEntraClientSecret: microsoftEntraClientSecret
  }
}

output AZURE_LOCATION string = location
output AZURE_CONTAINER_REGISTRY_ENDPOINT string = registry.outputs.loginServer
output AZURE_CONTAINER_REGISTRY_NAME string = registry.outputs.name
output AZURE_CONTAINER_APPS_ENVIRONMENT_NAME string = appsEnv.outputs.name
output AZURE_CONTAINER_APP_NAME string = web.outputs.name
output AZURE_CONTAINER_APP_URL string = web.outputs.uri
output AZURE_APPLICATION_INSIGHTS_NAME string = monitoring.outputs.applicationInsightsName
