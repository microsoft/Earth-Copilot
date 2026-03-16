// Copyright (c) Microsoft Corporation.
// Licensed under the MIT license.

// Environment-specific API configuration
// In production, VITE_API_BASE_URL is set dynamically during GitHub Actions build
// by querying the Azure Container App URL
const isDevelopment = import.meta.env.DEV;
const API_BASE_URL = isDevelopment 
  ? 'http://localhost:8000'  // Local development backend
  : import.meta.env.VITE_API_BASE_URL || '';  // Production: injected at build time, fallback to same-origin

// API endpoint configuration
const createEndpoint = (path: string) => `${API_BASE_URL}${path}`;

const BASE_CONFIG = {
  '/health': createEndpoint('/health'),
  '/debug': createEndpoint('/debug'),
  '/maps-config': createEndpoint('/maps-config'),
  '/collections': createEndpoint('/collections'),
  '/unified-chat': createEndpoint('/unified-chat'),
  '/chat': createEndpoint('/chat'),
  '/enhanced-chat': createEndpoint('/enhanced-chat'),
  '/api/v2/chat': createEndpoint('/api/v2/chat'),
  '/query': createEndpoint('/query'),
  '/api/chat': createEndpoint('/api/chat'),
  '/api/health': createEndpoint('/api/health'),
  '/api/query': createEndpoint('/api/query'),
  '/stac-search': createEndpoint('/stac-search'),
  '/api/stac-search': createEndpoint('/api/stac-search'),
  // '/mcp-query': createEndpoint('/mcp-query'), // DISABLED - MCP server functionality
  // '/mcp-status': createEndpoint('/mcp-status'), // DISABLED - MCP server functionality
  '/intelligent-route': createEndpoint('/intelligent-route'),
  '/veda': createEndpoint('/veda'),
  '/search': createEndpoint('/search')
};

// Helper function to get the full API URL for any endpoint
export const getApiUrl = (endpoint: string): string => {
  // Remove leading slash if present
  const cleanEndpoint = endpoint.startsWith('/') ? endpoint : `/${endpoint}`;
  return (BASE_CONFIG as Record<string, string>)[cleanEndpoint] || createEndpoint(cleanEndpoint);
};

// Helper function to check if we're in development mode
export const isDev = (): boolean => isDevelopment;

// Helper function to get environment info
export const getEnvironmentInfo = () => ({
  isDevelopment,
  apiBaseUrl: API_BASE_URL,
  mode: import.meta.env.MODE
});

export const API_ENDPOINTS = BASE_CONFIG;
export { API_BASE_URL };