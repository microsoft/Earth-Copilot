/**
 * TileJSON Fetcher Utility
 * 
 * Handles fetching, validating, and signing TileJSON URLs from Microsoft Planetary Computer
 * and other sources. Consolidates duplicated TileJSON fetching logic from MapView.tsx.
 * 
 * @module tileJsonFetcher
 */

import { API_BASE_URL } from '../config/api';
import { authenticatedFetch } from '../services/authHelper';

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

  console.log(' [TileJsonFetcher] ===== FETCHING TILEJSON =====');
  console.log(' [TileJsonFetcher] Original URL:', tilejsonUrl);
  console.log(' [TileJsonFetcher] Collection:', collection);

  try {
    // Sign URL with MPC authentication if needed
    // Uses BOTH URL-based and collection-based detection for maximum coverage
    let authenticatedUrl = tilejsonUrl;
    
    if (shouldAddSasToken(collection, tilejsonUrl)) {
      console.log(' [TileJsonFetcher] Microsoft Planetary Computer URL detected, signing...');
      console.log(' [TileJsonFetcher] Collection:', collection || 'unknown');
      authenticatedUrl = await signMPCUrl(tilejsonUrl);
      
      if (authenticatedUrl !== tilejsonUrl) {
        console.log(' [TileJsonFetcher]  URL signed with MPC authentication');
      } else {
        console.log(' [TileJsonFetcher]  Using unsigned URL (authentication may have failed)');
      }
    } else {
      console.log(' [TileJsonFetcher] Non-MPC URL, skipping authentication');
    }

    // Fetch TileJSON with timeout
    console.log(' [TileJsonFetcher] Validating TileJSON URL...');
    
    let tilejsonData: TileJsonResponse;
    
    // Try direct fetch first, fall back to backend proxy if it fails
    try {
      const controller = new AbortController();
      const timeoutId = setTimeout(() => controller.abort(), timeout);

      const response = await fetch(authenticatedUrl, {
        signal: controller.signal
      });

      clearTimeout(timeoutId);

      console.log(' [TileJsonFetcher] TileJSON response:', {
        status: response.status,
        statusText: response.statusText,
        contentType: response.headers.get('content-type')
      });

      if (!response.ok) {
        throw new Error(`HTTP ${response.status}: ${response.statusText}`);
      }

      tilejsonData = await response.json();
    } catch (directError) {
      console.warn(' [TileJsonFetcher] Direct fetch failed, trying backend proxy...', directError);
      
      // Fall back to backend proxy which can reach Planetary Computer server-side
      const proxyResponse = await authenticatedFetch(`${API_BASE_URL}/api/proxy-tilejson`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ url: tilejsonUrl })
      });
      
      if (!proxyResponse.ok) {
        console.error(` [TileJsonFetcher] Backend proxy also failed: ${proxyResponse.statusText}`);
        return {
          success: false,
          originalUrl: tilejsonUrl,
          authenticatedUrl,
          error: `Direct fetch and backend proxy both failed`
        };
      }
      
      tilejsonData = await proxyResponse.json();
      console.log(' [TileJsonFetcher] TileJSON fetched via backend proxy');
    }

    console.log(' [TileJsonFetcher] TileJSON validated successfully:', {
      tilejson: tilejsonData.tilejson,
      tilesCount: tilejsonData.tiles?.length,
      bounds: tilejsonData.bounds,
      minzoom: tilejsonData.minzoom,
      maxzoom: tilejsonData.maxzoom
    });

    // Extract and sign the tile template
    if (tilejsonData.tiles && tilejsonData.tiles.length > 0) {
      let tileTemplate = tilejsonData.tiles[0];
      
      console.log(' [TileJsonFetcher] Extracted tile template:', 
        tileTemplate.substring(0, 150) + '...');
      console.log(' [TileJsonFetcher] Template contains {z}/{x}/{y}:', 
        tileTemplate.includes('{z}') && tileTemplate.includes('{x}') && tileTemplate.includes('{y}'));

      // Sign the tile template URL if it's from MPC
      // Uses URL-based detection (FAILSAFE) and collection-based detection
      if (shouldAddSasToken(collection, tileTemplate)) {
        console.log(' [TileJsonFetcher] Signing tile template URL for authenticated access...');
        console.log(' [TileJsonFetcher] Template URL domain:', new URL(tileTemplate).hostname);
        
        // Replace {z}/{x}/{y} temporarily to sign, then restore placeholders
        const tempTileUrl = tileTemplate.replace('{z}', '0').replace('{x}', '0').replace('{y}', '0');
        const signedTempUrl = await signMPCUrl(tempTileUrl);
        
        // Restore the {z}/{x}/{y} placeholders in the signed URL
        tileTemplate = signedTempUrl
          .replace('/0/0/0', '/{z}/{x}/{y}')
          .replace('%2F0%2F0%2F0', '/{z}/{x}/{y}'); // Handle URL-encoded version
        
        console.log(' [TileJsonFetcher]  Tile template signed and ready');
        console.log(' [TileJsonFetcher] Signed template preview:', 
          tileTemplate.substring(0, 150) + '...');
      } else {
        console.log(' [TileJsonFetcher] Non-MPC tile template, no authentication needed');
      }

      // Analyze tile URL for quality parameters
      analyzeTileUrl(tileTemplate);

      return {
        success: true,
        tileTemplate,
        tilejson: tilejsonData,
        originalUrl: tilejsonUrl,
        authenticatedUrl
      };
    } else {
      console.warn(' [TileJsonFetcher] No tiles found in TileJSON');
      return {
        success: false,
        originalUrl: tilejsonUrl,
        authenticatedUrl,
        tilejson: tilejsonData,
        error: 'No tiles array in TileJSON response'
      };
    }
  } catch (error: any) {
    console.error(' [TileJsonFetcher] Error processing TileJSON:', error);
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
 * MPC has two URL types:
 *   1. Blob storage  (e.g. https://*.blob.core.windows.net/...)            → needs SAS
 *   2. TiTiler API  (https://planetarycomputer.microsoft.com/api/data/...) → PUBLIC, no SAS
 *
 * Calling /api/sign-mosaic-url for TiTiler URLs is a no-op round-trip that
 * adds 300–500 ms per tile layer; with ~20 layers per chat response that
 * was ~7–9 s of pure overhead. Short-circuit those here.
 *
 * @param collection - The collection identifier (optional)
 * @param url - The TileJSON or tile URL (optional)
 * @returns true if SAS token authentication should be applied
 */
function shouldAddSasToken(collection?: string, url?: string): boolean {
  // STRATEGY 1 (FAILSAFE): only blob-storage URLs need a SAS token. The MPC
  // TiTiler service (`/api/data/v1/...`) is public and rejects SAS params
  // that some clients used to add, so we deliberately skip signing it.
  if (url) {
    if (/\.blob\.core\.windows\.net/i.test(url)) {
      return true;
    }
    if (url.includes('planetarycomputer.microsoft.com')) {
      return false; // TiTiler / data API — public, no signing needed
    }
  }

  // STRATEGY 2: collection-based hint when only the collection ID is known.
  // Used for direct blob-storage links built client-side (rare).
  if (collection) {
    const lowerCollection = collection.toLowerCase();
    const mpcPatterns = [
      'sentinel', 'landsat', 'hls', 'modis', 'naip', 'aster',
      'cop-dem', 'nasadem', 'alos', 'goes', 'era5', '3dep',
      'noaa', 'daymet', 'terraclimate', 'gridmet', 'ms-buildings',
      'io-lulc', 'mtbs', 'nrcan'
    ];
    return mpcPatterns.some(pattern => lowerCollection.includes(pattern));
  }

  return false;
}

/**
 * Signs a URL using the Planetary Computer authentication API.
 *
 * In-flight de-dup + 50-minute TTL cache: MPC SAS tokens are valid ~1 h,
 * so re-signing the same URL on every tile/zoom/chat-followup is wasted RTT.
 *
 * @param url - URL to sign with MPC authentication
 * @returns Signed URL or original URL if signing fails
 */
const SIGN_TTL_MS = 50 * 60 * 1000; // 50 min (SAS tokens last ~1 h)
const signCache = new Map<string, { signedUrl: string; expiresAt: number }>();
const signInflight = new Map<string, Promise<string>>();

async function signMPCUrl(url: string): Promise<string> {
  const cached = signCache.get(url);
  if (cached && cached.expiresAt > Date.now()) {
    return cached.signedUrl;
  }
  const inflight = signInflight.get(url);
  if (inflight) {
    return inflight;
  }

  const promise = (async () => {
    const startTime = performance.now();
    try {
      const response = await authenticatedFetch(`${API_BASE_URL}/api/sign-mosaic-url`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ url })
      });

      const responseTime = Math.round(performance.now() - startTime);

      if (!response.ok) {
        console.error(`[MPC AUTH] Signing failed (${response.status}) after ${responseTime}ms - falling back to unsigned URL`);
        return url;
      }

      const data = await response.json();
      if (data.signed_url) {
        signCache.set(url, { signedUrl: data.signed_url, expiresAt: Date.now() + SIGN_TTL_MS });
        return data.signed_url as string;
      }
      return url;
    } catch (error) {
      console.error('[MPC AUTH] Exception during signing:', error instanceof Error ? error.message : String(error));
      return url;
    } finally {
      signInflight.delete(url);
    }
  })();

  signInflight.set(url, promise);
  return promise;
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
  console.log(` [TileJsonFetcher] Batch fetching ${urls.length} TileJSON documents`);
  
  const results = await Promise.allSettled(
    urls.map(url => fetchAndSignTileJSON(url, options))
  );

  return results.map((result, index) => {
    if (result.status === 'fulfilled') {
      return result.value;
    } else {
      console.error(` [TileJsonFetcher] Failed to fetch TileJSON ${index}:`, result.reason);
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
  console.log(' [TILE URL ANALYSIS] Checking tile URL parameters...');
  console.log('━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━');
  console.log(' URL:', tileUrl.substring(0, 150) + '...');
  console.log(' Domain:', url.hostname);
  console.log(' Path:', url.pathname);
  console.log('━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━');
  console.log(' RESOLUTION PARAMETERS:');
  console.log('  tile_scale:', hasTileScale ? (tileScaleValue + 'x') : (has2xIndicator ? 'ℹ Not needed (@2x in path)' : ' NOT FOUND'));
  console.log('  @2x in path:', has2xIndicator ? ' YES (512x512 tiles)' : ' NO (256x256 tiles)');
  console.log('  resampling:', resamplingMethod || ' none (will use default)');
  console.log('━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━');
  
  // Determine URL type for accurate SAS token reporting
  const isTiTilerUrl = url.hostname.includes('planetarycomputer') && url.pathname.includes('/api/data/v1/');
  
  console.log(' AUTHENTICATION:');
  if (isTiTilerUrl) {
    console.log('  URL Type: TiTiler (public API)');
    console.log('  SAS Token:', hasSasToken ? ' PRESENT' : 'ℹ NOT NEEDED (public service, full resolution)');
  } else {
    console.log('  URL Type:', url.hostname.includes('blob.core.windows.net') ? 'Blob Storage' : 'Other');
    console.log('  SAS Token:', hasSasToken ? ' PRESENT (authenticated)' : ' MISSING (may need authentication)');
  }
  
  if (hasSasToken) {
    console.log('  Token params:', Array.from(params.keys()).filter(k => ['se', 'sig', 'st', 'sp', 'sv'].includes(k)).join(', '));
  }
  console.log('━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━');
  console.log(' QUALITY ESTIMATION:');
  console.log('  Estimated tile quality:', estimatedQuality.toUpperCase());
  console.log('  Expected tile size:', estimatedQuality === 'high' ? '512x512 pixels' : '256x256 pixels');
  
  if (!hasTileScale && !has2xIndicator) {
    console.warn('━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━');
    console.warn(' WARNING: NO HIGH-RESOLUTION PARAMETERS FOUND!');
    console.warn(' Missing: tile_scale=2 or @2x path indicator');
    console.warn(' Result: Tiles will be standard resolution (256x256)');
    console.warn(' This WILL cause blurry imagery when zooming in');
    console.warn(' Backend should be adding tile_scale=2 to URLs');
    console.warn('━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━');
  }
  
  // Check for SAS token on MPC URLs
  // NOTE: TiTiler URLs (/api/data/v1/) do NOT need SAS tokens - they're publicly accessible!
  // Only direct blob storage URLs need SAS tokens (which we don't use)
  // (isTiTilerUrl already declared above at line 486)
  
  if (!hasSasToken && url.hostname.includes('planetarycomputer') && !isTiTilerUrl) {
    console.warn('━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━');
    console.warn(' WARNING: NO SAS TOKEN ON NON-TITILER MPC URL!');
    console.warn(' Direct blob storage access may require authentication');
    console.warn(' Backend /api/sign-mosaic-url may have failed');
    console.warn('━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━');
  } else if (!hasSasToken && isTiTilerUrl) {
    console.log('ℹ TiTiler URL has no SAS token (EXPECTED - service is public, full resolution available)');
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
