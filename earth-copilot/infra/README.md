# Earth Copilot Infrastructure Deployment

This directory contains Bicep templates for deploying the complete Earth Copilot infrastructure to Azure.

## 🏗️ What Gets Deployed

### Core Services
- **Azure AI Foundry** - GPT-4o and GPT-5 models for AI queries
- **Azure Maps** - Geocoding and location services
- **Azure Container Registry** - Docker image storage
- **ACR Agent Pool** (`buildpool`) - VNet-integrated build agents for private image builds (when private endpoints enabled)
- **Container Apps Environment** - Managed Kubernetes with VNet integration
- **Backend Container App** - FastAPI backend service
- **App Service + Plan** - React frontend hosting

### Storage & Security
- **Storage Account** - Blob storage for data and logs
- **Key Vault** - Secure secrets management
- **Log Analytics** - Container Apps diagnostics

### Optional Services
- **Azure AI Search** - Semantic search over STAC metadata (optional)

## 📋 Prerequisites

1. **Azure CLI** - Install from https://aka.ms/installazurecliwindows
2. **Azure Subscription** - With contributor/owner access
3. **Login to Azure** - Run `az login`

## 🚀 Quick Start

### Deploy All Infrastructure

```powershell
# Deploy to default location (East US) with default settings
.\deploy-infrastructure.ps1

# Deploy to custom location
.\deploy-infrastructure.ps1 -Location "canadacentral"

# Deploy with AI Search enabled
.\deploy-infrastructure.ps1 -DeployAISearch

# Deploy without GPT models (faster for testing)
.\deploy-infrastructure.ps1 -SkipModels
```

### Deploy to Test Environment

```powershell
# Create a separate test environment
.\deploy-infrastructure.ps1 -EnvironmentName "earthcopilot-test" -Location "eastus2"
```

## 📁 File Structure

```
infra/
├── main.bicep                 # Main orchestration template
├── main.parameters.json       # Parameter template
├── abbreviations.json         # Azure resource naming conventions
├── shared/                    # Shared infrastructure modules
│   ├── monitoring.bicep       # Log Analytics workspace
│   ├── storage.bicep          # Storage Account
│   ├── keyvault.bicep         # Key Vault
│   ├── ai-foundry.bicep       # Azure OpenAI / AI Foundry
│   ├── maps.bicep             # Azure Maps
│   ├── ai-search.bicep        # Azure AI Search (optional)
│   ├── registry.bicep         # Container Registry
│   └── apps-env.bicep         # Container Apps Environment + VNet
└── app/                       # Application modules
    ├── web.bicep              # Backend Container App
    └── frontend.bicep         # Frontend App Service
```

## ⚙️ Configuration

### Parameters

Edit `main.parameters.json` or pass as command-line arguments:

| Parameter | Description | Default |
|-----------|-------------|---------|
| `environmentName` | Name prefix for all resources | `earthcopilot` |
| `location` | Azure region | `eastus` |
| `deployAISearch` | Include Azure AI Search | `false` |
| `deployModels` | Deploy GPT-4o/GPT-5 models | `true` |
| `enableAuthentication` | Enable Entra ID auth | `false` |

### Resource Naming

Resources follow Azure naming conventions:
- Resource Group: `rg-{environmentName}`
- Storage: `st{uniqueString}`
- Key Vault: `kv-{uniqueString}`
- AI Foundry: `cog-foundry-{uniqueString}`
- Container App: `ca-api-{uniqueString}`
- Web App: `app-{uniqueString}`

## 🔑 Post-Deployment Steps

### 1. Get API Keys

```powershell
# Get AI Foundry key
az cognitiveservices account keys list \
  --name {AZURE_AI_FOUNDRY_NAME} \
  --resource-group {AZURE_RESOURCE_GROUP}

# Get Azure Maps key
az maps account keys list \
  --name {AZURE_MAPS_ACCOUNT_NAME} \
  --resource-group {AZURE_RESOURCE_GROUP}
```

### 2. Store Secrets in Key Vault

```powershell
# Store AI Foundry key
az keyvault secret set \
  --vault-name {AZURE_KEY_VAULT_NAME} \
  --name "azure-openai-api-key" \
  --value "{YOUR_AI_FOUNDRY_KEY}"

# Store Maps key
az keyvault secret set \
  --vault-name {AZURE_KEY_VAULT_NAME} \
  --name "azure-maps-subscription-key" \
  --value "{YOUR_MAPS_KEY}"
```

### 3. Deploy Applications

```powershell
# Deploy backend
cd earth-copilot/container-app
.\deploy-backend.ps1 -ResourceGroup {AZURE_RESOURCE_GROUP}

# Deploy frontend
cd earth-copilot/web-ui
.\deploy-frontend.ps1
```

## 🔄 Updates and Redeployment

The deployment is idempotent - running it again will update existing resources:

```powershell
# Update infrastructure (adds new resources, updates existing)
.\deploy-infrastructure.ps1
```

## 🧹 Cleanup

### Delete Test Environment

```powershell
az group delete --name rg-earthcopilot-test --yes --no-wait
```

### Delete Production Environment

```powershell
az group delete --name rg-earthcopilot --yes
```

## 📊 Monitoring

View deployment outputs:

```powershell
az deployment sub show \
  --name earth-copilot-{timestamp} \
  --query properties.outputs
```

## 🐛 Troubleshooting

### Deployment Fails

1. **Check quotas**: Ensure your subscription has quota for the resources
2. **Check permissions**: Verify you have Contributor or Owner role
3. **Check region**: Some resources may not be available in all regions
4. **View detailed errors**: Add `--debug` flag to az deployment commands

### Resource Already Exists

If deploying to an existing resource group:
- Resources with matching names will be updated
- Use a different `environmentName` for a fresh deployment

### Model Deployment Fails

GPT-5 model may not be available in all regions. Try:
- Use a different region with `location` parameter
- Skip model deployment with `-SkipModels` and deploy manually later

## 📚 Additional Resources

- [Azure Bicep Documentation](https://learn.microsoft.com/azure/azure-resource-manager/bicep/)
- [Azure Container Apps](https://learn.microsoft.com/azure/container-apps/)
- [Azure AI Foundry](https://learn.microsoft.com/azure/ai-services/)
- [Azure Maps](https://learn.microsoft.com/azure/azure-maps/)
