# Traversability Analysis Strategy
**Date**: October 18, 2025  
**Purpose**: Define intelligent approach for path traversability queries without road data

---

## 🎯 THE CORE PROBLEM

**User Query**: "Where can I go from this location?" (with pin drop + GEOINT on)

**Challenges**:
1. ❌ No road data available
2. ❌ Can't return "all possible paths" - too vague and map-dependent
3. ❌ Can't pre-render paths without knowing destination
4. ✅ Have: DEM data, slope calculations, pin coordinates
5. ✅ Need: Actionable intelligence about traversable terrain

---

## 💡 RECOMMENDED APPROACH: Directional Traversability Zones

Instead of paths, analyze **accessibility in each direction** from the pin location.

### Concept: 8-Direction Corridor Analysis

```
         N (0°)
         |
    NW   |   NE
      \  |  /
       \ | /
W ------●------ E  (Pin location)
       / | \
      /  |  \
    SW   |   SE
         |
         S (180°)
```

**For each cardinal/intercardinal direction:**
1. Project a corridor (e.g., 1km wide × 5km deep)
2. Analyze terrain traversability in that corridor
3. Return **GO/NO-GO assessment + distance achievable**

---

## 🔧 IMPLEMENTATION STRATEGY

### Option 1: Directional Corridor Analysis (RECOMMENDED)
**Best for**: "Where can I move from here?" queries

**Algorithm**:
```python
def analyze_traversability_from_point(
    pin_lat: float,
    pin_lng: float,
    max_slope_percent: float = 30.0,
    corridor_width_m: float = 1000,  # 1km wide corridors
    search_distance_km: float = 5     # How far to look
) -> Dict[str, Any]:
    """
    Analyze traversability in 8 directions from pin location.
    
    Returns:
        {
            'north': {
                'traversable_distance_km': 4.2,
                'assessment': 'GOOD',
                'avg_slope_percent': 12.3,
                'obstacles': ['steep_section_at_2.5km'],
                'recommendation': 'Clear path for 4.2km'
            },
            'northeast': {
                'traversable_distance_km': 1.8,
                'assessment': 'LIMITED',
                'avg_slope_percent': 28.5,
                'obstacles': ['steep_ridge_at_1.8km'],
                'recommendation': 'Passable for 1.8km, then terrain becomes too steep'
            },
            ...
        }
    """
```

**Advantages**:
- ✅ Actionable: "You can move north for 5km, east for 2km"
- ✅ Map-independent: Results don't depend on zoom level
- ✅ Efficient: Only 8 analyses instead of full raster processing
- ✅ Military relevant: Matches "avenue of approach" analysis
- ✅ Can visualize: Draw colored wedges on map showing GO/NO-GO zones

**Response Example**:
```
Traversability Analysis from Pin Location (38.5°N, -77.0°W)

Criteria: Slope ≤ 30% (suitable for vehicles/personnel)

📍 Directional Assessment:

✅ NORTH (0°): GOOD - Clear for 4.8 km
   - Avg slope: 8.2% | Max encountered: 18.3%
   - Terrain: Gentle rolling hills

⚠️ NORTHEAST (45°): LIMITED - Passable for 2.1 km
   - Avg slope: 22.5% | Max encountered: 34.2%
   - Obstacle: Steep ridge at 2.1km blocks further progress

✅ EAST (90°): GOOD - Clear for 5.0 km
   - Avg slope: 6.1% | Max encountered: 15.8%
   - Terrain: Flat to gentle slopes

🚫 SOUTHEAST (135°): BLOCKED - Impassable beyond 0.8 km
   - Avg slope: 41.2% | Max encountered: 58.9%
   - Obstacle: Steep escarpment immediately south

✅ SOUTH (180°): GOOD - Clear for 3.9 km
   ...

🎯 Best Routes:
1. EAST: 5.0 km of clear terrain (best option)
2. NORTH: 4.8 km of clear terrain
3. NORTHWEST: 4.2 km of clear terrain

⚠️ Avoid: SOUTHEAST and SOUTHWEST directions (steep terrain)
```

