import StatsRow from './StatsRow';
import CalendarStrip from './CalendarStrip';
import TaskList from './TaskList';

export default function SnapshotView({ days, loading }) {
  return (
    <>
      <div className="section-header">
        <span className="section-title">Upcoming Tasks</span>
      </div>
      <StatsRow days={days} />
      <CalendarStrip days={days} loading={loading} />
      <TaskList days={days} />
    </>
  );
}
