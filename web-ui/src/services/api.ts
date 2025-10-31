// Copyright (c) Microsoft Corporation.
// Licensed under the MIT license.

import axios, { AxiosInstance, AxiosResponse, AxiosError } from 'axios';

// ✅ BEST PRACTICE: Runtime Configuration for Cloud Apps
// The frontend is configured to proxy /api/* requests to the backend in production
// This is set via VITE_API_BASE_URL environment variable at BUILD time (unavoidable for Vite)
// But we use it intelligently with a fallback chain

const isDevelopment = import.meta.env.DEV;

// Determine API base URL with intelligent fallback chain:
// 1. Development: Use localhost backend
// 2. Production with build-time env var: Use configured backend URL  
// 3. Fallback: Use current origin (works if frontend and backend are on same domain)
const API_BASE = isDevelopment 
  ? 'http://localhost:8000'
  : (import.meta.env.VITE_API_BASE_URL || window.location.origin);

// Only log API configuration in development mode
if (isDevelopment) {
  console.log('🌐 API Service initialized with base URL:', API_BASE);
  console.log('  - Mode: Development');
  console.log('  - VITE_API_BASE_URL:', import.meta.env.VITE_API_BASE_URL || 'not set');
  console.log('  - Final API_BASE:', API_BASE);
}

// Export API_BASE for use in other components
export const API_BASE_URL = API_BASE;

// Debug mode - only enabled in development
const DEBUG_MODE = isDevelopment;

export interface Dataset {
  id: string;
  title: string;
  description: string;
  type?: string;
}

export interface ChatMessage {
  role: 'user' | 'assistant';
  content: string;
  timestamp: Date;
  source?: string;
  isThinking?: boolean;  // Flag to indicate "thinking" animation
}

export interface MapContext {
  bounds?: {
    north: number;
    south: number;
    east: number;
    west: number;
    center_lat: number;
    center_lng: number;
  };
  imagery_base64?: string; // Base64 screenshot from MapView canvas
  imagery_url?: string;
  current_collection?: string;
}

// Debug logging utility
const debugLog = (message: string, data?: any) => {
  if (DEBUG_MODE) {
    console.log(`🔍 [API DEBUG] ${message}`, data || '');
  }
};

const errorLog = (message: string, error?: any) => {
  console.error(`🚨 [API ERROR] ${message}`, error || '');
};

class ApiService {
  private api: AxiosInstance | null = null;

  constructor() {
    try {
      this.api = axios.create({
        baseURL: API_BASE || undefined,
        timeout: 240000, // Increased to 4 minutes for GPT-5 Vision GEOINT analysis
        headers: {
          'Content-Type': 'application/json',
        },
      });

      // Add request interceptor for debugging
      this.api.interceptors.request.use(
        (config) => {
          debugLog(`🚀 Making ${config.method?.toUpperCase()} request to ${config.url}`, {
            baseURL: config.baseURL,
            fullURL: `${config.baseURL}${config.url}`,
            data: config.data,
            headers: config.headers
          });
          return config;
        },
        (error) => {
          errorLog('Request interceptor error', error);
          return Promise.reject(error);
        }
      );

      // Add response interceptor for debugging
      this.api.interceptors.response.use(
        (response: AxiosResponse) => {
          debugLog(`✅ Received ${response.status} response from ${response.config.url}`, {
            status: response.status,
            statusText: response.statusText,
            data: response.data,
            headers: response.headers
          });
          return response;
        },
        (error: AxiosError) => {
          errorLog(`❌ Response error from ${error.config?.url}`, {
            status: error.response?.status,
            statusText: error.response?.statusText,
            data: error.response?.data,
            message: error.message
          });
          return Promise.reject(error);
        }
      );

      if (DEBUG_MODE) {
        console.log('✅ API service initialized successfully');
        console.log('  - API base URL:', API_BASE || 'relative (using Vite proxy)');
        console.log('  - Debug mode: ENABLED');
      }
    } catch (error) {
      console.error('Failed to create axios instance:', error);
      this.api = null;
      // Don't throw here, let methods handle null gracefully
    }
  }

