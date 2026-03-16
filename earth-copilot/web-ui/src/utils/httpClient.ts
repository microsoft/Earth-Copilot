// Copyright (c) Microsoft Corporation.
// Licensed under the MIT license.

import axios, { AxiosInstance, AxiosRequestConfig, AxiosResponse } from 'axios';
import { getApiUrl, getEnvironmentInfo, isDev } from '../config/api';

// Create axios instance with default configuration
const createHttpClient = (): AxiosInstance => {
  const envInfo = getEnvironmentInfo();
  
  const client = axios.create({
    timeout: 30000, // 30 seconds timeout
    headers: {
      'Content-Type': 'application/json',
      'Accept': 'application/json'
    }
  });

  // Request interceptor
  client.interceptors.request.use(
    (config) => {
      // Transform relative URLs to absolute URLs using our API configuration
      if (config.url && config.url.startsWith('/')) {
        config.url = getApiUrl(config.url);
      }
      
      // Add debug logging in development
      if (isDev()) {
        console.log(` API Request: ${config.method?.toUpperCase()} ${config.url}`);
      }
      
      return config;
    },
    (error) => {
      if (isDev()) {
        console.error(' Request Error:', error);
      }
      return Promise.reject(error);
    }
  );

  // Response interceptor
  client.interceptors.response.use(
    (response: AxiosResponse) => {
      if (isDev()) {
        console.log(` API Response: ${response.status} ${response.config.url}`);
      }
      return response;
    },
    (error) => {
      if (isDev()) {
        console.error(' Response Error:', error.response?.status, error.response?.data);
      }
      
      // Handle common errors
      if (error.response?.status === 404) {
        console.warn(' API endpoint not found:', error.config?.url);
      } else if (error.response?.status >= 500) {
        console.error(' Server error:', error.response?.data);
      }
      
      return Promise.reject(error);
    }
  );

  return client;
};

// Create the singleton HTTP client
export const httpClient = createHttpClient();

// Convenience methods
export const api = {
  get: <T = any>(url: string, config?: AxiosRequestConfig): Promise<AxiosResponse<T>> => 
    httpClient.get<T>(url, config),
  
  post: <T = any>(url: string, data?: any, config?: AxiosRequestConfig): Promise<AxiosResponse<T>> => 
    httpClient.post<T>(url, data, config),
  
  put: <T = any>(url: string, data?: any, config?: AxiosRequestConfig): Promise<AxiosResponse<T>> => 
    httpClient.put<T>(url, data, config),
  
  delete: <T = any>(url: string, config?: AxiosRequestConfig): Promise<AxiosResponse<T>> => 
    httpClient.delete<T>(url, config),
  
  // Health check method
  healthCheck: async (): Promise<boolean> => {
    try {
      const response = await httpClient.get('/health');
      return response.status === 200;
    } catch (error) {
      console.warn(' Health check failed:', error);
      return false;
    }
  }
};

export default httpClient;