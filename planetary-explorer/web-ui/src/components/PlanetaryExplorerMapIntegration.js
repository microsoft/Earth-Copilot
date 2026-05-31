/**
 * Enhanced Planetary Explorer Map Integration
 * 
 * This module bridges Planetary Explorer's PC tools with map visualization,
 * following the same patterns as VEDA GeoCoPilot for seamless integration.
 */

export class PlanetaryExplorerMapIntegration {
  constructor(mapInstance, setMapData) {
    this.mapInstance = mapInstance;
    this.setMapData = setMapData;
  }

  /**
   * Process Planetary Explorer response and extract visualization data
   */
  processResponse(response) {
    console.log('Planetary Explorer: Processing response for map visualization:', response);

    // If response is already in VEDA format, return as-is
    if (response.dataset_ids && response.bbox && response.action) {
      return response;
    }

    // Try to extract structured data from text response
    const structuredResponse = this.extractDataFromResponse(response);
    
    if (structuredResponse) {
      return structuredResponse;
    }

    // Fallback: create minimal response
    return {
      summary: typeof response === 'string' ? response : response.message || 'Data processed',
      action: 'load'
    };
  }

  /**
   * Extract structured data from PC tool responses
   */
  extractDataFromResponse(response) {
    try {
      // Look for JSON data in response
      const responseText = typeof response === 'string' ? response : response.message || '';
      
      // Try to extract collection IDs
      const collectionMatch = responseText.match(/collection[s]?[:\s]*([a-z0-9-]+)/gi);
      const collections = collectionMatch ? collectionMatch.map(m => m.split(/[:\s]+/).pop()) : [];

      // Try to extract bounding box
      const bboxMatch = responseText.match(/bbox[:\s]*\[([^\]]+)\]/i);
      const bbox = bboxMatch ? this.createBboxGeometry(bboxMatch[1]) : null;

      // Try to extract dates
      const dateMatch = responseText.match(/(\d{4}-\d{2}-\d{2})/g);
      const dates = dateMatch ? dateMatch.sort() : [];

      // Try to extract URLs
      const urlMatch = responseText.match(/https?:\/\/[^\s]+/g);
      const urls = urlMatch || [];

      // Determine action based on response content
      let action = 'load';
      
      if (responseText.includes('tile') || responseText.includes('mosaic')) {
        action = 'tiles';
      } else if (responseText.includes('animation') || responseText.includes('time-lapse')) {
        action = 'animation';
      } else if (responseText.includes('statistic') || responseText.includes('analysis')) {
        action = 'statistics';
      } else if (responseText.includes('compare') || dates.length > 1) {
        action = 'compare';
      }

      const result = {
        summary: responseText,
        action: action
      };

      if (collections.length > 0) {
        result.dataset_ids = collections;
      }

      if (bbox) {
        result.bbox = bbox;
      }

      if (dates.length >= 2) {
        result.date_range = {
          start_date: dates[0],
          end_date: dates[dates.length - 1]
        };
      }

      if (urls.length > 0) {
        result.visualization_data = {
          tile_urls: urls.filter(url => url.includes('tile')),
          preview_urls: urls.filter(url => url.includes('preview') || url.includes('crop')),
          mosaic_urls: urls.filter(url => url.includes('mosaic')),
          legend_url: urls.find(url => url.includes('legend'))
        };
      }

      return result;

    } catch (error) {
      console.error('Planetary Explorer: Error extracting data from response:', error);
      return null;
    }
  }

  /**
   * Create GeoJSON bbox geometry from coordinate string
   */
  createBboxGeometry(bboxString) {
    try {
      const coords = bboxString.split(',').map(s => parseFloat(s.trim()));
      
      if (coords.length === 4) {
        const [west, south, east, north] = coords;
        
        return {
          type: 'FeatureCollection',
          features: [{
            type: 'Feature',
            geometry: {
              type: 'Polygon',
              coordinates: [[
                [west, south],
                [east, south], 
                [east, north],
                [west, north],
                [west, south]
              ]]
            },
            properties: {}
          }]
        };
      }
    } catch (error) {
      console.error('Planetary Explorer: Error creating bbox geometry:', error);
    }
    
    return null;
  }

  /**
   * Visualize data on the map
   */
  visualizeOnMap(data) {
    console.log('Planetary Explorer: Visualizing data on map:', data);

    try {
      // Handle different visualization types
      switch (data.action) {
        case 'load':
          this.loadDataOnMap(data);
          break;
        case 'tiles':
          this.loadTilesOnMap(data);
          break;
        case 'compare':
          this.setupCompareMode(data);
          break;
        case 'statistics':
          this.setupAnalysisMode(data);
          break;
        case 'animation':
          this.showAnimation(data);
          break;
        default:
          this.loadDataOnMap(data);
      }

      // Update map data for the UI
      this.setMapData(data);

    } catch (error) {
      console.error('Planetary Explorer: Error visualizing data on map:', error);
    }
  }

  loadDataOnMap(data) {
    if (data.bbox && this.mapInstance) {
      // Add bbox to map
      this.addBboxToMap(data.bbox);
    }

    if (data.dataset_ids && data.dataset_ids.length > 0) {
      // Load datasets (this would integrate with the dataset loading system)
      console.log('Planetary Explorer: Loading datasets:', data.dataset_ids);
    }
  }

  loadTilesOnMap(data) {
    if (data.visualization_data?.tile_urls && this.mapInstance) {
      data.visualization_data.tile_urls.forEach(url => {
        console.log('Planetary Explorer: Adding tile layer:', url);
        // Add tile layer to map
      });
    }

    if (data.visualization_data?.mosaic_urls) {
      console.log('Planetary Explorer: Adding mosaic layers:', data.visualization_data.mosaic_urls);
    }
  }

  setupCompareMode(data) {
    console.log('Planetary Explorer: Setting up compare mode with date range:', data.date_range);
    this.loadDataOnMap(data);
  }

  setupAnalysisMode(data) {
    console.log('Planetary Explorer: Setting up analysis mode');
    this.loadDataOnMap(data);
  }

  showAnimation(data) {
    console.log('Planetary Explorer: Showing animation');
    // Handle animation display
  }

  addBboxToMap(bbox) {
    if (!this.mapInstance || !bbox) return;

    try {
      // Add bbox geometry to map as a layer
      if (this.mapInstance.getLayer('planetary-explorer-bbox')) {
        this.mapInstance.removeLayer('planetary-explorer-bbox');
      }
      
      if (this.mapInstance.getSource('planetary-explorer-bbox')) {
        this.mapInstance.removeSource('planetary-explorer-bbox');
      }

      this.mapInstance.addSource('planetary-explorer-bbox', {
        type: 'geojson',
        data: bbox
      });

      this.mapInstance.addLayer({
        id: 'planetary-explorer-bbox',
        type: 'line',
        source: 'planetary-explorer-bbox',
        paint: {
          'line-color': '#ff6b6b',
          'line-width': 3,
          'line-opacity': 0.8
        }
      });

      // Fit map to bbox
      if (bbox.features && bbox.features.length > 0) {
        const feature = bbox.features[0];
        if (feature.geometry.type === 'Polygon') {
          const coordinates = feature.geometry.coordinates[0];
          const bounds = coordinates.reduce((acc, coord) => {
            return [
              [Math.min(acc[0][0], coord[0]), Math.min(acc[0][1], coord[1])],
              [Math.max(acc[1][0], coord[0]), Math.max(acc[1][1], coord[1])]
            ];
          }, [[Infinity, Infinity], [-Infinity, -Infinity]]);

          this.mapInstance.fitBounds(bounds, { padding: 50 });
        }
      }

    } catch (error) {
      console.error('Planetary Explorer: Error adding bbox to map:', error);
    }
  }
}

/**
 * Enhanced chat message processing for map integration
 */
export function enhanceMessageForMapVisualization(message, response) {
  const integration = new PlanetaryExplorerMapIntegration(null, () => {});
  return integration.processResponse(response);
}

/**
 * Check if a response contains visualizable data
 */
export function hasVisualizableData(response) {
  if (!response) return false;
  
  const text = typeof response === 'string' ? response : response.message || '';
  
  // Check for indicators of visualizable data
  const indicators = [
    'collection', 'bbox', 'tile', 'mosaic', 'crop', 'preview',
    'longitude', 'latitude', 'coordinates', 'geometry',
    'sentinel', 'landsat', 'modis', 'viirs'
  ];
  
  return indicators.some(indicator => 
    text.toLowerCase().includes(indicator.toLowerCase())
  );
}

export default PlanetaryExplorerMapIntegration;
