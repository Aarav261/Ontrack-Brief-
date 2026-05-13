"""OnTracker web app — token-paste setup + scheduled email briefs."""

from __future__ import annotations

import logging
import os
import secrets
import urllib.parse
from datetime import date, datetime, timedelta

from apscheduler.jobstores.sqlalchemy import SQLAlchemyJobStore
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.date import DateTrigger
from flask import Flask, redirect, render_template, request, url_for
from flask_cors import CORS
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address

from core.builder import build_brief_direct
from core.constants import URGENT, TODO, WAITING
from core.db import (get_all_users, get_sqlalchemy_url, get_user_by_username,
                     init_db, mark_token_invalid, remove_user, upsert_user)
from core.fetcher import fetch_active_projects_direct, fetch_tasks_direct, validate_token, TokenExpiredError, make_session
from core.mailer import send_brief_to, send_reauth_email
from core.renderer import render_html

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger(__name__)

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY") or secrets.token_hex(32)

CORS(app, resources={
    r"/refresh-token": {"origins": "*"},
    r"/api/snapshot":  {"origins": "*"},
})

_REDIS_URL = os.environ.get("REDIS_URL", "")
limiter = Limiter(
    get_remote_address,
    app=app,
    storage_uri=_REDIS_URL or "memory://",
    default_limits=[],
)

scheduler = BackgroundScheduler(
    daemon=True,
    jobstores={"default": SQLAlchemyJobStore(url=get_sqlalchemy_url())},
)

APP_URL = os.environ.get("APP_URL", "http://localhost:5001/")


# ---------------------------------------------------------------------------
# Brief runner (called by scheduler)
# ---------------------------------------------------------------------------

def _run_brief(base_url: str, auth_token: str, username: str, email: str,
               user_id: int | None = None,
               recently_completed_days: int = 7, max_todo_tasks: int = 10) -> None:
    try:
        # One isolated session per brief run — prevents token cross-contamination
        # between concurrent jobs (Doubtfire rotates the token on every response).
        session, token_store = make_session()

        projects, fresh_token = fetch_active_projects_direct(base_url, auth_token, username, session=session)
        if fresh_token != auth_token:
            log.info("Token rotated for %s — updating DB", username)
            upsert_user(base_url, username, fresh_token, email)
        if not projects:
            return
        brief = build_brief_direct(base_url, fresh_token, username, projects,
                                   recently_completed_days=recently_completed_days,
                                   session=session)
        final_token = token_store["last"] or fresh_token
        if final_token != fresh_token:
            upsert_user(base_url, username, final_token, email)
            if user_id is not None:
                job = scheduler.get_job(f"brief_{user_id}")
                if job:
                    args = list(job.args)
                    args[1] = final_token
                    job.modify(args=args)
        html = render_html(brief, projects, date.today(), max_todo=max_todo_tasks)
        send_brief_to(html, email, date.today())
    except TokenExpiredError:
        log.warning("Token expired for %s — pausing briefs, waiting for extension to push fresh token", email)
        if user_id is not None and scheduler.get_job(f"brief_{user_id}"):
            scheduler.remove_job(f"brief_{user_id}")
        mark_token_invalid(email)
        send_reauth_email(email, APP_URL)
    except Exception as exc:
        log.error("Brief generation failed for %s: %s", email, exc, exc_info=True)


# ---------------------------------------------------------------------------
# Scheduler helpers
# ---------------------------------------------------------------------------

def _refresh_all_tokens() -> None:
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
            log.info("Token rotated for %s — updating DB + job args", user["username"])
            upsert_user(user["base_url"], user["username"], fresh_token,
                        user["email"], user["brief_hour"],
                        recently_completed_days=user.get("recently_completed_days", 7),
                        max_todo_tasks=user.get("max_todo_tasks", 10))
            job = scheduler.get_job(f"brief_{user['id']}")
            if job:
                args = list(job.args)
                args[1] = fresh_token
                job.modify(args=args)


