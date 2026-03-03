param location string = resourceGroup().location
param tags object = {}

param name string
param sku object = {
  name: 'S0'
}

@description('Deploy AI models')
param deployModels bool = true

@description('Deploy GPT-5 model (requires GlobalStandard SKU quota — set to false if unavailable in your region)')
param deployGpt5 bool = true

@description('Deploy AI Agent Service (Hub + Project)')
param deployAgentService bool = true

@description('Hub name for AI Foundry Agent Service')
param hubName string = ''

@description('Project name for AI Foundry Agent Service')
param projectName string = ''

@description('Storage Account ID (required for Hub)')
param storageAccountId string = ''

@description('Key Vault ID (required for Hub)')
param keyVaultId string = ''

@description('Cloud environment: Commercial or Government')
@allowed(['Commercial', 'Government'])
param cloudEnvironment string = 'Commercial'

@description('Enable private endpoints — disables public access')
param enablePrivateEndpoints bool = false

// Determine the AI Services domain suffix based on cloud environment
var aiServicesDomainSuffix = cloudEnvironment == 'Government' ? 'services.ai.azure.us' : 'services.ai.azure.com'

// Azure AI Foundry resource (formerly Azure AI Services)
// This provides access to the Model Catalog with multiple models
resource aiFoundry 'Microsoft.CognitiveServices/accounts@2025-04-01-preview' = {
  name: name
  location: location
  tags: tags
  kind: 'AIServices'  // AIServices provides access to Model Catalog
  sku: sku
  identity: {
    type: 'SystemAssigned'
  }
  properties: {
    customSubDomainName: name
    allowProjectManagement: true  // Required for Agent Service CogSvc project sub-resources
    // NOTE: Do NOT set 'restore: true' here. It conflicts with active resources and
    // cannot be conditionally toggled in Bicep. Instead, the CI/CD pipeline handles
    // purging soft-deleted accounts before deployment (see deploy.yml).
    // When private endpoints are enabled, disable public access and deny by default.
    // Both privatelink.cognitiveservices.azure.com AND privatelink.openai.azure.com
    // DNS zones must exist for the PE to work (OpenAI SDK uses the openai subdomain).
    publicNetworkAccess: enablePrivateEndpoints ? 'Disabled' : 'Enabled'
    disableLocalAuth: true  // Use AAD/MI auth only
    networkAcls: {
      defaultAction: enablePrivateEndpoints ? 'Deny' : 'Allow'
    }
  }
}

// Deploy GPT-4o model
resource gpt4oDeployment 'Microsoft.CognitiveServices/accounts/deployments@2024-10-01' = if (deployModels) {
  parent: aiFoundry
  name: 'gpt-4o'
  sku: {
    name: 'Standard'
    capacity: 10  // 10K TPM — conservative default to avoid quota failures on new subscriptions
  }
  properties: {
    model: {
      format: 'OpenAI'
      name: 'gpt-4o'
      version: '2024-11-20'
    }
    versionUpgradeOption: 'OnceNewDefaultVersionAvailable'
  }
}

// Deploy GPT-4o-mini model (faster, cheaper option)
resource gpt4oMiniDeployment 'Microsoft.CognitiveServices/accounts/deployments@2024-10-01' = if (deployModels) {
  parent: aiFoundry
  name: 'gpt-4o-mini'
  sku: {
    name: 'Standard'
    capacity: 10  // 10K TPM — conservative default to avoid quota failures on new subscriptions
  }
  properties: {
    model: {
      format: 'OpenAI'
      name: 'gpt-4o-mini'
      version: '2024-07-18'
    }
    versionUpgradeOption: 'OnceNewDefaultVersionAvailable'
  }
  dependsOn: [
    gpt4oDeployment
  ]
}

// Deploy GPT-5 model (default model — GlobalStandard SKU required)
// Set deployGpt5=false if gpt-5 is not available in your region/subscription.
// The deploy workflow will auto-select the best available model (gpt-5 > gpt-4o > gpt-4o-mini).
resource gpt5Deployment 'Microsoft.CognitiveServices/accounts/deployments@2024-10-01' = if (deployModels && deployGpt5) {
  parent: aiFoundry
  name: 'gpt-5'
  sku: {
    name: 'GlobalStandard'
    capacity: 10
  }
  properties: {
    model: {
      format: 'OpenAI'
      name: 'gpt-5'
      version: '2025-08-07'
    }
    versionUpgradeOption: 'OnceNewDefaultVersionAvailable'
  }
  dependsOn: [
    gpt4oMiniDeployment
  ]
}

// Additional models from Model Catalog (Llama, Phi, etc.) can be added as needed

