// Signed-out state: the popup can't run interactive auth in the MV3 sandbox,
// so it sends the user to sign in on the WEB APP (on-tracker.com). The session
// then syncs back via Clerk's syncHost (which points at the FAPI, a different
// host — see main.jsx). Don't reuse VITE_CLERK_SYNC_HOST here; in production
// that's clerk.on-tracker.com, not where /sign-in lives.
const WEB_APP = import.meta.env.VITE_WEB_APP_URL || 'http://localhost:5173'

export default function SignInCTA() {
  return (
    <div className="signin-cta">
      <p>Sign in to start your OnTrack Brief.</p>
      <button
        className="signin-btn"
        onClick={() => chrome.tabs.create({ url: `${WEB_APP}/sign-in` })}
      >
        Sign in at on-tracker.com
      </button>
      <p className="signin-hint">
        After signing in, open OnTrack so we can link your account.
      </p>
    </div>
  )
}
