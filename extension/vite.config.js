import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';
import { resolve } from 'path';
import { writeFileSync } from 'fs';
import { config as loadDotenv } from 'dotenv';

// Build mode picks the env file (gitignored): `vite build` -> .env.dev (local),
// `vite build --mode production` -> .env.prod (Web Store / live Clerk). Values
// are injected at build time and never logged.
export default defineConfig(({ mode }) => {
  const envFile = mode === 'production' ? '.env.prod' : '.env.dev';
  const env = loadDotenv({ path: resolve(__dirname, '..', envFile) }).parsed || {};
  const pick = (key) => env[key] || process.env[key] || '';

  // config.js sets globalThis.APP_URL for BOTH the popup and the service worker
  // (importScripts). Strip any trailing slash so `${APP_URL}/path` stays clean.
  const appUrl = (pick('APP_URL') || 'http://localhost:8000').replace(/\/$/, '');

  return {
    plugins: [
      react(),
      {
        // Overwrite the copied dist/config.js with the env-selected backend URL.
        name: 'write-app-url-config',
        closeBundle() {
          writeFileSync(
            resolve(__dirname, 'dist', 'config.js'),
            `globalThis.APP_URL = ${JSON.stringify(appUrl)};\n`
          );
        },
      },
    ],
    define: {
      'import.meta.env.VITE_CLERK_PUBLISHABLE_KEY': JSON.stringify(
        pick('VITE_CLERK_PUBLISHABLE_KEY')
      ),
      'import.meta.env.VITE_CLERK_FRONTEND_URL': JSON.stringify(
        pick('VITE_CLERK_FRONTEND_URL')
      ),
      'import.meta.env.VITE_CLERK_SYNC_HOST': JSON.stringify(
        pick('VITE_CLERK_SYNC_HOST')
      ),
      'import.meta.env.VITE_WEB_APP_URL': JSON.stringify(
        pick('VITE_WEB_APP_URL')
      ),
    },
    build: {
      outDir: 'dist',
      emptyOutDir: true,
      rollupOptions: {
        input: { popup: resolve(__dirname, 'popup.html') },
        output: {
          entryFileNames: 'assets/[name].js',
          chunkFileNames: 'assets/[name].js',
          assetFileNames: 'assets/[name].[ext]',
        },
      },
    },
  };
});
