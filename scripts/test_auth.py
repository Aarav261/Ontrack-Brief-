"""Test the OnTrack POST /api/auth endpoint with remember=true.

Usage:
    python scripts/test_auth.py --username <you> --password <pw>
    python scripts/test_auth.py --username <you> --password <pw> --base-url https://ontrack.example.edu.au
"""

from __future__ import annotations

import argparse
import getpass
import json
import logging
import sys
from pathlib import Path

import requests

sys.path.insert(0, str(Path(__file__).parent.parent))

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger(__name__)

DEFAULT_BASE_URL = "https://ontrack.deakin.edu.au"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--username", required=True, help="OnTrack username")
    parser.add_argument("--password", help="OnTrack password / auth_token (prompted if omitted)")
    parser.add_argument("--base-url", default=DEFAULT_BASE_URL, help="OnTrack base URL")
    args = parser.parse_args()

    password = args.password or getpass.getpass("Password: ")
    url = f"{args.base_url.rstrip('/')}/api/auth"

    payload = {
        "username": args.username,
        "auth_token": password,
        "remember": True,
    }

    log.info("POST %s  (username=%s, remember=true)", url, args.username)

    try:
        resp = requests.post(url, json=payload, timeout=15)
    except requests.exceptions.RequestException as exc:
        log.error("Request failed: %s", exc)
        sys.exit(1)

    log.info("Status: %d", resp.status_code)

    try:
        data = resp.json()
    except ValueError:
        log.error("Non-JSON response body:\n%s", resp.text[:500])
        sys.exit(1)

    print(json.dumps(data, indent=2))

    token = data.get("auth_token") or data.get("access_token") or data.get("token")
    if token:
        log.info("Token (last 8): ...%s", token[-8:])
    else:
        log.warning("No token field found in response — keys: %s", list(data.keys()))

    if not resp.ok:
        sys.exit(1)


if __name__ == "__main__":
    main()
