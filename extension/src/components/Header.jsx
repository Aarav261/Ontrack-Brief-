export default function Header({ onSettings, onRefresh, settingsActive }) {
  return (
    <div className="header">
      <div>
        <div className="header-title">OnTrack(er)</div>
        <div className="header-subtitle">Your OnTrack tasks, at a glance</div>
      </div>
      <div className="header-right">
        <button
          className={`icon-btn${settingsActive ? ' active' : ''}`}
          onClick={onSettings}
          title="Settings"
        >
          ⚙
        </button>
        <button
          className="icon-btn"
          onClick={onRefresh}
          title="Reload snapshot"
        >
          ↻
        </button>
      </div>
    </div>
  )
}
