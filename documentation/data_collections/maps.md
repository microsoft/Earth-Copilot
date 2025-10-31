# Earth Copilot Maps Integration Guide

This guide covers both **map visualization** (Azure Maps) and **location resolution** (Google Maps) for Earth Copilot.

---

## Part 1: Azure Maps - Visualization & Rendering

### Overview

Earth Copilot uses **Azure Maps** with integrated satellite imagery rendering to display Earth observation data from Microsoft Planetary Computer. The React UI provides an interactive map experience with TypeScript components and modern web technologies.

### Map Architecture

```
User Query → React UI → Router Function → Microsoft Planetary Computer API
                ↓
MapView Component ← Azure Maps SDK ← STAC Data Visualization
```

### Current Map Implementation

#### **Technology Stack**
- **Frontend**: React + TypeScript
- **Map Engine**: Azure Maps SDK v2
- **Styling**: CSS-in-JS with GlobalStyles
- **Data Source**: Microsoft Planetary Computer STAC API

#### **Key Components**

**MapView Component** (`src/components/MapView.tsx`)
- **Purpose**: Main map rendering and data visualization
- **Features**: Azure Maps integration, STAC data overlay, interactive controls
- **Technology**: Azure Maps SDK with TypeScript integration

**Azure Maps Configuration**
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

### Map Features

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

### Data Integration

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

### Supported Data Collections

#### **Primary Data Sources**

**Sentinel-2 Level-2A** (`sentinel-2-l2a`)
- **Resolution**: 10m, 20m, 60m bands
- **Coverage**: Global land surfaces
- **Visualization**: True color RGB imagery
- **Best For**: Land use mapping, vegetation analysis

**Landsat Collection 2** (`landsat-c2-l2`)
- **Resolution**: 30m
- **Coverage**: Global since 1972
- **Visualization**: Natural color and false color composites
- **Best For**: Long-term change detection

**NAIP** (`naip`)
- **Resolution**: 0.6m - 1m
- **Coverage**: Continental United States
- **Visualization**: High-resolution aerial imagery
- **Best For**: Detailed land cover analysis

#### **Specialized Collections**

**Sentinel-1 GRD** (`sentinel-1-grd`)
- **Type**: Synthetic Aperture Radar (SAR)
- **Resolution**: 10m
- **Coverage**: Global
- **Best For**: Weather-independent imaging, flood mapping

**NASADEM** (`nasadem`)
- **Resolution**: 30m
- **Coverage**: Global (60°N-56°S)
- **Titiler Rendering**: Hillshade, elevation color ramps, slope analysis
- **Best For**: Terrain analysis, watershed mapping
- **Visualization**: Terrain relief with elevation-based coloring

**ALOS DSM** (`alos-dem`)
- **Resolution**: 30m
- **Coverage**: Global
- **Titiler Rendering**: Digital surface model visualization
- **Best For**: 3D terrain modeling, flood risk assessment
- **Visualization**: Surface elevation including buildings and vegetation

**MODIS Thermal Anomalies** (`modis-14A1-061`, `modis-14A2-061`)
- **Resolution**: 1km
- **Coverage**: Global
- **Titiler Rendering**: Fire hotspot overlays, thermal anomaly detection
- **Best For**: Wildfire monitoring, volcanic activity
- **Visualization**: Bright pixels indicating thermal anomalies

**VIIRS Fire** (`noaa-emergency-response`)
- **Resolution**: 375m
- **Coverage**: Global
- **Titiler Rendering**: Active fire detection, burn scar mapping
- **Best For**: Near real-time fire monitoring
- **Visualization**: High-confidence fire pixels as red/orange overlays

### Titiler Rendering Parameters

#### **Standard Band Combinations**

**True Color (Natural)**
```
Red: Band 4 (Sentinel-2) / Band 4 (Landsat)
Green: Band 3 (Sentinel-2) / Band 3 (Landsat)  
Blue: Band 2 (Sentinel-2) / Band 2 (Landsat)
```

**False Color Infrared**
```
Red: Near-infrared band
Green: Red band
Blue: Green band
```

**SWIR False Color**
```
Red: SWIR band
Green: NIR band
Blue: Red band
```

#### **Color Scale Configurations**

