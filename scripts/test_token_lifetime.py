"""Poll OnTrack every N seconds and report when the token expires.

Usage:
    python scripts/test_token_lifetime.py --token <your_token> --username <you>
    python scripts/test_token_lifetime.py --token <your_token> --username <you> --interval 60
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

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger(__name__)

DEFAULT_BASE_URL = "https://ontrack.deakin.edu.au"
DEFAULT_INTERVAL = 30  # seconds


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
    args = parser.parse_args()

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
                log.error("Check #%d [+%s] — TOKEN EXPIRED", checks, elapsed_str)
                log.error("Token lasted approximately %s", elapsed_str)
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
