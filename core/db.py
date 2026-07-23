"""Database persistence — PostgreSQL (prod, set DATABASE_URL) or SQLite (local dev)."""

from __future__ import annotations

import functools
import logging
import os
import random
import sqlite3
import time
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path

from core.crypto import decrypt as _decrypt
from core.crypto import encrypt as _encrypt

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
_DB_PATH = Path(os.environ.get("DB_PATH", str(Path(__file__).parent.parent / "ontracker.db")))
_USE_PG = _DATABASE_URL.startswith(("postgresql://", "postgres://"))

if _USE_PG:
    import psycopg2
    import psycopg2.extras

# SQL placeholder: %s for psycopg2, ? for sqlite3
_P = "%s" if _USE_PG else "?"


def _pg_connect():
    """Connect to Postgres, retrying transient failures with backoff.

    Railway's private-network hostname (postgres.railway.internal) is only
    resolvable from inside its private network, and that DNS can hiccup
    briefly right after a deploy/restart even when both services are up.
    A bare psycopg2.connect() has no retry, so those blips surface as 500s.
    """
    attempts = 5
    for i in range(attempts):
        try:
            return psycopg2.connect(_DATABASE_URL)
        except psycopg2.OperationalError:
            if i == attempts - 1:
                raise
            backoff = 0.2 * (2**i) + random.uniform(0, 0.1)
            log.warning(
                "Postgres connection failed (attempt %d/%d) — retrying in %.0fms",
                i + 1,
                attempts,
                backoff * 1000,
            )
            time.sleep(backoff)


@contextmanager
def _connection():
    if _USE_PG:
        conn = _pg_connect()
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


# Postgres aborts one transaction in a deadlock (SQLSTATE 40P01) and serialization
# failures (40001); SQLite raises "database is locked". These are transient: the
# extension hammers the same user row concurrently (auto re-link on every popup open
# alongside /ingest, /refresh-token, /refresh-credential), so two writers can grab
# row/index locks in opposite order. The loser should just retry, not 500.
_RETRY_SQLSTATES = {"40P01", "40001"}
_RETRY_MESSAGES = ("deadlock detected", "database is locked")


def _is_transient_conflict(exc: Exception) -> bool:
    if getattr(exc, "pgcode", None) in _RETRY_SQLSTATES:
        return True
    msg = str(exc).lower()
    return any(m in msg for m in _RETRY_MESSAGES)


def _retry_on_deadlock(fn):
    """Retry a write that lost a deadlock / lock race, with a little backoff. Each of
    our write helpers runs in its own short transaction (open → one statement →
    commit → close), so re-running the whole function is a safe, fresh attempt."""

    @functools.wraps(fn)
    def wrapper(*args, **kwargs):
        attempts = 5
        for i in range(attempts):
            try:
                return fn(*args, **kwargs)
            except Exception as exc:
                if not _is_transient_conflict(exc) or i == attempts - 1:
                    raise
                backoff = 0.05 * (2**i) + random.uniform(0, 0.05)
                log.warning(
                    "Transient DB conflict in %s (attempt %d/%d) — retrying in %.0fms: %s",
                    fn.__name__,
                    i + 1,
                    attempts,
                    backoff * 1000,
                    exc,
                )
                time.sleep(backoff)

    return wrapper


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
                    brief_minute            INTEGER NOT NULL DEFAULT 0,
                    brief_dow               TEXT NOT NULL DEFAULT 'mon-fri',
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
                ("brief_minute", "INTEGER NOT NULL DEFAULT 0"),
                ("brief_dow", "TEXT NOT NULL DEFAULT 'mon-fri'"),
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
                "CREATE UNIQUE INDEX IF NOT EXISTS idx_users_clerk_user_id ON users(clerk_user_id)"
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
                    brief_minute            INTEGER NOT NULL DEFAULT 0,
                    brief_dow               TEXT NOT NULL DEFAULT 'mon-fri',
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
                ("brief_minute", "INTEGER NOT NULL DEFAULT 0"),
                ("brief_dow", "TEXT NOT NULL DEFAULT 'mon-fri'"),
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
                "CREATE UNIQUE INDEX IF NOT EXISTS idx_users_clerk_user_id ON users(clerk_user_id)"
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
            "CREATE INDEX IF NOT EXISTS idx_tasks_user_deadline ON tasks(user_id, deadline)"
        )


@_retry_on_deadlock
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
            row = cur.fetchone()
            if row is None:
                raise RuntimeError(f"upsert_user: RETURNING id returned no row for email={email!r}")
            return row[0]
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
            row = cur.execute(f"SELECT id FROM users WHERE email = {_P}", (email,)).fetchone()
            if row is None:
                raise RuntimeError(
                    f"upsert_user: user row missing after upsert for email={email!r}"
                )
            return row[0]


