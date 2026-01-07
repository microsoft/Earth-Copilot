/**
 * Tile Layer Factory
 * 
 * Creates and configures Azure Maps TileLayer instances with optimized settings
 * based o    // High-resolution optical: enable deep zoom
    // Covers: sentinel-2-l2a, landsat-c2-l2, landsat-8-c2-l2, landsat-9-c2-l2, naip, hls (all variants)
    if (collectionLower.includes('sentinel-2') || 
        collectionLower.includes('landsat') ||
        collectionLower.includes('hls') ||
        collectionLower.includes('naip')) {
      minZoom = 6;
      maxZoom = 22; // Maximum zoom for crisp detail
      console.log(`🗺️ [TileLayerFactory] High-res optical (no TileJSON): zoom range ${minZoom}-${maxZoom}`);
    }
    // MODIS: enforce minimum zoom to avoid 404 errors with large footprints
    else if (collectionLower.includes('modis')) {
      minZoom = 8; // CRITICAL: MODIS ~1200km footprints need zoom 8+
      maxZoom = 18;
      console.log(`🗺️ [TileLayerFactory] MODIS (no TileJSON): zoom range ${minZoom}-${maxZoom}`);
    }ype, data characteristics, and rendering requirements.
 * Consolidates tile layer creation logic from MapView.tsx.
 * 
 * @module tileLayerFactory
 */

import { getCollectionConfig, DataType } from './renderingConfig';
import type { TileJsonResponse } from './tileJsonFetcher';

export interface TileLayerOptions {
  tileUrl: string;
  collection: string;
  bounds?: number[];
  tilejson?: TileJsonResponse;
  isElevation?: boolean;
  isThermal?: boolean;
  isFire?: boolean;
  customOpacity?: number;
}

export interface TileLayerConfig {
  tileUrl: string;
  opacity: number;
  tileSize: number;
  bounds?: number[];
  minSourceZoom: number;
  maxSourceZoom: number;
  tileLoadRadius: number;
  blend: string;
  fadeDuration: number;
  rasterOpacity: number;
  buffer: number;
  tolerance: number;
  interpolate: boolean;
  // Thermal-specific
  noDataValue?: number;
  resample?: string;
  // Quality enhancements
  errorTolerance?: number;
  ignoreInvalidTiles?: boolean;
  maxRetries?: number;
  antialiasing?: boolean;
  smoothTransitions?: boolean;
}

/**
 * Creates an Azure Maps TileLayer with optimized configuration
 * 
 * @param options - Configuration options for tile layer
 * @param atlasLibrary - Azure Maps atlas library (window.atlas)
 * @returns Configured TileLayer instance
 */
