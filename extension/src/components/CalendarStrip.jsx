import { useRef, useState } from 'react';

const GRADE_SHORT = {
  'P (Pass)': 'P', 'C (Credit)': 'C',
  'D (Distinction)': 'D', 'HD (High Distinction)': 'HD',
};

function dotClass(offset, count) {
  if (count === 0) return '';
  return offset <= 3 ? 'red' : 'orange';
}

export default function CalendarStrip({ days, loading }) {
  const sectionRef = useRef(null);
  const [tooltip, setTooltip] = useState(null); // { tasks, style }

  function handleMouseEnter(e, day) {
    if (!sectionRef.current) return;
    const colRect = e.currentTarget.getBoundingClientRect();
    const secRect = sectionRef.current.getBoundingClientRect();
    const colCenter = colRect.left - secRect.left + colRect.width / 2;
    const colTop    = colRect.top  - secRect.top;
    setTooltip({
      tasks: day.tasks,
      style: {
        // Center tooltip over column; clamp so it stays within the card
        left:      Math.max(6, Math.min(colCenter - 130, secRect.width - 266)) + 'px',
        top:       colTop + 'px',
        transform: 'translateY(calc(-100% - 6px))',
      },
    });
  }

  function handleMouseLeave() {
    setTooltip(null);
  }

  const twoWeek = days && days.length > 7;

  return (
    <div className="strip-section" ref={sectionRef}>
      <div className="strip-header">
        <span className="strip-title">Schedule</span>
        <span className="strip-subtitle">Upcoming deadlines</span>
      </div>

      {loading && (
        <div className="strip-loading">
          <span className="strip-ld" />
          <span className="strip-ld" />
          <span className="strip-ld" />
        </div>
      )}

      {!loading && days && (
        <div className={`strip-row${twoWeek ? ' two-week' : ''}`}>
          {days.map((day) => {
            const count  = day.tasks.length;
            const cls    = dotClass(day.offset, count);
            const dateNum = day.date.slice(8);
            return (
              <div
                key={day.date}
                className={[
                  'strip-col',
                  day.offset === 0 ? 'today'     : '',
                  count > 0       ? 'has-tasks'  : '',
                ].filter(Boolean).join(' ')}
                onMouseEnter={count > 0 ? (e) => handleMouseEnter(e, day) : undefined}
                onMouseLeave={count > 0 ? handleMouseLeave : undefined}
              >
                <span className="strip-day">{day.label}</span>
                <span className="strip-date">{dateNum}</span>
                <span className={`strip-dot${cls ? ` ${cls}` : ''}`}>
                  {count > 0 ? count : ''}
                </span>
              </div>
            );
          })}
        </div>
      )}

      {tooltip && (
        <div className="strip-tooltip visible" style={tooltip.style}>
          {tooltip.tasks.map((t, i) => (
            <span key={i} className="tt-task">
              <span className="tt-unit">{t.unit}</span>
              <span className="tt-name">{t.name}</span>
              <span className="tt-grade">{GRADE_SHORT[t.grade] || t.grade}</span>
            </span>
          ))}
        </div>
      )}
    </div>
  );
}
