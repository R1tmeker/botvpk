import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import { readFile, writeFile } from "node:fs/promises";
import { resolve } from "node:path";

function versionServiceWorker() {
  return {
    name: "version-service-worker",
    async closeBundle() {
      const path = resolve("dist/sw.js");
      const source = await readFile(path, "utf8");
      const release = (process.env.VITE_RELEASE_VERSION ?? "local").replace(/[^a-zA-Z0-9._-]/g, "-");
      await writeFile(path, source.replace("__BOTVPK_RELEASE__", release), "utf8");
    },
  };
}

export default defineConfig({
  plugins: [react(), versionServiceWorker()],
  build: {
    rollupOptions: {
      output: {
        manualChunks(id) {
          if (!id.includes("node_modules")) {
            return undefined;
          }
          if (id.includes("react") || id.includes("react-dom")) {
            return "vendor-react";
          }
          if (id.includes("@tanstack")) {
            return "vendor-query";
          }
          if (id.includes("lucide-react")) {
            return "vendor-icons";
          }
          return "vendor";
        },
      },
    },
  },
  server: {
    host: "0.0.0.0",
    port: 5173,
    allowedHosts: true,
  },
});
