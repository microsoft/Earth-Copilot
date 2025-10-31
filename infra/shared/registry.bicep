param location string = resourceGroup().location
param tags object = {}
param name string

resource registry 'Microsoft.ContainerRegistry/registries@2023-07-01' = {
  name: name
  location: location
  tags: tags
  sku: {
    name: 'Basic'
  }
  properties: {
    adminUserEnabled: true
  }
}

output name string = registry.name
output loginServer string = registry.properties.loginServer
