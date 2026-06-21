import logging
from datetime import date, timedelta
from zoneinfo import ZoneInfo

from apscheduler.jobstores.base import JobLookupError
from apscheduler.triggers.cron import CronTrigger

from core.brief import pending_task_entries, render_html
from core.db import (
    get_all_users,
    get_capture_meta,
    get_pending_tasks,
    get_user_by_id,
    init_db,
)
from core.mailer import send_brief_to, send_briefs_enabled_email
from extensions import scheduler

log = logging.getLogger(__name__)
# brief_hour is the user's intended *local* hour. OnTrack is Deakin, so briefs
# run on Melbourne time (DST-aware) — without this the container's UTC clock
# would fire an "8am" brief at 6pm Melbourne. (tzdata is pinned in requirements
# so the zone resolves on the slim Docker image.)
_BRIEF_TZ = ZoneInfo("Australia/Melbourne")
_DEFAULT_WINDOW_DAYS = 14
_THIS_WEEK_DAYS = 6


def run_brief(user_id: int, *, confirm_if_empty: bool = False) -> None:
    """Build and email a user's brief from captured OnTrack data — no OnTrack call.

    Deterministic: the brief is a pure function of the stored tasks and today's
    date. The extension captures tasks/deadlines/status off the student's own
    OnTrack session and pushes them to /ingest; here we just read, filter to the
    user's window, and send. There is no token, mint, or re-auth path — an expired
    token simply means the student isn't on OnTrack, which means nothing changed.

    ``confirm_if_empty`` is set only by an explicit "Enable email briefs" action:
    when there's nothing to show, send a one-off confirmation instead of returning
    silently, so the deliberate click gets feedback. The daily cron leaves it False.
    """
    user = get_user_by_id(user_id)
    if not user:
        log.error("run_brief: no user found for id=%s", user_id)
        return
    if not user.get("subscribed", 1):
        # Defensive: a paused user should have no scheduled job, but never email
        # someone who has unsubscribed even if a stale job somehow fires.
        log.info("run_brief: %s is unsubscribed — skipping", user["email"])
        return

    email = user["email"]
    window_days = user.get("brief_days") or _DEFAULT_WINDOW_DAYS
    today = date.today()
    end = today + timedelta(days=window_days)

    task_count, last_seen = get_capture_meta(user_id)
    if task_count == 0:
        # Cold start: nothing captured yet (the student hasn't opened OnTrack with
        # the extension since subscribing). Don't send an empty brief every day —
        # confirm the deliberate enable click, otherwise stay quiet until data lands.
        if confirm_if_empty:
            log.info("No captured tasks for %s yet — sending briefs-enabled confirmation", email)
            send_briefs_enabled_email(email)
        else:
            log.info("run_brief: no captured tasks for %s yet — skipping", email)
        return

    rows = get_pending_tasks(user_id, today.isoformat(), end.isoformat())
    entries = pending_task_entries(rows, today, user["base_url"])
    due_this_week = sum(1 for e in entries if (e["due"] - today).days <= _THIS_WEEK_DAYS)

    # The user has captured data, so send the brief even when nothing is due in the
    # window — render_html shows the "nothing due" state, same as before.
    html = render_html(entries, today, window_days=window_days, as_of=last_seen)
    send_brief_to(html, email, today, due_this_week)


# The 20-min token-refresh poll has been retired. run_brief now mints a fresh
# auth_token on demand (mint_auth_token), so there's no need to chase the rotating
# token every 20 minutes — and the poll's strike logic was wrongly marking stale
# rotating tokens invalid and *removing the brief jobs*, silently stopping briefs.
def refresh_all_tokens() -> None:
    """Retired no-op. Kept as a resolvable reference so a `token_refresh` job
    pickled into the persistent jobstore by an older deploy loads without error
    and unschedules itself, instead of raising on an unresolvable function."""
    try:
        scheduler.remove_job("token_refresh")
        log.info("Retired token_refresh poll fired — removed it from the jobstore")
    except JobLookupError:
        pass


def _remove_retired_jobs() -> None:
    """Drop retired poll jobs left in the persistent jobstore by older deploys."""
    for job_id in ("token_refresh", "token_refresh_startup"):
        try:
            scheduler.remove_job(job_id)
            log.info("Removed retired job %s from the jobstore", job_id)
        except JobLookupError:
            pass


def schedule_brief(user_id: int, brief_hour: int) -> None:
    job_id = f"brief_{user_id}"
    trigger = CronTrigger(
        day_of_week="mon-fri", hour=brief_hour, minute=0, timezone=_BRIEF_TZ
    )
    if scheduler.get_job(job_id):
        scheduler.reschedule_job(job_id, trigger=trigger)
    else:
        scheduler.add_job(
            run_brief,
            trigger,
            args=[user_id],
            id=job_id,
            misfire_grace_time=3600,
            replace_existing=True,
        )


def startup() -> None:
    try:
        init_db()
    except Exception as exc:
        log.error("Database initialisation failed: %s", exc, exc_info=True)
        return

    try:
        for user in get_all_users():
            if not user.get("subscribed", 1):
                log.info("Skipping schedule for %s — unsubscribed (paused)", user["username"])
                continue
            schedule_brief(user["id"], user["brief_hour"])
    except Exception as exc:
        log.error("Failed to restore scheduled jobs: %s", exc, exc_info=True)

    scheduler.start()

    # Evict the retired 20-min token-refresh poll if an older deploy persisted it.
    _remove_retired_jobs()