  async getMyDatasets(): Promise<Dataset[]> {
    try {
      debugLog('📊 Fetching private datasets...');

      // Always return sample data for now since we're focused on chat functionality
      return [
        {
          id: 'fires-poc-data',
          title: 'Fire Events POC Data',
          description: 'Private fire event dataset indexed in Azure Search for analysis and detection'
        },
        {
          id: 'private-satellite-imagery',
          title: 'Private Satellite Imagery',
          description: 'Custom satellite imagery collection for internal analysis'
        },
        {
          id: 'enterprise-geospatial-data',
          title: 'Enterprise Geospatial Data',
          description: 'Organization-specific geospatial datasets and analytics'
        }
      ];
    } catch (error) {
      console.error('Failed to fetch private datasets:', error);
      // Return sample private data on error
      return [
        {
          id: 'fires-poc-data',
          title: 'Fire Events POC Data',
          description: 'Private fire event dataset indexed in Azure Search for analysis and detection'
        }
      ];
    }
  }

  async getVedaDatasets(): Promise<Dataset[]> {
    // Return known VEDA collections for sidebar display
    // Actual VEDA STAC API queries happen only when semantic matching determines relevance
    return [
      {
        id: 'bangladesh-landcover-2001-2020',
        title: 'Bangladesh Land Cover (2001-2020)',
        description: 'MODIS-based land cover classification maps for Bangladesh',
        type: 'veda'
      },
      {
        id: 'hls-l30-002-ej-fire-africa',
        title: 'HLS Fire Analysis - Africa',
        description: 'Fire analysis using HLS data for African regions',
        type: 'veda'
      },
      {
        id: 'hls-l30-002-ej-fire-se-asia',
        title: 'HLS Fire Analysis - Southeast Asia',
        description: 'Fire analysis using HLS data for Southeast Asian regions',
        type: 'veda'
      },
      {
        id: 'esacci-lc',
        title: 'ESA CCI Land Cover',
        description: 'ESA Climate Change Initiative Land Cover data',
        type: 'veda'
      },
      {
        id: 'worldpop-population-density',
        title: 'WorldPop Population Density',
        description: 'High-resolution population density maps',
        type: 'veda'
      },
      {
        id: 'world-settlement-footprint-2015',
        title: 'World Settlement Footprint 2015',
        description: 'Global human settlement layer for 2015',
        type: 'veda'
      },
      {
        id: 'world-settlement-footprint-evolution-2019',
        title: 'World Settlement Footprint Evolution 2019',
        description: 'Global human settlement evolution layer for 2019',
        type: 'veda'
      },
      {
        id: 'ecmwf-era5-single-levels-reanalysis',
        title: 'ERA5 Reanalysis Data',
        description: 'ECMWF ERA5 atmospheric reanalysis data',
        type: 'veda'
      },
      {
        id: 'fires-esri-91',
        title: 'Esri Fire Analysis',
        description: 'Fire detection and analysis using Esri data',
        type: 'veda'
      }
    ];
  }

  async getPublicDatasets(): Promise<Dataset[]> {
    try {
      // For now we only expose NIFC Fire Events as in the original
      return [
        {
          id: 'PUBLIC/NIFC/FIRE_EVENTS',
          title: 'NIFC Fire Events',
          description: 'National Interagency Fire Center active fire incidents (live API).'
        }
      ];
    } catch (error) {
      console.error('Failed to fetch public datasets:', error);
      return [];
    }
  }

  async getPlanetaryComputerDatasets(): Promise<Dataset[]> {
    try {
      // Return sample MPC datasets for now since we're focused on chat functionality
      return [
        {
          id: 'MPC/SENTINEL-2-L2A',
          title: 'Sentinel-2 Level-2A',
          description: 'Sentinel-2 Level-2A surface reflectance and classification products'
        },
        {
          id: 'MPC/LANDSAT-C2-L2',
          title: 'Landsat Collection 2 Level-2',
          description: 'Landsat Collection 2 Level-2 surface temperature and reflectance'
        },
        {
          id: 'MPC/DAYMET-DAILY-NA',
          title: 'Daymet Daily North America',
          description: 'Daily weather parameters for North America'
        }
      ];
    } catch (error) {
      console.error('Failed to fetch MPC datasets:', error);
      return [];
    }
  }

