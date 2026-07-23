import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

export default defineConfig({
  plugins: [react()],
  server: {
    host: '0.0.0.0',
    port: 5173,
    allowedHosts: true,
    proxy: {
      '/api':      { target: 'http://127.0.0.1:5000', changeOrigin: true },
      '/tenders':  { target: 'http://127.0.0.1:5000', changeOrigin: true },
      '/job':      { target: 'http://127.0.0.1:5000', changeOrigin: true },
      '/jobs':     { target: 'http://127.0.0.1:5000', changeOrigin: true },
      '/storage':  { target: 'http://127.0.0.1:5000', changeOrigin: true },
      '/health':   { target: 'http://127.0.0.1:5000', changeOrigin: true },
    },
  },
})
