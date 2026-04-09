param location string = resourceGroup().location
param tags object = {}

param name string
param sku object = {
  name: 'basic'
}

@description('Enable private endpoints — requires Standard SKU or higher')
param enablePrivateEndpoints bool = false

@description('Cloud environment: Commercial or Government')
@allowed(['Commercial', 'Government'])
param cloudEnvironment string = 'Commercial'

// Determine the search domain suffix based on cloud environment
var searchSuffix = cloudEnvironment == 'Government' ? 'search.windows.us' : 'search.windows.net'

// Private endpoints require Standard SKU or higher (Basic doesn't support PE)
var effectiveSku = enablePrivateEndpoints ? { name: 'standard' } : sku

resource searchService 'Microsoft.Search/searchServices@2023-11-01' = {
  name: name
  location: location
  tags: tags
  sku: effectiveSku
  properties: {
    replicaCount: 1
    partitionCount: 1
    hostingMode: 'default'
    publicNetworkAccess: enablePrivateEndpoints ? 'disabled' : 'enabled'
    // Disable local auth (API keys) to enforce Managed Identity authentication
    // When disableLocalAuth is true, authOptions must be null (AAD is automatically required)
    disableLocalAuth: true
    networkRuleSet: {
      ipRules: []
    }
  }
}

output name string = searchService.name
output id string = searchService.id
output endpoint string = 'https://${searchService.name}.${searchSuffix}'
