# Earth Copilot Map Visualization Guide

## Overview

Earth Copilot uses **Azure Maps** with integrated satellite imagery rendering to display Earth observation data from Microsoft Planetary Computer. The React UI provides an interactive map experience with TypeScript components and modern web technologies.

## Map Architecture

```
User Query → React UI → Router Function → Microsoft Planetary Computer API
                ↓
MapView Component ← Azure Maps SDK ← STAC Data Visualization
```

## Current Map Implementation

### **Technology Stack**
- **Frontend**: React + TypeScript
- **Map Engine**: Azure Maps SDK v2
- **Styling**: CSS-in-JS with GlobalStyles
- **Data Source**: Microsoft Planetary Computer STAC API

### **Key Components**

#### **MapView Component** (`src/components/MapView.tsx`)
- **Purpose**: Main map rendering and data visualization
- **Features**: Azure Maps integration, STAC data overlay, interactive controls
- **Technology**: Azure Maps SDK with TypeScript integration

#### **Azure Maps Configuration**
```typescript
// Azure Maps SDK v2 integration
import * as atlas from 'azure-maps-control';

// Map initialization with authentication
const map = new atlas.Map('map-container', {
  authOptions: {
    authType: atlas.AuthenticationType.subscriptionKey,
    subscriptionKey: process.env.AZURE_MAPS_SUBSCRIPTION_KEY
  }
});
```

## Microsoft Planetary Computer Collections Supported

Earth Copilot supports **126+ collections** from Microsoft Planetary Computer across 10 major categories:

### 1. Optical/Multispectral Data 🛰️

#### **Sentinel-2 Level-2A** (`sentinel-2-l2a`)
### **Map Features**

#### **Interactive Controls**
- **Zoom**: Mouse wheel and touch gestures
- **Pan**: Click and drag navigation
- **Layer Toggle**: Satellite vs street view options
- **Fullscreen**: Expandable map view

#### **Data Visualization**
- **STAC Data Overlay**: Satellite imagery from Microsoft Planetary Computer
- **Feature Highlighting**: Interactive selection of data points
- **Popup Information**: Detailed metadata for selected features
- **Dynamic Rendering**: Real-time data loading and display

### **Data Integration**

#### **STAC Data Processing**
```typescript
// Example STAC data handling in MapView
const handleSTACData = (stacResults: any) => {
  if (stacResults.features && Array.isArray(stacResults.features)) {
    const features = stacResults.features;
    
    // Process each STAC feature for map display
    features.forEach(feature => {
      const bbox = feature.bbox;
      const geometry = feature.geometry;
      
      // Add to Azure Maps layer
      addFeatureToMap(feature);
    });
  }
};
```

## Supported Data Collections

### **Primary Data Sources**

#### **Sentinel-2 Level-2A** (`sentinel-2-l2a`)
- **Resolution**: 10m, 20m, 60m bands
- **Coverage**: Global land surfaces
- **Visualization**: True color RGB imagery
- **Best For**: Land use mapping, vegetation analysis

#### **Landsat Collection 2** (`landsat-c2-l2`)
- **Resolution**: 30m
- **Coverage**: Global since 1972
- **Visualization**: Natural color and false color composites
- **Best For**: Long-term change detection

#### **NAIP** (`naip`)
- **Resolution**: 0.6m - 1m
- **Coverage**: Continental United States
- **Visualization**: High-resolution aerial imagery
- **Best For**: Detailed land cover analysis

### **Specialized Collections**

#### **Sentinel-1 GRD** (`sentinel-1-grd`)
- **Type**: Synthetic Aperture Radar (SAR)
- **Resolution**: 10m
- **Coverage**: Global
- **Best For**: Weather-independent imaging, flood mapping

#### **NASADEM** (`nasadem`)
- **Resolution**: 30m
- **Coverage**: Global (60°N-56°S)
- **Titiler Rendering**: Hillshade, elevation color ramps, slope analysis
- **Best For**: Terrain analysis, watershed mapping
- **Visualization**: Terrain relief with elevation-based coloring

#### **ALOS DSM** (`alos-dem`)
- **Resolution**: 30m
- **Coverage**: Global
- **Titiler Rendering**: Digital surface model visualization
- **Best For**: 3D terrain modeling, flood risk assessment
- **Visualization**: Surface elevation including buildings and vegetation

### 5. Fire & Thermal Data 🔥

