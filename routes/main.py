import logging
import os
from datetime import date, datetime, timedelta

import requests
from apscheduler.triggers.date import DateTrigger
from flask import Blueprint, g, jsonify, request
from flask_limiter.util import get_remote_address

from core.brief.builder import is_hidden
from core.clerk_auth import require_clerk_auth
from core.db import (
    delete_tasks_for_inactive_projects,
    get_capture_meta,
    get_feedback_entries,
    get_pending_tasks,
    get_unit_code,
    get_user_by_clerk_id,
    get_user_by_username,
    link_clerk_id_by_email,
    prune_ended_projects,
    reclaim_ontrack_username,
    reset_token_fail,
    set_refresh_token,
    set_subscribed,
    set_task_feedback,
    update_brief_prefs,
    upsert_projects,
    upsert_tasks,
    upsert_user,
)
from core.jobs import run_brief, schedule_brief
from core.mailer import send_issue_report
from core.ontrack import (
    RefreshTokenError,
    TokenManager,
    append_missing_tasks,
    enrich_tasks,
    extract_latest_feedback,
    mint_auth_token,
)
from extensions import limiter, scheduler

log = logging.getLogger(__name__)

main_bp = Blueprint("main", __name__)


@main_bp.route("/api/version")
def api_version():
    """Returns the minimum extension version required to use the service.
    Set MIN_EXTENSION_VERSION env var to force an update prompt for old builds."""
    min_required = os.environ.get("MIN_EXTENSION_VERSION", "1.9")
    return jsonify({"min_required": min_required})


@main_bp.route("/")
def index():
    return "OnTrack Brief API is running."


def _clamp_brief_days(raw) -> int:
    """The extension sends brief_days as weeks*7; the brief window is 1 or 2
    weeks, so clamp to {7, 14} with 14 the long-standing default."""
    return 7 if int(raw) <= 7 else 14


_VALID_DOW = ("mon", "tue", "wed", "thu", "fri", "sat", "sun")


def _normalize_dow(raw) -> str | None:
    """Normalize a requested send-days value into an APScheduler day_of_week string.

    Accepts a CSV string ("mon,wed,fri"), a hyphen range ("mon-fri"), or a list of
    day tokens; keeps only valid weekday tokens in canonical Mon→Sun order and
    returns them comma-joined. Returns None for an empty/invalid selection so the
    caller can fall back to the stored value rather than scheduling a brief that
    never fires.
    """
    if raw is None:
        return None
    if isinstance(raw, str):
        text = raw.strip().lower()
        if "-" in text:
            start, _, end = text.partition("-")
            i, j = (
                _VALID_DOW.index(start) if start in _VALID_DOW else -1,
                (_VALID_DOW.index(end) if end in _VALID_DOW else -1),
            )
            chosen = set(_VALID_DOW[i : j + 1]) if 0 <= i <= j else set()
        else:
            chosen = {t.strip()[:3] for t in text.split(",") if t.strip()}
    else:
        chosen = {str(t).strip().lower()[:3] for t in raw if str(t).strip()}
    ordered = [d for d in _VALID_DOW if d in chosen]
    return ",".join(ordered) if ordered else None


def _brief_schedule_args(user: dict) -> tuple[int, int, str]:
    """The (hour, minute, dow) triple schedule_brief needs, read from a user row with
    safe fallbacks for rows that predate the minute/dow columns."""
    return (
        user["brief_hour"],
        user.get("brief_minute", 0),
        user.get("brief_dow") or "mon-fri",
    )


def _schedule_welcome_brief(user_id: int) -> None:
    """Fire a one-off brief ~10s from now (first link / explicit enable)."""
    scheduler.add_job(
        run_brief,
        DateTrigger(run_date=datetime.now() + timedelta(seconds=10)),
        args=[user_id],
        kwargs={"confirm_if_empty": True},
        id=f"welcome_{user_id}",
        replace_existing=True,
    )


