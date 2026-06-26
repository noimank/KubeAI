/// <reference types="vitest" />
import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import path from 'path'

export default defineConfig({
  plugins: [react()],
  resolve: {
    alias: {
      '@': path.resolve(__dirname, './src'),
    },
  },
  server: {
    port: 3000,
    proxy: {
      '/api': {
        target: 'http://localhost:8000',
        changeOrigin: true,
        ws: true,
      },
      // APISIX-routed subpaths: dev envs (/devenv/<hex>) and TensorBoard
      // (/tensorboard/<hex>) are served by the Helm-deployed APISIX gateway
      // (NodePort :30080), not the Vite dev server. Forward both, websocket
      // included (TensorBoard data-plane + dev env terminals need it).
      '/devenv': {
        target: 'http://localhost:30080',
        changeOrigin: true,
        ws: true,
      },
      '/tensorboard': {
        target: 'http://localhost:30080',
        changeOrigin: true,
        ws: true,
      },
    },
  },
  build: {
    rollupOptions: {
      output: {
        manualChunks: {
          vendor: ['react', 'react-dom'],
          antd: ['antd', '@ant-design/icons'],
          router: ['react-router', 'react-router-dom'],
        },
      },
    },
  },
  test: {
    globals: true,
    environment: 'jsdom',
    setupFiles: ['./tests/setup.ts'],
  },
})
