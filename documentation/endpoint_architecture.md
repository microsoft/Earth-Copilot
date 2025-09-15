# Earth Copilot Endpoint Architecture - CURRENT SYSTEM STATUS
**System Status:** Streamlined 2-service architecture with unified backend  
**Current Architecture:** React UI + Router Function (unified backend)

## ✅ **CURRENT SYSTEM STATUS**

### **Production-Ready Simplified Architecture**
- ✅ **STREAMLINED:** 2-service architecture with unified Router Function backend
- ✅ **ORGANIZED:** Clean repository structure with unit/integration/e2e tests
- ✅ **AUTOMATED:** 3-script setup system for easy development workflow
- ✅ **UNIFIED:** Single API endpoint handles all user queries and STAC searches

## 🎯 **SYSTEM ARCHITECTURE OVERVIEW**

### **Current Services**
1. **React UI** (Port 5173) - TypeScript/React frontend with Azure Maps integration
2. **Router Function** (Port 7071) - Unified backend with GPT + STAC functionality

### **Key Improvements**
- **Simplified Architecture:** Reduced complexity with unified backend
- **Professional Setup:** 3-script system (setup, run, cleanup)
- **Enhanced Structure:** Organized tests, documentation, and scripts
- **Clean Codebase:** Removed redundant files and consolidated functionality


### **Service Startup Commands**
```bash
# Start React UI (Terminal 1)
cd /workspaces/Earth-Copilot/earth-copilot/react-ui
npm run dev

# Start Router Function (Terminal 2)  
cd /workspaces/Earth-Copilot/earth-copilot/router-function-app
func host start
```

### **Troubleshooting Port Issues**
If the React UI doesn't load properly:
1. Kill existing processes: `pkill -f vite`
2. Restart with explicit host: `npm run dev -- --host 0.0.0.0`
3. Try alternative port: `npm run dev -- --port 3000`
4. Check VS Code PORTS tab and ensure port 5173 is forwarded

## Service Analysis

### **Service 1: React UI (Port 5173)** ✅ **PRODUCTION READY**
**Location:** `earth_copilot/react-ui/`  
**Technology:** TypeScript, React, Azure Maps v2, Vite

| Component | Purpose | Implementation | Status |
|-----------|---------|----------------|--------|
| **Landing Page** | User query entry | `src/components/LandingPage.tsx` | ✅ **Active** |
| **Main App** | Data visualization | `src/components/MainApp.tsx` | ✅ **Active** |
| **Map View** | Azure Maps integration | `src/components/MapView.tsx` | ✅ **Active** |
| **Chat Interface** | Query interaction | `src/components/Chat.tsx` | ✅ **Active** |
| **Sidebar** | Dataset information | `src/components/Sidebar.tsx` | ✅ **Active** |

### **3. VEDA AI Search Integration** ✅ **CONFIGURED**
**Location:** `earth-copilot/ai-search/`  
**Technology:** Azure AI Search, Vector Embeddings, VEDA Collections

| Component | Purpose | Status |
|-----------|---------|--------|
| **Vector Index** | Indexed VEDA collections with embeddings | ✅ **10 Collections Indexed** |
| **Embedding Service** | Azure OpenAI text-embedding-ada-002 | ✅ **Active** |
| **Search Service** | Vector similarity search | ✅ **Configured** |
| **UI Integration** | VEDA search in React UI | ✅ **Connected** |

**Available Collections:**
- bangladesh-landcover-2001-2020
- barc-thomasfire  
- blizzard-era5-2m-temp
- blizzard-era5-10m-wind
- blizzard-era5-cfrac
- And 5 more indexed VEDA collections

### **Service 2: Router Function (Port 7071)** ✅ **PRODUCTION READY**
**Location:** `earth-copilot/router-function-app/`  
**Technology:** Azure Functions, Python, GPT integration, STAC search

| Endpoint | Method | Purpose | Status |
|----------|--------|---------|--------|
| `/api/health` | GET | Health check | ✅ **Active** |
| `/api/query` | POST | Main user queries | ✅ **Active** |
| `/api/stac-search` | POST | Direct STAC search | ✅ **Active** |

## Current System Architecture

