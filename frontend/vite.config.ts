import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

/**
 * macOS note:
 *  Backend always runs locally (not in Docker) because Docker Desktop
 *  cannot access the Mac's webcam.  So the proxy always points to localhost.
 *
 *  Inside full Docker deploys (Linux servers) set:
 *    VITE_BACKEND_HOST=backend
 *  in the frontend container env, which overrides the default.
 */
export default defineConfig({
  plugins: [react()],
  server: {
    host: '0.0.0.0',
    port: 5173,
    strictPort: true,
    proxy: {
      // All /api requests → FastAPI REST
      '/api': {
        target: 'http://localhost:8000',
        changeOrigin: true,
        secure: false,
      },
      // WebSocket upgrade → FastAPI /ws endpoint
      '/ws': {
        target: 'ws://localhost:8000',
        ws: true,
        changeOrigin: true,
        secure: false,
      },
    },
  },
})
