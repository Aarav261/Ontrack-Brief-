"""OnTrack integration — rotating-token auth, data shaping, and the fetch client.

Public API for the rest of the app; internals live in `auth.py`, `fetcher.py`,
and `normalize.py`.
"""

from .auth import (
    RefreshTokenError,
    TokenExpiredError,
    TokenManager,
    auth_headers,
    extract_token,
    mint_auth_token,
    new_session,
)
from .fetcher import (
    fetch_active_projects_direct,
    fetch_last_feedback_direct,
    fetch_tasks_direct,
    validate_token,
)
from .normalize import append_missing_tasks, enrich_tasks, extract_latest_feedback

__all__ = [
    "RefreshTokenError",
    "TokenExpiredError",
    "TokenManager",
    "auth_headers",
    "extract_token",
    "mint_auth_token",
    "new_session",
    "fetch_active_projects_direct",
    "fetch_last_feedback_direct",
    "fetch_tasks_direct",
    "validate_token",
    "append_missing_tasks",
    "enrich_tasks",
    "extract_latest_feedback",
]
