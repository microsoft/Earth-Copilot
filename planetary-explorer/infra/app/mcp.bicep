// MCP server Container App (in-repo planetary-explorer MCP server).
// Wraps the Planetary Explorer backend `/api/query` as MCP tools so VS Code Copilot
// / Claude Desktop / Cursor can talk to a deployed Planetary Explorer environment
// over the Model Context Protocol.
//
// One MCP server per environment — point it at the matching backend FQDN.
//   prod  → ca-mcp-planetaryexplorer       → ca-planetaryexplorer-api
//   dev   → ca-mcp-planetaryexplorer-dev   → ca-planetaryexplorer-api-dev

param name string
param location string = resourceGroup().location
param tags object = {}

param containerAppsEnvironmentName string
param containerRegistryName string

@description('Container image for the MCP server (e.g. planetary-explorer-mcp:latest)')
param imageName string

@description('Full URL (no trailing slash) of the Planetary Explorer backend this MCP server should call. Example: https://ca-planetaryexplorer-api-dev.<env-fqdn>.azurecontainerapps.io')
param planetaryExplorerApiUrl string

@description('Shared API key required on inbound MCP requests via the X-API-Key header. Empty disables key auth (NOT recommended outside a private network).')
@secure()
param mcpApiKey string = ''

resource containerAppsEnvironment 'Microsoft.App/managedEnvironments@2023-05-01' existing = {
  name: containerAppsEnvironmentName
}

resource containerRegistry 'Microsoft.ContainerRegistry/registries@2023-07-01' existing = {
  name: containerRegistryName
}

resource app 'Microsoft.App/containerApps@2023-05-01' = {
  name: name
  location: location
  tags: union(tags, { 'azd-service-name': 'mcp' })
  identity: {
    type: 'SystemAssigned'
  }
  properties: {
    managedEnvironmentId: containerAppsEnvironment.id
    configuration: {
      ingress: {
        external: true
        targetPort: 8080
        allowInsecure: false
        traffic: [
          {
            latestRevision: true
            weight: 100
          }
        ]
      }
      registries: [
        {
          server: containerRegistry.properties.loginServer
          identity: 'system'
        }
      ]
      secrets: !empty(mcpApiKey) ? [
        {
          name: 'mcp-api-key'
          value: mcpApiKey
        }
      ] : []
    }
    template: {
      containers: [
        {
          name: 'mcp'
          image: '${containerRegistry.properties.loginServer}/${imageName}'
          resources: {
            cpu: json('0.5')
            memory: '1Gi'
          }
          env: concat([
            {
              name: 'PLANETARY_EXPLORER_API_URL'
              value: planetaryExplorerApiUrl
            }
            {
              // mcp_bridge.py reads this; it's the upstream Planetary Explorer backend
              // the bridge proxies tool calls to.
              name: 'PLANETARY_EXPLORER_BASE_URL'
              value: planetaryExplorerApiUrl
            }
            {
              name: 'HOST'
              value: '0.0.0.0'
            }
            {
              name: 'PORT'
              value: '8080'
            }
          ], !empty(mcpApiKey) ? [
            {
              name: 'MCP_API_KEY'
              secretRef: 'mcp-api-key'
            }
          ] : [])
        }
      ]
      scale: {
        minReplicas: 0
        maxReplicas: 2
      }
    }
  }
}

// Grant the MCP container's managed identity AcrPull on the registry so it
// can pull the image without admin creds.
resource acrPullRole 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(app.id, containerRegistry.id, 'AcrPull')
  scope: containerRegistry
  properties: {
    roleDefinitionId: subscriptionResourceId(
      'Microsoft.Authorization/roleDefinitions',
      '7f951dda-4ed3-4680-a7ca-43fe172d538d'
    )
    principalId: app.identity.principalId
    principalType: 'ServicePrincipal'
  }
}

output name string = app.name
output uri string = 'https://${app.properties.configuration.ingress.fqdn}'
output fqdn string = app.properties.configuration.ingress.fqdn
