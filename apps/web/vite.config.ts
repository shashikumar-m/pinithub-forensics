import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';
import { resolve } from 'node:path';

export default defineConfig({
  plugins: [react()],
  resolve: {
    alias: {
      '@': resolve(__dirname, './src'),
      '@pinithub/shared': resolve(__dirname, '../../packages/shared/src'),
    },
  },
  server: {
    port: 5173,
    host: true,
    allowedHosts: true,
    proxy: {
      '/v1': {
        target: process.env.VITE_API_URL || 'http://localhost:4000',
        changeOrigin: true,
        timeout: 180000,
      },
    },
  },
  build: {
    outDir: 'dist',
    sourcemap: true,
  },
});
