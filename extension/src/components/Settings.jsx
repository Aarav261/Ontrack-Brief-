import { useState } from 'react'
import { useUser } from '@clerk/chrome-extension'

// Canonical Mon→Sun order; `value` is the APScheduler day_of_week token.
const DAYS = [
  { value: 'mon', label: 'Mon' },
  { value: 'tue', label: 'Tue' },
  { value: 'wed', label: 'Wed' },
  { value: 'thu', label: 'Thu' },
  { value: 'fri', label: 'Fri' },
  { value: 'sat', label: 'Sat' },
  { value: 'sun', label: 'Sun' },
]
const DAY_ORDER = DAYS.map((d) => d.value)

// Expand a stored brief_dow string into a Set of day tokens. Accepts a CSV
// ("mon,wed,fri") or a hyphen range ("mon-fri") — the historical default.
function parseDow(dow) {
  const raw = (dow || 'mon-fri').trim().toLowerCase()
  if (raw.includes('-')) {
    const [start, end] = raw.split('-')
    const i = DAY_ORDER.indexOf(start)
    const j = DAY_ORDER.indexOf(end)
    if (i !== -1 && j !== -1 && i <= j) return new Set(DAY_ORDER.slice(i, j + 1))
  }
  return new Set(raw.split(',').filter((d) => DAY_ORDER.includes(d)))
}

// Serialize selected days back to a canonical CSV string for the backend.
function serializeDow(daySet) {
  return DAY_ORDER.filter((d) => daySet.has(d)).join(',')
}

// Two-digit zero-pad for the HH:MM time input.
const pad2 = (n) => String(n).padStart(2, '0')

export default function Settings({
  initialHour,
  initialMinute,
  initialDow,
  initialBriefWeeks,
  initialStripWeeks,
  subscribed = true,
  onSubscribe,
  onUnsubscribe,
  onStripWeeksChange,
  onBriefWeeksChange,
}) {
  const { user } = useUser()
  // Recipient is the verified Clerk account email — not user-editable.
  const accountEmail = user?.primaryEmailAddress?.emailAddress || ''

  // A single HH:MM string drives the native time picker; split on save.
  const [time, setTime] = useState(`${pad2(initialHour ?? 8)}:${pad2(initialMinute ?? 0)}`)
  const [days, setDays] = useState(() => parseDow(initialDow))
  const [briefWeeks, setBriefWeeks] = useState(initialBriefWeeks)
  const [stripWeeks, setStripWeeks] = useState(initialStripWeeks)
  const [loading, setLoading] = useState(false)
  const [msg, setMsg] = useState(null)

  function toggleDay(value) {
    setDays((prev) => {
      const next = new Set(prev)
      if (next.has(value)) next.delete(value)
      else next.add(value)
      return next
    })
  }

  async function handleSubscribe() {
    setMsg(null)
    if (days.size === 0) {
      setMsg({ type: 'error', text: 'Pick at least one day to send the brief.' })
      return
    }
    setLoading(true)
    try {
      const [h, m] = time.split(':')
      await onSubscribe({ hour: h, minute: m, dow: serializeDow(days), briefWeeks })
      setMsg({ type: 'success', text: 'Done! Check your inbox in a moment.' })
    } catch (err) {
      let text
      if (err.message === 'no-session') {
        text = 'No OnTrack session found. Open OnTrack first.'
      } else if (err.status === 401) {
        // Genuinely logged out — opening OnTrack lets us recapture the session.
        text = 'Open OnTrack to refresh your session, then try again.'
      } else if (err.status === 503) {
        text = 'OnTrack is busy right now — please try again in a moment.'
      } else if (err.status) {
        text = `Server error (${err.status}).`
      } else {
        text = 'Could not reach the OnTrack Brief server.'
      }
      setMsg({ type: 'error', text })
    } finally {
      setLoading(false)
    }
  }

  async function handleUnsubscribe() {
    try {
      await onUnsubscribe()
      setMsg({
        type: 'success',
        text: 'Briefs paused. Re-enable any time — your settings are kept.',
      })
    } catch {
      setMsg({ type: 'error', text: 'Could not reach server.' })
    }
  }

  function handleStripWeeksChange(val) {
    setStripWeeks(val)
    onStripWeeksChange(parseInt(val, 10))
  }

  function handleBriefWeeksChange(val) {
    setBriefWeeks(val)
    onBriefWeeksChange(parseInt(val, 10))
  }

  return (
    <div className="settings-panel">
      <div className="settings-card">
        <div className="settings-heading">Email Briefs</div>
        <p className="settings-sub">
          A task summary sent to your account email at the time and on the days you
          choose.
        </p>

        {!subscribed && (
          <div className="msg warning">
            Briefs are paused. Click “Re-enable email briefs” to resume — your
            settings and account are kept.
          </div>
        )}

        <div className="field-group">
          <label>Briefs are sent to</label>
          <div className="account-email">{accountEmail || 'your account email'}</div>
        </div>

        <div className="field-group">
          <label>Brief window</label>
          <select
            value={briefWeeks}
            onChange={(e) => handleBriefWeeksChange(e.target.value)}
          >
            <option value="1">1 week (7 days)</option>
            <option value="2">2 weeks (14 days)</option>
          </select>
        </div>

        <div className="field-group">
          <label>Strip view</label>
          <select
            value={stripWeeks}
            onChange={(e) => handleStripWeeksChange(e.target.value)}
          >
            <option value="1">1 week (7 days)</option>
            <option value="2">2 weeks (14 days)</option>
          </select>
        </div>

        <div className="field-group">
          <label>Send brief at</label>
          <input type="time" value={time} onChange={(e) => setTime(e.target.value)} />
        </div>

        <div className="field-group">
          <label>Send on</label>
          <div className="day-toggle">
            {DAYS.map((d) => (
              <label key={d.value} className="day-checkbox">
                <input
                  type="checkbox"
                  checked={days.has(d.value)}
                  onChange={() => toggleDay(d.value)}
                />
                {d.label}
              </label>
            ))}
          </div>
        </div>

        <button
          className="subscribe-btn"
          onClick={handleSubscribe}
          disabled={loading}
        >
          {loading
            ? 'Saving…'
            : subscribed
              ? 'Save & send a brief now'
              : 'Re-enable email briefs'}
        </button>

        {msg && <div className={`msg ${msg.type}`}>{msg.text}</div>}

        {subscribed && (
          <button className="disconnect-btn" onClick={handleUnsubscribe}>
            Disconnect brief
          </button>
        )}
      </div>
    </div>
  )
}