  async sendChatMessage(
    message: string, 
    datasetId?: string, 
    conversationId?: string, 
    messageHistory?: ChatMessage[], 
    pin?: { lat: number; lng: number } | null, 
    geointMode?: boolean,
    mapContext?: MapContext
  ): Promise<any> {
    debugLog('sendChatMessage called', { message, datasetId, conversationId, historyLength: messageHistory?.length, pin, geointMode, hasMapContext: !!mapContext });

    if (!this.api) {
      console.error('API instance is not initialized');
      throw new Error('API service not initialized');
    }

    try {
      // Use the unified /api/query endpoint only (Router Function expects /api prefix)
      const endpoint = '/api/query';

      // Use the QueryRequest format for /query endpoint
      const requestData: any = {
        query: message,
        preferences: {
          interface_type: 'earth_copilot',
          data_source: 'planetary_computer',
          ...(datasetId && { dataset_id: datasetId })
        },
        include_visualization: true,
        session_id: conversationId || 'web-session-' + Date.now()
      };

      // Include pin if present
      if (pin) {
        requestData.pin = { lat: pin.lat, lng: pin.lng };
        debugLog('Including pin in request', { lat: pin.lat.toFixed(4), lng: pin.lng.toFixed(4) });
      }

      // Include GEOINT mode if active
      if (geointMode !== undefined) {
        requestData.geoint_mode = geointMode;
        debugLog('GEOINT mode', geointMode ? 'ENABLED' : 'DISABLED');
      }

      // Include map context if present (for Chat Vision capability)
      if (mapContext) {
        if (mapContext.bounds) {
          requestData.map_bounds = mapContext.bounds;
          debugLog('Including map bounds', mapContext.bounds);
        }
        if (mapContext.imagery_base64) {
          requestData.imagery_base64 = mapContext.imagery_base64;
          debugLog('Including base64 screenshot', `${mapContext.imagery_base64.length} chars`);
        }
        if (mapContext.imagery_url) {
          requestData.imagery_url = mapContext.imagery_url;
          debugLog('Including imagery URL', mapContext.imagery_url);
        }
        if (mapContext.current_collection) {
          requestData.current_collection = mapContext.current_collection;
          debugLog('Including collection', mapContext.current_collection);
        }
      }

      // Include conversation history for context (needed for Chat Vision follow-ups)
      if (messageHistory && messageHistory.length > 0) {
        requestData.conversation_history = messageHistory.map(msg => ({
          role: msg.role,
          content: msg.content
        }));
        debugLog('Including conversation history', `${messageHistory.length} messages`);
      }

      debugLog('Making query request', { endpoint, requestData });

      const response = await this.api.post(endpoint, requestData);
      debugLog('Query response received', { status: response.status, dataKeys: Object.keys(response.data || {}) });

      // Return the workflow result from QueryResponse format
      // Check if response has unified structure with top-level response field
      if (response.data && response.data.response) {
        return {
          response: response.data.response,
          user_response: response.data.response,
          data: response.data.data || null,
          ...response.data
        };
      }

      // Fallback to legacy results structure
      const results = (response.data && (response.data.results ?? null)) || null;
      return results ?? response.data;

    } catch (error: any) {
      console.error('API service error:', error);
      if (error.response) {
        console.error('Error response status:', error.response.status);
        console.error('Error response data:', error.response.data);
        console.error('Error response headers:', error.response.headers);
      }

      throw new Error('Failed to send message. Please try again.');
    }
  }

  async sendEnhancedChatMessage(
    message: string, 
    datasetId?: string, 
    conversationId?: string, 
    messageHistory?: ChatMessage[], 
    pin?: { lat: number; lng: number } | null, 
    geointMode?: boolean,
    mapContext?: MapContext
  ): Promise<any> {
    return this.sendChatMessage(message, datasetId, conversationId, messageHistory, pin, geointMode, mapContext);
  }

  async searchPrivateData(query: string, collection_id?: string): Promise<any> {
    debugLog('searchPrivateData called', { query, collection_id });

    if (!this.api) {
      console.error('API instance is not initialized');
      throw new Error('API service not initialized');
    }

    try {
      const endpoint = '/api/private-search';
      
      const requestData = {
        query: query,
        ...(collection_id && { collection_id: collection_id })
      };

      debugLog('Making private search request', { endpoint, requestData });

      const response = await this.api.post(endpoint, requestData);
      console.log('Private search response received:', response);
      console.log('Private search response status:', response.status);
      console.log('Private search response data:', response.data);

      return response.data;

    } catch (error: any) {
      console.error('Private search API error:', error);
      if (error.response) {
        console.error('Error response status:', error.response.status);
        console.error('Error response data:', error.response.data);
        console.error('Error response headers:', error.response.headers);
      }

      throw new Error('Failed to search private data. Please try again.');
    }
  }

