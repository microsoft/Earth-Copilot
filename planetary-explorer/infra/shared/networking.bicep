// Virtual Network and Subnets for Private Endpoint Deployment
// Deployed conditionally when enablePrivateEndpoints = true in main.bicep

param location string = resourceGroup().location
param tags object = {}

param vnetName string
param vnetAddressPrefix string = '10.0.0.0/16'

// Subnet address spaces
param containerAppsSubnetPrefix string = '10.0.0.0/23'    // /23 = 512 IPs (Container Apps needs large range)
param appServiceSubnetPrefix string = '10.0.2.0/24'       // /24 = 256 IPs
param privateEndpointsSubnetPrefix string = '10.0.3.0/24'  // /24 = 256 IPs (plenty for ~12 PEs)
param acrAgentSubnetPrefix string = '10.0.4.0/27'         // /27 = 32 IPs (ACR agent pool VMs)

// ═══════════════════════════════════════════════════════════════════
// NETWORK SECURITY GROUPS — Required by many enterprise Azure policies
// (e.g. Deny-Subnet-Without-Nsg). Each subnet gets its own NSG.
// ═══════════════════════════════════════════════════════════════════

resource nsgContainerApps 'Microsoft.Network/networkSecurityGroups@2024-01-01' = {
  name: 'nsg-container-apps'
  location: location
  tags: tags
  properties: {
    securityRules: []
  }
}

resource nsgAppService 'Microsoft.Network/networkSecurityGroups@2024-01-01' = {
  name: 'nsg-app-service'
  location: location
  tags: tags
  properties: {
    securityRules: []
  }
}

resource nsgPrivateEndpoints 'Microsoft.Network/networkSecurityGroups@2024-01-01' = {
  name: 'nsg-private-endpoints'
  location: location
  tags: tags
  properties: {
    securityRules: []
  }
}

resource nsgAcrAgent 'Microsoft.Network/networkSecurityGroups@2024-01-01' = {
  name: 'nsg-acr-agent'
  location: location
  tags: tags
  properties: {
    securityRules: []
  }
}

resource vnet 'Microsoft.Network/virtualNetworks@2024-01-01' = {
  name: vnetName
  location: location
  tags: tags
  properties: {
    addressSpace: {
      addressPrefixes: [
        vnetAddressPrefix
      ]
    }
    subnets: [
      {
        name: 'snet-container-apps'
        properties: {
          addressPrefix: containerAppsSubnetPrefix
          networkSecurityGroup: {
            id: nsgContainerApps.id
          }
          delegations: [
            {
              name: 'Microsoft.App.environments'
              properties: {
                serviceName: 'Microsoft.App/environments'
              }
            }
          ]
        }
      }
      {
        name: 'snet-app-service'
        properties: {
          addressPrefix: appServiceSubnetPrefix
          networkSecurityGroup: {
            id: nsgAppService.id
          }
          delegations: [
            {
              name: 'Microsoft.Web.serverFarms'
              properties: {
                serviceName: 'Microsoft.Web/serverFarms'
              }
            }
          ]
        }
      }
      {
        name: 'snet-private-endpoints'
        properties: {
          addressPrefix: privateEndpointsSubnetPrefix
          networkSecurityGroup: {
            id: nsgPrivateEndpoints.id
          }
        }
      }
      {
        name: 'snet-acr-agent'
        properties: {
          addressPrefix: acrAgentSubnetPrefix
          networkSecurityGroup: {
            id: nsgAcrAgent.id
          }
        }
      }
    ]
  }
}

output vnetName string = vnet.name
output vnetId string = vnet.id
output containerAppsSubnetId string = vnet.properties.subnets[0].id
output appServiceSubnetId string = vnet.properties.subnets[1].id
output privateEndpointsSubnetId string = vnet.properties.subnets[2].id
output acrAgentSubnetId string = vnet.properties.subnets[3].id