#### **MODIS Thermal Anomalies** (`modis-14A1-061`, `modis-14A2-061`)
- **Resolution**: 1km
- **Coverage**: Global
- **Titiler Rendering**: Fire hotspot overlays, thermal anomaly detection
- **Best For**: Wildfire monitoring, volcanic activity
- **Visualization**: Bright pixels indicating thermal anomalies

#### **VIIRS Fire** (`noaa-emergency-response`)
- **Resolution**: 375m
- **Coverage**: Global
- **Titiler Rendering**: Active fire detection, burn scar mapping
- **Best For**: Near real-time fire monitoring
- **Visualization**: High-confidence fire pixels as red/orange overlays

### 6. Ocean & Water Data 🌊

#### **GOES-16/17** (`goes-cmi`)
- **Resolution**: 0.5-2km
- **Coverage**: Americas, Pacific
- **Titiler Rendering**: Sea surface temperature, cloud imagery
- **Best For**: Ocean monitoring, weather tracking
- **Visualization**: Temperature gradients and cloud formations

#### **Landsat Water Extent** (`jrc-gsw`)
- **Resolution**: 30m
- **Coverage**: Global water bodies
- **Titiler Rendering**: Water occurrence frequency, seasonal water
- **Best For**: Water resource management, flood analysis
- **Visualization**: Blue intensity indicates water presence frequency

### 7. Snow & Ice Data ❄️

#### **MODIS Snow Cover** (`modis-10A1-061`)
- **Resolution**: 500m
- **Coverage**: Global
- **Titiler Rendering**: Snow cover percentage, snow/cloud discrimination
- **Best For**: Seasonal snow monitoring, climate studies
- **Visualization**: White/blue gradients indicating snow coverage

### 8. Vegetation & Agriculture 🌱

#### **MODIS NDVI** (`modis-13A1-061`)
- **Resolution**: 500m
- **Coverage**: Global
- **Titiler Rendering**: Vegetation index color scales (red=low, green=high)
- **Best For**: Crop monitoring, deforestation detection
- **Visualization**: Green intensity indicates vegetation health/density

#### **MODIS GPP** (`modis-17A2H-061`)
- **Resolution**: 500m
- **Coverage**: Global
- **Titiler Rendering**: Gross Primary Productivity color ramps
- **Best For**: Carbon cycle analysis, ecosystem productivity
- **Visualization**: Color gradients showing plant productivity levels

### 9. Atmospheric Data 🌫️

#### **MODIS Aerosol** (`modis-04A1-061`)
- **Resolution**: 1km
- **Coverage**: Global
- **Titiler Rendering**: Aerosol optical depth visualization
- **Best For**: Air quality monitoring, dust storm tracking
- **Visualization**: Color scales indicating atmospheric particle concentration

### 10. Specialized Agricultural Data 🚜

#### **USDA Crop Data Layer** (`usda-cdl`)
- **Resolution**: 30m
- **Coverage**: Continental United States
- **Titiler Rendering**: Categorical crop type mapping
- **Best For**: Agricultural land use analysis
- **Visualization**: Color-coded crop classifications

## Titiler Rendering Parameters

### Standard Band Combinations

#### **True Color (Natural)**
```
Red: Band 4 (Sentinel-2) / Band 4 (Landsat)
Green: Band 3 (Sentinel-2) / Band 3 (Landsat)  
Blue: Band 2 (Sentinel-2) / Band 2 (Landsat)
```

#### **False Color Infrared**
```
Red: Near-infrared band
Green: Red band
Blue: Green band
```

#### **SWIR False Color**
```
Red: SWIR band
Green: NIR band
Blue: Red band
```

### Color Scale Configurations

#### **Elevation Data**
- **Palette**: `terrain` or `elevation`
- **Range**: Auto-scaled to min/max elevation
- **Units**: Meters above sea level

#### **Temperature Data**
- **Palette**: `coolwarm` or `plasma`
- **Range**: Celsius or Kelvin
- **Scaling**: Linear or logarithmic

#### **Precipitation Data**
- **Palette**: `Blues` or `YlGnBu`
- **Range**: 0-500mm typically
- **Scaling**: Square root for better visualization

#### **Vegetation Indices (NDVI)**
- **Palette**: `RdYlGn` (Red-Yellow-Green)
- **Range**: -1 to +1
- **Threshold**: >0.2 indicates vegetation

#### **Fire/Thermal Data**
- **Palette**: `hot` or `Reds`
- **Range**: Brightness temperature
- **Threshold**: Confidence levels for fire detection

