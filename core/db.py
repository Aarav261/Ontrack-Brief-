"""SQLite persistence for web app users."""

from __future__ import annotations

import logging
import os
import sqlite3
from pathlib import Path

DB_PATH = Path(os.environ.get("DB_PATH", str(Path(__file__).parent.parent / "ontracker.db")))

log = logging.getLogger(__name__)


def init_db() -> None:
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS users (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                base_url    TEXT NOT NULL,
                username    TEXT NOT NULL,
                auth_token  TEXT NOT NULL,
                email       TEXT NOT NULL UNIQUE,
                brief_hour  INTEGER NOT NULL DEFAULT 8,
                token_valid INTEGER NOT NULL DEFAULT 1,
                created_at  TEXT NOT NULL DEFAULT (datetime('now'))
            )
        """)
        # Migrate existing DB that lacks token_valid column
        cols = {r[1] for r in conn.execute("PRAGMA table_info(users)").fetchall()}
        if "token_valid" not in cols:
            conn.execute("ALTER TABLE users ADD COLUMN token_valid INTEGER NOT NULL DEFAULT 1")
        if "recently_completed_days" not in cols:
            conn.execute("ALTER TABLE users ADD COLUMN recently_completed_days INTEGER NOT NULL DEFAULT 7")
        if "max_todo_tasks" not in cols:
            conn.execute("ALTER TABLE users ADD COLUMN max_todo_tasks INTEGER NOT NULL DEFAULT 10")


def upsert_user(base_url: str, username: str, auth_token: str, email: str,
                brief_hour: int = 8, token_valid: int = 1,
                recently_completed_days: int = 7, max_todo_tasks: int = 10) -> int:
    try:
        with sqlite3.connect(DB_PATH) as conn:
            conn.execute("""
                INSERT INTO users (base_url, username, auth_token, email, brief_hour, token_valid,
                                   recently_completed_days, max_todo_tasks)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(email) DO UPDATE SET
                    base_url                = excluded.base_url,
                    username                = excluded.username,
                    auth_token              = excluded.auth_token,
                    brief_hour              = excluded.brief_hour,
                    token_valid             = excluded.token_valid,
                    recently_completed_days = excluded.recently_completed_days,
                    max_todo_tasks          = excluded.max_todo_tasks
            """, (base_url, username, auth_token, email, brief_hour, token_valid,
                  recently_completed_days, max_todo_tasks))
            return conn.execute("SELECT id FROM users WHERE email = ?", (email,)).fetchone()[0]
    except sqlite3.Error as exc:
        log.error("Database error upserting user %s: %s", email, exc)
        raise


def mark_token_invalid(email: str) -> None:
    try:
        with sqlite3.connect(DB_PATH) as conn:
            conn.execute("UPDATE users SET token_valid = 0 WHERE email = ?", (email,))
    except sqlite3.Error as exc:
        log.error("Database error marking token invalid for %s: %s", email, exc)
        raise


def get_all_users() -> list[dict]:
    try:
        with sqlite3.connect(DB_PATH) as conn:
            conn.row_factory = sqlite3.Row
            return [dict(r) for r in conn.execute("SELECT * FROM users").fetchall()]
    except sqlite3.Error as exc:
        log.error("Database error loading users: %s", exc)
        return []


def remove_user(email: str) -> None:
    try:
        with sqlite3.connect(DB_PATH) as conn:
            conn.execute("DELETE FROM users WHERE email = ?", (email,))
    except sqlite3.Error as exc:
        log.error("Database error removing user %s: %s", email, exc)
        raise