export function createTileLayer(
  options: TileLayerOptions,
  atlasLibrary: any
): any {
  const {
    tileUrl,
    collection,
    bounds,
    tilejson,
    isElevation = false,
    isThermal = false,
    isFire = false,
    customOpacity
  } = options;

  console.log(`🗺️ [TileLayerFactory] Creating tile layer for collection: ${collection}`);

  // Get centralized rendering configuration
  const renderingConfig = getCollectionConfig(collection);
  
  // ✅ Normalize collection name for pattern matching (used throughout)
  const collectionLower = collection.toLowerCase();
  
  // ✅ COLLECTION-SPECIFIC ZOOM LEVEL CONFIGURATION
  // Determine zoom levels based on collection characteristics and data resolution
  let minZoom = renderingConfig.minZoom;
  let maxZoom = renderingConfig.maxZoom;

  // Override with TileJSON if available (authoritative source from data provider)
  if (tilejson) {
    if (tilejson.minzoom !== undefined || tilejson.maxzoom !== undefined) {
      // Special handling for MODIS collections (1km resolution - visible from zoom 4+)
      if (collectionLower.includes('modis')) {
        // MODIS 1km data works best at zoom 4-12 (tiles exist within granule bounds)
        // Each MODIS granule covers ~10x10 degrees, allowing country-level views
        minZoom = Math.max(4, tilejson.minzoom || 4); // ✅ FIXED: Allow zoom 4+ for country/state views
        maxZoom = tilejson.maxzoom !== undefined ? Math.min(tilejson.maxzoom, 12) : 12; // Cap at 12 (1km data pixelates beyond)
        console.log(`🗺️ [TileLayerFactory] MODIS collection: zoom range ${minZoom}-${maxZoom} (fire data visible from zoom 4+)`);
      } 
      // High-resolution optical collections can zoom very deep
      // Covers: sentinel-2-l2a, landsat-c2-l2, landsat-8-c2-l2, landsat-9-c2-l2, naip, hls (all variants)
      // NOTE: HLS mosaic tiles only exist at zoom 8+ from PC API (HTTP 204 at lower zooms)
      // However, we allow minZoom=0 so Azure Maps can OVERZOOM the tiles at lower zoom levels
      // This prevents tiles from disappearing when zooming out - instead they'll just be upscaled
      else if (collectionLower.includes('sentinel-2') || 
               collectionLower.includes('landsat') ||
               collectionLower.includes('hls') ||
               collectionLower.includes('naip')) {
        // ✅ FIX: Set minZoom=0 to allow tile display at all zoom levels via overzooming
        // The tiles may look pixelated at low zoom, but they won't disappear
        // Azure Maps will request zoom 8+ tiles and scale them down for display at lower zooms
        minZoom = 0; // Allow display at any zoom level
        maxZoom = tilejson.maxzoom !== undefined ? Math.max(tilejson.maxzoom, 22) : 22; // Allow deep zoom for clarity
        console.log(`🗺️ [TileLayerFactory] High-res optical: zoom range ${minZoom}-${maxZoom} (allowing overzoom at low zoom levels)`);
      }
      // SAR collections (Sentinel-1 GRD/RTC)
      else if (collectionLower.includes('sentinel-1')) {
        minZoom = Math.max(6, tilejson.minzoom || 6); // Enforce min zoom 6 for SAR too
        maxZoom = tilejson.maxzoom !== undefined ? Math.max(tilejson.maxzoom, 20) : 20;
        console.log(`🗺️ [TileLayerFactory] SAR collection: zoom range ${minZoom}-${maxZoom}`);
      }
      // Elevation models
      else if (isElevation || collectionLower.includes('dem') || collectionLower.includes('elevation')) {
        minZoom = Math.max(5, tilejson.minzoom || 5); // DEM can work at slightly lower zoom
        maxZoom = tilejson.maxzoom !== undefined ? Math.max(tilejson.maxzoom, 20) : 20;
        console.log(`🗺️ [TileLayerFactory] Elevation model: zoom range ${minZoom}-${maxZoom}`);
      }
      // Default: use TileJSON values
      else {
        minZoom = tilejson.minzoom !== undefined ? tilejson.minzoom : minZoom;
        maxZoom = tilejson.maxzoom !== undefined ? tilejson.maxzoom : maxZoom;
        console.log(`�️ [TileLayerFactory] Using TileJSON zoom range: ${minZoom}-${maxZoom}`);
      }
    }
  }
  // No TileJSON: use collection-specific defaults
  else {
    // HLS collections: allow display at all zoom levels via overzooming
    // Mosaic tiles only exist at zoom 8+, but we set minZoom=0 to overzoom at lower levels
    if (collectionLower.includes('hls')) {
      minZoom = 0; // Allow overzoom at lower levels (tiles will be upscaled from zoom 8)
      maxZoom = 22;
      console.log(`🗺️ [TileLayerFactory] HLS (no TileJSON): zoom range ${minZoom}-${maxZoom} (allowing overzoom at low zoom levels)`);
    }
    // High-resolution optical: enable deep zoom and allow overzoom
    else if (collectionLower.includes('sentinel-2') || 
        collectionLower.includes('landsat') ||
        collectionLower.includes('naip')) {
      minZoom = 0; // Allow overzoom at lower levels
      maxZoom = 22; // Maximum zoom for crisp detail
      console.log(`🗺️ [TileLayerFactory] High-res optical (no TileJSON): zoom range ${minZoom}-${maxZoom}`);
    }
    // MODIS: allow tiles at zoom 4+ for country/state level views (1km fire pixels visible when zoomed in)
    else if (collectionLower.includes('modis')) {
      minZoom = 4; // ✅ FIXED: Allow zoom 4+ to show tiles at country level (matches backend config)
      maxZoom = 18;
      console.log(`🗺️ [TileLayerFactory] MODIS (no TileJSON): zoom range ${minZoom}-${maxZoom} (fire data visible from zoom 4+)`);
    }
    // SAR, Elevation, other collections: use config defaults with reasonable max zoom
    else {
      minZoom = renderingConfig.minZoom;
      maxZoom = Math.max(renderingConfig.maxZoom, 20); // Ensure at least zoom 20 for satellite data
      console.log(`🗺️ [TileLayerFactory] Using config zoom range: ${minZoom}-${maxZoom}`);
    }
  }

  console.log(`📊 [TileLayerFactory] ✅ Final zoom configuration: ${minZoom}-${maxZoom} for ${collection}`);

  // Validate and clamp bounds if provided
  let validatedBounds = undefined;
  if (bounds && Array.isArray(bounds) && bounds.length === 4) {
    validatedBounds = validateAndClampBounds(bounds);
    if (validatedBounds) {
      console.log('🗺️ [TileLayerFactory] Using clamped bounds:', validatedBounds);
    }
  }

  // Ensure high-resolution tile URLs
  const highResUrl = ensureHighResolution(tileUrl);

  // ✅ COLLECTION-SPECIFIC OPACITY CONFIGURATION
  // Opacity is dynamically determined based on:
  // 1. Collection-specific requirements (high-res optical needs max clarity)
  // 2. Data type characteristics (elevation overlays, fire detection, thermal)
  // 3. Custom overrides from rendering system
  let opacity = customOpacity !== undefined ? customOpacity : renderingConfig.opacity;
  
  // HIGH-RESOLUTION OPTICAL IMAGERY (Sentinel-2, Landsat, NAIP, HLS)
  // These need MAXIMUM opacity for crisp, vivid satellite imagery
  // Covers: sentinel-2-l2a, landsat-c2-l2, landsat-8-c2-l2, landsat-9-c2-l2, 
  //         hls2-l30, hls2-s30, hls-l30, hls-s30, hls, naip
  if (collectionLower.includes('sentinel-2') || 
      collectionLower.includes('landsat') ||
      collectionLower.includes('hls') ||
      collectionLower.includes('naip')) {
    opacity = Math.max(opacity, 0.98); // Ensure at least 98% opacity for vivid RGB colors
    console.log(`🗺️ [TileLayerFactory] High-res optical imagery: using opacity ${opacity}`);
  }
  
  // SAR IMAGERY (Sentinel-1 RTC/GRD)
  // SAR needs high opacity for clear radar returns
  // Covers: sentinel-1-grd, sentinel-1-rtc
  else if (collectionLower.includes('sentinel-1')) {
    opacity = Math.max(opacity, 0.95); // High opacity for SAR clarity
    console.log(`🗺️ [TileLayerFactory] SAR imagery: using opacity ${opacity}`);
  }
  
  // ELEVATION MODELS (DEM, Copernicus, NASADEM)
  // Lower opacity to see terrain overlay on basemap
  else if (isElevation || collectionLower.includes('dem') || collectionLower.includes('elevation')) {
    opacity = 0.65; // Moderate opacity for elevation overlays
    console.log(`🗺️ [TileLayerFactory] Elevation data: using opacity ${opacity}`);
  }
  
  // FIRE DETECTION (MODIS 14A1/14A2, VIIRS)
  // High opacity to see fire hotspots clearly while keeping nodata transparent
  else if (isFire || collectionLower.includes('fire') || collectionLower.includes('14a')) {
    opacity = 0.7; // High opacity but allows base map to show through nodata areas
    console.log(`🗺️ [TileLayerFactory] Fire detection: using opacity ${opacity}`);
  }
  
  // THERMAL IMAGERY (Landsat thermal bands)
  // Full opacity for thermal analysis
  else if (isThermal || collectionLower.includes('thermal')) {
    opacity = 1.0; // FULL opacity for thermal data
    console.log(`🗺️ [TileLayerFactory] Thermal imagery: using opacity ${opacity}`);
  }
  
  // MODIS VEGETATION INDICES (NDVI, EVI, LAI, NPP, GPP)
  // High opacity for vegetation analysis
  else if (collectionLower.includes('modis') && 
          (collectionLower.includes('13') || collectionLower.includes('15') || collectionLower.includes('17'))) {
    opacity = Math.max(opacity, 0.90); // High opacity for vegetation indices
    console.log(`🗺️ [TileLayerFactory] MODIS vegetation: using opacity ${opacity}`);
  }
  
  // SNOW/ICE (MODIS Snow Cover, Sentinel-2 Snow)
  // High opacity for clear snow detection
  else if (collectionLower.includes('snow') || collectionLower.includes('ice')) {
    opacity = Math.max(opacity, 0.92);
    console.log(`🗺️ [TileLayerFactory] Snow/ice data: using opacity ${opacity}`);
  }
  
  // DEFAULT: Use collection config or ensure minimum 85%
  else {
    opacity = Math.max(opacity, 0.85); // Minimum 85% for any satellite data
    console.log(`🗺️ [TileLayerFactory] Default opacity: ${opacity} for ${collection}`);
  }

  // Build layer configuration
  const layerConfig: TileLayerConfig = {
    tileUrl: highResUrl,
    opacity,
    tileSize: renderingConfig.tileSize,
    bounds: validatedBounds,
    minSourceZoom: minZoom,
    maxSourceZoom: maxZoom,
    tileLoadRadius: renderingConfig.renderingHints?.tileLoadRadius ?? 2,
    blend: 'normal',
    fadeDuration: renderingConfig.renderingHints?.fadeEnabled ? 500 : 0,
    rasterOpacity: opacity,
    buffer: renderingConfig.renderingHints?.buffer ?? 128,
    tolerance: 0.05,
    interpolate: renderingConfig.renderingHints?.interpolate ?? true,
    // Quality enhancements
    errorTolerance: 0.1,
    ignoreInvalidTiles: true,
    maxRetries: 3,
    antialiasing: true,
    smoothTransitions: true
  };

  // Apply thermal-specific configuration
  if (isThermal) {
    console.log('🔥 [TileLayerFactory] Applying thermal-specific configuration');
    layerConfig.noDataValue = -9999;
    layerConfig.interpolate = false;
    layerConfig.resample = 'bilinear';
  }

  console.log('🗺️ [TileLayerFactory] Creating tile layer with config:', {
    collection,
    minZoom,
    maxZoom,
    opacity,
    tileSize: layerConfig.tileSize,
    bounds: validatedBounds ? 'set' : 'none',
    fadeEnabled: layerConfig.fadeDuration > 0
  });

  // Create and return the tile layer
  return new atlasLibrary.layer.TileLayer(layerConfig);
}

