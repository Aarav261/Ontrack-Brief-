"""Database persistence — PostgreSQL (prod, set DATABASE_URL) or SQLite (local dev)."""

from __future__ import annotations

import logging
import os
import sqlite3
from contextlib import contextmanager
from pathlib import Path

from core.crypto import decrypt as _decrypt, encrypt as _encrypt

log = logging.getLogger(__name__)


def _decrypt_row(row: dict | None) -> dict | None:
    """Decrypt the at-rest auth_token on a user row read from the DB."""
    if row and row.get("auth_token") is not None:
        row["auth_token"] = _decrypt(row["auth_token"])
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
                    email                   TEXT NOT NULL UNIQUE,
                    clerk_user_id           TEXT,
                    brief_hour              INTEGER NOT NULL DEFAULT 8,
                    token_valid             INTEGER NOT NULL DEFAULT 1,
                    recently_completed_days INTEGER NOT NULL DEFAULT 7,
                    max_todo_tasks          INTEGER NOT NULL DEFAULT 10,
                    last_snapshot           TEXT,
                    created_at              TIMESTAMPTZ NOT NULL DEFAULT now()
                )
            """)
            # Migrate existing PG DBs
            for col, typedef in [
                ("token_valid", "INTEGER NOT NULL DEFAULT 1"),
                ("recently_completed_days", "INTEGER NOT NULL DEFAULT 7"),
                ("max_todo_tasks", "INTEGER NOT NULL DEFAULT 10"),
                ("last_snapshot", "TEXT"),
                ("clerk_user_id", "TEXT"),
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
                    email                   TEXT NOT NULL UNIQUE,
                    clerk_user_id           TEXT,
                    brief_hour              INTEGER NOT NULL DEFAULT 8,
                    token_valid             INTEGER NOT NULL DEFAULT 1,
                    recently_completed_days INTEGER NOT NULL DEFAULT 7,
                    max_todo_tasks          INTEGER NOT NULL DEFAULT 10,
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
                ("last_snapshot", "TEXT"),
                ("clerk_user_id", "TEXT"),
            ]:
                if col not in cols:
                    cur.execute(f"ALTER TABLE users ADD COLUMN {col} {typedef}")
            # Clerk identity is unique but nullable (NULLs are distinct) — index, not
            # an ADD COLUMN UNIQUE (SQLite forbids that as a migration).
            cur.execute(
                "CREATE UNIQUE INDEX IF NOT EXISTS idx_users_clerk_user_id "
                "ON users(clerk_user_id)"
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


def get_sqlalchemy_url() -> str:
    if _USE_PG:
        # SQLAlchemy 2.x requires postgresql:// not postgres://
        return _DATABASE_URL.replace("postgres://", "postgresql://", 1)
    return f"sqlite:///{_DB_PATH}"
