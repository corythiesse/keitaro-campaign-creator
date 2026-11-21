import react from "@vitejs/plugin-react";
import { loadEnv } from "vite";
import { defineConfig } from "vitest/config";

export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, process.cwd(), "");
  // Use an explicit IPv4 address: on macOS "localhost" may resolve to ::1,
  // while uvicorn binds 127.0.0.1 by default. A different service on [::1]:8000
  // would silently receive the proxied /api requests.
  const apiTarget =
    process.env.VITE_API_PROXY_TARGET || env.VITE_API_PROXY_TARGET || "http://127.0.0.1:8000";
  // Server-side only: not exposed through import.meta.env. The production
  // deployment is expected to add this header in the reverse proxy.
  const apiToken = process.env.API_AUTH_TOKEN || env.API_AUTH_TOKEN;
  const proxyHeaders = apiToken ? { "X-API-Token": apiToken } : undefined;
  const proxy = {
    "/api": {
      target: apiTarget,
      changeOrigin: true,
      headers: proxyHeaders
    }
  };

  return {
    plugins: [react()],
    server: { proxy },
    preview: { proxy },
    build: {
      rollupOptions: {
        output: {
          manualChunks: {
            react: ["react", "react-dom", "react-router-dom"],
            mui: ["@mui/material", "@mui/icons-material", "@emotion/react", "@emotion/styled"]
          }
        }
      }
    },
    test: {
      environment: "jsdom",
      globals: true,
      setupFiles: "./src/test/setup.ts",
      clearMocks: true,
      restoreMocks: true,
      coverage: {
        provider: "v8",
        reporter: ["text", "html"],
        include: ["src/**/*.{ts,tsx}"],
        exclude: ["src/main.tsx", "src/vite-env.d.ts", "src/test/**", "src/shared/api/types.ts"],
        thresholds: {
          lines: 70,
          functions: 70,
          branches: 60,
          statements: 70
        }
      }
    }
  };
});
