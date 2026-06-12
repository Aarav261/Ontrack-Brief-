import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import { resolve } from 'path'
import { config as loadDotenv } from 'dotenv'

// Single source of truth for config: the repo-root .env.dev (gitignored).
// Loaded here so the VITE_ values are injected at build time and never
// duplicated into web/.env. Values are never logged.
const rootEnv = loadDotenv({ path: resolve(__dirname, '..', '.env.dev') }).parsed || {}

const pick = (key) => rootEnv[key] || process.env[key] || ''

export default defineConfig({
  plugins: [react()],
  server: { port: 5173 },
  define: {
    'import.meta.env.VITE_CLERK_PUBLISHABLE_KEY': JSON.stringify(
      pick('VITE_CLERK_PUBLISHABLE_KEY')
    ),
    'import.meta.env.VITE_CLERK_FRONTEND_URL': JSON.stringify(
      pick('VITE_CLERK_FRONTEND_URL')
    ),
    'import.meta.env.VITE_API_BASE': JSON.stringify(pick('VITE_API_BASE')),
  },
})
