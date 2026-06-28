"""
Tests: what happens when the refresh_token expires?

Scenarios covered:
  1. mint_auth_token() raises RefreshTokenError on HTTP 401/403/419
  2. mint_auth_token() raises RefreshTokenError on null (None) JSON body
  3. mint_auth_token() propagates requests.HTTPError on 5xx (transient)
  4. mint_auth_token() propagates RequestException on network failure
  5. /link-ontrack returns refresh_expired JSON when refresh_token is expired
  6. run_brief() still sends an email even when refresh_token is expired
     (the morning brief is now purely DB-driven — no OnTrack call)
  7. run_brief() sends briefs-enabled confirmation on cold start (confirm_if_empty=True)
  8. run_brief() stays silent on cold start daily cron (confirm_if_empty=False)
"""

import sys
import types
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

# ---------------------------------------------------------------------------
# Path setup
# ---------------------------------------------------------------------------
PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

# Stub out heavyweight imports before any project modules are imported.
# Order matters: these must be in sys.modules before 'from core.xxx import ...'

# --- Stub 'extensions' (APScheduler scheduler singleton) ---
ext_mod = types.ModuleType("extensions")
ext_mod.scheduler = MagicMock()
ext_mod.limiter = MagicMock()
# @limiter.limit(...) is used as a route decorator; make it a pass-through so the
# real view functions (and their __name__) survive blueprint registration.
ext_mod.limiter.limit.return_value = lambda f: f
sys.modules["extensions"] = ext_mod

# --- Stub 'resend' (email SDK) ---
sys.modules.setdefault("resend", MagicMock())

# --- Stub jwt / PyJWKClient (Clerk) ---
jwt_mod = MagicMock()
sys.modules.setdefault("jwt", jwt_mod)

# --- Stub 'core.crypto' so DB works without a real encryption key ---
crypto_mod = types.ModuleType("core.crypto")
crypto_mod.encrypt = lambda x: f"ENC:{x}"
crypto_mod.decrypt = lambda x: x[4:] if x and x.startswith("ENC:") else (x or "")
sys.modules["core.crypto"] = crypto_mod

# ---------------------------------------------------------------------------
# Now import project modules. These intentionally follow the sys.modules stubs
# above, so the import-order lint rule (E402) is suppressed here on purpose.
# ---------------------------------------------------------------------------
import requests  # noqa: E402

from core.ontrack.auth import RefreshTokenError, mint_auth_token  # noqa: E402


# ---------------------------------------------------------------------------
# Helper: build a mock requests.Response
# ---------------------------------------------------------------------------
def _mock_response(status_code: int, json_data=None, content: bytes = b""):
    r = MagicMock(spec=requests.Response)
    r.status_code = status_code
    r.ok = 200 <= status_code < 300
    if json_data is not None:
        r.content = b"x"
        r.json.return_value = json_data
    else:
        r.content = content
        r.json.side_effect = ValueError("no content")
    return r


# ===========================================================================
# 1. mint_auth_token — HTTP 401/403/419 → RefreshTokenError
# ===========================================================================

@pytest.mark.parametrize("status_code", [401, 403, 419])
def test_mint_auth_token_raises_on_auth_rejected(status_code):
    """OnTrack returns an auth-rejection status -> RefreshTokenError (not transient)."""
    session = MagicMock()
    session.post.return_value = _mock_response(status_code, content=b"Unauthorized")

    with pytest.raises(RefreshTokenError, match="rejected"):
        mint_auth_token(
            "https://ontrack.deakin.edu.au",
            "fake-refresh-token",
            "s1234567",
            session=session,
        )


# ===========================================================================
# 2. mint_auth_token — null (None) JSON body → RefreshTokenError
# ===========================================================================

def test_mint_auth_token_raises_on_null_body():
    """OnTrack 201 + literal null body (no session resolved) -> RefreshTokenError."""
    session = MagicMock()
    resp = MagicMock(spec=requests.Response)
    resp.status_code = 201
    resp.ok = True
    resp.content = b"null"
    resp.json.return_value = None   # null JSON body
    session.post.return_value = resp

    with pytest.raises(RefreshTokenError, match="no session"):
        mint_auth_token(
            "https://ontrack.deakin.edu.au",
            "expired-refresh-token",
            "s1234567",
            session=session,
        )