**Elevation Data**
- **Palette**: `terrain` or `elevation`
- **Range**: Auto-scaled to min/max elevation
- **Units**: Meters above sea level

**Temperature Data**
- **Palette**: `coolwarm` or `plasma`
- **Range**: Celsius or Kelvin
- **Scaling**: Linear or logarithmic

**Precipitation Data**
- **Palette**: `Blues` or `YlGnBu`
- **Range**: 0-500mm typically
- **Scaling**: Square root for better visualization

**Vegetation Indices (NDVI)**
- **Palette**: `RdYlGn` (Red-Yellow-Green)
- **Range**: -1 to +1
- **Threshold**: >0.2 indicates vegetation

**Fire/Thermal Data**
- **Palette**: `hot` or `Reds`
- **Range**: Brightness temperature
- **Threshold**: Confidence levels for fire detection

### Map Rendering Process

#### 1. STAC Query Resolution
1. User query parsed for location, time, and data type
2. Router Function determines appropriate collections
3. STAC Function queries Microsoft Planetary Computer
4. Results filtered by cloud cover, date range, spatial overlap

#### 2. Titiler Integration
1. STAC items converted to Titiler-compatible URLs
2. Band combinations selected based on collection type
3. Color scales and rendering parameters applied
4. Tiles generated dynamically for map zoom levels

#### 3. Map Layer Composition
1. Base map (satellite or street view)
2. STAC imagery layers with transparency control
3. Interactive controls for band selection
4. Metadata overlays (dates, cloud cover, collection info)

### Visualization Types by Query Category

**Disaster Impact Analysis**
- **Primary**: High-resolution optical (Sentinel-2, Landsat)
- **Secondary**: SAR for cloud penetration (Sentinel-1)
- **Temporal**: Before/during/after event comparison
- **Rendering**: True color with damage assessment overlays

**Environmental Monitoring**
- **Vegetation**: MODIS NDVI, Sentinel-2 NIR
- **Water**: Landsat water extent, SAR water detection
- **Climate**: ERA5 temperature/precipitation
- **Rendering**: Index-based color scales

**Agricultural Analysis**
- **Crop Health**: MODIS/Sentinel-2 vegetation indices
- **Crop Types**: USDA CDL categorical mapping
- **Seasonal**: Multi-temporal NDVI time series
- **Rendering**: Classification colors and health gradients

**Urban Planning**
- **High-Resolution**: NAIP aerial imagery
- **Change Detection**: Landsat time series
- **Infrastructure**: Sentinel-2 urban indices
- **Rendering**: True color with urban feature enhancement

### Technical Implementation Details

**Titiler Endpoints**
```
/cog/tiles/{z}/{x}/{y} - Standard tile endpoint
/cog/preview - Quick preview generation
/cog/info - Metadata and statistics
/cog/statistics - Band statistics for color scaling
```

**Dynamic Parameter Generation**
- **Rescaling**: Auto-computed from image statistics
- **Color Maps**: Selected based on data type and collection
- **NoData**: Handled transparently for compositing
- **Resampling**: Bilinear for continuous data, nearest for categorical

**Performance Optimizations**
- **COG Format**: Cloud Optimized GeoTIFFs for efficient streaming
- **Overviews**: Pre-computed pyramids for fast zoom levels
- **Caching**: Tile caching for repeated requests
- **Compression**: JPEG for visual data, PNG for precision

---

## Part 2: Google Maps - Location Resolution & Geocoding

### Why Google Maps?

The Earth Copilot location resolver uses **Google Maps Geocoding API** as the primary geocoding service because:

✅ **Most Accurate**: Industry standard for geocoding accuracy  
✅ **Best Disambiguation**: Correctly identifies NYC vs small towns named "NYC"  
✅ **Smart Prioritization**: Automatically prioritizes by population/prominence  
✅ **Global Coverage**: Recognizes virtually every location worldwide  
✅ **Comprehensive**: Handles cities, landmarks, natural features, neighborhoods, regions  

### Setup Instructions

#### Step 1: Get Google Maps API Key