@_retry_on_deadlock
def update_user_snapshot(username: str, snapshot_json: str) -> None:
    with _connection() as conn:
        cur = conn.cursor()
        cur.execute(
            f"UPDATE users SET last_snapshot = {_P} WHERE username = {_P}",
            (snapshot_json, username),
        )


@_retry_on_deadlock
def mark_token_invalid(email: str) -> None:
    with _connection() as conn:
        cur = conn.cursor()
        cur.execute(f"UPDATE users SET token_valid = 0 WHERE email = {_P}", (email,))


@_retry_on_deadlock
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
        cur.execute(f"SELECT token_fail_count FROM users WHERE email = {_P}", (email,))
        row = cur.fetchone()
        return row[0] if row else 0


@_retry_on_deadlock
def reset_token_fail(email: str) -> None:
    """Clear the failure count — the session is proven alive (valid check or fresh push)."""
    with _connection() as conn:
        cur = conn.cursor()
        cur.execute(f"UPDATE users SET token_fail_count = 0 WHERE email = {_P}", (email,))


@_retry_on_deadlock
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


@_retry_on_deadlock
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


@_retry_on_deadlock
def update_brief_prefs(
    username: str,
    *,
    brief_days: int | None = None,
    brief_minute: int | None = None,
    brief_dow: str | None = None,
) -> bool:
    """Update the brief send-time preferences (window / minute / days) in a single
    statement. Standalone setters rather than upsert_user params, so the token-refresh
    callers can't clobber them; folded into one UPDATE so a Settings save touches the
    user row once instead of three times — fewer lock acquisitions, less deadlock
    surface on the heavily-contended row. Only columns passed (non-None) are written.
    Returns True if a row was updated."""
    sets, params = [], []
    if brief_days is not None:
        sets.append(f"brief_days = {_P}")
        params.append(brief_days)
    if brief_minute is not None:
        sets.append(f"brief_minute = {_P}")
        params.append(brief_minute)
    if brief_dow is not None:
        sets.append(f"brief_dow = {_P}")
        params.append(brief_dow)
    if not sets:
        return False
    params.append(username)
    with _connection() as conn:
        cur = conn.cursor()
        cur.execute(
            f"UPDATE users SET {', '.join(sets)} WHERE username = {_P}",
            params,
        )
        return cur.rowcount > 0


@_retry_on_deadlock
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


@_retry_on_deadlock
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


@_retry_on_deadlock
def reclaim_ontrack_username(username: str, keep_user_id: int) -> list[int]:
    """Enforce one OnTrack login per account: an OnTrack username uniquely
    identifies a student, but `username` isn't a DB unique key, so two Clerk
    accounts linking the same login create two rows. /ingest resolves by username
    alone and can then write to the wrong row, so the snapshot (resolved by Clerk
    id) shows nothing. When an account (re)links a username, evict every *other*
    row holding it — last verified OnTrack linker wins — and delete that row's
    captured tasks/projects. Returns the evicted user ids so the caller can drop
    their scheduled brief jobs."""
    with _connection() as conn:
        cur = conn.cursor()
        cur.execute(
            f"SELECT id FROM users WHERE username = {_P} AND id <> {_P}",
            (username, keep_user_id),
        )
        evicted = [row[0] for row in cur.fetchall()]
        if not evicted:
            return []
        placeholders = ",".join([_P] * len(evicted))
        cur.execute(f"DELETE FROM tasks WHERE user_id IN ({placeholders})", tuple(evicted))
        cur.execute(f"DELETE FROM projects WHERE user_id IN ({placeholders})", tuple(evicted))
        cur.execute(f"DELETE FROM users WHERE id IN ({placeholders})", tuple(evicted))
        return evicted


# ---------------------------------------------------------------------------
# Deterministic-brief storage — captured OnTrack tasks/deadlines (no OnTrack call
# at read time). See docs/DETERMINISTIC_BRIEF_PLAN.md. ON CONFLICT … DO UPDATE is
# supported by both psycopg2 (PG) and sqlite3 (≥3.24), and `excluded` is spelled
# the same on both, so a single query serves both engines.
# ---------------------------------------------------------------------------


@_retry_on_deadlock
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


@_retry_on_deadlock
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


@_retry_on_deadlock
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


@_retry_on_deadlock
def set_task_feedback(user_id: int, project_id: int, task_def_id: int, text: str) -> bool:
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


def delete_tasks_for_inactive_projects(user_id: int) -> int:
    """Delete task rows whose project is no longer in the user's active projects
    (e.g. past-trimester tasks left behind after prune_ended_projects). Returns the
    number of rows removed."""
    with _connection() as conn:
        cur = conn.cursor()
        cur.execute(
            f"""DELETE FROM tasks
                WHERE user_id = {_P}
                  AND project_id NOT IN (
                      SELECT project_id FROM projects WHERE user_id = {_P}
                  )""",
            (user_id, user_id),
        )
        return cur.rowcount


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
