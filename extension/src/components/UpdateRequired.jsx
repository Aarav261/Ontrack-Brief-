const RELEASES_URL = 'https://github.com/Aarav261/Ontracker/releases/latest'

export default function UpdateRequired({ currentVersion, minRequired }) {
  return (
    <div className="info-card">
      <div className="info-icon">⚠️</div>
      <div className="info-title">Update required</div>
      <div className="info-sub">
        You're on v{currentVersion} — v{minRequired} is now required.
        <br />
        Download the latest version to keep using OnTrack Brief.
      </div>
      <button
        className="signin-btn"
        style={{ marginTop: '12px' }}
        onClick={() => chrome.tabs.create({ url: RELEASES_URL })}
      >
        Download v{minRequired}
      </button>
    </div>
  )
}
