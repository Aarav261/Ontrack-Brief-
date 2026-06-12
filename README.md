<div align="center">

<img src="assets/logo.png" alt="OnTrack(er)" width="120" />

# OnTrack(er)

**Your OnTrack week, sorted before you wake up.**

A weekday morning brief that ranks your [OnTrack](https://github.com/doubtfire-lms/doubtfire-web) tasks by urgency and grade target — links and tutor feedback included — and emails it to you. Even with your laptop closed.

<br/>

![Chrome Extension](https://img.shields.io/badge/Chrome-Extension-4361ee?style=flat-square&logo=googlechrome&logoColor=white)
![Backend](https://img.shields.io/badge/Backend-Flask-000000?style=flat-square&logo=flask&logoColor=white)
![Auth](https://img.shields.io/badge/Auth-Clerk-6c47ff?style=flat-square)
![Email](https://img.shields.io/badge/Email-Resend-000000?style=flat-square)

</div>

---

## What it does

Every weekday morning, OnTrack(er) fetches your active OnTrack projects and emails a brief organised into sections — ordered by urgency (red ≤ 3 days first), then by grade target (HD → P) within each group. Urgent and discuss tasks include the latest tutor comment inline.

| Section | Tasks included |
|---|---|
| **Needs Attention** | Overdue, redo, fix & resubmit, need help |
| **Upcoming** | Not started, in progress |
| **Discuss with Tutor** | Discuss, demonstrate |
| **Submitted** | Waiting on tutor feedback |
| **Recently Completed** | Finished within the last 7 days |

The companion Chrome extension shows the same tasks live in a popup and keeps your OnTrack session fresh in the background.

---

## Install the extension

### Option A — Download & load unpacked (no build needed)

1. **Download** the latest `ontrack-brief-extension.zip` from the **[Releases page »](https://github.com/Aarav261/Ontracker/releases/latest)**
2. **Unzip** it — you'll get a folder named `ontrack-brief-extension`.
3. Open **`chrome://extensions`** in Chrome.
4. Toggle **Developer mode** on (top-right).
5. Click **Load unpacked** and select the unzipped **`ontrack-brief-extension`** folder.
6. The OnTrack(er) icon appears in your toolbar. Click it and **sign in at [on-tracker.com](https://on-tracker.com)**.
7. Open OnTrack once so the extension can link your account — your tasks then load in the popup, and your daily brief is scheduled.

> **Updating:** download the new zip, then on `chrome://extensions` click the **reload ↻** on the OnTrack(er) card (or remove and re-add the folder).

### Option B — Build from source

```bash
git clone https://github.com/Aarav261/Ontracker.git
cd Ontracker/extension
npm install
npm run build:prod        # production build -> extension/dist
python ../scripts/package_extension.py   # optional: zip it for sharing
```

Then load `extension/dist` via **Load unpacked** (steps 3–7 above). Use `npm run build` instead of `build:prod` for a local-dev build pointed at `localhost`.

---

## How it works

**The hard problem:** OnTrack rotates its auth token on *every* API response, so the server can't store one token and reuse it on a schedule. The extension continuously captures the freshest token from your browser and pushes it to the backend, which keeps your brief running while you're away.

- **Identity** is handled by **Clerk** — you sign in once on the web app, and the extension picks up that session (via Clerk's sync host). Your brief is sent to your verified account email.
- **OnTrack access** is a separate, encrypted token linked to your Clerk account — captured automatically by the extension, never copy-pasted.
- If your OnTrack session truly expires (you clicked **Log Out** in OnTrack), briefs pause and you get a single re-auth notice. Reopen OnTrack and everything resumes automatically.

> **Tip:** you don't need to stay logged into OnTrack — just don't click *Log Out*. Closing the tab is fine.

---

## Local development

The backend + Postgres run via Docker; the web app and extension via Vite.

```bash
# Backend + database (reads .env.dev)
docker compose up -d --build

# Web app (Clerk sign-in host)  →  http://localhost:5173
cd web && npm install && npm run dev

# Extension (dev build)  →  load extension/dist unpacked
cd extension && npm install && npm run build
```

Secrets live in `.env.dev` (gitignored). See [`.env.example`](.env.example) for the full list (Clerk keys, Resend, `DATABASE_URL`, `TOKEN_ENCRYPTION_KEY`).

---

## Project layout

```
app.py            Flask app factory + startup
extensions.py     APScheduler (DB-backed) + rate limiter
routes/main.py    /link-ontrack, /api/snapshot, /refresh-token, /unsubscribe, webhooks
core/
  clerk_auth.py   Clerk session-JWT verification (JWKS)
  db.py           users table — Postgres (prod) / SQLite (dev)
  jobs.py         run_brief, refresh_all_tokens, scheduling
  mailer.py       Resend email delivery
  crypto.py       OnTrack token encryption at rest
  ontrack/        rotating-token auth + OnTrack API
  brief/          categorise + prioritise tasks → HTML email
web/              Vite + React landing / Clerk sign-in host (on-tracker.com)
extension/        MV3 Chrome extension (React popup + token-capture scripts)
scripts/          packaging + maintenance helpers
```

## Tech stack

**Backend** Flask · APScheduler · PostgreSQL · PyJWT  ·  **Auth** Clerk  ·  **Email** Resend  ·  **Frontend** React + Vite (web app + MV3 extension)  ·  **Hosting** Railway

---

## License

© 2026 Aarav. **All rights reserved.** This source is published for reference and
portfolio purposes only — it is **not** open source. You may view it, but you may
not use, copy, deploy, modify, or distribute it without written permission. See
[`LICENSE`](LICENSE) for the full terms.
