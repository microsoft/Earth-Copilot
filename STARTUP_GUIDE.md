# Earth Copilot - Startup Guide

This guide helps new users get Earth Copilot running quickly and correctly.

## Prerequisites

Before starting, ensure you have:
- **Python 3.8+** (Check with `python3 --version`)
- **Node.js 16+** (Check with `node --version`)
- **Azure Functions Core Tools** (Install with `npm install -g azure-functions-core-tools@4 --unsafe-perm true`)

## Quick Start (Recommended)

### Option 1: Automated Setup + Run
```bash
# 1. First-time setup (only needed once)
./setup-all-services.sh

# 2. Start all services
./run-all-services.sh
```

### Option 2: VS Code Integration
1. Open the project in VS Code
2. Use `Ctrl+Shift+P` → "Tasks: Run Task" → "func: host start"
3. In a separate terminal: `cd earth-copilot/react-ui && npm run dev`

### Option 3: Manual Development (Two Terminal Approach)

**⚠️ Important**: For development work, you need **TWO separate terminal sessions** running simultaneously.

**Why Two Terminals?**
- **Azure Functions** runs a continuous Python process serving API endpoints
- **React UI** runs a Vite development server with hot-reload capability  
- Both services must run simultaneously for full application functionality

```bash
# Terminal 1: Start Function App (Backend - Port 7071)
cd earth-copilot/router-function-app
source ../../.venv/bin/activate  # Activate virtual environment
func host start --port 7071

# Terminal 2: Start React UI (Frontend - Port 5173)
cd earth-copilot/react-ui
npm run dev
```

**Development Workflow**: Keep both terminals running while developing. The React UI will auto-reload on code changes, and the Function App will restart when Python files are modified.

## Service Endpoints

After startup, you'll have:

| Service | URL | Description |
|---------|-----|-------------|
| **React UI** | http://localhost:5173 | Main application interface |
| **Function App** | http://localhost:7071 | Backend API |
| **Health Check** | http://localhost:7071/api/health | Service status |
| **STAC Search** | http://localhost:7071/api/stac-search | Satellite data search |
| **Unified Query** | http://localhost:7071/api/query | Natural language queries |

## Testing the Application

1. **Open the UI**: Navigate to http://localhost:5173
2. **Test STAC functionality**: Try a query like "Show me satellite imagery of California"
3. **Verify results**: Check that satellite data appears on the map
4. **Check health**: Visit http://localhost:7071/api/health for backend status

## Port Configuration

The application uses these default ports:
- **5173**: React UI (Vite dev server)
- **7071**: Azure Functions

## Troubleshooting

### Common Issues

**Port already in use:**
```bash
# Clean up existing processes
./kill-all-services.sh
# Or manually:
pkill -f "func host" && pkill -f "vite"
```

**Virtual environment not found:**
```bash
# Run setup script first
./setup-all-services.sh
```

**Function App not starting:**
- Check Azure Functions Core Tools: `func --version`
- Verify Python virtual environment: `source .venv/bin/activate`
- Verify environment files exist: Check `.env` in project root
- Check logs: `tail -f /tmp/functions.log`

**React UI not loading:**
- Verify Node.js installation: `node --version`
- Install dependencies: `cd earth-copilot/react-ui && npm install`
- Verify environment files exist: Check `earth-copilot/react-ui/.env`
- Check logs: `tail -f /tmp/vite.log`

**Environment Configuration Issues:**
- Ensure all three environment files are configured:
  - Root `.env` with Azure OpenAI and Maps credentials
  - React UI `.env` with VITE_ prefixed variables
  - Function App `local.settings.json` with runtime settings
- Use the `.example` files as templates for proper formatting

### Environment Variables

The application uses **multiple environment files** for different components:

#### 1. Root Environment (Backend Services)
- **File**: `.env` (in project root)
- **Template**: `.env.example` (copy and configure)
- **Purpose**: Azure OpenAI, Azure Maps, and backend service credentials
- **Used by**: Router Function App for API calls

#### 2. React UI Environment (Frontend) 
- **File**: `earth-copilot/react-ui/.env`
- **Template**: `earth-copilot/react-ui/.env.example` (copy and configure)
- **Purpose**: Frontend variables (all prefixed with `VITE_`)
- **Used by**: React components and Vite build process

#### 3. Azure Functions Configuration
- **File**: `earth-copilot/router-function-app/local.settings.json`
- **Template**: `earth-copilot/router-function-app/local.settings.json.example`
- **Purpose**: Azure Functions runtime configuration
- **Used by**: Azure Functions Core Tools

**Setup Instructions**: Copy each `.example` file to remove the `.example` extension, then fill in your Azure service credentials.

## Architecture Overview

```
┌─────────────────┐    ┌─────────────────┐
│   React UI      │    │  Function App   │
│   (Port 5173)   │◄──►│   (Port 7071)   │
│                 │    │                 │
│ • User Interface│    │ • STAC Search   │
│ • Map Display   │    │ • AI Search     │
│ • Query Input   │    │ • Health API    │
└─────────────────┘    └─────────────────┘
                              │
                              ▼
                    ┌─────────────────┐
                    │ Microsoft       │
                    │ Planetary       │
                    │ Computer        │
                    └─────────────────┘
```

## Support

- **Documentation**: See the `documentation/` folder
- **Issues**: Check `DEBUG_GUIDE.md` for troubleshooting
- **Logs**: Service logs are in `/tmp/functions.log` and `/tmp/vite.log`

---

✅ **Success**: Both services running and accessible
🌐 **Ready**: Navigate to http://localhost:5173 to start using Earth Copilot!