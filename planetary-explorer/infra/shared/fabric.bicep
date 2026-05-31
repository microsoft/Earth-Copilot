// Microsoft Fabric capacity (F SKU).
//
// Notes:
//   • Fabric is mostly SaaS. ONLY the capacity is provisionable via ARM/Bicep.
//   • Workspaces, lakehouses, items, and capacity-to-workspace assignment must
//     be created in the Fabric portal (https://app.fabric.microsoft.com) or
//     via the Fabric REST API (POST /v1/workspaces, etc).
//   • F2 is the smallest paid SKU (~$262/mo at PAYG). Use a Fabric trial
//     capacity if you just need to demo OBO + workspace access without billing.
//   • `administrators` must be an array of UPNs or Entra object IDs that will
//     have capacity-admin rights. At least one is required.

param name string
param location string = resourceGroup().location
param tags object = {}

@description('Fabric capacity SKU. F2 is the cheapest paid tier; scale up for production workloads.')
@allowed([
  'F2'
  'F4'
  'F8'
  'F16'
  'F32'
  'F64'
  'F128'
  'F256'
  'F512'
  'F1024'
  'F2048'
])
param skuName string = 'F2'

@description('UPNs or Entra object IDs of users who will be capacity admins. At least one required.')
param administrators array

resource capacity 'Microsoft.Fabric/capacities@2023-11-01' = {
  name: name
  location: location
  tags: tags
  sku: {
    name: skuName
    tier: 'Fabric'
  }
  properties: {
    administration: {
      members: administrators
    }
  }
}

output name string = capacity.name
output id string = capacity.id
output skuName string = capacity.sku.name
