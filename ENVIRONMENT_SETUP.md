# 🔧 Environment Setup Guide

This document explains how to configure environment variables for Earth Copilot 2.0.

## 📋 Overview

Earth Copilot requires environment variables for multiple components:
- ✅ **Backend Container App** - Azure AI services, Maps, STAC APIs
- ✅ **Frontend Web UI** - API endpoints, Azure Maps
- ✅ **MCP Server** - Earth Copilot API integration
- ✅ **Deployment Scripts** - Azure resource management

## 📁 Environment File Structure

```
earth-copilot-container/
├── .env                                    # 🔐 Root environment (deployment scripts)
├── .env.example                            # 📝 Template for root .env
├── earth-copilot/
│   ├── container-app/
│   │   ├── .env                            # � Backend runtime environment
│   │   └── .env.example                    # 📝 Template for backend
│   ├── web-ui/
│   │   ├── .env                            # 🔐 Frontend environment (Vite)
│   │   └── .env.example                    # � Template for frontend
│   └── mcp-server/
│       ├── .env                            # 🔐 MCP server environment
│       └── .env.example                    # 📝 Template for MCP
```

## 🔐 Required Environment Variables

### 1. Root Environment (`.env`)

Used by deployment scripts (`deploy-infrastructure.ps1`, `collect-env-vars.ps1`):

```bash
# Azure AI Foundry
AZURE_OPENAI_ENDPOINT=https://your-foundry.cognitiveservices.azure.com
AZURE_OPENAI_API_KEY=your_key_here
AZURE_OPENAI_DEPLOYMENT_NAME=gpt-4o
AZURE_OPENAI_API_VERSION=2024-10-21

# Azure Maps
AZURE_MAPS_SUBSCRIPTION_KEY=your_maps_key
AZURE_MAPS_CLIENT_ID=your_client_id

# Azure Container Registry
ACR_NAME=yourregistry
ACR_LOGIN_SERVER=yourregistry.azurecr.io

# Resource Group
RESOURCE_GROUP=earthcopilot-rg
LOCATION=canadacentral
```

### 2. Backend Environment (`earth-copilot/container-app/.env`)

Runtime configuration for the FastAPI backend:

```bash
# Azure AI Foundry (GPT-4o/GPT-5)
AZURE_OPENAI_ENDPOINT=https://your-foundry.cognitiveservices.azure.com
AZURE_OPENAI_API_KEY=your_key_here
AZURE_OPENAI_DEPLOYMENT_NAME=gpt-4o
AZURE_OPENAI_API_VERSION=2024-10-21

# Azure Maps
AZURE_MAPS_SUBSCRIPTION_KEY=your_maps_key
AZURE_MAPS_CLIENT_ID=your_client_id

# STAC APIs
STAC_API_URL=https://planetarycomputer.microsoft.com/api/stac/v1
PLANETARY_COMPUTER_STAC_URL=https://planetarycomputer.microsoft.com/api/stac/v1
NASA_VEDA_STAC_URL=https://veda.usgs.gov/api/stac

# Optional: Google Maps (improves geocoding accuracy)
GOOGLE_MAPS_API_KEY=your_google_key

# Optional: Azure Storage (for GEOINT raster processing)
AZURE_STORAGE_CONNECTION_STRING=your_storage_connection
STORAGE_ACCOUNT_NAME=your_storage_account

# Optional: Application Insights (monitoring)
APPLICATIONINSIGHTS_CONNECTION_STRING=your_insights_connection
```

### 3. Frontend Environment (`earth-copilot/web-ui/.env`)

Vite environment variables (must be prefixed with `VITE_`):

```bash
VITE_API_BASE_URL=https://your-container-app-url.azurecontainerapps.io
VITE_AZURE_MAPS_SUBSCRIPTION_KEY=your_maps_key
VITE_AZURE_MAPS_CLIENT_ID=your_client_id
```

### 4. MCP Server Environment (`earth-copilot/mcp-server/.env`)

Model Context Protocol server configuration:

```bash
EARTH_COPILOT_API_URL=https://your-container-app-url.azurecontainerapps.io
```

## 🤖 Automated Environment Collection

Use the provided PowerShell script to automatically collect API keys and endpoints from your Azure subscription:

```powershell
.\collect-env-vars.ps1
```

This script will:
1. Query your Azure subscription for all deployed resources
2. Extract API keys, endpoints, and connection strings
3. Generate `.env` files in the correct locations
4. Validate all required variables are present

## 🔒 Security Best Practices

**⚠️ NEVER commit `.env` files to Git!**

All `.env` files are protected by `.gitignore` entries:
- Root: `/.env`
- Backend: `/earth-copilot/container-app/.env`
- Frontend: `/earth-copilot/web-ui/.env*`
- MCP: `/earth-copilot/mcp-server/.env`

**Always use `.env.example` files** as templates and copy them to `.env` before adding sensitive values.

## 🧪 Verifying Your Setup

