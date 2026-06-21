"""Database persistence — PostgreSQL (prod, set DATABASE_URL) or SQLite (local dev)."""

from __future__ import annotations

import logging
import os
import sqlite3
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path

from core.crypto import decrypt as _decrypt, encrypt as _encrypt

log = logging.getLogger(__name__)


def _decrypt_row(row: dict | None) -> dict | None:
    """Decrypt the at-rest credentials (auth_token, refresh_token) on a user row."""
    if row:
        if row.get("auth_token") is not None:
            row["auth_token"] = _decrypt(row["auth_token"])
        if row.get("refresh_token") is not None:
            row["refresh_token"] = _decrypt(row["refresh_token"])
    return row


_DATABASE_URL = os.environ.get("DATABASE_URL", "")
_DB_PATH = Path(
    os.environ.get("DB_PATH", str(Path(__file__).parent.parent / "ontracker.db"))
)
_USE_PG = _DATABASE_URL.startswith(("postgresql://", "postgres://"))

if _USE_PG:
    import psycopg2
    import psycopg2.extras

# SQL placeholder: %s for psycopg2, ? for sqlite3
_P = "%s" if _USE_PG else "?"


@contextmanager
def _connection():
    if _USE_PG:
        conn = psycopg2.connect(_DATABASE_URL)
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()
    else:
        conn = sqlite3.connect(_DB_PATH, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()


def init_db() -> None:
    with _connection() as conn:
        cur = conn.cursor()
        if _USE_PG:
            cur.execute("""
                CREATE TABLE IF NOT EXISTS users (
                    id                      SERIAL PRIMARY KEY,
                    base_url                TEXT NOT NULL,
                    username                TEXT NOT NULL,
                    auth_token              TEXT NOT NULL,
                    refresh_token           TEXT,
                    email                   TEXT NOT NULL UNIQUE,
                    clerk_user_id           TEXT,
                    brief_hour              INTEGER NOT NULL DEFAULT 8,
                    token_valid             INTEGER NOT NULL DEFAULT 1,
                    token_fail_count        INTEGER NOT NULL DEFAULT 0,
                    subscribed              INTEGER NOT NULL DEFAULT 1,
                    recently_completed_days INTEGER NOT NULL DEFAULT 7,
                    max_todo_tasks          INTEGER NOT NULL DEFAULT 10,
                    brief_days              INTEGER NOT NULL DEFAULT 14,
                    last_snapshot           TEXT,
                    created_at              TIMESTAMPTZ NOT NULL DEFAULT now()
                )
            """)
            # Migrate existing PG DBs
            for col, typedef in [
                ("token_valid", "INTEGER NOT NULL DEFAULT 1"),
                ("recently_completed_days", "INTEGER NOT NULL DEFAULT 7"),
                ("max_todo_tasks", "INTEGER NOT NULL DEFAULT 10"),
                ("brief_days", "INTEGER NOT NULL DEFAULT 14"),
                ("last_snapshot", "TEXT"),
                ("clerk_user_id", "TEXT"),
                ("token_fail_count", "INTEGER NOT NULL DEFAULT 0"),
                ("refresh_token", "TEXT"),
                ("subscribed", "INTEGER NOT NULL DEFAULT 1"),
            ]:
                cur.execute(f"""
                    DO $$
                    BEGIN
                        IF NOT EXISTS (SELECT 1 FROM information_schema.columns
                                       WHERE table_name='users' AND column_name='{col}') THEN
                            ALTER TABLE users ADD COLUMN {col} {typedef};
                        END IF;
                    END
                    $$;
                """)
            # Clerk identity is unique but nullable (NULLs are distinct) — index, not
            # an ADD COLUMN UNIQUE, so it works as a migration on both engines.
            cur.execute(
                "CREATE UNIQUE INDEX IF NOT EXISTS idx_users_clerk_user_id "
                "ON users(clerk_user_id)"
            )
        else:
            cur.execute("""
                CREATE TABLE IF NOT EXISTS users (
                    id                      INTEGER PRIMARY KEY AUTOINCREMENT,
                    base_url                TEXT NOT NULL,
                    username                TEXT NOT NULL,
                    auth_token              TEXT NOT NULL,
                    refresh_token           TEXT,
                    email                   TEXT NOT NULL UNIQUE,
                    clerk_user_id           TEXT,
                    brief_hour              INTEGER NOT NULL DEFAULT 8,
                    token_valid             INTEGER NOT NULL DEFAULT 1,
                    token_fail_count        INTEGER NOT NULL DEFAULT 0,
                    subscribed              INTEGER NOT NULL DEFAULT 1,
                    recently_completed_days INTEGER NOT NULL DEFAULT 7,
                    max_todo_tasks          INTEGER NOT NULL DEFAULT 10,
                    brief_days              INTEGER NOT NULL DEFAULT 14,
                    last_snapshot           TEXT,
                    created_at              TEXT NOT NULL DEFAULT (datetime('now'))
                )
            """)
            # Migrate existing SQLite DBs that predate newer columns
            cols = {r[1] for r in cur.execute("PRAGMA table_info(users)").fetchall()}
            for col, typedef in [
                ("token_valid", "INTEGER NOT NULL DEFAULT 1"),
                ("recently_completed_days", "INTEGER NOT NULL DEFAULT 7"),
                ("max_todo_tasks", "INTEGER NOT NULL DEFAULT 10"),
                ("brief_days", "INTEGER NOT NULL DEFAULT 14"),
                ("last_snapshot", "TEXT"),
                ("clerk_user_id", "TEXT"),
                ("token_fail_count", "INTEGER NOT NULL DEFAULT 0"),
                ("refresh_token", "TEXT"),
                ("subscribed", "INTEGER NOT NULL DEFAULT 1"),
            ]:
                if col not in cols:
                    cur.execute(f"ALTER TABLE users ADD COLUMN {col} {typedef}")
            # Clerk identity is unique but nullable (NULLs are distinct) — index, not
            # an ADD COLUMN UNIQUE (SQLite forbids that as a migration).
            cur.execute(
                "CREATE UNIQUE INDEX IF NOT EXISTS idx_users_clerk_user_id "
                "ON users(clerk_user_id)"
            )

        # Deterministic-brief tables (see docs/DETERMINISTIC_BRIEF_PLAN.md). The
        # extension captures OnTrack data off the student's own session and pushes
        # it here via /ingest; the morning brief reads these rows instead of calling
        # OnTrack. The column types below are valid on both PG and SQLite, so a
        # single DDL serves both engines (no at-rest credentials here → no encryption).
        cur.execute("""
            CREATE TABLE IF NOT EXISTS projects (
                user_id        INTEGER NOT NULL,
                project_id     INTEGER NOT NULL,
                unit_code      TEXT,
                unit_name      TEXT,
                unit_end_date  TEXT,
                last_seen      TEXT NOT NULL,
                PRIMARY KEY (user_id, project_id)
            )
        """)
        cur.execute("""
            CREATE TABLE IF NOT EXISTS tasks (
                user_id            INTEGER NOT NULL,
                project_id         INTEGER NOT NULL,
                task_def_id        INTEGER NOT NULL,
                abbreviation       TEXT,
                name               TEXT,
                unit_code          TEXT,
                target_grade_label TEXT,
                deadline           TEXT,
                status             TEXT,
                feedback_text      TEXT,
                feedback_seen_at   TEXT,
                last_seen          TEXT NOT NULL,
                PRIMARY KEY (user_id, project_id, task_def_id)
            )
        """)
        cur.execute(
            "CREATE INDEX IF NOT EXISTS idx_tasks_user_deadline "
            "ON tasks(user_id, deadline)"
        )


def upsert_user(
    base_url: str,
    username: str,
    auth_token: str,
    email: str,
    brief_hour: int = 8,
    token_valid: int = 1,
    recently_completed_days: int = 7,
    max_todo_tasks: int = 10,
    clerk_user_id: str | None = None,
) -> int:
    auth_token = _encrypt(auth_token)  # encrypt the bearer credential at rest
    with _connection() as conn:
        cur = conn.cursor()
        if _USE_PG:
            cur.execute(
                f"""
                INSERT INTO users (base_url, username, auth_token, email, brief_hour, token_valid,
                                   recently_completed_days, max_todo_tasks, clerk_user_id)
                VALUES ({_P}, {_P}, {_P}, {_P}, {_P}, {_P}, {_P}, {_P}, {_P})
                ON CONFLICT(email) DO UPDATE SET
                    base_url                = EXCLUDED.base_url,
                    username                = EXCLUDED.username,
                    auth_token              = EXCLUDED.auth_token,
                    brief_hour              = EXCLUDED.brief_hour,
                    token_valid             = EXCLUDED.token_valid,
                    recently_completed_days = EXCLUDED.recently_completed_days,
                    max_todo_tasks          = EXCLUDED.max_todo_tasks,
                    clerk_user_id           = COALESCE(EXCLUDED.clerk_user_id, users.clerk_user_id)
                RETURNING id
            """,
                (
                    base_url,
                    username,
                    auth_token,
                    email,
                    brief_hour,
                    token_valid,
                    recently_completed_days,
                    max_todo_tasks,
                    clerk_user_id,
                ),
            )
            return cur.fetchone()[0]
        else:
            cur.execute(
                f"""
                INSERT INTO users (base_url, username, auth_token, email, brief_hour, token_valid,
                                   recently_completed_days, max_todo_tasks, clerk_user_id)
                VALUES ({_P}, {_P}, {_P}, {_P}, {_P}, {_P}, {_P}, {_P}, {_P})
                ON CONFLICT(email) DO UPDATE SET
                    base_url                = excluded.base_url,
                    username                = excluded.username,
                    auth_token              = excluded.auth_token,
                    brief_hour              = excluded.brief_hour,
                    token_valid             = excluded.token_valid,
                    recently_completed_days = excluded.recently_completed_days,
                    max_todo_tasks          = excluded.max_todo_tasks,
                    clerk_user_id           = COALESCE(excluded.clerk_user_id, users.clerk_user_id)
            """,
                (
                    base_url,
                    username,
                    auth_token,
                    email,
                    brief_hour,
                    token_valid,
                    recently_completed_days,
                    max_todo_tasks,
                    clerk_user_id,
                ),
            )
            return cur.execute(
                f"SELECT id FROM users WHERE email = {_P}", (email,)
            ).fetchone()[0]


def update_user_snapshot(username: str, snapshot_json: str) -> None:
    with _connection() as conn:
        cur = conn.cursor()
        cur.execute(
            f"UPDATE users SET last_snapshot = {_P} WHERE username = {_P}",
            (snapshot_json, username),
        )


def mark_token_invalid(email: str) -> None:
    with _connection() as conn:
        cur = conn.cursor()
        cur.execute(f"UPDATE users SET token_valid = 0 WHERE email = {_P}", (email,))


def bump_token_fail(email: str) -> int:
    """Increment the consecutive token-validation failure count; return the new value.

    Used to tolerate transient rejections from OnTrack's token rotation — a single
    failed check is usually a rotation race, not a real expiry.
    """
    with _connection() as conn:
        cur = conn.cursor()
        cur.execute(
            f"UPDATE users SET token_fail_count = token_fail_count + 1 WHERE email = {_P}",
            (email,),
        )
        cur.execute(
            f"SELECT token_fail_count FROM users WHERE email = {_P}", (email,)
        )
        row = cur.fetchone()
        return row[0] if row else 0


def reset_token_fail(email: str) -> None:
    """Clear the failure count — the session is proven alive (valid check or fresh push)."""
    with _connection() as conn:
        cur = conn.cursor()
        cur.execute(
            f"UPDATE users SET token_fail_count = 0 WHERE email = {_P}", (email,)
        )


def reassign_email_by_username(username: str, new_email: str) -> bool:
    """Move an existing user's subscription to a new email (username is identity).

    Prevents duplicate rows when the same OnTrack account re-registers under a
    different email: instead of inserting a second row (the table is unique on
    email, not username), we repoint the existing row. Returns False if new_email
    already belongs to a *different* username — the move would breach the unique
    email constraint — so the caller can reject the re-registration.
    """
    with _connection() as conn:
        cur = conn.cursor()
        cur.execute(f"SELECT username FROM users WHERE email = {_P}", (new_email,))
        row = cur.fetchone()
        if row and row[0] != username:
            return False
        cur.execute(
            f"UPDATE users SET email = {_P} WHERE username = {_P}",
            (new_email, username),
        )
        return True


def set_refresh_token(username: str, refresh_token: str) -> bool:
    """Store the durable refresh_token (encrypted) for a user, keyed by username.

    The extension pushes this from the browser; the brief mints fresh auth_tokens
    from it. Returns True if a row was updated, False if no such user exists.
    """
    encrypted = _encrypt(refresh_token)
    with _connection() as conn:
        cur = conn.cursor()
        cur.execute(
            f"UPDATE users SET refresh_token = {_P} WHERE username = {_P}",
            (encrypted, username),
        )
        return cur.rowcount > 0


def set_brief_days(username: str, brief_days: int) -> bool:
    """Set the per-user brief window (7 or 14 days). A standalone setter rather than
    a new upsert_user param, so the token-refresh callers can't clobber it. Returns
    True if a row was updated."""
    with _connection() as conn:
        cur = conn.cursor()
        cur.execute(
            f"UPDATE users SET brief_days = {_P} WHERE username = {_P}",
            (brief_days, username),
        )
        return cur.rowcount > 0


def set_subscribed(email: str, subscribed: bool) -> bool:
    """Flip the brief subscription on/off, keyed by email. Returns True if a row
    was updated. Unsubscribe is a reversible pause (this flag) — never a row
    delete — so the user keeps their tokens/prefs and can resume instantly.
    """
    with _connection() as conn:
        cur = conn.cursor()
        cur.execute(
            f"UPDATE users SET subscribed = {_P} WHERE email = {_P}",
            (1 if subscribed else 0, email),
        )
        return cur.rowcount > 0


def get_all_users() -> list[dict]:
    with _connection() as conn:
        if _USE_PG:
            cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
            cur.execute("SELECT * FROM users")
            return [_decrypt_row(dict(r)) for r in cur.fetchall()]
        else:
            cur = conn.cursor()
            cur.execute("SELECT * FROM users")
            return [_decrypt_row(dict(r)) for r in cur.fetchall()]


def get_user_by_id(user_id: int) -> dict | None:
    with _connection() as conn:
        if _USE_PG:
            cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        else:
            cur = conn.cursor()
        cur.execute(f"SELECT * FROM users WHERE id = {_P}", (user_id,))
        row = cur.fetchone()
        return _decrypt_row(dict(row)) if row else None


def get_user_by_username(username: str) -> dict | None:
    with _connection() as conn:
        if _USE_PG:
            cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        else:
            cur = conn.cursor()
        cur.execute(f"SELECT * FROM users WHERE username = {_P}", (username,))
        row = cur.fetchone()
        return _decrypt_row(dict(row)) if row else None


def get_user_by_clerk_id(clerk_user_id: str) -> dict | None:
    with _connection() as conn:
        if _USE_PG:
            cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        else:
            cur = conn.cursor()
        cur.execute(f"SELECT * FROM users WHERE clerk_user_id = {_P}", (clerk_user_id,))
        row = cur.fetchone()
        return _decrypt_row(dict(row)) if row else None


def link_clerk_id_by_email(clerk_user_id: str, email: str) -> dict | None:
    """Claim a legacy row for this Clerk user by verified email (migration §8).

    Only attaches to a row whose clerk_user_id is still NULL, so an already-claimed
    row is never hijacked. Returns the linked row, or None if nothing was claimed.
    """
    with _connection() as conn:
        cur = conn.cursor()
        cur.execute(
            f"""UPDATE users SET clerk_user_id = {_P}
                WHERE email = {_P} AND clerk_user_id IS NULL""",
            (clerk_user_id, email),
        )
    return get_user_by_clerk_id(clerk_user_id)


def remove_user(email: str) -> None:
    with _connection() as conn:
        cur = conn.cursor()
        cur.execute(f"DELETE FROM users WHERE email = {_P}", (email,))


# ---------------------------------------------------------------------------
# Deterministic-brief storage — captured OnTrack tasks/deadlines (no OnTrack call
# at read time). See docs/DETERMINISTIC_BRIEF_PLAN.md. ON CONFLICT … DO UPDATE is
# supported by both psycopg2 (PG) and sqlite3 (≥3.24), and `excluded` is spelled
# the same on both, so a single query serves both engines.
# ---------------------------------------------------------------------------


def upsert_projects(user_id: int, projects: list[dict]) -> int:
    """Upsert the student's active units. ``projects`` items carry
    project_id, unit_code, unit_name, unit_end_date. Returns rows written."""
    if not projects:
        return 0
    now = datetime.now().isoformat(timespec="seconds")
    rows = [
        (
            user_id,
            p["project_id"],
            p.get("unit_code"),
            p.get("unit_name"),
            p.get("unit_end_date"),
            now,
        )
        for p in projects
    ]
    with _connection() as conn:
        cur = conn.cursor()
        cur.executemany(
            f"""
            INSERT INTO projects
                (user_id, project_id, unit_code, unit_name, unit_end_date, last_seen)
            VALUES ({_P}, {_P}, {_P}, {_P}, {_P}, {_P})
            ON CONFLICT (user_id, project_id) DO UPDATE SET
                unit_code     = excluded.unit_code,
                unit_name     = excluded.unit_name,
                unit_end_date = excluded.unit_end_date,
                last_seen     = excluded.last_seen
            """,
            rows,
        )
        return len(rows)


def prune_ended_projects(user_id: int, today_iso: str) -> None:
    """Drop units whose end_date has passed, and their tasks — keeps the store to
    the student's *current* enrolment so the brief never surfaces a dead unit."""
    with _connection() as conn:
        cur = conn.cursor()
        cur.execute(
            f"""DELETE FROM tasks WHERE user_id = {_P} AND project_id IN
                (SELECT project_id FROM projects
                 WHERE user_id = {_P} AND unit_end_date IS NOT NULL
                   AND unit_end_date < {_P})""",
            (user_id, user_id, today_iso),
        )
        cur.execute(
            f"""DELETE FROM projects WHERE user_id = {_P}
                AND unit_end_date IS NOT NULL AND unit_end_date < {_P}""",
            (user_id, today_iso),
        )


def upsert_tasks(user_id: int, project_id: int, unit_code: str, tasks: list[dict]) -> int:
    """Upsert enriched task rows for one project. Leaves feedback_text/seen_at
    untouched (those are captured separately), so a task sweep never wipes feedback.
    ``tasks`` are the dicts produced by core.ontrack.fetcher._enrich_tasks."""
    if not tasks:
        return 0
    now = datetime.now().isoformat(timespec="seconds")
    rows = [
        (
            user_id,
            project_id,
            t["task_definition_id"],
            t.get("abbreviation"),
            t.get("name"),
            unit_code,
            t.get("target_grade_label"),
            t.get("due_date"),
            t.get("status"),
            now,
        )
        for t in tasks
        if t.get("task_definition_id") is not None
    ]
    if not rows:
        return 0
    with _connection() as conn:
        cur = conn.cursor()
        cur.executemany(
            f"""
            INSERT INTO tasks
                (user_id, project_id, task_def_id, abbreviation, name, unit_code,
                 target_grade_label, deadline, status, last_seen)
            VALUES ({_P}, {_P}, {_P}, {_P}, {_P}, {_P}, {_P}, {_P}, {_P}, {_P})
            ON CONFLICT (user_id, project_id, task_def_id) DO UPDATE SET
                abbreviation       = excluded.abbreviation,
                name               = excluded.name,
                unit_code          = excluded.unit_code,
                target_grade_label = excluded.target_grade_label,
                deadline           = excluded.deadline,
                status             = excluded.status,
                last_seen          = excluded.last_seen
            """,
            rows,
        )
        return len(rows)


def set_task_feedback(
    user_id: int, project_id: int, task_def_id: int, text: str
) -> bool:
    """Store the latest tutor feedback for one task. Update-only: if the task row
    isn't captured yet, the next task sweep will create it and feedback re-lands."""
    now = datetime.now().isoformat(timespec="seconds")
    with _connection() as conn:
        cur = conn.cursor()
        cur.execute(
            f"""UPDATE tasks SET feedback_text = {_P}, feedback_seen_at = {_P}
                WHERE user_id = {_P} AND project_id = {_P} AND task_def_id = {_P}""",
            (text, now, user_id, project_id, task_def_id),
        )
        return cur.rowcount > 0


def get_capture_meta(user_id: int) -> tuple[int, str | None]:
    """Return (task_count, latest_capture_iso) for a user. Drives the brief's
    cold-start guard (count == 0 → no data yet, don't send) and the "as of" stamp."""
    with _connection() as conn:
        cur = conn.cursor()
        cur.execute(
            f"SELECT COUNT(*), MAX(last_seen) FROM tasks WHERE user_id = {_P}",
            (user_id,),
        )
        row = cur.fetchone()
        return (row[0] or 0, row[1]) if row else (0, None)


def get_feedback_entries(user_id: int, limit: int = 3) -> list[dict]:
    """Most recently captured tutor feedback for a user (for the extension strip)."""
    with _connection() as conn:
        if _USE_PG:
            cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        else:
            cur = conn.cursor()
        cur.execute(
            f"""SELECT project_id, abbreviation, name, unit_code, feedback_text
                FROM tasks
                WHERE user_id = {_P} AND feedback_text IS NOT NULL AND feedback_text <> ''
                ORDER BY feedback_seen_at DESC
                LIMIT {_P}""",
            (user_id, limit),
        )
        return [dict(r) for r in cur.fetchall()]


def get_unit_code(user_id: int, project_id: int) -> str | None:
    """Look up a stored project's unit_code (for labelling task rows when the
    project_tasks ingest arrives before/without the projects list)."""
    with _connection() as conn:
        cur = conn.cursor()
        cur.execute(
            f"SELECT unit_code FROM projects WHERE user_id = {_P} AND project_id = {_P}",
            (user_id, project_id),
        )
        row = cur.fetchone()
        return row[0] if row else None


def get_pending_tasks(user_id: int, today_iso: str, end_iso: str) -> list[dict]:
    """Tasks due in the inclusive window [today, end], ordered by deadline. Status
    filtering (HIDE_SET) is applied by the brief layer, not here — this just bounds
    the window and uses the (user_id, deadline) index."""
    with _connection() as conn:
        if _USE_PG:
            cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        else:
            cur = conn.cursor()
        cur.execute(
            f"""SELECT * FROM tasks
                WHERE user_id = {_P} AND deadline IS NOT NULL
                  AND deadline >= {_P} AND deadline <= {_P}
                ORDER BY deadline ASC""",
            (user_id, today_iso, end_iso),
        )
        return [dict(r) for r in cur.fetchall()]


def get_sqlalchemy_url() -> str:
    if _USE_PG:
        # SQLAlchemy 2.x requires postgresql:// not postgres://
        return _DATABASE_URL.replace("postgres://", "postgresql://", 1)
    return f"sqlite:///{_DB_PATH}"
