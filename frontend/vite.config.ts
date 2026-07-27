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
    // jsdom only exposes localStorage/sessionStorage for a non-opaque origin,
    // so without an explicit URL the shell's persisted sidebar prefs blow up
    // on mount. Pin one that looks like the dev server.
    environmentOptions: { jsdom: { url: "http://localhost:5173/" } },
    globals: false,
    setupFiles: ["./src/test/setup.ts"],
    include: ["src/**/*.test.{ts,tsx}"],
    // `clearMocks` resets call history between tests; `restoreMocks` alone
    // restores implementations but leaves `mock.calls` intact, so a
    // "was never called" assertion could pass or fail depending on what the
    // previous test did. Both, so each test starts genuinely isolated.
    clearMocks: true,
    restoreMocks: true,
  },
});
