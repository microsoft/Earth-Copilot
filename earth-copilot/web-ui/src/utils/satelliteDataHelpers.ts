/**
 * Satellite Data Helpers
 * 
 * Utilities for processing STAC items, satellite data structures, and preparing
 * data for rendering. Handles multi-item vs single-item cases, asset extraction,
 * and data structure transformations.
 * 
 * @module satelliteDataHelpers
 */

export interface STACItem {
  id: string;
  collection: string;
  bbox?: number[];
  geometry?: any;
  properties?: Record<string, any>;
  assets?: Record<string, STACAsset>;
  links?: any[];
}

export interface STACAsset {
  href: string;
  type?: string;
  title?: string;
  roles?: string[];
  [key: string]: any;
}

export interface TileInfo {
  item_id: string;
  tilejson_url: string;
  bbox: number[];
}

export interface SatelliteData {
  items: STACItem[];
  bbox?: number[];
  tile_url?: string;
  tilejson_url?: string;
  all_tile_urls?: TileInfo[];
  collection?: string;
  asset_types?: string[];
  metadata?: Record<string, any>;
}

export interface PreparedTileData {
  tileUrl: string;
  bounds: number[];
  itemId: string;
  collection: string;
  isMultiTile: boolean;
  isSingleTile: boolean;
  tilejsonUrl?: string;
}

/**
 * Determines if satellite data represents a multi-tile scenario
 * 
 * @param data - Satellite data from backend
 * @returns true if multi-tile rendering required
 */
export function isMultiTileData(data: SatelliteData): boolean {
  return !!(data.all_tile_urls && data.all_tile_urls.length > 0);
}

/**
 * Determines if satellite data represents a single-tile scenario
 * 
 * @param data - Satellite data from backend
 * @returns true if single-tile rendering
 */
export function isSingleTileData(data: SatelliteData): boolean {
  return !!(data.tile_url || data.tilejson_url) && !isMultiTileData(data);
}

/**
 * Extracts collection identifier from satellite data
 * 
 * @param data - Satellite data
 * @returns Collection ID or empty string
 */
export function getCollection(data: SatelliteData): string {
  if (data.collection) {
    return data.collection;
  }
  
  if (data.items && data.items.length > 0 && data.items[0].collection) {
    return data.items[0].collection;
  }
  
  return '';
}

/**
 * Extracts bounding box from satellite data
 * 
 * @param data - Satellite data
 * @returns Bounding box [west, south, east, north] or undefined
 */
export function getBoundingBox(data: SatelliteData): number[] | undefined {
  if (data.bbox && Array.isArray(data.bbox) && data.bbox.length === 4) {
    return data.bbox;
  }
  
  if (data.items && data.items.length > 0 && data.items[0].bbox) {
    return data.items[0].bbox;
  }
  
  return undefined;
}

/**
 * Prepares tile information for multi-tile rendering
 * 
 * @param data - Satellite data with all_tile_urls
 * @returns Array of prepared tile data
 */
export function prepareMultiTileData(data: SatelliteData): PreparedTileData[] {
  if (!data.all_tile_urls || data.all_tile_urls.length === 0) {
    console.warn(' [SatelliteDataHelpers] No multi-tile data available');
    return [];
  }

  const collection = getCollection(data);
  
  console.log(` [SatelliteDataHelpers] Preparing ${data.all_tile_urls.length} tiles for multi-tile rendering`);

  return data.all_tile_urls.map(tileInfo => ({
    tileUrl: tileInfo.tilejson_url, // Will be resolved to actual tile template
    bounds: tileInfo.bbox,
    itemId: tileInfo.item_id,
    collection,
    isMultiTile: true,
    isSingleTile: false,
    tilejsonUrl: tileInfo.tilejson_url
  }));
}

/**
 * Prepares tile information for single-tile rendering
 * 
 * @param data - Satellite data with tile_url or tilejson_url
 * @returns Prepared tile data
 */
