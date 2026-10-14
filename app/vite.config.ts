import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// Khi dev, mọi request /api được chuyển sang backend FastAPI (python -m api)
export default defineConfig({
  plugins: [react()],
  server: { port: 5173, proxy: { "/api": "http://127.0.0.1:8000" } },
});
