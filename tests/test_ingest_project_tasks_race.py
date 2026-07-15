"""
Regression test for the project_tasks/projects ingest ordering race.

A returning student's current-trimester "project_tasks" push can reach
/ingest before that trimester's "projects" push has been stored (they are
independent, concurrent requests from the extension). The project_tasks
handler used to reject any project_id absent from the `projects` table as
"inactive", silently dropping a currently-enrolled unit's tasks. This test
pins the fix: a project_tasks push for a project not yet in `projects`
must be stored, not skipped.
"""

import os
import sys
import tempfile
import types
from pathlib import Path
from unittest.mock import MagicMock

import pytest

PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

# Stub out heavyweight/external-service imports the same way
# test_refresh_token_expiry.py does, so importing app/routes doesn't need
# real Postgres/Resend/Clerk/Sentry configuration.
ext_mod = types.ModuleType("extensions")
ext_mod.scheduler = MagicMock()
ext_mod.limiter = MagicMock()
ext_mod.limiter.limit.return_value = lambda f: f
sys.modules["extensions"] = ext_mod

sys.modules.setdefault("resend", MagicMock())
sys.modules.setdefault("jwt", MagicMock())

crypto_mod = types.ModuleType("core.crypto")
crypto_mod.encrypt = lambda x: f"ENC:{x}"
crypto_mod.decrypt = lambda x: x[4:] if x and x.startswith("ENC:") else (x or "")
sys.modules["core.crypto"] = crypto_mod


@pytest.fixture()
def client(monkeypatch):
    """A Flask test client backed by a fresh, throwaway SQLite DB per test."""
    db_fd, db_path = tempfile.mkstemp(suffix=".db")
    os.close(db_fd)
    os.remove(db_path)  # let init_db() create it fresh
    monkeypatch.setenv("DB_PATH", db_path)
    monkeypatch.setenv("SECRET_KEY", "test-secret")
    monkeypatch.setenv("RESEND_API_KEY", "test-key")
    monkeypatch.setenv("RESEND_FROM_EMAIL", "test@example.com")

    # core.db reads DB_PATH at import time, so import it only now.
    for mod in ("core.db", "app", "routes.main"):
        sys.modules.pop(mod, None)
    import core.db as db

    db.init_db()
    db.upsert_user(
        base_url="https://ontrack.deakin.edu.au",
        username="s1234567",
        auth_token="tok",
        email="student@test.com",
    )

    from app import create_app

    flask_app = create_app()
    flask_app.config["TESTING"] = True
    with flask_app.test_client() as c:
        yield c


def test_project_tasks_stored_when_projects_row_not_yet_landed(client):
    """The race case: project_tasks for a unit arrives before that unit's row
    has been upserted into `projects` at all (a brand-new/first-ever ingest).
    This must be stored, not skipped."""
    resp = client.post(
        "/ingest",
        json={
            "username": "s1234567",
            "kind": "project_tasks",
            "payload": {
                "project_id": 555,
                "unit_code": "SIT999",
                "tasks": [
                    {
                        "task_definition_id": 1,
                        "status": "not_started",
                        "task_definition": {"id": 1, "name": "Task 1", "target_grade": 3},
                    }
                ],
                "task_definitions": [{"id": 1, "name": "Task 1", "target_grade": 3}],
            },
        },
    )
    data = resp.get_json()
    assert resp.status_code == 200, data
    assert data.get("skipped") is None, f"push was skipped, should have been stored: {data}"
    assert data.get("stored", 0) >= 1, f"expected at least one task stored: {data}"


def test_project_tasks_stored_when_stale_projects_from_other_unit_exist(client):
    """The real-world race: an OLD trimester's project is still in `projects`
    (its own ingest hasn't pruned it yet) when the NEW trimester's project_tasks
    push lands first. The new project_id is absent from the old active set —
    this must not be treated as "inactive"."""
    import core.db as db

    user = db.get_user_by_username("s1234567")
    old_project = {
        "project_id": 111,
        "unit_code": "SIT100",
        "unit_name": "Old Unit",
        "unit_end_date": "2020-01-01",
    }
    db.upsert_projects(user["id"], [old_project])

    resp = client.post(
        "/ingest",
        json={
            "username": "s1234567",
            "kind": "project_tasks",
            "payload": {
                "project_id": 222,  # the new unit — not yet in `projects`
                "unit_code": "SIT200",
                "tasks": [
                    {
                        "task_definition_id": 9,
                        "status": "not_started",
                        "task_definition": {"id": 9, "name": "Task 9", "target_grade": 3},
                    }
                ],
                "task_definitions": [{"id": 9, "name": "Task 9", "target_grade": 3}],
            },
        },
    )
    data = resp.get_json()
    assert resp.status_code == 200, data
    assert data.get("skipped") is None, f"current unit's push was skipped: {data}"
    assert data.get("stored", 0) >= 1, f"expected the new unit's task to be stored: {data}"
