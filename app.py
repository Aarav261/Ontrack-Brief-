"""OnTracker web app — token-paste setup + scheduled email briefs."""

from __future__ import annotations

import configparser
import sys
import threading
import urllib.parse
from datetime import date
from pathlib import Path

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from flask import Flask, redirect, render_template, request, url_for

sys.path.insert(0, str(Path(__file__).parent))

from builder import build_brief_direct
from constants import CONFIG_PATH
from db import get_all_users, init_db, remove_user, upsert_user
from fetcher import fetch_active_projects_direct, validate_token
from mailer import send_brief_to
from renderer import render_html

app = Flask(__name__)
app.secret_key = "ontracker-change-in-prod"

scheduler = BackgroundScheduler(daemon=True)


# ---------------------------------------------------------------------------
# Brief runner (called by scheduler)
# ---------------------------------------------------------------------------

def _run_brief(base_url: str, auth_token: str, username: str, email: str) -> None:
    try:
        projects = fetch_active_projects_direct(base_url, auth_token, username)
        if not projects:
            return
        brief = build_brief_direct(base_url, auth_token, username, projects)
        html  = render_html(brief, projects, date.today())
        cfg   = configparser.ConfigParser()
        cfg.read(CONFIG_PATH)
        send_brief_to(html, email, date.today(), cfg)
    except Exception as exc:
        print(f"[brief error] {email}: {exc}")


# ---------------------------------------------------------------------------
# Scheduler helpers
# ---------------------------------------------------------------------------

def _schedule(user_id: int, base_url: str, auth_token: str, username: str,
               email: str, brief_hour: int) -> None:
    job_id = f"brief_{user_id}"
    if scheduler.get_job(job_id):
        scheduler.remove_job(job_id)
    scheduler.add_job(
        _run_brief,
        CronTrigger(day_of_week="mon-fri", hour=brief_hour, minute=0),
        args=[base_url, auth_token, username, email],
        id=job_id,
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
    brief_hour = int(request.form.get("brief_hour", 8))

    if not validate_token(base_url, auth_token, username):
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

    threading.Thread(
        target=_run_brief,
        args=[base_url, auth_token, username, email],
        daemon=True,
    ).start()

    return render_template("success.html", email=email, hour=brief_hour)


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
    init_db()
    for user in get_all_users():
        _schedule(user["id"], user["base_url"], user["auth_token"],
                  user["username"], user["email"], user["brief_hour"])
    scheduler.start()
    app.run(debug=False, host="0.0.0.0", port=5001)
