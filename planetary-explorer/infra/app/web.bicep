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
//
// AUTH ARCHITECTURE NOTE (2026-05):
// This Container App intentionally does NOT define a `Microsoft.App/containerApps/authConfigs`
// child resource. Token validation is performed in-process by `auth_middleware.py`
// (EntraAuthMiddleware), which validates Bearer tokens issued for the Web/SPA AAD app
// (env var AZURE_AD_CLIENT_ID — set per deployment).
//
// Do NOT add Container Apps Easy Auth (platform-level authConfig) here. Doing so creates a
// 3-way mismatch (SPA token aud != Easy Auth clientId) and blocks the SPA from reaching the
// backend. If platform-level auth is ever required, ensure its `clientId` exactly matches
// the SPA token audience and remove the in-app middleware to avoid double-validation.
//
// `enableAuthentication` and `microsoftEntraClientSecret` below are legacy params retained
// only for parameter-file compatibility; they currently only gate a secret entry, not an
// authConfig resource.
param enableAuthentication bool = false
@secure()
param microsoftEntraClientSecret string = ''

// Cloud environment
@description('Cloud environment: Commercial or Government')
@allowed(['Commercial', 'Government'])
param cloudEnvironment string = 'Commercial'

@description('Internal URL of the MPC Pro MCP sidecar (e.g. https://<fqdn>). Empty when the sidecar is not deployed; the backend falls back to the legacy direct-STAC path regardless of the USE_MPC_MCP flag.')
param mpcMcpUrl string = ''

@description('Feature flag toggling MCP-first catalog inventory in pro_stac_client.get_pro_collection_ids. ``false`` leaves the backend on the legacy direct-STAC path even when mpcMcpUrl is set (safe default).')
@allowed(['true', 'false'])
param useMpcMcp string = 'false'

// UI feature flags surfaced via /api/config so the frontend can show or
// lock controls without redeploying the bundle. These are independent of
// the deploy* flags on the infra side — e.g. an operator can deploy the
// MPC Pro sidecar but keep enableMpcPro=false until validation is done.
@description('Master switch for Microsoft Fabric integration. Surfaced to the UI via /api/config.features.fabric and to the backend via PE_FEATURE_FABRIC.')
param enableFabric bool = false

@description('Surface the MPC Pro toggle in the UI. When false the StacModeToggle renders Pro as a locked control. Surfaced as PE_FEATURE_MPC_PRO.')
param enableMpcPro bool = false

@description('STAC API base URL for the private GeoCatalog (MPC Pro). Surfaced to the API container as MPC_PRO_STAC_URL. Empty disables the Pro path even if enableMpcPro=true.')
param mpcProStacUrl string = ''

@description('Fabric workspace ID containing the lakehouse the backend queries. Surfaced as FABRIC_LAKEHOUSE_WORKSPACE_ID.')
param fabricWorkspaceId string = ''

@description('Fabric lakehouse ID inside ``fabricWorkspaceId``. Surfaced as FABRIC_LAKEHOUSE_ID.')
param fabricLakehouseId string = ''

@description('Dynamic collection selector mode. off | shadow | v2. When v2, the natural-language -> STAC collection id mapping uses the live CollectionIndex + constrained-LLM pick pipeline instead of the legacy LoadAgent prompt catalog. Surfaced as COLLECTION_SELECTOR.')
@allowed([ 'off', 'shadow', 'v2' ])
param collectionSelectorMode string = 'v2'

@description('When true, the v2 selector returns a clarify Selection on low-confidence / tied top-1/top-2 picks. Surfaced as COLLECTION_SELECTOR_DISAMBIGUATE.')
param collectionSelectorDisambiguate bool = true

// Forecast Agent wiring. URLs are pulled from Key Vault at container start via
// secretRef (system MI must hold Key Vault Secrets User on the vault) so that
// rotating Aurora / Earth-2 / MAI Weather endpoints is a single keyvault secret
// set, not a redeploy. Empty keyVaultName disables the wiring entirely.
@description('Key Vault name hosting forecast provider URL secrets. Empty disables KV-backed forecast wiring.')
param keyVaultName string = ''

@description('Key Vault URI (https://<name>.vault.azure.net/). Required when keyVaultName is set.')
param keyVaultUri string = ''

@description('Master switch for the Forecast Agent. Surfaced as FORECAST_AGENT_ENABLED ("1"/"0").')
param forecastAgentEnabled bool = true

@description('True when aurora-endpoint-url secret exists in the vault. Gates the Container App secret + env var so we never reference a non-existent KV secret.')
param auroraEndpointUrlConfigured bool = false

@description('True when earth2-fcn-endpoint-url secret exists in the vault.')
param earth2FcnEndpointUrlConfigured bool = false

@description('True when mai-weather-endpoint-url secret exists in the vault.')
param maiWeatherEndpointUrlConfigured bool = false

