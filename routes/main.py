import logging
import json
from datetime import date, datetime, timedelta

import requests
from apscheduler.triggers.date import DateTrigger
from flask import Blueprint, g, jsonify, render_template, request

from core.clerk_auth import require_clerk_auth
from core.constants import URGENT, TODO, WAITING, SUBMITTED
from core.db import (
    get_all_users,
    get_user_by_clerk_id,
    get_user_by_username,
    link_clerk_id_by_email,
    reassign_email_by_username,
    remove_user,
    reset_token_fail,
    set_refresh_token,
    upsert_user,
    update_user_snapshot,
)
from core.jobs import run_brief, schedule_brief
from core.ontrack import (
    TokenManager,
    TokenExpiredError,
    fetch_active_projects_direct,
    fetch_last_feedback_direct,
    fetch_tasks_direct,
)
from extensions import limiter, scheduler

log = logging.getLogger(__name__)

main_bp = Blueprint("main", __name__)


@main_bp.route("/api/whoami")
@require_clerk_auth
def whoami():
    """Phase 0 spike: proves a Clerk session JWT verifies on the backend."""
    return jsonify(
        {
            "clerk_user_id": g.clerk_user_id,
            "email": (g.clerk_claims or {}).get("email"),
        }
    )


def _stale_snapshot_response(db_user):
    if db_user and db_user.get("last_snapshot"):
        try:
            data = json.loads(db_user["last_snapshot"])
            data["is_stale"] = True
            data["hint"] = "open_ontrack"
            return data, 200
        except Exception as exc:
            log.warning(
                "Failed to parse last_snapshot for %s: %s", db_user["username"], exc
            )
    return {"error": "token expired", "hint": "open_ontrack"}, 401


@main_bp.route("/")
def index():
    return "OnTrack Brief API is running."


def _process_user_setup(data: dict) -> tuple[int | None, tuple[dict, int] | None]:
    base_url = data.get("base_url", "https://ontrack.deakin.edu.au").rstrip("/")
    username = data.get("username", "").strip()
    auth_token = data.get("auth_token", "").strip()
    email = data.get("email", "").strip()
    try:
        brief_hour = max(0, min(23, int(data.get("brief_hour", 8))))
        recently_days = max(1, int(data.get("recently_completed_days", 7)))
        max_todo = max(1, int(data.get("max_todo_tasks", 10)))
    except (ValueError, TypeError):
        return None, ({"ok": False, "error": "invalid numbers"}, 400)

    if not username or not auth_token or not email:
        return None, ({"ok": False, "error": "missing fields"}, 400)

    tm = TokenManager(base_url, username, auth_token)
    try:
        valid = tm.validate()
    except requests.RequestException as exc:
        log.warning("setup: OnTrack unreachable for %s: %s", username, exc)
        return None, ({"ok": False, "error": "OnTrack unreachable, try again"}, 503)
    if not valid:
        return None, ({"ok": False, "error": "invalid token"}, 401)

    # Username is the account identity. If this OnTrack account is already
    # registered under a different email, move the subscription rather than
    # inserting a duplicate row (the table is unique on email, not username).
    existing = get_user_by_username(username)
    if existing and existing["email"] != email:
        if not reassign_email_by_username(username, email):
            return None, (
                {
                    "ok": False,
                    "error": "That email is already registered to another OnTrack account",
                },
                409,
            )
        log.info(
            "Re-registration of %s under a new email — moved subscription to %s",
            username,
            email,
        )

    user_id = upsert_user(
        tm.base_url,
        username,
        tm.token,
        email,
        brief_hour,
        recently_completed_days=recently_days,
        max_todo_tasks=max_todo,
    )
    schedule_brief(user_id, brief_hour)
    return user_id, None


@main_bp.route("/register", methods=["POST"])
@limiter.limit("10 per minute")
def register():
    data = request.get_json(silent=True) or {}
    user_id, err_resp = _process_user_setup(data)
    if err_resp:
        return err_resp[0], err_resp[1]

    scheduler.add_job(
        run_brief,
        DateTrigger(run_date=datetime.now() + timedelta(seconds=10)),
        args=[user_id],
        id=f"welcome_{user_id}",
        replace_existing=True,
    )
    log.info(
        "First brief for user_id=%s (via register) scheduled in 10 seconds", user_id
    )

    return {"ok": True}


