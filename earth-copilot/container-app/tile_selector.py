# Copyright (c) Microsoft Corporation.
# Licensed under the MIT license.

"""
Smart Tile Selection System for Earth Copilot

This module implements intelligent tile ranking and selection to ensure users
always see the most recent, clear, high-quality imagery for their queries.

Key Features:
- Multi-criteria quality scoring (recency, cloud cover, spatial coverage, quality flags)
- Automatic recent-data defaults (no date specified -> last 60 days)
- Cloud cover filtering for optical imagery
- Spatial overlap optimization
- Collection-aware ranking strategies

Architecture:
1. Query STAC API with limit=100 (fetch candidates)
2. Score each tile by quality metrics
3. Select top N tiles (default: 5 for small areas, more for large areas)
4. Return ranked results for optimal visualization

REVISION: v1.0.0 - Initial implementation
"""

import logging
from typing import Dict, List, Any, Optional, Tuple
from datetime import datetime, timedelta
from collections import defaultdict

logger = logging.getLogger(__name__)


class TileSelector:
    """
    Intelligent tile selection and ranking system
    
    Ensures users always see the best available imagery by scoring tiles
    across multiple quality dimensions.
    """
    
    # Quality score weights (sum to 100%)
    RECENCY_WEIGHT = 0.40      # 40% - Most important for time-series data
    CLOUD_COVER_WEIGHT = 0.30  # 30% - Critical for optical imagery clarity
    COVERAGE_WEIGHT = 0.20     # 20% - Ensure good spatial overlap
    QUALITY_FLAGS_WEIGHT = 0.10  # 10% - Use quality metadata when available
    
    # Collection-specific defaults
    OPTICAL_COLLECTIONS = {
        "sentinel-2-l2a", "landsat-c2-l2", "landsat-8-c2-l2", "landsat-9-c2-l2",
        "hls", "hls-l30", "hls-s30", "naip", "modis-09A1-061", "modis-09Q1-061"
    }
    
    SAR_COLLECTIONS = {
        "sentinel-1-grd", "sentinel-1-rtc"
    }
    
    THERMAL_COLLECTIONS = {
        "modis-14A1-061", "modis-14A2-061", "modis-MCD64A1-061", "landsat-c2-st"
    }
    
    DEM_COLLECTIONS = {
        "cop-dem-glo-30", "cop-dem-glo-90", "nasadem", "3dep-seamless", 
        "alos-dem", "srtm"
    }
    
    @classmethod
    def get_optimal_query_params(
        cls, 
        query: str, 
        collections: List[str],
        bbox: Optional[List[float]] = None,
        user_datetime: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Generate optimal STAC query parameters with smart defaults
        
        This is called BEFORE the STAC query to set up intelligent filtering.
        
        Args:
            query: Natural language query
            collections: STAC collection IDs
            bbox: [west, south, east, north]
            user_datetime: User-specified datetime (if any)
            
        Returns:
            Dict with optimized query parameters:
            {
                "limit": 100,  # Fetch enough candidates for ranking
                "datetime": "2025-09-07/2025-10-07",  # Smart temporal filter
                "query": {"eo:cloud_cover": {"lt": 20}},  # Quality filters
                "sortby": [{"field": "datetime", "direction": "desc"}]
            }
        """
        query_lower = query.lower()
        today = datetime.now()
        
        # =================================================================
        # STEP 1: DETERMINE TEMPORAL RANGE (with smart defaults)
        # =================================================================
        datetime_range = None
        
        # Check if user specified a date/time
        if user_datetime:
            datetime_range = user_datetime
            logger.info(f"[DATE] User-specified datetime: {datetime_range}")
        else:
            # Apply intelligent defaults based on query intent
            
            # DEMs and static datasets: Skip temporal filtering (use all available)
            is_static_data = any(col in collections for col in cls.DEM_COLLECTIONS)
            
            if is_static_data:
                datetime_range = None
                logger.info(f"[MTN] Static dataset detected - no temporal filter needed")
            
            # Recent/Latest keywords -> Last 30 days
            elif any(term in query_lower for term in ['recent', 'latest', 'current', 'now', 'today']):
                start_date = (today - timedelta(days=30)).strftime("%Y-%m-%d")
                end_date = today.strftime("%Y-%m-%d")
                datetime_range = f"{start_date}/{end_date}"
                logger.info(f"[TIME] 'Recent' detected -> Last 30 days: {datetime_range}")
            
            # Last week
            elif any(term in query_lower for term in ['last week', 'past week', 'this week']):
                start_date = (today - timedelta(days=7)).strftime("%Y-%m-%d")
                end_date = today.strftime("%Y-%m-%d")
                datetime_range = f"{start_date}/{end_date}"
                logger.info(f"[TIME] 'Last week' detected -> Last 7 days: {datetime_range}")
            
            # Last month
            elif any(term in query_lower for term in ['last month', 'past month', 'this month']):
                start_date = (today - timedelta(days=30)).strftime("%Y-%m-%d")
                end_date = today.strftime("%Y-%m-%d")
                datetime_range = f"{start_date}/{end_date}"
                logger.info(f"[TIME] 'Last month' detected -> Last 30 days: {datetime_range}")
            
            # Last year
            elif any(term in query_lower for term in ['last year', 'past year']):
                start_date = (today - timedelta(days=365)).strftime("%Y-%m-%d")
                end_date = today.strftime("%Y-%m-%d")
                datetime_range = f"{start_date}/{end_date}"
                logger.info(f"[TIME] 'Last year' detected -> Last 365 days: {datetime_range}")
            
            # Specific year (e.g., "2023 imagery")
            elif any(year in query for year in ['2020', '2021', '2022', '2023', '2024', '2025']):
                import re
                year_match = re.search(r'\b(20\d{2})\b', query)
                if year_match:
                    year = year_match.group(1)
                    datetime_range = f"{year}-01-01/{year}-12-31"
                    logger.info(f"[TIME] Specific year detected: {datetime_range}")
            
            # DEFAULT: Last 60 days (good balance of recency + availability)
            else:
                start_date = (today - timedelta(days=60)).strftime("%Y-%m-%d")
                end_date = today.strftime("%Y-%m-%d")
                datetime_range = f"{start_date}/{end_date}"
                logger.info(f"[TIME] No date specified -> DEFAULT: Last 60 days: {datetime_range}")
                logger.info(f"   [INFO] This ensures recent, relevant data by default")
        
        # =================================================================
        # STEP 2: DETERMINE QUALITY FILTERS (cloud cover, etc.)
        # =================================================================
        quality_filters = {}
        
        # Optical imagery: Filter by cloud cover
        is_optical = any(col in collections for col in cls.OPTICAL_COLLECTIONS)
        
        if is_optical:
            # Check if user explicitly WANTS cloudy imagery (rare case)
            wants_clouds = any(term in query_lower for term in [
                'cloudy', 'overcast', 'high cloud', 'show me clouds', 
                'with clouds', 'cloud cover imagery'
            ])
            
            # Check if user explicitly wants LOW/NO clouds (common case)
            wants_clear = any(term in query_lower for term in [
                'low cloud', 'no cloud', 'clear', 'cloudless', 
                'minimal cloud', 'cloud-free', 'without clouds'
            ])
            
            if wants_clouds and not wants_clear:
                # User explicitly wants clouds - no filter
                logger.info(f"[CLOUD] User wants cloudy imagery - skipping cloud filter")
            else:
                # Default: <20% cloud cover for clear imagery
                cloud_threshold = 20
                
                # Extra strict for explicit "clear" requests
                if wants_clear or any(term in query_lower for term in ['clear', 'cloudless']):
                    cloud_threshold = 10
                    logger.info(f"[CLOUD] 'Clear/low cloud' keyword detected -> cloud threshold: <{cloud_threshold}%")
                
                quality_filters["eo:cloud_cover"] = {"lt": cloud_threshold}
                logger.info(f"[CLOUD] Cloud cover filter: <{cloud_threshold}% (optical imagery)")
        
        # SAR imagery: No cloud filter needed (penetrates clouds)
        is_sar = any(col in collections for col in cls.SAR_COLLECTIONS)
        if is_sar:
            logger.info(f"[SIGNAL] SAR imagery detected - no cloud filter needed")
        
        # =================================================================
        # USDA CDL: Filter to cropland type items only
        # =================================================================
        # The usda-cdl collection has 3 item types: cropland, cultivated, frequency
        # Each type has DIFFERENT assets:
        #   - cropland items have 'cropland' asset (with usda-cdl colormap)
        #   - cultivated items have 'cultivated' asset (different colormap)
        #   - frequency items have frequency assets
        # The PC render config uses assets=["cropland"], so we MUST filter to
        # only return cropland type items, otherwise tiles return 404 errors.
        is_usda_cdl = any("usda-cdl" in col.lower() for col in collections)
        if is_usda_cdl:
            quality_filters["usda_cdl:type"] = {"eq": "cropland"}
            logger.info(f"[CROP] USDA CDL: Filtering to 'cropland' type items (required for render config)")
        
        # =================================================================
        # STEP 3: DETERMINE QUERY LIMIT (based on area size)
        # =================================================================
        query_limit = cls._calculate_optimal_tile_limit(bbox, collections)
        
        # =================================================================
        # STEP 4: BUILD QUERY PARAMETERS
        # =================================================================
        params = {
            "limit": query_limit,
            "sortby": [{"field": "datetime", "direction": "desc"}]  # Most recent first
        }
        
        if datetime_range:
            params["datetime"] = datetime_range
        
        if quality_filters:
            params["query"] = quality_filters
        
        logger.info(f"[OK] Optimal query params generated: limit={query_limit}, "
                   f"datetime={'YES' if datetime_range else 'NONE'}, "
                   f"filters={'YES' if quality_filters else 'NONE'}")
        
        return params
    
    @classmethod
    def select_best_tiles(
        cls,
        features: List[Dict[str, Any]],
        query_bbox: Optional[List[float]] = None,
        collections: Optional[List[str]] = None,
        max_tiles: int = 5,
        query: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """
        Select the best N tiles from STAC results based on quality scoring
        
        This is called AFTER the STAC query to rank and select optimal tiles.
        
        Args:
            features: STAC feature results from API
            query_bbox: User's requested bounding box [west, south, east, north]
            collections: Collection IDs (for collection-specific logic)
            max_tiles: Maximum number of tiles to return
            query: Original user query (for intent-based weight adjustment)
            
        Returns:
            List of top N tiles, sorted by quality score (best first)
        """
        if not features:
            logger.info("[EMPTY] No features to select from")
            return []
        
        logger.info(f"[TARGET] Selecting best tiles from {len(features)} candidates...")
        
        # =================================================================
        # STEP 0: DETECT USER INTENT & ADJUST WEIGHTS
        # =================================================================
        weights = cls._determine_scoring_weights(query)
        
        # =================================================================
        # STEP 0.5: DETERMINE IF WE SHOULD GROUP BY DATE OR PRIORITIZE COVERAGE
        # For large areas (country-scale), we SKIP date grouping to maximize
        # spatial coverage. Individual tiles may be from different dates, but
        # this ensures full coverage across the requested area.
        # =================================================================
        skip_date_grouping = False
        if query_bbox and len(query_bbox) == 4:
            width_deg = query_bbox[2] - query_bbox[0]
            height_deg = query_bbox[3] - query_bbox[1]
            area_degrees = width_deg * height_deg
            
            # For large areas (>10 sq deg, roughly state/country scale), skip date grouping
            # to maximize spatial coverage even if tiles are from different dates
            if area_degrees > 10:
                skip_date_grouping = True
                logger.info(f"[GLOBE] Large area detected ({area_degrees:.1f} sq deg) - skipping date grouping for full spatial coverage")
        
        if not skip_date_grouping:
            # Group by date for smaller areas to ensure temporal consistency
            tiles_by_date = cls._group_tiles_by_acquisition_date(features)
            
            if tiles_by_date:
                # Select the best date group (most recent with good coverage)
                best_date, best_date_tiles = cls._select_best_date_group(tiles_by_date, query_bbox, weights)
                
                if best_date_tiles:
                    logger.info(f"[DATE] Selected acquisition date: {best_date} ({len(best_date_tiles)} tiles)")
                    features = best_date_tiles  # Use only tiles from this date
        
        # =================================================================
        # STEP 1: SCORE EACH TILE
        # =================================================================
        scored_tiles = []
        
        for feature in features:
            score_breakdown = cls._score_tile(feature, query_bbox, collections, weights)
            
            scored_tiles.append({
                "feature": feature,
                "total_score": score_breakdown["total"],
                "breakdown": score_breakdown
            })
        
        # =================================================================
        # STEP 2: SORT BY SCORE (highest first)
        # =================================================================
        scored_tiles.sort(key=lambda x: x["total_score"], reverse=True)
        
        # =================================================================
        # STEP 3: SELECT TOP N TILES
        # =================================================================
        # Note: Spatial coverage is handled by STAC's grid system (MGRS/WRS)
        # STAC returns tiles that intersect the bbox, and deduplication keeps
        # one tile per grid cell. As long as we request enough items from STAC,
        # the deduplicated tiles will cover the entire area.
        if query_bbox:
            bbox_area = (query_bbox[2] - query_bbox[0]) * (query_bbox[3] - query_bbox[1])
            if bbox_area > 25:  # Country-scale (e.g., Greece ~71 sq deg)
                logger.info(f"[GLOBE] Country-scale area ({bbox_area:.1f} sq deg) -> using max_tiles={max_tiles}")
            elif bbox_area > 0.25:  # Large region
                logger.info(f"[MAP] Large area ({bbox_area:.1f} sq deg) -> using max_tiles={max_tiles}")
        
        # Ensure we don't exceed available tiles
        effective_max = min(max_tiles, len(scored_tiles))
        selected = scored_tiles[:effective_max]
        
        # =================================================================
        # STEP 4: LOG SELECTION RESULTS
        # =================================================================
        logger.info(f"[OK] Selected {len(selected)} tiles (from {len(features)} candidates)")
        
        for i, tile in enumerate(selected[:3], 1):  # Log top 3
            breakdown = tile["breakdown"]
            feature = tile["feature"]
            
            # Extract key metadata
            tile_id = feature.get("id", "unknown")
            datetime_str = feature.get("properties", {}).get("datetime", "unknown")
            cloud_cover = feature.get("properties", {}).get("eo:cloud_cover", "N/A")
            
            logger.info(f"  #{i} [{tile['total_score']:.2f}/100] {tile_id}")
            logger.info(f"      [DATE] Date: {datetime_str}")
            logger.info(f"      [CLOUD] Clouds: {cloud_cover}%")
            logger.info(f"      [CHART] Scores: recency={breakdown['recency']:.1f}, "
                       f"clouds={breakdown['cloud_cover']:.1f}, "
                       f"coverage={breakdown['coverage']:.1f}, "
                       f"quality={breakdown['quality_flags']:.1f}")
        
        # Return just the features (not the scoring metadata)
        return [tile["feature"] for tile in selected]
    
    @classmethod
    def _group_tiles_by_acquisition_date(cls, features: List[Dict[str, Any]]) -> Dict[str, List[Dict[str, Any]]]:
        """
        Group tiles by acquisition date (rounded to day) to prevent overlapping tiles
        from different dates appearing on the map.
        
        Returns:
            Dict mapping date strings (YYYY-MM-DD) to list of features from that date
        """
        from collections import defaultdict
        
        tiles_by_date = defaultdict(list)
        
        for feature in features:
            datetime_str = feature.get("properties", {}).get("datetime", "")
            
            if datetime_str:
                try:
                    # Parse and round to day
                    dt = datetime.fromisoformat(datetime_str.replace('Z', '+00:00'))
                    date_key = dt.strftime("%Y-%m-%d")
                    tiles_by_date[date_key].append(feature)
                except Exception:
                    # Can't parse date - put in "unknown" bucket
                    tiles_by_date["unknown"].append(feature)
            else:
                tiles_by_date["unknown"].append(feature)
        
        logger.info(f"[CHART] Grouped {len(features)} tiles into {len(tiles_by_date)} acquisition dates")
        
        return dict(tiles_by_date)
    
    @classmethod
    def _select_best_date_group(
        cls, 
        tiles_by_date: Dict[str, List[Dict[str, Any]]], 
        query_bbox: Optional[List[float]] = None,
        weights: Optional[Dict[str, float]] = None
    ) -> Tuple[str, List[Dict[str, Any]]]:
        """
        Select the best acquisition date based on:
        1. Recency (most recent is better)
        2. Coverage (more tiles = better coverage)
        3. Average cloud cover
        
        Returns:
            Tuple of (date_string, list_of_features)
        """
        if not tiles_by_date:
            return ("unknown", [])
        
        # Skip "unknown" dates in ranking
        date_scores = []
        
        for date_str, tiles in tiles_by_date.items():
            if date_str == "unknown":
                continue
                
            # Calculate recency score
            try:
                date = datetime.strptime(date_str, "%Y-%m-%d")
                days_old = (datetime.now() - date).days
                
                # More recent = higher score (0-100)
                if days_old <= 7:
                    recency_score = 100
                elif days_old <= 30:
                    recency_score = 80
                elif days_old <= 90:
                    recency_score = 60
                elif days_old <= 365:
                    recency_score = 40
                else:
                    recency_score = max(10, 30 - (days_old // 365) * 5)  # Decay over years
            except:
                recency_score = 50
            
            # Calculate coverage score (number of tiles normalized)
            coverage_score = min(100, len(tiles) * 20)  # 5+ tiles = 100%
            
            # Calculate average cloud cover score
            cloud_scores = []
            for tile in tiles:
                cloud = tile.get("properties", {}).get("eo:cloud_cover")
                if cloud is not None:
                    cloud_scores.append(100 - cloud)  # Lower cloud = higher score
            
            avg_cloud_score = sum(cloud_scores) / len(cloud_scores) if cloud_scores else 50
            
            # Weighted total (prioritize recency, then coverage, then cloud)
            total_score = (recency_score * 0.5) + (coverage_score * 0.3) + (avg_cloud_score * 0.2)
            
            date_scores.append({
                "date": date_str,
                "tiles": tiles,
                "score": total_score,
                "recency": recency_score,
                "coverage": coverage_score,
                "cloud": avg_cloud_score
            })
        
        if not date_scores:
            # Only "unknown" dates available
            return ("unknown", tiles_by_date.get("unknown", []))
        
        # Sort by score (highest first)
        date_scores.sort(key=lambda x: x["score"], reverse=True)
        
        best = date_scores[0]
        logger.info(f"[DATE] Best acquisition date: {best['date']} (score={best['score']:.1f}, tiles={len(best['tiles'])}, recency={best['recency']}, cloud={best['cloud']:.1f})")
        
        return (best["date"], best["tiles"])
    
    @classmethod
    def _determine_scoring_weights(cls, query: Optional[str]) -> Dict[str, float]:
        """
        Dynamically adjust scoring weights based on user intent
        
        Returns:
            Dict with weights that sum to 100:
            {
                "recency": 0-100,
                "cloud_cover": 0-100,
                "coverage": 0-100,
                "quality_flags": 0-100
            }
        """
        # Default balanced weights
        weights = {
            "recency": 40.0,
            "cloud_cover": 30.0,
            "coverage": 20.0,
            "quality_flags": 10.0
        }
        
        if not query:
            return weights
        
        query_lower = query.lower()
        
        # PRIORITY 1: User explicitly wants MOST RECENT
        if any(term in query_lower for term in [
            'most recent', 'latest', 'newest', 'current', 'now', 'today',
            'right now', 'present', 'up to date'
        ]):
            logger.info("[TIME] User intent: MOST RECENT -> Prioritizing recency (70%)")
            weights = {
                "recency": 70.0,      # Heavily prioritize recency
                "cloud_cover": 15.0,  # Still care about quality
                "coverage": 10.0,
                "quality_flags": 5.0
            }
        
        # PRIORITY 2: User explicitly wants CLEAR/CLOUDLESS
        elif any(term in query_lower for term in [
            'clear', 'cloudless', 'no cloud', 'low cloud', 'cloud-free',
            'clearest', 'best quality', 'high quality', 'good quality'
        ]):
            logger.info("[SUN] User intent: CLEAR IMAGERY -> Prioritizing cloud cover (60%)")
            weights = {
                "recency": 15.0,
                "cloud_cover": 60.0,  # Heavily prioritize clear skies
                "coverage": 15.0,
                "quality_flags": 10.0
            }
        
        # PRIORITY 3: User explicitly wants HIGH RESOLUTION
        elif any(term in query_lower for term in [
            'high resolution', 'high res', 'detailed', 'fine detail',
            'highest resolution', 'best resolution'
        ]):
            logger.info("[SEARCH] User intent: HIGH RESOLUTION -> Prioritizing quality (50%)")
            weights = {
                "recency": 20.0,
                "cloud_cover": 20.0,
                "coverage": 10.0,
                "quality_flags": 50.0  # Heavily prioritize resolution/quality
            }
        
        # PRIORITY 4: User wants FULL COVERAGE
        elif any(term in query_lower for term in [
            'full coverage', 'complete coverage', 'entire area', 'whole region',
            'cover the area', 'cover the region'
        ]):
            logger.info("[MAP] User intent: FULL COVERAGE -> Prioritizing coverage (50%)")
            weights = {
                "recency": 20.0,
                "cloud_cover": 15.0,
                "coverage": 50.0,  # Heavily prioritize spatial coverage
                "quality_flags": 15.0
            }
        else:
            logger.info("[SCALE] User intent: BALANCED -> Using default weights")
        
        return weights
    
    @classmethod
    def _score_tile(
        cls,
        feature: Dict[str, Any],
        query_bbox: Optional[List[float]] = None,
        collections: Optional[List[str]] = None,
        weights: Optional[Dict[str, float]] = None
    ) -> Dict[str, float]:
        """
        Score a single tile across multiple quality dimensions
        
        Args:
            weights: Dynamic weights based on user intent (if None, uses defaults)
        
        Returns:
            Dict with scores for each dimension + total:
            {
                "recency": 0-100,
                "cloud_cover": 0-100,
                "coverage": 0-100,
                "quality_flags": 0-100,
                "total": 0-100
            }
        """
        # Use provided weights or defaults
        if weights is None:
            weights = {
                "recency": 40.0,
                "cloud_cover": 30.0,
                "coverage": 20.0,
                "quality_flags": 10.0
            }
        
        scores = {
            "recency": 0.0,
            "cloud_cover": 0.0,
            "coverage": 0.0,
            "quality_flags": 0.0,
            "total": 0.0
        }
        
        properties = feature.get("properties", {})
        
        # =================================================================
        # DIMENSION 1: RECENCY (normalized 0-100, then weighted)
        # =================================================================
        recency_raw = 0.0
        datetime_str = properties.get("datetime")
        if datetime_str:
            try:
                tile_date = datetime.fromisoformat(datetime_str.replace('Z', '+00:00'))
                today = datetime.now(tile_date.tzinfo)
                
                days_old = (today - tile_date).days
                
                # Normalized scoring curve (0-100):
                # - 0-7 days old: 100 points (perfect)
                # - 7-30 days: 85-100 points (excellent)
                # - 30-60 days: 60-85 points (good)
                # - 60-180 days: 30-60 points (acceptable)
                # - 180+ days: 0-30 points (old)
                
                if days_old <= 7:
                    recency_raw = 100.0
                elif days_old <= 30:
                    recency_raw = 100.0 - ((days_old - 7) / 23) * 15  # 85-100
                elif days_old <= 60:
                    recency_raw = 85.0 - ((days_old - 30) / 30) * 25  # 60-85
                elif days_old <= 180:
                    recency_raw = 60.0 - ((days_old - 60) / 120) * 30  # 30-60
                else:
                    recency_raw = max(0, 30.0 - ((days_old - 180) / 180) * 30)  # 0-30
                
            except Exception as e:
                logger.debug(f"Could not parse datetime '{datetime_str}': {e}")
                recency_raw = 50.0  # Neutral score if date parsing fails
        else:
            # No date available (e.g., DEMs) - give neutral score
            recency_raw = 50.0
        
        # Apply weight to get final score
        scores["recency"] = (recency_raw / 100.0) * weights["recency"]
        
        # =================================================================
        # DIMENSION 2: CLOUD COVER (normalized 0-100, then weighted)
        # =================================================================
        cloud_raw = 0.0
        cloud_cover = properties.get("eo:cloud_cover")
        
        if cloud_cover is not None:
            # Normalized scoring curve (0-100):
            # - 0-5% clouds: 100 points (perfect)
            # - 5-10%: 80-100 points (excellent)
            # - 10-20%: 50-80 points (good)
            # - 20-50%: 15-50 points (acceptable)
            # - 50-100%: 0-15 points (poor)
            
            if cloud_cover <= 5:
                cloud_raw = 100.0
            elif cloud_cover <= 10:
                cloud_raw = 100.0 - ((cloud_cover - 5) / 5) * 20  # 80-100
            elif cloud_cover <= 20:
                cloud_raw = 80.0 - ((cloud_cover - 10) / 10) * 30  # 50-80
            elif cloud_cover <= 50:
                cloud_raw = 50.0 - ((cloud_cover - 20) / 30) * 35  # 15-50
            else:
                cloud_raw = max(0, 15.0 - ((cloud_cover - 50) / 50) * 15)  # 0-15
        else:
            # No cloud cover data (SAR, DEMs, etc.) - give full score
            cloud_raw = 100.0
        
        # Apply weight to get final score
        scores["cloud_cover"] = (cloud_raw / 100.0) * weights["cloud_cover"]
        
        # =================================================================
        # DIMENSION 3: SPATIAL COVERAGE (normalized 0-100, then weighted)
        # =================================================================
        coverage_raw = 0.0
        if query_bbox:
            tile_bbox = feature.get("bbox")
            if tile_bbox and len(tile_bbox) == 4:
                overlap = cls._calculate_overlap(query_bbox, tile_bbox)
                
                # Normalized scoring curve (0-100):
                # - 90-100% overlap: 100 points (perfect)
                # - 50-90%: 50-100 points (good)
                # - 10-50%: 25-50 points (partial)
                # - 0-10%: 0-25 points (minimal)
                
                if overlap >= 0.9:
                    coverage_raw = 100.0
                elif overlap >= 0.5:
                    coverage_raw = 50.0 + ((overlap - 0.5) / 0.4) * 50  # 50-100
                elif overlap >= 0.1:
                    coverage_raw = 25.0 + ((overlap - 0.1) / 0.4) * 25  # 25-50
                else:
                    coverage_raw = overlap * 250  # 0-25
            else:
                coverage_raw = 50.0  # Neutral if no bbox
        else:
            coverage_raw = 100.0  # Full score if no bbox to compare
        
        # Apply weight to get final score
        scores["coverage"] = (coverage_raw / 100.0) * weights["coverage"]
        
        # =================================================================
        # DIMENSION 4: QUALITY FLAGS (normalized 0-100, then weighted)
        # =================================================================
        # Check for quality metadata
        quality_raw = 50.0  # Neutral default
        
        # Landsat quality flags
        if "landsat:quality" in properties:
            quality = properties["landsat:quality"]
            if quality == "high":
                quality_raw = 100.0
            elif quality == "medium":
                quality_raw = 70.0
            elif quality == "low":
                quality_raw = 30.0
        
        # Sentinel-2 processing level
        elif "s2:processing_baseline" in properties:
            # Higher processing baselines = better calibration
            quality_raw = 80.0
        
        # General quality flags
        elif "quality" in properties:
            quality = properties["quality"]
            if isinstance(quality, (int, float)):
                # Assume 0-100 scale
                quality_raw = quality
        
        # Apply weight to get final score
        scores["quality_flags"] = (quality_raw / 100.0) * weights["quality_flags"]
        
        # =================================================================
        # CALCULATE TOTAL SCORE (weights already applied, sum to 100)
        # =================================================================
        scores["total"] = (
            scores["recency"] + 
            scores["cloud_cover"] + 
            scores["coverage"] + 
            scores["quality_flags"]
        )
        
        return scores
    
    @staticmethod
    def _calculate_overlap(bbox1: List[float], bbox2: List[float]) -> float:
        """
        Calculate percentage overlap between two bounding boxes
        
        Args:
            bbox1: [west, south, east, north] - query bbox
            bbox2: [west, south, east, north] - tile bbox
            
        Returns:
            Float 0.0-1.0 representing overlap percentage
        """
        if not bbox1 or not bbox2 or len(bbox1) != 4 or len(bbox2) != 4:
            return 0.0
        
        # Calculate intersection
        west = max(bbox1[0], bbox2[0])
        south = max(bbox1[1], bbox2[1])
        east = min(bbox1[2], bbox2[2])
        north = min(bbox1[3], bbox2[3])
        
        # No overlap
        if west >= east or south >= north:
            return 0.0
        
        # Calculate areas
        intersection_area = (east - west) * (north - south)
        bbox1_area = (bbox1[2] - bbox1[0]) * (bbox1[3] - bbox1[1])
        
        if bbox1_area == 0:
            return 0.0
        
        # Return overlap as percentage of query bbox
        return intersection_area / bbox1_area
    
    @classmethod
    def _calculate_optimal_tile_limit(
        cls,
        bbox: Optional[List[float]],
        collections: Optional[List[str]] = None
    ) -> int:
        """
        Dynamically calculate optimal tile limit based on area size and collection characteristics
        
        This calculates how many tiles are actually needed to cover the area, then applies
        a multiplier to account for temporal coverage (multiple revisits over time range).
        
        Args:
            bbox: [west, south, east, north] in degrees
            collections: STAC collection IDs
            
        Returns:
            Optimal query limit (minimum 50, maximum 1000)
        """
        if not bbox or len(bbox) != 4:
            logger.info(f"[PIN] No bbox provided -> default limit: 100")
            return 100
        
        # =================================================================
        # STEP 1: CALCULATE AREA COVERAGE
        # =================================================================
        
        # Calculate query area in square degrees
        bbox_width_deg = bbox[2] - bbox[0]  # east - west
        bbox_height_deg = bbox[3] - bbox[1]  # north - south
        bbox_area_deg = bbox_width_deg * bbox_height_deg
        
        # Convert degrees to approximate km (at mid-latitude)
        # At equator: 1 degree ≈ 111 km
        # Adjust for latitude using cosine of mid-latitude
        mid_latitude = (bbox[1] + bbox[3]) / 2
        import math
        lat_correction = math.cos(math.radians(mid_latitude))
        
        bbox_width_km = bbox_width_deg * 111.0 * lat_correction  # Width adjusted for latitude
        bbox_height_km = bbox_height_deg * 111.0  # Height (latitude doesn't affect N-S distance)
        bbox_area_km2 = bbox_width_km * bbox_height_km
        
        logger.info(f"[RULER] Query area dimensions:")
        logger.info(f"   Degrees: {bbox_width_deg:.4f}° × {bbox_height_deg:.4f}° = {bbox_area_deg:.4f} sq°")
        logger.info(f"   Physical: {bbox_width_km:.1f}km × {bbox_height_km:.1f}km = {bbox_area_km2:.0f} km²")
        
        # =================================================================
        # STEP 2: DETERMINE TYPICAL TILE SIZE FOR COLLECTION
        # =================================================================
        
        # Collection-specific tile sizes (approximate coverage in km)
        # Based on actual STAC tile footprints
        tile_sizes = {
            # High-resolution optical (smaller tiles)
            "sentinel-2-l2a": 100,    # ~100km × 100km
            "landsat-c2-l2": 185,     # ~185km × 185km (Landsat scene)
            "landsat-8-c2-l2": 185,
            "landsat-9-c2-l2": 185,
            "hls2-l30": 100,          # HLS Landsat, follows Sentinel-2 grid
            "hls2-s30": 100,          # HLS Sentinel-2, follows Sentinel-2 grid
            "hls": 100,               # Legacy name (for backward compatibility)
            "hls-l30": 100,           # Legacy name
            "hls-s30": 100,           # Legacy name
            "naip": 50,               # High-res aerial, smaller tiles
            
            # Medium-resolution MODIS (large tiles ~1200km × 1200km)
            "modis-09A1-061": 1200,   # Surface reflectance 500m
            "modis-09Q1-061": 1200,   # Surface reflectance 250m
            "modis-13Q1-061": 1200,   # NDVI 250m
            "modis-13A1-061": 1200,   # NDVI 500m
            "modis-15A2H-061": 1200,  # LAI 500m - FEATURED
            "modis-17A3HGF-061": 1200, # NPP 500m - FEATURED
            "modis-17A2H-061": 1200,  # GPP 500m - FEATURED
            "modis-14A1-061": 1200,   # Fire daily - FEATURED
            "modis-14A2-061": 1200,   # Fire 8-day - FEATURED
            "modis-10A1-061": 1200,   # Snow cover - FEATURED
            "modis-11A1-061": 1200,   # Temperature - FEATURED
            
            # SAR (same as Sentinel-2)
            "sentinel-1-grd": 250,    # ~250km × 250km (wider than optical)
            "sentinel-1-rtc": 250,
            
            # DEMs (large tiles, global coverage)
            "cop-dem-glo-30": 1000,   # ~1° × 1° tiles
            "cop-dem-glo-90": 1000,
            "nasadem": 1000,
            "3dep-seamless": 500,
            "alos-dem": 1000,
        }
        
        # Determine tile size based on collections
        typical_tile_size_km = 100  # Default (Sentinel-2/HLS)
        
        if collections:
            # Strategy: Try dynamic STAC query first, fall back to hardcoded
            collection_tile_sizes = []
            
            for col in collections:
                # Try hardcoded first (fast)
                if col in tile_sizes:
                    collection_tile_sizes.append(tile_sizes[col])
                else:
                    # Try dynamic STAC query (slower, but handles all 113+ collections)
                    dynamic_size = cls._query_tile_size_from_stac(col)
                    if dynamic_size:
                        collection_tile_sizes.append(dynamic_size)
                        logger.info(f"   [SIGNAL] Dynamic query: {col} -> {dynamic_size}km tiles")
                    else:
                        # Ultimate fallback
                        collection_tile_sizes.append(100)
                        logger.info(f"   [WARN] Unknown collection {col}, using 100km default")
            
            # Use the smallest tile size if multiple collections
            # (ensures we fetch enough tiles for highest-resolution collection)
            typical_tile_size_km = min(collection_tile_sizes)
            logger.info(f"[MAP] Typical tile size for {collections}: {typical_tile_size_km}km × {typical_tile_size_km}km")
        else:
            logger.info(f"[MAP] Using default tile size: {typical_tile_size_km}km × {typical_tile_size_km}km")
        
        # =================================================================
        # STEP 3: CALCULATE SPATIAL TILE COUNT
        # =================================================================
        
        # How many tiles needed to cover the area spatially?
        tile_area_km2 = typical_tile_size_km * typical_tile_size_km
        
        # Number of tiles needed (with 30% overlap buffer for tile boundaries)
        # 30% margin ensures we cover more than the AOI boundary if tiles are available
        tiles_needed_spatial = math.ceil(bbox_area_km2 / tile_area_km2 * 1.3)
        
        logger.info(f"[CALC] Spatial calculation:")
        logger.info(f"   Query area: {bbox_area_km2:.0f} km²")
        logger.info(f"   Tile area: {tile_area_km2:.0f} km² ({typical_tile_size_km}×{typical_tile_size_km}km)")
        logger.info(f"   Tiles needed (spatial with 30% margin): {tiles_needed_spatial}")
        
        # =================================================================
        # STEP 4: APPLY TEMPORAL MULTIPLIER
        # =================================================================
        
        # For time-series collections, we need multiple temporal acquisitions
        # Default time range is 60 days, with revisit frequency:
        # - Sentinel-2: 5 days -> 12 acquisitions
        # - Landsat: 16 days -> 4 acquisitions
        # - HLS (combined): 2-3 days -> 20 acquisitions
        # - MODIS: daily -> 60 acquisitions
        # - DEMs: static -> 1 acquisition
        
        temporal_multiplier = 1.0  # Default: no temporal dimension
        
        if collections:
            is_dems = any(col in collections for col in cls.DEM_COLLECTIONS)
            is_modis = any("modis" in col.lower() for col in collections)
            is_hls = any("hls" in col.lower() for col in collections)
            is_landsat = any("landsat" in col.lower() for col in collections)
            is_sentinel2 = any("sentinel-2" in col.lower() for col in collections)
            
            if is_dems:
                # DEMs are static - only 1 acquisition needed per tile
                temporal_multiplier = 1.0
                logger.info(f"[TIME] Temporal multiplier: 1.0× (DEMs are static)")
            elif is_modis:
                # MODIS: daily revisit over 60 days = 60 options per tile
                # But we only need top few, so use 5× multiplier
                temporal_multiplier = 5.0
                logger.info(f"[TIME] Temporal multiplier: 5.0× (MODIS daily revisit)")
            elif is_hls:
                # HLS: 2-3 day revisit over 60 days = ~20 options per tile
                # Use 10× to have good temporal selection
                temporal_multiplier = 10.0
                logger.info(f"[TIME] Temporal multiplier: 10.0× (HLS 2-3 day revisit)")
            elif is_sentinel2:
                # Sentinel-2: 5 day revisit over 60 days = ~12 options per tile
                # Use 8× to have good temporal selection
                temporal_multiplier = 8.0
                logger.info(f"[TIME] Temporal multiplier: 8.0× (Sentinel-2 5-day revisit)")
            elif is_landsat:
                # Landsat: 16 day revisit over 60 days = ~4 options per tile
                # Use 4× to have all temporal options
                temporal_multiplier = 4.0
                logger.info(f"[TIME] Temporal multiplier: 4.0× (Landsat 16-day revisit)")
            else:
                # Unknown collection - use moderate multiplier
                temporal_multiplier = 5.0
                logger.info(f"[TIME] Temporal multiplier: 5.0× (default)")
        
        # =================================================================
        # STEP 5: CALCULATE FINAL LIMIT
        # =================================================================
        
        # Total tiles to query = spatial tiles × temporal multiplier
        calculated_limit = int(tiles_needed_spatial * temporal_multiplier)
        
        # Apply reasonable bounds
        # Minimum: 50 tiles (ensure some selection even for tiny areas)
        # Maximum: 1000 tiles (API performance limit)
        final_limit = max(50, min(1000, calculated_limit))
        
        logger.info(f"[TARGET] Optimal tile limit calculation:")
        logger.info(f"   Spatial tiles: {tiles_needed_spatial}")
        logger.info(f"   Temporal multiplier: {temporal_multiplier}×")
        logger.info(f"   Calculated: {calculated_limit}")
        logger.info(f"   Final (bounded): {final_limit}")
        
        # =================================================================
        # STEP 6: LOG RECOMMENDATION
        # =================================================================
        
        if final_limit == 50:
            logger.info(f"[PIN] TINY AREA: Using minimum limit (50)")
        elif final_limit < 150:
            logger.info(f"[PIN] SMALL AREA: Single tile or small mosaic")
        elif final_limit < 400:
            logger.info(f"[MAP] MEDIUM AREA: Multi-tile mosaic")
        elif final_limit < 800:
            logger.info(f"[MAP] LARGE AREA: Regional mosaic")
        else:
            logger.info(f"[MAP] VERY LARGE AREA: Using maximum limit (1000)")
        
        return final_limit
    
    
    @classmethod
    def _query_tile_size_from_stac(cls, collection_id: str) -> Optional[float]:
        """
        Query STAC collection metadata to dynamically determine tile size.
        
        This method queries the MPC STAC API to extract tile grid information
        from collection metadata. It looks for:
        1. proj:epsg grid definitions with tile dimensions
        2. Grid extension specifications
        3. Spatial resolution and typical footprint
        4. Item spatial extent statistics
        
        Args:
            collection_id: STAC collection ID
            
        Returns:
            Tile size in kilometers, or None if not available
            
        Example metadata structures:
            - Sentinel-2: Uses MGRS grid with ~100km tiles
            - Landsat: WRS-2 path/row grid with ~185km scenes
            - MODIS: Sinusoidal grid with ~1200km tiles
            - HLS: Follows Sentinel-2 MGRS grid
        """
        try:
            import requests
            from cloud_config import cloud_cfg
            
            stac_api = cloud_cfg.stac_catalog_url
            url = f"{stac_api}/collections/{collection_id}"
            
            response = requests.get(url, timeout=10)
            if not response.ok:
                logger.debug(f"Could not fetch STAC metadata for {collection_id}")
                return None
            
            metadata = response.json()
            
            # Method 1: Check for explicit grid:code specification
            # Some collections define their grid system
            summaries = metadata.get("summaries", {})
            
            # Sentinel-2 uses MGRS grid
            if "grid:code" in summaries or "s2:mgrs_tile" in summaries:
                logger.debug(f"   Detected MGRS grid (Sentinel-2): ~100km tiles")
                return 100.0
            
            # Landsat uses WRS-2 path/row
            if "landsat:wrs_path" in summaries or "landsat:wrs_row" in summaries:
                logger.debug(f"   Detected WRS-2 grid (Landsat): ~185km scenes")
                return 185.0
            
            # Method 2: Check spatial resolution and infer typical tile size
            # gsd = Ground Sample Distance (meters per pixel)
            if "gsd" in summaries:
                gsd = summaries["gsd"]
                if isinstance(gsd, list):
                    gsd = min(gsd)  # Highest resolution
                
                # High-res optical (10-30m) typically use smaller tiles
                if gsd <= 30:
                    logger.debug(f"   High-resolution ({gsd}m): ~100km tiles")
                    return 100.0
                # Medium-res (100-500m) use larger tiles
                elif gsd <= 500:
                    logger.debug(f"   Medium-resolution ({gsd}m): ~250km tiles")
                    return 250.0
                # Low-res (>500m) use very large tiles
                else:
                    logger.debug(f"   Low-resolution ({gsd}m): ~1200km tiles")
                    return 1200.0
            
            # Method 3: Check for known keywords in description
            description = metadata.get("description", "").lower()
            keywords = [k.lower() for k in metadata.get("keywords", [])]
            
            if "modis" in description or "modis" in keywords:
                logger.debug(f"   Detected MODIS: ~1200km tiles")
                return 1200.0
            
            if "dem" in keywords or "elevation" in keywords:
                logger.debug(f"   Detected DEM: ~1000km tiles")
                return 1000.0
            
            if "sar" in keywords or "sentinel-1" in description:
                logger.debug(f"   Detected SAR: ~250km tiles")
                return 250.0
            
            # Method 4: Sample actual item footprints (expensive, use as fallback)
            # This would require searching for items and analyzing their bboxes
            # For now, we'll skip this to avoid performance impact
            
            logger.debug(f"   Could not determine tile size from metadata")
            return None
            
        except Exception as e:
            logger.debug(f"Error querying STAC for tile size: {e}")
            return None
