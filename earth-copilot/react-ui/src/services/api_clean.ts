// Copyright (c) Microsoft Corporation.
// Licensed under the MIT license.

import axios, { AxiosInstance } from 'axios';

// Point directly to Docker container since proxy isn't working
// This avoids CORS issues since the function app has proper CORS headers
const API_BASE = (import.meta as any)?.env?.VITE_API_BASE?.trim?.() || 'http://localhost:7071';

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
}

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

      console.log('API service initialized successfully');
      console.log('API base URL:', API_BASE || 'same-origin');
    } catch (error) {
      console.error('Failed to create axios instance:', error);
      this.api = null;
      // Don't throw here, let methods handle null gracefully
    }
  }

  async getMyDatasets(): Promise<Dataset[]> {
    try {
      console.log('Fetching private datasets...');

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
      // Return sample VEDA datasets for now since we're focused on chat functionality
      return [
        {
          id: 'VEDA/VIIRS/FIRES',
          title: 'VIIRS Fire Events',
          description: 'Fire detection data from VIIRS instrument'
        },
        {
          id: 'VEDA/S2/CLOUDLESS',
          title: 'Sentinel-2 Cloudless',
          description: 'Cloud-free Sentinel-2 imagery composite'
        },
        {
          id: 'VEDA/GPM/IMERG',
          title: 'GPM IMERG Precipitation',
          description: 'Global precipitation measurement data'
        }
      ];
    } catch (error) {
      console.error('Failed to fetch VEDA datasets:', error);
      return [];
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
      // Use the unified /api/query endpoint only
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
}

export const apiService = new ApiService();
