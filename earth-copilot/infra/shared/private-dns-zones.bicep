// Private DNS Zones for Private Endpoint Resolution
// Each Azure service type requires its own DNS zone linked to the VNet
// so that FQDNs resolve to private IPs instead of public IPs.

param tags object = {}
param vnetId string

@description('Cloud environment: Commercial or Government')
@allowed(['Commercial', 'Government'])
param cloudEnvironment string = 'Commercial'

// DNS zone names differ between Commercial and Government clouds
var dnsZones = cloudEnvironment == 'Government' ? {
  keyVault: 'privatelink.vaultcore.usgovcloudapi.net'
  storageBlob: 'privatelink.blob.core.usgovcloudapi.net'
  storageFile: 'privatelink.file.core.usgovcloudapi.net'
  cognitiveServices: 'privatelink.cognitiveservices.azure.us'
  openai: 'privatelink.openai.azure.us'
  search: 'privatelink.search.windows.us'
  containerRegistry: 'privatelink.azurecr.us'
  mlWorkspace: 'privatelink.api.ml.azure.us'
  mlNotebooks: 'privatelink.notebooks.usgovcloudapi.net'
  servicesAi: 'privatelink.services.ai.azure.us'
} : {
  keyVault: 'privatelink.vaultcore.azure.net'
  #disable-next-line no-hardcoded-env-urls // Private DNS zone names must be exact strings
  storageBlob: 'privatelink.blob.core.windows.net'
  #disable-next-line no-hardcoded-env-urls // Private DNS zone names must be exact strings
  storageFile: 'privatelink.file.core.windows.net'
  cognitiveServices: 'privatelink.cognitiveservices.azure.com'
  openai: 'privatelink.openai.azure.com'
  search: 'privatelink.search.windows.net'
  containerRegistry: 'privatelink.azurecr.io'
  mlWorkspace: 'privatelink.api.azureml.ms'
  mlNotebooks: 'privatelink.notebooks.azure.net'
  servicesAi: 'privatelink.services.ai.azure.com'
}

// ── Key Vault ──
resource dnsZoneKeyVault 'Microsoft.Network/privateDnsZones@2024-06-01' = {
  name: dnsZones.keyVault
  location: 'global'
  tags: tags
}
resource dnsZoneKeyVaultLink 'Microsoft.Network/privateDnsZones/virtualNetworkLinks@2024-06-01' = {
  parent: dnsZoneKeyVault
  name: 'link-keyvault'
  location: 'global'
  properties: {
    virtualNetwork: { id: vnetId }
    registrationEnabled: false
  }
}

// ── Storage (Blob) ──
resource dnsZoneStorageBlob 'Microsoft.Network/privateDnsZones@2024-06-01' = {
  name: dnsZones.storageBlob
  location: 'global'
  tags: tags
}
resource dnsZoneStorageBlobLink 'Microsoft.Network/privateDnsZones/virtualNetworkLinks@2024-06-01' = {
  parent: dnsZoneStorageBlob
  name: 'link-storage-blob'
  location: 'global'
  properties: {
    virtualNetwork: { id: vnetId }
    registrationEnabled: false
  }
}

// ── Storage (File) ──
resource dnsZoneStorageFile 'Microsoft.Network/privateDnsZones@2024-06-01' = {
  name: dnsZones.storageFile
  location: 'global'
  tags: tags
}
resource dnsZoneStorageFileLink 'Microsoft.Network/privateDnsZones/virtualNetworkLinks@2024-06-01' = {
  parent: dnsZoneStorageFile
  name: 'link-storage-file'
  location: 'global'
  properties: {
    virtualNetwork: { id: vnetId }
    registrationEnabled: false
  }
}

// ── Cognitive Services (AI Services / OpenAI) ──
resource dnsZoneCognitiveServices 'Microsoft.Network/privateDnsZones@2024-06-01' = {
  name: dnsZones.cognitiveServices
  location: 'global'
  tags: tags
}
resource dnsZoneCognitiveServicesLink 'Microsoft.Network/privateDnsZones/virtualNetworkLinks@2024-06-01' = {
  parent: dnsZoneCognitiveServices
  name: 'link-cognitive-services'
  location: 'global'
  properties: {
    virtualNetwork: { id: vnetId }
    registrationEnabled: false
  }
}

