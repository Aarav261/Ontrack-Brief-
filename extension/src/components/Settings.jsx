import { useState } from 'react'
import { useUser } from '@clerk/chrome-extension'

export default function Settings({
  initialHour,
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

  const [hour, setHour] = useState(initialHour)
  const [briefWeeks, setBriefWeeks] = useState(initialBriefWeeks)
  const [stripWeeks, setStripWeeks] = useState(initialStripWeeks)
  const [loading, setLoading] = useState(false)
  const [msg, setMsg] = useState(null)

  async function handleSubscribe() {
    setLoading(true)
    setMsg(null)
    try {
      await onSubscribe({ hour, briefWeeks })
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
          A daily task summary, sent to your account email on weekday mornings.
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
          <select value={hour} onChange={(e) => setHour(e.target.value)}>
            <option value="6">6:00 AM</option>
            <option value="7">7:00 AM</option>
            <option value="8">8:00 AM</option>
            <option value="9">9:00 AM</option>
            <option value="10">10:00 AM</option>
          </select>
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
          <div className="unsubscribe">
            <a onClick={handleUnsubscribe}>Unsubscribe</a>
          </div>
        )}
      </div>
    </div>
  )
}
