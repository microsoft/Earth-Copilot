/**
 * Collection Configuration Module
 * 
 * Centralized configuration for all Microsoft Planetary Computer collections.
 * Single source of truth for rendering parameters, zoom levels, and display settings.
 * 
 * Based on FEATURED_COLLECTIONS from backend hybrid_rendering_system.py (23 priority collections)
 */

export enum DataType {
  OPTICAL = 'optical',
  OPTICAL_REFLECTANCE = 'optical_reflectance',
  SAR = 'sar',
  ELEVATION = 'elevation',
  THERMAL = 'thermal',
  VEGETATION = 'vegetation',
  CLIMATE = 'climate',
  FIRE = 'fire',
  SNOW = 'snow',
}

export interface CollectionConfig {
  name: string;
  dataType: DataType;
  minZoom: number;
  maxZoom: number;
  tileSize: number;
  opacity: number;
  renderingHints?: {
    suppressMapLabels?: boolean;  // For DEM/elevation
    fadeEnabled?: boolean;         // Disable fade for MODIS
    tileLoadRadius?: number;       // Load radius (0 for MODIS, 2 for others)
    interpolate?: boolean;         // Enable interpolation (false for thermal)
    buffer?: number;               // Buffer size (32 reduced to prevent geometry errors)
  };
  notes?: string;
}

/**
 * Featured Collections Configuration
 * These 23 collections represent ~80% of Earth Copilot queries
 */
