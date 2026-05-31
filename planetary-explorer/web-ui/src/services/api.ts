// Copyright (c) Microsoft Corporation.
// Licensed under the MIT license.

import axios, { AxiosInstance, AxiosResponse, AxiosError } from 'axios';
import { getAuthToken, refreshAuthToken } from './authHelper';

//  BEST PRACTICE: Runtime Configuration for Cloud Apps
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
  console.log(' API Service initialized with base URL:', API_BASE);
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
  // Source-chip metadata surfaced from /api/query response. The backend
  // populates these so the UI can show small badges under each assistant
  // turn ("Data: MPC Pro"). All optional.
  dataSource?: string;          // "MPC Pro" | "Public PC" | undefined
  // Number of STAC items the backend search actually returned for this
  // turn. Surfaced in the SourceChips row so the user can verify the
  // routed catalog truly matched data (e.g. "Data: MPC Pro · 0 tiles"
  // immediately flags a misrouted toggle or empty private catalog).
  tilesAvailable?: number;
  toolsUsed?: string[];         // ordered tool names from the ReAct loop
  // Routing decision returned by the backend (response.debug.stac_routing
  // on /api/query). Authoritative per-request evidence of which catalog
  // actually served the turn -- shown in the SourceChips tooltip so the
  // user can verify Pro vs Public without paging through Log Analytics.
  stacRouting?: {
    requested_mode?: string | null;
    default_mode?: string;
    resolved_endpoint?: string;
    resolved_url?: string;
    resolved_host?: string;
    is_pro?: boolean;
    pro_configured?: boolean | null;
    pro_unconfigured_short_circuit?: boolean;
  };
  // MCP tool-trace rows captured from the agent's streaming SSE channel
  // (e.g. /api/resilience/assess/smart/stream). When present, the chat
  // panel renders <TraceDrawer rows={toolTrace}/> beneath the message so
  // the user can see every MCP call the agent made plus copy-able
  // JSON-RPC payloads. Shape matches `ToolTraceRow` from
  // `components/trace/types.ts`.
  toolTrace?: Array<{
    traceId: string;
    serverId: string;
    tool: string;
    tier: 'read' | 'write' | 'destructive';
    args: Record<string, unknown>;
    status: 'pending' | 'ok' | 'error' | 'denied';
    latencyMs?: number;
    responseSummary?: string | null;
    error?: string | null;
  }>;
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
  tile_urls?: Array<{  // TiTiler URLs from prior STAC response for Vision Agent
    tilejson_url: string;
    item_id?: string;
    collection?: string;
  }>;
  // Full STAC items captured by MapView after a search. Includes
  // `assets` with `href` URLs needed by the backend `sample_raster_value`
  // tool to fetch COGs and read pixel values at a pinned location.
  // Without this, ANALYZE-mode point-sampling queries (e.g.
  // "what is the elevation here?") fail with
  // "No STAC items available to sample".
  stac_items?: Array<{
    id: string;
    collection: string;
    bbox?: number[];
    properties?: Record<string, any>;
    assets?: Record<string, any>;
  }>;
  has_satellite_data?: boolean; // Flag indicating if STAC imagery is loaded
  vision_mode?: boolean; // NEW: explicit vision analysis mode
  vision_pin?: { lat: number; lng: number } | null; // NEW: pin coordinates for vision analysis
}

// Debug logging utility
const debugLog = (message: string, data?: any) => {
  if (DEBUG_MODE) {
    console.log(` [API DEBUG] ${message}`, data || '');
  }
};

const errorLog = (message: string, error?: any) => {
  console.error(` [API ERROR] ${message}`, error || '');
};

class ApiService {
  private api: AxiosInstance | null = null;