def _schedule(user_id: int, base_url: str, auth_token: str, username: str,
               email: str, brief_hour: int,
               recently_completed_days: int = 7, max_todo_tasks: int = 10) -> None:
    job_id = f"brief_{user_id}"
    if scheduler.get_job(job_id):
        scheduler.remove_job(job_id)
    scheduler.add_job(
        _run_brief,
        CronTrigger(day_of_week="mon-fri", hour=brief_hour, minute=0),
        args=[base_url, auth_token, username, email, user_id,
              recently_completed_days, max_todo_tasks],
        id=job_id,
        misfire_grace_time=3600,
    )
    if not scheduler.get_job("token_refresh"):
        scheduler.add_job(
            _refresh_all_tokens,
            CronTrigger(minute="*/20"),
            id="token_refresh",
            misfire_grace_time=600,
        )


# ---------------------------------------------------------------------------
# Bookmarklet generator
# ---------------------------------------------------------------------------

def _bookmarklet(setup_url: str) -> str:
    dest = setup_url.rstrip("/") + "/"

    preamble = (
        "(function(){"
        "var b=window.location.origin;"
        f"var dest='{dest}';"
        "var u=null;"
        "document.cookie.split(';').forEach(function(c){"
        "var kv=c.trim().split('=');"
        "var n=kv[0].trim();"
        "if(n==='username'||n==='email'){"
        "u=u||decodeURIComponent(kv.slice(1).join('=').trim());"
        "}"
        "});"
    )

    primary = (
        "fetch(b+'/api/auth/access-token',{"
        "method:'POST',"
        "headers:{'Content-Type':'application/json'},"
        "credentials:'include',"
        "body:JSON.stringify({delete_auth_token:false})"
        "})"
        ".then(function(r){if(!r.ok)throw new Error('HTTP '+r.status);return r.json();})"
        ".then(function(d){"
        "var t=d.auth_token||d.access_token||d.token;"
        "if(!t)throw new Error('no token');"
        "var usr=d.user||{};"
        "u=u||usr.username||usr.email||usr.firstName||'';"
        "window.location.href=dest+'?base_url='+encodeURIComponent(b)"
        "+'&username='+encodeURIComponent(u)"
        "+'&auth_token='+encodeURIComponent(t);"
        "})"
    )

    fallback = (
        ".catch(function(){"
        "var t=null;"
        "[localStorage,sessionStorage].forEach(function(store){"
        "for(var i=0;i<store.length;i++){"
        "try{"
        "var v=JSON.parse(store.getItem(store.key(i)));"
        "if(v&&typeof v==='object'){"
        "for(var p in v){"
        "var lp=p.toLowerCase();"
        "if(lp.indexOf('token')>=0&&typeof v[p]==='string'&&v[p].length>8){t=t||v[p];}"
        "if((lp==='username'||lp==='email')&&typeof v[p]==='string'){u=u||v[p];}"
        "}"
        "}"
        "}catch(e){}"
        "}"
        "});"
        "if(t){"
        "window.location.href=dest+'?base_url='+encodeURIComponent(b)"
        "+'&username='+encodeURIComponent(u||'')"
        "+'&auth_token='+encodeURIComponent(t);"
        "}else{"
        "alert('Could not get OnTrack token. Make sure you are logged in.');"
        "}"
        "});"
        "})()"
    )

    js = preamble + primary + fallback
    return "javascript:" + urllib.parse.quote(js, safe="")


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@app.route("/")
def index():
    bm = _bookmarklet(request.url_root)
    prefill = {
        "base_url":   request.args.get("base_url", ""),
        "username":   request.args.get("username", ""),
        "auth_token": request.args.get("auth_token", ""),
    }
    return render_template("index.html", bookmarklet=bm, **prefill)


