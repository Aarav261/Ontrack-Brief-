import { useState } from 'react'
import { Link } from 'react-router-dom'
import { SignedIn, SignedOut, UserButton, useAuth } from '@clerk/clerk-react'

// Backend base — VITE_API_BASE in prod (Railway), localhost for dev.
const API_BASE = import.meta.env.VITE_API_BASE || 'http://localhost:8000'

export default function Landing() {
  const { getToken } = useAuth()
  const [result, setResult] = useState('')

  // Phase 0 spike: prove a Clerk session JWT verifies on the Flask backend.
  async function testBackend() {
    setResult('Calling…')
    try {
      const token = await getToken()
      const res = await fetch(`${API_BASE}/api/whoami`, {
        headers: { Authorization: `Bearer ${token}` },
      })
      const body = await res.text()
      setResult(`${res.status} — ${body}`)
    } catch (err) {
      setResult(`Error: ${err.message}`)
    }
  }

  return (
    <main className="wrap">
      <header className="topbar">
        <span className="brand">OnTrack&nbsp;Brief</span>
        <SignedIn>
          <UserButton afterSignOutUrl="/" />
        </SignedIn>
      </header>

      <section className="hero">
        <h1>Your OnTrack tasks, prioritised, in your inbox every morning.</h1>
        <p>
          A weekday email brief that ranks your tasks by urgency and grade
          target — even while your laptop is closed.
        </p>
        <a className="btn btn-primary" href="#install">
          Add to Chrome
        </a>
      </section>

      <section className="auth">
        <SignedOut>
          <p>Sign in to link your OnTrack account and start your daily brief.</p>
          <Link className="btn" to="/sign-in">
            Sign in
          </Link>
        </SignedOut>
        <SignedIn>
          <p>
            You&rsquo;re signed in. Open the OnTrack Brief extension to finish
            linking your OnTrack account.
          </p>
          <button className="btn" onClick={testBackend}>
            Test backend (Phase 0 spike)
          </button>
          {result && <pre className="result">{result}</pre>}
        </SignedIn>
      </section>
    </main>
  )
}
