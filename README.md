# OnTracker

A daily prioritised task brief for [OnTrack](https://github.com/doubtfire-lms/doubtfire-web) students. Fetches your active units, scores each task by urgency and grade target, and delivers a formatted HTML email every weekday morning.

Task names in the email are linked directly to that task's page in OnTrack.

## What it does

Every weekday morning it fetches your active OnTrack projects and emails you a brief broken into sections:

| Section | Tasks included |
|---|---|
| 🚨 Needs Attention | Overdue, redo, fix & resubmit, need help |
| 🎯 Upcoming Tasks | Not started, in progress |
| 💬 Discuss with Tutor | Discuss, demonstrate |
| 📬 Submitted | Waiting on tutor feedback |
| ✅ Recently Completed | Finished within the last N days |

Urgent and "discuss" tasks show the latest tutor comment inline.

## Two modes

### Web app (recommended)

`app.py` is a Flask web server that handles setup via a bookmarklet and schedules daily briefs for multiple users using APScheduler. No CLI dependency needed.

1. Run the server: `python app.py`
2. Open `http://localhost:5001` in your browser
3. Drag the bookmarklet to your bookmarks bar
4. Log into OnTrack and click the bookmarklet — it calls OnTrack's `/api/auth/access-token` endpoint and redirects back with your token pre-filled
5. Enter your email address and preferred send time, then click Subscribe
6. A brief is sent immediately and then every weekday at the chosen hour

User credentials are stored in `ontracker.db` (SQLite). The scheduler restores all jobs on restart.

To unsubscribe, click the unsubscribe link in any brief email, or visit `/unsubscribe/<your-email>`.

### CLI

`brief.py` is a standalone script for local use. It requires the `ontrack-cli` tool to be installed and authenticated.

```bash
# Open brief in browser (no email)
python brief.py --preview

# Send brief via email
python brief.py

# Install weekday cron job at 8:00 AM
python brief.py --schedule

# Install at a custom hour (e.g. 7:30 AM)
python brief.py --schedule --hour 7
```

The `--schedule` flag writes a cron entry that runs the script on weekdays at the chosen hour. Logs go to `brief.log`.

To remove the cron job:
```bash
crontab -e   # delete the line containing "ontrack-morning-brief"
```

## Project structure

```
app.py             # Flask web app — bookmarklet setup + APScheduler
brief.py           # CLI entry point
builder.py         # Priority scoring and brief assembly (CLI + direct API variants)
constants.py       # Grade/status lookup tables and task-status sets
db.py              # SQLite persistence for web app users
fetcher.py         # OnTrack API calls — both CLI subprocess and direct HTTP
mailer.py          # SMTP email delivery
renderer.py        # HTML rendering (email-safe table layout)
scheduler.py       # Cron job installation (CLI mode only)
templates/
  index.html       # Setup page with bookmarklet and subscription form
  success.html     # Post-setup confirmation
  unsubscribed.html
config.ini         # Your credentials — never committed (see .gitignore)
config.ini.template
```

## Requirements

- Python 3.10+
- `pip install flask apscheduler requests`

For **CLI mode** only:
- [`ontrack-cli`](https://github.com/doubtfire-lms/ontrack-cli) installed and authenticated (`ontrack login`)

For **email delivery** in either mode:
- A Gmail account with [App Passwords](https://myaccount.google.com/apppasswords) enabled

## Setup

**1. Clone and install dependencies**

```bash
git clone https://github.com/yourusername/ontracker.git
cd ontracker
pip install flask apscheduler requests
```

**2. Configure email credentials**

```bash
cp config.ini.template config.ini
```

Edit `config.ini` with your Gmail address and App Password.

**3a. Web app**

```bash
python app.py
```

Open `http://localhost:5001`, follow the on-screen steps.

**3b. CLI**

```bash
ontrack login          # authenticate ontrack-cli
python brief.py --preview   # verify it works
```

## Configuration reference

`config.ini` supports these keys:

```ini
[email]
sender       = you@gmail.com
recipient    = you@gmail.com
app_password = xxxx xxxx xxxx xxxx

[brief]
recently_completed_days = 7   # days to show in "Recently Completed"
max_todo_tasks = 10           # cap on "Upcoming Tasks" rows (CLI mode)
```
