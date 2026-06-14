# Deterministic Brief — Client-Push Architecture Plan

> Goal: the morning brief and the extension panels become a **pure function of the
> local DB + today's date**. The server never calls OnTrack at send time. No token
> minting, no session-expiry path, no re-auth emails.

## The inversion

| | Today (server-pull) | This plan (client-push) |
|---|---|---|
| Who calls OnTrack | the server, every morning, with a stored token | the **student's own browser**, whenever they use OnTrack |
| What the extension captures | the rotating `Auth-Token` header | the **response bodies** (projects, tasks, status, feedback) |
| Morning job | mint token → fetch → categorise → send | **read DB → filter → send** |
| Failure mode | token expires → re-auth email | none — stale data just ages, honestly stamped |

**Core invariant:** OnTrack data can only change while the student is on OnTrack —
which is exactly when capture runs.
- *Student-driven* status (`not_started → working_on_it → ready_for_feedback`): the
  student must be on OnTrack to do it → captured **instantly**.
- *Time-driven* status (overdue): nobody acts; it flips by the calendar → **computed
  locally** from `deadline < today`, never captured.
- *Tutor-driven* status (`fix_and_resubmit`, `complete`, …): captured as-of the
  student's **next visit** — the same moment they'd find out anyway.

## The brief, reduced to one filter

```
show task IF
    today ≤ deadline ≤ today + window          # window = 7 or 14 days (user choice)
    AND status NOT IN HIDE_SET
sort by (deadline asc, grade desc)
```

- Forward-only: past-due tasks fall out via the date filter, so **overdue needs no
  special handling** in the brief.
- `HIDE_SET = SUBMITTED ∪ DONE` (from `core/constants.py`): hides `ready_for_feedback`,
  `complete`, `fail`.
- **Open decision:** whether `WAITING = {discuss, demonstrate}` joins `HIDE_SET`.
  Default below leaves them **visible**; flip one constant to hide.
- Unknown/new statuses default to **show** (over-remind rather than silently drop a
  real deadline).

---

# Phase 1 — Schema (`core/db.py`)

Two new tables, following the existing PG/SQLite dual-DDL + `ALTER TABLE` migration
pattern in `init_db()` (`db.py:65`). Nothing here is an at-rest credential, so no
encryption needed (unlike `auth_token`).

```sql
-- projects: one row per active unit the student is enrolled in
CREATE TABLE IF NOT EXISTS projects (
    user_id        INTEGER NOT NULL,        -- FK → users.id
    project_id     INTEGER NOT NULL,        -- OnTrack project id
    unit_code      TEXT,
    unit_name      TEXT,
    unit_end_date  TEXT,
    last_seen      TEXT NOT NULL,
    PRIMARY KEY (user_id, project_id)
);

-- tasks: one row per task definition, upserted on every capture
CREATE TABLE IF NOT EXISTS tasks (
    user_id            INTEGER NOT NULL,     -- FK → users.id
    project_id         INTEGER NOT NULL,
    task_def_id        INTEGER NOT NULL,
    abbreviation       TEXT,
    name               TEXT,
    unit_code          TEXT,                 -- denormalised for the brief query
    target_grade_label TEXT,
    deadline           TEXT,                 -- resolved ISO date; the only filter field
    status             TEXT,
    feedback_text      TEXT,
    feedback_seen_at   TEXT,
    last_seen          TEXT NOT NULL,
    PRIMARY KEY (user_id, project_id, task_def_id)
);
CREATE INDEX IF NOT EXISTS idx_tasks_user_deadline ON tasks(user_id, deadline);
```

New accessors in `db.py`:
- `upsert_projects(user_id, projects)` / `prune_ended_projects(user_id, today)`
- `upsert_tasks(user_id, project_id, tasks)` — `ON CONFLICT (user_id, project_id,
  task_def_id) DO UPDATE` all mutable fields + `last_seen`
- `set_task_feedback(user_id, project_id, task_def_id, text)`
- `get_pending_tasks(user_id, today, window_days)` — the brief query (filter + sort),
  status filtering done in Python against `HIDE_SET` for clarity

**Ship test:** migrations run clean on a copy of `ontracker.db` and on PG; tables and
index exist.

---

# Phase 2 — `/ingest` endpoint (`routes/main.py`)

Incremental and idempotent: the extension captures payloads piecemeal as the student
navigates, so `/ingest` accepts one fragment at a time and upserts. Reuses
`_enrich_tasks` / `_append_missing_tasks` (`core/ontrack/fetcher.py:40,59`) **unchanged**
— the date-resolution heuristic now runs once, at capture time, against fresh data, and
the result is frozen.

Identity is the **body-supplied username**, mirroring `/refresh-token` — the
background service worker pushes captures while the popup is closed, so there's no
Clerk session in that context. The payload is course data, not a credential; the
worst case is a known-username task list being poisoned (same trust model the token
push already accepts). Rate-limited at 120/min (passive capture is chatty).

```
POST /ingest        (resolve user by body username, like /refresh-token)
Body: { username, kind, payload }

kind = "projects"        payload = raw /api/projects response
   → filter to active units (end_date ≥ today), upsert_projects, prune ended

kind = "project_tasks"   payload = { project_id, tasks, unit:{id, task_definitions} }
   → _enrich_tasks + _append_missing_tasks, then upsert_tasks
   (tasks = body of /api/projects/{id}; task_definitions = body of /api/units/{id})

kind = "feedback"        payload = { project_id, task_def_id, comments }
   → _extract_latest_feedback(comments, student_id) → set_task_feedback
```

