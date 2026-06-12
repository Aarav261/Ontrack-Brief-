import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';
import { resolve } from 'path';
import { config as loadDotenv } from 'dotenv';

// Single source of truth: the repo-root .env.dev (gitignored). Inject the
// Clerk publishable key + frontend URL at build time, same as the web app.
const rootEnv =
  loadDotenv({ path: resolve(__dirname, '..', '.env.dev') }).parsed || {};
const pick = (key) => rootEnv[key] || process.env[key] || '';

export default defineConfig({
  plugins: [react()],
  define: {
    'import.meta.env.VITE_CLERK_PUBLISHABLE_KEY': JSON.stringify(
      pick('VITE_CLERK_PUBLISHABLE_KEY')
    ),
    'import.meta.env.VITE_CLERK_FRONTEND_URL': JSON.stringify(
      pick('VITE_CLERK_FRONTEND_URL')
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
});
