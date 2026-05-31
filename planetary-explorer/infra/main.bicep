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

// Microsoft Fabric integration (opt-in, three-way toggle)
//
//   enableFabric           Master switch. When false, the UI hides Fabric-
//                          backed surfaces and the backend short-circuits
//                          to bundled seed data. Default: false.
//
//   deployFabricCapacity   When true (and enableFabric=true), provision a
//                          new Fabric F-SKU capacity in this resource group.
//                          Default: false (because F2 is billed ~$262/mo).
//
//   fabricCapacityResourceId  ARM resource ID of an existing Fabric capacity
//                          to associate with this deployment (BYO). Used
//                          when enableFabric=true and deployFabricCapacity
//                          =false. Surfaced in outputs as the "effective"
//                          capacity ID so downstream wiring is uniform.
//
// Fabric is mostly SaaS — only the capacity itself is provisionable via
// Bicep. Workspaces / lakehouses / items must be created in the Fabric
// portal or via REST and their IDs supplied via fabricWorkspaceId /
// fabricLakehouseId so the backend container can query them at runtime.
@description('Master switch for Microsoft Fabric integration. When false, the UI hides Fabric-backed surfaces and the backend skips Fabric queries (falls back to bundled seed data).')
param enableFabric bool = false

@description('Deploy a new Microsoft Fabric F-SKU capacity. Requires enableFabric=true. Default false — use existing capacity (BYO via fabricCapacityResourceId) or a Fabric trial.')
param deployFabricCapacity bool = false

@description('ARM resource ID of an existing Fabric capacity to associate with this deployment (BYO). Used when enableFabric=true and deployFabricCapacity=false. Leave empty to provision a new capacity via deployFabricCapacity.')
param fabricCapacityResourceId string = ''

@description('Fabric capacity SKU when deployFabricCapacity=true (F2 = cheapest paid tier, ~$262/mo).')
param fabricSkuName string = 'F2'

@description('UPNs or Entra object IDs of Fabric capacity admins. Required when deployFabricCapacity = true.')
param fabricAdministrators array = []

@description('Fabric workspace ID containing the lakehouse the backend will query. Surfaced as FABRIC_LAKEHOUSE_WORKSPACE_ID. Required for live Fabric queries; if empty the backend falls back to bundled seed data.')
param fabricWorkspaceId string = ''

@description('Fabric lakehouse ID inside ``fabricWorkspaceId``. Surfaced as FABRIC_LAKEHOUSE_ID.')
param fabricLakehouseId string = ''

// Bot Service parameters (Teams integration)
@description('Deploy Azure Bot Service for Teams chat integration')
param deployBotService bool = false

@description('Microsoft App ID for the Bot (from Entra App Registration)')
param microsoftBotAppId string = ''

@description('Microsoft App Password (client secret) for the Bot')
@secure()
param microsoftBotAppPassword string = ''

// Private Networking
@description('Deploy with private endpoints (disables public access, creates VNet, DNS zones, and PEs). Off by default; the app relies on Entra ID auth at the front door for access control. Set to true only when an isolated network is a hard requirement (regulated tenant, sandbox sub forbidding public endpoints, etc.).')
param enablePrivateEndpoints bool = false

@description('Set to true to restore a soft-deleted Cognitive Services account (e.g. after a failed or torn-down deployment)')
param restoreSoftDeletedAccount bool = false

@description('Name of the ACR agent pool for VNet-integrated builds. Override to use an existing pool.')
param acrAgentPoolName string = 'buildpool'

@description('Number of always-on ACR agent pool VMs (1 = ready for builds, 0 = slower cold start)')
param acrAgentPoolCount int = 1

// MCP Server (in-repo Planetary Explorer MCP server, exposes /api/query as MCP tools)
@description('Deploy the in-repo Planetary Explorer MCP server alongside the API. One MCP container per environment, pointed at this environment\'s backend. Off by default — opt in for environments that need to be reachable from VS Code Copilot Agent / Claude Desktop / Cursor over MCP.')
param deployMcpServer bool = false

@description('Container image for the MCP server (e.g. planetary-explorer-mcp:latest). Required when deployMcpServer=true. Built from planetary-explorer/mcp-server/Dockerfile and pushed to this environment\'s ACR.')
param mcpImageName string = 'planetary-explorer-mcp:latest'

@description('Shared API key required on inbound MCP requests via the X-API-Key header. Empty disables key auth.')
@secure()
param mcpApiKey string = ''

