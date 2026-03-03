# 🛰️ STAC Collection Availability Guide

**Microsoft Planetary Computer | Earth Copilot**

This guide helps you craft queries that return results for all 21 available satellite and geospatial collections.

---

## ⭐ Featured Collections

The following collections are production-ready, high-priority datasets optimized for reliable querying and visualization in Earth Copilot.

### 🌍 Harmonized Landsat and Sentinel-2 (HLS) v2.0

**Collections:** `hls2-l30` (Landsat) and `hls2-s30` (Sentinel-2)

Harmonized Landsat Sentinel-2 (HLS) Version 2.0 provides consistent surface reflectance (SR) and top of atmosphere (TOA) brightness data from the Operational Land Imager (OLI) aboard the joint NASA/USGS Landsat 8 and Landsat 9 satellites and the Multi-Spectral Instrument (MSI) aboard the ESA (European Space Agency) Sentinel-2A, Sentinel-2B, and Sentinel-2C satellites.

**Specifications:**
- **Resolution:** 30m (harmonized from both sensors)
- **Temporal Coverage:** 2020-01-01 to Present
- **Revisit Time:** ~2-3 days (combined constellation)
- **Spectral Bands:** 11 harmonized bands (B02-B12)
- **Processing Level:** Surface reflectance (atmospherically corrected)

**How to Query:**
```
✅ "Show me HLS Landsat imagery of Washington State forests from 2024"
✅ "Find HLS Sentinel-2 data for California agriculture with low cloud cover"
✅ "Display recent HLS imagery of the Amazon rainforest"
```

**Best Practices:**
- Use "recent" or "latest" for current data (last 30 days)
- Mention "low cloud cover" for optical imagery
- Ideal for vegetation monitoring and land cover change detection
- Seamlessly combines Landsat and Sentinel-2 for consistent time-series

**Tags:** `Sentinel` `Landsat` `HLS` `Satellite` `Global` `Imagery`

---

### 🛰️ Landsat Collection 2

**Collections:** `landsat-c2-l2` (Surface Reflectance), `landsat-c2-l1` (Historical MSS)

The Landsat program provides a comprehensive, continuous archive of multispectral imagery of the Earth's surface from 1972 to present. The longest-running Earth observation program.

**Specifications:**
- **Resolution:** 30m (OLI/TIRS), 79m (MSS historical)
- **Temporal Coverage:** 
  - L2 (Surface Reflectance): 1982-08-22 to Present
  - L1 (MSS Historical): 1972-07-25 to 2013-01-07
- **Platform:** Landsat 4-9 (L2), Landsat 1-5 MSS (L1)
- **Spectral Bands:** 11 bands (L8/L9), 4 bands (MSS)

**How to Query:**
```
✅ "Show me Landsat imagery of Yellowstone National Park"
✅ "Find Landsat images of urban development in Phoenix from 2023"
✅ "Display recent Landsat data for forest monitoring"
✅ "Show me historical Landsat MSS imagery from 1970s Montana"
```

**Best Practices:**
- Use "recent" or "latest" for L2 surface reflectance
- Specify "historical" or "1970s-1990s" for L1 MSS data
- 16-day revisit time per satellite
- Ideal for long-term change detection (50+ year archive)

**Tags:** `Landsat` `USGS` `NASA` `Satellite` `Global` `Imagery`

---

### 🌡️ MODIS Version 6.1 Products

**Collections:** 14 MODIS products including vegetation, temperature, fire, and snow

The MODIS instrument operates on both the Terra and Aqua spacecraft, covering the entire surface of the Earth within one or two days. The derived data products describe atmosphere, cryosphere, land, and ocean features utilized in studies across various disciplines.

**Specifications:**
- **Resolution:** 250m, 500m, and 1km (varies by product)
- **Temporal Coverage:** 2000-02-16 to Present
- **Platform:** Terra + Aqua combined
- **Revisit Time:** Daily to 8-day composites

**Featured Products:**
- **MODIS-43A4-061** (NBAR): BRDF-corrected reflectance (500m)
- **MODIS-09A1/09Q1-061**: Surface reflectance (500m/250m)
- **MODIS-13A1/13Q1-061**: Vegetation indices - NDVI/EVI (500m/250m)
- **MODIS-11A1-061**: Land surface temperature (1km)
- **MODIS-14A1/14A2-061**: Thermal anomalies/fire detection (1km)
- **MODIS-15A2H-061**: Leaf area index (500m)
- **MODIS-17A2H/17A3HGF-061**: Gross/Net primary production (500m)
- **MODIS-10A1-061**: Snow cover daily (500m)