@main_bp.route("/setup", methods=["POST"])
@limiter.limit("10 per minute")
def setup():
    """Update email-brief settings for an already-authenticated user."""
    raw = request.get_json(silent=True)
    if raw is None:
        raw = {k: v for k, v in request.form.items()}
    data = raw or {}

    user_id, err_resp = _process_user_setup(data)
    if err_resp:
        return err_resp[0], err_resp[1]

    scheduler.add_job(
        run_brief,
        DateTrigger(run_date=datetime.now() + timedelta(seconds=10)),
        args=[user_id],
        id=f"welcome_{user_id}",
        replace_existing=True,
    )
    log.info("Settings updated for user_id=%s — immediate brief scheduled", user_id)
    return {"ok": True}


@main_bp.route("/refresh-token", methods=["POST"])
@limiter.limit("30 per minute")
def refresh_token():
    """Called by the browser extension on every OnTrack page load."""
    data = request.get_json(silent=True) or {}
    username = data.get("username", "").strip()
    auth_token = data.get("auth_token", "").strip()
    if not username or not auth_token:
        return {"ok": False, "error": "missing fields"}, 400

    user = get_user_by_username(username)
    if not user:
        return {"ok": False, "error": "not subscribed"}, 404

    # A live push from the extension proves the session is alive — clear any
    # token-failure strikes the rotation-race poll may have accumulated.
    reset_token_fail(user["email"])

    token_changed = user["auth_token"] != auth_token
    was_invalid = not user["token_valid"]

    if token_changed or was_invalid:
        upsert_user(
            user["base_url"],
            username,
            auth_token,
            user["email"],
            user["brief_hour"],
            token_valid=1,
            recently_completed_days=user.get("recently_completed_days", 7),
            max_todo_tasks=user.get("max_todo_tasks", 10),
        )
        if was_invalid:
            log.info("Token restored for %s — re-scheduling brief", username)
            schedule_brief(user["id"], user["brief_hour"])
        else:
            log.info("Token refreshed via extension for %s", username)

    return {"ok": True}


@main_bp.route("/refresh-credential", methods=["POST"])
@limiter.limit("30 per minute")
def refresh_credential():
    """Called by the extension to push the browser's durable refresh_token cookie.

    Unlike the rotating auth_token, this lets the server mint a fresh auth_token
    on demand (right before each brief), so the session survives overnight idle.
    """
    data = request.get_json(silent=True) or {}
    username = data.get("username", "").strip()
    refresh_token = data.get("refresh_token", "").strip()
    if not username or not refresh_token:
        return {"ok": False, "error": "missing fields"}, 400

    user = get_user_by_username(username)
    if not user:
        return {"ok": False, "error": "not subscribed"}, 404

    if not set_refresh_token(username, refresh_token):
        return {"ok": False, "error": "not subscribed"}, 404

    # A fresh refresh_token proves the user is re-authenticated — clear strikes and,
    # if briefs were paused on a dead token, restore and re-schedule them.
    reset_token_fail(user["email"])
    if not user["token_valid"]:
        upsert_user(
            user["base_url"],
            username,
            user["auth_token"],
            user["email"],
            user["brief_hour"],
            token_valid=1,
            recently_completed_days=user.get("recently_completed_days", 7),
            max_todo_tasks=user.get("max_todo_tasks", 10),
        )
        log.info("Refresh token received for %s — restoring paused brief", username)
        schedule_brief(user["id"], user["brief_hour"])
    else:
        log.info("Refresh token stored for %s", username)

    return {"ok": True}


