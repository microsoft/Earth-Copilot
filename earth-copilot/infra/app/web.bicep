param name string
param location string = resourceGroup().location
param tags object = {}

param containerAppsEnvironmentName string
param containerRegistryName string
param imageName string = ''
param frontendUrl string = '' // Frontend Web App URL for CORS

@secure()
param azureOpenAiApiKey string = ''
param azureOpenAiEndpoint string = ''
@secure()
param openAiApiKey string = ''
@secure()
param azureMapsSubscriptionKey string = ''

// AI Agent Service
param azureAiProjectEndpoint string = ''

// Teams Bot credentials
param microsoftBotAppId string = ''
@secure()
param microsoftBotAppPassword string = ''

// Authentication parameters
param enableAuthentication bool = false
@secure()
param microsoftEntraClientSecret string = ''

// Cloud environment
@description('Cloud environment: Commercial or Government')
@allowed(['Commercial', 'Government'])
param cloudEnvironment string = 'Commercial'

resource containerAppsEnvironment 'Microsoft.App/managedEnvironments@2023-05-01' existing = {
  name: containerAppsEnvironmentName
}

resource containerRegistry 'Microsoft.ContainerRegistry/registries@2023-07-01' existing = {
  name: containerRegistryName
}

resource app 'Microsoft.App/containerApps@2023-05-01' = {
  name: name
  location: location
  tags: union(tags, { 'azd-service-name': 'web' })
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
      secrets: concat(!empty(azureMapsSubscriptionKey) ? [
        {
          name: 'azure-maps-key'
          value: azureMapsSubscriptionKey
        }
      ] : [], !empty(microsoftBotAppPassword) ? [
        {
          name: 'microsoft-bot-password'
          value: microsoftBotAppPassword
        }
      ] : [], !empty(azureOpenAiApiKey) ? [
        {
          name: 'azure-openai-api-key'
          value: azureOpenAiApiKey
        }
      ] : [], !empty(openAiApiKey) ? [
        {
          name: 'openai-api-key'
          value: openAiApiKey
        }
      ] : [], enableAuthentication && !empty(microsoftEntraClientSecret) ? [
        {
          name: 'microsoft-client-secret'
          value: microsoftEntraClientSecret
        }
      ] : [])
    }
    template: {
      containers: [
        {
          image: imageName
          name: 'web'
          env: concat([
            {
              name: 'PORT'
              value: '8080'
            }
            {
              name: 'AZURE_OPENAI_ENDPOINT'
              value: azureOpenAiEndpoint
            }
            {
              // CRITICAL: Enable Managed Identity authentication for Azure OpenAI
              // This prevents 503 errors when container restarts
              name: 'USE_MANAGED_IDENTITY'
              value: 'true'
            }
            {
              // Cloud environment: Commercial or Government
              // Drives all endpoint/scope resolution in cloud_config.py
              name: 'AZURE_CLOUD_ENVIRONMENT'
              value: cloudEnvironment
            }
            {
              name: 'STAC_API_URL'
              value: 'https://planetarycomputer.microsoft.com/api/stac/v1'
            }
            {
              name: 'CORS_ORIGINS'
              value: '*'  // Allow all origins - can be restricted to specific domains in production
            }
          ], !empty(azureAiProjectEndpoint) ? [
            {
              name: 'AZURE_AI_PROJECT_ENDPOINT'
              value: azureAiProjectEndpoint
            }          ] : [], !empty(microsoftBotAppId) ? [
            {
              name: 'MICROSOFT_APP_ID'
              value: microsoftBotAppId
            }
          ] : [], !empty(microsoftBotAppPassword) ? [
            {
              name: 'MICROSOFT_APP_PASSWORD'
              secretRef: 'microsoft-bot-password'
            }          ] : [], !empty(azureMapsSubscriptionKey) ? [
            {
              name: 'AZURE_MAPS_SUBSCRIPTION_KEY'
              secretRef: 'azure-maps-key'
            }
          ] : [], !empty(azureOpenAiApiKey) ? [
            {
              name: 'AZURE_OPENAI_API_KEY'
              secretRef: 'azure-openai-api-key'
            }
          ] : [], !empty(openAiApiKey) ? [
            {
              name: 'OPENAI_API_KEY'
              secretRef: 'openai-api-key'
            }
          ] : [])
          resources: {
            cpu: json('1.0')
            memory: '2Gi'
          }
          probes: [
            {
              type: 'Liveness'
              httpGet: {
                path: '/health'
                port: 8080
              }
              initialDelaySeconds: 30
              periodSeconds: 10
              timeoutSeconds: 5
              failureThreshold: 3
            }
            {
              type: 'Readiness'
              httpGet: {
                path: '/health'
                port: 8080
              }
              initialDelaySeconds: 10
              periodSeconds: 5
              timeoutSeconds: 3
              failureThreshold: 3
            }
          ]
        }
      ]
      scale: {
        minReplicas: 1  // Start with 1 replica; scales up automatically under load
        maxReplicas: 10
        rules: [
          {
            name: 'http-rule'
            http: {
              metadata: {
                concurrentRequests: '10'  // Scale up early - trigger at 10 requests per replica
              }
            }
          }
        ]
      }
    }
  }
}

// Grant ACR pull permissions to the container app
resource acrPullRole 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(subscription().id, resourceGroup().id, app.name, 'acrPull')
  scope: containerRegistry
  properties: {
    principalId: app.identity.principalId
    principalType: 'ServicePrincipal'
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', '7f951dda-4ed3-4680-a7ca-43fe172d538d') // AcrPull role
  }
}

output name string = app.name
output uri string = 'https://${app.properties.configuration.ingress.fqdn}'
