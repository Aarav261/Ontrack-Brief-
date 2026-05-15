export default function StatusPill({ type, text }) {
  return (
    <div className={`status-pill ${type}`}>
      <span className={`dot ${type}`} />
      <span>{text}</span>
    </div>
  );
}
