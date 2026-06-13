import logging
import os
from datetime import date, datetime, timedelta

from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.date import DateTrigger

from core.brief import build_brief_direct, pending_due_entries, render_html
from core.db import (
    bump_token_fail,
    get_all_users,
    get_user_by_id,
    init_db,
    mark_token_invalid,
    reset_token_fail,
)
from core.mailer import send_brief_to, send_reauth_email
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

    try:
        projects, tm.token = fetch_active_projects_direct(
            tm.base_url, tm.token, tm.username, session=tm.session
        )
        tm.persist(user)  # save the token rotated by the projects call
        if not projects:
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


def refresh_all_tokens() -> None:
    """Single consolidated job — reads fresh from DB every 20 min for all users.

    For users with a durable refresh_token, liveness is "can we still mint?" — we
    mint a fresh auth_token (and persist it) so the credential stays warm and an
    expired refresh_token is caught before the morning brief. Legacy users without
    a refresh_token fall back to validating their rotating auth_token.
    """
    for user in get_all_users():
        # Already invalid: briefs are paused and the one-time re-auth email was
        # already sent. Skip until the extension pushes a fresh token (which
        # restores token_valid=1), so we don't re-email every cycle.
        if not user.get("token_valid", 1):
            continue

        tm = TokenManager.for_user(user)
        refresh_token = user.get("refresh_token")
        try:
            if refresh_token:
                # Mint, not validate: the stored auth_token may be legitimately
                # stale (e.g. overnight) — that's no longer a failure signal.
                tm.token, _ = mint_auth_token(
                    tm.base_url, refresh_token, tm.username, session=tm.session
                )
                valid = True
            else:
                valid = tm.validate()
        except RefreshTokenError as exc:
            valid = False  # refresh_token rejected — fall through to strike logic
            log.debug("Mint failed for %s: %s", user["username"], exc)
        except Exception as exc:
            log.warning(
                "OnTrack unreachable for %s (service may be down): %s",
                user["username"],
                exc,
            )
            continue

        if not valid:
            strikes = bump_token_fail(user["email"])
            if strikes < _FAIL_THRESHOLD:
                log.info(
                    "Token check failed for %s (strike %d/%d) — likely a rotation "
                    "race (browser/extension rotated it), not pausing",
                    user["username"],
                    strikes,
                    _FAIL_THRESHOLD,
                )
                continue
            log.warning(
                "Token for %s failed %d consecutive checks — pausing briefs, "
                "waiting for extension to push fresh token",
                user["username"],
                strikes,
            )
            _pause_and_reauth(user["id"], user["email"])
            continue
        reset_token_fail(user["email"])  # valid check — clear any accumulated strikes
        tm.persist(user)


def schedule_brief(user_id: int, brief_hour: int) -> None:
    job_id = f"brief_{user_id}"
    trigger = CronTrigger(day_of_week="mon-fri", hour=brief_hour, minute=0)
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
