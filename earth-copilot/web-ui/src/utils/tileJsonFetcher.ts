/**
 * TileJSON Fetcher Utility
 * 
 * Handles fetching, validating, and signing TileJSON URLs from Microsoft Planetary Computer
 * and other sources. Consolidates duplicated TileJSON fetching logic from MapView.tsx.
 * 
 * @module tileJsonFetcher
 */

import { API_BASE_URL } from '../config/api';

export interface TileJsonResponse {
  tilejson: string;
  tiles: string[];
  bounds?: number[];
  minzoom?: number;
  maxzoom?: number;
  center?: number[];
  name?: string;
  description?: string;
}

export interface TileJsonFetchOptions {
  collection?: string;
  itemId?: string;
  timeout?: number;
  addSasToken?: boolean;
}

export interface TileJsonResult {
  success: boolean;
  tileTemplate?: string;
  tilejson?: TileJsonResponse;
  originalUrl: string;
  authenticatedUrl?: string;
  error?: string;
}

/**
 * Fetches and validates a TileJSON document from a URL
 * Follows Microsoft Planetary Computer's approach exactly
 * 
 * @param tilejsonUrl - The TileJSON URL to fetch
 * @param options - Optional configuration
 * @returns TileJsonResult with tile template and metadata
 */
export async function fetchAndSignTileJSON(
  tilejsonUrl: string,
  options: TileJsonFetchOptions = {}
): Promise<TileJsonResult> {
  const { collection, timeout = 10000 } = options;

  console.log('🗺️ [TileJsonFetcher] ===== FETCHING TILEJSON =====');
  console.log('🗺️ [TileJsonFetcher] Original URL:', tilejsonUrl);
  console.log('🗺️ [TileJsonFetcher] Collection:', collection);

  try {
    // Sign URL with MPC authentication if needed
    // Uses BOTH URL-based and collection-based detection for maximum coverage
    let authenticatedUrl = tilejsonUrl;
    
    if (shouldAddSasToken(collection, tilejsonUrl)) {
      console.log('🗺️ [TileJsonFetcher] Microsoft Planetary Computer URL detected, signing...');
      console.log('🗺️ [TileJsonFetcher] Collection:', collection || 'unknown');
      authenticatedUrl = await signMPCUrl(tilejsonUrl);
      
      if (authenticatedUrl !== tilejsonUrl) {
        console.log('🗺️ [TileJsonFetcher] ✅ URL signed with MPC authentication');
      } else {
        console.log('🗺️ [TileJsonFetcher] ⚠️ Using unsigned URL (authentication may have failed)');
      }
    } else {
      console.log('🗺️ [TileJsonFetcher] Non-MPC URL, skipping authentication');
    }

    // Fetch TileJSON with timeout
    console.log('🗺️ [TileJsonFetcher] Validating TileJSON URL...');
    
    const controller = new AbortController();
    const timeoutId = setTimeout(() => controller.abort(), timeout);

    try {
      const response = await fetch(authenticatedUrl, {
        signal: controller.signal
      });

      clearTimeout(timeoutId);

      console.log('🗺️ [TileJsonFetcher] TileJSON response:', {
        status: response.status,
        statusText: response.statusText,
        contentType: response.headers.get('content-type')
      });

      if (!response.ok) {
        console.error(`🗺️ [TileJsonFetcher] TileJSON fetch failed: ${response.statusText}`);
        return {
          success: false,
          originalUrl: tilejsonUrl,
          authenticatedUrl,
          error: `HTTP ${response.status}: ${response.statusText}`
        };
      }

      const tilejsonData: TileJsonResponse = await response.json();

      console.log('🗺️ [TileJsonFetcher] TileJSON validated successfully:', {
        tilejson: tilejsonData.tilejson,
        tilesCount: tilejsonData.tiles?.length,
        bounds: tilejsonData.bounds,
        minzoom: tilejsonData.minzoom,
        maxzoom: tilejsonData.maxzoom
      });

      // Extract and sign the tile template
      if (tilejsonData.tiles && tilejsonData.tiles.length > 0) {
        let tileTemplate = tilejsonData.tiles[0];
        
        console.log('🗺️ [TileJsonFetcher] Extracted tile template:', 
          tileTemplate.substring(0, 150) + '...');
        console.log('🗺️ [TileJsonFetcher] Template contains {z}/{x}/{y}:', 
          tileTemplate.includes('{z}') && tileTemplate.includes('{x}') && tileTemplate.includes('{y}'));

        // Sign the tile template URL if it's from MPC
        // Uses URL-based detection (FAILSAFE) and collection-based detection
        if (shouldAddSasToken(collection, tileTemplate)) {
          console.log('🗺️ [TileJsonFetcher] Signing tile template URL for authenticated access...');
          console.log('🗺️ [TileJsonFetcher] Template URL domain:', new URL(tileTemplate).hostname);
          
          // Replace {z}/{x}/{y} temporarily to sign, then restore placeholders
          const tempTileUrl = tileTemplate.replace('{z}', '0').replace('{x}', '0').replace('{y}', '0');
          const signedTempUrl = await signMPCUrl(tempTileUrl);
          
          // Restore the {z}/{x}/{y} placeholders in the signed URL
          tileTemplate = signedTempUrl
            .replace('/0/0/0', '/{z}/{x}/{y}')
            .replace('%2F0%2F0%2F0', '/{z}/{x}/{y}'); // Handle URL-encoded version
          
          console.log('🗺️ [TileJsonFetcher] ✅ Tile template signed and ready');
          console.log('🗺️ [TileJsonFetcher] Signed template preview:', 
            tileTemplate.substring(0, 150) + '...');
        } else {
          console.log('🗺️ [TileJsonFetcher] Non-MPC tile template, no authentication needed');
        }

        // Analyze tile URL for quality parameters
        analyzeTileUrl(tileTemplate);

        // NOTE: measureTileQuality is disabled because it generates 404 errors
        // It tries to fetch tiles at arbitrary coordinates that don't exist for most collections
        // NAIP and other item-based collections only have tiles within their specific bbox
        // measureTileQuality(tileTemplate, 14).then(quality => {
        //   if (quality.error) {
        //     console.warn('📐 [TileQuality] Could not measure tile quality:', quality.error);
        //   }
        // }).catch(err => {
        //   console.warn('📐 [TileQuality] Tile quality measurement failed:', err);
        // });

        return {
          success: true,
          tileTemplate,
          tilejson: tilejsonData,
          originalUrl: tilejsonUrl,
          authenticatedUrl
        };
      } else {
        console.warn('🗺️ [TileJsonFetcher] No tiles found in TileJSON');
        return {
          success: false,
          originalUrl: tilejsonUrl,
          authenticatedUrl,
          tilejson: tilejsonData,
          error: 'No tiles array in TileJSON response'
        };
      }
    } catch (fetchError: any) {
      clearTimeout(timeoutId);
      
      if (fetchError.name === 'AbortError') {
        console.error(`🗺️ [TileJsonFetcher] Request timeout after ${timeout}ms`);
        return {
          success: false,
          originalUrl: tilejsonUrl,
          error: `Timeout after ${timeout}ms`
        };
      }
      
      throw fetchError;
    }
  } catch (error: any) {
    console.error('🗺️ [TileJsonFetcher] Error processing TileJSON:', error);
    return {
      success: false,
      originalUrl: tilejsonUrl,
      error: error?.message || String(error)
    };
  }
}