# ===========================================================================
# 3. mint_auth_token — 5xx → raises requests.HTTPError (transient, NOT expiry)
# ===========================================================================

def test_mint_auth_token_5xx_is_transient_not_expiry():
    """A 5xx from OnTrack must NOT raise RefreshTokenError.
    It should raise requests.HTTPError so callers can retry."""
    session = MagicMock()
    resp = MagicMock(spec=requests.Response)
    resp.status_code = 503
    resp.ok = False
    resp.content = b""
    session.post.return_value = resp

    with pytest.raises(requests.HTTPError):
        mint_auth_token(
            "https://ontrack.deakin.edu.au",
            "valid-refresh-token",
            "s1234567",
            session=session,
        )


# ===========================================================================
# 4. mint_auth_token — network timeout → propagates RequestException
# ===========================================================================

def test_mint_auth_token_timeout_propagates_not_expiry():
    """A connection timeout must NOT be treated as token expiry."""
    session = MagicMock()
    session.post.side_effect = requests.ConnectionError("timed out")

    with pytest.raises(requests.RequestException):
        mint_auth_token(
            "https://ontrack.deakin.edu.au",
            "valid-refresh-token",
            "s1234567",
            session=session,
        )


# ===========================================================================
# 5. /link-ontrack endpoint → returns refresh_expired when token is dead
# ===========================================================================

def test_link_ontrack_returns_refresh_expired_error():
    """/link-ontrack must return HTTP 401 + {error:'refresh_expired', hint:'open_ontrack'}
    when mint_auth_token raises RefreshTokenError (the refresh_token has expired)."""
    fake_user = {
        "id": 1,
        "base_url": "https://ontrack.deakin.edu.au",
        "username": "s1234567",
        "email": "student@test.com",
        "auth_token": "old-token",
        "refresh_token": "expired-token",
        "token_valid": 1,
        "brief_hour": 8,
        "recently_completed_days": 7,
        "max_todo_tasks": 10,
        "subscribed": 1,
        "token_fail_count": 0,
        "brief_days": 14,
    }

    with (
        patch("routes.main.get_user_by_clerk_id", return_value=None),
        patch("routes.main.get_user_by_username", return_value=fake_user),
        patch("routes.main.mint_auth_token",
              side_effect=RefreshTokenError("OnTrack rejected the refresh_token — likely expired")),
        patch("core.clerk_auth.verify_session_token",
              return_value={"sub": "clerk_abc", "email": "student@test.com"}),
    ):
        from app import create_app
        flask_app = create_app()
        flask_app.config["TESTING"] = True

        with flask_app.test_client() as client:
            resp = client.post(
                "/link-ontrack",
                json={
                    "username": "s1234567",
                    "auth_token": "old-scraped-token",
                    "refresh_token": "expired-token",
                },
                headers={"Authorization": "Bearer fake-clerk-jwt"},
            )
            data = resp.get_json()
            assert resp.status_code == 401, \
                f"Expected 401 on expired refresh_token, got {resp.status_code}: {data}"
            assert data.get("error") == "refresh_expired", \
                f"Expected error='refresh_expired', got: {data}"
            assert data.get("hint") == "open_ontrack", \
                f"Expected hint='open_ontrack', got: {data}"


# ===========================================================================
# 6. run_brief() — still sends email even when refresh_token is expired
#    (brief is purely DB-driven — no OnTrack / mint call happens)
# ===========================================================================