### Check Environment Variables

```powershell
# Verify root environment
python verify-requirements.py

# Test backend environment loading
cd earth-copilot/container-app
python -c "from dotenv import load_dotenv; load_dotenv(); import os; print('✅ Loaded:', os.getenv('AZURE_OPENAI_ENDPOINT'))"
```

### Test API Connectivity

```powershell
# Test Azure OpenAI
curl https://your-foundry.cognitiveservices.azure.com -H "api-key: your_key"

# Test Azure Maps
curl "https://atlas.microsoft.com/search/address/json?subscription-key=your_key&api-version=1.0&query=Denver"
```

## 📖 Related Documentation

- [AZURE_SETUP_GUIDE.md](AZURE_SETUP_GUIDE.md) - Creating Azure services
- [DEPLOYMENT.md](DEPLOYMENT.md) - Deployment instructions
- [SYSTEM_REQUIREMENTS.md](SYSTEM_REQUIREMENTS.md) - Technical requirements

## 🆘 Troubleshooting

### Missing Environment Variables

If deployment fails with "missing environment variable" errors:

1. Run `.\collect-env-vars.ps1` to regenerate `.env` files
2. Manually check `.env.example` files for required variables
3. Verify Azure resources are deployed: `az resource list -g earthcopilot-rg`

### Invalid API Keys

If you get authentication errors:

1. Verify keys in Azure Portal (Key Vault, AI Foundry, Maps)
2. Check key rotation date - regenerate if needed
3. Update `.env` files with new keys
4. Restart services after updating environment

### CORS Errors in Frontend

If frontend can't reach backend:

1. Check `VITE_API_BASE_URL` matches actual Container App URL
2. Verify Container App has CORS enabled for frontend origin
3. Check VNet integration allows frontend → backend communication

---

**📖 For complete setup instructions, see:**
- [AZURE_SETUP_GUIDE.md](AZURE_SETUP_GUIDE.md) - Azure services creation
- [DEPLOYMENT.md](DEPLOYMENT.md) - Application deployment
- [README.md](README.md) - Project overview

### 2. React UI Synchronization
React/Vite requires variables to be prefixed with `VITE_`. The sync script handles this:

```bash
python scripts/sync_env.py
```

This copies variables from root `.env` to `earth-copilot/react-ui/.env` with proper prefixes.

### 3. Security Protection
Multiple `.gitignore` files ensure no secrets are committed:
- Root `.gitignore`: Protects main `.env`
- React `.gitignore`: Protects React `.env`
- Comprehensive patterns for all environment file variations

## Usage

### Daily Development

1. **Update environment variables**: Edit the root `.env` file
2. **Sync to React**: Run `python scripts/sync_env.py`
3. **Test configuration**: Run `python scripts/test_env.py`

### Management Commands

```bash
# Sync all environment variables
python scripts/env_manager.py sync

# Test environment loading
python scripts/env_manager.py test

# Validate gitignore protection
python scripts/env_manager.py validate-gitignore

# Run all checks
python scripts/env_manager.py all
```

### Adding New Environment Variables

1. Add the variable to root `.env`:
   ```
   NEW_SERVICE_API_KEY=your-api-key-here
   ```

2. If needed by React UI, add mapping to `scripts/sync_env.py`:
   ```python
   env_mapping = {
       "NEW_SERVICE_API_KEY": "VITE_NEW_SERVICE_API_KEY",
       # ... other mappings
   }
   ```

3. Sync to React UI:
   ```bash
   python scripts/sync_env.py
   ```

4. Update `.env.example` templates for documentation.

## Security Best Practices

### ✅ DO:
- Keep all secrets in the root `.env` file
- Use the sync script for React variables
- Regularly run `env_manager.py validate-gitignore`
- Update `.env.example` files when adding new variables

### ❌ DON'T:
- Commit any `.env` files (they're protected by .gitignore)
- Hardcode API keys or secrets in source code
- Create additional `.env` files in subdirectories
- Put production secrets in `.env.example` files

## Troubleshooting

### Environment variables not loading?
1. Run `python scripts/test_env.py` to diagnose
2. Check that `.env` file exists in root directory
3. Verify file format (KEY=value, no spaces around =)

### React UI not seeing variables?
1. Run `python scripts/sync_env.py` to regenerate React `.env`
2. Check that variables are prefixed with `VITE_`
3. Restart the React development server

### Import errors?
- Ensure Python path includes the core module
- Check for circular imports (logging.py was renamed to app_logging.py)

## Files That Load Environment Variables

- `earth-copilot/core/config.py` - Main configuration class
- `earth-copilot/router-function-app/function_app.py` - Azure Function
- `earth-copilot/ai-search/scripts/create_search_index_with_vectors.py` - Search indexing
- `earth-copilot/router-function-app/validate_function.py` - Function validation
- All test files in `earth-copilot/tests/` and `tests/`

All these files now use the centralized loading mechanism pointing to the root `.env` file.