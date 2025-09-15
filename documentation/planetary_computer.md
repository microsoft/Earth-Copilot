# Microsoft Planetary Computer (MPC) - Data Catalog & API Reference

This document provides comprehensive information about Microsoft Planetary Computer: what it offers, available data types, and how to query it effectively for Earth science applications.

## 🌍 What is Microsoft Planetary Computer?

Microsoft Planetary Computer is a platform that combines **petabytes of Earth observation data** with **cloud computing power** to accelerate environmental sustainability and Earth science research. It provides:

- **Free access** to massive geospatial datasets hosted on Azure
- **STAC-compliant APIs** for standardized data discovery and access  
- **Open-source tools** and applications for environmental analysis
- **Global-scale** Earth monitoring capabilities

### Core Components
1. **Data Catalog**: Petabytes of Earth systems data
2. **APIs**: STAC-compliant search and access APIs
3. **Applications**: Partner-built environmental sustainability tools

## 📊 Comprehensive Data Catalog Analysis

Based on analysis of the MPC repository structure and official documentation, Microsoft Planetary Computer offers these comprehensive data categories:

### 🛰️ **1. Optical Satellite Imagery**
**Primary Collections:**
- `sentinel-2-l2a` - Sentinel-2 Level-2A (10-60m resolution, atmospheric correction applied)
- `landsat-c2-l2` - Landsat Collection 2 Level-2 (30m resolution, surface reflectance)
- `naip` - National Agriculture Imagery Program (0.6-1m resolution, US coverage)
- `hls-l30` / `hls-s30` - Harmonized Landsat Sentinel-2 (30m, consistent processing)

**Use Cases:** Land cover mapping, vegetation monitoring, agriculture, urban planning, change detection

### 📡 **2. SAR (Synthetic Aperture Radar)**
**Primary Collections:**
- `sentinel-1-grd` - Ground Range Detected products (10-40m resolution)
- `sentinel-1-rtc` - Radiometric Terrain Corrected (enhanced for terrain analysis)

**Use Cases:** All-weather imaging, flood monitoring, forest change, land deformation, ice monitoring

### 🌡️ **3. Climate & Weather Data**
**Primary Collections:**
- `era5-pds` - ERA5 reanalysis data (hourly, 31km resolution, 1940-present)
- `era5-land` - ERA5-Land high-resolution reanalysis (hourly, 9km, land surfaces)
- `daymet-daily-na` - Daily surface weather data (1km, North America, 1980-present)
- `gridmet` - Gridded meteorological data (4km, Western US, 1979-present)
- `gpm-imerg-hhr` - Global precipitation measurement (0.1°, 30-minute)

**Use Cases:** Climate analysis, weather pattern studies, precipitation monitoring, extreme event analysis

### 🏔️ **4. Elevation & Topography**
**Primary Collections:**
- `cop-dem-glo-30` - Copernicus DEM Global 30m (worldwide coverage)
- `cop-dem-glo-90` - Copernicus DEM Global 90m (lower resolution)
- `nasadem` - NASA DEM (30m, near-global coverage, void-filled)
- `alos-dem` - ALOS World 3D (30m, high-accuracy global DEM)

**Use Cases:** Terrain analysis, watershed modeling, slope calculations, viewshed analysis, flood modeling

### 🔥 **5. Fire & Environmental Monitoring**
**Primary Collections:**
- `modis-mcd64a1-061` - MODIS Burned Area Product (500m, monthly)
- `modis-mcd14ml` - MODIS Thermal Anomalies (1km, daily fire detection)
- `viirs-thermal-anomalies-nrt` - VIIRS active fire detection (375m, near real-time)
- `sentinel-5p-l2` - Air quality monitoring (NO2, SO2, CO, formaldehyde, ozone)
- `omi-so2-pds` - Ozone Monitoring Instrument SO2 data

**Use Cases:** Wildfire monitoring, burn severity assessment, air quality analysis, emission tracking

### 🌊 **6. Ocean & Water Data**
**Primary Collections:**
- `modis-oc` - MODIS Ocean Color (chlorophyll-a, primary productivity, 1km)
- `modis-sst` - MODIS Sea Surface Temperature (1-4km, daily/8-day/monthly)
- `viirs-oc` - VIIRS Ocean Color products
- `viirs-sst` - VIIRS Sea Surface Temperature

