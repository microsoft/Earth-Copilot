# Map Tiles in Earth Copilot

## Quick Overview

Earth Copilot uses **two types of tiles** for geospatial visualization:

| Type | What It Is | Best For | Can Calculate? |
|------|-----------|----------|----------------|
| **Raster** | Pre-rendered images (PNG/JPEG) | Satellite imagery, elevation, photos | ✅ Yes (on source data before rendering) |
| **Vector** | Geometric shapes (lines, polygons) | Roads, boundaries, labels | ✅ Yes (on geometry and attributes) |

---

## 🗺️ Raster Tiles

**Simple Definition**: Picture tiles showing satellite imagery or terrain.

**Key Points**:
- Pre-rendered images at fixed zoom levels
- File size: 20-100 KB per tile
- Photo-realistic but fixed styling
- Used for: Sentinel-2 imagery, Landsat-8, elevation maps, NDVI overlays

**Earth Copilot Examples**:
- Satellite RGB imagery of forests, cities, oceans
- Elevation/hillshade maps from Copernicus DEM
- NDVI vegetation health overlays
- Fire detection from MODIS

---

## 📐 Vector Tiles

**Simple Definition**: Geometric shapes with attributes that render on your device.

**Key Points**:
- Compressed geometry data (points, lines, polygons)
- File size: 10-50 KB per tile
- Dynamic styling and smooth zoom
- Used for: Roads, boundaries, labels, interactive features

**Earth Copilot Examples**:
- Azure Maps base map (streets, cities, borders)
- Search result bounding boxes
- User-drawn analysis areas
- Satellite scene footprints from STAC

---

## 🔢 Calculations on Tiles

### Raster Tiles (Satellite Imagery & Elevation)

**Can you calculate on rendered PNG tiles?** ❌ **No** - pixel colors don't contain original data values.

**Can you calculate on source data?** ✅ **YES** - STAC assets link to raw COG files with original band values.

#### What You Can Calculate on Raster Data:

**1. Vegetation Indices**
- **NDVI (Normalized Difference Vegetation Index)**
  ```
  NDVI = (NIR - Red) / (NIR + Red)
  Range: -1 to +1 (higher = more vegetation)
  ```
  - **Use Case**: Crop health monitoring, deforestation detection
  - **Data**: Sentinel-2 bands B08 (NIR) and B04 (Red)

- **EVI (Enhanced Vegetation Index)**
  ```
  EVI = 2.5 × (NIR - Red) / (NIR + 6×Red - 7.5×Blue + 1)
  ```
  - **Use Case**: Better for dense vegetation areas
  - **Data**: Sentinel-2 bands B08, B04, B02

- **NDMI (Normalized Difference Moisture Index)**
  ```
  NDMI = (NIR - SWIR) / (NIR + SWIR)
  ```
  - **Use Case**: Vegetation water stress, drought monitoring
  - **Data**: Sentinel-2 bands B08 (NIR) and B11 (SWIR)

**2. Water Indices**
- **NDWI (Normalized Difference Water Index)**
  ```
  NDWI = (Green - NIR) / (Green + NIR)
  Range: -1 to +1 (higher = water bodies)
  ```
  - **Use Case**: Flood mapping, water body detection
  - **Data**: Sentinel-2 bands B03 (Green) and B08 (NIR)

- **MNDWI (Modified NDWI)**
  ```
  MNDWI = (Green - SWIR) / (Green + SWIR)
  ```
  - **Use Case**: Better urban water detection
  - **Data**: Sentinel-2 bands B03 and B11

**3. Built-Up & Urban Indices**
- **NDBI (Normalized Difference Built-up Index)**
  ```
  NDBI = (SWIR - NIR) / (SWIR + NIR)
  ```
  - **Use Case**: Urban expansion monitoring, building detection
  - **Data**: Sentinel-2 bands B11 (SWIR) and B08 (NIR)

**4. Burn & Fire Detection**
- **NBR (Normalized Burn Ratio)**
  ```
  NBR = (NIR - SWIR) / (NIR + SWIR)
  ```
  - **Use Case**: Pre/post fire damage assessment
  - **Data**: Sentinel-2 bands B08 and B12

- **dNBR (Difference NBR)**
  ```
  dNBR = NBR_prefire - NBR_postfire
  ```
  - **Use Case**: Burn severity classification
  - **Data**: Two time periods of NBR

