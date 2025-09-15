param name string
param location string = resourceGroup().location
param tags object = {}

param applicationInsightsName string = ''
param logAnalyticsWorkspaceName string = ''

resource logAnalyticsWorkspace 'Microsoft.OperationalInsights/workspaces@2022-10-01' existing = if (!empty(logAnalyticsWorkspaceName)) {
  name: logAnalyticsWorkspaceName
}

resource appsEnv 'Microsoft.App/managedEnvironments@2023-05-01' = {
  name: name
  location: location
  tags: tags
  properties: {
    appLogsConfiguration: !empty(logAnalyticsWorkspaceName) ? {
      destination: 'log-analytics'
      logAnalyticsConfiguration: {
        customerId: logAnalyticsWorkspace.properties.customerId
        sharedKey: logAnalyticsWorkspace.listKeys().primarySharedKey
      }
    } : {}
  }
}

output name string = appsEnv.name
output domain string = appsEnv.properties.defaultDomain