/**
 * Creates multiple tile layers for seamless multi-tile rendering
 * 
 * @param tiles - Array of tile information with URLs and bounds
 * @param collection - Collection identifier
 * @param atlasLibrary - Azure Maps atlas library
 * @returns Array of configured TileLayer instances
 */
export async function createMultipleTileLayers(
  tiles: Array<{ tileUrl: string; bounds: number[]; itemId: string; tilejson?: TileJsonResponse }>,
  collection: string,
  atlasLibrary: any
): Promise<{ layers: any[]; successCount: number; errorCount: number }> {
  console.log(`🗺️ [TileLayerFactory] Creating ${tiles.length} tile layers for seamless coverage`);

  const layers: any[] = [];
  let successCount = 0;
  let errorCount = 0;

  const isElevation = collection.toLowerCase().includes('dem') || 
                     collection.toLowerCase().includes('elevation');

  for (const tile of tiles) {
    try {
      const layer = createTileLayer(
        {
          tileUrl: tile.tileUrl,
          collection,
          bounds: tile.bounds,
          tilejson: tile.tilejson,
          isElevation
        },
        atlasLibrary
      );

      layers.push(layer);
      successCount++;
      console.log(`✅ [TileLayerFactory] Created layer ${successCount}/${tiles.length}: ${tile.itemId}`);
    } catch (error) {
      console.error(`❌ [TileLayerFactory] Error creating layer for ${tile.itemId}:`, error);
      errorCount++;
    }
  }

  console.log(`🎉 [TileLayerFactory] Multi-tile layer creation complete. Success: ${successCount}, Errors: ${errorCount}`);

  return { layers, successCount, errorCount };
}

