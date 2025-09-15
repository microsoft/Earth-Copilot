# Earth Copilot - System Requirements & Setup Guide

> **Quick Start**: New to this repo? Run `.\setup-all-services.ps1` then `.\run-all-services.ps1`

## 📋 Prerequisites

### Required Software
- **Python 3.8+** - [Download from python.org](https://python.org)
  - ⚠️ **Important**: Add Python to PATH during installation
- **Node.js 16+** - [Download from nodejs.org](https://nodejs.org)
- **Azure Functions Core Tools v4** - Install with:
  ```powershell
  npm install -g azure-functions-core-tools@4 --unsafe-perm true
  ```

### Azure Services Required
1. **Azure OpenAI Service** with GPT-5 deployment
2. **Resource Group** (for organization)
3. **Storage Account** (for Azure Functions)

### VS Code Extensions (Recommended)
- **Azure Functions** - For function development
- **Python** - For Python development
- **Pylance** - Enhanced Python support

## 🚀 First-Time Setup

### 1. Clone and Setup Repository
```powershell
git clone <repository-url>
cd EC

# FIRST: Verify your Python environment
python verify-requirements.py

# If verification passes, continue with setup
.\setup-all-services.ps1
```

This script will:
- ✅ Check all prerequisites
- 🐍 Create Python virtual environment
- 📦 Install all dependencies (with force install for semantic-kernel)
- ⚙️ Create .env from template
- 🔧 Install React UI dependencies

### 2. Configure Environment Variables
Edit the `.env` file with your Azure credentials:
```env
AZURE_OPENAI_ENDPOINT=https://your-openai-resource.openai.azure.com/
AZURE_OPENAI_API_KEY=your-api-key-here
AZURE_OPENAI_DEPLOYMENT_NAME=gpt-5
```

### 3. Run the Application
```powershell
.\run-all-services.ps1
```

## 🔧 Architecture Overview

### Services & Ports
- **React UI**: `localhost:5173` - User interface
- **Router Function**: `localhost:7071` - Unified backend API

### Key Endpoints
- **Health Check**: `GET /api/health`
- **Main Query**: `POST /api/query` 
- **STAC Search**: `POST /api/stac-search`

## 📁 Project Structure

```
EC/
├── earth_copilot/
│   ├── react-ui/                 # React frontend
│   └── router_function_app/      # Azure Function backend
├── scripts/
│   └── stac_availability/        # STAC analysis tools
├── tests/                        # Organized test structure
│   ├── unit/                     # Unit tests
│   ├── integration/              # Integration tests
│   └── e2e/                      # End-to-end tests
├── setup-all-services.ps1       # First-time setup
├── run-all-services.ps1         # Start all services
├── kill-all-services.ps1        # Stop all services
└── requirements.txt              # Python dependencies
```

## 📦 Dependencies & Requirements

### Requirements Files
We maintain **2 requirements files**:

1. **`requirements.txt`** (Root) - Development environment
   - Contains all dependencies for local development
   - Used by setup script and virtual environment

2. **`earth-copilot/router-function-app/requirements.txt`** - Azure deployment
   - Azure Functions-specific dependencies
   - Used during function app deployment

### Critical Dependencies
- **semantic-kernel==1.36.2** - AI orchestration (Latest stable)
- **pydantic==2.11.9** - Data validation (Compatible with SK 1.36.2)
- **openai==1.107.2** - OpenAI API integration (Latest compatible)
- **azure-functions>=1.18.0** - Azure Functions runtime
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

### Daily Development
1. **Start services**: `.\run-all-services.ps1`
2. **Develop** in VS Code
3. **Stop services**: `.\kill-all-services.ps1`

### Troubleshooting
1. **Clean restart**: `.\kill-all-services.ps1` then `.\run-all-services.ps1`
2. **Dependency issues**: `.\setup-all-services.ps1 -Force`
3. **Port conflicts**: Check which process is using the port:
   ```powershell
   netstat -ano | findstr ":7071"
   netstat -ano | findstr ":5173"
   ```

### Testing
- **Unit tests**: `pytest tests/unit/`
- **Integration tests**: `pytest tests/integration/`
- **E2E tests**: `pytest tests/e2e/`
- **All tests**: `pytest`

## 🌍 Deployment

### Local Development
- Use `.\run-all-services.ps1`
- React UI runs on `localhost:5173`
- Function app runs on `localhost:7071`

### Azure Deployment
1. **Function App**: Deploy `earth-copilot/router-function-app/`
2. **Static Web App**: Deploy `earth_copilot/react-ui/dist/`
3. **Environment Variables**: Configure in Azure portal

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
.\setup-all-services.ps1 -Force
```

### Port Already in Use
```powershell
# Kill all services first
.\kill-all-services.ps1
# Then restart
.\run-all-services.ps1
```

### Azure Functions Core Tools Issues
```powershell
# Reinstall Azure Functions Core Tools
npm uninstall -g azure-functions-core-tools
npm install -g azure-functions-core-tools@4 --unsafe-perm true
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

## 🎯 Success Criteria

### System is working correctly when:
1. ✅ `.\run-all-services.ps1` starts without errors
2. ✅ React UI loads at `http://localhost:5173`
3. ✅ Health check responds at `http://localhost:7071/api/health`
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