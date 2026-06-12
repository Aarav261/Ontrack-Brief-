"""Set the Clerk instance's allowed origins (incl. the Chrome extension).

Clerk only honours frontend requests from origins on this allowlist. The
extension runs at a chrome-extension:// origin Clerk doesn't know yet, so the
popup's synced-session calls are rejected until it's added here.

Reads CLERK_SECRET_KEY from the repo-root .env.dev (never printed). Run:

    venv/Scripts/python.exe scripts/clerk_set_allowed_origins.py

Note: Clerk's PATCH replaces the whole allowed_origins list, so this sends the
full set we need (extension + web app, dev + prod).
"""

from __future__ import annotations

import pathlib
import re
import sys

import requests

EXTENSION_ID = "gkbemcnnekeadcpikdcfhedifdglihbn"

ALLOWED_ORIGINS = [
    f"chrome-extension://{EXTENSION_ID}",
    "http://localhost:5173",
    "https://on-tracker.com",
]


def _secret_key() -> str:
    env = pathlib.Path(__file__).parent.parent / ".env.dev"
    text = env.read_text(encoding="utf-8")
    keys = dict(re.findall(r"^([A-Z_]+)=(.*)$", text, re.M))
    key = (keys.get("CLERK_SECRET_KEY") or "").strip()
    if not key:
        sys.exit("CLERK_SECRET_KEY is not set in .env.dev")
    return key


def main() -> None:
    resp = requests.patch(
        "https://api.clerk.com/v1/instance",
        headers={
            "Authorization": f"Bearer {_secret_key()}",
            "Content-Type": "application/json",
        },
        json={"allowed_origins": ALLOWED_ORIGINS},
        timeout=15,
    )
    if resp.status_code in (200, 204):
        print("allowed_origins updated to:")
        for o in ALLOWED_ORIGINS:
            print("  -", o)
    else:
        sys.exit(f"Clerk API error {resp.status_code}: {resp.text}")


if __name__ == "__main__":
    main()