**Use Cases:** Ocean productivity monitoring, marine ecosystem health, coastal water quality, fisheries management

### ❄️ **7. Snow & Ice Monitoring**
**Primary Collections:**
- `modis-10a1-061` - MODIS Snow Cover Daily (500m resolution)
- `modis-10a2-061` - MODIS Snow Cover 8-Day Composite  
- `viirs-snow-cover` - VIIRS Snow Cover products (375m)

**Use Cases:** Snowpack monitoring, seasonal snow analysis, water resource management, climate studies

### 🌿 **8. Vegetation & Land Cover**
**Primary Collections:**
- `esa-worldcover` - ESA WorldCover 10m (global land cover map, 11 classes)
- `io-lulc-annual-v02` - Impact Observatory Annual Land Use/Land Cover (10m, AI-generated)
- `modis-13q1-061` - MODIS Vegetation Indices 16-Day (NDVI, EVI, 250m)
- `modis-16a2-061` - MODIS Evapotranspiration 8-Day (500m)
- `modis-09q1-061` - MODIS Surface Reflectance 8-Day (250m)

**Use Cases:** Land cover classification, vegetation health monitoring, deforestation tracking, agricultural assessment

### 🌬️ **9. Atmospheric & Air Quality**
**Primary Collections:**
- `sentinel-5p-l2` - Tropospheric monitoring (NO2, SO2, CO, CH4, aerosols)
- `tropomi-co` - Carbon monoxide concentrations
- `tropomi-no2` - Nitrogen dioxide concentrations  
- `tropomi-so2` - Sulfur dioxide concentrations

**Use Cases:** Air pollution monitoring, emission source identification, atmospheric chemistry studies

### 🌾 **10. Agriculture & Food Security**
**Primary Collections:**
- `usda-cdl` - USDA Cropland Data Layer (30m, US crop types)
- `modis-mcd12q1-061` - MODIS Land Cover Type (500m, annual)
- Agricultural applications through Landsat and Sentinel-2 data

**Use Cases:** Crop type mapping, yield estimation, agricultural monitoring, food security assessment

## 🔍 STAC API Query Format Reference

### **API Endpoint**
```
POST https://planetarycomputer.microsoft.com/api/stac/v1/search
```

### **Required Request Format**

```json
{
  "collections": ["collection-id1", "collection-id2"],
  "intersects": {
    "type": "Polygon",
    "coordinates": [[[lon1, lat1], [lon2, lat2], [lon3, lat3], [lon4, lat4], [lon1, lat1]]]
  },
  "datetime": "YYYY-MM-DD/YYYY-MM-DD",
  "query": {
    "property_name": {"operator": value}
  },
  "limit": 50,
  "sortby": [{"field": "datetime", "direction": "desc"}]
}
```

### **Field Specifications**

#### 1. `collections` (Required)
- **Type**: Array of strings
- **Description**: List of collection IDs to search within
- **Example**: `["sentinel-2-l2a", "landsat-c2-l2"]`
- **Validation**: Must be valid collection IDs from MPC catalog

#### 2. `intersects` (Spatial Filter)
- **Type**: GeoJSON Geometry object
- **Description**: Spatial area of interest
- **Format**: Must follow GeoJSON specification exactly
- **Example Polygon**:
  ```json
  {
    "type": "Polygon",
    "coordinates": [[
      [-122.2751, 47.5469],
      [-121.9613, 47.5469], 
      [-121.9613, 47.7458],
      [-122.2751, 47.7458],
      [-122.2751, 47.5469]
    ]]
  }
  ```

#### 3. `datetime` (Temporal Filter)
- **Type**: String
- **Format**: RFC 3339 datetime or interval
- **Examples**:
  - Single date: `"2020-12-01"`
  - Date range: `"2020-12-01/2020-12-31"`
  - Open-ended: `"2020-12-01/.."` or `"../2020-12-31"`

#### 4. `query` (Optional Property Filters)
- **Type**: Object
- **Description**: Property-based filtering using CQL2-JSON
- **Common Examples**:
  ```json
  {
    "eo:cloud_cover": {"lt": 20},
    "sat:orbit_state": {"eq": "descending"},
    "daymet:variable": {"in": ["prcp", "tmax", "tmin"]}
  }
  ```

