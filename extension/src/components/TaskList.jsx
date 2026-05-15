const MONTHS = ['Jan','Feb','Mar','Apr','May','Jun','Jul','Aug','Sep','Oct','Nov','Dec'];

const GRADE_CONFIG = {
  'P (Pass)':             { short: 'P',  color: '#fbbf24', bg: 'rgba(251,191,36,0.13)'  },
  'C (Credit)':           { short: 'C',  color: '#34d399', bg: 'rgba(52,211,153,0.12)'  },
  'D (Distinction)':      { short: 'D',  color: '#60a5fa', bg: 'rgba(96,165,250,0.12)'  },
  'HD (High Distinction)':{ short: 'HD', color: '#c084fc', bg: 'rgba(192,132,252,0.12)' },
};
const FALLBACK_CFG = { short: '?', color: '#9ca3af', bg: 'rgba(156,163,175,0.1)' };

function formatDueDate(iso) {
  if (!iso) return '';
  const parts = iso.split('-');
  return `${parseInt(parts[2])} ${MONTHS[parseInt(parts[1]) - 1]}`;
}

function dueLabel(offset) {
  if (offset === 0) return 'due today';
  if (offset === 1) return 'tomorrow';
  return `${offset} Days `;
}

export default function TaskList({ days }) {
  const allTasks = (days || [])
    .flatMap((d) => d.tasks.map((t) => ({ ...t, offset: d.offset })))
    .sort((a, b) => a.offset - b.offset);

  const count = allTasks.length;

  return (
    <div className="task-list-section">
      <div className="task-list-header">
        <span className="task-list-title">Tasks</span>
      </div>

      {count === 0 ? (
        <div className="task-empty">Nothing due in the next 7 days</div>
      ) : (
        allTasks.map((t, i) => {
          const cfg      = GRADE_CONFIG[t.grade] || FALLBACK_CFG;
          const isUrgent = t.offset <= 3;
          const barWidth = Math.max(8, 100 - t.offset * 13);

          return (
            <div key={i} className="task-item">
              {/* Coloured left accent — replaces the grade icon box */}
              <div className="task-accent" style={{ background: cfg.color }} />

              <div className="task-body">
                <div className="task-name">{t.name}</div>
                <div className="task-meta">
                  {t.abbreviation ? `${t.abbreviation} · ` : ''}{t.unit}
                  {' · '}
                  <span style={{ color: cfg.color, fontWeight: 700 }}>{cfg.short}</span>
                </div>
                <div className="task-bar-wrap">
                  <div
                    className="task-bar"
                    style={{ width: `${barWidth}%`, background: cfg.color, opacity: 0.7 }}
                  />
                </div>
              </div>

              <div className="task-right">
                <div className={`task-due ${isUrgent ? 'red' : 'orange'}`}>
                  {dueLabel(t.offset)}
                </div>
                <div className="task-date">{formatDueDate(t.due_date)}</div>
              </div>
            </div>
          );
        })
      )}
    </div>
  );
}
