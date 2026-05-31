// Copyright (c) Microsoft Corporation.
// Licensed under the MIT license.

// Collection-specific rendering configuration for STAC data types
// Based on Microsoft Planetary Computer collection capabilities

export interface AssetConfig {
  name: string;
  description: string;
  bands?: string[];
  colormap?: string;
  rescale?: [number, number];
  nodata?: number;
}

export interface CollectionConfig {
  id: string;
  title: string;
  description: string;
  defaultAssets: string[];
  availableAssets: AssetConfig[];
  visualization: {
    emoji: string;
    color: string;
    defaultStyle: 'visual' | 'false-color' | 'natural' | 'radar' | 'thermal';
  };
  tileFormat: 'png' | 'jpg' | 'webp';
  requiresToken: boolean;
  maxZoom: number;
  attribution: string;
}

export const COLLECTION_CONFIGS: Record<string, CollectionConfig> = {
  // Optical Collections
  'sentinel-2-l2a': {
    id: 'sentinel-2-l2a',
    title: 'Sentinel-2 Level-2A',
    description: 'High-resolution optical imagery at 10m resolution',
    defaultAssets: ['visual'],
    availableAssets: [
      { name: 'visual', description: 'True color composite (B04, B03, B02)' },
      { name: 'rendered_preview', description: 'Rendered preview image' },
      { name: 'B01', description: 'Coastal aerosol (443nm)', bands: ['B01'] },
      { name: 'B02', description: 'Blue (490nm)', bands: ['B02'] },
      { name: 'B03', description: 'Green (560nm)', bands: ['B03'] },
      { name: 'B04', description: 'Red (665nm)', bands: ['B04'] },
      { name: 'B05', description: 'Vegetation red edge (705nm)', bands: ['B05'] },
      { name: 'B06', description: 'Vegetation red edge (740nm)', bands: ['B06'] },
      { name: 'B07', description: 'Vegetation red edge (783nm)', bands: ['B07'] },
      { name: 'B08', description: 'NIR (842nm)', bands: ['B08'] },
      { name: 'B8A', description: 'Vegetation red edge (865nm)', bands: ['B8A'] },
      { name: 'B09', description: 'Water vapour (945nm)', bands: ['B09'] },
      { name: 'B11', description: 'SWIR (1610nm)', bands: ['B11'] },
      { name: 'B12', description: 'SWIR (2190nm)', bands: ['B12'] }
    ],
    visualization: {
      emoji: '',
      color: '#e8f8f5',
      defaultStyle: 'visual'
    },
    tileFormat: 'png',
    requiresToken: true,
    maxZoom: 18,
    attribution: 'ESA/Copernicus via Planetary Computer'
  },

  'landsat-c2-l2': {
    id: 'landsat-c2-l2',
    title: 'Landsat Collection 2 Level-2',
    description: 'Landsat satellite imagery with 30m resolution',
    defaultAssets: ['visual'],
    availableAssets: [
      { name: 'visual', description: 'True color composite' },
      { name: 'rendered_preview', description: 'Rendered preview image' },
      { name: 'red', description: 'Red band', bands: ['red'] },
      { name: 'green', description: 'Green band', bands: ['green'] },
      { name: 'blue', description: 'Blue band', bands: ['blue'] },
      { name: 'nir08', description: 'Near infrared', bands: ['nir08'] },
      { name: 'swir16', description: 'SWIR 1.6μm', bands: ['swir16'] },
      { name: 'swir22', description: 'SWIR 2.2μm', bands: ['swir22'] },
      { name: 'lwir11', description: 'Thermal infrared', bands: ['lwir11'] }
    ],
    visualization: {
      emoji: '',
      color: '#e8f5e8',
      defaultStyle: 'visual'
    },
    tileFormat: 'png',
    requiresToken: true,
    maxZoom: 22, // Allow deep zoom to see full 30m resolution with @4x tile scaling
    attribution: 'USGS/NASA via Planetary Computer'
  },

  // Radar Collections
  'sentinel-1-rtc': {
    id: 'sentinel-1-rtc',
    title: 'Sentinel-1 RTC',
    description: 'Radar imagery for all-weather monitoring',
    defaultAssets: ['vh'],
    availableAssets: [
      { name: 'vh', description: 'VH polarization', bands: ['vh'], rescale: [-30, 0] },
      { name: 'vv', description: 'VV polarization', bands: ['vv'], rescale: [-30, 0] }
    ],
    visualization: {
      emoji: '',
      color: '#f0f4ff',
      defaultStyle: 'radar'
    },
    tileFormat: 'png',
    requiresToken: true,
    maxZoom: 16,
    attribution: 'ESA via Planetary Computer'
  },

  // MODIS Surface Reflectance Collections
  'modis-09A1-061': {
    id: 'modis-09A1-061',
    title: 'MODIS Surface Reflectance 8-Day (500m)',
    description: 'MODIS Terra/Aqua Surface Reflectance 8-Day composite at 500m resolution',
    defaultAssets: ['visual'],
    availableAssets: [
      { name: 'visual', description: 'True color composite (sur_refl_b01, sur_refl_b04, sur_refl_b03)' },
      { name: 'rendered_preview', description: 'Rendered preview image' },
      { name: 'sur_refl_b01', description: 'Red (620-670nm)', bands: ['sur_refl_b01'], rescale: [0, 3000] },
      { name: 'sur_refl_b02', description: 'NIR (841-876nm)', bands: ['sur_refl_b02'], rescale: [0, 3000] },
      { name: 'sur_refl_b03', description: 'Blue (459-479nm)', bands: ['sur_refl_b03'], rescale: [0, 3000] },
      { name: 'sur_refl_b04', description: 'Green (545-565nm)', bands: ['sur_refl_b04'], rescale: [0, 3000] },
      { name: 'sur_refl_b05', description: 'NIR (1230-1250nm)', bands: ['sur_refl_b05'], rescale: [0, 3000] },
      { name: 'sur_refl_b06', description: 'SWIR (1628-1652nm)', bands: ['sur_refl_b06'], rescale: [0, 3000] },
      { name: 'sur_refl_b07', description: 'SWIR (2105-2155nm)', bands: ['sur_refl_b07'], rescale: [0, 3000] }
    ],
    visualization: {
      emoji: '',
      color: '#e8f5e8',
      defaultStyle: 'visual'
    },
    tileFormat: 'png',
    requiresToken: false,
    maxZoom: 12,
    attribution: 'NASA via Planetary Computer'
  },

  'modis-09Q1-061': {
    id: 'modis-09Q1-061',
    title: 'MODIS Surface Reflectance 8-Day (250m)',
    description: 'MODIS Terra/Aqua Surface Reflectance 8-Day composite at 250m resolution',
    defaultAssets: ['visual'],
    availableAssets: [
      { name: 'visual', description: 'True color composite (sur_refl_b01, sur_refl_b02)' },
      { name: 'rendered_preview', description: 'Rendered preview image' },
      { name: 'sur_refl_b01', description: 'Red (620-670nm)', bands: ['sur_refl_b01'], rescale: [0, 3000] },
      { name: 'sur_refl_b02', description: 'NIR (841-876nm)', bands: ['sur_refl_b02'], rescale: [0, 3000] }
    ],
    visualization: {
      emoji: '',
      color: '#e8f8e8',
      defaultStyle: 'visual'
    },
    tileFormat: 'png',
    requiresToken: false,
    maxZoom: 12,
    attribution: 'NASA via Planetary Computer'
  },

  // MODIS Vegetation Indices
  'modis-13Q1-061': {
    id: 'modis-13Q1-061',
    title: 'MODIS Vegetation Indices 16-Day (250m)',
    description: 'MODIS Terra/Aqua Vegetation Indices 16-Day composite at 250m resolution',
    defaultAssets: ['250m_16_days_NDVI'],
    availableAssets: [
      { name: '250m_16_days_NDVI', description: 'NDVI (Normalized Difference Vegetation Index)', bands: ['250m_16_days_NDVI'], rescale: [-2000, 10000], colormap: 'viridis' },
      { name: '250m_16_days_EVI', description: 'EVI (Enhanced Vegetation Index)', bands: ['250m_16_days_EVI'], rescale: [-2000, 10000], colormap: 'viridis' },
      { name: '250m_16_days_VI_Quality', description: 'VI Quality flags', bands: ['250m_16_days_VI_Quality'] }
    ],
    visualization: {
      emoji: '',
      color: '#e8ffe8',
      defaultStyle: 'natural'
    },
    tileFormat: 'png',
    requiresToken: false,
    maxZoom: 12,
    attribution: 'NASA via Planetary Computer'
  },

  'modis-13A1-061': {
    id: 'modis-13A1-061',
    title: 'MODIS Vegetation Indices 16-Day (500m)',
    description: 'MODIS Terra/Aqua Vegetation Indices 16-Day composite at 500m resolution',
    defaultAssets: ['500m_16_days_NDVI'],
    availableAssets: [
      { name: '500m_16_days_NDVI', description: 'NDVI (Normalized Difference Vegetation Index)', bands: ['500m_16_days_NDVI'], rescale: [-2000, 10000], colormap: 'viridis' },
      { name: '500m_16_days_EVI', description: 'EVI (Enhanced Vegetation Index)', bands: ['500m_16_days_EVI'], rescale: [-2000, 10000], colormap: 'viridis' },
      { name: '500m_16_days_VI_Quality', description: 'VI Quality flags', bands: ['500m_16_days_VI_Quality'] }
    ],
    visualization: {
      emoji: '',
      color: '#f0fff0',
      defaultStyle: 'natural'
    },
    tileFormat: 'png',
    requiresToken: false,
    maxZoom: 12,
    attribution: 'NASA via Planetary Computer'
  },

  // MODIS Leaf Area Index
  'modis-15A2H-061': {
    id: 'modis-15A2H-061',
    title: 'MODIS Leaf Area Index 8-Day (500m)',
    description: 'MODIS Terra/Aqua Leaf Area Index 8-Day composite at 500m resolution',
    defaultAssets: ['Lai_500m'],
    availableAssets: [
      { name: 'Lai_500m', description: 'Leaf Area Index', bands: ['Lai_500m'], rescale: [0, 100], colormap: 'viridis' },
      { name: 'Fpar_500m', description: 'Fraction of Photosynthetically Active Radiation', bands: ['Fpar_500m'], rescale: [0, 100], colormap: 'viridis' },
      { name: 'FparLai_QC', description: 'LAI/FPAR Quality flags', bands: ['FparLai_QC'] },
      { name: 'FparExtra_QC', description: 'Extra Quality flags', bands: ['FparExtra_QC'] }
    ],
    visualization: {
      emoji: '',
      color: '#f0fff4',
      defaultStyle: 'natural'
    },
    tileFormat: 'png',
    requiresToken: false,
    maxZoom: 12,
    attribution: 'NASA via Planetary Computer'
  },

  // MODIS Gross Primary Productivity
  'modis-17A2H-061': {
    id: 'modis-17A2H-061',
    title: 'MODIS Gross Primary Productivity 8-Day (500m)',
    description: 'MODIS Terra/Aqua Gross Primary Productivity 8-Day composite at 500m resolution',
    defaultAssets: ['Gpp_500m'],
    availableAssets: [
      { name: 'Gpp_500m', description: 'Gross Primary Productivity', bands: ['Gpp_500m'], rescale: [0, 30000], colormap: 'plasma' },
      { name: 'PsnNet_500m', description: 'Net Photosynthesis', bands: ['PsnNet_500m'], rescale: [0, 30000], colormap: 'plasma' },
      { name: 'Psn_QC_500m', description: 'Quality flags', bands: ['Psn_QC_500m'] }
    ],
    visualization: {
      emoji: '',
      color: '#e8f5e8',
      defaultStyle: 'natural'
    },
    tileFormat: 'png',
    requiresToken: false,
    maxZoom: 12,
    attribution: 'NASA via Planetary Computer'
  },

  // MODIS Net Primary Productivity
  'modis-17A3HGF-061': {
    id: 'modis-17A3HGF-061',
    title: 'MODIS Net Primary Productivity Annual (500m)',
    description: 'MODIS Terra/Aqua Net Primary Productivity Annual composite at 500m resolution',
    defaultAssets: ['Npp_500m'],
    availableAssets: [
      { name: 'Npp_500m', description: 'Net Primary Productivity', bands: ['Npp_500m'], rescale: [0, 32700], colormap: 'plasma' },
      { name: 'Npp_QC_500m', description: 'Quality flags', bands: ['Npp_QC_500m'] }
    ],
    visualization: {
      emoji: '',
      color: '#e6f3e6',
      defaultStyle: 'natural'
    },
    tileFormat: 'png',
    requiresToken: false,
    maxZoom: 12,
    attribution: 'NASA via Planetary Computer'
  },

  // MODIS Fire Detection
  'modis-14A1-061': {
    id: 'modis-14A1-061',
    title: 'MODIS Thermal Anomalies Daily',
    description: 'MODIS Terra/Aqua Thermal Anomalies/Fire Daily L3 Global',
    defaultAssets: ['FireMask'],
    availableAssets: [
      { name: 'FireMask', description: 'Fire detection mask', bands: ['FireMask'], colormap: 'hot' },
      { name: 'MaxFRP', description: 'Maximum Fire Radiative Power', bands: ['MaxFRP'], rescale: [0, 1500], colormap: 'hot' },
      { name: 'QA', description: 'Quality Assessment', bands: ['QA'] }
    ],
    visualization: {
      emoji: '',
      color: '#ffe4e1',
      defaultStyle: 'thermal'
    },
    tileFormat: 'png',
    requiresToken: false,
    maxZoom: 12,
    attribution: 'NASA via Planetary Computer'
  },

  'modis-14A2-061': {
    id: 'modis-14A2-061',
    title: 'MODIS Thermal Anomalies 8-Day',
    description: 'MODIS Terra/Aqua Thermal Anomalies/Fire 8-Day L3 Global',
    defaultAssets: ['FireMask'],
    availableAssets: [
      { name: 'FireMask', description: 'Fire detection mask (8-day composite)', bands: ['FireMask'], colormap: 'hot' },
      { name: 'MaxFRP', description: 'Maximum Fire Radiative Power', bands: ['MaxFRP'], rescale: [0, 1500], colormap: 'hot' },
      { name: 'QA', description: 'Quality Assessment', bands: ['QA'] }
    ],
    visualization: {
      emoji: '',
      color: '#ffe4e1',
      defaultStyle: 'thermal'
    },
    tileFormat: 'png',
    requiresToken: false,
    maxZoom: 12,
    attribution: 'NASA via Planetary Computer'
  },

  // Climate Collections
  'modis': {
    id: 'modis',
    title: 'MODIS',
    description: 'Global daily observations from Terra and Aqua',
    defaultAssets: ['B01'],
    availableAssets: [
      { name: 'B01', description: 'Red (620-670nm)', bands: ['B01'] },
      { name: 'B02', description: 'NIR (841-876nm)', bands: ['B02'] },
      { name: 'B03', description: 'Blue (459-479nm)', bands: ['B03'] },
      { name: 'B04', description: 'Green (545-565nm)', bands: ['B04'] }
    ],
    visualization: {
      emoji: '',
      color: '#fff5e6',
      defaultStyle: 'natural'
    },
    tileFormat: 'png',
    requiresToken: false,
    maxZoom: 12,
    attribution: 'NASA via Planetary Computer'
  },

  'daymet-daily-na': {
    id: 'daymet-daily-na',
    title: 'Daymet Daily North America',
    description: 'Daily weather data on 1km grid for North America',
    defaultAssets: ['tmax'],
    availableAssets: [
      { name: 'tmax', description: 'Maximum temperature', bands: ['tmax'], colormap: 'turbo' },
      { name: 'tmin', description: 'Minimum temperature', bands: ['tmin'], colormap: 'turbo' },
      { name: 'prcp', description: 'Precipitation', bands: ['prcp'], colormap: 'blues' },
      { name: 'swe', description: 'Snow water equivalent', bands: ['swe'], colormap: 'winter' }
    ],
    visualization: {
      emoji: '',
      color: '#f0f8ff',
      defaultStyle: 'natural'
    },
    tileFormat: 'png',
    requiresToken: false,
    maxZoom: 14,
    attribution: 'ORNL DAAC via Planetary Computer'
  },

  'era5-pds': {
    id: 'era5-pds',
    title: 'ERA5 Reanalysis',
    description: 'Global atmospheric reanalysis data',
    defaultAssets: ['temperature_2m'],
    availableAssets: [
      { name: 'temperature_2m', description: '2m temperature', bands: ['temperature_2m'], colormap: 'turbo' },
      { name: 'precipitation', description: 'Total precipitation', bands: ['precipitation'], colormap: 'blues' },
      { name: 'wind_speed_10m', description: '10m wind speed', bands: ['wind_speed_10m'], colormap: 'viridis' }
    ],
    visualization: {
      emoji: '',
      color: '#f5f5ff',
      defaultStyle: 'natural'
    },
    tileFormat: 'png',
    requiresToken: false,
    maxZoom: 10,
    attribution: 'ECMWF via Planetary Computer'
  },

  // Elevation Collections
  'nasadem': {
    id: 'nasadem',
    title: 'NASADEM',
    description: 'Global elevation model at 30m resolution',
    defaultAssets: ['elevation'],
    availableAssets: [
      { name: 'elevation', description: 'Elevation in meters', bands: ['elevation'], colormap: 'terrain' }
    ],
    visualization: {
      emoji: '',
      color: '#f5f0e8',
      defaultStyle: 'natural'
    },
    tileFormat: 'png',
    requiresToken: false,
    maxZoom: 16,
    attribution: 'NASA via Planetary Computer'
  },

  'cop-dem-glo-30': {
    id: 'cop-dem-glo-30',
    title: 'Copernicus DEM 30m',
    description: 'Global digital elevation model at 30m',
    defaultAssets: ['data'],
    availableAssets: [
      { name: 'data', description: 'Elevation data', bands: ['data'], colormap: 'terrain' }
    ],
    visualization: {
      emoji: '',
      color: '#f5f5f0',
      defaultStyle: 'natural'
    },
    tileFormat: 'png',
    requiresToken: false,
    maxZoom: 16,
    attribution: 'ESA via Planetary Computer'
  },

  // Weather Collections
  'goes-cmi': {
    id: 'goes-cmi',
    title: 'GOES-R CMI',
    description: 'Real-time weather satellite imagery',
    defaultAssets: ['CMI'],
    availableAssets: [
      { name: 'CMI', description: 'Cloud and Moisture Imagery', bands: ['CMI'] }
    ],
    visualization: {
      emoji: '',
      color: '#f8f8ff',
      defaultStyle: 'natural'
    },
    tileFormat: 'png',
    requiresToken: false,
    maxZoom: 12,
    attribution: 'NOAA via Planetary Computer'
  },

  'terraclimate': {
    id: 'terraclimate',
    title: 'TerraClimate',
    description: 'Monthly climate and water balance data',
    defaultAssets: ['tmax'],
    availableAssets: [
      { name: 'tmax', description: 'Maximum temperature', bands: ['tmax'], colormap: 'turbo' },
      { name: 'tmin', description: 'Minimum temperature', bands: ['tmin'], colormap: 'turbo' },
      { name: 'ppt', description: 'Precipitation', bands: ['ppt'], colormap: 'blues' },
      { name: 'pet', description: 'Potential evapotranspiration', bands: ['pet'], colormap: 'greens' }
    ],
    visualization: {
      emoji: '',
      color: '#e8f4f8',
      defaultStyle: 'natural'
    },
    tileFormat: 'png',
    requiresToken: false,
    maxZoom: 12,
    attribution: 'University of Idaho via Planetary Computer'
  },

  // Weather and Lightning Collections (data only - not visualizable)
  'goes-glm': {
    id: 'goes-glm',
    title: 'GOES Geostationary Lightning Mapper',
    description: 'Lightning detection and fire monitoring data (metadata only)',
    defaultAssets: [],  // No visual assets available
    availableAssets: [
      { name: 'netcdf', description: 'NetCDF4 lightning data file (not visualizable)', bands: [] }
    ],
    visualization: {
      emoji: '',
      color: '#fff8dc',
      defaultStyle: 'natural'
    },
    tileFormat: 'png',
    requiresToken: false,
    maxZoom: 10,
    attribution: 'NOAA via Planetary Computer'
  },

  // Special Collections
  'gbif': {
    id: 'gbif',
    title: 'GBIF Occurrence Data',
    description: 'Global species occurrence data points',
    defaultAssets: [],
    availableAssets: [],
    visualization: {
      emoji: '',
      color: '#f0fff0',
      defaultStyle: 'natural'
    },
    tileFormat: 'png',
    requiresToken: false,
    maxZoom: 18,
    attribution: 'GBIF via Planetary Computer'
  },

  'aster-l1t': {
    id: 'aster-l1t',
    title: 'ASTER L1T',
    description: 'Multispectral imagery for mineral analysis',
    defaultAssets: ['B3N'],
    availableAssets: [
      { name: 'B01', description: 'Green VNIR', bands: ['B01'] },
      { name: 'B02', description: 'Red VNIR', bands: ['B02'] },
      { name: 'B3N', description: 'Near-infrared VNIR', bands: ['B3N'] },
      { name: 'B04', description: 'SWIR 1', bands: ['B04'] },
      { name: 'B05', description: 'SWIR 2', bands: ['B05'] },
      { name: 'B10', description: 'Thermal infrared', bands: ['B10'] }
    ],
    visualization: {
      emoji: '',
      color: '#fff8e8',
      defaultStyle: 'false-color'
    },
    tileFormat: 'png',
    requiresToken: false,
    maxZoom: 16,
    attribution: 'NASA/METI via Planetary Computer'
  }
};

// Utility functions
export function getCollectionConfig(collectionId: string): CollectionConfig | null {
  return COLLECTION_CONFIGS[collectionId] || null;
}

export function getDefaultAssets(collectionId: string): string[] {
  const config = getCollectionConfig(collectionId);
  return config?.defaultAssets || ['visual'];
}

export function getCollectionVisualization(collectionId: string) {
  const config = getCollectionConfig(collectionId);
  return config?.visualization || {
    emoji: '',
    color: '#f8f9fa',
    defaultStyle: 'visual' as const
  };
}

export function requiresAuthentication(collectionId: string): boolean {
  const config = getCollectionConfig(collectionId);
  return config?.requiresToken || false;
}

export function getTileFormat(collectionId: string): string {
  const config = getCollectionConfig(collectionId);
  return config?.tileFormat || 'png';
}

export function getMaxZoom(collectionId: string): number {
  const config = getCollectionConfig(collectionId);
  return config?.maxZoom || 16;
}