#### 5. `limit` (Optional)
- **Type**: Integer
- **Range**: 1-1000 (default: 250 in MPC)
- **Description**: Maximum number of items to return

#### 6. `sortby` (Optional)
- **Type**: Array of sort objects
- **Format**: `[{"field": "field_name", "direction": "asc|desc"}]`
- **Example**: `[{"field": "datetime", "direction": "desc"}]`

## 🎯 Collection-Specific Query Patterns

### **Optical Collections (Sentinel-2, Landsat, NAIP)**
```json
{
  "collections": ["sentinel-2-l2a"],
  "query": {
    "eo:cloud_cover": {"lt": 20}
  },
  "sortby": [{"field": "eo:cloud_cover", "direction": "asc"}]
}
```

### **SAR Collections (Sentinel-1)**
```json
{
  "collections": ["sentinel-1-grd"],
  "query": {
    "sat:orbit_state": {"eq": "descending"}
  },
  "sortby": [{"field": "datetime", "direction": "desc"}]
}
```

### **Weather/Climate Collections**
```json
{
  "collections": ["daymet-daily-na"],
  "query": {
    "daymet:variable": {"in": ["prcp", "tmax", "tmin"]}
  }
}
```

## ✅ Validated Example Request

This exact request has been tested and confirmed working with MPC STAC API:

```json
{
  "collections": ["sentinel-2-l2a"],
  "intersects": {
    "type": "Polygon",
    "coordinates": [[
      [-122.2751, 47.5469],
      [-121.9613, 47.5469],
      [-121.9613, 47.7458],
      [-122.2751, 47.7458],
      [-122.2751, 47.5469]
    ]]
  },
  "datetime": "2020-12-01/2020-12-31",
  "query": {
    "eo:cloud_cover": {"lt": 20}
  },
  "limit": 1,
  "sortby": [{"field": "datetime", "direction": "desc"}]
}
```

**Test Result**: ✅ SUCCESS - Returns valid STAC FeatureCollection

## 🏷️ Key Collections by Domain

### **Popular Collections for Common Use Cases:**
- **Optical Satellite**: `sentinel-2-l2a`, `landsat-c2-l2`, `naip`
- **SAR/All-Weather**: `sentinel-1-grd`, `sentinel-1-rtc`  
- **Elevation/Terrain**: `cop-dem-glo-30`, `nasadem`, `alos-dem`
- **Weather/Climate**: `daymet-daily-na`, `gridmet`, `era5-pds`
- **Land Cover**: `io-lulc-annual-v02`, `esa-worldcover`
- **Fire Detection**: `modis-mcd64a1-061`, `modis-mcd14ml`
- **Ocean Data**: `modis-oc`, `modis-sst`
- **Snow Monitoring**: `modis-10a1-061`, `viirs-snow-cover`
- **Air Quality**: `sentinel-5p-l2`, `tropomi-no2`
- **Precipitation**: `gpm-imerg-hhr`, `daymet-daily-na`

## 🚀 Earth Copilot Integration

### **Collection Mapping Strategy**
Our system maps user intents to appropriate MPC collections using:

1. **Domain-based routing**: Wildfire → fire collections, Flooding → SAR collections
2. **Collection expansion**: Primary collection → related collections for comprehensive coverage
3. **Auto-relaxation**: Fallback strategies when initial queries return insufficient results

### **Implementation Requirements**
- All requests MUST include `collections` array
- Spatial filter MUST use `intersects` with valid GeoJSON
- Temporal filter MUST use `datetime` in RFC 3339 format
- Query filters MUST match collection property schemas

## 📚 Additional Resources

- **Official MPC Documentation**: https://planetarycomputer.microsoft.com/docs/
- **Data Catalog Browser**: https://planetarycomputer.microsoft.com/catalog
- **API Specification**: https://planetarycomputer.microsoft.com/api/stac/v1/docs
- **Example Notebooks**: https://github.com/microsoft/PlanetaryComputerExamples
- **STAC Specification**: https://stacspec.org/

---

**Document Version**: 2.0  
**Last Updated**: September 5, 2025  
**Validated Against**: Microsoft Planetary Computer STAC API v1  
**Earth Copilot Compatibility**: Current development branch