export function prepareSingleTileData(data: SatelliteData): PreparedTileData | null {
  const collection = getCollection(data);
  const bounds = getBoundingBox(data);
  
  if (!bounds) {
    console.warn(' [SatelliteDataHelpers] No bounds available for single-tile data');
    return null;
  }

  const itemId = data.items && data.items.length > 0 ? data.items[0].id : 'unknown';
  
  // Prefer tilejson_url if available (MPC approach)
  if (data.tilejson_url) {
    console.log(' [SatelliteDataHelpers] Using tilejson_url for single-tile rendering');
    return {
      tileUrl: data.tilejson_url, // Will be resolved to actual tile template
      bounds,
      itemId,
      collection,
      isMultiTile: false,
      isSingleTile: true,
      tilejsonUrl: data.tilejson_url
    };
  }
  
  // Fallback to direct tile_url
  if (data.tile_url) {
    console.log(' [SatelliteDataHelpers] Using direct tile_url for single-tile rendering');
    return {
      tileUrl: data.tile_url,
      bounds,
      itemId,
      collection,
      isMultiTile: false,
      isSingleTile: true
    };
  }

  console.warn(' [SatelliteDataHelpers] No tile URL available for single-tile data');
  return null;
}

/**
 * Extracts assets from STAC item
 * 
 * @param item - STAC item
 * @param assetTypes - Optional specific asset types to extract
 * @returns Record of assets
 */
export function extractAssets(
  item: STACItem,
  assetTypes?: string[]
): Record<string, STACAsset> {
  if (!item.assets) {
    return {};
  }

  if (!assetTypes || assetTypes.length === 0) {
    return item.assets;
  }

  // Filter to specific asset types
  const filtered: Record<string, STACAsset> = {};
  
  for (const [key, asset] of Object.entries(item.assets)) {
    if (assetTypes.includes(key)) {
      filtered[key] = asset;
    }
  }

  return filtered;
}

/**
 * Determines if satellite data is elevation/DEM data
 * 
 * @param data - Satellite data
 * @returns true if elevation data
 */
export function isElevationData(data: SatelliteData): boolean {
  const collection = getCollection(data).toLowerCase();
  
  return collection.includes('dem') || 
         collection.includes('elevation') ||
         collection.includes('nasadem') ||
         collection.includes('copernicus');
}

/**
 * Determines if satellite data is thermal infrared data
 * 
 * @param data - Satellite data
 * @returns true if thermal data
 */
export function isThermalData(data: SatelliteData): boolean {
  const collection = getCollection(data).toLowerCase();
  
  return collection.includes('thermal') || 
         collection.includes('modis-11') ||
         collection.includes('lst');
}

/**
 * Determines if satellite data is fire detection data
 * 
 * @param data - Satellite data
 * @returns true if fire data
 */
export function isFireData(data: SatelliteData): boolean {
  const collection = getCollection(data).toLowerCase();
  
  return collection.includes('fire') || 
         collection.includes('modis-14');
}

/**
 * Determines if satellite data is HLS (Harmonized Landsat Sentinel) data
 * 
 * @param data - Satellite data
 * @returns true if HLS data
 */
export function isHLSData(data: SatelliteData): boolean {
  const collection = getCollection(data).toLowerCase();
  
  return collection.includes('hls');
}

/**
 * Determines if satellite data is optical RGB imagery
 * 
 * @param data - Satellite data
 * @returns true if optical RGB data
 */
export function isOpticalData(data: SatelliteData): boolean {
  const collection = getCollection(data).toLowerCase();
  
  return collection.includes('sentinel-2') || 
         collection.includes('landsat') ||
         collection.includes('hls') ||
         collection.includes('naip');
}

/**
 * Determines if satellite data is SAR (Synthetic Aperture Radar)
 * 
 * @param data - Satellite data
 * @returns true if SAR data
 */
export function isSARData(data: SatelliteData): boolean {
  const collection = getCollection(data).toLowerCase();
  
  return collection.includes('sentinel-1') || 
         collection.includes('sar');
}

