function truncateLabel(text, max = 42) {
  if (!text) return ''
  return text.length > max ? `${text.slice(0, max - 1)}…` : text
}

export default function FeedbackList({ items }) {
  const entries = items || []
  return (
    <div className="feedback-section">
      <div className="feedback-title">Tutor feedback</div>
      {entries.length === 0 ? (
        <div className="feedback-empty">No recent tutor feedback.</div>
      ) : (
        entries.map((entry, idx) => (
          <a
            key={idx}
            className="feedback-item"
            href={entry.url || '#'}
            target="_blank"
            rel="noopener noreferrer"
            title={entry.task}
          >
            <div className="feedback-meta">
              <span className="feedback-unit">{entry.unit}</span>
              <span className="feedback-task">{truncateLabel(entry.task)}</span>
            </div>
            <div className="feedback-text">{entry.text}</div>
          </a>
        ))
      )}
    </div>
  )
}
