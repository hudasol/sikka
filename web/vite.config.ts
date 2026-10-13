/// <reference types="vitest" />
import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

// Static mode reads the precomputed snapshot in public/snapshot; live mode talks
// to the API started with `sikka serve`. No other network access is made.
export default defineConfig(({ mode }) => ({
  plugins: [react()],
  base: "./",
  define: {
    __SIKKA_MODE__: JSON.stringify(mode === "static" ? "static" : "live"),
  },
  build: {
    outDir: "dist",
    sourcemap: false,
    chunkSizeWarningLimit: 1200,
  },
  test: {
    globals: true,
    environment: "jsdom",
    setupFiles: ["./src/test/setup.ts"],
    include: ["src/**/*.test.{ts,tsx}"],
    css: false,
  },
}));
