# Planetary Explorer Infrastructure Deployment

This directory contains Bicep templates for deploying the complete Planetary Explorer infrastructure to Azure.

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

The deploy script defaults to **public stack, all opt-ins off, auto-picked region**.
A fresh fork should need exactly one command:

```powershell
# From the repo root
.\deploy-infrastructure.ps1
```

The script will:

1. Verify you're signed in to Azure (`az login` if not).
2. Run `planetary-explorer/scripts/select-region.ps1` to pick a region where
   Azure OpenAI (`gpt-4o`), Container Apps, ACR, Key Vault, and any opt-in
   services you enabled are all available.
3. Run `az deployment sub validate` (catches region/SKU/quota errors before
   any resource is created).
4. Provision the stack into `rg-planetaryexplorer`.

### Override via environment variables (CI / one-click deploy friendly)

```powershell
$env:MPC_PRO = 'true'      # surface MPC Pro toggle in the UI
$env:PRIVATE = 'true'      # private endpoints + VNet
$env:FABRIC  = 'true'      # provision Microsoft Fabric capacity
$env:LOCATION = 'eastus2'  # pin a region, skip preflight
.\deploy-infrastructure.ps1
```

### Override via flags

```powershell
.\deploy-infrastructure.ps1 -EnableMpcPro -EnableFabric -EnablePrivateEndpoints
.\deploy-infrastructure.ps1 -Location canadacentral
.\deploy-infrastructure.ps1 -EnvironmentName planetaryexplorer-test
```

### Feature flag defaults

| Flag (switch / env)                        | Default | What it does |
|--------------------------------------------|---------|--------------|
| `-EnableMpcPro` / `MPC_PRO`                | off     | Surfaces the MPC Pro toggle in the UI. Requires `mpcProStacUrl` to point at your GeoCatalog. |
| `-EnablePrivateEndpoints` / `PRIVATE`      | off     | VNet + private endpoints + private DNS zones. Public access disabled. |
| `-EnableFabric` / `FABRIC`                 | off     | Provisions a Fabric F2 capacity (~$262/mo). When off, Fabric-backed UI is hidden and backend uses seed data. |
| `-EnableWeatherModels` / `WEATHER_MODELS`  | off     | Deploys a CPU-only weather stub Container App (mocks Aurora + Earth-2 FCN) and wires the Forecast Agent to it. Avoids the `Standard_NC24ads_A100_v4` GPU quota requirement. Override with real Foundry endpoints via the `auroraEndpointUrl` / `earth2FcnEndpointUrl` / `maiWeatherEndpointUrl` Bicep params (MAI has no stub). The stub image must be built and pushed to ACR first (see [`planetary-explorer/weather-stub-server/`](../weather-stub-server/)). |

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
| `environmentName` | Name prefix for all resources | `planetaryexplorer` |
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
cd planetary-explorer/container-app
.\deploy-backend.ps1 -ResourceGroup {AZURE_RESOURCE_GROUP}

# Deploy frontend
cd planetary-explorer/web-ui
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
az group delete --name rg-planetaryexplorer-test --yes --no-wait
```

### Delete Production Environment

```powershell
az group delete --name rg-planetaryexplorer --yes
```

## 📊 Monitoring

View deployment outputs:

```powershell
az deployment sub show \
  --name planetary-explorer-{timestamp} \
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
