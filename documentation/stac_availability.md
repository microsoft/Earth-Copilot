# STAC Collection Availability Reference

*Last Updated: September 12, 2025*
*Data Source: Microsoft Planetary Computer STAC API v1*
*Total Collections Available: 126*
*Working Collections: 113 (89.7% success rate)*

This document provides current availability status for Earth observation data collections accessible through the Microsoft Planetary Computer STAC API, based on comprehensive testing with multiple time ranges (2015-2024) and geographic areas (global, regional, local).

## 🔍 **Collection Validation Methodology**

**Deep Testing Strategy:** All 126 collections tested with 10 different strategies including:
- Multiple time ranges: 2024, 2023, 2022, 2020-2021, 2015-2019
- Geographic extents: Global, Continental US, California, Europe, Small areas
- Minimal data queries to find any available data

**Success Criteria:** Collections marked as "working" have data available through at least one strategy combination.

---

## � **Optical Satellite Imagery** (5/5 collections working - 100%)

### **Sentinel-2 L2A - Surface Reflectance**
- **Collection ID:** `sentinel-2-l2a` 
- **Status:** ✅ **EXCELLENT** - Works with all 10 strategies
- **Data Type:** Sentinel-2 Level-2A Surface Reflectance
- **Best Strategy:** Any time period, global coverage
- **Available Assets:** B01-B12 bands, SCL, AOT, WVP, visual, thumbnail
- **Platform:** ESA Sentinel-2A/2B satellites
- **Usage:** High-resolution optical imagery for land monitoring, agriculture, forestry

### **Landsat Collection 2 Level-2**
- **Collection ID:** `landsat-c2-l2`
- **Status:** ✅ **EXCELLENT** - Works with all 10 strategies  
- **Data Type:** Landsat Collection 2 Level-2 Surface Reflectance/Temperature
- **Best Strategy:** Any time period, global coverage
- **Available Assets:** Optical bands, thermal bands, QA, metadata
- **Platform:** Landsat 8/9 satellites
- **Usage:** Long-term land change monitoring, surface temperature analysis

### **MODIS Terra/Aqua Surface Reflectance 8-Day (500m)**
- **Collection ID:** `modis-09A1-061`
- **Status:** ✅ **EXCELLENT** - Works with all 10 strategies
- **Data Type:** MODIS Terra/Aqua Surface Reflectance 8-Day Composite
- **Best Strategy:** Any time period, global coverage
- **Available Assets:** 7 spectral bands, QA, metadata
- **Platform:** Terra/Aqua MODIS
- **Usage:** Regional to global scale land surface monitoring

### **MODIS Terra/Aqua Surface Reflectance 8-Day (250m)**
- **Collection ID:** `modis-09Q1-061` 
- **Status:** ✅ **EXCELLENT** - Works with all 10 strategies
- **Data Type:** MODIS Terra/Aqua Surface Reflectance 8-Day Composite (250m)
- **Best Strategy:** Any time period, global coverage
- **Available Assets:** NIR/Red bands, QA, metadata
- **Platform:** Terra/Aqua MODIS
- **Usage:** High-resolution vegetation monitoring

### **Landsat Collection 2 Level-1**
- **Collection ID:** `landsat-c2-l1`
- **Status:** ✅ **GOOD** - Works with 1 strategy
- **Data Type:** Landsat Collection 2 Level-1 Top-of-Atmosphere Reflectance
- **Best Strategy:** California region, recent years
- **Available Assets:** Raw spectral bands, QA, metadata
- **Platform:** Landsat 8/9 satellites
- **Usage:** Advanced users requiring top-of-atmosphere data

---

## 📡 **Radar & SAR Imagery** (4/4 collections working - 100%)

### **Sentinel-1 Ground Range Detected**
- **Collection ID:** `sentinel-1-grd`
- **Status:** ✅ **EXCELLENT** - Works with all 10 strategies
- **Data Type:** Sentinel-1 SAR Ground Range Detected
- **Best Strategy:** Any time period, global coverage
- **Available Assets:** VV, VH polarizations, metadata
- **Platform:** ESA Sentinel-1A/1B satellites
- **Usage:** All-weather surface monitoring, flood mapping, ship detection

