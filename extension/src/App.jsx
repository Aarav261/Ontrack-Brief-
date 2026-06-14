import { useState, useEffect, useRef, useCallback } from 'react'
import { useAuth } from '@clerk/chrome-extension'
import Header from './components/Header'
import StatusPill from './components/StatusPill'
import NoAuth from './components/NoAuth'
import SignInCTA from './components/SignInCTA'
import SnapshotView from './components/SnapshotView'
import Settings from './components/Settings'
import ReportIssue from './components/ReportIssue'
import Footer from './components/Footer'
import { api } from './lib/api'
import { syncLabel } from './utils/time'
import { SNAPSHOT_KEY, SNAPSHOT_TTL_MS, DEFAULT_BASE_URL } from './constants'

export default function App() {
  const { isLoaded, isSignedIn, getToken } = useAuth()
  const [storageData, setStorageData] = useState(null)
  const [activeTab, setActiveTab] = useState('main')
  const [statusType, setStatusType] = useState('warning')
  const [statusText, setStatusText] = useState('Waiting for OnTrack…')
  const [days, setDays] = useState(null)
  const [feedback, setFeedback] = useState([])
  const [subscribed, setSubscribed] = useState(true)
  const [stripLoading, setStripLoading] = useState(false)
  const [footerSync, setFooterSync] = useState('')
  const snapshotAuthRef = useRef(null)
  const didInitRef = useRef(false)

  const setStatus = useCallback((type, text) => {
    setStatusType(type)
    setStatusText(text)
  }, [])

  // View machine. Identity is now the Clerk session (synced from the web app);
  // OnTrack creds (auth_token/username) still come from the content script.
  const view = !isLoaded || !storageData
    ? 'loading'
    : !isSignedIn
      ? 'signed-out'
      : !storageData.auth_token || !storageData.username
        ? 'no-ontrack'
        : 'snapshot'

  const loadSnapshot = useCallback(
    (username, baseUrl, force = false, numDays = 7) => {
      snapshotAuthRef.current = { username, baseUrl, days: numDays }

      chrome.storage.local.get([SNAPSHOT_KEY], (stored) => {
        const cached = stored[SNAPSHOT_KEY]
        const hasCache = !!cached?.data
        const fresh = hasCache && Date.now() - cached.ts < SNAPSHOT_TTL_MS

        if (hasCache) {
          // Stale-while-revalidate: paint cached data instantly (any age), no
          // blocking spinner. Skip the network entirely while still fresh.
          setDays(cached.data.days)
          setFeedback(cached.data.feedback || [])
          if (typeof cached.data.subscribed === 'boolean')
            setSubscribed(cached.data.subscribed)
          setStripLoading(false)
          setFooterSync(syncLabel(cached.ts))
          if (!force && fresh) return
          setFooterSync('Refreshing…') // background revalidate cue
        } else {
          // First load on this device — nothing to show yet.
          setStripLoading(true)
          setDays(null)
          setFeedback([])
        }

        // Server resolves the user from the verified Clerk JWT; the body no
        // longer carries identity (just snapshot params).
        api('/api/snapshot', {
          method: 'POST',
          getToken,
          body: { base_url: baseUrl || DEFAULT_BASE_URL, days: numDays },
        })
          .then((data) => {
            const ts = Date.now()
            if (data.is_stale) {
              setStatus('warning', 'Open OnTrack to refresh your tasks')
            } else {
              setStatus('ok', `Logged in as ${username}`)
              chrome.storage.local.set({ [SNAPSHOT_KEY]: { ts, data } })
            }
            setDays(data.days)
            setFeedback(data.feedback || [])
            if (typeof data.subscribed === 'boolean') setSubscribed(data.subscribed)
            setFooterSync(data.is_stale ? 'Stale Data' : syncLabel(ts))
          })
          .catch((err) => {
            // A failed *background* revalidate keeps the cached data on screen;
            // only surface actionable states, and stay quiet on generic errors
            // when we already have something to show.
            if (err?.data?.hint === 'open_ontrack') {
              setStatus('warning', 'Open OnTrack to refresh your tasks')
            } else if (err?.data?.error === 'not_linked') {
              setStatus('warning', 'Open OnTrack so we can link your account')
            } else if (!hasCache) {
              setStatus('warning', 'Could not load tasks — is the server running?')
            }
            setFooterSync(hasCache ? syncLabel(cached.ts) : '')
            if (!hasCache) setFeedback([])
          })
          .finally(() => setStripLoading(false))
      })
    },
    [setStatus, getToken]
  )

  // Bind the scraped OnTrack token to the Clerk identity, then load tasks.
  const linkAndLoad = useCallback(
    (data) => {
      const weeks = parseInt(data.strip_weeks || '1', 10)
      api('/link-ontrack', {
        method: 'POST',
        getToken,
        body: {
          base_url: data.base_url || DEFAULT_BASE_URL,
          username: data.username,
          auth_token: data.auth_token,
          // Durable token (stashed by background.js) so the row is created with it.
          refresh_token: data.refresh_token,
          brief_hour: parseInt(data.brief_hour || '8', 10),
        },
      })
        .catch(() => {}) // non-fatal: snapshot will surface a clear status
        .finally(() =>
          loadSnapshot(data.username, data.base_url, false, weeks * 7)
        )
    },
    [getToken, loadSnapshot]
  )

  // Load storage once Clerk has resolved; drive the flow off the session.
  useEffect(() => {
    if (!isLoaded || didInitRef.current) return
    chrome.storage.local.get(
      [
        'auth_token',
        'username',
        'refresh_token',
        'base_url',
        'strip_weeks',
        'recently_completed_days',
        'max_todo_tasks',
        'brief_hour',
        'brief_weeks',
      ],
      (data) => {
        didInitRef.current = true
        setStorageData(data)
        if (!isSignedIn) {
          setStatus('warning', 'Sign in to start your OnTrack Brief')
        } else if (data.auth_token && data.username) {
          setStatus('ok', `Logged in as ${data.username}`)
          linkAndLoad(data)
        } else {
          setStatus('warning', 'Open OnTrack — your tasks will appear automatically')
        }
      }
    )
  }, [isLoaded, isSignedIn, setStatus, linkAndLoad])

  const handleRefresh = () => {
    const a = snapshotAuthRef.current
    if (!a) return
    chrome.storage.local.remove(SNAPSHOT_KEY, () => {
      loadSnapshot(a.username, a.baseUrl, true, a.days)
    })
  }

  const handleStripWeeksChange = (weeks) => {
    chrome.storage.local.set({ strip_weeks: String(weeks) })
    setStorageData((prev) => ({ ...prev, strip_weeks: String(weeks) }))
    const a = snapshotAuthRef.current
    if (a) {
      chrome.storage.local.remove(SNAPSHOT_KEY, () => {
        loadSnapshot(a.username, a.baseUrl, true, weeks * 7)
      })
    }
  }

  const handleBriefWeeksChange = (weeks) => {
    chrome.storage.local.set({ brief_weeks: String(weeks) })
    setStorageData((prev) => ({ ...prev, brief_weeks: String(weeks) }))
  }

  // Persist brief settings against the Clerk-linked account (email is sourced
  // from Clerk server-side, so it's no longer entered here).
  const handleSaveSettings = ({ hour, briefWeeks }) =>
    new Promise((resolve, reject) => {
      chrome.storage.local.get(
        ['auth_token', 'username', 'base_url', 'refresh_token'],
        (stored) => {
        if (!stored.auth_token || !stored.username) {
          reject(new Error('no-session'))
          return
        }
        api('/link-ontrack', {
          method: 'POST',
          getToken,
          body: {
            base_url: stored.base_url || DEFAULT_BASE_URL,
            username: stored.username,
            auth_token: stored.auth_token,
            refresh_token: stored.refresh_token,
            brief_hour: parseInt(hour, 10),
            brief_days: parseInt(briefWeeks, 10) * 7,
            // Deliberate "Enable email briefs" click — send one now even if the
            // user is already linked (the auto re-link on open omits this).
            send_brief_now: true,
          },
        })
          .then(() => {
            chrome.storage.local.set({ brief_hour: hour, brief_weeks: briefWeeks })
            setStorageData((prev) => ({ ...prev, brief_hour: hour }))
            setSubscribed(true) // enabling/saving (re)activates the subscription
            resolve()
          })
          .catch(reject)
      })
    })

  const handleUnsubscribe = () =>
    api('/unsubscribe', { method: 'POST', getToken }).then(() => {
      setSubscribed(false)
      setStatus('warning', 'Briefs paused — re-enable them any time.')
    })

  const handleReportIssue = (description) =>
    api('/api/issues', {
      method: 'POST',
      getToken,
      body: { description, version: chrome.runtime.getManifest().version },
    })

  const username = storageData?.username || ''

  return (
    <>
      <Header
        onSettings={() =>
          setActiveTab((t) => (t === 'settings' ? 'main' : 'settings'))
        }
        onReport={() =>
          setActiveTab((t) => (t === 'report' ? 'main' : 'report'))
        }
        onRefresh={handleRefresh}
        settingsActive={activeTab === 'settings'}
        reportActive={activeTab === 'report'}
      />

      {statusType !== 'ok' && <StatusPill type={statusType} text={statusText} />}

      {/* Settings & feedback panels require a signed-in session; otherwise fall
          back to the main view (which surfaces the sign-in CTA). */}
      {activeTab === 'settings' && storageData && isSignedIn ? (
        <Settings
          initialHour={storageData.brief_hour || '8'}
          initialBriefWeeks={storageData.brief_weeks || '1'}
          initialStripWeeks={storageData.strip_weeks || '1'}
          subscribed={subscribed}
          onSubscribe={handleSaveSettings}
          onUnsubscribe={handleUnsubscribe}
          onStripWeeksChange={handleStripWeeksChange}
          onBriefWeeksChange={handleBriefWeeksChange}
        />
      ) : activeTab === 'report' && isSignedIn ? (
        <ReportIssue onSubmit={handleReportIssue} />
      ) : (
        <>
          {view === 'signed-out' && <SignInCTA />}
          {view === 'no-ontrack' && <NoAuth />}
          {view === 'snapshot' && (
            <SnapshotView days={days} loading={stripLoading} feedback={feedback} />
          )}
        </>
      )}

      <Footer footerUser={username} footerSync={footerSync} />
    </>
  )
}
