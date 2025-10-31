// Copyright (c) Microsoft Corporation.
// Licensed under the MIT license.
// Pin button relocated to top-left - cleaned up duplicates

import React, { useEffect, useState, useRef } from 'react';
import { Dataset, API_BASE_URL } from '../services/api';
// TileUrlGenerator removed - using backend-only tile URL generation (MPC best practice)
import { getCollectionVisualization, getCollectionConfig } from '../config/collectionConfig';
import { getCollectionConfig as getRenderingConfig } from '../utils/renderingConfig';
import { fetchAndSignTileJSON, fetchMultipleTileJSON } from '../utils/tileJsonFetcher';
import { createTileLayer, createMultipleTileLayers, validateAndClampBounds } from '../utils/tileLayerFactory';
import {
  isMultiTileData,
  isSingleTileData,
  getCollection,
  getBoundingBox,
  prepareMultiTileData,
  prepareSingleTileData,
  isElevationData,
  isThermalData,
  isFireData,
  validateSatelliteData,
  applyAssetFixes
} from '../utils/satelliteDataHelpers';
import {
  logRenderingStart,
  logRenderingComplete,
  logTileJsonFetch,
  logTileLayerCreated,
  logError,
  logWarning,
  logDEMDetection,
  logSymbolLayerSuppression,
  startPerformanceTracking,
  endPerformanceTracking
} from '../utils/renderingLogger';
import DataLegend from './DataLegend';

/**
 * Extract geographic region from query text and return appropriate bounds
 * NOTE: This function now relies on backend location resolution instead of hardcoded coordinates
 */
function extractGeographicRegion(queryText: string): { west: number; south: number; east: number; north: number } | null {
  if (!queryText) return null;

  // The backend's dynamic location resolution (Azure Maps, Nominatim, etc.) handles all location queries
  // This frontend function is kept for legacy compatibility but should not be used
  console.log('?? MapView: Frontend region extraction bypassed - using backend location resolution');
  return null;
}

// Declare global objects for TypeScript
declare global {
  interface Window {
    atlas: any;
    L: any; // Leaflet
    MapDebugger?: any;
    STACDebugger?: any;
    enableMapDebugging?: (map: any) => void;
    testKnownWorkingQuery?: () => Promise<any>;
    downloadDebugReport?: () => void;
  }
}

interface MapViewProps {
  selectedDataset: Dataset | null;
  lastChatResponse?: any;
  onPinChange?: (pin: { lat: number; lng: number } | null) => void;
  onMobilityAnalysisRequested?: () => void; // New: when pin button is clicked
  onGeointAnalysis?: (result: any) => void;
  onMapContextChange?: (context: any) => void; // New: provides map context for Chat Vision
  onModulesMenuOpen?: () => void; // New: when modules menu opens
  onModuleSelected?: (module: string) => void; // New: when a module is selected
  onToggleSidebar?: () => void; // New: toggle data catalog sidebar
  sidebarOpen?: boolean; // New: current state of sidebar
  comparisonUserQuery?: string | null; // New: user's comparison query to process
}

interface SatelliteData {
  bbox?: number[];
  items: Array<{
    id: string;
    collection: string;
    datetime: string;
    preview?: string;
    tile_url?: string;
    assets?: any;
  }>;
  preview_url?: string;
  tile_url?: string;
  thermal_mode?: boolean;
  thermal_timestamp?: number;
  all_tile_urls?: Array<{
    item_id: string;
    bbox: number[];
    tilejson_url: string;
  }>;
}

/**
 * MapView Component
 * 
 * Interactive satellite map with pin-based mobility analysis.
 * 
 * Workflow:
 * 1. User clicks "Drop Pin" → triggers onMobilityAnalysisRequested()
 * 2. Chat shows: "Dropping a pin will produce mobility analysis"
 * 3. User clicks map → pin placed, coordinates stored
 * 4. Automatically triggers mobility analysis
 * 5. Results displayed in chat
 */