/**
 * Extracts metadata from STAC items
 * 
 * @param data - Satellite data
 * @returns Metadata object with useful information
 */
export function extractMetadata(data: SatelliteData): Record<string, any> {
  const metadata: Record<string, any> = {
    collection: getCollection(data),
    itemCount: data.items?.length || 0,
    bounds: getBoundingBox(data),
    isMultiTile: isMultiTileData(data),
    isSingleTile: isSingleTileData(data),
    dataType: determineDataType(data)
  };

  // Extract properties from first item if available
  if (data.items && data.items.length > 0) {
    const firstItem = data.items[0];
    
    if (firstItem.properties) {
      metadata.datetime = firstItem.properties.datetime;
      metadata.cloudCover = firstItem.properties['eo:cloud_cover'];
      metadata.gsd = firstItem.properties.gsd; // Ground Sample Distance
      metadata.platform = firstItem.properties.platform;
      metadata.instruments = firstItem.properties.instruments;
    }
  }

  return metadata;
}

/**
 * Determines the general data type category
 * 
 * @param data - Satellite data
 * @returns Data type string
 */
export function determineDataType(data: SatelliteData): string {
  if (isElevationData(data)) return 'elevation';
  if (isThermalData(data)) return 'thermal';
  if (isFireData(data)) return 'fire';
  if (isSARData(data)) return 'sar';
  if (isOpticalData(data)) return 'optical';
  
  return 'unknown';
}

/**
 * Validates satellite data structure
 * 
 * @param data - Satellite data to validate
 * @returns Object with validation results
 */
export function validateSatelliteData(data: any): {
  valid: boolean;
  errors: string[];
  warnings: string[];
} {
  const errors: string[] = [];
  const warnings: string[] = [];

  // Check basic structure
  if (!data || typeof data !== 'object') {
    errors.push('Satellite data is not an object');
    return { valid: false, errors, warnings };
  }

  // Check for items array
  if (!data.items || !Array.isArray(data.items)) {
    errors.push('Missing or invalid items array');
  } else if (data.items.length === 0) {
    warnings.push('Items array is empty');
  }

  // Check for at least one rendering option
  const hasMultiTile = !!(data.all_tile_urls && data.all_tile_urls.length > 0);
  const hasSingleTile = !!(data.tile_url || data.tilejson_url);
  
  if (!hasMultiTile && !hasSingleTile) {
    errors.push('No tile URLs available (neither all_tile_urls nor tile_url/tilejson_url)');
  }

  // Check for bounds
  if (!data.bbox && (!data.items || !data.items[0]?.bbox)) {
    warnings.push('No bounding box available');
  }

  // Check for collection
  if (!data.collection && (!data.items || !data.items[0]?.collection)) {
    warnings.push('No collection identifier found');
  }

  const valid = errors.length === 0;

  return { valid, errors, warnings };
}

/**
 * Applies asset fixes for known collection issues
 * (e.g., Sentinel-2 L2A visual asset)
 * 
 * @param tileUrl - Original tile URL
 * @param collection - Collection identifier
 * @returns Fixed tile URL
 */
export function applyAssetFixes(tileUrl: string, collection: string): string {
  // Fix Sentinel-2 L2A: replace red,green,blue with visual asset
  if (collection.toLowerCase().includes('sentinel-2-l2a')) {
    if (tileUrl.includes('assets=red') || 
        tileUrl.includes('assets=green') || 
        tileUrl.includes('assets=blue')) {
      const fixedUrl = tileUrl.replace(
        /assets=(red|green|blue|red,green,blue)/g,
        'assets=visual'
      );
      
      if (fixedUrl !== tileUrl) {
        console.log(' [SatelliteDataHelpers] Fixed Sentinel-2 L2A assets: [red,green,blue] -> [visual]');
        return fixedUrl;
      }
    }
  }

  return tileUrl;
}