/**
 * Validates and clamps bounds to prevent geometry extent errors
 * 
 * @param bounds - [west, south, east, north]
 * @returns Validated and clamped bounds or undefined if invalid
 */
export function validateAndClampBounds(bounds: number[]): number[] | undefined {
  if (!bounds || !Array.isArray(bounds) || bounds.length !== 4) {
    console.warn('🗺️ [TileLayerFactory] Invalid bounds array:', bounds);
    return undefined;
  }

  const [west, south, east, north] = bounds;

  // Validate each coordinate is a valid number
  const isValidBound = (coord: any) => {
    return coord !== null && 
           coord !== undefined && 
           typeof coord === 'number' && 
           !isNaN(coord) && 
           isFinite(coord) &&
           coord >= -180 && 
           coord <= 180;
  };

  if (!isValidBound(west) || !isValidBound(south) || 
      !isValidBound(east) || !isValidBound(north)) {
    console.warn('🗺️ [TileLayerFactory] Invalid bound coordinates:', bounds);
    return undefined;
  }

  if (west >= east || south >= north) {
    console.warn('🗺️ [TileLayerFactory] Invalid bounds geometry (west >= east or south >= north):', bounds);
    return undefined;
  }

  // Clamp to safe ranges
  const clampedWest = Math.max(-180, Math.min(180, west));
  const clampedSouth = Math.max(-85, Math.min(85, south)); // Web Mercator latitude limits
  const clampedEast = Math.max(-180, Math.min(180, east));
  const clampedNorth = Math.max(-85, Math.min(85, north));

  const clamped = [clampedWest, clampedSouth, clampedEast, clampedNorth];

  // Log if clamping occurred
  if (JSON.stringify(bounds) !== JSON.stringify(clamped)) {
    console.log('🗺️ [TileLayerFactory] Bounds clamped:', { original: bounds, clamped });
  }

  return clamped;
}

