import { defineConfig } from 'vitest/config';
import react from '@vitejs/plugin-react';
import { loadEnv } from 'vite';
import process from 'node:process';

export default defineConfig(({ mode }) => {
  if (process.env.CF_PAGES === '1' && mode === 'production') {
    const value = process.env.VITE_API_BASE_URL || loadEnv(mode, process.cwd(), 'VITE_').VITE_API_BASE_URL;
    let url: URL;
    try {
      url = new URL(value ?? '');
    } catch {
      throw new Error('Cloudflare Pages requires VITE_API_BASE_URL set to the HTTPS Cloud Run service URL.');
    }
    if (url.protocol !== 'https:' || url.hostname === 'localhost' || url.username || url.password ||
      url.search || url.hash || (url.pathname !== '/' && url.pathname !== '')) {
      throw new Error('VITE_API_BASE_URL must be a public HTTPS origin without a path or credentials.');
    }
  }
  return {
  plugins: [react()],
  // MapLibre's worker is an ES module worker.
  worker: { format: 'es' },
  build: { chunkSizeWarningLimit: 1200 },
  test: {
    environment: 'node',
    include: ['src/**/*.test.ts'],
  },
  };
});
