// Copyright (c) Microsoft Corporation.
// Licensed under the MIT license.

// Enhanced tile URL generation supporting all STAC collection types
// Based on Microsoft Planetary Computer Titiler API patterns

import { getCollectionConfig, getDefaultAssets, getTileFormat, requiresAuthentication, AssetConfig } from '../config/collectionConfig';

export interface TileUrlOptions {
  collection: string;
  item?: string;
  assets?: string[];
  format?: string;
  scale?: number;
  rescale?: string;
  colormap?: string;
  expression?: string;
  resampling?: string;
  return_mask?: boolean;
  algorithm?: string;
  algorithm_params?: Record<string, any>;
}

export interface MosaicUrlOptions {
  collection: string;
  datetime?: string;
  bbox?: number[];
  assets?: string[];
  format?: string;
  scale?: number;
  rescale?: string;
  colormap?: string;
  expression?: string;
  max_items?: number;
}

export class TileUrlGenerator {
  private static readonly PC_BASE_URL = 'https://planetarycomputer.microsoft.com/api/data/v1';
  private static readonly STAC_BASE_URL = 'https://planetarycomputer.microsoft.com/api/stac/v1';

  /**
   * Generate tile URL for a specific STAC item
   * Returns TileJSON URL following MPC patterns to avoid asset_bidx issues
   */
  static generateItemTileUrl(options: TileUrlOptions): string {
    // Follow MPC's pattern: return tilejson URL instead of tile template
    // This avoids asset_bidx parameter issues entirely
    return this.generateTileJsonUrl(options);
  }

  /**
   * Generate tile URL for a mosaic of multiple items
   */
  static generateMosaicTileUrl(options: MosaicUrlOptions): string {
    const config = getCollectionConfig(options.collection);
    
    // Use collection-specific defaults
    const assets = options.assets || getDefaultAssets(options.collection);
    const format = options.format || getTileFormat(options.collection);
    const scale = options.scale || 1;
    const maxItems = options.max_items || 10;

    // Build base URL
    let url = `${this.PC_BASE_URL}/mosaic/tiles/WebMercatorQuad/{z}/{x}/{y}@${scale}x`;
    
    // Add query parameters
    const params = new URLSearchParams();
    params.set('collection', options.collection);
    
    if (assets.length > 0) {
      params.set('assets', assets.join(','));
    }
    
    params.set('format', format);
    params.set('max_items', maxItems.toString());

    // Add temporal filter
    if (options.datetime) {
      params.set('datetime', options.datetime);
    }

    // Add spatial filter
    if (options.bbox && options.bbox.length === 4) {
      params.set('bbox', options.bbox.join(','));
    }

    // Add collection-specific parameters (same as item tiles)
    if (config) {
      if (options.collection === 'sentinel-1-rtc' && !options.rescale) {
        params.set('rescale', '-30,0');
      }
      
      if (['daymet-daily-na', 'era5-pds', 'terraclimate'].includes(options.collection)) {
        const asset = assets[0];
        const assetConfig = config.availableAssets.find((a: AssetConfig) => a.name === asset);
        if (assetConfig?.colormap && !options.colormap) {
          params.set('colormap', assetConfig.colormap);
        }
      }
      
      if (['nasadem', 'cop-dem-glo-30'].includes(options.collection) && !options.colormap) {
        params.set('colormap', 'terrain');
      }
    }

    // Add optional parameters
    if (options.rescale) params.set('rescale', options.rescale);
    if (options.colormap) params.set('colormap', options.colormap);
    if (options.expression) params.set('expression', options.expression);

    return `${url}?${params.toString()}`;
  }

  /**
   * Generate preview image URL for a specific item
   */
  static generatePreviewUrl(options: TileUrlOptions): string {
    const assets = options.assets || getDefaultAssets(options.collection);
    const format = options.format || getTileFormat(options.collection);

    let url = `${this.PC_BASE_URL}/item/preview.${format}`;
    
    const params = new URLSearchParams();
    params.set('collection', options.collection);
    
    if (options.item) {
      params.set('item', options.item);
    }
    
    if (assets.length > 0) {
      params.set('assets', assets.join(','));
    }

    // Add collection-specific parameters
    const config = getCollectionConfig(options.collection);
    if (config) {
      if (options.collection === 'sentinel-1-rtc' && !options.rescale) {
        params.set('rescale', '-30,0');
      }
      
      if (['daymet-daily-na', 'era5-pds', 'terraclimate'].includes(options.collection)) {
        const asset = assets[0];
        const assetConfig = config.availableAssets.find((a: AssetConfig) => a.name === asset);
        if (assetConfig?.colormap && !options.colormap) {
          params.set('colormap', assetConfig.colormap);
        }
      }
      
      if (['nasadem', 'cop-dem-glo-30'].includes(options.collection) && !options.colormap) {
        params.set('colormap', 'terrain');
      }
    }

    if (options.rescale) params.set('rescale', options.rescale);
    if (options.colormap) params.set('colormap', options.colormap);
    if (options.expression) params.set('expression', options.expression);

    return `${url}?${params.toString()}`;
  }

