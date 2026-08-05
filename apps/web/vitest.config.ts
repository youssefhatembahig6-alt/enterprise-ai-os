import react from "@vitejs/plugin-react";
import { defineConfig } from "vitest/config";

/**
 * Component tests only. Vite is no longer the application bundler — Next is —
 * but Vitest still needs a JSX transform, which is all `@vitejs/plugin-react`
 * does here.
 *
 * End-to-end coverage (navigation, viewport widths, axe) lives in `e2e/` and
 * runs under Playwright, so it is excluded from this project.
 */
export default defineConfig({
  plugins: [react()],
  test: {
    environment: "jsdom",
    globals: true,
    setupFiles: ["./tests/setup.ts"],
    include: ["tests/**/*.test.{ts,tsx}"],
    exclude: ["e2e/**", "node_modules/**", ".next/**"],
  },
});
