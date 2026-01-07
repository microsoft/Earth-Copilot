param location string = resourceGroup().location
param tags object = {}

param name string
param sku object = {
  name: 'S0'
}

@description('Deploy GPT-4o model')
param deployModels bool = true

resource aiFoundry 'Microsoft.CognitiveServices/accounts@2023-05-01' = {
  name: name
  location: location
  tags: tags
  kind: 'OpenAI'
  sku: sku
  properties: {
    customSubDomainName: name
    publicNetworkAccess: 'Enabled'
    // Note: disableLocalAuth may be enforced by Azure Policy - credentials handled by workflow
    networkAcls: {
      defaultAction: 'Allow'
    }
  }
}

// Deploy GPT-4o model
resource gpt4oDeployment 'Microsoft.CognitiveServices/accounts/deployments@2023-05-01' = if (deployModels) {
  parent: aiFoundry
  name: 'gpt-4o'
  sku: {
    name: 'Standard'
    capacity: 10
  }
  properties: {
    model: {
      format: 'OpenAI'
      name: 'gpt-4o'
      version: '2024-08-06'
    }
    versionUpgradeOption: 'OnceNewDefaultVersionAvailable'
  }
}

output name string = aiFoundry.name
output endpoint string = aiFoundry.properties.endpoint
output id string = aiFoundry.id
