import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

// Build output is the committed bundle served by FastAPI from the wheel
// (SPECIFICATION.md D24): end users need no Node.
export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      "/api": "http://127.0.0.1:8091",
    },
  },
  build: {
    outDir: "../src/bizkit/api/static",
    emptyOutDir: true,
  },
});
