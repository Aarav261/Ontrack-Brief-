"""OnTrack data fetching — CLI subprocess and direct API calls."""

from __future__ import annotations

import json
import logging
import pathlib
import subprocess
import sys
from datetime import date

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

log = logging.getLogger(__name__)

# Shared HTTP session with automatic retry on transient errors
_http = requests.Session()
_retry = Retry(total=3, backoff_factor=0.5, status_forcelist={429, 500, 502, 503, 504}, read=0)
_http.mount("https://", HTTPAdapter(max_retries=_retry))
_http.mount("http://", HTTPAdapter(max_retries=_retry))

# Doubtfire rotates Auth-Token on every response. We capture the latest value
# here so callers can retrieve it after any sequence of API calls.
_last_seen_token: list[str] = []   # list so it's mutable from the closure

def _capture_token(r: requests.Response, **_kwargs) -> None:
    token = r.headers.get("Auth-Token") or r.headers.get("auth-token") or r.headers.get("x-auth-token")
    if token:
        if _last_seen_token:
            _last_seen_token[0] = token
        else:
            _last_seen_token.append(token)

_http.hooks["response"].append(_capture_token)


def get_last_seen_token() -> str | None:
    """Return the most-recently seen Auth-Token across all API calls, or None."""
    return _last_seen_token[0] if _last_seen_token else None


# ---------------------------------------------------------------------------
# Direct API helpers (used by the web app — no ontrack CLI dependency)
# ---------------------------------------------------------------------------

def _headers(auth_token: str, username: str) -> dict:
    return {"Username": username, "Auth-Token": auth_token, "Accept": "application/json"}


class TokenExpiredError(Exception):
    """Raised when the OnTrack API rejects credentials (401/419)."""


def validate_token(base_url: str, auth_token: str, username: str) -> tuple[bool, str]:
    """Return (is_valid, current_token).

    Doubtfire rotates auth_token on each request and returns the new value
    in the Auth-Token response header.  We capture it so the DB stays fresh.
    """
    try:
        r = _http.get(
            f"{base_url}/api/unit_roles",
            headers=_headers(auth_token, username),
            timeout=10,
        )
        if r.status_code != 200:
            return False, auth_token
        refreshed = (
            r.headers.get("Auth-Token")
            or r.headers.get("auth-token")
            or r.headers.get("x-auth-token")
            or auth_token
        )
        log.debug("validate_token: stored=%s…  refreshed=%s…", auth_token[-6:], refreshed[-6:])
        return True, refreshed
    except requests.RequestException:
        raise  # let caller distinguish service-down from token-expired


def fetch_active_projects_direct(
    base_url: str, auth_token: str, username: str
) -> tuple[list[dict], str]:
    """Return (projects, current_token) — token may be refreshed by the server."""
    r = _http.get(
        f"{base_url}/api/projects",
        headers=_headers(auth_token, username),
        timeout=15,
    )
    if r.status_code in (401, 419):
        raise TokenExpiredError(f"OnTrack rejected credentials (HTTP {r.status_code})")
    r.raise_for_status()
    refreshed = (
        r.headers.get("Auth-Token")
        or r.headers.get("auth-token")
        or r.headers.get("x-auth-token")
        or auth_token
    )
    today = date.today()
    projects = [p for p in r.json() if date.fromisoformat(p["unit"]["end_date"]) >= today]
    return projects, refreshed


