#!/usr/bin/env python3
"""OnTrack Morning Brief — daily prioritised task summary via email."""

from __future__ import annotations

import argparse
import configparser
import sys
import tempfile
import webbrowser
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))  # project root

from core.builder import build_brief
from core.constants import CONFIG_PATH
from core.fetcher import fetch_active_projects
from core.mailer import send_email
from core.renderer import render_html
from scripts.scheduler import setup_cron


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Generate and send a prioritised OnTrack task brief.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "examples:\n"
            "  brief.py --preview          open brief in browser (no email)\n"
            "  brief.py                    send brief via email\n"
            "  brief.py --schedule         install 8am weekday cron job\n"
            "  brief.py --schedule --hour 7  install 7am weekday cron job\n"
        ),
    )
    parser.add_argument("--preview",  action="store_true", help="Open in browser instead of emailing")
    parser.add_argument("--schedule", action="store_true", help="Install cron job and exit")
    parser.add_argument("--hour",     type=int, default=8, help="Hour for cron schedule (default: 8)")
    args = parser.parse_args()

    if args.schedule:
        setup_cron(hour=args.hour)
        return

    cfg = configparser.ConfigParser()
    recently_days = 7
    max_todo      = 10
    if CONFIG_PATH.exists():
        cfg.read(CONFIG_PATH)
        recently_days = cfg.getint("brief", "recently_completed_days", fallback=7)
        max_todo      = cfg.getint("brief", "max_todo_tasks",          fallback=10)

    today = date.today()
    print("Fetching active projects...")
    projects = fetch_active_projects()

    if not projects:
        print("No active projects found. Check that ontrack is authenticated.")
        return

    print(f"Units: {', '.join(p['unit']['code'] for p in projects)}")
    brief = build_brief(projects, recently_days)
    html  = render_html(brief, projects, today, max_todo)

    if args.preview:
        tmp = Path(tempfile.mktemp(suffix=".html"))
        tmp.write_text(html, encoding="utf-8")
        webbrowser.open(f"file://{tmp}")
        print("Preview opened in browser.")
        return

    if not CONFIG_PATH.exists():
        print(f"\nNo config found at: {CONFIG_PATH}")
        print("Copy config.ini.template → config.ini and fill in your Gmail details.")
        print("Or run with --preview to see the brief without email.\n")
        return

    if "email" not in cfg:
        print("config.ini is missing the [email] section.")
        return

    send_email(html, cfg, today)


if __name__ == "__main__":
    main()
