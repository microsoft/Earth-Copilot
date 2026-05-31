"""
Planetary Computer Rendering System

This module provides rendering configurations for ALL Planetary Computer STAC collections
by loading official configs DIRECTLY from the planetary-computer-tasks repository.

ALL collections use TiTiler API:
- RGB optical imagery: TiTiler with assets + color_formula from PC configs
- Colormap data (SAR, DEM, MODIS): TiTiler with colormap_name + rescale from PC configs
- Single-band data: TiTiler with appropriate single-band params from PC configs

Architecture:
- STRICTLY uses configs from planetary-computer-tasks/datasets/*/config.json (via pc_tasks_config_loader)
- NO inference, NO fallbacks, NO additional logic
- If collection not in PC repo, returns None (handled by caller)
- Single source of truth: Live repository configs
- ALL collections build TiTiler URLs from scratch using PC configs

Config Loading Strategy:
- pc_tasks_config_loader.py: Loads DIRECTLY from planetary-computer-tasks repo (ONLY source for rendering)
- pc_metadata_loader.py: Loads from pre-extracted JSON files (used for GPT catalog only, NOT rendering)

Usage:
    from hybrid_rendering_system import HybridRenderingSystem
    
    # Get config (None if not in PC repo)
    config = HybridRenderingSystem.get_render_config("modis-14A1-061")
    
    # Build TiTiler URL with PC rendering params
    url = HybridRenderingSystem.build_titiler_tilejson_url(item_id, collection_id)
"""

from typing import Dict, List, Optional, Tuple, Any
from enum import Enum
import logging
import os
import re
import time

import requests

# Import PC config loader (single source of truth)
from pc_tasks_config_loader import get_pc_rendering_config, DataType, RenderingConfig

logger = logging.getLogger(__name__)


# ============================================================================
# FEATURED DATASETS - Microsoft Planetary Computer Priority Collections
# ============================================================================
# These collections are prioritized for optimal rendering quality
# Represents ~80% of typical Planetary Explorer queries

FEATURED_COLLECTIONS = [
    # High-resolution optical imagery
    "sentinel-2-l2a",
    "landsat-c2-l2",
    "landsat-c2-l1",      # Historical Landsat MSS (1972-2013)
    "hls2-l30",           # HLS Landsat
    "hls2-s30",           # HLS Sentinel-2
    "naip",
    
    # Elevation models
    "cop-dem-glo-30",
    "cop-dem-glo-90",
    "nasadem",
    
    # SAR imagery
    "sentinel-1-rtc",
    "sentinel-1-grd",
    
    # MODIS products (vegetation, fire, snow)
    "modis-13Q1-061",      # NDVI 250m
    "modis-13A1-061",      # NDVI 500m
    "modis-15A2H-061",     # LAI
    "modis-17A3HGF-061",   # NPP
    "modis-17A2H-061",     # GPP
    "modis-14A1-061",      # Fire daily
    "modis-14A2-061",      # Fire 8-day
    "modis-10A1-061",      # Snow cover
    "modis-11A1-061",      # Temperature
    "modis-43A4-061",      # NBAR daily (BRDF-corrected)
    "modis-09A1-061",      # Surface reflectance 500m
    "modis-09Q1-061",      # Surface reflectance 250m
]


class DataType(str, Enum):
    """STAC data types for rendering"""
    OPTICAL = "optical"
    OPTICAL_REFLECTANCE = "optical_reflectance"
    SAR = "sar"
    ELEVATION = "elevation"
    THERMAL = "thermal"
    VEGETATION = "vegetation"
    CLIMATE = "climate"
    OCEAN = "ocean"
    FIRE = "fire"
    SNOW = "snow"
    DEMOGRAPHICS = "demographics"
    UNKNOWN = "unknown"


