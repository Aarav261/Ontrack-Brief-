# OnTrack Brief — Architecture

A system that emails Deakin students a prioritised daily summary of their
OnTrack (Doubtfire) tasks, plus a Chrome extension that shows a live task
strip and keeps the user's auth token fresh.

> **The hard problem this system solves:** OnTrack (Doubtfire) **rotates the
> auth token on every single API response**. A token captured at 9am is dead by
> 9:01am once the user browses OnTrack. So the server can't just store one token
> and reuse it forever — it must continuously chase the latest token. Almost
> every design decision below exists to manage this rotation.

---

## 1. The Three Moving Parts

```
┌──────────────────────┐     ┌──────────────────────┐     ┌──────────────────────┐
│   Chrome Extension    │     │   Flask Web Server    │     │   OnTrack / Doubtfire │
│   (runs in browser)   │     │   (Python backend)    │     │   (Deakin's API)      │
│                       │     │                       │     │                       │
│ • Captures auth token │────▶│ • Stores users + token│────▶│ • Returns tasks       │
│ • Shows task strip    │◀────│ • Sends daily emails  │◀────│ • Rotates token on    │
│ • Pushes fresh tokens │     │ • Schedules jobs      │     │   every response      │
└──────────────────────┘     └──────────────────────┘     └──────────────────────┘
         │                              │
         │                              ▼
         │                    ┌──────────────────────┐
         │                    │    Resend (email)     │
         │                    └──────────────────────┘
         ▼
   chrome.storage.local
   (auth_token, username,
    subscribed_email, …)
```

| Part | Tech | Location | Role |
|------|------|----------|------|
| **Extension** | React + Vite, MV3 | `extension/` | Token capture, live task strip, subscription UI |
| **Web server** | Flask + APScheduler | `app.py`, `routes/`, `core/` | User store, scheduled briefs, snapshot API |
| **Database** | PostgreSQL (prod) / SQLite (dev) | `core/db.py` | One `users` table |
| **Email** | Resend | `core/mailer.py` | Brief + re-auth delivery |
| **Source** | OnTrack/Doubtfire REST API | external | Projects, tasks, comments |

---

## 2. Token Authentication — The Core of the System

### 2.1 Why it's hard

Doubtfire uses **rotating bearer tokens**. Each authenticated request must send
`Username` + `Auth-Token` headers. The response comes back with a **new**
`Auth-Token` header that must be used on the *next* request. The old token is
immediately invalid.

This means:
- You cannot store a token and reuse it on a schedule — it rots the moment the
  user uses OnTrack in their browser.
