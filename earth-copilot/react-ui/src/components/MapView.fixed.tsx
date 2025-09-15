import React, { useEffect, useState, useRef } from 'react';
import { Dataset } from '../services/api';

// Declare global objects for TypeScript
declare global {
  interface Window {
    atlas: any;
    L: any; // Leaflet
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

  // Dataset visualization configuration
  const getDatasetVisualization = (dataset: Dataset | null) => {
    if (!dataset) return { emoji: '🗺️', description: 'Interactive satellite map', color: '#f8f9fa' };
    
    const visualizations: Record<string, { emoji: string; description: string; color: string }> = {
      'landsat-c2-l2': { 
        emoji: '🛰️', 
        description: 'Landsat satellite imagery with 30m resolution',
        color: '#e8f5e8'
      },
      'sentinel-2-l2a': { 
        emoji: '🌿', 
        description: 'High-resolution optical imagery at 10m resolution',
        color: '#e8f8f5'
      },
      'sentinel-1-rtc': { 
        emoji: '📡', 
        description: 'Radar imagery for all-weather monitoring',
        color: '#f8f8ff'
      },
      'modis': { 
        emoji: '🌍', 
        description: 'Daily global climate and ocean monitoring',
        color: '#f0f8ff'
      },
      'viirs-dnb-nighttime': { 
        emoji: '🌙', 
        description: 'Nighttime lights and human activity',
        color: '#f5f5f5'
      },
      'nasadem': { 
        emoji: '⛰️', 
        description: 'High-resolution elevation data at 30m',
        color: '#f8f4e6'
      },
      'daymet-daily-na': { 
        emoji: '🌡️', 
        description: 'Daily weather data across North America',
        color: '#fff8e1'
      },
      'terraclimate': { 
        emoji: '🌧️', 
        description: 'Monthly climate and water balance data',
        color: '#e8f4f8'
      },
      'gbif': { 
        emoji: '🦋', 
        description: 'Global species occurrence data points',
        color: '#f0fff0'
      },
      'aster-l1t': { 
        emoji: '🔍', 
        description: 'Multispectral imagery for mineral analysis',
        color: '#fff8e8'
      },
      'cop-dem-glo-30': { 
        emoji: '🗻', 
        description: 'Global digital elevation model at 30m',
        color: '#f5f5f0'
      }
    };

    return visualizations[dataset.id] || { 
      emoji: '📊', 
      description: `${dataset.title} visualization`,
      color: '#f8f9fa'
    };
  };

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

        // Add OpenStreetMap tile layer
        window.L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
          attribution: '© OpenStreetMap contributors',
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

  // Parse satellite data from chat responses
  useEffect(() => {
    if (!lastChatResponse) return;

    try {
      console.log('🗺️ MapView: Processing chat response:', JSON.stringify(lastChatResponse, null, 2));
      
      // Check for new structured visualization data
      if (lastChatResponse.visualization_data) {
        console.log('MapView: Found structured visualization data');
        
        const vizData = lastChatResponse.visualization_data;
        const newSatelliteData: SatelliteData = {
          bbox: vizData.bbox ? [
            vizData.bbox.west,
            vizData.bbox.south,
            vizData.bbox.east,
            vizData.bbox.north
          ] : null,
          items: vizData.items || [],
          preview_url: vizData.preview_url,
          tile_url: vizData.tile_url
        };
        
        setSatelliteData(newSatelliteData);
        console.log('MapView: Set visualization data for map:', newSatelliteData);
        return;
      }
      
      // Legacy support: Check if this is a structured response with satellite data
      if (lastChatResponse.dataset_ids && lastChatResponse.bbox) {
        console.log('MapView: Found legacy structured satellite data response');
        
        const newSatelliteData: SatelliteData = {
          bbox: [
            lastChatResponse.bbox.west,
            lastChatResponse.bbox.south,
            lastChatResponse.bbox.east,
            lastChatResponse.bbox.north
          ],
          items: lastChatResponse.dataset_ids.map((id: string) => ({
            id,
            collection: id.split(':')[0] || 'sentinel-2-l2a',
            datetime: lastChatResponse.date_range?.start_date || new Date().toISOString(),
            preview: `https://planetarycomputer.microsoft.com/api/data/v1/item/preview.png?collection=${id.split(':')[0]}&item=${id.split(':')[1]}&assets=visual&format=png`,
            tile_url: `https://planetarycomputer.microsoft.com/api/data/v1/mosaic/tiles/WebMercatorQuad/{z}/{x}/{y}@1x?collection=${id.split(':')[0]}&item=${id.split(':')[1]}&assets=visual&format=png`
          })),
          preview_url: `https://planetarycomputer.microsoft.com/api/data/v1/item/preview.png?collection=${lastChatResponse.dataset_ids[0]?.split(':')[0]}&item=${lastChatResponse.dataset_ids[0]?.split(':')[1]}&assets=visual&format=png`,
          tile_url: `https://planetarycomputer.microsoft.com/api/data/v1/mosaic/tiles/WebMercatorQuad/{z}/{x}/{y}@1x?collection=${lastChatResponse.dataset_ids[0]?.split(':')[0]}&item=${lastChatResponse.dataset_ids[0]?.split(':')[1]}&assets=visual&format=png`
        };
        
        setSatelliteData(newSatelliteData);
        console.log('MapView: Set satellite data for map visualization:', newSatelliteData);
        return;
      }
    } catch (error) {
      console.error('Error parsing satellite data:', error);
    }
  }, [lastChatResponse]);

  // Add map update function for bounding box
  const updateMapView = (bbox: number[] | null) => {
    if (map && bbox && bbox.length >= 4) {
      try {
        // Convert bbox to Azure Maps bounds format
        const bounds = [
          [bbox[0], bbox[1]], // southwest
          [bbox[2], bbox[3]]  // northeast
        ];
        
        // Set camera to fit bounds
        map.setCamera({
          bounds: bounds,
          padding: 50
        });
        
        console.log('Updated map view to bbox:', bbox);
      } catch (error) {
        console.error('Error updating map view:', error);
      }
    }
  };

  // Fetch Azure Maps configuration
  useEffect(() => {
    const fetchMapsConfig = async () => {
      // First try to get the subscription key from environment variables
      const azureMapsKey = import.meta.env.VITE_AZURE_MAPS_SUBSCRIPTION_KEY || import.meta.env.AZURE_MAPS_SUBSCRIPTION_KEY;
      
      console.log('🗺️ MapView: Checking for Azure Maps subscription key...');
      console.log('🗺️ MapView: Environment key available:', !!azureMapsKey);
      
      if (azureMapsKey) {
        console.log('🗺️ MapView: Using Azure Maps key from environment');
        setMapsConfig({
          subscriptionKey: azureMapsKey,
          style: 'road',
          zoom: 10,
          center: [-122.4194, 47.6062]
        });
        return;
      }
      
      // Fallback to loading from config file
      try {
        const response = await fetch('/maps-config.json');
        if (!response.ok) {
          throw new Error(`HTTP ${response.status}: ${response.statusText}`);
        }
        const config = await response.json();
        console.log('🗺️ MapView: Loaded maps configuration from file:', config);
        setMapsConfig(config);
      } catch (error) {
        console.error('Failed to fetch maps configuration:', error);
        // Use fallback config without key
        console.log('🗺️ MapView: Using fallback maps configuration (no key)');
        setMapsConfig({
          subscriptionKey: null,
          style: 'road',
          zoom: 10,
          center: [-122.4194, 47.6062]
        });
      }
    };

    fetchMapsConfig();
  }, []);

  // Initialize Azure Maps
  useEffect(() => {
    if (!mapRef.current || map || !mapsConfig) return;

    // Ensure Azure Maps SDK is loaded
    if (typeof window !== 'undefined' && window.atlas) {
      try {
        console.log('🗺️ MapView: Initializing Azure Maps with config:', mapsConfig);
        
        // Initialize the map with default US view
        const mapConfig: any = {
          center: [-98.5795, 39.8282], // Center of United States
          zoom: 4, // Better initial zoom for US view
          language: 'en-US',
          style: 'satellite_road_labels', // Start with satellite view
          showBuildingModels: true,
          showLogo: false,
          showFeedbackLink: false
        };

        // Add authentication if available
        if (mapsConfig?.subscriptionKey && mapsConfig.subscriptionKey !== 'your-azure-maps-subscription-key-here') {
          mapConfig.authOptions = {
            authType: window.atlas.AuthenticationType.subscriptionKey,
            subscriptionKey: mapsConfig.subscriptionKey
          };
          console.log('🗺️ MapView: Using Azure Maps subscription key authentication');
        } else {
          console.warn('🗺️ MapView: Azure Maps subscription key not available or placeholder, map may not load properly');
          console.log('🗺️ MapView: Available key:', mapsConfig?.subscriptionKey ? 'present but placeholder' : 'not present');
        }

        const newMap = new window.atlas.Map(mapRef.current, mapConfig);

        // Wait for the map to be ready
        newMap.events.add('ready', () => {
          console.log('🗺️ MapView: Azure Maps is ready and centered on United States');
          setMapProvider('azure');
          
          // Add data source for future use
          const dataSource = new window.atlas.source.DataSource();
          newMap.sources.add(dataSource);

          // Add zoom controls
          newMap.controls.add(new window.atlas.control.ZoomControl(), {
            position: 'bottom-right'
          });

          // Add pitch control for 3D view
          newMap.controls.add(new window.atlas.control.PitchControl(), {
            position: 'bottom-right'
          });

          // Add compass control
          newMap.controls.add(new window.atlas.control.CompassControl(), {
            position: 'bottom-right'
          });

          // Add style control for switching map styles
          newMap.controls.add(new window.atlas.control.StyleControl({
            mapStyles: ['road', 'satellite', 'satellite_road_labels', 'grayscale_light', 'night']
          }), {
            position: 'top-right'
          });

          setMapLoaded(true);
        });

        // Add error handling
        newMap.events.add('error', (error: any) => {
          console.error('🗺️ MapView: Azure Maps error:', error);
          setMapError(`Azure Maps failed: ${error instanceof Error ? error.message : 'Unknown error'}`);
          // Initialize fallback map
          initializeFallbackMap();
        });

        // Add authentication error handling
        newMap.events.add('authenticationFailed', (error: any) => {
          console.error('🗺️ MapView: Azure Maps authentication failed:', error);
          setMapError('Azure Maps authentication failed - check your subscription key');
          // Initialize fallback map
          initializeFallbackMap();
        });

        setMap(newMap);
      } catch (error) {
        console.error('🗺️ MapView: Error initializing Azure Maps:', error);
        setMapError(`Failed to initialize Azure Maps: ${error instanceof Error ? error.message : 'Unknown error'}`);
        // Initialize fallback map
        initializeFallbackMap();
      }
    } else {
      console.error('🗺️ MapView: Azure Maps SDK not loaded - initializing fallback map');
      setMapError('Azure Maps SDK not available');
      initializeFallbackMap();
    }
  }, [mapsConfig, map]);

  // Render satellite data on map when available
  useEffect(() => {
    if (!map || !mapLoaded || !satelliteData) return;

    console.log('🗺️ MapView: Attempting to render satellite data:', {
      satelliteData: !!satelliteData,
      map: !!map,
      mapLoaded,
      mapProvider
    });

    if (!satelliteData) {
      console.log('🗺️ MapView: Skipping satellite data rendering - no satellite data');
      return;
    }

    if (!map) {
      console.log('🗺️ MapView: Skipping satellite data rendering - no map instance');
      return;
    }

    if (!mapLoaded) {
      console.log('🗺️ MapView: Skipping satellite data rendering - map not loaded');
      return;
    }

    console.log('🗺️ MapView: All requirements met for satellite data rendering');

    try {
      // Remove existing layers if any
      if (currentLayer && map.layers) {
        console.log('🗺️ MapView: Removing existing layer');
        map.layers.remove(currentLayer);
        setCurrentLayer(null);
      }

      // If we have a tile URL, add it as a tile layer
      if (satelliteData.tile_url && window.atlas) {
        console.log('🗺️ MapView: Adding tile layer:', satelliteData.tile_url);
        
        const tileLayer = new window.atlas.layer.TileLayer({
          tileUrl: satelliteData.tile_url,
          opacity: 0.8,
          tileSize: 256
        });
        
        map.layers.add(tileLayer);
        setCurrentLayer(tileLayer);
        
        console.log('✅ MapView: Successfully added satellite tile layer');
      }
      
      // If we have map_data GeoJSON, add it as vector data
      if (lastChatResponse?.map_data?.features && window.atlas) {
        console.log('🗺️ MapView: Adding GeoJSON features to map');
        
        const dataSource = new window.atlas.source.DataSource();
        map.sources.add(dataSource);
        
        // Add the GeoJSON features
        dataSource.add(lastChatResponse.map_data.features);
        
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
        console.log('✅ MapView: Successfully added GeoJSON features');
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

  const visualization = getDatasetVisualization(selectedDataset);

  return (
    <div className="map">
      {!mapLoaded ? (
        <div style={{
          display: 'flex',
          flexDirection: 'column',
          alignItems: 'center',
          justifyContent: 'center',
          height: '100%',
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
        </div>
      ) : (
        <>
          {/* Azure Maps container */}
          <div 
            ref={mapRef} 
            style={{ 
              width: '100%', 
              height: '100%',
              display: 'block'
            }} 
          />
          
          {/* Map status overlay */}
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
          
          {/* Dataset info panel when selected */}
          {selectedDataset && (
            <div style={{
              position: 'absolute',
              bottom: '20px',
              left: '20px',
              background: 'rgba(255, 255, 255, 0.95)',
              padding: '16px',
              borderRadius: '8px',
              boxShadow: '0 4px 12px rgba(0, 0, 0, 0.15)',
              maxWidth: '300px',
              border: '1px solid rgba(0, 0, 0, 0.1)',
              zIndex: 1000,
              backdropFilter: 'blur(8px)'
            }}>
              <div style={{
                display: 'flex',
                alignItems: 'center',
                marginBottom: '8px',
                padding: '8px',
                borderRadius: '6px',
                backgroundColor: visualization.color
              }}>
                <span style={{ fontSize: '20px', marginRight: '8px' }}>{visualization.emoji}</span>
                <div>
                  <div style={{ fontSize: '14px', fontWeight: '600', color: '#333' }}>
                    {selectedDataset.title}
                  </div>
                  <div style={{ fontSize: '12px', color: '#666', marginTop: '2px' }}>
                    {visualization.description}
                  </div>
                </div>
              </div>
            </div>
          )}

          {/* Error overlay */}
          {mapError && (
            <div style={{
              position: 'absolute',
              top: '50%',
              left: '50%',
              transform: 'translate(-50%, -50%)',
              background: 'rgba(255, 255, 255, 0.95)',
              padding: '16px',
              borderRadius: '8px',
              boxShadow: '0 4px 12px rgba(0, 0, 0, 0.15)',
              zIndex: 1000,
              textAlign: 'center',
              border: '1px solid #ff6b6b'
            }}>
              <div style={{ color: '#ff6b6b', fontSize: '16px', marginBottom: '8px' }}>
                ⚠️ Map Error
              </div>
              <div style={{ color: '#333', fontSize: '14px' }}>
                {mapError}
              </div>
            </div>
          )}
        </>
      )}
    </div>
  );
};

export default MapView;