**How to Query:**
```
✅ "Show me MODIS vegetation index for the Sahel from early 2024"
✅ "Find MODIS fire data for California from January-June 2024"
✅ "Display MODIS land surface temperature in Death Valley from spring 2024"
✅ "Show me MODIS snow cover in the Himalayas from winter 2024"
```

**Best Practices:**
- ⚠️ **CRITICAL:** Use "early 2024", "spring 2024", or "January-June 2024" dates
- **Do NOT use current dates** - MODIS has 3-6 month processing lag
- Ideal for global monitoring at moderate resolution
- Use for vegetation health, fire detection, thermal analysis, snow monitoring

**Tags:** `MODIS` `NASA` `USGS` `Satellite` `Global` `Imagery`

---

### 📡 Sentinel-1 Synthetic Aperture Radar (SAR)

**Collections:** `sentinel-1-rtc` (Radiometrically Terrain Corrected), `sentinel-1-grd` (Ground Range Detected)

Sentinel-1 comprises a constellation of two polar-orbiting satellites, operating day and night performing C-band synthetic aperture radar imaging. Weather-independent, cloud-penetrating radar.

**Specifications:**
- **Resolution:** 10m pixel spacing (~20m ground resolution)
- **Temporal Coverage:** 2014-10-10 to Present
- **Platform:** Sentinel-1A, Sentinel-1B, Sentinel-1C
- **Polarizations:** VV, VH, HH, HV
- **Revisit Time:** 6-12 days

**How to Query:**
```
✅ "Show me Sentinel-1 radar imagery of Seattle for flood monitoring"
✅ "Find SAR data for ship detection near Los Angeles"
✅ "Display Sentinel-1 RTC for Houston during Hurricane Harvey August 2017"
```

**Best Practices:**
- **Weather-independent** - works through clouds and at night
- Use "recent" or "latest" for current monitoring
- RTC recommended for terrain analysis (includes terrain correction)
- GRD for general SAR applications
- Ideal for flood mapping, ship detection, change detection

**Tags:** `ESA` `Copernicus` `Sentinel` `C-Band` `SAR`

---

### 🌍 Sentinel-2 Level-2A

**Collection:** `sentinel-2-l2a`

The Sentinel-2 program provides global imagery in thirteen spectral bands at 10m-60m resolution and a revisit time of approximately five days. This dataset contains the global Sentinel-2 archive, from 2015 to the present, processed to L2A (bottom-of-atmosphere surface reflectance).

**Specifications:**
- **Resolution:** 10m (RGB+NIR), 20m (red edge+SWIR), 60m (coastal/water vapor)
- **Temporal Coverage:** 2015-06-27 to Present
- **Platform:** Sentinel-2A, Sentinel-2B
- **Spectral Bands:** 13 bands including red edge bands
- **Revisit Time:** ~5 days (with both satellites)

**How to Query:**
```
✅ "Show me Sentinel-2 imagery of California with low cloud cover"
✅ "Find recent Sentinel-2 images of the Amazon rainforest"
✅ "Display Sentinel-2 data for coastal monitoring in Florida"
```

**Best Practices:**
- Mention "recent" or "latest" for current data (last 30 days)
- Always include "low cloud cover" or "clear sky" for best results
- Superior to Landsat for: higher resolution (10m vs 30m), red edge bands, faster revisit
- Ideal for vegetation analysis, land cover mapping, precision agriculture

**Tags:** `Sentinel` `Copernicus` `ESA` `Satellite` `Global` `Imagery` `Reflectance`

---

## 📅 Understanding Data Availability

Different satellite collections have different update schedules and data availability patterns. Use this guide to ensure your queries match the right time ranges for each collection type.

---

## 🎯 Quick Reference Table

