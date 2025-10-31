// Copyright (c) Microsoft Corporation.
// Licensed under the MIT license.

import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';

export default defineConfig({
  plugins: [react()],
  base: './',
  build: {
    outDir: 'dist',
    sourcemap: false, // Disable for production
    rollupOptions: {
      output: {
        manualChunks: {
          vendor: ['react', 'react-dom'],
          query: ['@tanstack/react-query']
        }
      }
    }
  },
  define: {
    __DEV__: JSON.stringify(false),
    'process.env.DEBUG_MODE': JSON.stringify(false),
    'process.env.VITE_API_BASE_URL': JSON.stringify(process.env.VITE_API_BASE_URL || 'https://earthcopilot-router-functionapp.azurewebsites.net')
  }
});