1. Go to [Google Cloud Console](https://console.cloud.google.com/)
2. Create a new project or select existing project
3. Enable **Geocoding API**:
   - Navigate to "APIs & Services" > "Library"
   - Search for "Geocoding API"
   - Click "Enable"
4. Create API Key:
   - Go to "APIs & Services" > "Credentials"
   - Click "Create Credentials" > "API Key"
   - Copy the generated API key

#### Step 2: Secure the API Key (Recommended)

1. Click "Restrict Key" for the newly created key
2. Under "API restrictions":
   - Select "Restrict key"
   - Check only: **Geocoding API**
3. Under "Application restrictions" (optional):
   - Select "HTTP referrers" or "IP addresses"
   - Add your server's IP or domain

#### Step 3: Add to Environment Variables

Add the API key to your environment:

**Local Development (.env file):**
```bash
GOOGLE_MAPS_API_KEY=your_api_key_here
```

**Azure Container App:**
```powershell
az containerapp update `
  --name earthcopilot-api `
  --resource-group earthcopilot-rg `
  --set-env-vars "GOOGLE_MAPS_API_KEY=your_api_key_here"
```

#### Step 4: Verify Setup

Test the location resolver:

```powershell
$query = @{ query = "Show me satellite images of NYC" } | ConvertTo-Json
$response = Invoke-RestMethod -Uri "https://your-api-url/api/query" -Method Post -Body $query -ContentType "application/json"

# Check logs for "Google Maps resolved"
```

### Pricing

**Google Maps Geocoding API Pricing** (as of 2024):
- **$5.00 per 1,000 requests**
- **$200 free credit per month** (~40,000 free requests/month)
- Very cost-effective for typical usage

**Cost Optimization:**
- ✅ Results are cached (reduces API calls for repeated locations)
- ✅ Top 30 cities respond instantly (no API call)
- ✅ Only called when needed (after local lookup fails)

#### Expected Costs for Earth Copilot:

**Scenario 1: Low Traffic** (1,000 unique locations/month)
- Cost: **$0** (within free tier)

**Scenario 2: Medium Traffic** (10,000 unique locations/month)
- Cost: **$0** (within free tier)

**Scenario 3: High Traffic** (100,000 unique locations/month)
- Cost: **~$300/month** (100K × $0.005)

**Scenario 4: Very High Traffic** (1M unique locations/month)
- Cost: **~$5,000/month**
- Consider implementing aggressive caching or rate limiting

### Fallback Strategy

The location resolver uses a **waterfall approach**:

1. **Instant Response** (0ms): Check if location is in top 30 cities → return immediately
2. **Google Maps** (100-300ms): Most accurate, handles 95%+ of queries
3. **Mapbox** (100-300ms): Excellent for geographic features (mountains, parks)
4. **Azure Maps** (100-300ms): Enterprise integration, decent coverage
5. **Azure OpenAI** (500-1000ms): AI-powered understanding for complex queries

If Google Maps key is not configured, system automatically falls back to other services.

### Testing Without Google Maps

If you don't want to set up Google Maps immediately:

1. The system will work with existing APIs (Mapbox, Azure Maps)
2. Top 30 cities (NYC, LA, Chicago, etc.) will still work perfectly
3. Less common locations may have lower accuracy

### Monitoring

Check logs for location resolution:

```
🌟 Google Maps resolved 'NYC' to: New York, NY, USA
✅ Bbox: [-74.02, 40.70, -73.91, 40.88]
```

If Google Maps fails, you'll see:
```
⚠️ Google Maps timeout for: [location]
🔄 Trying next strategy: Mapbox
```

### Security Best Practices

1. **Never commit API keys to git**
2. **Use environment variables** for all keys
3. **Restrict API key** to Geocoding API only
4. **Monitor usage** in Google Cloud Console
5. **Set up billing alerts** to avoid unexpected charges
6. **Rotate keys periodically** (every 6-12 months)

### Support

If you encounter issues:
- Check that API is enabled in Google Cloud Console
- Verify API key is correctly added to environment
- Check billing is enabled (required even for free tier)
- Review logs for error messages
- Ensure network allows outbound HTTPS to googleapis.com

---

## Summary

**Azure Maps**: Used for map visualization, STAC data rendering, and interactive map controls in the React UI.

**Google Maps**: Used for geocoding and location resolution to convert user queries ("NYC", "Seattle") into precise geographic coordinates.

Both services work together to provide a comprehensive mapping and location intelligence solution for Earth Copilot.

---

*Last Updated: October 29, 2025*
