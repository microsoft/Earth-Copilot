// Grant a principal the 'Cognitive Services OpenAI User' role on an AI Foundry
// (AIServices kind) Cognitive Services account. Used by the web container app
// and MCP server when disableLocalAuth=true forces managed-identity auth.

param aiFoundryAccountName string
param principalId string

resource aiFoundry 'Microsoft.CognitiveServices/accounts@2024-10-01' existing = {
  name: aiFoundryAccountName
}

// 'Cognitive Services OpenAI User' built-in role
var roleCognitiveServicesOpenAIUser = '5e0bd9bd-7b93-4f28-af87-19fc36ad61bd'
// 'Azure AI Developer' built-in role — required to call AI Foundry Project
// Agents API (/api/projects/{project}/...). Without it the Foundry endpoint
// returns PermissionDenied for agent/tool invocations.
var roleAzureAIDeveloper = '64702f94-c441-49e6-a78b-ef80e0188fee'
// 'Cognitive Services User' — data-plane access for non-OpenAI AIServices
// surfaces (vision, etc.).
var roleCognitiveServicesUser = 'a97b65f3-24c7-4388-baec-2e87135dc908'

resource roleAssignment 'Microsoft.Authorization/roleAssignments@2022-04-01' = if (!empty(principalId)) {
  name: guid(aiFoundry.id, principalId, roleCognitiveServicesOpenAIUser)
  scope: aiFoundry
  properties: {
    principalId: principalId
    principalType: 'ServicePrincipal'
    roleDefinitionId: subscriptionResourceId(
      'Microsoft.Authorization/roleDefinitions',
      roleCognitiveServicesOpenAIUser
    )
  }
}

resource roleAssignmentAiDeveloper 'Microsoft.Authorization/roleAssignments@2022-04-01' = if (!empty(principalId)) {
  name: guid(aiFoundry.id, principalId, roleAzureAIDeveloper)
  scope: aiFoundry
  properties: {
    principalId: principalId
    principalType: 'ServicePrincipal'
    roleDefinitionId: subscriptionResourceId(
      'Microsoft.Authorization/roleDefinitions',
      roleAzureAIDeveloper
    )
  }
}

resource roleAssignmentCogUser 'Microsoft.Authorization/roleAssignments@2022-04-01' = if (!empty(principalId)) {
  name: guid(aiFoundry.id, principalId, roleCognitiveServicesUser)
  scope: aiFoundry
  properties: {
    principalId: principalId
    principalType: 'ServicePrincipal'
    roleDefinitionId: subscriptionResourceId(
      'Microsoft.Authorization/roleDefinitions',
      roleCognitiveServicesUser
    )
  }
}
