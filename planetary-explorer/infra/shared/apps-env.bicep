// Container Apps Environment — VNet integration must be set at creation time
param name string
param location string = resourceGroup().location
param tags object = {}

param logAnalyticsWorkspaceName string

@description('Subnet ID for VNet integration (required when using private endpoints)')
param infrastructureSubnetId string = ''

@description('Whether the Container Apps Environment uses internal-only ingress (no public IP)')
param internal bool = false

resource logAnalyticsWorkspace 'Microsoft.OperationalInsights/workspaces@2022-10-01' existing = {
  name: logAnalyticsWorkspaceName
}

resource appsEnv 'Microsoft.App/managedEnvironments@2024-03-01' = {
  name: name
  location: location
  tags: tags
  properties: {
    appLogsConfiguration: {
      destination: 'log-analytics'
      logAnalyticsConfiguration: {
        customerId: logAnalyticsWorkspace.properties.customerId
        sharedKey: logAnalyticsWorkspace.listKeys().primarySharedKey
      }
    }
    // VNet integration must be set at creation time — cannot be added later.
    // When infrastructureSubnetId is provided, the CAE joins the VNet so it can
    // reach private-endpoint-locked services (ACR, AI Services, Key Vault, etc.).
    vnetConfiguration: !empty(infrastructureSubnetId) ? {
      infrastructureSubnetId: infrastructureSubnetId
      internal: internal
    } : null
    workloadProfiles: [
      {
        name: 'Consumption'
        workloadProfileType: 'Consumption'
      }
    ]
  }
}

output name string = appsEnv.name
output domain string = appsEnv.properties.defaultDomain