def test_run_brief_sends_email_regardless_of_token_expiry():
    """The morning brief must go out from stored DB tasks regardless of token state.
    An expired refresh_token has zero effect on the daily email."""
    from datetime import date

    from core import jobs as _jobs

    fake_user = {
        "id": 42,
        "email": "student@test.com",
        "base_url": "https://ontrack.deakin.edu.au",
        "username": "s1234567",
        "subscribed": 1,
        "brief_days": 14,
        "brief_hour": 8,
        "recently_completed_days": 7,
        "max_todo_tasks": 10,
        "refresh_token": "EXPIRED",   # token is dead
        "auth_token": "stale-token",
        "token_valid": 0,             # marked invalid
    }

    fake_tasks = [
        {
            "user_id": 42,
            "project_id": 10,
            "task_def_id": 1,
            "abbreviation": "1.1P",
            "name": "Setup task",
            "unit_code": "SIT374",
            "target_grade_label": "P (Pass)",
            "deadline": "2099-12-31",
            "status": "not_started",
            "feedback_text": None,
            "feedback_seen_at": None,
            "last_seen": "2024-01-01T08:00:00",
        }
    ]

    fake_entries = [{
        "abbreviation": "1.1P",
        "name": "Setup task",
        "unit_code": "SIT374",
        "status": "not_started",
        "due": date(2099, 12, 31),
        "deadline_iso": "2099-12-31",
        "link": None,
        "grade": None,
        "target_grade_label": "P (Pass)",
        "feedback_text": None,
    }]

    with (
        patch("core.jobs.get_user_by_id", return_value=fake_user),
        patch("core.jobs.get_capture_meta", return_value=(1, "2024-01-01T08:00:00")),
        patch("core.jobs.get_pending_tasks", return_value=fake_tasks),
        patch("core.jobs.send_brief_to", return_value=True) as mock_send,
        patch("core.jobs.render_html", return_value="<html>brief</html>"),
        patch("core.brief.pending_task_entries", return_value=fake_entries),
    ):
        _jobs.run_brief(42, confirm_if_empty=False)

    assert mock_send.called, \
        "BUG: send_brief_to was NOT called even though tasks exist and only token expired!"
    assert mock_send.call_args[0][1] == "student@test.com", \
        "Email sent to wrong address"


# ===========================================================================
# 7. run_brief() — sends briefs-enabled confirmation on cold start
# ===========================================================================

def test_run_brief_sends_confirmation_on_cold_start_with_explicit_enable():
    """When confirm_if_empty=True and no captured tasks (cold start), must send
    the briefs-enabled confirmation — not silently skip."""
    from core import jobs as _jobs

    fake_user = {
        "id": 1,
        "email": "new@test.com",
        "base_url": "https://ontrack.deakin.edu.au",
        "username": "s0000001",
        "subscribed": 1,
        "brief_days": 14,
        "brief_hour": 8,
        "recently_completed_days": 7,
        "max_todo_tasks": 10,
        "refresh_token": None,
        "auth_token": "token",
        "token_valid": 1,
        "token_fail_count": 0,
    }

    with (
        patch("core.jobs.get_user_by_id", return_value=fake_user),
        patch("core.jobs.get_capture_meta", return_value=(0, None)),
        patch("core.jobs.send_briefs_enabled_email", return_value=True) as mock_confirm,
        patch("core.jobs.send_brief_to") as mock_brief,
    ):
        _jobs.run_brief(1, confirm_if_empty=True)

    assert mock_confirm.called, \
        "BUG: briefs-enabled confirmation email was NOT sent on cold start!"
    assert not mock_brief.called, \
        "send_brief_to should NOT be called when there are no tasks"


# ===========================================================================
# 8. run_brief() — daily cron stays silent on cold start
# ===========================================================================

def test_run_brief_silent_on_cold_start_daily_cron():
    """Daily cron (confirm_if_empty=False) must stay silent when no tasks captured yet."""
    from core import jobs as _jobs

    fake_user = {
        "id": 1,
        "email": "new@test.com",
        "base_url": "https://ontrack.deakin.edu.au",
        "username": "s0000001",
        "subscribed": 1,
        "brief_days": 14,
        "brief_hour": 8,
        "recently_completed_days": 7,
        "max_todo_tasks": 10,
        "refresh_token": None,
        "auth_token": "token",
        "token_valid": 1,
        "token_fail_count": 0,
    }

    with (
        patch("core.jobs.get_user_by_id", return_value=fake_user),
        patch("core.jobs.get_capture_meta", return_value=(0, None)),
        patch("core.jobs.send_briefs_enabled_email") as mock_confirm,
        patch("core.jobs.send_brief_to") as mock_brief,
    ):
        _jobs.run_brief(1, confirm_if_empty=False)

    assert not mock_confirm.called, "send_briefs_enabled_email should NOT fire on daily cron"
    assert not mock_brief.called, "send_brief_to should NOT fire on cold start"
