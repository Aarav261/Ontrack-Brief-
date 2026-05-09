"""OnTracker web app — token-paste setup + scheduled email briefs."""

from __future__ import annotations

import configparser
import logging
import os
import secrets
import sys
import urllib.parse
from datetime import date, datetime, timedelta
from pathlib import Path

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.date import DateTrigger
from flask import Flask, redirect, render_template, request, url_for
from flask_cors import CORS

sys.path.insert(0, str(Path(__file__).parent))

from builder import build_brief_direct
from constants import CONFIG_PATH
from db import get_all_users, init_db, remove_user, upsert_user
from fetcher import fetch_active_projects_direct, validate_token, TokenExpiredError, get_last_seen_token
from mailer import send_brief_to, send_reauth_email
from renderer import render_html

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger(__name__)

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY") or secrets.token_hex(32)
CORS(app, resources={r"/refresh-token": {"origins": "*"}})

scheduler = BackgroundScheduler(daemon=True)


# ---------------------------------------------------------------------------
# Brief runner (called by scheduler)
# ---------------------------------------------------------------------------

def _run_brief(base_url: str, auth_token: str, username: str, email: str,
               user_id: int | None = None) -> None:
    try:
        projects, fresh_token = fetch_active_projects_direct(base_url, auth_token, username)
        if fresh_token != auth_token:
            log.info("Token rotated for %s — updating DB", username)
            upsert_user(base_url, username, fresh_token, email)
        if not projects:
            return
        brief = build_brief_direct(base_url, fresh_token, username, projects)
        # build_brief_direct makes many API calls, each rotating the token.
        # Save the final token so _refresh_all_tokens doesn't see a stale one.
        final_token = get_last_seen_token() or fresh_token
        if final_token != fresh_token:
            upsert_user(base_url, username, final_token, email)
            if user_id is not None:
                job = scheduler.get_job(f"brief_{user_id}")
                if job:
                    args = list(job.args)
                    args[1] = final_token
                    job.modify(args=args)
        html  = render_html(brief, projects, date.today())
        cfg   = configparser.ConfigParser()
        cfg.read(CONFIG_PATH)
        send_brief_to(html, email, date.today(), cfg)
    except TokenExpiredError:
        log.warning("Token expired for %s — removing and notifying", email)
        if user_id is not None and scheduler.get_job(f"brief_{user_id}"):
            scheduler.remove_job(f"brief_{user_id}")
        remove_user(email)
        cfg = configparser.ConfigParser()
        cfg.read(CONFIG_PATH)
        app_url = os.environ.get("APP_URL", "http://localhost:5001/")
        send_reauth_email(email, app_url, cfg)
    except Exception as exc:
        log.error("Brief generation failed for %s: %s", email, exc, exc_info=True)


# ---------------------------------------------------------------------------
# Scheduler helpers
# ---------------------------------------------------------------------------

def _refresh_all_tokens() -> None:
    """Single consolidated job — reads fresh from DB every 20 min for all users."""
    cfg     = configparser.ConfigParser()
    cfg.read(CONFIG_PATH)
    app_url = os.environ.get("APP_URL", "http://localhost:5001/")

    for user in get_all_users():
        try:
            valid, fresh_token = validate_token(
                user["base_url"], user["auth_token"], user["username"]
            )
        except Exception as exc:
            # OnTrack service is down or unreachable — skip silently, retry next cycle
            log.warning("OnTrack unreachable for %s (service may be down): %s", user["username"], exc)
            continue
        if not valid:
            log.warning("Token expired for %s — notifying and removing", user["username"])
            if scheduler.get_job(f"brief_{user['id']}"):
                scheduler.remove_job(f"brief_{user['id']}")
            remove_user(user["email"])
            send_reauth_email(user["email"], app_url, cfg)
            continue
        if fresh_token != user["auth_token"]:
            log.info("Token rotated for %s — updating DB + job args", user["username"])
            upsert_user(user["base_url"], user["username"], fresh_token,
                        user["email"], user["brief_hour"])
            job = scheduler.get_job(f"brief_{user['id']}")
            if job:
                args = list(job.args)
                args[1] = fresh_token
                job.modify(args=args)


