/// <reference types="vitest" />
import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';
import tailwindcss from '@tailwindcss/vite';
import { fileURLToPath, URL } from 'node:url';

// The build lands inside the Python package. That is what makes `pip install
// jobsheet` enough: no Node at run time, no second server, no CORS.
export default defineConfig({
  plugins: [react(), tailwindcss()],
  resolve: {
    alias: { '@': fileURLToPath(new URL('./src', import.meta.url)) },
  },
  build: {
    outDir: '../src/jobsheet/web',
    emptyOutDir: true,
    // The page is served from a strict CSP with no external origins, so every
    // asset has to be local and every chunk has to be a plain script.
    assetsDir: 'assets',
  },
  server: {
    port: 5173,
    // In development the interface runs on Vite and the API on the Python
    // process; proxying keeps them one origin, exactly as in production.
    proxy: { '/api': 'http://127.0.0.1:8765' },
  },
  test: {
    environment: 'jsdom',
    globals: true,
    setupFiles: ['./src/test/setup.ts'],
    css: false,
  },
});
