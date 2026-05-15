import { useState, useEffect, useRef, useCallback } from 'react';
import Header from './components/Header';
import StatusPill from './components/StatusPill';
import NoAuth from './components/NoAuth';
import SignupFlow from './components/SignupFlow';
import SnapshotView from './components/SnapshotView';
import Settings from './components/Settings';
import Footer from './components/Footer';

const SNAPSHOT_KEY    = 'snapshot_cache';
const SNAPSHOT_TTL_MS = 30 * 60 * 1000;

function syncLabel(ts) {
  const sec = Math.floor((Date.now() - ts) / 1000);
  if (sec < 60)  return `Synced ${sec}s ago`;
  const min = Math.floor(sec / 60);
  if (min < 60)  return `Synced ${min}m ago`;
  return `Synced ${Math.floor(min / 60)}h ago`;
}

export default function App() {
  const [storageData, setStorageData]   = useState(null);
  const [activeTab, setActiveTab]       = useState('main');
  const [statusType, setStatusType]     = useState('warning');
  const [statusText, setStatusText]     = useState('Waiting for OnTrack…');
  const [days, setDays]                 = useState(null);
  const [stripLoading, setStripLoading] = useState(false);
  const [footerSync, setFooterSync]     = useState('');
  const snapshotAuthRef                 = useRef(null);

  const setStatus = useCallback((type, text) => {
    setStatusType(type);
    setStatusText(text);
  }, []);

  // Derive which section to show from storage state
  const view = !storageData
    ? 'loading'
    : (!storageData.auth_token || !storageData.username)
      ? 'no-auth'
      : (!storageData.subscribed_email && !storageData.signup_skipped)
        ? 'signup'
        : 'snapshot';

  const loadSnapshot = useCallback((authToken, username, baseUrl, force = false, numDays = 7) => {
    snapshotAuthRef.current = { authToken, username, baseUrl, days: numDays };
    setStripLoading(true);
    setDays(null);

    chrome.storage.local.get([SNAPSHOT_KEY], (stored) => {
      const cached = stored[SNAPSHOT_KEY];
      if (!force && cached?.data && (Date.now() - cached.ts) < SNAPSHOT_TTL_MS) {
        setDays(cached.data.days);
        setStripLoading(false);
        setFooterSync(syncLabel(cached.ts));
        return;
      }

      const fetchP = fetch(`${window.APP_URL}/api/snapshot`, {
        method:  'POST',
        headers: { 'Content-Type': 'application/json' },
        body:    JSON.stringify({
          username,
          auth_token: authToken,
          base_url:   baseUrl || 'https://ontrack.deakin.edu.au',
          days:       numDays,
        }),
      });
      const timeoutP = new Promise((_, rej) => setTimeout(() => rej(new Error('timeout')), 10000));

      Promise.race([fetchP, timeoutP])
        .then((r) => {
          if (!r.ok) {
            return r.json().then((body) => {
              if (body.hint === 'open_ontrack') {
                setStatus('warning', 'Session expired — open OnTrack to refresh');
              }
              throw new Error(`HTTP ${r.status}`);
            });
          }
          return r.json();
        })
        .then((data) => {
          const ts = Date.now();
          if (data.is_stale) {
            setStatus('warning', 'Session expired — open OnTrack for latest updates');
          } else {
            setStatus('ok', `Logged in as ${username}`);
            chrome.storage.local.set({ [SNAPSHOT_KEY]: { ts, data } });
          }
          if (data.auth_token && data.auth_token !== authToken) {
            chrome.storage.local.set({ auth_token: data.auth_token });
          }
          setDays(data.days);
          setFooterSync(data.is_stale ? 'Stale Data' : syncLabel(ts));
        })
        .catch((err) => {
          setStatus('warning', 'Could not load tasks — is the OnTrack Brief server running on port 5001?');
        })
        .finally(() => setStripLoading(false));
    });
  }, [setStatus]);

  // Load from chrome.storage on mount
  useEffect(() => {
    chrome.storage.local.get(
      ['auth_token', 'username', 'base_url', 'subscribed_email',
       'strip_weeks', 'recently_completed_days', 'max_todo_tasks', 'signup_skipped', 'brief_hour'],
      (data) => {
        setStorageData(data);
        if (data.auth_token && data.username) {
          setStatus('ok', `Logged in as ${data.username}`);
          if (data.subscribed_email || data.signup_skipped) {
            const weeks = parseInt(data.strip_weeks || '1', 10);
            loadSnapshot(data.auth_token, data.username, data.base_url, false, weeks * 7);
          }
        } else {
          setStatus('warning', 'Open OnTrack — your tasks will appear automatically');
        }
      }
    );
  }, []);

  const handleRefresh = () => {
    const a = snapshotAuthRef.current;
    if (!a) return;
    chrome.storage.local.remove(SNAPSHOT_KEY, () => {
      loadSnapshot(a.authToken, a.username, a.baseUrl, true, a.days);
    });
  };

  const handleStripWeeksChange = (weeks) => {
    chrome.storage.local.set({ strip_weeks: String(weeks) });
    setStorageData((prev) => ({ ...prev, strip_weeks: String(weeks) }));
    const a = snapshotAuthRef.current;
    if (a) {
      chrome.storage.local.remove(SNAPSHOT_KEY, () => {
        loadSnapshot(a.authToken, a.username, a.baseUrl, true, weeks * 7);
      });
    }
  };

  const handleSignup = (email) =>
    new Promise((resolve, reject) => {
      chrome.storage.local.get(['auth_token', 'username', 'base_url'], (stored) => {
        fetch(`${window.APP_URL}/register`, {
          method:  'POST',
          headers: { 'Content-Type': 'application/json' },
          body:    JSON.stringify({
            base_url:   stored.base_url || 'https://ontrack.deakin.edu.au',
            username:   stored.username,
            auth_token: stored.auth_token,
            email,
            brief_hour: 8,
          }),
        })
          .then((r) => r.json())
          .then((res) => {
            if (res.ok) {
              chrome.storage.local.set({ subscribed_email: email }, () => {
                setStorageData((prev) => ({ ...prev, subscribed_email: email }));
              });
            }
            resolve(res);
          })
          .catch(reject);
      });
    });

  const handleSkipSignup = () => {
    chrome.storage.local.set({ signup_skipped: true });
    setStorageData((prev) => ({ ...prev, signup_skipped: true }));
  };

  const handleSubscribe = ({ email, hour, recentlyDays, maxTodo }) =>
    new Promise((resolve, reject) => {
      chrome.storage.local.get(['auth_token', 'username', 'base_url'], (stored) => {
        if (!stored.auth_token || !stored.username) {
          reject(new Error('no-session'));
          return;
        }
        fetch(`${window.APP_URL}/setup`, {
          method:  'POST',
          headers: { 'Content-Type': 'application/json' },
          body:    JSON.stringify({
            base_url:                stored.base_url || 'https://ontrack.deakin.edu.au',
            username:                stored.username,
            auth_token:              stored.auth_token,
            email,
            brief_hour:              parseInt(hour, 10),
            recently_completed_days: parseInt(recentlyDays, 10),
            max_todo_tasks:          parseInt(maxTodo, 10),
          }),
        })
          .then((r) => {
            if (r.ok) {
              chrome.storage.local.set({ subscribed_email: email, recently_completed_days: recentlyDays, max_todo_tasks: maxTodo, brief_hour: hour });
              setStorageData((prev) => ({ ...prev, subscribed_email: email }));
            }
            resolve(r);
          })
          .catch(reject);
      });
    });

  const handleUnsubscribe = (email) =>
    fetch(`${window.APP_URL}/unsubscribe/${encodeURIComponent(email)}`)
      .then(() => {
        chrome.storage.local.remove(['subscribed_email', 'signup_skipped']);
        setStorageData((prev) => ({ ...prev, subscribed_email: undefined, signup_skipped: undefined }));
        setStatus('warning', 'Unsubscribed — enter your email to re-subscribe.');
      });

  const username = storageData?.username || '';

  return (
    <>
      <Header
        onSettings={() => setActiveTab((t) => (t === 'settings' ? 'main' : 'settings'))}
        onRefresh={handleRefresh}
        settingsActive={activeTab === 'settings'}
      />

      {statusType !== 'ok' && <StatusPill type={statusType} text={statusText} />}

      {activeTab === 'main' && (
        <>
          {view === 'no-auth'  && <NoAuth />}
          {view === 'signup'   && <SignupFlow onSignup={handleSignup} onSkip={handleSkipSignup} />}
          {view === 'snapshot' && <SnapshotView days={days} loading={stripLoading} />}
        </>
      )}

      {activeTab === 'settings' && storageData && (
        <Settings
          initialEmail={storageData.subscribed_email || ''}
          initialHour={storageData.brief_hour || '8'}
          initialRecentlyDays={storageData.recently_completed_days || '7'}
          initialMaxTodo={storageData.max_todo_tasks || '10'}
          initialStripWeeks={storageData.strip_weeks || '1'}
          subscribedEmail={storageData.subscribed_email}
          onSubscribe={handleSubscribe}
          onUnsubscribe={handleUnsubscribe}
          onStripWeeksChange={handleStripWeeksChange}
        />
      )}

      <Footer footerUser={username} footerSync={footerSync} />
    </>
  );
}