  constructor() {
    try {
      this.api = axios.create({
        baseURL: API_BASE || undefined,
        timeout: 300000, // 5 minutes — extreme weather queries via chat can be slow (NetCDF sampling)
        headers: {
          'Content-Type': 'application/json',
        },
      });

      // Add request interceptor for auth token + debugging
      this.api.interceptors.request.use(
        async (config) => {
          // Attach EasyAuth token for backend Container App auth
          const token = await getAuthToken();
          if (token) {
            config.headers.Authorization = `Bearer ${token}`;
          }
          debugLog(`Making ${config.method?.toUpperCase()} request to ${config.url}`, {
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

      // Add response interceptor for debugging + automatic token refresh on 401
      this.api.interceptors.response.use(
        (response: AxiosResponse) => {
          debugLog(`Received ${response.status} response from ${response.config.url}`, {
            status: response.status,
            statusText: response.statusText,
            data: response.data,
            headers: response.headers
          });
          return response;
        },
        async (error: AxiosError) => {
          const originalRequest = error.config as any;

          // Auto-refresh token and retry on 401 "Token has expired"
          if (
            error.response?.status === 401 &&
            !originalRequest._authRetried
          ) {
            originalRequest._authRetried = true;
            console.warn('[Auth] 401 received — attempting token refresh...');

            const newToken = await refreshAuthToken();
            if (newToken) {
              console.log('[Auth] Token refreshed — retrying request');
              originalRequest.headers.Authorization = `Bearer ${newToken}`;
              return this.api!.request(originalRequest);
            }

            // Refresh failed — redirect to login
            console.warn('[Auth] Token refresh failed — redirecting to login');
            window.location.href = '/.auth/login/aad?post_login_redirect_uri=' +
              encodeURIComponent(window.location.pathname + window.location.search);
            return Promise.reject(error);
          }

          errorLog(`Response error from ${error.config?.url}`, {
            status: error.response?.status,
            statusText: error.response?.statusText,
            data: error.response?.data,
            message: error.message
          });
          return Promise.reject(error);
        }
      );

      if (DEBUG_MODE) {
        console.log(' API service initialized successfully');
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
      debugLog('Fetching private datasets...');

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

  /**
   * Fetch the collection list from the configured MPC Pro (private GeoCatalog)
   * STAC endpoint. Returns an empty array if Pro is not configured server-side;
   * UI should treat that as "no private collections available" and fall back
   * to the public dropdown without throwing.
   */
  async getProCollections(): Promise<{ collections: Dataset[]; configured: boolean; error?: string }> {
    if (!this.api) {
      console.warn('getProCollections: API not initialized');
      return { collections: [], configured: false, error: 'API not initialized' };
    }
    try {
      const res = await this.api.get('/api/pro/collections');
      const data = res.data || {};
      if (!data.configured) {
        return { collections: [], configured: false };
      }
      const cols = Array.isArray(data.collections) ? data.collections : [];
      return {
        configured: true,
        collections: cols.map((c: any): Dataset => ({
          id: c.id,
          title: c.title || c.id,
          description: c.description || '',
          type: 'mpc-pro',
        })),
      };
    } catch (err: any) {
      errorLog('getProCollections failed', err);
      const status = err?.response?.status;
      const detail =
        err?.response?.data?.error ||
        err?.response?.data?.detail ||
        err?.message ||
        'request failed';
      return {
        collections: [],
        configured: false,
        error: status ? `HTTP ${status}: ${detail}` : detail,
      };
    }
  }

  async sendChatMessage(
    message: string, 
    datasetId?: string, 
    conversationId?: string, 
    messageHistory?: ChatMessage[], 
    pin?: { lat: number; lng: number } | null, 
    geointMode?: boolean,
    mapContext?: MapContext,
    selectedModel?: string,
    partOfSplit?: boolean,
    stacMode?: 'public' | 'pro',
    signal?: AbortSignal
  ): Promise<any> {
    debugLog('sendChatMessage called', { message, datasetId, conversationId, historyLength: messageHistory?.length, pin, geointMode, hasMapContext: !!mapContext, selectedModel, partOfSplit, stacMode, hasAbortSignal: !!signal });

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
        model: selectedModel || 'gpt-5',  // Default to GPT-5
        preferences: {
          interface_type: 'planetary_explorer',
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

      // Mark this call as a sub-part of a split sequence so the backend
      // skips its own splitter (preventing infinite recursion).
      if (partOfSplit) {
        requestData.part_of_split = true;
      }

      // Public vs MPC Pro routing. Backend treats this as authoritative for
      // the LOAD path — when "pro", STAC searches hit MPC_PRO_STAC_URL with
      // AAD bearer + api-version. Default is "public".
      if (stacMode) {
        requestData.stac_mode = stacMode;
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
        if (mapContext.tile_urls && mapContext.tile_urls.length > 0) {
          requestData.tile_urls = mapContext.tile_urls;
          debugLog('Including tile URLs', `${mapContext.tile_urls.length} tiles`);
        }
        // Forward full STAC items (with asset hrefs) to the backend so
        // ANALYZE-mode tools like sample_raster_value can read actual
        // pixel values from the loaded COGs at the pin location. Without
        // this the backend has only tile URLs (which are titiler mosaics
        // for many collections) and cannot reconstruct a STAC item ->
        // sampling falls back to "No STAC items available to sample".
        if (mapContext.stac_items && mapContext.stac_items.length > 0) {
          requestData.stac_items = mapContext.stac_items;
          debugLog('Including STAC items', `${mapContext.stac_items.length} items`);
        }
        // CRITICAL: Include has_satellite_data flag for router to know when to use vision
        if (mapContext.has_satellite_data !== undefined) {
          requestData.has_satellite_data = mapContext.has_satellite_data;
          debugLog('Including has_satellite_data', mapContext.has_satellite_data);
        }
        // NEW: Include vision mode flag for explicit vision routing
        if (mapContext.vision_mode !== undefined) {
          requestData.vision_mode = mapContext.vision_mode;
          debugLog('Including vision_mode', mapContext.vision_mode);
        }
        if (mapContext.vision_pin) {
          requestData.vision_pin = mapContext.vision_pin;
          debugLog('Including vision_pin', mapContext.vision_pin);
        }
      }

      //  DEBUG: Log the complete request body before sending
      console.log(' API Request Body:', {
        query: requestData.query,
        vision_mode: requestData.vision_mode || false,
        vision_pin: requestData.vision_pin || null,
        has_satellite_data: requestData.has_satellite_data,
        has_screenshot: !!requestData.imagery_base64,
        collection: requestData.current_collection,
        tile_urls_count: requestData.tile_urls?.length || 0,
        has_conversation_history: !!requestData.conversation_history
      });

      // Include conversation history for context (needed for Chat Vision follow-ups)
      if (messageHistory && messageHistory.length > 0) {
        requestData.conversation_history = messageHistory.map(msg => ({
          role: msg.role,
          content: msg.content
        }));
        debugLog('Including conversation history', `${messageHistory.length} messages`);
      }

      debugLog('Making query request', { endpoint, requestData });

      const response = await this.api.post(endpoint, requestData, { signal });
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
      // If the caller aborted via AbortController, surface that as a
      // distinct error so the UI can drop the result silently.
      if (error?.name === 'CanceledError' || error?.code === 'ERR_CANCELED' || error?.message === 'canceled') {
        const cancelErr: any = new Error('Request cancelled by user.');
        cancelErr.name = 'CanceledError';
        cancelErr.cancelled = true;
        throw cancelErr;
      }
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
   * Terrain Agent Chat - Multi-turn conversation with memory
   * 
   * Sends a follow-up question to the terrain analysis agent.
   * The agent maintains conversation memory per session.
   */
  async sendTerrainChatMessage(
    sessionId: string | null,
    message: string,
    latitude: number,
    longitude: number,
    screenshot?: string,
    radiusKm: number = 5.0
  ): Promise<any> {
    console.log(' API: Sending terrain chat message', { sessionId, message: message.substring(0, 50) + '...' });

    if (!this.api) {
      throw new Error('API service not initialized');
    }

    try {
      const requestData: any = {
        message,
        latitude,
        longitude,
        radius_km: radiusKm
      };

      // Include session_id if we have one (for follow-up questions)
      if (sessionId) {
        requestData.session_id = sessionId;
      }

      // Include screenshot if provided
      if (screenshot) {
        requestData.screenshot = screenshot;
        console.log(' Including screenshot in terrain chat request');
      }

      const response = await this.api.post('/api/geoint/terrain/chat', requestData);
      console.log(' Terrain chat response:', response.data);

      return response.data;

    } catch (error: any) {
      console.error(' Terrain chat API error:', error);
      throw new Error(`Terrain chat failed: ${error.response?.data?.detail || error.message}`);
    }
  }

  /**
   * Clear terrain agent session (reset memory)
   */
  async clearTerrainSession(sessionId: string): Promise<boolean> {
    console.log(' API: Clearing terrain session', sessionId);

    if (!this.api) {
      throw new Error('API service not initialized');
    }

    try {
      await this.api.delete(`/api/geoint/terrain/chat/${sessionId}`);
      console.log(' Terrain session cleared');
      return true;
    } catch (error: any) {
      console.error(' Failed to clear terrain session:', error);
      return false;
    }
  }

  /**
   * Send a follow-up message to the vision agent with session context
   * For the FIRST message (no sessionId), uses /api/geoint/vision to create a session
   * For follow-ups (with sessionId), uses /api/geoint/vision/chat
   */
  async sendVisionChatMessage(
    sessionId: string | null,
    message: string,
    latitude: number,
    longitude: number,
    screenshot?: string,
    mapContext?: any  // Full map context with tile_urls, collection, bounds, etc.
  ): Promise<any> {
    console.log(' API: Sending vision chat message', { 
      sessionId, 
      message: message.substring(0, 50) + '...',
      hasMapContext: !!mapContext,
      hasTileUrls: !!(mapContext?.tile_urls?.length),
      collection: mapContext?.current_collection
    });

    if (!this.api) {
      throw new Error('API service not initialized');
    }

    try {
      // For the FIRST message (no session), use /api/geoint/vision which creates a session
      if (!sessionId) {
        console.log(' API: First vision message - using /api/geoint/vision to create session');
        
        const requestData: any = {
          latitude,
          longitude,
          user_query: message
        };

        // Include screenshot if provided
        if (screenshot) {
          requestData.screenshot = screenshot;
          console.log(' Including screenshot in initial vision request');
        }
        
        // Include tile URLs and collection for raster analysis
        if (mapContext?.tile_urls?.length > 0) {
          requestData.tile_urls = mapContext.tile_urls;
          console.log(' Including', mapContext.tile_urls.length, 'tile URLs for raster analysis');
        }
        if (mapContext?.current_collection) {
          requestData.collection = mapContext.current_collection;
          console.log(' Including collection:', mapContext.current_collection);
        }
        if (mapContext?.bounds) {
          requestData.map_bounds = mapContext.bounds;
        }
        //  NEW: Include STAC items with assets for NDVI/raster analysis
        if (mapContext?.stac_items?.length > 0) {
          requestData.stac_items = mapContext.stac_items;
          console.log(' Including', mapContext.stac_items.length, 'STAC items with assets for raster analysis');
        }
        
        //  Include analysis type hint (raster vs screenshot) to guide tool selection
        if (mapContext?.analysis_type) {
          requestData.analysis_type = mapContext.analysis_type;
          console.log(' Including analysis type hint:', mapContext.analysis_type);
        }

        const response = await this.api.post('/api/geoint/vision', requestData);
        console.log(' Initial vision response:', response.data);
        
        // Return in a format compatible with follow-up responses
        return {
          response: response.data?.result?.analysis || response.data?.result?.response || response.data?.analysis,
          session_id: response.data?.session_id,
          tool_calls: response.data?.result?.tools_used || []
        };
      }

      // For follow-up messages (with session), use /api/geoint/vision/chat
      console.log(' API: Follow-up vision message - using /api/geoint/vision/chat');
      
      const requestData: any = {
        message,
        latitude,
        longitude,
        session_id: sessionId
      };

      // Include screenshot if provided
      if (screenshot) {
        requestData.screenshot = screenshot;
        console.log(' Including screenshot in vision chat request');
      }
      
      // Include tile URLs and collection for raster analysis (follow-ups may need fresh context)
      if (mapContext?.tile_urls?.length > 0) {
        requestData.tile_urls = mapContext.tile_urls;
      }
      if (mapContext?.current_collection) {
        requestData.collection = mapContext.current_collection;
      }
      //  NEW: Include STAC items with assets for NDVI/raster analysis
      if (mapContext?.stac_items?.length > 0) {
        requestData.stac_items = mapContext.stac_items;
        console.log(' [FOLLOW-UP] Including', mapContext.stac_items.length, 'STAC items with assets for raster analysis');
      } else {
        console.log(' [FOLLOW-UP] No STAC items in mapContext! stac_items:', mapContext?.stac_items);
      }
      
      //  Include analysis type hint (raster vs screenshot) to guide tool selection
      if (mapContext?.analysis_type) {
        requestData.analysis_type = mapContext.analysis_type;
        console.log(' [FOLLOW-UP] Including analysis type hint:', mapContext.analysis_type);
      }

      const response = await this.api.post('/api/geoint/vision/chat', requestData);
      console.log(' Vision chat response:', response.data);

      return {
        response: response.data?.result?.response,
        session_id: response.data?.session_id,
        tool_calls: response.data?.result?.tools_used || []
      };

    } catch (error: any) {
      console.error(' Vision chat API error:', error);
      throw new Error(`Vision chat failed: ${error.response?.data?.detail || error.message}`);
    }
  }

  /**
   * Clear vision agent session (reset memory)
   */
  async clearVisionSession(sessionId: string): Promise<boolean> {
    console.log(' API: Clearing vision session', sessionId);

    if (!this.api) {
      throw new Error('API service not initialized');
    }

    try {
      await this.api.delete(`/api/geoint/vision/chat/${sessionId}`);
      console.log(' Vision session cleared');
      return true;
    } catch (error: any) {
      console.error(' Failed to clear vision session:', error);
      return false;
    }
  }

  /**
   * Trigger GEOINT analysis with explicit module selection
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
    signal?: AbortSignal,
    extraParams?: Record<string, any>
  ): Promise<any> {
    console.log(' API: Triggering GEOINT analysis with module:', module, 'at', { latitude, longitude });

    if (!this.api) {
      console.error('API instance is not initialized');
      throw new Error('API service not initialized');
    }

    try {
      // Map frontend module names to backend endpoint URLs
      const moduleEndpointMap: Record<string, string> = {
        'vision': '/api/geoint/vision',
        'terrain': '/api/geoint/terrain',
        'mobility': '/api/geoint/mobility',
        'building_damage': '/api/geoint/building-damage',
        'extreme_weather': '/api/geoint/extreme-weather',
        'comparison': '/api/geoint/comparison',
        'animation': '/api/geoint/animation',
        'site_audit': '/api/sites/audit'
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

      // Add screenshot for GEOINT modules that use vision analysis.
      // Extreme weather skips vision pre-analysis (NetCDF point sampling doesn't
      // need the map screenshot), so don't send the 500KB+ payload unnecessarily.
      const modulesUsingScreenshot = ['vision', 'terrain', 'mobility', 'building_damage', 'comparison'];
      if (screenshot && modulesUsingScreenshot.includes(module)) {
        requestData.screenshot = screenshot;
        console.log(` Including screenshot in ${module} analysis request`);
      } else if (screenshot) {
        console.log(` Skipping screenshot for ${module} (not used by this module)`);
      }

      // Add extra parameters (e.g., latitude_b/longitude_b for mobility A->B)
      if (extraParams) {
        Object.assign(requestData, extraParams);
      }

      console.log(' Making GEOINT analysis request to', endpoint, ':', {
        ...requestData,
        screenshot: requestData.screenshot ? `<base64 data ${requestData.screenshot.length} chars>` : undefined
      });

      const response = await this.api.post(endpoint, requestData, {
        signal, // Pass AbortSignal to axios
        timeout: 300000, // 5 minutes for GEOINT (climate NetCDF sampling can be slow)
      });
      console.log(' GEOINT analysis response received:', response.data);

      return response.data;

    } catch (error: any) {
      console.error(' GEOINT analysis API error:', error);
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
    console.log(' API: Triggering GEOINT mobility analysis at', { latitude, longitude });

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

      console.log(' Making GEOINT mobility request to', endpoint, ':', requestData);

      const response = await this.api.post(endpoint, requestData);
      console.log(' GEOINT mobility response received:', response.data);

      return response.data;

    } catch (error: any) {
      console.error(' GEOINT mobility API error:', error);
      if (error.response) {
        console.error('Error response status:', error.response.status);
        console.error('Error response data:', error.response.data);
      }

      throw new Error(`GEOINT mobility analysis failed: ${error.response?.data?.detail || error.message}`);
    }
  }

  // ------------------------------------------------------------------
  // Microsoft Fabric
  // ------------------------------------------------------------------
  async getFabricStatus(): Promise<{ configured: boolean; endpoint?: string }> {
    const res = await this.api!.get('/api/fabric/status');
    return res.data;
  }

  async listFabricWorkspaces(): Promise<Array<{ id: string; displayName: string }>> {
    const res = await this.api!.get('/api/fabric/workspaces');
    return res.data?.workspaces || [];
  }

  async listFabricLakehouses(workspaceId: string): Promise<Array<{ id: string; displayName: string }>> {
    const res = await this.api!.get(`/api/fabric/workspaces/${workspaceId}/lakehouses`);
    return res.data?.lakehouses || [];
  }

  async getFabricLakehouseSchema(workspaceId: string, lakehouseId: string): Promise<any> {
    const res = await this.api!.get(`/api/fabric/lakehouses/${workspaceId}/${lakehouseId}/schema`);
    return res.data;
  }

  async queryFabricLakehouse(workspaceId: string, lakehouseId: string, sql: string): Promise<any> {
    const res = await this.api!.post('/api/fabric/query', {
      workspace_id: workspaceId,
      lakehouse_id: lakehouseId,
      sql,
    });
    return res.data;
  }

  async searchFabricDocuments(workspaceId: string, query: string, topK = 5): Promise<any[]> {
    const res = await this.api!.post('/api/fabric/search_documents', {
      workspace_id: workspaceId,
      query,
      top_k: topK,
    });
    return res.data?.results || [];
  }

  // ------------------------------------------------------------------
  // Site Audit (data center siting dossier across Fabric + MPC + AI Search)
  // ------------------------------------------------------------------
  async triggerSiteAudit(
    lat: number,
    lng: number,
    claimedMw: number = 200,
    userQuery?: string,
    signal?: AbortSignal
  ): Promise<any> {
    if (!this.api) {
      throw new Error('API service not initialized');
    }
    console.log(' API: Triggering Site Audit at', { lat, lng, claimedMw, userQuery });
    try {
      const response = await this.api.post(
        '/api/sites/audit',
        { lat, lng, claimed_mw: claimedMw, user_query: userQuery },
        { signal, timeout: 180000 }
      );
      return response.data;
    } catch (error: any) {
      console.error(' Site Audit API error:', error);
      throw new Error(
        `Site audit failed: ${error.response?.data?.detail || error.message}`
      );
    }
  }

  // ------------------------------------------------------------------
  // Forecast (Aurora + Earth-2 FCN + MAI Weather ensemble at a lat/lng)
  // ------------------------------------------------------------------
  async triggerForecast(
    lat: number,
    lng: number,
    userQuery?: string,
    options?: {
      leadHours?: number;
      variables?: string[];
      gridSize?: number;
      providers?: string[];
      locationLabel?: string;
    },
    signal?: AbortSignal
  ): Promise<any> {
    if (!this.api) {
      throw new Error('API service not initialized');
    }
    const body: Record<string, any> = {
      latitude: lat,
      longitude: lng,
      lead_hours: options?.leadHours ?? 72,
      grid_size: options?.gridSize ?? 8,
    };
    if (options?.variables && options.variables.length > 0) body.variables = options.variables;
    if (options?.providers && options.providers.length > 0) body.providers = options.providers;
    if (userQuery) body.user_query = userQuery;
    if (options?.locationLabel) body.location_label = options.locationLabel;
    console.log(' API: Triggering Forecast', body);
    try {
      const response = await this.api.post('/api/geoint/forecast', body, {
        signal,
        timeout: 180000,
      });
      return response.data;
    } catch (error: any) {
      console.error(' Forecast API error:', error);
      throw new Error(
        `Forecast failed: ${error.response?.data?.detail || error.message}`
      );
    }
  }

  // ------------------------------------------------------------------
  // Resilience (climate-aware industrial productivity twin)
  // ------------------------------------------------------------------
  async triggerResilienceAssessment(
    params: {
      regionFilter?: string;
      horizonDays?: number;
      hazards?: string[];
      userQuery?: string;
      smart?: boolean;
    } = {},
    signal?: AbortSignal
  ): Promise<any> {
    if (!this.api) {
      throw new Error('API service not initialized');
    }
    const body: Record<string, any> = {
      region_filter: params.regionFilter ?? 'TX',
      horizon_days: params.horizonDays ?? 7,
      hazards: params.hazards ?? ['heat', 'wildfire'],
    };
    if (params.userQuery) body.user_query = params.userQuery;
    // Investigative phrasings (counterfactuals, comparisons, similarity)
    // route through the planner-loop endpoint; everything else goes to
    // the deterministic DAG. The backend also has its own classifier, so
    // the worst case from a false-negative here is "we used the cheap
    // path for a query the planner could have answered" — never a crash.
    const path = params.smart ? '/api/resilience/assess/smart' : '/api/resilience/assess';
    console.log(' API: Triggering Resilience assessment', { path, ...body });
    try {
      const response = await this.api.post(path, body, {
        signal,
        timeout: 180000,
      });
      return response.data;
    } catch (error: any) {
      console.error(' Resilience API error:', error);
      throw new Error(
        `Resilience assessment failed: ${error.response?.data?.detail || error.message}`
      );
    }
  }

  /**
   * Stream a Resilience assessment via SSE. Same inputs as
   * :func:`triggerResilienceAssessment` but consumes
   * ``/api/resilience/assess/smart/stream``: parses every
   * ``tool_call`` / ``tool_result`` / ``confirm_request`` event into the
   * supplied callbacks, then resolves with the final dossier emitted as
   * the terminal ``dossier`` event. Falls back to the buffered
   * non-streaming endpoint if SSE plumbing fails for any reason so the
   * chat panel never bricks on a network hiccup.
   */
  async streamResilienceAssessment(
    params: {
      regionFilter?: string;
      horizonDays?: number;
      hazards?: string[];
      userQuery?: string;
    } = {},
    handlers: {
      onTrace?: (evt: any) => void;
      onConfirmRequest?: (evt: any) => void;
      onConfirmResolved?: (evt: any) => void;
      onProgress?: (evt: any) => void;
      onComplete?: (dossier: any) => void;
      onError?: (err: Error) => void;
    } = {},
    signal?: AbortSignal,
  ): Promise<any> {
    const baseURL = this.api?.defaults.baseURL || '';
    const url = `${baseURL.replace(/\/$/, '')}/api/resilience/assess/smart/stream`;
    const body: Record<string, any> = {
      region_filter: params.regionFilter ?? 'TX',
      horizon_days: params.horizonDays ?? 7,
      hazards: params.hazards ?? ['heat', 'wildfire'],
    };
    if (params.userQuery) body.user_query = params.userQuery;

    // Forward the same Authorization header axios would have sent so
    // the Fabric-assertion guard accepts the stream. The interceptor
    // attaches the token per-request and never writes it to
    // axios.defaults.headers, so we have to call getAuthToken()
    // ourselves instead of cribbing from defaults (which always come
    // back empty and yield a 401 'Missing or invalid Authorization
    // header' from the FastAPI EasyAuth guard).
    const headers: Record<string, string> = { 'Content-Type': 'application/json' };
    try {
      const token = await getAuthToken();
      if (token) headers['Authorization'] = `Bearer ${token}`;
    } catch (err) {
      // Fall back to whatever (if anything) axios has cached; the
      // request will then fail with a 401 and the caller will surface
      // a friendlier message.
      const authHeader = (this.api?.defaults.headers as any)?.common?.Authorization
        || (this.api?.defaults.headers as any)?.Authorization;
      if (authHeader) headers['Authorization'] = String(authHeader);
    }

    let response: Response;
    try {
      response = await fetch(url, {
        method: 'POST',
        headers,
        body: JSON.stringify(body),
        signal,
      });
    } catch (err: any) {
      handlers.onError?.(err);
      throw err;
    }
    if (!response.ok || !response.body) {
      const detail = await response.text().catch(() => '');
      const err = new Error(`Resilience stream failed: HTTP ${response.status} ${detail}`);
      handlers.onError?.(err);
      throw err;
    }

    const reader = response.body.getReader();
    const decoder = new TextDecoder();
    let buffer = '';
    let finalDossier: any = null;

    const flushEvent = (block: string) => {
      // Parse a single SSE event block ("event: foo\ndata: ...").
      const lines = block.split(/\r?\n/);
      let eventName = 'message';
      const dataLines: string[] = [];
      for (const line of lines) {
        if (line.startsWith('event:')) eventName = line.slice(6).trim();
        else if (line.startsWith('data:')) dataLines.push(line.slice(5).trim());
      }
      if (dataLines.length === 0) return;
      const raw = dataLines.join('\n');
      let payload: any;
      try { payload = JSON.parse(raw); } catch { payload = { raw }; }

      if (eventName === 'error') {
        handlers.onError?.(new Error(payload?.error || raw));
        return;
      }
      const t = payload?.type;
      if (t === 'tool_call' || t === 'tool_result') {
        handlers.onTrace?.(payload);
      } else if (t === 'confirm_request') {
        handlers.onConfirmRequest?.(payload);
      } else if (t === 'confirm_resolved') {
        handlers.onConfirmResolved?.(payload);
      } else if (t === 'dossier' || payload?.facilities || payload?.summary) {
        // The planner stream terminates with the dossier payload (the
        // backend tags it `type: dossier` when available; older builds
        // emit the raw object without a type field).
        finalDossier = payload?.payload || payload?.dossier || payload;
        handlers.onComplete?.(finalDossier);
      } else {
        handlers.onProgress?.(payload);
      }
    };

    try {
      while (true) {
        const { value, done } = await reader.read();
        if (done) break;
        buffer += decoder.decode(value, { stream: true });
        let idx: number;
        // SSE events are delimited by a blank line.
        while ((idx = buffer.indexOf('\n\n')) !== -1) {
          const block = buffer.slice(0, idx);
          buffer = buffer.slice(idx + 2);
          if (block.trim()) flushEvent(block);
        }
      }
      if (buffer.trim()) flushEvent(buffer);
    } catch (err: any) {
      handlers.onError?.(err);
      throw err;
    }
    return finalDossier;
  }

  /**
   * Resolve a pending MCP confirmation. ``traceId`` comes from the
   * ``confirm_request`` SSE event. ``approved`` is the user's choice.
   * Returns true when the broker accepted the resolution (false means
   * it had already timed out or the POST hit the wrong replica).
   */
  async resolveMcpConfirmation(traceId: string, approved: boolean, note?: string): Promise<boolean> {
    if (!this.api) throw new Error('API service not initialized');
    try {
      const { data } = await this.api.post(
        `/api/mcp/confirm/${encodeURIComponent(traceId)}`,
        { approved, note },
        { timeout: 15000 },
      );
      return Boolean(data?.resolved);
    } catch (err: any) {
      if (err?.response?.status === 404) return false;
      throw err;
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
  signal?: AbortSignal,
  extraParams?: Record<string, any>
): Promise<any> {
  return apiService.triggerGeointAnalysis(latitude, longitude, module, userQuery, userContext, screenshot, signal, extraParams);
}

export async function triggerGeointMobility(latitude: number, longitude: number, userContext?: string): Promise<any> {
  return apiService.triggerGeointMobility(latitude, longitude, userContext);
}

export async function sendTerrainChatMessage(
  sessionId: string | null,
  message: string,
  latitude: number,
  longitude: number,
  screenshot?: string,
  radiusKm: number = 5.0
): Promise<any> {
  return apiService.sendTerrainChatMessage(sessionId, message, latitude, longitude, screenshot, radiusKm);
}

export async function clearTerrainSession(sessionId: string): Promise<boolean> {
  return apiService.clearTerrainSession(sessionId);
}

export async function sendVisionChatMessage(
  sessionId: string | null,
  message: string,
  latitude: number,
  longitude: number,
  screenshot?: string,
  mapContext?: any  // Full map context with tile_urls, collection, bounds
): Promise<any> {
  return apiService.sendVisionChatMessage(sessionId, message, latitude, longitude, screenshot, mapContext);
}

export async function clearVisionSession(sessionId: string): Promise<boolean> {
  return apiService.clearVisionSession(sessionId);
}