def _schedule(user_id: int, base_url: str, auth_token: str, username: str,
               email: str, brief_hour: int) -> None:
    job_id = f"brief_{user_id}"
    if scheduler.get_job(job_id):
        scheduler.remove_job(job_id)
    scheduler.add_job(
        _run_brief,
        CronTrigger(day_of_week="mon-fri", hour=brief_hour, minute=0),
        args=[base_url, auth_token, username, email, user_id],
        id=job_id,
        misfire_grace_time=3600,
    )
    # Ensure the single global refresh job exists
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

    # ---- helpers shared by both paths ----
    preamble = (
        "(function(){"
        "var b=window.location.origin;"
        f"var dest='{dest}';"
        # grab username/email from readable cookies (non-HttpOnly)
        "var u=null;"
        "document.cookie.split(';').forEach(function(c){"
        "var kv=c.trim().split('=');"
        "var n=kv[0].trim();"
        "if(n==='username'||n==='email'){"
        "u=u||decodeURIComponent(kv.slice(1).join('=').trim());"
        "}"
        "});"
    )

    # ---- primary: same exchange the CLI does ----
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

    # ---- fallback: scan localStorage / sessionStorage ----
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
def setup():
    base_url   = request.form["base_url"].rstrip("/")
    username   = request.form["username"].strip()
    auth_token = request.form["auth_token"].strip()
    email      = request.form["email"].strip()
    brief_hour = max(0, min(23, int(request.form.get("brief_hour", 8))))

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

    user_id = upsert_user(base_url, username, auth_token, email, brief_hour)
    _schedule(user_id, base_url, auth_token, username, email, brief_hour)

    # Send a first brief 2 minutes after sign-up via the scheduler (tests the scheduler path)
    scheduler.add_job(
        _run_brief,
        DateTrigger(run_date=datetime.now() + timedelta(seconds=10)),
        args=[base_url, auth_token, username, email, user_id],
        id=f"welcome_{user_id}",
        replace_existing=True,
    )
    log.info("First brief for %s scheduled in 2 minutes", email)

    return render_template("success.html", email=email, hour=brief_hour)


@app.route("/refresh-token", methods=["POST"])
def refresh_token():
    """Called by the browser extension on every OnTrack page load."""
    data       = request.get_json(silent=True) or {}
    username   = data.get("username", "").strip()
    auth_token = data.get("auth_token", "").strip()
    if not username or not auth_token:
        return {"ok": False, "error": "missing fields"}, 400
    for user in get_all_users():
        if user["username"] == username:
            if user["auth_token"] != auth_token:
                upsert_user(user["base_url"], username, auth_token,
                            user["email"], user["brief_hour"])
                # Propagate fresh token to both scheduled jobs
                for jid in (f"brief_{user['id']}", f"refresh_{user['id']}"):
                    job = scheduler.get_job(jid)
                    if job:
                        args = list(job.args)
                        args[1] = auth_token  # auth_token is always index 1
                        job.modify(args=args)
                log.info("Token refreshed via extension for %s", username)
            return {"ok": True}
    return {"ok": False, "error": "not subscribed"}, 404


@app.route("/unsubscribe/<path:email>")
def unsubscribe(email: str):
    # find user_id to cancel the scheduled job
    for user in get_all_users():
        if user["email"] == email:
            job_id = f"brief_{user['id']}"
            if scheduler.get_job(job_id):
                scheduler.remove_job(job_id)
            break
    remove_user(email)
    return render_template("unsubscribed.html", email=email)


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    try:
        init_db()
    except Exception as exc:
        log.error("Database initialisation failed: %s", exc, exc_info=True)
        sys.exit(1)

    try:
        for user in get_all_users():
            _schedule(user["id"], user["base_url"], user["auth_token"],
                      user["username"], user["email"], user["brief_hour"])
    except Exception as exc:
        log.error("Failed to restore scheduled jobs: %s", exc, exc_info=True)

    scheduler.start()
    port = int(os.environ.get("PORT", 5001))
    app.run(debug=False, host="0.0.0.0", port=port)
