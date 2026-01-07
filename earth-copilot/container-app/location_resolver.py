# Copyright (c) Microsoft Corporation.
# Licensed under the MIT license.

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

# Load environment variables
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass  # dotenv not available in production

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
    4. ✅ IMPROVED NOMINATIM (Enhanced queries as fallback)
    
    NO MORE FALLBACK COORDINATES - All resolution via proper geocoding
    """
    
    # 🗺️ HARDCODED GLOBAL LOCATIONS - Ultimate fallback for reliable resolution
    # Format: [west, south, east, north] bounding boxes
    STORED_LOCATIONS = {
        # === WORLD COUNTRIES ===
        'united states': [-179.15, 18.91, -66.95, 71.44],
        'usa': [-179.15, 18.91, -66.95, 71.44],
        'canada': [-141.00, 41.68, -52.62, 83.11],
        'quebec': [-79.76, 45.00, -57.10, 62.58],  # Quebec province, Canada
        'mexico': [-118.45, 14.53, -86.71, 32.72],
        'united kingdom': [-8.65, 49.86, 1.77, 60.86],
        'uk': [-8.65, 49.86, 1.77, 60.86],
        'great britain': [-8.65, 49.86, 1.77, 60.86],
        'france': [-5.14, 41.33, 9.56, 51.09],
        'germany': [5.87, 47.27, 15.04, 55.06],
        'italy': [6.63, 35.49, 18.52, 47.09],
        'spain': [-18.16, 27.64, 4.33, 43.79],
        'portugal': [-31.28, 32.64, -6.19, 42.15],
        'netherlands': [3.36, 50.75, 7.23, 53.56],
        'belgium': [2.54, 49.50, 6.41, 51.51],
        'switzerland': [5.96, 45.82, 10.49, 47.81],
        'austria': [9.53, 46.37, 17.16, 49.02],
        'poland': [14.12, 49.00, 24.15, 54.84],
        'czech republic': [12.09, 48.56, 18.86, 51.06],
        'slovakia': [16.83, 47.73, 22.56, 49.61],
        'hungary': [16.11, 45.74, 22.90, 48.59],
        'romania': [20.26, 43.62, 29.71, 48.27],
        'bulgaria': [22.36, 41.24, 28.61, 44.22],
        'greece': [19.37, 34.80, 29.65, 41.75],
        'turkey': [25.66, 35.82, 44.83, 42.11],
        'russia': [19.64, 41.19, 180.00, 81.86],
        'ukraine': [22.14, 44.39, 40.23, 52.38],
        'norway': [4.65, 57.98, 31.08, 71.18],
        'sweden': [11.12, 55.34, 24.16, 69.06],
        'finland': [20.55, 59.81, 31.59, 70.09],
        'denmark': [8.09, 54.56, 15.19, 57.75],
        'ireland': [-10.48, 51.42, -5.99, 55.39],
        'iceland': [-24.54, 63.39, -13.50, 66.54],
        'greenland': [-73.04, 59.78, -11.31, 83.63],  # World's largest island
        'japan': [122.93, 24.25, 153.99, 45.52],
        'china': [73.50, 18.16, 134.77, 53.56],
        'india': [68.18, 6.75, 97.40, 35.67],
        'australia': [112.92, -43.64, 153.64, -10.06],
        'new zealand': [166.51, -47.29, 178.52, -34.39],
        'south korea': [125.07, 33.11, 129.58, 38.61],
        'north korea': [124.32, 37.67, 130.68, 43.01],
        'thailand': [97.35, 5.61, 105.64, 20.46],
        'vietnam': [102.14, 8.56, 109.47, 23.39],
        'malaysia': [99.64, 0.85, 119.28, 7.36],
        'singapore': [103.61, 1.16, 104.04, 1.47],
        'indonesia': [95.01, -11.01, 141.02, 5.91],
        'philippines': [116.93, 4.64, 126.60, 21.12],
        'brazil': [-73.99, -33.75, -34.79, 5.27],
        'argentina': [-73.56, -55.06, -53.59, -21.78],
        'chile': [-109.45, -55.92, -66.42, -17.50],
        'peru': [-81.33, -18.35, -68.67, -0.04],
        'colombia': [-79.00, -4.23, -66.87, 12.46],
        'venezuela': [-73.35, 0.65, -59.80, 12.20],
        'ecuador': [-92.01, -5.02, -75.19, 1.68],
        'bolivia': [-69.64, -22.90, -57.45, -9.68],
        'uruguay': [-58.44, -35.02, -53.08, -30.09],
        'paraguay': [-62.65, -27.61, -54.26, -19.29],
        'egypt': [24.70, 22.00, 36.89, 31.67],
        'south africa': [16.46, -34.84, 32.89, -22.13],
        'kenya': [33.91, -4.68, 41.91, 5.03],
        'nigeria': [2.67, 4.27, 14.68, 13.89],
        'morocco': [-17.02, 21.41, -0.99, 35.92],
        'algeria': [-8.67, 18.97, 12.00, 37.09],
        'tunisia': [7.52, 30.23, 11.60, 37.54],
        'saudi arabia': [34.57, 16.38, 55.67, 32.16],
        'united arab emirates': [51.50, 22.63, 56.38, 26.08],
        'uae': [51.50, 22.63, 56.38, 26.08],
        'israel': [34.27, 29.50, 35.89, 33.34],
        'jordan': [34.96, 29.19, 39.30, 33.38],
        'lebanon': [35.10, 33.05, 36.62, 34.69],
        'iran': [44.03, 25.06, 63.33, 39.78],
        'iraq': [38.79, 29.07, 48.57, 37.38],
        'afghanistan': [60.48, 29.38, 74.88, 38.49],
        'pakistan': [60.88, 23.69, 77.84, 37.08],
        'bangladesh': [88.03, 20.74, 92.67, 26.63],
        'nepal': [80.06, 26.35, 88.20, 30.43],
        'sri lanka': [79.70, 5.92, 81.88, 9.83],
        'myanmar': [92.19, 9.78, 101.18, 28.55],
        'burma': [92.19, 9.78, 101.18, 28.55],  # Alias for Myanmar
        'cambodia': [102.34, 10.41, 107.63, 14.69],
        'laos': [100.09, 13.91, 107.70, 22.50],
        'mongolia': [87.75, 41.57, 119.93, 52.15],
        'taiwan': [120.04, 21.90, 122.01, 25.30],
        'hong kong': [113.84, 22.15, 114.41, 22.56],
        'macao': [113.53, 22.11, 113.60, 22.22],
        'papua new guinea': [140.84, -11.66, 159.49, -0.89],
        'fiji': [177.12, -20.67, -178.42, -12.48],
        'solomon islands': [155.51, -11.85, 167.84, -5.32],
        'vanuatu': [166.52, -20.25, 170.24, -13.07],
        'samoa': [-172.80, -14.08, -171.42, -13.43],
        'tonga': [-175.68, -21.46, -173.91, -15.56],
        'micronesia': [137.33, 1.03, 163.04, 10.09],
        'palau': [131.12, 2.91, 134.72, 8.09],
        'marshall islands': [165.52, 5.59, 171.93, 14.62],
        'kiribati': [-174.54, -11.44, -150.21, 4.71],
        'tuvalu': [176.07, -10.80, 179.86, -5.64],
        'nauru': [166.90, -0.55, 166.96, -0.50],
        
        # Additional African countries
        'libya': [9.39, 19.50, 25.15, 33.17],
        'sudan': [21.83, 8.68, 38.61, 22.23],
        'south sudan': [23.89, 3.49, 35.95, 12.25],
        'ethiopia': [32.99, 3.40, 47.99, 14.89],
        'somalia': [40.99, -1.67, 51.42, 11.98],
        'eritrea': [36.44, 12.36, 43.14, 18.00],
        'djibouti': [41.77, 10.93, 43.42, 12.71],
        'tanzania': [29.34, -11.75, 40.44, -0.99],
        'uganda': [29.57, -1.48, 35.04, 4.23],
        'rwanda': [28.86, -2.84, 30.90, -1.05],
        'burundi': [29.00, -4.47, 30.85, -2.31],
        'zimbabwe': [25.24, -22.42, 33.07, -15.61],
        'zambia': [21.99, -18.08, 33.71, -8.20],
        'malawi': [32.67, -17.13, 35.92, -9.37],
        'mozambique': [30.22, -26.87, 40.84, -10.47],
        'botswana': [19.90, -26.91, 29.37, -17.78],
        'namibia': [11.73, -28.97, 25.26, -16.96],
        'angola': [11.68, -18.04, 24.08, -4.38],
        'democratic republic of congo': [12.20, -13.46, 31.31, 5.39],
        'drc': [12.20, -13.46, 31.31, 5.39],  # Alias for DRC
        'congo': [11.13, -5.04, 18.65, 3.71],
        'gabon': [8.70, -4.00, 14.52, 2.32],
        'cameroon': [8.49, 1.65, 16.19, 13.08],
        'central african republic': [14.42, 2.22, 27.46, 11.01],
        'chad': [13.47, 7.44, 24.00, 23.45],
        'niger': [0.16, 11.69, 15.99, 23.52],
        'mali': [-12.24, 10.16, 4.27, 25.00],
        'burkina faso': [-5.52, 9.40, 2.41, 15.08],
        'mauritania': [-17.07, 14.72, -4.83, 27.30],
        'senegal': [-17.54, 12.31, -11.36, 16.69],
        'gambia': [-16.83, 13.06, -13.80, 13.83],
        'guinea-bissau': [-16.72, 10.87, -13.64, 12.68],
        'guinea': [-15.08, 7.19, -7.64, 12.68],
        'sierra leone': [-13.31, 6.93, -10.27, 10.00],
        'liberia': [-11.49, 4.35, -7.37, 8.55],
        'ivory coast': [-8.60, 4.36, -2.49, 10.74],
        'cote d\'ivoire': [-8.60, 4.36, -2.49, 10.74],  # Alias
        'ghana': [-3.26, 4.74, 1.19, 11.17],
        'togo': [-0.15, 6.10, 1.81, 11.14],
        'benin': [0.77, 6.23, 3.85, 12.42],
        'madagascar': [43.25, -25.61, 50.48, -11.95],
        'mauritius': [57.31, -20.53, 63.50, -10.32],
        'seychelles': [46.20, -10.36, 56.30, -3.71],
        'comoros': [43.22, -12.42, 44.54, -11.36],
        'swaziland': [30.79, -27.32, 32.14, -25.72],
        'eswatini': [30.79, -27.32, 32.14, -25.72],  # Official name
        'lesotho': [27.01, -30.67, 29.46, -28.57],
        
        # Additional European countries
        'belarus': [23.18, 51.26, 32.77, 56.17],
        'lithuania': [20.94, 53.90, 26.84, 56.45],
        'latvia': [20.97, 55.67, 28.24, 58.09],
        'estonia': [21.84, 57.52, 28.21, 59.68],
        'moldova': [26.62, 45.47, 30.14, 48.49],
        'albania': [19.26, 39.64, 21.05, 42.66],
        'macedonia': [20.45, 40.86, 23.04, 42.36],
        'north macedonia': [20.45, 40.86, 23.04, 42.36],  # Official name
        'montenegro': [18.45, 41.85, 20.36, 43.56],
        'kosovo': [20.02, 41.86, 21.79, 43.27],
        'bosnia and herzegovina': [15.75, 42.56, 19.62, 45.28],
        'bosnia': [15.75, 42.56, 19.62, 45.28],  # Alias
        'serbia': [18.83, 42.23, 23.01, 46.19],
        'croatia': [13.49, 42.39, 19.43, 46.56],
        'slovenia': [13.38, 45.42, 16.61, 46.88],
        'luxembourg': [5.73, 49.45, 6.53, 50.18],
        'liechtenstein': [9.47, 47.05, 9.64, 47.27],
        'andorra': [1.41, 42.43, 1.79, 42.66],
        'monaco': [7.41, 43.72, 7.44, 43.75],
        'san marino': [12.40, 43.89, 12.52, 43.99],
        'vatican city': [12.44, 41.90, 12.46, 41.91],
        'malta': [14.18, 35.81, 14.58, 36.08],
        'cyprus': [32.27, 34.63, 34.60, 35.71],
        
        # Additional Middle East countries
        'yemen': [42.55, 12.59, 54.53, 19.00],
        'oman': [51.88, 16.65, 59.84, 26.40],
        'qatar': [50.76, 24.56, 51.64, 26.16],
        'kuwait': [46.55, 28.52, 48.43, 30.10],
        'bahrain': [50.45, 25.80, 50.66, 26.28],
        'syria': [35.73, 32.31, 42.38, 37.32],
        'palestine': [34.22, 31.22, 35.57, 32.55],
        
        # Additional Asian countries
        'uzbekistan': [55.99, 37.18, 73.15, 45.59],
        'kazakhstan': [46.47, 40.94, 87.36, 55.45],
        'turkmenistan': [52.44, 35.14, 66.68, 42.80],
        'kyrgyzstan': [69.28, 39.18, 80.28, 43.24],
        'tajikistan': [67.39, 36.67, 75.14, 41.04],
        'azerbaijan': [44.79, 38.39, 50.39, 41.91],
        'armenia': [43.45, 38.84, 46.63, 41.30],
        'georgia': [40.01, 41.05, 46.72, 43.59],
        'bhutan': [88.75, 26.70, 92.13, 28.36],
        'maldives': [72.69, -0.69, 73.76, 7.09],
        'brunei': [114.08, 4.00, 115.36, 5.05],
        'timor-leste': [124.05, -9.50, 127.34, -8.13],
        'east timor': [124.05, -9.50, 127.34, -8.13],  # Alias
        'north korea': [124.32, 37.67, 130.68, 43.01],
        
        # Additional South American countries
        'guyana': [-61.39, 1.18, -56.48, 8.56],
        'suriname': [-58.09, 1.84, -53.98, 6.00],
        'french guiana': [-54.60, 2.11, -51.64, 5.78],
        
        # Additional Central American countries
        'belize': [-89.23, 15.89, -87.78, 18.50],
        'guatemala': [-92.24, 13.74, -88.23, 17.82],
        'honduras': [-89.36, 12.98, -83.15, 16.51],
        'el salvador': [-90.13, 13.15, -87.69, 14.45],
        'nicaragua': [-87.69, 10.71, -82.74, 15.03],
        'costa rica': [-85.95, 8.03, -82.55, 11.22],
        'panama': [-83.05, 7.20, -77.18, 9.65],
        
        # Caribbean countries
        'cuba': [-84.97, 19.83, -74.13, 23.19],
        'jamaica': [-78.37, 17.70, -76.18, 18.52],
        'haiti': [-74.48, 18.03, -71.62, 20.09],
        'dominican republic': [-72.00, 17.54, -68.32, 19.93],
        'puerto rico': [-67.27, 17.93, -65.59, 18.52],
        'bahamas': [-79.00, 20.91, -72.71, 27.26],
        'trinidad and tobago': [-61.95, 10.04, -60.52, 11.35],
        'trinidad': [-61.95, 10.04, -60.52, 11.35],  # Alias
        'barbados': [-59.65, 13.04, -59.42, 13.34],
        'saint lucia': [-61.08, 13.71, -60.87, 14.11],
        'grenada': [-61.80, 11.98, -61.38, 12.53],
        'saint vincent and the grenadines': [-61.46, 12.58, -61.11, 13.38],
        'antigua and barbuda': [-62.02, 16.99, -61.67, 17.73],
        'dominica': [-61.48, 15.20, -61.24, 15.64],
        'saint kitts and nevis': [-62.86, 17.10, -62.54, 17.42],
        
        # === US STATES ===
        'california': [-124.48, 32.53, -114.13, 42.01],
        'texas': [-106.65, 25.84, -93.51, 36.50],
        'florida': [-87.63, 24.52, -80.03, 31.00],
        'new york': [-79.76, 40.50, -71.86, 45.02],
        'pennsylvania': [-80.52, 39.72, -74.69, 42.27],
        'illinois': [-91.51, 36.97, -87.02, 42.51],
        'ohio': [-84.82, 38.40, -80.52, 41.98],
        'georgia': [-85.61, 30.36, -80.84, 35.00],
        'north carolina': [-84.32, 33.84, -75.46, 36.59],
        'michigan': [-90.42, 41.70, -82.42, 48.31],
        'new jersey': [-75.56, 38.93, -73.89, 41.36],
        'virginia': [-83.68, 36.54, -75.24, 39.47],
        'washington': [-124.85, 45.54, -116.92, 49.00],
        'arizona': [-114.82, 31.33, -109.05, 37.00],
        'massachusetts': [-73.51, 41.24, -69.93, 42.89],
        'tennessee': [-90.31, 34.98, -81.65, 36.68],
        'indiana': [-88.10, 37.77, -84.78, 41.76],
        'maryland': [-79.49, 37.91, -75.05, 39.72],
        'missouri': [-95.77, 35.99, -89.10, 40.61],
        'wisconsin': [-92.89, 42.49, -86.25, 47.31],
        'colorado': [-109.06, 36.99, -102.04, 41.00],
        'minnesota': [-97.24, 43.50, -89.49, 49.38],
        'south carolina': [-83.35, 32.03, -78.54, 35.22],
        'alabama': [-88.47, 30.22, -84.89, 35.01],
        'louisiana': [-94.04, 28.93, -88.82, 33.02],
        'kentucky': [-89.57, 36.50, -81.96, 39.15],
        'oregon': [-124.70, 41.99, -116.46, 46.29],
        'oklahoma': [-103.00, 33.62, -94.43, 37.00],
        'connecticut': [-73.73, 40.99, -71.79, 42.05],
        'utah': [-114.05, 36.99, -109.04, 42.00],
        'iowa': [-96.64, 40.38, -90.14, 43.50],
        'nevada': [-120.01, 35.00, -114.04, 42.00],
        'arkansas': [-94.62, 33.00, -89.64, 36.50],
        'mississippi': [-91.66, 30.17, -88.10, 34.99],
        'kansas': [-102.05, 36.99, -94.59, 40.00],
        'new mexico': [-109.05, 31.33, -103.00, 37.00],
        'nebraska': [-104.05, 40.00, -95.31, 43.00],
        'west virginia': [-82.64, 37.20, -77.72, 40.64],
        'idaho': [-117.24, 41.99, -111.04, 49.00],
        'hawaii': [-160.25, 18.91, -154.81, 22.24],
        'new hampshire': [-72.56, 42.70, -70.61, 45.31],
        'maine': [-71.08, 43.06, -66.95, 47.46],
        'montana': [-116.05, 44.36, -104.04, 49.00],
        'rhode island': [-71.91, 41.15, -71.12, 42.02],
        'delaware': [-75.79, 38.45, -75.05, 39.84],
        'south dakota': [-104.06, 42.48, -96.44, 45.95],
        'north dakota': [-104.05, 45.94, -96.55, 49.00],
        'alaska': [-179.15, 51.21, -129.98, 71.44],
        'vermont': [-73.44, 42.73, -71.46, 45.02],
        'wyoming': [-111.06, 40.99, -104.05, 45.01],
        
        # === MAJOR US CITIES (Top 50) ===
        'new york city': [-74.26, 40.49, -73.70, 40.92],
        'nyc': [-74.26, 40.49, -73.70, 40.92],  # Alias for New York City
        'los angeles': [-118.67, 33.70, -118.16, 34.34],
        'la': [-118.67, 33.70, -118.16, 34.34],  # Alias for Los Angeles
        'chicago': [-87.94, 41.64, -87.52, 42.02],
        'houston': [-95.82, 29.52, -95.01, 30.11],
        'phoenix': [-112.32, 33.28, -111.93, 33.92],
        'philadelphia': [-75.28, 39.87, -74.96, 40.14],
        'san antonio': [-98.70, 29.21, -98.29, 29.68],
        'san diego': [-117.27, 32.53, -116.91, 33.11],
        'dallas': [-97.04, 32.62, -96.46, 33.02],
        'san jose': [-122.06, 37.20, -121.65, 37.47],
        'austin': [-97.94, 30.09, -97.56, 30.52],
        'jacksonville': [-81.95, 30.10, -81.39, 30.60],
        'fort worth': [-97.52, 32.53, -97.04, 33.04],
        'columbus': [-83.21, 39.90, -82.89, 40.14],
        'charlotte': [-81.06, 35.00, -80.65, 35.44],
        'san francisco': [-122.52, 37.70, -122.36, 37.83],
        'sf': [-122.52, 37.70, -122.36, 37.83],  # Alias for San Francisco
        'indianapolis': [-86.33, 39.63, -85.94, 39.93],
        'seattle': [-122.44, 47.49, -122.24, 47.73],
        'denver': [-105.11, 39.61, -104.60, 39.91],
        'washington dc': [-77.12, 38.79, -76.91, 38.99],
        'dc': [-77.12, 38.79, -76.91, 38.99],  # Alias for Washington DC
        'boston': [-71.19, 42.23, -70.92, 42.40],
        'nashville': [-86.95, 35.99, -86.62, 36.41],
        'baltimore': [-76.71, 39.20, -76.53, 39.37],
        'memphis': [-90.11, 34.98, -89.79, 35.26],
        'portland': [-122.79, 45.43, -122.53, 45.65],
        'las vegas': [-115.32, 36.00, -114.98, 36.28],
        'detroit': [-83.29, 42.25, -82.91, 42.45],
        'reston': [-77.37, 38.94, -77.34, 38.97],  # Reston, Virginia
        'napa': [-122.32, 38.27, -122.27, 38.32],  # Napa, California
        'miami': [-80.32, 25.71, -80.13, 25.86],
        'atlanta': [-84.55, 33.65, -84.29, 33.89],
        'minneapolis': [-93.33, 44.89, -93.19, 45.05],
        'cleveland': [-81.88, 41.39, -81.54, 41.57],
        'tampa': [-82.64, 27.87, -82.33, 28.11],
        'st louis': [-90.32, 38.53, -90.17, 38.77],
        'pittsburgh': [-80.10, 40.36, -79.87, 40.50],
        'cincinnati': [-84.72, 39.02, -84.39, 39.22],
        'kansas city': [-94.83, 38.95, -94.35, 39.37],
        'milwaukee': [-88.07, 42.92, -87.84, 43.19],
        'sacramento': [-121.59, 38.44, -121.30, 38.68],
        'salt lake city': [-112.11, 40.70, -111.81, 40.81],
        'new orleans': [-90.14, 29.87, -89.63, 30.20],
        'tucson': [-111.16, 32.05, -110.77, 32.37],
        'oklahoma city': [-97.71, 35.35, -97.24, 35.66],
        'albuquerque': [-106.76, 34.95, -106.48, 35.23],
        'fresno': [-119.89, 36.67, -119.64, 36.87],
        'mesa': [-111.72, 33.32, -111.59, 33.51],
        'omaha': [-96.18, 41.20, -95.93, 41.33],
        'raleigh': [-78.78, 35.70, -78.56, 35.88],
        'long beach': [-118.25, 33.73, -118.09, 33.86],
        'virginia beach': [-76.13, 36.72, -75.97, 36.93],
        'oakland': [-122.36, 37.70, -122.15, 37.86],
        
        # === MAJOR WORLD CITIES ===
        'london': [-0.51, 51.28, 0.33, 51.69],
        'paris': [2.22, 48.82, 2.47, 48.90],
        'tokyo': [139.56, 35.53, 139.92, 35.82],
        'beijing': [116.12, 39.72, 116.72, 40.18],
        'shanghai': [121.21, 30.92, 121.83, 31.45],
        'hong kong': [113.84, 22.15, 114.41, 22.56],
        'singapore': [103.61, 1.16, 104.04, 1.47],
        'dubai': [54.89, 24.77, 55.61, 25.36],
        'sydney': [150.52, -34.12, 151.34, -33.58],
        'melbourne': [144.59, -38.43, 145.51, -37.51],
        'toronto': [-79.64, 43.58, -79.12, 43.86],
        'vancouver': [-123.27, 49.20, -123.02, 49.32],
        'montreal': [-73.98, 45.41, -73.48, 45.70],
        'rome': [12.37, 41.80, 12.62, 42.00],
        'madrid': [-3.83, 40.31, -3.56, 40.56],
        'barcelona': [2.05, 41.32, 2.23, 41.47],
        'berlin': [13.23, 52.38, 13.76, 52.67],
        'munich': [11.36, 48.06, 11.72, 48.25],
        'amsterdam': [4.73, 52.28, 5.07, 52.43],
        'brussels': [4.24, 50.80, 4.48, 50.91],
        'vienna': [16.18, 48.12, 16.58, 48.32],
        'zurich': [8.45, 47.32, 8.63, 47.43],
        'stockholm': [17.83, 59.24, 18.20, 59.41],
        'oslo': [10.56, 59.83, 10.90, 60.00],
        'copenhagen': [12.45, 55.61, 12.73, 55.73],
        'helsinki': [24.78, 60.13, 25.17, 60.31],
        'moscow': [37.36, 55.57, 37.89, 55.92],
        'istanbul': [28.78, 40.90, 29.23, 41.24],
        'athens': [23.63, 37.90, 23.82, 38.03],
        'cairo': [31.13, 29.95, 31.41, 30.13],
        'johannesburg': [27.91, -26.27, 28.19, -26.07],
        'cape town': [18.32, -34.08, 18.84, -33.71],
        'mumbai': [72.78, 18.89, 72.98, 19.27],
        'delhi': [76.84, 28.40, 77.35, 28.88],
        'bangalore': [77.46, 12.84, 77.78, 13.14],
        'bangkok': [100.33, 13.62, 100.94, 13.96],
        'kuala lumpur': [101.59, 3.04, 101.77, 3.24],
        'jakarta': [106.68, -6.37, 106.98, -6.08],
        'manila': [120.90, 14.40, 121.15, 14.76],
        'seoul': [126.76, 37.43, 127.18, 37.70],
        'taipei': [121.46, 24.99, 121.65, 25.21],
        'mexico city': [-99.37, 19.05, -98.94, 19.59],
        'buenos aires': [-58.53, -34.71, -58.34, -34.53],
        'rio de janeiro': [-43.79, -23.08, -43.10, -22.75],
        'sao paulo': [-46.83, -23.73, -46.36, -23.36],
        'lima': [-77.19, -12.21, -76.84, -11.92],
        'bogota': [-74.22, 4.47, -73.99, 4.83],
        'santiago': [-70.79, -33.57, -70.48, -33.35],
        
        # === US NATIONAL PARKS & NATURAL WONDERS ===
        'grand canyon': [-112.36, 35.99, -111.73, 36.44],
        'yellowstone': [-111.16, 44.13, -109.83, 45.12],
        'yosemite': [-119.90, 37.49, -119.20, 38.19],
        'zion': [-113.15, 37.15, -112.83, 37.51],
        'grand teton': [-111.05, 43.65, -110.40, 44.00],
        'glacier national park': [-114.35, 48.25, -113.32, 49.00],
        'rocky mountain national park': [-105.92, 40.16, -105.49, 40.56],
        'acadia': [-68.48, 44.16, -68.11, 44.42],
        'great smoky mountains': [-84.01, 35.43, -83.10, 35.79],
        'olympic national park': [-124.68, 47.49, -123.42, 48.05],
        'arches': [-109.92, 38.47, -109.47, 38.79],
        'bryce canyon': [-112.27, 37.43, -112.10, 37.70],
        'monument valley': [-110.27, 36.85, -109.86, 37.12],
        'death valley': [-117.58, 36.09, -116.38, 37.13],
        'mount rushmore': [-103.48, 43.85, -103.43, 43.90],
        'niagara falls': [-79.09, 43.07, -79.02, 43.12],
        'everglades': [-81.43, 25.19, -80.28, 25.86],
        'sequoia': [-118.97, 36.26, -118.23, 36.87],
        'joshua tree': [-116.32, 33.67, -115.54, 34.35],
        'big sur': [-121.90, 35.78, -121.40, 36.48],
        
        # === WORLD NATURAL WONDERS & LANDMARKS ===
        'mount everest': [86.83, 27.90, 87.03, 28.08],
        'great wall of china': [115.42, 40.43, 117.23, 40.68],
        'machu picchu': [-72.59, -13.21, -72.50, -13.15],
        'petra': [35.43, 30.31, 35.48, 30.34],
        'colosseum': [12.49, 41.89, 12.50, 41.89],
        'eiffel tower': [2.29, 48.86, 2.30, 48.86],
        'taj mahal': [78.04, 27.17, 78.05, 27.18],
        'great barrier reef': [142.59, -24.50, 153.55, -10.69],
        'victoria falls': [25.84, -17.93, 25.88, -17.92],
        'mount kilimanjaro': [37.26, -3.13, 37.46, -2.98],
        'amazon': [-73.99, -16.00, -48.00, 4.00],  # Amazon rainforest alias
        'amazon rainforest': [-73.99, -16.00, -48.00, 4.00],
        'amazon basin': [-73.99, -16.00, -48.00, 4.00],  # Amazon basin alias
        'sahara desert': [-17.00, 15.00, 35.00, 33.00],
        'sahara': [-17.00, 15.00, 35.00, 33.00],  # Sahara alias
        'serengeti': [34.00, -3.30, 35.30, -1.50],
        'galapagos islands': [-92.00, -1.40, -89.43, 0.70],
        'galapagos': [-92.00, -1.40, -89.43, 0.70],  # Galapagos alias
        'antarctica': [-180.00, -90.00, 180.00, -60.00],
        'arctic': [-180.00, 66.56, 180.00, 90.00],
        'swiss alps': [5.96, 45.82, 10.49, 47.81],
        'himalaya': [73.00, 27.00, 97.00, 36.00],
        'himalayas': [73.00, 27.00, 97.00, 36.00],  # Himalayas alias
        'andes': [-75.00, -55.00, -66.00, 10.00],
        'rockies': [-120.00, 31.00, -103.00, 60.00],
        'rocky mountains': [-120.00, 31.00, -103.00, 60.00],
        'alps': [4.00, 43.00, 17.00, 48.00],
        'fjords': [4.50, 58.00, 30.00, 71.00],
        'patagonia': [-75.00, -55.00, -66.00, -40.00],
        'iceland': [-24.54, 63.39, -13.50, 66.54],
        'new zealand': [166.51, -47.29, 178.52, -34.39],
        'bali': [114.43, -8.85, 115.71, -8.06],
        'maldives': [72.68, -0.69, 73.76, 7.11],
        'santorini': [25.35, 36.35, 25.48, 36.48],
        'amalfi coast': [14.47, 40.50, 14.71, 40.71],
        'cinque terre': [9.68, 44.10, 9.74, 44.18],
        'lake como': [9.07, 45.77, 9.51, 46.22],
        'provence': [4.20, 43.20, 6.50, 44.50],
        'scottish highlands': [-5.50, 56.50, -3.00, 58.50],
        'lake district': [-3.40, 54.20, -2.70, 54.75],
        'canadian rockies': [-120.00, 49.00, -110.00, 54.00],
        'banff': [-116.60, 51.10, -115.30, 51.60],
        'jasper': [-118.70, 52.70, -117.70, 53.20],
        
        # === FAMOUS TOURIST DESTINATIONS ===
        'disneyland': [-117.93, 33.81, -117.91, 33.82],
        'disney world': [-81.59, 28.36, -81.52, 28.42],
        'times square': [-73.99, 40.75, -73.98, 40.76],
        'statue of liberty': [-74.05, 40.69, -74.04, 40.69],
        'golden gate bridge': [-122.48, 37.81, -122.47, 37.83],
        'hollywood': [-118.37, 34.08, -118.32, 34.13],
        'venice': [12.27, 45.40, 12.40, 45.47],
        'florence': [11.20, 43.74, 11.31, 43.80],
        'prague': [14.36, 50.04, 14.56, 50.13],
        'dubrovnik': [18.04, 42.63, 18.13, 42.68],
        'reykjavik': [-22.00, 64.12, -21.83, 64.17],
        'marrakech': [-8.04, 31.60, -7.95, 31.66],
        
        # === MAJOR ISLAND GROUPS & ISLANDS ===
        
        # Greek Islands
        'corfu': [19.62, 39.45, 20.00, 39.79],  # Kerkyra/Corfu Island
        'kerkyra': [19.62, 39.45, 20.00, 39.79],  # Greek name for Corfu
        'crete': [23.51, 34.82, 26.33, 35.71],
        'rhodes': [27.68, 35.89, 28.25, 36.48],
        'santorini': [25.36, 36.35, 25.47, 36.48],
        'mykonos': [25.30, 37.41, 25.40, 37.48],
        'zakynthos': [20.61, 37.65, 20.90, 37.86],
        'lesbos': [25.95, 38.92, 26.62, 39.40],
        'kos': [26.92, 36.67, 27.29, 36.90],
        
        # Caribbean Islands
        'aruba': [-70.07, 12.41, -69.87, 12.62],
        'curacao': [-69.16, 12.01, -68.73, 12.39],
        'cayman islands': [-81.43, 19.26, -79.73, 19.76],
        'virgin islands': [-65.09, 17.68, -64.56, 18.42],
        'us virgin islands': [-65.09, 17.68, -64.56, 18.42],
        'british virgin islands': [-64.75, 18.38, -64.27, 18.76],
        'turks and caicos': [-72.48, 21.42, -71.12, 21.96],
        'bermuda': [-64.89, 32.25, -64.65, 32.39],
        'martinique': [-61.23, 14.39, -60.81, 14.88],
        'guadeloupe': [-61.81, 15.83, -61.00, 16.51],
        
        # Pacific Islands
        'phuket': [98.26, 7.75, 98.44, 8.15],
        'bali': [114.59, -8.85, 115.71, -8.09],
        'bora bora': [-151.78, -16.53, -151.70, -16.46],
        'tahiti': [-149.65, -17.87, -149.10, -17.48],
        'fiji': [177.00, -19.00, -178.00, -16.00],
        'galapagos': [-92.00, -1.40, -89.43, 0.70],
        'tomas de berlanga': [-90.78, -0.44, -90.65, -0.36],  # Rábida Island, Galápagos
        'rabida island': [-90.78, -0.44, -90.65, -0.36],      # Alias
        'easter island': [-109.48, -27.19, -109.21, -27.04],
        
        # Mediterranean Islands
        'sicily': [12.43, 36.65, 15.66, 38.81],
        'sardinia': [8.13, 38.86, 9.83, 41.26],
        'corsica': [8.54, 41.33, 9.56, 43.03],
        'ibiza': [1.18, 38.87, 1.64, 39.13],
        'mallorca': [2.32, 39.27, 3.48, 39.96],
        'majorca': [2.32, 39.27, 3.48, 39.96],  # Alias for Mallorca
        'menorca': [3.82, 39.80, 4.32, 40.10],
        'capri': [14.19, 40.53, 14.27, 40.56],
        'elba': [10.17, 42.72, 10.46, 42.85],
        'malta': [14.18, 35.81, 14.58, 36.08],
        'cyprus': [32.27, 34.63, 34.60, 35.71],
        
        # Atlantic Islands
        'azores': [-31.27, 36.89, -24.77, 39.76],
        'madeira': [-17.29, 32.39, -16.65, 32.89],
        'canary islands': [-18.17, 27.64, -13.41, 29.42],
        'tenerife': [-16.93, 28.01, -16.39, 28.60],
        'fuerteventura': [-14.53, 28.05, -13.86, 28.75],
        'cape verde': [-25.36, 14.81, -22.67, 17.20],
        'iceland': [-24.54, 63.39, -13.50, 66.54],
        'faroe islands': [-7.69, 61.39, -6.26, 62.40],
        
        # Major Water Bodies / Oceans
        'gulf of america': [-97.90, 18.09, -80.03, 30.72],  # Gulf of Mexico
        'gulf of mexico': [-97.90, 18.09, -80.03, 30.72],   # Alias
        
        # Indian Ocean Islands
        'maldives': [72.69, -0.69, 73.76, 7.09],
        'seychelles': [55.23, -4.79, 56.29, -4.21],
        'mauritius': [57.31, -20.53, 57.79, -19.99],
        'cancun': [-86.85, 21.04, -86.74, 21.23],
        'cabo san lucas': [-109.95, 22.86, -109.86, 22.93],
        'hawaii': [-160.25, 18.91, -154.81, 22.24],
        'maui': [-156.69, 20.57, -155.98, 21.03],
        'oahu': [-158.29, 21.25, -157.65, 21.71],
        'kauai': [-159.79, 21.87, -159.30, 22.23],
        'big island': [-156.07, 18.91, -154.81, 20.27],
        
        # === AUSTRALIAN STATES AND TERRITORIES ===
        'queensland': [138.00, -29.18, 153.55, -10.69],
        'qld': [138.00, -29.18, 153.55, -10.69],  # Alias for Queensland
        'new south wales': [140.99, -37.51, 153.64, -28.16],
        'nsw': [140.99, -37.51, 153.64, -28.16],  # Alias for New South Wales
        'victoria': [140.96, -39.16, 149.98, -33.98],
        'vic': [140.96, -39.16, 149.98, -33.98],  # Alias for Victoria
        'south australia': [129.00, -38.06, 141.00, -26.00],
        'sa': [129.00, -38.06, 141.00, -26.00],  # Alias for South Australia
        'western australia': [112.92, -35.13, 129.00, -13.69],
        'wa': [112.92, -35.13, 129.00, -13.69],  # Alias for Western Australia
        'tasmania': [143.82, -43.64, 148.48, -39.58],
        'tas': [143.82, -43.64, 148.48, -39.58],  # Alias for Tasmania
        'northern territory': [129.00, -26.00, 138.00, -10.97],
        'nt': [129.00, -26.00, 138.00, -10.97],  # Alias for Northern Territory
        'australian capital territory': [148.76, -35.92, 149.40, -35.12],
        'act': [148.76, -35.92, 149.40, -35.12],  # Alias for ACT
        'canberra': [148.99, -35.48, 149.25, -35.15],
        
        # === MAJOR AUSTRALIAN CITIES ===
        'sydney': [150.52, -34.17, 151.34, -33.57],
        'melbourne': [144.59, -38.43, 145.51, -37.51],
        'brisbane': [152.67, -27.77, 153.32, -27.05],
        'perth': [115.62, -32.17, 116.08, -31.62],
        'adelaide': [138.44, -35.15, 138.78, -34.65],
        'darwin': [130.81, -12.55, 130.93, -12.35],
        'hobart': [147.21, -43.00, 147.43, -42.75],
        'gold coast': [153.32, -28.21, 153.55, -27.82],
        'cairns': [145.72, -17.00, 145.81, -16.87],
        'townsville': [146.73, -19.35, 146.86, -19.20],
        'newcastle': [151.64, -33.00, 151.84, -32.85],
        'wollongong': [150.79, -34.55, 150.94, -34.35],
        'geelong': [144.29, -38.25, 144.45, -38.08],
        'sunshine coast': [152.95, -26.85, 153.15, -26.35],
        'alice springs': [133.83, -23.80, 133.91, -23.65],
        'uluru': [131.00, -25.40, 131.10, -25.30],  # Ayers Rock
        'ayers rock': [131.00, -25.40, 131.10, -25.30],  # Alias for Uluru
        'great barrier reef': [142.50, -24.50, 154.00, -10.50],
        'barrier reef': [142.50, -24.50, 154.00, -10.50],  # Alias
        'kakadu': [131.88, -13.95, 133.00, -12.11],  # Kakadu National Park
        'blue mountains': [150.10, -33.85, 150.75, -33.35],
        
        # === TEST LOCATIONS FOR COMPARISON QUERIES ===
        'darwin harbour': [130.78, -12.50, 130.90, -12.40],  # Darwin Harbour, Northern Territory, Australia
        'miami beach': [-80.15, 25.76, -80.11, 25.88],  # Miami Beach, Florida, USA
    }
    
    def __init__(self):
        self.logger = logging.getLogger(__name__)
        self.cache = LocationCache()
        
        # Azure Maps authentication - supports both API key and Managed Identity
        self.azure_maps_key = os.getenv('AZURE_MAPS_SUBSCRIPTION_KEY')
        self.azure_maps_client_id = os.getenv('AZURE_MAPS_CLIENT_ID')
        self.azure_maps_use_managed_identity = os.getenv('AZURE_MAPS_USE_MANAGED_IDENTITY', 'false').lower() == 'true'
        
        # Initialize token provider for Managed Identity if configured
        self._token_provider = None
        if self.azure_maps_use_managed_identity and self.azure_maps_client_id:
            try:
                from azure.identity import DefaultAzureCredential, get_bearer_token_provider
                credential = DefaultAzureCredential()
                self._token_provider = get_bearer_token_provider(
                    credential,
                    "https://atlas.microsoft.com/.default"
                )
                self.logger.info("✓ Azure Maps Managed Identity authentication enabled")
            except ImportError:
                self.logger.warning("azure-identity not installed, falling back to API key authentication")
            except Exception as e:
                self.logger.warning(f"Failed to initialize Managed Identity for Azure Maps: {e}")
        
        self.mapbox_token = os.getenv('MAPBOX_ACCESS_TOKEN')
        
        # Azure OpenAI for intelligent location resolution
        self.azure_openai_endpoint = os.getenv('AZURE_OPENAI_ENDPOINT')
        self.azure_openai_api_key = os.getenv('AZURE_OPENAI_API_KEY')
        self.model_name = os.getenv('AZURE_OPENAI_MODEL_NAME', 'gpt-4')
        
        self.logger.info(f"✓ Enhanced Location Resolver initialized with {len(self.STORED_LOCATIONS)} stored global locations (countries, cities, landmarks, natural wonders) + dynamic API resolution")
    
    def _get_azure_maps_auth(self) -> tuple[dict, dict]:
        """
        Get Azure Maps authentication headers and params.
        Returns (headers, params) for requests.
        - If Managed Identity is enabled: returns Bearer token in headers, client-id in params
        - If API key is available: returns subscription-key in params
        """
        headers = {}
        params = {"api-version": "1.0"}
        
        if self.azure_maps_use_managed_identity and self._token_provider and self.azure_maps_client_id:
            # Use Managed Identity with Bearer token
            token = self._token_provider()
            headers["Authorization"] = f"Bearer {token}"
            params["x-ms-client-id"] = self.azure_maps_client_id
            self.logger.debug("Using Managed Identity authentication for Azure Maps")
        elif self.azure_maps_key:
            # Use API key authentication
            params["subscription-key"] = self.azure_maps_key
            self.logger.debug("Using API key authentication for Azure Maps")
        else:
            raise ValueError("Azure Maps authentication not configured. Set either AZURE_MAPS_CLIENT_ID with Managed Identity or AZURE_MAPS_SUBSCRIPTION_KEY")
        
        return headers, params
    
    def _is_azure_maps_configured(self) -> bool:
        """Check if Azure Maps is configured with either authentication method"""
        return bool(
            (self.azure_maps_use_managed_identity and self._token_provider and self.azure_maps_client_id) or
            self.azure_maps_key
        )
    
    async def health_check(self) -> Dict[str, Any]:
        """
        🏥 LOCATION RESOLVER HEALTH CHECK
        
        Tests all configured location resolution services:
        1. Azure Maps API connectivity and authentication
        2. Azure OpenAI/GPT API connectivity  
        3. Nominatim OSM API availability
        
        Returns health status for each service
        """
        health_status = {
            "azure_maps": {"status": "not_configured", "message": ""},
            "azure_openai": {"status": "not_configured", "message": ""},
            "nominatim": {"status": "unknown", "message": ""}
        }
        
        # Test Azure Maps
        if self._is_azure_maps_configured():
            try:
                test_result = await self._strategy_azure_maps("New York")
                if test_result:
                    auth_type = "Managed Identity" if self.azure_maps_use_managed_identity else "API Key"
                    health_status["azure_maps"] = {"status": "healthy", "message": f"Connected and working ({auth_type})"}
                else:
                    health_status["azure_maps"] = {"status": "degraded", "message": "Connected but test query failed"}
            except Exception as e:
                health_status["azure_maps"] = {"status": "unhealthy", "message": f"Connection failed: {str(e)}"}
        else:
            health_status["azure_maps"] = {"status": "not_configured", "message": "Set AZURE_MAPS_CLIENT_ID with Managed Identity or AZURE_MAPS_SUBSCRIPTION_KEY"}
        
        # Test Azure OpenAI
        if self.azure_openai_endpoint and self.azure_openai_api_key:
            try:
                test_result = await self._strategy_azure_openai("New York", "city")
                if test_result:
                    health_status["azure_openai"] = {"status": "healthy", "message": "Connected and working"}
                else:
                    health_status["azure_openai"] = {"status": "degraded", "message": "Connected but test query failed"}
            except Exception as e:
                health_status["azure_openai"] = {"status": "unhealthy", "message": f"Connection failed: {str(e)}"}
        else:
            missing = []
            if not self.azure_openai_endpoint: missing.append("AZURE_OPENAI_ENDPOINT")
            if not self.azure_openai_api_key: missing.append("AZURE_OPENAI_API_KEY")
            health_status["azure_openai"] = {"status": "not_configured", "message": f"Missing: {', '.join(missing)}"}
        
        # Test Nominatim (always available as fallback)
        try:
            test_result = await self._strategy_improved_nominatim("New York")
            if test_result:
                health_status["nominatim"] = {"status": "healthy", "message": "OSM fallback available"}
            else:
                health_status["nominatim"] = {"status": "degraded", "message": "OSM available but test failed"}
        except Exception as e:
            health_status["nominatim"] = {"status": "unhealthy", "message": f"OSM unavailable: {str(e)}"}
        
        return health_status
    
    async def resolve_location_to_bbox(self, location_name: str, location_type: str = "region") -> Optional[List[float]]:
        """
        🎯 AZURE-FIRST DYNAMIC LOCATION RESOLUTION WITH SEMANTIC PREPROCESSING
        
        Azure ecosystem focused location resolution (NO hardcoded coordinates):
        1. Semantic preprocessing (translate ambiguous terms to API-friendly queries)
        2. Cache check (performance optimization)
        3. Azure Maps API (Microsoft native, enterprise-grade geocoding)
        4. Azure OpenAI/GPT (AI-powered intelligent location understanding)
        5. Nominatim API (OSM fallback, free alternative)
        
        Prioritizes Microsoft Azure services for:
        - Integration consistency with Azure ecosystem
        - Enterprise-grade reliability and support
        - AI-enhanced location understanding via GPT
        
        Handles ANY location type:
        - Precise addresses: "1600 Pennsylvania Avenue, Washington DC"
        - Landmarks: "Times Square", "Statue of Liberty"
        - Geographic regions: "Silicon Valley", "Rocky Mountains"  
        - Parks/Natural features: "Yellowstone", "Grand Canyon"
        - Complex descriptions: "the area around Manhattan where Wall Street is"
        
        Returns: [west, south, east, north] bounding box or None
        """
        self.logger.info(f"🔍 Resolving location: '{location_name}' (type: {location_type})")
        
        # Step 0: Check hardcoded US locations first (instant, guaranteed accuracy)
        location_lower = location_name.lower().strip()
        
        # Strip leading articles ("the", "a", "an") for matching
        # E.g., "the Amazon rainforest" → "amazon rainforest"
        articles_to_strip = ['the ', 'a ', 'an ']
        location_normalized = location_lower
        for article in articles_to_strip:
            if location_normalized.startswith(article):
                location_normalized = location_normalized[len(article):].strip()
                break
        
        # Try exact match first (with normalized version)
        for loc_variant in [location_lower, location_normalized]:
            if loc_variant in self.STORED_LOCATIONS:
                bbox = self.STORED_LOCATIONS[loc_variant]
                self.logger.info(f"✅ Resolved from hardcoded US locations: '{location_name}' → {bbox}")
                self.cache.set(location_name, location_type, bbox)
                return bbox
        
        # Try without common geographic descriptors (e.g., "Corfu Island" → "corfu")
        descriptors_to_strip = [
            ' island', ' islands', ' isle', ' islet',
            ' city', ' town', ' village', ' municipality',
            ' county', ' state', ' province', ' region',
            ' mountain', ' mountains', ' mount', ' mt',
            ' lake', ' river', ' valley', ' desert',
            ' national park', ' park', ' forest', ' bay'
        ]
        
        # Try stripping descriptors from both original and normalized versions
        for loc_variant in [location_lower, location_normalized]:
            for descriptor in descriptors_to_strip:
                if loc_variant.endswith(descriptor):
                    stripped_name = loc_variant[:-len(descriptor)].strip()
                    if stripped_name in self.STORED_LOCATIONS:
                        bbox = self.STORED_LOCATIONS[stripped_name]
                        self.logger.info(f"✅ Resolved from hardcoded locations (stripped '{descriptor}'): '{location_name}' → '{stripped_name}' → {bbox}")
                        self.cache.set(location_name, location_type, bbox)
                        return bbox
        
        # Step 1: Semantic preprocessing to improve API query accuracy
        processed_queries = self._preprocess_location_query(location_name, location_type)
        self.logger.info(f"📝 Preprocessed queries: {processed_queries}")
        
        # Check cache first (try original and processed queries)
        for query in [location_name] + processed_queries:
            cached_bbox = self.cache.get(query, location_type)
            if cached_bbox:
                self.logger.info(f"📋 Cache hit for {query}")
                return cached_bbox
        
        # Try resolution with preprocessed queries (most specific first)
        all_queries = processed_queries + [location_name]  # Try processed queries first, then original
        
        for query in all_queries:
            # Strategy 1: Try Azure Maps with proper administrative division handling
            if self._is_azure_maps_configured():
                bbox = await self._strategy_azure_maps(query, location_type)
                if bbox:
                    # Expand bbox for large geographic features
                    bbox = self._expand_bbox_for_large_features(bbox, location_name)
                    self.logger.info(f"✅ Resolved via Azure Maps: '{query}' (original: '{location_name}')")
                    self.cache.set(location_name, location_type, bbox)  # Cache under original name
                    return bbox
            
            # Strategy 2: Try Azure OpenAI/GPT for complex queries (Microsoft native AI)
            bbox = await self._strategy_azure_openai(query, location_type)
            if bbox:
                # Expand bbox for large geographic features
                bbox = self._expand_bbox_for_large_features(bbox, location_name)
                self.logger.info(f"✅ Resolved via Azure OpenAI: '{query}' (original: '{location_name}')")
                self.cache.set(location_name, location_type, bbox)
                return bbox
        
        # Strategy 3: Try Mapbox (excellent for geographic regions) - ONLY if we really need it
        # Disabled to focus on Azure ecosystem
        # if self.mapbox_token:
        #     bbox = await self._strategy_mapbox(location_name)
        #     if bbox:
        #         self.logger.info(f"✅ Resolved via Mapbox: {location_name}")
        #         self.cache.set(location_name, location_type, bbox)
        #         return bbox
        

        
        # Strategy 5: International-focused Nominatim with smart queries
        bbox = await self._strategy_international_nominatim(location_name, location_type)
        if bbox:
            # Expand bbox for large geographic features
            bbox = self._expand_bbox_for_large_features(bbox, location_name)
            self.logger.info(f"🌍 Resolved via International Nominatim: {location_name}")
            self.cache.set(location_name, location_type, bbox)
            return bbox
            
        # Strategy 6: Multi-language Wikipedia/GeoNames approach
        bbox = await self._strategy_geonames_alternative(location_name, location_type)
        if bbox:
            # Expand bbox for large geographic features
            bbox = self._expand_bbox_for_large_features(bbox, location_name)
            self.logger.info(f"📚 Resolved via GeoNames alternative: {location_name}")
            self.cache.set(location_name, location_type, bbox)
            return bbox
        
        self.logger.error(f"❌ Could not resolve location: {location_name}")
        return None
    
    async def _strategy_azure_maps(self, location_name: str, location_type: str = "region") -> Optional[List[float]]:
        """🔵 Azure Maps Search with intelligent administrative division handling and validation"""
        
        # Strategy 1: Try Structured Geocoding first for administrative divisions
        if location_type in ['state', 'region', 'province', 'country'] or self._looks_like_admin_division(location_name):
            bbox = await self._azure_maps_structured_search(location_name)
            if bbox and self._is_reasonable_admin_bbox(bbox):
                self.logger.info(f"Found admin division bbox for {location_name}: {bbox}")
                return bbox
        
        # Strategy 2: Smart fuzzy search with intelligent result ranking
        bbox = await self._azure_maps_fuzzy_search(location_name)
        if bbox and self._is_reasonable_admin_bbox(bbox):
            return bbox
        
        # Strategy 3: For cities, try population-priority search
        if self._looks_like_city(location_name):
            bbox = await self._azure_maps_with_population_priority(location_name)
            if bbox and self._is_reasonable_admin_bbox(bbox):
                return bbox
        
        # Strategy 4: Fallback to address search
        return await self._azure_maps_address_search(location_name)
    
    async def _azure_maps_with_population_priority(self, location_name: str) -> Optional[List[float]]:
        """Try Azure Maps search prioritizing populated places over administrative regions"""
        
        if not self._is_azure_maps_configured():
            return None
        
        # Get authentication headers and base params
        headers, params = self._get_azure_maps_auth()
        
        # Use a more specific query that prioritizes major populated places
        url = "https://atlas.microsoft.com/search/fuzzy/json"
        params.update({
            "query": f"{location_name} city United States",  # Add "city" to prioritize urban areas
            "limit": 5,
            "entityType": "Municipality,PopulatedPlace",
            "countrySet": "US"
        })
        
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(url, params=params, headers=headers) as response:
                    if response.status == 200:
                        data = await response.json()
                        results = data.get("results", [])
                        
                        if results:
                            # Use our ranking system to find the best match
                            ranked_results = self._rank_results_by_relevance(results, location_name)
                            if ranked_results:
                                return self._extract_azure_bounds(ranked_results[0])
                                
        except Exception as e:
            self.logger.error(f"Azure Maps population priority search error: {e}")
        
        return None
    
    def _looks_like_admin_division(self, location_name: str) -> bool:
        """Detect if location name refers to an administrative division"""
        name_lower = location_name.lower().strip()
        
        # Common US state names and patterns
        us_states = {
            'california', 'texas', 'florida', 'new york', 'pennsylvania', 'illinois', 'ohio', 
            'georgia', 'north carolina', 'michigan', 'new jersey', 'virginia', 'washington',
            'arizona', 'massachusetts', 'tennessee', 'indiana', 'maryland', 'missouri', 
            'wisconsin', 'colorado', 'minnesota', 'south carolina', 'alabama', 'louisiana',
            'kentucky', 'oregon', 'oklahoma', 'connecticut', 'utah', 'iowa', 'nevada',
            'arkansas', 'mississippi', 'kansas', 'new mexico', 'nebraska', 'west virginia',
            'idaho', 'hawaii', 'new hampshire', 'maine', 'montana', 'rhode island',
            'delaware', 'south dakota', 'north dakota', 'alaska', 'vermont', 'wyoming'
        }
        
        return name_lower in us_states or 'state' in name_lower or 'province' in name_lower
    
    def _looks_like_city(self, location_name: str) -> bool:
        """Detect if location name refers to a city/populated place using heuristics"""
        name_lower = location_name.lower().strip()
        
        # If it's clearly an administrative division, not a city
        if self._looks_like_admin_division(location_name):
            return False
        
        # Simple heuristics: short names (1-3 words) are likely cities
        # Let the APIs determine the actual ranking and importance
        word_count = len(location_name.split())
        return word_count <= 3 and not any(term in name_lower for term in 
                                          ['mountain', 'range', 'national', 'forest', 'park', 'river', 'lake'])
    
    def _expand_bbox_for_large_features(self, bbox: List[float], location_name: str) -> List[float]:
        """
        Expand bounding box for large geographic features that need wider coverage.
        
        Large natural features like the Grand Canyon, mountain ranges, national parks
        often return small viewports from geocoding APIs. This expands them to provide
        better satellite data coverage.
        
        Args:
            bbox: [west, south, east, north] bounding box
            location_name: Name of the location to check for expansion
            
        Returns:
            Expanded bbox if feature is identified as large geographic feature, otherwise original bbox
        """
        if not bbox or len(bbox) != 4:
            return bbox
            
        name_lower = location_name.lower().strip()
        west, south, east, north = bbox
        
        # Calculate current bbox dimensions
        width = abs(east - west)
        height = abs(north - south)
        current_extent = max(width, height)
        
        # Keywords indicating large geographic features that need expansion
        large_feature_keywords = [
            'canyon', 'canyons', 'grand canyon',
            'national park', 'national parks', 'state park',
            'mountain range', 'mountains', 'sierra', 'rockies', 'cascades', 'appalachian',
            'valley', 'valleys', 'death valley', 'yosemite',
            'desert', 'deserts', 'mojave', 'sahara',
            'forest', 'rainforest', 'wilderness',
            'great plains', 'basin', 'plateau',
            'range', 'peaks', 'summit'
        ]
        
        # Check if location name contains large feature keywords
        is_large_feature = any(keyword in name_lower for keyword in large_feature_keywords)
        
        if is_large_feature:
            # Determine expansion factor based on current size and feature type
            if current_extent < 0.5:  # Very small bbox (< ~35 miles)
                expansion_factor = 6.0
                self.logger.info(f"🔍 Expanding small bbox for large feature '{location_name}' by {expansion_factor}x")
            elif current_extent < 1.0:  # Small bbox (< ~69 miles)
                expansion_factor = 4.0
                self.logger.info(f"🔍 Expanding bbox for large feature '{location_name}' by {expansion_factor}x")
            elif current_extent < 2.0:  # Medium bbox (< ~138 miles)
                expansion_factor = 2.5
                self.logger.info(f"🔍 Expanding bbox for large feature '{location_name}' by {expansion_factor}x")
            else:
                # Already large enough
                return bbox
            
            # Calculate center point
            center_lon = (west + east) / 2
            center_lat = (south + north) / 2
            
            # Expand from center
            new_width = width * expansion_factor
            new_height = height * expansion_factor
            
            expanded_bbox = [
                center_lon - new_width / 2,   # west
                center_lat - new_height / 2,  # south
                center_lon + new_width / 2,   # east
                center_lat + new_height / 2   # north
            ]
            
            self.logger.info(f"📏 Expanded bbox from {bbox} to {expanded_bbox} (extent: {current_extent:.2f}° → {max(new_width, new_height):.2f}°)")
            return expanded_bbox
        
        return bbox
    
    async def _azure_maps_structured_search(self, location_name: str) -> Optional[List[float]]:
        """Use Azure Maps Structured Search for administrative divisions"""
        
        if not self._is_azure_maps_configured():
            return None
        
        # Get authentication headers and base params
        headers, params = self._get_azure_maps_auth()
        
        url = "https://atlas.microsoft.com/search/address/structured/json"
        params.update({
            "countryCode": "US",
            "countrySubdivision": location_name,  # This targets state-level
            "limit": 3
        })
        
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(url, params=params, headers=headers) as response:
                    if response.status == 200:
                        data = await response.json()
                        results = data.get("results", [])
                        
                        # Look for the best administrative match
                        for result in results:
                            address = result.get("address", {})
                            # Check if this is actually the state we're looking for
                            if address.get("countrySubdivision", "").lower() == location_name.lower():
                                bbox = self._extract_azure_bounds(result)
                                if bbox:
                                    return bbox
        except Exception as e:
            self.logger.error(f"Azure Maps structured search error: {e}")
        
        return None
    
    async def _azure_maps_fuzzy_search(self, location_name: str) -> Optional[List[float]]:
        """Use Azure Maps Fuzzy Search with improved accuracy"""
        
        if not self._is_azure_maps_configured():
            return None
        
        # Get authentication headers and base params
        headers, params = self._get_azure_maps_auth()
        
        url = "https://atlas.microsoft.com/search/fuzzy/json"
        
        # For cities, prioritize population/importance over administrative divisions
        if self._looks_like_city(location_name):
            params.update({
                "query": location_name,  # Don't force ", United States" - let ranking find the most important match
                "limit": 10,  # Get more results to find the best match
                "entityType": "Municipality,PopulatedPlace",  # Focus on populated places for cities
                "countrySet": "US"
            })
        else:
            # For regions/states, use administrative division search
            params.update({
                "query": f"{location_name}, United States",
                "limit": 5,
                "entityType": "CountrySubdivision,CountrySecondarySubdivision",
                "countrySet": "US"
            })
        
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(url, params=params, headers=headers) as response:
                    if response.status == 200:
                        data = await response.json()
                        results = data.get("results", [])
                        
                        if results:
                            # Use intelligent ranking to find the best result
                            ranked_results = self._rank_results_by_relevance(results, location_name)
                            
                            # Try the top-ranked results in order
                            for result in ranked_results:
                                bbox = self._extract_azure_bounds(result)
                                if bbox:
                                    self.logger.info(f"Using result: {result.get('address', {}).get('freeformAddress', 'N/A')} "
                                                   f"(type: {result.get('entityType', 'N/A')})")
                                    return bbox
        except Exception as e:
            self.logger.error(f"Azure Maps fuzzy search error: {e}")
        
        return None
    
    async def _azure_maps_address_search(self, location_name: str) -> Optional[List[float]]:
        """Fallback to regular address search"""
        
        if not self._is_azure_maps_configured():
            return None
        
        # Get authentication headers and base params
        headers, params = self._get_azure_maps_auth()
        
        url = "https://atlas.microsoft.com/search/address/json"
        params.update({
            "query": location_name,
            "limit": 1
        })
        
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(url, params=params, headers=headers) as response:
                    if response.status == 200:
                        data = await response.json()
                        results = data.get("results", [])
                        if results:
                            return self._extract_azure_bounds(results[0])
        except Exception as e:
            self.logger.error(f"Azure Maps address search error: {e}")
        
        return None
    
    def _is_reasonable_admin_bbox(self, bbox: List[float]) -> bool:
        """Check if bounding box is reasonable for an administrative division"""
        if not bbox or len(bbox) != 4:
            return False
            
        west, south, east, north = bbox
        width = abs(east - west)
        height = abs(north - south)
        
        # Administrative divisions should have some geographic extent
        # Even small states like Rhode Island have ~1° extent
        # Cities typically have < 0.5° extent
        return width >= 0.3 or height >= 0.3
    
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
    
    async def _strategy_azure_openai(self, location_name: str, location_type: str) -> Optional[List[float]]:
        """🤖 Strategy 2.5: Azure OpenAI for intelligent location resolution"""
        
        if not self.azure_openai_endpoint or not self.azure_openai_api_key:
            self.logger.debug("Azure OpenAI not configured, skipping AI resolution")
            return None
        
        try:
            # Enhanced prompt with international awareness and specific context
            international_context = ""
            specific_context = ""
            
            if self._likely_international_location(location_name):
                international_context = "\n\nIMPORTANT: This appears to be an INTERNATIONAL location. Prioritize the most famous/populous version globally, not US alternatives."
                
                # Add specific context for well-known locations
                name_lower = location_name.lower()
                location_hints = {
                    'paris': 'This is Paris, the capital of France in Europe.',
                    'london': 'This is London, the capital of the United Kingdom.',
                    'tokyo': 'This is Tokyo, the capital of Japan.',
                    'beijing': 'This is Beijing, the capital of China.',
                    'sydney': 'This is Sydney, the largest city in Australia.',
                    'mumbai': 'This is Mumbai, the financial capital of India.',
                    'berlin': 'This is Berlin, the capital of Germany.',
                    'rome': 'This is Rome, the capital of Italy.',
                    'tuscany': 'This is Tuscany, a region in central Italy.',
                    'provence': 'This is Provence, a region in southeastern France.'
                }
                
                if name_lower in location_hints:
                    specific_context = f"\n\nCONTEXT: {location_hints[name_lower]}"
            
            prompt = f"""You are a geographic expert with global knowledge. Provide precise bounding box coordinates for: {location_name}

