import { Link } from 'react-router-dom'
import { SignedIn, SignedOut, UserButton } from '@clerk/clerk-react'

const FEATURES = [
  {
    n: '01',
    title: 'Prioritised for you',
    body: 'Tasks ranked by urgency and grade target — red-flag deadlines first, the HD-pushing work next.',
  },
  {
    n: '02',
    title: 'In your inbox by morning',
    body: 'A clean weekday brief lands before you wake up. No app to open, no laptop to leave on.',
  },
  {
    n: '03',
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
            <Link className="navlink" to="/sign-in">
              Sign in
            </Link>
          </SignedOut>
          <SignedIn>
            <UserButton afterSignOutUrl="/" />
          </SignedIn>
        </nav>
      </header>

      <main className="hero">
        <p className="eyebrow">The weekday morning brief</p>
        <h1 className="hero-title">
          Your OnTrack week, <em>sorted</em> before you wake up.
        </h1>
        <p className="hero-sub">
          A weekday morning brief that ranks your OnTrack tasks by urgency and
          grade target — links and tutor feedback included — delivered straight
          to your inbox. Even with your laptop closed.
        </p>
        <div className="hero-cta">
          <a
            className="btn btn-primary"
            href="https://github.com/Aarav261/Ontracker/releases/latest"
            target="_blank"
            rel="noopener noreferrer"
          >
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
          <div className="feature" key={f.n}>
            <span className="feature-num">{f.n}</span>
            <h3 className="feature-title">{f.title}</h3>
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
