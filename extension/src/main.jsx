import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import { ClerkProvider } from '@clerk/chrome-extension'
import './styles/popup.css'
import App from './App'

const publishableKey = import.meta.env.VITE_CLERK_PUBLISHABLE_KEY

// Where the user actually signs in. The popup can't run interactive auth in the
// MV3 sandbox, so it reads the session synced from the web app (Phase 0 spike).
// Dev: the Vite web app on 5173; prod: the deployed landing page.
const SYNC_HOST =
  import.meta.env.VITE_CLERK_SYNC_HOST || 'http://localhost:5173'

if (!publishableKey) {
  throw new Error('Missing VITE_CLERK_PUBLISHABLE_KEY — set it in repo-root .env.dev')
}

createRoot(document.getElementById('root')).render(
  <StrictMode>
    <ClerkProvider publishableKey={publishableKey} syncHost={SYNC_HOST}>
      <App />
    </ClerkProvider>
  </StrictMode>
)
