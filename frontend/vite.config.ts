import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// The backend FastAPI service runs on port 8000 (see the "Backend API" workflow).
// We proxy its routes through the Vite dev server so the browser only ever
// talks to a single relative origin (works through the Replit preview proxy,
// avoids CORS, and avoids hardcoding any host/domain in app code).
const BACKEND_TARGET = "http://127.0.0.1:8000";

export default defineConfig({
  plugins: [react()],
  server: {
    host: "0.0.0.0",
    port: 5000,
    strictPort: true,
    allowedHosts: true,
    proxy: {
      "/tenders": BACKEND_TARGET,
      "/job": BACKEND_TARGET,
      "/jobs": BACKEND_TARGET,
      "/storage": BACKEND_TARGET,
      "/health": BACKEND_TARGET,
    },
  },
});
