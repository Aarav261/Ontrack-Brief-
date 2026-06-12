"""Poll OnTrack every N seconds and report when the token expires.

Built to measure the token's *absolute* lifetime: leave it running overnight
with the browser closed (so nothing else rotates the token) and read off how
long the token survives on poll-only refreshes. Use --log to capture the result
to a file so it survives a closed terminal.

Usage:
    python scripts/test_token_lifetime.py --token <your_token> --username <you>
    python scripts/test_token_lifetime.py --token <your_token> --username <you> --interval 300
    python scripts/test_token_lifetime.py --token <your_token> --username <you> --interval 300 --log token_lifetime.log
"""

from __future__ import annotations

import argparse
import logging
import sys
import time
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from core.ontrack import validate_token

log = logging.getLogger(__name__)

DEFAULT_BASE_URL = "https://ontrack.deakin.edu.au"
DEFAULT_INTERVAL = 30  # seconds


def _configure_logging(log_path: str | None) -> None:
    fmt = "%(asctime)s %(levelname)s %(message)s"
    handlers: list[logging.Handler] = [logging.StreamHandler(sys.stdout)]
    if log_path:
        # Append + flush each line so an overnight run's result is on disk even
        # if the terminal dies or the process is killed mid-poll.
        handlers.append(logging.FileHandler(log_path, mode="a", encoding="utf-8"))
    logging.basicConfig(level=logging.INFO, format=fmt, handlers=handlers)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--token", required=True, help="OnTrack auth token")
    parser.add_argument("--username", required=True, help="OnTrack username")
    parser.add_argument("--base-url", default=DEFAULT_BASE_URL)
    parser.add_argument(
        "--interval",
        type=int,
        default=DEFAULT_INTERVAL,
        help=f"Poll interval in seconds (default: {DEFAULT_INTERVAL})",
    )
    parser.add_argument(
        "--log",
        metavar="PATH",
        help="Also append output to this file (for unattended overnight runs)",
    )
    args = parser.parse_args()

    _configure_logging(args.log)

    token = args.token.strip()
    started = datetime.now()
    checks = 0
    rotations = 0

    log.info(
        "Started at %s — polling every %ds", started.strftime("%H:%M:%S"), args.interval
    )
    log.info("Token (last 8): ...%s", token[-8:])
    log.info("Press Ctrl+C to stop.\n")

    try:
        while True:
            checks += 1
            try:
                valid, fresh = validate_token(args.base_url, token, args.username)
            except Exception as exc:
                log.warning("Check #%d — request error: %s", checks, exc)
                time.sleep(args.interval)
                continue

            elapsed = datetime.now() - started
            h, rem = divmod(int(elapsed.total_seconds()), 3600)
            m, s = divmod(rem, 60)
            elapsed_str = f"{h:02d}:{m:02d}:{s:02d}"

            if not valid:
                now = datetime.now()
                log.error("Check #%d [+%s] — TOKEN EXPIRED", checks, elapsed_str)
                log.error(
                    "Token lasted ~%s (started %s, died ~%s) across %d poll-only "
                    "checks at %ds intervals — polling did NOT extend its lifetime",
                    elapsed_str,
                    started.strftime("%Y-%m-%d %H:%M:%S"),
                    now.strftime("%Y-%m-%d %H:%M:%S"),
                    checks,
                    args.interval,
                )
                sys.exit(0)

            if fresh != token:
                rotations += 1
                log.info(
                    "Check #%d [+%s] — valid, token ROTATED (rotation #%d)  ...%s -> ...%s",
                    checks,
                    elapsed_str,
                    rotations,
                    token[-8:],
                    fresh[-8:],
                )
                token = fresh
            else:
                log.info(
                    "Check #%d [+%s] — valid, token unchanged  ...%s",
                    checks,
                    elapsed_str,
                    token[-8:],
                )

            time.sleep(args.interval)

    except KeyboardInterrupt:
        elapsed = datetime.now() - started
        h, rem = divmod(int(elapsed.total_seconds()), 3600)
        m, s = divmod(rem, 60)
        log.info(
            "\nStopped after %02d:%02d:%02d — token was still valid (%d checks, %d rotations)",
            h,
            m,
            s,
            checks,
            rotations,
        )


if __name__ == "__main__":
    main()
