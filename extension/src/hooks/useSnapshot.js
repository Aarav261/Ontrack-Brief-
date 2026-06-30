import { useCallback, useEffect, useRef, useState } from 'react'
import { api } from '../lib/api'
import { getLocal, setLocal, removeLocal } from '../lib/storage'
import { syncLabel } from '../utils/time'
import { SNAPSHOT_KEY, SNAPSHOT_TTL_MS, DEFAULT_BASE_URL } from '../constants'

// Storage keys the popup reads on init (creds + saved brief/strip preferences).
const STORAGE_KEYS = [
  'auth_token',
  'username',
  'refresh_token',
  'base_url',
  'strip_weeks',
  'recently_completed_days',
  'max_todo_tasks',
  'brief_hour',
  'brief_minute',
  'brief_dow',
  'brief_weeks',
]

// Owns everything data-related in the popup: the cached OnTrack snapshot
// (stale-while-revalidate), the Clerk↔OnTrack link on open, and the brief
// settings writes. App.jsx consumes this and stays a pure view.
export function useSnapshot({ isLoaded, isSignedIn, getToken }) {
  const [storageData, setStorageData] = useState(null)
  const [status, setStatus] = useState({ type: 'warning', text: 'Waiting for OnTrack…' })
  const [days, setDays] = useState(null)
  const [feedback, setFeedback] = useState([])
  const [subscribed, setSubscribed] = useState(true)
  const [stripLoading, setStripLoading] = useState(false)
  const [footerSync, setFooterSync] = useState('')
  const snapshotAuthRef = useRef(null)
  const didInitRef = useRef(false)

  // View machine. Identity is the Clerk session (synced from the web app);
  // OnTrack creds (auth_token/username) still come from the content script.
  const view =
    !isLoaded || !storageData
      ? 'loading'
      : !isSignedIn
        ? 'signed-out'
        : !storageData.auth_token || !storageData.username
          ? 'no-ontrack'
          : 'snapshot'

  const loadSnapshot = useCallback(
    async (username, baseUrl, force = false, numDays = 7) => {
      snapshotAuthRef.current = { username, baseUrl, days: numDays }

      const cached = (await getLocal([SNAPSHOT_KEY]))[SNAPSHOT_KEY]
      const hasCache = !!cached?.data
      const fresh = hasCache && Date.now() - cached.ts < SNAPSHOT_TTL_MS
      // The cache isn't keyed by window size, so a fresh 7-day snapshot must not
      // satisfy a 14-day request — otherwise switching to the 2-week strip paints
      // the stale 7-day data and silently drops days 8–14 (and their tasks).
      const coversWindow = hasCache && (cached.data.days?.length || 0) >= numDays

      if (hasCache) {
        // Stale-while-revalidate: paint cached data instantly (any age), no
        // blocking spinner. Skip the network entirely while still fresh AND the
        // cached window is at least as wide as the one we need.
        setDays(cached.data.days)
        setFeedback(cached.data.feedback || [])
        if (typeof cached.data.subscribed === 'boolean') setSubscribed(cached.data.subscribed)
        setStripLoading(false)
        setFooterSync(syncLabel(cached.ts))
        if (!force && fresh && coversWindow) return
        setFooterSync('Refreshing…') // background revalidate cue
      } else {
        // First load on this device — nothing to show yet.
        setStripLoading(true)
        setDays(null)
        setFeedback([])
      }

      try {
        // Server resolves the user from the verified Clerk JWT; the body only
        // carries snapshot params.
        const data = await api('/api/snapshot', {
          method: 'POST',
          getToken,
          body: { base_url: baseUrl || DEFAULT_BASE_URL, days: numDays },
        })
        const ts = Date.now()
        if (data.is_stale) {
          setStatus({ type: 'warning', text: 'Open OnTrack to refresh your tasks' })
        } else {
          setStatus({ type: 'ok', text: `Logged in as ${username}` })
          await setLocal({ [SNAPSHOT_KEY]: { ts, data } })
        }
        setDays(data.days)
        setFeedback(data.feedback || [])
        if (typeof data.subscribed === 'boolean') setSubscribed(data.subscribed)
        setFooterSync(data.is_stale ? 'Stale Data' : syncLabel(ts))
      } catch (err) {
        // A failed *background* revalidate keeps the cached data on screen; only
        // surface actionable states, and stay quiet on generic errors when we
        // already have something to show.
        if (err?.data?.hint === 'open_ontrack') {
          setStatus({ type: 'warning', text: 'Open OnTrack to refresh your tasks' })
        } else if (err?.data?.error === 'not_linked') {
          setStatus({ type: 'warning', text: 'Open OnTrack so we can link your account' })
        } else if (!hasCache) {
          setStatus({ type: 'warning', text: 'Could not load tasks — is the server running?' })
        }
        setFooterSync(hasCache ? syncLabel(cached.ts) : '')
        if (!hasCache) setFeedback([])
      } finally {
        setStripLoading(false)
      }
    },
    [getToken]
  )

  // Bind the scraped OnTrack token to the Clerk identity, then load tasks.
  const linkAndLoad = useCallback(
    async (data) => {
      const weeks = parseInt(data.strip_weeks || '1', 10)
      try {
        await api('/link-ontrack', {
          method: 'POST',
          getToken,
          body: {
            base_url: data.base_url || DEFAULT_BASE_URL,
            username: data.username,
            auth_token: data.auth_token,
            // Durable token (stashed by background.js) so the row is created with it.
            refresh_token: data.refresh_token,
            // NB: deliberately omit brief send-time fields (hour/minute/dow). This
            // auto re-link runs on every popup open; sending them would let a stale
            // or default value clobber the user's saved schedule. Only an explicit
            // Settings save (saveSettings) sends them.
          },
        })
      } catch {
        // non-fatal: the snapshot below will surface a clear status.
      }
      await loadSnapshot(data.username, data.base_url, false, weeks * 7)
    },
    [getToken, loadSnapshot]
  )

  // Load storage once Clerk has resolved; drive the flow off the session.
  useEffect(() => {
    if (!isLoaded || didInitRef.current) return
    didInitRef.current = true
    getLocal(STORAGE_KEYS).then((data) => {
      setStorageData(data)
      if (!isSignedIn) {
        setStatus({ type: 'warning', text: 'Sign in to start your OnTrack Brief' })
      } else if (data.auth_token && data.username) {
        setStatus({ type: 'ok', text: `Logged in as ${data.username}` })
        linkAndLoad(data)
      } else {
        setStatus({ type: 'warning', text: 'Open OnTrack — your tasks will appear automatically' })
      }
    })
  }, [isLoaded, isSignedIn, linkAndLoad])

  const refresh = useCallback(async () => {
    const a = snapshotAuthRef.current
    if (!a) return
    await removeLocal(SNAPSHOT_KEY)
    await loadSnapshot(a.username, a.baseUrl, true, a.days)
  }, [loadSnapshot])

  const setStripWeeks = useCallback(
    async (weeks) => {
      await setLocal({ strip_weeks: String(weeks) })
      setStorageData((prev) => ({ ...prev, strip_weeks: String(weeks) }))
      const a = snapshotAuthRef.current
      if (a) {
        await removeLocal(SNAPSHOT_KEY)
        await loadSnapshot(a.username, a.baseUrl, true, weeks * 7)
      }
    },
    [loadSnapshot]
  )

  const setBriefWeeks = useCallback(async (weeks) => {
    await setLocal({ brief_weeks: String(weeks) })
    setStorageData((prev) => ({ ...prev, brief_weeks: String(weeks) }))
  }, [])

  // Keep the cached snapshot's subscribed flag in sync with an in-session
  // change. Without this, reopening the popup paints the stale cached value (and
  // skips the revalidate while the cache is fresh), so a just-disconnected user
  // would still see the "Disconnect brief" button.
  const patchCachedSubscribed = useCallback(async (value) => {
    const cached = (await getLocal([SNAPSHOT_KEY]))[SNAPSHOT_KEY]
    if (cached?.data) {
      await setLocal({ [SNAPSHOT_KEY]: { ...cached, data: { ...cached.data, subscribed: value } } })
    }
  }, [])

  // Persist brief settings against the Clerk-linked account (email is sourced
  // from Clerk server-side, so it's no longer entered here). Throws 'no-session'
  // when OnTrack creds are missing, matching the Settings panel's error handling.
  const saveSettings = useCallback(
    async ({ hour, minute, dow, briefWeeks }) => {
      const stored = await getLocal(['auth_token', 'username', 'base_url', 'refresh_token'])
      if (!stored.auth_token || !stored.username) throw new Error('no-session')
      await api('/link-ontrack', {
        method: 'POST',
        getToken,
        body: {
          base_url: stored.base_url || DEFAULT_BASE_URL,
          username: stored.username,
          auth_token: stored.auth_token,
          refresh_token: stored.refresh_token,
          brief_hour: parseInt(hour, 10),
          brief_minute: parseInt(minute, 10),
          brief_dow: dow,
          brief_days: parseInt(briefWeeks, 10) * 7,
          // Deliberate "Enable email briefs" click — send one now even if the
          // user is already linked (the auto re-link on open omits this).
          send_brief_now: true,
        },
      })
      await setLocal({
        brief_hour: hour,
        brief_minute: minute,
        brief_dow: dow,
        brief_weeks: briefWeeks,
      })
      setStorageData((prev) => ({ ...prev, brief_hour: hour, brief_minute: minute, brief_dow: dow }))
      setSubscribed(true) // enabling/saving (re)activates the subscription
      await patchCachedSubscribed(true)
    },
    [getToken, patchCachedSubscribed]
  )

  const unsubscribe = useCallback(async () => {
    await api('/unsubscribe', { method: 'POST', getToken })
    setSubscribed(false)
    await patchCachedSubscribed(false)
    setStatus({ type: 'warning', text: 'Briefs paused — re-enable them any time.' })
  }, [getToken, patchCachedSubscribed])

  return {
    view,
    status,
    days,
    feedback,
    subscribed,
    stripLoading,
    footerSync,
    storageData,
    username: storageData?.username || '',
    actions: { refresh, setStripWeeks, setBriefWeeks, saveSettings, unsubscribe },
  }
}
