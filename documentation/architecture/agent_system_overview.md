# Earth Copilot - Architecture & Agent System

## Table of Contents

1. [Frontend Experience](#1-frontend-experience)
2. [Data Access](#2-data-access)
3. [Backend Architecture](#3-backend-architecture)
4. [Agent System (Query Processing Pipeline)](#4-agent-system-query-processing-pipeline)
   - Agent 1: Intent Classification
   - Agent 2: Collection Mapping
   - Agent 3: STAC Query Builder (Orchestrator)
   - Agent 4: Location Extraction
   - Agent 5: Datetime Translation
   - Agent 6: Cloud Filtering
   - Agent 7: Tile Selector
   - Hybrid Rendering System (Utility)
   - Agent 8: Response Generation
5. [Agent Pipeline Summary](#5-agent-pipeline-summary)
6. [Geointelligence Pin Drop Module](#6-geointelligence-pin-drop-module-advanced-raster-analysis)
   - Agent 9: Terrain Analysis (7 Function Tools + Vision)
   - Agent 10: Mobility Analysis (5 Function Tools + Raster + Vision)
   - Agent 11: Building Damage Assessment (2 Function Tools)
   - Agent 12: Comparison Analysis (3 Function Tools)
   - Agent 13: Extreme Weather Analysis (7 Function Tools)
   - Agent 14: Animation Generation (Stub)
   - Router Agent (Semantic Kernel)
   - Enhanced Vision Agent (13 Function Tools)
   - GEOINT Orchestrator
7. [API Endpoints](#7-api-endpoints)
   - Core Endpoints (4)
   - Geointelligence Endpoints (14)
   - Processing Endpoints (3)
   - Utility Endpoints (9)
8. [Complete System Summary](#8-complete-system-summary)
   - Agent Inventory (19 Total)
   - Technology Stack

---

## Overview

Earth Copilot is a natural language geospatial intelligence platform powered by Azure AI Foundry (model of choice) and Semantic Kernel. It enables users to query satellite imagery and geospatial data using conversational language, with automated data discovery, intelligent tile selection, and dynamic map visualization.

**Key Capabilities:**
- **14 AI Agents** (8 text query agents + 6 geointelligence pin-drop agents)
- **113+ Satellite Collections** from Microsoft Planetary Computer & NASA VEDA
- **5-Layer Raster Analysis** for mobility/terrain assessment
- **Azure AI Agent Service** for multimodal satellite imagery analysis

---

## 1. Frontend Experience

**Technology Stack:**
- React + TypeScript
- Azure Maps SDK for visualization
- Deployed as Azure App Service (Static Web App)

**Key Features:**
- **Natural Language Search:** Users type queries like "Show me Sentinel-2 imagery of Seattle from last month"
- **Results Page:** Azure Maps with integrated chatbot sidebar
- **Dynamic Multi-Catalog Rendering:** Supports 113+ collections from Microsoft Planetary Computer and NASA VEDA
- **Interactive Legends:** Auto-generated legends for fire detection, NDVI, water bodies, etc.
- **Contextual Chat:** Follow-up questions maintain conversation context

---

## 2. Data Access

**Primary Data Sources:**
- **Microsoft Planetary Computer (MPC):** 113+ STAC collections including Sentinel-2, Landsat, MODIS, SAR, DEM
- **NASA VEDA:** Climate and Earth science datasets via STAC API
- **Custom Data:** Azure AI Search integration for client-uploaded datasets

**For comprehensive collection details, see:** [STAC Collections Reference](../data_collections/stac_collections.md)

**Collection Categories:**
- **Optical Imagery** (12 collections): Sentinel-2, Landsat, HLS, NAIP
- **Radar/SAR** (6 collections): Sentinel-1 GRD/RTC, ALOS PALSAR
- **Elevation/Terrain** (10 collections): Copernicus DEM, NASADEM, 3DEP Lidar
- **Fire Detection** (8 collections): MODIS thermal anomalies, burned area, MTBS
- **Weather/Climate** (15+ collections): ERA5, Daymet, ECMWF, GOES
- **Vegetation** (12 collections): MODIS NDVI/LAI/GPP/NPP, biomass
- **Land Cover** (10 collections): 10m global land use, ESA WorldCover, forest mapping
- **Water/Hydrology** (8 collections): National Water Model, surface water, precipitation
- **Snow/Ice** (3 collections): MODIS/VIIRS snow cover
- **Atmospheric** (4 collections): Sentinel-5P air quality, aerosols
- **Ocean/Marine** (5 collections): Ocean color, SST, wave height
- **Specialized** (10+ collections): Buildings, biodiversity, soil, solar, demographics

---

## 3. Backend Architecture

**Deployment:**
- Azure Container App (VNet-integrated for security)
- Python FastAPI backend
- Semantic Kernel framework for AI orchestration

**Core Components:**
- `semantic_translator.py` - Multi-agent system
- `collection_profiles.py` - Single source of truth for 113+ collections
- `hybrid_rendering_system.py` - Dynamic TiTiler URL generation
- `location_resolver.py` - Multi-tier geocoding (Azure Maps, Nominatim, GPT fallback)

---

## 4. Multi-Agent System (Semantic Kernel)

### **Agent 1: Unified Intent Classification**

**Purpose:** Determines query type and required modules

**Intent Types:**
- `stac` - Map visualization (STAC query required)
- `contextual` - Information/educational questions
- `hybrid` - Map + contextual explanation
- `vision` - Analyze currently displayed imagery

**Output Example:**
```json
{
  "intent_type": "stac",
  "needs_satellite_data": true,
  "needs_contextual_info": true,
  "confidence": 0.95
}
```

---

### **Agent 2: Collection Mapping Agent**

**Purpose:** Select relevant STAC collections based on query intent

**Input:** Natural language query  
**Process:**
- Analyzes 113+ collection profiles from `COLLECTION_PROFILES`
- Understands explicit mentions ("Sentinel-2") and implicit needs ("high-resolution imagery")
- Applies keyword priority rules (SAR, MODIS, elevation, fire, etc.)

**Output:** List of collection IDs (e.g., `["sentinel-2-l2a", "landsat-c2-l2"]`)

**Fallback:** Keyword-based selection if GPT unavailable

---

### **Agent 3: STAC Query Builder (Orchestrator Agent)**

**Purpose:** Orchestrates multiple specialized agents to construct complete STAC API query

**Architecture:** Composite orchestrator that coordinates 3 GPT-powered agents + 1 utility function

**Orchestration Flow:**
```
Agent 3 (Orchestrator)
├── Agent 4: Location Extraction (GPT) → location name
├── Utility: Location Resolution (APIs) → bbox coordinates  
├── Agent 5: Datetime Translation (GPT) → ISO 8601 datetime
├── Agent 6: Cloud Filtering (GPT) → cloud cover threshold
└── Output: Complete STAC query dictionary
```

**Agents Coordinated:**

---

### **Agent 4: Location Extraction Agent (GPT-Powered)**
- **Type:** AI Agent (uses Azure AI Foundry, model of choice)
- **Input:** Natural language query
- **Process:** Extracts location entities from query text
- **Handles:** Cities ("Seattle"), regions ("Pacific Northwest"), landmarks ("Grand Canyon"), coordinates
- **Output:** `{"location": {"name": "Seattle", "type": "city", "confidence": 0.9}}`

---

### **Location Resolution Utility (Multi-Tier Geocoding)**
- **Type:** Utility function
- **Input:** Location name from Agent 4
- **Cascade Strategy:**
  1. **Hardcoded/Stored Locations** (instant lookup for common places)
  2. **Azure Maps API** (primary geocoding service)
  3. **Azure OpenAI** (AI-powered geographic inference)
  4. **Nominatim** (OpenStreetMap, free fallback)
  5. **GeoNames** (alternative geographic database)
- **Output:** Bounding box `[west, south, east, north]` coordinates

---

### **Agent 5: Datetime Translation Agent (GPT-Powered)**
- **Type:** AI Agent (uses Azure AI Foundry, model of choice)
- **Input:** Natural language temporal expressions
- **Process:** Converts phrases to ISO 8601 datetime ranges
- **Handles:** "last month", "Q3 2024", "October 15, 2023", "recent", comparison mode (before/after)
- **Output:** `"2024-09-01T00:00:00Z/2024-09-30T23:59:59Z"`

---

### **Agent 6: Cloud Filtering Agent (GPT-Powered)**
- **Type:** AI Agent (uses Azure AI Foundry, model of choice)
- **Input:** Query intent and collection types
- **Process:** Determines if cloud cover filtering should be applied
- **Used With:** Optical collections (Sentinel-2, Landsat)
- **Output:** `{"filter": {"eo:cloud_cover": {"lt": 20}}}` or `None`

---

### **Orchestrator Role (Agent 3):**
- Sequences agent execution (location → datetime → cloud filter)
- Aggregates results into unified STAC query structure
- Handles error fallbacks for each sub-component
- Returns complete query ready for STAC API execution

---

### **Agent 7: Tile Selector Agent (Conditional GPT-Powered Agent)**

**When Invoked:** 
- Large areas (>10,000 km²)
- Multiple collections with different resolutions
- User requests "highest resolution" or "best quality"

**Selection Strategy:**
1. **Highest Resolution Priority** - Select best resolution available (e.g., 10m over 30m)
2. **Full Spatial Coverage** - Ensure 100% coverage of requested area
3. **Single Temporal Snapshot** - All tiles from same acquisition datetime
4. **Query-Specific Criteria** - Respect cloud cover, date preferences

**GPT-Powered Logic:** Analyzes tile summary and makes intelligent selection

**Fallback:** Rule-based selection (sort by resolution, date, cloud cover)

---

### **Hybrid Rendering System (Utility Class)**

**Type:** Deterministic utility class (NOT an agent - no GPT/AI)

**Purpose:** Maps STAC collections to optimal visualization parameters

**Process:**
1. Looks up collection in 113+ predefined rendering configs
2. Determines appropriate bands (RGB, thermal, NDVI, etc.)
3. Applies color scales (fire: YlOrRd, water: Blues, NDVI: RdYlGn)
4. Generates TiTiler URL parameters

**Implementation:** `HybridRenderingSystem` class with static methods

**Output:** TiTiler URL parameters and rendering metadata

---

### **Agent 8: Response Generation (GPT-Powered)**

**Type:** AI Agent (uses Azure AI Foundry, model of choice)

**Purpose:** Generate natural language explanations of query results

**Process:**
- Analyzes STAC search results and tile selections
- Incorporates conversation context and follow-up questions
- Integrates geointelligence analysis results when available
- Produces educational, contextual responses

**Uses Azure AI Foundry for:**
- Summarizing what data was found and displayed
- Explaining scientific concepts and phenomena
- Providing context about locations and events
- Answering follow-up questions with conversation memory

**Implementation:** `generate_contextual_earth_science_response()` method

**Output:** Natural language response with map visualization guidance

---

## 5. Agent Pipeline Summary

**Complete Query Processing Flow:**

```
User Query: "Show me HLS images of San Diego with low cloud cover from June 2025"
    ↓
Agent 1: Intent Classification
    → intent_type: "satellite"
    → needs_satellite_data: true
    ↓
Agent 2: Collection Mapping
    → collections: ["hls"]
    ↓
Agent 3: STAC Query Builder (ORCHESTRATOR)
    ├─ Agent 4: Location Extraction (GPT)
    │   → location_name: "San Diego"
    ├─ Location Resolution Utility (APIs)
    │   → bbox: [-117.3, 32.6, -116.9, 33.0]
    ├─ Agent 5: Datetime Translation (GPT)
    │   → datetime: "2025-06-01T00:00:00Z/2025-06-30T23:59:59Z"
    └─ Agent 6: Cloud Filtering (GPT)
        → filter: {"eo:cloud_cover": {"lt": 20}}
    ↓
STAC API Execution (Utility)
    → 28 tiles returned
    ↓
Agent 7: Tile Selector (Conditional)
    → 8 tiles selected for optimal coverage
    ↓
Hybrid Rendering System (Utility)
    → TiTiler URLs generated with true color RGB
    ↓
Agent 8: Response Generation (GPT)
    → "Showing HLS (Harmonized Landsat Sentinel-2) imagery for San Diego..."
    ↓
Frontend: Azure Maps displays tiles with legend
```

---

## 6. Geointelligence Modules

### **Overview**

The Geointelligence module provides advanced geospatial intelligence through pin-based analysis. Users drop a pin on the map to trigger specialized terrain analysis agents that query and analyze raw satellite raster data.

**Trigger:** User selects Geointelligence module → Drops pin on map → Backend analyzes 5-mile radius

---

### **Agent 9: Terrain Analysis (Azure AI Agent)**

**Type:** Azure AI Agent Service (`AgentsClient` with `AsyncFunctionTool` / `AsyncToolSet`)

**Purpose:** Comprehensive terrain analysis using raster data tools and optional satellite Vision

**Trigger:** User selects "Terrain Analysis" module + drops pin

**Process:**
1. Creates a persistent agent thread for multi-turn conversation
2. AI agent autonomously decides which terrain tools to call based on the user query
3. Tool results (raster-derived metrics) are returned to the agent for reasoning
4. Agent synthesizes findings into a coherent terrain assessment
5. Optional: Analyzes Sentinel-2 satellite screenshot via Vision for additional context

**Registered Function Tools (7):**
| Tool | Purpose | Data Source |
|------|---------|-------------|
| `get_elevation_analysis` | Elevation statistics within radius | Copernicus DEM 30m |
| `get_slope_analysis` | Slope distribution and steepness | Copernicus DEM 30m |
| `get_aspect_analysis` | Directional slope facing | Copernicus DEM 30m |
| `find_flat_areas` | Identify areas below slope threshold | Copernicus DEM 30m |
| `analyze_flood_risk` | Low-elevation flood-prone areas | Copernicus DEM 30m |
| `analyze_water_proximity` | Distance to water bodies, setback analysis | JRC Global Surface Water |
| `analyze_environmental_sensitivity` | Land cover and environmental constraints | ESA WorldCover 10m |

**Multi-Turn Chat:** Supports persistent conversation threads — users can ask follow-up questions about the same terrain (e.g., "What about flood risk?" after an initial elevation query).

**Data Sources:** Copernicus DEM 30m, JRC Global Surface Water, ESA WorldCover 10m, Sentinel-2 L2A (via Vision)

**Implementation:** `terrain_agent.py` → `TerrainAgent` class

**Output:**
```json
{
  "analysis": "The satellite image shows a dense urban area centered around Washington D.C. The Potomac River is clearly visible running through the center...",
  "features_identified": ["Water Bodies", "Urban Infrastructure", "Vegetation", "Landmarks"],
  "imagery_metadata": {
    "source": "Sentinel-2 L2A",
    "date": "2025-10-15T10:30:00Z",
    "cloud_cover": 5.2,
    "resolution": "10m RGB"
  },
  "confidence": 0.85
}
```

---

### **Agent 10: Mobility Analysis (Azure AI Agent + Raster Tools)**

**Type:** Azure AI Agent Service (`AgentsClient` with `AsyncFunctionTool` / `AsyncToolSet`)

**Purpose:** Assess terrain trafficability and mobility conditions

**Trigger:** User selects "Mobility Analysis" module + drops pin

**Process:**
1. Creates an agent session with registered raster analysis tools
2. AI agent calls mobility tools to query 5 STAC collections within 5-mile radius
3. Each tool downloads COG raster data for pixel-level analysis
4. Agent synthesizes results into directional mobility assessment (N, S, E, W)
5. Optional Vision enhancement for contextual satellite imagery analysis

**Registered Function Tools (5):**
| Tool | Purpose |
|------|---------|
| `analyze_directional_mobility` | Full N/S/E/W mobility assessment |
| `detect_water_bodies` | SAR-based water detection |
| `detect_active_fires` | MODIS thermal fire detection |
| `analyze_slope_for_mobility` | DEM-based slope trafficability |
| `analyze_vegetation_density` | NDVI vegetation obstacle detection |

**5-Layer Data Collection System:**

| Collection | Purpose | Resolution | Refresh | Analysis Method |
|------------|---------|------------|---------|-----------------|
| **sentinel-1-grd** | Water detection | 10m | 30-day window | SAR backscatter (VV < -20 dB = water) |
| **sentinel-1-rtc** | Terrain backscatter | 10m | 30-day window | Normalized radar reflectance |
| **sentinel-2-l2a** | Vegetation density | 10-60m | 30-day, <20% cloud | NDVI: (NIR - Red) / (NIR + Red) |
| **cop-dem-glo-30** | Elevation/slope | 30m | Static dataset | Slope analysis (GO: <15°, SLOW: 15-30°, NO-GO: >30°) |
| **modis-14A1-061** | Active fires | 1km | Daily composite | FireMask value 7-9 detection |

**Technical Details:**

All 5 collections queried **concurrently** using `asyncio.gather()` for optimal performance.

**Mobility Thresholds:**
- **Slope**: <15° = GO, 15-30° = SLOW-GO, >30° = NO-GO
- **Water Detection**: SAR backscatter < -20 dB = water presence
- **Vegetation**: NDVI > 0.6 = dense vegetation (obstacle)
- **Fire Hazard**: FireMask ≥ 7 = active fire (NO-GO)

**Mobility Classification:**
- **GO**: <15° slope, no water, no fires, low vegetation
- **SLOW-GO**: 15-30° slope, scattered obstacles
- **NO-GO**: >30° slope, water bodies, active fires, dense vegetation

**Directional Analysis:** Assesses mobility in 4 cardinal directions (N, S, E, W) within 5-mile radius

**Implementation:** `mobility_agent.py` → `GeointMobilityAgent` class

**Output:**
```json
{
  "mobility_assessment": {
    "north": {"status": "GO", "confidence": 0.85, "obstacles": []},
    "south": {"status": "SLOW-GO", "confidence": 0.72, "obstacles": ["Dense vegetation"]},
    "east": {"status": "NO-GO", "confidence": 0.91, "obstacles": ["Water bodies", "Steep terrain"]},
    "west": {"status": "GO", "confidence": 0.88, "obstacles": []}
  },
  "terrain_metrics": {
    "water_coverage_pct": 12.3,
    "vegetation_ndvi_avg": 0.45,
    "slope_avg_degrees": 8.2,
    "fire_detections": 0,
    "elevation_range_meters": [120, 380]
  },
  "data_sources": ["sentinel-1-grd", "sentinel-1-rtc", "sentinel-2-l2a", "cop-dem-glo-30", "modis-14A1-061"],
  "vision_analysis": "The terrain reveals excellent mobility corridors to the north and west..."
}
```

---

### **Agent 11: Building Damage Assessment (Azure AI Agent)**

**Type:** Azure AI Agent Service (`AgentsClient` with `AsyncFunctionTool` / `AsyncToolSet`)

**Purpose:** Detect and classify building damage from disasters

**Trigger:** User selects "Building Damage" module + drops pin

**Process:**
1. Creates an agent session with damage assessment tools
2. AI agent fetches satellite imagery and calls registered tools for analysis
3. Tools classify damage levels: No damage, Minor, Major, Destroyed
4. Agent generates damage assessment report

**Registered Function Tools (2):**
| Tool | Purpose |
|------|---------|
| `assess_building_damage` | Full damage assessment pipeline (imagery fetch + analysis) |
| `classify_damage_severity` | Severity classification of detected damage |

**Damage Levels:**
- **No Damage**: Structures intact
- **Minor Damage**: <30% structural damage
- **Major Damage**: 30-70% structural damage
- **Destroyed**: >70% structural damage

**Data Source:** Satellite imagery via STAC collections

**Implementation:** `building_damage_agent.py` → `BuildingDamageAgent` class

---

### **Agent 12: Comparison Analysis (Azure AI Agent)**

**Type:** Azure AI Agent Service (`AgentsClient` with `AsyncFunctionTool` / `AsyncToolSet`)

**Purpose:** Detect changes between two time periods

**Trigger:** Text query with temporal comparison (e.g., "Compare Seattle 2023 vs 2024") or pin-drop comparison

**Process:**
1. AI agent parses comparison query (before/after dates, location)
2. Calls registered tools to query STAC API for imagery at both time periods
3. Generates side-by-side tile URLs for visualization
4. Calls Vision analysis tool to describe observed changes

**Registered Function Tools (3):**
| Tool | Purpose |
|------|---------|
| `compare_temporal_imagery` | Full comparison pipeline (search + tile generation for both periods) |
| `search_stac_for_period` | Search STAC catalog for a specific collection, location, and time |
| `analyze_comparison_imagery` | GPT-4o Vision analysis of before/after tile imagery |

**Implementation:** `comparison_agent.py` → `ComparisonAgent` class

---

### **Agent 13: Extreme Weather Analysis (Azure AI Agent)**

**Type:** Azure AI Agent Service (`AgentsClient` with `AsyncFunctionTool` / `AsyncToolSet`)

**Purpose:** Climate projections and extreme weather trend analysis using CMIP6 NetCDF data

**Trigger:** User selects "Extreme Weather" module or asks about climate projections

**Process:**
1. Creates an agent session with climate projection tools
2. AI agent decides which climate variables to query based on user question
3. Tools sample CMIP6 NetCDF data (not COG raster) at specified coordinates
4. Agent synthesizes multi-variable projections into a coherent climate assessment
5. Supports multi-turn conversation for follow-up climate questions

**Registered Function Tools (7):**
| Tool | Purpose | Data Variable |
|------|---------|---------------|
| `get_temperature_projection` | Temperature trends (min/max/mean) | `tasmax`, `tasmin`, `tas` |
| `get_precipitation_projection` | Rainfall and precipitation patterns | `pr` |
| `get_wind_projection` | Wind speed projections | `sfcWind` |
| `get_humidity_projection` | Near-surface humidity | `huss` |
| `get_radiation_projection` | Shortwave radiation flux | `rsds` |
| `get_climate_overview` | Combined overview of all variables | All |
| `compare_climate_scenarios` | SSP2-4.5 vs SSP5-8.5 scenario comparison | Configurable |

**Data Source:** NASA NEX-GDDP-CMIP6 (NetCDF climate model projections, **not COG raster**)

**Implementation:** `extreme_weather_agent.py` → `ExtremeWeatherAgent` class

**Status:** Active

---

### **Agent 14: Animation Generation (Time Series)**

**Type:** Utility Agent (stub)

**Purpose:** Create animated GIFs from time-series satellite data

**Trigger:** Text query requesting animation (e.g., "Animate wildfire spread")

**Planned Process:**
1. Query STAC API for time-ordered imagery
2. Fetch tiles for each time step
3. Generate animated GIF
4. Return visualization URL

**Implementation:** `animation_generation_agent()` function in `agents.py`

**Status:** ⏳ Placeholder — returns stub message. Full implementation planned.

---

### **Router Agent (Semantic Kernel)**

**Type:** Semantic Kernel `ChatCompletionAgent` with `KernelPlugin` (different architecture from GEOINT agents)

**Purpose:** Orchestrates multi-step user interactions by selecting the right tool at each turn

**Trigger:** Activated via the Router Function App or direct API invocation

**Process:**
1. Receives user message + session context (location, active layers, conversation history)
2. SK agent autonomously selects which kernel function to call
3. Kernel function executes (e.g., STAC search, Vision analysis, navigation)
4. Agent returns structured response with actions for the frontend

**Registered Kernel Functions (6):**
| Function | Purpose |
|----------|---------|
| `get_session_context` | Retrieve current session state (location, layers, map center) |
| `navigate_to_location` | Fly-to a location on the map |
| `search_and_render_stac` | Execute a full STAC search and return rendered tiles |
| `answer_with_vision` | Analyze current map screenshot with GPT-4o Vision |
| `answer_contextual_question` | Answer general knowledge / Earth science questions |
| `search_and_analyze` | Combined search + vision analysis pipeline |

**Implementation:** `router_agent.py` → `RouterAgent` class, `RouterAgentTools` plugin class

---

### **Enhanced Vision Agent (Azure AI Agent)**

**Type:** Azure AI Agent Service (`AgentsClient` with `AsyncFunctionTool` / `AsyncToolSet`)

**Purpose:** Deep analysis of satellite imagery using specialized vision tools + raster sampling

**Trigger:** User asks about what's visible on the map, or selects "Vision Analysis" module

**Process:**
1. Creates an agent session with 13 registered vision tools
2. User provides map screenshot + optional coordinates
3. AI agent decides which vision/raster tools to call based on the query
4. Tools analyze imagery, sample raster values, query knowledge base
5. Agent synthesizes findings into a comprehensive analysis
6. Supports multi-turn conversation via persistent threads

**Registered Function Tools (13):**
| Tool | Purpose |
|------|---------|
| `analyze_screenshot` | General satellite screenshot analysis |
| `analyze_raster` | Generic raster data interpretation |
| `analyze_vegetation` | NDVI-based vegetation health analysis |
| `analyze_fire` | Thermal anomaly and fire detection |
| `analyze_land_cover` | Land use / land cover classification |
| `analyze_snow` | Snow and ice extent detection |
| `analyze_sar` | Synthetic Aperture Radar interpretation |
| `analyze_water` | Water body and flood detection |
| `analyze_biomass` | Above-ground biomass estimation |
| `sample_raster_value` | Extract pixel values at coordinates |
| `query_knowledge` | Query Azure AI Search knowledge base |
| `identify_features` | Identify geographic features in imagery |
| `compare_temporal` | Before/after temporal image comparison |

**Implementation:** `agents/enhanced_vision_agent.py` → `EnhancedVisionAgent` class, `agents/vision_tools.py`

---

### **Chat Vision Analyzer**

**Type:** GPT-4o Vision (direct API call)

**Purpose:** Lightweight conversational map analysis — answers follow-up questions about what's on screen

**Trigger:** User asks about current map view in conversational context

**Implementation:** `geoint/chat_vision_analyzer.py` → `ChatVisionAnalyzer` class

---

### **Vision Analyzer (Shared Utility)**

**Type:** GPT-4o Vision (direct API call)

**Purpose:** Shared Vision analysis utility used by Terrain, Mobility, Building Damage, and Comparison agents

**Implementation:** `geoint/vision_analyzer.py` → `VisionAnalyzer` class

---

### **GEOINT Orchestrator**

**Type:** Coordination function (not an agent itself)

**Purpose:** Run multiple GEOINT modules in parallel on the same location

**Trigger:** `POST /api/geoint/orchestrate` or multi-module pin drop

**Process:**
1. Receives list of requested modules (e.g., `["terrain", "mobility", "building_damage"]`)
2. Runs each agent concurrently using `asyncio.gather()`
3. Combines results into a unified response

**Implementation:** `geoint/agents.py` → `geoint_orchestrator()` function

---

## 8. Complete System Summary

### Agent Inventory (19 Components)

| # | Agent | Type | Framework | Tools |
|---|-------|------|-----------|-------|
| 1 | Intent Classification | Text Query | GPT (Azure OpenAI) | — |
| 2 | Collection Mapping | Text Query | GPT (Azure OpenAI) | — |
| 3 | STAC Query Builder | Text Query | GPT (Azure OpenAI) | — |
| 4 | Location Extraction | Text Query | GPT + Azure Maps | — |
| 5 | Datetime Translation | Text Query | GPT (Azure OpenAI) | — |
| 6 | Cloud Filtering | Text Query | GPT (Azure OpenAI) | — |
| 7 | Tile Selector | Text Query | Algorithmic (no GPT) | — |
| — | Hybrid Rendering System | Utility | Algorithmic | — |
| 8 | Response Generation | Text Query | GPT (Azure OpenAI) | — |
| 9 | Terrain Analysis | GEOINT | Azure AI Agent Service | 7 function tools |
| 10 | Mobility Analysis | GEOINT | Azure AI Agent Service | 5 function tools |
| 11 | Building Damage | GEOINT | Azure AI Agent Service | 2 function tools |
| 12 | Comparison Analysis | GEOINT | Azure AI Agent Service | 3 function tools |
| 13 | Extreme Weather | GEOINT | Azure AI Agent Service | 7 function tools |
| 14 | Animation Generation | GEOINT | Stub (planned) | — |
| — | Router Agent | Orchestrator | Semantic Kernel | 6 kernel functions |
| — | Enhanced Vision Agent | GEOINT | Azure AI Agent Service | 13 function tools |
| — | Chat Vision Analyzer | Vision | GPT-4o Vision (direct) | — |
| — | Vision Analyzer | Shared Utility | GPT-4o Vision (direct) | — |
| — | GEOINT Orchestrator | Coordination | asyncio.gather | — |

### Technology Stack

| Layer | Technology |
|-------|-----------|
| **Text Query Agents (1-8)** | Azure OpenAI GPT via Semantic Kernel |
| **GEOINT Agents (9-13)** | Azure AI Agent Service (`AgentsClient` + function tools) |
| **Router Agent** | Semantic Kernel `ChatCompletionAgent` + `KernelPlugin` |
| **Enhanced Vision** | Azure AI Agent Service + 13 vision/raster tools |
| **Vision Utilities** | GPT-4o Vision (direct HTTP API) |
| **Raster Processing** | COG via TiTiler / rasterio (except Extreme Weather: NetCDF) |
| **Location Resolution** | Azure Maps Geocoding API |
| **Data Catalog** | Microsoft Planetary Computer STAC API + NASA VEDA STAC |
| **Tile Rendering** | TiTiler (self-hosted) |
| **Knowledge Base** | Azure AI Search |

### **Core Endpoints (Text Query Processing)**

**`POST /api/query`**
- **Purpose:** Main query translation and STAC search
- **Process:** Routes through Agent 1–8 pipeline
- **Input:** `{"query": "Show me wildfire activity in California", "conversationHistory": [...]}`
- **Output:** STAC search results + TiTiler URLs + natural language response
- **Use When:** User enters text query in chat

**`GET /api/health`**
- **Purpose:** Health check with connectivity tests
- **Tests:** STAC API, TiTiler, Azure OpenAI, database
- **Output:** `{"status": "healthy", "services": {...}}`
- **Use When:** Monitoring system availability

**`POST /api/stac-search`**
- **Purpose:** Direct STAC API passthrough
- **Input:** Raw STAC query JSON
- **Output:** STAC search results
- **Use When:** Advanced users need direct STAC access (bypasses agents)

**`POST /api/session-reset`**
- **Purpose:** Clear conversation context and memory
- **Output:** `{"status": "session_reset"}`
- **Use When:** Starting fresh conversation

---

### **Geointelligence Endpoints (Pin-Drop Analysis)**

**`POST /api/geoint/terrain`**
- **Purpose:** One-shot terrain analysis (7 function tools + Vision)
- **Input:** `{"latitude": 38.9, "longitude": -77.0, "screenshot_base64": "...", "user_query": "Analyze terrain", "radius_miles": 5.0}`
- **Output:** Terrain analysis with tool results and features identified
- **Triggers:** Agent 9 (Terrain Analysis)
- **Use When:** User selects "Terrain Analysis" + drops pin

**`POST /api/geoint/terrain/chat`**
- **Purpose:** Multi-turn terrain conversation (persistent thread)
- **Input:** `{"session_id": "...", "latitude": 38.9, "longitude": -77.0, "message": "What about flood risk?"}`
- **Output:** Agent response with tool calls and reasoning
- **Triggers:** Agent 9 (Terrain Analysis) in chat mode
- **Use When:** Follow-up terrain questions in same session

**`GET /api/geoint/terrain/chat/{session_id}/history`**
- **Purpose:** Retrieve terrain chat conversation history

**`DELETE /api/geoint/terrain/chat/{session_id}`**
- **Purpose:** Clear a terrain chat session

**`POST /api/geoint/mobility`**
- **Purpose:** Mobility assessment (5 function tools + 5-layer raster analysis)
- **Input:** `{"latitude": 38.9, "longitude": -77.0, "screenshot_base64": "...", "user_query": "Assess mobility", "include_vision": true}`
- **Output:** Directional mobility status (GO/SLOW-GO/NO-GO)
- **Triggers:** Agent 10 (Mobility Analysis)
- **Use When:** User selects "Mobility Analysis" + drops pin

**`POST /api/geoint/building-damage`**
- **Purpose:** Building damage detection (Azure AI Agent + Vision)
- **Input:** `{"latitude": 38.9, "longitude": -77.0, "screenshot_base64": "...", "user_query": "Assess building damage"}`
- **Output:** Damage classification (No damage/Minor/Major/Destroyed)
- **Triggers:** Agent 11 (Building Damage Assessment)
- **Use When:** User selects "Building Damage" + drops pin

**`POST /api/geoint/comparison`**
- **Purpose:** Temporal change detection (3 function tools)
- **Input:** `{"location": "Seattle", "before_date": "2023-06-01", "after_date": "2024-06-01"}`
- **Output:** Side-by-side tile URLs with AI change analysis
- **Triggers:** Agent 12 (Comparison Analysis)
- **Use When:** User asks for before/after comparison

**`POST /api/geoint/extreme-weather`**
- **Purpose:** Climate projection analysis (7 function tools)
- **Input:** `{"latitude": 38.9, "longitude": -77.0, "message": "What are temperature projections?", "session_id": "..."}`
- **Output:** Climate projection data and analysis
- **Triggers:** Agent 13 (Extreme Weather Analysis)
- **Use When:** User selects "Extreme Weather" module or asks climate questions

**`POST /api/geoint/vision`**
- **Purpose:** One-shot enhanced vision analysis of map imagery (13 function tools)
- **Input:** `{"screenshot_base64": "...", "user_query": "What do you see?", "latitude": 38.9, "longitude": -77.0}`
- **Output:** AI analysis of visible satellite imagery with tool-derived data
- **Triggers:** Enhanced Vision Agent
- **Use When:** User asks about what's visible on the current map

**`POST /api/geoint/vision/chat`**
- **Purpose:** Multi-turn vision conversation (persistent thread)
- **Input:** `{"session_id": "...", "message": "Tell me more about the vegetation", "screenshot_base64": "..."}`
- **Output:** Agent response with tool calls and reasoning
- **Use When:** Follow-up vision questions about the same map view

**`DELETE /api/geoint/vision/chat/{session_id}`**
- **Purpose:** Clear a vision chat session

**`POST /api/geoint/animation`**
- **Purpose:** Time-series animation generation (placeholder)
- **Input:** `{"location": "California", "start_date": "2024-08-01", "end_date": "2024-08-30", "collection": "modis-14A1-061"}`
- **Output:** Stub response (not yet implemented)
- **Triggers:** Agent 14 (Animation Generation)

**`POST /api/geoint/orchestrate`**
- **Purpose:** Run multiple GEOINT agents in parallel
- **Input:** `{"latitude": 38.9, "longitude": -77.0, "modules": ["terrain", "mobility"], ...}`
- **Output:** Combined results from all requested modules
- **Use When:** Running multiple analyses on the same location simultaneously

---

### **Processing Endpoints**

**`POST /api/process-comparison-query`**
- **Purpose:** Process comparison query text
- **Input:** `{"query": "Compare Seattle before and after 2023 wildfire"}`
- **Output:** Parsed comparison parameters + imagery
- **Use When:** Backend needs to parse temporal comparison queries

**`POST /api/veda-search`**
- **Purpose:** Search NASA VEDA STAC catalog
- **Input:** STAC query JSON for VEDA collections
- **Output:** VEDA STAC search results
- **Use When:** Querying NASA climate/Earth science datasets

**`POST /api/structured-search`**
- **Purpose:** Structured STAC search with explicit parameters
- **Input:** Pre-parsed search parameters (collections, bbox, datetime, etc.)
- **Output:** STAC search results
- **Use When:** Programmatic search with known parameters (bypasses NLP agents)

---

### **Utility Endpoints**

**`GET /api/config`**
- **Purpose:** Get frontend configuration (API keys, feature flags)
- **Output:** `{"azureMapsKey": "...", "features": {...}}`
- **Use When:** Frontend initialization

**`POST /api/sign-mosaic-url`**
- **Purpose:** Generate signed URLs for mosaic tiles
- **Input:** `{"mosaicId": "...", "tileUrl": "..."}`
- **Output:** Signed TiTiler URL with authentication
- **Use When:** Securing tile access

**`GET /api/colormaps`**
- **Purpose:** List all available color maps
- **Output:** Array of colormap names (YlOrRd, Blues, RdYlGn, etc.)
- **Use When:** Building color scale selector UI

**`GET /api/colormaps/{colormap_name}`**
- **Purpose:** Get specific colormap definition
- **Output:** Colormap RGB values and stops
- **Use When:** Rendering custom color scales

**`GET /api/colormaps/collection/{collection_id}`**
- **Purpose:** Get recommended colormap for collection
- **Input:** Collection ID (e.g., "modis-14A1-061")
- **Output:** Recommended colormap name ("YlOrRd" for fire)
- **Use When:** Auto-selecting color scales for satellite data

**`GET /api/geoint/cmip6-test`**
- **Purpose:** Quick test of CMIP6 NetCDF data sampling
- **Input:** Query params: `lat`, `lng`, `variable`, `aggregate`
- **Output:** Raw climate data sample
- **Use When:** Testing/debugging Extreme Weather data pipeline

**`GET /api/debug/location/{location}`**
- **Purpose:** Debug location resolution
- **Input:** Location name (e.g., "Seattle")
- **Output:** Geocoding results with bounding boxes
- **Use When:** Troubleshooting location extraction issues
