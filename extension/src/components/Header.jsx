export default function Header({
  onSettings,
  onRefresh,
  onReport,
  settingsActive,
  reportActive,
}) {
  return (
    <div className="header">
      <div>
        <div className="header-title">OnTrack(er)</div>
        <div className="header-subtitle">Your OnTrack tasks, at a glance</div>
      </div>
      <div className="header-right">
        <button
          className={`icon-btn${reportActive ? ' active' : ''}`}
          onClick={onReport}
          title="Send feedback"
        >
          <svg
            width="16"
            height="16"
            viewBox="0 0 24 24"
            fill="none"
            stroke="currentColor"
            strokeWidth="2"
            strokeLinecap="round"
            strokeLinejoin="round"
            aria-hidden="true"
          >
            <path d="M21 11.5a8.38 8.38 0 0 1-.9 3.8 8.5 8.5 0 0 1-7.6 4.7 8.38 8.38 0 0 1-3.8-.9L3 21l1.9-5.7a8.38 8.38 0 0 1-.9-3.8 8.5 8.5 0 0 1 4.7-7.6 8.38 8.38 0 0 1 3.8-.9h.5a8.48 8.48 0 0 1 8 8v.5z" />
          </svg>
        </button>
        <button
          className={`icon-btn${settingsActive ? ' active' : ''}`}
          onClick={onSettings}
          title="Settings"
        >
          ⚙
        </button>
        <button className="icon-btn" onClick={onRefresh} title="Reload snapshot">
          ↻
        </button>
      </div>
    </div>
  )
}