// MPC Pro MCP sidecar (Microsoft\'s upstream geocatalog-mcp-server, run as an
// internal Container App for the backend to call as an MCP client). The image
// is built from planetary-explorer/mpc-mcp-sidecar/ which vendors the MIT-licensed
// upstream binary and wraps it with a stdio<->streamable-HTTP bridge.
@description('Surface the MPC Pro toggle in the UI. When false, the StacModeToggle renders Pro as a locked control with a "How to enable" link. Independent of ``deployMpcMcp`` so an operator can flip the UI flag on/off without redeploying the sidecar.')
param enableMpcPro bool = false

@description('STAC API base URL for the private GeoCatalog (MPC Pro). Surfaced to the API container as MPC_PRO_STAC_URL. Format: https://<gc>.<region>.geocatalog.spatio.azure.com/stac. Empty disables the Pro path even if enableMpcPro=true.')
param mpcProStacUrl string = ''

@description('Deploy the MPC Pro MCP sidecar. Off by default — image must exist in ACR first (no CI build step yet for mpc-mcp-sidecar/Dockerfile). When on, also flip USE_MPC_MCP on the backend after granting the sidecar MI Reader inside the GeoCatalog. See planetary-explorer/mpc-mcp-sidecar/README.md.')
param deployMpcMcp bool = false

@description('Container image for the MPC Pro MCP sidecar (e.g. planetary-explorer-mpc-mcp:v1.0.9). Required when deployMpcMcp=true. Built from planetary-explorer/mpc-mcp-sidecar/Dockerfile.')
param mpcMcpImageName string = 'planetary-explorer-mpc-mcp:v1.0.9'

@description('Optional default GeoCatalog URL the MPC MCP sidecar advertises when a tool call omits ``geocatalog_uri``. Per-call override always works; safe to leave empty.')
param mpcDefaultGeoCatalogUri string = ''

@description('Backend feature flag: route Pro catalog inventory through the MCP sidecar when ``true``. Set to ``false`` initially after deploy, then flip to ``true`` after the Phase 2 validation checklist passes in dev.')
@allowed(['true', 'false'])
param useMpcMcp string = 'false'

@description('Dynamic collection selector mode. off | shadow | v2. When v2, the natural-language -> STAC collection id mapping uses the live CollectionIndex + constrained-LLM pick pipeline (collection_selector.py) instead of the legacy LoadAgent prompt catalog. Passed to web.bicep as COLLECTION_SELECTOR.')
@allowed([ 'off', 'shadow', 'v2' ])
param collectionSelectorMode string = 'v2'

@description('When true, the v2 selector returns a clarify Selection on low-confidence / tied top-1/top-2 picks. Passed to web.bicep as COLLECTION_SELECTOR_DISAMBIGUATE.')
param collectionSelectorDisambiguate bool = true

// Forecast Agent / weather provider parameters. URLs are persisted as
// Key Vault secrets and surfaced to the API container as AURORA_ENDPOINT_URL
// / EARTH2_FCN_ENDPOINT_URL / MAI_WEATHER_ENDPOINT_URL via secretRef so that
// rotating the endpoint (e.g. swapping the CPU-backed weather-providers ACA
// for a real Aurora / Earth-2 / MAI Weather inference endpoint) is a single
// ``az keyvault secret set`` instead of a container redeploy.
@description('Deploy the in-cluster weather stub Container App that emulates Aurora + Earth-2 endpoints for dev. Off by default.')
param deployWeatherStub bool = false

@description('Container image for the weather stub. Used only when deployWeatherStub=true.')
param weatherStubImageName string = 'planetary-explorer-weather-stub:latest'

@description('Aurora scoring endpoint URL. Persisted as Key Vault secret aurora-endpoint-url and surfaced to the API container as AURORA_ENDPOINT_URL. Empty value disables the provider.')
param auroraEndpointUrl string = ''

@description('NVIDIA Earth-2 FCN scoring endpoint URL. Persisted as Key Vault secret earth2-fcn-endpoint-url and surfaced as EARTH2_FCN_ENDPOINT_URL. Empty value disables the provider.')
param earth2FcnEndpointUrl string = ''

@description('MAI Weather scoring endpoint URL. Persisted as Key Vault secret mai-weather-endpoint-url and surfaced as MAI_WEATHER_ENDPOINT_URL. Empty value disables the provider.')
param maiWeatherEndpointUrl string = ''

@description('Scoring path appended to MAI_WEATHER_ENDPOINT_URL. Defaults to /mai-weather/score (matches the weather-providers ACA). Set to /score when wiring real Foundry MAI Weather.')
param maiWeatherScorePath string = '/mai-weather/score'

@description('Master switch for the Forecast Agent. When false the /api/geoint/forecast endpoint returns 503 even if provider URLs are configured.')
param forecastAgentEnabled bool = true