---

### Option 2: Radial Distance Analysis
**Best for**: "How far can I go from here?" queries

**Algorithm**:
```python
def analyze_traversability_radial(
    pin_lat: float,
    pin_lng: float,
    max_slope_percent: float = 30.0,
    max_radius_km: float = 5
) -> Dict[str, Any]:
    """
    Calculate maximum traversable distance in all directions.
    
    Returns:
        {
            'traversable_area_km2': 45.8,
            'percentage_accessible': 58.3,
            'max_distance_any_direction_km': 5.0,
            'min_distance_any_direction_km': 0.8,
            'avg_traversable_distance_km': 3.2,
            'radial_profile': [
                {'bearing': 0, 'max_distance_km': 4.8},
                {'bearing': 45, 'max_distance_km': 2.1},
                ...
            ]
        }
    """
```

**Advantages**:
- ✅ Simple metric: "58% of area within 5km is accessible"
- ✅ Good for strategic planning
- ⚠️ Less actionable than directional analysis

---

### Option 3: Cost-Distance Surface (Advanced)
**Best for**: "What's the easiest route to point B?" queries

**Algorithm**: Calculate accumulated movement cost from origin
- Each pixel gets a "cost" based on slope
- Propagate cost outward from pin location
- Generate "isochrones" (lines of equal travel difficulty)

**Advantages**:
- ✅ Most sophisticated
- ✅ Can find optimal paths between two points
- ❌ Complex to implement (~5 days)
- ❌ Requires destination point (A-to-B query)

**Defer this** until we have directional analysis working.

---

## 🎯 RECOMMENDED IMPLEMENTATION: Directional Corridor Analysis

### Phase 1: Basic Directional Analysis (2-3 hours)

**Step 1**: Add corridor projection function
```python
def _project_corridor(
    self,
    origin_lat: float,
    origin_lng: float,
    bearing_degrees: float,
    width_m: float,
    length_m: float
) -> List[float]:
    """
    Project a rectangular corridor from origin point.
    
    Args:
        origin_lat, origin_lng: Starting point
        bearing_degrees: Direction (0=N, 90=E, 180=S, 270=W)
        width_m: Corridor width in meters
        length_m: Corridor length in meters
    
    Returns:
        Bounding box [west, south, east, north] for corridor
    """
    from geopy import distance
    from geopy import Point
    
    # Calculate center line endpoint
    origin = Point(origin_lat, origin_lng)
    endpoint = distance.distance(meters=length_m).destination(origin, bearing_degrees)
    
    # Calculate perpendicular offset for width
    half_width = width_m / 2
    left_bearing = (bearing_degrees - 90) % 360
    right_bearing = (bearing_degrees + 90) % 360
    
    # Get four corners
    origin_left = distance.distance(meters=half_width).destination(origin, left_bearing)
    origin_right = distance.distance(meters=half_width).destination(origin, right_bearing)
    end_left = distance.distance(meters=half_width).destination(endpoint, left_bearing)
    end_right = distance.distance(meters=half_width).destination(endpoint, right_bearing)
    
    # Calculate bounding box
    all_lons = [origin_left.longitude, origin_right.longitude, end_left.longitude, end_right.longitude]
    all_lats = [origin_left.latitude, origin_right.latitude, end_left.latitude, end_right.latitude]
    
    return [min(all_lons), min(all_lats), max(all_lons), max(all_lats)]
```

