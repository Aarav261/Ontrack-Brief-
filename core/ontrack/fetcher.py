"""OnTrack data fetching — direct API calls.

Auth — the rotating Auth-Token, header building, validation, and write-back —
lives in the sibling `auth` module. This is the data layer that consumes it.
"""

from __future__ import annotations

import logging
from datetime import date

import requests

from .auth import (
    TokenExpiredError,
    TokenManager,
    new_session,
)
from .auth import (
    auth_headers as _headers,
)
from .auth import (
    extract_token as _extract_token,
)
from .normalize import append_missing_tasks, enrich_tasks, extract_latest_feedback

log = logging.getLogger(__name__)

# Shared session for stateless one-off calls (the feedback helper below).
# Per-user token capture is owned by core.auth.TokenManager.
_http = new_session()


def _fetch_feedback(
    task_def_id: int,
    url: str,
    headers: dict,
    student_id: int | None,
    session: requests.Session | None = None,
) -> str | None:
    http = session or _http
    try:
        r = http.get(url, headers=headers, timeout=10)
        r.raise_for_status()
    except requests.RequestException as exc:
        log.warning("Could not fetch feedback for task_def %s: %s", task_def_id, exc)
        return None
    return extract_latest_feedback(r.json(), student_id)


def validate_token(
    base_url: str,
    auth_token: str,
    username: str,
    session: requests.Session | None = None,
) -> tuple[bool, str]:
    """Backward-compatible shim: validate and return (is_valid, current_token).

    New code should use core.auth.TokenManager directly (tm.validate() / tm.token).
    Kept for the dev script `test_token_lifetime.py`.
    """
    tm = TokenManager(base_url, username, auth_token, session=session)
    return tm.validate(), tm.token


def fetch_active_projects_direct(
    base_url: str,
    auth_token: str,
    username: str,
    session: requests.Session | None = None,
) -> tuple[list[dict], str]:
    """Return (projects, current_token) — token may be refreshed by the server."""
    http = session or _http
    r = http.get(
        f"{base_url}/api/projects",
        headers=_headers(auth_token, username),
        timeout=15,
    )
    if r.status_code in (401, 419):
        raise TokenExpiredError(f"OnTrack rejected credentials (HTTP {r.status_code})")
    r.raise_for_status()
    refreshed = _extract_token(r, auth_token)
    today = date.today()
    projects = [p for p in r.json() if date.fromisoformat(p["unit"]["end_date"]) >= today]
    return projects, refreshed


def fetch_tasks_direct(
    base_url: str,
    auth_token: str,
    username: str,
    project_id: int,
    session: requests.Session | None = None,
) -> list[dict]:
    http = session or _http
    r = http.get(
        f"{base_url}/api/projects/{project_id}",
        headers=_headers(auth_token, username),
        timeout=15,
    )
    r.raise_for_status()
    data = r.json()
    tasks = data.get("tasks", [])

    unit_id = data.get("unit_id") or (data.get("unit") or {}).get("id")
    task_defs = []
    if unit_id:
        try:
            unit_r = http.get(
                f"{base_url}/api/units/{unit_id}",
                headers=_headers(auth_token, username),
                timeout=15,
            )
            unit_r.raise_for_status()
            task_defs = unit_r.json().get("task_definitions", [])
        except requests.RequestException as exc:
            log.warning("Could not fetch unit %s for task_definitions: %s", unit_id, exc)
    else:
        log.warning(
            "No unit_id found in project %s response — task names will be blank",
            project_id,
        )

    enrich_tasks(tasks, task_defs)
    append_missing_tasks(tasks, task_defs)

    return tasks


def fetch_last_feedback_direct(
    base_url: str,
    auth_token: str,
    username: str,
    project_id: int,
    task_def_id: int,
    student_id: int | None,
    session: requests.Session | None = None,
) -> str | None:
    url = f"{base_url}/api/projects/{project_id}/task_def_id/{task_def_id}/comments"
    headers = _headers(auth_token, username)
    return _fetch_feedback(task_def_id, url, headers, student_id, session=session)