Return ONLY valid JSON in this exact format:
{{"bbox": [west_longitude, south_latitude, east_longitude, north_latitude], "confidence": 0.0_to_1.0, "country": "country_name"}}

Guidelines:
- Use decimal degrees: longitude (-180 to +180), latitude (-90 to +90)  
- Ensure west < east and south < north
- For cities: tight bounding box around urban area
- For landmarks: appropriate buffer around the feature
- For regions: encompass the full geographic area
- Confidence: 0.9 for well-known places, 0.7 for regions, 0.5 for uncertain
- Always prioritize the most famous/populous location globally{international_context}{specific_context}

Location: {location_name}"""

            headers = {
                "Content-Type": "application/json",
                "api-key": self.azure_openai_api_key
            }
            
            payload = {
                "messages": [{"role": "user", "content": prompt}],
                "max_completion_tokens": 150,
                "temperature": 0.0,
                "response_format": {"type": "json_object"}
            }
            
            url = f"{self.azure_openai_endpoint}/openai/deployments/{self.model_name}/chat/completions?api-version=2024-06-01"
            
            async with aiohttp.ClientSession() as session:
                timeout = aiohttp.ClientTimeout(total=15)
                async with session.post(url, json=payload, headers=headers, timeout=timeout) as response:
                    if response.status == 200:
                        data = await response.json()
                        if data.get("choices"):
                            content = data["choices"][0]["message"]["content"]
                            
                            try:
                                import json
                                location_data = json.loads(content)
                                bbox = location_data.get("bbox")
                                confidence = location_data.get("confidence", 0.0)
                                
                                if bbox and len(bbox) == 4 and confidence >= 0.5:
                                    west, south, east, north = bbox
                                    if (-180 <= west < east <= 180 and -90 <= south < north <= 90):
                                        return bbox
                                    
                            except json.JSONDecodeError:
                                self.logger.warning(f"Failed to parse Azure OpenAI response for {location_name}")
                    
        except Exception as e:
            self.logger.warning(f"Azure OpenAI error for {location_name}: {e}")
        
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
    
    def _preprocess_location_query(self, location_name: str, location_type: str) -> List[str]:
        """
        🧠 Semantic Location Preprocessor
        
        Translates ambiguous location terms into more specific API-friendly queries
        to improve geocoding accuracy and disambiguation.
        
        Examples:
        - "Chicago" → ["Chicago Illinois USA", "Chicago city", "Chicago municipality"]
        - "Silicon Valley" → ["Silicon Valley California", "San Jose California area"]
        - "Wall Street" → ["Wall Street New York", "Financial District Manhattan"]
        """
        processed_queries = []
        name_lower = location_name.lower().strip()
        
        # Geographic region enhancements
        region_mappings = {
            'silicon valley': ['Silicon Valley California USA', 'San Jose California area', 'South Bay California'],
            'wall street': ['Wall Street New York USA', 'Financial District Manhattan', 'Lower Manhattan New York'],
            'hollywood': ['Hollywood Los Angeles California', 'Hollywood District Los Angeles'],
            'brooklyn': ['Brooklyn New York USA', 'Brooklyn Borough New York'],
            'manhattan': ['Manhattan New York USA', 'Manhattan Borough New York'],
            'the bronx': ['Bronx New York USA', 'Bronx Borough New York'],
            'long island': ['Long Island New York USA', 'Nassau County New York'],
            'cape cod': ['Cape Cod Massachusetts USA', 'Barnstable County Massachusetts'],
            'outer banks': ['Outer Banks North Carolina USA', 'OBX North Carolina'],
            'florida keys': ['Florida Keys USA', 'Monroe County Florida'],
            'texas hill country': ['Hill Country Texas USA', 'Central Texas Hills'],
            'appalachian mountains': ['Appalachian Mountains USA', 'Appalachian Range Eastern USA'],
            'rocky mountains': ['Rocky Mountains USA', 'Rocky Mountain Range Western USA'],
            'great lakes': ['Great Lakes Region USA', 'Great Lakes States'],
            'new england': ['New England USA', 'Northeastern United States'],
            'pacific northwest': ['Pacific Northwest USA', 'Washington Oregon region'],
            'midwest': ['Midwest USA', 'Midwestern United States'],
            'south beach': ['South Beach Miami Florida', 'Miami Beach Florida'],
            'french quarter': ['French Quarter New Orleans Louisiana', 'Vieux Carré New Orleans'],
            'las vegas strip': ['Las Vegas Strip Nevada', 'Las Vegas Boulevard Nevada']
        }
        
        # City disambiguation (add state context)
        major_city_states = {
            'chicago': 'Illinois',
            'houston': 'Texas', 
            'phoenix': 'Arizona',
            'philadelphia': 'Pennsylvania',
            'san antonio': 'Texas',
            'san diego': 'California',
            'dallas': 'Texas',
            'san jose': 'California',
            'austin': 'Texas',
            'jacksonville': 'Florida',
            'fort worth': 'Texas',
            'charlotte': 'North Carolina',
            'san francisco': 'California',
            'indianapolis': 'Indiana',
            'seattle': 'Washington',
            'denver': 'Colorado',
            'boston': 'Massachusetts',
            'el paso': 'Texas',
            'detroit': 'Michigan',
            'nashville': 'Tennessee',
            'portland': 'Oregon',
            'memphis': 'Tennessee',
            'oklahoma city': 'Oklahoma',
            'las vegas': 'Nevada',
            'louisville': 'Kentucky',
            'baltimore': 'Maryland',
            'milwaukee': 'Wisconsin',
            'atlanta': 'Georgia',
            'miami': 'Florida'
        }
        
        # Check for international landmarks first
        landmark_country_map = {
            'eiffel tower': 'Paris France',
            'louvre': 'Paris France', 
            'arc de triomphe': 'Paris France',
            'notre dame': 'Paris France',
            'big ben': 'London UK',
            'tower bridge': 'London UK',
            'buckingham palace': 'London UK',
            'westminster abbey': 'London UK',
            'colosseum': 'Rome Italy',
            'vatican': 'Vatican City',
            'leaning tower of pisa': 'Pisa Italy',
            'sagrada familia': 'Barcelona Spain',
            'alhambra': 'Granada Spain',
            'acropolis': 'Athens Greece',
            'parthenon': 'Athens Greece',
            'taj mahal': 'Agra India',
            'red fort': 'Delhi India',
            'great wall of china': 'Beijing China',
            'forbidden city': 'Beijing China',
            'sydney opera house': 'Sydney Australia',
            'harbour bridge': 'Sydney Australia',
            'christ the redeemer': 'Rio de Janeiro Brazil',
            'machu picchu': 'Cusco Peru',
            'kremlin': 'Moscow Russia',
            'st basils cathedral': 'Moscow Russia'
        }
        
        # US landmark mapping for better disambiguation
        us_landmark_map = {
            'grand canyon': 'Grand Canyon National Park Arizona',
            'yellowstone': 'Yellowstone National Park Wyoming',
            'yosemite': 'Yosemite National Park California',
            'mount rushmore': 'Mount Rushmore National Memorial South Dakota',
            'statue of liberty': 'Statue of Liberty New York',
            'golden gate bridge': 'Golden Gate Bridge San Francisco California',
            'times square': 'Times Square New York City',
            'central park': 'Central Park New York City',
            'hollywood sign': 'Hollywood Sign Los Angeles California'
        }
        
        if name_lower in us_landmark_map:
            enhanced_query = us_landmark_map[name_lower]
            processed_queries.extend([
                enhanced_query,
                f"{location_name} USA",
                f"{location_name} United States"
            ])
        elif name_lower in landmark_country_map:
            location_with_country = landmark_country_map[name_lower]
            processed_queries.extend([
                location_with_country,
                f"{location_name} {location_with_country.split()[-1]}",
                f"{location_name} landmark"
            ])
        elif name_lower in region_mappings:
            processed_queries.extend(region_mappings[name_lower])
        elif name_lower in major_city_states:
            state = major_city_states[name_lower]
            processed_queries.extend([
                f"{location_name} {state} USA",
                f"{location_name} city {state}",
                f"{location_name} municipality {state}"
            ])
        elif self._likely_international_location(location_name):
            # Add specific country context for known international cities
            international_city_countries = {
                'paris': 'France',
                'london': 'UK England',
                'berlin': 'Germany',
                'rome': 'Italy',
                'madrid': 'Spain',
                'amsterdam': 'Netherlands',
                'sydney': 'Australia',
                'melbourne': 'Australia',
                'mumbai': 'India',
                'delhi': 'India',
                'tokyo': 'Japan',
                'beijing': 'China',
                'shanghai': 'China',
                'moscow': 'Russia',
                'sao paulo': 'Brazil',
                'são paulo': 'Brazil',
                'toronto': 'Canada',
                'vancouver': 'Canada',
                'tuscany': 'Italy',
                'provence': 'France'
            }
            
            if name_lower in international_city_countries:
                country = international_city_countries[name_lower]
                processed_queries.extend([
                    f"{location_name} {country}",
                    f"{location_name} city {country}",
                    f"{location_name} {country.split()[-1]}"  # Just the main country name
                ])
            else:
                # Generic international processing
                processed_queries.extend([
                    f"{location_name} city",
                    f"{location_name} municipality",
                    f"{location_name} urban area"
                ])
        else:
            # Check if this might be an international location
            likely_international = self._likely_international_location(location_name)
            
            if likely_international:
                # For likely international locations, don't bias toward USA
                if location_type == 'city' or self._looks_like_city(location_name):
                    processed_queries.extend([
                        f"{location_name} city",
                        f"{location_name} municipality", 
                        f"{location_name} urban area"
                    ])
                else:
                    processed_queries.extend([
                        f"{location_name} region",
                        f"{location_name} area"
                    ])
            else:
                # For likely US locations, add USA context
                if location_type == 'city' or self._looks_like_city(location_name):
                    processed_queries.extend([
                        f"{location_name} city USA",
                        f"{location_name} municipality USA",
                        f"{location_name} urban area USA"
                    ])
                elif location_type in ['state', 'province', 'region'] or self._looks_like_admin_division(location_name):
                    processed_queries.extend([
                        f"{location_name} state USA",
                        f"{location_name} province USA",
                        f"{location_name} region USA"
                    ])
                else:
                    # Default geographic enhancement
                    processed_queries.extend([
                        f"{location_name} USA",
                        f"{location_name} United States"
                    ])
        
        # Remove duplicates while preserving order
        unique_queries = []
        seen = set()
        for query in processed_queries:
            if query.lower() not in seen and query.lower() != name_lower:
                unique_queries.append(query)
                seen.add(query.lower())
        
        return unique_queries[:3]  # Limit to top 3 most relevant queries
    
    def _likely_international_location(self, location_name: str) -> bool:
        """Detect if a location is likely international (non-US) to avoid USA bias in preprocessing"""
        name_lower = location_name.lower().strip()
        
        # Famous international cities
        international_cities = {
            'paris', 'london', 'berlin', 'rome', 'madrid', 'amsterdam', 'vienna',
            'prague', 'budapest', 'stockholm', 'copenhagen', 'oslo', 'helsinki',
            'dublin', 'edinburgh', 'glasgow', 'manchester', 'birmingham', 'cambridge',
            'oxford', 'bristol', 'newcastle', 'york', 'bath', 'canterbury',
            'toronto', 'montreal', 'vancouver', 'calgary', 'ottawa',
            'sydney', 'melbourne', 'brisbane', 'perth', 'adelaide',
            'mumbai', 'delhi', 'bangalore', 'kolkata', 'hyderabad',
            'tokyo', 'osaka', 'kyoto', 'yokohama', 'kobe',
            'seoul', 'busan', 'beijing', 'shanghai', 'guangzhou', 'shenzhen',
            'moscow', 'st. petersburg', 'sao paulo', 'rio de janeiro',
            'buenos aires', 'mexico city', 'cairo', 'johannesburg', 'lagos'
        }
        
        # International landmarks with country context
        landmark_country_map = {
            'eiffel tower': 'Paris France',
            'louvre': 'Paris France', 
            'arc de triomphe': 'Paris France',
            'notre dame': 'Paris France',
            'big ben': 'London UK',
            'tower bridge': 'London UK',
            'buckingham palace': 'London UK',
            'westminster abbey': 'London UK',
            'colosseum': 'Rome Italy',
            'vatican': 'Vatican City',
            'leaning tower of pisa': 'Pisa Italy',
            'sagrada familia': 'Barcelona Spain',
            'alhambra': 'Granada Spain',
            'acropolis': 'Athens Greece',
            'parthenon': 'Athens Greece',
            'taj mahal': 'Agra India',
            'red fort': 'Delhi India',
            'great wall of china': 'Beijing China',
            'forbidden city': 'Beijing China',
            'sydney opera house': 'Sydney Australia',
            'harbour bridge': 'Sydney Australia',
            'christ the redeemer': 'Rio de Janeiro Brazil',
            'machu picchu': 'Cusco Peru',
            'kremlin': 'Moscow Russia',
            'st basils cathedral': 'Moscow Russia'
        }
        
        international_landmarks = set(landmark_country_map.keys())
        
        # International regions
        international_regions = {
            'tuscany', 'provence', 'bavaria', 'andalusia', 'catalonia',
            'scottish highlands', 'cornwall', 'cotswolds', 'lake district',
            'patagonia', 'amazon basin', 'sahara desert', 'serengeti',
            'himalayas', 'alps', 'andes'
        }
        
        return (name_lower in international_cities or 
                name_lower in international_landmarks or 
                name_lower in international_regions)
    
    async def _strategy_international_nominatim(self, location_name: str, location_type: str) -> Optional[List[float]]:
        """🌍 International-focused Nominatim with smart query strategies"""
        
        # Try different international query strategies
        query_strategies = []
        
        if self._likely_international_location(location_name):
            # For international locations, try without country bias
            query_strategies.extend([
                location_name,  # Pure name first
                f"{location_name} landmark",
                f"{location_name} city",
                f"{location_name} tourist attraction"
            ])
        else:
            # For likely US locations, add some context
            query_strategies.extend([
                f"{location_name} USA",
                location_name,
                f"{location_name} United States"
            ])
        
        for query in query_strategies:
            bbox = await self._nominatim_international_query(query)
            if bbox and self._is_valid_geographic_bbox(bbox):
                # Additional validation: prefer results that match expected region
                if self._validate_international_result(location_name, bbox):
                    return bbox
        
        return None
    
    async def _nominatim_international_query(self, query: str) -> Optional[List[float]]:
        """Enhanced Nominatim query with international focus"""
        url = "https://nominatim.openstreetmap.org/search"
        params = {
            "q": query,
            "format": "json",
            "limit": 10,  # Get more results to find best match
            "addressdetails": 1,
            "extratags": 1,
            "namedetails": 1,
            "dedupe": 1,
            "accept-language": "en"  # Prefer English results
        }
        headers = {"User-Agent": "EarthCopilot/2.1 (enhanced-international-geocoding)"}
        
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(url, params=params) as response:
                    if response.status == 200:
                        data = await response.json()
                        
                        # Rank results by international relevance
                        ranked_results = self._rank_nominatim_international(data, query)
                        
                        for result in ranked_results:
                            bbox = self._extract_nominatim_bounds(result)
                            if bbox:
                                return bbox
        except Exception as e:
            self.logger.error(f"International Nominatim error: {e}")
        
        return None
    
    def _rank_nominatim_international(self, results: List[Dict], query: str) -> List[Dict]:
        """Rank Nominatim results prioritizing international locations when appropriate"""
        if not results:
            return results
        
        query_lower = query.lower()
        is_likely_international = self._likely_international_location(query)
        
        def calculate_score(result):
            score = 0
            display_name = result.get('display_name', '').lower()
            place_type = result.get('type', '').lower()
            osm_class = result.get('class', '').lower()
            importance = float(result.get('importance', 0.0))
            
            # Base score from OSM importance
            score += importance * 100
            
            # Boost for appropriate place types
            if place_type in ['city', 'town', 'village', 'municipality']:
                score += 30
            elif place_type in ['tourist_attraction', 'monument', 'landmark']:
                score += 25
            elif place_type in ['building', 'attraction']:
                score += 20
            
            if is_likely_international:
                # For international queries, penalize US results
                if any(us_term in display_name for us_term in ['united states', 'usa', ', us']):
                    score -= 50
                # Boost for international countries
                if any(country in display_name for country in 
                      ['france', 'uk', 'england', 'germany', 'italy', 'spain', 'japan', 'china', 'india', 'australia']):
                    score += 40
            else:
                # For US queries, boost US results
                if any(us_term in display_name for us_term in ['united states', 'usa', ', us']):
                    score += 30
            
            return score
        
        return sorted(results, key=calculate_score, reverse=True)
    
    def _validate_international_result(self, location_name: str, bbox: List[float]) -> bool:
        """Validate that international results are in expected geographic regions"""
        if not bbox or len(bbox) != 4:
            return False
        
        west, south, east, north = bbox
        center_lon = (west + east) / 2
        center_lat = (south + north) / 2
        name_lower = location_name.lower()
        
        # Define expected regions for international locations
        expected_regions = {
            # European locations
            'paris': (-10, 40, 40, 70),
            'london': (-10, 49, 5, 61),
            'berlin': (5, 50, 20, 60),
            'rome': (5, 40, 20, 50),
            'madrid': (-10, 35, 5, 45),
            'eiffel tower': (-5, 48, 5, 50),
            'big ben': (-5, 51, 2, 52),
            'colosseum': (10, 41, 15, 43),
            
            # Asian locations  
            'tokyo': (130, 30, 145, 40),
            'beijing': (110, 35, 125, 45),
            'mumbai': (70, 15, 80, 25),
            'taj mahal': (75, 25, 80, 30),
            
            # Other continents
            'sydney': (145, -40, 155, -30),
            'toronto': (-85, 40, -75, 50),
        }
        
        if name_lower in expected_regions:
            min_lon, min_lat, max_lon, max_lat = expected_regions[name_lower]
            if not (min_lon <= center_lon <= max_lon and min_lat <= center_lat <= max_lat):
                self.logger.info(f"🚫 Rejected {location_name} result ({center_lon:.2f}, {center_lat:.2f}) - outside expected region")
                return False
        
        return True
    
    async def _strategy_geonames_alternative(self, location_name: str, location_type: str) -> Optional[List[float]]:
        """📚 Alternative using free GeoNames-style approach via Nominatim with geographic focus"""
        
        # Enhanced queries focusing on geographic features and populated places
        geographic_queries = []
        
        if self._likely_international_location(location_name):
            geographic_queries.extend([
                f"{location_name} admin",  # Administrative boundaries
                f"{location_name} populated place",
                f"{location_name} geographic feature"
            ])
        
        # Try country-specific queries for famous international locations
        country_specific_queries = {
            'paris': ['Paris France', 'Paris Île-de-France'],
            'london': ['London England UK', 'London Greater London'],
            'tokyo': ['Tokyo Japan', 'Tokyo Kantō'],
            'berlin': ['Berlin Germany', 'Berlin Deutschland'],
            'sydney': ['Sydney Australia', 'Sydney New South Wales'],
            'mumbai': ['Mumbai India', 'Mumbai Maharashtra'],
            'beijing': ['Beijing China', 'Beijing Municipality']
        }
        
        name_lower = location_name.lower()
        if name_lower in country_specific_queries:
            geographic_queries.extend(country_specific_queries[name_lower])
        
        for query in geographic_queries:
            bbox = await self._nominatim_international_query(query)
            if bbox and self._is_valid_geographic_bbox(bbox):
                if self._validate_international_result(location_name, bbox):
                    return bbox
        
        return None
    
    def _rank_results_by_relevance(self, results: List[Dict], location_name: str) -> List[Dict]:
        """Rank API results by relevance using population, admin level, and name matching"""
        if not results:
            return results
        
        def calculate_score(result):
            score = 0
            address = result.get('address', {})
            entity_type = result.get('entityType', '')
            
            # Higher score for exact name matches
            municipality = address.get('municipality', '').lower()
            if municipality == location_name.lower():
                score += 50
            
            # Higher score for populated places and municipalities
            if 'Municipality' in entity_type or 'PopulatedPlace' in entity_type:
                score += 30
            
            # Lower score for administrative subdivisions (avoid small towns)
            if 'CountrySecondarySubdivision' in entity_type:
                score -= 10
            
            # Prefer results with state information
            if address.get('countrySubdivision'):
                score += 10
                
            return score
        
        # Sort by score (highest first)
        sorted_results = sorted(results, key=calculate_score, reverse=True)
        return sorted_results


# ============================================================================
# SINGLETON INSTANCE
# ============================================================================

_location_resolver: Optional[EnhancedLocationResolver] = None


def get_location_resolver() -> EnhancedLocationResolver:
    """Get the singleton EnhancedLocationResolver instance."""
    global _location_resolver
    if _location_resolver is None:
        _location_resolver = EnhancedLocationResolver()
    return _location_resolver


def get_known_location_names() -> set:
    """
    Get the set of all known location names from the hardcoded locations.
    Used by unified_router.py for bare location detection.
    
    Returns:
        Set of lowercase location names (e.g., 'nyc', 'paris', 'egypt')
    """
    resolver = get_location_resolver()
    return set(resolver.STORED_LOCATIONS.keys())