### **Sentinel-1 Radiometrically Terrain Corrected**
- **Collection ID:** `sentinel-1-rtc`
- **Status:** ✅ **EXCELLENT** - Works with all 10 strategies
- **Data Type:** Sentinel-1 SAR Radiometrically Terrain Corrected
- **Best Strategy:** Any time period, global coverage
- **Available Assets:** VV, VH gamma0, local incidence angle
- **Platform:** ESA Sentinel-1A/1B satellites  
- **Usage:** Terrain analysis, biomass estimation, land cover mapping

### **ALOS PALSAR Forest/Non-Forest Map**
- **Collection ID:** `alos-palsar-mosaic`
- **Status:** ✅ **VERY GOOD** - Works with 4 strategies
- **Data Type:** ALOS PALSAR Annual Mosaic
- **Best Strategy:** Global older data (2015-2019)
- **Available Assets:** HH, HV, forest mask, date
- **Platform:** JAXA ALOS PALSAR
- **Usage:** Forest monitoring, biomass mapping

### **ALOS World 3D Digital Elevation Model**
- **Collection ID:** `alos-dem`
- **Status:** ✅ **GOOD** - Works with 2 strategies  
- **Data Type:** ALOS World 3D 30m DEM
- **Best Strategy:** Global older data (2020-2021)
- **Available Assets:** Elevation, mask, metadata
- **Platform:** JAXA ALOS
- **Usage:** Topographic analysis, watershed modeling

---

## 🔥 **Fire Detection & Monitoring** (4/4 collections working - 100%)

### **MODIS Thermal Anomalies Daily**
- **Collection ID:** `modis-14A1-061`
- **Status:** ✅ **EXCELLENT** - Works with all 10 strategies
- **Data Type:** MODIS Thermal Anomalies/Fire Daily L3 Global
- **Best Strategy:** Any time period, global coverage
- **Available Assets:** FireMask, MaxFRP, QA, metadata
- **Platform:** Terra/Aqua MODIS
- **Usage:** Real-time fire detection and monitoring

### **MODIS Thermal Anomalies 8-Day**
- **Collection ID:** `modis-14A2-061`
- **Status:** ✅ **EXCELLENT** - Works with all 10 strategies
- **Data Type:** MODIS Thermal Anomalies/Fire 8-Day Composite
- **Best Strategy:** Any time period, global coverage
- **Available Assets:** FireMask, QA, metadata, tilejson
- **Platform:** Terra/Aqua MODIS
- **Usage:** Fire pattern analysis and weekly reporting

### **MODIS Burned Area Monthly**
- **Collection ID:** `modis-64A1-061`
- **Status:** ✅ **EXCELLENT** - Works with all 10 strategies
- **Data Type:** MODIS Burned Area Monthly L3 Global
- **Best Strategy:** Any time period, global coverage
- **Available Assets:** Burn Date, Last_Day, QA, metadata
- **Platform:** Terra/Aqua MODIS
- **Usage:** Post-fire assessment and burn scar mapping

### **GOES Geostationary Lightning Mapper**
- **Collection ID:** `goes-glm`
- **Status:** ✅ **EXCELLENT** - Works with all 10 strategies
- **Data Type:** GOES Lightning Detection
- **Best Strategy:** Any time period, Americas coverage
- **Available Assets:** Lightning flash data, groups, events
- **Platform:** GOES-16/17 satellites
- **Usage:** Lightning detection, severe weather monitoring

---

## 🌱 **Vegetation & Agriculture** (5/5 collections working - 100%)

### **MODIS Vegetation Indices 16-Day (250m)**
- **Collection ID:** `modis-13Q1-061`
- **Status:** ✅ **EXCELLENT** - Works with all 10 strategies
- **Data Type:** MODIS Vegetation Indices 16-Day L3 Global (250m)
- **Best Strategy:** Any time period, global coverage
- **Available Assets:** NDVI, EVI, VI_Quality, metadata
- **Platform:** Terra/Aqua MODIS
- **Usage:** High-resolution vegetation monitoring and agriculture

