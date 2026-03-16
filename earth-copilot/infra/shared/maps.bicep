param location string = resourceGroup().location
param tags object = {}

param name string
param sku object = {
  name: 'G2'
}

// Azure Maps only available in limited regions - fallback to eastus if not supported
var mapsLocation = contains(['westcentralus', 'westus2', 'eastus', 'westeurope', 'northeurope'], toLower(location)) ? location : 'eastus'

resource mapsAccount 'Microsoft.Maps/accounts@2023-06-01' = {
  name: name
  location: mapsLocation
  tags: tags
  sku: sku
  kind: 'Gen2'
  properties: {
    // Enable local auth for frontend map rendering (browser cannot use container's MI)
    // Backend still uses Managed Identity for server-side geocoding operations
    disableLocalAuth: false
  }
}

output name string = mapsAccount.name
output id string = mapsAccount.id
output clientId string = mapsAccount.properties.uniqueId
output primaryKey string = mapsAccount.listKeys().primaryKey