def _persist_valid_token(user: dict, username: str, auth_token: str) -> None:
    """Re-store the user with token_valid=1, preserving their saved preferences.
    Shared by the two extension push paths that prove the session is alive."""
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
        _persist_valid_token(user, username, auth_token)
        if was_invalid:
            log.info("Token restored for %s — re-scheduling brief", username)
            schedule_brief(user["id"], *_brief_schedule_args(user))
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
        _persist_valid_token(user, username, user["auth_token"])
        log.info("Refresh token received for %s — restoring paused brief", username)
        schedule_brief(user["id"], *_brief_schedule_args(user))
    else:
        log.info("Refresh token stored for %s", username)

    return {"ok": True}


def _ingest_rate_key():
    """Per-student rate-limit bucket for /ingest.

    The endpoint is unauthenticated and, in Docker and behind Railway's proxy,
    every session arrives from one shared IP (the gateway / proxy). Keying the
    limit on IP (the limiter default) therefore lets one busy session — whose
    project sweep fans out into many small pushes — exhaust the limit for every
    other student. Key on the body-supplied username so each student gets their
    own bucket, falling back to IP when the body has no username (malformed
    request, which the handler rejects anyway)."""
    data = request.get_json(silent=True) or {}
    username = (data.get("username") or "").strip()
    return f"ingest:{username}" if username else get_remote_address()