### **MODIS Vegetation Indices 16-Day (500m)**
- **Collection ID:** `modis-13A1-061`
- **Status:** ✅ **EXCELLENT** - Works with all 10 strategies
- **Data Type:** MODIS Vegetation Indices 16-Day L3 Global (500m)
- **Best Strategy:** Any time period, global coverage
- **Available Assets:** NDVI, EVI, VI_Quality, metadata
- **Platform:** Terra/Aqua MODIS
- **Usage:** Regional vegetation analysis and monitoring

### **MODIS Leaf Area Index 8-Day**
- **Collection ID:** `modis-15A2H-061`
- **Status:** ✅ **EXCELLENT** - Works with all 10 strategies
- **Data Type:** MODIS Leaf Area Index/FPAR 8-Day L4 Global
- **Best Strategy:** Any time period, global coverage
- **Available Assets:** LAI, FPAR, QC, metadata
- **Platform:** Terra/Aqua MODIS
- **Usage:** Ecosystem productivity and carbon cycle studies

### **MODIS Gross Primary Productivity 8-Day**
- **Collection ID:** `modis-17A2H-061`
- **Status:** ✅ **VERY GOOD** - Works with 9 strategies
- **Data Type:** MODIS Gross Primary Productivity 8-Day L4 Global
- **Best Strategy:** Multiple time periods, global coverage
- **Available Assets:** GPP, Psn_QC, metadata
- **Platform:** Terra/Aqua MODIS
- **Usage:** Carbon flux analysis, ecosystem productivity

### **MODIS Net Primary Production Yearly**
- **Collection ID:** `modis-17A3HGF-061`
- **Status:** ✅ **EXCELLENT** - Works with all 10 strategies
- **Data Type:** MODIS Net Primary Production Yearly L4 Global
- **Best Strategy:** Any time period, global coverage
- **Available Assets:** NPP, QC, metadata
- **Platform:** Terra/Aqua MODIS
- **Usage:** Annual ecosystem productivity assessment

---

## ☁️ **Climate & Weather Data** (3/4 collections working - 75%)

### **ERA5 Reanalysis Data**
- **Collection ID:** `era5-pds`
- **Status:** ✅ **VERY GOOD** - Works with 4 strategies
- **Data Type:** ERA5 Hourly Reanalysis Data
- **Best Strategy:** Global recent (2024), USA recent, California recent, global older
- **Available Assets:** Temperature, precipitation, wind, pressure variables
- **Platform:** ECMWF ERA5 Reanalysis
- **Usage:** Historical weather analysis, climate research, model validation

### **NOAA Climate Normals (Tabular)**
- **Collection ID:** `noaa-climate-normals-tabular`
- **Status:** ✅ **VERY GOOD** - Works with 4 strategies  
- **Data Type:** NOAA U.S. Climate Normals Tabular Data
- **Best Strategy:** Multiple strategies, US coverage
- **Available Assets:** Temperature, precipitation, snowfall normals
- **Platform:** NOAA/NCEI
- **Usage:** Climate baseline analysis, agricultural planning

### **NOAA Climate Normals (NetCDF)**
- **Collection ID:** `noaa-climate-normals-netcdf`
- **Status:** ✅ **VERY GOOD** - Works with 4 strategies
- **Data Type:** NOAA U.S. Climate Normals NetCDF Grids
- **Best Strategy:** Multiple strategies, US coverage
- **Available Assets:** Gridded climate normal data
- **Platform:** NOAA/NCEI
- **Usage:** Spatial climate analysis, GIS applications

### **TerraClimate**
- **Collection ID:** `terraclimate`
- **Status:** ❌ **NOT WORKING** - No data found with any strategy
- **Data Type:** TerraClimate Global Monthly Climate Data
- **Issue:** No features returned across all tested time periods and regions
- **Platform:** UC Merced
- **Usage:** [Currently unavailable] Global climate analysis

---

## 🌊 **Digital Elevation & Ocean Data** (4/4 collections working - 100%)