**Step 2**: Add traversability analysis for corridor
```python
def _analyze_corridor_traversability(
    self,
    corridor_bbox: List[float],
    max_slope_percent: float,
    origin_lat: float,
    origin_lng: float,
    bearing_degrees: float
) -> Dict[str, Any]:
    """
    Analyze how far you can traverse in a corridor direction.
    
    Returns:
        {
            'traversable_distance_km': float,
            'assessment': 'GOOD' | 'LIMITED' | 'BLOCKED',
            'avg_slope_percent': float,
            'max_slope_percent': float,
            'obstacle_distance_km': float | None
        }
    """
    # Get elevation data for corridor
    results = self.analyze(bbox=corridor_bbox, analysis_type='slope')
    slope_data = np.array(results['slope']['data'])
    
    # Calculate distance from origin for each pixel
    # (We need pixel coordinates → lat/lng → distance from origin)
    height, width = slope_data.shape
    
    # Create distance matrix
    distances_km = self._calculate_pixel_distances_from_origin(
        slope_data.shape,
        corridor_bbox,
        origin_lat,
        origin_lng
    )
    
    # Find where slope exceeds threshold
    max_slope_degrees = np.degrees(np.arctan(max_slope_percent / 100))
    impassable_mask = slope_data > max_slope_degrees
    
    # Find first obstacle distance
    if np.any(impassable_mask):
        # Get minimum distance where impassable terrain exists
        impassable_distances = distances_km[impassable_mask]
        obstacle_distance_km = float(np.min(impassable_distances))
        traversable_distance_km = obstacle_distance_km
    else:
        # Entire corridor is passable
        traversable_distance_km = float(np.max(distances_km))
        obstacle_distance_km = None
    
    # Calculate statistics for passable terrain
    passable_mask = ~impassable_mask
    passable_slopes = slope_data[passable_mask]
    
    avg_slope_degrees = float(np.mean(passable_slopes)) if len(passable_slopes) > 0 else 0
    max_slope_degrees_actual = float(np.max(passable_slopes)) if len(passable_slopes) > 0 else 0
    
    # Convert to percent
    avg_slope_percent = np.tan(np.radians(avg_slope_degrees)) * 100
    max_slope_percent_actual = np.tan(np.radians(max_slope_degrees_actual)) * 100
    
    # Determine assessment
    if traversable_distance_km < 1.0:
        assessment = 'BLOCKED'
    elif traversable_distance_km < 3.0:
        assessment = 'LIMITED'
    else:
        assessment = 'GOOD'
    
    return {
        'traversable_distance_km': round(traversable_distance_km, 2),
        'assessment': assessment,
        'avg_slope_percent': round(avg_slope_percent, 1),
        'max_slope_percent': round(max_slope_percent_actual, 1),
        'obstacle_distance_km': round(obstacle_distance_km, 2) if obstacle_distance_km else None
    }
```

**Step 3**: Add 8-direction analysis
```python
def analyze_traversability_from_point(
    self,
    pin_lat: float,
    pin_lng: float,
    max_slope_percent: float = 30.0,
    corridor_width_m: float = 1000,
    search_distance_km: float = 5
) -> Dict[str, Any]:
    """
    Analyze traversability in 8 directions from pin location.
    """
    directions = {
        'north': 0,
        'northeast': 45,
        'east': 90,
        'southeast': 135,
        'south': 180,
        'southwest': 225,
        'west': 270,
        'northwest': 315
    }
    
    results = {}
    
    for direction_name, bearing in directions.items():
        logger.info(f"Analyzing {direction_name} corridor (bearing {bearing}°)")
        
        # Project corridor
        corridor_bbox = self._project_corridor(
            pin_lat, pin_lng,
            bearing,
            width_m=corridor_width_m,
            length_m=search_distance_km * 1000
        )
        
        # Analyze traversability
        corridor_results = self._analyze_corridor_traversability(
            corridor_bbox,
            max_slope_percent,
            pin_lat, pin_lng,
            bearing
        )
        
        results[direction_name] = corridor_results
    
    # Add summary statistics
    distances = [r['traversable_distance_km'] for r in results.values()]
    results['summary'] = {
        'max_distance_km': max(distances),
        'min_distance_km': min(distances),
        'avg_distance_km': np.mean(distances),
        'num_good_routes': sum(1 for r in results.values() if r['assessment'] == 'GOOD'),
        'num_blocked_routes': sum(1 for r in results.values() if r['assessment'] == 'BLOCKED')
    }
    
    return results
```

