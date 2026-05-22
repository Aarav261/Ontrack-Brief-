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

  function handleMouseMove(e, day) {
    if (!sectionRef.current) return;
    const secRect = sectionRef.current.getBoundingClientRect();
    const cursorX = e.clientX - secRect.left;
    const cursorY = e.clientY - secRect.top;
    const TT_WIDTH = 260;
    setTooltip({
      tasks: day.tasks,
      style: {
        // Centre horizontally on the cursor; clamp inside the card
        left:      Math.max(6, Math.min(cursorX - TT_WIDTH / 2, secRect.width - TT_WIDTH - 6)) + 'px',
        top:       cursorY + 'px',
        // Sit just above the pointer
        transform: 'translateY(calc(-100% - 12px))',
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
                onMouseMove={count > 0 ? (e) => handleMouseMove(e, day) : undefined}
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
        <div
          className="strip-tooltip visible"
          style={tooltip.style}
          onMouseLeave={handleMouseLeave}
        >
          {tooltip.tasks.map((t, i) => (
            <a
              key={i}
              className="tt-task"
              href={t.url || '#'}
              target="_blank"
              rel="noopener noreferrer"
            >
              <span className="tt-unit">{t.unit}</span>
              <span className="tt-name">{t.name}</span>
              <span className="tt-grade">{GRADE_SHORT[t.grade] || t.grade}</span>
            </a>
          ))}
        </div>
      )}
    </div>
  );
}