class RenderingConfig:
    """Complete rendering configuration for a collection"""
    
    def __init__(
        self,
        collection_id: str,
        data_type: DataType,
        assets: Optional[List[str]] = None,
        rescale: Optional[Tuple[float, float]] = None,
        colormap: Optional[str] = None,
        resampling: str = "bilinear",
        color_formula: Optional[str] = None,
        bidx: Optional[int] = None,
        asset_bidx: Optional[str] = None,
        notes: str = "",
        params_to_remove: Optional[List[str]] = None,
        tile_scale: int = 2,
        min_zoom: int = 6,
        max_zoom: int = 22,
        buffer: Optional[int] = None,
        unscale: bool = False
    ):
        self.collection_id = collection_id
        self.data_type = data_type
        self.assets = assets
        self.rescale = rescale
        self.colormap = colormap
        self.resampling = resampling
        self.color_formula = color_formula
        self.bidx = bidx
        self.asset_bidx = asset_bidx  # e.g. "image|1,2,3" - slices bands from a multi-band asset
        self.notes = notes
        self.params_to_remove = params_to_remove or self._get_default_params_to_remove()
        self.tile_scale = tile_scale  # 2 = @2x (512x512 tiles), 1 = standard (256x256)
        self.min_zoom = min_zoom  # Minimum zoom level (prevent 404s)
        self.max_zoom = max_zoom  # Maximum zoom level (native resolution limit)
        self.buffer = buffer  # Tile buffer in pixels to prevent edge artifacts
        self.unscale = unscale  # Apply STAC scale/offset automatically
    
    def _get_default_params_to_remove(self) -> List[str]:
        """
        Get default parameters to remove from STAC API tilejson URLs.
        Different data types have different problematic parameters.
        """
        # Always remove these (universal problems)
        always_remove = [
            "asset_bidx",      # Causes 404 with MPC API
            "color_formula"    # Prevents duplicate color_formula parameters
        ]
        
        # Data-type specific removals
        if self.data_type in [DataType.OPTICAL, DataType.OPTICAL_REFLECTANCE]:
            # Optical imagery issues
            return always_remove + [
                "nodata",   # nodata=0 causes gray/blurry images (valid dark pixels treated as missing)
                "assets"    # Remove assets parameter - will use collection-specific assets from config
            ]
        elif self.data_type == DataType.SAR:
            # SAR imagery issues
            return always_remove + [
                "nodata"  # Can cause issues with dB values
            ]
        elif self.data_type == DataType.ELEVATION:
            # DEM issues
            return always_remove + [
                "nodata"  # Elevation nodata should be handled by colormap
            ]
        else:
            # Default: just remove universal problems
            return always_remove
    
    def clean_stac_url(self, url: str) -> str:
        """
        Clean a STAC tilejson URL by removing problematic parameters.
        This is collection-specific based on data type and known issues.
        
        Args:
            url: Original tilejson URL from STAC API
            
        Returns:
            Cleaned URL with problematic parameters removed
        """
        if "?" not in url:
            return url
        
        base_url, params = url.split("?", 1)
        param_list = params.split("&")
        
        # Filter out problematic parameters
        clean_params = []
        for param in param_list:
            should_remove = False
            for pattern in self.params_to_remove:
                if param.startswith(pattern):
                    should_remove = True
                    break
            if not should_remove:
                clean_params.append(param)
        
        # Rebuild URL
        if clean_params:
            return f"{base_url}?{'&'.join(clean_params)}"
        else:
            return base_url
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for TiTiler parameters"""
        params = {
            "scale": self.tile_scale,  # Use collection-specific tile scale
            "format": "png",
            "resampling": self.resampling,
            "min_zoom": self.min_zoom,  # Add zoom constraints
            "max_zoom": self.max_zoom
        }
        
        if self.assets:
            params["assets"] = self.assets
        if self.rescale:
            params["rescale"] = self.rescale
        if self.colormap:
            params["colormap_name"] = self.colormap
        if self.color_formula:
            params["color_formula"] = self.color_formula
        if self.bidx:
            params["bidx"] = self.bidx
        if self.asset_bidx:
            params["asset_bidx"] = self.asset_bidx
            
        return params
    
    def __repr__(self):
        return f"RenderingConfig({self.collection_id}, {self.data_type})"


# ============================================================================
# EXPLICIT COLLECTION CONFIGURATIONS (Priority 1)
# ============================================================================
# 
# [WARN] ARCHITECTURE NOTE:
# These configs are ONLY USED AS FALLBACKS when a collection is NOT found
# in pc_rendering_config.json (the golden source extracted from PC tasks repo).
# 
# The system's config loading priority is:
#   1. pc_rendering_config.json (via get_pc_rendering_config() - PRIMARY SOURCE)
#   2. EXPLICIT_RENDER_CONFIGS (this dictionary - FALLBACK ONLY)
#   3. STAC API metadata (automatic extraction - LAST RESORT)
# 
# To add a new collection properly:
#   1. Check if it exists in planetary-computer-tasks/datasets/
#   2. If YES: Run scripts/extract_all_pc_configs.py to add it to pc_rendering_config.json
#   3. If NO: Add it here with a clear note that it's "NOT IN PC TASKS"
# 
# Collections extracted from PC tasks (71+ available):
#   - chloris-biomass (biomass data with chloris-biomass colormap)
#   - mtbs (burn severity with mtbs-severity colormap)
#   - sentinel-1-rtc (SAR backscatter)
#   - All MODIS collections (19 sub-collections)
#   - Landsat, Sentinel-2, HLS, NAIP, etc.
# 
# ============================================================================

EXPLICIT_RENDER_CONFIGS: Dict[str, RenderingConfig] = {
    
    # === OPTICAL IMAGERY ===
    
    "hls2-s30": RenderingConfig(
        collection_id="hls2-s30",
        data_type=DataType.OPTICAL_REFLECTANCE,
        assets=["B04", "B03", "B02"],
        rescale=(0, 6000),  # Wider range to handle snow (reflectance 8000-9500) without clipping
        color_formula="gamma RGB 1.5, saturation 1.3, sigmoidal RGB 6 0.5",  # Balanced: avoids washing out snow scenes
        resampling="lanczos",  # Highest quality resampling
        tile_scale=2,  # @2x tiles (512x512) for sharp rendering
        min_zoom=8,  # 30m data useful from zoom 8+ (regional scale)
        max_zoom=18,  # Practical limit for 30m data (1 pixel ≈ 30m at zoom 16)
        buffer=256,  # Tile buffer to prevent edge artifacts during stitching
        unscale=True,  # Apply STAC metadata scale/offset automatically
        notes="HLS S30 - Harmonized Sentinel-2, 30m resolution, optimized for crisp rendering at zoom 12-16"
    ),
    
    "hls2-l30": RenderingConfig(
        collection_id="hls2-l30",
        data_type=DataType.OPTICAL_REFLECTANCE,
        assets=["B04", "B03", "B02"],
        rescale=(0, 6000),  # Wider range to handle snow (reflectance 8000-9500) without clipping
        color_formula="gamma RGB 1.5, saturation 1.3, sigmoidal RGB 6 0.5",  # Balanced: avoids washing out snow scenes
        resampling="lanczos",  # Highest quality resampling
        tile_scale=2,  # @2x tiles (512x512) for sharp rendering
        min_zoom=8,  # 30m data useful from zoom 8+ (regional scale)
        max_zoom=18,  # Practical limit for 30m data (beyond this magnifies pixels)
        buffer=256,  # Tile buffer to prevent edge artifacts during stitching
        unscale=True,  # Apply STAC metadata scale/offset automatically
        notes="HLS L30 - Harmonized Landsat, 30m resolution, optimized for crisp rendering at zoom 12-16"
    ),
    
    # NOTE: ``sentinel-2-l2a`` is intentionally NOT listed in
    # EXPLICIT_RENDER_CONFIGS. Its render configuration now lives as data:
    #   - Public mode  -> pc_rendering_config.json (sentinel-2 entry with a
    #     ``presets`` block; intent-aware via tier 2 of get_render_config).
    #   - Pro mode     -> private collection's live STAC ``renders`` block
    #     (intent-aware via tier 0 of get_render_config).
    # Keeping a hardcoded EXPLICIT entry here would short-circuit tier 1 and
    # defeat intent matching for Public mode (e.g. "show me fire" would
    # always pick natural-color regardless of query).

    # MPC Pro custom collection: Sentinel-2 L2A items ingested for fire
    # visualization. Uses SWIR false-color (B12=SWIR2, B11=SWIR1, B8A=NIR-narrow)
    # to highlight active burn perimeters (bright orange/red) and burn scars
    # (deep red) while making smoke largely transparent. Per-band rescale is
    # not supported by the single tuple here; (0, 6000) is a balanced average
    # that keeps SWIR bands from saturating while preserving NIR detail.
    # Without this entry HybridRenderingSystem returns empty params and the
    # /api/pro/tile endpoint renders solid white tiles.
    "sentinel2-fire": RenderingConfig(
        collection_id="sentinel2-fire",
        data_type=DataType.OPTICAL,
        assets=["B12", "B11", "B8A"],
        rescale=(0, 6000),
        color_formula="gamma RGB 1.6, saturation 1.4, sigmoidal RGB 10 0.5",
        resampling="lanczos",
        tile_scale=2,
        min_zoom=6,
        max_zoom=22,
        notes="MPC Pro sentinel2-fire — SWIR false-color (B12/B11/B8A) for active fire and burn-scar visualization"
    ),

    "landsat-c2-l1": RenderingConfig(
        collection_id="landsat-c2-l1",
        data_type=DataType.OPTICAL,
        assets=["nir08", "red", "green"],
        rescale=(0, 3000),  # TOA reflectance 0-10000 range, scaled to 0-3000 for proper contrast
        resampling="bilinear",
        color_formula="gamma RGB 2.5, saturation 1.3, sigmoidal RGB 12 0.5",
        tile_scale=2,  # @2x for highest resolution
        min_zoom=5,
        max_zoom=22,  # Native ~30m resolution
        notes="Landsat Collection 2 Level-1 TOA false color (NIR-R-G)"
    ),
    
    "landsat-c2-l2": RenderingConfig(
        collection_id="landsat-c2-l2",
        data_type=DataType.OPTICAL,
        assets=["red", "green", "blue"],
        rescale=(0, 3000),  # Surface reflectance 0-10000 range, scaled to 0-3000 for proper contrast (like Sentinel-2 L2A)
        resampling="bilinear",  # Bilinear for maximum sharpness (sharper than lanczos)
        tile_scale=4,  # @4x for ultra-high resolution (2048x2048 tiles)
        min_zoom=5,
        max_zoom=22,  # Native ~30m resolution, allow deep zoom
        color_formula="gamma RGB 2.7, saturation 1.5, sigmoidal RGB 15 0.55",
        notes="Landsat Collection 2 Level-2 surface reflectance with maximum sharpness - @4x tiles with bilinear resampling"
    ),
    
    # NAIP: public Planetary Computer publishes NAIP items with a single
    # 4-band ``image`` asset (R, G, B, NIR) -- NOT separate red/green/blue
    # assets. Requesting ``?assets=red&assets=green&assets=blue`` returns
    # 404. The correct rendering is ``assets=image&asset_bidx=image|1,2,3``.
    "naip": RenderingConfig(
        collection_id="naip",
        data_type=DataType.OPTICAL,
        assets=["image"],
        asset_bidx="image|1,2,3",
        resampling="lanczos",
        tile_scale=2,
        min_zoom=11,
        max_zoom=18,
        notes="NAIP single 4-band 'image' asset; asset_bidx slices bands 1,2,3 for natural-color RGB"
    ),

    "aster-l1t": RenderingConfig(
        collection_id="aster-l1t",
        data_type=DataType.OPTICAL,
        assets=["VNIR_Band3N", "VNIR_Band2", "VNIR_Band1"],  # NIR, Red, Green for false color
        rescale=(0, 255),
        resampling="lanczos",
        notes="ASTER Level 1T"
    ),
    
    # === MODIS OPTICAL ===
    
    "modis-43A4-061": RenderingConfig(
        collection_id="modis-43A4-061",
        data_type=DataType.OPTICAL_REFLECTANCE,
        assets=["Nadir_Reflectance_Band1", "Nadir_Reflectance_Band4", "Nadir_Reflectance_Band3"],  # Red, Green, Blue
        rescale=(0, 2500),  # NBAR scaled 0-10000, using 0-2500 for typical surfaces
        resampling="bilinear",
        notes="MODIS NBAR daily 500m - BRDF-corrected reflectance at local solar noon (16-day moving window)"
    ),
    
    "modis-09A1-061": RenderingConfig(
        collection_id="modis-09A1-061",
        data_type=DataType.OPTICAL_REFLECTANCE,
        assets=["sur_refl_b01", "sur_refl_b04", "sur_refl_b03"],  # Red, Green, Blue
        rescale=(0, 8000),  # Typical MODIS surface reflectance range for Earth surfaces (scale factor 0.0001)
        resampling="bilinear",
        notes="MODIS 8-day surface reflectance 500m - optimized for typical Earth surface values"
    ),
    
    "modis-09Q1-061": RenderingConfig(
        collection_id="modis-09Q1-061",
        data_type=DataType.OPTICAL_REFLECTANCE,
        assets=["sur_refl_b01", "sur_refl_b02"],  # Red, NIR (no blue band)
        rescale=(0, 8000),  # Typical MODIS surface reflectance range for Earth surfaces (scale factor 0.0001)
        resampling="bilinear",
        notes="MODIS 8-day surface reflectance 250m (Red/NIR only) - optimized for typical Earth surface values"
    ),
    
    # === ELEVATION/DEM ===
    
    "cop-dem-glo-30": RenderingConfig(
        collection_id="cop-dem-glo-30",
        data_type=DataType.ELEVATION,
        assets=["data"],  # Single-band elevation asset
        rescale=(0, 4000),
        colormap="terrain",
        resampling="cubic",
        notes="Copernicus DEM 30m, optimized for common terrain elevations - single-band asset doesn't need bidx"
    ),
    
    "cop-dem-glo-90": RenderingConfig(
        collection_id="cop-dem-glo-90",
        data_type=DataType.ELEVATION,
        assets=["data"],  # Single-band elevation asset
        rescale=(0, 4000),
        colormap="terrain",
        resampling="cubic",
        notes="Copernicus DEM 90m - single-band asset doesn't need bidx"
    ),
    
    "nasadem": RenderingConfig(
        collection_id="nasadem",
        data_type=DataType.ELEVATION,
        assets=["elevation"],  # Single-band elevation asset
        rescale=(0, 4000),
        colormap="terrain",
        resampling="cubic",
        notes="NASA DEM - single-band asset doesn't need bidx"
    ),
    
    "3dep-seamless": RenderingConfig(
        collection_id="3dep-seamless",
        data_type=DataType.ELEVATION,
        assets=["data"],  # Single-band elevation asset
        rescale=(0, 4000),
        colormap="terrain",
        resampling="cubic",
        notes="USGS 3DEP seamless DEM - single-band asset doesn't need bidx"
    ),
    
    "alos-dem": RenderingConfig(
        collection_id="alos-dem",
        data_type=DataType.ELEVATION,
        assets=["data"],  # Single-band elevation asset
        rescale=(0, 4000),
        colormap="terrain",
        resampling="cubic",
        notes="ALOS World 3D DEM - single-band asset doesn't need bidx"
    ),
    
    # === SAR/RADAR ===
    
    "sentinel-1-grd": RenderingConfig(
        collection_id="sentinel-1-grd",
        data_type=DataType.SAR,
        assets=["vv"],  # VV polarization (single-band asset)
        rescale=(-25, 0),  # SAR backscatter in dB: -25 (water/dark) to 0 (bright/urban)
        colormap="greys",
        resampling="bilinear",
        tile_scale=2,  # @2x for better SAR detail
        min_zoom=6,
        max_zoom=20,  # Native ~10m resolution
        notes="Sentinel-1 Ground Range Detected SAR - single-band asset doesn't need bidx"
    ),
    
    "sentinel-1-rtc": RenderingConfig(
        collection_id="sentinel-1-rtc",
        data_type=DataType.SAR,
        assets=["vv"],  # VV polarization (single-band asset)
        rescale=(-25, 0),  # SAR backscatter in dB: -25 (water/dark) to 0 (bright/urban)
        colormap="greys",
        resampling="bilinear",
        tile_scale=2,  # @2x for better SAR detail
        min_zoom=6,
        max_zoom=20,  # Native ~10m resolution
        notes="Sentinel-1 Radiometrically Terrain Corrected - single-band asset doesn't need bidx"
    ),
    
    "alos-palsar-mosaic": RenderingConfig(
        collection_id="alos-palsar-mosaic",
        data_type=DataType.SAR,
        assets=["HH"],  # HH polarization (single-band asset)
        rescale=None,
        colormap="greys",
        resampling="bilinear",
        notes="ALOS PALSAR annual mosaic - single-band asset doesn't need bidx"
    ),
    
    # === VEGETATION INDICES ===
    
    "modis-13Q1-061": RenderingConfig(
        collection_id="modis-13Q1-061",
        data_type=DataType.VEGETATION,
        assets=["250m_16_days_NDVI"],
        rescale=(-2000, 10000),  # MODIS NDVI scaled by 10000
        colormap="rdylgn",
        resampling="bilinear",
        tile_scale=1,  # Native resolution, don't oversample
        min_zoom=8,  # Enforce minimum to avoid 404s
        max_zoom=18,  # Native ~250m resolution
        notes="MODIS 16-day NDVI 250m - single-band asset doesn't need bidx"
    ),
    
    "modis-13A1-061": RenderingConfig(
        collection_id="modis-13A1-061",
        data_type=DataType.VEGETATION,
        assets=["500m_16_days_NDVI"],
        rescale=(-2000, 10000),
        colormap="rdylgn",
        resampling="bilinear",
        tile_scale=1,  # Native resolution, don't oversample
        min_zoom=8,  # Enforce minimum to avoid 404s
        max_zoom=18,  # Native ~500m resolution
        notes="MODIS 16-day NDVI 500m - single-band asset doesn't need bidx"
    ),
    
    "modis-15A2H-061": RenderingConfig(
        collection_id="modis-15A2H-061",
        data_type=DataType.VEGETATION,
        assets=["Lai_500m"],
        rescale=(0, 100),  # LAI values scaled by 10
        colormap="viridis",
        resampling="bilinear",
        notes="MODIS 8-day Leaf Area Index (LAI) 500m - single-band asset doesn't need bidx"
    ),
    
    "modis-17A3HGF-061": RenderingConfig(
        collection_id="modis-17A3HGF-061",
        data_type=DataType.VEGETATION,
        assets=["Npp_500m"],
        rescale=(0, 32700),  # NPP in kg C/m^2
        colormap="greens",
        resampling="bilinear",
        notes="MODIS Annual Net Primary Productivity (NPP) 500m - single-band asset doesn't need bidx"
    ),
    
    "modis-17A2H-061": RenderingConfig(
        collection_id="modis-17A2H-061",
        data_type=DataType.VEGETATION,
        assets=["Gpp"],
        rescale=(0, 30000),  # GPP in kg C/m^2
        colormap="greens",
        resampling="bilinear",
        notes="MODIS 8-day Gross Primary Productivity (GPP) 500m - single-band asset doesn't need bidx"
    ),
    
    # === THERMAL ===
    
    "modis-11A1-061": RenderingConfig(
        collection_id="modis-11A1-061",
        data_type=DataType.THERMAL,
        assets=["LST_Day_1km"],
        rescale=(250, 330),  # Kelvin
        colormap="plasma",
        resampling="bilinear",
        min_zoom=10,  # [OK] FIX: 1km resolution requires zoom 10+ for tile generation
        max_zoom=18,
        notes="MODIS daily land surface temperature - 1km resolution, single-band asset doesn't need bidx"
    ),
    
    # === FIRE ===
    
    "modis-14A1-061": RenderingConfig(
        collection_id="modis-14A1-061",
        data_type=DataType.FIRE,
        assets=["FireMask"],
        bidx=1,  # FireMask has 8 bands (one per day), select first band for colormap compatibility
        colormap="modis-14A1|A2",  # Official MPC colormap for MODIS fire (transparent background, red/orange fire)
        resampling="nearest",  # Nearest neighbor for categorical data
        tile_scale=2,  # @2x for better visibility at lower zoom levels
        min_zoom=4,  # Show tiles even when zoomed out (good for state/country level views)
        max_zoom=18,  # Native ~1km resolution
        notes="MODIS daily fire mask using official MPC colormap (transparent background, fire pixels in red/orange)"
    ),
    
    "modis-14A2-061": RenderingConfig(
        collection_id="modis-14A2-061",
        data_type=DataType.FIRE,
        assets=["FireMask"],
        bidx=1,  # FireMask has 8 bands (one per 8-day period), select first band for colormap compatibility
        colormap="modis-14A1|A2",  # Official MPC colormap for MODIS fire (transparent background, red/orange fire)
        resampling="nearest",  # Nearest neighbor for categorical data
        tile_scale=2,  # @2x for better visibility at lower zoom levels
        min_zoom=4,  # Show tiles even when zoomed out (good for state/country level views)
        max_zoom=18,
        notes="MODIS 8-day fire mask using official MPC colormap (transparent background, fire pixels in red/orange)"
    ),
    
    "modis-MCD64A1-061": RenderingConfig(
        collection_id="modis-MCD64A1-061",
        data_type=DataType.FIRE,
        assets=["Burn_Date"],  # Single-band categorical asset
        rescale=(1, 366),  # Day of year when burn detected
        colormap="magma",
        resampling="nearest",
        tile_scale=2,  # 2x upsampling for 500m resolution burned area visibility
        min_zoom=8,
        max_zoom=18,
        notes="MODIS burned area monthly - 500m resolution, single-band asset doesn't need bidx"
    ),
    
    # === SNOW & ICE ===
    
    "modis-10A1-061": RenderingConfig(
        collection_id="modis-10A1-061",
        data_type=DataType.SNOW,
        assets=["NDSI_Snow_Cover"],  # Single-band percentage asset
        rescale=(0, 100),  # Snow cover percentage
        colormap="blues",
        resampling="nearest",
        notes="MODIS Daily Snow Cover 500m - single-band asset doesn't need bidx"
    ),
    
    # === CLIMATE ===
    
    "era5-pds": RenderingConfig(
        collection_id="era5-pds",
        data_type=DataType.CLIMATE,
        assets=["air_temperature_at_2_metres"],  # Single-band temperature asset
        rescale=(250, 320),  # Kelvin
        colormap="turbo",
        resampling="bilinear",
        notes="ERA5 reanalysis temperature - single-band asset doesn't need bidx"
    ),
    
    # === OCEAN ===
    
    "mur-sst": RenderingConfig(
        collection_id="mur-sst",
        data_type=DataType.OCEAN,
        assets=["analysed_sst"],  # Single-band SST asset
        rescale=(0, 35),  # Celsius (typical ocean temp range 0°C to 35°C)
        colormap="rdylbu_r",  # Red-yellow-blue reversed: warm=red, cold=blue
        resampling="bilinear",
        notes="Multi-scale Ultra-high Resolution Sea Surface Temperature - single-band asset doesn't need bidx"
    ),
    
    "noaa-cdr-sea-surface-temperature-whoi": RenderingConfig(
        collection_id="noaa-cdr-sea-surface-temperature-whoi",
        data_type=DataType.OCEAN,
        assets=["sea_surface_temperature"],  # Single-band SST asset
        rescale=(0, 35),  # Celsius (typical ocean temp range 0°C to 35°C)
        colormap="rdylbu_r",  # Red-yellow-blue reversed: warm=red, cold=blue
        resampling="bilinear",
        notes="NOAA CDR Sea Surface Temperature (WHOI) - global 0.25° resolution daily SST"
    ),
    
    # Add more explicit configs as needed...
}


# ============================================================================
# CATEGORY-BASED DEFAULTS (Priority 2)
# ============================================================================

CATEGORY_DEFAULTS: Dict[DataType, Dict[str, Any]] = {
    
    DataType.OPTICAL: {
        "assets": ["red", "green", "blue"],
        "rescale": None,  # Auto-detect
        "resampling": "lanczos",
        "colormap": None
    },
    
    DataType.OPTICAL_REFLECTANCE: {
        "assets": ["red", "green", "blue"],
        "rescale": (0, 3000),  # Common for surface reflectance
        "resampling": "lanczos",
        "colormap": None
    },
    
    DataType.ELEVATION: {
        "assets": ["data"],
        "rescale": (0, 4000),
        "colormap": "terrain",
        "resampling": "cubic",
        "bidx": 1
    },
    
    DataType.SAR: {
        "assets": ["vv"],
        "rescale": None,  # Auto-detect dB values
        "colormap": "greys",
        "resampling": "bilinear",
        "bidx": 1
    },
    
    DataType.THERMAL: {
        "assets": None,  # Must be determined per collection
        "rescale": (250, 330),  # Kelvin
        "colormap": "plasma",
        "resampling": "bilinear",
        "bidx": 1
    },
    
    DataType.VEGETATION: {
        "assets": None,  # Must be determined per collection
        "rescale": (-1, 1),  # Standard for normalized indices
        "colormap": "rdylgn",
        "resampling": "bilinear",
        "bidx": 1
    },
    
    DataType.CLIMATE: {
        "assets": None,  # Too variable
        "rescale": None,  # Auto-detect
        "colormap": "viridis",
        "resampling": "bilinear",
        "bidx": 1
    },
    
    DataType.OCEAN: {
        "assets": None,
        "rescale": (0, 35),  # SST in Celsius
        "colormap": "rdylbu_r",  # Red-yellow-blue reversed: warm=red, cold=blue
        "resampling": "bilinear",
        "bidx": 1
    },
    
    DataType.FIRE: {
        "assets": None,
        "rescale": None,
        "colormap": "hot",
        "resampling": "nearest",  # Categorical
        "bidx": 1
    },
}


# ============================================================================
# COLLECTION FAMILY PATTERNS (Priority 3)
# ============================================================================

def match_collection_family(collection_id: str) -> Optional[DataType]:
    """
    Match collection ID to a family pattern for smart defaults.
    
    Examples:
    - modis-* -> Check which MODIS product
    - sentinel-1-* -> SAR
    - *-dem-* -> Elevation
    """
    coll_lower = collection_id.lower()
    
    # Elevation patterns
    if any(pattern in coll_lower for pattern in ["dem", "dsm", "dtm", "elevation"]):
        return DataType.ELEVATION
    
    # SAR patterns
    if "sentinel-1" in coll_lower or "sar" in coll_lower or "palsar" in coll_lower:
        return DataType.SAR
    
    # Vegetation patterns
    if any(pattern in coll_lower for pattern in ["ndvi", "evi", "lai", "fpar"]):
        return DataType.VEGETATION
    
    # Thermal patterns
    if any(pattern in coll_lower for pattern in ["lst", "thermal", "temperature"]) and "modis" in coll_lower:
        return DataType.THERMAL
    
    # Fire patterns
    if "fire" in coll_lower or "burn" in coll_lower:
        return DataType.FIRE
    
    # Ocean patterns
    if any(pattern in coll_lower for pattern in ["sst", "ocean", "sea"]):
        return DataType.OCEAN
    
    # Climate patterns
    if any(pattern in coll_lower for pattern in ["era5", "climate", "weather"]):
        return DataType.CLIMATE
    
    # Default to optical for satellite imagery
    if any(pattern in coll_lower for pattern in ["sentinel-2", "landsat", "hls", "modis-09", "naip"]):
        return DataType.OPTICAL
    
    return None


# ============================================================================
# STAC METADATA INFERENCE (Priority 4)
# ============================================================================

MPC_STAC_API = "https://planetarycomputer.microsoft.com/api/stac/v1"
METADATA_CACHE: Dict[str, Dict[str, Any]] = {}


def fetch_stac_metadata(collection_id: str) -> Optional[Dict[str, Any]]:
    """Fetch STAC collection metadata with caching"""
    if collection_id in METADATA_CACHE:
        return METADATA_CACHE[collection_id]
    
    try:
        url = f"{MPC_STAC_API}/collections/{collection_id}"
        response = requests.get(url, timeout=10)
        
        if response.ok:
            metadata = response.json()
            METADATA_CACHE[collection_id] = metadata
            return metadata
    except Exception as e:
        logger.error(f"Failed to fetch STAC metadata for {collection_id}: {e}")
    
    return None


# ============================================================================
# TIER-3 RENDER-CONFIG FETCHER: Live STAC ``renders`` extension
# ============================================================================
#
# Why this exists:
#   Both Public Planetary Computer and MPC Pro / GeoCatalog publish per-
#   collection render presets via the STAC ``renders`` extension at
#   ``{stac_base}/collections/{id}``. The PC Explorer and TiTiler examples
#   consume this block directly. We do the same here so that:
#
#     * New Public PC collections work the moment PC publishes their
#       ``renders`` template -- no commit needed in this repo.
#     * Custom Pro collections (e.g. ``sentinel2-fire``) work the moment
#       a render preset is registered on the GeoCatalog collection. The
#       data owner controls the rendering, not the application.
#
# Where it sits in the lookup order:
#   1. EXPLICIT_RENDER_CONFIGS  -- intentional overrides only
#   2. pc_rendering_config.json -- pre-extracted PC repo snapshot
#   3. STAC live ``renders``    -- THIS BLOCK (Public PC + Pro fallback)
#
# Cache:
#   In-memory, TTL = ``_STAC_RENDERS_TTL_SEC`` (default 600s = 10 min).
#   Negative results are cached too (with a shorter TTL) to avoid
#   hammering the STAC API for collections that simply have no renders
#   block.
#
# Auth:
#   Public PC is anonymous. Pro requires AAD. We use the sync
#   DefaultAzureCredential here (sibling module pro_stac_client uses the
#   async one for request hot paths). The token is cached for ~55 min.
# ============================================================================

_STAC_RENDERS_TTL_SEC = 600  # 10 minutes — preset edits propagate within
_STAC_RENDERS_NEG_TTL_SEC = 60
# {(collection_id, is_pro): (expires_at_epoch, renders_dict | None)}
# We cache the FULL renders block (not a pre-picked RenderingConfig) so the
# intent-aware picker can choose a different preset per query without
# re-fetching. None = collection has no renders block (or fetch failed).
# is_pro is part of the key because the same collection id can exist in both
# Public PC and a private GeoCatalog with DIFFERENT renders blocks (e.g. a
# private mirror that publishes additional presets the public copy lacks).
_STAC_RENDERS_CACHE: Dict[Tuple[str, bool], Tuple[float, Optional[Dict[str, Any]]]] = {}

_PRO_AUDIENCE = "https://geocatalog.spatio.azure.com"
_PRO_API_VERSION = "2025-04-30-preview"
_PRO_TOKEN_CACHE: Dict[str, Tuple[str, float]] = {}


def _get_pro_token_sync() -> Optional[str]:
    """Sync AAD bearer for the Pro STAC. Returns None if unavailable.

    Mirrors :func:`pro_stac_client._acquire_token` but is sync so it can
    be called from synchronous render-config lookups. Tokens are cached
    in :data:`_PRO_TOKEN_CACHE` for ~55 minutes.
    """
    now = time.time()
    cached = _PRO_TOKEN_CACHE.get(_PRO_AUDIENCE)
    if cached and cached[1] - now > 60:
        return cached[0]
    try:
        from azure.identity import DefaultAzureCredential  # lazy import
    except Exception as exc:
        logger.debug(f"[RENDERS] azure-identity unavailable, skipping Pro fetch: {exc}")
        return None
    try:
        cred = DefaultAzureCredential()
        tok = cred.get_token(f"{_PRO_AUDIENCE}/.default")
        _PRO_TOKEN_CACHE[_PRO_AUDIENCE] = (tok.token, tok.expires_on)
        return tok.token
    except Exception as exc:
        logger.warning(f"[RENDERS] Pro AAD token acquisition failed: {exc}")
        return None
    finally:
        try:
            cred.close()  # type: ignore[name-defined]
        except Exception:
            pass


def _flatten_rescale(rescale: Any) -> Optional[Tuple[float, float]]:
    """Map a STAC ``renders.rescale`` value to a single (min, max) tuple.

    Accepts:
      * ``[min, max]``           -> (min, max)
      * ``[[a,b], [c,d], ...]``  -> (min(a,c,...), max(b,d,...))
      * anything else            -> None
    The widest-range fold is intentional: it avoids accidentally clipping
    the brightest band when a preset publishes per-band stretches.
    """
    if rescale is None:
        return None
    try:
        if (
            isinstance(rescale, (list, tuple))
            and len(rescale) > 0
            and isinstance(rescale[0], (list, tuple))
        ):
            mins = [float(r[0]) for r in rescale if r is not None and len(r) >= 2]
            maxs = [float(r[1]) for r in rescale if r is not None and len(r) >= 2]
            if mins and maxs:
                return (min(mins), max(maxs))
            return None
        if isinstance(rescale, (list, tuple)) and len(rescale) >= 2:
            return (float(rescale[0]), float(rescale[1]))
    except Exception:
        return None
    return None


def _preset_to_rendering_config(
    collection_id: str,
    preset_name: str,
    preset: Dict[str, Any],
) -> Optional[RenderingConfig]:
    """Translate one STAC ``renders`` preset dict into a RenderingConfig.

    Returns None if the preset has no assets and no colormap (i.e.
    nothing renderable). We accept ``colormap_name`` (PC convention) and
    ``colormap`` (TiTiler convention).
    """
    assets = preset.get("assets")
    if isinstance(assets, str):
        assets = [assets]
    rescale = _flatten_rescale(preset.get("rescale"))
    colormap = preset.get("colormap_name") or preset.get("colormap")
    color_formula = preset.get("color_formula")
    resampling = preset.get("resampling", "bilinear")
    minz = preset.get("minzoom") or preset.get("min_zoom") or 6
    maxz = preset.get("maxzoom") or preset.get("max_zoom") or 22
    if not assets and not colormap:
        return None
    try:
        cfg = RenderingConfig(
            collection_id=collection_id,
            data_type=DataType.OPTICAL,  # tier-3 doesn't know the real category; OPTICAL is the safest default for params_to_remove
            assets=assets,
            rescale=rescale,
            colormap=colormap,
            resampling=resampling,
            color_formula=color_formula,
            min_zoom=int(minz) if isinstance(minz, (int, float)) else 6,
            max_zoom=int(maxz) if isinstance(maxz, (int, float)) else 22,
            notes=f"Loaded from STAC renders extension (preset='{preset_name}')",
        )
        return cfg
    except Exception as exc:
        logger.warning(f"[RENDERS] Failed to build RenderingConfig from preset '{preset_name}' for {collection_id}: {exc}")
        return None


def _pick_preset(renders: Dict[str, Any]) -> Tuple[Optional[str], Optional[Dict[str, Any]]]:
    """Choose which preset to use when no query context is available.

    Preference: ``default`` key, else first dict-valued key. Used as a
    fall-through from :func:`_pick_preset_by_intent` when no query is
    supplied or no preset matches the query intent.
    """
    if not isinstance(renders, dict) or not renders:
        return (None, None)
    if "default" in renders and isinstance(renders["default"], dict):
        return ("default", renders["default"])
    for k, v in renders.items():
        if isinstance(v, dict):
            return (k, v)
    return (None, None)


# Intent vocabulary — small, deterministic synonym map used to bridge user
# query language ("fire", "burned") to STAC ``renders`` preset vocabulary
# ("swir", "thermal", "burn"). NOT a hardcoded (collection, query) → preset
# table: this is a query-side normalizer, applied uniformly to every
# preset's text. Each entry expands one user-side concept into the set of
# tokens that data owners typically use in preset keys/titles.
_INTENT_SYNONYMS: Dict[str, Tuple[str, ...]] = {
    # Fire / burn-scar visualization → SWIR false-color presets
    "fire":       ("fire", "burn", "burned", "burnt", "swir", "thermal", "hotspot"),
    "burn":       ("burn", "burned", "burnt", "fire", "swir", "scar"),
    "wildfire":   ("fire", "burn", "swir", "thermal"),
    "thermal":    ("thermal", "fire", "hotspot", "lst", "temperature"),
    # Vegetation / agriculture
    "vegetation": ("vegetation", "ndvi", "evi", "agriculture", "veg"),
    "ndvi":       ("ndvi", "vegetation", "veg"),
    "crop":       ("agriculture", "crop", "cropland", "veg"),
    "agriculture":("agriculture", "crop", "cropland", "veg"),
    "forest":     ("forest", "vegetation", "canopy"),
    # Water / flood
    "water":      ("water", "ndwi", "moisture"),
    "flood":      ("water", "flood", "ndwi"),
    "snow":       ("snow", "ndsi", "ice"),
    "ice":        ("ice", "snow", "ndsi"),
    # Geology / minerals
    "geology":    ("geology", "mineral", "swir"),
    "mineral":    ("mineral", "geology", "swir"),
    # Bathymetry
    "bathymetry": ("bathymetric", "bathymetry", "depth"),
    "depth":      ("bathymetric", "depth"),
}

# Stopwords we strip from the query before scoring so common filler doesn't
# create false matches against equally-common preset descriptions.
_QUERY_STOPWORDS = frozenset({
    "show", "me", "the", "of", "a", "an", "for", "in", "on", "at",
    "and", "or", "to", "with", "from", "by", "is", "are", "was",
    "were", "image", "images", "imagery", "data", "satellite",
    "give", "get", "display", "find", "view", "over", "near",
})


def _tokenize_query(query: str) -> List[str]:
    """Lowercase + split + drop stopwords. Expand via _INTENT_SYNONYMS."""
    raw = re.findall(r"[a-z0-9]+", (query or "").lower())
    base = [t for t in raw if t and t not in _QUERY_STOPWORDS]
    expanded: List[str] = []
    for tok in base:
        expanded.append(tok)
        for syn in _INTENT_SYNONYMS.get(tok, ()):
            if syn not in expanded:
                expanded.append(syn)
    return expanded


def _score_preset(preset_key: str, preset: Dict[str, Any], query_tokens: List[str]) -> int:
    """Score a single STAC ``renders`` preset against tokenized query.

    Weighting: key match = 3, title match = 2, description match = 1.
    All comparisons are substring containment on lowercased preset text,
    which handles "swir-fire" matching "fire" and "False Color (SWIR)"
    matching "swir". Returns 0 when no tokens match — caller treats 0 as
    "no signal" and falls back to default-or-first.
    """
    if not query_tokens:
        return 0
    key_lower = (preset_key or "").lower()
    title_lower = str(preset.get("title") or "").lower()
    desc_lower = str(preset.get("description") or "").lower()
    score = 0
    for tok in query_tokens:
        if tok in key_lower:
            score += 3
        if tok in title_lower:
            score += 2
        if tok in desc_lower:
            score += 1
    return score


def _pick_preset_by_intent(
    renders: Dict[str, Any],
    query_context: Optional[str],
) -> Tuple[Optional[str], Optional[Dict[str, Any]], bool]:
    """Pick the preset whose key/title/description best matches the query.

    Returns ``(preset_name, preset_dict, intent_matched)``. ``intent_matched``
    is True only when the chosen preset scored > 0 against the tokenized
    query — i.e. the user's query carried visualization intent that the
    data owner's preset metadata responded to. False when we fell back to
    :func:`_pick_preset` (default-or-first) because:
      * ``query_context`` was empty/None, OR
      * every preset scored 0 (no intent signal in the query).

    This is the *only* place that uses query text to influence rendering.
    No hardcoded ``(collection_id, keyword) → preset`` mappings — the
    decision is driven entirely by the data owner's preset metadata and
    a small generic synonym table (:data:`_INTENT_SYNONYMS`).
    """
    if not isinstance(renders, dict) or not renders:
        return (None, None, False)
    if not query_context:
        name, preset = _pick_preset(renders)
        return (name, preset, False)
    tokens = _tokenize_query(query_context)
    if not tokens:
        name, preset = _pick_preset(renders)
        return (name, preset, False)

    best_key: Optional[str] = None
    best_preset: Optional[Dict[str, Any]] = None
    best_score = 0
    for k, v in renders.items():
        if not isinstance(v, dict):
            continue
        s = _score_preset(k, v, tokens)
        if s > best_score:
            best_score = s
            best_key = k
            best_preset = v

    if best_preset is not None:
        logger.info(
            f"[RENDERS] Intent-matched preset '{best_key}' (score={best_score}) "
            f"for query='{query_context[:80]}'"
        )
        return (best_key, best_preset, True)
    name, preset = _pick_preset(renders)
    return (name, preset, False)


def _fetch_pub_doc(collection_id: str) -> Optional[Dict[str, Any]]:
    """GET ``/collections/{id}`` from Public PC. Anonymous, no AAD."""
    pub_url = f"{MPC_STAC_API}/collections/{collection_id}"
    try:
        r = requests.get(pub_url, timeout=8)
        if r.status_code == 200:
            return r.json()
        if r.status_code != 404:
            logger.debug(f"[RENDERS] Public PC returned {r.status_code} for {collection_id}")
    except Exception as exc:
        logger.debug(f"[RENDERS] Public PC fetch failed for {collection_id}: {exc}")
    return None


def _fetch_pro_doc(collection_id: str) -> Optional[Dict[str, Any]]:
    """GET ``/collections/{id}`` from MPC Pro (private GeoCatalog). AAD-authed.

    Returns None when ``MPC_PRO_STAC_URL`` is unset or no AAD token can be
    obtained -- callers must be resilient to that.
    """
    pro_base = os.getenv("MPC_PRO_STAC_URL")
    if not pro_base:
        return None
    token = _get_pro_token_sync()
    if not token:
        return None
    pro_url = f"{pro_base.rstrip('/')}/collections/{collection_id}?api-version={_PRO_API_VERSION}"
    try:
        r = requests.get(pro_url, headers={"Authorization": f"Bearer {token}"}, timeout=8)
        if r.status_code == 200:
            return r.json()
        logger.debug(f"[RENDERS] Pro returned {r.status_code} for {collection_id}")
    except Exception as exc:
        logger.debug(f"[RENDERS] Pro fetch failed for {collection_id}: {exc}")
    return None


def _fetch_collection_doc(collection_id: str, is_pro: bool = False) -> Optional[Dict[str, Any]]:
    """GET ``/collections/{id}`` from the request's active catalog first.

    When ``is_pro=True`` (Pro-mode tile request), query the private
    GeoCatalog first and fall back to Public PC on miss. When
    ``is_pro=False``, query Public PC first and fall back to Pro on 404.

    The directional asymmetry matters: a private mirror published under
    the same id as a Public PC collection (e.g. ``sentinel-2-l2a``) can
    carry a richer renders block. Pro-mode rendering MUST see the
    private renders, never the public ones; vice versa for Public-mode.
    Returns the parsed JSON dict or None. Never raises.
    """
    if is_pro:
        return _fetch_pro_doc(collection_id) or _fetch_pub_doc(collection_id)
    return _fetch_pub_doc(collection_id) or _fetch_pro_doc(collection_id)


def _get_renders_block(collection_id: str, is_pro: bool = False) -> Optional[Dict[str, Any]]:
    """Return the cached ``renders`` dict for a collection, or None.

    Caches the full renders block (not a picked preset) so per-request
    intent matching is free after the first fetch. Negative results are
    cached too with a shorter TTL.

    Keyed by ``(collection_id, is_pro)`` so a private mirror with extra
    presets doesn't pollute the Public-mode cache (and vice versa).
    """
    now = time.time()
    cache_key = (collection_id, bool(is_pro))
    cached = _STAC_RENDERS_CACHE.get(cache_key)
    if cached and cached[0] > now:
        return cached[1]

    doc = _fetch_collection_doc(collection_id, is_pro=is_pro)
    renders: Optional[Dict[str, Any]] = None
    if doc:
        block = doc.get("renders")
        if isinstance(block, dict) and block:
            renders = block

    ttl = _STAC_RENDERS_TTL_SEC if renders else _STAC_RENDERS_NEG_TTL_SEC
    _STAC_RENDERS_CACHE[cache_key] = (now + ttl, renders)
    return renders


def read_renders(
    collection_id: str,
    preset_name: Optional[str],
    *,
    is_pro: bool = False,
) -> Optional[RenderingConfig]:
    """Return the :class:`RenderingConfig` for a named preset on a collection.

    This is the **symmetric Pro/Public helper** introduced in Phase 3 of
    MCPProobjective.md. Given a collection id and a preset name picked
    by the dynamic selector (``collection_selector.select_collection``),
    return the corresponding RenderingConfig from the collection's live
    STAC ``renders`` block.

    Pro/Public symmetry: the underlying ``_get_renders_block`` is keyed
    on ``(collection_id, is_pro)`` and queries the appropriate catalog
    first. Two collections with the same id but different ``renders``
    (e.g. a Pro mirror with extra presets) produce different configs
    here, by design.

    Returns ``None`` when any of the following is true (caller falls
    back to the legacy ``HybridRenderingSystem.get_render_config`` stack):

      * ``preset_name`` is empty
      * the collection publishes no renders block on the chosen catalog
      * the named preset does not exist in that renders block
      * the preset has neither assets nor a colormap (nothing renderable)
    """
    if not preset_name:
        return None
    renders = _get_renders_block(collection_id, is_pro=is_pro)
    if not renders:
        return None
    preset = renders.get(preset_name)
    if not isinstance(preset, dict):
        return None
    cfg = _preset_to_rendering_config(collection_id, preset_name, preset)
    if cfg is not None:
        cfg.notes = (cfg.notes or "") + " [v2-explicit-preset]"
    return cfg


def fetch_renders_config(
    collection_id: str,
    query_context: Optional[str] = None,
    is_pro: bool = False,
) -> Optional[RenderingConfig]:
    """Return a RenderingConfig derived from the collection's STAC ``renders``.

    When ``is_pro=True`` the private GeoCatalog (``MPC_PRO_STAC_URL``)
    is queried first; when False, Public PC is queried first. See
    :func:`_fetch_collection_doc` for the fallback policy.

    The renders block is cached for :data:`_STAC_RENDERS_TTL_SEC`
    seconds keyed by (collection_id, is_pro); the preset choice *within*
    that block is recomputed per call based on ``query_context`` so the
    same collection can serve a true-color tile for one query and a
    SWIR-fire tile for the next without re-fetching STAC.

    Returns None when no renders block is published or the lookup fails.
    """
    renders = _get_renders_block(collection_id, is_pro=is_pro)
    if not renders:
        return None
    preset_name, preset, intent_matched = _pick_preset_by_intent(renders, query_context)
    if not preset:
        return None
    cfg = _preset_to_rendering_config(collection_id, preset_name or "default", preset)
    if cfg and intent_matched:
        # Tag the config so tier-0 of HybridRenderingSystem.get_render_config
        # can distinguish a real intent match (override EXPLICIT_RENDER_CONFIGS)
        # from a fall-through default-or-first pick (fall back to it instead).
        cfg.notes = (cfg.notes or "") + " [intent-matched]"
    return cfg


# ============================================================================
# MAIN RENDERING SYSTEM - NO INFERENCE, STRICTLY PC CONFIGS ONLY
# ============================================================================

class HybridRenderingSystem:
    """
    Rendering system that STRICTLY uses PC official configs from repository.
    
    NO inference, NO fallbacks, NO guessing.
    If collection not in PC repo -> returns None
    """
    
    @staticmethod
    def get_render_config(
        collection_id: str,
        query_context: Optional[str] = None,
        is_pro: bool = False,
        explicit_preset: Optional[str] = None,
    ) -> Optional[RenderingConfig]:
        """
        Get rendering configuration for a STAC collection.

        Priority (first hit wins):
          -1. ``explicit_preset``       -- WHEN the dynamic selector
                                          (collection_selector.select_collection)
                                          chose a specific preset for this query.
                                          Calls :func:`read_renders` and returns
                                          immediately on a match -- bypasses every
                                          heuristic below. This is the Phase 3
                                          path that makes Pro/Public symmetric:
                                          the selector picks ``(id, preset)`` once
                                          and both modes honor that pick verbatim.
          0. Live STAC ``renders`` (intent-matched)
                                       -- WHEN ``query_context`` is provided AND
                                          the collection publishes a renders block
                                          AND a preset key/title/description matches
                                          the user query (score > 0). The data
                                          owner's visualization intent wins over
                                          our cached/explicit overrides because
                                          they author the renders extension.
          1. EXPLICIT_RENDER_CONFIGS    -- intentional overrides shipped with the app
          2. pc_rendering_config.json   -- pre-extracted snapshot of PC's tasks repo
          3. Live STAC ``renders``      -- default-or-first preset from the
                                          collection's renders block (used when no
                                          intent signal in the query, or no preset
                                          matched the intent).

        ``is_pro`` controls which catalog tier-0/tier-3 queries first: True
        means the private GeoCatalog (``MPC_PRO_STAC_URL``) is preferred,
        which is required for private mirrors that publish additional
        presets the Public PC copy lacks (e.g. a ``sentinel-2-l2a`` mirror
        carrying ``swir-fire`` in its renders block).

        Args:
            collection_id: STAC collection ID (e.g., "modis-14A1-061")
            query_context: Optional user query, drives tier-0 intent match.
            is_pro: True when the feature being rendered came from a Pro
                response. Routes the renders fetch to the private catalog
                first.

        Returns:
            RenderingConfig if found, None if not found in any source.
        """
        logger.info(f"[ART] STEP 7 RENDERER: Getting render config for: {collection_id} (is_pro={is_pro})")

        # SOURCE -1: EXPLICIT preset from the dynamic v2 selector.
        # When set, the caller has already picked an authoritative
        # (collection_id, preset_name) pair from the live STAC ``renders``
        # block via select_collection. Honor it verbatim -- bypass every
        # heuristic below. Phase 3 of MCPProobjective.md: Pro and Public
        # modes converge by reading the SAME preset name off the SAME
        # collection's renders extension (catalog selection differs only
        # in WHICH catalog we read it from, controlled by ``is_pro``).
        if explicit_preset:
            v2_cfg = read_renders(collection_id, explicit_preset, is_pro=is_pro)
            if v2_cfg is not None:
                logger.info(
                    "   [OK] CONFIG SOURCE: v2-selector explicit preset '%s' "
                    "(is_pro=%s) — symmetric Pro/Public path",
                    explicit_preset, is_pro,
                )
                return v2_cfg
            logger.info(
                "   [WARN] v2-selector preset '%s' not found on %s "
                "(is_pro=%s); falling through to legacy tiers",
                explicit_preset, collection_id, is_pro,
            )

        # SOURCE 0: Live STAC ``renders`` -- INTENT-MATCHED.
        # When the user query carries visualization intent ("fire", "swir",
        # "burn", "thermal", etc.) AND the collection publishes a renders
        # block with a preset whose key/title/description matches, we honor
        # the data owner's authored preset OVER our local overrides. This
        # is what lets Pro-mode "sentinel 2 fire" queries pick the
        # ``swir-fire`` preset that the private GeoCatalog mirror declares,
        # even though EXPLICIT_RENDER_CONFIGS has a natural-color override
        # for ``sentinel-2-l2a``. Falls through silently when no preset
        # matches by intent so the established tier-1/2 fallback still wins
        # for queries that don't express visualization intent.
        if query_context:
            intent_config = fetch_renders_config(collection_id, query_context=query_context, is_pro=is_pro)
            if intent_config and "intent-matched" in (intent_config.notes or "").lower():
                # Only honor tier-0 when the preset was actually chosen by
                # intent. fetch_renders_config drops the "intent-matched"
                # marker into notes only when _pick_preset_by_intent scored > 0.
                logger.info(f"   [OK] CONFIG SOURCE: STAC renders (intent-matched, tier-0)")
                return intent_config

        # SOURCE 1: EXPLICIT_RENDER_CONFIGS - preferred for collections we've optimized
        # These configs use raw bands instead of 'visual' asset, which works better with TiTiler
        # Location: hybrid_rendering_system.py > EXPLICIT_RENDER_CONFIGS dict
        if collection_id in EXPLICIT_RENDER_CONFIGS:
            config = EXPLICIT_RENDER_CONFIGS[collection_id]
            logger.info(f"   [OK] CONFIG SOURCE: EXPLICIT_RENDER_CONFIGS (hybrid_rendering_system.py)")
            logger.info(f"   [DIR] Location: hybrid_rendering_system.py line ~260")
            logger.info(f"   [ART] Assets: {config.assets}")
            logger.info(f"   [CHART] Rescale: {config.rescale}")
            logger.info(f"   [PAINT] Color Formula: {config.color_formula[:50] if config.color_formula else 'None'}...")
            logger.info(f"   [NOTE] Why explicit: Optimized raw bands (B04,B03,B02) instead of 'visual' asset")
            return config
        
        # SOURCE 2: Planetary Computer official configuration from pc_rendering_config.json
        # Location: pc_rendering_config.json (loaded via pc_tasks_config_loader.py)
        # ``query_context`` is forwarded so that collections carrying a
        # ``presets`` block in pc_rendering_config.json get intent-aware
        # preset selection -- the Public-side counterpart to tier 0's
        # live-STAC intent matching. Backwards-compatible: entries without
        # a ``presets`` block return their single flat config unchanged.
        pc_config = get_pc_rendering_config(collection_id, query_context=query_context)
        if pc_config:
            # Check if PC config uses 'visual' asset - these don't work well with TiTiler
            logger.info(f"   [OK] CONFIG SOURCE: PC Repository (pc_rendering_config.json)")
            logger.info(f"   [DIR] Location: pc_rendering_config.json > collections.{collection_id}")
            logger.info(f"   [ART] Data Type: {pc_config.data_type}")
            logger.info(f"   [ART] Assets: {pc_config.assets}")
            logger.info(f"   [CHART] Rescale: {pc_config.rescale}")
            logger.info(f"   [MAP] Colormap: {pc_config.colormap}")
            if pc_config.assets and 'visual' in pc_config.assets:
                logger.warning(f"   [WARN] PC config uses 'visual' asset which may cause 404s - consider adding to EXPLICIT_RENDER_CONFIGS")
            return pc_config
        
        # SOURCE 3: Live STAC ``renders`` -- DEFAULT-OR-FIRST preset.
        # Reached when (a) no query_context was provided, or (b) no preset
        # matched the query intent. Uses ``msft:render_default`` (if any)
        # or the first dict-valued preset. Same backing fetch as tier-0,
        # but driven by the data owner's chosen default rather than the
        # user's query intent.
        stac_config = fetch_renders_config(collection_id, query_context=query_context, is_pro=is_pro)
        if stac_config:
            logger.info(f"   [OK] CONFIG SOURCE: STAC renders extension (live, tier-3 default-or-first)")
            logger.info(f"   [ART] Assets: {stac_config.assets}")
            logger.info(f"   [CHART] Rescale: {stac_config.rescale}")
            logger.info(f"   [MAP] Colormap: {stac_config.colormap}")
            logger.info(f"   [PAINT] Color Formula: {(stac_config.color_formula or '')[:50]}")
            logger.info(f"   [NOTE] {stac_config.notes}")
            return stac_config

        # Not found in any source
        logger.warning(f"   [FAIL] No config found for: {collection_id}")
        logger.warning(f"   [DIR] Not in: EXPLICIT_RENDER_CONFIGS (hybrid_rendering_system.py)")
        logger.warning(f"   [DIR] Not in: pc_rendering_config.json")
        return None
    
    @staticmethod
    def build_titiler_url_params(
        collection_id: str,
        query_context: Optional[str] = None,
        is_pro: bool = False,
    ) -> str:
        """
        Build TiTiler URL parameters from rendering config.
        ONLY uses parameters explicitly defined in PC-tasks configs - no additions!
        Returns empty string if no config found.
        
        FORCE REBUILD: 2025-11-09-16:45 - Removed tile_format, format, scale params
        """
        config = HybridRenderingSystem.get_render_config(collection_id, query_context, is_pro=is_pro)
        if not config:
            logger.warning(f"No config found for {collection_id}, returning empty params")
            return ""
        
        params = config.to_dict()
        
        query_parts = []
        
        # Handle assets (ONLY if specified in config)
        if "assets" in params and params["assets"]:
            assets = params["assets"]
            if isinstance(assets, list):
                for asset in assets:
                    query_parts.append(f"assets={asset}")
            else:
                query_parts.append(f"assets={assets}")
        
        # Handle colormap (ONLY if specified in config)
        # URL-encode pipe characters and other special chars
        if "colormap_name" in params and params["colormap_name"]:
            from urllib.parse import quote
            colormap_encoded = quote(params["colormap_name"], safe='')
            query_parts.append(f"colormap_name={colormap_encoded}")
        
        # Handle rescale (ONLY if specified in config)
        if "rescale" in params and params["rescale"] is not None:
            min_val, max_val = params["rescale"]
            query_parts.append(f"rescale={min_val},{max_val}")
        
        # Handle color_formula (ONLY if specified in config - for RGB optical imagery)
        if "color_formula" in params and params["color_formula"]:
            formula = params["color_formula"].replace(" ", "+").replace(",", "%2C")
            query_parts.append(f"color_formula={formula}")
        
        # Handle bidx (ONLY if specified in config)
        if "bidx" in params and params["bidx"] is not None:
            query_parts.append(f"bidx={params['bidx']}")
        
        # Handle asset_bidx (ONLY if specified in config)
        # URL-encode pipe (|) and comma (,) -- some proxies/servers reject raw '|'
        if "asset_bidx" in params and params["asset_bidx"]:
            from urllib.parse import quote
            asset_bidx_encoded = quote(params["asset_bidx"], safe='')
            query_parts.append(f"asset_bidx={asset_bidx_encoded}")
        
        # Handle expression (ONLY if specified in config)
        if "expression" in params and params["expression"]:
            query_parts.append(f"expression={params['expression']}")
        
        # Emit tile_scale (TiTiler's hi-DPI knob). 2 = 512x512 tiles for crisp
        # rendering on retina/4K displays; 1 = native 256x256. Without this,
        # TiTiler defaults to 1 and the map looks blurry when zoomed in.
        # NOTE: param name is `tile_scale` (NOT `scale`/`tile_format`/`format`,
        # which TiTiler ignores — historical bug).
        tile_scale = params.get("scale", 2)
        if tile_scale and tile_scale != 1:
            query_parts.append(f"tile_scale={tile_scale}")

        # Emit resampling when the RenderingConfig requests a non-default
        # method. TiTiler's default is `nearest`, which preserves source
        # pixels exactly but yields blocky/pixelated output when the map
        # zoom exceeds the source's native ground resolution (e.g. NAIP at
        # z>19). Collections like NAIP/HLS/Sentinel-2 declare
        # `resampling="lanczos"` or `"bilinear"` for smoother deep-zoom
        # rendering; that intent needs to reach the tile URL.
        resampling = params.get("resampling")
        if resampling and resampling != "nearest":
            query_parts.append(f"resampling={resampling}")

        return "&".join(query_parts)
    
    @staticmethod
    def clean_stac_tilejson_url(url: str, collection_id: str) -> str:
        """
        Clean a STAC tilejson URL using collection-specific rules.
        
        Returns original URL if no config found.
        
        Args:
            url: Original tilejson URL from STAC API
            collection_id: STAC collection ID
            
        Returns:
            Cleaned URL with problematic parameters removed, or original URL if no config
        """
        config = HybridRenderingSystem.get_render_config(collection_id)
        if not config:
            logger.warning(f"No config found for {collection_id}, returning original URL")
            return url
        
        return config.clean_stac_url(url)
    
    @staticmethod
    def needs_titiler_rendering(collection_id: str) -> bool:
        """
        Check if a collection has a PC rendering config (all PC collections use TiTiler).
        
        ALL collections in the Planetary Computer should use TiTiler API with the
        correct render parameters from their config. This includes:
        - RGB optical imagery (with color_formula)
        - Colormap data (with colormap_name + rescale)
        - Single-band data
        
        Returns:
            True if collection has a PC config (should use TiTiler), False if not in PC repo
        """
        config = HybridRenderingSystem.get_render_config(collection_id)
        return config is not None
    
    @staticmethod
    def build_titiler_tilejson_url(
        item_id: str,
        collection_id: str,
        *,
        is_pro: bool = False,
        query_context: Optional[str] = None,
    ) -> str:
        """
        Build a TiTiler tilejson.json URL for ANY collection using PC rendering configs.

        ALL Planetary Computer collections use the TiTiler API endpoint with render
        parameters from their config.json files. This includes:
        - Optical imagery (RGB): assets + color_formula
        - Colormap data (SAR, DEM, MODIS): colormap_name + rescale + assets
        - Single-band data: appropriate single-band parameters

        Args:
            item_id: STAC item ID
            collection_id: STAC collection ID
            is_pro: When True, emit a relative ``/api/pro/tilejson`` URL
                pointing at the backend Pro tile proxy. The proxy handles
                AAD auth to the catalog's ``/data/v1`` tiler so the browser
                doesn't need a GeoCatalog audience token.
            query_context: The original user query. When provided, tier-3
                live STAC renders selection becomes intent-aware (e.g. a
                "fire" query against ``sentinel-2-l2a`` picks the SWIR
                preset instead of the default true-color preset).

        Returns:
            Complete TiTiler tilejson.json URL with rendering parameters from PC configs

        Examples:
            >>> # MODIS Fire (colormap)
            >>> url = HybridRenderingSystem.build_titiler_tilejson_url("MYD14A1.A2025145.h08v04", "modis-14A1-061")
            >>> # Returns: "...?collection=modis-14A1-061&item=MYD14A1...&assets=FireMask&rescale=0,9&colormap_name=magma&resampling=nearest"

            >>> # HLS (RGB optical)
            >>> url = HybridRenderingSystem.build_titiler_tilejson_url("HLS.S30.T10TEM.2025123", "hls")
            >>> # Returns: "...?collection=hls&item=HLS.S30...&assets=B04,B03,B02&color_formula=gamma RGB 2.7..."
        """
        if is_pro:
            # Browser-facing absolute URL when API_PUBLIC_BASE_URL is set;
            # otherwise relative (works only when web+api share origin).
            import os
            api_base = (os.getenv("API_PUBLIC_BASE_URL") or "").rstrip("/")
            base_url = f"{api_base}/api/pro/tilejson" if api_base else "/api/pro/tilejson"
        else:
            base_url = "https://planetarycomputer.microsoft.com/api/data/v1/item/tilejson.json"
        params = [
            f"collection={collection_id}",
            f"item={item_id}"
        ]

        # Add rendering parameters from config (intent-aware when query_context given,
        # mode-aware when is_pro is set so private mirror renders blocks are honored)
        render_params = HybridRenderingSystem.build_titiler_url_params(collection_id, query_context, is_pro=is_pro)
        if render_params:
            params.append(render_params)

        return f"{base_url}?{'&'.join(params)}"


# ============================================================================
# MOSAIC SERVICE FUNCTIONS
# ============================================================================
# These functions use the Planetary Computer Mosaic API to provide seamless
# composited imagery across multiple dates, solving the "coverage gaps" problem
# for large areas like countries where a single satellite pass doesn't cover
# the entire area.
# ============================================================================

# Cache for mosaic search_ids to avoid redundant API calls
# Key: hash of (collections, bbox, datetime_range, query_filters)
# Value: {"search_id": str, "timestamp": float}
import hashlib
import time
from typing import Tuple

_mosaic_cache: Dict[str, Dict[str, Any]] = {}
_MOSAIC_CACHE_TTL = 3600  # 1 hour TTL - mosaic search_ids are stable


def _get_mosaic_cache_key(
    collections: List[str],
    bbox: List[float],
    datetime_range: Optional[str],
    query_filters: Optional[Dict[str, Any]]
) -> str:
    """Generate a cache key for mosaic search parameters."""
    # Sort collections for consistent hashing
    sorted_collections = sorted(collections) if collections else []
    # Round bbox to 2 decimals to allow small variations
    rounded_bbox = [round(x, 2) for x in bbox] if bbox else []
    
    key_data = {
        "collections": sorted_collections,
        "bbox": rounded_bbox,
        "datetime": datetime_range,
        "filters": query_filters
    }
    key_str = str(key_data)
    return hashlib.md5(key_str.encode()).hexdigest()


def _get_cached_mosaic_search_id(cache_key: str) -> Optional[str]:
    """Get cached mosaic search_id if valid."""
    if cache_key in _mosaic_cache:
        cached = _mosaic_cache[cache_key]
        if time.time() - cached["timestamp"] < _MOSAIC_CACHE_TTL:
            logger.info(f"[FAST] Mosaic cache HIT: {cache_key[:8]}... -> {cached['search_id'][:16]}...")
            return cached["search_id"]
        else:
            # Expired - remove from cache
            del _mosaic_cache[cache_key]
            logger.info(f"[TIME] Mosaic cache EXPIRED: {cache_key[:8]}...")
    return None


def _cache_mosaic_search_id(cache_key: str, search_id: str) -> None:
    """Cache a mosaic search_id."""
    _mosaic_cache[cache_key] = {
        "search_id": search_id,
        "timestamp": time.time()
    }
    logger.info(f"[SAVE] Mosaic cache SET: {cache_key[:8]}... -> {search_id[:16]}...")


async def register_mosaic_search(
    collections: List[str],
    bbox: List[float],
    datetime_range: Optional[str] = None,
    query_filters: Optional[Dict[str, Any]] = None
) -> Optional[str]:
    """
    Register a search with the Planetary Computer Mosaic API.
    
    The mosaic service composites tiles from multiple satellite passes into a
    seamless layer, automatically filling coverage gaps. This is especially
    useful for large areas (countries, continents) where a single date's
    imagery doesn't cover the entire region.
    
    Uses caching to avoid redundant API calls for repeated queries.
    
    Args:
        collections: List of STAC collection IDs (e.g., ["hls2-l30", "hls2-s30"])
        bbox: Bounding box [west, south, east, north]
        datetime_range: ISO datetime range (e.g., "2025-06-01/2025-06-30")
        query_filters: Additional STAC query filters (e.g., {"eo:cloud_cover": {"lt": 20}})
        
    Returns:
        search_id if registration successful, None otherwise
    """
    try:
        # Check cache first
        cache_key = _get_mosaic_cache_key(collections, bbox, datetime_range, query_filters)
        cached_search_id = _get_cached_mosaic_search_id(cache_key)
        if cached_search_id:
            return cached_search_id
        
        mosaic_register_url = "https://planetarycomputer.microsoft.com/api/data/v1/mosaic/register"
        
        # Build the search payload
        search_body = {
            "collections": collections,
            "filter-lang": "cql2-json"
        }
        
        # Build CQL2 filter
        cql_filter = {
            "op": "and",
            "args": []
        }
        
        # Add bbox filter
        if bbox and len(bbox) == 4:
            cql_filter["args"].append({
                "op": "s_intersects",
                "args": [
                    {"property": "geometry"},
                    {
                        "type": "Polygon",
                        "coordinates": [[
                            [bbox[0], bbox[1]],
                            [bbox[2], bbox[1]],
                            [bbox[2], bbox[3]],
                            [bbox[0], bbox[3]],
                            [bbox[0], bbox[1]]
                        ]]
                    }
                ]
            })
        
        # Add datetime filter
        if datetime_range:
            # Parse datetime range
            if "/" in datetime_range:
                start_dt, end_dt = datetime_range.split("/")
                cql_filter["args"].append({
                    "op": "t_intersects",
                    "args": [
                        {"property": "datetime"},
                        {"interval": [start_dt, end_dt]}
                    ]
                })
            else:
                cql_filter["args"].append({
                    "op": "t_intersects",
                    "args": [
                        {"property": "datetime"},
                        {"interval": [datetime_range, datetime_range]}
                    ]
                })
        
        # Add cloud cover filter if specified
        if query_filters and "eo:cloud_cover" in query_filters:
            cloud_filter = query_filters["eo:cloud_cover"]
            if "lt" in cloud_filter:
                cql_filter["args"].append({
                    "op": "<",
                    "args": [
                        {"property": "eo:cloud_cover"},
                        cloud_filter["lt"]
                    ]
                })
            elif "lte" in cloud_filter:
                cql_filter["args"].append({
                    "op": "<=",
                    "args": [
                        {"property": "eo:cloud_cover"},
                        cloud_filter["lte"]
                    ]
                })
        
        # Only add filter if we have conditions
        if cql_filter["args"]:
            search_body["filter"] = cql_filter
        
        logger.info(f"[GLOBE] Registering mosaic search: collections={collections}, bbox={bbox}")
        
        # Try httpx first (async), fall back to urllib (sync)
        import asyncio
        import json as json_lib
        
        response = None
        
        # Try httpx first (async, faster), fall back to urllib (sync)
        try:
            import httpx
            # Use async httpx for better performance - reduced timeout
            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.post(
                    mosaic_register_url,
                    json=search_body,
                    headers={"Content-Type": "application/json"}
                )
                response = {"status_code": resp.status_code, "text": resp.text}
                logger.info(f"[LAUNCH] Mosaic registration via httpx: {resp.status_code}")
        except ImportError:
            # Fallback to urllib if httpx not available
            import urllib.request
            import urllib.error
            
            def _make_request():
                data = json_lib.dumps(search_body).encode('utf-8')
                req = urllib.request.Request(
                    mosaic_register_url,
                    data=data,
                    headers={"Content-Type": "application/json"},
                    method='POST'
                )
                try:
                    with urllib.request.urlopen(req, timeout=15) as resp:
                        return {
                            "status_code": resp.getcode(),
                            "text": resp.read().decode('utf-8')
                        }
                except urllib.error.HTTPError as e:
                    return {
                        "status_code": e.code,
                        "text": e.read().decode('utf-8')
                    }
            
            response = await asyncio.to_thread(_make_request)
            logger.info(f"[SLOW] Mosaic registration via urllib fallback: {response['status_code']}")
        
        if response["status_code"] == 200:
            result = json_lib.loads(response["text"])
            search_id = result.get("searchid") or result.get("search_id")
            logger.info(f"[OK] Mosaic search registered: search_id={search_id}")
            
            # Cache the search_id for future requests
            if search_id:
                _cache_mosaic_search_id(cache_key, search_id)
            
            return search_id
        else:
            logger.error(f"[FAIL] Mosaic registration failed: {response['status_code']} - {response['text']}")
            return None
                    
    except Exception as e:
        logger.error(f"[FAIL] Mosaic registration error: {e}")
        return None


def build_mosaic_tilejson_url(
    search_id: str,
    collection_id: str,
    tile_matrix_set: str = "WebMercatorQuad"
) -> str:
    """
    Build a mosaic tilejson URL for the registered search.
    
    IMPORTANT: Mosaic endpoints need RAW BAND data (B04, B03, B02) with rescale,
    NOT pre-rendered 'visual' assets. The 'visual' asset is a pre-rendered PNG
    that doesn't work for mosaic compositing.
    
    Args:
        search_id: The search_id returned from register_mosaic_search()
        collection_id: Collection ID for rendering parameters
        tile_matrix_set: Tile matrix set (kept for back-compat; MPC's
            mosaic API does NOT accept ``{tileMatrixSetId}`` between
            ``{search_id}`` and ``tilejson.json`` in a way that
            produces a working tiles URL after the standard
            ``tilejson.json`` -> ``tiles/{z}/{x}/{y}`` substitution.
            See bug: emitting ``.../mosaic/{id}/WebMercatorQuad/tilejson.json``
            tilejsons fine (200) but the substituted tile path
            ``.../mosaic/{id}/WebMercatorQuad/tiles/{z}/{x}/{y}``
            returns 404. Using ``.../mosaic/{id}/tilejson.json``
            yields tile path ``.../mosaic/{id}/tiles/{z}/{x}/{y}``
            which MPC serves correctly.

    Returns:
        Complete tilejson URL for the mosaic
    """
    # NOTE: Do NOT insert ``{tile_matrix_set}`` here. See docstring.
    base_url = f"https://planetarycomputer.microsoft.com/api/data/v1/mosaic/{search_id}/tilejson.json"
    
    # CRITICAL: MPC mosaic requires collection parameter for tile requests
    params = [f"collection={collection_id}"]
    
    # Get config to check what assets it specifies
    config = HybridRenderingSystem.get_render_config(collection_id)
    collection_lower = collection_id.lower()
    
    # MOSAIC-SPECIFIC RENDERING:
    # The 'visual' asset is a pre-rendered PNG that doesn't work for mosaic compositing.
    # Mosaic needs raw band data (B04, B03, B02) with proper rescale and color formula.
    # We must use raw bands for any optical imagery collection.
    
    needs_raw_bands = False
    if config:
        # Check if config uses 'visual' asset - this won't work for mosaic
        if config.assets and 'visual' in config.assets:
            needs_raw_bands = True
            logger.info(f"[SYNC] Mosaic: Config uses 'visual' asset - switching to raw bands for {collection_id}")
    
    if needs_raw_bands or not config:
        # Use raw band rendering for mosaic
        if 'sentinel-2' in collection_lower:
            # Sentinel-2 RGB bands with proper rescale for surface reflectance (0-10000 scaled)
            params.extend(["assets=B04", "assets=B03", "assets=B02"])
            params.append("rescale=0,3000")
            params.append("color_formula=gamma+RGB+2.7%2C+saturation+1.5%2C+sigmoidal+RGB+15+0.55")
            logger.info(f"[ART] Using raw RGB bands (B04,B03,B02) for Sentinel-2 mosaic")
        elif 'landsat' in collection_lower:
            # Landsat RGB composite  
            params.extend(["assets=red", "assets=green", "assets=blue"])
            params.append("rescale=0,30000")
            params.append("color_formula=gamma+RGB+2.7%2C+saturation+1.5%2C+sigmoidal+RGB+15+0.55")
            logger.info(f"[ART] Using raw RGB bands for Landsat mosaic")
        elif 'hls' in collection_lower:
            # HLS RGB composite (B04=Red, B03=Green, B02=Blue for HLS2)
            params.extend(["assets=B04", "assets=B03", "assets=B02"])
            params.append("rescale=0,3000")
            params.append("color_formula=gamma+RGB+2.7%2C+saturation+1.5%2C+sigmoidal+RGB+15+0.55")
            logger.info(f"[ART] Using raw RGB bands for HLS mosaic")
        elif 'naip' in collection_lower:
            # NAIP on public PC: single 4-band ``image`` asset (R/G/B/NIR).
            # TiTiler needs asset_bidx to select the RGB bands; otherwise
            # the request collapses to band 1 only or 404s.
            params.append("assets=image")
            params.append("asset_bidx=image%7C1%2C2%2C3")
            logger.info(f"[ART] Using image asset (bidx 1,2,3) for NAIP mosaic")
        else:
            # Try to use config params if available, otherwise fallback to visual
            render_params = HybridRenderingSystem.build_titiler_url_params(collection_id)
            if render_params:
                params.append(render_params)
            else:
                params.append("assets=visual")
                logger.warning(f"[WARN] Unknown collection {collection_id}, using 'visual' asset fallback")
    else:
        # Config exists and doesn't use 'visual' - use its params directly
        render_params = HybridRenderingSystem.build_titiler_url_params(collection_id)
        if render_params:
            params.append(render_params)
    
    return f"{base_url}?{'&'.join(params)}"
    
    return f"{base_url}?{'&'.join(params)}"


async def get_mosaic_tilejson_url(
    collections: List[str],
    bbox: List[float],
    datetime_range: Optional[str] = None,
    query_filters: Optional[Dict[str, Any]] = None
) -> Optional[Dict[str, Any]]:
    """
    Complete flow to get a mosaic tilejson URL.
    
    Registers the search and returns the tilejson URL for seamless composited tiles.
    
    Args:
        collections: List of STAC collection IDs
        bbox: Bounding box [west, south, east, north]
        datetime_range: ISO datetime range
        query_filters: Additional query filters
        
    Returns:
        Dict with 'tilejson_url', 'search_id', 'collection' if successful, None otherwise
    """
    search_id = await register_mosaic_search(
        collections=collections,
        bbox=bbox,
        datetime_range=datetime_range,
        query_filters=query_filters
    )
    
    if not search_id:
        logger.warning("[WARN] Mosaic registration failed, falling back to individual tiles")
        return None
    
    # Use first collection for rendering params (they should be similar for related collections)
    collection_id = collections[0] if collections else "sentinel-2-l2a"
    
    tilejson_url = build_mosaic_tilejson_url(search_id, collection_id)
    
    return {
        "tilejson_url": tilejson_url,
        "search_id": search_id,
        "collection": collection_id,
        "is_mosaic": True
    }


# Convenience functions
def get_render_config(collection_id: str, query_context: Optional[str] = None) -> Optional[RenderingConfig]:
    """Quick access to rendering configuration. Returns None if not in PC repo."""
    return HybridRenderingSystem.get_render_config(collection_id, query_context)


def build_render_url_params(collection_id: str, query_context: Optional[str] = None) -> str:
    """Quick access to URL parameter building"""
    return HybridRenderingSystem.build_titiler_url_params(collection_id, query_context)


def clean_tilejson_url(url: str, collection_id: str) -> str:
    """Quick access to collection-specific URL cleaning"""
    return HybridRenderingSystem.clean_stac_tilejson_url(url, collection_id)