---

## 📊 VISUALIZATION OPTIONS

### Option 1: Colored Wedges (Simple, Recommended)
Draw 8 wedge-shaped overlays on map:
- 🟢 Green: GOOD routes (>3km clear)
- 🟡 Yellow: LIMITED routes (1-3km clear)
- 🔴 Red: BLOCKED routes (<1km clear)

**GeoJSON Format**:
```json
{
  "type": "FeatureCollection",
  "features": [
    {
      "type": "Feature",
      "properties": {
        "direction": "north",
        "assessment": "GOOD",
        "distance_km": 4.8,
        "color": "#00ff00"
      },
      "geometry": {
        "type": "Polygon",
        "coordinates": [/* wedge shape */]
      }
    },
    ...
  ]
}
```

### Option 2: Gradient Heatmap (Advanced)
- Show entire slope raster with color coding
- Green = passable, Red = impassable
- More information, but harder to interpret quickly

**Defer** until directional analysis is proven useful.

---

## 🎯 QUERY HANDLING STRATEGY

### Query Classification

**Type A: "Where can I go from here?"**
- Trigger: Pin drop + words like "go", "move", "traverse", "travel"
- Action: Run 8-direction analysis
- Response: Directional assessment with best routes

**Type B: "Can I reach point B from here?"**
- Trigger: Pin drop + destination mention OR two pins
- Action: Run corridor analysis in direction of destination
- Response: YES/NO + distance achievable + obstacles

**Type C: "Show me passable terrain"**
- Trigger: Pin drop + "show", "highlight", "display" + slope criteria
- Action: Run radial slope filtering (existing functionality)
- Response: Area statistics + filtered raster

---

## ⏰ IMPLEMENTATION TIMELINE

| Phase | Task | Time |
|-------|------|------|
| **Phase 1** | Corridor projection function | 30 min |
| | Distance-from-origin calculation | 30 min |
| | Corridor traversability analysis | 1 hour |
| | 8-direction wrapper | 30 min |
| | Testing | 30 min |
| | **Subtotal** | **3 hours** |
| **Phase 2** | Response formatting | 30 min |
| | Query classification updates | 30 min |
| | Integration with existing modules | 30 min |
| | **Subtotal** | **1.5 hours** |
| **Phase 3** | Visualization GeoJSON generation | 1 hour |
| | Frontend wedge rendering | 2 hours |
| | **Subtotal** | **3 hours** |
| | | |
| | **TOTAL (Backend working)** | **4.5 hours** |
| | **TOTAL (With visualization)** | **7.5 hours** |

---

## 🎯 SUCCESS CRITERIA

**After Phase 1 + 2 (Backend):**
- ✅ User pins location, asks "Where can I go from here?"
- ✅ System returns 8-direction assessment
- ✅ Response shows: "You can move NORTH for 4.8km, EAST for 5.0km, avoid SOUTHEAST (blocked)"
- ✅ Results are accurate based on DEM slope data

**After Phase 3 (Visualization):**
- ✅ Map shows colored wedges indicating GO/NO-GO directions
- ✅ User can visually see safe routes at a glance

---

## 📋 RECOMMENDATION

**Implement Phase 1 + 2 NOW (4.5 hours):**
1. Directional corridor analysis
2. 8-direction traversability assessment
3. Response formatting
4. Query classification

**Defer Phase 3 (Visualization):**
- Wait until users confirm directional analysis is valuable
- Frontend work can happen in parallel with backend testing

**This gives you:**
- ✅ Actionable intelligence ("go north, avoid southeast")
- ✅ Map-independent results
- ✅ Efficient analysis (8 corridors vs full raster)
- ✅ Military-relevant output format

---

**Ready to implement Phase 1 + 2?** This is the most effective approach for path traversability without road data.

