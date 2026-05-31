param location string = resourceGroup().location
param tags object = {}
param name string

@description('Enable private endpoints — requires Premium SKU')
param enablePrivateEndpoints bool = false

@description('VNet subnet resource ID for the ACR agent pool (required when enablePrivateEndpoints = true)')
param acrAgentSubnetId string = ''

@description('Name of the ACR agent pool for VNet-integrated builds. Users with an existing pool can override this.')
param acrAgentPoolName string = 'buildpool'

@description('Number of always-on agent VMs (1 = ready for builds, 0 = scale-from-zero but slower first build)')
param acrAgentPoolCount int = 1

resource registry 'Microsoft.ContainerRegistry/registries@2023-07-01' = {
  name: name
  location: location
  tags: tags
  sku: {
    name: 'Premium'  // Always Premium — avoids SkuUpdateConflict when toggling private endpoints
  }
  properties: {
    adminUserEnabled: false  // Use managed identity instead of admin user
    anonymousPullEnabled: false  // Security best practice
    // Public deploy: defaultAction = Allow. ACR Tasks (`az acr build`) cannot
    // push to a registry whose firewall denies its ephemeral build agent IP,
    // and AzureServices bypass does not cover Tasks. Auth is still enforced
    // via AAD (anonymous + admin user are disabled above).
    // Private-endpoint deploy: defaultAction = Deny; builds run on a
    // VNet-integrated agent pool, and Container Apps pull via the PE.
    publicNetworkAccess: 'Enabled'
    networkRuleBypassOptions: 'AzureServices'
    networkRuleSet: enablePrivateEndpoints ? {
      defaultAction: 'Deny'
    } : {
      defaultAction: 'Allow'
    }
  }
}

output name string = registry.name
output loginServer string = registry.properties.loginServer
output id string = registry.id

// ═══════════════════════════════════════════════════════════════════
// ACR AGENT POOL — VNet-integrated build agents for private image builds.
// Only deployed when private endpoints are enabled (Premium SKU required).
// The CI/CD pipeline auto-detects this pool and uses --agent-pool to build
// inside the VNet, avoiding any need to open the ACR firewall.
// ═══════════════════════════════════════════════════════════════════

resource agentPool 'Microsoft.ContainerRegistry/registries/agentPools@2019-06-01-preview' = if (enablePrivateEndpoints && !empty(acrAgentSubnetId)) {
  parent: registry
  name: acrAgentPoolName
  location: location
  properties: {
    count: acrAgentPoolCount
    tier: 'S1'
    os: 'Linux'
    virtualNetworkSubnetResourceId: acrAgentSubnetId
  }
}

output agentPoolName string = enablePrivateEndpoints && !empty(acrAgentSubnetId) ? agentPool.name : ''