@description('Scoring path for MAI Weather. Plain env var (not secret).')
param maiWeatherScorePath string = '/mai-weather/score'

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
      ] : [],
      // Forecast Agent provider URLs sourced from Key Vault via system MI.
      // The vault must already hold these secrets and grant Key Vault
      // Secrets User to this container app's MI (handled in main.bicep).
      (!empty(keyVaultName) && auroraEndpointUrlConfigured) ? [
        {
          name: 'aurora-endpoint-url'
          keyVaultUrl: '${keyVaultUri}secrets/aurora-endpoint-url'
          identity: 'system'
        }
      ] : [],
      (!empty(keyVaultName) && earth2FcnEndpointUrlConfigured) ? [
        {
          name: 'earth2-fcn-endpoint-url'
          keyVaultUrl: '${keyVaultUri}secrets/earth2-fcn-endpoint-url'
          identity: 'system'
        }
      ] : [],
      (!empty(keyVaultName) && maiWeatherEndpointUrlConfigured) ? [
        {
          name: 'mai-weather-endpoint-url'
          keyVaultUrl: '${keyVaultUri}secrets/mai-weather-endpoint-url'
          identity: 'system'
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
            {
              // MPC Pro MCP sidecar URL (internal Container Apps FQDN). Empty
              // disables the MCP-first catalog inventory path regardless of
              // USE_MPC_MCP; the backend falls back to direct STAC calls.
              name: 'MPC_MCP_URL'
              value: mpcMcpUrl
            }
            {
              name: 'USE_MPC_MCP'
              value: useMpcMcp
            }
            {
              // UI feature flags. Read by the backend's /api/config
              // endpoint and reflected to the SPA so it can lock controls
              // for features that are intentionally disabled in this
              // deployment. Use 'true' / 'false' string values so env-var
              // -> bool conversion is unambiguous across runtimes.
              name: 'PE_FEATURE_FABRIC'
              value: enableFabric ? 'true' : 'false'
            }
            {
              name: 'PE_FEATURE_MPC_PRO'
              value: enableMpcPro ? 'true' : 'false'
            }
            {
              // Private GeoCatalog STAC base URL (MPC Pro). Backend reads
              // this in pro_stac_client.py and fastapi_app.py. Container
              // app's managed identity must have the GeoCatalog Reader role
              // on the target catalog so the token request succeeds.
              name: 'MPC_PRO_STAC_URL'
              value: mpcProStacUrl
            }
            {
              // Fabric lakehouse coordinates. Empty values are treated by
              // the backend (agents/resilience/data_loader.py) as "feature
              // unconfigured" and force a fallback to bundled seed data.
              name: 'FABRIC_LAKEHOUSE_WORKSPACE_ID'
              value: fabricWorkspaceId
            }
            {
              name: 'FABRIC_LAKEHOUSE_ID'
              value: fabricLakehouseId
            }
            {
              // Dynamic collection selector. off = legacy LoadAgent prompt
              // catalog (deprecated). shadow = run v2 alongside legacy and
              // log the diff. v2 = v2 is authoritative; LoadAgent picks
              // are overridden with the constrained-LLM choice over the
              // live MPC catalog. See collection_selector.py.
              name: 'COLLECTION_SELECTOR'
              value: collectionSelectorMode
            }
            {
              name: 'COLLECTION_SELECTOR_DISAMBIGUATE'
              value: collectionSelectorDisambiguate ? 'on' : 'off'
            }
            {
              // Pipeline V2 shadow mode: when true, every /api/query is also
              // routed through the new two-layer pipeline in a fire-and-forget
              // task and the resulting plan + answer length is logged. The
              // legacy router still serves the response, so users see no
              // behavior change. Used to validate v2 plans against real
              // traffic before flipping ENABLE_PIPELINE_V2=true.
              name: 'ENABLE_PIPELINE_V2_SHADOW'
              value: 'true'
            }
            {
              // Pipeline V2 live mode: v2 owns ANALYZE / LOAD_AND_ANALYZE
              // responses. NAVIGATE / LOAD still fall through to the legacy
              // STAC / navigation paths until Stage 4 cutover. Set to 'false'
              // to instantly revert to the legacy 5-intent router.
              name: 'ENABLE_PIPELINE_V2'
              value: 'true'
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
          ] : [],
          // Forecast provider URLs from Key Vault (matched against the
          // secrets[] entries above; secretRef name must match secret name).
          (!empty(keyVaultName) && auroraEndpointUrlConfigured) ? [
            {
              name: 'AURORA_ENDPOINT_URL'
              secretRef: 'aurora-endpoint-url'
            }
          ] : [],
          (!empty(keyVaultName) && earth2FcnEndpointUrlConfigured) ? [
            {
              name: 'EARTH2_FCN_ENDPOINT_URL'
              secretRef: 'earth2-fcn-endpoint-url'
            }
          ] : [],
          (!empty(keyVaultName) && maiWeatherEndpointUrlConfigured) ? [
            {
              name: 'MAI_WEATHER_ENDPOINT_URL'
              secretRef: 'mai-weather-endpoint-url'
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
output principalId string = app.identity.principalId
