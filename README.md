# OnTrack Morning Brief

A daily prioritised task brief for [OnTrack](https://github.com/doubtfire-lms/doubtfire-web) students. Fetches your active units, scores each task by urgency and grade target, and delivers a formatted HTML email every weekday morning — even when your laptop is closed.

Task names in the email link directly to that task's page in OnTrack.

## What it does

Every weekday morning it fetches your active OnTrack projects and emails you a brief broken into sections:

| Section | Tasks included |
|---|---|
| 🚨 Needs Attention | Overdue, redo, fix & resubmit, need help |
| 🎯 Upcoming Tasks | Not started, in progress |
| 💬 Discuss with Tutor | Discuss, demonstrate |
| 📬 Submitted | Waiting on tutor feedback |
| ✅ Recently Completed | Finished within the last 7 days |

Tasks are sorted by urgency: red (≤3 days) floats to the top, then sorted by grade target HD → P within each group. Urgent and discuss tasks show the latest tutor comment inline.

## How authentication works

OnTrack tokens are long-lived — they survive closing the browser, sleeping your laptop, or switching devices. The only way a token dies is if you explicitly click **Log Out** on OnTrack.

> **Tip:** Once subscribed, you don't need to stay logged in. Just don't click Log Out — closing the tab is fine.

If your token does expire, the app emails you a re-authentication link and pauses your briefs until you re-subscribe.

## Quick start

**1. Clone and install dependencies**

```bash
git clone https://github.com/Aarav261/Ontrack-Brief-.git
cd Ontrack-Brief-
pip install flask apscheduler requests
```

**2. Configure email credentials**

```bash
cp config.ini.template config.ini
```

Edit `config.ini` with your Gmail address and [App Password](https://myaccount.google.com/apppasswords).

**3. Run the web app**

```bash
python app.py
```

Open `http://localhost:5001`, drag the bookmarklet to your bookmarks bar, then log into OnTrack and click it. Your token is captured automatically and you're redirected back to the setup form.

Enter your email and preferred send hour → Subscribe. A brief is sent within 10 seconds to confirm everything works.

## Project structure

```
app.py             # Flask web app — bookmarklet setup + APScheduler
builder.py         # Priority scoring and brief assembly
constants.py       # Grade/status lookup tables and task-status sets
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
- `pip install flask apscheduler requests`
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