  /**
   * 🧠 Trigger GEOINT analysis with explicit module selection
   * 
   * Called when user drops a pin with a selected module.
   * Routes directly to the appropriate agent (mobility, terrain, building damage).
   */
  async triggerGeointAnalysis(
    latitude: number, 
    longitude: number, 
    module: string,
    userQuery?: string, 
    userContext?: string,
    screenshot?: string,
    signal?: AbortSignal
  ): Promise<any> {
    console.log('🧠 API: Triggering GEOINT analysis with module:', module, 'at', { latitude, longitude });

    if (!this.api) {
      console.error('API instance is not initialized');
      throw new Error('API service not initialized');
    }

    try {
      // Map frontend module names to backend endpoint URLs
      const moduleEndpointMap: Record<string, string> = {
        'terrain': '/api/geoint/terrain',
        'mobility': '/api/geoint/mobility',
        'building_damage': '/api/geoint/building-damage',
        'comparison': '/api/geoint/comparison',
        'animation': '/api/geoint/animation'
      };

      const endpoint = moduleEndpointMap[module];
      
      if (!endpoint) {
        throw new Error(`Unknown GEOINT module: ${module}. Valid modules: ${Object.keys(moduleEndpointMap).join(', ')}`);
      }
      
      const requestData: any = {
        latitude,
        longitude,
        user_query: userQuery || "",
        user_context: userContext || ""
      };

      // Add screenshot for terrain analysis
      if (module === 'terrain' && screenshot) {
        requestData.screenshot = screenshot;
        console.log('📸 Including screenshot in terrain analysis request');
      }

      console.log('🧠 Making GEOINT analysis request to', endpoint, ':', {
        ...requestData,
        screenshot: requestData.screenshot ? `<base64 data ${requestData.screenshot.length} chars>` : undefined
      });

      const response = await this.api.post(endpoint, requestData, {
        signal // Pass AbortSignal to axios
      });
      console.log('✅ GEOINT analysis response received:', response.data);

      return response.data;

    } catch (error: any) {
      console.error('❌ GEOINT analysis API error:', error);
      if (error.response) {
        console.error('Error response status:', error.response.status);
        console.error('Error response data:', error.response.data);
      }

      throw new Error(`GEOINT analysis failed: ${error.response?.data?.detail || error.message}`);
    }
  }

  /**
   * Trigger GEOINT Mobility Analysis (Agent 5)
   * 
   * Called when user drops a pin with GEOINT mode enabled.
   * Performs terrain-based mobility analysis in N/S/E/W directions.
   */
  async triggerGeointMobility(latitude: number, longitude: number, userContext?: string): Promise<any> {
    console.log('🎖️ API: Triggering GEOINT mobility analysis at', { latitude, longitude });

    if (!this.api) {
      console.error('API instance is not initialized');
      throw new Error('API service not initialized');
    }

    try {
      const endpoint = '/api/geoint/mobility';
      
      const requestData = {
        latitude,
        longitude,
        user_context: userContext
      };

      console.log('🎖️ Making GEOINT mobility request to', endpoint, ':', requestData);

      const response = await this.api.post(endpoint, requestData);
      console.log('✅ GEOINT mobility response received:', response.data);

      return response.data;

    } catch (error: any) {
      console.error('❌ GEOINT mobility API error:', error);
      if (error.response) {
        console.error('Error response status:', error.response.status);
        console.error('Error response data:', error.response.data);
      }

      throw new Error(`GEOINT mobility analysis failed: ${error.response?.data?.detail || error.message}`);
    }
  }

}

export const apiService = new ApiService();

// Export standalone functions for convenience
export async function triggerGeointAnalysis(
  latitude: number, 
  longitude: number, 
  module: string,
  userQuery?: string, 
  userContext?: string,
  screenshot?: string,
  signal?: AbortSignal
): Promise<any> {
  return apiService.triggerGeointAnalysis(latitude, longitude, module, userQuery, userContext, screenshot, signal);
}

export async function triggerGeointMobility(latitude: number, longitude: number, userContext?: string): Promise<any> {
  return apiService.triggerGeointMobility(latitude, longitude, userContext);
}
