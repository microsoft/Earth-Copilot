param location string = resourceGroup().location
param tags object = {}

param name string
param sku object = {
  name: 'basic'
}

resource searchService 'Microsoft.Search/searchServices@2023-11-01' = {
  name: name
  location: location
  tags: tags
  sku: sku
  properties: {
    replicaCount: 1
    partitionCount: 1
    hostingMode: 'default'
    publicNetworkAccess: 'enabled'
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
output endpoint string = 'https://${searchService.name}.search.windows.net'