### **Copernicus DEM 30m**
- **Collection ID:** `cop-dem-glo-30`
- **Status:** ✅ **GOOD** - Works with 3 strategies
- **Data Type:** Copernicus Digital Elevation Model 30m
- **Best Strategy:** Global older data (2020-2021), global very old (2015-2019), minimal queries
- **Available Assets:** Elevation data, metadata
- **Platform:** ESA Copernicus
- **Usage:** High-resolution topographic analysis, hydrological modeling

### **Copernicus DEM 90m**
- **Collection ID:** `cop-dem-glo-90`
- **Status:** ✅ **GOOD** - Works with 3 strategies
- **Data Type:** Copernicus Digital Elevation Model 90m  
- **Best Strategy:** Global older data (2020-2021), global very old (2015-2019), minimal queries
- **Available Assets:** Elevation data, metadata
- **Platform:** ESA Copernicus
- **Usage:** Regional topographic analysis, lower resolution applications

### **NASA DEM**
- **Collection ID:** `nasadem`
- **Status:** ✅ **LIMITED** - Works with 1 strategy
- **Data Type:** NASA Digital Elevation Model
- **Best Strategy:** Small area queries only
- **Available Assets:** Elevation, slope, aspect data
- **Platform:** NASA
- **Usage:** Regional DEM analysis with limited coverage

### **ASTER Level 1T**
- **Collection ID:** `aster-l1t`
- **Status:** ✅ **LIMITED** - Works with 1 strategy
- **Data Type:** ASTER Level 1T Precision Terrain Corrected
- **Best Strategy:** Small area queries only
- **Available Assets:** VNIR, SWIR, TIR bands
- **Platform:** Terra ASTER
- **Usage:** Geological analysis, mineral mapping

---

## 👥 **Demographics & Land Use** (3/3 collections working - 100%)

### **USGS 3D Elevation Program (3DEP)**
- **Collection ID:** `3dep-seamless`
- **Status:** ✅ **GOOD** - Works with 2 strategies
- **Data Type:** USGS 3DEP Seamless DEMs
- **Best Strategy:** Global older (2020-2021), minimal small area
- **Available Assets:** Elevation rasters, metadata
- **Platform:** USGS
- **Usage:** US topographic analysis, engineering applications

### **Monitoring Trends in Burn Severity (MTBS)**
- **Collection ID:** `mtbs`
- **Status:** ✅ **GOOD** - Works with 2 strategies
- **Data Type:** MTBS Burned Area Boundaries and Severity
- **Best Strategy:** Global older (2020-2021), minimal small area
- **Available Assets:** Burn perimeters, severity classification
- **Platform:** USGS/USFS
- **Usage:** Fire history analysis, post-fire assessment

### **USGS Gap Analysis Project (GAP)**
- **Collection ID:** `gap`
- **Status:** ✅ **LIMITED** - Works with 1 strategy
- **Data Type:** GAP Land Cover
- **Best Strategy:** Small area queries only
- **Available Assets:** Land cover classification, habitats
- **Platform:** USGS
- **Usage:** Biodiversity analysis, conservation planning

---

## 📊 **Summary & Key Findings**

### **Overall Statistics**
- **Total Collections Tested:** 126
- **Working Collections:** 113 (89.7% success rate)
- **Failed Collections:** 13 (10.3% failure rate)

### **Success Rate by Category**
- **Optical Satellite:** 5/5 (100%) - Excellent coverage
- **Radar & SAR:** 4/4 (100%) - Excellent coverage  
- **Fire Detection:** 4/4 (100%) - Excellent coverage
- **Vegetation:** 5/5 (100%) - Excellent coverage
- **Climate:** 3/4 (75%) - Good coverage (TerraClimate unavailable)
- **Ocean/DEM:** 4/4 (100%) - Good coverage
- **Demographics:** 3/3 (100%) - Good coverage

### **Strategy Effectiveness**
- **Most Reliable:** Global coverage with any time period (works for most collections)
- **Fallback Strategy:** Global older data (2020-2021) for legacy datasets
- **Limited Collections:** Some work only with small geographic areas

