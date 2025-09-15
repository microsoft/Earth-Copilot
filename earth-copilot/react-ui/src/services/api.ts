// Copyright (c) Microsoft Corporation.
// Licensed under the MIT license.

import axios, { AxiosInstance, AxiosResponse, AxiosError } from 'axios';

// Use Vite proxy for local development to avoid CORS issues
// The proxy is configured in vite.config.ts to route /api/* to localhost:7071
const API_BASE = window.location.origin; // Use relative URLs to leverage Vite proxy

// Debug mode check - force enable for debugging
const DEBUG_MODE = true; // (import.meta as any)?.env?.DEV || false;

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
        timeout: 120000, // Increased to 2 minutes for complex queries
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

      console.log('API service initialized successfully');
      console.log('API base URL:', API_BASE || 'relative (using Vite proxy)');
      console.log('Debug mode:', DEBUG_MODE ? 'ENABLED' : 'DISABLED');
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
    try {
      // Use the new private collections endpoint for VEDA data
      return await this.getPrivateCollections();
    } catch (error) {
      console.error('Failed to fetch VEDA datasets:', error);
      // Return fallback VEDA datasets
      return [
        {
          id: 'barc-thomasfire',
          title: 'Burn Area Reflectance Classification for Thomas Fire',
          description: 'BARC from BAER program for Thomas fire, 2017'
        },
        {
          id: 'blizzard-era5-pressure',
          title: 'Blizzard ERA5 Surface Pressure',
          description: 'Surface pressure from ERA5 during blizzard events'
        },
        {
          id: 'blizzard-era5-2m-temp',
          title: 'Blizzard ERA5 2m Temperature',
          description: '2m temperature from ERA5 during blizzard events'
        }
      ];
    }
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

  async sendChatMessage(message: string, datasetId?: string, conversationId?: string, messageHistory?: ChatMessage[]): Promise<any> {
    console.log('API service sendChatMessage called with:', { message, datasetId, conversationId, historyLength: messageHistory?.length });

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

      console.log('Making unified query request to', endpoint, ':', requestData);

      const response = await this.api.post(endpoint, requestData);
      console.log('Query response received:', response);
      console.log('Query response status:', response.status);
      console.log('Query response data:', response.data);

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

  async sendEnhancedChatMessage(message: string, datasetId?: string, conversationId?: string, messageHistory?: ChatMessage[]): Promise<any> {
    return this.sendChatMessage(message, datasetId, conversationId, messageHistory);
  }

  async searchPrivateData(query: string, collection_id?: string): Promise<any> {
    console.log('API service searchPrivateData called with:', { query, collection_id });

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

      console.log('Making private search request to', endpoint, ':', requestData);

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

  async getPrivateCollections(): Promise<Dataset[]> {
    console.log('API service getPrivateCollections called');

    if (!this.api) {
      console.error('API instance is not initialized');
      throw new Error('API service not initialized');
    }

    try {
      const endpoint = '/api/private-collections';
      
      console.log('Making private collections request to', endpoint);

      const response = await this.api.get(endpoint);
      console.log('Private collections response received:', response);
      console.log('Private collections response status:', response.status);
      console.log('Private collections response data:', response.data);

      if (response.data && response.data.success && response.data.collections) {
        return response.data.collections.map((collection: any) => ({
          id: collection.id,
          title: collection.title,
          description: collection.description || '',
          type: 'veda'
        }));
      }

      // Fallback to empty array
      return [];

    } catch (error: any) {
      console.error('Private collections API error:', error);
      if (error.response) {
        console.error('Error response status:', error.response.status);
        console.error('Error response data:', error.response.data);
        console.error('Error response headers:', error.response.headers);
      }

      // Return fallback collections on error
      return [
        { id: 'barc-thomasfire', title: 'Burn Area Reflectance Classification for Thomas Fire', description: 'BARC from BAER program for Thomas fire, 2017', type: 'veda' },
        { id: 'blizzard-era5-pressure', title: 'Blizzard ERA5 Surface Pressure', description: 'Surface pressure from ERA5 during blizzard events', type: 'veda' },
        { id: 'blizzard-era5-2m-temp', title: 'Blizzard ERA5 2m Temperature', description: '2m temperature from ERA5 during blizzard events', type: 'veda' },
        { id: 'bangladesh-landcover-2001-2020', title: 'Bangladesh Land Cover (2001-2020)', description: 'MODIS-based land cover classification maps', type: 'veda' }
      ];
    }
  }
}

export const apiService = new ApiService();
