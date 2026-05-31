// Forecast Agent provider URLs persisted as Key Vault secrets, plus a
// Key Vault Secrets User role assignment for the API container app's MI.
//
// Wired by main.bicep. Conditional on each URL parameter being non-empty
// so partial wiring (e.g. only Aurora configured) is supported without
// creating empty secrets.

@description('Name of the existing Key Vault to write secrets into.')
param keyVaultName string

@description('System-assigned managed identity principalId of the web container app. Granted Key Vault Secrets User on the vault.')
param webPrincipalId string

@description('Aurora scoring endpoint URL. Empty -> secret not created.')
@secure()
param auroraEndpointUrl string = ''

@description('Earth-2 FCN scoring endpoint URL. Empty -> secret not created.')
@secure()
param earth2FcnEndpointUrl string = ''

@description('MAI Weather scoring endpoint URL. Empty -> secret not created.')
@secure()
param maiWeatherEndpointUrl string = ''

resource keyVault 'Microsoft.KeyVault/vaults@2023-07-01' existing = {
  name: keyVaultName
}

resource auroraEndpointSecret 'Microsoft.KeyVault/vaults/secrets@2023-07-01' = if (!empty(auroraEndpointUrl)) {
  parent: keyVault
  name: 'aurora-endpoint-url'
  properties: {
    value: auroraEndpointUrl
    contentType: 'text/uri'
  }
}

resource earth2FcnEndpointSecret 'Microsoft.KeyVault/vaults/secrets@2023-07-01' = if (!empty(earth2FcnEndpointUrl)) {
  parent: keyVault
  name: 'earth2-fcn-endpoint-url'
  properties: {
    value: earth2FcnEndpointUrl
    contentType: 'text/uri'
  }
}

resource maiWeatherEndpointSecret 'Microsoft.KeyVault/vaults/secrets@2023-07-01' = if (!empty(maiWeatherEndpointUrl)) {
  parent: keyVault
  name: 'mai-weather-endpoint-url'
  properties: {
    value: maiWeatherEndpointUrl
    contentType: 'text/uri'
  }
}

// Grant the API container app's MI Key Vault Secrets User so it can resolve
// the secrets at container start (via keyVaultUrl + identity in web.bicep).
resource webSecretsUser 'Microsoft.Authorization/roleAssignments@2022-04-01' = if (!empty(webPrincipalId)) {
  name: guid(keyVault.id, webPrincipalId, 'KeyVaultSecretsUser')
  scope: keyVault
  properties: {
    principalId: webPrincipalId
    principalType: 'ServicePrincipal'
    // Key Vault Secrets User (read-only on secret values)
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', '4633458b-17de-408a-b874-0445c86b69e6')
  }
}