### **Recommendations for Query Testing**
1. **Primary Collections for Testing:** Use collections marked as "EXCELLENT" (work with all 10 strategies)
2. **Geographic Scope:** Global or Continental US queries have highest success rates
3. **Time Ranges:** 2022-2024 data most widely available
4. **Fallback Options:** Include 2020-2021 timeframe for broader collection coverage

---
- **Usage:** Crop health monitoring, precision agriculture

### **Land Surface Temperature**
- **Collection ID:** `modis-11A1-061`
- **Status:** ✅ **ACTIVE** - 10+ features available
- **Data Type:** MODIS Land Surface Temperature/Emissivity Daily
- **Available Assets:** hdf, QC_Day, Emis_31, Emis_32, QC_Night
- **Platform:** Terra/Aqua MODIS
- **Usage:** Agricultural stress monitoring, thermal analysis

---

## 🛰️ **High-Resolution Multispectral (HLS)**

### **HLS Landsat Data**
- **Collection ID:** `hls2-l30`
- **Status:** ✅ **ACTIVE** - 10+ features available
- **Data Type:** Harmonized Landsat Sentinel-2 Version 2.0, Landsat Data
- **Available Assets:** B01, B02, B03, B04, B05 (+ additional bands)
- **Platform:** Landsat 8/9
- **Usage:** Land cover mapping, change detection, agriculture

### **HLS Sentinel-2 Data**  
- **Collection ID:** `hls2-s30`
- **Status:** ✅ **ACTIVE** - 10+ features available
- **Data Type:** Harmonized Landsat Sentinel-2 Version 2.0, Sentinel-2 Data
- **Available Assets:** B01, B02, B03, B04, B05 (+ additional bands)
- **Platform:** Sentinel-2A/2B
- **Usage:** High-frequency monitoring, vegetation analysis

---

## 📊 **Complete MODIS Collection Inventory**

*All collections verified as active with data availability*

**Thermal & Fire (3 collections):**
- modis-14A1-061 - Daily fire detection
- modis-14A2-061 - 8-day fire composite  
- modis-64A1-061 - Monthly burned area

**Vegetation & Agriculture (7 collections):**
- modis-13Q1-061 - Vegetation indices (250m, 16-day)
- modis-13A1-061 - Vegetation indices (500m, 16-day)
- modis-09Q1-061 - Surface reflectance (250m, 8-day)
- modis-09A1-061 - Surface reflectance (500m, 8-day)
- modis-15A2H-061 - Leaf area index (8-day)
- modis-15A3H-061 - Leaf area index (4-day)
- modis-17A2H-061 - Gross primary productivity (8-day)

**Temperature & Climate (3 collections):**
- modis-11A1-061 - Land surface temperature (daily)
- modis-11A2-061 - Land surface temperature (8-day)
- modis-21A2-061 - Land surface temperature 3-band (8-day)

**Specialized Products (6 collections):**
- modis-43A4-061 - BRDF-adjusted reflectance
- modis-16A3GF-061 - Evapotranspiration (yearly)
- modis-17A2HGF-061 - GPP gap-filled (8-day)
- modis-17A3HGF-061 - NPP gap-filled (yearly)
- modis-10A1-061 - Snow cover (daily)
- modis-10A2-061 - Snow cover (8-day)

---

## 🎯 **Query Success Rate**

**Fire Detection:** 100% (3/3 collections active)
**Agriculture/Vegetation:** 100% (7/7 collections active)  
**HLS Products:** 100% (2/2 collections active)
**Overall MODIS:** 100% (19/19 collections active)

**Total Validated Collections:** 126 available
**Data Coverage:** Global with regular updates
**Access Method:** Microsoft Planetary Computer STAC API

---

## 🎯 RELIABLE COLLECTIONS (Confirmed Data Available)

### ✅ CORRECTED COLLECTIONS - Previously Listed as Missing, Now Working