**5. Snow & Ice**
- **NDSI (Normalized Difference Snow Index)**
  ```
  NDSI = (Green - SWIR) / (Green + SWIR)
  Range: -1 to +1 (higher = snow/ice)
  ```
  - **Use Case**: Snow cover mapping, glacier monitoring
  - **Data**: Sentinel-2 bands B03 and B11

**6. Terrain Analysis (from Elevation Data)**
- **Slope Calculation**
  ```
  Slope = arctan(√(dz/dx)² + (dz/dy)²) × (180/π)
  Result: Degrees (0° = flat, 90° = vertical)
  ```
  - **Use Case**: Mobility analysis, landslide risk assessment
  - **Data**: Copernicus DEM

- **Aspect (Direction of Slope)**
  ```
  Aspect = arctan2(dz/dy, -dz/dx) × (180/π)
  Result: Degrees (0° = North, 90° = East, 180° = South, 270° = West)
  ```
  - **Use Case**: Solar exposure, watershed analysis
  - **Data**: Copernicus DEM

- **Hillshade (3D Visualization)**
  ```
  Hillshade = 255 × cos(zenith) × cos(slope) + sin(zenith) × sin(slope) × cos(azimuth - aspect)
  ```
  - **Use Case**: Terrain visualization, topographic maps
  - **Data**: Copernicus DEM

- **Elevation Change Detection**
  ```
  Change = DEM_time2 - DEM_time1
  ```
  - **Use Case**: Landslide detection, coastal erosion, construction monitoring
  - **Data**: Multi-temporal DEMs

**7. Temperature & Thermal**
- **Land Surface Temperature (LST)**
  ```
  LST = BT / (1 + (λ × BT / ρ) × ln(ε))
  Where: BT = Brightness Temperature, λ = wavelength, ε = emissivity
  ```
  - **Use Case**: Urban heat island analysis, drought monitoring
  - **Data**: Landsat-8 thermal bands B10/B11

**8. Cloud Masking**
- **Cloud Probability**
  ```
  Cloud_Mask = Threshold(Blue, Cirrus, SCL)
  ```
  - **Use Case**: Filter out cloudy pixels for analysis
  - **Data**: Sentinel-2 B02 (Blue), B10 (Cirrus), Scene Classification Layer

#### How Earth Copilot Does Calculations:

```
User: "Show NDVI for California farmland"
   ↓
Backend: Query STAC for Sentinel-2 scenes (B04 Red, B08 NIR)
   ↓
TiTiler: Calculate (B08 - B04) / (B08 + B04) on COG files
   ↓
TiTiler: Apply colormap (red=low vegetation, green=high)
   ↓
Frontend: Display as raster PNG tiles
```

**Key Point**: Calculations happen **server-side on raw COG data** before rendering to PNG tiles.

---

### Vector Tiles (Geometry & Boundaries)

**Can you calculate on vector tiles?** ✅ **YES** - geometry and attributes are preserved.

#### What You Can Calculate on Vector Data:

**1. Spatial Measurements**
- **Area Calculation**
  ```javascript
  area = polygon.getArea() // Square meters
  ```
  - **Use Case**: Agricultural field size, deforestation area
  - **Data**: Building footprints, land parcels, analysis polygons

- **Perimeter/Length**
  ```javascript
  perimeter = polygon.getPerimeter() // Meters
  length = linestring.getLength()    // Meters
  ```
  - **Use Case**: Fence requirements, road distance
  - **Data**: Property boundaries, road networks

- **Distance Between Points**
  ```javascript
  distance = point1.distanceTo(point2) // Meters
  ```
  - **Use Case**: Asset proximity, evacuation radius
  - **Data**: Facility locations, incident points

**2. Spatial Relationships**
- **Point-in-Polygon**
  ```javascript
  isInside = polygon.contains(point)
  ```
  - **Use Case**: "Is this facility in the flood zone?"
  - **Data**: Administrative boundaries, hazard zones

- **Polygon Intersection**
  ```javascript
  overlap = polygon1.intersection(polygon2)
  overlapArea = overlap.getArea()
  ```
  - **Use Case**: Land use overlap, conflicting claims
  - **Data**: Property parcels, protected areas

- **Buffer/Proximity**
  ```javascript
  buffer = point.buffer(1000) // 1km radius
  ```
  - **Use Case**: 1km evacuation zone around a facility
  - **Data**: Critical infrastructure, incident locations

**3. Attribute Calculations**
- **Population Density**
  ```javascript
  density = feature.properties.population / feature.getArea()
  ```
  - **Use Case**: Urban planning, resource allocation
  - **Data**: Census boundaries with population attributes

