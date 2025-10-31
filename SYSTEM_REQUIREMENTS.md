# Earth Copilot - System Requirements & Setup Guide

> **Quick Start**: This application is deployed on Azure Container Apps. See [DEPLOYMENT_STATUS.md](DEPLOYMENT_STATUS.md) for deployment information.

## 📋 Prerequisites

### Required Software (for development)
- **Python 3.12+** - [Download from python.org](https://python.org)
  - ⚠️ **Important**: Add Python to PATH during installation
- **Node.js 16+** - [Download from nodejs.org](https://nodejs.org)

### Azure Services Required
1. **Azure OpenAI Service** with GPT-5 deployment
2. **Azure Container Apps** for hosting containerized services
3. **Resource Group** (for organization)
4. **Azure Container Registry** (for container images)

### VS Code Extensions (Recommended)
- **Python** - For Python development
- **Pylance** - Enhanced Python support
- **Docker** - For container development

## 🚀 Development Setup

### 1. Clone Repository
```powershell
git clone <repository-url>
cd earth-copilot-container

# Verify your Python environment
python verify-requirements.py
```

### 2. Configure Environment Variables
Create a `.env` file with your Azure credentials:
```env
AZURE_OPENAI_ENDPOINT=https://your-openai-resource.openai.azure.com/
AZURE_OPENAI_API_KEY=your-api-key-here
AZURE_OPENAI_DEPLOYMENT_NAME=gpt-5
```

### 3. Local Frontend Development
```powershell
cd earth-copilot/container-app/frontend
npm install
npm run dev  # Runs on localhost:5173
```

## 🔧 Architecture Overview

### Deployed Services
- **Frontend (Azure App Service)**: User interface
- **Backend API (Azure Container Apps)**: Unified backend API

### Key Endpoints (Production)
- **Health Check**: `GET /api/health`
- **Main Query**: `POST /api/query` 
- **STAC Search**: `POST /api/stac-search`

## 📁 Project Structure

```
earth-copilot-container/
├── earth-copilot/
│   ├── container-app/
│   │   ├── frontend/             # React frontend (Vite)
│   │   └── backend/              # FastAPI backend
│   └── mcp-server/               # MCP server components
├── scripts/
│   └── stac_availability/        # STAC analysis tools
├── infra/                        # Azure infrastructure (Bicep)
├── azure.yaml                    # Azure deployment config
├── deploy-infrastructure.ps1     # Infrastructure deployment
└── requirements.txt              # Python dependencies
```

## 📦 Dependencies & Requirements

### Requirements Files
We maintain **multiple requirements files** for different contexts:

1. **`requirements.txt`** (Root) - Development environment
   - Contains all dependencies for local development
   - Used by setup and virtual environment

2. **`earth-copilot/container-app/backend/requirements.txt`** - Backend API
   - FastAPI backend dependencies
   - Used in container builds

### Critical Dependencies
- **semantic-kernel==1.36.2** - AI orchestration (Latest stable)
- **pydantic==2.11.9** - Data validation (Compatible with SK 1.36.2)
- **openai==1.107.2** - OpenAI API integration (Latest compatible)
- **fastapi>=0.100.0** - Modern web framework
- **pystac-client>=0.7.0** - STAC API interaction
- **planetary-computer>=1.0.0** - Microsoft Planetary Computer

### ⚠️ **Critical Version Compatibility Matrix**

**Status:** ✅ **RESOLVED** - Working configuration documented

#### **Semantic Kernel 1.36.2 Compatibility**
- **semantic-kernel:** `1.36.2` (LATEST STABLE)
- **pydantic:** `2.11.9` (LATEST COMPATIBLE)
- **pydantic-core:** `2.33.2` (AUTO-COMPATIBLE with pydantic 2.11.9)
- **openai:** `1.107.2` (LATEST COMPATIBLE)

#### **Critical Import Path Changes:**
```python
# ✅ CORRECT (1.36.2+ API)
from semantic_kernel.connectors.ai.open_ai import AzureChatCompletion
from semantic_kernel.functions import KernelArguments
from semantic_kernel import Kernel

# ❌ WRONG (old 1.0.x API - will fail)
from semantic_kernel.connectors.ai.azure_openai import AzureChatCompletion
```

#### **Installation Commands:**
```bash
# Install compatible versions together
pip install semantic-kernel==1.36.2 pydantic==2.11.9 openai==1.107.2

# Force reinstall if issues
pip install --force-reinstall semantic-kernel==1.36.2 pydantic==2.11.9 openai==1.107.2
```

#### **⚠️ CRITICAL RULES:**
1. **Import path changed** - Use `semantic_kernel.connectors.ai.open_ai` not `azure_openai`
2. **Always install together** - These versions are interdependent
3. **Use exact versions** - Avoid >= or ~ operators for critical dependencies
4. **Test after any changes** - SK imports are sensitive to version mismatches

## 🛠️ Development Workflow

### Frontend Development
```powershell
cd earth-copilot/container-app/frontend
npm install
npm run dev  # Runs on localhost:5173
```

### Testing
```powershell
cd earth-copilot/container-app/frontend
npm run build  # Build for production
```

## 🌍 Deployment

### Azure Container Apps Deployment
The application is deployed using Azure Container Apps via `azure.yaml`:

1. **Infrastructure**: Deploy using `.\deploy-infrastructure.ps1`
2. **Application**: Deploy using `azd deploy`
3. **Environment Variables**: Configure via Azure portal or `azd env set`

See [DEPLOYMENT_STATUS.md](DEPLOYMENT_STATUS.md) for current deployment details.

## ⚠️ Common Issues & Solutions

### Semantic Kernel Installation Issues
```powershell
# Force reinstall if SK fails with import errors
python -m pip install --force-reinstall semantic-kernel==1.36.2 pydantic==2.11.9 openai==1.107.2

# Test that imports work after installation
python -c "from semantic_kernel.connectors.ai.open_ai import AzureChatCompletion; print('✅ Semantic Kernel imports working')"
```

### Virtual Environment Issues
```powershell
# Recreate virtual environment
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

### Frontend Build Issues
```powershell
# Clean install
cd earth-copilot/container-app/frontend
Remove-Item -Recurse -Force node_modules, package-lock.json
npm install
npm run build
```

## 📝 Environment Variables Reference

| Variable | Required | Description | Example |
|----------|----------|-------------|---------|
| `AZURE_OPENAI_ENDPOINT` | Yes | Azure OpenAI service endpoint | `https://myoai.openai.azure.com/` |
| `AZURE_OPENAI_API_KEY` | Yes | Azure OpenAI API key | `abc123...` |
| `AZURE_OPENAI_DEPLOYMENT_NAME` | Yes | GPT model deployment name | `gpt-5` |

## 🧪 Testing Installation

### Verify Dependencies
After installation, test that critical imports work:

```bash
# Test semantic kernel imports
cd earth-copilot/router-function-app
python -c "
from semantic_kernel.connectors.ai.open_ai import AzureChatCompletion
from semantic_kernel.functions import KernelFunction, KernelArguments
from semantic_kernel import Kernel
print('✅ All semantic kernel imports successful')
"

# Test version compatibility
python -c "
import semantic_kernel as sk
import pydantic
import openai
print(f'Semantic Kernel: {sk.__version__}')
print(f'Pydantic: {pydantic.__version__}')
print(f'OpenAI: {openai.__version__}')
"
```

Expected output:
```
✅ All semantic kernel imports successful
Semantic Kernel: 1.36.2
Pydantic: 2.11.9
OpenAI: 1.107.2
```

### Test System Health
After deployment, verify the application is working:

```powershell
# Check if frontend is accessible
curl https://your-app-url.azurewebsites.net

# Test API health endpoint
curl https://your-api-url.azurecontainerapps.io/api/health
```

## 🎯 Success Criteria

### System is working correctly when:
1. ✅ Frontend builds successfully with `npm run build`
2. ✅ Application deploys to Azure Container Apps
3. ✅ Health check responds at production API endpoint
4. ✅ Query "Show me satellite imagery of California" returns STAC results
5. ✅ Results display on the map visualization

---

---

## 📚 Quick Reference for Import Errors

### If you see "cannot import name 'AzureChatCompletion'"
```bash
# This means you have the wrong semantic-kernel version
pip install --force-reinstall semantic-kernel==1.36.2 pydantic==2.11.9

# Verify the fix
python -c "from semantic_kernel.connectors.ai.open_ai import AzureChatCompletion; print('✅ Fixed')"
```

### If you see pydantic compatibility errors
```bash
# Install the exact compatible versions together
pip install semantic-kernel==1.36.2 pydantic==2.11.9 openai==1.107.2
```

### For new team members
```bash
# Run this first to check your environment
python verify-requirements.py

# Then follow the setup process
./setup-all-services.ps1  # or .sh on Linux/Mac
```

**Need help?** Check the main README.md or create an issue in the repository.