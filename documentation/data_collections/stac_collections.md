# Earth Copilot - Master Collections Reference

**Purpose:** Single source of truth for all satellite imagery and geospatial data collections  
**Sources:** Microsoft Planetary Computer, NASA VEDA STAC API

---

## Table of Contents

1. [Overview](#overview)
2. [Quick Reference](#quick-reference)
3. [Featured Collections (Top Priority)](#featured-collections-top-priority)
4. [Collection Categories](#collection-categories)
5. [NASA VEDA Collections](#nasa-veda-collections)
6. [Technical Configuration](#technical-configuration)
7. [Usage Guidelines](#usage-guidelines)

---

## Overview

### Collection Statistics

| Source | Total Collections | Success Rate | Primary Use Case |
|--------|------------------|--------------|------------------|
| **Microsoft Planetary Computer** | 113+ | 89.7% | Real-time satellite monitoring |
| **NASA VEDA** | 10 | 100% | Specialized research datasets |
| **Featured Collections** | 21 | 100% | High-priority operational use |

### Dual Collection System

Earth Copilot uses **two separate STAC APIs** for different data needs:

1. **Microsoft Planetary Computer (MPC)**
   - Real-time satellite data (Sentinel-2, Landsat, MODIS)
   - Time-series focused with temporal filters
   - Cloud cover filtering supported
   - 113 working collections

2. **NASA VEDA**
   - Specialized research datasets (ERA5, climate models)
   - Static/historical datasets
   - No cloud cover filtering
   - 10 specialized collections

---

## Quick Reference

### Most Common Collections

| Collection ID | Resolution | Type | Best For | Update Frequency |
|--------------|------------|------|----------|------------------|
| `sentinel-2-l2a` | 10-60m | Optical | High-res imagery | 5 days |
| `landsat-c2-l2` | 30m | Optical | Long-term monitoring | 16 days |
| `hls-l30-002` | 30m | Optical | Harmonized L+S | 2-3 days |
| `hls-s30-002` | 30m | Optical | Harmonized L+S | 2-3 days |
| `cop-dem-glo-30` | 30m | Elevation | Terrain analysis | Static |
| `nasadem` | 30m | Elevation | Global DEM | Static |
| `sentinel-1-rtc` | 10m | SAR | All-weather imaging | 12 days |
| `modis-14A1-061` | 1km | Thermal | Fire detection | Daily |
| `modis-13Q1-061` | 250m | Vegetation | NDVI monitoring | 16 days |

### Date Range Strategies

Different collection types require different date strategies:

| Collection Type | Optimal Date Range | Reason |
|----------------|-------------------|---------|
| **Sentinel-2, Landsat, HLS** | Last 30-90 days | Near real-time updates |
| **Sentinel-1 SAR** | Last 30-90 days | Frequent acquisitions |
| **MODIS** | Jan-Jun 2024 | 3-6 month processing lag |
| **DEMs** (Copernicus, NASADEM) | No date filter | Static datasets |
| **NAIP** | 2020-2022 | Updated every 2-3 years |
| **NASA VEDA** | No date filter | Static/historical research data |

---

## Featured Collections (Top Priority)

### 21 Featured Collections - 100% Validated

These collections represent ~80% of typical Earth Copilot queries and are fully validated against the MPC STAC API.

#### High-Resolution Optical Imagery (5 collections)

**1. Sentinel-2 Level-2A** (`sentinel-2-l2a`)
- **Resolution:** 10m (RGB), 20m (red edge), 60m (atmospheric)
- **Coverage:** Global land and coastal waters
- **Temporal:** 2015-present, 5-day revisit
- **Key Bands:** 13 spectral bands (B01-B12, B8A)
- **Best For:** High-resolution optical imagery, vegetation analysis, water quality
- **Configuration:**
  - `rescale=0,3000` (prevents black tiles)
  - RGB bands: B04, B03, B02
  - Resampling: lanczos

**2. Landsat Collection 2 Level-2** (`landsat-c2-l2`)
- **Resolution:** 30m (optical), 100m (thermal)
- **Coverage:** Global, 16-day revisit
- **Temporal:** 1982-present (combined Landsat 4-9)
- **Key Bands:** 11 bands including thermal
- **Best For:** Long-term change detection, historical analysis
- **Configuration:**
  - RGB bands: red, green, blue
  - color_formula for enhancement
  - Resampling: lanczos

**3. HLS Landsat** (`hls-l30-002`)
- **Resolution:** 30m harmonized
- **Coverage:** North America
- **Temporal:** 2013-present, 2-3 day combined revisit
- **Best For:** Frequent monitoring, agriculture
- **Configuration:**
  - `rescale=0,3000` (CRITICAL - prevents black tiles)
  - RGB bands: B04, B03, B02
  - Resampling: lanczos

**4. HLS Sentinel-2** (`hls-s30-002`)
- **Resolution:** 30m harmonized
- **Coverage:** North America
- **Temporal:** 2013-present
- **Best For:** Harmonized cross-sensor analysis
- **Configuration:**
  - `rescale=0,3000` (CRITICAL)
  - RGB bands: B04, B03, B02
  - Resampling: lanczos

**5. NAIP** (`naip`)
- **Resolution:** 0.6m-1m (ultra-high resolution)
- **Coverage:** Continental US
- **Temporal:** 2010-2022, updated every 2-3 years
- **Best For:** Detailed US land cover, infrastructure
- **Configuration:**
  - RGB bands: R, G, B
  - Resampling: lanczos

---

#### Elevation Models (3 collections)

**6. Copernicus DEM 30m** (`cop-dem-glo-30`)
- **Resolution:** 30m
- **Coverage:** Global (-90° to 90° latitude)
- **Type:** Static elevation data
- **Best For:** Terrain analysis, slope calculations
- **Configuration:**
  - `rescale=0,3000`
  - colormap: terrain
  - Resampling: cubic
  - bidx: 1

**7. Copernicus DEM 90m** (`cop-dem-glo-90`)
- **Resolution:** 90m
- **Coverage:** Global
- **Type:** Static elevation data
- **Best For:** Large-area terrain analysis
- **Configuration:** Similar to 30m version

**8. NASADEM** (`nasadem`)
- **Resolution:** 30m
- **Coverage:** Global (60°N to 56°S)
- **Type:** Static NASA DEM
- **Best For:** High-quality global elevation
- **Configuration:**
  - `rescale=0,4000`
  - colormap: terrain
  - Resampling: cubic

---

#### SAR/Radar Imagery (2 collections)

**9. Sentinel-1 RTC** (`sentinel-1-rtc`)
- **Resolution:** 10m
- **Coverage:** Global
- **Temporal:** 2014-present, 12-day revisit
- **Best For:** All-weather imaging, displacement monitoring
- **Configuration:**
  - assets: vv
  - colormap: greys
  - Resampling: bilinear

**10. Sentinel-1 GRD** (`sentinel-1-grd`)
- **Resolution:** 10m
- **Coverage:** Global
- **Temporal:** 2014-present
- **Best For:** SAR backscatter analysis
- **Configuration:** Similar to RTC

---

#### MODIS Vegetation Products (5 collections)

**11. MODIS Vegetation Indices** (`modis-13Q1-061`)
- **Resolution:** 250m
- **Product:** MOD13Q1 (NDVI/EVI)
- **Temporal:** 16-day composites
- **Configuration:**
  - assets: 250m_16_days_NDVI
  - `rescale=-2000,10000`
  - colormap: greens

**12. MODIS Gross Primary Productivity** (`modis-17A2HGF-061`)
- **Resolution:** 500m
- **Product:** GPP/NPP
- **Temporal:** 8-day composites
- **Configuration:**
  - assets: Gpp_500m
  - `rescale=0,30000`
  - colormap: greens

**13. MODIS Leaf Area Index** (`modis-15A2H-061`)
- **Resolution:** 500m
- **Product:** LAI/FPAR
- **Temporal:** 8-day composites

**14. MODIS Land Cover** (`modis-17A3HGF-061`)
- **Resolution:** 500m
- **Product:** Annual NPP
- **Temporal:** Annual

**15. MODIS Vegetation Continuous Fields** (`modis-64A1-061`)
- **Resolution:** 250m
- **Product:** Vegetation cover
- **Temporal:** Annual

---

#### MODIS Fire Detection (2 collections)

**16. MODIS Thermal Anomalies (Terra)** (`modis-14A1-061`)
- **Resolution:** 1km
- **Product:** MOD14A1 Fire detection (Terra satellite)
- **Temporal:** Daily
- **Configuration:**
  - assets: FireMask
  - Resampling: nearest
  - bidx: 1

**17. MODIS Thermal Anomalies (Aqua)** (`modis-14A2-061`)
- **Resolution:** 1km
- **Product:** MYD14A2 Fire detection (Aqua satellite)
- **Temporal:** 8-day composite

---

#### MODIS Snow Cover (1 collection)

**18. MODIS Snow Cover** (`modis-10A1-061`)
- **Resolution:** 500m
- **Product:** Daily snow cover
- **Temporal:** Daily
- **Configuration:**
  - assets: NDSI_Snow_Cover
  - colormap: blues
  - Resampling: nearest

---

#### MODIS Temperature (1 collection)

**19. MODIS Land Surface Temperature** (`modis-11A2-061`)
- **Resolution:** 1km
- **Product:** LST 8-day composite
- **Temporal:** 8-day
- **Configuration:**
  - assets: LST_Day_1km
  - `rescale=7500,65535`
  - colormap: rdylbu_r

---

#### MODIS Surface Reflectance (2 collections)

**20. MODIS Daily Reflectance (Terra)** (`modis-09GA-061`)
- **Resolution:** 500m/1km
- **Product:** MOD09GA Daily surface reflectance (Terra)
- **Temporal:** Daily

**21. MODIS Daily Reflectance (Aqua)** (`modis-09GQ-061`)
- **Resolution:** 250m
- **Product:** MYD09GQ Daily surface reflectance (Aqua)
- **Temporal:** Daily

---

## Collection Categories

### Optical Imagery

#### High Resolution (≤10m)
- `sentinel-2-l2a` (10m) - ESA multispectral
- `naip` (0.6-1m) - US aerial imagery
- `alos-avnir-2` (10m) - Japanese optical

#### Medium Resolution (30m)
- `landsat-c2-l2` (30m) - USGS/NASA archive
- `hls-l30-002` (30m) - Harmonized Landsat
- `hls-s30-002` (30m) - Harmonized Sentinel-2

#### Coarse Resolution (>250m)
- `modis-09GA-061` (500m) - Daily reflectance
- `modis-13Q1-061` (250m) - Vegetation indices

---

### Synthetic Aperture Radar (SAR)

| Collection | Resolution | Polarization | Best For |
|-----------|-----------|--------------|----------|
| `sentinel-1-rtc` | 10m | VV, VH | Terrain-corrected radar |
| `sentinel-1-grd` | 10m | VV, VH | Raw backscatter |
| `alos-palsar-mosaic` | 25m | HH, HV | Forest monitoring |

**Key Advantages:**
- All-weather imaging (cloud penetration)
- Day/night capability
- Displacement monitoring
- Soil moisture detection

---

### Digital Elevation Models (DEMs)

| Collection | Resolution | Coverage | Vertical Accuracy |
|-----------|-----------|----------|------------------|
| `cop-dem-glo-30` | 30m | Global | ±2m |
| `cop-dem-glo-90` | 90m | Global | ±4m |
| `nasadem` | 30m | 60°N-56°S | ±5m |
| `alos-dem` | 30m | 82°N-82°S | ±5m |
| `3dep-seamless` | 10m | Continental US | ±1m |

**Use Cases:**
- Terrain analysis
- Slope/aspect calculations
- Line-of-sight analysis
- Flood modeling
- Viewshed analysis

---

### Fire & Thermal

**Active Fire Detection:**
- `modis-14A1-061` (1km, daily) - Terra/Aqua thermal anomalies
- `modis-14A2-061` (1km, 8-day) - Fire composite

**Burn Severity:**
- `barc-thomasfire` (30m) - Landsat-derived burn classification

**Land Surface Temperature:**
- `modis-11A2-061` (1km, 8-day) - Day/night LST

---

### Vegetation & Agriculture

**Vegetation Indices:**
- `modis-13Q1-061` (250m, 16-day) - NDVI/EVI
- `modis-13A1-061` (500m, 16-day) - NDVI/EVI
- `modis-13A2-061` (1km, 16-day) - NDVI/EVI

**Productivity:**
- `modis-17A2HGF-061` (500m, 8-day) - Gross Primary Productivity
- `modis-17A3HGF-061` (500m, annual) - Net Primary Productivity

**Biophysical:**
- `modis-15A2H-061` (500m, 8-day) - Leaf Area Index / FPAR
- `modis-64A1-061` (250m, annual) - Vegetation Continuous Fields

---

### Water & Hydrology

**Surface Water:**
- `jrc-gsw` (30m) - Global Surface Water (1984-2021)
- `hrea` (10m) - High-Resolution Elevation for Africa

**Water Quality:**
- Use Sentinel-2 bands (B03, B04, B08) for turbidity/chlorophyll

---

### Snow & Ice

**Snow Cover:**
- `modis-10A1-061` (500m, daily) - Snow cover extent
- `modis-10A2-061` (500m, 8-day) - Snow cover composite

**Fractional Snow Cover:**
- Use NDSI (Normalized Difference Snow Index) from Sentinel-2/Landsat

---

### Land Cover

**Global Products:**
- `esa-worldcover` (10m) - ESA WorldCover 2020/2021
- `esa-cci-lc` (300m) - ESA CCI Land Cover 1992-2020
- `modis-17A3HGF-061` (500m) - MODIS land cover

**Regional:**
- `bangladesh-landcover-2001-2020` (500m) - Bangladesh specific
- `io-lulc` (10m) - Impact Observatory global land use

---

### Weather & Climate

**Reanalysis (NASA VEDA):**
- `blizzard-era5-10m-wind` (0.25°) - ERA5 wind events
- `blizzard-era5-2m-temp` (0.25°) - ERA5 temperature events
- `blizzard-era5-mslp` (0.25°) - Mean sea level pressure
- `blizzard-era5-precip` (0.25°) - Precipitation events

**Atmospheric:**
- `sentinel-5p-l2-netcdf` - Atmospheric composition
- `sentinel-3-synergy-aod-l2-netcdf` - Aerosol optical depth

---

## NASA VEDA Collections

### Overview

NASA VEDA (Visualization, Exploration, and Data Analysis) provides specialized research datasets through a separate STAC API.

**Key Differences from MPC:**
- Static/historical datasets (not time-series)
- Use `no_datetime` query strategy
- Research-focused vs operational monitoring
- 100% success rate with proper configuration

### VEDA Collection Inventory (10 Collections)

#### 1. Land Cover & Vegetation (1 collection)

**Bangladesh Land Cover 2001-2020** (`bangladesh-landcover-2001-2020`)
- **Resolution:** 500m
- **Platform:** MODIS MCD12Q1
- **Temporal:** 2001, 2020 (two snapshots)
- **Type:** Categorical land cover classification
- **Use Cases:** Land cover change analysis, Bangladesh-specific studies
- **Query Strategy:** `no_datetime`

---

#### 2. Fire & Burn Severity (1 collection)

**BARC Thomas Fire** (`barc-thomasfire`)
- **Resolution:** 30m
- **Platform:** Landsat-derived BARC
- **Event:** Thomas Fire, December 2017 (California)
- **Type:** Burn Area Reflectance Classification
- **Use Cases:** Wildfire damage assessment, burn severity mapping
- **Query Strategy:** `no_datetime`

---

#### 3. Climate & Weather Research (4 collections)

**ERA5 10m Wind Events** (`blizzard-era5-10m-wind`)
- **Resolution:** 0.25° (~28km)
- **Platform:** ERA5 Reanalysis
- **Type:** Wind speed at 10 meters
- **Events:** Select blizzards/storms
- **Use Cases:** Storm analysis, wind pattern research

**ERA5 2m Temperature Events** (`blizzard-era5-2m-temp`)
- **Resolution:** 0.25°
- **Platform:** ERA5 Reanalysis
- **Type:** Temperature at 2 meters
- **Events:** Select cold weather events
- **Use Cases:** Temperature extremes, cold snap analysis

**ERA5 Mean Sea Level Pressure** (`blizzard-era5-mslp`)
- **Resolution:** 0.25°
- **Platform:** ERA5 Reanalysis
- **Type:** Atmospheric pressure
- **Events:** Select weather systems
- **Use Cases:** Cyclone tracking, pressure system analysis

**ERA5 Precipitation Events** (`blizzard-era5-precip`)
- **Resolution:** 0.25°
- **Platform:** ERA5 Reanalysis
- **Type:** Total precipitation
- **Events:** Select extreme precipitation events
- **Use Cases:** Flood analysis, precipitation patterns

---

#### 4. Snow & Ice Research (2 collections)

**Colorado Low Snow** (`coloradolow-snow`)
- **Resolution:** Varies
- **Type:** Snow depth/extent research
- **Event:** Colorado Low weather pattern
- **Use Cases:** Winter storm analysis, snow accumulation

**Alberta Clipper Snow** (`albertaclipper-snow`)
- **Resolution:** Varies
- **Type:** Snow depth/extent research
- **Event:** Alberta Clipper weather pattern
- **Use Cases:** Fast-moving winter storm analysis

---

#### 5. Temperature Extremes (2 collections)

**Colorado Low Temperature** (`coloradolow-temp`)
- **Resolution:** Varies
- **Type:** Temperature analysis
- **Event:** Colorado Low cold air outbreak
- **Use Cases:** Cold weather research

**Alberta Clipper Temperature** (`albertaclipper-temp`)
- **Resolution:** Varies
- **Type:** Temperature analysis
- **Event:** Alberta Clipper cold front
- **Use Cases:** Rapid temperature drop analysis

---

### Automatic Query Routing

The system automatically routes queries to VEDA when it detects:

```python
veda_indicators = [
    "bangladesh", "thomas fire", "era5", "blizzard",
    "alberta clipper", "colorado low", 
    "specialized research", "nasa research",
    "climate model", "scientific study",
    "historical analysis", "static dataset"
]
```

**Example Queries:**
- "Show me the Bangladesh land cover change from 2001 to 2020" → VEDA
- "Analyze the Thomas Fire burn severity" → VEDA
- "ERA5 wind patterns during the 2021 blizzard" → VEDA
- "Show me current Sentinel-2 imagery of Seattle" → Microsoft Planetary Computer

---

## Technical Configuration

### Rendering Parameters

#### Critical Parameters by Collection Type

**Optical RGB Imagery:**
```python
{
    "assets": "B04,B03,B02",  # Red, Green, Blue
    "rescale": "0,3000",      # Prevents black tiles for HLS/Sentinel-2
    "resampling": "lanczos"   # High-quality resampling
}
```

**Elevation (DEMs):**
```python
{
    "assets": "data",
    "rescale": "0,3000",      # Adjust range as needed
    "colormap": "terrain",
    "resampling": "cubic",    # Smooth elevation
    "bidx": 1
}
```

**SAR (Sentinel-1):**
```python
{
    "assets": "vv",           # VV polarization
    "colormap": "greys",
    "resampling": "bilinear",
    "bidx": 1
}
```

**MODIS Vegetation:**
```python
{
    "assets": "250m_16_days_NDVI",
    "rescale": "-2000,10000",
    "colormap": "greens",
    "resampling": "nearest"
}
```

**MODIS Fire:**
```python
{
    "assets": "FireMask",
    "colormap": "hot",        # Fire color scheme
    "resampling": "nearest",  # Preserve discrete values
    "bidx": 1
}
```

---

### Temporal Query Strategies

```python
COLLECTION_DATE_STRATEGIES = {
    # Static datasets - no date filter
    "cop-dem-glo-30": {"date_filter": False},
    "cop-dem-glo-90": {"date_filter": False},
    "nasadem": {"date_filter": False},
    
    # Near real-time - use recent dates
    "sentinel-2-l2a": {"days_back": 30, "from_date": "2024-10-29"},
    "landsat-c2-l2": {"days_back": 90, "from_date": "2024-10-29"},
    "hls-l30-002": {"days_back": 30, "from_date": "2024-10-29"},
    "hls-s30-002": {"days_back": 30, "from_date": "2024-10-29"},
    "sentinel-1-rtc": {"days_back": 90, "from_date": "2024-10-29"},
    "sentinel-1-grd": {"days_back": 30, "from_date": "2024-10-29"},
    
    # MODIS - 3-6 month lag
    "modis-13Q1-061": {"fixed_range": ["2024-01-01", "2024-06-30"]},
    "modis-14A1-061": {"fixed_range": ["2024-01-01", "2024-06-30"]},
    "modis-11A2-061": {"fixed_range": ["2024-01-01", "2024-06-30"]},
    # ... all MODIS collections use Jan-Jun 2024
    
    # VEDA collections - no datetime
    "bangladesh-landcover-2001-2020": {"strategy": "no_datetime"},
    "barc-thomasfire": {"strategy": "no_datetime"},
    "blizzard-era5-10m-wind": {"strategy": "no_datetime"},
    # ... all VEDA collections use no_datetime
}
```

---

### Cloud Cover Filtering

**Analysis-Based Cloud Cover Limits:**

```python
def determine_cloud_cover_limit(analysis_type):
    limits = {
        "blue_tarp_detection": 5,     # Very strict
        "emergency_response": 10,      # Strict
        "damage_assessment": 15,       # Moderate
        "general_monitoring": 30,      # Relaxed
        "change_detection": 20,        # Moderate-strict
        "vegetation_analysis": 25      # Moderate
    }
    return limits.get(analysis_type, 20)  # Default: 20%
```

**Collections Without Cloud Filtering:**
- All DEMs (static elevation)
- SAR collections (cloud-penetrating)
- MODIS thermal/fire (uses quality masks)
- NASA VEDA collections (research datasets)

---

## Usage Guidelines

### Best Practices

#### 1. Collection Selection
- **High-resolution needs** → Sentinel-2 (10m) or NAIP (0.6m)
- **Long-term monitoring** → Landsat (1982-present)
- **Frequent updates** → HLS (2-3 day revisit)
- **All-weather** → Sentinel-1 SAR
- **Fire detection** → MODIS thermal anomalies
- **Vegetation health** → MODIS NDVI (250m-1km)
- **Terrain analysis** → Copernicus DEM or NASADEM

#### 2. Date Range Selection
- **Optical imagery:** Last 30-90 days for best cloud-free options
- **MODIS products:** Jan-Jun 2024 (account for processing lag)
- **DEMs:** No date filter required
- **VEDA:** Always use `no_datetime` strategy

#### 3. Cloud Cover Management
- **Critical analysis:** <10% cloud cover
- **General monitoring:** <30% cloud cover
- **SAR when available:** No cloud concerns
- **MODIS:** Use quality masks instead of cloud filters

#### 4. Resolution vs Coverage Trade-offs
- **<1m:** Limited coverage, very high detail (NAIP - US only)
- **10-30m:** Good balance (Sentinel-2, Landsat, HLS)
- **250m-1km:** Global, frequent (MODIS)
- **Consider revisit time:** Higher resolution = longer revisit

---

### Common Issues & Solutions

#### Issue: Black Tiles on HLS Collections
**Solution:** Always use `rescale=0,3000` parameter
```python
#  Correct
"rescale": "0,3000"

#  Wrong - will produce black tiles
"rescale": "0,10000"  # or missing rescale
```

#### Issue: No MODIS Results for Recent Dates
**Solution:** Use Jan-Jun 2024 date range (3-6 month processing lag)
```python
#  Correct for MODIS
"datetime": "2024-01-01/2024-06-30"

#  Wrong - no results
"datetime": "2024-10-01/2024-10-29"
```

#### Issue: VEDA Collections Return No Results
**Solution:** Use `no_datetime` strategy - don't include temporal filters
```python
#  Correct for VEDA
query = {
    "collections": ["bangladesh-landcover-2001-2020"]
    # No datetime parameter
}

#  Wrong - will fail
query = {
    "collections": ["bangladesh-landcover-2001-2020"],
    "datetime": "2020-01-01/2020-12-31"  # Don't use dates
}
```

#### Issue: DEM Queries Returning No Results
**Solution:** Remove datetime filters - DEMs are static
```python
#  Correct for DEMs
collections = ["cop-dem-glo-30"]
# No date filtering

#  Wrong
collections = ["cop-dem-glo-30"]
datetime = "2024-01-01/2024-10-29"  # DEMs don't have dates
```

---

### Validation Status

#### Featured Collections Test Results
- **Total Tested:** 21 collections
- **Success Rate:** 100% (21/21)
- **Tests per Collection:** 6
  1. Collection exists in MPC STAC API 
  2. Render configuration present 
  3. Tile URL generation successful 
  4. Asset mapping correct 
  5. Required parameters included 
  6. Data type validation passed 

#### VEDA Collections Test Results
- **Total Tested:** 10 collections
- **Success Rate:** 100% (10/10)
- **Strategy:** All use `no_datetime` approach
- **API Endpoint:** `https://openveda.cloud/api/stac/`

---

### Related Documentation

- **VEDA Profiles:** `earth-copilot/container-app/veda_collection_profiles.py`
- **MPC Profiles:** `earth-copilot/container-app/collection_profiles.py`
- **Rendering System:** `earth-copilot/container-app/hybrid_rendering_system.py`
- **Semantic Translator:** `earth-copilot/container-app/semantic_translator.py`

---

### External Resources

- **Microsoft Planetary Computer:** https://planetarycomputer.microsoft.com/catalog
- **NASA VEDA:** https://www.earthdata.nasa.gov/dashboard/
- **STAC Browser:** https://radiantearth.github.io/stac-browser/
- **TiTiler Docs:** https://developmentseed.org/titiler/
- **COG Spec:** https://www.cogeo.org/

---

## Summary

This master reference consolidates all Earth Copilot collection documentation into a single source of truth. Use this document for:

- **Collection selection** - Find the right data for your use case  
- **Configuration** - Get proven rendering parameters  
- **Date strategies** - Use correct temporal filters  
- **Troubleshooting** - Solve common issues  
- **Validation** - Confirm collection availability

---

*For technical implementation details, see the codebase:*
- `collection_profiles.py` - MPC configurations
- `veda_collection_profiles.py` - NASA VEDA configurations  
- `semantic_translator.py` - Query routing logic
- `hybrid_rendering_system.py` - Rendering configurations
