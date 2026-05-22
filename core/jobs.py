import logging
import os
from datetime import date, datetime, timedelta

from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.date import DateTrigger

from core.brief import build_brief_direct, pending_due_entries, render_html
from core.db import get_all_users, get_user_by_id, init_db, mark_token_invalid
from core.mailer import send_brief_to, send_reauth_email
from core.ontrack import TokenManager, TokenExpiredError, fetch_active_projects_direct
from extensions import scheduler

log = logging.getLogger(__name__)
APP_URL = os.environ.get("APP_URL", "http://localhost:8000/")
_PENDING_WINDOW_DAYS = 14
_THIS_WEEK_DAYS = 6

def run_brief(user_id: int) -> None:
    user = get_user_by_id(user_id)
    if not user:
        log.error("run_brief: no user found for id=%s", user_id)
        return
    email = user["email"]
    recently_completed_days = user.get("recently_completed_days", 7)

    # One TokenManager (and its isolated session) per brief run — its response
    # hook captures every token rotation into tm.token, so concurrent jobs never
    # clobber each other's tokens. tm.persist() writes the freshest token back.
    tm = TokenManager.for_user(user)

    try:
        projects, tm.token = fetch_active_projects_direct(
            tm.base_url, tm.token, tm.username, session=tm.session)
        tm.persist(user)  # save the token rotated by the projects call
        if not projects:
            return
        brief = build_brief_direct(tm.base_url, tm.token, tm.username, projects,
                                   recently_completed_days=recently_completed_days,
                                   session=tm.session)
        tm.persist(user)  # save the freshest token seen across the task calls
        today = date.today()
        pending_due = pending_due_entries(brief, today, _PENDING_WINDOW_DAYS)
        due_this_week = len(pending_due_entries(brief, today, _THIS_WEEK_DAYS))
        html = render_html(pending_due, today, window_days=_PENDING_WINDOW_DAYS)
        send_brief_to(html, email, today, due_this_week)
    except TokenExpiredError:
        log.warning("Token expired for %s — pausing briefs, waiting for extension to push fresh token", email)
        if scheduler.get_job(f"brief_{user_id}"):
            scheduler.remove_job(f"brief_{user_id}")
        mark_token_invalid(email)
        send_reauth_email(email, APP_URL)
    except Exception as exc:
        log.error("Brief generation failed for %s: %s", email, exc, exc_info=True)


def refresh_all_tokens() -> None:
    """Single consolidated job — reads fresh from DB every 20 min for all users."""
    for user in get_all_users():
        tm = TokenManager.for_user(user)
        try:
            valid = tm.validate()
        except Exception as exc:
            log.warning("OnTrack unreachable for %s (service may be down): %s", user["username"], exc)
            continue
        if not valid:
            log.warning("Token expired for %s — pausing briefs, waiting for extension to push fresh token", user["username"])
            if scheduler.get_job(f"brief_{user['id']}"):
                scheduler.remove_job(f"brief_{user['id']}")
            mark_token_invalid(user["email"])
            send_reauth_email(user["email"], APP_URL)
            continue
        tm.persist(user)


def schedule_brief(user_id: int, brief_hour: int) -> None:
    job_id = f"brief_{user_id}"
    trigger = CronTrigger(day_of_week="mon-fri", hour=brief_hour, minute=0)
    if scheduler.get_job(job_id):
        scheduler.reschedule_job(job_id, trigger=trigger)
    else:
        scheduler.add_job(
            run_brief, trigger, args=[user_id], id=job_id,
            misfire_grace_time=3600,
            replace_existing=True,
        )
    if not scheduler.get_job("token_refresh"):
        scheduler.add_job(
            refresh_all_tokens,
            CronTrigger(minute="*/20"),
            id="token_refresh",
            misfire_grace_time=600,
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
            if not user.get("token_valid", 1):
                log.info("Skipping schedule for %s — token invalid", user["username"])
                continue
            schedule_brief(user["id"], user["brief_hour"])
    except Exception as exc:
        log.error("Failed to restore scheduled jobs: %s", exc, exc_info=True)

    scheduler.start()

    scheduler.add_job(
        refresh_all_tokens,
        DateTrigger(run_date=datetime.now() + timedelta(seconds=5)),
        id="token_refresh_startup",
        replace_existing=True,
    )