| Collection | Resolution | Date Range to Use | Why |
|-----------|-----------|-------------------|-----|
| **NAIP** | 0.6m | No date needed | Updates every 2-3 years, use latest available |
| **Sentinel-2 L2A** | 10m | Last 30 days | Near real-time, updated continuously |
| **Landsat C2 L2** | 30m | Last 90 days | Near real-time, updated continuously |
| **HLS L30** | 30m | Last 30 days | Harmonized Landsat, recent data |
| **HLS S30** | 30m | Last 30 days | Harmonized Sentinel-2, recent data |
| **Copernicus DEM 30m** | 30m | No date needed | Static elevation dataset (2021) |
| **Copernicus DEM 90m** | 90m | No date needed | Static elevation dataset (2021) |
| **NASADEM** | 30m | No date needed | Static elevation dataset (2000) |
| **Sentinel-1 RTC** | 10-20m | Last 90 days | Radar data, updated continuously |
| **Sentinel-1 GRD** | 10-20m | Last 30 days | Radar data, updated continuously |
| **MODIS 09A1** (500m) | 500m | January-June 2024 | 3-6 month processing lag |
| **MODIS 09Q1** (250m) | 250m | January-June 2024 | 3-6 month processing lag |
| **MODIS 13A1** (NDVI 500m) | 500m | January-June 2024 | 3-6 month processing lag |
| **MODIS 13Q1** (NDVI 250m) | 250m | January-June 2024 | 3-6 month processing lag |
| **MODIS 15A2H** (LAI) | 500m | January-June 2024 | 3-6 month processing lag |
| **MODIS 17A2H** (GPP) | 500m | January-June 2024 | 3-6 month processing lag |
| **MODIS 17A3HGF** (NPP) | 500m | 2023-2024 | Yearly product, processing lag |
| **MODIS 14A1** (Fire Daily) | 1km | January-June 2024 | 3-6 month processing lag |
| **MODIS 14A2** (Fire 8-day) | 1km | January-June 2024 | 3-6 month processing lag |
| **MODIS 10A1** (Snow) | 500m | Winter 2024 (Jan-Mar) | Seasonal, 3-6 month lag |
| **MODIS 11A1** (Temperature) | 1km | January-June 2024 | 3-6 month processing lag |

---

## 💡 Example Queries That Work

### Ultra High-Resolution Imagery (0.6m - 10m)

**NAIP (0.6m aerial imagery)**
```
✅ "Show me NAIP imagery of Seattle"
✅ "Find NAIP aerial photos of New York City"
✅ "Display NAIP imagery for agricultural areas in Iowa"
```
💡 **Tip:** Don't specify dates - NAIP updates every 2-3 years, latest is from 2023

---

**Sentinel-2 L2A (10m multispectral)**
```
✅ "Show me Sentinel-2 imagery of California with low cloud cover"
✅ "Find recent Sentinel-2 images of the Amazon rainforest"
✅ "Display Sentinel-2 data for coastal monitoring in Florida"
```
💡 **Tip:** Mention "recent" or "latest" - data is near real-time (last 30 days)

---

### High Resolution Imagery (30m)

**Landsat C2 L2**
```
✅ "Show me Landsat imagery of Yellowstone National Park"
✅ "Find Landsat images of urban development in Phoenix"
✅ "Display recent Landsat data for forest monitoring"
```
💡 **Tip:** Use "recent" for best results - data updated continuously

---

**HLS (Harmonized Landsat Sentinel-2)**
```
✅ "Show me HLS images of agricultural fields in Kansas"
✅ "Find HLS data for vegetation monitoring with low cloud cover"
✅ "Display HLS imagery of wetlands in Louisiana"
```
💡 **Tip:** HLS combines Landsat and Sentinel-2, use recent dates

---

### Elevation Data (30m - 90m)

**Copernicus DEM / NASADEM**
```
✅ "Show me elevation of the Rocky Mountains"
✅ "Display terrain data for California"
✅ "Find topography of the Appalachian Mountains"
✅ "Show me a 3D elevation model of Hawaii"
```
💡 **Tip:** No dates needed - these are static datasets from 2000-2021

---

### Radar/SAR Data (10m - 20m)

**Sentinel-1 RTC/GRD**
```
✅ "Show me Sentinel-1 radar imagery of Seattle"
✅ "Find SAR data for flood monitoring in the Mississippi River"
✅ "Display Sentinel-1 for ship detection near Los Angeles"
```
💡 **Tip:** Mention "recent" - radar data updated every 6-12 days

---

### MODIS Collections (250m - 1km)

**⚠️ IMPORTANT: MODIS data has a 3-6 month processing delay**

**Surface Reflectance (MODIS 09A1 / 09Q1)**
```
✅ "Show me MODIS surface reflectance of California from early 2024"
✅ "Find MODIS tiles for the Amazon from January to June 2024"
✅ "Display MODIS imagery of Africa from spring 2024"
```
💡 **Tip:** Specify "early 2024", "January-June 2024", or "spring 2024"

---

**Vegetation Indices (MODIS 13A1 / 13Q1 - NDVI)**
```
✅ "Show me MODIS vegetation index of the Sahel from early 2024"
✅ "Find MODIS NDVI for agricultural monitoring from spring 2024"
✅ "Display vegetation health in the Great Plains from Jan-Jun 2024"
```
💡 **Tip:** Use "early 2024" or "spring 2024" for vegetation data

---

