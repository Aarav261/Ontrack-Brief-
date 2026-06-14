import logging
import os
from datetime import date
from zoneinfo import ZoneInfo

import requests

from apscheduler.jobstores.base import JobLookupError
from apscheduler.triggers.cron import CronTrigger

from core.brief import build_brief_direct, pending_due_entries, render_html
from core.db import (
    bump_token_fail,
    get_all_users,
    get_user_by_id,
    init_db,
    mark_token_invalid,
    reset_token_fail,
)
from core.mailer import send_brief_to, send_briefs_enabled_email, send_reauth_email
from core.ontrack import (
    RefreshTokenError,
    TokenManager,
    TokenExpiredError,
    fetch_active_projects_direct,
    mint_auth_token,
)
from extensions import scheduler

log = logging.getLogger(__name__)
APP_URL = os.environ.get("APP_URL", "http://localhost:8000/")
# brief_hour is the user's intended *local* hour. OnTrack is Deakin, so briefs
# run on Melbourne time (DST-aware) — without this the container's UTC clock
# would fire an "8am" brief at 6pm Melbourne. (tzdata is pinned in requirements
# so the zone resolves on the slim Docker image.)
_BRIEF_TZ = ZoneInfo("Australia/Melbourne")
_PENDING_WINDOW_DAYS = 14
_THIS_WEEK_DAYS = 6
# Consecutive failed token checks before treating a token as truly expired.
# Tolerates OnTrack's rotation races (a stale-but-superseded token reads as
# rejected); a real logout fails every check and trips this within ~an hour.
_FAIL_THRESHOLD = 3


def _pause_and_reauth(user_id: int, email: str) -> None:
    """Pause a user's brief and send the one-time re-auth email."""
    if scheduler.get_job(f"brief_{user_id}"):
        scheduler.remove_job(f"brief_{user_id}")
    mark_token_invalid(email)
    send_reauth_email(email, APP_URL)


def run_brief(user_id: int, *, confirm_if_empty: bool = False) -> None:
    """Build and email a user's brief.

    ``confirm_if_empty`` is set only by an explicit "Enable email briefs" action:
    when the user has no active units (nothing to brief), send a one-off
    confirmation email instead of returning silently — so the deliberate click
    gets feedback. The daily cron leaves it False, so it never spams an empty brief.
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
    recently_completed_days = user.get("recently_completed_days", 7)

    # One TokenManager (and its isolated session) per brief run — its response
    # hook captures every token rotation into tm.token, so concurrent jobs never
    # clobber each other's tokens. tm.persist() writes the freshest token back.
    tm = TokenManager.for_user(user)

    # Mint a fresh auth_token from the durable refresh_token if we have one. This
    # is what keeps the brief working after overnight idle: the stored auth_token
    # may have lapsed, but the refresh_token mints a live one on demand. A rejected
    # refresh_token (expired) is the real "logged out" signal → pause + re-auth.
    refresh_token = user.get("refresh_token")
    if refresh_token:
        try:
            tm.token, _user = mint_auth_token(
                tm.base_url, refresh_token, tm.username, session=tm.session
            )
            tm.persist(user)
        except RefreshTokenError as exc:
            log.warning(
                "Refresh token expired for %s (%s) — pausing briefs, waiting for "
                "extension to push a fresh one",
                email,
                exc,
            )
            _pause_and_reauth(user_id, email)
            return
        except requests.RequestException as exc:
            # Transient OnTrack hiccup (timeout / 5xx) — NOT expiry. Skip today's
            # brief and let the next scheduled run retry. Do not pause or send a
            # re-auth email: a false "re-login" prompt would rotate the token.
            log.warning(
                "Mint failed transiently for %s (%s) — skipping this run, no pause",
                email,
                exc,
            )
            return

    try:
        projects, tm.token = fetch_active_projects_direct(
            tm.base_url, tm.token, tm.username, session=tm.session
        )
        tm.persist(user)  # save the token rotated by the projects call
        if not projects:
            if confirm_if_empty:
                log.info("No active units for %s — sending briefs-enabled confirmation", email)
                send_briefs_enabled_email(email)
                reset_token_fail(email)  # mint/fetch worked — session is alive
            return
        brief = build_brief_direct(
            tm.base_url,
            tm.token,
            tm.username,
            projects,
            recently_completed_days=recently_completed_days,
            session=tm.session,
        )
        tm.persist(user)  # save the freshest token seen across the task calls
        today = date.today()
        pending_due = pending_due_entries(brief, today, _PENDING_WINDOW_DAYS)
        due_this_week = len(pending_due_entries(brief, today, _THIS_WEEK_DAYS))
        html = render_html(pending_due, today, window_days=_PENDING_WINDOW_DAYS)
        send_brief_to(html, email, today, due_this_week)
        reset_token_fail(email)  # brief succeeded — session is alive
    except TokenExpiredError:
        strikes = bump_token_fail(email)
        if strikes < _FAIL_THRESHOLD:
            log.info(
                "Brief token check failed for %s (strike %d/%d) — likely a rotation "
                "race, not pausing",
                email,
                strikes,
                _FAIL_THRESHOLD,
            )
            return
        log.warning(
            "Token expired for %s after %d failed checks — pausing briefs, waiting "
            "for extension to push fresh token",
            email,
            strikes,
        )
        _pause_and_reauth(user_id, email)
    except Exception as exc:
        log.error("Brief generation failed for %s: %s", email, exc, exc_info=True)


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
            if not user.get("token_valid", 1):
                log.info("Skipping schedule for %s — token invalid", user["username"])
                continue
            if not user.get("subscribed", 1):
                log.info("Skipping schedule for %s — unsubscribed (paused)", user["username"])
                continue
            schedule_brief(user["id"], user["brief_hour"])
    except Exception as exc:
        log.error("Failed to restore scheduled jobs: %s", exc, exc_info=True)

    scheduler.start()

    # Evict the retired 20-min token-refresh poll if an older deploy persisted it.
    _remove_retired_jobs()
