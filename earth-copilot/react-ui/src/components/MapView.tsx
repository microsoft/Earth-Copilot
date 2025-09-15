// Copyright (c) Microsoft Corporation.
// Licensed under the MIT license.

import React, { useEffect, useState, useRef } from 'react';
import { Dataset } from '../services/api';
import { TileUrlGenerator } from '../utils/tileUrlGenerator';
import { getCollectionVisualization, getCollectionConfig } from '../config/collectionConfig';

/**
 * Extract geographic region from query text and return appropriate bounds
 * NOTE: This function now relies on backend location resolution instead of hardcoded coordinates
 */
function extractGeographicRegion(queryText: string): { west: number; south: number; east: number; north: number } | null {
  if (!queryText) return null;

  // The backend's dynamic location resolution (Azure Maps, Nominatim, etc.) handles all location queries
  // This frontend function is kept for legacy compatibility but should not be used
  console.log('🌍 MapView: Frontend region extraction bypassed - using backend location resolution');
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
}

interface SatelliteData {
  bbox: number[] | null;
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
}

const MapView: React.FC<MapViewProps> = ({ selectedDataset, lastChatResponse }) => {
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

  // Initialize fallback map using OpenStreetMap when Azure Maps fails
  const initializeFallbackMap = () => {
    if (!mapRef.current || mapProvider === 'leaflet') return;

    console.log('🗺️ MapView: Initializing fallback Leaflet map');

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
          attribution: '© Esri World Imagery',
          maxZoom: 19
        }).addTo(leafletMap);

        setMap(leafletMap);
        setMapProvider('leaflet');
        setMapLoaded(true);
        setMapError(null);

        console.log('🗺️ MapView: Fallback Leaflet map initialized successfully');
      } catch (error) {
        console.error('🗺️ MapView: Failed to initialize fallback map:', error);
        setMapError('Failed to initialize any map system');
      }
    } else {
      // Create basic HTML/CSS map as last resort
      console.log('🗺️ MapView: Creating basic HTML map as last resort');
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
            <h3>📍 Map View</h3>
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

  // Helper function to get SAS token for MPC collections
  const getMPCToken = async (collection: string): Promise<string | null> => {
    try {
      console.log('🗺️ MapView: Requesting SAS token for collection:', collection);
      const tokenResponse = await fetch(`https://planetarycomputer.microsoft.com/api/sas/v1/token/${collection}`);
      if (tokenResponse.ok) {
        const tokenData = await tokenResponse.json();
        console.log('🗺️ MapView: [DEBUG] Received SAS token');
        return tokenData.token;
      } else {
        console.log('🗺️ MapView: [WARN] Failed to get SAS token (status:', tokenResponse.status, ')');
        return null;
      }
    } catch (error) {
      console.log('🗺️ MapView: [ERROR] Error requesting SAS token:', error);
      return null;
    }
  };

  // Helper function to test tile URL at specific coordinates
  const testTileUrl = async (tileTemplate: string, z: number, x: number, y: number): Promise<void> => {
    const testUrl = tileTemplate.replace('{z}', z.toString()).replace('{x}', x.toString()).replace('{y}', y.toString());
    console.log(`🗺️ MapView: [TILE-TEST] Testing tile at ${z}/${x}/${y}: ${testUrl}`);

    try {
      // MPC API doesn't support HEAD requests, use GET with signal to abort early
      const controller = new AbortController();
      const timeoutId = setTimeout(() => controller.abort(), 5000); // 5 second timeout

      const response = await fetch(testUrl, {
        method: 'GET',
        signal: controller.signal,
        headers: {
          'Range': 'bytes=0-1' // Request just the first byte to minimize data transfer
        }
      }).finally(() => {
        clearTimeout(timeoutId);
      });

      console.log(`🗺️ MapView: [TILE-TEST] Tile ${z}/${x}/${y} response:`, {
        status: response.status,
        statusText: response.statusText,
        contentType: response.headers.get('content-type'),
        contentLength: response.headers.get('content-length'),
        cacheControl: response.headers.get('cache-control'),
        url: response.url
      });

      if (response.status === 404) {
        console.log(`🗺️ MapView: [TILE-TEST] 404 analysis for ${z}/${x}/${y}:`, {
          expectedTileExists: false,
          possibleReasons: [
            'Tile coordinates outside data bounds',
            'Zoom level not available for this item',
            'Data not yet processed into tiles',
            'Authentication/token issues'
          ]
        });
      }
    } catch (error: any) {
      const errorMessage = error.name === 'AbortError' ? 'Request timeout' : error.message;
      console.log(`🗺️ MapView: [TILE-TEST] Tile ${z}/${x}/${y} error:`, errorMessage);
    }
  };

  // Helper function to fetch and process tilejson URLs with comprehensive debugging
  const processTilejsonUrl = async (tilejsonUrl: string, collection?: string): Promise<string> => {
    try {
      console.log('🗺️ MapView: [MPC-APPROACH] ===== PROCESSING TILEJSON URL =====');
      console.log('🗺️ MapView: [MPC-APPROACH] Original URL:', tilejsonUrl);
      console.log('🗺️ MapView: [MPC-APPROACH] Collection:', collection);
      console.log('🗺️ MapView: [MPC-APPROACH] Using Microsoft Planetary Computer exact approach');

      // ===== MICROSOFT'S EXACT APPROACH =====
      // Microsoft's makeRasterTileJsonUrl returns TileJSON URLs that get passed directly to Azure Maps
      // We need to follow their pattern exactly: return TileJSON URL with authentication

      // For MPC collections, add SAS token for authentication
      let authenticatedTilejsonUrl = tilejsonUrl;
      if (collection && (collection.includes('sentinel') || collection.includes('landsat'))) {
        console.log('🗺️ MapView: [MPC-APPROACH] MPC collection detected, requesting SAS token...');
        const sasToken = await getMPCToken(collection);
        if (sasToken) {
          authenticatedTilejsonUrl = `${tilejsonUrl}&${sasToken}`;
          console.log('🗺️ MapView: [MPC-APPROACH] SAS token added to tilejson URL');
        } else {
          console.log('🗺️ MapView: [MPC-APPROACH] No SAS token obtained');
        }
      }

      // Validate TileJSON URL is accessible (same as Microsoft does)
      console.log('🗺️ MapView: [MPC-APPROACH] Validating TileJSON URL...');
      const tilejsonResponse = await fetch(authenticatedTilejsonUrl);
      console.log('🗺️ MapView: [MPC-APPROACH] TileJSON response:', {
        status: tilejsonResponse.status,
        statusText: tilejsonResponse.statusText,
        contentType: tilejsonResponse.headers.get('content-type')
      });

      if (tilejsonResponse.ok) {
        const tilejsonData = await tilejsonResponse.json();
        console.log('🗺️ MapView: [MPC-APPROACH] TileJSON validated successfully:', {
          tilejson: tilejsonData.tilejson,
          tilesCount: tilejsonData.tiles?.length,
          bounds: tilejsonData.bounds,
          minzoom: tilejsonData.minzoom,
          maxzoom: tilejsonData.maxzoom
        });

        // Extract the authenticated tile template (Microsoft's actual pattern)
        // Microsoft passes TileJSON URLs to Azure Maps, but Azure Maps v2 expects tile templates
        if (tilejsonData.tiles && tilejsonData.tiles.length > 0) {
          const authenticatedTileTemplate = tilejsonData.tiles[0];
          console.log('🗺️ MapView: [MPC-APPROACH] Returning authenticated tile template for Azure Maps v2:', authenticatedTileTemplate.substring(0, 150) + '...');
          console.log('🗺️ MapView: [MPC-APPROACH] Template contains {z}/{x}/{y}:', authenticatedTileTemplate.includes('{z}') && authenticatedTileTemplate.includes('{x}') && authenticatedTileTemplate.includes('{y}'));
          return authenticatedTileTemplate;
        } else {
          console.log('🗺️ MapView: [MPC-APPROACH] No tiles found in TileJSON, using original URL');
          return tilejsonUrl;
        }
      } else {
        console.log('🗺️ MapView: [MPC-APPROACH] TileJSON validation failed, using original URL');
        return tilejsonUrl;
      }
    } catch (error) {
      console.log('🗺️ MapView: [MPC-APPROACH] Error processing TileJSON:', error, 'using original URL');
      return tilejsonUrl;
    }
  };

  // Test thermal detection logic on component mount
  useEffect(() => {
    console.log('🧪 MapView: Testing thermal detection logic...');
    
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
    
    console.log('🧪 MapView: [THERMAL TEST] Conditions check:', {
      collection,
      isLandsatCollection,
      originalQuery,
      isThermalQuery,
      shouldTriggerThermalDetection: isLandsatCollection && isThermalQuery
    });

    if (isLandsatCollection && isThermalQuery) {
      console.log('🔥 MapView: [TEST] THERMAL DETECTION LOGIC WOULD TRIGGER!');
      
      const thermalAssets = ['lwir11', 'lwir', 'thermal'];
      const availableThermalAsset = thermalAssets.find(asset => (firstFeature.assets as any)[asset]);
      
      if (availableThermalAsset) {
        console.log('🔥 MapView: [TEST] Found thermal asset:', availableThermalAsset);
        
        let tilejsonUrl = firstFeature.assets.tilejson.href;
        console.log('🔥 MapView: [TEST] Original URL:', tilejsonUrl);
        
        tilejsonUrl = tilejsonUrl
          .replace('assets=red&assets=green&assets=blue', `assets=${availableThermalAsset}`)
          .replace('color_formula=gamma+RGB+2.7%2C+saturation+1.5%2C+sigmoidal+RGB+15+0.55', '');
        
        // Clean up any double & characters
        tilejsonUrl = tilejsonUrl.replace(/&&/g, '&').replace(/&$/, '').replace(/\?&/, '?');
        
        console.log('🔥 MapView: [TEST] Modified thermal URL:', tilejsonUrl);
        console.log('🔥 MapView: [TEST] ✅ URL modification logic is working correctly!');
      }
    } else {
      console.log('🧪 MapView: [TEST] ❌ Thermal detection conditions not met');
    }
  }, []); // Run once on mount

  // Parse satellite data from chat responses
  useEffect(() => {
    if (!lastChatResponse) {
      console.log('🗺️ MapView: No lastChatResponse - skipping processing');
      return;
    }

    try {
      console.log('🗺️ MapView: ====== PROCESSING CHAT RESPONSE ======');
      console.log('🗺️ MapView: Full response object:', lastChatResponse);
      console.log('🗺️ MapView: Response type:', typeof lastChatResponse);
      console.log('🗺️ MapView: Response keys:', Object.keys(lastChatResponse || {}));
      console.log('🗺️ MapView: JSON stringified response:', JSON.stringify(lastChatResponse, null, 2));

      // Add specific debugging for data structure
      if (lastChatResponse.data) {
        console.log('🗺️ MapView: ✅ Found data object');
        console.log('🗺️ MapView: Data keys:', Object.keys(lastChatResponse.data));
        console.log('🗺️ MapView: Full data object:', lastChatResponse.data);
      }

      // Check for translation metadata containing original query
      if (lastChatResponse.translation_metadata) {
        console.log('🗺️ MapView: ✅ Found translation_metadata');
        console.log('🗺️ MapView: Translation metadata:', lastChatResponse.translation_metadata);
      }

      if (lastChatResponse.data) {

        if (lastChatResponse.data.stac_results) {
          console.log('🗺️ MapView: ✅ Found stac_results');
          console.log('🗺️ MapView: STAC results type:', typeof lastChatResponse.data.stac_results);
          console.log('🗺️ MapView: STAC results keys:', Object.keys(lastChatResponse.data.stac_results));
          console.log('🗺️ MapView: Full STAC results:', lastChatResponse.data.stac_results);

          // Check for features directly (correct structure)
          if (lastChatResponse.data.stac_results.features && Array.isArray(lastChatResponse.data.stac_results.features)) {
            console.log('🗺️ MapView: ✅ Found features in stac_results');
            console.log('🗺️ MapView: Features count:', lastChatResponse.data.stac_results.features.length);
            console.log('🗺️ MapView: First feature:', lastChatResponse.data.stac_results.features[0]);

            // Process the STAC features for satellite data
            const stacFeatures = lastChatResponse.data.stac_results.features;
            if (stacFeatures.length > 0) {
              const firstFeature = stacFeatures[0];
              const bbox = firstFeature.bbox;

              // Try to get a tile server URL from assets in order of preference
              let tileUrl: string | null = null;
              if (firstFeature.assets) {
                console.log('🗺️ MapView: [DEBUG] Assets available:', Object.keys(firstFeature.assets));
                console.log('🗺️ MapView: [DEBUG] Tilejson asset exists:', !!firstFeature.assets.tilejson);
                if (firstFeature.assets.tilejson) {
                  console.log('🗺️ MapView: [DEBUG] Tilejson asset:', firstFeature.assets.tilejson);
                }

                // Priority 1: Use tilejson asset URL - fetch to get actual tile template
                if (firstFeature.assets.tilejson) {
                  console.log('🗺️ MapView: Processing tilejson asset URL');
                  let tilejsonUrl = firstFeature.assets.tilejson.href;
                  console.log('🗺️ MapView: Original Tilejson URL:', tilejsonUrl);

                  // Extract collection from the feature
                  const collection = firstFeature.collection || (firstFeature.links?.find((link: any) => link.rel === 'collection')?.href?.split('/').pop());
                  console.log('🗺️ MapView: [DEBUG] Feature collection:', collection);

                  // THERMAL DETECTION: Modify tilejson URL for thermal queries
                  const isLandsatCollection = collection === 'landsat-c2-l2';
                  const originalQuery = lastChatResponse.translation_metadata?.original_query || '';
                  const isThermalQuery = originalQuery.toLowerCase().includes('thermal') || 
                                        originalQuery.toLowerCase().includes('infrared') || 
                                        originalQuery.toLowerCase().includes('heat') ||
                                        originalQuery.toLowerCase().includes('temperature');
                  
                  // Enhanced debugging for thermal detection
                  console.log('🔥 MapView: [THERMAL DEBUG] Collection check:', {
                    collection: collection,
                    isLandsatCollection: isLandsatCollection,
                    originalQuery: originalQuery,
                    isThermalQuery: isThermalQuery,
                    thermal_found: originalQuery.toLowerCase().includes('thermal'),
                    infrared_found: originalQuery.toLowerCase().includes('infrared'),
                    heat_found: originalQuery.toLowerCase().includes('heat'),
                    temperature_found: originalQuery.toLowerCase().includes('temperature')
                  });
                  
                  if (isLandsatCollection && isThermalQuery) {
                    console.log('🔥 MapView: THERMAL QUERY DETECTED for Landsat - switching to thermal infrared bands');
                    console.log('🔥 MapView: Original query:', originalQuery);
                    
                    // Check if thermal assets are available
                    const thermalAssets = ['lwir11', 'lwir', 'thermal'];
                    const availableThermalAsset = thermalAssets.find(asset => firstFeature.assets[asset]);
                    
                    if (availableThermalAsset) {
                      console.log('🔥 MapView: ⚡ THERMAL MODE ACTIVATED! Asset:', availableThermalAsset);
                      
                      // Set thermal mode state
                      setIsThermalMode(true);
                      
                      // Modify the tilejson URL to use thermal band instead of RGB
                      // Apply thermal visualization with adaptive rescale ranges for better contrast
                      // Using 'plasma' colormap: dark purple (cool) to bright yellow (hot)
                      // Try multiple rescale ranges to find the best thermal contrast
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
                      
                      // DEBUG: Log thermal URL and alternatives for manual testing
                      console.log('🔥 THERMAL ACTIVE - Primary range:', selectedRange);
                      console.log('🔥 THERMAL URL:', tilejsonUrl);
                      console.log('🔥 Alternative ranges for testing:');
                      thermalRanges.forEach((range, i) => {
                        if (range !== selectedRange) {
                          const altUrl = tilejsonUrl.replace(`rescale=${selectedRange}`, `rescale=${range}`);
                          console.log(`   ${i + 1}. Range ${range}K: ${altUrl.substring(0, 120)}...`);
                        }
                      });
                      
                      // Clean up any double & characters
                      tilejsonUrl = tilejsonUrl.replace(/&&/g, '&').replace(/&$/, '').replace(/\?&/, '?');
                      
                      console.log('🔥 MapView: Modified thermal tilejson URL (optimized rescale + plasma):', tilejsonUrl);
                    } else {
                      console.log('🔥 MapView: No thermal assets found, checking available assets:', Object.keys(firstFeature.assets));
                    }
                  } else {
                    console.log('🔥 MapView: Thermal mode not detected - using standard RGB processing');
                    setIsThermalMode(false);
                  }

                  console.log('🗺️ MapView: Final Tilejson URL:', tilejsonUrl);

                  // Process tilejson asynchronously with collection info for authentication
                  processTilejsonUrl(tilejsonUrl, collection).then((processedTileUrl) => {
                    console.log('🗺️ MapView: [DEBUG] Processed tile URL:', processedTileUrl);

                    if (bbox && processedTileUrl) {
                      console.log('🗺️ MapView: Creating satellite data from STAC feature with tilejson');
                      console.log('🗺️ MapView: BBOX:', bbox);
                      console.log('🗺️ MapView: Tile URL:', processedTileUrl);
                      console.log('🗺️ MapView: Tile URL type:', processedTileUrl.includes('{z}') ? 'Tile template' : 'Static image');

                      setSatelliteData({
                        bbox: bbox,
                        tile_url: processedTileUrl,
                        items: stacFeatures.slice(0, 5), // Use first 5 features
                        thermal_mode: isThermalMode,
                        thermal_timestamp: isThermalMode ? Date.now() : undefined // Force refresh for thermal
                      });
                    }
                  }).catch((error) => {
                    console.log('🗺️ MapView: [ERROR] Failed to process tilejson, using fallback:', error);
                    // Continue with fallback processing below
                  });

                  // Early return to avoid duplicate processing
                  return;
                }
                // Priority 2: Use rendered_preview for static preview (fallback for static images)
                else if (firstFeature.assets.rendered_preview) {
                  console.log('🗺️ MapView: Using rendered_preview asset URL (static image)');
                  tileUrl = firstFeature.assets.rendered_preview.href;
                }
                // Priority 3: Fallback to visual asset (direct TIFF - convert to preview)
                else if (firstFeature.assets.visual) {
                  console.log('🗺️ MapView: Converting visual asset to preview URL');
                  // Try to convert visual asset to a preview URL
                  const collection = firstFeature.collection;
                  const itemId = firstFeature.id;
                  if (collection && itemId) {
                    tileUrl = `https://planetarycomputer.microsoft.com/api/data/v1/item/preview.png?collection=${collection}&item=${itemId}&assets=visual&format=png`;
                    console.log('🗺️ MapView: Generated preview URL from visual asset:', tileUrl);
                  } else {
                    tileUrl = firstFeature.assets.visual.href;
                    console.log('🗺️ MapView: Using visual asset URL directly (may not work as tile):', tileUrl);
                  }
                }
              }

              // Fallback: look for preview links
              if (!tileUrl && firstFeature.links) {
                const previewLink = firstFeature.links.find((link: any) => link.rel === 'preview');
                if (previewLink) {
                  console.log('🗺️ MapView: Using preview link from links array');
                  tileUrl = previewLink.href;
                }
              }

              if (bbox && tileUrl) {
                console.log('🗺️ MapView: Creating satellite data from STAC feature');
                console.log('🗺️ MapView: BBOX:', bbox);
                console.log('🗺️ MapView: Tile URL:', tileUrl);
                console.log('🗺️ MapView: Tile URL type:', tileUrl.includes('{z}') ? 'Tile template' : 'Static image');

                setSatelliteData({
                  bbox: bbox,
                  tile_url: tileUrl,
                  items: stacFeatures.slice(0, 5) // Use first 5 features
                });
              }
            }
          } else if (lastChatResponse.data.stac_results.results) {
            // Fallback: check old structure for backwards compatibility
            console.log('🗺️ MapView: ✅ Found results in stac_results (old structure)');
            console.log('🗺️ MapView: Results type:', typeof lastChatResponse.data.stac_results.results);
            console.log('🗺️ MapView: Results keys:', Object.keys(lastChatResponse.data.stac_results.results));
            console.log('🗺️ MapView: Full results object:', lastChatResponse.data.stac_results.results);
          } else {
            console.log('🗺️ MapView: ❌ No features or results in stac_results');
            console.log('🗺️ MapView: Available keys:', Object.keys(lastChatResponse.data.stac_results));
          }
        } else {
          console.log('🗺️ MapView: ❌ No stac_results in data');
        }
      } else {
        console.log('🗺️ MapView: ❌ No data object in response');
      }

      // Only process STAC results - no hardcoded fallbacks allowed

      // Check for STAC results structure from the API
      if (lastChatResponse.data && lastChatResponse.data.stac_results) {
        console.log('🗺️ MapView: Found STAC results structure');
        console.log('🗺️ MapView: STAC results object:', lastChatResponse.data.stac_results);

        const stacResults = lastChatResponse.data.stac_results;

        // Handle multiple possible data structures
        let features = null;

        // Case 1: Direct features array (current API format)
        if (stacResults.features && Array.isArray(stacResults.features)) {
          features = stacResults.features;
          console.log('🗺️ MapView: ✅ Found direct features array with', features.length, 'STAC features');
        }
        // Case 2: results.features format (legacy)
        else if (stacResults.results && stacResults.results.features && Array.isArray(stacResults.results.features)) {
          features = stacResults.results.features;
          console.log('🗺️ MapView: ✅ Found results.features array with', features.length, 'STAC features');
        }
        // Case 3: FeatureCollection format
        else if (stacResults.results && stacResults.results.type === 'FeatureCollection' && stacResults.results.features) {
          features = stacResults.results.features;
          console.log('🗺️ MapView: ✅ Found FeatureCollection with', features.length, 'STAC features');
        }
        // Case 4: Direct results array
        else if (stacResults.results && Array.isArray(stacResults.results)) {
          features = stacResults.results;
          console.log('🗺️ MapView: ✅ Found direct results array with', features.length, 'features');
        }

        if (features && features.length > 0) {

          // Calculate overall bounding box from all features
          let overallBbox = null;
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
                  console.warn('🗺️ MapView: ⚠️ Skipping feature with invalid bbox coordinates:', feature.bbox);
                }
              }
            });

            if (minLng !== Infinity && isFinite(minLng) && isFinite(minLat) && isFinite(maxLng) && isFinite(maxLat)) {
              overallBbox = [minLng, minLat, maxLng, maxLat];
              console.log('🗺️ MapView: ✅ Calculated valid overall bbox:', overallBbox);
            } else {
              console.warn('🗺️ MapView: ⚠️ Could not calculate valid overall bbox from features');
            }
          }

          // Create satellite data structure
          const newSatelliteData: SatelliteData = {
            bbox: overallBbox,
            items: features.map((feature: any) => {
              const collection = feature.collection || 'sentinel-2-l2a';
              const itemId = feature.id;

              // Find visual asset or preview link
              let previewUrl = null;
              let tileUrl = null;

              if (feature.links) {
                const previewLink = feature.links.find((link: any) => link.rel === 'preview');
                if (previewLink) {
                  previewUrl = previewLink.href;
                }
              }

              // Generate optimized tile URLs using collection-aware system (only if we don't have one from tilejson)
              console.log('🗺️ MapView: [DEBUG] Before fallback generation - tileUrl:', tileUrl);
              console.log('🗺️ MapView: [DEBUG] Collection:', collection, 'ItemId:', itemId);
              console.log('🗺️ MapView: [DEBUG] Should generate fallback?', !!(collection && itemId && !tileUrl));

              if (collection && itemId && !tileUrl) {
                try {
                  tileUrl = TileUrlGenerator.generateItemTileUrl({
                    collection,
                    item: itemId
                  });

                  console.log(`🗺️ MapView: Generated fallback tile URL for ${collection}:${itemId}:`, tileUrl);
                } catch (error) {
                  console.warn(`🗺️ MapView: Failed to generate fallback tile URL for ${collection}, using simple fallback:`, error);
                  // Use simple fallback URL without complex parameters
                  tileUrl = `https://planetarycomputer.microsoft.com/api/data/v1/item/tiles/WebMercatorQuad/{z}/{x}/{y}@1x?collection=${collection}&item=${itemId}&assets=visual&format=png`;
                }
              }

              // Generate preview URL if needed
              if (collection && itemId && !previewUrl) {
                try {
                  previewUrl = TileUrlGenerator.generatePreviewUrl({
                    collection,
                    item: itemId
                  });
                } catch (error) {
                  console.warn(`🗺️ MapView: Failed to generate preview URL for ${collection}:`, error);
                  previewUrl = `https://planetarycomputer.microsoft.com/api/data/v1/item/preview.png?collection=${collection}&item=${itemId}&assets=visual&format=png`;
                }
              }

              if (tileUrl) {
                console.log(`🗺️ MapView: ✅ Using tile URL for ${collection}:${itemId}:`, tileUrl);
              }

              return {
                id: itemId,
                collection: collection,
                datetime: feature.properties?.datetime || new Date().toISOString(),
                preview: previewUrl,
                tile_url: tileUrl,
                bbox: feature.bbox
              };
            }),
            preview_url: features[0] ? (() => {
              try {
                return TileUrlGenerator.generatePreviewUrl({
                  collection: features[0].collection || 'sentinel-2-l2a',
                  item: features[0].id
                });
              } catch (error) {
                console.warn('🗺️ MapView: Failed to generate preview URL, using fallback:', error);
                return `https://planetarycomputer.microsoft.com/api/data/v1/item/preview.png?collection=${features[0].collection || 'sentinel-2-l2a'}&item=${features[0].id}&assets=visual&format=png`;
              }
            })() : undefined,
            // CRITICAL FIX: Preserve tilejson URL if we already found one, don't overwrite with fallback
            tile_url: (() => {
              // Check if we already have a valid tilejson URL from the first feature processing
              if (features[0]?.assets?.tilejson?.href) {
                console.log('🗺️ MapView: [FIX] Preserving tilejson URL from assets:', features[0].assets.tilejson.href);
                return features[0].assets.tilejson.href;
              }

              // Otherwise generate fallback tile template URL
              if (features[0]) {
                try {
                  const fallbackUrl = TileUrlGenerator.generateItemTileUrl({
                    collection: features[0].collection || 'sentinel-2-l2a',
                    item: features[0].id
                  });
                  console.log('🗺️ MapView: [FIX] Using fallback tile template URL:', fallbackUrl);
                  return fallbackUrl;
                } catch (error) {
                  console.warn('🗺️ MapView: Failed to generate tile URL, using simple fallback:', error);
                  return `https://planetarycomputer.microsoft.com/api/data/v1/item/tiles/WebMercatorQuad/{z}/{x}/{y}@1x?collection=${features[0].collection || 'sentinel-2-l2a'}&item=${features[0].id}&assets=visual&format=png`;
                }
              }
              return undefined;
            })()
          };

          setSatelliteData(newSatelliteData);
          console.log('🗺️ MapView: Set STAC satellite data for map visualization:', newSatelliteData);

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
            const collection = id.split(':')[0] || 'sentinel-2-l2a';
            const item = id.split(':')[1];

            try {
              return {
                id,
                collection,
                datetime: lastChatResponse.date_range?.start_date || new Date().toISOString(),
                preview: TileUrlGenerator.generatePreviewUrl({ collection, item }),
                tile_url: TileUrlGenerator.generateItemTileUrl({ collection, item })
              };
            } catch (error) {
              console.warn(`MapView: Failed to generate URLs for ${collection}:${item}, using fallback`);
              return {
                id,
                collection,
                datetime: lastChatResponse.date_range?.start_date || new Date().toISOString(),
                preview: `https://planetarycomputer.microsoft.com/api/data/v1/item/preview.png?collection=${collection}&item=${item}&assets=visual&format=png`,
                tile_url: `https://planetarycomputer.microsoft.com/api/data/v1/mosaic/tiles/WebMercatorQuad/{z}/{x}/{y}@1x?collection=${collection}&item=${item}&assets=visual&format=png`
              };
            }
          }),
          preview_url: itemId ? TileUrlGenerator.generatePreviewUrl({ collection: collectionId, item: itemId }) :
            `https://planetarycomputer.microsoft.com/api/data/v1/item/preview.png?collection=${collectionId}&item=${itemId}&assets=visual&format=png`,
          tile_url: itemId ? TileUrlGenerator.generateItemTileUrl({ collection: collectionId, item: itemId }) :
            `https://planetarycomputer.microsoft.com/api/data/v1/mosaic/tiles/WebMercatorQuad/{z}/{x}/{y}@1x?collection=${collectionId}&item=${itemId}&assets=visual&format=png`
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
              console.error(`❌ Invalid coordinate value: "${cleaned}" -> ${parsed}`);
              return null;
            }
            return parsed;
          });

          // Check if any coordinates failed to parse
          if (parsedBbox.includes(null) || parsedBbox.length !== 4) {
            console.error('❌ Failed to parse valid bbox coordinates:', bboxMatch[0], '-> parsed:', parsedBbox);
          } else {
            const data: SatelliteData = {
              bbox: parsedBbox as number[],
              items: [],
              preview_url: tileUrls.find((url: string) => url.includes('/preview')) || tileUrls[0],
              tile_url: tileUrls.find((url: string) => url.includes('/tiles/')) || tileUrls.find((url: string) => url.includes('/tile/'))
            };

            console.log('✅ Successfully parsed satellite data with bbox:', parsedBbox);
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
        console.log('🗺️ MapView: Updating map view with bbox:', bbox, 'provider:', mapProvider);

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

        // Validate coordinate ranges
        if (west < -180 || west > 180 || east < -180 || east > 180) {
          throw new Error(`Invalid longitude values: west=${west}, east=${east}`);
        }
        if (south < -90 || south > 90 || north < -90 || north > 90) {
          throw new Error(`Invalid latitude values: south=${south}, north=${north}`);
        }
        if (west >= east || south >= north) {
          throw new Error(`Invalid bbox bounds: west=${west} >= east=${east} or south=${south} >= north=${north}`);
        }

        if (mapProvider === 'azure') {
          // Azure Maps API expects [west, south, east, north] format
          console.log('🗺️ MapView: Setting Azure Maps camera to bounds:', [west, south, east, north]);
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

        console.log('✅ Updated map view to bbox:', bbox, 'using provider:', mapProvider);
      } catch (error) {
        console.error('❌ Error updating map view:', error);
      }
    }
  };

  // Fetch Azure Maps configuration
  useEffect(() => {
    const fetchMapsConfig = async () => {
      console.log('🗺️ MapView: Starting config fetch process...');

      // Get the subscription key from environment variables
      const azureMapsKey = import.meta.env.VITE_AZURE_MAPS_SUBSCRIPTION_KEY;

      console.log('🗺️ MapView: Environment variable debug:', {
        rawKey: azureMapsKey,
        keyExists: !!azureMapsKey,
        keyLength: azureMapsKey?.length || 0,
        keyPreview: azureMapsKey ? `${azureMapsKey.substring(0, 12)}...${azureMapsKey.slice(-8)}` : 'not found',
        allEnvVars: Object.keys(import.meta.env).filter(key => key.includes('AZURE'))
      });

      if (azureMapsKey && azureMapsKey.length > 20) {
        console.log('🗺️ MapView: ✅ Using Azure Maps key from environment');
        setMapsConfig({
          subscriptionKey: azureMapsKey,
          style: 'satellite_road_labels',
          zoom: 4,
          center: [-98.5795, 39.8282] // Center on United States
        });
        return;
      } else {
        console.error('🗺️ MapView: ❌ VITE_AZURE_MAPS_SUBSCRIPTION_KEY not found or invalid in environment variables');
        console.error('🗺️ MapView: Expected valid subscription key but got:', azureMapsKey);
        setMapError('Azure Maps subscription key not properly configured in .env file');
        return;
      }
    };

    fetchMapsConfig();
  }, []);  // Initialize Azure Maps
  useEffect(() => {
    console.log('🗺️ MapView: Azure Maps useEffect triggered');
    console.log('  - mapRef.current exists:', !!mapRef.current);
    console.log('  - mapRef.current:', mapRef.current);
    console.log('  - map exists:', !!map);
    console.log('  - map value:', map);
    console.log('  - mapsConfig exists:', !!mapsConfig);
    console.log('  - mapsConfig value:', mapsConfig);

    if (!mapRef.current || !mapsConfig) {
      console.log('🗺️ MapView: Skipping Azure Maps initialization');
      console.log('  - Skip reason:', !mapRef.current ? 'mapRef.current is null/undefined' : 'mapsConfig not loaded yet');
      console.log('  - mapRef.current:', mapRef.current);
      console.log('  - mapsConfig:', mapsConfig);
      return;
    }

    // If we already have a map, check if it's Azure Maps
    if (map && mapProvider === 'azure') {
      console.log('🗺️ MapView: Azure Maps already initialized, skipping');
      return;
    }

    // If we have a Leaflet map, we'll try to replace it with Azure Maps
    if (map && mapProvider === 'leaflet') {
      console.log('🗺️ MapView: Attempting to replace Leaflet with Azure Maps...');
    }

    // Enhanced debugging for Azure Maps SDK availability
    console.log('🗺️ MapView: Azure Maps initialization debug:', {
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
        console.log('🗺️ MapView: ✅ Azure Maps SDK fully available - initializing...');
        console.log('🗺️ MapView: Atlas object:', {
          hasMap: !!window.atlas.Map,
          hasAuthenticationType: !!window.atlas.AuthenticationType,
          hasControl: !!window.atlas.control,
          hasSource: !!window.atlas.source,
          version: window.atlas.getVersion ? window.atlas.getVersion() : 'unknown'
        });

        // Clear existing map if replacing Leaflet
        if (map && mapProvider === 'leaflet') {
          console.log('🗺️ MapView: Clearing existing Leaflet map to make room for Azure Maps');
          try {
            map.remove();
          } catch (e) {
            console.log('🗺️ MapView: Error removing Leaflet map:', e);
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
          style: 'satellite_road_labels', // Start with satellite view with road labels for excellent Earth observation
          showBuildingModels: false, // Disable 3D for better performance
          showLogo: false,
          showFeedbackLink: false,
          enableInertia: true, // Smooth zoom and pan
          showTileBoundaries: false // Hide tile boundaries for cleaner look
        };

        // Add authentication if available
        if (mapsConfig?.subscriptionKey && mapsConfig.subscriptionKey !== 'your-azure-maps-subscription-key-here') {
          // Validate subscription key format (Azure Maps keys are typically 64-88 characters)
          if (mapsConfig.subscriptionKey.length >= 60 && mapsConfig.subscriptionKey.length <= 100) {
            mapConfig.authOptions = {
              authType: window.atlas.AuthenticationType.subscriptionKey,
              subscriptionKey: mapsConfig.subscriptionKey
            };
            console.log('🗺️ MapView: ✅ Using Azure Maps subscription key authentication');
            console.log('🗺️ MapView: Key length:', mapsConfig.subscriptionKey.length);
            console.log('🗺️ MapView: Key starts with:', mapsConfig.subscriptionKey.substring(0, 8) + '...');
            console.log('🗺️ MapView: Key ends with:', '...' + mapsConfig.subscriptionKey.substring(-8));
            console.log('🗺️ MapView: AuthType:', mapConfig.authOptions.authType);
          } else {
            console.error('🗺️ MapView: ⚠️ Unusual subscription key length - will try anyway:', mapsConfig.subscriptionKey.length);
            mapConfig.authOptions = {
              authType: window.atlas.AuthenticationType.subscriptionKey,
              subscriptionKey: mapsConfig.subscriptionKey
            };
          }
        } else {
          console.warn('🗺️ MapView: ⚠️ Azure Maps subscription key not available or placeholder');
          console.log('🗺️ MapView: Available key:', mapsConfig?.subscriptionKey ? `present (${mapsConfig.subscriptionKey.substring(0, 8)}...)` : 'not present');
          console.log('🗺️ MapView: Will attempt anonymous access (limited functionality)');
          // Try without authentication - Azure Maps may work with limited functionality
        }

        console.log('🗺️ MapView: Creating Azure Maps instance with config:', mapConfig);
        const newMap = new window.atlas.Map(mapRef.current, mapConfig);
        console.log('🗺️ MapView: ✅ Azure Maps instance created successfully');

        // Enhanced error handling for source loading issues
        newMap.events.add('error', (error: any) => {
          console.warn('🗺️ MapView: Azure Maps error event:', error);
          // Don't fail the whole map for individual source errors
        });

        // Set up a timeout to catch if the map never loads
        let mapInitialized = false;

        const initTimeout = setTimeout(() => {
          if (!mapInitialized) {
            console.error('🗺️ MapView: ❌ Azure Maps failed to initialize within 15 seconds');
            setMapError('Azure Maps initialization timeout - check subscription key and network connectivity');
          }
        }, 15000);

        // Wait for the map to be ready
        newMap.events.add('ready', () => {
          mapInitialized = true;
          clearTimeout(initTimeout);
          console.log('🗺️ MapView: ✅ Azure Maps is ready and centered on United States');

          try {
            // Add zoom controls
            newMap.controls.add(new window.atlas.control.ZoomControl(), {
              position: 'bottom-right'
            });

            // Add compass control
            newMap.controls.add(new window.atlas.control.CompassControl(), {
              position: 'bottom-right'
            });

            // Add style control for switching map styles with better text visibility options
            newMap.controls.add(new window.atlas.control.StyleControl({
              mapStyles: [
                'road',                    // Clear road map with excellent text visibility
                'road_shaded_relief',      // Road map with topography, good text visibility  
                'satellite_road_labels',   // Satellite with road labels (for reference)
                'grayscale_light',         // Light grayscale for minimal distraction
                'satellite',               // Pure satellite (no text overlay issues)
                'night'                    // Dark theme option
              ],
              layout: 'list' // Use dropdown layout for better UX
            }), {
              position: 'top-right'
            });

            // Set map state AFTER map is fully ready
            setMapProvider('azure');
            setMapError(null);
            setMapLoaded(true);
            console.log('🗺️ MapView: ✅ Azure Maps fully configured and ready');

          } catch (controlError) {
            console.error('🗺️ MapView: Error adding controls:', controlError);
            // Even if controls fail, mark map as loaded
            setMapProvider('azure');
            setMapError(null);
            setMapLoaded(true);
          }
        });

        // Add error handling
        newMap.events.add('error', (error: any) => {
          console.error('🗺️ MapView: ❌ Azure Maps error:', error);
          console.error('🗺️ MapView: Error details:', {
            message: error.message,
            type: error.type,
            target: error.target,
            error: error.error
          });
          setMapError(`Azure Maps failed: ${error.message || error.type || 'Unknown error'}`);
        });

        // Add authentication error handling
        newMap.events.add('authenticationFailed', (error: any) => {
          console.error('🗺️ MapView: ❌ Azure Maps authentication failed:', error);
          console.error('🗺️ MapView: Auth error details:', {
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
            // Only log critical source failures, ignore common bing source issues
            const sourceId = e.source?.id || 'unknown';
            if (!sourceId.includes('bing-') && !sourceId.includes('traffic') && !sourceId.includes('satellite-base')) {
              console.warn('🗺️ MapView: ⚠️ Critical map source failed to load:', {
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
                console.error('🗺️ MapView: ❌ Microsoft Planetary Computer tile source failed to load');
                console.error('🗺️ MapView: Failed URL:', e.source.url);
              }
            }
          }
        });

        // Enhanced WebGL error handling to prevent null value errors
        newMap.events.add('error', (error: any) => {
          // Handle specific WebGL null value errors
          if (error.message && error.message.includes('Expected value to be of type number, but found null')) {
            console.warn('🗺️ MapView: ⚠️ WebGL geometry buffer error (handled):', error.message);
            // Don't let WebGL errors break the entire map
            return;
          }

          // Handle other errors normally
          console.warn('🗺️ MapView: Azure Maps error event:', error);
        });

        // Add global error suppression for Azure Maps WebGL geometry issues
        const originalConsoleError = console.error;
        const suppressedErrors = [
          'Expected value to be of type number, but found null',
          'WebGL',
          'geometry buffer',
          'atlas layer'
        ];
        
        window.addEventListener('error', (event) => {
          const message = event.message || '';
          if (suppressedErrors.some(pattern => message.includes(pattern))) {
            console.log('🗺️ MapView: ⚠️ Suppressed thermal rendering error:', message);
            event.preventDefault();
            return false;
          }
        });

        // Suppress console errors that match the WebGL pattern
        console.error = function(...args) {
          const message = args.join(' ');
          if (suppressedErrors.some(pattern => message.includes(pattern))) {
            console.log('🗺️ MapView: ⚠️ Suppressed thermal console error:', message);
            return;
          }
          originalConsoleError.apply(console, args);
        };

        // Add style data loading event to ensure map is fully ready
        newMap.events.add('styledata', (e: any) => {
          if (e.dataType === 'style') {
            console.log('🗺️ MapView: ✅ Azure Maps style loaded successfully');
          }
        });

        // Add token error handling
        newMap.events.add('tokenacquired', () => {
          console.log('🗺️ MapView: ✅ Azure Maps token acquired successfully');
        });

        newMap.events.add('tokenrenewalfailed', (error: any) => {
          console.error('🗺️ MapView: ❌ Azure Maps token renewal failed:', error);
          setMapError('Azure Maps token renewal failed - subscription may be expired');
        });

        setMap(newMap);
      } catch (error) {
        console.error('🗺️ MapView: Error initializing Azure Maps:', error);
        setMapError(`Failed to initialize Azure Maps: ${error instanceof Error ? error.message : 'Unknown error'}`);
        // Initialize fallback map
        initializeFallbackMap();
      }
    } else {
      console.error('🗺️ MapView: Azure Maps SDK not loaded - attempting retry in 2 seconds');
      console.log('🗺️ MapView: Will retry Azure Maps initialization...');

      // Try waiting for the SDK to load asynchronously
      const retryTimeout = setTimeout(() => {
        console.log('🗺️ MapView: Retry attempt - checking Azure Maps SDK again:', {
          windowExists: typeof window !== 'undefined',
          atlasExists: typeof window !== 'undefined' && !!window.atlas,
          atlasType: typeof window !== 'undefined' ? typeof window.atlas : 'N/A',
          scriptsInDOM: Array.from(document.scripts).filter(s => s.src.includes('atlas')).length
        });

        if (typeof window !== 'undefined' && window.atlas) {
          console.log('🗺️ MapView: Azure Maps SDK now available - initializing...');
          // Trigger re-render to try initialization again
          setMapError(null);
        } else {
          console.error('🗺️ MapView: Azure Maps SDK still not available after retry - using fallback');
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

  // Add satellite imagery to map when data is available
  useEffect(() => {
    console.log('🗺️ MapView: Satellite data rendering useEffect triggered');
    console.log('🗺️ MapView: Checking requirements:', {
      hasSatelliteData: !!satelliteData,
      hasMap: !!map,
      mapLoaded,
      mapProvider,
      satelliteDataDetails: satelliteData ? 'Present' : 'Missing',
      mapDetails: map ? 'Present' : 'Missing'
    });

    if (!satelliteData || !map) {
      console.log('🗺️ MapView: Skipping satellite data rendering - missing basic requirements');
      return;
    }

    // Allow rendering even if mapLoaded is false for Azure Maps, as it might be ready
    if (mapProvider === 'leaflet' && !mapLoaded) {
      console.log('🗺️ MapView: Skipping satellite data rendering - Leaflet map not loaded yet');
      return;
    }

    console.log('🗺️ MapView: ✅ Requirements met - proceeding with satellite data rendering');
    console.log('🗺️ MapView: Adding satellite data to map:', satelliteData);
    console.log('🗺️ MapView: Current mapProvider:', mapProvider);
    console.log('🗺️ MapView: Map instance type:', map?.constructor?.name || 'unknown');

    try {
      if (mapProvider === 'azure') {
        // Azure Maps implementation
        // Remove existing satellite layer if any
        if (currentLayer) {
          console.log('🗺️ MapView: Removing existing Azure Maps layer');
          map.layers.remove(currentLayer);
          setCurrentLayer(null);
        }

        // Clear all custom tile layers to prevent conflicts
        const allLayers = map.layers.getLayers();
        allLayers.forEach((layer: any) => {
          if (layer.getId && (layer.getId().includes('satellite-tiles') || layer.getId().includes('planetary-computer'))) {
            console.log('🗺️ MapView: Removing conflicting layer:', layer.getId());
            map.layers.remove(layer);
          }
        });

        // If we have a tile URL, add it as a tile layer
        if (satelliteData.tile_url && window.atlas) {
          console.log('🗺️ MapView: Adding Azure Maps tile layer:', satelliteData.tile_url);

          // Ensure map is ready before adding layers
          const addTileLayer = () => {
            try {
              // Check if map is properly initialized
              if (!map) {
                console.log('🗺️ MapView: No map instance, skipping tile layer...');
                return;
              }

              console.log('🗺️ MapView: Map available, adding tile layer...');
              console.log('🗺️ MapView: Satellite data bbox:', satelliteData.bbox);
              console.log('🗺️ MapView: Tile URL template:', satelliteData.tile_url);

              // === MICROSOFT PLANETARY COMPUTER APPROACH ===
              // Based on MPC's setupRasterTileLayer function, we should use TileJSON URLs directly
              // instead of extracting tile templates. This lets Azure Maps handle coordinate calculations.
              console.log('🗺️ MapView: [MPC-APPROACH] Using Microsoft Planetary Computer approach with TileJSON URL');

              const tileUrl = satelliteData.tile_url;
              const bounds = satelliteData.bbox;

              // Safety check for tileUrl
              if (!tileUrl) {
                console.log('🗺️ MapView: [ERROR] No tile URL available');
                return;
              }

              // Check if this is a TileJSON URL or tile template
              const isTileTemplate = tileUrl.includes('{z}') && tileUrl.includes('{x}') && tileUrl.includes('{y}');

              console.log('🗺️ MapView: [MPC-APPROACH] URL analysis:', {
                url: tileUrl.substring(0, 150) + '...',
                isTileTemplate: isTileTemplate,
                approach: isTileTemplate ? 'Authenticated tile template (MPC approach)' : 'TileJSON URL (needs processing)'
              });

              let tileLayerConfig: any;

              // Detect elevation/DEM data for special opacity handling
              const isElevationData = satelliteData.items && satelliteData.items.length > 0 && (
                satelliteData.items[0].collection.includes('cop-dem') ||
                satelliteData.items[0].collection.includes('nasadem') ||
                satelliteData.items[0].collection.includes('alos-dem') ||
                satelliteData.items[0].collection.includes('dem') ||
                satelliteData.items[0].collection.toLowerCase().includes('elevation')
              );

              // Detect thermal infrared data for special rendering
              const isThermalData = tileUrl.includes('assets=lwir') || 
                                   tileUrl.includes('colormap_name=') || 
                                   tileUrl.includes('rescale=');

              // Set opacity based on data type for optimal text visibility
              const baseOpacity = isElevationData ? 0.5 : 0.65; // Lower opacity for elevation data
              console.log(`🗺️ MapView: Using opacity ${baseOpacity} for ${isElevationData ? 'elevation' : isThermalData ? 'thermal' : 'standard'} data (collection: ${satelliteData.items?.[0]?.collection})`);

              if (isThermalData) {
                console.log('🔥 MapView: [THERMAL] Detected thermal infrared data - applying thermal-specific layer configuration');
              }

              if (isTileTemplate) {
                // === MICROSOFT'S APPROACH: Use authenticated tile template directly ===
                console.log('🗺️ MapView: [MPC-APPROACH] Using authenticated tile template directly (Microsoft approach)');

                // Use different zoom constraints based on data type
                const isMODISData = satelliteData.items[0]?.collection?.toLowerCase().includes('modis');
                const minZoom = isMODISData ? 0 : 6; // MODIS data often sparse, start from zoom 0
                const maxZoom = isMODISData ? 4 : 20; // MODIS rarely has tiles above zoom 4, limit to prevent 404s

                console.log(`🗺️ MapView: [ZOOM-FIX] Using minZoom ${minZoom}, maxZoom ${maxZoom} for ${isMODISData ? 'MODIS' : 'standard'} data`);

                // More restrictive bounds for MODIS to prevent geometry errors
                const tileBounds = bounds && Array.isArray(bounds) && bounds.length === 4 &&
                  bounds.every(coord => coord !== null && !isNaN(coord) && isFinite(coord))
                  ? [bounds[0], bounds[1], bounds[2], bounds[3]]
                  : undefined;

                if (bounds && !tileBounds) {
                  console.warn('🗺️ MapView: ⚠️ Invalid bounds detected, not setting tile bounds:', bounds);
                }

                tileLayerConfig = {
                  tileUrl: tileUrl,
                  opacity: baseOpacity, // Dynamic opacity based on data type for better text visibility
                  tileSize: 256,
                  bounds: tileBounds,
                  minSourceZoom: minZoom,
                  maxSourceZoom: maxZoom,
                  tileLoadRadius: isMODISData ? 0 : 1, // Reduce tile loading radius for MODIS to prevent errors
                  // Enhanced rendering for better text visibility and stability
                  blend: 'normal', // Normal blending to allow text to show through
                  // Add error handling options for MODIS data
                  fadeDuration: isMODISData ? 0 : 300, // Reduce fade for MODIS to minimize rendering issues
                  rasterOpacity: baseOpacity, // Explicit raster opacity
                  // Thermal-specific configuration to handle null values
                  ...(isThermalData && {
                    noDataValue: null, // Explicitly handle null values for thermal data
                    interpolate: false, // Disable interpolation to prevent null value errors
                    resample: 'nearest', // Use nearest neighbor resampling for thermal data
                    // Additional WebGL error mitigation
                    errorTolerance: 0.1, // Allow some rendering errors without failing
                    ignoreDataErrors: true // Continue rendering even with bad data points
                  })
                };
              } else {
                // === ENHANCED FALLBACK: Optimized configuration for radar imagery ===
                console.log('🗺️ MapView: [ENHANCED FALLBACK] Using optimized radar imagery configuration');

                tileLayerConfig = {
                  tileUrl: tileUrl,
                  opacity: baseOpacity, // Dynamic opacity based on data type for better text visibility
                  tileSize: 256,
                  // Enhanced error handling for better stability
                  bounds: satelliteData.bbox && Array.isArray(satelliteData.bbox) && satelliteData.bbox.length === 4 &&
                    satelliteData.bbox.every(coord => coord !== null && !isNaN(coord) && isFinite(coord))
                    ? [satelliteData.bbox[0], satelliteData.bbox[1], satelliteData.bbox[2], satelliteData.bbox[3]]
                    : undefined,
                  minSourceZoom: 0, // Allow full zoom range
                  maxSourceZoom: 20, // Extended maximum zoom for detailed inspection
                  // Improve rendering performance and text visibility
                  fadeIn: true,
                  tileLoadRadius: 2, // Load more surrounding tiles for smoother experience
                  blend: 'normal' // Normal blending mode for better text preservation
                };
              }

              console.log('🗺️ MapView: [DEBUG] Creating Azure Maps TileLayer with config:', tileLayerConfig);
              console.log('🗺️ MapView: [DEBUG] tileUrl type:', typeof tileUrl);
              console.log('🗺️ MapView: [DEBUG] tileUrl length:', tileUrl?.length);
              console.log('🗺️ MapView: [DEBUG] tileUrl starts with https:', tileUrl?.startsWith('https://'));
              console.log('🗺️ MapView: [DEBUG] atlas.layer.TileLayer available:', typeof window.atlas.layer.TileLayer);

              let tileLayer: any;
              try {
                tileLayer = new window.atlas.layer.TileLayer(tileLayerConfig, `planetary-computer-tiles-${Date.now()}`);
                console.log('🗺️ MapView: [DEBUG] TileLayer instance created successfully');
              } catch (error) {
                console.error('🗺️ MapView: [ERROR] Failed to create TileLayer:', error);
                return;
              }

              // DEBUGGING: Add event listeners before adding the layer
              console.log('🗺️ MapView: [DEBUG] TileLayer instance created with ID:', tileLayer.getId?.());

              // Listen for source events on the map to understand what's happening
              const sourceLoadHandler = (e: any) => {
                try {
                  console.log('🗺️ MapView: [DEBUG] Source event:', e.type, e);
                  if (e.source && e.source.id) {
                    console.log('🗺️ MapView: [DEBUG] Source ID:', e.source.id);
                    console.log('🗺️ MapView: [DEBUG] Source type:', e.source.type);
                  }

                  // Log specific errors for troubleshooting
                  if (e.type === 'error') {
                    console.error('🗺️ MapView: [ERROR] Source error event:', e);
                  }

                  // Check for failed source loading
                  if (e.type === 'sourcedata' && e.isSourceLoaded === false && e.sourceDataType === 'metadata') {
                    console.log('🗺️ MapView: ⚠️ Critical map source failed to load:', {
                      sourceId: e.source?.id || 'unknown',
                      sourceType: e.source?.type || 'unknown',
                      type: e.type,
                      sourceDataType: e.sourceDataType,
                      isSourceLoaded: e.isSourceLoaded,
                      tile: e.tile
                    });
                  }
                } catch (handlerError) {
                  console.error('🗺️ MapView: [ERROR] Source handler error:', handlerError);
                }
              };

              // Add error handler for map errors
              const errorHandler = (e: any) => {
                console.error('🗺️ MapView: [ERROR] Map error event:', e);
              };

              map.events.add('sourcedata', sourceLoadHandler);
              map.events.add('sourcedataloading', sourceLoadHandler);
              map.events.add('error', errorHandler);

              console.log('🗺️ MapView: [DEBUG] Adding tile layer to map...');
              map.layers.add(tileLayer);
              setCurrentLayer(tileLayer);

              console.log('✅ MapView: Successfully added Azure Maps tile layer with zoom constraints');

              // Zoom to the satellite data area with appropriate zoom level
              if (satelliteData.bbox && Array.isArray(satelliteData.bbox) && satelliteData.bbox.length === 4) {
                let [west, south, east, north] = satelliteData.bbox;
                console.log('🗺️ MapView: Original satellite data bounds:', { west, south, east, north });

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

                console.log('🗺️ MapView: Original query for region detection:', originalQuery);

                // ENHANCED: Use backend-resolved location bounds instead of hardcoded coordinates
                const bboxWidth = Math.abs(east - west);
                const bboxHeight = Math.abs(north - south);
                const isLargeBbox = bboxWidth > 2 || bboxHeight > 2; // Large area covering multiple cities/regions

                console.log('🗺️ MapView: Bbox analysis:', {
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
                    console.log('🗺️ MapView: ✅ Using backend-resolved location bounds:', backendResolvedBounds);
                  }
                }

                // Use backend-resolved bounds if available and more precise than satellite data bounds
                if (backendResolvedBounds && isLargeBbox) {
                  console.log('🗺️ MapView: ✅ Applying backend-resolved bounds for precise location focus');
                  west = backendResolvedBounds.west;
                  south = backendResolvedBounds.south;
                  east = backendResolvedBounds.east;
                  north = backendResolvedBounds.north;
                  console.log('🗺️ MapView: ✅ Applied backend location resolution for precise coordinates');
                } else if (backendResolvedBounds) {
                  console.log('🗺️ MapView: Backend bounds available but satellite data bbox is already focused, using satellite bounds');
                } else {
                  console.log('🗺️ MapView: Using original satellite data bounds (no backend location resolution found)');
                }

                console.log('🗺️ MapView: Final bounds for map view:', { west, south, east, north });

                // Update satelliteData.bbox with the region-specific bounds for consistent use throughout
                satelliteData.bbox = [west, south, east, north];
                console.log('🗺️ MapView: ✅ Updated satelliteData.bbox with region-specific bounds');

                // Smart zoom calculation for optimal radar imagery visibility
                const finalBboxWidth = Math.abs(east - west);
                const finalBboxHeight = Math.abs(north - south);
                const bboxArea = finalBboxWidth * finalBboxHeight;

                // Enhanced zoom calculation for better satellite data visibility
                let targetZoom = 6; // Safe default
                if (bboxArea < 0.1) { // City-level detail
                  targetZoom = isMODISData ? 4 : 12; // MODIS max zoom 4 to prevent 404s
                } else if (bboxArea < 0.5) { // Metropolitan area
                  targetZoom = isMODISData ? 4 : 10;
                } else if (bboxArea < 2) { // Large metropolitan area
                  targetZoom = isMODISData ? 3 : 8;
                } else if (bboxArea < 10) { // Regional coverage 
                  targetZoom = isMODISData ? 3 : 7;
                } else if (bboxArea < 50) { // State-level coverage
                  targetZoom = isMODISData ? 3 : 6;
                } else { // Multi-state/continental coverage
                  targetZoom = isMODISData ? 2 : 5; // Zoom 2 for large MODIS continental data
                }

                console.log(`🗺️ MapView: Calculated zoom level ${targetZoom} for ${isMODISData ? 'MODIS' : 'standard'} data (bbox area ${bboxArea.toFixed(4)} sq degrees)`);
                console.log('🗺️ MapView: Enhanced zoom calculation for better satellite data visibility');

                try {
                  // Enhanced validation before setCamera to prevent null coordinate errors
                  if (west === null || west === undefined ||
                    south === null || south === undefined ||
                    east === null || east === undefined ||
                    north === null || north === undefined) {
                    throw new Error(`Null coordinate values detected before setCamera: west=${west}, south=${south}, east=${east}, north=${north}`);
                  }

                  // Check for NaN values
                  if (isNaN(west) || isNaN(south) || isNaN(east) || isNaN(north)) {
                    throw new Error(`NaN coordinate values detected before setCamera: west=${west}, south=${south}, east=${east}, north=${north}`);
                  }

                  console.log('🗺️ MapView: Validated coordinates before setCamera:', { west, south, east, north });

                  map.setCamera({
                    bounds: [west, south, east, north],
                    zoom: targetZoom,
                    maxZoom: isMODISData ? 4 : 20, // Restrict max zoom for MODIS to prevent 404s
                    minZoom: isMODISData ? 0 : 2,  // Allow wide overview, start from 0 for MODIS
                    padding: 50,
                    type: 'ease',
                    duration: 2000
                  });
                  console.log('✅ MapView: Successfully zoomed to satellite data area with appropriate zoom level');

                  // Enhanced text visibility management after satellite layer is added
                  const ensureTextVisibility = () => {
                    try {
                      // Check current map style and suggest better alternatives for text visibility
                      const currentStyle = map.getStyle();
                      console.log('🗺️ MapView: Current map style:', currentStyle);

                      // Show style tip for better user experience
                      setShowStyleTip(true);

                      // Auto-hide tip after 8 seconds
                      setTimeout(() => {
                        setShowStyleTip(false);
                      }, 8000);

                      // If using satellite style with overlay, suggest switching to road view
                      if (currentStyle && (currentStyle.includes('satellite') || currentStyle === 'satellite_road_labels')) {
                        console.log('🗺️ MapView: 💡 TIP: Switch to "Road" or "Light Grayscale" style for better text visibility with satellite overlay');
                      }

                      // Add opacity control information
                      console.log('🗺️ MapView: 💡 Satellite layer opacity set to preserve map labels');
                      console.log('🗺️ MapView: 💡 Use style control (top-right) to switch between map styles for optimal viewing');

                    } catch (e) {
                      console.log('🗺️ MapView: Text visibility check completed');
                    }
                  };

                  // Run text visibility check after a short delay to ensure layer is loaded
                  setTimeout(ensureTextVisibility, 1000);

                } catch (cameraError) {
                  console.error('❌ MapView: Error setting camera bounds:', cameraError);
                }
              }

              console.log('✅ MapView: Successfully added Azure Maps satellite tile layer');

            } catch (layerError) {
              console.error('❌ MapView: Error adding Azure Maps tile layer:', layerError);
              console.log('🗺️ MapView: Tile layer addition failed, but continuing...');
            }
          };

          // Try to add tile layer immediately if map is ready
          addTileLayer();
        }

        // If we have map_data GeoJSON, add it as vector data
        if (lastChatResponse?.map_data?.features && window.atlas) {
          console.log('🗺️ MapView: Adding GeoJSON features to Azure Maps');

          const addGeoJsonLayers = () => {
            try {
              // Basic map check
              if (!map) {
                console.log('🗺️ MapView: No map instance for GeoJSON, skipping...');
                return;
              }

              console.log('🗺️ MapView: Adding GeoJSON data source and layers...');

              const dataSource = new window.atlas.source.DataSource();
              map.sources.add(dataSource);

              // Filter out features with null/invalid coordinates
              const validFeatures = lastChatResponse.map_data.features.filter((feature: any) => {
                if (!feature.geometry || !feature.geometry.coordinates) {
                  console.warn('🚨 MapView: Skipping feature with missing geometry:', feature.id || 'unknown');
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
              });

              console.log(`🗺️ MapView: Filtered ${lastChatResponse.map_data.features.length - validFeatures.length} features with invalid coordinates`);
              
              // Add the valid GeoJSON features
              if (validFeatures.length > 0) {
                dataSource.add(validFeatures);
                console.log(`✅ MapView: Added ${validFeatures.length} valid features to data source`);
              } else {
                console.warn('⚠️ MapView: No valid features to display after coordinate filtering');
              }

              // Add polygon layer for search area
              const polygonLayer = new window.atlas.layer.PolygonLayer(dataSource, null, {
                fillColor: 'rgba(0, 0, 255, 0.2)',
                fillOpacity: 0.3
              });

              const lineLayer = new window.atlas.layer.LineLayer(dataSource, null, {
                strokeColor: 'blue',
                strokeWidth: 2
              });

              map.layers.add([polygonLayer, lineLayer]);
              console.log('✅ MapView: Successfully added GeoJSON features to Azure Maps');
            } catch (geoError) {
              console.error('❌ MapView: Error adding GeoJSON to Azure Maps:', geoError);
              // If timing issue, try again after delay
              if (geoError instanceof Error && geoError.message && geoError.message.includes('not ready')) {
                console.log('🗺️ MapView: Retrying GeoJSON addition in 500ms...');
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
        console.log('🗺️ MapView: Using Leaflet provider - verifying map instance');

        // Safety check: ensure we're not trying to use Leaflet methods on Azure Maps
        if (map && map.constructor && map.constructor.name && map.constructor.name.includes('Map') && !map.removeLayer) {
          console.error('❌ MapView: CRITICAL ERROR - mapProvider is "leaflet" but map instance appears to be Azure Maps!');
          console.log('🗺️ MapView: Map constructor:', map.constructor.name);
          console.log('🗺️ MapView: Correcting mapProvider to "azure"');
          setMapProvider('azure');
          return; // Exit and let the effect re-run with correct provider
        }

        // Remove existing satellite layer if any
        if (currentLayer) {
          console.log('🗺️ MapView: Removing existing Leaflet layer');
          map.removeLayer(currentLayer);
          setCurrentLayer(null);
        }

        // If we have a tile URL, add it as a tile layer
        if (satelliteData.tile_url && window.L) {
          console.log('🗺️ MapView: Adding Leaflet tile layer:', satelliteData.tile_url);

          const tileLayer = window.L.tileLayer(satelliteData.tile_url, {
            opacity: 0.8,
            attribution: 'Planetary Computer'
          });

          tileLayer.addTo(map);
          setCurrentLayer(tileLayer);

          console.log('✅ MapView: Successfully added Leaflet satellite tile layer');
        }

        // If we have map_data GeoJSON, add it as vector data
        if (lastChatResponse?.map_data?.features && window.L) {
          console.log('🗺️ MapView: Adding GeoJSON features to Leaflet');

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

          console.log('✅ MapView: Successfully added GeoJSON features to Leaflet');
        }
      }

      // Update view to show the data
      if (satelliteData.bbox) {
        console.log('🗺️ MapView: Updating map view to bbox:', satelliteData.bbox);
        updateMapView(satelliteData.bbox);
      }

    } catch (error) {
      console.error('❌ MapView: Error adding satellite data to map:', error);
    }
  }, [satelliteData, map, mapLoaded, lastChatResponse]);

  // Enhanced dataset visualization using collection config
  const getDatasetVisualization = (dataset: Dataset | null) => {
    if (!dataset) return { emoji: '🗺️', description: 'Interactive satellite map', color: '#f8f9fa' };

    // Use the new collection configuration system
    try {
      const visualization = getCollectionVisualization(dataset.id);
      return {
        emoji: visualization.emoji,
        description: getCollectionConfig(dataset.id)?.description || dataset.description || `${dataset.title} visualization`,
        color: visualization.color
      };
    } catch (error) {
      console.warn('🗺️ MapView: Failed to get collection visualization, using fallback:', error);
      return {
        emoji: '📊',
        description: `${dataset.title} visualization`,
        color: '#f8f9fa'
      };
    }
  };

  const visualization = getDatasetVisualization(selectedDataset);

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
          {!mapsConfig ? (
            <>
              <div style={{ marginBottom: '10px' }}>🗺️ Loading Azure Maps configuration...</div>
              <div style={{ fontSize: '12px', opacity: 0.7 }}>
                Preparing United States view
              </div>
            </>
          ) : (
            <>
              <div style={{ marginBottom: '10px' }}>🛰️ Initializing Azure Maps...</div>
              <div style={{ fontSize: '12px', opacity: 0.7 }}>
                Centering on United States
              </div>
            </>
          )}

          {/* Debug information */}
          <div style={{
            marginTop: '20px',
            padding: '10px',
            background: '#f8f9fa',
            borderRadius: '4px',
            fontSize: '11px',
            color: '#666',
            maxWidth: '300px',
            textAlign: 'left'
          }}>
            <strong>🐛 Debug Info:</strong><br />
            • Azure SDK: {typeof window !== 'undefined' && window.atlas ? '✅ Loaded' : '❌ Missing'}<br />
            • Maps Config: {mapsConfig ? '✅ Loaded' : '❌ Missing'}<br />
            • Container: {mapRef.current ? '✅ Ready' : '❌ Not Ready'}<br />
            • Map Object: {map ? '✅ Created' : '❌ Not Created'}<br />
            • Provider: {mapProvider || 'None'}<br />
            • Error: {mapError || 'None'}<br />
            <div style={{ marginTop: '5px', fontSize: '10px', opacity: 0.7 }}>
              Press F12 to see console logs
            </div>
          </div>
        </div>
      )}

      {/* Map status overlay - only show when map is loaded */}
      {mapLoaded && (
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
          {satelliteData ? (
            <div>
              <div style={{ fontSize: '12px', color: '#666', marginBottom: '2px' }}>
                🛰️ SATELLITE DATA ACTIVE
              </div>
              <div style={{ color: '#333' }}>
                {satelliteData.items?.length || 0} Landsat images found
              </div>
            </div>
          ) : selectedDataset ? (
            <div>
              <div style={{ fontSize: '12px', color: '#666', marginBottom: '2px' }}>
                VIEWING DATASET
              </div>
              <div style={{ color: '#333' }}>{selectedDataset.title}</div>
            </div>
          ) : (
            <div style={{ color: '#333' }}>🇺🇸 United States View</div>
          )}
        </div>
      )}

      {/* Dataset info panel when selected - REMOVED */}

      {/* Text Visibility Tip - shown when satellite data is loaded */}
      {showStyleTip && satelliteData && mapLoaded && (
        <div className={`map-style-tip ${showStyleTip ? 'show' : ''}`}>
          � <strong>Text Hard to Read?</strong><br />
          • Use the style control (top-right) to switch to <strong>"Road"</strong> or <strong>"Road Shaded Relief"</strong><br />
          • These styles provide much better text contrast over satellite imagery<br />
          • Or use <strong>"Satellite"</strong> (no labels) for pure imagery view
        </div>
      )}
    </div>
  );
};

export default MapView;
