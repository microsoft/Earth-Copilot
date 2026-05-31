// Public Container App running the weather-stub server. This is a
// **CPU-only** mock of Microsoft Aurora + NVIDIA Earth-2 FCN scoring
// endpoints, used to prove the Forecast Agent wiring end-to-end
// without GPU quota.
//
// When real GPU endpoints come online, leave this in place for dev
// (it's nearly free at scale-to-zero) and point the backend's
// ``AURORA_ENDPOINT_URL`` and ``EARTH2_FCN_ENDPOINT_URL`` at the
// production endpoints instead. The HTTP contract is identical.

param name string
param location string = resourceGroup().location
param tags object = {}

param containerAppsEnvironmentName string
param containerRegistryName string

@description('Container image (e.g. planetary-explorer-weather-stub:latest).')
param imageName string

@description('Bearer token clients must present. Stored as a Container Apps secret; leave empty to disable auth.')
@secure()
param stubApiKey string = ''

@description('Min replicas. 0 = scale-to-zero (cold start ~1s, near-zero idle cost).')
@minValue(0)
@maxValue(5)
param minReplicas int = 0

@description('Max replicas.')
@minValue(1)
@maxValue(10)
param maxReplicas int = 2

resource containerAppsEnvironment 'Microsoft.App/managedEnvironments@2023-05-01' existing = {
  name: containerAppsEnvironmentName
}

resource containerRegistry 'Microsoft.ContainerRegistry/registries@2023-07-01' existing = {
  name: containerRegistryName
}

resource app 'Microsoft.App/containerApps@2023-05-01' = {
  name: name
  location: location
  tags: union(tags, { 'azd-service-name': 'weather-stub' })
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
        transport: 'auto'
        traffic: [
          {
            latestRevision: true
            weight: 100
          }
        ]
      }
      secrets: empty(stubApiKey) ? [] : [
        {
          name: 'stub-api-key'
          value: stubApiKey
        }
      ]
      registries: [
        {
          server: containerRegistry.properties.loginServer
          identity: 'system'
        }
      ]
    }
    template: {
      containers: [
        {
          name: 'weather-stub'
          image: '${containerRegistry.properties.loginServer}/${imageName}'
          resources: {
            cpu: json('0.25')
            memory: '0.5Gi'
          }
          env: concat(
            [
              {
                name: 'HOST'
                value: '0.0.0.0'
              }
              {
                name: 'PORT'
                value: '8080'
              }
            ],
            empty(stubApiKey) ? [] : [
              {
                name: 'STUB_API_KEY'
                secretRef: 'stub-api-key'
              }
            ]
          )
          probes: [
            {
              type: 'Liveness'
              httpGet: {
                path: '/health'
                port: 8080
              }
              periodSeconds: 30
              failureThreshold: 3
            }
            {
              type: 'Readiness'
              httpGet: {
                path: '/health'
                port: 8080
              }
              periodSeconds: 10
              failureThreshold: 3
              initialDelaySeconds: 5
            }
          ]
        }
      ]
      scale: {
        minReplicas: minReplicas
        maxReplicas: maxReplicas
      }
    }
  }
}

resource acrPullRole 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(app.id, containerRegistry.id, 'AcrPull')
  scope: containerRegistry
  properties: {
    roleDefinitionId: subscriptionResourceId(
      'Microsoft.Authorization/roleDefinitions',
      '7f951dda-4ed3-4680-a7ca-43fe172d538d' // AcrPull
    )
    principalId: app.identity.principalId
    principalType: 'ServicePrincipal'
  }
}

output name string = app.name
output fqdn string = app.properties.configuration.ingress.fqdn
output uri string = 'https://${app.properties.configuration.ingress.fqdn}'
