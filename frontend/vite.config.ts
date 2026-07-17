import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// PWA: o service worker (public/sw.js) e o manifest são servidos estáticos.
export default defineConfig({
  plugins: [react()],
  server: { port: 5173 },
  build: { outDir: "dist" },
});
