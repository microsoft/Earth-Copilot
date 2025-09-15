"""
Multi-Strategy Enhanced Location Resolver 
Replaces Nominatim-only approach with comprehensive geographic region resolution
"""
import json
import time
import hashlib
from typing import Dict, List, Optional, Any
import asyncio
import aiohttp
import logging
import os
import re

class LocationCache:
    """In-memory location cache with TTL and persistence"""
    
    def __init__(self, ttl_hours: int = 24, max_entries: int = 1000):
        self.cache = {}
        self.ttl_seconds = ttl_hours * 3600
        self.max_entries = max_entries
        self.logger = logging.getLogger(__name__)
    
    def _generate_key(self, location_name: str, location_type: str) -> str:
        """Generate cache key for location"""
        key_string = f"{location_name.lower().strip()}:{location_type.lower()}"
        return hashlib.md5(key_string.encode()).hexdigest()
    
    def get(self, location_name: str, location_type: str) -> Optional[List[float]]:
        """Get cached location bbox"""
        key = self._generate_key(location_name, location_type)
        
        if key in self.cache:
            entry = self.cache[key]
            # Check if entry is still valid
            if time.time() - entry['timestamp'] < self.ttl_seconds:
                self.logger.debug(f"Cache hit for {location_name}")
                return entry['bbox']
            else:
                # Remove expired entry
                del self.cache[key]
                self.logger.debug(f"Cache expired for {location_name}")
        
        return None
    
    def set(self, location_name: str, location_type: str, bbox: List[float]):
        """Cache location bbox"""
        key = self._generate_key(location_name, location_type)
        
        # Remove oldest entries if cache is full
        if len(self.cache) >= self.max_entries:
            oldest_key = min(self.cache.keys(), key=lambda k: self.cache[k]['timestamp'])
            del self.cache[oldest_key]
        
        self.cache[key] = {
            'bbox': bbox,
            'timestamp': time.time(),
            'location_name': location_name,
            'location_type': location_type
        }
        self.logger.debug(f"Cached location {location_name}")

