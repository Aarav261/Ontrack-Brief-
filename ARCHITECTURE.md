# OnTrack Brief — Architecture

```mermaid
flowchart TD

  subgraph Browser["Browser (OnTrack Tab)"]
    OT["OnTrack Angular App\nontrack.deakin.edu.au"]
    INJ["injected.js\nIntercepts XHR & fetch\nrequest headers"]
    CONT["content.js\nListens for captured token\nStores to chrome.storage"]
    OT -- "API requests with\nAuth-Token header" --> INJ
    INJ -- "ontrack-auth-captured\nevent" --> CONT
  end

  subgraph Extension["Chrome Extension"]
    STORAGE["chrome.storage.local\nauth_token\nusername\nbase_url"]
    POPUP["popup.js + popup.html\nSubscription UI"]
    BG["background.js\nService worker (minimal)"]
    CONT -- "set auth_token,\nusername, base_url" --> STORAGE
    STORAGE -- "read on open" --> POPUP
  end

  subgraph FlaskApp["Flask Web App (app.py)"]
    SETUP["/setup POST\nValidate token\nCreate user\nSchedule job"]
    REFRESH["/refresh-token POST\nUpdate token in DB\n+ job args"]
    UNSUB["/unsubscribe GET\nRemove user + job"]
    INDEX["/ GET\nSetup page +\nbookmarklet"]

    subgraph Scheduler["APScheduler (Background)"]
      BRIEF_JOB["brief_<id>\nWeekday cron\nat brief_hour"]
      TOKEN_JOB["token_refresh\nEvery 20 minutes"]
    end
  end

  subgraph PythonModules["Python Modules"]
    FETCHER["fetcher.py\nOnTrack API calls\nToken capture hook"]
    BUILDER["builder.py\nTask categorisation\n& scoring"]
    RENDERER["renderer.py\nHTML email builder\nCalendar deeplinks"]
    MAILER["mailer.py\nGmail SMTP"]
    DB["db.py\nSQLite helpers"]
  end

  subgraph Data["Persistence"]
    SQLITE[("ontracker.db\nusers table\nbase_url · username\nauth_token · email\nbrief_hour")]
  end

  subgraph External["External Services"]
    ONTRACK["OnTrack API\nDoubtfire\n/api/projects\n/api/units\n/api/unit_roles"]
    GMAIL["Gmail SMTP\nsmtp.gmail.com:465"]
    GCAL["Google Calendar\nDeeplink URLs\n(no OAuth)"]
  end

  %% Extension → App
  CONT -- "POST /refresh-token\n{auth_token, username}" --> REFRESH
  POPUP -- "POST /setup\n{base_url, username,\nauth_token, email, hour}" --> SETUP

  %% App → DB
  SETUP --> DB
  REFRESH --> DB
  UNSUB --> DB
  DB <--> SQLITE

  %% App → Scheduler
  SETUP -- "schedule brief_<id>\n+ token_refresh job" --> Scheduler
  REFRESH -- "update job args\nauth_token[1]" --> BRIEF_JOB

  %% Scheduler → Modules
  BRIEF_JOB -- "_run_brief()" --> FETCHER
  TOKEN_JOB -- "_refresh_all_tokens()\nvalidate_token()" --> FETCHER

  %% Module chain
  FETCHER -- "projects + tasks" --> BUILDER
  BUILDER -- "brief dict" --> RENDERER
  RENDERER -- "HTML email" --> MAILER
  FETCHER -- "token capture hook\nget_last_seen_token()" --> DB

  %% External calls
  FETCHER <-- "Auth-Token rotation\non every response" --> ONTRACK
  MAILER --> GMAIL
  RENDERER -- "&#128197; per red task\nin email HTML" --> GCAL

  %% Token refresh loop
  TOKEN_JOB -- "update DB +\nbrief job args" --> DB

  %% Email delivery
  GMAIL -- "Daily brief email\nwith calendar links" --> USER["User Inbox"]
  GCAL -- "One-click event\ncreation" --> USER
```

## Component Responsibilities

| Component | File | Role |
|---|---|---|
| `injected.js` | `extension/injected.js` | Runs inside OnTrack page context; patches XHR/fetch to capture `Auth-Token` from outgoing request headers |
| `content.js` | `extension/content.js` | Bridge between page and extension; stores token in `chrome.storage`, pushes to `/refresh-token` |
| `popup.js` | `extension/popup.js` | Subscription UI; reads stored credentials and POSTs to `/setup` |
| `background.js` | `extension/background.js` | Minimal service worker; keeps extension registered |
| Flask routes | `app.py` | `/setup`, `/refresh-token`, `/unsubscribe`, `/` |
| APScheduler | `app.py` | `brief_<id>` (weekday cron) + `token_refresh` (every 20 min) |
| `fetcher.py` | `fetcher.py` | All OnTrack API calls; response hook captures latest rotated token via `get_last_seen_token()` |
| `builder.py` | `builder.py` | Categorises tasks into urgent/todo/waiting/submitted/done; scores by red band → grade → deadline |
| `renderer.py` | `renderer.py` | Builds HTML email; inlines Google Calendar deeplinks on red tasks (≤3 days) |
| `mailer.py` | `mailer.py` | Sends via Gmail SMTP (port 465 SSL) |
| `db.py` | `db.py` | SQLite CRUD for the `users` table |

## Token Rotation Flow

```
User logs in to OnTrack
        │
        ▼
injected.js captures Auth-Token from request headers
        │
        ├──► chrome.storage.local (popup reads this)
        │
        └──► POST /refresh-token ──► DB + brief job args updated
                                              │
                          ┌───────────────────┤
                          │  Every 20 minutes │
                          ▼                   │
              validate_token() ──► OnTrack    │
              (rotated token saved to DB      │
               + brief job args updated) ─────┘
                          │
                          ▼
              _run_brief() at scheduled hour
              fetch_active_projects() ──► OnTrack (rotates token)
              build_brief() ──► multiple API calls (each rotates token)
              get_last_seen_token() ──► save final token to DB + job args
```
