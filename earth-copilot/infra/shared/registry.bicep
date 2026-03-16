param location string = resourceGroup().location
param tags object = {}
param name string

@description('Enable private endpoints — requires Premium SKU')
param enablePrivateEndpoints bool = false

resource registry 'Microsoft.ContainerRegistry/registries@2023-07-01' = {
  name: name
  location: location
  tags: tags
  sku: {
    name: enablePrivateEndpoints ? 'Premium' : 'Basic'  // Premium required for private endpoints
  }
  properties: {
    adminUserEnabled: false  // Use managed identity instead of admin user
    anonymousPullEnabled: false  // Security best practice
    // Public network access: Enabled + defaultAction: Deny blocks all internet IPs.
    // During CI/CD builds, the pipeline temporarily sets defaultAction: Allow,
    // builds the image via managed ACR Tasks, then re-locks to Deny.
    // Container Apps pull images via ACR private endpoint (unaffected by firewall).
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
