// Azure Bot Service for Teams integration with Earth Copilot
// Deploys a single-tenant Azure Bot and enables the Microsoft Teams channel.

param name string
param location string = 'global' // Bot Service is always deployed globally
param tags object = {}

@description('Microsoft App ID from the Entra ID App Registration')
param microsoftAppId string

@description('HTTPS endpoint that receives Bot Framework activities (Container App URL + /api/messages)')
param messagingEndpoint string

@description('Entra ID tenant for single-tenant bot authentication')
param tenantId string

resource botService 'Microsoft.BotService/botServices@2022-09-15' = {
  name: name
  location: location
  tags: tags
  sku: {
    name: 'F0' // Free tier — sufficient for most internal use
  }
  kind: 'azurebot'
  properties: {
    displayName: 'Earth Copilot'
    description: 'Geospatial intelligence assistant — search 113+ satellite collections and analyze terrain using natural language.'
    endpoint: messagingEndpoint
    msaAppId: microsoftAppId
    msaAppType: 'SingleTenant'
    msaAppTenantId: tenantId
    schemaTransformationVersion: '1.3'
  }
}

// Enable Microsoft Teams channel
resource teamsChannel 'Microsoft.BotService/botServices/channels@2022-09-15' = {
  parent: botService
  name: 'MsTeamsChannel'
  location: location
  properties: {
    channelName: 'MsTeamsChannel'
    properties: {
      isEnabled: true
    }
  }
}

output botServiceName string = botService.name
output botServiceId string = botService.id
