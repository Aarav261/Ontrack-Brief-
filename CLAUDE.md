# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this project is

**OnTrack(er)** sends students a prioritized weekday morning email brief of their [OnTrack](https://github.com/doubtfire-lms/doubtfire-web) (Deakin LMS) tasks, ranked by urgency and grade target. A MV3 Chrome extension provides a live popup view and keeps the OnTrack session alive in the background.

**Stack:** Flask + APScheduler + PostgreSQL (prod) / SQLite (dev) · Clerk (identity) · Resend (email) · React 18 + Vite (web app + extension) · Docker + Railway (hosting)

---

## Commands

### Backend
```bash
# Start backend + Postgres (reads .env.dev)
docker compose up -d --build

# Python linting (ruff)
ruff check .
ruff format .
```

### Web app (`web/`)
```bash
npm install
npm run dev       # Vite dev server → http://localhost:5173
npm run build     # Production build
```

### Extension (`extension/`)
```bash
npm install
npm run build           # Dev build → extension/dist/ (points to localhost)
npm run build:local     # Dev build → extension/dist-local/ (separate instance, no key collision)
npm run build:prod      # Prod build → extension/dist/ (points to on-tracker.com)
npm run lint            # ESLint
```

Load `extension/dist` via **chrome://extensions → Load unpacked** for local development.

### Scripts
```bash
python scripts/test_send_now.py      # Send a brief immediately (dev testing)
python scripts/package_extension.py  # Zip extension/dist for distribution
```

---

## Architecture

### The core problem: rotating OnTrack tokens

OnTrack rotates its auth token on every API response. The extension continuously captures the freshest token from the browser and pushes it to the backend. Briefs are generated from a DB snapshot (not live API calls), so they never race against token rotation.

### Data flow

1. **Extension → Backend (`/ingest`):** As the student navigates OnTrack, the content/background scripts capture projects, tasks, and feedback and push them to the server's DB tables (`projects`, `tasks`, `feedback`).
2. **Extension → Backend (`/refresh-token`, `/refresh-credential`):** The rotating `auth_token` and durable `refresh_token` cookie are pushed and stored encrypted.
3. **APScheduler (`core/jobs.py`):** Mon–Fri at the user's preferred hour (Melbourne TZ), `run_brief(user_id)` reads stored tasks, filters/prioritises, renders HTML, sends via Resend. No live OnTrack API call during send — fully deterministic from DB.
4. **Extension popup (`/api/snapshot`):** On popup open, the backend mints a fresh `auth_token` from the stored `refresh_token`, fetches live task data, and returns a snapshot. The popup caches this in `chrome.storage.local` (TTL-gated).

### Auth layers (two separate systems)

- **Identity (Clerk):** Web and extension sign-in. Session JWT verified server-side by `@require_clerk_auth` in `core/clerk_auth.py` via JWKS. Claims provide `clerk_user_id` and `email`.
- **OnTrack credentials:** Separate rotating token linked to the Clerk user. Stored encrypted at rest (`core/crypto.py`, Fernet, `enc:v1:` prefix). The extension captures these; users never copy-paste tokens.

### Backend structure

| File | Role |
|------|------|
| `app.py` | Flask app factory, registers blueprint, runs startup jobs |
| `extensions.py` | APScheduler (DB-backed jobstore) + Flask-Limiter |
| `routes/main.py` | All HTTP endpoints (register, setup, link-ontrack, snapshot, ingest, unsubscribe, webhooks) |
| `core/db.py` | All DB access — users, projects, tasks, feedback tables; SQLAlchemy + psycopg2; PG/SQLite abstraction |
| `core/clerk_auth.py` | `@require_clerk_auth` decorator — JWKS verification |
| `core/ontrack/auth.py` | `TokenManager` — mints auth_token from refresh_token, handles rotation/expiry |
| `core/ontrack/fetcher.py` | OnTrack API client (projects, tasks, feedback) |
| `core/brief/builder.py` | Task filtering and prioritisation into sections |
| `core/brief/renderer.py` | HTML email rendering |
| `core/jobs.py` | `run_brief()`, `schedule_brief()`, startup routines |
| `core/mailer.py` | Resend email delivery + issue reporting |
| `core/crypto.py` | Fernet encryption/decryption; auto-migrates legacy plaintext rows |
| `core/constants.py` | Grade/status lookup tables and priority weights |

### Brief sections and priority

Tasks are sorted: overdue/red (≤3 days) first, then by grade target (HD → P), then by deadline.

| Section | Statuses included |
|---------|------------------|
| Needs Attention | overdue, redo, fix & resubmit, need help |
| Upcoming | not started, in progress |
| Discuss with Tutor | discuss, demonstrate (+ latest feedback) |
| Submitted | waiting on tutor feedback |
| Recently Completed | finished within last N days (default 7, user-configurable) |

### Extension structure

- `public/background.js` — MV3 service worker: token capture lifecycle, scheduler
- `public/content.js` — Content script on `ontrack.deakin.edu.au`
- `public/injected.js` — Page-context injection for auth cookie extraction
- `public/config.js` — Injected at build time with `APP_URL`
- `src/App.jsx` — Popup state machine: loading → signed-out / no-ontrack / snapshot view
- `src/api.js` — Fetch wrapper attaching Clerk JWT to all requests

### Extension build modes

`extension/vite.config.js` loads different `.env.*` files per mode:
- `npm run build` → `.env.dev` → `dist/` (localhost backend)
- `npm run build:local` → `.env.dev` → `dist-local/` (separate Chrome extension instance, avoids manifest key collision with a prod-installed extension)
- `npm run build:prod` → `.env.prod` → `dist/` (production, `on-tracker.com`)

---

## Environment variables

Secrets live in `.env.dev` (gitignored). See `.env.example` for the full list.

| Variable | Required | Notes |
|----------|----------|-------|
| `SECRET_KEY` | Yes | Flask secret |
| `DATABASE_URL` | No | Postgres URL; defaults to SQLite `ontracker.db` |
| `RESEND_API_KEY` | Yes | Email delivery |
| `RESEND_FROM_EMAIL` | Yes | Verified Resend sender address |
| `TOKEN_ENCRYPTION_KEY` | Yes (prod) | Fernet key for at-rest token encryption |
| `PORT` | No | Default 8000 (Docker) / 5001 (local) |
| `RESEND_DRY_RUN` | No | `"true"` to log emails instead of sending |
| `MIN_EXTENSION_VERSION` | No | Triggers update prompt (default `1.9`) |

Web/extension also need `VITE_CLERK_PUBLISHABLE_KEY` and `VITE_API_BASE` set in their respective `.env.*` files.

---

## Deployment

- **Backend:** Dockerfile — Python 3.11-slim, Gunicorn 1 worker + 8 gthread threads
- **APScheduler** uses a DB-backed jobstore (not memory), so jobs survive restarts
- **Rate limiting:** Flask-Limiter; uses Redis if `REDIS_URL` is set, otherwise in-memory
- **Hosting:** Railway (backend + DB) + separate deploy for web app
