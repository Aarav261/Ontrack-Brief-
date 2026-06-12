import { Link } from 'react-router-dom'
import { SignedIn, SignedOut, UserButton } from '@clerk/clerk-react'

const FEATURES = [
  {
    icon: '🎯',
    title: 'Prioritised for you',
    body: 'Tasks ranked by urgency and grade target — red-flag deadlines first, the HD-pushing work next.',
  },
  {
    icon: '📬',
    title: 'In your inbox by morning',
    body: 'A clean weekday brief lands before you wake up. No app to open, no laptop to leave on.',
  },
  {
    icon: '💬',
    title: 'Context included',
    body: 'Every task links straight to OnTrack, with the latest tutor feedback right inside the email.',
  },
]

export default function Landing() {
  return (
    <div className="page">
      <header className="topbar">
        <span className="brand">
          OnTrack<span className="brand-paren">(er)</span>
        </span>
        <nav className="topbar-right">
          <SignedOut>
            <Link className="btn btn-ghost" to="/sign-in">
              Sign in
            </Link>
          </SignedOut>
          <SignedIn>
            <UserButton afterSignOutUrl="/" />
          </SignedIn>
        </nav>
      </header>

      <main className="hero">
        <h1 className="hero-title">
          Your OnTrack week, sorted before you wake up.
        </h1>
        <p className="hero-sub">
          A weekday morning brief that ranks your OnTrack tasks by urgency and
          grade target — links and tutor feedback included — delivered straight
          to your inbox. Even with your laptop closed.
        </p>
        <div className="hero-cta">
          <a className="btn btn-primary" href="#install">
            Add to Chrome
          </a>
          <SignedOut>
            <Link className="btn btn-ghost" to="/sign-in">
              Sign in
            </Link>
          </SignedOut>
          <SignedIn>
            <span className="signed-note">
              You&rsquo;re signed in — open the OnTrack(er) extension to finish
              setup.
            </span>
          </SignedIn>
        </div>
      </main>

      <section className="features">
        {FEATURES.map((f) => (
          <div className="feature" key={f.title}>
            <div className="feature-icon">{f.icon}</div>
            <div className="feature-title">{f.title}</div>
            <p className="feature-body">{f.body}</p>
          </div>
        ))}
      </section>

      <footer className="site-footer">
        <span className="brand brand-sm">
          OnTrack<span className="brand-paren">(er)</span>
        </span>
        <span>Made for Deakin students.</span>
      </footer>
    </div>
  )
}