/**
 * Determines if a URL requires SAS token authentication from Microsoft Planetary Computer
 * 
 * This function uses TWO strategies:
 * 1. Collection-based detection (for known MPC collections)
 * 2. URL-based detection (for ANY planetarycomputer.microsoft.com URL)
 * 
 * Strategy 2 is the FAILSAFE - it ensures we NEVER miss authentication for ANY MPC collection,
 * even if it's not in our known list.
 * 
 * @param collection - The collection identifier (optional)
 * @param url - The TileJSON or tile URL (optional)
 * @returns true if SAS token authentication should be applied
 */
function shouldAddSasToken(collection?: string, url?: string): boolean {
  // STRATEGY 1: URL-Based Detection (FAILSAFE - most reliable)
  // If the URL is from Microsoft Planetary Computer, it DEFINITELY needs authentication
  if (url && url.includes('planetarycomputer.microsoft.com')) {
    return true;
  }
  
  // STRATEGY 2: Collection-Based Detection (for cases where we only have collection ID)
  if (collection) {
    const lowerCollection = collection.toLowerCase();
    
    // Known MPC collection patterns that require authentication
    // This list covers all major MPC collections
    const mpcPatterns = [
      'sentinel',       // Sentinel-1 (GRD, RTC) and Sentinel-2 (L2A, L1C)
      'landsat',        // Landsat Collection 2 (L1, L2, 8, 9)
      'hls',            // Harmonized Landsat Sentinel (HLS2-L30, HLS2-S30)
      'modis',          // MODIS collections (all variants: 09, 10, 11, 13, 14, 15, 17, 43, 64, etc.)
      'naip',           // National Agriculture Imagery Program
      'aster',          // ASTER L1T
      'cop-dem',        // Copernicus DEM (30m, 90m)
      'nasadem',        // NASA DEM
      'alos',           // ALOS PALSAR and DEM
      'goes',           // GOES satellite (CMI, GLM)
      'era5',           // ERA5 climate data
      '3dep',           // USGS 3DEP
      'noaa',           // NOAA climate data
      'daymet',         // Daymet climate data
      'terraclimate',   // TerraClimate
      'gridmet',        // GridMET
      'ms-buildings',   // Microsoft Building Footprints
      'io-lulc',        // Impact Observatory Land Use Land Cover
      'mtbs',           // Monitoring Trends in Burn Severity
      'nrcan'           // Natural Resources Canada
    ];
    
    return mpcPatterns.some(pattern => lowerCollection.includes(pattern));
  }
  
  // If no collection or URL provided, default to false (no auth)
  return false;
}