var abbrs = loadJsonContent('./abbreviations.json')
var resourceToken = toLower(uniqueString(subscription().id, environmentName, location))
var tags = {
  'azd-env-name': environmentName
  'azd-app-name': 'planetary-explorer'
}

// Auto-generate a stable, recoverable Postgres admin password if the caller
// didn't supply one. Format: <16-char hash><uppercase><digit><symbol>.
// Stable per (subscription, environmentName, location) so re-runs don't change it.

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
    acrAgentSubnetId: enablePrivateEndpoints ? (networking.?outputs.?acrAgentSubnetId ?? '') : ''
    acrAgentPoolName: acrAgentPoolName
    acrAgentPoolCount: acrAgentPoolCount
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
    imageName: '${registry.outputs.loginServer}/${containerImage}'
    // AI Foundry / Azure OpenAI: prefer managed-identity (DefaultAzureCredential
    // in the container falls through to MI when AZURE_OPENAI_API_KEY is empty).
    // We do NOT call listKeys() on the Foundry account because many managed
    // subscriptions (MngEnvMCAP*, gov, regulated tenants) enforce
    // disableLocalAuth=true and listKeys() fails with BadRequest.
    azureOpenAiApiKey: azureOpenAiApiKey
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
    // MPC Pro MCP sidecar wiring. URL is empty when the sidecar is not
    // deployed; the backend treats an empty URL as "feature disabled"
    // regardless of useMpcMcp, so it's safe to ship the flag set to
    // ``true`` only after the sidecar exists AND the GeoCatalog grant has
    // been applied.
    mpcMcpUrl: deployMpcMcp ? (mpcMcp.?outputs.?uri ?? '') : ''
    useMpcMcp: useMpcMcp
    // Feature flags surfaced to the UI via /api/config. These are
    // independent of the deploy* flags so an operator can disable a
    // feature's UI without tearing down its infrastructure.
    enableFabric: enableFabric
    enableMpcPro: enableMpcPro
    mpcProStacUrl: mpcProStacUrl
    fabricWorkspaceId: fabricWorkspaceId
    fabricLakehouseId: fabricLakehouseId
    collectionSelectorMode: collectionSelectorMode
    collectionSelectorDisambiguate: collectionSelectorDisambiguate
    // Forecast Agent wiring. URLs are pulled from Key Vault at container
    // start via secretRef so rotating providers does not require redeploy.
    keyVaultName: deployAIFoundry ? (keyVault.?outputs.?name ?? '') : ''
    keyVaultUri: deployAIFoundry ? (keyVault.?outputs.?uri ?? '') : ''
    forecastAgentEnabled: forecastAgentEnabled
    auroraEndpointUrlConfigured: !empty(auroraEndpointUrl)
    earth2FcnEndpointUrlConfigured: !empty(earth2FcnEndpointUrl)
    maiWeatherEndpointUrlConfigured: !empty(maiWeatherEndpointUrl)
    maiWeatherScorePath: maiWeatherScorePath
  }
}

// Forecast Agent provider URLs + KV-User role assignment for the API
// container. Wraps RG-scope resources in a module so they deploy from
// this subscription-scope template.
module forecastSecrets './shared/forecast-secrets.bicep' = if (deployAIFoundry && !empty(containerImage)) {
  name: 'forecast-secrets'
  scope: rg
  params: {
    keyVaultName: '${abbrs.keyVaultVaults}${resourceToken}'
    webPrincipalId: web.?outputs.?principalId ?? ''
    auroraEndpointUrl: auroraEndpointUrl
    earth2FcnEndpointUrl: earth2FcnEndpointUrl
    maiWeatherEndpointUrl: maiWeatherEndpointUrl
  }
  dependsOn: [
    keyVault
  ]
}