@main_bp.route("/link-ontrack", methods=["POST"])
@limiter.limit("10 per minute")
@require_clerk_auth
def link_ontrack():
    """Store the user's OnTrack token against their Clerk identity (Phase 2).

    Identity (clerk_user_id + verified email) comes from the JWT; the body
    carries only the scraped OnTrack creds + optional brief settings. This is
    what clears the /api/snapshot "not_linked" state.
    """
    clerk_id = g.clerk_user_id
    email = (g.clerk_claims or {}).get("email")
    if not email:
        # Clerk JWT template must expose an `email` claim (see setup docs).
        return {"ok": False, "error": "no_email_claim"}, 400

    data = request.get_json(silent=True) or {}
    base_url = (data.get("base_url") or "https://ontrack.deakin.edu.au").rstrip("/")
    username = (data.get("username") or "").strip()
    auth_token = (data.get("auth_token") or "").strip()
    try:
        brief_hour = max(0, min(23, int(data.get("brief_hour", 8))))
        recently_days = max(1, int(data.get("recently_completed_days", 7)))
        max_todo = max(1, int(data.get("max_todo_tasks", 10)))
    except (ValueError, TypeError):
        return {"ok": False, "error": "invalid numbers"}, 400

    if not username or not auth_token:
        return {"ok": False, "error": "missing fields"}, 400

    tm = TokenManager(base_url, username, auth_token)
    try:
        valid = tm.validate()
    except requests.RequestException as exc:
        log.warning("link-ontrack: OnTrack unreachable for %s: %s", username, exc)
        return {"ok": False, "error": "OnTrack unreachable, try again"}, 503
    if not valid:
        return {"ok": False, "error": "invalid token"}, 401

    # First link = no row yet for this Clerk identity. The popup re-links on
    # every open, so only the first one schedules an immediate welcome brief —
    # otherwise the user gets an email every time they open the extension.
    is_first_link = get_user_by_clerk_id(clerk_id) is None

    user_id = upsert_user(
        tm.base_url,
        username,
        tm.token,
        email,
        brief_hour,
        recently_completed_days=recently_days,
        max_todo_tasks=max_todo,
        clerk_user_id=clerk_id,
    )
    schedule_brief(user_id, brief_hour)
    if is_first_link:
        scheduler.add_job(
            run_brief,
            DateTrigger(run_date=datetime.now() + timedelta(seconds=10)),
            args=[user_id],
            id=f"welcome_{user_id}",
            replace_existing=True,
        )
        log.info("First link for clerk_user_id=%s — welcome brief scheduled", clerk_id)
    log.info("OnTrack linked for clerk_user_id=%s (user_id=%s)", clerk_id, user_id)
    return {"ok": True}


