# OnTrack Morning Brief

A weekday email brief for [OnTrack](https://github.com/doubtfire-lms/doubtfire-web) students that prioritises tasks by urgency and grade target, then delivers a clean, link-rich HTML summary each morning—even when your laptop is closed.

Each task title links directly to its corresponding OnTrack page.

## What it does

Every weekday morning, the app fetches your active OnTrack projects and emails a brief organised into sections:

| Section | Tasks included |
|---|---|
| 🚨 Needs Attention | Overdue, redo, fix & resubmit, need help |
| 🎯 Upcoming Tasks | Not started, in progress |
| 💬 Discuss with Tutor | Discuss, demonstrate |
| 📬 Submitted | Waiting on tutor feedback |
| ✅ Recently Completed | Finished within the last 7 days |

Tasks are ordered by urgency (red ≤ 3 days first), then by grade target (HD → P) within each group. Urgent and discuss tasks include the latest tutor comment inline.

## How authentication works

OnTrack tokens are long-lived and survive browser restarts, sleep, or device changes. A token only expires if you explicitly click **Log Out** in OnTrack.

> **Tip:** Once subscribed, you don't need to stay logged in. Just don't click Log Out — closing the tab is fine.

If a token does expire, the app emails a re-authentication link and pauses briefs until you re-subscribe.

## Quick start

**1. Clone and install dependencies**

```bash
git clone https://github.com/Aarav261/Ontrack-Brief-.git
cd Ontrack-Brief-
pip install -r requirements.txt
```

**2. Configure email credentials**

```bash
cp config.ini.template config.ini
```

Edit `config.ini` with your Gmail address and an [App Password](https://myaccount.google.com/apppasswords).

**3. Run the web app**

```bash
python app.py
```

Open `http://localhost:5001`, drag the bookmarklet to your bookmarks bar, then log into OnTrack and click it. Your token is captured automatically and you are redirected back to the setup form.

Enter your email and preferred send hour, then select **Subscribe**. A brief is sent within 10 seconds to confirm everything works.

## Project structure

```
app.py             # Flask app: bookmarklet setup + APScheduler
builder.py         # Priority scoring and brief assembly
constants.py       # Grade/status lookups and task-status sets
db.py              # SQLite persistence for subscribers
fetcher.py         # OnTrack API calls + TokenExpiredError handling
mailer.py          # SMTP email delivery + re-auth notification
renderer.py        # HTML rendering (email-safe table layout)
templates/
  index.html       # Setup page with bookmarklet and subscription form
  success.html     # Post-setup confirmation
  unsubscribed.html
test_send_now.py   # Send a brief immediately (no scheduler)
test_schedule.py   # Fire two briefs 10s apart via APScheduler
config.ini         # Your credentials — never committed (see .gitignore)
config.ini.template
```

## Requirements

- Python 3.10+
- `pip install -r requirements.txt`
- A Gmail account with [App Passwords](https://myaccount.google.com/apppasswords) enabled

## Configuration reference

`config.ini`:

```ini
[email]
sender       = you@gmail.com
recipient    = you@gmail.com
app_password = xxxx xxxx xxxx xxxx
```

## Unsubscribe

Click the unsubscribe link in any brief email, or visit:

```
http://localhost:5001/unsubscribe/<your-email>
```