### **Streamlined Data Flow:**
```
React UI (Port 5173)
    ↓ TypeScript/React frontend with Azure Maps
    ↓ User query input via LandingPage or Chat
    ↓ API call to /api/query
Router Function (Port 7071)  
    ↓ GPT natural language processing
    ↓ STAC search integration
    ↓ Microsoft Planetary Computer API
    ↓ Formatted response with map data
    ↓ JSON response to React UI
React UI
    ↓ MapView component renders STAC data
    ↓ Azure Maps visualization
    ↓ User sees results on map
```

## API Endpoint Details

### **1. Health Check Endpoint**
```
GET /api/health
```
**Purpose:** Service health monitoring  
**Response:** Simple status confirmation

### **2. Main Query Endpoint**
```
POST /api/query
Content-Type: application/json

{
  "query": "Show me wildfire data in California",
  "session_id": "web-session-123"
}
```
**Purpose:** Process natural language queries  
**Response:** Contains both text response and map data

### **3. STAC Search Endpoint**
```
POST /api/stac-search
Content-Type: application/json

{
  "collections": ["sentinel-2-l2a"],
  "bbox": [-120, 34, -117, 37],
  "limit": 10
}
```
**Purpose:** Direct STAC API searches  
**Response:** STAC feature collection

### **4. VEDA Search Integration** ✅ **NEW**
**Frontend Service:** Direct Azure AI Search integration in React UI  
**Technology:** Vector similarity search with indexed VEDA collections  
**Purpose:** Private data catalog search using natural language  

**Available via React UI:**
- Vector search across 10 indexed VEDA collections
- Azure OpenAI GPT-5 responses grounded in real data
- Real-time semantic similarity matching

## Development Workflow

### **3-Script Setup System**
```powershell
# 1. Complete environment setup
.\setup-all-services.ps1

# 2. Start all services
.\run-all-services.ps1

# 3. Stop all services and cleanup
.\kill-all-services.ps1
```

### **Project Structure**
```
EC/
├── earth_copilot/
│   ├── react-ui/          # TypeScript React frontend
│   ├── router_function_app/ # Unified Python backend
│   ├── core/              # Configuration utilities
│   └── infra/             # Azure deployment files
├── tests/
│   ├── unit/              # Unit tests
│   ├── integration/       # Integration tests
│   └── e2e/               # End-to-end tests
├── scripts/
│   └── stac_availability/ # STAC analysis tools
├── documentation/         # Project documentation
├── tools/                 # Utility scripts
└── debug/                 # Debugging guides
```

## Testing Structure

### **Organized Test Categories**
- **Unit Tests** (`tests/unit/`): Component and function testing
- **Integration Tests** (`tests/integration/`): API and service interaction testing
- **End-to-End Tests** (`tests/e2e/`): Complete system workflow testing

### **Available Test Commands**
```bash
# Run all tests
pytest tests/

# Run specific test category
pytest tests/unit/
pytest tests/integration/
pytest tests/e2e/
```

## Configuration

### **Environment Setup**
- **React UI**: Uses Vite configuration with proxy setup
- **Router Function**: Uses Azure Functions configuration
- **Dependencies**: Managed via requirements.txt files

### **Key Configuration Files**
- `earth_copilot/react-ui/vite.config.ts` - Frontend proxy configuration
- `earth-copilot/router-function-app/host.json` - Azure Functions configuration
- `requirements.txt` - Development dependencies
- `earth-copilot/router-function-app/requirements.txt` - Production dependencies

## Architecture Benefits

### **Current System Advantages**
- ✅ **Simplified Deployment:** 2 services instead of complex multi-service setup
- ✅ **Enhanced Maintainability:** Unified backend with clear separation of concerns
- ✅ **Professional Workflow:** Automated setup and cleanup scripts
- ✅ **Clean Structure:** Organized tests, documentation, and utilities
- ✅ **Modern Stack:** TypeScript React + Azure Functions + Azure Maps

### **Development Experience**
- ✅ **One-Command Setup:** Complete environment initialization
- ✅ **Fast Iteration:** Hot reloading and automatic restarts
- ✅ **Easy Debugging:** Organized test structure and debug tools
- ✅ **Professional Standards:** Clean code organization and documentation

## Next Steps for Production

### **Azure Deployment Options**
1. **Azure Static Web Apps** for React UI
2. **Azure Web App** for Router Function
3. **GitHub Actions** for CI/CD pipeline

### **Monitoring and Scaling**
1. **Application Insights** for monitoring
2. **Azure App Service** scaling options
3. **Performance optimization** based on usage patterns

This architecture provides a solid foundation for both development and production deployment while maintaining simplicity and professional standards.