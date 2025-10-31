# Earth Copilot 2.0 - Architecture & Agent System

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
   - Agent 9: Terrain Analysis (GPT-5 Vision)
   - Agent 10: Mobility Analysis (5-Layer Raster + Vision)
   - Agent 11: Building Damage Assessment
   - Agent 12: Comparison Analysis
   - Agent 13: Animation Generation
7. [API Endpoints](#7-api-endpoints)
   - Core Endpoints (4)
   - Geointelligence Endpoints (6)
   - Processing Endpoints (2)
   - Utility Endpoints (7)
8. [Extensibility & Future Modules](#8-extensibility--future-modules)
9. [Complete System Summary](#9-complete-system-summary)
   - Agent Inventory (13 Total)
   - 5-Layer Data Collection Architecture
   - API Surface (19 Endpoints)
   - Technology Stack

---

## Overview

Earth Copilot 2.0 is a natural language geospatial intelligence platform powered by Azure OpenAI (GPT-4o/GPT-5) and Semantic Kernel. It enables users to query satellite imagery and geospatial data using conversational language, with automated data discovery, intelligent tile selection, and dynamic map visualization.

**Key Capabilities:**
- **13 AI Agents** (8 text query agents + 5 geointelligence pin-drop agents)
- **113+ Satellite Collections** from Microsoft Planetary Computer & NASA VEDA
- **5-Layer Raster Analysis** for mobility/terrain assessment
- **GPT-5 Vision Integration** for multimodal satellite imagery analysis

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

**📖 For comprehensive collection details, see:** [STAC Collections Reference](../data_collections/STAC_COLLECTIONS.md)

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
- `satellite` - Map visualization (STAC query required)
- `contextual` - Information/educational questions
- `hybrid` - Map + contextual explanation
- `vision` - Analyze currently displayed imagery

**Output Example:**
```json
{
  "intent_type": "satellite",
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
- **Type:** AI Agent (uses GPT-4o/GPT-5)
- **Input:** Natural language query
- **Process:** Extracts location entities from query text
- **Handles:** Cities ("Seattle"), regions ("Pacific Northwest"), landmarks ("Grand Canyon"), coordinates
- **Output:** `{"location": {"name": "Seattle", "type": "city", "confidence": 0.9}}`

---

### **Location Resolution Utility (Multi-Tier Geocoding)**
- **Type:** Utility function
- **Input:** Location name from Agent 4
- **Cascade Strategy:**
  1. **Azure Maps API** (primary geocoding service)
  2. **Mapbox API** (geographic specialist)
  3. **Google Maps API** (comprehensive coverage)
  4. **Nominatim** (OpenStreetMap, free fallback)
- **Output:** Bounding box `[west, south, east, north]` coordinates

---

### **Agent 5: Datetime Translation Agent (GPT-Powered)**
- **Type:** AI Agent (uses GPT-4o/GPT-5)
- **Input:** Natural language temporal expressions
- **Process:** Converts phrases to ISO 8601 datetime ranges
- **Handles:** "last month", "Q3 2024", "October 15, 2023", "recent", comparison mode (before/after)
- **Output:** `"2024-09-01T00:00:00Z/2024-09-30T23:59:59Z"`

---

### **Agent 6: Cloud Filtering Agent (GPT-Powered)**
- **Type:** AI Agent (uses GPT-4o/GPT-5)
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

**Type:** AI Agent (uses GPT-4o/GPT-5)

**Purpose:** Generate natural language explanations of query results

**Process:**
- Analyzes STAC search results and tile selections
- Incorporates conversation context and follow-up questions
- Integrates geointelligence analysis results when available
- Produces educational, contextual responses

**Uses GPT-4o/GPT-5 for:**
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

### **Agent 9: Terrain Analysis (GPT-5 Vision)**

**Type:** GPT-Powered Agent (uses GPT-5 Vision multimodal)

**Purpose:** Visual analysis of terrain features using satellite imagery

**Trigger:** User selects "Terrain Analysis" module + drops pin

**Process:**
1. Fetches Sentinel-2 L2A RGB imagery (512x512px, 5-mile radius around pin)
2. Sends satellite image to GPT-5 Vision API
3. Analyzes visual features using custom terrain analysis prompt

**Analyzes:**
- Bodies of water (rivers, lakes, ponds, coastal areas)
- Vegetation types and density
- Roads and infrastructure
- Urban vs rural characteristics
- Terrain features (hills, valleys, plains)
- Land use patterns

**Data Source:** Sentinel-2 L2A (10m RGB optical imagery)

**Implementation:** `terrain_analysis_agent.py` → `TerrainAnalysisAgent` class

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

### **Agent 10: Mobility Analysis (Hybrid: Raster + Vision)**

**Type:** Hybrid Agent (algorithmic raster analysis + optional GPT-5 Vision)

**Purpose:** Assess terrain trafficability and mobility conditions

**Trigger:** User selects "Mobility Analysis" module + drops pin

**Process:**
1. Queries 5 STAC collections within 5-mile radius
2. Downloads raster data for pixel-level analysis
3. Computes terrain metrics algorithmically
4. Performs directional mobility assessment (N, S, E, W)
5. Optionally enhances with GPT-5 Vision for contextual insights

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

### **Agent 11: Building Damage Assessment (CNN-Based)**

**Type:** Deep Learning Agent (Siamese U-Net CNN + GPT-5 Vision)

**Purpose:** Detect and classify building damage from disasters

**Trigger:** User selects "Building Damage" module + drops pin

**Process:**
1. Fetches pre/post-disaster Sentinel-2 imagery
2. Runs Siamese U-Net CNN model for pixel-level damage detection
3. Classifies damage levels: No damage, Minor, Major, Destroyed
4. Generates damage assessment report

**Model:** Siamese U-Net CNN (trained on xBD disaster dataset)

**Damage Levels:**
- **No Damage**: Structures intact
- **Minor Damage**: <30% structural damage
- **Major Damage**: 30-70% structural damage
- **Destroyed**: >70% structural damage

**Data Source:** Sentinel-2 L2A (10m RGB + NIR)

**Implementation:** `building_damage_agent.py` → `BuildingDamageAgent` class

---

### **Agent 12: Comparison Analysis (Temporal Change Detection)**

**Type:** GPT-Powered Agent

**Purpose:** Detect changes between two time periods

**Trigger:** Text query with temporal comparison (e.g., "Compare Seattle 2023 vs 2024")

**Process:**
1. Parses comparison query (before/after dates, location)
2. Queries STAC API for imagery at both time periods
3. Generates side-by-side visualization
4. Analyzes changes using GPT-5

**Implementation:** `comparison_analysis_agent()` function

---

### **Agent 13: Animation Generation (Time Series)**

**Type:** Utility Agent

**Purpose:** Create animated GIFs from time-series satellite data

**Trigger:** Text query requesting animation (e.g., "Animate wildfire spread")

**Process:**
1. Queries STAC API for time-ordered imagery
2. Fetches tiles for each time step
3. Generates animated GIF
4. Returns visualization URL

**Implementation:** `animation_generation_agent()` function

**Status:** ✅ Fully implemented

---

## 7. API Endpoints

### **Core Endpoints (Text Query Processing)**

**`POST /api/query`**
- **Purpose:** Main query translation and STAC search
- **Process:** Routes through Agent 1-5 pipeline
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
- **Purpose:** Terrain feature analysis using GPT-5 Vision
- **Input:** `{"latitude": 38.9, "longitude": -77.0, "screenshot_base64": "...", "user_query": "Analyze terrain", "radius_miles": 5.0}`
- **Output:** Terrain analysis with features identified
- **Triggers:** Agent 6 (Terrain Analysis)
- **Use When:** User selects "Terrain Analysis" + drops pin

**`POST /api/geoint/mobility`**
- **Purpose:** Mobility assessment (5-layer raster analysis)
- **Input:** `{"latitude": 38.9, "longitude": -77.0, "screenshot_base64": "...", "user_query": "Assess mobility", "include_vision": true}`
- **Output:** Directional mobility status (GO/SLOW-GO/NO-GO)
- **Triggers:** Agent 7 (Mobility Analysis)
- **Use When:** User selects "Mobility Analysis" + drops pin

**`POST /api/geoint/building-damage`**
- **Purpose:** Building damage detection (CNN + Vision)
- **Input:** `{"latitude": 38.9, "longitude": -77.0, "screenshot_base64": "...", "user_query": "Assess building damage"}`
- **Output:** Damage classification (No damage/Minor/Major/Destroyed)
- **Triggers:** Agent 8 (Building Damage Assessment)
- **Use When:** User selects "Building Damage" + drops pin

**`POST /api/geoint/comparison`**
- **Purpose:** Temporal change detection
- **Input:** `{"location": "Seattle", "before_date": "2023-06-01", "after_date": "2024-06-01"}`
- **Output:** Side-by-side imagery with change analysis
- **Triggers:** Agent 9 (Comparison Analysis)
- **Use When:** User asks for before/after comparison

**`POST /api/geoint/animation`**
- **Purpose:** Time-series animation generation
- **Input:** `{"location": "California", "start_date": "2024-08-01", "end_date": "2024-08-30", "collection": "modis-14A1-061"}`
- **Output:** Animated GIF URL
- **Triggers:** Agent 10 (Animation Generation)
- **Use When:** User requests animation of temporal changes

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

**`GET /api/debug/location/{location}`**
- **Purpose:** Debug location resolution
- **Input:** Location name (e.g., "Seattle")
- **Output:** Geocoding results with bounding boxes
- **Use When:** Troubleshooting location extraction issues
