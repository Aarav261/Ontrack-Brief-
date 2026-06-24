import { useState } from 'react'
import { useAuth } from '@clerk/chrome-extension'
import Header from './components/Header'
import StatusPill from './components/StatusPill'
import NoAuth from './components/NoAuth'
import SignInCTA from './components/SignInCTA'
import SnapshotView from './components/SnapshotView'
import Settings from './components/Settings'
import ReportIssue from './components/ReportIssue'
import Footer from './components/Footer'
import UpdateRequired from './components/UpdateRequired'
import { api } from './lib/api'
import { useSnapshot } from './hooks/useSnapshot'
import { useVersionGate } from './hooks/useVersionGate'

export default function App() {
  const { isLoaded, isSignedIn, getToken } = useAuth()
  const [activeTab, setActiveTab] = useState('main')

  const currentVersion = chrome.runtime.getManifest().version
  const minVersion = useVersionGate(currentVersion)

  const {
    view,
    status,
    days,
    feedback,
    subscribed,
    stripLoading,
    footerSync,
    storageData,
    username,
    actions,
  } = useSnapshot({ isLoaded, isSignedIn, getToken })

  const handleReportIssue = (description) =>
    api('/api/issues', {
      method: 'POST',
      getToken,
      body: { description, version: currentVersion },
    })

  if (minVersion) {
    return <UpdateRequired currentVersion={currentVersion} minRequired={minVersion} />
  }

  return (
    <>
      <Header
        onSettings={() =>
          setActiveTab((t) => (t === 'settings' ? 'main' : 'settings'))
        }
        onReport={() => setActiveTab((t) => (t === 'report' ? 'main' : 'report'))}
        onRefresh={actions.refresh}
        settingsActive={activeTab === 'settings'}
        reportActive={activeTab === 'report'}
      />

      {status.type !== 'ok' && <StatusPill type={status.type} text={status.text} />}

      {/* Settings & feedback panels require a signed-in session; otherwise fall
          back to the main view (which surfaces the sign-in CTA). */}
      {activeTab === 'settings' && storageData && isSignedIn ? (
        <Settings
          initialHour={storageData.brief_hour || '8'}
          initialBriefWeeks={storageData.brief_weeks || '1'}
          initialStripWeeks={storageData.strip_weeks || '1'}
          subscribed={subscribed}
          onSubscribe={actions.saveSettings}
          onUnsubscribe={actions.unsubscribe}
          onStripWeeksChange={actions.setStripWeeks}
          onBriefWeeksChange={actions.setBriefWeeks}
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
