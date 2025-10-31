// Copyright (c) Microsoft Corporation.
// Licensed under the MIT license.

import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';

// Container App API URL for production (update with your deployed URL)
const CONTAINER_APP_URL = process.env.VITE_API_BASE_URL || 'https://your-container-app.azurecontainerapps.io';

export default defineConfig(({ command, mode }) => {
  const isDev = command === 'serve';
  const isProd = mode === 'production';
  
  return {
    plugins: [react()],
    base: isProd ? './' : '/',
    server: isDev ? {
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
        // '/mcp-query': 'http://localhost:7071', // DISABLED - MCP server functionality
        // '/mcp-status': 'http://localhost:7071', // DISABLED - MCP server functionality
        '/intelligent-route': 'http://localhost:7071',
        '/veda': 'http://localhost:7071',
        '/search': 'http://localhost:7071'
      }
    } : undefined,
    build: {
      outDir: 'dist',
      sourcemap: !isProd, // Disable source maps in production
      minify: isProd ? 'esbuild' : false,
      rollupOptions: {
        output: {
          manualChunks: isProd ? {
            vendor: ['react', 'react-dom'],
            query: ['@tanstack/react-query'],
            utils: ['axios']
          } : undefined
        }
      }
    },
    define: {
      // Environment-specific configurations
      __DEV__: JSON.stringify(isDev),
      'process.env.DEBUG_MODE': JSON.stringify(isDev),
      'import.meta.env.VITE_API_BASE_URL': JSON.stringify(
        isDev ? 'http://localhost:8000' : CONTAINER_APP_URL
      ),
      'import.meta.env.VITE_CONTAINER_APP_URL': JSON.stringify(CONTAINER_APP_URL)
    }
  };
});