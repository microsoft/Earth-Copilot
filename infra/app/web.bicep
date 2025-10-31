param name string
param location string = resourceGroup().location
param tags object = {}

param applicationInsightsName string = ''
param containerAppsEnvironmentName string
param containerRegistryName string
param imageName string = ''

@secure()
param azureOpenAiApiKey string = ''
param azureOpenAiEndpoint string = ''
@secure()
param openAiApiKey string = ''

// Authentication parameters
param enableAuthentication bool = true
param microsoftEntraClientId string = ''
param microsoftEntraTenantId string = ''
@secure()
param microsoftEntraClientSecret string = ''

resource containerAppsEnvironment 'Microsoft.App/managedEnvironments@2023-05-01' existing = {
  name: containerAppsEnvironmentName
}

resource containerRegistry 'Microsoft.ContainerRegistry/registries@2023-07-01' existing = {
  name: containerRegistryName
}

resource applicationInsights 'Microsoft.Insights/components@2020-02-02' existing = if (!empty(applicationInsightsName)) {
  name: applicationInsightsName
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
      secrets: concat([
        {
          name: 'azure-openai-api-key'
          value: azureOpenAiApiKey
        }
      ], !empty(openAiApiKey) ? [
        {
          name: 'openai-api-key'
          value: openAiApiKey
        }
      ] : [], !empty(applicationInsightsName) ? [
        {
          name: 'appinsights-cs'
          value: applicationInsights.properties.ConnectionString
        }
      ] : [], enableAuthentication && !empty(microsoftEntraClientSecret) ? [
        {
          name: 'microsoft-client-secret'
          value: microsoftEntraClientSecret
        }
      ] : [])
      auth: enableAuthentication && !empty(microsoftEntraClientId) ? {
        platform: {
          enabled: true
        }
        globalValidation: {
          unauthenticatedClientAction: 'RedirectToLoginPage'
          redirectToProvider: 'azureactivedirectory'
        }
        identityProviders: {
          azureActiveDirectory: {
            enabled: true
            registration: {
              clientId: microsoftEntraClientId
              clientSecretSettingName: 'microsoft-client-secret'
              openIdIssuer: 'https://login.microsoftonline.com/${microsoftEntraTenantId}/v2.0'
            }
            validation: {
              allowedAudiences: [
                'api://${microsoftEntraClientId}'
              ]
            }
            login: {
              loginParameters: [
                'prompt=select_account'
                'domain_hint=organizations'
              ]
            }
          }
        }
      } : null
    }
    template: {
      containers: [
        {
          image: !empty(imageName) ? imageName : 'mcr.microsoft.com/azuredocs/containerapps-helloworld:latest'
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
              name: 'AZURE_OPENAI_API_KEY'
              secretRef: 'azure-openai-api-key'
            }
            {
              name: 'STAC_API_URL'
              value: 'https://planetarycomputer.microsoft.com/api/stac/v1'
            }
            {
              name: 'CORS_ORIGINS'
              value: 'https://${name}.azurecontainerapps.io'
            }
          ], !empty(openAiApiKey) ? [
            {
              name: 'OPENAI_API_KEY'
              secretRef: 'openai-api-key'
            }
          ] : [], !empty(applicationInsightsName) ? [
            {
              name: 'APPLICATION_INSIGHTS_CONNECTION_STRING'
              secretRef: 'appinsights-cs'
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
        minReplicas: 1
        maxReplicas: 10
        rules: [
          {
            name: 'http-rule'
            http: {
              requests: 100
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