/**
 * Ensures tile URL includes high-resolution parameter
 * 
 * @param tileUrl - Original tile URL
 * @returns URL with tile_scale=2 parameter (only for TiTiler URLs, not native tiles)
 */
export function ensureHighResolution(tileUrl: string): string {
  // Check if tile_scale parameter already exists
  if (tileUrl.includes('tile_scale=')) {
    return tileUrl;
  }

  // ⚠️ CRITICAL: Do NOT add tile_scale=2 to Planetary Computer native tiles URLs
  // Native tiles API (/api/data/v1/item/tiles/) does NOT support tile_scale parameter
  // Adding it causes 404 errors
  const isNativeTiles = tileUrl.includes('/api/data/v1/item/tiles/');
  
  if (isNativeTiles) {
    console.log('🗺️ [TileLayerFactory] Native tiles detected - NOT adding tile_scale (would cause 404)');
    return tileUrl;
  }

  // For TiTiler URLs, add tile_scale=2 for high-resolution rendering
  const separator = tileUrl.includes('?') ? '&' : '?';
  const highResUrl = `${tileUrl}${separator}tile_scale=2`;
  
  console.log('🗺️ [TileLayerFactory] Added tile_scale=2 for high-resolution rendering');
  
  return highResUrl;
}

/**
 * Determines if collection is elevation data
 * 
 * @param collection - Collection identifier
 * @returns true if elevation/DEM data
 */
export function isElevationCollection(collection: string): boolean {
  const lower = collection.toLowerCase();
  return lower.includes('dem') || 
         lower.includes('elevation') || 
         lower.includes('nasadem') ||
         lower.includes('copernicus');
}

/**
 * Determines if collection is thermal data
 * 
 * @param collection - Collection identifier
 * @returns true if thermal infrared data
 */
export function isThermalCollection(collection: string): boolean {
  const lower = collection.toLowerCase();
  return lower.includes('thermal') || 
         lower.includes('modis-11') ||
         lower.includes('lst'); // Land Surface Temperature
}

/**
 * Determines if collection is fire data
 * 
 * @param collection - Collection identifier
 * @returns true if fire detection data
 */
export function isFireCollection(collection: string): boolean {
  const lower = collection.toLowerCase();
  return lower.includes('fire') || 
         lower.includes('modis-14');
}