@main_bp.route("/api/snapshot", methods=["POST"])
@limiter.limit("60 per minute")
@require_clerk_auth
def api_snapshot():
    data = request.get_json(silent=True) or {}
    base_url = (data.get("base_url") or "https://ontrack.deakin.edu.au").rstrip("/")
    days_count = min(14, max(1, int(data.get("days", 7))))

    # Identity comes only from the verified Clerk session — no body-supplied
    # username. Resolve by clerk_user_id, claiming a legacy row by verified
    # email on first sign-in. The server already holds the OnTrack token.
    clerk_id = g.clerk_user_id
    clerk_email = (g.clerk_claims or {}).get("email")
    db_user = get_user_by_clerk_id(clerk_id)
    if not db_user and clerk_email:
        db_user = link_clerk_id_by_email(clerk_id, clerk_email)
    if not db_user:
        return {"error": "not_linked", "hint": "link_ontrack"}, 404

    username = db_user["username"]
    auth_token = db_user["auth_token"]
    base_url = db_user["base_url"] or base_url
    log.info("api_snapshot: %s (clerk %s)", username, clerk_id)

    # Dedicated TokenManager so token capture doesn't interfere with brief jobs.
    tm = TokenManager(base_url, username, auth_token)

    try:
        valid = tm.validate()
    except Exception as exc:
        log.warning("api_snapshot: OnTrack unreachable for %s: %s", username, exc)
        return {"error": "OnTrack unreachable"}, 503

    if not valid:
        log.warning(
            "api_snapshot: token rejected by OnTrack for %s — open OnTrack to refresh",
            username,
        )
        return _stale_snapshot_response(db_user)

    try:
        projects, tm.token = fetch_active_projects_direct(
            tm.base_url, tm.token, tm.username, session=tm.session
        )
    except TokenExpiredError:
        return _stale_snapshot_response(db_user)
    except Exception as exc:
        log.warning("api_snapshot: fetch_projects failed for %s: %s", username, exc)
        return {"error": "could not fetch projects"}, 502

    today = date.today()
    ACTIVE = URGENT | TODO | WAITING
    FEEDBACK_STATUSES = URGENT | TODO | WAITING | SUBMITTED
    feedback_entries = []
    feedback_checks = 0
    student_id = None
    if projects:
        user = projects[0].get("user") or {}
        student_id = user.get("id")

    date_index = {}
    days = []
    for offset in range(days_count):
        d = today + timedelta(days=offset)
        iso = d.isoformat()
        date_index[iso] = offset
        days.append(
            {"offset": offset, "date": iso, "label": d.strftime("%a"), "tasks": []}
        )

    for project in projects:
        if len(feedback_entries) >= 3 or feedback_checks >= 8:
            break
        project_id = project["id"]
        unit_code = project["unit"]["code"]
        try:
            tasks = fetch_tasks_direct(
                tm.base_url, tm.token, tm.username, project_id, session=tm.session
            )
        except Exception as exc:
            log.warning(
                "api_snapshot: fetch_tasks failed project %s: %s", project_id, exc
            )
            continue
        for task in tasks:
            if task.get("status") not in ACTIVE:
                continue
            due = (task.get("due_date") or "")[:10]
            if due not in date_index:
                continue
            abbrev = task.get("abbreviation", "")
            days[date_index[due]]["tasks"].append(
                {
                    "name": task.get("name", abbrev),
                    "abbreviation": abbrev,
                    "unit": unit_code,
                    "grade": task.get("target_grade_label", "P (Pass)"),
                    "due_date": due,
                    "url": f"{base_url}/projects/{project_id}/dashboard/{abbrev}",
                }
            )
        if len(feedback_entries) >= 3:
            continue
        for task in tasks:
            if task.get("status") not in FEEDBACK_STATUSES:
                continue
            if len(feedback_entries) >= 3:
                break
            if feedback_checks >= 8:
                break
            feedback_checks += 1
            text = fetch_last_feedback_direct(
                tm.base_url,
                tm.token,
                tm.username,
                project_id,
                task.get("task_definition_id"),
                student_id,
                session=tm.session,
            )
            if not text:
                continue
            trimmed = " ".join(text.split())
            if len(trimmed) > 220:
                trimmed = trimmed[:217].rstrip() + "..."
            abbrev = task.get("abbreviation", "")
            feedback_entries.append(
                {
                    "unit": unit_code,
                    "task": task.get("name", abbrev) or abbrev,
                    "text": trimmed,
                    "url": f"{base_url}/projects/{project_id}/dashboard/{abbrev}",
                }
            )

    response_data = {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "days": days,
        "feedback": feedback_entries,
        "auth_token": tm.token,
    }

    if db_user:
        # Don't persist the rotating token inside the snapshot — it's a credential
        # at rest, and a stale snapshot must never hand back an outdated token.
        stored = {k: v for k, v in response_data.items() if k != "auth_token"}
        update_user_snapshot(username, json.dumps(stored))

    return response_data


@main_bp.route("/unsubscribe/<path:email>")
def unsubscribe(email: str):
    for user in get_all_users():
        if user["email"] == email:
            job_id = f"brief_{user['id']}"
            if scheduler.get_job(job_id):
                scheduler.remove_job(job_id)
            break
    remove_user(email)
    return render_template("unsubscribed.html", email=email)


@main_bp.route("/unsubscribe", methods=["POST"])
@limiter.limit("10 per minute")
@require_clerk_auth
def unsubscribe_clerk():
    """Unsubscribe the caller, keyed off their verified Clerk identity.

    Keying on clerk_user_id (not an email in the URL) prevents anyone from
    unsubscribing another user by guessing their address.
    """
    user = get_user_by_clerk_id(g.clerk_user_id)
    if not user:
        return {"ok": True}  # nothing linked — idempotent no-op
    job_id = f"brief_{user['id']}"
    if scheduler.get_job(job_id):
        scheduler.remove_job(job_id)
    remove_user(user["email"])
    return {"ok": True}