/**
 * Signs a URL using the Planetary Computer authentication API
 * 
 * @param url - URL to sign with MPC authentication
 * @returns Signed URL or original URL if signing fails
 */
async function signMPCUrl(url: string): Promise<string> {
  const startTime = performance.now();
  
  console.log('━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━');
  console.log('� [MPC AUTH] Starting URL signing process...');
  console.log('🔐 [MPC AUTH] Backend API Base URL:', API_BASE_URL);
  console.log('🔐 [MPC AUTH] Full endpoint:', `${API_BASE_URL}/api/sign-mosaic-url`);
  console.log('🔐 [MPC AUTH] Original URL:', url.substring(0, 120) + '...');
  
  try {
    const requestBody = { url };
    console.log('🔐 [MPC AUTH] Request body:', JSON.stringify(requestBody).substring(0, 150));
    
    const response = await fetch(`${API_BASE_URL}/api/sign-mosaic-url`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json'
      },
      body: JSON.stringify(requestBody)
    });

    const responseTime = Math.round(performance.now() - startTime);
    console.log('🔐 [MPC AUTH] Response received in ' + responseTime + 'ms');
    console.log('🔐 [MPC AUTH] Status:', response.status, response.statusText);
    console.log('🔐 [MPC AUTH] Content-Type:', response.headers.get('content-type'));

    if (!response.ok) {
      console.error('━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━');
      console.error('❌ [MPC AUTH] SIGNING FAILED!');
      console.error('❌ [MPC AUTH] HTTP Status:', response.status, response.statusText);
      console.error('❌ [MPC AUTH] This means tiles will NOT be authenticated');
      console.error('❌ [MPC AUTH] Result: LOW RESOLUTION (256x256) tiles');
      console.error('❌ [MPC AUTH] Expected: HIGH RESOLUTION (512x512) tiles');
      console.error('━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━');
      
      // Try to get error details from response body
      try {
        const errorText = await response.text();
        console.error('❌ [MPC AUTH] Error details:', errorText.substring(0, 200));
      } catch (e) {
        console.error('❌ [MPC AUTH] Could not read error response body');
      }
      
      return url; // Return unsigned URL as fallback
    }

    const data = await response.json();
    console.log('🔐 [MPC AUTH] Response data keys:', Object.keys(data));
    console.log('🔐 [MPC AUTH] Authenticated:', data.authenticated);
    
    if (data.signed_url) {
      const originalHasToken = url.includes('?') && (url.includes('se=') || url.includes('sig='));
      const signedHasToken = data.signed_url.includes('?') && (data.signed_url.includes('se=') || data.signed_url.includes('sig='));
      
      console.log('━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━');
      console.log('✅ [MPC AUTH] URL SIGNED SUCCESSFULLY!');
      console.log('✅ [MPC AUTH] Original had SAS token:', originalHasToken);
      console.log('✅ [MPC AUTH] Signed has SAS token:', signedHasToken);
      console.log('✅ [MPC AUTH] Signed URL preview:', data.signed_url.substring(0, 120) + '...');
      console.log('✅ [MPC AUTH] SAS token params present:', signedHasToken ? 'YES ✓' : 'NO ⚠️');
      console.log('✅ [MPC AUTH] This will enable HIGH RESOLUTION tiles');
      console.log('━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━');
      
      return data.signed_url;
    } else {
      console.warn('━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━');
      console.warn('⚠️ [MPC AUTH] No signed_url in response!');
      console.warn('⚠️ [MPC AUTH] Response data:', JSON.stringify(data));
      console.warn('⚠️ [MPC AUTH] Using original unsigned URL');
      console.warn('⚠️ [MPC AUTH] This may result in low-resolution tiles');
      console.warn('━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━');
      return url;
    }
  } catch (error) {
    console.error('━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━');
    console.error('❌ [MPC AUTH] EXCEPTION DURING SIGNING!');
    console.error('❌ [MPC AUTH] Error type:', error instanceof Error ? error.name : typeof error);
    console.error('❌ [MPC AUTH] Error message:', error instanceof Error ? error.message : String(error));
    console.error('❌ [MPC AUTH] This is a critical failure - tiles will be unsigned');
    console.error('❌ [MPC AUTH] Result: LOW RESOLUTION imagery');
    console.error('━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━');
    return url; // Return unsigned URL as fallback
  }
}

