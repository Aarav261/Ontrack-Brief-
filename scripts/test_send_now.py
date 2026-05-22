"""Send a brief immediately — no scheduler, no delay.

Usage:
    python scripts/test_send_now.py
    python scripts/test_send_now.py --token <paste-token-from-popup>
"""

from __future__ import annotations

import argparse
import configparser
import logging
import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))  # project root

from core.brief import build_brief_direct, pending_due_entries, render_html
from core.constants import CONFIG_PATH
from core.db import get_all_users, upsert_user
from core.mailer import send_brief_to
from core.ontrack import fetch_active_projects_direct, TokenExpiredError

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger(__name__)

def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--token", help="Override the auth token from the DB (paste from popup)")
    args = parser.parse_args()

    cfg = configparser.ConfigParser()
    cfg.read(CONFIG_PATH)
    try:
        test_email = cfg["email"]["recipient"]
    except KeyError:
        log.error("Missing [email] recipient in config.ini")
        sys.exit(1)

    users = get_all_users()
    if not users:
        log.error("No subscribers in database. Subscribe via the web app first.")
        sys.exit(1)

    u = next((u for u in users if u["email"] == test_email), users[0])

    base_url   = u["base_url"]
    auth_token = args.token.strip() if args.token else u["auth_token"]
    username   = u["username"]

    if args.token:
        log.info("Using token from --token argument")

    log.info("Sending brief for %s to %s", username, test_email)
    log.info("Token (last 8): ...%s", auth_token[-8:] if auth_token else "NONE")

    try:
        projects, fresh_token = fetch_active_projects_direct(base_url, auth_token, username)
        if fresh_token != auth_token:
            log.info("Token rotated — was ...%s, now ...%s", auth_token[-6:], fresh_token[-6:])
            upsert_user(base_url, username, fresh_token, u["email"], u["brief_hour"])

        if not projects:
            log.warning("No active projects found — nothing to send.")
            sys.exit(0)
        log.info("Found %d active project(s)", len(projects))

        brief = build_brief_direct(base_url, fresh_token, username, projects)
        final_token = get_last_seen_token() or fresh_token
        if final_token != fresh_token:
            log.info("Token rotated after build — saving ...%s", final_token[-6:])
            upsert_user(base_url, username, final_token, u["email"], u["brief_hour"])
        today = date.today()
        pending_due = pending_due_entries(brief, today, 14)
        due_this_week = len(pending_due_entries(brief, today, 6))
        html = render_html(pending_due, today, window_days=14)
        ok = send_brief_to(html, test_email, today, due_this_week)
        if ok:
            log.info("✓ Brief sent to %s", test_email)
        else:
            log.error("✗ SMTP delivery failed — check logs above.")
            sys.exit(1)
    except TokenExpiredError:
        log.error("✗ Token expired — open OnTrack so the extension can capture a fresh token.")
        sys.exit(1)
    except Exception as exc:
        log.error("✗ Failed: %s", exc, exc_info=True)
        sys.exit(1)


if __name__ == "__main__":
    main()
