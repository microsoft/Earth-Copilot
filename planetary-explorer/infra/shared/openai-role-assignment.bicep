@description('Name of the Azure AI Foundry (OpenAI) account')
param aiFoundryName string

@description('Principal ID of the managed identity to grant access to')
param principalId string

// Reference the existing Azure OpenAI account
resource aiFoundry 'Microsoft.CognitiveServices/accounts@2023-05-01' existing = {
  name: aiFoundryName
}

// Grant Cognitive Services OpenAI User role to the managed identity
// This role allows using the OpenAI API with the account
// Using a deterministic GUID based on subscription, resource group, AI Foundry, and principal
resource openAiRoleAssignment 'Microsoft.Authorization/roleAssignments@2022-04-01' = if (!empty(principalId)) {
  name: guid(subscription().subscriptionId, resourceGroup().id, aiFoundry.id, principalId, 'cognitive-services-openai-user')
  scope: aiFoundry
  properties: {
    principalId: principalId
    principalType: 'ServicePrincipal'
    // Cognitive Services OpenAI User role: 5e0bd9bd-7b93-4f28-af87-19fc36ad61bd
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', '5e0bd9bd-7b93-4f28-af87-19fc36ad61bd')
  }
}