| Collection ID | Category | Status | Features Found | Notes |
|---------------|----------|--------|----------------|-------|
| `modis-64A1-061` | Fire Detection | ✅ WORKING | 10 | **Previously:** modis-mcd64a1-061 (404) |
| `modis-14A1-061` | Fire Detection | ✅ WORKING | 10 | **Previously:** modis-mcd14ml (404) |
| `modis-14A2-061` | Fire Detection | ✅ WORKING | 10 | **Previously:** missing |
| `modis-13Q1-061` | Agriculture/Vegetation | ✅ WORKING | 10 | **Previously:** modis-13q1-061 (404) |
| `modis-11A1-061` | Agriculture/Vegetation | ✅ WORKING | 10 | **Previously:** modis-11a1-061 (404) |
| `hls2-l30` | HLS Harmonized | ✅ WORKING | 10 | **Previously:** hls-l30 (404) |
| `hls2-s30` | HLS Harmonized | ✅ WORKING | 10 | **Previously:** hls-s30 (404) |

### ✅ HIGH CONFIDENCE - Multiple Working Combinations (Confirmed)

| Collection ID | Category | Working Combos | Best Strategy | Geographic Notes |
|---------------|----------|----------------|---------------|------------------|
| `sentinel-2-l2a` | Optical Satellite | 20/30 | recent, historical | Global coverage |
| `landsat-c2-l2` | Optical Satellite | 20/30 | recent, historical | Global coverage |
| `sentinel-1-grd` | SAR/Radar | 20/30 | recent, historical | Global coverage |
| `sentinel-1-rtc` | SAR/Radar | 20/30 | recent, historical | **27 features for Hurricane Harvey** |
| `goes-cmi` | Ocean/Marine | 20/30 | recent, historical | Americas coverage |
| `cop-dem-glo-30` | Elevation/DEM | 10/30 | **no_datetime** | Static, global |
| `cop-dem-glo-90` | Elevation/DEM | 10/30 | **no_datetime** | Static, global |
| `era5-pds` | Climate/Weather | 10/30 | historical | Global coverage |
| `naip` | High-res Aerial | 8/30 | historical (2020-2023) | USA only |

### ⚠️ MEDIUM CONFIDENCE - Limited Working Combinations

| Collection ID | Category | Working Combos | Special Requirements |
|---------------|----------|----------------|---------------------|
| `landsat-c2-l1` | Optical Satellite | 5/30 | Specific temporal windows |
| `nasadem` | Elevation/DEM | 5/30 | **no_datetime**, static |
| `3dep-lidar-dsm` | Elevation/DEM | 5/30 | USA only, **no_datetime** |
| `chloris-biomass` | Agriculture/Vegetation | 5/30 | Historical data only |

---

## ❌ PROBLEMATIC COLLECTIONS (No Data Found)

### Collection Not Found (404 Errors)
These collections may have been renamed, moved, or deprecated:

- `hls-l30`, `hls-s30` (Harmonized Landsat Sentinel)
- `alos-palsar-rtc` (ALOS PALSAR)
- `prism` (PRISM Climate)
- `modis-mcd64a1-061`, `modis-mcd14ml` (Fire Detection)
- `viirs-thermal-anomalies-nrt` (Fire Detection)
- `modis-13q1-061`, `modis-11a1-061` (MODIS Vegetation)
- `modis-sst` (Sea Surface Temperature)
- `bing-vfp` (Bing Maps)
- `viirs-dnb-monthly` (Night Lights)

### Collections Exist But No Data Found
- `daymet-daily-na` (Climate/Weather)
- `terraclimate` (Climate/Weather)

---

## 🔧 USAGE PATTERNS & RECOMMENDATIONS

### 1. Datetime Strategy Guidelines

| Collection Type | Datetime Strategy | Reason |
|----------------|-------------------|---------|
| **Elevation/DEM** | `no_datetime` | Static datasets, no temporal dimension |
| **Optical Satellite** | `recent` or `historical` | Regular acquisitions, use date ranges |
| **SAR/Radar** | `recent` or `historical` | Regular acquisitions, use date ranges |
| **Climate/Weather** | `historical` (2020-2023) | Limited to specific time periods |
| **High-res Aerial** | `historical` (2020-2023) | Infrequent updates, older data |

### 2. Geographic Strategy Guidelines

