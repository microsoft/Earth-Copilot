// Reusable Private Endpoint Module
// Creates a private endpoint for any Azure service and registers it in a DNS zone.
// Called once per service from main.bicep.

param location string = resourceGroup().location
param tags object = {}

@description('Name for the private endpoint resource')
param name string

@description('Resource ID of the target Azure service')
param serviceResourceId string

@description('Private link sub-resource type (e.g., vault, blob, searchService, account, registry)')
param groupId string

@description('Subnet ID where the private endpoint NIC will be placed')
param subnetId string

@description('Resource ID of the Private DNS Zone for automatic DNS registration')
param privateDnsZoneId string

@description('Additional Private DNS Zone IDs (e.g., openai zone alongside cognitiveservices zone)')
param additionalDnsZoneIds array = []

resource privateEndpoint 'Microsoft.Network/privateEndpoints@2024-01-01' = {
  name: name
  location: location
  tags: tags
  properties: {
    subnet: {
      id: subnetId
    }
    privateLinkServiceConnections: [
      {
        name: '${name}-connection'
        properties: {
          privateLinkServiceId: serviceResourceId
          groupIds: [
            groupId
          ]
        }
      }
    ]
  }
}

// Build array of DNS zone configs: primary + any additional zones
var primaryDnsConfig = [
  {
    name: 'config'
    properties: {
      privateDnsZoneId: privateDnsZoneId
    }
  }
]

var additionalDnsConfigs = [for (zoneId, i) in additionalDnsZoneIds: {
  name: 'config-${i + 1}'
  properties: {
    privateDnsZoneId: zoneId
  }
}]

// Register the PE's private IP in the DNS zone(s) so FQDNs resolve privately
resource dnsZoneGroup 'Microsoft.Network/privateEndpoints/privateDnsZoneGroups@2024-01-01' = {
  parent: privateEndpoint
  name: 'default'
  properties: {
    privateDnsZoneConfigs: concat(primaryDnsConfig, additionalDnsConfigs)
  }
}

output privateEndpointId string = privateEndpoint.id
output networkInterfaceId string = privateEndpoint.properties.networkInterfaces[0].id