// =========================================
// AI Foundry Hub + Project (Agent Service)
// =========================================

// AI Foundry Hub - central workspace for AI resources
// Required for Azure AI Agent Service to function
@description('Application Insights resource ID (required for Hub — cannot be removed once set)')
param applicationInsightsId string = ''

resource hub 'Microsoft.MachineLearningServices/workspaces@2024-10-01' = if (deployAgentService && !empty(hubName)) {
  name: hubName
  location: location
  tags: tags
  kind: 'Hub'
  identity: {
    type: 'SystemAssigned'
  }
  properties: {
    friendlyName: 'Earth Copilot AI Hub'
    storageAccount: storageAccountId
    keyVault: keyVaultId
    // Application Insights cannot be detached once set — always include it if provided
    applicationInsights: !empty(applicationInsightsId) ? applicationInsightsId : null
    publicNetworkAccess: enablePrivateEndpoints ? 'Disabled' : 'Enabled'
  }
  dependsOn: [
    aiFoundry
  ]
}

// Connect AI Services account to the Hub using Managed Identity (AAD auth)
// Note: Uses AAD instead of ApiKey because disableLocalAuth may be enabled
resource aiServicesConnection 'Microsoft.MachineLearningServices/workspaces/connections@2024-10-01' = if (deployAgentService && !empty(hubName)) {
  parent: hub
  name: 'Default_AIServices'
  properties: {
    category: 'AIServices'
    target: aiFoundry.properties.endpoint
    authType: 'AAD'
    isSharedToAll: true
    metadata: {
      ApiType: 'Azure'
      ResourceId: aiFoundry.id
    }
  }
}

// AI Foundry Project - required endpoint for Agent Service API
resource project 'Microsoft.MachineLearningServices/workspaces@2024-10-01' = if (deployAgentService && !empty(projectName)) {
  name: projectName
  location: location
  tags: tags
  kind: 'Project'
  identity: {
    type: 'SystemAssigned'
  }
  properties: {
    friendlyName: 'Earth Copilot Agent Project'
    hubResourceId: hub.id
    publicNetworkAccess: enablePrivateEndpoints ? 'Disabled' : 'Enabled'
  }
  dependsOn: [
    aiServicesConnection
  ]
}

// =========================================
// Agent Service: CogSvc Project + Capability Hosts
// The Agent Service requires a project sub-resource under the CognitiveServices
// account (NOT the ML workspace project) and capability hosts at both the
// account and project level.
// =========================================

@description('Name for the CogSvc Agent project sub-resource')
param agentProjectName string = 'earth-copilot-agents'

// CogSvc project sub-resource (required for Agent Service API endpoint)
resource agentProject 'Microsoft.CognitiveServices/accounts/projects@2025-04-01-preview' = if (deployAgentService) {
  parent: aiFoundry
  name: agentProjectName
  location: location
  identity: {
    type: 'SystemAssigned'
  }
  properties: {
    description: 'Earth Copilot GEOINT Agent Project'
    displayName: 'Earth Copilot Agents'
  }
  dependsOn: [
    project // Ensure ML workspace project is created first
  ]
}

// Account-level capability host (enables Agent Service on the account)
resource accountCapabilityHost 'Microsoft.CognitiveServices/accounts/capabilityHosts@2025-04-01-preview' = if (deployAgentService) {
  name: 'default'
  parent: aiFoundry
  properties: {
    capabilityHostKind: 'Agents'
  }
  dependsOn: [
    agentProject
  ]
}

// Project-level capability host (enables Agent Service on the project)
resource projectCapabilityHost 'Microsoft.CognitiveServices/accounts/projects/capabilityHosts@2025-04-01-preview' = if (deployAgentService) {
  name: 'default'
  parent: agentProject
  properties: {
    capabilityHostKind: 'Agents'
  }
  dependsOn: [
    accountCapabilityHost
  ]
}

output name string = aiFoundry.name
output endpoint string = aiFoundry.properties.endpoint
output id string = aiFoundry.id

// Agent Service outputs
output hubName string = (deployAgentService && !empty(hubName)) ? hub.name : ''
output hubId string = (deployAgentService && !empty(hubName)) ? hub.id : ''
output projectName string = (deployAgentService && !empty(projectName)) ? project.name : ''
output projectId string = (deployAgentService && !empty(projectName)) ? project.id : ''
output projectDiscoveryUrl string = (deployAgentService && !empty(projectName)) ? project.properties.discoveryUrl : ''

// CogSvc Agent project endpoint (correct format for Agent Service SDK)
output agentProjectEndpoint string = deployAgentService ? 'https://${name}.${aiServicesDomainSuffix}/api/projects/${agentProjectName}' : ''