- Concurrent requests with the same token will clobber each other (one wins, the
  other's token becomes stale).

### 2.2 How a token is captured (extension side)

The user never copies/pastes anything. The extension intercepts OnTrack's own
network traffic:

```
OnTrack page (HTTPS)
    │
    │ 1. content.js injects injected.js into the PAGE context
    ▼
injected.js  ── monkeypatches XMLHttpRequest + fetch ──┐
    │                                                   │
    │ 2. On every OnTrack API response, reads the       │
    │    rotated "Auth-Token" response header           │
    ▼                                                   │
window.dispatchEvent("ontrack-auth-captured")           │
    │                                                   │
    │ 3. content.js hears the event                     │
    ▼                                                   │
chrome.storage.local.set({ auth_token, username })  ◀───┘
    │
    │ 4. content.js → background.js (avoids mixed-content block:
    │    HTTPS page can't POST to HTTP localhost directly)
    ▼
background.js  POST /refresh-token  →  Flask server
```

**Key files:**
- [extension/public/injected.js](extension/public/injected.js) — runs in page
  context, patches `XMLHttpRequest.open` and `window.fetch` to read the
  `Auth-Token` response header. Dedupes so it only emits on change.
- [extension/public/content.js](extension/public/content.js) — bridge: injects
  the interceptor, stores tokens in `chrome.storage.local`, forwards to
  background.
- [extension/public/background.js](extension/public/background.js) — service
  worker that POSTs the token to `/refresh-token` (the content script can't
  reach HTTP localhost from an HTTPS page).

> Why a 3-script dance? Page-context patching (injected.js) is the only way to
> see response headers; the extension sandbox can't. But page context can't use
> `chrome.*` APIs — hence content.js. And HTTPS→HTTP requests are blocked —
> hence background.js.

### 2.3 How a token is kept fresh (server side)

The server's freshness logic is owned by **`TokenManager`**
([core/ontrack/auth.py](core/ontrack/auth.py)) — it builds the `Username`/
`Auth-Token` headers, captures the rotated token off each response, validates a
token, and persists changes back to the DB. Three mechanisms chase the rotating
token:

**(a) Push from extension — `/refresh-token`** ([routes/main.py](routes/main.py))
Called on *every OnTrack page load*. A lightweight handler (not via TokenManager):
if the token changed or was marked invalid, the DB is updated, and if it was
previously invalid the brief schedule is restored. This is the primary freshness
mechanism.

**(b) Capture during the server's own API calls — `TokenManager`**
([core/ontrack/auth.py](core/ontrack/auth.py))
When the server fetches tasks, *those responses also rotate the token*. Each
brief run builds one manager (`TokenManager.for_user(user)`); its isolated
session installs a response hook that captures the newest token into `tm.token`,
and `tm.persist(user)` writes it back to the DB. One manager per run means
concurrent jobs never clobber each other's tokens.

**(c) Periodic poll — `refresh_all_tokens()`** ([core/jobs.py](core/jobs.py))
Every 20 minutes, `tm.validate()` checks each user's token against
`/api/unit_roles`. If rotated → `tm.persist()` updates the DB. If rejected →
mark invalid, pause briefs, send re-auth email. A transient/server error is
treated as "unreachable" and skipped (no false re-auth).

### 2.4 Token lifecycle state machine

```
                 extension pushes token via /register or /setup
                                  │
                                  ▼
                          ┌───────────────┐
        token rotates     │  token_valid  │   used in brief / validate
        (captured & saved)│      = 1      │◀──────────────────────┐
              ┌──────────▶│   (ACTIVE)    │                       │
              │           └───────┬───────┘                       │
              │                   │                               │
              │      OnTrack rejects token (401/419)              │
              │      — user clicked "Log Out" on OnTrack          │
              │                   ▼                               │
              │           ┌───────────────┐                      │
              │           │  token_valid  │                      │
              └───────────│      = 0      │                      │
   extension pushes fresh │  (INVALID)    │                      │
   token via /refresh-    │ • brief job   │                      │
   token → schedule_brief │   removed     │                      │
   restores the job       │ • re-auth     │                      │
                          │   email sent  │                      │
                          └───────────────┘                      │
                                                                 │
        api_snapshot serves last_snapshot (stale) ──────────────┘
        while invalid, so the extension still shows something
```

**Important:** an expired token does **not** delete the user. It pauses briefs
and serves the cached `last_snapshot`. The moment the user opens OnTrack again,
the extension pushes a fresh token and everything resumes automatically.

---

## 3. The Database

Single table, two backends. `core/db.py` switches on `DATABASE_URL`:
- `postgresql://…` → PostgreSQL (production) via `psycopg2`
- unset → SQLite at `DB_PATH` (local dev)

The placeholder token `_P` is `%s` (PG) or `?` (SQLite); every query uses it so
the same SQL string works on both.

### 3.1 Schema — `users`

| Column | Type | Notes |
|--------|------|-------|
| `id` | serial / autoincrement PK | used in job IDs (`brief_{id}`) |
| `base_url` | text | e.g. `https://ontrack.deakin.edu.au` |
| `username` | text | OnTrack username (never rotates) |
| `auth_token` | text | **the rotating token — overwritten constantly** |
| `email` | text **UNIQUE** | the upsert key; one subscription per email |
| `brief_hour` | int (default 8) | hour (0–23) to send the daily brief |
| `token_valid` | int (default 1) | 1 = active, 0 = expired/paused |
| `recently_completed_days` | int (default 7) | "recently completed" window |
| `max_todo_tasks` | int (default 10) | cap per section in the email |
| `last_snapshot` | text (JSON) | cached snapshot for stale fallback |
| `created_at` | timestamp | |

`email` is the unique business key — `upsert_user()` does
`INSERT … ON CONFLICT(email) DO UPDATE`. The `id` is only used internally to
name scheduler jobs.

### 3.2 DB access functions ([core/db.py](core/db.py))

| Function | Purpose |
|----------|---------|
| `init_db()` | Create table + run idempotent column migrations |
| `upsert_user(...)` | Create or update by email; returns `id` |
| `get_user_by_id(id)` | Used by `run_brief` (jobs hold the id) |
| `get_user_by_username(name)` | Used by `/refresh-token`, `/api/snapshot` |
| `get_all_users()` | Used by `refresh_all_tokens` + startup restore |
| `mark_token_invalid(email)` | Set `token_valid = 0` |
| `update_user_snapshot(name, json)` | Cache latest snapshot |
| `remove_user(email)` | Unsubscribe |
| `get_sqlalchemy_url()` | URL for APScheduler's job store (shared DB) |

> **Two consumers of the DB:** the app code (above) **and** APScheduler, which
> stores its own job rows via `SQLAlchemyJobStore` ([extensions.py](extensions.py))
> in the same database. That's why scheduled jobs survive a server restart.

---

## 4. Scheduling — APScheduler

[extensions.py](extensions.py) configures a `BackgroundScheduler` with a
**SQLAlchemy job store** (same DB as users) so jobs persist across restarts.

Jobs ([core/jobs.py](core/jobs.py)):

| Job ID | Trigger | Function | Purpose |
|--------|---------|----------|---------|
| `brief_{user_id}` | Cron: Mon–Fri at `brief_hour`:00 | `run_brief` | The daily email |
| `welcome_{user_id}` | Date: now + 10s | `run_brief` | Immediate brief on subscribe |
| `token_refresh` | Cron: every 20 min | `refresh_all_tokens` | Token freshness poll |
| `token_refresh_startup` | Date: now + 5s | `refresh_all_tokens` | Refresh on boot |

On startup ([core/jobs.py](core/jobs.py) `startup()` → called from
[app.py](app.py)): init DB, re-register a `brief_*` job for every user with a
valid token, start the scheduler, kick a one-off refresh.

---

## 5. Request Flows

### 5.1 First-time subscribe

```
Extension (SignupFlow)                Flask                      DB / Scheduler
─────────────────────                ─────                      ──────────────
POST /register ───────────────────▶  TokenManager.validate() ─▶ OnTrack
{email, username,                     (rotates token)
 auth_token, base_url,                     │
 brief_hour}                               ▼
                                      upsert_user() ─────────▶ users row created
                                      schedule_brief() ──────▶ brief_{id} cron job
                                      add_job(welcome) ──────▶ run_brief in 10s
                                           │
◀────────────────────────────────── {ok: true}
                                                             (10s later)
                                      run_brief() ──────────▶ fetch tasks, send email
```

`/setup` (Settings panel) is the same path for an already-subscribed user, and
also schedules an immediate `welcome_{id}` brief.

### 5.2 Daily brief (`run_brief`) — [core/jobs.py](core/jobs.py)

```
1. get_user_by_id(id)                       — load creds from DB
2. TokenManager.for_user(user)              — isolated session; captures rotations into tm.token
3. fetch_active_projects_direct(…tm…)       — GET /api/projects (token rotates)
   └─ tm.persist(user)                      — save rotated token if it changed
   └─ if 401/419 → TokenExpiredError        — pause briefs, send re-auth, mark invalid
4. build_brief_direct(…session=tm.session)  — fetch tasks + feedback per project
   └─ tm.persist(user)                      — save the freshest token again
5. render_html()                            — build the email (core/brief/renderer.py)
6. send_brief_to()                          — Resend (core/mailer.py)
```

### 5.3 Live snapshot for the extension — `POST /api/snapshot`

Powers the calendar strip. Prefers the **DB token** over the extension-supplied
one (DB is authoritative). On token rejection, returns `last_snapshot` with
`is_stale: true` instead of failing — so the strip always shows something.

---

## 6. Data Pipeline (OnTrack → email)

```
ontrack/fetcher.py        brief/builder.py           brief/renderer.py
──────────────────        ────────────────           ─────────────────
fetch_active_projects ──▶ build_brief_direct ──────▶ render_html
fetch_tasks               • categorise by status      • HTML email
fetch_last_feedback         (URGENT/TODO/WAITING/        (core/brief/renderer.py)
                             SUBMITTED/DONE)
                          • _score() sort per section
                          • returns {urgent, todo,
                            waiting, submitted, done}
```

Status categories live in [core/constants.py](core/constants.py)
(`URGENT`, `TODO`, `WAITING`, `SUBMITTED`, `DONE`). Note `ontrack/fetcher.py`
has two parallel API surfaces: `*_direct()` (used by the web app, explicit creds)
and the CLI-based variants (`fetch_tasks`, `fetch_last_feedback`) used by the
older `build_brief()` path.

---

## 7. Key Design Decisions & Gotchas

| Decision | Why |
|----------|-----|
| Token read from **response** headers, not request | Doubtfire rotates per response; request headers are already stale |
| **Per-run** `TokenManager` (a session each) | Prevents concurrent briefs from clobbering each other's tokens |
| `email` is the unique key, not `username` | A user re-subscribing with a new token shouldn't duplicate |
| Expired token → **pause**, don't delete | Auto-resumes when extension pushes a fresh token |
| `last_snapshot` cached in DB | Extension stays useful even when token is dead |
| Job store in the DB (not memory) | Schedules survive restarts/deploys |
| 3-script extension chain | Page-context capture + `chrome.*` access + HTTPS→HTTP bridge |
| Same SQL with `_P` placeholder | One codebase for PostgreSQL and SQLite |

---

## 8. File Map

```
app.py                      Flask app factory + startup()
extensions.py               Limiter + APScheduler (DB-backed job store)
routes/
  main.py                   /register /setup /refresh-token /api/snapshot /unsubscribe
core/
  db.py                     users table, PG/SQLite, upsert/get/remove
  jobs.py                   run_brief, refresh_all_tokens, schedule_brief, startup
  mailer.py                 Resend send (brief + re-auth)
  constants.py              status sets, grade/colour lookup tables (cross-cutting)
  ontrack/                  OnTrack integration (rotating-token auth + data)
    __init__.py             re-exports the public API
    auth.py                 TokenManager: validate / capture / persist the token
    fetcher.py              OnTrack API calls (consumes auth)
  brief/                    turn OnTrack data into the email
    __init__.py             re-exports build_brief(_direct), render_html
    builder.py              categorise + prioritise tasks → brief dict
    renderer.py             brief dict → HTML email
templates/
  unsubscribed.html         post-unsubscribe page
extension/
  public/
    manifest.json           MV3 manifest
    injected.js             page-context token interceptor
    content.js              inject + store + forward
    background.js           POST /refresh-token (service worker, native fetch)
  src/
    main.jsx                React entry
    App.jsx                 view routing, storage, subscribe/unsubscribe
    constants.js            SNAPSHOT_KEY, TTL, default base URL
    lib/
      api.js                fetch wrapper (base URL, JSON, timeout, errors)
    utils/
      time.js               syncLabel (relative-time formatting)
    components/             SignupFlow, Settings, CalendarStrip, TaskList, …
    styles/
      popup.css             styling
```
