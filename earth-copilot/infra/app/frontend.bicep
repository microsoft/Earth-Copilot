param location string = resourceGroup().location
param tags object = {}

param appServicePlanName string
param webAppName string
param containerAppUrl string = ''

@description('Enable private endpoints — upgrades to Standard SKU for VNet integration')
param enablePrivateEndpoints bool = false

@description('Subnet ID for App Service VNet integration')
param vnetSubnetId string = ''

param sku object = {
  name: 'B1'
  tier: 'Basic'
}

// Private endpoints require Standard tier or higher for VNet integration
var effectiveSku = enablePrivateEndpoints ? {
  name: 'S1'
  tier: 'Standard'
} : sku

// App Service Plan for hosting the React frontend
resource appServicePlan 'Microsoft.Web/serverfarms@2023-01-01' = {
  name: appServicePlanName
  location: location
  tags: tags
  sku: effectiveSku
  kind: 'linux'
  properties: {
    reserved: true
  }
}

// Web App for React frontend with Microsoft Entra ID authentication
resource webApp 'Microsoft.Web/sites@2023-01-01' = {
  name: webAppName
  location: location
  tags: tags
  kind: 'app,linux'
  identity: {
    type: 'SystemAssigned'
  }
  properties: {
    serverFarmId: appServicePlan.id
    httpsOnly: true
    virtualNetworkSubnetId: !empty(vnetSubnetId) ? vnetSubnetId : null
    siteConfig: {
      linuxFxVersion: 'NODE|20-lts'
      alwaysOn: enablePrivateEndpoints  // Supported on Standard+ only
      ftpsState: 'Disabled'
      minTlsVersion: '1.2'
      appCommandLine: 'node server.js'  // Dependencies pre-installed during deployment
      appSettings: [
        {
          name: 'WEBSITE_NODE_DEFAULT_VERSION'
          value: '~20'
        }
        {
          name: 'SCM_DO_BUILD_DURING_DEPLOYMENT'
          value: 'false'  // We deploy pre-built static files, no build needed
        }
        {
          name: 'VITE_API_BASE_URL'
          value: containerAppUrl
        }
        {
          name: 'PORT'
          value: '8080'
        }
      ]
    }
  }
}

// Note: Microsoft Entra ID authentication must be configured manually after deployment
// Navigate to: Azure Portal > App Service > Authentication > Add identity provider > Microsoft
// This enables tenant-only access without requiring an app registration

output appServicePlanName string = appServicePlan.name
output appServicePlanId string = appServicePlan.id
output webAppName string = webApp.name
output webAppId string = webApp.id
output webAppUrl string = 'https://${webApp.properties.defaultHostName}'