def fetch_tasks_direct(base_url: str, auth_token: str, username: str, project_id: int) -> list[dict]:
    r = _http.get(
        f"{base_url}/api/projects/{project_id}",
        headers=_headers(auth_token, username),
        timeout=15,
    )
    r.raise_for_status()
    data  = r.json()
    tasks = data.get("tasks", [])

    # task_definitions are not embedded in the project response — fetch the full unit separately
    # (mirrors what ontrack-cli does: get_project() + get_unit(item.unit.id))
    unit_id = data.get("unit_id") or (data.get("unit") or {}).get("id")
    task_defs = []
    if unit_id:
        try:
            unit_r = _http.get(
                f"{base_url}/api/units/{unit_id}",
                headers=_headers(auth_token, username),
                timeout=15,
            )
            unit_r.raise_for_status()
            task_defs = unit_r.json().get("task_definitions", [])
        except requests.RequestException as exc:
            log.warning("Could not fetch unit %s for task_definitions: %s", unit_id, exc)
    else:
        log.warning("No unit_id found in project %s response — task names will be blank", project_id)

    td_by_id = {td["id"]: td for td in task_defs}
    for t in tasks:
        td = td_by_id.get(t["task_definition_id"], {})
        t["abbreviation"]       = t.get("abbreviation") or td.get("abbreviation", "")
        t["name"]               = t.get("name") or td.get("name", "")
        t["target_grade"]       = t.get("target_grade") if t.get("target_grade") is not None else td.get("target_grade")
        t["target_grade_label"] = _GRADE_LABELS.get(t["target_grade"], "P (Pass)")
        t["due_date"]           = t.get("due_date") or td.get("target_date") or td.get("due_date")
        t["deadline"]           = t.get("deadline") or td.get("due_date")
        t["status_label"]       = t.get("status_label") or t.get("status", "").replace("_", " ").title()

    submitted_def_ids = {t["task_definition_id"] for t in tasks}
    today = date.today().isoformat()

    for td in task_defs:
        if td["id"] in submitted_def_ids:
            continue
        if td.get("start_date", "0000") > today:
            continue
        tasks.append({
            "id":                 None,
            "task_definition_id": td["id"],
            "abbreviation":       td["abbreviation"],
            "name":               td["name"],
            "status":             "not_started",
            "status_label":       "Not Started",
            "target_grade":       td.get("target_grade"),
            "target_grade_label": _GRADE_LABELS.get(td.get("target_grade"), "P (Pass)"),
            "due_date":           td.get("target_date") or td.get("due_date"),
            "deadline":           td.get("due_date"),
            "submission_date":    None,
            "completion_date":    None,
            "extensions":         0,
            "grade":              None,
            "is_overdue":         False,
        })

    return tasks


def fetch_last_feedback_direct(
    base_url: str,
    auth_token: str,
    username: str,
    project_id: int,
    task_def_id: int,
    student_id: int | None,
) -> str | None:
    url = f"{base_url}/api/projects/{project_id}/task_def_id/{task_def_id}/comments"
    try:
        r = _http.get(url, headers=_headers(auth_token, username), timeout=10)
        r.raise_for_status()
    except requests.RequestException as exc:
        log.warning("Could not fetch feedback for task_def %s: %s", task_def_id, exc)
        return None

    comments = r.json()
    if not isinstance(comments, list):
        return None

    for comment in reversed(comments):
        if comment.get("type") != "text":
            continue
        author_id = (comment.get("author") or {}).get("id")
        if author_id and author_id == student_id:
            continue
        text = (comment.get("comment") or "").strip()
        if text:
            return text

    return None

_GRADE_LABELS = {0: "P (Pass)", 1: "C (Credit)", 2: "D (Distinction)", 3: "HD (High Distinction)"}


def _run_ontrack(cmd: list[str]) -> list | dict:
    result = subprocess.run(["ontrack"] + cmd, capture_output=True, text=True)
    if result.returncode != 0:
        print(f"ontrack error: {result.stderr.strip()}", file=sys.stderr)
        sys.exit(1)
    return json.loads(result.stdout)


def fetch_active_projects() -> list[dict]:
    today = date.today()
    projects = _run_ontrack(["projects", "--json"])
    return [p for p in projects if date.fromisoformat(p["unit"]["end_date"]) >= today]


