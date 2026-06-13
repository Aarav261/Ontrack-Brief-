import { Link } from 'react-router-dom'
import { SignedIn, SignedOut, UserButton } from '@clerk/clerk-react'

const RELEASES_URL = 'https://github.com/Aarav261/Ontracker/releases/latest'

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

const INSTALL_STEPS = [
  {
    n: '1',
    body: (
      <>
        <a href={RELEASES_URL} target="_blank" rel="noopener noreferrer">
          Download
        </a>{' '}
        the latest extension <code>.zip</code> from the releases page.
      </>
    ),
  },
  {
    n: '2',
    body: (
      <>
        <strong>Unzip</strong> it — you&rsquo;ll get a folder named{' '}
        <code>ontrack-brief-extension</code>.
      </>
    ),
  },
  {
    n: '3',
    body: (
      <>
        Open <code>chrome://extensions</code> in Chrome.
      </>
    ),
  },
  {
    n: '4',
    body: (
      <>
        Turn on <strong>Developer mode</strong> — the toggle in the top-right.
      </>
    ),
  },
  {
    n: '5',
    body: (
      <>
        Click <strong>Load unpacked</strong> and select the unzipped folder.
      </>
    ),
  },
  {
    n: '6',
    body: (
      <>
        Click the OnTrack(er) icon in your toolbar and <strong>sign in</strong> —
        your brief is on its way.
      </>
    ),
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
            href={RELEASES_URL}
            target="_blank"
            rel="noopener noreferrer"
          >
            Add to Chrome
          </a>
          <a className="btn btn-ghost" href="#install">
            How to install
          </a>
          <SignedOut>
            <Link className="navlink signed-note" to="/sign-in">
              or sign in
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

      <section className="install" id="install">
        <p className="eyebrow">Install in under a minute</p>
        <h2 className="install-title">
          Add OnTrack(er) <em>to Chrome</em>.
        </h2>
        <p className="install-sub">
          It&rsquo;s a quick load-unpacked install — no Web Store needed. One time,
          then it runs quietly in the background.
        </p>

        <ol className="steps">
          {INSTALL_STEPS.map((s) => (
            <li className="step" key={s.n}>
              <span className="step-num">{s.n}</span>
              <span className="step-body">{s.body}</span>
            </li>
          ))}
        </ol>

        <div className="install-cta">
          <a
            className="btn btn-primary"
            href={RELEASES_URL}
            target="_blank"
            rel="noopener noreferrer"
          >
            Download the extension
          </a>
          <span className="install-note">
            Updating later? Download the new zip, then hit reload&nbsp;&#8635; on the
            OnTrack(er) card in <code>chrome://extensions</code>.
          </span>
        </div>
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
