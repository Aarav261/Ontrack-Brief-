"""OnTrack integration — rotating-token auth and the data-fetch client.

Public API for the rest of the app; internals live in `auth.py` and `fetcher.py`.
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
    fetch_active_projects,
    fetch_active_projects_direct,
    fetch_last_feedback,
    fetch_last_feedback_direct,
    fetch_submission,
    fetch_task_sheet,
    fetch_tasks,
    fetch_tasks_direct,
    load_api_auth,
    validate_token,
)

__all__ = [
    "RefreshTokenError",
    "TokenExpiredError",
    "TokenManager",
    "auth_headers",
    "extract_token",
    "mint_auth_token",
    "new_session",
    "fetch_active_projects",
    "fetch_active_projects_direct",
    "fetch_last_feedback",
    "fetch_last_feedback_direct",
    "fetch_submission",
    "fetch_task_sheet",
    "fetch_tasks",
    "fetch_tasks_direct",
    "load_api_auth",
    "validate_token",
]
