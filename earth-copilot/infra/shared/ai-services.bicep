@description('Location for the Azure AI Services resource')
param location string = resourceGroup().location

@description('Resource tags')
param tags object = {}

@description('Name of the Azure AI Services resource')
param name string

@description('SKU for the Azure AI Services resource')
param sku object = {
  name: 'S0'
}

@description('Whether to enable public network access')
param publicNetworkAccess string = 'Enabled'

resource aiServices 'Microsoft.CognitiveServices/accounts@2024-10-01' = {
  name: name
  location: location
  tags: tags
  kind: 'AIServices'
  sku: sku
  identity: {
    type: 'SystemAssigned'
  }
  properties: {
    customSubDomainName: name
    publicNetworkAccess: publicNetworkAccess
    networkAcls: {
      defaultAction: 'Allow'
    }
  }
}

@description('The name of the Azure AI Services resource')
output name string = aiServices.name

@description('The endpoint of the Azure AI Services resource')
output endpoint string = aiServices.properties.endpoint

@description('The resource ID of the Azure AI Services resource')
output id string = aiServices.id

@description('The principal ID of the system-assigned managed identity')
output principalId string = aiServices.identity.principalId
