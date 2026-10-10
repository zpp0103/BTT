import { defineConfig } from "vite";
import vue from "@vitejs/plugin-vue";
import { fileURLToPath, URL } from "node:url";
import { writeFileSync } from "node:fs";

export default defineConfig({
  plugins: [
    vue(),
    {
      name: "btt-ui-version",
      closeBundle() {
        writeFileSync(fileURLToPath(new URL("../installed/.uiversion", import.meta.url)), "btt-0.1.0\n");
      },
    },
  ],
  base: "/",
  build: {
    outDir: "../installed",
    emptyOutDir: true,
    sourcemap: false,
  },
  resolve: {
    alias: {
      "@": fileURLToPath(new URL("./src", import.meta.url)),
    },
  },
  server: {
    proxy: {
      "/api": "http://127.0.0.1:8080",
      "/ui_version": "http://127.0.0.1:8080",
    },
  },
  test: {
    environment: "jsdom",
  },
});
