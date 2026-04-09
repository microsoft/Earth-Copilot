<div align="center">

<img src="./documentation/images/hero_banner.png" alt="Earth Copilot - AI-Powered Geospatial Intelligence" width="100%"/>

[![Open in GitHub Codespaces](https://github.com/codespaces/badge.svg)](https://codespaces.new/microsoft/earth-copilot)

</div>

# 🌍 Welcome to Earth Copilot!
**An AI-powered geospatial application that allows you to explore and visualize vast Earth science data using natural language queries.**

## Overview

Built with Azure AI Foundry, Semantic Kernel agents, Azure AI Agent Service, and containerized microservices, Earth Copilot automatically finds the right planetary data collection, renders it on a map, and analyzes it for you. Whether you're a scientist, analyst, or decision-maker, Earth Copilot helps you spend less time finding data and more time unlocking insights.

**Watch Satya Nadella introduce NASA Earth Copilot 1.0 at Microsoft Ignite 2024**: [View Here](https://www.linkedin.com/posts/microsoft_msignite-activity-7265061510635241472-CAYx/?utm_source=share&utm_medium=member_desktop)

**Auto-Deploy Ready:** This repository includes fully automated deployment via **Bicep** and **GitHub Actions**. Follow the [Quick Start Guide](QUICK_DEPLOY.md) to deploy the complete architecture: infrastructure, backend, and frontend within one hour. Its modular architecture is designed for extensibility to any use case.

> **This is a proof-of-concept, not a production-ready product.**
> 
> Earth Copilot demonstrates a reusable geospatial AI pattern that can be adapted across different use cases. This open source repository is not supported by Microsoft Copilot and will continue to evolve.

##  Features

- **AI Agent Architecture** — Semantic Kernel + Azure AI Agent Service with extendable modules for vision, terrain, mobility, comparison, building damage, and extreme weather analysis
- **130+ Satellite Collections** — Microsoft Planetary Computer & NASA VEDA data catalog integration
- **Bring Your Own Data** — Connect your own private STAC catalogs via Planetary Computer Pro or extend with custom MCP tools
- **MCP Server Integration** — Model Context Protocol server for integration with VS Code GitHub Copilot and other AI assistants
- **Copilot Studio & M365** — Integrate with Microsoft Copilot Studio for Teams and M365 deployment via custom connectors
- **ArcGIS Integration** — Connect with Esri ArcGIS for advanced geospatial workflows, map services, and enterprise GIS capabilities
- **Fully Private Deployment** — Automated VNet integration with private endpoints, private DNS zones, and Entra ID authentication for an enterprise-ready deployment out of the box


## Use Cases

| | | | | |
|:---:|:---:|:---:|:---:|:---:|
| **Science & Environment** | **Agriculture & Natural Resources** | **Energy & Infrastructure** | **Public Safety & Emergency Management** | **Defense / National Security** |
| Accelerates climate, air quality, land-surface, extreme weather scenarios, and environmental research | Assess drought conditions, soil moisture, and water quality for agriculture planning | Monitor energy grids, transmission corridors, and dam infrastructure, supporting site selection and permitting | Supports response to wildfires, floods, hurricanes, and other natural disasters | Monitor geospatial intelligence and support situational awareness for national security operations |


##  What Earth Copilot Does

![Earth Copilot Interface](documentation/images/EC.png)

### Query Examples

<details>
<summary><b>Satellite Imagery & Visualization</b></summary>

| Query |
|-------|
| Show me high resolution satellite imagery of Dubai urban expansion in 2020 |
| Show me radar imagery of Houston Texas during Hurricane Harvey August 2017 |
| Show me HLS Landsat imagery for Ukraine farmland from 2024 |
| Show me burned area mapping for Montana wildfire regions 2023 |
| Show me NDVI vegetation health for Iowa cropland summer 2024 |
| Show me sea surface temperature anomalies in the Gulf of Mexico |

</details>

<details>
<summary><b>Contextual Earth Science Questions</b></summary>

| Query |
|-------|
| How was NYC impacted by Hurricane Sandy |
| What was the impact of Hurricane Florence 2018 in North Carolina |
| How did vegetation recover after flooding in Missouri River valley 2023 |
| What are the long-term climate trends affecting Pacific Northwest forests |
| Explain the correlation between El Niño events and wildfire patterns |

</details>

<details>
<summary><b>Geointelligence & Raster Analysis</b></summary>

| Module | Query |
|--------|-------|
| **Vision** | Analyze this satellite image — what land cover types are visible and what is the surface reflectance? |
| **Terrain** | Analyze terrain elevation, slope, and line-of-sight at 38.9N, 77.0W |
| **Comparison** | Show wildfire activity in Southern California in January 2025 and analyze how it evolved over 48 hours |
| **Mobility** | Classify terrain traversability at these coordinates across 5 elevation layers |
| **Building Damage** | Assess building damage using before/after satellite imagery at these coordinates |
| **Extreme Weather** | What are the projected temperature and precipitation trends for Miami through 2050? |

</details>

<details>
<summary><b>Private Data Search with RAG</b></summary>

| Query |
|-------|
| Analyze our proprietary STAC collection for mineral exploration sites |
| Compare our private agricultural data with public MODIS vegetation indices |
| Search our internal disaster response catalog for similar flood patterns |
| Query our custom satellite constellation for urban heat island analysis |

</details>

### Examples

![GEOINT Modules](./documentation/images/modules.png)

<table>
<tr>
<td align="center" width="25%"><b>ALOS World (Berlanga)</b><br/><img src="./documentation/images/maps/alos_world_berlanga.png" width="220"/></td>
<td align="center" width="25%"><b>Burn Severity (California)</b><br/><img src="./documentation/images/maps/burn_severity_california.png" width="220"/></td>
<td align="center" width="25%"><b>Cropland (Florida)</b><br/><img src="./documentation/images/maps/cropland_florida.png" width="220"/></td>
<td align="center" width="25%"><b>Elevation (Grand Canyon)</b><br/><img src="./documentation/images/maps/elevation_grand_canyon.png" width="220"/></td>
</tr>
<tr>
<td align="center"><b>HLS Greece Elevation</b><br/><img src="./documentation/images/maps/hls_greece_elevation.png" width="220"/></td>
<td align="center"><b>LIDAR Height (New Orleans)</b><br/><img src="./documentation/images/maps/lidar_height_new_orleans.png" width="220"/></td>
<td align="center"><b>MODIS Snow Cover (Quebec)</b><br/><img src="./documentation/images/maps/modis_snow_cover_quebec.png" width="220"/></td>
<td align="center"><b>Nadir BDRF (Mexico)</b><br/><img src="./documentation/images/maps/nadir_bdrf_mexico.png" width="220"/></td>
</tr>
<tr>
<td align="center"><b>Net Production (San Jose)</b><br/><img src="./documentation/images/maps/net_production_san_jose.png" width="220"/></td>
<td align="center"><b>Sea Surface Temp (Madagascar)</b><br/><img src="./documentation/images/maps/sea_surface_temp_madagascar.png" width="220"/></td>
<td align="center"><b>Sentinel (NYC)</b><br/><img src="./documentation/images/maps/sentinel_nyc.png" width="220"/></td>
<td align="center"><b>Sentinel RTC (Philippines)</b><br/><img src="./documentation/images/maps/sentinel_rtc_philipines.png" width="220"/></td>
</tr>
<tr>
<td align="center"><b>Surface Water (Bangladesh)</b><br/><img src="./documentation/images/maps/surface_water_bangladesh.png" width="220"/></td>
<td align="center"><b>Vegetation Indices (Ukraine)</b><br/><img src="./documentation/images/maps/vegetation_indices_ukraine.png" width="220"/></td>
<td align="center"><b>Vision Agent</b><br/><img src="./documentation/images/maps/agent_vision.png" width="220"/></td>
<td align="center"><b>Vision Agent</b><br/><img src="./documentation/images/maps/agent_vision_fire.png" width="220"/></td>
</tr>
<tr>
<td align="center"><b>Terrain Agent</b><br/><img src="./documentation/images/maps/agent_terrain_galapagos.png" width="220"/></td>
<td align="center"><b>Terrain Agent</b><br/><img src="./documentation/images/maps/agent_terrain_florida.png" width="220"/></td>
<td align="center"><b>Terrain Agent</b><br/><img src="./documentation/images/maps/agent_terrain_huston.png" width="220"/></td>
<td align="center"><b>Mobility Agent</b><br/><img src="./documentation/images/maps/agent_mobility.png" width="220"/></td>
</tr>
<tr>
<td align="center"><b>Mobility Agent</b><br/><img src="./documentation/images/maps/agent_mobility_alos_palsar_equador.png" width="220"/></td>
<td align="center"><b>Extreme Weather Agent</b><br/><img src="./documentation/images/maps/agent_extreme_weather.png" width="220"/></td>
<td align="center"><b>Extreme Weather Agent</b><br/><img src="./documentation/images/maps/agent_extreme_weather_new_orleans.png" width="220"/></td>
<td align="center"><b>Thermal Anomalies (Australia)</b><br/><img src="./documentation/images/maps/thermal_anomalies_australia.png" width="220"/></td>
</tr>
</table>

---


##  Architecture

![Earth Copilot Architecture](documentation/images/architecture.png)

### Query Processing Pipeline

| Step | Technology |
|------|-----------|
| **Unified Router** — Classifies intent and routes to the right agent | Semantic Kernel |
| **Location Resolver** — Resolves place names to coordinates | Azure Maps, Google Maps, Mapbox |
| **Collection Mapping Agent** — Matches query to satellite data collections | Azure AI Foundry (model of choice) |
| **STAC Query Builder Agent** — Builds spatial-temporal search queries | Azure AI Foundry (model of choice) |
| **STAC Search Executor** — Searches Planetary Computer & VEDA catalogs | STAC API |
| **Tile Selector** — Picks the best imagery tiles from results | Function / LLM |
| **TiTiler Renderer** — Renders satellite tiles for map display | TiTiler |

**GEOINT Modules:**
| Module | Agent Class | Type | Status |
|--------|-------------|------|:------:|
| **Vision** | `EnhancedVisionAgent` | Azure AI Agent + 5 Tools |  Active |
| **Terrain** | `TerrainAgent` | Azure AI Agent + Tools |  Active |
| **Mobility** | `GeointMobilityAgent` | Azure AI Agent + Vision |  Active |
| **Comparison** | `ComparisonAgent` | Azure AI Agent (Query Mode) |  Active |
| **Building Damage** | `BuildingDamageAgent` | Azure AI Agent + 2 Tools |  Active |
| **Extreme Weather** | `ExtremeWeatherAgent` | Azure AI Agent + 7 Tools |  Active |


**Detailed Architecture Documentation:** [Agent System Overview](documentation/architecture/agent_system_overview.md)

### Core Services

**React UI (`earth-copilot/web-ui/`) - Azure Web Apps**
- **Main Search Interface**: Unified natural language query input
- **Chat Sidebar**: Conversation history with context awareness
- **Azure Maps Integration**: Interactive map with satellite overlay and geointelligence results
- **Data Catalog Selector**: Switch between MPC, NASA VEDA, and custom data sources
- **Technology**: React 18, TypeScript, Vite, Azure Maps SDK v2

**Container App Backend (`earth-copilot/container-app/`) - Azure Container Apps**
- **Semantic Kernel Framework**: Multi-agent orchestration with Azure AI Foundry (model of choice)
- **AI Agents**: Query processing and geointelligence analysis pipeline
- **STAC Integration**: Microsoft Planetary Computer and NASA VEDA API connectivity
- **Geointelligence Processing**: Terrain analysis, mobility classification, line-of-sight (GDAL/Rasterio)
- **Multi-Strategy Geocoding**: Google Maps, Azure Maps, Mapbox, OpenAI fallback
- **Hybrid Rendering System**: TiTiler integration for 113+ satellite collection types
- **VNet Integration**: Enterprise-grade security with private networking
- **Technology**: Python 3.12, FastAPI, Semantic Kernel, Azure Container Apps

**Azure Infrastructure**
- **Azure AI Foundry**: Model deployments for agent intelligence (GPT-5 or model of choice)
- **Azure AI Agent Service**: Multi-turn tool orchestration for GEOINT agents (Hub + Project)
- **Azure Maps**: Geocoding, reverse geocoding, and map tile services
- **Azure AI Search**: Vector search for private data catalogs (RAG)
- **Azure Storage**: Blob storage for geointelligence raster processing results
- **Virtual Network**: Private networking with private endpoints and DNS resolution

**MCP Server (`earth-copilot/mcp-server/`) - Model Context Protocol (Optional)**
- **GitHub Copilot Integration**: Expose Earth Copilot as tool for VS Code
- **HTTP Bridge**: MCP protocol bridge for external tool access
- **Technology**: Python, FastAPI, Docker, Azure Container Apps

**Copilot Studio - M365 Integration (Optional)**
- **Teams Bot**: Chat with Earth Copilot directly inside Microsoft Teams
- **M365 Copilot Plugin**: Extend Microsoft 365 Copilot with geospatial capabilities
- **Custom Connector**: Points to the deployed backend API — no additional infrastructure required


##  Environment Setup

### Prerequisites

**Technical Background:**
- **Azure Subscription Management** - Resource groups, RBAC, cost management, service quotas
- **Azure Cloud Services** - Azure AI Foundry, Azure Maps, Container Apps, AI Search
- **Python Development** - Python 3.12, FastAPI, async programming, package management
- **React/TypeScript** - React 18, TypeScript, Vite, modern JavaScript
- **AI/ML Concepts** - LLMs, Semantic Kernel, multi-agent systems, RAG
- **Geospatial Data** - STAC standards, satellite imagery, raster processing (GDAL/Rasterio)
- **Docker & Containers** - Docker builds, Azure Container Apps, VNet integration
- **Infrastructure as Code** - Bicep templates, Azure CLI, resource deployment

### Quick Start with VS Code Agent Mode

You can deploy this application using **Agent mode in Visual Studio Code** or **GitHub Codespaces**:

[![Open in GitHub Codespaces](https://github.com/codespaces/badge.svg)](https://codespaces.new/microsoft/earth-copilot)

![VS Code Agent Mode](documentation/images/vsc_agentmode.png)

### Azure Services Setup

>  **For step-by-step deployment instructions, see [QUICK_DEPLOY.md](QUICK_DEPLOY.md)**

**Services Deployed Automatically:**
- **Azure AI Foundry** - Model deployment for AI agents (GPT-5 or model of choice)
- **Azure AI Agent Service** - Multi-turn tool orchestration for GEOINT agents
- **Azure Container Apps** - Backend API hosting (VNet-integrated when private endpoints enabled)
- **Azure Web Apps** - Frontend hosting  
- **Azure Maps** - Geocoding and map visualization
- **Azure Container Registry** - Docker image storage (with VNet-integrated build agent pool when private endpoints are enabled)

**Data Sources (External - No Setup Required):**
- **Microsoft Planetary Computer STAC API** - 113+ global satellite collections
- **NASA VEDA STAC API** - Earth science datasets from NASA missions


##  Deployment Guide

###  GitHub Actions Deployment (Recommended)

Deploy Earth Copilot to Azure using fully automated GitHub Actions.

 **Complete Step-by-Step Guide:** [**QUICK_DEPLOY.md**](QUICK_DEPLOY.md) ← Start here!

```powershell
# 1. Fork the repo on GitHub, then clone your fork
git clone https://github.com/YOUR-USERNAME/Earth-Copilot.git
cd Earth-Copilot
```

## Extend & Integrate

After deploying the core application, you can extend Earth Copilot with these optional integrations:

| Integration | What It Does | Guide |
|-------------|-------------|-------|
| **Planetary Computer Pro** | Upload and query your own private satellite data alongside 130+ public collections. Connect your private STAC catalog so Earth Copilot searches both public and private datasets in a single query. | [Planetary Computer Pro](https://planetarycomputer.microsoft.com/docs/concepts/what-is-pc-pro/) |
| **Copilot Studio** | Chat with Earth Copilot in **Microsoft Teams** (as a bot) or inside **M365 Copilot** (as a plugin). Create a custom connector pointing to your deployed backend API — no additional infrastructure required. | [Microsoft Copilot Studio](https://learn.microsoft.com/microsoft-copilot-studio/) |
| **MCP Server** | Expose Earth Copilot as a Model Context Protocol (MCP) server so VS Code GitHub Copilot, Claude Desktop, and other MCP-compatible AI assistants can search satellite imagery and run GEOINT analyses directly from the chat. | [Setup Guide](earth-copilot/mcp-server/README.md) |


##  Project Structure

```
Earth-Copilot/
├── earth-copilot/                       # Main application directory
│   ├── container-app/                   # FastAPI backend (Container Apps)
│   │   ├── fastapi_app.py                 # Main FastAPI application
│   │   ├── semantic_translator.py         # STAC query orchestrator
│   │   ├── location_resolver.py           # Multi-strategy geocoding
│   │   ├── collection_profiles.py         # Collection mappings
│   │   ├── collection_name_mapper.py      # Collection name resolution
│   │   ├── tile_selector.py               # Tile selection logic
│   │   ├── hybrid_rendering_system.py     # TiTiler rendering configs
│   │   ├── titiler_config.py              # TiTiler configuration
│   │   ├── veda_collection_profiles.py    # NASA VEDA collection profiles
│   │   ├── pc_tasks_config_loader.py      # Planetary Computer config loader
│   │   ├── pc_rendering_config.json       # Rendering configuration
│   │   ├── quickstart_cache.py            # Quick-start query cache
│   │   ├── requirements.txt               # Python dependencies
│   │   ├── Dockerfile                     # Container build
│   │   ├── agents/                        # Semantic Kernel agents
│   │   │   └── enhanced_vision_agent.py     # Vision Agent (SK)
│   │   └── geoint/                        # Azure AI Agent Service modules
│   │       ├── agents.py                    # Agent factory & initialization
│   │       ├── router_agent.py              # Router Agent (Semantic Kernel)
│   │       ├── terrain_agent.py             # Terrain Analysis Agent
│   │       ├── terrain_tools.py             # Terrain tool definitions
│   │       ├── mobility_agent.py            # Mobility Classification Agent
│   │       ├── mobility_tools.py            # Mobility tool definitions
│   │       ├── comparison_agent.py          # Temporal Comparison Agent
│   │       ├── comparison_tools.py          # Comparison tool definitions
│   │       ├── building_damage_agent.py     # Building Damage Agent
│   │       ├── building_damage_tools.py     # Building Damage tool definitions
│   │       ├── extreme_weather_agent.py     # Extreme Weather Agent
│   │       ├── extreme_weather_tools.py     # Extreme Weather tool definitions
│   │       ├── vision_analyzer.py           # Vision analysis utilities
│   │       ├── chat_vision_analyzer.py      # Chat-based vision analysis
│   │       ├── raster_data_fetcher.py       # Raster data extraction
│   │       └── tools.py                     # Shared GEOINT tools
│   │
│   ├── web-ui/                          # React frontend (Static Web App)
│   │   ├── src/
│   │   │   ├── components/                # React components
│   │   │   │   ├── Chat.tsx                 # Chat interface
│   │   │   │   ├── MapView.tsx              # Azure Maps + satellite overlays
│   │   │   │   ├── DatasetDropdown.tsx      # Data source selection
│   │   │   │   ├── GeointOverlay.tsx        # GEOINT module overlay
│   │   │   │   ├── LandingPage.tsx          # Landing page
│   │   │   │   ├── PCSearchPanel.tsx        # Planetary Computer search
│   │   │   │   └── ...
│   │   │   ├── services/                  # API integration
│   │   │   │   ├── api.ts                   # Backend API client
│   │   │   │   └── vedaSearchService.ts     # NASA VEDA integration
│   │   │   ├── ui/                        # UI layout components
│   │   │   └── utils/                     # Rendering & tile utilities
│   │   ├── public/                        # Static assets & config
│   │   ├── package.json                   # Node.js dependencies
│   │   ├── vite.config.ts                 # Vite build config
│   │   ├── vitest.config.ts               # Test config
│   │   └── staticwebapp.config.json       # Azure SWA config
│   │
│   ├── mcp-server/                      # MCP server (Optional)
│   │   ├── server.py                      # MCP server with tool definitions
│   │   ├── mcp_bridge.py                  # MCP HTTP bridge for external access
│   │   ├── requirements.txt               # MCP dependencies
│   │   ├── Dockerfile                     # MCP container build
│   │   ├── deploy-mcp-server.ps1          # Deployment script
│   │   ├── test_deployed_mcp.py           # Production tests
│   │   ├── test_mcp_server.py             # Unit tests
│   │   ├── CLIENT_CONNECTION_GUIDE.md     # Client connection guide
│   │   ├── QUICK_START.md                 # Quick start guide
│   │   └── apim/                          # API Management
│   │       ├── apim-template.json           # APIM template
│   │       └── deploy-apim.ps1              # APIM deployment
│   │
│   ├── copilot-studio/                  # Copilot Studio integration (Optional)
│   │
│   ├── ai-search/                       # Azure AI Search setup
│   │   ├── README.md
│   │   ├── setup.sh
│   │   └── scripts/                       # Index creation scripts
│   │       ├── create_search_index_with_vectors.py
│   │       └── requirements.txt
│   │
│   ├── infra/                           # Infrastructure as Code
│   │   ├── main.bicep                     # Main Bicep template
│   │   ├── main.parameters.json           # Parameters
│   │   ├── README.md
│   │   ├── app/                           # App-specific resources
│   │   │   └── web.bicep
│   │   └── shared/                        # Shared infrastructure
│   │       ├── ai-foundry.bicep             # AI Foundry Hub + Project
│   │       ├── ai-search.bicep              # AI Search service
│   │       ├── apps-env.bicep               # Container Apps Environment
│   │       ├── keyvault.bicep               # Key Vault
│   │       ├── maps.bicep                   # Azure Maps
│   │       ├── monitoring.bicep             # Log Analytics
│   │       ├── openai-role-assignment.bicep # OpenAI role assignments
│   │       ├── registry.bicep               # Container Registry
│   │       └── storage.bicep                # Storage Account
│   │
│   ├── scripts/                         # App-level scripts
│   │   └── health-check.sh
│   │
│   ├── azure.yaml                       # Azure Developer CLI config
│   └── deploy-all.ps1                   # Deploy all services
│
├── documentation/                       # Project documentation
│   ├── architecture/
│   │   ├── agent_system_overview.md       # Agent architecture
│   │   ├── geoint_agent_tools.md          # GEOINT tools reference
│   │   └── semantic_translator_logic.md   # Translator logic
│   ├── data_collections/
│   │   ├── stac_collections.md            # 113+ collections reference
│   │   └── tiles.md                       # Tile rendering guide
│   └── images/                          # Screenshots and diagrams
│
├── scripts/                             # Utility & setup scripts
│   ├── bootstrap-github-environment.ps1   # GitHub environment setup
│   ├── bootstrap-github-environment.sh
│   ├── enable-agent-service.ps1           # Enable Azure AI Agent Service
│   ├── enable-backend-auth.ps1            # Enable backend auth
│   ├── enable-webapp-auth.ps1             # Enable web app auth
│   ├── restrict-access.ps1                # Restrict resource access
│   ├── verify-requirements.py             # Verify dependencies
│   ├── stac_availability/                 # STAC data exploration
│   │   └── generate_dataset_table.py
│   └── veda_availability/                 # VEDA data exploration
│       └── comprehensive_veda_analyzer.py
│
├── .github/                             # GitHub configuration
│   ├── copilot/
│   │   └── mcp-servers.json               # MCP server config for Copilot
│   ├── environment-config-template.yml    # Environment config template
│   └── workflows/
│       └── deploy.yml                     # CI/CD deployment workflow
│
├── deploy-infrastructure.ps1            # Deploy all Azure resources
├── requirements.txt                     # Root Python dependencies (dev)
├── README.md                            # This file
├── QUICK_DEPLOY.md                      # Automated deployment guide
├── LICENSE.txt                          # MIT License
├── SECURITY.md                          # Security policy
├── SUPPORT.md                           # Support information
├── CONTRIBUTING.md                      # Contribution guidelines
└── CODE_OF_CONDUCT.md                   # Code of conduct
```

##  License

MIT License - see [LICENSE.txt](LICENSE.txt) for details.

## Trademarks

This project may contain trademarks or logos for projects, products, or services. Authorized use of Microsoft trademarks or logos is subject to and must follow [Microsoft's Trademark & Brand Guidelines](https://www.microsoft.com/en-us/legal/intellectualproperty/trademarks/usage/general). Use of Microsoft trademarks or logos in modified versions of this project must not cause confusion or imply Microsoft sponsorship. Any use of third-party trademarks or logos are subject to those third-party's policies.

---

##  Acknowledgments

Earth Copilot was developed by Melisa Bardhi and advised by Juan Carlos Lopez.

A big thank you to our collaborators: 
- **Microsoft Planetary Computer** 
- **NASA**
- **Microsoft Team**: Juan Carlos Lopez, Jocelynn Hartwig, Minh Nguyen & Matt Morrell.

*Built for the Earth science community with ❤️ and AI*
