// Signed-out state: the popup can't run interactive auth in the MV3 sandbox,
// so it sends the user to sign in on the web app. The session then syncs back
// into the popup via Clerk's syncHost.
const WEB_APP =
  import.meta.env.VITE_CLERK_SYNC_HOST || 'http://localhost:5173'

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
