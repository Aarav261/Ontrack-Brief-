import logging
import json
from datetime import date, datetime, timedelta

from apscheduler.triggers.date import DateTrigger
from flask import Blueprint, render_template, request

from core.constants import URGENT, TODO, WAITING
from core.db import (get_all_users, get_user_by_username, remove_user,
                     upsert_user, update_user_snapshot)
from core.fetcher import (TokenExpiredError, fetch_active_projects_direct,
                          fetch_tasks_direct, make_session, validate_token)
from core.jobs import run_brief, schedule_brief
from extensions import limiter, scheduler

log = logging.getLogger(__name__)

main_bp = Blueprint("main", __name__)

def _stale_snapshot_response(db_user):
    if db_user and db_user.get("last_snapshot"):
        try:
            data = json.loads(db_user["last_snapshot"])
            data["is_stale"] = True
            data["hint"] = "open_ontrack"
            return data, 200
        except Exception as exc:
            log.warning("Failed to parse last_snapshot for %s: %s", db_user["username"], exc)
    return {"error": "token expired", "hint": "open_ontrack"}, 401

@main_bp.route("/")
def index():
    return "OnTrack Brief API is running."


def _process_user_setup(data: dict) -> tuple[int | None, tuple[dict, int] | None]:
    base_url   = data.get("base_url", "https://ontrack.deakin.edu.au").rstrip("/")
    username   = data.get("username", "").strip()
    auth_token = data.get("auth_token", "").strip()
    email      = data.get("email", "").strip()
    try:
        brief_hour = max(0, min(23, int(data.get("brief_hour", 8))))
        recently_days = max(1, int(data.get("recently_completed_days", 7)))
        max_todo = max(1, int(data.get("max_todo_tasks", 10)))
    except (ValueError, TypeError):
        return None, ({"ok": False, "error": "invalid numbers"}, 400)

    if not username or not auth_token or not email:
        return None, ({"ok": False, "error": "missing fields"}, 400)

    valid, auth_token = validate_token(base_url, auth_token, username)
    if not valid:
        return None, ({"ok": False, "error": "invalid token"}, 401)

    user_id = upsert_user(base_url, username, auth_token, email, brief_hour,
                          recently_completed_days=recently_days,
                          max_todo_tasks=max_todo)
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
    log.info("First brief for user_id=%s (via register) scheduled in 10 seconds", user_id)

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
    data       = request.get_json(silent=True) or {}
    username   = data.get("username", "").strip()
    auth_token = data.get("auth_token", "").strip()
    if not username or not auth_token:
        return {"ok": False, "error": "missing fields"}, 400

    user = get_user_by_username(username)
    if not user:
        return {"ok": False, "error": "not subscribed"}, 404

    token_changed = user["auth_token"] != auth_token
    was_invalid   = not user["token_valid"]

    if token_changed or was_invalid:
        upsert_user(user["base_url"], username, auth_token,
                    user["email"], user["brief_hour"], token_valid=1,
                    recently_completed_days=user.get("recently_completed_days", 7),
                    max_todo_tasks=user.get("max_todo_tasks", 10))
        if was_invalid:
            log.info("Token restored for %s — re-scheduling brief", username)
            schedule_brief(user["id"], user["brief_hour"])
        else:
            log.info("Token refreshed via extension for %s", username)

    return {"ok": True}


@main_bp.route("/api/snapshot", methods=["POST"])
@limiter.limit("60 per minute")
def api_snapshot():
    data       = request.get_json(silent=True) or {}
    username   = (data.get("username") or "").strip()
    auth_token = (data.get("auth_token") or "").strip()
    base_url   = (data.get("base_url") or "https://ontrack.deakin.edu.au").rstrip("/")
    days_count = min(14, max(1, int(data.get("days", 7))))

    if not username or not auth_token:
        return {"error": "missing fields"}, 400

    db_user = get_user_by_username(username)
    if db_user:
        auth_token = db_user["auth_token"]
        base_url   = db_user["base_url"] or base_url
        log.info("api_snapshot: using DB token ...%s for %s", auth_token[-6:], username)
    else:
        log.warning("api_snapshot: %s not found in DB — using extension token ...%s", username, auth_token[-6:])

    try:
        valid, auth_token = validate_token(base_url, auth_token, username)
    except Exception as exc:
        log.warning("api_snapshot: OnTrack unreachable for %s: %s", username, exc)
        return {"error": "OnTrack unreachable"}, 503

    if not valid:
        log.warning("api_snapshot: token rejected by OnTrack for %s — open OnTrack to refresh", username)
        return _stale_snapshot_response(db_user)

    # Use a dedicated session so token capture doesn't interfere with brief jobs
    snap_session, snap_tokens = make_session()

    try:
        projects, auth_token = fetch_active_projects_direct(base_url, auth_token, username, session=snap_session)
    except TokenExpiredError:
        return _stale_snapshot_response(db_user)
    except Exception as exc:
        log.warning("api_snapshot: fetch_projects failed for %s: %s", username, exc)
        return {"error": "could not fetch projects"}, 502

    today  = date.today()
    ACTIVE = URGENT | TODO | WAITING

    date_index = {}
    days = []
    for offset in range(days_count):
        d   = today + timedelta(days=offset)
        iso = d.isoformat()
        date_index[iso] = offset
        days.append({"offset": offset, "date": iso, "label": d.strftime("%a"), "tasks": []})

    for project in projects:
        project_id = project["id"]
        unit_code  = project["unit"]["code"]
        try:
            tasks = fetch_tasks_direct(base_url, auth_token, username, project_id, session=snap_session)
            if snap_tokens["last"]:
                auth_token = snap_tokens["last"]
        except Exception as exc:
            log.warning("api_snapshot: fetch_tasks failed project %s: %s", project_id, exc)
            continue
        for task in tasks:
            if task.get("status") not in ACTIVE:
                continue
            due = (task.get("due_date") or "")[:10]
            if due not in date_index:
                continue
            abbrev = task.get("abbreviation", "")
            days[date_index[due]]["tasks"].append({
                "name":         task.get("name", abbrev),
                "abbreviation": abbrev,
                "unit":         unit_code,
                "grade":        task.get("target_grade_label", "P (Pass)"),
                "due_date":     due,
                "url":          f"{base_url}/projects/{project_id}/dashboard/{abbrev}",
            })

    response_data = {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "days": days,
        "auth_token": auth_token
    }

    if db_user:
        update_user_snapshot(username, json.dumps(response_data))

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
