import { defineConfig } from 'vite'

export default defineConfig({
  // content.js imports design/product.json, shared with the macOS app.
  server: { fs: { allow: ['..'] } },
  build: {
    outDir: 'dist',
    assetsDir: 'assets',
  },
})
