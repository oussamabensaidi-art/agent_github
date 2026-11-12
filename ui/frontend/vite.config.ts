import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// Construit dans ../dist, servi par FastAPI sous /ui. Aucun CDN : polices et code embarqués.
export default defineConfig({
  base: "/ui/",
  plugins: [react()],
  build: { outDir: "../dist", emptyOutDir: true, assetsInlineLimit: 0 },
  server: { port: 5173, proxy: { "/ui/api": { target: "http://localhost:8020", changeOrigin: false } } },
});
