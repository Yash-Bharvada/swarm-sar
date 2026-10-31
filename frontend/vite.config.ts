/// <reference types="vitest" />
import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';
import { fileURLToPath } from 'node:url';

export default defineConfig({
  plugins: [react()],
  server: {
    proxy: { '/api/ppo': { target: 'http://127.0.0.1:8765', changeOrigin: true } },
    // Original evidence lives beside the frontend. Serve only those asset paths in development.
    fs: { allow: ['.', '../docs/media', '../models/ppo_754k/training_definition.json', '../models/ppo_754k/ppo_754k_review.json'].map(path => fileURLToPath(new URL(path, import.meta.url))) },
  },
  build: {
    chunkSizeWarningLimit: 1500,
    rollupOptions: {
      output: {
        manualChunks: {
          three: ['three'],
          r3f: ['@react-three/fiber', '@react-three/drei'],
        },
      },
    },
  },
  test: {
    environment: 'node',
    include: ['src/tests/**/*.test.ts'],
    globals: true,
  },
});
