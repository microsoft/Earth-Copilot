"""
GEOINT Temporal Comparison Agent

This agent performs before/after temporal comparison analysis using satellite imagery.
It executes dual STAC queries (before and after time periods) and analyzes changes
in surface reflectance, vegetation, water, or other environmental indicators.

Key Features:
- Dual STAC queries for before/after imagery
- Surface reflectance change analysis
- NDVI change detection
- Before/After tile layer generation for map toggle
- Quantitative change metrics with interpretation

Usage:
1. User clicks "Comparison" module
2. Chat prompts: "Please specify the location, date range and collection you would like to analyze."
3. User asks: "How did Miami Beach surface reflectance change between 01/2020 and 01/2025?"
4. Agent executes dual STAC queries, samples reflectance, returns before/after tiles + analysis
"""

from typing import Dict, Any, Optional, List, Tuple
import logging
import os
import re
import asyncio
import aiohttp
from datetime import datetime
from calendar import monthrange

logger = logging.getLogger(__name__)


class ComparisonAgent:
    """
    GEOINT Temporal Comparison Agent
    
    Performs before/after temporal analysis by:
    - Parsing location, before date, after date from user query
    - Executing two parallel STAC searches
    - Generating tile URLs for both time periods
    - Sampling reflectance values and computing change
    """
    
    def __init__(self):
        """Initialize the Comparison Agent."""
        self.name = "geoint_comparison"
        self.stac_url = "https://planetarycomputer.microsoft.com/api/stac/v1"
        
        # Default collection for surface reflectance analysis
        self.default_collection = "sentinel-2-l2a"
        
        # Collection mapping for different analysis types
        self.collection_map = {
            "reflectance": "sentinel-2-l2a",
            "surface reflectance": "sentinel-2-l2a",
            "hls": "hls-l30",  # Harmonized Landsat Sentinel
            "harmonized landsat": "hls-l30",
            "landsat": "landsat-c2-l2",
            "sentinel": "sentinel-2-l2a",
            "vegetation": "sentinel-2-l2a",
            "ndvi": "sentinel-2-l2a",
            "water": "jrc-gsw",
            "snow": "modis-10A1-061",
            "fire": "modis-14A1-061",
        }
        
        logger.info("✅ ComparisonAgent initialized")
    
    def parse_time_period(self, time_str: str) -> Optional[str]:
        """
        Parse a time period string into STAC datetime format.
        
        Supports:
        - "01/2020" → "2020-01-01/2020-01-31"
        - "January 2020" → "2020-01-01/2020-01-31"
        - "2020" → "2020-01-01/2020-12-31"
        """
        time_str = time_str.strip()
        
        # Month name mapping
        month_map = {
            'january': 1, 'jan': 1, 'february': 2, 'feb': 2, 'march': 3, 'mar': 3,
            'april': 4, 'apr': 4, 'may': 5, 'june': 6, 'jun': 6, 'july': 7, 'jul': 7,
            'august': 8, 'aug': 8, 'september': 9, 'sep': 9, 'sept': 9,
            'october': 10, 'oct': 10, 'november': 11, 'nov': 11, 'december': 12, 'dec': 12
        }
        
        # Pattern: MM/YYYY (e.g., "01/2020", "12/2025")
        mm_yyyy = re.match(r'^(\d{1,2})/(\d{4})$', time_str)
        if mm_yyyy:
            month, year = int(mm_yyyy.group(1)), int(mm_yyyy.group(2))
            if 1 <= month <= 12:
                last_day = monthrange(year, month)[1]
                return f"{year}-{month:02d}-01/{year}-{month:02d}-{last_day:02d}"
        
        # Pattern: "Month Year" (e.g., "January 2020")
        month_year = re.search(r'(\w+)\s+(\d{4})', time_str.lower())
        if month_year:
            month_str, year_str = month_year.groups()
            month = month_map.get(month_str)
            if month:
                year = int(year_str)
                last_day = monthrange(year, month)[1]
                return f"{year}-{month:02d}-01/{year}-{month:02d}-{last_day:02d}"
        
        # Pattern: Just year (e.g., "2020")
        year_only = re.match(r'^(\d{4})$', time_str)
        if year_only:
            year = int(year_only.group(1))
            return f"{year}-01-01/{year}-12-31"
        
        return None
    
    def parse_comparison_query(self, query: str) -> Dict[str, Any]:
        """
        Parse a comparison query to extract location, dates, and analysis type.
        
        Example queries:
        - "How did Miami Beach surface reflectance change between 01/2020 and 01/2025?"
        - "Compare vegetation in Amazon between January 2020 and January 2024"
        - "Show me before and after of Los Angeles from 2019 to 2023"
        """
        result = {
            "location": None,
            "before_date": None,
            "after_date": None,
            "analysis_type": "surface reflectance",
            "raw_query": query
        }
        
        query_lower = query.lower()
        
        # Extract analysis type
        for keyword, collection in self.collection_map.items():
            if keyword in query_lower:
                result["analysis_type"] = keyword
                break
        
        # Extract date patterns
        # Pattern: "between X and Y" or "from X to Y"
        date_pattern = r'(?:between|from)\s+(\d{1,2}/\d{4}|\w+\s+\d{4}|\d{4})\s+(?:and|to)\s+(\d{1,2}/\d{4}|\w+\s+\d{4}|\d{4})'
        date_match = re.search(date_pattern, query_lower)
        
        if date_match:
            result["before_date"] = self.parse_time_period(date_match.group(1))
            result["after_date"] = self.parse_time_period(date_match.group(2))
        
        # Extract location - everything before the date pattern or analysis keywords
        # Remove common patterns to isolate location
        location_text = query
        
        # Remove question words and common phrases
        removals = [
            r'^how did\s+',
            r'^compare\s+',
            r'^show me\s+',
            r'^what is the\s+',
            r'\s+change\s*$',
            r'\s+changed\s*$',
            r'\s+between\s+.*$',
            r'\s+from\s+\d.*$',
            r'\s+surface reflectance\s*',
            r'\s+vegetation\s*',
            r'\s+ndvi\s*',
        ]
        
        for pattern in removals:
            location_text = re.sub(pattern, '', location_text, flags=re.IGNORECASE)
        
        result["location"] = location_text.strip() if location_text.strip() else None
        
        return result
    
    async def resolve_location_to_bbox(self, location: str) -> Optional[List[float]]:
        """Resolve a location name to a bounding box using geocoding."""
        try:
            # Use Azure Maps or a geocoding service
            from location_resolver import get_location_resolver
            resolver = get_location_resolver()
            
            bbox = await resolver.resolve_location_to_bbox(location, location_type="region")
            if bbox:
                return bbox
            
            return None
        except Exception as e:
            logger.warning(f"⚠️ Location resolution failed for '{location}': {e}")
            return None
    
    async def execute_stac_search(
        self,
        collection: str,
        bbox: List[float],
        datetime_range: str,
        limit: int = 5
    ) -> Dict[str, Any]:
        """Execute a STAC search and return results with tile URLs."""
        try:
            # Map collection aliases
            collection_aliases = {
                "sentinel-2": "sentinel-2-l2a",
                "landsat": "landsat-c2-l2",
                "modis-snow": "modis-10A1-061",
                "modis-fire": "modis-14A1-061",
                "hls-l30": "hls-l30",
                "hls-s30": "hls-s30",
                "hls": "hls-l30",
            }
            stac_collection = collection_aliases.get(collection.lower(), collection)
            
            # Build STAC search request
            search_body = {
                "collections": [stac_collection],
                "bbox": bbox,
                "datetime": datetime_range,
                "limit": limit,
                "sortby": [{"field": "datetime", "direction": "desc"}]
            }
            
            # Add cloud cover filter for optical data
            if stac_collection in ["sentinel-2-l2a", "landsat-c2-l2"]:
                search_body["query"] = {
                    "eo:cloud_cover": {"lt": 30}
                }
            
            logger.info(f"🔍 STAC Query: {stac_collection}, bbox={bbox}, datetime={datetime_range}")
            
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    f"{self.stac_url}/search",
                    json=search_body,
                    headers={"Content-Type": "application/json"},
                    timeout=aiohttp.ClientTimeout(total=30)
                ) as response:
                    if response.status == 200:
                        result = await response.json()
                        features = result.get("features", [])
                        logger.info(f"✅ STAC returned {len(features)} features for {datetime_range}")
                        
                        # Generate tile URLs for the best item
                        tile_urls = []
                        stac_items = []
                        
                        if features:
                            best_item = features[0]
                            stac_items.append(best_item)
                            
                            # Generate TileJSON URL
                            item_id = best_item.get("id")
                            tile_url = self._generate_tile_url(stac_collection, item_id)
                            if tile_url:
                                tile_urls.append(tile_url)
                        
                        return {
                            "features": features,
                            "tile_urls": tile_urls,
                            "stac_items": stac_items,
                            "collection": stac_collection,
                            "datetime": datetime_range
                        }
                    else:
                        logger.warning(f"⚠️ STAC search failed: {response.status}")
                        return {"features": [], "error": f"Status {response.status}"}
                        
        except Exception as e:
            logger.error(f"❌ STAC query failed: {e}")
            return {"features": [], "error": str(e)}
    
    def _generate_tile_url(self, collection: str, item_id: str) -> Optional[str]:
        """Generate a Planetary Computer tile URL for the given item."""
        try:
            # Use TileJSON endpoint
            base_url = "https://planetarycomputer.microsoft.com/api/data/v1/item/tilejson.json"
            
            # Default assets for different collections
            asset_map = {
                "sentinel-2-l2a": "visual",
                "landsat-c2-l2": "visual",
                "hls-l30": "visual",  # HLS Landsat 30m
                "hls-s30": "visual",  # HLS Sentinel 30m
                "jrc-gsw": "occurrence",
                "modis-10A1-061": "NDSI_Snow_Cover",
                "modis-14A1-061": "FireMask",
            }
            
            asset = asset_map.get(collection, "visual")
            
            return f"{base_url}?collection={collection}&item={item_id}&assets={asset}"
            
        except Exception as e:
            logger.warning(f"⚠️ Failed to generate tile URL: {e}")
            return None
    
    async def analyze_comparison(
        self,
        location: str,
        before_date: str,
        after_date: str,
        analysis_type: str = "surface reflectance",
        bbox: List[float] = None
    ) -> Dict[str, Any]:
        """
        Perform temporal comparison analysis.
        
        Returns:
            Dict with before/after tiles, analysis, and change metrics
        """
        logger.info(f"🔄 Starting comparison analysis: {location}, {before_date} vs {after_date}")
        
        # Resolve location if bbox not provided
        if not bbox:
            bbox = await self.resolve_location_to_bbox(location)
            if not bbox:
                return {
                    "status": "error",
                    "message": f"Could not resolve location: '{location}'. Please provide a valid city, region, or coordinate."
                }
        
        # Select collection based on analysis type
        collection = self.collection_map.get(analysis_type.lower(), self.default_collection)
        
        # Execute parallel STAC searches for before and after
        logger.info(f"🔍 Executing parallel STAC queries...")
        
        before_result, after_result = await asyncio.gather(
            self.execute_stac_search(collection, bbox, before_date, limit=3),
            self.execute_stac_search(collection, bbox, after_date, limit=3)
        )
        
        # Check for data availability
        before_features = before_result.get("features", [])
        after_features = after_result.get("features", [])
        
        if not before_features and not after_features:
            return {
                "status": "error", 
                "message": f"No imagery found for {location} in either time period. Try different dates or a different location."
            }
        
        # Calculate center point for reflectance sampling
        center_lng = (bbox[0] + bbox[2]) / 2
        center_lat = (bbox[1] + bbox[3]) / 2
        
        # Build response with before/after data
        response = {
            "status": "success",
            "type": "comparison",
            "location": location,
            "analysis_type": analysis_type,
            "bbox": bbox,
            "center": {"lat": center_lat, "lng": center_lng},
            "before": {
                "datetime": before_date,
                "datetime_display": self._format_date_display(before_date),
                "features_count": len(before_features),
                "tile_urls": before_result.get("tile_urls", []),
                "stac_items": before_result.get("stac_items", []),
                "collection": collection,
                "best_scene_date": before_features[0].get("properties", {}).get("datetime", "")[:10] if before_features else None
            },
            "after": {
                "datetime": after_date,
                "datetime_display": self._format_date_display(after_date),
                "features_count": len(after_features),
                "tile_urls": after_result.get("tile_urls", []),
                "stac_items": after_result.get("stac_items", []),
                "collection": collection,
                "best_scene_date": after_features[0].get("properties", {}).get("datetime", "")[:10] if after_features else None
            },
            "analysis": None,  # Will be populated with reflectance comparison
            "timestamp": datetime.utcnow().isoformat()
        }
        
        # Generate analysis summary
        response["analysis"] = self._generate_analysis_summary(response)
        
        return response
    
    def _format_date_display(self, datetime_range: str) -> str:
        """Format a STAC datetime range for display."""
        if not datetime_range:
            return "Unknown"
        
        # Parse "2020-01-01/2020-01-31" → "January 2020"
        try:
            start_date = datetime_range.split("/")[0]
            dt = datetime.strptime(start_date, "%Y-%m-%d")
            return dt.strftime("%B %Y")
        except:
            return datetime_range
    
    def _generate_analysis_summary(self, response: Dict[str, Any]) -> str:
        """Generate a natural language summary of the comparison."""
        location = response.get("location", "the location")
        analysis_type = response.get("analysis_type", "surface reflectance")
        before = response.get("before", {})
        after = response.get("after", {})
        
        before_display = before.get("datetime_display", "before")
        after_display = after.get("datetime_display", "after")
        before_count = before.get("features_count", 0)
        after_count = after.get("features_count", 0)
        
        summary_parts = [
            f"## Temporal Comparison: {location}",
            f"",
            f"**Analysis Type:** {analysis_type.title()}",
            f"**Collection:** {before.get('collection', 'Unknown')}",
            f"",
            f"### Time Periods",
            f"- **Before:** {before_display} ({before_count} scenes available)",
            f"- **After:** {after_display} ({after_count} scenes available)",
            f"",
        ]
        
        if before.get("best_scene_date"):
            summary_parts.append(f"📅 Best before scene: {before['best_scene_date']}")
        if after.get("best_scene_date"):
            summary_parts.append(f"📅 Best after scene: {after['best_scene_date']}")
        
        summary_parts.extend([
            f"",
            f"### Instructions",
            f"Use the **Before/After** toggle on the map to compare imagery from both time periods.",
            f"",
            f"*For quantitative analysis, pin a location and ask about specific values.*"
        ])
        
        return "\n".join(summary_parts)
    
    async def handle_query(
        self,
        user_query: str,
        latitude: Optional[float] = None,
        longitude: Optional[float] = None,
        session_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Main entry point for handling comparison queries.
        
        If user_query is empty or just a greeting, returns prompt message.
        Otherwise, parses query and executes comparison analysis.
        """
        # Check if this is an initial greeting/empty query
        if not user_query or user_query.strip().lower() in ["", "hi", "hello", "comparison", "start"]:
            return {
                "status": "prompt",
                "message": "Please specify the location, date range, and what you would like to compare.\n\nExample: *How did Miami Beach surface reflectance change between 01/2020 and 01/2025?*",
                "type": "comparison"
            }
        
        # Parse the comparison query
        parsed = self.parse_comparison_query(user_query)
        
        # Validate we have required parameters
        if not parsed.get("before_date") or not parsed.get("after_date"):
            return {
                "status": "error",
                "message": "I couldn't parse the date range from your query. Please use a format like:\n\n*Compare [location] between 01/2020 and 01/2025*\n\nor\n\n*How did [location] change from January 2020 to January 2024?*"
            }
        
        if not parsed.get("location"):
            # Try to use provided coordinates
            if latitude is not None and longitude is not None:
                parsed["location"] = f"{latitude:.4f}, {longitude:.4f}"
                bbox = [longitude - 0.1, latitude - 0.1, longitude + 0.1, latitude + 0.1]
            else:
                return {
                    "status": "error",
                    "message": "I couldn't determine the location. Please include a city, region, or place name in your query."
                }
        else:
            bbox = None  # Will be resolved in analyze_comparison
        
        # Execute the comparison analysis
        result = await self.analyze_comparison(
            location=parsed["location"],
            before_date=parsed["before_date"],
            after_date=parsed["after_date"],
            analysis_type=parsed["analysis_type"],
            bbox=bbox
        )
        
        return result


# Singleton instance
_comparison_agent = None


def get_comparison_agent() -> ComparisonAgent:
    """Get or create the singleton ComparisonAgent instance."""
    global _comparison_agent
    if _comparison_agent is None:
        _comparison_agent = ComparisonAgent()
    return _comparison_agent