**Leaf Area Index (MODIS 15A2H)**
```
✅ "Show me leaf area index of the Amazon from early 2024"
✅ "Find MODIS LAI for forest canopy analysis from spring 2024"
✅ "Display vegetation coverage in Southeast Asia from Jan-Jun 2024"
```
💡 **Tip:** Best for tropical forests and dense vegetation areas

---

**Productivity (MODIS 17A2H GPP / 17A3HGF NPP)**
```
✅ "Show me MODIS productivity of the Amazon from early 2024"
✅ "Find gross primary production in rainforests from spring 2024"
✅ "Display ecosystem productivity in Congo Basin from Jan-Jun 2024"
```
💡 **Tip:** Focus on highly productive ecosystems (rainforests, croplands)

---

**Fire Detection (MODIS 14A1 / 14A2)**
```
✅ "Show me MODIS fire data for California from early 2024"
✅ "Find active fires in Australia from January to June 2024"
✅ "Display fire activity in the Amazon from spring 2024"
```
💡 **Tip:** Use "early 2024" or specify Jan-Jun for fire data

---

**Snow Cover (MODIS 10A1)**
```
✅ "Show me MODIS snow cover in the Sierra Nevada from winter 2024"
✅ "Find snow extent in the Alps from January to March 2024"
✅ "Display snow coverage in the Himalayas from early 2024"
```
💡 **Tip:** Use winter months (Jan-Mar 2024) for snow data

---

**Land Surface Temperature (MODIS 11A1)**
```
✅ "Show me MODIS temperature of Death Valley from spring 2024"
✅ "Find land surface temperature in the Sahara from early 2024"
✅ "Display thermal data for urban heat islands from Jan-Jun 2024"
```
💡 **Tip:** Great for hot regions and urban heat analysis

---

## 🚫 Common Query Mistakes to Avoid

### ❌ Don't Use Current/Recent Dates for MODIS
```
❌ "Show me MODIS data from October 2024"  (No results - data not yet processed)
✅ "Show me MODIS data from spring 2024"   (Works - data available)
```

### ❌ Don't Specify Dates for Static Datasets
```
❌ "Show me 2024 elevation data for Colorado"  (Elevation doesn't change)
✅ "Show me elevation of Colorado"             (Gets static DEM data)
```

### ❌ Don't Use Old Dates for Near Real-Time Data
```
❌ "Show me Sentinel-2 from 2020"  (Too old, use recent dates)
✅ "Show me recent Sentinel-2"     (Gets latest data)
```

### ❌ Don't Use Specific Dates for NAIP
```
❌ "Show me NAIP from 2024"  (NAIP updates every 2-3 years)
✅ "Show me NAIP imagery"    (Gets latest available, usually 2023)
```

---

## 📊 Collection Categories Summary

### Category 1: No Date Filter Needed
- **NAIP** - Get latest available (usually 2023)
- **All DEMs** - Static datasets (Copernicus 30m/90m, NASADEM)

### Category 2: Use Recent Dates (Last 30-90 Days)
- **Sentinel-2 L2A** - Last 30 days
- **Landsat C2 L2** - Last 90 days
- **HLS (L30/S30)** - Last 30 days
- **Sentinel-1 (RTC/GRD)** - Last 30-90 days

### Category 3: Use January-June 2024 (MODIS with Processing Lag)
- **MODIS 09A1/09Q1** - Surface reflectance
- **MODIS 13A1/13Q1** - Vegetation indices (NDVI)
- **MODIS 15A2H** - Leaf area index
- **MODIS 17A2H** - Gross primary production
- **MODIS 17A3HGF** - Net primary production (yearly)
- **MODIS 14A1/14A2** - Fire detection
- **MODIS 11A1** - Land surface temperature

### Category 4: Seasonal Data (Winter 2024 for Snow)
- **MODIS 10A1** - Snow cover (use Jan-Mar 2024)

---

## 🎓 Pro Tips for Better Results

1. **For MODIS queries:** Always specify "early 2024", "spring 2024", or "January-June 2024"
2. **For optical imagery:** Mention "low cloud cover" or "clear sky" to filter cloudy scenes
3. **For elevation:** No need to specify dates - these are static datasets
4. **For NAIP:** Just request the imagery without dates - system returns latest available
5. **For near real-time data:** Use "recent", "latest", or "last month" in your query

---

## 🔍 Need Help?

If your query returns no results:
- **Check the date range** - Most issues are date-related
- **MODIS collections:** Use January-June 2024, not current dates
- **Elevation data:** Remove date filters
- **NAIP:** Remove date specifications
- **Optical imagery:** Try "recent" or "latest" instead of specific dates

---

**Last Updated:** October 9, 2025  
**Data Source:** Microsoft Planetary Computer STAC API  
**Validated Collections:** 21/21 (100% operational)
