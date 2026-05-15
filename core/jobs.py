import logging
import os
from datetime import date, datetime, timedelta

from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.date import DateTrigger

from core.builder import build_brief_direct
from core.db import (get_all_users, get_user_by_id, init_db, mark_token_invalid,
                     upsert_user)
from core.fetcher import fetch_active_projects_direct, validate_token, TokenExpiredError, make_session
from core.mailer import send_brief_to, send_reauth_email
from core.renderer import render_html
from extensions import scheduler

log = logging.getLogger(__name__)
APP_URL = os.environ.get("APP_URL", "http://localhost:8000/")

def run_brief(user_id: int) -> None:
    user = get_user_by_id(user_id)
    if not user:
        log.error("run_brief: no user found for id=%s", user_id)
        return
    base_url = user["base_url"]
    auth_token = user["auth_token"]
    username = user["username"]
    email = user["email"]
    recently_completed_days = user.get("recently_completed_days", 7)
    max_todo_tasks = user.get("max_todo_tasks", 10)

    try:
        # One isolated session per brief run — prevents token cross-contamination
        # between concurrent jobs (Doubtfire rotates the token on every response).
        session, token_store = make_session()

        projects, fresh_token = fetch_active_projects_direct(base_url, auth_token, username, session=session)
        if fresh_token != auth_token:
            log.info("Token rotated for %s — updating DB", username)
            upsert_user(base_url, username, fresh_token, email,
                        brief_hour=user.get("brief_hour", 8),
                        recently_completed_days=recently_completed_days,
                        max_todo_tasks=max_todo_tasks)
        if not projects:
            return
        brief = build_brief_direct(base_url, fresh_token, username, projects,
                                   recently_completed_days=recently_completed_days,
                                   session=session)
        final_token = token_store["last"] or fresh_token
        if final_token != fresh_token:
            upsert_user(base_url, username, final_token, email,
                        brief_hour=user.get("brief_hour", 8),
                        recently_completed_days=recently_completed_days,
                        max_todo_tasks=max_todo_tasks)
        html = render_html(brief, projects, date.today(), max_todo=max_todo_tasks)
        send_brief_to(html, email, date.today())
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
        try:
            valid, fresh_token = validate_token(
                user["base_url"], user["auth_token"], user["username"]
            )
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
        if fresh_token != user["auth_token"]:
            log.info("Token rotated for %s — updating DB", user["username"])
            upsert_user(user["base_url"], user["username"], fresh_token,
                        user["email"], user["brief_hour"],
                        recently_completed_days=user.get("recently_completed_days", 7),
                        max_todo_tasks=user.get("max_todo_tasks", 10))


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
