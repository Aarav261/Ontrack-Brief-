import { useState } from 'react';

export default function SignupFlow({ onSignup, onSkip }) {
  const [email, setEmail]   = useState('');
  const [loading, setLoading] = useState(false);
  const [msg, setMsg]       = useState(null); // { type, text }

  async function handleSignup() {
    if (!email || !email.includes('@')) {
      setMsg({ type: 'error', text: 'Enter a valid email address.' });
      return;
    }
    setLoading(true);
    setMsg(null);
    try {
      const res = await onSignup(email);
      if (!res.ok) {
        setMsg({ type: 'error', text: res.error || 'Signup failed.' });
      }
    } catch {
      setMsg({ type: 'error', text: 'Could not reach server.' });
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="info-card">
      <div className="info-icon">✉️</div>
      <div className="info-title">Step 2: Enter your email</div>
      <div className="info-sub" style={{ marginBottom: 20 }}>
        Get your daily task summary by email.<br />No more missing deadlines!
      </div>

      <div className="field-group" style={{ textAlign: 'left' }}>
        <input
          type="email"
          placeholder="you@example.com"
          value={email}
          onChange={(e) => setEmail(e.target.value)}
          onKeyDown={(e) => e.key === 'Enter' && handleSignup()}
        />
      </div>

      <button
        className="subscribe-btn"
        onClick={handleSignup}
        disabled={loading}
        style={{ padding: '14px', fontSize: 14 }}
      >
        {loading ? 'Setting up…' : 'Subscribe to Email Briefs'}
      </button>

      {msg && <div className={`msg ${msg.type}`}>{msg.text}</div>}

      <div style={{ marginTop: 20 }}>
        <span
          onClick={onSkip}
          style={{ fontSize: 12, color: '#9ca3af', cursor: 'pointer' }}
        >
          Not now, just show my tasks →
        </span>
      </div>
    </div>
  );
}