@main_bp.route("/ingest", methods=["POST"])
@limiter.limit("120 per minute", key_func=_ingest_rate_key)
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
    was_invalid = not user.get("token_valid", 1)
    reset_token_fail(user["email"])
    if was_invalid:
        # User's token_valid=0 flag may have been set by the old polling code,
        # which also removed their brief job. Restore it here so a pure-ingest
        # user isn't silently left without briefs until a server restart.
        log.info("ingest: restoring brief job for %s (was token_invalid)", user["email"])
        schedule_brief(user_id, *_brief_schedule_args(user))

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
        # Drop tasks left behind by now-ended projects (past trimesters) so the
        # snapshot/brief never read stale rows. Pairs with the project_tasks guard
        # below — together they keep the DB to the active trimester even if an old
        # extension build keeps sweeping every project.
        removed = delete_tasks_for_inactive_projects(user_id)
        if removed:
            log.info("ingest: pruned %d task(s) for ended projects (user %s)", removed, user_id)
        return {"ok": True, "stored": stored}

    if kind == "project_tasks":
        project_id = payload.get("project_id")
        if project_id is None:
            return {"ok": False, "error": "missing project_id"}, 400
        # Past-trimester pushes (an older extension build still sweeping an ended
        # unit) are cleaned up by prune_ended_projects/delete_tasks_for_inactive_projects
        # on the next "projects" ingest, not rejected here. An eager active_ids
        # check used to reject pushes for a project not yet present in `projects`,
        # but project_tasks and projects land as independent concurrent requests —
        # a returning student's current-trimester project_tasks push routinely beat
        # its own projects ingest to the DB, got misclassified as "inactive", and
        # (compounded by the extension's ingest dedup) never got stored at all.
        # Guard: enrich_tasks and append_missing_tasks both use
        # t["task_definition_id"] (hard key access). Drop any task dicts the
        # extension sent without that field before passing them in.
        tasks = [t for t in (payload.get("tasks") or []) if t.get("task_definition_id") is not None]
        task_defs = payload.get("task_definitions") or []
        # Same enrichment the server-pull path uses — resolve deadlines and
        # synthesise not-yet-started tasks — but run once here, against fresh data.
        enrich_tasks(tasks, task_defs)
        append_missing_tasks(tasks, task_defs)
        # DB lookup wins over client-supplied unit_code so the extension can't
        # inject an arbitrary label; fall back to the payload when the project row
        # hasn't been upserted yet.
        unit_code = get_unit_code(user_id, project_id) or payload.get("unit_code") or ""
        stored = upsert_tasks(user_id, project_id, unit_code, tasks)
        return {"ok": True, "stored": stored}

    if kind == "feedback":
        project_id = payload.get("project_id")
        task_def_id = payload.get("task_def_id")
        if project_id is None or task_def_id is None:
            return {"ok": False, "error": "missing ids"}, 400
        comments = payload.get("comments")
        text = extract_latest_feedback(comments, payload.get("student_id"))
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
        recently_days = max(1, int(data.get("recently_completed_days", 7)))
        max_todo = max(1, int(data.get("max_todo_tasks", 10)))
        # The brief send-time settings (hour/minute/day) are only present on a
        # deliberate Settings save — the auto re-link on every popup open omits them,
        # so we must NOT reset the user's choice. Parse to None when absent and
        # resolve against the stored value below.
        _raw_hour = data.get("brief_hour")
        brief_hour = max(0, min(23, int(_raw_hour))) if _raw_hour is not None else None
        _raw_minute = data.get("brief_minute")
        brief_minute = max(0, min(59, int(_raw_minute))) if _raw_minute is not None else None
        brief_dow = _normalize_dow(data.get("brief_dow"))
        brief_days = _clamp_brief_days(data["brief_days"]) if "brief_days" in data else None
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

    # Resolve each send-time field against the stored value so a bare popup-open
    # auto-link (which omits them) never silently resets the user's schedule. Only a
    # deliberate Settings save carries them.
    stored_hour = existing.get("brief_hour", 8) if existing else 8
    stored_minute = existing.get("brief_minute", 0) if existing else 0
    stored_dow = (existing.get("brief_dow") if existing else None) or "mon-fri"
    resolved_hour = brief_hour if brief_hour is not None else stored_hour
    resolved_minute = brief_minute if brief_minute is not None else stored_minute
    resolved_dow = brief_dow if brief_dow is not None else stored_dow

    user_id = upsert_user(
        base_url,
        username,
        auth_token,
        email,
        resolved_hour,
        recently_completed_days=recently_days,
        max_todo_tasks=max_todo,
        clerk_user_id=clerk_id,
    )
    # Persist a body-supplied refresh_token now that the row exists — this is what
    # closes the chicken-and-egg with /refresh-credential for first-time users.
    if body_refresh_token:
        set_refresh_token(username, body_refresh_token)

    # Enforce one OnTrack login per account. If another Clerk account previously
    # linked this same OnTrack username, it left a duplicate row; /ingest (keyed on
    # username alone) could then write to it instead of this account, so the
    # snapshot — resolved by Clerk id — would show nothing. Evict those stale rows
    # (and their captured data) now that this account holds the username, and drop
    # their orphaned brief jobs. Idempotent: a no-op once there's a single row.
    for evicted_id in reclaim_ontrack_username(username, user_id):
        job_id = f"brief_{evicted_id}"
        if scheduler.get_job(job_id):
            scheduler.remove_job(job_id)
        log.info(
            "link-ontrack: reclaimed username %s for user %s — evicted duplicate account %s",
            username,
            user_id,
            evicted_id,
        )

    # Apply deliberate brief-window / send-time changes from the Settings panel in a
    # single UPDATE. Each value is None unless explicitly provided, so the auto
    # re-link (which omits them) can't clobber a saved choice; folding them into one
    # write keeps a Settings save to a single touch of the contended user row.
    if brief_days is not None or brief_minute is not None or brief_dow is not None:
        update_brief_prefs(
            username,
            brief_days=brief_days,
            brief_minute=brief_minute,
            brief_dow=brief_dow,
        )

    # An explicit "Enable email briefs" click resumes a paused subscription.
    if send_now:
        set_subscribed(email, True)

    # Only (re)schedule for an active subscription. A paused user re-linking on a
    # bare popup open must NOT be silently resubscribed — keep their creds warm so
    # the snapshot works, but leave briefs off until they click enable.
    if send_now or not was_paused:
        schedule_brief(user_id, resolved_hour, resolved_minute, resolved_dow)
        if is_first_link or send_now:
            _schedule_welcome_brief(user_id)
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
    try:
        days_count = min(14, max(1, int(data.get("days", 7))))
    except (ValueError, TypeError):
        days_count = 7

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
        if is_hidden(r):
            continue
        deadline = r.get("deadline") or ""
        if not deadline:
            continue
        try:
            offset = (date.fromisoformat(deadline) - today).days
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
                "due_date": deadline,
                "url": f"{base_url}/projects/{r.get('project_id', '')}/dashboard/{abbrev}",
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
                "url": f"{base_url}/projects/{r.get('project_id', '')}/dashboard/{abbrev}",
            }
        )

    response_data = {
        # None when no data has been captured yet — avoids a misleading "just now"
        # timestamp on a cold-start response.
        "generated_at": last_seen,
        "has_data": task_count > 0,
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
