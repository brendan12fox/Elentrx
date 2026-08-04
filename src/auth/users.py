"""SQLite-backed username/password authentication."""

from __future__ import annotations

import os
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone

import bcrypt

from src.db.schema import get_connection, init_db

USERS_SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    username TEXT UNIQUE NOT NULL,
    password_hash TEXT NOT NULL,
    email TEXT,
    alert_email TEXT,
    is_admin INTEGER DEFAULT 0,
    created_at TEXT NOT NULL
);
"""


def _hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def _verify_password(password: str, password_hash: str) -> bool:
    try:
        return bcrypt.checkpw(password.encode("utf-8"), password_hash.encode("utf-8"))
    except ValueError:
        return False


def init_auth_tables() -> None:
    init_db()
    with get_connection() as conn:
        conn.executescript(USERS_SCHEMA)


@dataclass
class User:
    id: int
    username: str
    email: str | None
    alert_email: str | None
    is_admin: bool


def signup_allowed() -> bool:
    return os.getenv("ALLOW_SIGNUP", "true").lower() in ("1", "true", "yes")


def username_exists(username: str) -> bool:
    init_auth_tables()
    with get_connection() as conn:
        row = conn.execute(
            "SELECT 1 FROM users WHERE username = ?",
            (username.strip().lower(),),
        ).fetchone()
        return row is not None


def ensure_bootstrap_admin() -> None:
    """Create the first admin from ADMIN_USERNAME / ADMIN_PASSWORD env vars."""
    init_auth_tables()
    username = os.getenv("ADMIN_USERNAME", "admin").strip()
    password = os.getenv("ADMIN_PASSWORD", "").strip()
    email = os.getenv("ALERT_EMAIL", "").strip() or None

    with get_connection() as conn:
        row = conn.execute("SELECT COUNT(*) AS n FROM users").fetchone()
        if row and int(row["n"]) > 0:
            return
        if not password:
            return
        create_user(
            username=username,
            password=password,
            email=email,
            alert_email=email,
            is_admin=True,
            conn=conn,
        )


def create_user(
    username: str,
    password: str,
    email: str | None = None,
    alert_email: str | None = None,
    is_admin: bool = False,
    conn: sqlite3.Connection | None = None,
) -> User:
    init_auth_tables()
    now = datetime.now(timezone.utc).isoformat()
    password_hash = _hash_password(password)

    def _insert(connection: sqlite3.Connection) -> User:
        cursor = connection.execute(
            """
            INSERT INTO users (username, password_hash, email, alert_email, is_admin, created_at)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                username.strip().lower(),
                password_hash,
                email,
                alert_email or email,
                1 if is_admin else 0,
                now,
            ),
        )
        return User(
            id=int(cursor.lastrowid),
            username=username.strip().lower(),
            email=email,
            alert_email=alert_email or email,
            is_admin=is_admin,
        )

    if conn is not None:
        return _insert(conn)

    with get_connection() as connection:
        return _insert(connection)


def authenticate(username: str, password: str) -> User | None:
    init_auth_tables()
    with get_connection() as conn:
        row = conn.execute(
            "SELECT id, username, password_hash, email, alert_email, is_admin FROM users WHERE username = ?",
            (username.strip().lower(),),
        ).fetchone()
        if not row or not _verify_password(password, row["password_hash"]):
            return None
        return User(
            id=int(row["id"]),
            username=row["username"],
            email=row["email"],
            alert_email=row["alert_email"],
            is_admin=bool(row["is_admin"]),
        )


def get_user(user_id: int) -> User | None:
    init_auth_tables()
    with get_connection() as conn:
        row = conn.execute(
            "SELECT id, username, email, alert_email, is_admin FROM users WHERE id = ?",
            (user_id,),
        ).fetchone()
        if not row:
            return None
        return User(
            id=int(row["id"]),
            username=row["username"],
            email=row["email"],
            alert_email=row["alert_email"],
            is_admin=bool(row["is_admin"]),
        )


def update_alert_email(user_id: int, alert_email: str) -> None:
    init_auth_tables()
    with get_connection() as conn:
        conn.execute(
            "UPDATE users SET alert_email = ? WHERE id = ?",
            (alert_email.strip(), user_id),
        )


def user_count() -> int:
    init_auth_tables()
    with get_connection() as conn:
        row = conn.execute("SELECT COUNT(*) AS n FROM users").fetchone()
        return int(row["n"]) if row else 0


def update_password(user_id: int, new_password: str) -> None:
    init_auth_tables()
    password_hash = _hash_password(new_password)
    with get_connection() as conn:
        conn.execute(
            "UPDATE users SET password_hash = ? WHERE id = ?",
            (password_hash, user_id),
        )


def list_alert_recipients() -> list[str]:
    """Emails to notify on favorable hits (DB users + ALERT_EMAIL env fallback)."""
    init_auth_tables()
    recipients: list[str] = []
    with get_connection() as conn:
        rows = conn.execute(
            "SELECT DISTINCT alert_email FROM users WHERE alert_email IS NOT NULL AND alert_email != ''"
        ).fetchall()
        recipients.extend(row["alert_email"] for row in rows)

    env_email = os.getenv("ALERT_EMAIL", "").strip()
    if env_email and env_email not in recipients:
        recipients.append(env_email)
    return recipients
