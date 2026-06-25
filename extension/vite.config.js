import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';
import { resolve } from 'path';
import { readFileSync, writeFileSync } from 'fs';
import { config as loadDotenv } from 'dotenv';

// Build mode picks the env file (gitignored) AND the output dir, so a localhost
// build and the prod build can coexist and be loaded in Chrome side by side:
//   `npm run build`       (--mode development) -> .env.dev,  dist/       (dev, localhost)
//   `npm run build:prod`  (--mode production)  -> .env.prod, dist/       (Web Store / live)
//   `npm run build:local` (--mode devlocal)    -> .env.dev,  dist-local/ (separate instance)
// `build` must pin --mode development: a bare `vite build` defaults the mode to
// 'production', which would load .env.prod and point dev at the live backend.
// ('local' is reserved by Vite — it clashes with the .env.local postfix.)
// Values are injected at build time and never logged.
export default defineConfig(({ mode }) => {
  const isProd = mode === 'production';
  const isLocal = mode === 'devlocal';
  const envFile = isProd ? '.env.prod' : '.env.dev';
  const env = loadDotenv({ path: resolve(__dirname, '..', envFile) }).parsed || {};
  const pick = (key) => env[key] || process.env[key] || '';

  // A separate output dir for the local instance so it never clobbers the prod
  // build (and vice-versa) — load both unpacked extensions at once.
  const outDir = isLocal ? 'dist-local' : 'dist';

  // config.js sets globalThis.APP_URL for BOTH the popup and the service worker
  // (importScripts). Strip any trailing slash so `${APP_URL}/path` stays clean.
  const appUrl = (pick('APP_URL') || 'http://localhost:8000').replace(/\/$/, '');

  // The committed manifest carries every host the extension might touch across dev
  // and prod (localhost backends, the dev Clerk *.accounts.dev domain, etc.). The
  // Web Store build must request only the live hosts it actually uses, both to pass
  // review and to keep the install-time permission prompt honest. In prod the
  // backend is APP_URL, the web app + Clerk FAPI live under on-tracker.com, and
  // OnTrack is the capture target — nothing else.
  const PROD_HOST_PERMISSIONS = [
    'https://ontrack.deakin.edu.au/*',
    'https://on-tracker.com/*',
    'https://*.on-tracker.com/*',
    'https://ontracker-production.up.railway.app/*',
  ];

  return {
    plugins: [
      react(),
      {
        // Overwrite the copied config.js with the env-selected backend URL, and
        // for the local instance give the manifest a distinct identity so Chrome
        // treats it as a different extension from the prod build.
        name: 'write-app-url-config',
        closeBundle() {
          writeFileSync(
            resolve(__dirname, outDir, 'config.js'),
            `globalThis.APP_URL = ${JSON.stringify(appUrl)};\n`
          );

          const manifestPath = resolve(__dirname, outDir, 'manifest.json');
          const manifest = JSON.parse(readFileSync(manifestPath, 'utf8'));

          if (isProd) {
            // Narrow host_permissions to the live hosts only — drop the localhost
            // backends, the dev Clerk *.accounts.dev domain, and dead legacy hosts
            // the committed manifest keeps for dev convenience.
            manifest.host_permissions = PROD_HOST_PERMISSIONS;
          } else {
            // Dev/devlocal point APP_URL at a localhost backend, but the committed
            // manifest omits the localhost hosts so the prod build stays clean.
            // Merge them back in from manifest.dev.json (overlay, not a full copy,
            // so the shared hosts can't drift out of sync).
            const devHosts = JSON.parse(
              readFileSync(resolve(__dirname, 'manifest.dev.json'), 'utf8')
            ).host_permissions;
            manifest.host_permissions = [
              ...manifest.host_permissions,
              ...devHosts.filter((h) => !manifest.host_permissions.includes(h)),
            ];
          }

          if (isLocal) {
            // Chrome refuses to load two unpacked extensions that share an ID.
            // The fixed `key` pins the prod ID, so strip it here (Chrome assigns
            // a path-derived ID instead) and relabel so the two are obvious in
            // chrome://extensions.
            delete manifest.key;
            manifest.name = `${manifest.name} (local)`;
          }

          writeFileSync(manifestPath, JSON.stringify(manifest, null, 2) + '\n');
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
      outDir,
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
