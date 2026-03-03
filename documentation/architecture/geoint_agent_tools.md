# GEOINT Modules Quick Reference

Earth Copilot provides four GEOINT modules. Each table shows **use cases → example queries → tools → collections**.

---

##  Vision Module

General-purpose satellite imagery analysis using GPT-4o Vision and raster sampling.

| Use Case | Example Query | Tool | What It Does | Collections |
|----------|---------------|------|--------------|-------------|
| Visual interpretation | "What do I see on the map?" | `analyze_screenshot` | GPT-4o analyzes map screenshot | Any visible layer |
| Point value extraction | "What's the NDVI at the pin?" | `sample_raster_value` | Extracts single pixel value | HLS, MODIS, Sentinel-2 |
| Area statistics | "What's the elevation range?" | `analyze_raster` | Computes min/max/mean over area | Copernicus DEM |
| Fire detection | "Is there active fire here?" | `analyze_fire` | Detects thermal anomalies | MODIS 14A1, MTBS |
| Water analysis | "Show water occurrence" | `analyze_water` | Historical water frequency | JRC-GSW |
| Snow cover | "How much snow coverage?" | `analyze_snow` | Snow cover percentage | MODIS 10A1 |
| Vegetation health | "Analyze vegetation here" | `analyze_vegetation` | NDVI/LAI/NPP analysis | MODIS 13Q1, 15A2H |
| Biomass estimation | "What's the biomass?" | `analyze_biomass` | Above-ground biomass (Mg/ha) | CHLORIS |
| Land cover | "What type of land is this?" | `analyze_land_cover` | Classification (urban, forest, etc.) | ESA WorldCover, USDA-CDL |
| SAR analysis | "Detect flooding with SAR" | `analyze_sar` | Backscatter analysis, flood detection | Sentinel-1 RTC |
| Feature identification | "What city is this?" | `identify_features` | Names geographic features | GPT-4o Vision |
| Educational | "What is NDVI?" | `query_knowledge` | Answers science questions | Knowledge base |

---

##  Terrain Module

Site permitting and environmental suitability analysis.

| Use Case | Example Query | Tool | What It Does | Collections |
|----------|---------------|------|--------------|-------------|
| Elevation analysis | "What's the elevation here?" | `get_elevation_analysis` | Min/max/mean elevation, terrain type | Copernicus DEM GLO-30 |
| Slope assessment | "Is this too steep for construction?" | `get_slope_analysis` | Slope steepness in degrees | Copernicus DEM GLO-30 |
| Sun exposure | "Which direction does this slope face?" | `get_aspect_analysis` | Slope direction (N/S/E/W) | Copernicus DEM GLO-30 |
| Flat area search | "Where can I site a facility?" | `find_flat_areas` | Locates areas below slope threshold | Copernicus DEM GLO-30 |
| Flood risk | "Is this in a flood zone?" | `analyze_flood_risk` | Historical water occurrence % | JRC Global Surface Water |
| Water setback | "How far to nearest water?" | `analyze_water_proximity` | Distance to water bodies | JRC-GSW |
| Environmental check | "Any wetlands or protected areas?" | `analyze_environmental_sensitivity` | Wetlands, forests, protected land | ESA WorldCover |

---

##  Mobility Module

Military operations, search & rescue, and emergency response route assessment.

| Use Case | Example Query | Tool | What It Does | Collections |
|----------|---------------|------|--------------|-------------|
| Full mobility assessment | "Can vehicles traverse this area?" | `analyze_mobility` | Combined GO/SLOW-GO/NO-GO analysis | All 5 below |
| Water obstacles | "Are there rivers to cross?" | `analyze_mobility` (water) | Detects water from SAR backscatter | Sentinel-1 GRD/RTC |
| Slope limits | "Is slope passable for vehicles?" | `analyze_mobility` (slope) | Slope steepness vs vehicle limits | Copernicus DEM GLO-30 |
| Vegetation density | "Is the forest too dense?" | `analyze_mobility` (vegetation) | NDVI-based obstruction detection | Sentinel-2 L2A |
| Fire hazards | "Any active fires blocking route?" | `analyze_mobility` (fire) | Thermal anomaly detection | MODIS 14A1 |
| Directional analysis | "Best exit route from here?" | `analyze_mobility` (directional) | N/S/E/W corridor GO/NO-GO | All combined |
| Helicopter LZ | "Where can a helicopter land?" | `analyze_mobility` | Finds flat, clear areas (<5° slope) | Copernicus DEM |

---

##  Comparison Module

Before/after change detection and anomaly analysis.

### Query Format Required
Queries **must** specify: **Location** + **Collection** + **Date Range**

The module executes **2 STAC queries** (before/after) for the location and analyzes changes.

| Use Case | Example Query | Tool | What It Does | Collections |
|----------|---------------|------|--------------|-------------|
| Urban expansion | "Compare Miami surface reflectance between 01/2020 and 01/2025" | `execute_comparison` | Dual STAC queries → change metrics | Sentinel-2, HLS |
| Deforestation | "How did Amazon NDVI change from 2019 to 2024?" | `execute_comparison` | Vegetation index difference | Sentinel-2 L2A |
| Fire damage | "Before/after the 2023 California wildfire" | `execute_comparison` | Burn severity change (dNBR) | Sentinel-2, MTBS |
| Coastal erosion | "LA coastline change 2018 to 2025" | `execute_comparison` | Land/water boundary shift | Sentinel-2, HLS |
| Flood impact | "Pre and post Hurricane Ian flooding" | `execute_comparison` | Water extent difference | Sentinel-1 SAR |
| Glacier retreat | "Alaska glacier change 2015 vs 2025" | `execute_comparison` | Ice/snow extent reduction | MODIS Snow, Landsat |
| Anomaly detection | "Detect anomalies in Lake Mead 2020-2025" | `execute_comparison` | Statistical outlier detection | Landsat, Sentinel-2 |

### Comparison Output
| Output | Description |
|--------|-------------|
| Before tile | Map layer for time period 1 |
| After tile | Map layer for time period 2 |
| Δ Value | Absolute change (e.g., -0.15 NDVI) |
| Δ Percent | Percentage change (e.g., -23%) |
| Classification | Increase/Decrease/Stable |

---

## Collections Reference

| Category | Collection | Resolution | Modules Using |
|----------|------------|------------|---------------|
| Optical | Sentinel-2 L2A | 10m | Vision, Comparison |
| Optical | HLS-L30/S30 | 30m | Vision, Comparison |
| Optical | Landsat C2 L2 | 30m | Vision, Comparison |
| Elevation | Copernicus DEM GLO-30 | 30m | Vision, Terrain, Mobility |
| Vegetation | MODIS 13A1/13Q1 | 250-500m | Vision |
| Fire | MODIS 14A1 | 1km | Vision, Mobility |
| Fire | MTBS | 30m | Vision, Comparison |
| Water | JRC Global Surface Water | 30m | Vision, Terrain |
| Snow | MODIS 10A1 | 500m | Vision, Comparison |
| Land Cover | ESA WorldCover | 10m | Vision, Terrain |
| SAR | Sentinel-1 GRD/RTC | 10m | Vision, Mobility, Comparison |
| Biomass | CHLORIS | 100m | Vision |