class EnhancedLocationResolver:
    """
    🌍 MULTI-STRATEGY LOCATION RESOLVER
    
    Fixes the Nominatim geographic region failures by using multiple strategies:
    1. ✅ PREDEFINED REGIONS (Highest accuracy for major geographic features)
    2. ✅ AZURE MAPS (Microsoft's service - enterprise GIS)
    3. ✅ MAPBOX (Geographic region specialist)
    4. ✅ GOOGLE MAPS (Most comprehensive)
    5. ✅ IMPROVED NOMINATIM (Enhanced queries as fallback)
    
    NO MORE FALLBACK COORDINATES - All resolution via proper geocoding
    """
    
    def __init__(self):
        self.logger = logging.getLogger(__name__)
        self.cache = LocationCache()
        
        # API keys from environment
        self.azure_maps_key = os.getenv('AZURE_MAPS_SUBSCRIPTION_KEY')
        self.mapbox_token = os.getenv('MAPBOX_ACCESS_TOKEN')
        self.google_api_key = os.getenv('GOOGLE_MAPS_API_KEY')
        
        # 🎯 ACCURATE GEOGRAPHIC REGIONS (fixes Nominatim coordinate issues)
        self.geographic_regions = {
            # Rocky Mountains and subregions - CORRECT COORDINATES
            "rocky mountains": {
                "bounds": [-114.0, 37.0, -104.0, 49.0],
                "center": [40.0, -107.0],
                "name": "Rocky Mountains, North America"
            },
            "rocky mountains colorado": {
                "bounds": [-109.0, 37.0, -102.0, 41.0],
                "center": [39.0, -106.0],  # CORRECT: Not medical center!
                "name": "Colorado Rocky Mountains"
            },
            "colorado rockies": {
                "bounds": [-109.0, 37.0, -102.0, 41.0],
                "center": [39.0, -106.0],  # CORRECT: Not prison!
                "name": "Colorado Rocky Mountains"
            },
            "front range colorado": {
                "bounds": [-106.0, 38.5, -104.5, 41.0],
                "center": [39.75, -105.25],  # CORRECT: Not college!
                "name": "Front Range, Colorado"
            },
            "colorado front range": {
                "bounds": [-106.0, 38.5, -104.5, 41.0],
                "center": [39.75, -105.25], 
                "name": "Front Range, Colorado"
            },
            
            # Other major mountain ranges
            "sierra nevada": {
                "bounds": [-120.0, 35.0, -117.5, 40.0],
                "center": [37.5, -118.75],
                "name": "Sierra Nevada Mountains"
            },
            "sierra nevada california": {
                "bounds": [-120.0, 35.0, -117.5, 40.0],
                "center": [37.5, -118.75],
                "name": "Sierra Nevada, California"
            },
            "appalachian mountains": {
                "bounds": [-84.0, 33.0, -76.0, 47.0],
                "center": [40.0, -80.0],
                "name": "Appalachian Mountains"
            },
            
            # States and regions
            "colorado": {
                "bounds": [-109.0, 37.0, -102.0, 41.0],
                "center": [39.0, -105.5],
                "name": "Colorado, United States"
            },
            "california": {
                "bounds": [-124.0, 32.5, -114.0, 42.0],
                "center": [37.25, -119.0],
                "name": "California, United States"
            },
            
            # Disaster-prone regions
            "gulf coast": {
                "bounds": [-97.5, 25.5, -81.0, 30.5],
                "center": [28.0, -89.25],
                "name": "Gulf Coast, United States"
            },
            "florida keys": {
                "bounds": [-82.0, 24.5, -80.0, 25.5],
                "center": [25.0, -81.0],
                "name": "Florida Keys"
            }
        }
        
        self.logger.info(f"✓ Enhanced Location Resolver initialized with {len(self.geographic_regions)} predefined regions")
    
    async def resolve_location_to_bbox(self, location_name: str, location_type: str = "region") -> Optional[List[float]]:
        """
        🎯 MULTI-STRATEGY LOCATION RESOLUTION
        
        Priority order ensures accurate geographic region resolution:
        1. Cache check
        2. Predefined regions (highest accuracy)
        3. Azure Maps (Microsoft native)
        4. Mapbox (geographic specialist)
        5. Google Maps (comprehensive)
        6. Improved Nominatim (fallback)
        
        Returns: [west, south, east, north] bounding box or None
        """
        self.logger.info(f"🔍 Resolving location: '{location_name}' (type: {location_type})")
        
        # Check cache first
        cached_bbox = self.cache.get(location_name, location_type)
        if cached_bbox:
            self.logger.info(f"📋 Cache hit for {location_name}")
            return cached_bbox
        
        # Strategy 1: Check predefined accurate regions (highest confidence)
        bbox = await self._strategy_predefined_regions(location_name)
        if bbox:
            self.logger.info(f"✅ Resolved via predefined regions: {location_name}")
            self.cache.set(location_name, location_type, bbox)
            return bbox
        
        # Strategy 2: Try Azure Maps (Microsoft integration)
        if self.azure_maps_key:
            bbox = await self._strategy_azure_maps(location_name)
            if bbox:
                self.logger.info(f"✅ Resolved via Azure Maps: {location_name}")
                self.cache.set(location_name, location_type, bbox)
                return bbox
        
        # Strategy 3: Try Mapbox (excellent for geographic regions)
        if self.mapbox_token:
            bbox = await self._strategy_mapbox(location_name)
            if bbox:
                self.logger.info(f"✅ Resolved via Mapbox: {location_name}")
                self.cache.set(location_name, location_type, bbox)
                return bbox
        
        # Strategy 4: Try Google Maps (most comprehensive)
        if self.google_api_key:
            bbox = await self._strategy_google_maps(location_name)
            if bbox:
                self.logger.info(f"✅ Resolved via Google Maps: {location_name}")
                self.cache.set(location_name, location_type, bbox)
                return bbox
        
        # Strategy 5: Improved Nominatim queries (fallback)
        bbox = await self._strategy_improved_nominatim(location_name)
        if bbox:
            self.logger.info(f"⚠️ Resolved via Nominatim fallback: {location_name}")
            self.cache.set(location_name, location_type, bbox)
            return bbox
        
        self.logger.error(f"❌ Could not resolve location: {location_name}")
        return None
    
    async def _strategy_predefined_regions(self, location_name: str) -> Optional[List[float]]:
        """🎯 Strategy 1: Check predefined accurate geographic regions"""
        query_lower = location_name.lower().strip()
        
        # Direct exact matches
        if query_lower in self.geographic_regions:
            region = self.geographic_regions[query_lower]
            return region['bounds']
        
        # Fuzzy matches for variations
        for key, region in self.geographic_regions.items():
            if self._is_fuzzy_match(query_lower, key):
                return region['bounds']
        
        return None
    
    def _is_fuzzy_match(self, query: str, region_key: str) -> bool:
        """Check if query fuzzy matches a region key"""
        query_words = set(re.findall(r'\b\w+\b', query.lower()))
        key_words = set(re.findall(r'\b\w+\b', region_key.lower()))
        
        if len(key_words) == 0:
            return False
            
        overlap = len(query_words.intersection(key_words))
        overlap_ratio = overlap / len(key_words)
        
        return overlap_ratio >= 0.75  # 75% word overlap required
    
    async def _strategy_azure_maps(self, location_name: str) -> Optional[List[float]]:
        """🔵 Strategy 2: Azure Maps Search API"""
        url = "https://atlas.microsoft.com/search/address/json"
        params = {
            "api-version": "1.0",
            "subscription-key": self.azure_maps_key,
            "query": location_name,
            "limit": 1
        }
        
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(url, params=params) as response:
                    if response.status == 200:
                        data = await response.json()
                        results = data.get("results", [])
                        if results:
                            result = results[0]
                            return self._extract_azure_bounds(result)
        except Exception as e:
            self.logger.error(f"Azure Maps error: {e}")
        
        return None
    
    def _extract_azure_bounds(self, result: Dict) -> Optional[List[float]]:
        """Extract bounds from Azure Maps result"""
        viewport = result.get("viewport", {})
        if viewport:
            top_left = viewport.get("topLeftPoint", {})
            bottom_right = viewport.get("btmRightPoint", {})
            if top_left and bottom_right:
                return [
                    top_left.get("lon"),    # west
                    bottom_right.get("lat"), # south
                    bottom_right.get("lon"), # east
                    top_left.get("lat")     # north
                ]
        return None
    
    async def _strategy_mapbox(self, location_name: str) -> Optional[List[float]]:
        """📦 Strategy 3: Mapbox Geocoding API"""
        encoded_query = location_name.replace(" ", "%20")
        url = f"https://api.mapbox.com/geocoding/v5/mapbox.places/{encoded_query}.json"
        params = {
            "access_token": self.mapbox_token,
            "limit": 1,
            "types": "region,place,district,country"
        }
        
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(url, params=params) as response:
                    if response.status == 200:
                        data = await response.json()
                        features = data.get("features", [])
                        if features:
                            feature = features[0]
                            bbox = feature.get("bbox")
                            return bbox if bbox else None
        except Exception as e:
            self.logger.error(f"Mapbox error: {e}")
        
        return None
    
    async def _strategy_google_maps(self, location_name: str) -> Optional[List[float]]:
        """🔍 Strategy 4: Google Maps Geocoding API"""
        url = "https://maps.googleapis.com/maps/api/geocode/json"
        params = {
            "address": location_name,
            "key": self.google_api_key
        }
        
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(url, params=params) as response:
                    if response.status == 200:
                        data = await response.json()
                        results = data.get("results", [])
                        if results:
                            result = results[0]
                            return self._extract_google_bounds(result)
        except Exception as e:
            self.logger.error(f"Google Maps error: {e}")
        
        return None
    
    def _extract_google_bounds(self, result: Dict) -> Optional[List[float]]:
        """Extract bounds from Google Maps result"""
        geometry = result.get("geometry", {})
        viewport = geometry.get("viewport")
        bounds_data = geometry.get("bounds", viewport)
        
        if bounds_data:
            southwest = bounds_data.get("southwest", {})
            northeast = bounds_data.get("northeast", {})
            if southwest and northeast:
                return [
                    southwest.get("lng"), # west
                    southwest.get("lat"), # south
                    northeast.get("lng"), # east
                    northeast.get("lat")  # north
                ]
        return None
    
    async def _strategy_improved_nominatim(self, location_name: str) -> Optional[List[float]]:
        """🌍 Strategy 5: Improved Nominatim queries (fallback)"""
        
        # Try different query variations optimized for geographic regions
        query_variations = [
            f"{location_name} mountain range",
            f"{location_name} mountains",
            f"{location_name} region",
            f"{location_name} geographical feature",
            location_name  # Original query last
        ]
        
        for variation in query_variations:
            bbox = await self._nominatim_single_query(variation)
            if bbox and self._is_valid_geographic_bbox(bbox):
                return bbox
        
        return None
    
    async def _nominatim_single_query(self, query: str) -> Optional[List[float]]:
        """Single optimized Nominatim query"""
        url = "https://nominatim.openstreetmap.org/search"
        params = {
            "q": query,
            "format": "json",
            "limit": 5,
            "addressdetails": 1,
            "extratags": 1,
            "namedetails": 1,
            "dedupe": 1
        }
        headers = {"User-Agent": "EarthCopilot/2.0 (geographic-analysis)"}
        
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(url, params=params) as response:
                    if response.status == 200:
                        data = await response.json()
                        
                        # Filter for best geographic result
                        for result in data:
                            if self._is_valid_geographic_result(result):
                                return self._extract_nominatim_bounds(result)
        except Exception as e:
            self.logger.error(f"Nominatim error: {e}")
        
        return None
    
    def _is_valid_geographic_result(self, result: Dict) -> bool:
        """Enhanced validation for geographic features (not businesses/roads)"""
        display_name = result.get('display_name', '').lower()
        place_type = result.get('type', '').lower()
        osm_class = result.get('class', '').lower()
        
        # EXCLUDE businesses, institutions, infrastructure
        exclude_patterns = [
            'center', 'college', 'university', 'hospital', 'hotel', 'restaurant',
            'store', 'shop', 'office', 'building', 'street', 'road', 'avenue',
            'boulevard', 'drive', 'lane', 'penitentiary', 'prison', 'jail',
            'airport', 'school', 'library', 'museum', 'bank', 'clinic'
        ]
        
        for pattern in exclude_patterns:
            if pattern in display_name:
                return False
        
        # PREFER natural geographic features
        prefer_types = [
            'peak', 'mountain', 'range', 'natural', 'place', 'region',
            'state', 'county', 'administrative', 'boundary'
        ]
        
        return any(geo_type in place_type or geo_type in osm_class 
                  for geo_type in prefer_types)
    
    def _extract_nominatim_bounds(self, result: Dict) -> Optional[List[float]]:
        """Extract bounds from Nominatim result"""
        boundingbox = result.get('boundingbox')
        if boundingbox and len(boundingbox) == 4:
            # Nominatim: [min_lat, max_lat, min_lon, max_lon]
            # Convert to: [min_lon, min_lat, max_lon, max_lat]
            return [
                float(boundingbox[2]),  # min_lon (west)
                float(boundingbox[0]),  # min_lat (south)
                float(boundingbox[3]),  # max_lon (east)
                float(boundingbox[1])   # max_lat (north)
            ]
        return None
    
    def _is_valid_geographic_bbox(self, bbox: List[float]) -> bool:
        """Validate that bounding box represents a reasonable geographic area"""
        if not bbox or len(bbox) != 4:
            return False
        
        west, south, east, north = bbox
        
        # Basic coordinate validation
        if not (-180 <= west <= 180 and -180 <= east <= 180):
            return False
        if not (-90 <= south <= 90 and -90 <= north <= 90):
            return False
        if west >= east or south >= north:
            return False
        
        # Size validation (not too small, not too large)
        width = east - west
        height = north - south
        
        # Reject tiny areas (likely specific buildings)
        if width < 0.001 or height < 0.001:
            return False
        
        # Reject unreasonably large areas (likely geocoding errors)
        if width > 50 or height > 50:
            return False
        
        return True