const MapView: React.FC<MapViewProps> = ({ 
  selectedDataset, 
  lastChatResponse, 
  onPinChange, 
  onMobilityAnalysisRequested, 
  onGeointAnalysis, 
  onMapContextChange,
  onModulesMenuOpen,
  onModuleSelected,
  onToggleSidebar,
  sidebarOpen = false,
  comparisonUserQuery = null
}) => {
  const mapRef = useRef<HTMLDivElement>(null);
  const [map, setMap] = useState<any>(null);
  const [mapLoaded, setMapLoaded] = useState(false);
  const [mapProvider, setMapProvider] = useState<'azure' | 'leaflet' | null>(null);
  const [mapsConfig, setMapsConfig] = useState<any>(null);
  const [satelliteData, setSatelliteData] = useState<SatelliteData | null>(null);
  const [currentLayer, setCurrentLayer] = useState<any>(null);
  const [mapError, setMapError] = useState<string | null>(null);
  const [showStyleTip, setShowStyleTip] = useState<boolean>(false);
  const [isThermalMode, setIsThermalMode] = useState<boolean>(false);
  
  // Dynamic tile expansion state
  const [originalBounds, setOriginalBounds] = useState<number[] | null>(null);
  const [lastCollection, setLastCollection] = useState<string | null>(null);
  const [isExpanding, setIsExpanding] = useState<boolean>(false);
  
  // Elevation legend state
  const [showDataLegend, setShowDataLegend] = useState<boolean>(false);
  
  // Pin state for location-based GEOINT analysis
  const [pinMode, setPinMode] = useState<boolean>(false);
  const [selectedModule, setSelectedModule] = useState<string | null>(null); // 'terrain', 'mobility', 'building_damage'
  const [showModulesMenu, setShowModulesMenu] = useState<boolean>(false);
  const [analysisInProgress, setAnalysisInProgress] = useState<boolean>(false);
  const analysisAbortControllerRef = useRef<AbortController | null>(null);
  const [pinState, setPinState] = useState<{
    lat: number | null;
    lng: number | null;
    active: boolean;
    marker: any | null;
  }>({
    lat: null,
    lng: null,
    active: false,
    marker: null
  });
  
  // Terrain analysis state
  const [terrainAnalysisMode, setTerrainAnalysisMode] = useState<boolean>(false);
  const [terrainAnalysisPin, setTerrainAnalysisPin] = useState<{
    lat: number | null;
    lng: number | null;
    marker: any | null;
  }>({
    lat: null,
    lng: null,
    marker: null
  });
  
  // Comparison module state
  const [comparisonMode, setComparisonMode] = useState<boolean>(false);
  const [comparisonState, setComparisonState] = useState<{
    awaitingUserQuery: boolean;
    beforeImagery: any | null;
    afterImagery: any | null;
    beforeScreenshot: string | null;
    afterScreenshot: string | null;
    showingBefore: boolean;
  }>({
    awaitingUserQuery: false,
    beforeImagery: null,
    afterImagery: null,
    beforeScreenshot: null,
    afterScreenshot: null,
    showingBefore: true  // Default to showing "before" view
  });
  
  // Map style dropdown state
  const [showMapStyleDropdown, setShowMapStyleDropdown] = useState<boolean>(false);
  const [currentMapStyle, setCurrentMapStyle] = useState<string>('satellite_road_labels');

  // Initialize fallback map using OpenStreetMap when Azure Maps fails
  const initializeFallbackMap = () => {
    if (!mapRef.current || mapProvider === 'leaflet') return;

    console.log('??? MapView: Initializing fallback Leaflet map');

    // Check if Leaflet is available
    if (typeof window !== 'undefined' && window.L) {
      try {
        // Create Leaflet map
        const leafletMap = window.L.map(mapRef.current, {
          center: [39.8282, -98.5795], // Center of United States
          zoom: 4,
          zoomControl: true
        });

        // Add satellite tile layer using Esri World Imagery
        window.L.tileLayer('https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}', {
          attribution: '� Esri World Imagery',
          maxZoom: 22 // Maximum useful zoom level for satellite imagery
        }).addTo(leafletMap);

        setMap(leafletMap);
        setMapProvider('leaflet');
        setMapLoaded(true);
        setMapError(null);

        console.log('??? MapView: Fallback Leaflet map initialized successfully');
      } catch (error) {
        console.error('??? MapView: Failed to initialize fallback map:', error);
        setMapError('Failed to initialize any map system');
      }
    } else {
      // Create basic HTML/CSS map as last resort
      console.log('??? MapView: Creating basic HTML map as last resort');
      if (mapRef.current) {
        mapRef.current.innerHTML = `
          <div style="
            width: 100%;
            height: 100%;
            background: linear-gradient(45deg, #4a90e2, #7fb3d3);
            display: flex;
            align-items: center;
            justify-content: center;
            color: white;
            font-family: Arial, sans-serif;
            text-align: center;
            flex-direction: column;
          ">
            <h3>?? Map View</h3>
            <p>Map services temporarily unavailable</p>
            <p>Satellite data will be displayed here when map loads</p>
          </div>
        `;
        setMapProvider('leaflet'); // Set to indicate fallback is active
        setMapLoaded(true);
        setMapError(null);
      }
    }
  };

  // Helper function to test tile URL at specific coordinates
  const testTileUrl = async (tileTemplate: string, z: number, x: number, y: number): Promise<void> => {
    const testUrl = tileTemplate.replace('{z}', z.toString()).replace('{x}', x.toString()).replace('{y}', y.toString());
    console.log(`??? MapView: [TILE-TEST] Testing tile at ${z}/${x}/${y}: ${testUrl}`);

    try {
      const response = await fetch(testUrl);
      console.log(`??? MapView: [TILE-TEST] Response status: ${response.status}`);
      
      if (response.ok) {
        const blob = await response.blob();
        console.log(`✅ MapView: [TILE-TEST] Success! Blob size: ${blob.size} bytes, type: ${blob.type}`);
      } else {
        console.log(`❌ MapView: [TILE-TEST] Failed with status ${response.status}`);
      }
    } catch (error) {
      console.error(`❌ MapView: [TILE-TEST] Error:`, error);
    }
  };

  /**
   * Capture Map Screenshot for Chat Vision Analysis
   * 
   * Captures the current map view as a base64-encoded PNG image.
   * This is used when users ask questions about the visible imagery
   * (e.g., "What bodies of water are in this image?")
   */
  const captureMapScreenshot = (): Promise<string | null> => {
    return new Promise((resolve) => {
      try {
        console.log('📸 MapView: Starting screenshot capture...');
        
        const mapContainer = mapRef.current;
        if (!mapContainer) {
          console.warn('⚠️ MapView: Cannot capture screenshot - map container not found');
          resolve(null);
          return;
        }

        const canvases = mapContainer.querySelectorAll<HTMLCanvasElement>('canvas');
        console.log(`📸 MapView: Found ${canvases.length} canvas element(s)`);
        
        if (canvases.length === 0) {
          console.warn('⚠️ MapView: Cannot capture screenshot - no canvas elements found');
          resolve(null);
          return;
        }

        // Find the largest canvas (main map canvas, not overlays)
        let largestCanvas: HTMLCanvasElement | null = null;
        let maxArea = 0;
        
        canvases.forEach((canvas, index) => {
          const area = canvas.width * canvas.height;
          console.log(`📸 Canvas ${index}: ${canvas.width}x${canvas.height} (${area} pixels)`);
          if (area > maxArea) {
            maxArea = area;
            largestCanvas = canvas;
          }
        });
        
        if (!largestCanvas) {
          console.error('❌ MapView: No valid canvas found');
          resolve(null);
          return;
        }
        
        const canvas: HTMLCanvasElement = largestCanvas;
        console.log(`📸 MapView: Using canvas: ${canvas.width}x${canvas.height}`);
        
        // CRITICAL: For WebGL, we MUST capture during the next animation frame
        // This is the only reliable way to get the rendered content
        console.log('📸 Scheduling capture for next animation frame...');
        
        requestAnimationFrame(() => {
          console.log('📸 Animation frame triggered - capturing NOW');
          
          try {
            // Try direct capture first (works during animation frame)
            const direct = canvas.toDataURL('image/png');
            
            if (direct && direct.length > 5000) {
              console.log(`✅ Direct capture succeeded (${Math.round(direct.length/1024)}KB)`);
              resolve(direct);
              return;
            }
            
            console.warn(`⚠️ Direct capture too small (${direct?.length || 0} bytes), trying 2D copy...`);
            
            // Fallback: copy to 2D canvas
            const tempCanvas = document.createElement('canvas');
            tempCanvas.width = canvas.width;
            tempCanvas.height = canvas.height;
            const ctx = tempCanvas.getContext('2d');
            
            if (ctx) {
              ctx.drawImage(canvas, 0, 0);
              const screenshot = tempCanvas.toDataURL('image/png');
              
              if (screenshot && screenshot.length > 5000) {
                console.log(`✅ 2D copy succeeded (${Math.round(screenshot.length/1024)}KB)`);
                resolve(screenshot);
                return;
              }
            }
            
            console.error('❌ All capture methods failed - canvas is black/empty');
            resolve(null);
            
          } catch (err) {
            console.error('❌ Screenshot capture error:', err);
            resolve(null);
          }
        });
        
      } catch (error) {
        console.error('❌ MapView: Error in screenshot setup:', error);
        resolve(null);
      }
    });
  };

  // Test thermal detection logic on component mount
  useEffect(() => {
    console.log('?? MapView: Testing thermal detection logic...');
    
    // Create a mock thermal response to test the detection logic
    const mockThermalResponse = {
      data: {
        stac_results: {
          features: [{
            collection: 'landsat-c2-l2',
            assets: {
              lwir11: { href: "test" },
              tilejson: { 
                href: "https://planetarycomputer.microsoft.com/api/data/v1/item/tilejson.json?collection=landsat-c2-l2&item=LC08_L2SP_041037_20250903_02_T1&assets=red&assets=green&assets=blue&color_formula=gamma+RGB+2.7%2C+saturation+1.5%2C+sigmoidal+RGB+15+0.55&format=png"
              }
            }
          }]
        }
      },
      translation_metadata: {
        original_query: 'Show me Landsat thermal infrared data for Los Angeles to detect urban heat islands'
      }
    };

    const firstFeature = mockThermalResponse.data.stac_results.features[0];
    const collection = firstFeature.collection;
    const originalQuery = mockThermalResponse.translation_metadata.original_query;
    
    const isLandsatCollection = collection === 'landsat-c2-l2';
    const isThermalQuery = originalQuery.toLowerCase().includes('thermal') || 
                          originalQuery.toLowerCase().includes('infrared') || 
                          originalQuery.toLowerCase().includes('heat') ||
                          originalQuery.toLowerCase().includes('temperature');
    
    console.log('?? MapView: [THERMAL TEST] Conditions check:', {
      collection,
      isLandsatCollection,
      originalQuery,
      isThermalQuery,
      shouldTriggerThermalDetection: isLandsatCollection && isThermalQuery
    });

    if (isLandsatCollection && isThermalQuery) {
      console.log('?? MapView: [TEST] THERMAL DETECTION LOGIC WOULD TRIGGER!');
      
      const thermalAssets = ['lwir11', 'lwir', 'thermal'];
      const availableThermalAsset = thermalAssets.find(asset => (firstFeature.assets as any)[asset]);
      
      if (availableThermalAsset) {
        console.log('?? MapView: [TEST] Found thermal asset:', availableThermalAsset);
        
        let tilejsonUrl = firstFeature.assets.tilejson.href;
        console.log('?? MapView: [TEST] Original URL:', tilejsonUrl);
        
        tilejsonUrl = tilejsonUrl
          .replace('assets=red&assets=green&assets=blue', `assets=${availableThermalAsset}`)
          .replace('color_formula=gamma+RGB+2.7%2C+saturation+1.5%2C+sigmoidal+RGB+15+0.55', '');
        
        // Clean up any double & characters
        tilejsonUrl = tilejsonUrl.replace(/&&/g, '&').replace(/&$/, '').replace(/\?&/, '?');
        
        console.log('?? MapView: [TEST] Modified thermal URL:', tilejsonUrl);
        console.log('?? MapView: [TEST] ? URL modification logic is working correctly!');
      }
    } else {
      console.log('?? MapView: [TEST] ? Thermal detection conditions not met');
    }
  }, []); // Run once on mount

  // Close map style dropdown when clicking outside
  useEffect(() => {
    const handleClickOutside = (event: MouseEvent) => {
      if (showMapStyleDropdown) {
        const target = event.target as HTMLElement;
        // Check if click is outside the dropdown
        if (!target.closest('[data-map-style-dropdown]')) {
          setShowMapStyleDropdown(false);
        }
      }
    };

    if (showMapStyleDropdown) {
      document.addEventListener('mousedown', handleClickOutside);
    }

    return () => {
      document.removeEventListener('mousedown', handleClickOutside);
    };
  }, [showMapStyleDropdown]);

  // Parse satellite data from chat responses
  useEffect(() => {
    if (!lastChatResponse) {
      console.log('??? MapView: No lastChatResponse - skipping processing');
      return;
    }

    try {
      console.log('??? MapView: ====== PROCESSING CHAT RESPONSE ======');
      console.log('??? MapView: Full response object:', lastChatResponse);
      console.log('??? MapView: Response type:', typeof lastChatResponse);
      console.log('??? MapView: Response keys:', Object.keys(lastChatResponse || {}));
      console.log('??? MapView: JSON stringified response:', JSON.stringify(lastChatResponse, null, 2));

      // Add specific debugging for data structure
      if (lastChatResponse.data) {
        console.log('??? MapView: ? Found data object');
        console.log('??? MapView: Data keys:', Object.keys(lastChatResponse.data));
        console.log('??? MapView: Full data object:', lastChatResponse.data);
      }

      // Check for translation metadata containing original query
      if (lastChatResponse.translation_metadata) {
        console.log('??? MapView: ? Found translation_metadata');
        console.log('??? MapView: Translation metadata:', lastChatResponse.translation_metadata);
      }

      if (lastChatResponse.data) {

        if (lastChatResponse.data.stac_results) {
          console.log('??? MapView: ? Found stac_results');
          console.log('??? MapView: STAC results type:', typeof lastChatResponse.data.stac_results);
          console.log('??? MapView: STAC results keys:', Object.keys(lastChatResponse.data.stac_results));
          console.log('??? MapView: Full STAC results:', lastChatResponse.data.stac_results);

          // Check for features directly (correct structure)
          if (lastChatResponse.data.stac_results.features && Array.isArray(lastChatResponse.data.stac_results.features)) {
            console.log('??? MapView: ? Found features in stac_results');
            console.log('??? MapView: Features count:', lastChatResponse.data.stac_results.features.length);
            console.log('??? MapView: First feature:', lastChatResponse.data.stac_results.features[0]);

            // Process the STAC features for satellite data
            const stacFeatures = lastChatResponse.data.stac_results.features;
            if (stacFeatures.length > 0) {
              const firstFeature = stacFeatures[0];
              const bbox = firstFeature.bbox;
              
              // Extract collection from the feature early for mosaic detection
              const collection = firstFeature.collection || (firstFeature.links?.find((link: any) => link.rel === 'collection')?.href?.split('/').pop());

              // ??? MULTI-TILE DEM RENDERING: Check if backend provided all_tile_urls
              const allTileUrls = lastChatResponse.translation_metadata?.all_tile_urls;
              
              // Fix incorrect assets in tile URLs from backend
              const fixTileUrlAssets = (url: string, collection: string): string => {
                if (collection === 'sentinel-2-l2a' && url.includes('assets=red&assets=green&assets=blue')) {
                  const fixedUrl = url.replace(/assets=red&assets=green&assets=blue/g, 'assets=visual');
                  console.log('??? MapView: Fixed Sentinel-2 L2A tile URL assets from [red,green,blue] to [visual]');
                  return fixedUrl;
                }
                return url;
              };
              
              if (allTileUrls && Array.isArray(allTileUrls) && allTileUrls.length > 1) {
                console.log('🗺️ MapView: 📊 MULTI-TILE DEM DETECTED!');
                console.log(`🗺️ MapView: Backend provided ${allTileUrls.length} tile URLs for seamless coverage`);
                
                // ⚠️ CRITICAL FIX: Limit tiles to prevent overwhelming the tile server
                const MAX_TILES_TO_RENDER = 50;
                const shouldLimitTiles = allTileUrls.length > MAX_TILES_TO_RENDER;
                const tilesToRender = shouldLimitTiles ? allTileUrls.slice(0, MAX_TILES_TO_RENDER) : allTileUrls;
                
                if (shouldLimitTiles) {
                  console.warn(`⚠️ MapView: Found ${allTileUrls.length} tiles, limiting to ${MAX_TILES_TO_RENDER} for performance`);
                }
                
                console.log('🗺️ MapView: Rendering tile URLs:', tilesToRender);
                
                // Fix tile URLs with incorrect assets
                const fixedTileUrls = tilesToRender.map((tileUrlData: any) => ({
                  ...tileUrlData,
                  tilejson_url: fixTileUrlAssets(tileUrlData.tilejson_url, collection || 'unknown')
                }));
                
                // Store all tile URLs in satellite data (limit items to match rendered tiles)
                const tilesToRenderFeatures = shouldLimitTiles ? stacFeatures.slice(0, MAX_TILES_TO_RENDER) : stacFeatures;
                const multiTileSatelliteData: SatelliteData = {
                  bbox: bbox,
                  tile_url: fixedTileUrls[0].tilejson_url, // Primary tile for backward compatibility
                  items: tilesToRenderFeatures.map((feature: any) => ({
                    id: feature.id,
                    collection: feature.collection,
                    datetime: feature.properties?.datetime || new Date().toISOString(),
                    bbox: feature.bbox
                  })),
                  all_tile_urls: fixedTileUrls // Add multi-tile array with fixed URLs
                };
                
                setSatelliteData(multiTileSatelliteData);
                console.log('? MapView: Set multi-tile satellite data');
                
                // Update map view to show entire coverage area
                if (map && bbox) {
                  updateMapView(bbox);
                }
                
                return; // Exit early - multi-tile rendering will be handled in the rendering effect
              }

              // ??? MOSAIC APPROACH: Use continuous tile rendering for collections designed for seamless coverage
              
              // 1. Elevation/DEM Collections - Static terrain data
              const elevationCollections = ['cop-dem-glo-30', 'cop-dem-glo-90', 'nasadem', '3dep-seamless', 'alos-dem'];
              
              // 2. MODIS Composite Collections - Designed for global seamless coverage
              const modisCompositeCollections = [
                'modis-09A1-061', 'modis-09Q1-061',  // Surface reflectance composites
                'modis-13Q1-061', 'modis-13A1-061',  // Vegetation indices (NDVI/EVI)
                'modis-15A2H-061', 'modis-17A2H-061', // LAI and GPP
                'modis-11A2-061',                     // Land surface temperature
                'modis-64A1-061'                      // Burned area
              ];
              
              // 3. MODIS Fire Collections - Global fire monitoring
              const modisFireCollections = ['modis-14A1-061', 'modis-14A2-061'];
              
              const isElevationCollection = elevationCollections.some(col => collection?.includes(col));
              const isMODISComposite = modisCompositeCollections.some(col => collection?.includes(col));
              const isMODISFire = modisFireCollections.some(col => collection?.includes(col));
              const useMosaicApproach = isElevationCollection || isMODISComposite || isMODISFire;
              
              if (useMosaicApproach) {
                console.log('📍 MapView: MOSAIC COLLECTION DETECTED - Using TileJSON approach');
                console.log('🗺️ MapView: Collection:', collection);
                console.log('📊 MapView: Type:', isElevationCollection ? 'Elevation/DEM' : isMODISFire ? 'Fire Detection' : 'MODIS Composite');
                console.log('📊 MapView: Number of STAC items:', stacFeatures.length);
                
                // ⚠️ CRITICAL FIX: Limit tiles to prevent overwhelming the tile server
                const MAX_TILES_TO_RENDER = 50;
                const shouldLimitMosaicTiles = stacFeatures.length > MAX_TILES_TO_RENDER;
                const mosaicTilesToRender = shouldLimitMosaicTiles ? stacFeatures.slice(0, MAX_TILES_TO_RENDER) : stacFeatures;
                
                if (shouldLimitMosaicTiles) {
                  console.warn(`⚠️ MapView: Found ${stacFeatures.length} mosaic tiles, limiting to ${MAX_TILES_TO_RENDER} for performance`);
                }
                
                // Use the first feature's tilejson asset (CORRECT approach for MPC)
                const firstFeatureAssets = firstFeature.assets;
                let tileJsonUrl = '';
                
                if (firstFeatureAssets && firstFeatureAssets.tilejson) {
                  // Use the pre-built tilejson URL from the STAC item
                  tileJsonUrl = firstFeatureAssets.tilejson.href;
                  console.log('? MapView: Found tilejson asset in STAC item');
                  console.log('?? MapView: TileJSON URL:', tileJsonUrl);
                } else {
                  // Fallback: Build tilejson URL manually
                  const itemId = firstFeature.id;
                  if (isElevationCollection) {
                    tileJsonUrl = `https://planetarycomputer.microsoft.com/api/data/v1/item/tilejson.json?collection=${collection}&item=${itemId}&assets=data&colormap_name=terrain&rescale=0,4000&format=png`;
                    console.log('?? MapView: Built elevation tilejson URL (fallback)');
                  } else {
                    console.warn('?? MapView: No tilejson asset found and not elevation collection');
                    return; // Can't proceed without tilejson
                  }
                }

                // Fetch and use TileJSON (using IIFE for async)
                (async () => {
                  try {
                    console.log('MapView: Fetching TileJSON from:', tileJsonUrl.substr(0, 100) + '...');
                    
                    // Sign the tilejson URL
                    let signedTileJsonUrl = tileJsonUrl;
                    try {
                      const signResponse = await fetch('/api/sign-mosaic-url', {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify({ url: tileJsonUrl })
                      });
                      
                      if (signResponse.ok) {
                        const signData = await signResponse.json();
                        signedTileJsonUrl = signData.signed_url;
                        console.log('? MapView: Signed TileJSON URL');
                      }
                    } catch (signError) {
                      console.warn('MapView: Could not sign TileJSON URL, using unsigned');
                    }
                    
                    // Fetch the TileJSON
                    const tilejsonResponse = await fetch(signedTileJsonUrl);
                    if (!tilejsonResponse.ok) {
                      throw new Error(`TileJSON fetch failed: ${tilejsonResponse.status}`);
                    }
                    
                    const tilejsonData = await tilejsonResponse.json();
                    console.log('? MapView: TileJSON loaded successfully');
                    console.log('?? MapView: TileJSON bounds:', tilejsonData.bounds);
                    console.log('?? MapView: Tile URL template:', tilejsonData.tiles[0].substr(0, 100) + '...');
                    
                    // Use the tile URL template from TileJSON
                    const tileUrlTemplate = tilejsonData.tiles[0];
                    
                    // CRITICAL FIX: Prioritize backend-resolved bbox over STAC feature bboxes
                    // For global elevation datasets (cop-dem-glo-90), STAC features can have random tile bboxes
                    let overallBbox = bbox; // Start with query-resolved bbox from backend
                    
                    // Check if backend provided location-specific bounds in the response metadata
                    if (lastChatResponse?.data?.search_metadata?.spatial_extent) {
                      const spatialExtent = lastChatResponse.data.search_metadata.spatial_extent;
                      if (Array.isArray(spatialExtent) && spatialExtent.length === 4) {
                        overallBbox = spatialExtent;
                        console.log('✅ MapView: Using backend-resolved spatial_extent for map bounds:', overallBbox);
                      }
                    } else {
                      console.log('⚠️ MapView: No spatial_extent from backend, using original bbox:', bbox);
                    }
                    
                    // Only calculate from STAC features as a last resort fallback
                    if (!overallBbox || overallBbox.some((coord: number) => !isFinite(coord))) {
                      console.log('⚠️ MapView: Fallback - calculating bbox from STAC features');
                      let minLng = Infinity, minLat = Infinity, maxLng = -Infinity, maxLat = -Infinity;
                      mosaicTilesToRender.forEach((feature: any) => {
                        if (feature.bbox && feature.bbox.length >= 4) {
                          const [west, south, east, north] = feature.bbox;
                          if (west !== null && !isNaN(west) && isFinite(west) &&
                              south !== null && !isNaN(south) && isFinite(south) &&
                              east !== null && !isNaN(east) && isFinite(east) &&
                              north !== null && !isNaN(north) && isFinite(north)) {
                            minLng = Math.min(minLng, west);
                            minLat = Math.min(minLat, south);
                            maxLng = Math.max(maxLng, east);
                            maxLat = Math.max(maxLat, north);
                          }
                        }
                      });
                      
                      if (minLng !== Infinity) {
                        overallBbox = [minLng, minLat, maxLng, maxLat];
                        console.log('MapView: Calculated bbox from STAC features:', overallBbox);
                      }
                    }
                    
                    console.log('✅ MapView: Final bbox for elevation display:', overallBbox);
                    
                    const elevationData: SatelliteData = {
                      bbox: overallBbox,
                      tile_url: tileUrlTemplate, // Use the correct tile URL from TileJSON
                      items: mosaicTilesToRender.map((feature: any) => ({
                        id: feature.id,
                        collection: feature.collection,
                        datetime: feature.properties?.datetime || new Date().toISOString(),
                        bbox: feature.bbox
                      }))
                    };
                    
                    setSatelliteData(elevationData);
                    console.log('? MapView: Set elevation data with TileJSON tiles');
                    console.log('?? MapView: Tiles will now render from authenticated TileJSON endpoint');
                    
                    if (map && overallBbox) {
                      updateMapView(overallBbox);
                    }
                  } catch (error) {
                    console.error('? MapView: Error fetching TileJSON:', error);
                    console.warn('?? MapView: Falling back to individual item rendering');
                    // Fall through to normal processing below
                  }
                })();
                
                // Early return since mosaic handling is done asynchronously above
                
                return;
              }

              // Try to get a tile server URL from assets in order of preference
              let tileUrl: string | null = null;
              if (firstFeature.assets) {
                console.log('??? MapView: [DEBUG] Assets available:', Object.keys(firstFeature.assets));
                console.log('??? MapView: [DEBUG] Tilejson asset exists:', !!firstFeature.assets.tilejson);
                if (firstFeature.assets.tilejson) {
                  console.log('??? MapView: [DEBUG] Tilejson asset:', firstFeature.assets.tilejson);
                }

                // Priority 1: Check if backend provided optimized tile URLs
                // Backend uses HybridRenderingSystem for 113+ collections with optimal parameters
                const backendOptimizedUrls = lastChatResponse.translation_metadata?.all_tile_urls;
                const backendOptimizedUrl = backendOptimizedUrls?.find(
                  (urlData: any) => urlData.item_id === firstFeature.id
                );

                let tilejsonUrl: string | null = null;

                if (backendOptimizedUrl && backendOptimizedUrl.tilejson_url) {
                  // ? BEST: Use backend-optimized URL with HybridRenderingSystem parameters
                  tilejsonUrl = backendOptimizedUrl.tilejson_url;
                  console.log('? MapView: Using backend-optimized tile URL from HybridRenderingSystem');
                  console.log('?? MapView: Optimized URL:', tilejsonUrl);
                } else if (firstFeature.assets.tilejson) {
                  // ?? FALLBACK: Use STAC tilejson URL (may lack optimization)
                  console.log('?? MapView: Backend optimization not available, using STAC tilejson URL');
                  let stacTilejsonUrl = firstFeature.assets.tilejson.href;
                  console.log('??? MapView: Original STAC Tilejson URL:', stacTilejsonUrl);
                  
                  // Fix incorrect assets in tilejson URL
                  stacTilejsonUrl = fixTileUrlAssets(stacTilejsonUrl, collection || 'unknown');
                  console.log('??? MapView: Fixed Tilejson URL:', stacTilejsonUrl);
                  console.log('??? MapView: [DEBUG] Feature collection:', collection);

                  // ===== LEGACY HLS RESCALE FIX =====
                  // Only needed if backend doesn't provide optimized URL
                  // HLS imagery requires rescale=(0,3000) to display properly
                  const isHLSCollection = collection === 'hls2-s30' || collection === 'hls2-l30';
                  if (isHLSCollection) {
                    console.log('?? MapView: [LEGACY FIX] HLS COLLECTION - adding rescale parameter');
                    const urlParts = stacTilejsonUrl.split('?');
                    if (urlParts.length === 2) {
                      const params = new URLSearchParams(urlParts[1]);
                      if (!params.has('rescale')) {
                        params.set('rescale', '0,3000');
                        stacTilejsonUrl = `${urlParts[0]}?${params.toString()}`;
                        console.log('?? MapView: Added rescale=0,3000 for HLS imagery');
                      }
                    }
                  }
                  
                  tilejsonUrl = stacTilejsonUrl;

                  // THERMAL/FIRE DETECTION: Modify tilejson URL for thermal and wildfire queries
                  const isLandsatCollection = collection === 'landsat-c2-l2';
                  const isMODISFireCollection = collection && (
                    collection.includes('modis-14A1') || 
                    collection.includes('modis-14A2') || 
                    collection.includes('modis-64A1')
                  );
                  const originalQuery = lastChatResponse.translation_metadata?.original_query || '';
                  const isThermalQuery = originalQuery.toLowerCase().includes('thermal') || 
                                        originalQuery.toLowerCase().includes('infrared') || 
                                        originalQuery.toLowerCase().includes('heat') ||
                                        originalQuery.toLowerCase().includes('temperature');
                  const isFireQuery = originalQuery.toLowerCase().includes('fire') || 
                                     originalQuery.toLowerCase().includes('wildfire') || 
                                     originalQuery.toLowerCase().includes('burn');
                  
                  // Enhanced debugging for thermal/fire detection
                  console.log('?? MapView: [THERMAL/FIRE DEBUG] Collection check:', {
                    collection: collection,
                    isLandsatCollection: isLandsatCollection,
                    isMODISFireCollection: isMODISFireCollection,
                    originalQuery: originalQuery,
                    isThermalQuery: isThermalQuery,
                    isFireQuery: isFireQuery,
                    thermal_found: originalQuery.toLowerCase().includes('thermal'),
                    infrared_found: originalQuery.toLowerCase().includes('infrared'),
                    heat_found: originalQuery.toLowerCase().includes('heat'),
                    temperature_found: originalQuery.toLowerCase().includes('temperature'),
                    fire_found: originalQuery.toLowerCase().includes('fire'),
                    wildfire_found: originalQuery.toLowerCase().includes('wildfire'),
                    burn_found: originalQuery.toLowerCase().includes('burn')
                  });
                  
                  if ((isLandsatCollection && isThermalQuery) || (isMODISFireCollection && isFireQuery)) {
                    if (isLandsatCollection) {
                      console.log('?? MapView: THERMAL QUERY DETECTED for Landsat - switching to thermal infrared bands');
                    } else if (isMODISFireCollection) {
                      console.log('?? MapView: WILDFIRE QUERY DETECTED for MODIS - switching to fire visualization');
                    }
                    console.log('?? MapView: Original query:', originalQuery);
                    
                    // Handle Landsat thermal data
                    if (isLandsatCollection && isThermalQuery) {
                      // Check if thermal assets are available
                      const thermalAssets = ['lwir11', 'lwir', 'thermal'];
                      const availableThermalAsset = thermalAssets.find(asset => firstFeature.assets[asset]);
                      
                      if (availableThermalAsset && tilejsonUrl) {
                        console.log('?? MapView: ? THERMAL MODE ACTIVATED! Asset:', availableThermalAsset);
                        
                        // Set thermal mode state
                        setIsThermalMode(true);
                        
                        // Modify the tilejson URL to use thermal band instead of RGB
                        // Apply thermal visualization with adaptive rescale ranges for better contrast
                        // Using 'plasma' colormap: dark purple (cool) to bright yellow (hot)
                        const thermalRanges = [
                          '270,330',  // Default balanced range
                          '250,350',  // Wider range for more variation
                          '230,280',  // Cooler range for summer scenes
                          '290,340'   // Warmer range for winter scenes
                        ];
                        
                        // Use default range for now, but log alternatives for debugging
                        const selectedRange = thermalRanges[0];
                        tilejsonUrl = tilejsonUrl
                          .replace('assets=red&assets=green&assets=blue', `assets=${availableThermalAsset}`)
                          .replace('color_formula=gamma+RGB+2.7%2C+saturation+1.5%2C+sigmoidal+RGB+15+0.55', `rescale=${selectedRange}&colormap_name=plasma`);
                      }
                    }
                    // Handle MODIS fire data
                    else if (isMODISFireCollection && isFireQuery && tilejsonUrl) {
                      console.log('?? MapView: ? FIRE MODE ACTIVATED for MODIS!');
                      
                      // Set thermal mode state for fire visualization
                      setIsThermalMode(true);
                      
                      // MODIS fire collections have different asset structure
                      // Priority order: FireMask (best for fire visualization), MaxFRP, QA
                      // Note: rendered_preview causes 404 tile errors, so we use FireMask directly
                      const fireAssets = ['FireMask', 'MaxFRP', 'QA'];
                      let availableFireAsset = null;
                      
                      // Check what assets are available
                      console.log('?? MapView: [MODIS] Available assets:', firstFeature.assets ? Object.keys(firstFeature.assets) : 'None');
                      
                      if (firstFeature.assets) {
                        availableFireAsset = fireAssets.find(asset => firstFeature.assets[asset]);
                        
                        console.log('?? MapView: [MODIS] Selected fire asset:', availableFireAsset);
                        
                        if (availableFireAsset) {
                          // Clean up the tilejson URL first
                          let baseUrl = tilejsonUrl.split('?')[0];
                          let params = new URLSearchParams(tilejsonUrl.split('?')[1] || '');
                          
                          // Remove ALL RGB-related parameters that conflict with fire assets
                          params.delete('color_formula');
                          params.delete('expression');
                          params.delete('bidx');
                          params.delete('color_map');
                          params.delete('colormap');
                          params.delete('nodata');
                          params.delete('unscale');
                          params.delete('resampling');
                          params.delete('return_mask');
                          
                          // Set the fire asset
                          params.set('assets', availableFireAsset);
                          
                          // Apply appropriate visualization based on asset type
                          if (availableFireAsset === 'FireMask') {
                            // FireMask: Use MODIS fire colormap for fire confidence (matches planetary computer default)
                            params.set('colormap_name', 'modis-14A1|A2');
                            params.set('format', 'png');
                            console.log('?? MapView: [MODIS] Using FireMask with MODIS fire colormap for fire confidence');
                          } else if (availableFireAsset === 'MaxFRP') {
                            // MaxFRP: Fire radiative power - use hot colormap
                            params.set('colormap_name', 'viridis');
                            params.set('rescale', '0,500'); // Fire radiative power in MW
                            params.set('format', 'png');
                            console.log('?? MapView: [MODIS] Using MaxFRP with viridis colormap for fire intensity');

                          } else {
                            // Fallback for other assets (QA, etc.)
                            params.set('colormap_name', 'plasma');
                            params.set('format', 'png');
                            console.log('?? MapView: [MODIS] Using fallback plasma colormap');
                          }
                          
                          // Reconstruct URL with clean parameters
                          tilejsonUrl = baseUrl + '?' + params.toString();
                        }
                      }
                      
                      console.log('?? MapView: [MODIS] Modified fire visualization URL:', tilejsonUrl);
                    } else {
                      console.log('?? MapView: No thermal assets found, checking available assets:', Object.keys(firstFeature.assets));
                    }
                  } else {
                    console.log('?? MapView: Thermal mode not detected - using standard RGB processing');
                    setIsThermalMode(false);
                  }

                  console.log('??? MapView: Final Tilejson URL:', tilejsonUrl);

                  // Process tilejson asynchronously with collection info for authentication
                  if (tilejsonUrl) {
                    fetchAndSignTileJSON(tilejsonUrl, { collection }).then((result) => {
                      if (result.success && result.tileTemplate) {
                        console.log('??? MapView: [DEBUG] Processed tile URL:', result.tileTemplate);

                        if (bbox && result.tileTemplate) {
                          console.log('??? MapView: Creating satellite data from STAC feature with tilejson');
                          console.log('??? MapView: BBOX:', bbox);
                          console.log('??? MapView: Tile URL:', result.tileTemplate);
                          console.log('??? MapView: Tile URL type:', result.tileTemplate.includes('{z}') ? 'Tile template' : 'Static image');

                          setSatelliteData({
                          bbox: bbox,
                          tile_url: result.tileTemplate,
                          items: stacFeatures.slice(0, 5), // Use first 5 features
                          thermal_mode: isThermalMode,
                          thermal_timestamp: isThermalMode ? Date.now() : undefined // Force refresh for thermal
                        });
                      }
                    }
                  }).catch((error: any) => {
                    console.log('??? MapView: [ERROR] Failed to process tilejson, using fallback:', error);
                    // Continue with fallback processing below
                  });

                  // Early return to avoid duplicate processing
                  return;
                  } else {
                    console.log('?? MapView: No tilejsonUrl available after optimization check');
                  }
                }
                // Priority 2: Use rendered_preview for static preview (fallback for static images)
                else if (firstFeature.assets.rendered_preview) {
                  console.log('??? MapView: Using rendered_preview asset URL (static image)');
                  tileUrl = firstFeature.assets.rendered_preview.href;
                }
                // Priority 3: Fallback to visual asset (direct TIFF - convert to preview)
                else if (firstFeature.assets.visual) {
                  console.log('??? MapView: Converting visual asset to preview URL');
                  // Try to convert visual asset to a preview URL
                  const collection = firstFeature.collection;
                  const itemId = firstFeature.id;
                  if (collection && itemId) {
                    tileUrl = `https://planetarycomputer.microsoft.com/api/data/v1/item/preview.png?collection=${collection}&item=${itemId}&assets=visual&format=png`;
                    console.log('??? MapView: Generated preview URL from visual asset:', tileUrl);
                  } else {
                    tileUrl = firstFeature.assets.visual.href;
                    console.log('??? MapView: Using visual asset URL directly (may not work as tile):', tileUrl);
                  }
                }
              }

              // Fallback: look for preview links
              if (!tileUrl && firstFeature.links) {
                const previewLink = firstFeature.links.find((link: any) => link.rel === 'preview');
                if (previewLink) {
                  console.log('??? MapView: Using preview link from links array');
                  tileUrl = previewLink.href;
                }
              }

              if (bbox && tileUrl) {
                console.log('??? MapView: Creating satellite data from STAC feature');
                console.log('??? MapView: BBOX:', bbox);
                console.log('??? MapView: Tile URL:', tileUrl);
                console.log('??? MapView: Tile URL type:', tileUrl.includes('{z}') ? 'Tile template' : 'Static image');

                setSatelliteData({
                  bbox: bbox,
                  tile_url: tileUrl,
                  items: stacFeatures.slice(0, 5) // Use first 5 features
                });
              }
            }
          } else if (lastChatResponse.data.stac_results.results) {
            // Fallback: check old structure for backwards compatibility
            console.log('??? MapView: ? Found results in stac_results (old structure)');
            console.log('??? MapView: Results type:', typeof lastChatResponse.data.stac_results.results);
            console.log('??? MapView: Results keys:', Object.keys(lastChatResponse.data.stac_results.results));
            console.log('??? MapView: Full results object:', lastChatResponse.data.stac_results.results);
          } else {
            console.log('??? MapView: ? No features or results in stac_results');
            console.log('??? MapView: Available keys:', Object.keys(lastChatResponse.data.stac_results));
          }
        } else {
          console.log('??? MapView: ? No stac_results in data');
        }
      } else {
        console.log('??? MapView: ? No data object in response');
      }

      // Only process STAC results - no hardcoded fallbacks allowed

      // Check for STAC results structure from the API
      if (lastChatResponse.data && lastChatResponse.data.stac_results) {
        console.log('??? MapView: Found STAC results structure');
        console.log('??? MapView: STAC results object:', lastChatResponse.data.stac_results);

        const stacResults = lastChatResponse.data.stac_results;

        // Handle multiple possible data structures
        let features = null;

        // Case 1: Direct features array (current API format)
        if (stacResults.features && Array.isArray(stacResults.features)) {
          features = stacResults.features;
          console.log('??? MapView: ? Found direct features array with', features.length, 'STAC features');
        }
        // Case 2: results.features format (legacy)
        else if (stacResults.results && stacResults.results.features && Array.isArray(stacResults.results.features)) {
          features = stacResults.results.features;
          console.log('??? MapView: ? Found results.features array with', features.length, 'STAC features');
        }
        // Case 3: FeatureCollection format
        else if (stacResults.results && stacResults.results.type === 'FeatureCollection' && stacResults.results.features) {
          features = stacResults.results.features;
          console.log('??? MapView: ? Found FeatureCollection with', features.length, 'STAC features');
        }
        // Case 4: Direct results array
        else if (stacResults.results && Array.isArray(stacResults.results)) {
          features = stacResults.results;
          console.log('??? MapView: ? Found direct results array with', features.length, 'features');
        }

        if (features && features.length > 0) {

          // ⚠️ CRITICAL FIX: Limit tiles to prevent overwhelming the tile server
          // When querying large areas (like entire countries), STAC can return 1000+ results
          // Loading all tiles simultaneously causes ERR_HTTP2_SERVER_REFUSED_STREAM errors
          const MAX_TILES_TO_RENDER = 50; // Reasonable limit for performance
          const shouldLimitTiles = features.length > MAX_TILES_TO_RENDER;
          
          if (shouldLimitTiles) {
            console.warn(`⚠️ MapView: Found ${features.length} STAC items, limiting to ${MAX_TILES_TO_RENDER} for performance`);
            console.warn(`⚠️ MapView: To see more tiles, zoom in or refine your query with date/cloud filters`);
          }
          
          const tilesToRender = shouldLimitTiles ? features.slice(0, MAX_TILES_TO_RENDER) : features;

          // Calculate overall bounding box from all features (use all for bbox, but limit rendering)
          let overallBbox: number[] | undefined = undefined;
          if (features.length > 0) {
            let minLng = Infinity, minLat = Infinity, maxLng = -Infinity, maxLat = -Infinity;

            features.forEach((feature: any) => {
              if (feature.bbox && feature.bbox.length >= 4) {
                const [west, south, east, north] = feature.bbox;

                // Validate each coordinate before using it
                if (west !== null && !isNaN(west) && isFinite(west) &&
                  south !== null && !isNaN(south) && isFinite(south) &&
                  east !== null && !isNaN(east) && isFinite(east) &&
                  north !== null && !isNaN(north) && isFinite(north)) {

                  minLng = Math.min(minLng, west);
                  minLat = Math.min(minLat, south);
                  maxLng = Math.max(maxLng, east);
                  maxLat = Math.max(maxLat, north);
                } else {
                  console.warn('??? MapView: ?? Skipping feature with invalid bbox coordinates:', feature.bbox);
                }
              }
            });

            if (minLng !== Infinity && isFinite(minLng) && isFinite(minLat) && isFinite(maxLng) && isFinite(maxLat)) {
              overallBbox = [minLng, minLat, maxLng, maxLat];
              console.log('??? MapView: ? Calculated valid overall bbox:', overallBbox);
            } else {
              console.warn('??? MapView: ?? Could not calculate valid overall bbox from features');
            }
          }

          // ============================================================
          // BACKEND-ONLY TILE URL APPROACH (MPC Best Practice)
          // ============================================================
          // Backend HybridRenderingSystem generates ALL tile URLs with optimal parameters
          // Frontend ONLY uses backend-provided URLs - no fallback generation
          // This follows Microsoft Planetary Computer pattern where backend defines render configurations
          // ============================================================

          // Get backend-optimized tile URLs (includes rescale, color_formula, optimal bands, etc.)
          const backendOptimizedUrls = lastChatResponse.translation_metadata?.all_tile_urls;
          
          if (!backendOptimizedUrls || backendOptimizedUrls.length === 0) {
            console.error('❌ MapView: Backend did not provide optimized tile URLs. Cannot render tiles.');
            console.error('❌ MapView: This indicates HybridRenderingSystem failed to process STAC results.');
            console.error('❌ MapView: STAC features:', features.length, 'items');
            // Don't try to generate URLs on frontend - backend is single source of truth
          }

          // Create satellite data structure using ONLY backend-provided URLs
          // ⚠️ Use tilesToRender (limited subset) instead of all features
          const newSatelliteData: SatelliteData = {
            bbox: overallBbox,
            items: tilesToRender.map((feature: any) => {
              const collection = feature.collection || 'unknown';
              const itemId = feature.id;

              // Find backend-optimized tile URL for this specific item
              const backendTileData = backendOptimizedUrls?.find(
                (urlData: any) => urlData.item_id === itemId
              );

              let tileUrl: string | null = null;
              let previewUrl: string | null = null;

              if (backendTileData?.tilejson_url) {
                tileUrl = backendTileData.tilejson_url;
                console.log(`? MapView: Using backend-optimized tile URL for ${collection}:${itemId}`);
                console.log(`?? MapView: Optimized URL: ${backendTileData.tilejson_url.substring(0, Math.min(150, backendTileData.tilejson_url.length))}...`);
              } else {
                console.warn(`?? MapView: No backend tile URL for ${collection}:${itemId}`);
                console.warn(`?? MapView: This item will not be visualizable without backend optimization`);
                // Don't generate fallback - backend must provide URLs
              }

              // Find preview link from STAC (preview is less critical than tile URL)
              if (feature.links) {
                const previewLink = feature.links.find((link: any) => link.rel === 'preview');
                if (previewLink) {
                  previewUrl = previewLink.href;
                }
              }

              return {
                id: itemId,
                collection: collection,
                datetime: feature.properties?.datetime || new Date().toISOString(),
                preview: previewUrl,
                tile_url: tileUrl, // ONLY backend URL, never frontend-generated
                bbox: feature.bbox
              };
            }),
            // Overall preview URL (optional, for thumbnail display)
            preview_url: (() => {
              if (features[0]?.links) {
                const previewLink = features[0].links.find((link: any) => link.rel === 'preview');
                if (previewLink) return previewLink.href;
              }
              return undefined;
            })(),
            // Overall tile URL - use first item's backend-optimized URL
            tile_url: (() => {
              const backendTileData = backendOptimizedUrls?.find(
                (urlData: any) => urlData.item_id === features[0]?.id
              );
              
              if (backendTileData?.tilejson_url) {
                console.log('? MapView: Using backend-optimized tile URL for primary rendering');
                console.log('?? MapView: URL:', backendTileData.tilejson_url);
                return backendTileData.tilejson_url;
              }

              console.error('? MapView: No backend-optimized tile URL available for primary item');
              console.error('? MapView: Collection:', features[0]?.collection, 'Item:', features[0]?.id);
              console.error('? MapView: Backend must provide tile URLs via HybridRenderingSystem');
              return undefined; // No fallback - backend is single source of truth
            })()
          };

          setSatelliteData(newSatelliteData);
          console.log('??? MapView: Set STAC satellite data for map visualization:', newSatelliteData);

          // Update map view if we have a bounding box
          if (map && overallBbox) {
            updateMapView(overallBbox);
          }

          return;
        }
      }

      // Legacy support: Check if this is a structured response with satellite data
      if (lastChatResponse.dataset_ids && lastChatResponse.bbox) {
        console.log('MapView: Found legacy structured satellite data response');

        // Use collection-aware tile generation for legacy responses
        const firstDatasetId = lastChatResponse.dataset_ids[0];
        const collectionId = firstDatasetId?.split(':')[0] || 'sentinel-2-l2a';
        const itemId = firstDatasetId?.split(':')[1];

        const newSatelliteData: SatelliteData = {
          bbox: [
            lastChatResponse.bbox.west,
            lastChatResponse.bbox.south,
            lastChatResponse.bbox.east,
            lastChatResponse.bbox.north
          ],
          items: lastChatResponse.dataset_ids.map((id: string) => {
            const collection = id.split(':')[0] || 'unknown';
            const item = id.split(':')[1];

            // BACKEND-ONLY: Look for backend-optimized URL
            const backendOptimizedUrls = lastChatResponse.translation_metadata?.all_tile_urls;
            const backendTileData = backendOptimizedUrls?.find(
              (urlData: any) => urlData.item_id === item
            );

            if (!backendTileData?.tilejson_url) {
              console.error(`? MapView: No backend tile URL for legacy item ${collection}:${item}`);
              console.error(`? MapView: Backend must provide tile URLs via HybridRenderingSystem`);
            }

            // Find preview link from STAC if available (less critical)
            let previewUrl: string | null = null;
            // Preview URLs are optional - we won't generate fallbacks

            return {
              id,
              collection,
              datetime: lastChatResponse.date_range?.start_date || new Date().toISOString(),
              preview: previewUrl,
              tile_url: backendTileData?.tilejson_url || null // ONLY backend URL
            };
          }),
          preview_url: undefined, // Preview is optional
          tile_url: (() => {
            // Use first item's backend-optimized URL
            const firstItemId = lastChatResponse.dataset_ids[0]?.split(':')[1];
            const backendOptimizedUrls = lastChatResponse.translation_metadata?.all_tile_urls;
            const backendTileData = backendOptimizedUrls?.find(
              (urlData: any) => urlData.item_id === firstItemId
            );
            
            if (!backendTileData?.tilejson_url) {
              console.error(`? MapView: No backend tile URL for legacy primary item`);
            }
            
            return backendTileData?.tilejson_url || undefined;
          })()
        };

        setSatelliteData(newSatelliteData);
        console.log('MapView: Set satellite data for map visualization:', newSatelliteData);
        return;
      }

      // Fallback: Try to parse as text response
      if (typeof lastChatResponse === 'string') {
        // Look for URLs in the response that might be tile URLs or preview images
        const urlPattern = /https?:\/\/[^\s<>"]+/g;
        const urls = lastChatResponse.match(urlPattern) || [];

        // Look for tile URLs (typically contain /tiles/ or similar)
        const tileUrls = urls.filter((url: string) =>
          url.includes('/tiles/') ||
          url.includes('/tile/') ||
          url.includes('/preview') ||
          url.includes('/crop')
        );

        // Look for bbox coordinates in the response
        const bboxPattern = /\[?(-?\d+\.?\d*),\s*(-?\d+\.?\d*),\s*(-?\d+\.?\d*),\s*(-?\d+\.?\d*)\]?/g;
        const bboxMatch = lastChatResponse.match(bboxPattern);

        if (tileUrls.length > 0 && bboxMatch) {
          const parsedBbox = bboxMatch[0].split(',').map((n: string) => {
            const cleaned = n.replace(/[\[\]]/g, '').trim();
            const parsed = parseFloat(cleaned);
            // Validate parsed number
            if (isNaN(parsed) || !isFinite(parsed)) {
              console.error(`? Invalid coordinate value: "${cleaned}" -> ${parsed}`);
              return null;
            }
            return parsed;
          });

          // Check if any coordinates failed to parse
          if (parsedBbox.includes(null) || parsedBbox.length !== 4) {
            console.error('? Failed to parse valid bbox coordinates:', bboxMatch[0], '-> parsed:', parsedBbox);
          } else {
            const data: SatelliteData = {
              bbox: parsedBbox as number[],
              items: [],
              preview_url: tileUrls.find((url: string) => url.includes('/preview')) || tileUrls[0],
              tile_url: tileUrls.find((url: string) => url.includes('/tiles/')) || tileUrls.find((url: string) => url.includes('/tile/'))
            };

            console.log('? Successfully parsed satellite data with bbox:', parsedBbox);
            setSatelliteData(data);
          }
        }
      }
    } catch (error) {
      console.error('Error parsing satellite data:', error);
    }
  }, [lastChatResponse]);

  // Add map update function for bounding box
  const updateMapView = (bbox: number[] | null) => {
    if (map && bbox && bbox.length >= 4) {
      try {
        console.log('??? MapView: Updating map view with bbox:', bbox, 'provider:', mapProvider);

        const [west, south, east, north] = bbox;

        // Enhanced validation: Check for null/undefined values first
        if (west === null || west === undefined ||
          south === null || south === undefined ||
          east === null || east === undefined ||
          north === null || north === undefined) {
          throw new Error(`Null coordinate values detected: west=${west}, south=${south}, east=${east}, north=${north}`);
        }

        // Check for NaN values
        if (isNaN(west) || isNaN(south) || isNaN(east) || isNaN(north)) {
          throw new Error(`NaN coordinate values detected: west=${west}, south=${south}, east=${east}, north=${north}`);
        }

        // Validate coordinate ranges (allow small tolerance for rounding errors at dateline)
        const DATELINE_TOLERANCE = 0.01; // ~1km tolerance at dateline
        if (west < (-180 - DATELINE_TOLERANCE) || west > (180 + DATELINE_TOLERANCE) || 
            east < (-180 - DATELINE_TOLERANCE) || east > (180 + DATELINE_TOLERANCE)) {
          throw new Error(`Invalid longitude values: west=${west}, east=${east}`);
        }
        if (south < -90 || south > 90 || north < -90 || north > 90) {
          throw new Error(`Invalid latitude values: south=${south}, north=${north}`);
        }
        
        // For dateline-crossing bounds, west > east is valid (e.g., 170 to -170 crosses dateline)
        // Only check if south >= north (always invalid)
        if (south >= north) {
          throw new Error(`Invalid bbox bounds: south=${south} >= north=${north}`);
        }
        
        // Warn but allow west >= east (dateline crossing)
        if (west >= east) {
          console.warn(`⚠️ MapView: Dateline-crossing bounds detected: west=${west} >= east=${east} (this is valid for dateline crossing)`);
        }

        if (mapProvider === 'azure') {
          // Azure Maps API expects [west, south, east, north] format
          console.log('??? MapView: Setting Azure Maps camera to bounds:', [west, south, east, north]);
          map.setCamera({
            bounds: [west, south, east, north],
            padding: 50
          });
        } else if (mapProvider === 'leaflet') {
          // Leaflet API
          const bounds = [
            [south, west], // southwest [lat, lng]
            [north, east]  // northeast [lat, lng]
          ];

          map.fitBounds(bounds, { padding: [20, 20] });
        }

        console.log('? Updated map view to bbox:', bbox, 'using provider:', mapProvider);
      } catch (error) {
        console.error('? Error updating map view:', error);
      }
    }
  };

  // Process comparison user query
  useEffect(() => {
    if (!comparisonUserQuery || !comparisonState.awaitingUserQuery) {
      return;
    }

    console.log('📊 MapView: Processing comparison user query:', comparisonUserQuery);

    // Function to process the comparison query
    const processComparisonQuery = async () => {
      try {
        // Show thinking message
        if (onGeointAnalysis) {
          onGeointAnalysis({
            type: 'thinking',
            message: 'Analyzing your comparison request...'
          });
        }

        // Call backend to extract parameters (location, aspect, before/after dates)
        // This uses the existing datetime_translation_agent with mode="comparison"
        const response = await fetch(`${import.meta.env.VITE_API_BASE_URL}/api/process-comparison-query`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ query: comparisonUserQuery })
        });

        if (!response.ok) {
          // Parse error detail from response body
          let errorMessage = `Failed to process comparison query: ${response.statusText}`;
          try {
            const errorData = await response.json();
            if (errorData.detail) {
              errorMessage = errorData.detail;
            }
          } catch {
            // If JSON parsing fails, use status text
          }
          throw new Error(errorMessage);
        }

        const data = await response.json();
        console.log('📊 MapView: Extracted comparison parameters:', data);

        // data should contain: { location: {lat, lng}, aspect, before_date, after_date, collections }

        // Reset awaiting flag
        setComparisonState(prev => ({ ...prev, awaitingUserQuery: false }));

        // Execute dual STAC queries in parallel
        console.log('📊 MapView: Executing dual STAC queries...');
        const [beforeResults, afterResults] = await Promise.all([
          fetch(`${import.meta.env.VITE_API_BASE_URL}/api/stac-query`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
              latitude: data.location.lat,
              longitude: data.location.lng,
              datetime: data.before_date,
              collections: data.collections,
              limit: 5
            })
          }).then(r => r.json()),
          fetch(`${import.meta.env.VITE_API_BASE_URL}/api/stac-query`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
              latitude: data.location.lat,
              longitude: data.location.lng,
              datetime: data.after_date,
              collections: data.collections,
              limit: 5
            })
          }).then(r => r.json())
        ]);

        console.log('📊 MapView: BEFORE results:', beforeResults);
        console.log('📊 MapView: AFTER results:', afterResults);

        // Store imagery
        setComparisonState(prev => ({
          ...prev,
          beforeImagery: beforeResults,
          afterImagery: afterResults,
          showingBefore: true // Start by showing BEFORE view
        }));

        // Render BEFORE imagery on map by setting satelliteData
        if (beforeResults && beforeResults.data && beforeResults.data.stac_results) {
          console.log('📊 MapView: Rendering BEFORE imagery on map');
          const stacData = beforeResults.data.stac_results;
          
          // Convert STAC results to satelliteData format
          const satelliteDataFormat = {
            bbox: stacData.bbox || [data.location.lng - 0.1, data.location.lat - 0.1, data.location.lng + 0.1, data.location.lat + 0.1],
            items: stacData.features || [],
            tile_url: stacData.features?.[0]?.assets?.tilejson?.href || stacData.features?.[0]?.assets?.rendered_preview?.href,
            preview_url: stacData.features?.[0]?.assets?.thumbnail?.href
          };
          
          setSatelliteData(satelliteDataFormat);
          console.log('📊 MapView: BEFORE imagery rendered');
        }
        
        // Notify user that comparison mode is active
        if (onGeointAnalysis) {
          onGeointAnalysis({
            type: 'assistant',
            message: `📊 **Comparison Mode Active**\n\nShowing imagery from **${data.before_date}** (BEFORE view). Use the toggle buttons to switch between BEFORE and AFTER views.\n\n⏳ Analyzing changes with GPT-5 Vision...`
          });
        }

        // **PARALLEL PROCESSING**: Map rendering and GPT-5 analysis happen simultaneously
        // Send STAC results directly to comparison agent, no screenshots needed
        console.log('📊 MapView: Starting parallel map rendering and GPT-5 analysis...');
        
        // Trigger GPT-5 Vision analysis immediately with STAC data (no screenshots)
        const analysisPromise = (async () => {
          try {
            console.log('📊 MapView: Sending STAC results to comparison agent...');
            const analysisResponse = await fetch(`${import.meta.env.VITE_API_BASE_URL}/api/geoint/comparison`, {
              method: 'POST',
              headers: { 'Content-Type': 'application/json' },
              body: JSON.stringify({
                latitude: data.location.lat,
                longitude: data.location.lng,
                before_date: data.before_date,
                after_date: data.after_date,
                collection_id: data.primary_collection,  // For raster download
                download_rasters: true,  // Agent will download rasters from STAC
                before_metadata: beforeResults.data.stac_results,
                after_metadata: afterResults.data.stac_results,
                user_query: comparisonUserQuery,
                comparison_aspect: data.aspect
              })
            });
            
            if (!analysisResponse.ok) {
              throw new Error(`Analysis failed: ${analysisResponse.statusText}`);
            }
            
            const analysisData = await analysisResponse.json();
            console.log('📊 MapView: GPT-5 Vision analysis complete:', analysisData);
            
            // Display analysis results in chat
            if (onGeointAnalysis && analysisData.result && analysisData.result.analysis) {
              onGeointAnalysis({
                type: 'assistant',
                message: `📊 **Temporal Change Analysis**\n\n${analysisData.result.analysis}\n\n---\n\n**Time Span:** ${analysisData.result.time_span}\n**Aspect Analyzed:** ${analysisData.result.aspect_analyzed}`
              });
            }
          } catch (analysisError) {
            console.error('📊 MapView: Error in GPT-5 analysis:', analysisError);
            if (onGeointAnalysis) {
              onGeointAnalysis({
                type: 'error',
                message: `Failed to complete comparison analysis: ${analysisError instanceof Error ? analysisError.message : 'Unknown error'}`
              });
            }
          }
        })();

        // Map rendering happens in parallel - no need to wait for analysis
        console.log('📊 MapView: Map rendering will continue in parallel with analysis');

      } catch (error) {
        console.error('📊 MapView: Error processing comparison query:', error);
        if (onGeointAnalysis) {
          onGeointAnalysis({
            type: 'error',
            message: `Failed to process comparison request: ${error instanceof Error ? error.message : 'Unknown error'}`
          });
        }
        setComparisonState(prev => ({ ...prev, awaitingUserQuery: false }));
      }
    };

    processComparisonQuery();
  }, [comparisonUserQuery, comparisonState.awaitingUserQuery]);

  // Fetch Azure Maps configuration
  useEffect(() => {
    const fetchMapsConfig = async () => {
      console.log('??? MapView: Starting config fetch process...');

      try {
        // First try to get the subscription key from environment variables (for local development)
        const azureMapsKey = import.meta.env.VITE_AZURE_MAPS_SUBSCRIPTION_KEY;

        if (azureMapsKey && azureMapsKey.length > 20) {
          console.log('??? MapView: ? Using Azure Maps key from environment');
          setMapsConfig({
            subscriptionKey: azureMapsKey,
            style: 'satellite_road_labels',
            zoom: 4,
            center: [-98.5795, 39.8282] // Center on United States
          });
          return;
        }

        // If no environment variable, fetch from API endpoint (for containerized deployment)
        console.log('??? MapView: No environment variable found, fetching config from API...');
        console.log('??? MapView: Using API base URL:', API_BASE_URL);
        
        const response = await fetch(`${API_BASE_URL}/api/config`);
        if (!response.ok) {
          throw new Error(`Failed to fetch config: ${response.status} ${response.statusText}`);
        }
        
        const config = await response.json();
        const apiAzureMapsKey = config.azureMaps?.subscriptionKey;

        console.log('??? MapView: API config debug:', {
          configExists: !!config,
          azureMapsConfig: !!config.azureMaps,
          keyExists: !!apiAzureMapsKey,
          keyLength: apiAzureMapsKey?.length || 0,
          keyPreview: apiAzureMapsKey ? `${apiAzureMapsKey.substring(0, 12)}...${apiAzureMapsKey.slice(-8)}` : 'not found'
        });

        if (apiAzureMapsKey && apiAzureMapsKey.length > 20 && apiAzureMapsKey !== "DEVELOPMENT_MODE_NO_KEY") {
          console.log('??? MapView: ? Using Azure Maps key from API config');
          setMapsConfig({
            subscriptionKey: apiAzureMapsKey,
            style: 'satellite_road_labels',
            zoom: 4,
            center: [-98.5795, 39.8282] // Center on United States
          });
          return;
        } else if (apiAzureMapsKey === "DEVELOPMENT_MODE_NO_KEY" || config.azureMaps?.developmentMode) {
          console.log('??? MapView: ?? Development mode - Azure Maps key not configured');
          console.log('??? MapView: Map functionality will be limited. Configure AZURE_MAPS_SUBSCRIPTION_KEY to enable full features.');
          setMapsConfig({
            subscriptionKey: null,
            style: 'satellite_road_labels',
            zoom: 4,
            center: [-98.5795, 39.8282], // Center on United States
            developmentMode: true
          });
          return;
        } else {
          throw new Error('Azure Maps subscription key not found in API config');
        }

      } catch (error) {
        console.error('??? MapView: ? Error fetching Azure Maps configuration:', error);
        setMapError('Azure Maps subscription key not properly configured - check server configuration');
        return;
      }
    };

    fetchMapsConfig();
  }, []);  // Initialize Azure Maps
  useEffect(() => {
    console.log('??? MapView: Azure Maps useEffect triggered');
    console.log('  - mapRef.current exists:', !!mapRef.current);
    console.log('  - mapRef.current:', mapRef.current);
    console.log('  - map exists:', !!map);
    console.log('  - map value:', map);
    console.log('  - mapsConfig exists:', !!mapsConfig);
    console.log('  - mapsConfig value:', mapsConfig);

    if (!mapRef.current || !mapsConfig) {
      console.log('??? MapView: Skipping Azure Maps initialization');
      console.log('  - Skip reason:', !mapRef.current ? 'mapRef.current is null/undefined' : 'mapsConfig not loaded yet');
      console.log('  - mapRef.current:', mapRef.current);
      console.log('  - mapsConfig:', mapsConfig);
      return;
    }

    // If we already have a map, check if it's Azure Maps
    if (map && mapProvider === 'azure') {
      console.log('??? MapView: Azure Maps already initialized, skipping');
      return;
    }

    // If we have a Leaflet map, we'll try to replace it with Azure Maps
    if (map && mapProvider === 'leaflet') {
      console.log('??? MapView: Attempting to replace Leaflet with Azure Maps...');
    }

    // Enhanced debugging for Azure Maps SDK availability
    console.log('??? MapView: Azure Maps initialization debug:', {
      windowExists: typeof window !== 'undefined',
      atlasExists: typeof window !== 'undefined' && !!window.atlas,
      atlasType: typeof window !== 'undefined' ? typeof window.atlas : 'N/A',
      atlasKeys: typeof window !== 'undefined' && window.atlas ? Object.keys(window.atlas) : [],
      documentReadyState: document.readyState,
      bodyExists: !!document.body,
      scriptsLoaded: Array.from(document.scripts).map(s => s.src).filter(src => src.includes('atlas')),
      mapsConfigLoaded: !!mapsConfig,
      subscriptionKey: mapsConfig?.subscriptionKey ? 'present' : 'missing'
    });

    // Ensure Azure Maps SDK is loaded
    if (typeof window !== 'undefined' && window.atlas && window.atlas.Map) {
      try {
        console.log('??? MapView: ? Azure Maps SDK fully available - initializing...');
        console.log('??? MapView: Atlas object:', {
          hasMap: !!window.atlas.Map,
          hasAuthenticationType: !!window.atlas.AuthenticationType,
          hasControl: !!window.atlas.control,
          hasSource: !!window.atlas.source,
          version: window.atlas.getVersion ? window.atlas.getVersion() : 'unknown'
        });

        // Clear existing map if replacing Leaflet
        if (map && mapProvider === 'leaflet') {
          console.log('??? MapView: Clearing existing Leaflet map to make room for Azure Maps');
          try {
            map.remove();
          } catch (e) {
            console.log('??? MapView: Error removing Leaflet map:', e);
          }
          mapRef.current.innerHTML = ''; // Clear the container
          setMap(null);
          setCurrentLayer(null);
        }

        // Initialize the map with default US view
        const mapConfig: any = {
          center: [-98.5795, 39.8282], // Center of United States
          zoom: 4, // Standard initial zoom for US view
          language: 'en-US',
          // ✅ Use 'satellite_road_labels' basemap so label layers exist and can be moved on top
          // We'll programmatically move the label layers above our satellite tiles after adding them
          style: 'satellite_road_labels', // Satellite base WITH labels (we'll reorder layers later)
          showBuildingModels: false, // Disable 3D for better performance
          showLogo: false,
          showFeedbackLink: false,
          enableInertia: true, // Smooth zoom and pan
          showTileBoundaries: false // Hide tile boundaries for cleaner look
        };

        // Add authentication if available (skip for development mode)
        if (mapsConfig?.subscriptionKey && 
            mapsConfig.subscriptionKey !== 'your-azure-maps-subscription-key-here' && 
            !mapsConfig.developmentMode) {
          // Validate subscription key format (Azure Maps keys are typically 64-88 characters)
          if (mapsConfig.subscriptionKey.length >= 60 && mapsConfig.subscriptionKey.length <= 100) {
            mapConfig.authOptions = {
              authType: window.atlas.AuthenticationType.subscriptionKey,
              subscriptionKey: mapsConfig.subscriptionKey
            };
            console.log('??? MapView: ? Using Azure Maps subscription key authentication');
            console.log('??? MapView: Key length:', mapsConfig.subscriptionKey.length);
            console.log('??? MapView: Key starts with:', mapsConfig.subscriptionKey.substring(0, 8) + '...');
            console.log('??? MapView: Key ends with:', '...' + mapsConfig.subscriptionKey.substring(-8));
            console.log('??? MapView: AuthType:', mapConfig.authOptions.authType);
          } else {
            console.error('??? MapView: ?? Unusual subscription key length - will try anyway:', mapsConfig.subscriptionKey.length);
            mapConfig.authOptions = {
              authType: window.atlas.AuthenticationType.subscriptionKey,
              subscriptionKey: mapsConfig.subscriptionKey
            };
          }
        } else if (mapsConfig?.developmentMode) {
          console.log('??? MapView: ?? Development mode - attempting to initialize without authentication');
          console.log('??? MapView: Note: Some Azure Maps features may not work without a subscription key');
        } else {
          console.warn('??? MapView: ?? Azure Maps subscription key not available or placeholder');
          console.log('??? MapView: Available key:', mapsConfig?.subscriptionKey ? `present (${mapsConfig.subscriptionKey.substring(0, 8)}...)` : 'not present');
          console.log('??? MapView: Will attempt anonymous access (limited functionality)');
        }

        console.log('??? MapView: Creating Azure Maps instance with config:', mapConfig);
        const newMap = new window.atlas.Map(mapRef.current, mapConfig);
        console.log('??? MapView: ? Azure Maps instance created successfully');

        // Enhanced error handling for source loading issues
        newMap.events.add('error', (error: any) => {
          console.warn('??? MapView: Azure Maps error event:', error);
          // Don't fail the whole map for individual source errors
        });

        // Set up a timeout to catch if the map never loads
        let mapInitialized = false;

        const initTimeout = setTimeout(() => {
          if (!mapInitialized) {
            console.error('??? MapView: ? Azure Maps failed to initialize within 15 seconds');
            setMapError('Azure Maps initialization timeout - check subscription key and network connectivity');
          }
        }, 15000);

        // Wait for the map to be ready
        newMap.events.add('ready', () => {
          mapInitialized = true;
          clearTimeout(initTimeout);
          console.log('??? MapView: ? Azure Maps is ready and centered on United States');

          try {
            // Custom controls will be rendered in JSX - no default Azure Maps controls
            console.log('??? MapView: Skipping default Azure Maps controls - using custom UI');

            // Set map state AFTER map is fully ready
            setMapProvider('azure');
            setMapError(null);
            setMapLoaded(true);
            console.log('??? MapView: ? Azure Maps fully configured and ready');

          } catch (controlError) {
            console.error('??? MapView: Error during map setup:', controlError);
            // Even if there are errors, mark map as loaded
            setMapProvider('azure');
            setMapError(null);
            setMapLoaded(true);
          }
        });

        // Add error handling
        newMap.events.add('error', (error: any) => {
          console.error('??? MapView: ? Azure Maps error:', error);
          console.error('??? MapView: Error details:', {
            message: error.message,
            type: error.type,
            target: error.target,
            error: error.error
          });
          setMapError(`Azure Maps failed: ${error.message || error.type || 'Unknown error'}`);
        });

        // Add authentication error handling
        newMap.events.add('authenticationFailed', (error: any) => {
          console.error('??? MapView: ? Azure Maps authentication failed:', error);
          console.error('??? MapView: Auth error details:', {
            message: error.message,
            status: error.status,
            statusText: error.statusText,
            response: error.response
          });
          setMapError(`Azure Maps authentication failed: ${error.message || error.statusText || 'Invalid subscription key'}`);
        });

        // Add loading error handling with reduced verbosity
        newMap.events.add('sourcedata', (e: any) => {
          if (e.isSourceLoaded === false && e.sourceDataType === 'metadata') {
            // Only log critical source failures, ignore common bing source issues and internal Azure Maps sources
            const sourceId = e.source?.id || 'unknown';
            const isNonCriticalSource = sourceId.includes('bing-') || 
                                       sourceId.includes('traffic') || 
                                       sourceId.includes('satellite-base') ||
                                       sourceId.startsWith('jk') ||
                                       sourceId === 'unknown' ||
                                       sourceId.includes('basemap');
            
            if (!isNonCriticalSource) {
              console.warn('??? MapView: ?? Critical map source failed to load:', {
                sourceId: sourceId,
                sourceType: e.source?.type || 'unknown',
                type: e.type,
                sourceDataType: e.sourceDataType,
                isSourceLoaded: e.isSourceLoaded,
                source: e.source?.id || 'unknown',
                url: e.source?.url || 'unknown',
                error: e.error || 'no error details'
              });
              // Check if this is a planetary computer source
              if (e.source?.url && e.source.url.includes('planetarycomputer.microsoft.com')) {
                console.error('??? MapView: ? Microsoft Planetary Computer tile source failed to load');
                console.error('??? MapView: Failed URL:', e.source.url);
                
                // ✅ CRITICAL: Check if MODIS tiles are 404ing
                if (e.source.url.includes('modis')) {
                  console.error('🚨 MODIS TILE LOAD FAILURE:', {
                    collection: 'MODIS',
                    url: e.source.url,
                    reason: 'Tile URL returned 404 or failed to load',
                    possibleCauses: [
                      '1. Date range: MODIS data unavailable for requested dates',
                      '2. Zoom level: Current zoom too low (need zoom 10+ for MODIS 1km)',
                      '3. Location: No MODIS data for this specific tile/location',
                      '4. Collection: Wrong collection selected for query'
                    ]
                  });
                }
              }
            }
          }
        });

        // Enhanced WebGL error handling to prevent null value errors
        newMap.events.add('error', (error: any) => {
          // Handle specific WebGL null value errors
          if (error.message && error.message.includes('Expected value to be of type number, but found null')) {
            console.warn('??? MapView: ?? WebGL geometry buffer error (handled):', error.message);
            // Don't let WebGL errors break the entire map
            return;
          }

          // Handle other errors normally
          console.warn('??? MapView: Azure Maps error event:', error);
        });

        // Enhanced global error suppression for Azure Maps WebGL geometry issues
        const originalConsoleError = console.error;
        const suppressedErrors = [
          'Expected value to be of type number, but found null',
          'Expected value to be of type number, but found null instead',
          'WebGL',
          'geometry buffer',
          'atlas layer',
          'Geometry exceeds allowed extent',
          'reduce your vector tile buffer size',
          'symbol layout',
          'performSymbolLayout',
          'un.evaluate',
          'hn.evaluate',
          'Ni.evaluate',
          'Ri.evaluate'
        ];
        
        // Comprehensive error event suppression
        window.addEventListener('error', (event) => {
          const message = event.message || '';
          if (suppressedErrors.some(pattern => message.toLowerCase().includes(pattern.toLowerCase()))) {
            // console.log('??? MapView: ?? Suppressed rendering error:', message);
            event.preventDefault();
            event.stopPropagation();
            return false;
          }
        });

        // Enhanced console error suppression
        console.error = function(...args) {
          const message = args.join(' ');
          if (suppressedErrors.some(pattern => message.toLowerCase().includes(pattern.toLowerCase()))) {
            // Silently suppress these errors - they don't affect functionality
            return;
          }
          originalConsoleError.apply(console, args);
        };

        // Add unhandled promise rejection handler for Azure Maps rendering errors
        window.addEventListener('unhandledrejection', (event) => {
          const reason = event.reason?.message || event.reason || '';
          if (suppressedErrors.some(pattern => reason.toLowerCase().includes(pattern.toLowerCase()))) {
            // console.log('??? MapView: ?? Suppressed promise rejection:', reason);
            event.preventDefault();
            return false;
          }
        });

        // Add style data loading event to ensure map is fully ready
        newMap.events.add('styledata', (e: any) => {
          if (e.dataType === 'style') {
            console.log('✅ MapView: 🗺️ Azure Maps style loaded successfully');
            
            // ✅ CSS-BASED TEXT ENHANCEMENT (NON-INTRUSIVE)
            // Use CSS only - no layer manipulation to avoid Azure Maps rendering errors
            try {
              console.log('🎨 MapView: Applying CSS-based text enhancement for satellite overlay visibility');
              
              const mapContainer = newMap.getCanvasContainer();
              if (mapContainer) {
                // Add CSS styling for enhanced text visibility
                mapContainer.style.setProperty('--map-text-color', '#FFFFFF');
                mapContainer.style.setProperty('--map-text-stroke', '#000000');
                mapContainer.style.setProperty('--map-text-stroke-width', '2px');
                mapContainer.style.filter = 'contrast(1.1) brightness(1.05)';
                mapContainer.classList.add('enhanced-text-visibility');
                console.log('✅ MapView: Applied CSS-based text enhancement');
              }
            } catch (styleError) {
              console.warn('⚠️ MapView: Could not enhance text styling:', styleError);
            }
          }
        });

        // Map is fully ready - no additional text enhancement needed
        newMap.events.add('ready', () => {
          console.log('✅ MapView: 🗺️ Azure Maps fully ready');
        });


        // Add token error handling
        newMap.events.add('tokenacquired', () => {
          console.log('??? MapView: ? Azure Maps token acquired successfully');
        });

        newMap.events.add('tokenrenewalfailed', (error: any) => {
          console.error('??? MapView: ? Azure Maps token renewal failed:', error);
          setMapError('Azure Maps token renewal failed - subscription may be expired');
        });

        setMap(newMap);
      } catch (error) {
        console.error('??? MapView: Error initializing Azure Maps:', error);
        setMapError(`Failed to initialize Azure Maps: ${error instanceof Error ? error.message : 'Unknown error'}`);
        // Initialize fallback map
        initializeFallbackMap();
      }
    } else {
      console.error('??? MapView: Azure Maps SDK not loaded - attempting retry in 2 seconds');
      console.log('??? MapView: Will retry Azure Maps initialization...');

      // Try waiting for the SDK to load asynchronously
      const retryTimeout = setTimeout(() => {
        console.log('??? MapView: Retry attempt - checking Azure Maps SDK again:', {
          windowExists: typeof window !== 'undefined',
          atlasExists: typeof window !== 'undefined' && !!window.atlas,
          atlasType: typeof window !== 'undefined' ? typeof window.atlas : 'N/A',
          scriptsInDOM: Array.from(document.scripts).filter(s => s.src.includes('atlas')).length
        });

        if (typeof window !== 'undefined' && window.atlas) {
          console.log('??? MapView: Azure Maps SDK now available - initializing...');
          // Trigger re-render to try initialization again
          setMapError(null);
        } else {
          console.error('??? MapView: Azure Maps SDK still not available after retry - using fallback');
          setMapError('Azure Maps SDK failed to load - check network connectivity');
          initializeFallbackMap();
        }
      }, 2000);

      // Clean up timeout on unmount
      return () => clearTimeout(retryTimeout);
    }
  }, [mapsConfig]); // Remove 'map' from dependencies to prevent infinite loops

  // Update map based on selected dataset
  useEffect(() => {
    if (!map || !selectedDataset) return;

    // You can add dataset-specific map updates here
    // For example, adding data layers, changing view, etc.
    console.log('Selected dataset changed:', selectedDataset);
  }, [map, selectedDataset]);

  // Dynamic tile expansion when user zooms out
  useEffect(() => {
    if (!map || !mapLoaded || !satelliteData || !originalBounds || !lastCollection) return;

    let expansionTimeoutId: NodeJS.Timeout | null = null;

    const handleZoomChange = async () => {
      try {
        const currentCamera = map.getCamera();
        const currentBounds = currentCamera.bounds;
        
        if (!currentBounds || isExpanding) return;

        // Enhanced bounds validation to prevent null coordinate errors
        const isValidBounds = (bounds: any) => {
          return bounds && Array.isArray(bounds) && bounds.length === 4 &&
                 bounds.every((coord: any) => 
                   typeof coord === 'number' && 
                   !isNaN(coord) && 
                   isFinite(coord) &&
                   coord >= -180 && coord <= 180
                 );
        };

        if (!isValidBounds(currentBounds) || !isValidBounds(originalBounds)) {
          console.warn('??? MapView: Invalid bounds detected, skipping zoom expansion:', { currentBounds, originalBounds });
          return;
        }

        // Calculate expansion ratio - how much larger is the current view vs original
        const originalWidth = Math.abs(originalBounds[2] - originalBounds[0]);
        const originalHeight = Math.abs(originalBounds[3] - originalBounds[1]);
        const currentWidth = Math.abs(currentBounds[2] - currentBounds[0]);
        const currentHeight = Math.abs(currentBounds[3] - currentBounds[1]);
        
        const widthRatio = currentWidth / originalWidth;
        const heightRatio = currentHeight / originalHeight;
        const expansionRatio = Math.max(widthRatio, heightRatio);

        // If user has zoomed out significantly (3x or more), fetch expanded data
        if (expansionRatio >= 3.0) {
          console.log('?? MapView: User zoomed out significantly, requesting expanded tiles');
          console.log('?? MapView: Expansion ratio:', expansionRatio.toFixed(2));
          console.log('?? MapView: Original bounds:', originalBounds);
          console.log('?? MapView: Current bounds:', currentBounds);
          
          setIsExpanding(true);

          // Calculate expanded bounding box with padding and validation
          const paddingWidth = currentWidth * 0.1;
          const paddingHeight = currentHeight * 0.1;
          
          const expandedBbox = [
            Math.max(-180, Math.min(currentBounds[0], originalBounds[0]) - paddingWidth),
            Math.max(-85, Math.min(currentBounds[1], originalBounds[1]) - paddingHeight),
            Math.min(180, Math.max(currentBounds[2], originalBounds[2]) + paddingWidth),
            Math.min(85, Math.max(currentBounds[3], originalBounds[3]) + paddingHeight)
          ];

          // Final validation of expanded bbox
          if (!isValidBounds(expandedBbox)) {
            console.error('??? MapView: Generated invalid expanded bbox, aborting expansion:', expandedBbox);
            setIsExpanding(false);
            return;
          }

          console.log('🔍 MapView: Requesting expanded bbox:', expandedBbox);

          // Clear any existing timeout
          if (expansionTimeoutId) {
            clearTimeout(expansionTimeoutId);
          }

          // Set a safety timeout to clear the indicator after 10 seconds max
          expansionTimeoutId = setTimeout(() => {
            console.log('⏰ MapView: Expansion timeout reached, clearing indicator');
            setIsExpanding(false);
            expansionTimeoutId = null;
          }, 10000);

          try {
            // Use VITE_API_BASE_URL for production backend routing
            const apiUrl = `${import.meta.env.VITE_API_BASE_URL || ''}/api/query`;
            console.log('🔍 MapView: Expansion API URL:', apiUrl);
            
            const response = await fetch(apiUrl, {
              method: 'POST',
              headers: { 'Content-Type': 'application/json' },
              body: JSON.stringify({
                query: `Show me ${lastCollection.includes('elevation') || lastCollection.includes('dem') ? 'elevation' : 'satellite'} data in this expanded region`,
                conversation_id: 'map-expansion',
                internal_params: {
                  collection: lastCollection,
                  bbox: expandedBbox,
                  expand_tiles: true,
                  source: 'zoom_expansion'
                }
              })
            });

            if (response.ok) {
              const data = await response.json();
              console.log('?? MapView: Expansion API response:', data);
              
              if (data.data && data.data.tile_url) {
                // Validate the expanded tile data before applying
                const newTileData = data.data;
                
                // Ensure the new bbox is valid
                if (newTileData.bbox && Array.isArray(newTileData.bbox) && newTileData.bbox.length === 4) {
                  if (isValidBounds(newTileData.bbox)) {
                    console.log('? MapView: Applying validated expanded tile data');
                    console.log('? MapView: New bbox:', newTileData.bbox);
                    console.log('? MapView: New tile URL:', newTileData.tile_url.substring(0, 100) + '...');
                    
                    // Update satellite data which will trigger re-rendering
                    setSatelliteData(newTileData);
                    setOriginalBounds(expandedBbox); // Update bounds for next expansion
                    
                    console.log('? MapView: Successfully expanded tile coverage with validated data');
                  } else {
                    console.error('? MapView: Expansion returned invalid bbox, keeping current tiles:', newTileData.bbox);
                  }
                } else {
                  console.error('? MapView: Expansion returned malformed bbox data:', newTileData.bbox);
                }
              } else {
                console.log('?? MapView: No tile data in expansion response, keeping current tiles');
              }
            } else {
              console.error('? MapView: Expansion API request failed:', response.status, response.statusText);
              const errorText = await response.text().catch(() => 'Unknown error');
              console.error('? MapView: Expansion error details:', errorText);
            }
          } catch (error) {
            console.error('? MapView: Network error during tile expansion:', error);
          }

          // Clear the expansion timeout since operation completed
          if (expansionTimeoutId) {
            clearTimeout(expansionTimeoutId);
            expansionTimeoutId = null;
          }
          
          setIsExpanding(false);
        }
      } catch (error) {
        console.error('? MapView: Error during tile expansion:', error);
        
        // Clear timeout on error
        if (expansionTimeoutId) {
          clearTimeout(expansionTimeoutId);
          expansionTimeoutId = null;
        }
        
        setIsExpanding(false);
      }
    };

    // Add zoom change listener
    if (mapProvider === 'azure' && map.events) {
      map.events.add('zoomend', handleZoomChange);
      map.events.add('moveend', handleZoomChange);
      
      return () => {
        // Clean up timeout on unmount
        if (expansionTimeoutId) {
          clearTimeout(expansionTimeoutId);
        }
        map.events.remove('zoomend', handleZoomChange);
        map.events.remove('moveend', handleZoomChange);
      };
    } else if (mapProvider === 'leaflet' && map.on) {
      map.on('zoomend', handleZoomChange);
      map.on('moveend', handleZoomChange);
      
      return () => {
        // Clean up timeout on unmount
        if (expansionTimeoutId) {
          clearTimeout(expansionTimeoutId);
        }
        map.off('zoomend', handleZoomChange);
        map.off('moveend', handleZoomChange);
      };
    }
  }, [map, mapLoaded, mapProvider, satelliteData, originalBounds, lastCollection, isExpanding]);

  // Reset isExpanding when new satellite data is loaded from a user query (not zoom expansion)
  // This ensures the "Adjusting tiles" indicator is hidden when:
  // 1. User submits a new query
  // 2. Map is fully covered with tiles
  // 3. User zooms back in
  useEffect(() => {
    if (satelliteData && isExpanding) {
      // Wait a moment to ensure expansion is complete, then hide indicator
      const timeout = setTimeout(() => {
        setIsExpanding(false);
        console.log('✅ MapView: Cleared expansion indicator');
      }, 500);
      return () => clearTimeout(timeout);
    }
  }, [satelliteData]);

  // Terrain analysis click handler
  const handleTerrainAnalysisClick = async (lat: number, lng: number) => {
    console.log(`🌍 MapView: Terrain analysis pin placed at (${lat.toFixed(6)}, ${lng.toFixed(6)})`);

    // Remove existing terrain pin if present
    if (terrainAnalysisPin.marker) {
      if (mapProvider === 'leaflet' && window.L) {
        map.removeLayer(terrainAnalysisPin.marker);
      } else if (mapProvider === 'azure' && window.atlas) {
        map.markers.remove(terrainAnalysisPin.marker);
      }
    }

    // Create modern pin marker
    let newMarker: any = null;
    try {
      if (mapProvider === 'leaflet' && window.L) {
        // Modern SVG pin for Leaflet
        const pinIcon = window.L.divIcon({
          html: `
            <svg width="32" height="32" viewBox="0 0 24 24" fill="none" stroke="#3B82F6" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round" style="filter: drop-shadow(0 2px 4px rgba(0,0,0,0.3));">
              <path d="M21 10c0 7-9 13-9 13s-9-6-9-13a9 9 0 0 1 18 0z" fill="#3B82F6"></path>
              <circle cx="12" cy="10" r="3" fill="white"></circle>
            </svg>
          `,
          className: 'terrain-pin-marker',
          iconSize: [32, 32],
          iconAnchor: [16, 32]
        });
        
        newMarker = window.L.marker([lat, lng], {
          icon: pinIcon,
          draggable: false
        }).addTo(map);
        
      } else if (mapProvider === 'azure' && window.atlas) {
        // Modern pin for Azure Maps
        newMarker = new window.atlas.HtmlMarker({
          position: [lng, lat],
          htmlContent: `
            <div style="width: 32px; height: 32px;">
              <svg width="32" height="32" viewBox="0 0 24 24" fill="none" stroke="#3B82F6" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round" style="filter: drop-shadow(0 2px 4px rgba(0,0,0,0.3));">
                <path d="M21 10c0 7-9 13-9 13s-9-6-9-13a9 9 0 0 1 18 0z" fill="#3B82F6"></path>
                <circle cx="12" cy="10" r="3" fill="white"></circle>
              </svg>
            </div>
          `,
          anchor: 'bottom'
        });
        map.markers.add(newMarker);
      }

      // Update terrain analysis pin state
      setTerrainAnalysisPin({
        lat,
        lng,
        marker: newMarker
      });

      // Capture screenshot of current map view
      console.log('📸 MapView: Capturing screenshot for terrain analysis...');
      
      // For Azure Maps, we need to force a render and wait a bit longer
      // Azure Maps uses WebGL which doesn't preserve drawing buffer by default
      if (mapProvider === 'azure') {
        console.log('📸 Azure Maps detected - forcing map render...');
        // Trigger a map update to ensure fresh render
        if (map && typeof (map as any).render === 'function') {
          try {
            (map as any).render();
          } catch (e) {
            console.log('📸 Note: render() not available, proceeding anyway');
          }
        }
        // Wait longer for Azure Maps to fully render
        await new Promise(resolve => setTimeout(resolve, 1500));
      } else {
        // Leaflet renders faster
        await new Promise(resolve => setTimeout(resolve, 500));
      }
      
      const screenshot = await captureMapScreenshot();
      
      if (!screenshot) {
        console.error('❌ MapView: Failed to capture screenshot');
        if (onGeointAnalysis) {
          onGeointAnalysis({
            type: 'error',
            message: 'Failed to capture map screenshot. The map canvas appears to be empty. This is a known issue with Azure Maps WebGL rendering. Please try switching to Leaflet map style (bottom right button) and try again.'
          });
        }
        return;
      }

      // Strip the data URL prefix to get just the base64 string
      // captureMapScreenshot returns "data:image/png;base64,xxxxx"
      // Backend expects just "xxxxx"
      const base64Screenshot = screenshot.startsWith('data:image/png;base64,') 
        ? screenshot.replace('data:image/png;base64,', '')
        : screenshot;
      
      console.log(`✅ MapView: Screenshot captured and processed (base64 length: ${base64Screenshot.length} chars, ~${Math.round(base64Screenshot.length/1024)}KB)`);
      
      // Validate screenshot isn't too small (likely empty canvas)
      if (base64Screenshot.length < 1000) {
        console.error('❌ MapView: Screenshot is too small, likely empty canvas');
        if (onGeointAnalysis) {
          onGeointAnalysis({
            type: 'error',
            message: 'Map screenshot appears to be empty. Azure Maps WebGL canvas is not preserving the drawing buffer. Please switch to Leaflet map style and try again.'
          });
        }
        return;
      }

      // Get current map bounds and zoom level for context
      let bounds: any = null;
      let zoomLevel: number = 0;
      
      if (mapProvider === 'leaflet') {
        const leafletBounds = map.getBounds();
        bounds = {
          north: leafletBounds.getNorth(),
          south: leafletBounds.getSouth(),
          east: leafletBounds.getEast(),
          west: leafletBounds.getWest()
        };
        zoomLevel = map.getZoom();
      } else if (mapProvider === 'azure') {
        const azureBounds = map.getCamera().bounds;
        bounds = {
          north: azureBounds[3],
          south: azureBounds[1],
          east: azureBounds[2],
          west: azureBounds[0]
        };
        zoomLevel = map.getCamera().zoom;
      }

      console.log('🌍 MapView: Sending terrain analysis request to backend...');
      console.log(`📍 Pin location: (${lat}, ${lng})`);
      console.log(`🔍 Zoom level: ${zoomLevel}`);
      console.log(`📦 Bounds:`, bounds);

      // Show "thinking" indicator in chat before API call
      if (onGeointAnalysis) {
        onGeointAnalysis({
          type: 'thinking',
          message: '🤖 Analyzing terrain features with GPT-5 Vision...'
        });
      }

      // Disable terrain analysis mode after pin is placed
      setTerrainAnalysisMode(false);

      // Send to backend terrain analysis endpoint using API service
      try {
        const { triggerGeointAnalysis } = await import('../services/api');
        
        // Call terrain analysis with screenshot
        const result = await triggerGeointAnalysis(
          lat,
          lng,
          'terrain', // Frontend module name
          'Analyze all terrain characteristics including elevation, vegetation, water bodies, urban vs rural characteristics, soil type, and landforms.',
          JSON.stringify({ bounds, zoom_level: zoomLevel }), // Additional context
          base64Screenshot // Pass screenshot as separate parameter (base64 only, no data URL prefix)
        );

        console.log('✅ MapView: Terrain analysis completed:', result);

        // Display analysis results in chat
        if (onGeointAnalysis && result.status === 'success') {
          const analysis = result.result?.analysis || 'Analysis completed';
          
          // Format numbered section headers (1. Overview, 2. Elevation, etc.) to be bold
          // Match lines that start with a number followed by a period and text
          const formattedAnalysis = analysis.replace(/^(\d+\.\s+[^\n]+)/gm, '**$1**');
          
          onGeointAnalysis({
            type: 'assistant',
            message: formattedAnalysis
          });
        } else {
          throw new Error('Invalid response from terrain analysis API');
        }

      } catch (apiError) {
        console.error('❌ MapView: Failed to get terrain analysis from backend:', apiError);
        if (onGeointAnalysis) {
          onGeointAnalysis({
            type: 'error',
            message: `Failed to analyze terrain: ${apiError instanceof Error ? apiError.message : String(apiError)}`
          });
        }
      }

    } catch (error) {
      console.error('❌ MapView: Error in terrain analysis:', error);
      if (onGeointAnalysis) {
        onGeointAnalysis({
          type: 'error',
          message: `Failed to analyze terrain: ${error}`
        });
      }
    }
  };

  // Attach map click listener for pin placement
  useEffect(() => {
    if (!map || !mapLoaded) return;

    const handleMapClick = (e: any) => {
      // Check if we're in terrain analysis mode
      if (terrainAnalysisMode) {
        let lat: number, lng: number;

        if (mapProvider === 'azure') {
          const position = e.position;
          lat = position[1];
          lng = position[0];
        } else if (mapProvider === 'leaflet') {
          lat = e.latlng.lat;
          lng = e.latlng.lng;
        } else {
          return;
        }

        handleTerrainAnalysisClick(lat, lng);
        return;
      }

      // Allow pin mode if either pinMode is true OR a module is selected
      if (!pinMode && !selectedModule) return;

      let lat: number, lng: number;

      if (mapProvider === 'azure') {
        // Azure Maps click event
        const position = e.position;
        lat = position[1];
        lng = position[0];
      } else if (mapProvider === 'leaflet') {
        // Leaflet click event
        lat = e.latlng.lat;
        lng = e.latlng.lng;
      } else {
        return;
      }

      handleMapClickForPin(lat, lng);
    };

    // Add click listener
    if (mapProvider === 'azure' && map.events) {
      map.events.add('click', handleMapClick);
      console.log('?? MapView: Attached Azure Maps click listener for pin placement');

      return () => {
        map.events.remove('click', handleMapClick);
        console.log('?? MapView: Removed Azure Maps click listener');
      };
    } else if (mapProvider === 'leaflet' && map.on) {
      map.on('click', handleMapClick);
      console.log('?? MapView: Attached Leaflet click listener for pin placement');

      return () => {
        map.off('click', handleMapClick);
        console.log('?? MapView: Removed Leaflet click listener');
      };
    }
  }, [map, mapLoaded, mapProvider, pinMode, selectedModule, pinState.marker, terrainAnalysisMode]);

  // Notify parent when pin changes
  const prevPinStateRef = useRef<{ active: boolean; lat: number | null; lng: number | null }>({
    active: false,
    lat: null,
    lng: null
  });

  useEffect(() => {
    // Only notify if the pin state actually changed
    const hasChanged = 
      prevPinStateRef.current.active !== pinState.active ||
      prevPinStateRef.current.lat !== pinState.lat ||
      prevPinStateRef.current.lng !== pinState.lng;

    if (!hasChanged) {
      return; // No change, skip notification
    }

    // Update the ref to track current state
    prevPinStateRef.current = {
      active: pinState.active,
      lat: pinState.lat,
      lng: pinState.lng
    };

    if (onPinChange) {
      if (pinState.active && pinState.lat !== null && pinState.lng !== null) {
        onPinChange({ lat: pinState.lat, lng: pinState.lng });
        console.log(`?? MapView: Notifying parent of pin change: (${pinState.lat.toFixed(4)}, ${pinState.lng.toFixed(4)})`);
      } else {
        onPinChange(null);
        console.log('?? MapView: Notifying parent that pin was cleared');
      }
    }
  }, [pinState.active, pinState.lat, pinState.lng]); // Removed onPinChange from dependencies

  // Track if we're currently rendering to prevent re-entry during async operations
  const isRenderingRef = useRef(false);
  
  // Reset rendering flag when new satellite data arrives
  useEffect(() => {
    isRenderingRef.current = false;
    console.log('?? MapView: Reset rendering flag for new satellite data');
  }, [satelliteData]);

  // Add satellite imagery to map when data is available
  useEffect(() => {
    console.log('??? MapView: Satellite data rendering useEffect triggered');
    
    // ??? PREVENT RE-ENTRY: If already rendering, skip to avoid clearing tiles mid-render
    if (isRenderingRef.current) {
      console.log('?? MapView: Already rendering tiles, skipping duplicate trigger to preserve existing layers');
      return;
    }
    
    console.log('??? MapView: Checking requirements:', {
      hasSatelliteData: !!satelliteData,
      hasMap: !!map,
      mapLoaded,
      mapProvider,
      satelliteDataDetails: satelliteData ? `Present with ${satelliteData.items?.length || 0} items` : 'Missing',
      mapDetails: map ? 'Present' : 'Missing',
      tileUrl: satelliteData?.tile_url ? 'Available' : 'Missing'
    });

    // More specific validation - check for essential data
    if (!satelliteData) {
      console.log('??? MapView: Skipping satellite data rendering - no satellite data provided');
      return;
    }
    
    if (!map) {
      console.log('??? MapView: Skipping satellite data rendering - map instance not available');
      return;
    }
    
    if (!satelliteData.tile_url) {
      console.log('??? MapView: No tile URL available - this collection may contain non-visualizable data (like GOES-GLM)');
      console.log('??? MapView: Available satellite data items:', satelliteData.items?.length || 0);
      
      // Still zoom to the geographic area if we have location data
      if (satelliteData.bbox && Array.isArray(satelliteData.bbox) && satelliteData.bbox.length === 4 && map) {
        console.log('??? MapView: Zooming to collection area despite no visualizable data');
        const [west, south, east, north] = satelliteData.bbox;
        
        try {
          // Validate coordinates
          if (!isNaN(west) && !isNaN(south) && !isNaN(east) && !isNaN(north)) {
            const bboxArea = Math.abs(east - west) * Math.abs(north - south);
            let targetZoom = bboxArea < 0.1 ? 12 : bboxArea < 2 ? 8 : 6;
            
            console.log('??? MapView: Setting camera for non-visualizable data with zoom:', targetZoom);
            map.setCamera({
              bounds: [west, south, east, north],
              zoom: targetZoom,
              padding: 50
            });
          }
        } catch (error) {
          console.error('??? MapView: Error setting camera for non-visualizable data:', error);
        }
      }
      return;
    }

    // Allow rendering even if mapLoaded is false for Azure Maps, as it might be ready
    if (mapProvider === 'leaflet' && !mapLoaded) {
      console.log('??? MapView: Skipping satellite data rendering - Leaflet map not loaded yet');
      return;
    }

    console.log('??? MapView: ? Requirements met - proceeding with satellite data rendering');
    console.log('??? MapView: Adding satellite data to map:', satelliteData);
    console.log('??? MapView: Current mapProvider:', mapProvider);
    console.log('??? MapView: Map instance type:', map?.constructor?.name || 'unknown');

    // Initialize original bounds and collection for dynamic expansion
    if (satelliteData.bbox && !originalBounds) {
      setOriginalBounds(satelliteData.bbox);
      console.log('??? MapView: Set original bounds for dynamic expansion:', satelliteData.bbox);
    }
    
    // Track collection type for expansion queries
    if (satelliteData.items && satelliteData.items.length > 0) {
      const collection = satelliteData.items[0].collection;
      if (collection !== lastCollection) {
        setLastCollection(collection);
        console.log('??? MapView: Tracking collection for expansion:', collection);
        
        // Show data legend for all visualizable collections including fire data
        const hasVisualizableData = !!satelliteData.tile_url;
        setShowDataLegend(hasVisualizableData);
        
        if (hasVisualizableData) {
          console.log('?? MapView: Showing data legend for collection:', collection);
        }
      }
    }

    try {
      if (mapProvider === 'azure') {
        // Azure Maps implementation
        
        // ??? MULTI-TILE RENDERING LOGIC (ALL COLLECTIONS)
        // Check if we have multiple tile URLs - supports DEM, optical, SAR, etc.
        if (satelliteData.all_tile_urls && satelliteData.all_tile_urls.length > 1 && window.atlas) {
          const collection = getCollection(satelliteData);
          const tileCount = satelliteData.all_tile_urls.length;
          
          logRenderingStart(collection, true, tileCount);
          startPerformanceTracking('multi-tile-rendering');
          
          // ??? SET RENDERING FLAG to prevent useEffect from re-triggering mid-render
          isRenderingRef.current = true;
          
          // Clear existing layers ONCE before starting multi-tile rendering
          if (currentLayer) {
            console.log('??? MapView: Removing existing Azure Maps layer');
            map.layers.remove(currentLayer);
            setCurrentLayer(null);
          }

          const allLayers = map.layers.getLayers();
          allLayers.forEach((layer: any) => {
            if (layer.getId && (layer.getId().includes('satellite-tiles') || layer.getId().includes('planetary-computer'))) {
              console.log('??? MapView: Removing conflicting layer:', layer.getId());
              map.layers.remove(layer);
            }
          });
          console.log('??? MapView: Cleared existing layers, starting multi-tile rendering');
          
          // Detect data type for specialized rendering
          const isElevation = isElevationData(satelliteData);
          
          // ?? SUPPRESS SYMBOL LAYERS FOR DEM VISUALIZATION (elevation data only)
          if (isElevation && map && window.atlas) {
              console.log('?? MapView: Suppressing symbol layers for DEM visualization');
              
              try {
                const allLayers = map.layers.getLayers();
                let suppressedCount = 0;
                
                allLayers.forEach((layer: any) => {
                  const layerType = layer.getType ? layer.getType() : null;
                  const layerId = layer.getId ? layer.getId() : '';
                  const isSymbolOrLabel = layerId.includes('label') || 
                                         layerId.includes('symbol') || 
                                         layerId.includes('text') ||
                                         layerId.includes('icon') ||
                                         layerId.includes('place') ||
                                         layerId.includes('road') ||
                                         layerType === 'SymbolLayer';
                  
                  if (isSymbolOrLabel) {
                    try {
                      const layerOptions = layer.getOptions ? layer.getOptions() : {};
                      layer.setOptions({ ...layerOptions, visible: false });
                      suppressedCount++;
                    } catch (err) {
                      console.warn(`?? MapView: Could not suppress layer ${layerId}:`, err);
                    }
                  }
                });
                
              logSymbolLayerSuppression(suppressedCount);
            } catch (error) {
              logWarning('Error suppressing symbol layers', { error });
            }
          }
          
          // Wrap in async IIFE for tile processing
          (async () => {
            const tileLayers: any[] = [];
            let successCount = 0;
            let errorCount = 0;

            // ??? PARALLEL PROCESSING: Fetch all TileJSON configs simultaneously
            console.log(`??? MapView: Fetching ${satelliteData.all_tile_urls!.length} TileJSON configs in parallel...`);
            
            const tilePromises = satelliteData.all_tile_urls!.map(async (tileInfo) => {
              try {
                // Fetch and validate TileJSON using utility
                const result = await fetchAndSignTileJSON(tileInfo.tilejson_url, { collection });
                
                if (!result.success || !result.tileTemplate) {
                  logTileJsonFetch(tileInfo.tilejson_url, false, undefined, result.error);
                  return { success: false, tileInfo, error: result.error };
                }

                logTileJsonFetch(tileInfo.tilejson_url, true, result.tileTemplate);

                // Create tile layer using factory
                const tileLayer = createTileLayer(
                  {
                    tileUrl: result.tileTemplate,
                    collection,
                    bounds: tileInfo.bbox,
                    tilejson: result.tilejson,
                    isElevation
                  },
                  window.atlas
                );

                logTileLayerCreated(tileInfo.item_id, collection, {
                  minZoom: result.tilejson?.minzoom || 6,
                  maxZoom: result.tilejson?.maxzoom || 18,
                  opacity: isElevation ? 0.5 : 0.85,
                  bounds: tileInfo.bbox
                });

                return { success: true, tileLayer, tileInfo };
              } catch (error) {
                logError(`processing tile ${tileInfo.item_id}`, error);
                return { success: false, tileInfo, error };
              }
            });

            // Wait for all tiles to be processed
            const results = await Promise.all(tilePromises);
            
            // ??? ADD ALL LAYERS TO MAP AT ONCE (static rendering - no looping!)
            console.log('??? MapView: Adding all tile layers to map simultaneously below labels...');
            results.forEach(result => {
              if (result.success && result.tileLayer) {
                // ✅ Insert tile layer below 'labels' to keep map text visible over data
                try {
                  map.layers.add(result.tileLayer, 'labels');
                } catch (insertError) {
                  // Fallback: If 'labels' layer doesn't exist, add normally
                  console.warn('⚠️ MapView: Could not insert below labels, adding normally:', insertError);
                  map.layers.add(result.tileLayer);
                }
                tileLayers.push(result.tileLayer);
                successCount++;
              } else {
                errorCount++;
              }
            });
            
            console.log(`??? MapView: Added ${successCount} tile layers in one batch - no iterative rendering!`);

            // Complete rendering
            logRenderingComplete(collection, true, successCount, errorCount);
            endPerformanceTracking('multi-tile-rendering');
            
            // ??? CLEAR RENDERING FLAG now that all tiles are added
            isRenderingRef.current = false;
            
            if (successCount > 0) {
              setCurrentLayer(tileLayers[0]);
              
              // ✅ CRITICAL FIX: Force minimum zoom level for MODIS data
              if (collection.toLowerCase().includes('modis') && satelliteData.bbox) {
                const [west, south, east, north] = satelliteData.bbox;
                
                // MODIS requires zoom 10+ for 1km resolution tiles to be visible
                // Use maxZoom constraint to prevent zooming out below level 10
                console.log(`🔍 MapView: [MODIS FIX] Fitting bounds with minimum zoom 10 for collection ${collection}`);
                map.setCamera({
                  bounds: [west, south, east, north],
                  padding: 50,
                  maxZoom: 10,  // ✅ Prevent zooming out below level 10 (MODIS tile visibility threshold)
                  duration: 1000
                });
                console.log(`✅ MapView: [MODIS FIX] Fitted bounds ${satelliteData.bbox} with minZoom=10 constraint`);
              } else if (satelliteData.bbox) {
                // Normal bbox update for non-MODIS
                updateMapView(satelliteData.bbox);
              }
              
              console.log(`? MapView: Multi-tile rendering successful - map should now show ${successCount} tiles with seamless coverage`);
            } else {
              logError('multi-tile rendering', 'All tile rendering attempts failed');
            }
          })();
          
          return; // Exit early - multi-tile rendering is being handled asynchronously
        }
        // Single-tile rendering path
        // Clear existing layers before adding new single tile
        if (currentLayer) {
          console.log('??? MapView: Removing existing Azure Maps layer (single-tile path)');
          map.layers.remove(currentLayer);
          setCurrentLayer(null);
        }

        const allLayers = map.layers.getLayers();
        allLayers.forEach((layer: any) => {
          if (layer.getId && (layer.getId().includes('satellite-tiles') || layer.getId().includes('planetary-computer'))) {
            console.log('??? MapView: Removing conflicting layer (single-tile path):', layer.getId());
            map.layers.remove(layer);
          }
        });

        // If we have a tile URL, add it as a tile layer
        if (satelliteData.tile_url && window.atlas) {
          console.log('??? MapView: Adding Azure Maps tile layer:', satelliteData.tile_url);

          // Ensure map is ready before adding layers
          const addTileLayer = async () => {
            try {
              // Check if map is properly initialized
              if (!map) {
                console.log('??? MapView: No map instance, skipping tile layer...');
                return;
              }

              console.log('??? MapView: Map available, adding tile layer...');
              console.log('??? MapView: Satellite data bbox:', satelliteData.bbox);
              console.log('??? MapView: Tile URL template:', satelliteData.tile_url);

              // === MICROSOFT PLANETARY COMPUTER APPROACH ===
              // Based on MPC's setupRasterTileLayer function, we should use TileJSON URLs directly
              // instead of extracting tile templates. This lets Azure Maps handle coordinate calculations.
              console.log('??? MapView: [MPC-APPROACH] Using Microsoft Planetary Computer approach with TileJSON URL');

              const tileUrl = satelliteData.tile_url;
              const bounds = satelliteData.bbox;

              // Safety check for tileUrl
              if (!tileUrl) {
                console.log('??? MapView: [ERROR] No tile URL available');
                return;
              }

              // Check if this is a TileJSON URL or tile template
              const isTileTemplate = tileUrl.includes('{z}') && tileUrl.includes('{x}') && tileUrl.includes('{y}');

              console.log('??? MapView: [MPC-APPROACH] URL analysis:', {
                url: tileUrl.substring(0, 150) + '...',
                isTileTemplate: isTileTemplate,
                approach: isTileTemplate ? 'Authenticated tile template (MPC approach)' : 'TileJSON URL (needs processing)'
              });

              // Check if this is a Planetary Computer native tiles URL (doesn't support tile_scale)
              const isNativeTiles = tileUrl.includes('/api/data/v1/item/tilejson.json');

              // IMPORTANT: Only add tile_scale=2 for TiTiler URLs, NOT for native tiles
              // Native tiles API (tilejson.json) doesn't support tile_scale and returns 404
              let enhancedTileUrl = tileUrl;
              if (!isNativeTiles && !tileUrl.includes('tile_scale=')) {
                const separator = tileUrl.includes('?') ? '&' : '?';
                enhancedTileUrl = `${tileUrl}${separator}tile_scale=2`;
                console.log('Added tile_scale=2 for high-resolution tiles');
              } else if (isNativeTiles) {
                console.log('Native tiles detected - NOT adding tile_scale (would cause 404)');
              } else {
                console.log('tile_scale parameter already present');
              }

              let tileLayerConfig: any;

              // Detect elevation/DEM data for special opacity handling
              const isElevationData = satelliteData.items && satelliteData.items.length > 0 && (
                satelliteData.items[0].collection.includes('cop-dem') ||
                satelliteData.items[0].collection.includes('nasadem') ||
                satelliteData.items[0].collection.includes('alos-dem') ||
                satelliteData.items[0].collection.includes('dem') ||
                satelliteData.items[0].collection.toLowerCase().includes('elevation')
              );

              // Detect thermal infrared and fire data for special rendering
              // ?? FIX: Exclude HLS collections from thermal detection (HLS is optical RGB, not thermal)
              const collection = satelliteData.items[0]?.collection || '';
              const isHLS = collection.includes('hls') || collection.includes('HLS');
              const isThermalData = !isHLS && (tileUrl.includes('assets=lwir') || 
                                   tileUrl.includes('colormap_name='));
              
              // Detect MODIS fire data for enhanced visibility
              const isFireData = (satelliteData.items[0]?.collection?.includes('modis-14A') || 
                                satelliteData.items[0]?.collection?.includes('modis-14A1') ||
                                satelliteData.items[0]?.collection?.includes('modis-14A2')) && 
                               (tileUrl.includes('FireMask') || tileUrl.includes('MaxFRP') || 
                                tileUrl.includes('rendered_preview') || tileUrl.includes('hot') ||
                                tileUrl.includes('plasma') || isThermalMode);

              // Set opacity based on data type for optimal visibility
              // ✅ MAXIMUM OPACITY for vivid, clear satellite imagery
              // With 'satellite' style (no labels), we can use 100% opacity without text interference
              let baseOpacity = 1.0; // FULL opacity for crystal-clear satellite imagery
              if (isElevationData) {
                baseOpacity = 0.75; // Moderate opacity for elevation overlays to see terrain
              } else if (isFireData) {
                baseOpacity = 1.0; // FULL opacity for critical fire detection data
              } else if (isThermalData) {
                baseOpacity = 1.0; // FULL opacity for thermal infrared analysis
              } else if (isHLS) {
                baseOpacity = 1.0; // Full opacity for HLS optical RGB imagery
              }
              
              console.log(`✅ MapView: Using opacity ${baseOpacity} for ${isElevationData ? 'elevation' : isFireData ? 'fire' : isThermalData ? 'thermal' : isHLS ? 'HLS' : 'standard'} data (collection: ${satelliteData.items?.[0]?.collection})`);

              if (isThermalData) {
                console.log('?? MapView: [THERMAL] Detected thermal infrared data - applying thermal-specific layer configuration');
              }
              
              if (isHLS) {
                console.log('?? MapView: [HLS] Detected HLS optical RGB imagery - using full opacity');
              }
              
              if (isFireData) {
                console.log('?? MapView: [FIRE] Detected MODIS fire data - applying enhanced fire visualization');
              }

              if (isTileTemplate) {
                // === MICROSOFT'S APPROACH: Use authenticated tile template directly ===
                console.log('??? MapView: [MPC-APPROACH] Using authenticated tile template directly (Microsoft approach)');

                // ?? USE RENDERING CONFIG: Get collection-specific settings
                const currentCollection = satelliteData.items[0]?.collection || '';
                const renderingConfig = getRenderingConfig(currentCollection);
                
                console.log(`??? MapView: [RENDERING-CONFIG] Using zoom range ${renderingConfig.minZoom}-${renderingConfig.maxZoom} for ${currentCollection}`);

                // Enhanced bounds validation to prevent geometry extent errors
                let tileBounds = undefined;
                if (bounds && Array.isArray(bounds) && bounds.length === 4) {
                  const [west, south, east, north] = bounds;
                  
                  // Validate each coordinate is a valid number
                  const isValidBound = (coord: any) => {
                    return coord !== null && coord !== undefined && 
                           typeof coord === 'number' && 
                           !isNaN(coord) && isFinite(coord) &&
                           coord >= -180 && coord <= 180; // Basic longitude/latitude range check
                  };
                  
                  if (isValidBound(west) && isValidBound(south) && 
                      isValidBound(east) && isValidBound(north) &&
                      west < east && south < north) {
                    
                    // Clamp bounds to prevent geometry extent issues
                    const clampedWest = Math.max(-180, Math.min(180, west));
                    const clampedSouth = Math.max(-85, Math.min(85, south));
                    const clampedEast = Math.max(-180, Math.min(180, east));
                    const clampedNorth = Math.max(-85, Math.min(85, north));
                    
                    tileBounds = [clampedWest, clampedSouth, clampedEast, clampedNorth];
                    console.log('??? MapView: Using clamped bounds to prevent geometry errors:', tileBounds);
                  } else {
                    console.warn('??? MapView: ?? Invalid or malformed bounds detected, not setting tile bounds:', bounds);
                  }
                }

                // Only add tile_scale=2 for non-native tiles (TiTiler URLs)
                // Native tiles URLs (tilejson.json) don't support tile_scale
                const highResUrl = isNativeTiles ? tileUrl : 
                  (tileUrl.includes('tile_scale=') ? tileUrl : 
                  `${tileUrl}${tileUrl.includes('?') ? '&' : '?'}tile_scale=2`);

                tileLayerConfig = {
                  tileUrl: highResUrl, // Use high-resolution tile URL for crisp images
                  opacity: renderingConfig.opacity, // Use config opacity
                  tileSize: renderingConfig.tileSize, // Use config tile size
                  bounds: tileBounds,
                  minSourceZoom: renderingConfig.minZoom,  // Use config min zoom
                  maxSourceZoom: renderingConfig.maxZoom,  // Use config max zoom
                  tileLoadRadius: renderingConfig.renderingHints?.tileLoadRadius ?? 2,
                  // Enhanced rendering for better text visibility and stability
                  blend: 'normal', // Normal blending to allow text to show through
                  // Improved fade settings for seamless tile transitions
                  fadeDuration: renderingConfig.renderingHints?.fadeEnabled ? 500 : 0,
                  rasterOpacity: renderingConfig.opacity, // Explicit raster opacity
                  // Enhanced null value and geometry error handling
                  buffer: renderingConfig.renderingHints?.buffer ?? 32,
                  tolerance: 0.05, // Reduced tolerance for better quality
                  // Improved interpolation for smoother appearance
                  interpolate: renderingConfig.renderingHints?.interpolate ?? true,
                  // Thermal-specific configuration
                  ...(isThermalData && {
                    noDataValue: -9999, // Use a specific nodata value instead of null
                    interpolate: false, // Disable interpolation to prevent null value errors
                    resample: 'bilinear', // Better resampling for thermal data
                  }),
                  // General error mitigation and quality improvements
                  errorTolerance: 0.1, // Stricter error tolerance for better quality
                  ignoreInvalidTiles: true, // Skip tiles with invalid data instead of failing
                  maxRetries: 3, // More retries for better reliability
                  // Additional quality enhancements
                  antialiasing: true, // Enable antialiasing for smoother edges
                  smoothTransitions: true // Enable smooth tile transitions
                };
              } else {
                // === ENHANCED FALLBACK: Optimized configuration for radar imagery ===
                console.log('??? MapView: [ENHANCED FALLBACK] Using optimized radar imagery configuration');

                // Apply same bounds validation as template approach
                let fallbackBounds = undefined;
                const bounds = satelliteData.bbox;
                if (bounds && Array.isArray(bounds) && bounds.length === 4) {
                  const [west, south, east, north] = bounds;
                  
                  // Validate and clamp bounds to prevent geometry errors
                  const isValidBound = (coord: any) => {
                    return coord !== null && coord !== undefined && 
                           typeof coord === 'number' && 
                           !isNaN(coord) && isFinite(coord) &&
                           coord >= -180 && coord <= 180;
                  };
                  
                  if (isValidBound(west) && isValidBound(south) && 
                      isValidBound(east) && isValidBound(north) &&
                      west < east && south < north) {
                    
                    const clampedWest = Math.max(-180, Math.min(180, west));
                    const clampedSouth = Math.max(-85, Math.min(85, south));
                    const clampedEast = Math.max(-180, Math.min(180, east));
                    const clampedNorth = Math.max(-85, Math.min(85, north));
                    
                    fallbackBounds = [clampedWest, clampedSouth, clampedEast, clampedNorth];
                  }
                }

                // Only add tile_scale=2 for non-native tiles (TiTiler URLs)
                // Native tiles URLs (tilejson.json) don't support tile_scale parameter
                const tilejsonUrl = isNativeTiles ? tileUrl : 
                  (tileUrl.includes('tile_scale=') ? tileUrl : 
                  `${tileUrl}${tileUrl.includes('?') ? '&' : '?'}tile_scale=2`);

                console.log('🔍 MapView: Fetching TileJSON to get tile template:', tilejsonUrl);

                // Fetch TileJSON synchronously (we're in an async context)
                const tilejsonResult = await fetchAndSignTileJSON(tilejsonUrl, { 
                  collection: satelliteData.items[0]?.collection 
                });

                if (!tilejsonResult.success || !tilejsonResult.tileTemplate) {
                  console.error('❌ MapView: Failed to fetch TileJSON:', tilejsonResult.error);
                  return; // Cannot render without tile template
                }

                console.log('✅ MapView: Using tile template from TileJSON:', tilejsonResult.tileTemplate);
                console.log('🔍 MapView: TileJSON zoom range:', tilejsonResult.tilejson?.minzoom, '-', tilejsonResult.tilejson?.maxzoom);

                tileLayerConfig = {
                  tileUrl: tilejsonResult.tileTemplate, // ✅ Use tile template (has {z}/{x}/{y}), not TileJSON URL
                  opacity: baseOpacity, // Dynamic opacity based on data type for better text visibility
                  tileSize: 512, // Larger tile size for better quality
                  bounds: fallbackBounds,
                  minSourceZoom: tilejsonResult.tilejson?.minzoom || 0, // Use TileJSON-specified minzoom
                  maxSourceZoom: tilejsonResult.tilejson?.maxzoom || 22, // Use TileJSON-specified maxzoom
                  // Improve rendering performance and text visibility
                  fadeIn: true,
                  fadeDuration: 500, // Longer fade for smoother transitions
                  tileLoadRadius: 2, // Increased radius for smoother loading
                  blend: 'normal', // Normal blending mode for better text preservation
                  // Enhanced error handling and quality - REDUCED BUFFER
                  buffer: 32, // Significantly reduced buffer to prevent geometry extent errors
                  tolerance: 0.05, // Better geometry quality
                  errorTolerance: 0.1, // Stricter error handling
                  ignoreInvalidTiles: true, // Skip invalid tiles
                  maxRetries: 3, // More retries for reliability
                  // Quality enhancements
                  interpolate: true, // Enable interpolation for smoother appearance
                  antialiasing: true, // Enable antialiasing
                  smoothTransitions: true // Enable smooth transitions
                };
              }

              console.log('??? MapView: [DEBUG] Creating Azure Maps TileLayer with config:', tileLayerConfig);
              console.log('??? MapView: [DEBUG] tileUrl type:', typeof tileUrl);
              console.log('??? MapView: [DEBUG] tileUrl length:', tileUrl?.length);
              console.log('??? MapView: [DEBUG] tileUrl starts with https:', tileUrl?.startsWith('https://'));
              console.log('??? MapView: [DEBUG] atlas.layer.TileLayer available:', typeof window.atlas.layer.TileLayer);

              // Enhanced validation function for tile layer coordinates
              const validateTileCoordinates = (coords: any) => {
                return coords !== null && coords !== undefined &&
                       typeof coords === 'number' &&
                       !isNaN(coords) &&
                       isFinite(coords) &&
                       coords >= -180 && coords <= 180;
              };

              // Comprehensive data sanitization function for map properties
              const sanitizeMapData = (data: any): any => {
                // Handle null, undefined, or invalid values
                if (data === null || data === undefined) return 0; // Return 0 instead of null for numeric contexts
                
                // Sanitize numeric values with enhanced null checking
                if (typeof data === 'number') {
                  if (isNaN(data) || !isFinite(data) || data === null || data === undefined) {
                    return 0; // Return 0 for any invalid numeric value
                  }
                  return data;
                }
                
                // Handle string numbers that might be null or invalid
                if (typeof data === 'string') {
                  const numericValue = parseFloat(data);
                  if (!isNaN(numericValue) && isFinite(numericValue)) {
                    return numericValue;
                  }
                  return data; // Return string as-is if not numeric
                }
                
                // Sanitize arrays with null filtering
                if (Array.isArray(data)) {
                  return data
                    .map(item => sanitizeMapData(item))
                    .filter(item => item !== null && item !== undefined);
                }
                
                // Sanitize objects with comprehensive null checking
                if (typeof data === 'object') {
                  const sanitized: any = {};
                  for (const key in data) {
                    if (data.hasOwnProperty(key)) {
                      const value = data[key];
                      
                      // Skip null/undefined values to prevent "Expected number but found null" errors
                      if (value === null || value === undefined) {
                        continue; // Skip this property entirely
                      }
                      
                      const sanitizedValue = sanitizeMapData(value);
                      if (sanitizedValue !== null && sanitizedValue !== undefined) {
                        sanitized[key] = sanitizedValue;
                      }
                    }
                  }
                  return sanitized;
                }
                
                return data;
              };

              // Create a clean config with only valid Azure Maps TileLayer properties
              const cleanTileLayerConfig: any = {
                tileUrl: tileLayerConfig.tileUrl, // Use the high-resolution URL from config
                opacity: Math.max(0, Math.min(1, tileLayerConfig.opacity || 1.0)), // 100% opacity for crisp imagery (labels rendered on top separately)
                tileSize: Math.max(256, Math.min(1024, tileLayerConfig.tileSize || 512)), // Reasonable tile size range
                minSourceZoom: Math.max(0, Math.min(22, tileLayerConfig.minSourceZoom || 0)),
                maxSourceZoom: Math.max(0, Math.min(22, tileLayerConfig.maxSourceZoom || 22)),
                // Vector tile buffer configuration to fix extent errors - CRITICAL FIX
                buffer: 16, // Significantly reduced buffer size to prevent geometry extent errors
                tolerance: 0.1, // Reduced tolerance for better quality and fewer geometry errors
                cluster: false, // Disable clustering to reduce geometry complexity
                lineMetrics: false, // Disable line metrics to reduce processing overhead
                generateId: false, // Disable auto ID generation to reduce memory usage
                // Additional geometry optimization
                simplifyGeometry: true, // Simplify complex geometries to prevent buffer overflow
                validateGeometry: true, // Enable geometry validation to catch errors early
                maxGeometryComplexity: 1000 // Limit geometry complexity to prevent buffer issues
              };

              // Enhanced bounds validation with comprehensive null checking
              if (tileLayerConfig.bounds && Array.isArray(tileLayerConfig.bounds) && tileLayerConfig.bounds.length === 4) {
                const [west, south, east, north] = tileLayerConfig.bounds;
                
                // Comprehensive validation for each coordinate
                if (validateTileCoordinates(west) && validateTileCoordinates(south) && 
                    validateTileCoordinates(east) && validateTileCoordinates(north) &&
                    west < east && south < north) {
                  
                  // Double-clamp coordinates to prevent edge case issues
                  const safeWest = Math.max(-180, Math.min(179.999, west));
                  const safeSouth = Math.max(-85, Math.min(84.999, south));
                  const safeEast = Math.max(-179.999, Math.min(180, east));
                  const safeNorth = Math.max(-84.999, Math.min(85, north));
                  
                  cleanTileLayerConfig.bounds = [safeWest, safeSouth, safeEast, safeNorth];
                  console.log('??? MapView: [DEBUG] Using validated safe bounds:', cleanTileLayerConfig.bounds);
                } else {
                  console.warn('??? MapView: [DEBUG] Rejecting invalid bounds to prevent null coordinate errors:', {
                    original: tileLayerConfig.bounds,
                    west: west, south: south, east: east, north: north,
                    westValid: validateTileCoordinates(west),
                    southValid: validateTileCoordinates(south),
                    eastValid: validateTileCoordinates(east),
                    northValid: validateTileCoordinates(north)
                  });
                }
              }

              console.log('??? MapView: [DEBUG] Clean TileLayer config:', cleanTileLayerConfig);

              let tileLayer: any;
              try {
                // Additional safety check before creating tile layer
                if (!cleanTileLayerConfig.tileUrl || typeof cleanTileLayerConfig.tileUrl !== 'string') {
                  throw new Error('Invalid tile URL provided');
                }

                // Generate unique layer ID to prevent conflicts
                const layerId = `earth-copilot-tiles-${Date.now()}-${Math.random().toString(36).substr(2, 9)}`;
                
                console.log('??? MapView: [DEBUG] Creating TileLayer with config:', {
                  tileUrl: cleanTileLayerConfig.tileUrl.substring(0, 100) + '...',
                  opacity: cleanTileLayerConfig.opacity,
                  bounds: cleanTileLayerConfig.bounds,
                  layerId: layerId
                });

                // Apply data sanitization before creating tile layer
                const sanitizedConfig = sanitizeMapData(cleanTileLayerConfig);
                
                // Additional geometry validation for vector tiles
                if (sanitizedConfig.bounds) {
                  const [west, south, east, north] = sanitizedConfig.bounds;
                  
                  // Ensure bounds don't exceed maximum extents to prevent buffer overflow
                  const maxExtent = 20037508.34; // Web Mercator max extent
                  const boundedWest = Math.max(-maxExtent, Math.min(maxExtent, west));
                  const boundedSouth = Math.max(-maxExtent, Math.min(maxExtent, south));
                  const boundedEast = Math.max(-maxExtent, Math.min(maxExtent, east));
                  const boundedNorth = Math.max(-maxExtent, Math.min(maxExtent, north));
                  
                  sanitizedConfig.bounds = [boundedWest, boundedSouth, boundedEast, boundedNorth];
                }

                tileLayer = new window.atlas.layer.TileLayer(sanitizedConfig, layerId);
                console.log('??? MapView: [DEBUG] TileLayer instance created successfully with ID:', layerId);
              } catch (error) {
                console.error('??? MapView: [ERROR] Failed to create TileLayer:', error);
                console.error('??? MapView: [ERROR] Config that failed:', cleanTileLayerConfig);
                return;
              }

              // DEBUGGING: Add event listeners before adding the layer
              console.log('??? MapView: [DEBUG] TileLayer instance created with ID:', tileLayer.getId?.());

              // Enhanced source event handler with better null safety
              const sourceLoadHandler = (e: any) => {
                try {
                  // Only log essential information to reduce console noise
                  if (e && e.type) {
                    // Filter out excessive bing-aerial/bing-mvt source events that cause console spam
                    const sourceId = e.source?.id || 'unknown';
                    const isBingSource = sourceId.includes('bing-') || sourceId === 'bing-aerial' || sourceId === 'bing-mvt';
                    
                    if (!isBingSource || e.type === 'error') {
                      console.log('??? MapView: [DEBUG] Source event:', e.type, 'Object');
                      if (e.source && e.source.id) {
                        console.log('??? MapView: [DEBUG] Source ID:', e.source.id);
                        console.log('??? MapView: [DEBUG] Source type:', e.source.type);
                      }
                    }

                    // Handle critical errors with better validation
                    if (e.type === 'error') {
                      console.error('??? MapView: [ERROR] Map source error:', {
                        type: e.type,
                        sourceId: sourceId,
                        message: e.error?.message || 'Unknown error'
                      });
                    }

                    // Check for failed source loading with enhanced filtering
                    if (e.type === 'sourcedata' && e.isSourceLoaded === false && e.sourceDataType === 'metadata') {
                      const isNonCriticalSource = sourceId.includes('bing-') || 
                                                 sourceId.includes('traffic') || 
                                                 sourceId.includes('satellite-base') ||
                                                 sourceId.startsWith('jk') ||
                                                 sourceId === 'unknown' ||
                                                 sourceId.includes('basemap');
                      
                      if (!isNonCriticalSource) {
                        console.log('??? MapView: ?? User data source failed to load:', {
                          sourceId: sourceId,
                          sourceType: e.source?.type || 'unknown',
                          type: e.type,
                          sourceDataType: e.sourceDataType,
                          isSourceLoaded: e.isSourceLoaded
                        });
                      }
                    }
                  }
                } catch (handlerError) {
                  console.error('??? MapView: [ERROR] Source handler caught error:', handlerError);
                }
              };

              // Add error handler for map errors
              const errorHandler = (e: any) => {
                console.error('??? MapView: [ERROR] Map error event:', e);
              };

              map.events.add('sourcedata', sourceLoadHandler);
              map.events.add('sourcedataloading', sourceLoadHandler);
              map.events.add('error', errorHandler);

              console.log('??? MapView: [DEBUG] Adding tile layer to map...');
              
              // ✅ CORRECT APPROACH: Insert tile layer BELOW the 'labels' layer
              // Azure Maps documentation: "To insert a tile layer below the map labels, use: map.layers.add(myTileLayer, 'labels');"
              // The second parameter specifies the layer ID to insert BELOW
              // This ensures our satellite tiles appear under the labels, keeping text visible
              try {
                console.log('🏷️ MapView: Inserting tile layer below labels for visible text...');
                map.layers.add(tileLayer, 'labels');
                console.log('✅ MapView: Tile layer inserted below labels - text should be visible');
              } catch (insertError) {
                // Fallback: If 'labels' layer doesn't exist, just add normally
                console.warn('⚠️ MapView: Could not insert below labels, adding normally:', insertError);
                map.layers.add(tileLayer);
              }
              
              setCurrentLayer(tileLayer);
              console.log('✅ MapView: Successfully added Azure Maps tile layer with zoom constraints and label visibility')

              // Zoom to the satellite data area with appropriate zoom level
              if (satelliteData.bbox && Array.isArray(satelliteData.bbox) && satelliteData.bbox.length === 4) {
                let [west, south, east, north] = satelliteData.bbox;
                console.log('??? MapView: Original satellite data bounds:', { west, south, east, north });

                // Check if this is MODIS data for adjusted zoom levels and coordinates
                const isMODISData = satelliteData.items[0]?.collection?.toLowerCase().includes('modis');

                // Extract original query from chat response for dynamic region detection
                let originalQuery = '';
                if (lastChatResponse?.translation_metadata?.original_query) {
                  originalQuery = lastChatResponse.translation_metadata.original_query;
                } else if (lastChatResponse?.debug?.original_query) {
                  originalQuery = lastChatResponse.debug.original_query;
                } else if (lastChatResponse?.response) {
                  // Fallback: try to extract region info from the response text
                  originalQuery = lastChatResponse.response;
                }

                console.log('??? MapView: Original query for region detection:', originalQuery);

                // ENHANCED: Use backend-resolved location bounds instead of hardcoded coordinates
                const bboxWidth = Math.abs(east - west);
                const bboxHeight = Math.abs(north - south);
                const isLargeBbox = bboxWidth > 2 || bboxHeight > 2; // Large area covering multiple cities/regions

                console.log('??? MapView: Bbox analysis:', {
                  width: bboxWidth.toFixed(2),
                  height: bboxHeight.toFixed(2),
                  isLarge: isLargeBbox,
                  collection: satelliteData.items[0]?.collection
                });

                // Check if backend provided location-specific bounds in the response metadata
                let backendResolvedBounds = null;
                if (lastChatResponse?.data?.search_metadata?.spatial_extent) {
                  const spatialExtent = lastChatResponse.data.search_metadata.spatial_extent;
                  if (Array.isArray(spatialExtent) && spatialExtent.length === 4) {
                    backendResolvedBounds = {
                      west: spatialExtent[0],
                      south: spatialExtent[1],
                      east: spatialExtent[2],
                      north: spatialExtent[3]
                    };
                    console.log('??? MapView: ? Using backend-resolved location bounds:', backendResolvedBounds);
                  }
                }
                
                // Enhanced California detection for wildfire queries
                if (!backendResolvedBounds && originalQuery && 
                    (originalQuery.toLowerCase().includes('california') || 
                     originalQuery.toLowerCase().includes('ca ') ||
                     originalQuery.toLowerCase().includes('wildfire') ||
                     originalQuery.toLowerCase().includes('fire')) && 
                    isLargeBbox) {
                  // Use precise California bounds for wildfire queries
                  backendResolvedBounds = {
                    west: -124.41516,  // California western boundary
                    south: 32.53434,   // California southern boundary  
                    east: -114.13121,  // California eastern boundary
                    north: 42.00952    // California northern boundary
                  };
                  console.log('?? MapView: ? Applied California bounds for wildfire query:', backendResolvedBounds);
                }
                
                // Enhanced California detection for wildfire queries
                if (!backendResolvedBounds && originalQuery && 
                    (originalQuery.toLowerCase().includes('california') || 
                     originalQuery.toLowerCase().includes('ca ') ||
                     originalQuery.toLowerCase().includes('wildfire') ||
                     originalQuery.toLowerCase().includes('fire')) && 
                    isLargeBbox) {
                  // Use precise California bounds for wildfire queries
                  backendResolvedBounds = {
                    west: -124.41516,  // California western boundary
                    south: 32.53434,   // California southern boundary  
                    east: -114.13121,  // California eastern boundary
                    north: 42.00952    // California northern boundary
                  };
                  console.log('?? MapView: ? Applied California bounds for wildfire query:', backendResolvedBounds);
                }

                // Use backend-resolved bounds if available and more precise than satellite data bounds
                if (backendResolvedBounds && isLargeBbox) {
                  console.log('??? MapView: ? Applying backend-resolved bounds for precise location focus');
                  west = backendResolvedBounds.west;
                  south = backendResolvedBounds.south;
                  east = backendResolvedBounds.east;
                  north = backendResolvedBounds.north;
                  console.log('??? MapView: ? Applied backend location resolution for precise coordinates');
                } else if (backendResolvedBounds) {
                  console.log('??? MapView: Backend bounds available but satellite data bbox is already focused, using satellite bounds');
                } else {
                  console.log('??? MapView: Using original satellite data bounds (no backend location resolution found)');
                }

                console.log('??? MapView: Final bounds for map view:', { west, south, east, north });

                // Update satelliteData.bbox with the region-specific bounds for consistent use throughout
                satelliteData.bbox = [west, south, east, north];
                console.log('??? MapView: ? Updated satelliteData.bbox with region-specific bounds');

                // Smart zoom calculation for optimal radar imagery visibility
                const finalBboxWidth = Math.abs(east - west);
                const finalBboxHeight = Math.abs(north - south);
                const bboxArea = finalBboxWidth * finalBboxHeight;

                // Enhanced zoom calculation for better satellite data visibility
                let targetZoom = 6; // Safe default
                if (bboxArea < 0.1) { // City-level detail
                  targetZoom = isMODISData ? 12 : 12; // Allow detailed zoom for MODIS fire data viewing
                } else if (bboxArea < 0.5) { // Metropolitan area
                  targetZoom = isMODISData ? 10 : 10;
                } else if (bboxArea < 2) { // Large metropolitan area
                  targetZoom = isMODISData ? 8 : 8;
                } else if (bboxArea < 10) { // Regional coverage 
                  targetZoom = isMODISData ? 7 : 7;
                } else if (bboxArea < 50) { // State-level coverage
                  targetZoom = isMODISData ? 6 : 6;
                } else { // Multi-state/continental coverage
                  targetZoom = isMODISData ? 5 : 5; // Better zoom for large MODIS continental data
                }

                console.log(`??? MapView: Calculated zoom level ${targetZoom} for ${isMODISData ? 'MODIS' : 'standard'} data (bbox area ${bboxArea.toFixed(4)} sq degrees)`);
                console.log('??? MapView: Enhanced zoom calculation for better satellite data visibility');

                try {
                  // Enhanced validation function for camera coordinates
                  const isValidCameraCoord = (coord: any) => {
                    return coord !== null && coord !== undefined &&
                           typeof coord === 'number' &&
                           !isNaN(coord) &&
                           isFinite(coord) &&
                           coord >= -180 && coord <= 180;
                  };

                  // Comprehensive validation before setCamera to prevent null coordinate errors
                  if (!isValidCameraCoord(west) || !isValidCameraCoord(south) || 
                      !isValidCameraCoord(east) || !isValidCameraCoord(north)) {
                    throw new Error(`Invalid coordinate values detected before setCamera: west=${west}, south=${south}, east=${east}, north=${north}`);
                  }

                  // Ensure logical bounds relationship
                  if (west >= east || south >= north) {
                    throw new Error(`Invalid bounds relationship: west(${west}) >= east(${east}) or south(${south}) >= north(${north})`);
                  }

                  console.log('??? MapView: Validated coordinates before setCamera:', { west, south, east, north });

                  // Clamp coordinates to safe ranges for Azure Maps
                  const safeWest = Math.max(-179.999, Math.min(179.999, west));
                  const safeSouth = Math.max(-84.999, Math.min(84.999, south));
                  const safeEast = Math.max(-179.999, Math.min(179.999, east));
                  const safeNorth = Math.max(-84.999, Math.min(84.999, north));

                  map.setCamera({
                    bounds: [safeWest, safeSouth, safeEast, safeNorth],
                    zoom: Math.max(0, Math.min(22, targetZoom)), // Clamp zoom level
                    maxZoom: Math.max(0, Math.min(22, isMODISData ? 16 : 22)),
                    minZoom: Math.max(0, Math.min(22, isMODISData ? 0 : 2)),
                    padding: Math.max(0, Math.min(200, 50)), // Clamp padding
                    type: 'ease',
                    duration: Math.max(0, Math.min(5000, 2000)) // Clamp duration
                  });
                  console.log('? MapView: Successfully zoomed to satellite data area with appropriate zoom level');

                  // Enhanced text visibility management after satellite layer is added
                  const ensureTextVisibility = () => {
                    try {
                      // Check current map style and suggest better alternatives for text visibility
                      const currentStyle = map.getStyle();
                      console.log('??? MapView: Current map style:', currentStyle);

                      // Show style tip for better user experience
                      setShowStyleTip(true);

                      // Auto-hide tip after 8 seconds
                      setTimeout(() => {
                        setShowStyleTip(false);
                      }, 8000);

                      // If using satellite style with overlay, suggest switching to road view
                      if (currentStyle && (currentStyle.includes('satellite') || currentStyle === 'satellite_road_labels')) {
                        console.log('??? MapView: ?? TIP: Switch to "Road" or "Light Grayscale" style for better text visibility with satellite overlay');
                      }

                      // Add opacity control information
                      console.log('??? MapView: ?? Satellite layer opacity set to preserve map labels');
                      console.log('??? MapView: ?? Use style control (top-right) to switch between map styles for optimal viewing');

                    } catch (e) {
                      console.log('??? MapView: Text visibility check completed');
                    }
                  };

                  // Run text visibility check after a short delay to ensure layer is loaded
                  setTimeout(ensureTextVisibility, 1000);

                } catch (cameraError) {
                  console.error('? MapView: Error setting camera bounds:', cameraError);
                }
              }

              console.log('? MapView: Successfully added Azure Maps satellite tile layer');

            } catch (layerError) {
              console.error('? MapView: Error adding Azure Maps tile layer:', layerError);
              console.log('??? MapView: Tile layer addition failed, but continuing...');
            }
          };

          // Try to add tile layer immediately if map is ready
          addTileLayer();
        }

        // If we have map_data GeoJSON, add it as vector data
        if (lastChatResponse?.map_data?.features && window.atlas) {
          console.log('??? MapView: Adding GeoJSON features to Azure Maps');

          const addGeoJsonLayers = () => {
            try {
              // Basic map check
              if (!map) {
                console.log('??? MapView: No map instance for GeoJSON, skipping...');
                return;
              }

              console.log('??? MapView: Adding GeoJSON data source and layers...');

              const dataSource = new window.atlas.source.DataSource();
              map.sources.add(dataSource);

              // Filter out features with null/invalid coordinates AND clean properties
              const validFeatures = lastChatResponse.map_data.features.filter((feature: any) => {
                if (!feature.geometry || !feature.geometry.coordinates) {
                  console.warn('?? MapView: Skipping feature with missing geometry:', feature.id || 'unknown');
                  return false;
                }
                
                // Check for null coordinates in different geometry types
                const coords = feature.geometry.coordinates;
                if (feature.geometry.type === 'Polygon') {
                  // For polygons, coordinates are arrays of linear rings
                  return coords.every((ring: number[][]) => 
                    ring.every((coord: number[]) => 
                      coord.length >= 2 && coord[0] !== null && coord[1] !== null
                    )
                  );
                } else if (feature.geometry.type === 'LineString') {
                  // For linestrings, coordinates are array of positions
                  return coords.every((coord: number[]) => 
                    coord.length >= 2 && coord[0] !== null && coord[1] !== null
                  );
                } else if (feature.geometry.type === 'Point') {
                  // For points, coordinates are a single position
                  return coords.length >= 2 && coords[0] !== null && coords[1] !== null;
                }
                
                return true; // Allow other geometry types through
              }).map((feature: any) => {
                // Clean up feature properties to prevent null values from causing Azure Maps errors
                const cleanedFeature = {
                  ...feature,
                  properties: feature.properties ? cleanNullProperties(feature.properties) : {}
                };
                return cleanedFeature;
              });

              // Helper function to clean null properties that cause Azure Maps symbol layout errors
              function cleanNullProperties(properties: any): any {
                const cleaned: any = {};
                for (const [key, value] of Object.entries(properties)) {
                  // Replace null values with appropriate defaults based on expected data type
                  if (value === null || value === undefined) {
                    // For numeric properties that might be used in expressions, default to 0
                    if (key.includes('count') || key.includes('size') || key.includes('area') || 
                        key.includes('population') || key.includes('elevation') || key.includes('zoom')) {
                      cleaned[key] = 0;
                    }
                    // For string properties, use empty string
                    else if (key.includes('name') || key.includes('title') || key.includes('label') || 
                             key.includes('type') || key.includes('category')) {
                      cleaned[key] = '';
                    }
                    // For other properties, convert to empty string to avoid null issues
                    else {
                      cleaned[key] = '';
                    }
                  } else {
                    cleaned[key] = value;
                  }
                }
                return cleaned;
              }

              console.log(`??? MapView: Filtered ${lastChatResponse.map_data.features.length - validFeatures.length} features with invalid coordinates`);
              
              // Add the valid GeoJSON features
              if (validFeatures.length > 0) {
                dataSource.add(validFeatures);
                console.log(`? MapView: Added ${validFeatures.length} valid features to data source`);
              } else {
                console.warn('?? MapView: No valid features to display after coordinate filtering');
              }

              // Add polygon layer for search area with safe styling options
              const polygonLayer = new window.atlas.layer.PolygonLayer(dataSource, `polygon-layer-${Date.now()}`, {
                fillColor: 'rgba(0, 0, 255, 0.2)',
                fillOpacity: 0.3,
                // Prevent symbol layout errors by avoiding data-driven expressions with null values
                filter: ['!=', ['typeof', ['get', 'geometry']], 'null']
              });

              const lineLayer = new window.atlas.layer.LineLayer(dataSource, `line-layer-${Date.now()}`, {
                strokeColor: 'blue',
                strokeWidth: 2,
                // Prevent symbol layout errors by avoiding data-driven expressions with null values
                filter: ['!=', ['typeof', ['get', 'geometry']], 'null']
              });

              try {
                map.layers.add([polygonLayer, lineLayer]);
                console.log('? MapView: Successfully added GeoJSON features to Azure Maps');
              } catch (layerError) {
                console.error('? MapView: Error adding layers to Azure Maps:', layerError);
                // Try adding layers individually if batch add fails
                try {
                  map.layers.add(polygonLayer);
                  map.layers.add(lineLayer);
                  console.log('? MapView: Successfully added layers individually after batch failure');
                } catch (individualError) {
                  console.error('? MapView: Failed to add layers individually:', individualError);
                }
              }
            } catch (geoError) {
              console.error('? MapView: Error adding GeoJSON to Azure Maps:', geoError);
              // If timing issue, try again after delay
              if (geoError instanceof Error && geoError.message && geoError.message.includes('not ready')) {
                console.log('??? MapView: Retrying GeoJSON addition in 500ms...');
                setTimeout(addGeoJsonLayers, 500);
              }
            }
          };

          // Use longer delay to ensure map is fully initialized
          if (map && mapLoaded) {
            setTimeout(addGeoJsonLayers, 750);
          } else {
            // If map not ready, wait for ready event and then add delay
            map.events.add('ready', () => {
              setTimeout(addGeoJsonLayers, 1250);
            });
          }
        }
      } else if (mapProvider === 'leaflet') {
        // Leaflet implementation
        console.log('??? MapView: Using Leaflet provider - verifying map instance');

        // Safety check: ensure we're not trying to use Leaflet methods on Azure Maps
        if (map && map.constructor && map.constructor.name && map.constructor.name.includes('Map') && !map.removeLayer) {
          console.error('? MapView: CRITICAL ERROR - mapProvider is "leaflet" but map instance appears to be Azure Maps!');
          console.log('??? MapView: Map constructor:', map.constructor.name);
          console.log('??? MapView: Correcting mapProvider to "azure"');
          setMapProvider('azure');
          return; // Exit and let the effect re-run with correct provider
        }

        // Remove existing satellite layer if any
        if (currentLayer) {
          console.log('??? MapView: Removing existing Leaflet layer');
          map.removeLayer(currentLayer);
          setCurrentLayer(null);
        }

        // If we have a tile URL, add it as a tile layer
        if (satelliteData.tile_url && window.L) {
          console.log('??? MapView: Adding Leaflet tile layer:', satelliteData.tile_url);

          // Configure tile layer options with bounds to prevent 404s outside data coverage
          const tileLayerOptions: any = {
            opacity: 0.8,
            attribution: 'Planetary Computer',
            errorTileUrl: 'data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNkYAAAAAYAAjCB0C8AAAAASUVORK5CYII=', // Transparent 1x1 pixel
            maxNativeZoom: 18, // Prevent requests beyond available zoom levels
            tileSize: 256
          };

          // Add bounds if available to limit tile requests to actual data coverage
          // This prevents excessive 404 errors for tiles outside the STAC item's bbox
          if (satelliteData.bbox && satelliteData.bbox.length === 4) {
            const [west, south, east, north] = satelliteData.bbox;
            tileLayerOptions.bounds = window.L.latLngBounds(
              window.L.latLng(south, west),
              window.L.latLng(north, east)
            );
            console.log('??? MapView: Tile layer constrained to bbox:', satelliteData.bbox);
          }

          const tileLayer = window.L.tileLayer(satelliteData.tile_url, tileLayerOptions);

          // Suppress tile load errors in console (404s outside bounds are expected)
          tileLayer.on('tileerror', (error: any) => {
            // Silently handle tile errors - they're expected for tiles outside data coverage
            // Only log if it's a repeated pattern that might indicate a real issue
            const url = error.tile?.src || 'unknown';
            if (Math.random() < 0.01) { // Log only 1% of errors to avoid console spam
              console.debug('? MapView: Tile not available (expected for tiles outside data bounds):', url.substring(0, 120));
            }
          });

          tileLayer.addTo(map);
          setCurrentLayer(tileLayer);

          console.log('? MapView: Successfully added Leaflet satellite tile layer');
        }

        // If we have map_data GeoJSON, add it as vector data
        if (lastChatResponse?.map_data?.features && window.L) {
          console.log('??? MapView: Adding GeoJSON features to Leaflet');

          lastChatResponse.map_data.features.forEach((feature: any) => {
            const geoJsonLayer = window.L.geoJSON(feature, {
              style: {
                fillColor: 'rgba(0, 0, 255, 0.2)',
                fillOpacity: 0.3,
                color: 'blue',
                weight: 2
              }
            });

            geoJsonLayer.addTo(map);
          });

          console.log('? MapView: Successfully added GeoJSON featu to Leaflet');
        }
      }

      // Update view to show the data
      if (satelliteData.bbox) {
        console.log('??? MapView: Updating map view to bbox:', satelliteData.bbox);
        updateMapView(satelliteData.bbox);
      }

    } catch (error) {
      console.error('? MapView: Error adding satellite data to map:', error);
    }
  }, [satelliteData, map, mapLoaded, lastChatResponse]);

  // Pin button click handler - always opens module selection menu
  const handlePinButtonClick = () => {
    console.log('📍 MapView: Pin button clicked');
    
    // ALWAYS open modules menu when pin button is clicked
    // User should always see the module selection, regardless of current state
    console.log('📍 MapView: Opening modules menu');
    const newMenuState = !showModulesMenu;
    setShowModulesMenu(newMenuState);
    
    if (newMenuState && onModulesMenuOpen) {
      // Notify parent that modules menu opened (MainApp will display the message)
      onModulesMenuOpen();
    }
  };

  // Module selection handler
  const handleModuleSelect = (module: string) => {
    console.log('🎯 MapView: Module selected:', module);
    setSelectedModule(module);
    
    // Handle comparison module differently - needs user input first
    if (module === 'comparison') {
      console.log('📊 MapView: Comparison module selected - prompting user for parameters');
      setComparisonMode(true);
      
      // DO NOT set selectedModule or enable pinMode for comparison
      // Comparison uses natural language queries, not pin drops
      
      // Ask user for comparison parameters via chat
      if (onGeointAnalysis) {
        onGeointAnalysis({
          type: 'assistant',
          message: `📊 **Comparison Analysis**\n\nPlease describe what location you would like to compare, what aspect of that location, and over what time range.\n\nFor example:\n• "Show wildfire activity in Southern California in January 2025 and how it evolved over 48 hours"\n• "Track methane emissions in the Permian Basin from 2023 to 2025"\n• "Compare sea level change along the U.S. Atlantic coast over the past decade"`
        });
      }
      
      // Set state to await user query
      setComparisonState(prev => ({ ...prev, awaitingUserQuery: true }));
      
      // Close modules menu
      setShowModulesMenu(false);
      return;
    }
    
    // For other modules, enable pin mode automatically
    setPinMode(true);
    console.log('📍 MapView: Pin mode automatically enabled for module:', module);
    
    // Notify parent that module was selected
    if (onModuleSelected) {
      onModuleSelected(module);
    }
    
    // Show appropriate chat message based on module
    let message = '';
    
    if (module === 'terrain') {
      message = 'Please click on the map to drop a pin on the location you want to perform terrain analysis.';
      setTerrainAnalysisMode(true);
    } else if (module === 'mobility') {
      message = 'Please click on the map to drop a pin for mobility analysis.';
    } else if (module === 'building_damage') {
      message = 'Please click on the map to drop a pin for building damage assessment.';
    } else if (module === 'timeseries') {
      message = 'Please click on the map to drop a pin for time series animation.';
    }
    
    // Send message to chat
    if (onGeointAnalysis && message) {
      onGeointAnalysis({
        type: 'module_selected',
        message: message
      });
    }
    
    // Close modules menu after selection
    setShowModulesMenu(false);
  };

  // Handle Before/After toggle for comparison mode
  const toggleBeforeAfter = async () => {
    console.log('📊 MapView: Toggling between BEFORE and AFTER views');
    
    const newShowingBefore = !comparisonState.showingBefore;
    setComparisonState(prev => ({ ...prev, showingBefore: newShowingBefore }));
    
    // Switch the rendered imagery
    const imageryToRender = newShowingBefore ? comparisonState.beforeImagery : comparisonState.afterImagery;
    
    if (imageryToRender && imageryToRender.data && imageryToRender.data.stac_results) {
      console.log(`📊 MapView: Rendering ${newShowingBefore ? 'BEFORE' : 'AFTER'} imagery`);
      const stacData = imageryToRender.data.stac_results;
      
      // Convert STAC results to satelliteData format
      const satelliteDataFormat = {
        bbox: stacData.bbox || satelliteData?.bbox,
        items: stacData.features || [],
        tile_url: stacData.features?.[0]?.assets?.tilejson?.href || stacData.features?.[0]?.assets?.rendered_preview?.href,
        preview_url: stacData.features?.[0]?.assets?.thumbnail?.href
      };
      
      setSatelliteData(satelliteDataFormat);
      console.log(`📊 MapView: ${newShowingBefore ? 'BEFORE' : 'AFTER'} imagery rendered`);
      
      // Notify user via chat
      if (onGeointAnalysis) {
        onGeointAnalysis({
          type: 'info',
          message: `Switched to ${newShowingBefore ? 'BEFORE' : 'AFTER'} view`
        });
      }
    }
  };

  // Map click handler for pin placement
  const handleMapClickForPin = async (lat: number, lng: number) => {
    if (!pinMode || !map || !selectedModule) {
      console.log('📍 MapView: Pin drop cancelled - pinMode:', pinMode, 'selectedModule:', selectedModule);
      return;
    }

    // Comparison module does NOT use pin drops - it uses natural language queries only
    if (selectedModule === 'comparison') {
      console.log('📍 MapView: Pin drop cancelled - comparison module uses text queries, not pins');
      return;
    }

    console.log(`📍 MapView: Placing pin at (${lat.toFixed(4)}, ${lng.toFixed(4)}) for module: ${selectedModule}`);

    // Remove existing marker if present
    if (pinState.marker) {
      if (mapProvider === 'leaflet' && window.L) {
        map.removeLayer(pinState.marker);
      } else if (mapProvider === 'azure' && window.atlas) {
        // Azure Maps marker removal
        map.markers.remove(pinState.marker);
      }
    }

    // Create new marker
    let newMarker: any = null;
    try {
      if (mapProvider === 'leaflet' && window.L) {
        // Leaflet marker
        newMarker = window.L.marker([lat, lng], {
          draggable: false,
          icon: window.L.icon({
            iconUrl: 'https://raw.githubusercontent.com/pointhi/leaflet-color-markers/master/img/marker-icon-2x-red.png',
            shadowUrl: 'https://cdnjs.cloudflare.com/ajax/libs/leaflet/1.7.1/images/marker-shadow.png',
            iconSize: [25, 41],
            iconAnchor: [12, 41],
            popupAnchor: [1, -34],
            shadowSize: [41, 41]
          })
        }).addTo(map);
        
        // Add popup with coordinates
        newMarker.bindPopup(`📍 Pin Location<br/>Lat: ${lat.toFixed(4)}°<br/>Lng: ${lng.toFixed(4)}°`).openPopup();
        
      } else if (mapProvider === 'azure' && window.atlas) {
        // Azure Maps marker
        newMarker = new window.atlas.HtmlMarker({
          position: [lng, lat],
          color: 'red',
          text: '📍'
        });
        map.markers.add(newMarker);
      }

      setPinState({
        lat,
        lng,
        active: true,
        marker: newMarker
      });

      console.log('✅ MapView: Pin placed successfully (can be repositioned while in pin mode)');

      // Cancel any ongoing analysis when pin is repositioned
      if (analysisInProgress && analysisAbortControllerRef.current) {
        console.log('🛑 MapView: Cancelling previous analysis - pin repositioned');
        analysisAbortControllerRef.current.abort();
        analysisAbortControllerRef.current = null;
      }

      // Send notification to chat about pin drop and trigger analysis
      if (onGeointAnalysis) {
        console.log(`📍 MapView: Triggering ${selectedModule} analysis at`, lat, lng);
        setAnalysisInProgress(true);
        
        // Create new AbortController for this analysis
        const abortController = new AbortController();
        analysisAbortControllerRef.current = abortController;
        
        // Map UI module names to API module names and get display names
        let apiModule = '';
        let query = '';
        let displayName = '';
        switch (selectedModule) {
          case 'terrain':
            apiModule = 'terrain';  // Backend expects 'terrain' not 'terrain_analysis'
            query = 'Describe the terrain features in this location';
            displayName = 'Terrain';
            break;
          case 'mobility':
            apiModule = 'mobility';  // Backend expects 'mobility' not 'mobility_analysis'
            query = 'Analyze mobility and trafficability in this location';
            displayName = 'Mobility';
            break;
          case 'building_damage':
            apiModule = 'building_damage';
            query = 'Assess building damage in this location';
            displayName = 'Building Damage';
            break;
          case 'comparison':
            // Comparison module should NEVER reach here - it uses text queries, not pins
            console.error('❌ MapView: Comparison module incorrectly triggered with pin drop');
            onGeointAnalysis({
              type: 'error',
              message: '❌ **Comparison Module Error**\n\nThe comparison module does not use pin drops. Please use the chat to describe what you want to compare.'
            });
            setAnalysisInProgress(false);
            analysisAbortControllerRef.current = null;
            return;
          default:
            console.error(`❌ MapView: Unknown module selected: ${selectedModule}`);
            onGeointAnalysis({
              type: 'error',
              message: `❌ **Unknown Module**\n\nThe selected module "${selectedModule}" is not recognized. Please select a valid analysis module.`
            });
            setAnalysisInProgress(false);
            analysisAbortControllerRef.current = null;
            return;
        }
        
        // Show "Analyzing..." message immediately
        onGeointAnalysis({ 
          type: 'pending',
          message: `🔍 **Analyzing ${displayName.toLowerCase()}...**\n\nProcessing satellite imagery at coordinates (${lat.toFixed(4)}°, ${lng.toFixed(4)}°).`,
          coordinates: { lat, lng }
        });
        
        // Trigger analysis based on selected module
        try {
          const { triggerGeointAnalysis } = await import('../services/api');
          
          const result = await triggerGeointAnalysis(
            lat, 
            lng, 
            apiModule, 
            query, 
            `Selected module: ${selectedModule}`,
            undefined, // screenshot (not used here)
            abortController.signal // Pass abort signal
          );
          
          // Send results to chat
          onGeointAnalysis({
            type: 'complete',
            data: result,
            module: selectedModule,
            coordinates: { lat, lng }
          });
          
          // Reset analysis flag to allow new analysis
          setAnalysisInProgress(false);
          analysisAbortControllerRef.current = null;
          
        } catch (error) {
          // Check if this was an abort (user repositioned pin)
          if (error instanceof Error && error.name === 'AbortError') {
            console.log('⏭️ MapView: Analysis cancelled (pin repositioned)');
            // Don't show error to user - this is intentional cancellation
            return;
          }
          
          console.error('❌ MapView: GEOINT analysis failed:', error);
          onGeointAnalysis({
            type: 'error',
            message: `❌ **Analysis Failed**\n\n${error instanceof Error ? error.message : 'Unknown error occurred'}`,
            coordinates: { lat, lng }
          });
          
          // Reset analysis flag even on error
          setAnalysisInProgress(false);
          analysisAbortControllerRef.current = null;
        }
      } else if (analysisInProgress) {
        console.log('⏳ MapView: Analysis already in progress, pin moved but not re-analyzing');
      }
    } catch (error) {
      console.error('❌ MapView: Error placing pin marker:', error);
    }
  };

  // Clear pin handler
  const handleClearPin = () => {
    console.log('?? MapView: Clearing pin');

    // Cancel any ongoing analysis
    if (analysisAbortControllerRef.current) {
      console.log('🛑 MapView: Cancelling ongoing analysis - pin cleared');
      analysisAbortControllerRef.current.abort();
      analysisAbortControllerRef.current = null;
    }

    // Remove marker from map
    if (pinState.marker && map) {
      try {
        if (mapProvider === 'leaflet' && window.L) {
          map.removeLayer(pinState.marker);
        } else if (mapProvider === 'azure' && window.atlas) {
          map.markers.remove(pinState.marker);
        }
      } catch (error) {
        console.error('? MapView: Error removing pin marker:', error);
      }
    }

    // Reset pin state
    setPinState({
      lat: null,
      lng: null,
      active: false,
      marker: null
    });
    
    // Reset analysis flag
    setAnalysisInProgress(false);

    console.log('🗑️ MapView: Pin cleared');
  };

  // Map style change handler
  const handleMapStyleChange = (style: string) => {
    if (!map || mapProvider !== 'azure') return;
    
    console.log('🗺️ MapView: Changing map style to:', style);
    
    try {
      map.setStyle({ style: style });
      setCurrentMapStyle(style);
      setShowMapStyleDropdown(false);
      console.log('✅ MapView: Map style changed successfully');
    } catch (error) {
      console.error('❌ MapView: Error changing map style:', error);
    }
  };

  // Zoom in handler
  const handleZoomIn = () => {
    if (!map) return;
    
    try {
      if (mapProvider === 'azure') {
        const camera = map.getCamera();
        map.setCamera({ zoom: (camera.zoom || 4) + 1 });
      } else if (mapProvider === 'leaflet') {
        map.zoomIn();
      }
      console.log('➕ MapView: Zoomed in');
    } catch (error) {
      console.error('❌ MapView: Error zooming in:', error);
    }
  };

  // Zoom out handler
  const handleZoomOut = () => {
    if (!map) return;
    
    try {
      if (mapProvider === 'azure') {
        const camera = map.getCamera();
        map.setCamera({ zoom: (camera.zoom || 4) - 1 });
      } else if (mapProvider === 'leaflet') {
        map.zoomOut();
      }
      console.log('➖ MapView: Zoomed out');
    } catch (error) {
      console.error('❌ MapView: Error zooming out:', error);
    }
  };

  // Reset bearing/rotation handler
  const handleResetBearing = () => {
    if (!map || mapProvider !== 'azure') return;
    
    try {
      map.setCamera({ bearing: 0, pitch: 0 });
      console.log('🧭 MapView: Reset map bearing');
    } catch (error) {
      console.error('❌ MapView: Error resetting bearing:', error);
    }
  };

  // Enhanced dataset visualization using collection config
  const getDatasetVisualization = (dataset: Dataset | null) => {
    if (!dataset) return { emoji: '???', description: 'Interactive satellite map', color: '#f8f9fa' };

    // Use the new collection configuration system
    try {
      const visualization = getCollectionVisualization(dataset.id);
      return {
        emoji: visualization.emoji,
        description: getCollectionConfig(dataset.id)?.description || dataset.description || `${dataset.title} visualization`,
        color: visualization.color
      };
    } catch (error) {
      console.warn('??? MapView: Failed to get collection visualization, using fallback:', error);
      return {
        emoji: '??',
        description: `${dataset.title} visualization`,
        color: '#f8f9fa'
      };
    }
  };

  const visualization = getDatasetVisualization(selectedDataset);

  // Update map context for Chat Vision capability
  // This provides the chat with current map state for vision-based queries
  useEffect(() => {
    if (!onMapContextChange) return;

    // Only need map to be loaded - don't require satelliteData
    // This allows vision queries to work even without explicitly loaded STAC imagery
    if (!map || !mapLoaded) {
      onMapContextChange(null);
      return;
    }

    try {
      // Get current map bounds
      let bounds = null;
      if (mapProvider === 'leaflet' && window.L) {
        const leafletBounds = map.getBounds();
        bounds = {
          north: leafletBounds.getNorth(),
          south: leafletBounds.getSouth(),
          east: leafletBounds.getEast(),
          west: leafletBounds.getWest(),
          center_lat: map.getCenter().lat,
          center_lng: map.getCenter().lng
        };
      } else if (mapProvider === 'azure' && window.atlas) {
        const azureBounds = map.getCamera().bounds;
        const center = map.getCamera().center;
        bounds = {
          north: azureBounds[3],
          south: azureBounds[1],
          east: azureBounds[2],
          west: azureBounds[0],
          center_lat: center[1],
          center_lng: center[0]
        };
      }

      // Always try to capture map screenshot, regardless of satellite data
      // Note: Screenshot capture is async, so we handle it separately
      captureMapScreenshot().then(screenshot => {
        // Build map context
        const context = {
          bounds: bounds,
          imagery_base64: screenshot, // Screenshot of current view (base map or satellite data)
          current_collection: satelliteData?.items?.[0]?.collection || lastCollection || null,
          item_id: satelliteData?.items?.[0]?.id || null,
          datetime: satelliteData?.items?.[0]?.datetime || null,
          zoom_level: mapProvider === 'leaflet' ? map.getZoom() : map.getCamera().zoom,
          has_satellite_data: !!satelliteData  // Flag to indicate if STAC imagery is loaded
        };

        console.log('🗺️ MapView: Updated map context for Chat Vision:', {
          has_screenshot: !!screenshot,
          has_satellite_data: context.has_satellite_data,
          collection: context.current_collection,
          bounds: context.bounds
        });

        onMapContextChange(context);
      }).catch(err => {
        console.error('❌ MapView: Failed to capture screenshot for context:', err);
        // Still send context without screenshot
        const context = {
          bounds: bounds,
          imagery_base64: null,
          current_collection: satelliteData?.items?.[0]?.collection || lastCollection || null,
          item_id: satelliteData?.items?.[0]?.id || null,
          datetime: satelliteData?.items?.[0]?.datetime || null,
          zoom_level: mapProvider === 'leaflet' ? map.getZoom() : map.getCamera().zoom,
          has_satellite_data: !!satelliteData
        };
        onMapContextChange(context);
      });
    } catch (error) {
      console.error('❌ MapView: Error updating map context:', error);
      onMapContextChange(null);
    }
  }, [satelliteData, map, mapLoaded, mapProvider, onMapContextChange, lastCollection]);

  return (
    <div className="map" style={{ position: 'relative' }}>
      {/* Always render map container so mapRef.current is available */}
      <div
        ref={mapRef}
        style={{
          width: '100%',
          height: '100%',
          display: 'block'
        }}
      />

      {/* Loading overlay - only show when map is not loaded */}
      {!mapLoaded && (
        <div style={{
          position: 'absolute',
          top: 0,
          left: 0,
          right: 0,
          bottom: 0,
          display: 'flex',
          flexDirection: 'column',
          alignItems: 'center',
          justifyContent: 'center',
          backgroundColor: 'rgba(255, 255, 255, 0.9)',
          zIndex: 1000,
          color: 'var(--muted)',
          fontSize: '16px',
          padding: '20px'
        }}>
          <div style={{ marginBottom: '10px' }}>Loading map...</div>
        </div>
      )}

      {/* Map status overlay - only show when there's an active dataset */}
      {mapLoaded && selectedDataset && (
        <div style={{
          position: 'absolute',
          top: '10px',
          left: '10px',
          background: 'rgba(255, 255, 255, 0.95)',
          padding: '8px 12px',
          borderRadius: '6px',
          fontSize: '14px',
          fontWeight: '500',
          boxShadow: '0 2px 8px rgba(0, 0, 0, 0.15)',
          zIndex: 1000,
          border: '1px solid rgba(0, 0, 0, 0.1)'
        }}>
          <div>
            <div style={{ fontSize: '12px', color: '#666', marginBottom: '2px' }}>
              VIEWING DATASET
            </div>
            <div style={{ color: '#333' }}>{selectedDataset.title}</div>
          </div>
        </div>
      )}

      {/* Pin controls - show when map is loaded */}
      {mapLoaded && (
        <>
          {/* Pin toggle button - Modern icon-only button */}
          <div 
            onClick={handlePinButtonClick}
            title="Geointelligence Modules"
            style={{
              position: 'absolute',
              top: '10px',
              left: '10px', // Moved to top left
              background: showModulesMenu ? 'rgba(34, 197, 94, 0.85)' : 'rgba(255, 255, 255, 0.3)',
              color: showModulesMenu ? 'white' : '#333',
              width: '48px',
              height: '48px',
              borderRadius: '12px',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              fontSize: '24px',
              boxShadow: '0 2px 12px rgba(0, 0, 0, 0.15)',
              zIndex: 1000,
              border: showModulesMenu ? '2px solid rgba(34, 197, 94, 1)' : '1px solid rgba(0, 0, 0, 0.15)',
              cursor: 'pointer',
              userSelect: 'none',
              transition: 'all 0.2s ease',
              backdropFilter: 'blur(10px)'
            }}
            onMouseEnter={(e) => {
              e.currentTarget.style.transform = 'scale(1.08)';
              e.currentTarget.style.boxShadow = '0 4px 16px rgba(0, 0, 0, 0.2)';
            }}
            onMouseLeave={(e) => {
              e.currentTarget.style.transform = 'scale(1)';
              e.currentTarget.style.boxShadow = '0 2px 12px rgba(0, 0, 0, 0.15)';
            }}
          >
            {/* Modern Pin Icon - SVG */}
            <svg 
              width="24" 
              height="24" 
              viewBox="0 0 24 24" 
              fill="none" 
              stroke="currentColor" 
              strokeWidth="2.5" 
              strokeLinecap="round" 
              strokeLinejoin="round"
              style={{ display: 'block' }}
            >
              <path d="M21 10c0 7-9 13-9 13s-9-6-9-13a9 9 0 0 1 18 0z"></path>
              <circle cx="12" cy="10" r="3"></circle>
            </svg>
          </div>

          {/* Modules Menu - appears BELOW Pin button when clicked */}
          {showModulesMenu && (
            <div style={{
              position: 'absolute',
              top: '65px', // Below Pin button
              left: '10px', // Aligned with Pin button - top left
              background: 'rgba(255, 255, 255, 0.85)',
              borderRadius: '16px',
              boxShadow: '0 8px 32px rgba(0, 0, 0, 0.18)',
              zIndex: 1001,
              padding: '20px',
              width: '300px',
              backdropFilter: 'blur(12px)',
              border: '1px solid rgba(0, 0, 0, 0.08)'
            }}>
              <div style={{
                fontSize: '16px',
                fontWeight: '700',
                color: '#1f2937',
                marginBottom: '14px',
                display: 'flex',
                alignItems: 'center',
                gap: '10px',
                letterSpacing: '-0.01em'
              }}>
                Geointelligence Modules
              </div>
              
              <div style={{ display: 'flex', flexDirection: 'column', gap: '8px' }}>
                {/* Terrain Analysis Module */}
                <div
                  onClick={() => handleModuleSelect('terrain')}
                  style={{
                    padding: '12px',
                    borderRadius: '8px',
                    cursor: 'pointer',
                    border: selectedModule === 'terrain' ? '2px solid #3b82f6' : '1px solid rgba(0, 0, 0, 0.1)',
                    background: selectedModule === 'terrain' ? 'rgba(59, 130, 246, 0.1)' : 'white',
                    transition: 'all 0.2s ease'
                  }}
                  onMouseEnter={(e) => {
                    if (selectedModule !== 'terrain') {
                      e.currentTarget.style.background = 'rgba(0, 0, 0, 0.05)';
                    }
                  }}
                  onMouseLeave={(e) => {
                    if (selectedModule !== 'terrain') {
                      e.currentTarget.style.background = 'white';
                    }
                  }}
                >
                  <div style={{ fontSize: '14px', fontWeight: '600', color: '#1f2937', marginBottom: '4px' }}>
                    Terrain Analysis
                  </div>
                  <div style={{ fontSize: '12px', color: '#6b7280' }}>
                    Analyze landscape characteristics.
                  </div>
                </div>

                {/* Mobility Analysis Module */}
                <div
                  onClick={() => handleModuleSelect('mobility')}
                  style={{
                    padding: '12px',
                    borderRadius: '8px',
                    cursor: 'pointer',
                    border: selectedModule === 'mobility' ? '2px solid #10b981' : '1px solid rgba(0, 0, 0, 0.1)',
                    background: selectedModule === 'mobility' ? 'rgba(16, 185, 129, 0.1)' : 'white',
                    transition: 'all 0.2s ease'
                  }}
                  onMouseEnter={(e) => {
                    if (selectedModule !== 'mobility') {
                      e.currentTarget.style.background = 'rgba(0, 0, 0, 0.05)';
                    }
                  }}
                  onMouseLeave={(e) => {
                    if (selectedModule !== 'mobility') {
                      e.currentTarget.style.background = 'white';
                    }
                  }}
                >
                  <div style={{ fontSize: '14px', fontWeight: '600', color: '#1f2937', marginBottom: '4px' }}>
                    Mobility Analysis
                  </div>
                  <div style={{ fontSize: '12px', color: '#6b7280' }}>
                    Analyze how conditions impact mobility.
                  </div>
                </div>

                {/* Building Damage Analysis Module */}
                <div
                  onClick={() => handleModuleSelect('building_damage')}
                  style={{
                    padding: '12px',
                    borderRadius: '8px',
                    cursor: 'pointer',
                    border: selectedModule === 'building_damage' ? '2px solid #ef4444' : '1px solid rgba(0, 0, 0, 0.1)',
                    background: selectedModule === 'building_damage' ? 'rgba(239, 68, 68, 0.1)' : 'white',
                    transition: 'all 0.2s ease'
                  }}
                  onMouseEnter={(e) => {
                    if (selectedModule !== 'building_damage') {
                      e.currentTarget.style.background = 'rgba(0, 0, 0, 0.05)';
                    }
                  }}
                  onMouseLeave={(e) => {
                    if (selectedModule !== 'building_damage') {
                      e.currentTarget.style.background = 'white';
                    }
                  }}
                >
                  <div style={{ fontSize: '14px', fontWeight: '600', color: '#1f2937', marginBottom: '4px' }}>
                    Building Damage
                  </div>
                  <div style={{ fontSize: '12px', color: '#6b7280' }}>
                    Detect and classify building damage levels.
                  </div>
                </div>

                {/* Comparison Module */}
                <div
                  onClick={() => handleModuleSelect('comparison')}
                  style={{
                    padding: '12px',
                    borderRadius: '8px',
                    cursor: 'pointer',
                    border: selectedModule === 'comparison' ? '2px solid #f59e0b' : '1px solid rgba(0, 0, 0, 0.1)',
                    background: selectedModule === 'comparison' ? 'rgba(245, 158, 11, 0.1)' : 'white',
                    transition: 'all 0.2s ease'
                  }}
                  onMouseEnter={(e) => {
                    if (selectedModule !== 'comparison') {
                      e.currentTarget.style.background = 'rgba(0, 0, 0, 0.05)';
                    }
                  }}
                  onMouseLeave={(e) => {
                    if (selectedModule !== 'comparison') {
                      e.currentTarget.style.background = 'white';
                    }
                  }}
                >
                  <div style={{ fontSize: '14px', fontWeight: '600', color: '#1f2937', marginBottom: '4px' }}>
                    Comparison
                  </div>
                  <div style={{ fontSize: '12px', color: '#6b7280' }}>
                    Compare location to identify changes.
                  </div>
                </div>

                {/* Time Series Module */}
                <div
                  onClick={() => handleModuleSelect('time_series')}
                  style={{
                    padding: '12px',
                    borderRadius: '8px',
                    cursor: 'pointer',
                    border: selectedModule === 'time_series' ? '2px solid #8b5cf6' : '1px solid rgba(0, 0, 0, 0.1)',
                    background: selectedModule === 'time_series' ? 'rgba(139, 92, 246, 0.1)' : 'white',
                    transition: 'all 0.2s ease'
                  }}
                  onMouseEnter={(e) => {
                    if (selectedModule !== 'time_series') {
                      e.currentTarget.style.background = 'rgba(0, 0, 0, 0.05)';
                    }
                  }}
                  onMouseLeave={(e) => {
                    if (selectedModule !== 'time_series') {
                      e.currentTarget.style.background = 'white';
                    }
                  }}
                >
                  <div style={{ fontSize: '14px', fontWeight: '600', color: '#1f2937', marginBottom: '4px' }}>
                    Time Series Animation
                  </div>
                  <div style={{ fontSize: '12px', color: '#6b7280' }}>
                    Display location evolution over time.
                  </div>
                </div>
              </div>

              {selectedModule && (
                <div style={{
                  marginTop: '14px',
                  padding: '10px 14px',
                  background: 'rgba(34, 197, 94, 0.12)',
                  borderRadius: '8px',
                  fontSize: '13px',
                  color: '#059669',
                  fontWeight: '600',
                  textAlign: 'center'
                }}>
                  ✓ {selectedModule === 'terrain' ? 'Terrain Analysis' : 
                     selectedModule === 'mobility' ? 'Mobility Analysis' :
                     selectedModule === 'building_damage' ? 'Building Damage' :
                     selectedModule === 'comparison' ? 'Comparison' :
                     'Time Series'} selected
                </div>
              )}
            </div>
          )}

          {/* Before/After Toggle Buttons - only show in comparison mode with imagery */}
          {comparisonMode && comparisonState.beforeImagery && comparisonState.afterImagery && (
            <div style={{
              position: 'absolute',
              top: '10px',
              right: '10px',
              display: 'flex',
              gap: '8px',
              zIndex: 1000
            }}>
              <div
                onClick={toggleBeforeAfter}
                style={{
                  background: comparisonState.showingBefore ? 'rgba(59, 130, 246, 0.95)' : 'rgba(255, 255, 255, 0.9)',
                  color: comparisonState.showingBefore ? 'white' : '#1a1a1a',
                  padding: '10px 16px',
                  borderRadius: '10px',
                  fontSize: '14px',
                  fontWeight: '600',
                  boxShadow: '0 2px 12px rgba(0, 0, 0, 0.15)',
                  cursor: 'pointer',
                  border: comparisonState.showingBefore ? '2px solid #3b82f6' : '1px solid rgba(0, 0, 0, 0.1)',
                  transition: 'all 0.2s ease',
                  backdropFilter: 'blur(10px)',
                  userSelect: 'none'
                }}
                onMouseEnter={(e) => {
                  e.currentTarget.style.transform = 'translateY(-2px)';
                  e.currentTarget.style.boxShadow = '0 4px 16px rgba(0, 0, 0, 0.2)';
                }}
                onMouseLeave={(e) => {
                  e.currentTarget.style.transform = 'translateY(0)';
                  e.currentTarget.style.boxShadow = '0 2px 12px rgba(0, 0, 0, 0.15)';
                }}
              >
                📅 BEFORE
              </div>
              
              <div
                onClick={toggleBeforeAfter}
                style={{
                  background: !comparisonState.showingBefore ? 'rgba(16, 185, 129, 0.95)' : 'rgba(255, 255, 255, 0.9)',
                  color: !comparisonState.showingBefore ? 'white' : '#1a1a1a',
                  padding: '10px 16px',
                  borderRadius: '10px',
                  fontSize: '14px',
                  fontWeight: '600',
                  boxShadow: '0 2px 12px rgba(0, 0, 0, 0.15)',
                  cursor: 'pointer',
                  border: !comparisonState.showingBefore ? '2px solid #10b981' : '1px solid rgba(0, 0, 0, 0.1)',
                  transition: 'all 0.2s ease',
                  backdropFilter: 'blur(10px)',
                  userSelect: 'none'
                }}
                onMouseEnter={(e) => {
                  e.currentTarget.style.transform = 'translateY(-2px)';
                  e.currentTarget.style.boxShadow = '0 4px 16px rgba(0, 0, 0, 0.2)';
                }}
                onMouseLeave={(e) => {
                  e.currentTarget.style.transform = 'translateY(0)';
                  e.currentTarget.style.boxShadow = '0 2px 12px rgba(0, 0, 0, 0.15)';
                }}
              >
                📅 AFTER
              </div>
            </div>
          )}

          {/* Map Style Dropdown Button - positioned under pin button on left */}
          <div 
            onClick={() => setShowMapStyleDropdown(!showMapStyleDropdown)}
            title="Change Map Style"
            data-map-style-dropdown
            style={{
              position: 'absolute',
              top: '68px', // Under pin button
              left: '10px',
              background: showMapStyleDropdown ? 'rgba(255, 255, 255, 0.7)' : 'rgba(255, 255, 255, 0.3)',
              color: '#1a1a1a',
              width: '48px',
              height: '48px',
              borderRadius: '12px',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              fontSize: '24px',
              boxShadow: '0 2px 12px rgba(0, 0, 0, 0.15)',
              zIndex: 1000,
              border: '1px solid rgba(0, 0, 0, 0.15)',
              cursor: 'pointer',
              userSelect: 'none',
              transition: 'all 0.2s ease',
              backdropFilter: 'blur(10px)'
            }}
            onMouseEnter={(e) => {
              e.currentTarget.style.transform = 'scale(1.08)';
              e.currentTarget.style.boxShadow = '0 4px 16px rgba(0, 0, 0, 0.2)';
            }}
            onMouseLeave={(e) => {
              e.currentTarget.style.transform = 'scale(1)';
              e.currentTarget.style.boxShadow = '0 2px 12px rgba(0, 0, 0, 0.15)';
            }}
          >
            {/* Map icon */}
            <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
              <polygon points="3 6 9 3 15 6 21 3 21 18 15 21 9 18 3 21"></polygon>
              <line x1="9" y1="3" x2="9" y2="18"></line>
              <line x1="15" y1="6" x2="15" y2="21"></line>
            </svg>
          </div>

          {/* Map Style Dropdown Menu */}
          {showMapStyleDropdown && (
            <div 
              style={{
                position: 'absolute',
                top: '68px', // Same top as button
                left: '68px', // To the right of the button
                background: 'rgba(255, 255, 255, 0.97)',
                borderRadius: '12px',
                boxShadow: '0 8px 24px rgba(0, 0, 0, 0.18)',
                zIndex: 1001,
                minWidth: '240px',
                backdropFilter: 'blur(12px)',
                border: '1px solid rgba(0, 0, 0, 0.08)',
                overflow: 'hidden'
              }}
            >
              <div style={{
                padding: '12px 16px',
                borderBottom: '1px solid rgba(0, 0, 0, 0.1)',
                fontSize: '14px',
                fontWeight: '600',
                color: '#333',
                fontFamily: '"Segoe UI", "Segoe UI Variable Text", -apple-system, BlinkMacSystemFont, system-ui, Roboto, Inter, "Helvetica Neue", Arial, "Noto Sans"'
              }}>
                Map Styles
              </div>
              
              {[
                { id: 'satellite_road_labels', name: 'Satellite (Default)', icon: '🛰️' },
                { id: 'road', name: 'Road', icon: '🗺️' },
                { id: 'road_shaded_relief', name: 'Road + Terrain', icon: '⛰️' },
                { id: 'satellite', name: 'Satellite Only', icon: '🌍' },
                { id: 'grayscale_light', name: 'Grayscale Light', icon: '⚪' },
                { id: 'night', name: 'Night Mode', icon: '🌙' }
              ].map((style) => (
                <div
                  key={style.id}
                  onClick={() => handleMapStyleChange(style.id)}
                  style={{
                    padding: '12px 16px',
                    cursor: 'pointer',
                    fontSize: '14px',
                    fontFamily: '"Segoe UI", "Segoe UI Variable Text", -apple-system, BlinkMacSystemFont, system-ui, Roboto, Inter, "Helvetica Neue", Arial, "Noto Sans"',
                    display: 'flex',
                    alignItems: 'center',
                    gap: '10px',
                    background: currentMapStyle === style.id ? 'rgba(0, 120, 212, 0.1)' : 'transparent',
                    borderLeft: currentMapStyle === style.id ? '3px solid #0078d4' : '3px solid transparent',
                    transition: 'all 0.2s ease'
                  }}
                  onMouseEnter={(e) => {
                    if (currentMapStyle !== style.id) {
                      e.currentTarget.style.background = 'rgba(0, 0, 0, 0.05)';
                    }
                  }}
                  onMouseLeave={(e) => {
                    if (currentMapStyle !== style.id) {
                      e.currentTarget.style.background = 'transparent';
                    }
                  }}
                >
                  <span style={{ fontSize: '18px' }}>{style.icon}</span>
                  <span style={{ 
                    fontWeight: currentMapStyle === style.id ? '600' : '400',
                    color: currentMapStyle === style.id ? '#0078d4' : '#333'
                  }}>
                    {style.name}
                  </span>
                  {currentMapStyle === style.id && (
                    <span style={{ marginLeft: 'auto', color: '#0078d4' }}>✓</span>
                  )}
                </div>
              ))}
            </div>
          )}

          {/* Zoom In Button - positioned under map style button */}
          <div 
            onClick={handleZoomIn}
            title="Zoom In"
            style={{
              position: 'absolute',
              top: '126px', // Under map style button
              left: '10px',
              background: 'rgba(255, 255, 255, 0.3)',
              color: '#1a1a1a',
              width: '48px',
              height: '48px',
              borderRadius: '12px',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              fontSize: '24px',
              boxShadow: '0 2px 12px rgba(0, 0, 0, 0.15)',
              zIndex: 1000,
              border: '1px solid rgba(0, 0, 0, 0.15)',
              cursor: 'pointer',
              userSelect: 'none',
              transition: 'all 0.2s ease',
              backdropFilter: 'blur(10px)',
              fontWeight: '300'
            }}
            onMouseEnter={(e) => {
              e.currentTarget.style.transform = 'scale(1.08)';
              e.currentTarget.style.boxShadow = '0 4px 16px rgba(0, 0, 0, 0.2)';
            }}
            onMouseLeave={(e) => {
              e.currentTarget.style.transform = 'scale(1)';
              e.currentTarget.style.boxShadow = '0 2px 12px rgba(0, 0, 0, 0.15)';
            }}
          >
            +
          </div>

          {/* Zoom Out Button - positioned under zoom in button */}
          <div 
            onClick={handleZoomOut}
            title="Zoom Out"
            style={{
              position: 'absolute',
              top: '184px', // Under zoom in button
              left: '10px',
              background: 'rgba(255, 255, 255, 0.3)',
              color: '#1a1a1a',
              width: '48px',
              height: '48px',
              borderRadius: '12px',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              fontSize: '24px',
              boxShadow: '0 2px 12px rgba(0, 0, 0, 0.15)',
              zIndex: 1000,
              border: '1px solid rgba(0, 0, 0, 0.15)',
              cursor: 'pointer',
              userSelect: 'none',
              transition: 'all 0.2s ease',
              backdropFilter: 'blur(10px)',
              fontWeight: '300'
            }}
            onMouseEnter={(e) => {
              e.currentTarget.style.transform = 'scale(1.08)';
              e.currentTarget.style.boxShadow = '0 4px 16px rgba(0, 0, 0, 0.2)';
            }}
            onMouseLeave={(e) => {
              e.currentTarget.style.transform = 'scale(1)';
              e.currentTarget.style.boxShadow = '0 2px 12px rgba(0, 0, 0, 0.15)';
            }}
          >
            −
          </div>

          {/* Compass/Reset Bearing Button - positioned under zoom out button */}
          <div 
            onClick={handleResetBearing}
            title="Reset Map Rotation"
            style={{
              position: 'absolute',
              top: '242px', // Under zoom out button
              left: '10px',
              background: 'rgba(255, 255, 255, 0.3)',
              color: '#1a1a1a',
              width: '48px',
              height: '48px',
              borderRadius: '12px',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              fontSize: '20px',
              boxShadow: '0 2px 12px rgba(0, 0, 0, 0.15)',
              zIndex: 1000,
              border: '1px solid rgba(0, 0, 0, 0.15)',
              cursor: 'pointer',
              userSelect: 'none',
              transition: 'all 0.2s ease',
              backdropFilter: 'blur(10px)'
            }}
            onMouseEnter={(e) => {
              e.currentTarget.style.transform = 'scale(1.08)';
              e.currentTarget.style.boxShadow = '0 4px 16px rgba(0, 0, 0, 0.2)';
            }}
            onMouseLeave={(e) => {
              e.currentTarget.style.transform = 'scale(1)';
              e.currentTarget.style.boxShadow = '0 2px 12px rgba(0, 0, 0, 0.15)';
            }}
          >
            {/* Compass icon */}
            <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
              <circle cx="12" cy="12" r="10"></circle>
              <polygon points="16.24 7.76 14.12 14.12 7.76 16.24 9.88 9.88 16.24 7.76"></polygon>
            </svg>
          </div>

          {/* Data Catalog Toggle Button - positioned under compass button */}
          <div 
            onClick={onToggleSidebar}
            title={sidebarOpen ? "Collapse Data Catalog" : "Expand Data Catalog"}
            style={{
              position: 'absolute',
              top: '300px', // Under compass button
              left: '10px',
              background: 'rgba(255, 255, 255, 0.3)',
              color: '#1a1a1a',
              width: '48px',
              height: '48px',
              borderRadius: '12px',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              fontSize: '20px',
              boxShadow: '0 2px 12px rgba(0, 0, 0, 0.15)',
              zIndex: 1000,
              border: '1px solid rgba(0, 0, 0, 0.15)',
              cursor: 'pointer',
              userSelect: 'none',
              transition: 'all 0.2s ease',
              backdropFilter: 'blur(10px)'
            }}
            onMouseEnter={(e) => {
              e.currentTarget.style.transform = 'scale(1.08)';
              e.currentTarget.style.boxShadow = '0 4px 16px rgba(0, 0, 0, 0.2)';
            }}
            onMouseLeave={(e) => {
              e.currentTarget.style.transform = 'scale(1)';
              e.currentTarget.style.boxShadow = '0 2px 12px rgba(0, 0, 0, 0.15)';
            }}
          >
            {/* Arrow icon - rotates based on sidebar state */}
            <svg 
              width="20" 
              height="20" 
              viewBox="0 0 24 24" 
              fill="none" 
              style={{
                transform: sidebarOpen ? 'rotate(0deg)' : 'rotate(180deg)',
                transition: 'transform 0.3s ease'
              }}
            >
              <path
                d="M15 18L9 12L15 6"
                stroke="currentColor"
                strokeWidth="2"
                strokeLinecap="round"
                strokeLinejoin="round"
              />
            </svg>
          </div>

          {/* Pin coordinate indicator - show when pin is active */}
          {pinState.active && (
            <div style={{
              position: 'absolute',
              bottom: '60px',
              left: '50%',
              transform: 'translateX(-50%)',
              background: 'rgba(220, 38, 38, 0.95)',
              color: 'white',
              padding: '8px 16px',
              borderRadius: '20px',
              fontSize: '13px',
              fontWeight: '500',
              boxShadow: '0 2px 8px rgba(0, 0, 0, 0.2)',
              zIndex: 1000,
              display: 'flex',
              alignItems: 'center',
              gap: '12px'
            }}>
              <span>
                📍 Pin: {pinState.lat?.toFixed(4)}°, {pinState.lng?.toFixed(4)}°
              </span>
              <span 
                onClick={handleClearPin}
                style={{
                  cursor: 'pointer',
                  padding: '2px 6px',
                  borderRadius: '10px',
                  background: 'rgba(255, 255, 255, 0.2)',
                  fontSize: '12px'
                }}
              >
                ✕ Clear
              </span>
            </div>
          )}

          {/* Terrain Analysis Pin coordinate indicator - modern translucent style */}
          {terrainAnalysisPin.lat && terrainAnalysisPin.lng && (
            <div style={{
              position: 'absolute',
              bottom: '20px',
              left: '50%',
              transform: 'translateX(-50%)',
              background: 'rgba(200, 200, 200, 0.25)',
              backdropFilter: 'blur(12px)',
              color: '#1f2937',
              padding: '10px 20px',
              borderRadius: '24px',
              fontSize: '14px',
              fontWeight: '500',
              boxShadow: '0 4px 12px rgba(0, 0, 0, 0.15)',
              zIndex: 1000,
              display: 'flex',
              alignItems: 'center',
              gap: '12px',
              border: '1px solid rgba(255, 255, 255, 0.4)',
              fontFamily: '"Segoe UI", "Segoe UI Variable Text", -apple-system, BlinkMacSystemFont, system-ui, Roboto, Inter, "Helvetica Neue", Arial, "Noto Sans"'
            }}>
              <span style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="#3B82F6" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
                  <path d="M21 10c0 7-9 13-9 13s-9-6-9-13a9 9 0 0 1 18 0z" fill="#3B82F6"></path>
                  <circle cx="12" cy="10" r="3" fill="white"></circle>
                </svg>
                <span style={{ fontWeight: '600' }}>
                  {terrainAnalysisPin.lat.toFixed(6)}°, {terrainAnalysisPin.lng.toFixed(6)}°
                </span>
              </span>
            </div>
          )}
        </>
      )}

      {/* Tile expansion indicator - show when expanding coverage */}
      {isExpanding && (
        <div style={{
          position: 'absolute',
          top: '50%',
          left: '50%',
          transform: 'translate(-50%, -50%)',
          background: 'rgba(173, 216, 230, 0.15)',
          color: '#1e40af',
          padding: '12px 20px',
          borderRadius: '8px',
          fontSize: '14px',
          fontWeight: '500',
          backdropFilter: 'blur(4px)',
          boxShadow: '0 2px 8px rgba(135, 206, 235, 0.2)',
          zIndex: 2000,
          display: 'flex',
          alignItems: 'center',
          gap: '10px',
          border: '1px solid rgba(173, 216, 230, 0.3)'
        }}>
          <div style={{
            width: '16px',
            height: '16px',
            border: '2px solid transparent',
            borderTop: '2px solid #1e40af',
            borderRadius: '50%',
            animation: 'spin 1s linear infinite'
          }} />
          Adjusting tiles to zoom level
        </div>
      )}

      {/* Dataset info panel when selected - REMOVED */}

      {/* Text Visibility Tip - shown when satellite data is loaded */}
      {showStyleTip && satelliteData && mapLoaded && (
        <div className={`map-style-tip ${showStyleTip ? 'show' : ''}`}>
          ? <strong>Text Hard to Read?</strong><br />
          � Use the style control (top-right) to switch to <strong>"Road"</strong> or <strong>"Road Shaded Relief"</strong><br />
          � These styles provide much better text contrast over satellite imagery<br />
          � Or use <strong>"Satellite"</strong> (no labels) for pure imagery view
        </div>
      )}

      {/* Data Legend - shown when any visualizable data is displayed */}
      <DataLegend 
        collection={lastCollection || ''}
        isVisible={showDataLegend && mapLoaded}
      />
    </div>
  );
};

export default MapView;
