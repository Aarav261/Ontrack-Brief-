"""Centralized handling of Doubtfire's rotating auth token.

Doubtfire rotates the Auth-Token on *every* response, so authentication here is
not a fetch-and-cache flow (as with an OAuth client) but a continuous chase:
read the rotated token off each response and persist it. This module is the
single owner of that lifecycle — header building, token extraction, validation,
session creation with rotation capture, and write-back to the DB.

A `TokenManager` wraps one user's auth context (base URL, username, current
token) plus an isolated requests session whose response hook captures each
rotation into ``self.token``. Construct one per brief run / request so
concurrent jobs never clobber each other's tokens.
"""

from __future__ import annotations

import logging

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from core.db import upsert_user

log = logging.getLogger(__name__)

# Retry transient failures at the transport layer.
RETRY = Retry(
    total=3, backoff_factor=0.5, status_forcelist={429, 500, 502, 503, 504}, read=0
)

# Doubtfire returns the rotated token in one of these response headers.
_TOKEN_HEADERS = ("Auth-Token", "auth-token", "x-auth-token")

# Statuses that mean the token itself is rejected (vs. a transient server error).
_AUTH_REJECTED = (401, 403, 419)


class TokenExpiredError(Exception):
    """Raised when the OnTrack API rejects credentials (401/419)."""


class RefreshTokenError(Exception):
    """Raised when minting a fresh auth_token from a refresh_token fails."""


def mint_auth_token(
    base_url: str,
    refresh_token: str,
    username: str,
    *,
    session: requests.Session | None = None,
) -> tuple[str, dict]:
    """Exchange a durable ``refresh_token`` for a fresh, short-lived ``auth_token``.

    This is the proper fix for overnight expiry: instead of hoarding the rotating
    auth_token (hours-long life, dies while idle), we hold the long-lived
    refresh_token cookie OnTrack issues at SSO login and mint a fresh auth_token
    on demand — e.g. right before each brief.

    Mirrors ontrack-cli's browser flow: POST the ``refresh_token`` *and*
    ``username`` as cookies to ``/api/auth/access-token`` with
    ``delete_auth_token=False`` so minting does NOT invalidate the token the
    user's browser is currently holding (no rotation race). Both cookies are
    required — verified against OnTrack: refresh_token alone returns HTTP 201
    with a ``null`` body. Returns ``(auth_token, user_dict)``.

    Raises RefreshTokenError if OnTrack rejects the refresh_token or the response
    is missing an auth_token — callers treat that as "refresh_token expired, ask
    the user to re-open OnTrack" (the extension will push a fresh one).
    """
    base_url = (base_url or "").rstrip("/")
    domain = _cookie_domain(base_url)
    http = session or new_session()
    # The endpoint authenticates off the cookies, not headers. Both are required:
    # refresh_token alone yields a 201 with a null body (no user resolved).
    http.cookies.set("refresh_token", refresh_token, domain=domain)
    http.cookies.set("username", username, domain=domain)

    try:
        r = http.post(
            f"{base_url}/api/auth/access-token",
            json={"delete_auth_token": False},
            timeout=15,
        )
    except requests.RequestException as exc:
        raise RefreshTokenError(f"OnTrack unreachable while minting token: {exc}") from exc

    if r.status_code in _AUTH_REJECTED:
        raise RefreshTokenError(
            f"OnTrack rejected the refresh_token (HTTP {r.status_code}) — likely expired"
        )
    if not r.ok:
        raise RefreshTokenError(f"OnTrack returned HTTP {r.status_code} on token mint")

    payload = r.json() if r.content else None
    if not isinstance(payload, dict):
        # OnTrack returns HTTP 201 + a literal ``null`` body when the
        # refresh_token/username pair resolves to no session — i.e. the
        # refresh_token has expired. Treat as a re-auth signal.
        raise RefreshTokenError(
            "OnTrack returned no session for the refresh_token — likely expired"
        )

    auth_token = (
        payload.get("auth_token")
        or payload.get("access_token")
        or payload.get("token")
    )
    if not auth_token:
        raise RefreshTokenError("Token mint succeeded but no auth_token in response")

    user = payload.get("user") if isinstance(payload.get("user"), dict) else {}
    log.info("Minted fresh auth_token from refresh_token (…%s)", auth_token[-6:])
    return auth_token, user