// Grant the web container app's managed identity 'Cognitive Services OpenAI User'
// on the AI Foundry account so DefaultAzureCredential in the container can call
// the OpenAI inference endpoint. This is required when disableLocalAuth=true is
// enforced (managed sandbox / regulated subscriptions).
module webFoundryAccess './shared/foundry-role.bicep' = if (deployAIFoundry && !empty(containerImage)) {
  name: 'web-foundry-access'
  scope: rg
  params: {
    aiFoundryAccountName: 'cog-foundry-${resourceToken}'
    principalId: web.?outputs.?principalId ?? ''
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

// MCP server (opt-in via deployMcpServer). Deployed AFTER web so it can be
// pointed at the freshly provisioned backend FQDN.
module mcp './app/mcp.bicep' = if (deployMcpServer && !empty(containerImage)) {
  name: 'mcp'
  scope: rg
  params: {
    name: '${abbrs.appContainerApps}mcp-${resourceToken}'
    location: location
    tags: tags
    containerAppsEnvironmentName: appsEnv.outputs.name
    containerRegistryName: registry.outputs.name
    imageName: mcpImageName
    planetaryExplorerApiUrl: web.?outputs.?uri ?? ''
    mcpApiKey: mcpApiKey
  }
}

// MPC Pro MCP sidecar (opt-in via deployMpcMcp). Internal-only Container App
// running Microsoft's upstream geocatalog-mcp-server. The backend reaches it
// over the env's internal DNS via MPC_MCP_URL. Auth into the GeoCatalog is
// granted out-of-band inside the GeoCatalog instance (data-plane RBAC) using
// the principalId output. See planetary-explorer/mpc-mcp-sidecar/README.md.
module mpcMcp './app/mpc-mcp.bicep' = if (deployMpcMcp) {
  name: 'mpc-mcp'
  scope: rg
  params: {
    name: '${abbrs.appContainerApps}mpc-mcp-${resourceToken}'
    location: location
    tags: tags
    containerAppsEnvironmentName: appsEnv.outputs.name
    containerRegistryName: registry.outputs.name
    imageName: mpcMcpImageName
    defaultGeoCatalogUri: mpcDefaultGeoCatalogUri
  }
}

// ═══════════════════════════════════════════════════════════════════
// MICROSOFT FABRIC (opt-in capacity)
// ═══════════════════════════════════════════════════════════════════
//
// Only the capacity is provisioned here. After deploy, an operator must:
//   1. Sign in to https://app.fabric.microsoft.com as a capacity admin
//   2. Create a workspace and assign it to this capacity
//   3. Create lakehouse / warehouse / items as needed
//   4. Grant the OBO app (FABRIC_CLIENT_ID) Contributor or Member on the workspace
module fabricCapacity './shared/fabric.bicep' = if (enableFabric && deployFabricCapacity) {
  name: 'fabric-capacity'
  scope: rg
  params: {
    name: 'fab${resourceToken}'
    location: location
    tags: tags
    skuName: fabricSkuName
    administrators: fabricAdministrators
  }
}

// Effective Fabric capacity ID surfaced to consumers regardless of whether
// it was provisioned here or supplied as BYO. Empty string when
// enableFabric=false.
var fabricEffectiveCapacityId = enableFabric
  ? (deployFabricCapacity ? (fabricCapacity.?outputs.?id ?? '') : fabricCapacityResourceId)
  : ''

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

// MCP Server outputs (empty when deployMcpServer = false)
output AZURE_MCP_CONTAINER_APP_NAME string = mcp.?outputs.?name ?? ''
output AZURE_MCP_CONTAINER_APP_URL string = mcp.?outputs.?uri ?? ''
output AZURE_MCP_CONTAINER_APP_FQDN string = mcp.?outputs.?fqdn ?? ''

// MPC Pro MCP sidecar outputs (empty when deployMpcMcp = false). The
// principalId is what an operator pastes into the GeoCatalog instance's
// Access control pane to grant the sidecar Reader (or Contributor).
output AZURE_MPC_MCP_CONTAINER_APP_NAME string = mpcMcp.?outputs.?name ?? ''
output AZURE_MPC_MCP_CONTAINER_APP_URL string = mpcMcp.?outputs.?uri ?? ''
output AZURE_MPC_MCP_CONTAINER_APP_FQDN string = mpcMcp.?outputs.?fqdn ?? ''
output AZURE_MPC_MCP_PRINCIPAL_ID string = mpcMcp.?outputs.?principalId ?? ''

// Fabric capacity outputs.
// AZURE_FABRIC_CAPACITY_ID is the freshly provisioned capacity (empty when
// deployFabricCapacity = false).
// AZURE_FABRIC_EFFECTIVE_CAPACITY_ID is the capacity actually wired to the
// backend — either the provisioned one or the BYO fabricCapacityResourceId.
output AZURE_FABRIC_CAPACITY_NAME string = fabricCapacity.?outputs.?name ?? ''
output AZURE_FABRIC_CAPACITY_ID string = fabricCapacity.?outputs.?id ?? ''
output AZURE_FABRIC_CAPACITY_SKU string = fabricCapacity.?outputs.?skuName ?? ''
output AZURE_FABRIC_EFFECTIVE_CAPACITY_ID string = fabricEffectiveCapacityId
output AZURE_FABRIC_ENABLED bool = enableFabric
output AZURE_MPC_PRO_ENABLED bool = enableMpcPro
