import StatsRow from './StatsRow';
import CalendarStrip from './CalendarStrip';
import TaskList from './TaskList';
import FeedbackList from './FeedbackList';

export default function SnapshotView({ days, loading, feedback }) {
  return (
    <>
      <div className="section-header">
        <span className="section-title">Upcoming Tasks</span>
      </div>
      <StatsRow days={days} />
      <CalendarStrip days={days} loading={loading} />
      <TaskList days={days} />
      <FeedbackList items={feedback} />
    </>
  );
}