def _cookie_domain(base_url: str) -> str:
    """Bare hostname for cookie scoping (no scheme/port)."""
    from urllib.parse import urlparse

    return urlparse(base_url).hostname or ""


def extract_token(
    response: requests.Response, fallback: str | None = None
) -> str | None:
    """Return the rotated Auth-Token from a Doubtfire response, or ``fallback``.

    Single source of truth for reading the rotating token off a response — every
    code path goes through here so the header lookup never drifts.
    """
    for header in _TOKEN_HEADERS:
        token = response.headers.get(header)
        if token:
            return token
    return fallback


def auth_headers(auth_token: str, username: str) -> dict:
    """Build the Username/Auth-Token headers every Doubtfire request needs."""
    return {
        "Username": username,
        "Auth-Token": auth_token,
        "Accept": "application/json",
    }


def new_session(*, capture=None) -> requests.Session:
    """Create a requests session with retry adapters.

    If ``capture`` is given it is registered as a response hook — used by
    TokenManager to capture the rotated token off every response.
    """
    session = requests.Session()
    adapter = HTTPAdapter(max_retries=RETRY)
    session.mount("https://", adapter)
    session.mount("http://", adapter)
    if capture is not None:
        session.hooks["response"].append(capture)
    return session


class TokenManager:
    """Owns one user's rotating Doubtfire token and its isolated session.

    Doubtfire rotates the Auth-Token on every response; the session's response
    hook captures each rotation into ``self.token``. Build one per brief run /
    request so concurrent jobs never overwrite each other's tokens.
    """

    def __init__(
        self,
        base_url: str,
        username: str,
        auth_token: str,
        *,
        session: requests.Session | None = None,
    ):
        self.base_url = (base_url or "").rstrip("/")
        self.username = username
        self.token = auth_token
        # Own a capturing session unless the caller supplied one.
        self.session = session or new_session(capture=self._capture)

    @classmethod
    def for_user(
        cls, user: dict, *, session: requests.Session | None = None
    ) -> "TokenManager":
        """Build a TokenManager from a DB user row."""
        return cls(
            user["base_url"], user["username"], user["auth_token"], session=session
        )

    def _capture(self, response: requests.Response, **_kwargs) -> None:
        token = extract_token(response)
        if token:
            self.token = token

    @property
    def headers(self) -> dict:
        return auth_headers(self.token, self.username)

    def validate(self) -> bool:
        """Return True if OnTrack accepts the current token, capturing any rotation.

        Only an auth-rejection status (401/403/419) reports the token as invalid.
        Any other non-2xx is a transient/service problem and is raised, so callers
        treat it as "OnTrack unreachable" rather than pausing briefs and emailing a
        re-auth prompt over a server hiccup. RequestException propagates the same way.
        """
        r = self.session.get(
            f"{self.base_url}/api/unit_roles", headers=self.headers, timeout=10
        )
        if r.status_code in _AUTH_REJECTED:
            return False
        if not r.ok:
            raise requests.HTTPError(
                f"OnTrack returned HTTP {r.status_code}", response=r
            )
        log.debug(
            "validate: token for %s accepted (…%s)", self.username, self.token[-6:]
        )
        return True

    def persist(self, user: dict) -> str:
        """Write the current token back to the DB if it rotated since ``user``.

        Returns the current token. No-op when the token is unchanged, so callers
        can call it unconditionally after a batch of requests.
        """
        if self.token and self.token != user["auth_token"]:
            log.info("Token rotated for %s — updating DB", self.username)
            upsert_user(
                self.base_url,
                self.username,
                self.token,
                user["email"],
                brief_hour=user.get("brief_hour", 8),
                recently_completed_days=user.get("recently_completed_days", 7),
                max_todo_tasks=user.get("max_todo_tasks", 10),
            )
        return self.token