@app.route("/setup", methods=["POST"])
@limiter.limit("10 per minute")
def setup():
    base_url   = request.form["base_url"].rstrip("/")
    username   = request.form["username"].strip()
    auth_token = request.form["auth_token"].strip()
    email      = request.form["email"].strip()
    brief_hour              = max(0, min(23, int(request.form.get("brief_hour", 8))))
    recently_completed_days = max(1, min(30, int(request.form.get("recently_completed_days", 7))))
    max_todo_tasks          = max(1, min(50, int(request.form.get("max_todo_tasks", 10))))

    valid, auth_token = validate_token(base_url, auth_token, username)
    if not valid:
        error = "Could not verify your OnTrack token. Check your details and try again."
        bm = _bookmarklet(request.url_root)
        return render_template(
            "index.html",
            bookmarklet=bm,
            error=error,
            base_url=base_url,
            username=username,
            auth_token=auth_token,
        ), 400

    user_id = upsert_user(base_url, username, auth_token, email, brief_hour,
                          recently_completed_days=recently_completed_days,
                          max_todo_tasks=max_todo_tasks)
    _schedule(user_id, base_url, auth_token, username, email, brief_hour,
              recently_completed_days=recently_completed_days, max_todo_tasks=max_todo_tasks)

    scheduler.add_job(
        _run_brief,
        DateTrigger(run_date=datetime.now() + timedelta(seconds=10)),
        args=[base_url, auth_token, username, email, user_id,
              recently_completed_days, max_todo_tasks],
        id=f"welcome_{user_id}",
        replace_existing=True,
    )
    log.info("First brief for %s scheduled in 10 seconds", email)

    return render_template("success.html", email=email, hour=brief_hour)


@app.route("/refresh-token", methods=["POST"])
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
        job = scheduler.get_job(f"brief_{user['id']}")
        if job:
            args = list(job.args)
            args[1] = auth_token
            job.modify(args=args)
        if was_invalid:
            log.info("Token restored for %s — re-scheduling brief", username)
            _schedule(user["id"], user["base_url"], auth_token,
                      username, user["email"], user["brief_hour"],
                      user.get("recently_completed_days", 7),
                      user.get("max_todo_tasks", 10))
        else:
            log.info("Token refreshed via extension for %s", username)

    return {"ok": True}


@app.route("/api/snapshot", methods=["POST"])
@limiter.limit("60 per minute")
def api_snapshot():
    data       = request.get_json(silent=True) or {}
    username   = (data.get("username") or "").strip()
    auth_token = (data.get("auth_token") or "").strip()
    base_url   = (data.get("base_url") or "https://ontrack.deakin.edu.au").rstrip("/")
    days_count = min(14, max(1, int(data.get("days", 7))))

    if not username or not auth_token:
        return {"error": "missing fields"}, 400

    db_user = next((u for u in get_all_users() if u["username"] == username), None)
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
        return {"error": "token expired", "hint": "open_ontrack"}, 401

    # Use a dedicated session so token capture doesn't interfere with brief jobs
    snap_session, snap_tokens = make_session()

    try:
        projects, auth_token = fetch_active_projects_direct(base_url, auth_token, username, session=snap_session)
    except TokenExpiredError:
        return {"error": "token expired"}, 401
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

    return {"generated_at": datetime.now().isoformat(timespec="seconds"), "days": days,
            "auth_token": auth_token}


@app.route("/unsubscribe/<path:email>")
def unsubscribe(email: str):
    for user in get_all_users():
        if user["email"] == email:
            job_id = f"brief_{user['id']}"
            if scheduler.get_job(job_id):
                scheduler.remove_job(job_id)
            break
    remove_user(email)
    return render_template("unsubscribed.html", email=email)


# ---------------------------------------------------------------------------
# Startup — runs at import time so gunicorn workers also initialise correctly
# ---------------------------------------------------------------------------

def _startup() -> None:
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
            _schedule(user["id"], user["base_url"], user["auth_token"],
                      user["username"], user["email"], user["brief_hour"],
                      user.get("recently_completed_days", 7), user.get("max_todo_tasks", 10))
    except Exception as exc:
        log.error("Failed to restore scheduled jobs: %s", exc, exc_info=True)

    scheduler.start()

    scheduler.add_job(
        _refresh_all_tokens,
        DateTrigger(run_date=datetime.now() + timedelta(seconds=5)),
        id="token_refresh_startup",
        replace_existing=True,
    )


_startup()


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5001))
    app.run(debug=False, host="0.0.0.0", port=port)
