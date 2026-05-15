import { useState } from 'react';

export default function Settings({
  initialEmail, initialHour, initialRecentlyDays, initialMaxTodo, initialStripWeeks,
  subscribedEmail, onSubscribe, onUnsubscribe, onStripWeeksChange,
}) {
  const [email,        setEmail]        = useState(initialEmail);
  const [hour,         setHour]         = useState(initialHour);
  const [recentlyDays, setRecentlyDays] = useState(initialRecentlyDays);
  const [maxTodo,      setMaxTodo]      = useState(initialMaxTodo);
  const [stripWeeks,   setStripWeeks]   = useState(initialStripWeeks);
  const [loading,      setLoading]      = useState(false);
  const [msg,          setMsg]          = useState(null);

  async function handleSubscribe() {
    if (!email || !email.includes('@')) {
      setMsg({ type: 'error', text: 'Enter a valid email address.' });
      return;
    }
    setLoading(true);
    setMsg(null);
    try {
      const r = await onSubscribe({ email, hour, recentlyDays, maxTodo });
      if (r.ok) {
        setMsg({ type: 'success', text: 'Done! Check your inbox in a moment.' });
      } else if (r.status === 400) {
        setMsg({ type: 'error', text: 'Session expired — log out and back in to OnTrack, then try again.' });
      } else {
        setMsg({ type: 'error', text: `Server error (${r.status}).` });
      }
    } catch (err) {
      setMsg({
        type: 'error',
        text: err.message === 'no-session'
          ? 'No OnTrack session found. Open OnTrack first.'
          : 'Could not reach the OnTrack Brief server.',
      });
    } finally {
      setLoading(false);
    }
  }

  async function handleUnsubscribe() {
    if (!subscribedEmail) return;
    try {
      await onUnsubscribe(subscribedEmail);
      setMsg({ type: 'success', text: "You've been unsubscribed." });
    } catch {
      setMsg({ type: 'error', text: 'Could not reach server.' });
    }
  }

  function handleStripWeeksChange(val) {
    setStripWeeks(val);
    onStripWeeksChange(parseInt(val, 10));
  }

  return (
    <div className="settings-panel">
      <div className="settings-card">
        <div className="settings-heading">Email Briefs</div>
        <p className="settings-sub">
          Optional — get a daily task summary by email on weekday mornings.
        </p>

        <div className="field-group">
          <label>Your email</label>
          <input
            type="email"
            placeholder="you@example.com"
            value={email}
            onChange={(e) => setEmail(e.target.value)}
          />
        </div>

        <div className="field-group">
          <label>Recently completed (days back)</label>
          <select value={recentlyDays} onChange={(e) => setRecentlyDays(e.target.value)}>
            <option value="3">3 days</option>
            <option value="5">5 days</option>
            <option value="7">7 days</option>
            <option value="14">14 days</option>
            <option value="30">30 days</option>
          </select>
        </div>

        <div className="field-group">
          <label>Max tasks in email</label>
          <select value={maxTodo} onChange={(e) => setMaxTodo(e.target.value)}>
            <option value="5">5 tasks</option>
            <option value="10">10 tasks</option>
            <option value="15">15 tasks</option>
            <option value="20">20 tasks</option>
            <option value="50">All tasks</option>
          </select>
        </div>

        <div className="field-group">
          <label>Strip view</label>
          <select value={stripWeeks} onChange={(e) => handleStripWeeksChange(e.target.value)}>
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
          disabled={loading || !email}
        >
          {loading ? 'Enabling…' : 'Enable email briefs'}
        </button>

        {msg && <div className={`msg ${msg.type}`}>{msg.text}</div>}

        {subscribedEmail && (
          <div className="unsubscribe">
            <a onClick={handleUnsubscribe}>Unsubscribe</a>
          </div>
        )}
      </div>
    </div>
  );
}
