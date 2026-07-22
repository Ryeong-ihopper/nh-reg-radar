import react from "@vitejs/plugin-react";
import { defineConfig } from "vitest/config";

import { developmentApiProxy } from "./dev-api-proxy";

export default defineConfig({
  plugins: [react()],
  server: {
    // Development VM ingress terminates on this hostname before forwarding to
    // Vite. Keep the allow-list explicit rather than weakening host validation.
    allowedHosts: ["nh-compliance.ihopper.co.kr"],
    proxy: developmentApiProxy(process.env.VITE_API_PROXY_TARGET),
  },
  test: {
    environment: "jsdom",
    globals: true,
    setupFiles: "./src/test/setup.ts",
  },
});
