export default function StatsRow({ days }) {
  const allTasks = (days || []).flatMap((d) => d.tasks.map((t) => ({ ...t, offset: d.offset })));
  const urgent   = allTasks.filter((t) => t.offset <= 3).length;
  const soon     = allTasks.filter((t) => t.offset >  3).length;
  const total    = allTasks.length;
  const loaded   = days !== null;

  return (
    <div className="stats-row">
      <div className="stat-cell dark">
        <div className="stat-label">Urgent</div>
        <div className="stat-value">{loaded ? urgent : '—'}</div>
        <div className="stat-change">≤ 3 days left</div>
      </div>
      <div className="stat-cell light">
        <div className="stat-label">Due Soon</div>
        <div className="stat-value">{loaded ? soon : '—'}</div>
        <div className="stat-change">4+ days left</div>
      </div>
      <div className="stat-cell accent">
        <div className="stat-label">This Week</div>
        <div className="stat-value">{loaded ? total : '—'}</div>
        <div className="stat-change">Total tasks</div>
      </div>
    </div>
  );
}
