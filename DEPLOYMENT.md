# Earth Copilot - Deployment Guide

Quick reference for deploying Earth Copilot to Azure with VNet-integrated Container Apps and App Service.

---

## Prerequisites

```powershell
# Install Azure CLI
winget install Microsoft.AzureCLI

# Login to Azure
az login

# Set subscription (optional)
az account set --subscription "<subscription-id>"
```

---

## Azure Resources

### Location: East US 2 (All Resources)

**Core Application Services**:
| Resource | Type | Purpose |
|----------|------|---------|
| earthcopilot-api | Container App | Backend API (Python FastAPI + Semantic Kernel) |
| earthcopilot-web-ui | App Service | Frontend (React + Azure Maps) |

**Infrastructure**:
| Resource | Type | Details |
|----------|------|---------|
| Virtual Network | VNet | 10.0.0.0/16, custom DNS (168.63.129.16, 8.8.8.8, 8.8.4.4) |
| Container Apps Environment | Managed Environment | VNet-integrated, Log Analytics connected |
| earthcopilotregistry | Container Registry | Docker images for Container App |
| App Service Plan | Service Plan | F1 (Free tier) for web-ui |

**AI & Data Services**:
| Resource | Type | Purpose |
|----------|------|---------|
| earth-copilot-foundry | Azure AI Foundry | GPT-4o/GPT-5 deployments |
| earth-copilot-search | Azure AI Search | STAC metadata indexing |
| earth-copilot-maps | Azure Maps | Geocoding, map tiles |
| earthcopilotstore | Storage Account | Data and logs |
| earthcopilot-keys | Key Vault | Secrets management |

**Monitoring**:
| Resource | Type | Purpose |
|----------|------|---------|
| earth-copilot-insights | Application Insights | APM, traces, metrics |
| Log Analytics Workspace | Log Analytics | Container App logs |

---

## Network Architecture

```
Virtual Network (10.0.0.0/16)
├── Container Apps Subnet (10.0.0.0/23)
│   ├── Delegated to: Microsoft.App/environments
│   └── Hosts: earthcopilot-api
│
└── DNS Configuration
    ├── Primary: 168.63.129.16 (Azure DNS)
    ├── Secondary: 8.8.8.8 (Google DNS)
    └── Fallback: 8.8.4.4 (Google DNS)

Ingress: HTTPS (port 8080) → Container App → Internet
Egress: Container App → VNet NAT → External APIs
```

**Benefits**:
- ✅ DNS resolution for external services (Microsoft Planetary Computer)
- ✅ Network isolation and security
- ✅ Static outbound IP for firewall rules
- ✅ Private connectivity to Azure services

---

## Quick Start

### 1. Deploy Infrastructure (5-10 minutes)

```powershell
# Deploy all Azure resources (VNet, Container Apps, ACR, AI services)
.\deploy-infrastructure.ps1

# Collect environment variables
.\collect-env-vars.ps1
```

**What gets deployed**:
- Virtual Network (10.0.0.0/16) with custom DNS (Azure DNS + Google DNS)
- Container Apps Environment (VNet-integrated)
- Container Registry
- Azure AI Foundry (GPT-4o/GPT-5)
- Azure Maps, Storage, Key Vault
- Application Insights, Log Analytics

### 2. Deploy Applications (8-12 minutes)

```powershell
# Deploy both backend and frontend
cd earth-copilot
.\deploy-all.ps1

# OR deploy individually:
# Backend only (5-8 min)
cd container-app
.\deploy-backend.ps1

# Frontend only (3-5 min)
cd ..\web-ui
.\deploy-frontend.ps1
```

### 3. Verify Deployment

```powershell
# Check backend health
az containerapp show --name earthcopilot-api --resource-group earthcopilot-rg \
  --query "properties.configuration.ingress.fqdn" -o tsv

# Visit URLs
# Backend API: https://<app-fqdn>/docs
# Frontend: https://earthcopilot-web-ui.azurewebsites.net
```

---

## Deployment Scripts