Returns `{ ok: true, stored: N }`. No token, no OnTrack call — pure write.

**Ship test:** POST a captured payload by hand → rows appear; re-POST → idempotent.

---

# Phase 3 — Capture (extension)

The interceptor in `extension/public/injected.js` already wraps `XMLHttpRequest`
(`:36`) and `fetch` (`:56`) and reads response *headers*. Extend it to read response
*bodies* for the data endpoints and emit them.

**`injected.js`** — in the XHR `load` handler and the `fetch` `.then`, inspect `url`:
- `/api/projects` (exact) → `ontrack-data-captured` `{ kind: "projects", payload }`
- `/api/projects/{id}` → `{ kind: "project_tasks", payload: { project_id, tasks } }`
- `/api/units/{id}` → merge `task_definitions` into the matching `project_tasks`
- `…/task_def_id/{id}/comments` → `{ kind: "feedback", payload }`

Clone before reading: `xhr.responseText` is already available on `load`; for `fetch`
use `response.clone().json()` so the page still receives its body.

**`content.js`** — add a listener mirroring the token one (`content.js:15`): on
`ontrack-data-captured`, forward to background via `chrome.runtime.sendMessage`.

**`background.js`** — add a handler beside the `refresh-token` one (`background.js:50`)
that `POST`s to `/ingest`. (Routing through background avoids the mixed-content block,
same reason the token push does.)

Optional **sync sweep:** `/api/projects/{id}` only fires when the student opens that
unit. Once an authenticated session is detected, the content script can fire those
calls itself in page context (student's token is right there) for full coverage on a
single visit, rather than waiting for them to click each unit.

**Ship test:** browse OnTrack with the unpacked extension → tasks/feedback rows populate
in the DB; submit a task → its `status` updates to `ready_for_feedback` on next capture.

---

# Phase 4 — Brief read-path (`core/brief`, `core/jobs.py`)

Replace the categorisation engine with the filter.

**`core/brief/builder.py`** — `_build_brief` / `_score` (`builder.py:28-109`) are
**deleted**. New:
```python
HIDE_SET = SUBMITTED | DONE          # | WAITING  ← flip to hide discuss/demonstrate

def pending_tasks(rows, today, window_days):
    end = today + timedelta(days=window_days)
    out = [r for r in rows
           if r["deadline"]
           and today <= date.fromisoformat(r["deadline"]) <= end
           and r["status"] not in HIDE_SET]
    out.sort(key=lambda r: (r["deadline"],
                            -GRADE_WEIGHT.get(r["target_grade_label"], 0)))
    return out
```

**`core/jobs.py` — `run_brief` (`:53`)** collapses to:
```
user = get_user_by_id(id)                 # unchanged
if not subscribed: return                 # unchanged
rows = get_pending_tasks(id, today, window)# NEW — DB read, no OnTrack
html = render_html(rows, today, window)    # simplified renderer + "as of" stamp
send_brief_to(...)                         # unchanged
```

**Delete from `jobs.py`:** `mint_auth_token`, `fetch_active_projects_direct`,
`TokenManager` usage, `bump_token_fail` / `reset_token_fail` / `_FAIL_THRESHOLD`,
`_pause_and_reauth`, `send_reauth_email`, the whole `TokenExpiredError` /
`RefreshTokenError` ladder (`:82-154`).

**`core/brief/renderer.py`** — render one forward list (no status sections); add an
"as of {last_seen}" line so a stale brief is honest.

**Ship test:** run old and new `run_brief` side by side for a user with data; the new
brief lists exactly the tasks due in-window that aren't submitted.

---

# Phase 5 — Repoint the extension panels (`routes/main.py`)

`/api/snapshot` (`main.py:382`) currently does a **live** server-side OnTrack fetch
(mint → `fetch_active_projects_direct`). Repoint it to read the same DB rows the brief
uses and reshape into the existing `days[]` buckets (`main.py:461-516`) — the
CalendarStrip is already forward-only (`for offset in range(days_count)`), so past-due
already never appears. Drop the mint/fetch/feedback-scrape block (`:406-555`).

Result: strip == email by construction; popup opens instantly (no OnTrack round-trip).

**Ship test:** popup renders from DB with no network call to OnTrack; matches the email.

---

# Phase 6 — Decommission

Once Phases 4–5 are proven in prod:
- Remove the brief's dependence on stored tokens; `run_brief` no longer reads
  `auth_token` / `refresh_token`.
- Retire `send_reauth_email` and the `token_valid` / `token_fail_count` pause logic
  from the brief path (keep columns for now; drop in a later migration).
- Keep token capture (`/refresh-token`, `/refresh-credential`) **only** if you want the
  optional hybrid fallback (server-pull for chronically-inactive students). For pure
  v1, leave it dormant.

---

## Honest caveats (accepted by design)

1. **Best-effort freshness.** The brief is as current as the student's last OnTrack
   visit. Mitigated by the "as of" stamp + frequent passive capture.
2. **Already-submitted tasks** drop off correctly (status capture), but only as of last
   visit — a task submitted then re-opened by a tutor reflects next visit.
3. **Cold start:** a subscriber who hasn't opened OnTrack since signup has no rows →
   skip with an "open OnTrack to start" state, or rely on the `/setup`/`welcome`
   capture that already happens at link time.

## Build order (each independently shippable)

1. Schema + accessors
2. `/ingest`
3. Extension capture
4. Brief read-path + deletions
5. Repoint `/api/snapshot`
6. Decommission token machinery
