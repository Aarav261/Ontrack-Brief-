import { Link } from 'react-router-dom'

// Last substantive update to this policy. Bump when the data practices change.
const LAST_UPDATED = '26 June 2026'
const CONTACT_EMAIL = 'support@on-tracker.com'

export default function Privacy() {
  return (
    <div className="page">
      <header className="topbar">
        <Link className="brand brand-sm" to="/" style={{ textDecoration: 'none' }}>
          OnTrack<span className="brand-paren">(er)</span>
        </Link>
        <nav className="topbar-right">
          <Link className="navlink" to="/">
            Home
          </Link>
        </nav>
      </header>

      <main className="legal">
        <p className="eyebrow">Privacy Policy</p>
        <h1 className="legal-title">How OnTrack(er) handles your data</h1>
        <p className="legal-meta">Last updated: {LAST_UPDATED}</p>

        <p className="legal-lead">
          OnTrack(er) sends Deakin students a weekday morning email brief of their{' '}
          <a href="https://ontrack.deakin.edu.au" target="_blank" rel="noopener noreferrer">
            OnTrack
          </a>{' '}
          tasks, and provides a Chrome extension that keeps your OnTrack session
          alive so those briefs can be generated. This policy explains exactly what
          data we collect, why, who it is shared with, and how it is protected. We
          collect the minimum needed to deliver your brief — nothing more.
        </p>

        <h2 className="legal-h2">1. Who we are</h2>
        <p>
          OnTrack(er) (&ldquo;we&rdquo;, &ldquo;us&rdquo;) is an independent service
          built for Deakin University students. It is not operated by, affiliated
          with, or endorsed by Deakin University or the OnTrack/Doubtfire project.
        </p>

        <h2 className="legal-h2">2. What we collect</h2>

        <h3 className="legal-h3">Account identity</h3>
        <p>
          When you sign in, our identity provider (Clerk) gives us your{' '}
          <strong>email address</strong> and a unique user ID. We use your email to
          send your brief and to identify your account.
        </p>

        <h3 className="legal-h3">OnTrack credentials</h3>
        <p>
          The extension captures your OnTrack session credentials &mdash; a rotating{' '}
          <code>auth_token</code>, a durable <code>refresh_token</code> cookie, and
          your OnTrack username &mdash; directly from your own OnTrack session in the
          browser. You never copy or paste a token. These let our server generate
          your brief on your behalf without you needing to stay logged in. They are{' '}
          <strong>encrypted at rest</strong> (see &sect;5).
        </p>

        <h3 className="legal-h3">OnTrack course data</h3>
        <p>
          As you browse OnTrack, the extension reads the task data OnTrack returns to
          your browser and sends it to our server so your brief reflects your real
          tasks. This includes: your unit codes and names, task names, deadlines,
          target grades, task statuses, and the text of tutor feedback on your tasks.
          We do <strong>not</strong> collect submission files, marks history beyond
          target grade, or any data unrelated to task prioritisation.
        </p>

        <h3 className="legal-h3">Your preferences</h3>
        <p>
          Settings you choose &mdash; what time your brief arrives, how many tasks it
          lists, the brief window, and whether you are subscribed.
        </p>

        <h3 className="legal-h3">Issue reports</h3>
        <p>
          If you use the &ldquo;Report an issue&rdquo; feature, we receive the
          description you write, your email, and your extension version, by email. We
          do not store these in our database.
        </p>

        <p className="legal-note">
          We do not collect browsing history outside OnTrack, we do not use
          advertising or tracking cookies, and we never sell your data.
        </p>

        <h2 className="legal-h2">3. How we use it</h2>
        <ul className="legal-list">
          <li>To generate and email your weekday brief.</li>
          <li>To show your live task strip in the extension popup.</li>
          <li>To keep your OnTrack session alive so briefs don&rsquo;t break overnight.</li>
          <li>To respond to issues you report.</li>
        </ul>
        <p>
          We do not use your data for profiling, advertising, or any purpose beyond
          delivering the service described above.
        </p>

        <h2 className="legal-h2">4. Who we share it with</h2>
        <p>
          We share data only with the service providers needed to run OnTrack(er).
          Each receives only what it needs:
        </p>
        <ul className="legal-list">
          <li>
            <strong>Clerk</strong> &mdash; sign-in and identity.
          </li>
          <li>
            <strong>Resend</strong> &mdash; delivers your brief email.
          </li>
          <li>
            <strong>Railway</strong> &mdash; hosts our server and database.
          </li>
          <li>
            <strong>Sentry</strong> &mdash; error monitoring; configured to{' '}
            <strong>exclude personal data</strong> (no emails, usernames, or IP
            addresses are sent).
          </li>
          <li>
            <strong>Deakin OnTrack</strong> &mdash; the source of your task data; we
            authenticate to it on your behalf using your captured credentials.
          </li>
        </ul>
        <p>
          We never sell your data or share it with advertisers. We may disclose data
          if required by law.
        </p>

        <h2 className="legal-h2">5. How we protect it</h2>
        <ul className="legal-list">
          <li>
            <strong>Encryption at rest.</strong> Your OnTrack credentials are
            encrypted in our database. The encryption key lives only in our server
            environment, never in the database, so a database dump alone cannot
            reveal them.
          </li>
          <li>
            <strong>Encryption in transit.</strong> All traffic between the
            extension and our server uses HTTPS/TLS.
          </li>
          <li>
            <strong>Verified identity.</strong> Sensitive actions are tied to your
            verified sign-in session, so no one can access or change your account by
            guessing your email.
          </li>
          <li>
            <strong>Rate limiting</strong> protects every endpoint against abuse.
          </li>
          <li>
            <strong>Data minimisation.</strong> Briefs are generated from stored task
            data, and monitoring is configured to exclude personal data.
          </li>
        </ul>

        <h2 className="legal-h2">6. How long we keep it</h2>
        <p>
          We keep your data while your account is active. Units that have ended are
          automatically pruned from our store. If you unsubscribe, we pause your
          briefs but retain your settings so you can resume with one click. You can
          ask us to delete your account and all associated data at any time (see
          &sect;8).
        </p>

        <h2 className="legal-h2">7. Browser extension permissions</h2>
        <p>The Chrome extension requests only what it needs to function:</p>
        <ul className="legal-list">
          <li>
            <code>storage</code> &mdash; to cache your session and brief data locally.
          </li>
          <li>
            <code>cookies</code> &mdash; to read your OnTrack <code>refresh_token</code>{' '}
            cookie so your session survives overnight.
          </li>
          <li>
            Access to <code>ontrack.deakin.edu.au</code> and <code>on-tracker.com</code>{' '}
            &mdash; the only sites the extension reads from or talks to.
          </li>
        </ul>

        <h2 className="legal-h2">8. Your rights</h2>
        <p>
          You can access, correct, export, or delete your data. To unsubscribe, use
          the link in any brief email or the extension popup. To delete your account
          and all associated data, contact us at{' '}
          <a href={`mailto:${CONTACT_EMAIL}`}>{CONTACT_EMAIL}</a>.
        </p>

        <h2 className="legal-h2">9. Children&rsquo;s privacy</h2>
        <p>
          OnTrack(er) is intended for university students and is not directed at
          children under 16.
        </p>

        <h2 className="legal-h2">10. Changes to this policy</h2>
        <p>
          If we change how we handle your data, we will update this page and the
          &ldquo;last updated&rdquo; date above.
        </p>

        <h2 className="legal-h2">11. Contact</h2>
        <p>
          Questions about your privacy? Email us at{' '}
          <a href={`mailto:${CONTACT_EMAIL}`}>{CONTACT_EMAIL}</a>.
        </p>
      </main>

      <footer className="site-footer">
        <Link className="brand brand-sm" to="/" style={{ textDecoration: 'none' }}>
          OnTrack<span className="brand-paren">(er)</span>
        </Link>
        <span>Made for Deakin students.</span>
      </footer>
    </div>
  )
}