// ── OpenAI (required alongside Cognitive Services for Azure OpenAI PE resolution) ──
// The OpenAI SDK resolves to *.openai.azure.com, not *.cognitiveservices.azure.com,
// so both DNS zones must exist for the private endpoint to work correctly.
resource dnsZoneOpenAI 'Microsoft.Network/privateDnsZones@2024-06-01' = {
  name: dnsZones.openai
  location: 'global'
  tags: tags
}
resource dnsZoneOpenAILink 'Microsoft.Network/privateDnsZones/virtualNetworkLinks@2024-06-01' = {
  parent: dnsZoneOpenAI
  name: 'link-openai'
  location: 'global'
  properties: {
    virtualNetwork: { id: vnetId }
    registrationEnabled: false
  }
}

// ── AI Search ──
resource dnsZoneSearch 'Microsoft.Network/privateDnsZones@2024-06-01' = {
  name: dnsZones.search
  location: 'global'
  tags: tags
}
resource dnsZoneSearchLink 'Microsoft.Network/privateDnsZones/virtualNetworkLinks@2024-06-01' = {
  parent: dnsZoneSearch
  name: 'link-search'
  location: 'global'
  properties: {
    virtualNetwork: { id: vnetId }
    registrationEnabled: false
  }
}

// ── Container Registry ──
resource dnsZoneContainerRegistry 'Microsoft.Network/privateDnsZones@2024-06-01' = {
  name: dnsZones.containerRegistry
  location: 'global'
  tags: tags
}
resource dnsZoneContainerRegistryLink 'Microsoft.Network/privateDnsZones/virtualNetworkLinks@2024-06-01' = {
  parent: dnsZoneContainerRegistry
  name: 'link-container-registry'
  location: 'global'
  properties: {
    virtualNetwork: { id: vnetId }
    registrationEnabled: false
  }
}

// ── AI Foundry Hub (ML Workspace) ──
resource dnsZoneMlWorkspace 'Microsoft.Network/privateDnsZones@2024-06-01' = {
  name: dnsZones.mlWorkspace
  location: 'global'
  tags: tags
}
resource dnsZoneMlWorkspaceLink 'Microsoft.Network/privateDnsZones/virtualNetworkLinks@2024-06-01' = {
  parent: dnsZoneMlWorkspace
  name: 'link-ml-workspace'
  location: 'global'
  properties: {
    virtualNetwork: { id: vnetId }
    registrationEnabled: false
  }
}

// ── AI Foundry Notebooks ──
resource dnsZoneMlNotebooks 'Microsoft.Network/privateDnsZones@2024-06-01' = {
  name: dnsZones.mlNotebooks
  location: 'global'
  tags: tags
}
resource dnsZoneMlNotebooksLink 'Microsoft.Network/privateDnsZones/virtualNetworkLinks@2024-06-01' = {
  parent: dnsZoneMlNotebooks
  name: 'link-ml-notebooks'
  location: 'global'
  properties: {
    virtualNetwork: { id: vnetId }
    registrationEnabled: false
  }
}

// ── AI Agent Service (services.ai.azure.com) ──
// The Azure AI Agent Service SDK resolves to *.services.ai.azure.com,
// which requires its own DNS zone alongside cognitiveservices and openai zones.
resource dnsZoneServicesAi 'Microsoft.Network/privateDnsZones@2024-06-01' = {
  name: dnsZones.servicesAi
  location: 'global'
  tags: tags
}
resource dnsZoneServicesAiLink 'Microsoft.Network/privateDnsZones/virtualNetworkLinks@2024-06-01' = {
  parent: dnsZoneServicesAi
  name: 'link-services-ai'
  location: 'global'
  properties: {
    virtualNetwork: { id: vnetId }
    registrationEnabled: false
  }
}

// Outputs — DNS zone IDs needed when creating private endpoints
output keyVaultDnsZoneId string = dnsZoneKeyVault.id
output storageBlobDnsZoneId string = dnsZoneStorageBlob.id
output storageFileDnsZoneId string = dnsZoneStorageFile.id
output cognitiveServicesDnsZoneId string = dnsZoneCognitiveServices.id
output openaiDnsZoneId string = dnsZoneOpenAI.id
output searchDnsZoneId string = dnsZoneSearch.id
output containerRegistryDnsZoneId string = dnsZoneContainerRegistry.id
output mlWorkspaceDnsZoneId string = dnsZoneMlWorkspace.id
output mlNotebooksDnsZoneId string = dnsZoneMlNotebooks.id
output servicesAiDnsZoneId string = dnsZoneServicesAi.id