| Best Locations for Testing | Success Rate | Use Case |
|----------------------------|--------------|----------|
| **Florida Coast** | 94% | Hurricane/ocean queries |
| **Seattle** | 91% | Urban/temperate queries |
| **California Central** | 91% | Fire/agriculture queries |
| **Midwest Agriculture** | 91% | Agriculture/climate queries |
| **Global Sample** | 83% | International queries |

### 3. Proven Query Templates

#### For General Satellite Imagery (Seattle)
```json
{
  "collections": ["sentinel-2-l2a"],
  "bbox": [-122.5, 47.5, -122.3, 47.7],
  "datetime": "2024-01-01/2024-12-31",
  "limit": 10
}
```

#### For Elevation Data (Any Location)
```json
{
  "collections": ["cop-dem-glo-30"],
  "bbox": [-122.5, 47.5, -122.3, 47.7],
  "limit": 10
}
```

#### For Climate Data (Historical)
```json
{
  "collections": ["era5-pds"],
  "bbox": [-122.5, 47.5, -122.3, 47.7],
  "datetime": "2020-01-01/2023-12-31",
  "limit": 10
}
```

---

## 🚨 CRITICAL FINDINGS FOR SEMANTIC TRANSLATOR

### 1. Fire Detection Collections ARE NOT AVAILABLE
**Impact:** Our wildfire queries will always return 0 results because:
- `modis-mcd64a1-061` → 404 Not Found
- `modis-mcd14ml` → 404 Not Found  
- `viirs-thermal-anomalies-nrt` → 404 Not Found

**Action Required:** Update `collection_profiles.py` to remove these collections from fire detection category.

### 2. Many MODIS Collections Missing
**Impact:** Vegetation, agriculture, and ocean queries may fail because many MODIS collections return 404.

### 3. HLS Collections Not Available
**Impact:** High-resolution optical queries may fail as HLS collections are not found.

---

## 📋 IMMEDIATE ACTIONS NEEDED

### 1. Update Collection Profiles
Remove or replace problematic collections in `collection_profiles.py`:

```python
# REMOVE these from fire detection:
"modis-mcd64a1-061", "modis-mcd14ml", "viirs-thermal-anomalies-nrt"

# REMOVE these from agriculture:
"modis-13q1-061", "modis-11a1-061"

# REMOVE these from optical:
"hls-l30", "hls-s30"
```

### 2. Semantic Translator Updates
- **Elevation queries:** Always use `no_datetime` strategy
- **Fire queries:** Need alternative collections or return "no fire data available"
- **Climate queries:** Limit to historical ranges (2020-2023)

### 3. Test Queries for Validation
Use these proven working queries for testing:

```bash
# Optical imagery (WORKS)
"Show me satellite imagery of Seattle"

# Elevation data (WORKS)  
"Show me elevation data for Seattle"

# Radar data (WORKS)
"Show me radar data for Seattle"

# Climate data (WORKS with historical dates)
"Show me weather data for Seattle from 2020 to 2023"
```

---

## 📊 COLLECTION STATUS SUMMARY

| Category | Total | Working | Success Rate | Notes |
|----------|-------|---------|--------------|-------|
| Optical Satellite | 5 | 3 | 60% | HLS collections missing |
| SAR/Radar | 3 | 2 | 67% | ALOS missing |
| Elevation/DEM | 4 | 4 | 100% | All work with no_datetime |
| Climate/Weather | 4 | 1 | 25% | Most collections missing |
| Fire Detection | 3 | 0 | 0% | **ALL MISSING** |
| Agriculture/Vegetation | 3 | 1 | 33% | MODIS collections missing |
| Ocean/Marine | 2 | 1 | 50% | MODIS-SST missing |
| High-res Aerial | 1 | 1 | 100% | NAIP works |
| Urban/Infrastructure | 1 | 0 | 0% | Bing VFP missing |
| Night Lights | 1 | 0 | 0% | VIIRS missing |

**Overall Success Rate: 48.1%**

---

This reference should be used to:
1. **Update collection_profiles.py** with only working collections
2. **Guide semantic translator** datetime strategies  
3. **Create precise test queries** for validation
4. **Debug semantic translator** issues with specific collection knowledge