/**
 * Batch fetches multiple TileJSON documents
 * Useful for multi-tile rendering scenarios
 * 
 * @param urls - Array of TileJSON URLs
 * @param options - Optional configuration
 * @returns Array of TileJsonResult
 */
export async function fetchMultipleTileJSON(
  urls: string[],
  options: TileJsonFetchOptions = {}
): Promise<TileJsonResult[]> {
  console.log(`🗺️ [TileJsonFetcher] Batch fetching ${urls.length} TileJSON documents`);
  
  const results = await Promise.allSettled(
    urls.map(url => fetchAndSignTileJSON(url, options))
  );

  return results.map((result, index) => {
    if (result.status === 'fulfilled') {
      return result.value;
    } else {
      console.error(`🗺️ [TileJsonFetcher] Failed to fetch TileJSON ${index}:`, result.reason);
      return {
        success: false,
        originalUrl: urls[index],
        error: result.reason?.message || String(result.reason)
      };
    }
  });
}

/**
 * Validates if a URL is a valid TileJSON URL
 * 
 * @param url - URL to validate
 * @returns true if URL appears to be a TileJSON URL
 */
export function isValidTileJsonUrl(url: string): boolean {
  try {
    const parsed = new URL(url);
    
    // Check for common TileJSON URL patterns
    const isTileJson = parsed.pathname.includes('tilejson') ||
                      parsed.pathname.includes('tile.json') ||
                      parsed.searchParams.has('tilejson');
    
    return isTileJson;
  } catch {
    return false;
  }
}

/**
 * Extracts tile template from TileJSON, handling various formats
 * 
 * @param tilejson - TileJSON response object
 * @returns Tile template URL or null
 */
export function extractTileTemplate(tilejson: TileJsonResponse): string | null {
  if (!tilejson.tiles || tilejson.tiles.length === 0) {
    return null;
  }

  // Return first tile template (primary)
  return tilejson.tiles[0];
}

// FUNCTION REMOVED: measureTileQuality
//
// This function was removed because it caused 404 errors by attempting to fetch tiles at 
// arbitrary coordinates (e.g., z=14, x=8192, y=8192) that don't exist for item-based collections.
//
// Why it failed:
// - NAIP and similar collections only have tiles within their specific geographic extent
// - Each NAIP item covers a small area (e.g., a county in Montana), not the entire globe
// - Fetching random tile coordinates results in 404s for most locations
//
// Alternative approach:
// - Tile quality can be inferred from URL parameters (tile_scale=2, @2x suffix, etc.)
// - URL analysis (analyzeTileUrl function) provides sufficient quality indicators
// - No need to actually fetch sample tiles and measure dimensions

/**
 * Analyzes a tile URL to check for high-resolution parameters
 * 
 * @param tileUrl - Tile URL to analyze
 * @returns Analysis results
 */
