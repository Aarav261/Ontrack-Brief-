"""Send a brief immediately — no scheduler, no delay.

Usage:
    python test_send_now.py
"""

from __future__ import annotations

import configparser
import logging
import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from builder import build_brief_direct
from constants import CONFIG_PATH
from db import get_all_users
from fetcher import fetch_active_projects_direct, TokenExpiredError
from mailer import send_brief_to

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger(__name__)

def main() -> None:
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

    # Find the subscriber matching the config recipient, fall back to first user
    u = next((u for u in users if u["email"] == test_email), users[0])

    base_url   = u["base_url"]
    auth_token = u["auth_token"]
    username   = u["username"]

    log.info("Sending brief for %s to %s", username, test_email)
    log.info("Token (last 8): ...%s", auth_token[-8:] if auth_token else "NONE")

    try:
        projects, fresh_token = fetch_active_projects_direct(base_url, auth_token, username)
        if fresh_token != auth_token:
            log.info("Token rotated — was ...%s, now ...%s", auth_token[-6:], fresh_token[-6:])
        if not projects:
            log.warning("No active projects found — nothing to send.")
            sys.exit(0)
        log.info("Found %d active project(s)", len(projects))

        brief = build_brief_direct(base_url, fresh_token, username, projects)
        from renderer import render_html
        html = render_html(brief, projects, date.today())
        ok = send_brief_to(html, test_email, date.today(), cfg)
        if ok:
            log.info("✓ Brief sent to %s", test_email)
        else:
            log.error("✗ SMTP delivery failed — check logs above.")
            sys.exit(1)
    except TokenExpiredError as exc:
        log.error("✗ Token expired: %s — re-subscribe via the bookmarklet.", exc)
        sys.exit(1)
    except Exception as exc:
        log.error("✗ Failed: %s", exc, exc_info=True)
        sys.exit(1)


if __name__ == "__main__":
    main()
