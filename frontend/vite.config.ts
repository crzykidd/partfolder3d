import path from 'path'
import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'

export default defineConfig({
  plugins: [
    react(),
    tailwindcss(),
  ],
  resolve: {
    alias: {
      '@': path.resolve(__dirname, './src'),
    },
  },
  server: {
    port: 5173,
    // Bind all interfaces so the nginx container can reach the dev server.
    host: true,
    // Accept any Host header. This is a dev-only server that runs behind the
    // nginx reverse proxy and is reached via whatever hostname the operator
    // points at it (localhost, a LAN host like crzydev.home.arpa, an IP, …).
    // Without this, Vite's host check rejects non-localhost hosts with
    // "Blocked request. This host is not allowed."
    allowedHosts: true,
    proxy: {
      // When running `npm run dev` standalone (outside docker), proxy /api
      // to the backend running locally on port 8000.
      '/api': {
        target: 'http://localhost:8000',
        changeOrigin: true,
      },
    },
  },
})
