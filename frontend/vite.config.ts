import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import http from 'node:http'

const keepAliveAgent = new http.Agent({
  keepAlive: true,
  maxSockets: 30,
  keepAliveMsecs: 10000,
})

export default defineConfig({
  plugins: [react()],
  server: {
    host: '0.0.0.0',
    port: 5174,
    strictPort: false,
    allowedHosts: true,
    proxy: {
      '/api':      { target: 'http://127.0.0.1:8000', changeOrigin: true, agent: keepAliveAgent },
      '/tenders':  { target: 'http://127.0.0.1:8000', changeOrigin: true, agent: keepAliveAgent },
      '/job':      { target: 'http://127.0.0.1:8000', changeOrigin: true, agent: keepAliveAgent },
      '/jobs':     { target: 'http://127.0.0.1:8000', changeOrigin: true, agent: keepAliveAgent },
      '/storage':  { target: 'http://127.0.0.1:8000', changeOrigin: true, agent: keepAliveAgent },
      '/health':   { target: 'http://127.0.0.1:8000', changeOrigin: true, agent: keepAliveAgent },
    },
  },
})