def fetch_tasks(project_id: int) -> list[dict]:
    data = _run_ontrack(["project", str(project_id), "--json"])
    tasks = data["tasks"]

    submitted_def_ids = {t["task_definition_id"] for t in tasks}
    today = date.today().isoformat()

    for td in data["unit"]["task_definitions"]:
        if td["id"] in submitted_def_ids:
            continue
        if td.get("start_date", "0000") > today:
            continue
        tasks.append({
            "id":                 None,
            "task_definition_id": td["id"],
            "abbreviation":       td["abbreviation"],
            "name":               td["name"],
            "status":             "not_started",
            "status_label":       "Not Started",
            "target_grade":       td.get("target_grade"),
            "target_grade_label": _GRADE_LABELS.get(td.get("target_grade"), "P (Pass)"),
            "due_date":           td.get("target_date") or td.get("due_date"),
            "deadline":           td.get("due_date"),
            "submission_date":    None,
            "completion_date":    None,
            "extensions":         0,
            "grade":              None,
            "is_overdue":         False,
        })

    return tasks


def load_api_auth() -> tuple[str, dict, int | None]:
    """Return (base_url, headers, student_id) using the ontrack CLI's stored auth."""
    try:
        from ontrack_cli.config import load_auth_config  # type: ignore
    except ImportError:
        candidates = [
            *pathlib.Path(__file__).parent.glob(".venv/lib/python*/site-packages"),
            *pathlib.Path.home().glob(".local/share/uv/tools/ontrack-cli/lib/python*/site-packages"),
        ]
        if not candidates:
            print("Could not locate ontrack-cli. Activate the project venv or install via uv.", file=sys.stderr)
            sys.exit(1)
        sys.path.insert(0, str(candidates[0]))
        from ontrack_cli.config import load_auth_config  # type: ignore

    auth = load_auth_config()
    headers = {
        "Username":   auth.username,
        "Auth-Token": auth.auth_token,
        "Accept":     "application/json",
    }
    student_id = auth.cached_user.id if auth.cached_user else None
    return auth.base_url, headers, student_id


_API_AUTH: tuple | None = None


def _api_auth() -> tuple[str, dict, int | None]:
    global _API_AUTH
    if _API_AUTH is None:
        _API_AUTH = load_api_auth()
    return _API_AUTH


def fetch_task_sheet(unit_id: int, task_def_id: int) -> bytes | None:
    """Return the task sheet PDF bytes, or None if unavailable."""
    base_url, headers, _ = _api_auth()
    url = f"{base_url}/api/units/{unit_id}/task_definitions/{task_def_id}/task_pdf.json"

    try:
        r = _http.get(url, headers={**headers, "Accept": "*/*"},
                      params={"as_attachment": "true"}, timeout=15)
        r.raise_for_status()
    except requests.RequestException:
        return None

    if r.content[:4] != b"%PDF":
        return None
    return r.content


def fetch_submission(project_id: int, task_def_id: int) -> tuple[bytes, str] | None:
    """Return (pdf_bytes, filename) for the latest submission, or None if unavailable."""
    base_url, headers, _ = _api_auth()
    url = f"{base_url}/api/projects/{project_id}/task_def_id/{task_def_id}/submission"

    try:
        r = _http.get(url, headers={**headers, "Accept": "*/*"},
                      params={"as_attachment": "true"}, timeout=15)
        r.raise_for_status()
    except requests.RequestException:
        return None

    if r.content[:4] != b"%PDF":
        return None

    disposition = r.headers.get("Content-Disposition", "")
    filename = disposition.split("filename=")[-1].strip() if "filename=" in disposition else f"{task_def_id}.pdf"
    return r.content, filename


def fetch_last_feedback(project_id: int, task_def_id: int) -> str | None:
    """Return the most recent tutor text comment, or None."""
    base_url, headers, student_id = _api_auth()
    url = f"{base_url}/api/projects/{project_id}/task_def_id/{task_def_id}/comments"

    try:
        r = _http.get(url, headers=headers, timeout=10)
        r.raise_for_status()
    except requests.RequestException as exc:
        log.warning("Could not fetch feedback for task_def %s: %s", task_def_id, exc)
        return None

    comments = r.json()
    if not isinstance(comments, list):
        return None

    for comment in reversed(comments):
        if comment.get("type") != "text":
            continue
        author_id = (comment.get("author") or {}).get("id")
        if author_id and author_id == student_id:
            continue
        text = (comment.get("comment") or "").strip()
        if text:
            return text

    return None
