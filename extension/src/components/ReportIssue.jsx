import { useState } from 'react'

const MAX_LEN = 2000

export default function ReportIssue({ onSubmit }) {
  const [text, setText] = useState('')
  const [loading, setLoading] = useState(false)
  const [msg, setMsg] = useState(null)

  async function handleSubmit() {
    const description = text.trim()
    if (!description) {
      setMsg({ type: 'error', text: 'Please describe the issue first.' })
      return
    }
    setLoading(true)
    setMsg(null)
    try {
      await onSubmit(description)
      setText('')
      setMsg({ type: 'success', text: 'Thanks! Your feedback has been sent.' })
    } catch (err) {
      const errText =
        err?.status === 429
          ? 'You’ve sent a few already — please try again later.'
          : 'Could not send right now. Please try again.'
      setMsg({ type: 'error', text: errText })
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="settings-panel">
      <div className="settings-card">
        <div className="settings-heading">Send feedback</div>
        <p className="settings-sub">
          Hit a bug or have an idea? Tell us what happened — it goes straight to
          the team, and we can reply to your account email.
        </p>

        <div className="field-group">
          <label>What&rsquo;s going on?</label>
          <textarea
            className="issue-textarea"
            value={text}
            maxLength={MAX_LEN}
            onChange={(e) => setText(e.target.value)}
            placeholder="Describe the problem or idea…"
            rows={6}
          />
          <div className="char-count">
            {text.length}/{MAX_LEN}
          </div>
        </div>

        <button
          className="subscribe-btn"
          onClick={handleSubmit}
          disabled={loading}
        >
          {loading ? 'Sending…' : 'Send feedback'}
        </button>

        {msg && <div className={`msg ${msg.type}`}>{msg.text}</div>}
      </div>
    </div>
  )
}
