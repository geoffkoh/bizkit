import react from "@vitejs/plugin-react";
// `vitest/config` re-exports vite's defineConfig with the `test` block typed;
// vitest is a devDependency, so this never reaches an end user's install.
import { defineConfig } from "vitest/config";

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
  test: {
    // jsdom for component tests; `globals` stays off so describe/it/expect are
    // explicit imports, matching the project's strict-typing convention.
    environment: "jsdom",
    globals: false,
    setupFiles: ["./src/test/setup.ts"],
    include: ["src/**/*.test.{ts,tsx}"],
    restoreMocks: true,
  },
});