| Script | Purpose | Location | Time |
|--------|---------|----------|------|
| **deploy-infrastructure.ps1** | Deploy all Azure resources | Root | 5-10 min |
| **collect-env-vars.ps1** | Collect API keys and endpoints | Root | 1 min |
| **deploy-all.ps1** | Deploy both backend + frontend | earth-copilot/ | 8-12 min |
| **deploy-backend.ps1** | Deploy Container App only | earth-copilot/container-app/ | 5-8 min |
| **deploy-frontend.ps1** | Deploy App Service only | earth-copilot/web-ui/ | 3-5 min |

### Script Options

```powershell
# Skip building (use existing images)
.\deploy-backend.ps1 -SkipBuild
.\deploy-frontend.ps1 -SkipBuild
.\deploy-all.ps1 -SkipBuild

# Deploy specific target
.\deploy-all.ps1 -Target backend   # Backend only
.\deploy-all.ps1 -Target frontend  # Frontend only

# Custom resource names
.\deploy-backend.ps1 -ResourceGroup "my-rg" -ContainerAppName "my-api"
```

---

## Environment Variables

### Backend (Container App)

The backend Container App requires **19+ environment variables** configured as secrets and environment variables.

**Configuration Files**:
- Template: `.env.example` (root directory)
- Auto-collection: `collect-env-vars.ps1` (automatically retrieves values from deployed Azure resources)

**Required Variables**:

**Azure AI Foundry (GPT-4o/GPT-5)**:
```bash
AZURE_OPENAI_ENDPOINT=https://earth-copilot-foundry.cognitiveservices.azure.com
AZURE_OPENAI_API_KEY=<from-azure-ai-foundry>
AZURE_OPENAI_API_VERSION=2025-04-01-preview
AZURE_OPENAI_DEPLOYMENT_NAME=gpt-5
```

**Azure Maps (Geocoding & Map Tiles)**:
```bash
AZURE_MAPS_SUBSCRIPTION_KEY=<from-azure-maps>
AZURE_MAPS_CLIENT_ID=<from-azure-maps>
```

**STAC API (Satellite Data)**:
```bash
STAC_API_URL=https://planetarycomputer.microsoft.com/api/stac/v1
PLANETARY_COMPUTER_STAC_URL=https://planetarycomputer.microsoft.com/api/stac/v1
```

**Azure Storage (Optional)**:
```bash
AZURE_STORAGE_CONNECTION_STRING=<from-storage-account>
STORAGE_ACCOUNT_NAME=<storage-account-name>
STORAGE_ACCOUNT_KEY=<from-storage-account>
```

**Application Insights (Monitoring)**:
```bash
APPLICATIONINSIGHTS_CONNECTION_STRING=<from-app-insights>
APPLICATION_INSIGHTS_CONNECTION_STRING=<from-app-insights>
```

**See full list**: `.env.example` (70 lines with all variables and descriptions)

---

### Frontend (App Service)

The frontend requires **2-3 environment variables** for App Service configuration.

**Configuration File**: `earth-copilot/web-ui/.env.example`

**Required Variables**:
```bash
VITE_AZURE_MAPS_SUBSCRIPTION_KEY=<from-azure-maps>
VITE_API_BASE_URL=https://<container-app-fqdn>
```

**Optional** (for direct Azure service access):
```bash
VITE_AZURE_MAPS_CLIENT_ID=<from-azure-maps>
```

**Note**: Frontend fetches most configuration at runtime from backend `/api/config` endpoint.

---

## Quick Reference

### Essential Commands

```powershell
# Deploy infrastructure
.\deploy-infrastructure.ps1

# Collect environment variables from Azure
.\collect-env-vars.ps1

# Deploy applications
cd earth-copilot
.\deploy-all.ps1

# Check deployment status
az containerapp show --name earthcopilot-api --resource-group earthcopilot-rg

# View logs
az containerapp logs show --name earthcopilot-api --resource-group earthcopilot-rg --follow
```

---

## Additional Documentation

- **Agent System**: `AGENT_SYSTEM_OVERVIEW.md` - 7-agent architecture details
- **Startup Guide**: `STARTUP_GUIDE.md` - Getting started with the application
- **Authentication**: `ENTRA_AUTH_SETUP.md` - Microsoft Entra ID configuration

---

**Last Updated**: October 29, 2025  
**Infrastructure**: VNet-integrated from deployment  
**Location**: East US 2 (all resources)
