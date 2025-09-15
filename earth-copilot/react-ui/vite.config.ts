// Copyright (c) Microsoft Corporation.
// Licensed under the MIT license.

import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';

export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    host: true, // Allow external connections for debugging
    cors: true, // Enable CORS for debugging
    open: false, // Don't auto-open browser during debugging
    proxy: {
      '/health': {
        target: 'http://localhost:7071',
        changeOrigin: true,
        configure: (proxy, options) => {
          proxy.on('error', (err, req, res) => {
            console.log('🚨 Proxy error to Router Function:', err);
          });
          proxy.on('proxyReq', (proxyReq, req, res) => {
            console.log('🔄 Proxying request to Router Function:', req.url);
          });
        }
      },
      '/debug': 'http://localhost:7071',
      '/maps-config': 'http://localhost:7071',
      '/collections': 'http://localhost:7071',
      '/unified-chat': 'http://localhost:7071',
      '/chat': 'http://localhost:7071',
      '/enhanced-chat': 'http://localhost:7071',
      '/api/v2/chat': 'http://localhost:7071',
      '/query': 'http://localhost:7071',
      '/api/chat': 'http://localhost:7071',
      '/api/health': {
        target: 'http://localhost:7071',
        changeOrigin: true,
        configure: (proxy, options) => {
          proxy.on('error', (err, req, res) => {
            console.log('🚨 Proxy error to Router Function (health):', err);
          });
        }
      },
      '/api/query': {
        target: 'http://localhost:7071',
        changeOrigin: true,
        configure: (proxy, options) => {
          proxy.on('error', (err, req, res) => {
            console.log('🚨 Proxy error to Router Function (query):', err);
          });
          proxy.on('proxyReq', (proxyReq, req, res) => {
            console.log('🔄 Proxying QUERY request to Router Function:', req.url);
          });
        }
      },
      '/stac-search': {
        target: 'http://localhost:7071',
        changeOrigin: true,
        configure: (proxy, options) => {
          proxy.on('error', (err, req, res) => {
            console.log('🚨 Proxy error to Unified Function:', err);
          });
        }
      },
      '/api/stac-search': {
        target: 'http://localhost:7071',
        changeOrigin: true,
        configure: (proxy, options) => {
          proxy.on('error', (err, req, res) => {
            console.log('🚨 Proxy error to Unified Function (stac-search):', err);
          });
          proxy.on('proxyReq', (proxyReq, req, res) => {
            console.log('🔄 Proxying STAC request to Unified Function:', req.url);
          });
        }
      },
      '/mcp-query': 'http://localhost:7071',
      '/mcp-status': 'http://localhost:7071',
      '/intelligent-route': 'http://localhost:7071',
      '/veda': 'http://localhost:7071',
      '/search': 'http://localhost:7071'
    }
  },
  build: {
    sourcemap: true, // Enable source maps for debugging
    rollupOptions: {
      output: {
        sourcemap: true
      }
    }
  },
  define: {
    // Enable debugging in development
    __DEV__: JSON.stringify(true),
    // Add debugging flags
    'process.env.DEBUG_MODE': JSON.stringify(true)
  }
});