const COLLECTION_CONFIGS: Record<string, CollectionConfig> = {
  // ============================================================================
  // HIGH-RESOLUTION OPTICAL IMAGERY
  // ============================================================================
  'sentinel-2-l2a': {
    name: 'Sentinel-2 Level-2A',
    dataType: DataType.OPTICAL,
    minZoom: 6,
    maxZoom: 22,
    tileSize: 512,
    opacity: 0.85,
    renderingHints: {
      suppressMapLabels: false,
      fadeEnabled: true,
      tileLoadRadius: 2,
      interpolate: true,
      buffer: 128,
    },
    notes: 'High-resolution optical imagery from ESA Sentinel-2 satellites',
  },

  'landsat-c2-l2': {
    name: 'Landsat Collection 2 Level-2',
    dataType: DataType.OPTICAL,
    minZoom: 6,
    maxZoom: 22,
    tileSize: 512,
    opacity: 0.85,
    renderingHints: {
      suppressMapLabels: false,
      fadeEnabled: true,
      tileLoadRadius: 2,
      interpolate: true,
      buffer: 128,
    },
    notes: 'Landsat 8/9 optical and thermal imagery',
  },

  'hls2-l30': {
    name: 'HLS Landsat',
    dataType: DataType.OPTICAL_REFLECTANCE,
    minZoom: 6,
    maxZoom: 22,
    tileSize: 512,
    opacity: 0.85,
    renderingHints: {
      suppressMapLabels: false,
      fadeEnabled: true,
      tileLoadRadius: 2,
      interpolate: true,
      buffer: 128,
    },
    notes: 'Harmonized Landsat Sentinel-2 (HLS) - Landsat component',
  },

  'hls2-s30': {
    name: 'HLS Sentinel-2',
    dataType: DataType.OPTICAL_REFLECTANCE,
    minZoom: 6,
    maxZoom: 22,
    tileSize: 512,
    opacity: 0.85,
    renderingHints: {
      suppressMapLabels: false,
      fadeEnabled: true,
      tileLoadRadius: 2,
      interpolate: true,
      buffer: 128,
    },
    notes: 'Harmonized Landsat Sentinel-2 (HLS) - Sentinel-2 component',
  },

  'naip': {
    name: 'NAIP',
    dataType: DataType.OPTICAL,
    minZoom: 6,
    maxZoom: 22,
    tileSize: 512,
    opacity: 0.85,
    renderingHints: {
      suppressMapLabels: false,
      fadeEnabled: true,
      tileLoadRadius: 2,
      interpolate: true,
      buffer: 128,
    },
    notes: 'National Agriculture Imagery Program - US aerial imagery',
  },

  // ============================================================================
  // ELEVATION MODELS
  // ============================================================================
  'cop-dem-glo-30': {
    name: 'Copernicus DEM 30m',
    dataType: DataType.ELEVATION,
    minZoom: 6,
    maxZoom: 22,
    tileSize: 512,
    opacity: 0.5,  // Lower opacity for DEM to see through to basemap
    renderingHints: {
      suppressMapLabels: true,  // DEM should suppress map labels
      fadeEnabled: true,
      tileLoadRadius: 2,
      interpolate: true,
      buffer: 128,
    },
    notes: 'Copernicus Global Digital Elevation Model 30m resolution',
  },

  'cop-dem-glo-90': {
    name: 'Copernicus DEM 90m',
    dataType: DataType.ELEVATION,
    minZoom: 6,
    maxZoom: 22,
    tileSize: 512,
    opacity: 0.5,
    renderingHints: {
      suppressMapLabels: true,
      fadeEnabled: true,
      tileLoadRadius: 2,
      interpolate: true,
      buffer: 128,
    },
    notes: 'Copernicus Global Digital Elevation Model 90m resolution',
  },

  'nasadem': {
    name: 'NASADEM',
    dataType: DataType.ELEVATION,
    minZoom: 6,
    maxZoom: 22,
    tileSize: 512,
    opacity: 0.5,
    renderingHints: {
      suppressMapLabels: true,
      fadeEnabled: true,
      tileLoadRadius: 2,
      interpolate: true,
      buffer: 128,
    },
    notes: 'NASA Digital Elevation Model',
  },

  // ============================================================================
  // SAR IMAGERY
  // ============================================================================
  'sentinel-1-rtc': {
    name: 'Sentinel-1 RTC',
    dataType: DataType.SAR,
    minZoom: 6,
    maxZoom: 22,
    tileSize: 512,
    opacity: 0.85,
    renderingHints: {
      suppressMapLabels: false,
      fadeEnabled: true,
      tileLoadRadius: 2,
      interpolate: true,
      buffer: 128,
    },
    notes: 'Sentinel-1 SAR Radiometrically Terrain Corrected',
  },

  'sentinel-1-grd': {
    name: 'Sentinel-1 GRD',
    dataType: DataType.SAR,
    minZoom: 6,
    maxZoom: 22,
    tileSize: 512,
    opacity: 0.85,
    renderingHints: {
      suppressMapLabels: false,
      fadeEnabled: true,
      tileLoadRadius: 2,
      interpolate: true,
      buffer: 128,
    },
    notes: 'Sentinel-1 SAR Ground Range Detected',
  },

  // ============================================================================
  // MODIS VEGETATION INDICES
  // ============================================================================
  'modis-13Q1-061': {
    name: 'MODIS NDVI 250m',
    dataType: DataType.VEGETATION,
    minZoom: 10,  // 🔧 CRITICAL: MODIS 1km resolution requires zoom 10+ for tile availability
    maxZoom: 18,
    tileSize: 512,
    opacity: 0.85,
    renderingHints: {
      suppressMapLabels: false,
      fadeEnabled: false,  // Disable fade for MODIS
      tileLoadRadius: 0,   // MODIS sparse data
      interpolate: true,
      buffer: 32,
    },
    notes: 'MODIS 16-day NDVI composite 250m - Terra satellite',
  },

  'modis-13A1-061': {
    name: 'MODIS NDVI 500m',
    dataType: DataType.VEGETATION,
    minZoom: 8,
    maxZoom: 18,
    tileSize: 512,
    opacity: 0.85,
    renderingHints: {
      suppressMapLabels: false,
      fadeEnabled: false,
      tileLoadRadius: 0,
      interpolate: true,
      buffer: 32,
    },
    notes: 'MODIS 16-day NDVI composite 500m - Aqua satellite',
  },

  // ============================================================================
  // MODIS AGRICULTURE/PRODUCTIVITY
  // ============================================================================
  'modis-15A2H-061': {
    name: 'MODIS LAI',
    dataType: DataType.VEGETATION,
    minZoom: 8,
    maxZoom: 18,
    tileSize: 512,
    opacity: 0.85,
    renderingHints: {
      suppressMapLabels: false,
      fadeEnabled: false,
      tileLoadRadius: 0,
      interpolate: true,
      buffer: 32,
    },
    notes: 'MODIS 8-day Leaf Area Index (LAI) 500m',
  },

  'modis-17A3HGF-061': {
    name: 'MODIS NPP',
    dataType: DataType.VEGETATION,
    minZoom: 8,
    maxZoom: 18,
    tileSize: 512,
    opacity: 0.85,
    renderingHints: {
      suppressMapLabels: false,
      fadeEnabled: false,
      tileLoadRadius: 0,
      interpolate: true,
      buffer: 32,
    },
    notes: 'MODIS Annual Net Primary Productivity (NPP) 500m',
  },

  'modis-17A2H-061': {
    name: 'MODIS GPP',
    dataType: DataType.VEGETATION,
    minZoom: 8,
    maxZoom: 18,
    tileSize: 512,
    opacity: 0.85,
    renderingHints: {
      suppressMapLabels: false,
      fadeEnabled: false,
      tileLoadRadius: 0,
      interpolate: true,
      buffer: 32,
    },
    notes: 'MODIS 8-day Gross Primary Productivity (GPP) 500m',
  },

  // ============================================================================
  // MODIS FIRE DETECTION
  // ============================================================================
  'modis-14A1-061': {
    name: 'MODIS Fire Daily',
    dataType: DataType.FIRE,
    minZoom: 10,
    maxZoom: 18,
    tileSize: 512,
    opacity: 0.85,
    renderingHints: {
      suppressMapLabels: false,
      fadeEnabled: false,
      tileLoadRadius: 0,
      interpolate: true,
      buffer: 32,
    },
    notes: 'MODIS Daily Thermal Anomalies and Fire - 1km resolution',
  },

  'modis-14A2-061': {
    name: 'MODIS Fire 8-Day',
    dataType: DataType.FIRE,
    minZoom: 10,
    maxZoom: 18,
    tileSize: 512,
    opacity: 0.85,
    renderingHints: {
      suppressMapLabels: false,
      fadeEnabled: false,
      tileLoadRadius: 0,
      interpolate: true,
      buffer: 32,
    },
    notes: 'MODIS 8-day Thermal Anomalies and Fire - 1km resolution',
  },

  // ============================================================================
  // MODIS SNOW COVER
  // ============================================================================
  'modis-10A1-061': {
    name: 'MODIS Snow Cover',
    dataType: DataType.SNOW,
    minZoom: 8,
    maxZoom: 18,
    tileSize: 512,
    opacity: 0.85,
    renderingHints: {
      suppressMapLabels: false,
      fadeEnabled: false,
      tileLoadRadius: 0,
      interpolate: true,
      buffer: 32,
    },
    notes: 'MODIS Daily Snow Cover 500m',
  },

  // ============================================================================
  // MODIS TEMPERATURE
  // ============================================================================
  'modis-11A1-061': {
    name: 'MODIS Temperature',
    dataType: DataType.THERMAL,
    minZoom: 8,
    maxZoom: 18,
    tileSize: 512,
    opacity: 0.85,
    renderingHints: {
      suppressMapLabels: false,
      fadeEnabled: false,
      tileLoadRadius: 0,
      interpolate: false,  // Disable interpolation for thermal data
      buffer: 32,
    },
    notes: 'MODIS Daily Land Surface Temperature 1km',
  },

  // ============================================================================
  // MODIS SURFACE REFLECTANCE
  // ============================================================================
  'modis-09A1-061': {
    name: 'MODIS Surface Reflectance 500m',
    dataType: DataType.OPTICAL_REFLECTANCE,
    minZoom: 8,
    maxZoom: 18,
    tileSize: 512,
    opacity: 0.85,
    renderingHints: {
      suppressMapLabels: false,
      fadeEnabled: false,
      tileLoadRadius: 0,
      interpolate: true,
      buffer: 32,
    },
    notes: 'MODIS 8-day Surface Reflectance 500m',
  },

  'modis-09Q1-061': {
    name: 'MODIS Surface Reflectance 250m',
    dataType: DataType.OPTICAL_REFLECTANCE,
    minZoom: 8,
    maxZoom: 18,
    tileSize: 512,
    opacity: 0.85,
    renderingHints: {
      suppressMapLabels: false,
      fadeEnabled: false,
      tileLoadRadius: 0,
      interpolate: true,
      buffer: 32,
    },
    notes: 'MODIS 8-day Surface Reflectance 250m',
  },
};

