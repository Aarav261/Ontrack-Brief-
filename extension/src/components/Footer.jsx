export default function Footer({ footerUser, footerSync }) {
  return (
    <div className="footer">
      <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
        <a
          className="footer-open"
          href="https://ontrack.deakin.edu.au"
          target="_blank"
          rel="noreferrer"
        >
          Open OnTrack
        </a>
        {footerUser && (
          <span style={{ fontSize: 11, color: '#9ca3af' }}>{footerUser}</span>
        )}
      </div>
      <span className="footer-sync">{footerSync}</span>
      <span className="footer-ver">v1.1</span>
    </div>
  )
}