  /**
   * Generate TileJSON URL for dynamic map configuration
   * Following Microsoft Planetary Computer's makeRasterTileJsonUrl pattern
   * Ensures no asset_bidx parameters are included
   */
  static generateTileJsonUrl(options: TileUrlOptions): string {
    let assets = options.assets || getDefaultAssets(options.collection);
    const format = options.format || getTileFormat(options.collection);
    const scale = options.scale || 2; // Use scale 2 for high-resolution tiles (512x512)
    
    // Fix incorrect asset combinations for specific collections
    if (options.collection === 'sentinel-2-l2a' && 
        assets.length === 3 && 
        assets.includes('red') && assets.includes('green') && assets.includes('blue')) {
      // Use 'visual' asset instead of individual RGB bands for Sentinel-2
      assets = ['visual'];
      console.log('TileUrlGenerator: Corrected Sentinel-2 L2A assets from [red,green,blue] to [visual]');
    }
    
    let url = `${this.PC_BASE_URL}/item/tilejson.json`;
    
    const params = new URLSearchParams();
    
    // Core parameters following MPC pattern
    params.set('collection', options.collection);
    // Add tile_scale=2 for high-resolution tiles (makes returned tile template use @2x)
    params.set('tile_scale', scale.toString());
    
    if (options.item) {
      params.set('item', options.item);
    }
    
    if (assets.length > 0) {
      // Use individual asset parameters instead of comma-separated
      // This avoids asset_bidx generation
      assets.forEach(asset => {
        params.append('assets', asset);
      });
    }

    // Add format if not already in render params
    if (!options.expression?.includes('format')) {
      params.set('format', format);
    }

    // Add collection-specific parameters
    const config = getCollectionConfig(options.collection);
    if (config) {
      if (options.collection === 'sentinel-1-rtc' && !options.rescale) {
        params.set('rescale', '-30,0');
      }
      
      if (['daymet-daily-na', 'era5-pds', 'terraclimate'].includes(options.collection)) {
        const asset = assets[0];
        const assetConfig = config.availableAssets.find((a: AssetConfig) => a.name === asset);
        if (assetConfig?.colormap && !options.colormap) {
          params.set('colormap', assetConfig.colormap);
        }
      }
      
      if (['nasadem', 'cop-dem-glo-30'].includes(options.collection) && !options.colormap) {
        params.set('colormap', 'terrain');
      }
    }

    // Optional rendering parameters
    if (options.rescale) params.set('rescale', options.rescale);
    if (options.colormap) params.set('colormap', options.colormap);
    if (options.expression) params.set('expression', encodeURIComponent(options.expression));
    if (options.resampling) params.set('resampling', options.resampling);

    // Ensure nodata parameter for transparency
    if (!params.has('nodata')) {
      params.set('nodata', '0');
    }

    return `${url}?${params.toString()}`;
  }

  /**
   * Generate appropriate tile URL based on data type and availability
   */
  static generateAdaptiveTileUrl(
    collection: string,
    items?: Array<{ id: string; collection: string; datetime?: string; bbox?: number[] }>,
    bbox?: number[],
    datetime?: string,
    assets?: string[]
  ): string {
    if (items && items.length === 1) {
      // Single item - use item tile endpoint
      return this.generateItemTileUrl({
        collection,
        item: items[0].id,
        assets
      });
    } else if (items && items.length > 1) {
      // Multiple items - use mosaic endpoint
      return this.generateMosaicTileUrl({
        collection,
        bbox,
        datetime,
        assets,
        max_items: Math.min(items.length, 50) // Limit for performance
      });
    } else {
      // No specific items - use collection mosaic
      return this.generateMosaicTileUrl({
        collection,
        bbox,
        datetime,
        assets
      });
    }
  }

  /**
   * Get collection-specific asset recommendations
   */
  static getAssetRecommendations(collection: string, useCase: 'visual' | 'analysis' | 'false-color' | 'radar' | 'thermal'): string[] {
    const config = getCollectionConfig(collection);
    if (!config) return ['visual'];

    switch (useCase) {
      case 'visual':
        if (collection.includes('sentinel-2')) return ['visual'];
        if (collection.includes('landsat')) return ['visual'];
        if (collection.includes('sentinel-1')) return ['vh'];
        return config.defaultAssets;

      case 'false-color':
        if (collection.includes('sentinel-2')) return ['B08', 'B04', 'B03']; // NIR, Red, Green
        if (collection.includes('landsat')) return ['nir08', 'red', 'green'];
        return config.defaultAssets;

      case 'radar':
        if (collection.includes('sentinel-1')) return ['vh', 'vv'];
        return config.defaultAssets;

      case 'thermal':
        if (collection.includes('landsat')) return ['lwir11'];
        if (collection.includes('aster')) return ['B10'];
        if (['daymet-daily-na', 'era5-pds', 'terraclimate'].includes(collection)) {
          return ['tmax', 'tmin'];
        }
        return config.defaultAssets;

      case 'analysis':
        // Return all available bands for analysis
        return config.availableAssets.map((asset: AssetConfig) => asset.name);

      default:
        return config.defaultAssets;
    }
  }
}
