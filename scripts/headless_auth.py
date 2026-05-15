"""Keep an OnTrack session alive indefinitely using a headless browser.

Flow:
  1. First run — opens a visible window so you can log in (SSO + MFA as normal).
     Once you press Enter, the session is saved to disk and the browser goes headless.
  2. Subsequent runs — skips login entirely, reuses the saved session headlessly.

The headless browser pings the OnTrack API on a set interval to rotate the
token and pushes each new token to your running OnTracker app.

Requirements (one-time setup):
    pip install playwright
    playwright install chromium

Usage:
    python scripts/headless_auth.py --username s224378345
    python scripts/headless_auth.py --username s224378345 --app-url http://localhost:8000
    python scripts/headless_auth.py --username s224378345 --relogin   # force fresh login
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import sys
from pathlib import Path

import requests as _requests

sys.path.insert(0, str(Path(__file__).parent.parent))

log = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

DEFAULT_BASE_URL  = "https://ontrack.deakin.edu.au"
DEFAULT_APP_URL   = "http://localhost:8000"
DEFAULT_PING_SECS = 300

SESSION_FILE = Path(__file__).parent / ".ontrack_session.json"
LS_KEYS = ["auth_token", "authToken", "doubtfire.auth_token"]


def _push_token(app_url: str, username: str, token: str) -> None:
    try:
        r = _requests.post(
            f"{app_url.rstrip('/')}/refresh-token",
            json={"username": username, "auth_token": token},
            timeout=5,
        )
        if r.ok:
            log.info("Pushed token to app  ...%s", token[-8:])
        else:
            log.warning("App rejected token push: %s %s", r.status_code, r.text[:120])
    except _requests.RequestException as exc:
        log.warning("Could not reach app at %s: %s", app_url, exc)


async def _grab_token(page) -> str | None:
    """Try localStorage keys then an in-page fetch."""
    for key in LS_KEYS:
        try:
            val = await page.evaluate(f"() => localStorage.getItem({key!r})")
            if val and isinstance(val, str) and len(val) > 8:
                if val.startswith("{"):
                    obj = json.loads(val)
                    t = obj.get("auth_token") or obj.get("authToken") or obj.get("token")
                    if t:
                        return t
                else:
                    return val
        except Exception:
            pass

    try:
        result = await page.evaluate("""async () => {
            const r = await fetch('/api/projects', {credentials: 'include'});
            return r.headers.get('Auth-Token') || r.headers.get('auth-token') || null;
        }""")
        if result:
            return result
    except Exception:
        pass

    return None


async def _login_and_save_session(base_url: str, pw) -> None:
    """Open a visible browser, let the user log in, save session to disk."""
    log.info("Opening browser for login (SSO + MFA as normal)...")
    browser = await pw.chromium.launch(headless=False)
    context = await browser.new_context()
    page    = await context.new_page()
    await page.goto(base_url)

    loop = asyncio.get_event_loop()
    log.info("Log in as normal. When you see the OnTrack dashboard, press Enter here.")
    await loop.run_in_executor(None, input, "")

    await context.storage_state(path=str(SESSION_FILE))
    log.info("Session saved to %s", SESSION_FILE)
    await browser.close()


async def _run_headless(base_url: str, username: str, app_url: str, ping_interval: int, pw) -> None:
    """Run the keep-alive loop in a headless browser using the saved session."""
    log.info("Starting headless browser with saved session...")
    browser = await pw.chromium.launch(headless=True)
    context = await browser.new_context(storage_state=str(SESSION_FILE))
    page    = await context.new_page()

    current_token: list[str | None] = [None]

    def _on_token(token: str) -> None:
        if token == current_token[0]:
            return
        current_token[0] = token
        _push_token(app_url, username, token)

    # Passive header capture
    async def _handle_request(request) -> None:
        try:
            t = (request.headers.get("auth-token") or request.headers.get("Auth-Token"))
            if t:
                _on_token(t)
        except Exception:
            pass

    async def _handle_response(response) -> None:
        try:
            t = (response.headers.get("auth-token") or response.headers.get("Auth-Token"))
            if t:
                _on_token(t)
        except Exception:
            pass

    page.on("request",  _handle_request)
    page.on("response", _handle_response)

    await page.goto(base_url)

    # Initial token grab
    token = await _grab_token(page)
    if token:
        _on_token(token)
        log.info("Initial token captured: ...%s", token[-8:])
    else:
        log.warning("Could not capture initial token — session may have expired. Re-run with --relogin.")

    log.info("Headless. Pinging every %ds. Press Ctrl+C to stop.", ping_interval)

    while True:
        await asyncio.sleep(ping_interval)
        log.info("Pinging OnTrack...")
        try:
            result = await page.evaluate("""async () => {
                const r = await fetch('/api/projects', {credentials: 'include'});
                return {
                    status: r.status,
                    token:  r.headers.get('Auth-Token') || r.headers.get('auth-token') || null
                };
            }""")
            status = result.get("status") if result else "?"
            token  = result.get("token")  if result else None

            if status in (401, 419):
                log.warning("Session expired (HTTP %s). Re-run with --relogin.", status)
                await browser.close()
                sys.exit(1)

            log.info("Ping OK (status %s)", status)
            if token:
                _on_token(token)

            # Persist the updated session (rotated cookies) to disk
            await context.storage_state(path=str(SESSION_FILE))

        except Exception as exc:
            log.warning("Ping error: %s", exc)


async def run(base_url: str, username: str, app_url: str, ping_interval: int, relogin: bool) -> None:
    try:
        from playwright.async_api import async_playwright
    except ImportError:
        log.error("Playwright not installed. Run:  pip install playwright && playwright install chromium")
        sys.exit(1)

    async with async_playwright() as pw:
        if relogin or not SESSION_FILE.exists():
            await _login_and_save_session(base_url, pw)
        else:
            log.info("Found saved session (%s) — skipping login.", SESSION_FILE)

        await _run_headless(base_url, username, app_url, ping_interval, pw)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--username",      required=True,             help="Your OnTrack username")
    parser.add_argument("--base-url",      default=DEFAULT_BASE_URL)
    parser.add_argument("--app-url",       default=DEFAULT_APP_URL)
    parser.add_argument("--ping-interval", type=int, default=DEFAULT_PING_SECS)
    parser.add_argument("--relogin",       action="store_true",       help="Force a fresh login even if a session exists")
    args = parser.parse_args()

    try:
        asyncio.run(run(args.base_url, args.username, args.app_url, args.ping_interval, args.relogin))
    except KeyboardInterrupt:
        log.info("Stopped.")


if __name__ == "__main__":
    main()
