import react from "@vitejs/plugin-react-swc";
import { defineConfig } from "vite";
import { VitePWA } from "vite-plugin-pwa";

// https://vite.dev/config/
export default defineConfig({
  plugins: [
    react({
      jsxImportSource: "@emotion/react",
    }),
    VitePWA({
      registerType: "autoUpdate",
      devOptions: { enabled: true },
      manifest: {
        name: "Kdb っぽいなにか",
        icons: [
          {
            sizes: "192x192",
            src: "icon-192x192.png",
            type: "image/png",
          },
          {
            sizes: "512x512",
            src: "icon-512x512.png",
            type: "image/png",
          },
          {
            sizes: "512x512",
            src: "icon-512x512.png",
            type: "image/png",
            purpose: "maskable",
          },
        ],
      },
      workbox: {
        maximumFileSizeToCacheInBytes: 10 * 1024 * 1024, // 10 MB までキャッシュ
        disableDevLogs: true,
        runtimeCaching: [
          {
            urlPattern: /\.(css|js)$/,
            handler: "StaleWhileRevalidate",
          },
          {
            urlPattern: /\.ttf/,
            handler: "CacheFirst",
          },
        ],
      },
    }),
  ],
  resolve: {
    alias: {
      "@": `${__dirname}/src`,
    },
  },
  base: "/alternative-tsukuba-kdb-2026-pre/",
});
