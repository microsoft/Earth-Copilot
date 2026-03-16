param location string = resourceGroup().location
param tags object = {}

param logAnalyticsName string
param applicationInsightsName string = ''

resource logAnalytics 'Microsoft.OperationalInsights/workspaces@2022-10-01' = {
  name: logAnalyticsName
  location: location
  tags: tags
  properties: {
    retentionInDays: 30
    features: {
      searchVersion: 1
    }
    sku: {
      name: 'PerGB2018'
    }
  }
}

// Application Insights — required by AI Foundry Hub (cannot be detached once set)
resource appInsights 'Microsoft.Insights/components@2020-02-02' = if (!empty(applicationInsightsName)) {
  name: applicationInsightsName
  location: location
  tags: tags
  kind: 'web'
  properties: {
    Application_Type: 'web'
    WorkspaceResourceId: logAnalytics.id
  }
}

output logAnalyticsWorkspaceName string = logAnalytics.name
output applicationInsightsId string = !empty(applicationInsightsName) ? appInsights.id : ''
