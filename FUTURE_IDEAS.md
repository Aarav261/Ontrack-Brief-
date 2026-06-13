# Future Ideas

A backlog of features and improvements to revisit. Not committed work — just
captured so nothing gets lost.

## Custom brief send time (any time of day)

**What:** Let users pick *any* send time instead of the fixed 6–10 AM dropdown
(`extension/src/components/Settings.jsx`). Ideally a scrollable hour + minute
picker ("time scroll").

**Why:** Users want full control over when the daily brief lands.

**Approaches considered:**
- **Native time picker** — a styled `<input type="time">` (scrollable HH:MM, any
  minute). Least custom code; matches OS time-scroll UX.
- **Custom scroll wheel** — bespoke iOS-style hour/minute wheel, fully matching the
  extension's Lora aesthetic. Most polished, most code.
- **All 24 hours dropdown** — simplest (list 00:00–23:00), but no minute control.

**What it touches:**
- Extension UI (`Settings.jsx`) — replace the 6–10 AM `<select>`.
- Request payloads — `/link-ontrack`, `/register`, `/setup` send `brief_hour`;
  add `brief_minute`.
- DB — add a `brief_minute` column (idempotent migration, PG + SQLite), default 0.
- `schedule_brief` (`core/jobs.py`) — `CronTrigger(hour=brief_hour,
  minute=brief_minute, timezone=_BRIEF_TZ)` (currently `minute=0`).
- Keep the Australia/Melbourne timezone already wired in.

**Open question:** minute granularity (any HH:MM) vs hour-only — "whatever time
they desire" implies full HH:MM, which is why a `brief_minute` column is needed.

## Snapshot speed — remaining optimizations

Done on `perf/snapshot-parallel-swr`: parallelized per-project task fetches
(ThreadPoolExecutor) + client stale-while-revalidate. Still on the table:

- **Lazy-load / parallelize feedback.** The up-to-8 `/comments` calls in
  `api_snapshot` are still sequential and run after the task fetches. Either
  parallelize them (own sessions, like the task fetch) or move them to a separate
  `/api/feedback` request so the task strip renders first.
- **Skip the redundant mint per open.** `api_snapshot` now mints on every call
  (one extra OnTrack round-trip). Cache the minted token in-process for a few
  minutes per user, or skip minting if the stored token was refreshed very
  recently.
- **Fast cached-return endpoint for cold cross-device opens.** Client SWR covers
  repeat opens; a first open on a new device has no client cache. The server
  already stores `last_snapshot` — a `?prefer_cached=1` fast path could return it
  instantly while the client revalidates.
- **Tighter interactive timeouts.** The transport `Retry(total=3, backoff=0.5)`
  and 10–15s timeouts can stall a popup load on one flaky call; use a shorter
  budget for the interactive snapshot path.
