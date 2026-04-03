import { defineConfig } from 'vitest/config';
import react from '@vitejs/plugin-react';

const buildVersion = new Date().toISOString().replace(/[-:.TZ]/g, '').slice(0, 14);

export default defineConfig({
  plugins: [
    react(),
    {
      name: 'cache-bust-entry-assets',
      apply: 'build',
      enforce: 'post',
      transformIndexHtml(html) {
        return html
          .replace('/assets/app.js', `/assets/app.js?v=${buildVersion}`)
          .replace('/assets/app.css', `/assets/app.css?v=${buildVersion}`);
      },
    },
  ],
  build: {
    rollupOptions: {
      output: {
        // Keep the HTML entrypoint stable so Telegram's webview cache
        // doesn't point at a no-longer-existing hashed bootstrap file.
        entryFileNames: 'assets/app.js',
        assetFileNames: (assetInfo) => {
          if (assetInfo.name?.endsWith('.css')) {
            return 'assets/app.css';
          }

          return 'assets/[name]-[hash][extname]';
        },
      },
    },
  },
  resolve: {
    extensions: ['.mts', '.ts', '.tsx', '.mjs', '.js', '.jsx', '.json'],
  },
  test: {
    environment: 'jsdom',
    setupFiles: './setupTests.ts',
  },
  server: {
    host: '0.0.0.0',
    port: 5173,
    allowedHosts: true,
    proxy: {
      '/api': {
        target: 'http://backend:8000',
        changeOrigin: true,
      },
    },
  },
});
