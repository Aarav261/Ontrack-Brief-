import logging
from datetime import date, datetime, timedelta

import requests
from apscheduler.triggers.date import DateTrigger
from flask import Blueprint, g, jsonify, render_template, request

from core.clerk_auth import require_clerk_auth
from core.brief.builder import HIDE_SET
from core.db import (
    get_all_users,
    get_capture_meta,
    get_feedback_entries,
    get_pending_tasks,
    get_unit_code,
    get_user_by_clerk_id,
    get_user_by_username,
    link_clerk_id_by_email,
    prune_ended_projects,
    reassign_email_by_username,
    reset_token_fail,
    set_brief_days,
    set_refresh_token,
    set_subscribed,
    set_task_feedback,
    upsert_projects,
    upsert_tasks,
    upsert_user,
)
from core.jobs import run_brief, schedule_brief
from core.mailer import send_issue_report
from core.ontrack import (
    RefreshTokenError,
    TokenManager,
    mint_auth_token,
)
from core.ontrack.fetcher import (
    _append_missing_tasks,
    _enrich_tasks,
    _extract_latest_feedback,
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
        # The extension sends brief_days as weeks*7; the brief window is 1 or 2
        # weeks, so clamp to [7, 14] with 14 the long-standing default.
        brief_days = 7 if int(data.get("brief_days", 14)) <= 7 else 14
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
    set_brief_days(username, brief_days)
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
        kwargs={"confirm_if_empty": True},
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
        kwargs={"confirm_if_empty": True},
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


@main_bp.route("/ingest", methods=["POST"])
@limiter.limit("120 per minute")
def ingest():
    """Receive OnTrack data captured off the student's own session and store it.

    The morning brief (and the extension strip) read these rows instead of calling
    OnTrack — so there is no token, mint, or re-auth path here. Identity is the
    body-supplied username, the same trust model as /refresh-token: the payload is
    course data, not a credential, and the worst case is a known-username user's
    task list being poisoned. Incremental and idempotent — the extension pushes one
    fragment at a time as the student navigates; each kind upserts independently.

    Body: { username, kind, payload }
      kind="projects"       payload = raw /api/projects list
      kind="project_tasks"  payload = { project_id, unit_code?, tasks, task_definitions }
      kind="feedback"       payload = { project_id, task_def_id, comments, student_id? }
    """
    data = request.get_json(silent=True) or {}
    username = (data.get("username") or "").strip()
    kind = data.get("kind")
    payload = data.get("payload") or {}
    log.info("ingest: kind=%s username=%s", kind, username)
    if not username or not kind:
        return {"ok": False, "error": "missing fields"}, 400

    user = get_user_by_username(username)
    if not user:
        log.warning("ingest: no user row for username=%s — capture dropped", username)
        return {"ok": False, "error": "not subscribed"}, 404
    user_id = user["id"]
    today = date.today()

    # A live push proves the OnTrack session is alive — clear any rotation-race
    # strikes, the same signal /refresh-token uses.
    reset_token_fail(user["email"])

    if kind == "projects":
        if not isinstance(payload, list):
            return {"ok": False, "error": "payload must be a list"}, 400
        projects = []
        for p in payload:
            unit = p.get("unit") or {}
            end_date = unit.get("end_date")
            if end_date and end_date < today.isoformat():
                continue  # ended unit — let the prune drop any stragglers
            projects.append(
                {
                    "project_id": p.get("id"),
                    "unit_code": unit.get("code"),
                    "unit_name": unit.get("name"),
                    "unit_end_date": end_date,
                }
            )
        projects = [p for p in projects if p["project_id"] is not None]
        stored = upsert_projects(user_id, projects)
        prune_ended_projects(user_id, today.isoformat())
        return {"ok": True, "stored": stored}

    if kind == "project_tasks":
        project_id = payload.get("project_id")
        if project_id is None:
            return {"ok": False, "error": "missing project_id"}, 400
        tasks = payload.get("tasks") or []
        task_defs = payload.get("task_definitions") or []
        # Same enrichment the server-pull path uses — resolve deadlines and
        # synthesise not-yet-started tasks — but run once here, against fresh data.
        _enrich_tasks(tasks, task_defs)
        _append_missing_tasks(tasks, task_defs)
        unit_code = payload.get("unit_code") or get_unit_code(user_id, project_id) or ""
        stored = upsert_tasks(user_id, project_id, unit_code, tasks)
        return {"ok": True, "stored": stored}

    if kind == "feedback":
        project_id = payload.get("project_id")
        task_def_id = payload.get("task_def_id")
        if project_id is None or task_def_id is None:
            return {"ok": False, "error": "missing ids"}, 400
        comments = payload.get("comments")
        text = _extract_latest_feedback(comments, payload.get("student_id"))
        if not text:
            return {"ok": True, "stored": 0}
        updated = set_task_feedback(user_id, project_id, task_def_id, text)
        return {"ok": True, "stored": 1 if updated else 0}

    return {"ok": False, "error": f"unknown kind: {kind}"}, 400


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

    # OnTrack rotates the auth_token on every response, so the token the extension
    # scraped has almost certainly gone stale by the time a returning user reopens
    # the popup (which auto re-links). For anyone we already hold a durable
    # refresh_token for, mint a fresh auth_token instead of 401-ing on the stale
    # one — the same path snapshot/brief use. Only the genuine first link (no row
    # yet, OnTrack freshly open during install) falls back to validating the
    # scraped token.
    existing = get_user_by_clerk_id(clerk_id) or get_user_by_username(username)
    is_first_link = existing is None
    # The extension stashes the durable refresh_token in chrome.storage and sends it
    # here, so a brand-new row is created WITH it (otherwise /refresh-credential
    # 404s until the row exists, and the user can be left on the fragile scraped
    # token). Prefer the body's value; fall back to whatever we already hold.
    body_refresh_token = (data.get("refresh_token") or "").strip()
    refresh_token = body_refresh_token or (existing.get("refresh_token") if existing else None)

    if refresh_token:
        try:
            auth_token, _ = mint_auth_token(base_url, refresh_token, username)
        except RefreshTokenError:
            log.info("link-ontrack: refresh_token expired for %s", username)
            return {"ok": False, "error": "refresh_expired", "hint": "open_ontrack"}, 401
        except requests.RequestException as exc:
            log.warning("link-ontrack: OnTrack unreachable minting for %s: %s", username, exc)
            return {"ok": False, "error": "OnTrack unreachable, try again"}, 503
    else:
        tm = TokenManager(base_url, username, auth_token)
        try:
            valid = tm.validate()
        except requests.RequestException as exc:
            log.warning("link-ontrack: OnTrack unreachable for %s: %s", username, exc)
            return {"ok": False, "error": "OnTrack unreachable, try again"}, 503
        if not valid:
            return {"ok": False, "error": "invalid token"}, 401
        auth_token = tm.token

    # The popup auto re-links on every open, so we don't email on every link —
    # only on the first link, OR when the user explicitly clicks "Enable email
    # briefs" (which sends send_brief_now). The auto-link omits the flag.
    send_now = bool(data.get("send_brief_now"))
    was_paused = bool(existing) and not existing.get("subscribed", 1)

    user_id = upsert_user(
        base_url,
        username,
        auth_token,
        email,
        brief_hour,
        recently_completed_days=recently_days,
        max_todo_tasks=max_todo,
        clerk_user_id=clerk_id,
    )
    # Persist a body-supplied refresh_token now that the row exists — this is what
    # closes the chicken-and-egg with /refresh-credential for first-time users.
    if body_refresh_token:
        set_refresh_token(username, body_refresh_token)

    # An explicit "Enable email briefs" click resumes a paused subscription.
    if send_now:
        set_subscribed(email, True)

    # Only (re)schedule for an active subscription. A paused user re-linking on a
    # bare popup open must NOT be silently resubscribed — keep their creds warm so
    # the snapshot works, but leave briefs off until they click enable.
    if send_now or not was_paused:
        schedule_brief(user_id, brief_hour)
        if is_first_link or send_now:
            scheduler.add_job(
                run_brief,
                DateTrigger(run_date=datetime.now() + timedelta(seconds=10)),
                args=[user_id],
                kwargs={"confirm_if_empty": True},
                id=f"welcome_{user_id}",
                replace_existing=True,
            )
            log.info(
                "Immediate brief scheduled for clerk_user_id=%s (first_link=%s, send_now=%s)",
                clerk_id,
                is_first_link,
                send_now,
            )
    else:
        log.info(
            "link-ontrack: %s is paused — refreshed creds, briefs stay off",
            username,
        )
    log.info("OnTrack linked for clerk_user_id=%s (user_id=%s)", clerk_id, user_id)
    return {"ok": True}


@main_bp.route("/api/snapshot", methods=["POST"])
@limiter.limit("60 per minute")
@require_clerk_auth
def api_snapshot():
    """Live strip for the extension — now served entirely from captured data.

    No OnTrack call: the strip reads the same stored tasks the morning brief does,
    so the two match by construction and the popup opens instantly. The data is
    populated by the extension's own /ingest pushes while the student is on OnTrack.
    """
    data = request.get_json(silent=True) or {}
    days_count = min(14, max(1, int(data.get("days", 7))))

    # Identity comes only from the verified Clerk session — no body-supplied
    # username. Resolve by clerk_user_id, claiming a legacy row by verified email.
    clerk_id = g.clerk_user_id
    clerk_email = (g.clerk_claims or {}).get("email")
    db_user = get_user_by_clerk_id(clerk_id)
    if not db_user and clerk_email:
        db_user = link_clerk_id_by_email(clerk_id, clerk_email)
    if not db_user:
        return {"error": "not_linked", "hint": "link_ontrack"}, 404

    user_id = db_user["id"]
    username = db_user["username"]
    base_url = (db_user["base_url"] or "https://ontrack.deakin.edu.au").rstrip("/")
    log.info("api_snapshot: %s (clerk %s)", username, clerk_id)

    today = date.today()
    days = [
        {
            "offset": offset,
            "date": (today + timedelta(days=offset)).isoformat(),
            "label": (today + timedelta(days=offset)).strftime("%a"),
            "tasks": [],
        }
        for offset in range(days_count)
    ]

    # Bucket captured pending tasks by their day offset. Same HIDE_SET as the brief
    # (submitted/done/discuss/demonstrate dropped), so strip == email.
    end = today + timedelta(days=days_count - 1)
    task_count, last_seen = get_capture_meta(user_id)
    for r in get_pending_tasks(user_id, today.isoformat(), end.isoformat()):
        if (r.get("status") or "") in HIDE_SET:
            continue
        try:
            offset = (date.fromisoformat(r["deadline"]) - today).days
        except (ValueError, TypeError):
            continue
        if not 0 <= offset < days_count:
            continue
        abbrev = r.get("abbreviation") or ""
        days[offset]["tasks"].append(
            {
                "name": r.get("name") or abbrev,
                "abbreviation": abbrev,
                "unit": r.get("unit_code") or "",
                "grade": r.get("target_grade_label") or "P (Pass)",
                "due_date": r["deadline"],
                "url": f"{base_url}/projects/{r['project_id']}/dashboard/{abbrev}",
            }
        )

    feedback_entries = []
    for r in get_feedback_entries(user_id, limit=3):
        abbrev = r.get("abbreviation") or ""
        trimmed = " ".join((r.get("feedback_text") or "").split())
        if len(trimmed) > 220:
            trimmed = trimmed[:217].rstrip() + "..."
        feedback_entries.append(
            {
                "unit": r.get("unit_code") or "",
                "task": r.get("name") or abbrev,
                "text": trimmed,
                "url": f"{base_url}/projects/{r['project_id']}/dashboard/{abbrev}",
            }
        )

    response_data = {
        "generated_at": last_seen or datetime.now().isoformat(timespec="seconds"),
        "days": days,
        "feedback": feedback_entries,
        "subscribed": bool(db_user.get("subscribed", 1)),
    }
    # No captured data yet (student hasn't opened OnTrack with the extension since
    # linking) — flag it so the popup can nudge them, same hint the old token-stale
    # path used.
    if task_count == 0:
        response_data["is_stale"] = True
        response_data["hint"] = "open_ontrack"

    return response_data


@main_bp.route("/api/issues", methods=["POST"])
@limiter.limit("5 per hour")
@require_clerk_auth
def report_issue():
    """Accept a user-submitted issue/feedback and email it to the admin inbox.

    Identity is the verified Clerk session (we email that address, never a
    body-supplied one). The description is escaped server-side before it lands in
    the HTML email.
    """
    reporter_email = (g.clerk_claims or {}).get("email")
    if not reporter_email:
        return {"ok": False, "error": "no_email_claim"}, 400

    data = request.get_json(silent=True) or {}
    description = (data.get("description") or "").strip()
    if not description:
        return {"ok": False, "error": "empty"}, 400
    if len(description) > 2000:
        description = description[:2000]

    # Best-effort triage context — the username only exists if OnTrack is linked.
    db_user = get_user_by_clerk_id(g.clerk_user_id)
    context = {
        "Extension": (data.get("version") or "").strip() or "unknown",
        "OnTrack user": db_user["username"] if db_user else "(not linked)",
    }

    if not send_issue_report(description, reporter_email, context=context):
        return {"ok": False, "error": "delivery_failed"}, 502
    log.info("Issue report submitted by %s", reporter_email)
    return {"ok": True}


@main_bp.route("/unsubscribe/<path:email>")
def unsubscribe(email: str):
    # Pause, don't delete: drop the scheduled job and flip the flag so the user
    # keeps their tokens/prefs and can resume from the popup with one click.
    for user in get_all_users():
        if user["email"] == email:
            job_id = f"brief_{user['id']}"
            if scheduler.get_job(job_id):
                scheduler.remove_job(job_id)
            break
    set_subscribed(email, False)
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
    # Reversible pause: drop the job and flip subscribed=0, but keep the row so
    # tokens/preferences survive and re-enabling is instant. A hard delete here
    # was the bug — the popup's auto re-link on next open silently recreated the
    # user and fired a fresh welcome brief.
    job_id = f"brief_{user['id']}"
    if scheduler.get_job(job_id):
        scheduler.remove_job(job_id)
    set_subscribed(user["email"], False)
    return {"ok": True}