## Map Rendering Process

### 1. STAC Query Resolution
1. User query parsed for location, time, and data type
2. Router Function determines appropriate collections
3. STAC Function queries Microsoft Planetary Computer
4. Results filtered by cloud cover, date range, spatial overlap

### 2. Titiler Integration
1. STAC items converted to Titiler-compatible URLs
2. Band combinations selected based on collection type
3. Color scales and rendering parameters applied
4. Tiles generated dynamically for map zoom levels

### 3. Map Layer Composition
1. Base map (satellite or street view)
2. STAC imagery layers with transparency control
3. Interactive controls for band selection
4. Metadata overlays (dates, cloud cover, collection info)

## Visualization Types by Query Category

### **Disaster Impact Analysis**
- **Primary**: High-resolution optical (Sentinel-2, Landsat)
- **Secondary**: SAR for cloud penetration (Sentinel-1)
- **Temporal**: Before/during/after event comparison
- **Rendering**: True color with damage assessment overlays

### **Environmental Monitoring**
- **Vegetation**: MODIS NDVI, Sentinel-2 NIR
- **Water**: Landsat water extent, SAR water detection
- **Climate**: ERA5 temperature/precipitation
- **Rendering**: Index-based color scales

### **Agricultural Analysis**
- **Crop Health**: MODIS/Sentinel-2 vegetation indices
- **Crop Types**: USDA CDL categorical mapping
- **Seasonal**: Multi-temporal NDVI time series
- **Rendering**: Classification colors and health gradients

### **Urban Planning**
- **High-Resolution**: NAIP aerial imagery
- **Change Detection**: Landsat time series
- **Infrastructure**: Sentinel-2 urban indices
- **Rendering**: True color with urban feature enhancement

## Technical Implementation Details

### Titiler Endpoints
```
/cog/tiles/{z}/{x}/{y} - Standard tile endpoint
/cog/preview - Quick preview generation
/cog/info - Metadata and statistics
/cog/statistics - Band statistics for color scaling
```

### Dynamic Parameter Generation
- **Rescaling**: Auto-computed from image statistics
- **Color Maps**: Selected based on data type and collection
- **NoData**: Handled transparently for compositing
- **Resampling**: Bilinear for continuous data, nearest for categorical

### Performance Optimizations
- **COG Format**: Cloud Optimized GeoTIFFs for efficient streaming
- **Overviews**: Pre-computed pyramids for fast zoom levels
- **Caching**: Tile caching for repeated requests
- **Compression**: JPEG for visual data, PNG for precision

## Collection Categories Summary

| Category | Collections | Primary Use Cases | Titiler Strengths |
|----------|-------------|------------------|------------------|
| **Optical** | 25+ | Land monitoring, change detection | True color visualization, multi-spectral analysis |
| **SAR** | 8+ | All-weather monitoring, water detection | Texture analysis, coherence mapping |
| **Climate** | 15+ | Weather analysis, climate studies | Temporal animation, gradient visualization |
| **Elevation** | 6+ | Terrain analysis, flood modeling | Hillshade rendering, 3D visualization |
| **Fire** | 10+ | Wildfire monitoring, thermal detection | Hotspot overlay, confidence mapping |
| **Ocean** | 12+ | Marine monitoring, SST analysis | Temperature gradients, current visualization |
| **Snow/Ice** | 8+ | Seasonal monitoring, climate tracking | Binary snow maps, coverage percentages |
| **Vegetation** | 20+ | Crop monitoring, forest analysis | Index visualization, phenology tracking |
| **Atmosphere** | 15+ | Air quality, aerosol monitoring | Particle concentration mapping |
| **Agriculture** | 8+ | Crop classification, yield prediction | Categorical mapping, temporal profiles |

## Future Enhancements

### Planned Titiler Features
- **3D Visualization**: Integration with terrain models
- **Time Series Animation**: Temporal data visualization
- **Custom Algorithms**: On-the-fly index calculations
- **Multi-Collection Compositing**: Seamless data fusion

### Enhanced Analytical Capabilities
- **Statistical Overlays**: Real-time statistics on map regions
- **Change Detection Visualization**: Automated before/after analysis
- **Machine Learning Integration**: AI-powered feature detection
- **Export Capabilities**: High-resolution map exports

---

*This documentation covers the comprehensive mapping capabilities of Earth Copilot, enabling users to visualize and analyze diverse Earth observation data through intelligent query processing and dynamic tile rendering.*
