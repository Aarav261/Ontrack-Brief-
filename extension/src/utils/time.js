// Time / relative-time formatting helpers.

/** Human "Synced Ns/Nm/Nh ago" label for a past timestamp (ms since epoch). */
export function syncLabel(ts) {
  const sec = Math.floor((Date.now() - ts) / 1000);
  if (sec < 60) return `Synced ${sec}s ago`;
  const min = Math.floor(sec / 60);
  if (min < 60) return `Synced ${min}m ago`;
  return `Synced ${Math.floor(min / 60)}h ago`;
}
