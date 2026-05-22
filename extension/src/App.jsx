import { useState, useEffect, useRef, useCallback } from 'react';
import Header from './components/Header';
import StatusPill from './components/StatusPill';
import NoAuth from './components/NoAuth';
import SignupFlow from './components/SignupFlow';
import SnapshotView from './components/SnapshotView';
import Settings from './components/Settings';
import Footer from './components/Footer';
import { api } from './lib/api';
import { syncLabel } from './utils/time';
import { SNAPSHOT_KEY, SNAPSHOT_TTL_MS, DEFAULT_BASE_URL } from './constants';

export default function App() {
  const [storageData, setStorageData]   = useState(null);
  const [activeTab, setActiveTab]       = useState('main');
  const [statusType, setStatusType]     = useState('warning');
  const [statusText, setStatusText]     = useState('Waiting for OnTrack…');
  const [days, setDays]                 = useState(null);
  const [feedback, setFeedback]         = useState([]);
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
    setFeedback([]);

    chrome.storage.local.get([SNAPSHOT_KEY], (stored) => {
      const cached = stored[SNAPSHOT_KEY];
      if (!force && cached?.data && (Date.now() - cached.ts) < SNAPSHOT_TTL_MS) {
        setDays(cached.data.days);
        setFeedback(cached.data.feedback || []);
        setStripLoading(false);
        setFooterSync(syncLabel(cached.ts));
        return;
      }

      api('/api/snapshot', {
        method: 'POST',
        body: {
          username,
          auth_token: authToken,
          base_url:   baseUrl || DEFAULT_BASE_URL,
          days:       numDays,
        },
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
          setFeedback(data.feedback || []);
          setFooterSync(data.is_stale ? 'Stale Data' : syncLabel(ts));
        })
        .catch((err) => {
          if (err?.data?.hint === 'open_ontrack') {
            setStatus('warning', 'Session expired — open OnTrack to refresh');
          } else {
            setStatus('warning', 'Could not load tasks — is the OnTrack Brief server running on port 5001?');
          }
          setFeedback([]);
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

  const handleBriefWeeksChange = (weeks) => {
    chrome.storage.local.set({ brief_weeks: String(weeks) });
    setStorageData((prev) => ({ ...prev, brief_weeks: String(weeks) }));
  };

  const handleSignup = (email) =>
    new Promise((resolve, reject) => {
      chrome.storage.local.get(['auth_token', 'username', 'base_url'], (stored) => {
        api('/register', {
          method: 'POST',
          body: {
            base_url:   stored.base_url || DEFAULT_BASE_URL,
            username:   stored.username,
            auth_token: stored.auth_token,
            email,
            brief_hour: 8,
          },
        })
          .then((res) => {
            if (res.ok) {
              chrome.storage.local.set({ subscribed_email: email }, () => {
                setStorageData((prev) => ({ ...prev, subscribed_email: email }));
              });
            }
            resolve(res);
          })
          .catch((err) => {
            // A server error response carries the {ok:false, error} body — let
            // the form surface it. Only a real network failure should reject.
            if (err?.data && Object.keys(err.data).length) resolve(err.data);
            else reject(err);
          });
      });
    });

  const handleSkipSignup = () => {
    chrome.storage.local.set({ signup_skipped: true });
    setStorageData((prev) => ({ ...prev, signup_skipped: true }));
  };

  const handleSubscribe = ({ email, hour, briefWeeks }) =>
    new Promise((resolve, reject) => {
      chrome.storage.local.get(['auth_token', 'username', 'base_url'], (stored) => {
        if (!stored.auth_token || !stored.username) {
          reject(new Error('no-session'));
          return;
        }
        api('/setup', {
          method: 'POST',
          body: {
            base_url:   stored.base_url || DEFAULT_BASE_URL,
            username:   stored.username,
            auth_token: stored.auth_token,
            email,
            brief_hour: parseInt(hour, 10),
            brief_days: parseInt(briefWeeks, 10) * 7,
          },
        })
          .then(() => {
            chrome.storage.local.set({ subscribed_email: email, brief_hour: hour, brief_weeks: briefWeeks });
            setStorageData((prev) => ({ ...prev, subscribed_email: email }));
            resolve();
          })
          .catch(reject);  // err carries .status for the Settings handler
      });
    });

  const handleUnsubscribe = (email) =>
    api(`/unsubscribe/${encodeURIComponent(email)}`)
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
          {view === 'snapshot' && <SnapshotView days={days} loading={stripLoading} feedback={feedback} />}
        </>
      )}

      {activeTab === 'settings' && storageData && (
        <Settings
          initialEmail={storageData.subscribed_email || ''}
          initialHour={storageData.brief_hour || '8'}
          initialBriefWeeks={storageData.brief_weeks || '1'}
          initialStripWeeks={storageData.strip_weeks || '1'}
          subscribedEmail={storageData.subscribed_email}
          onSubscribe={handleSubscribe}
          onUnsubscribe={handleUnsubscribe}
          onStripWeeksChange={handleStripWeeksChange}
          onBriefWeeksChange={handleBriefWeeksChange}
        />
      )}

      <Footer footerUser={username} footerSync={footerSync} />
    </>
  );
}