- **Aggregation (Sum, Average)**
  ```javascript
  totalPop = features.reduce((sum, f) => sum + f.properties.pop, 0)
  avgIncome = totalIncome / features.length
  ```
  - **Use Case**: Regional statistics, demographic analysis
  - **Data**: Administrative boundaries with socioeconomic data

**4. Network Analysis (on Road Vectors)**
- **Shortest Path**
  ```javascript
  route = graph.shortestPath(startNode, endNode)
  ```
  - **Use Case**: Optimal routing, logistics planning
  - **Data**: Road network with speed/capacity attributes

- **Service Area**
  ```javascript
  reachable = graph.serviceArea(startPoint, 15) // 15-minute drive
  ```
  - **Use Case**: Hospital coverage, delivery zones
  - **Data**: Road network with travel times

**5. Change Detection (Multi-Temporal Vectors)**
- **Building Growth**
  ```javascript
  newBuildings = buildings2024.filter(b => 
    !buildings2020.some(old => old.intersects(b))
  )
  ```
  - **Use Case**: Urban expansion monitoring
  - **Data**: Building footprints from different years

- **Deforestation Area**
  ```javascript
  lost = forest2020.difference(forest2024).getArea()
  ```
  - **Use Case**: Forest loss quantification
  - **Data**: Forest boundary polygons

**6. Geometric Transformations**
- **Centroid**
  ```javascript
  center = polygon.getCentroid()
  ```
  - **Use Case**: Label placement, center of mass
  - **Data**: Any polygon features

- **Simplification**
  ```javascript
  simplified = linestring.simplify(tolerance)
  ```
  - **Use Case**: Reduce vertices for performance
  - **Data**: Complex coastlines, boundaries

- **Convex Hull**
  ```javascript
  hull = points.convexHull()
  ```
  - **Use Case**: Minimal bounding area for scattered points
  - **Data**: Facility clusters, incident locations

#### Earth Copilot Vector Examples:

```javascript
// Example 1: Count buildings in flood zone
const floodZone = getUserDrawnPolygon()
const buildings = getVectorTileFeatures('buildings')
const affected = buildings.filter(b => floodZone.contains(b.geometry))
console.log(`${affected.length} buildings at risk`)

// Example 2: Calculate area of agricultural parcels
const parcels = getVectorTileFeatures('land-parcels')
const totalArea = parcels
  .filter(p => p.properties.use === 'agriculture')
  .reduce((sum, p) => sum + p.geometry.getArea(), 0)
console.log(`Total farmland: ${totalArea / 1e6} km²`)

// Example 3: Find facilities within 5km of incident
const incident = new Point(lon, lat)
const facilities = getVectorTileFeatures('infrastructure')
const nearby = facilities.filter(f => 
  incident.distanceTo(f.geometry) <= 5000
)
```

---

## 🧮 STAC: Metadata + Data Links

**STAC = Catalog (JSON metadata, not the data itself)**

- **Metadata**: Scene boundaries, dates, cloud cover, sensor info
- **Asset Links**: URLs to actual data files (mostly COG raster files)

**STAC Asset Types**:
- ✅ **90% Raster**: COG files with spectral bands (B04, B08, etc.)
- ✅ **10% Vector**: Occasionally GeoJSON boundaries or shapefiles

**Calculation Flow**:
```
STAC Catalog → COG Assets → TiTiler Calculations → PNG Tiles → Map Display
(metadata)     (raw data)   (NDVI, slope, etc.)   (visual)    (frontend)
```

---

## 💡 Key Takeaways

1. **Both tile types support calculations** - just at different stages:
   - **Raster**: Calculate on source COG data before rendering (NDVI, slope, LST)
   - **Vector**: Calculate on geometry/attributes client-side (area, distance, intersects)

2. **Raster calculations** require server-side processing (TiTiler) because PNG tiles lose original values

3. **Vector calculations** can happen client-side in the browser because geometry is preserved

4. **STAC links to data** - most commonly raster COG files, occasionally vector files

5. **Earth Copilot architecture**: Backend calculates → TiTiler renders → Frontend displays

---

## Related Files

- `earth-copilot/container-app/collection_profiles.py` - STAC collection definitions
- `earth-copilot/container-app/hybrid_rendering_system.py` - TiTiler rendering logic
- `earth-copilot/web-ui/src/utils/tileLayerFactory.ts` - Frontend tile layers