export function analyzeTileUrl(tileUrl: string): {
  hasTileScale: boolean;
  tileScaleValue: number | null;
  has2xIndicator: boolean;
  hasResampling: boolean;
  resamplingMethod: string | null;
  estimatedQuality: 'high' | 'standard' | 'unknown';
  hasSasToken: boolean;
} {
  const url = new URL(tileUrl.replace('{z}', '0').replace('{x}', '0').replace('{y}', '0'));
  const params = url.searchParams;
  
  // Check for tile_scale parameter
  const hasTileScale = params.has('tile_scale');
  const tileScaleValue = params.get('tile_scale') ? parseInt(params.get('tile_scale')!) : null;
  
  // Check for @2x in path
  const has2xIndicator = url.pathname.includes('@2x');
  
  // Check for resampling method
  const hasResampling = params.has('resampling');
  const resamplingMethod = params.get('resampling');
  
  // Check for SAS token (se= signature expiry, sig= signature)
  const hasSasToken = params.has('se') || params.has('sig') || params.has('st');
  
  // Estimate quality
  let estimatedQuality: 'high' | 'standard' | 'unknown' = 'unknown';
  if (tileScaleValue === 2 || has2xIndicator) {
    estimatedQuality = 'high';
  } else if (tileScaleValue === 1 || (!hasTileScale && !has2xIndicator)) {
    estimatedQuality = 'standard';
  }
  
  console.log('━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━');
  console.log('🔍 [TILE URL ANALYSIS] Checking tile URL parameters...');
  console.log('━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━');
  console.log('🔍 URL:', tileUrl.substring(0, 150) + '...');
  console.log('🔍 Domain:', url.hostname);
  console.log('🔍 Path:', url.pathname);
  console.log('━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━');
  console.log('📐 RESOLUTION PARAMETERS:');
  console.log('  tile_scale:', hasTileScale ? (tileScaleValue + 'x') : (has2xIndicator ? 'ℹ️ Not needed (@2x in path)' : '❌ NOT FOUND'));
  console.log('  @2x in path:', has2xIndicator ? '✅ YES (512x512 tiles)' : '❌ NO (256x256 tiles)');
  console.log('  resampling:', resamplingMethod || '❌ none (will use default)');
  console.log('━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━');
  
  // Determine URL type for accurate SAS token reporting
  const isTiTilerUrl = url.hostname.includes('planetarycomputer') && url.pathname.includes('/api/data/v1/');
  
  console.log('🔐 AUTHENTICATION:');
  if (isTiTilerUrl) {
    console.log('  URL Type: TiTiler (public API)');
    console.log('  SAS Token:', hasSasToken ? '✅ PRESENT' : 'ℹ️ NOT NEEDED (public service, full resolution)');
  } else {
    console.log('  URL Type:', url.hostname.includes('blob.core.windows.net') ? 'Blob Storage' : 'Other');
    console.log('  SAS Token:', hasSasToken ? '✅ PRESENT (authenticated)' : '❌ MISSING (may need authentication)');
  }
  
  if (hasSasToken) {
    console.log('  Token params:', Array.from(params.keys()).filter(k => ['se', 'sig', 'st', 'sp', 'sv'].includes(k)).join(', '));
  }
  console.log('━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━');
  console.log('🎯 QUALITY ESTIMATION:');
  console.log('  Estimated tile quality:', estimatedQuality.toUpperCase());
  console.log('  Expected tile size:', estimatedQuality === 'high' ? '512x512 pixels' : '256x256 pixels');
  
  if (!hasTileScale && !has2xIndicator) {
    console.warn('━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━');
    console.warn('⚠️ WARNING: NO HIGH-RESOLUTION PARAMETERS FOUND!');
    console.warn('⚠️ Missing: tile_scale=2 or @2x path indicator');
    console.warn('⚠️ Result: Tiles will be standard resolution (256x256)');
    console.warn('⚠️ This WILL cause blurry imagery when zooming in');
    console.warn('⚠️ Backend should be adding tile_scale=2 to URLs');
    console.warn('━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━');
  }
  
  // Check for SAS token on MPC URLs
  // NOTE: TiTiler URLs (/api/data/v1/) do NOT need SAS tokens - they're publicly accessible!
  // Only direct blob storage URLs need SAS tokens (which we don't use)
  // (isTiTilerUrl already declared above at line 486)
  
  if (!hasSasToken && url.hostname.includes('planetarycomputer') && !isTiTilerUrl) {
    console.warn('━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━');
    console.warn('⚠️ WARNING: NO SAS TOKEN ON NON-TITILER MPC URL!');
    console.warn('⚠️ Direct blob storage access may require authentication');
    console.warn('⚠️ Backend /api/sign-mosaic-url may have failed');
    console.warn('━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━');
  } else if (!hasSasToken && isTiTilerUrl) {
    console.log('ℹ️ TiTiler URL has no SAS token (EXPECTED - service is public, full resolution available)');
  }
  
  console.log('━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━');
  
  return {
    hasTileScale,
    tileScaleValue,
    has2xIndicator,
    hasResampling,
    resamplingMethod,
    estimatedQuality,
    hasSasToken
  };
}