/**
 * Get collection configuration with intelligent fallback
 * 
 * Returns specific config if available, otherwise provides sensible defaults
 * based on collection naming patterns.
 */
export function getCollectionConfig(collectionId: string): CollectionConfig {
  // Direct match for featured collections
  if (COLLECTION_CONFIGS[collectionId]) {
    return COLLECTION_CONFIGS[collectionId];
  }

  // Pattern matching for non-featured collections
  const lowerCollection = collectionId.toLowerCase();

  // MODIS collections (all start with "modis-")
  if (lowerCollection.startsWith('modis-')) {
    return {
      name: collectionId,
      dataType: DataType.VEGETATION,
      minZoom: 10,  // All MODIS need zoom 10+ for 1km resolution tile availability
      maxZoom: 18,
      tileSize: 512,
      opacity: 0.85,
      renderingHints: {
        suppressMapLabels: false,
        fadeEnabled: false,
        tileLoadRadius: 0,
        interpolate: true,
        buffer: 32,
      },
      notes: 'MODIS collection (pattern matched)',
    };
  }

  // DEM/Elevation collections
  if (lowerCollection.includes('dem') || lowerCollection.includes('elevation')) {
    return {
      name: collectionId,
      dataType: DataType.ELEVATION,
      minZoom: 6,
      maxZoom: 22,
      tileSize: 512,
      opacity: 0.5,  // Lower opacity for elevation
      renderingHints: {
        suppressMapLabels: true,
        fadeEnabled: true,
        tileLoadRadius: 2,
        interpolate: true,
        buffer: 128,
      },
      notes: 'Elevation/DEM collection (pattern matched)',
    };
  }

  // SAR collections
  if (lowerCollection.includes('sentinel-1') || lowerCollection.includes('sar')) {
    return {
      name: collectionId,
      dataType: DataType.SAR,
      minZoom: 6,
      maxZoom: 22,
      tileSize: 512,
      opacity: 0.85,
      renderingHints: {
        suppressMapLabels: false,
        fadeEnabled: true,
        tileLoadRadius: 2,
        interpolate: true,
        buffer: 128,
      },
      notes: 'SAR collection (pattern matched)',
    };
  }

  // Default: Optical imagery settings (Sentinel-2, Landsat, etc.)
  return {
    name: collectionId,
    dataType: DataType.OPTICAL,
    minZoom: 6,
    maxZoom: 22,
    tileSize: 512,
    opacity: 0.85,
    renderingHints: {
      suppressMapLabels: false,
      fadeEnabled: true,
      tileLoadRadius: 2,
      interpolate: true,
      buffer: 128,
    },
    notes: 'Optical collection (default fallback)',
  };
}

/**
 * Check if collection is a MODIS collection
 */
export function isMODISCollection(collectionId: string): boolean {
  return collectionId.toLowerCase().includes('modis-');
}

/**
 * Check if collection is an elevation/DEM collection
 */
export function isElevationCollection(collectionId: string): boolean {
  const config = getCollectionConfig(collectionId);
  return config.dataType === DataType.ELEVATION;
}

/**
 * Get all featured collection IDs
 */
export function getFeaturedCollections(): string[] {
  return Object.keys(COLLECTION_CONFIGS);
}
