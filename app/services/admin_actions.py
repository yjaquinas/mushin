"""Admin mutation helpers for user and content moderation."""

from __future__ import annotations

import re
import sqlite3
import unicodedata
from datetime import UTC, datetime
from zoneinfo import ZoneInfo

from app.auth.passwords import hash_password
from app.services import entries

_USERNAME_RE = re.compile(r"^[a-z0-9_]{3,20}$")


class AdminValidationError(ValueError):
    """Raised when an admin form value is invalid."""


def update_user(
    conn: sqlite3.Connection,
    user_id: int,
    *,
    username: str,
    email: str | None = None,
    password: str | None = None,
) -> None:
    normalized_username = _normalize_username(username)
    _ensure_unique_identity(conn, user_id, normalized_username)

    assignments = ["username = ?"]
    params: list[object] = [normalized_username]
    if email is not None:
        assignments.append("email = ?")
        params.append(email.strip() or None)
    if password:
        assignments.append("password_hash = ?")
        params.append(hash_password(password))
    params.append(user_id)
    conn.execute(
        f"UPDATE user SET {', '.join(assignments)} WHERE id = ?",
        params,
    )


def set_user_suspended(conn: sqlite3.Connection, user_id: int, *, suspended: bool) -> None:
    conn.execute(
        "UPDATE user SET suspended_at = ? WHERE id = ?",
        (_now_iso() if suspended else None, user_id),
    )


def delete_user(conn: sqlite3.Connection, user_id: int) -> None:
    """Soft-delete a user: rename username, remove password, mark deleted."""
    conn.execute(
        """
        UPDATE user
        SET username = 'deleted-user-' || id,
            password_hash = '',
            deleted_at = ?,
            suspended_at = NULL
        WHERE id = ?
        """,
        (_now_iso(), user_id),
    )


def update_entry_memo(conn: sqlite3.Connection, user_id: int, entry_id: int, memo: str) -> None:
    conn.execute(
        "UPDATE entry SET memo = ?, updated_at = ? WHERE owner_id = ? AND id = ?",
        (memo.strip() or None, _now_iso(), user_id, entry_id),
    )


def set_entry_hidden(
    conn: sqlite3.Connection, user_id: int, entry_id: int, *, hidden: bool
) -> None:
    row = conn.execute(
        "SELECT activity_id FROM entry WHERE owner_id = ? AND id = ?",
        (user_id, entry_id),
    ).fetchone()
    if row is None:
        return
    conn.execute(
        "UPDATE entry SET hidden_at = ?, updated_at = ? WHERE owner_id = ? AND id = ?",
        (_now_iso() if hidden else None, _now_iso(), user_id, entry_id),
    )
    entries._refresh_cache(conn, row["activity_id"], user_id, ZoneInfo("UTC"))


def update_comment_body(conn: sqlite3.Connection, user_id: int, comment_id: int, body: str) -> None:
    trimmed = body.strip()
    if not trimmed:
        raise AdminValidationError("comment body must not be empty")
    conn.execute(
        """
        UPDATE comment
        SET body = ?
        WHERE id = ?
          AND (
              author_id = ?
              OR entry_id IN (SELECT id FROM entry WHERE owner_id = ?)
          )
        """,
        (trimmed, comment_id, user_id, user_id),
    )


def set_comment_hidden(
    conn: sqlite3.Connection, user_id: int, comment_id: int, *, hidden: bool
) -> None:
    conn.execute(
        """
        UPDATE comment
        SET hidden_at = ?
        WHERE id = ?
          AND (
              author_id = ?
              OR entry_id IN (SELECT id FROM entry WHERE owner_id = ?)
          )
        """,
        (_now_iso() if hidden else None, comment_id, user_id, user_id),
    )


def _normalize_username(username: str) -> str:
    normalized = unicodedata.normalize("NFKC", username.strip()).casefold()
    if not _USERNAME_RE.match(normalized):
        raise AdminValidationError(
            "Username must be 3-20 characters: lowercase letters, numbers, and underscores only."
        )
    return normalized


def _ensure_unique_identity(
    conn: sqlite3.Connection, user_id: int, username: str
) -> None:
    username_row = conn.execute(
        "SELECT id FROM user WHERE username = ? AND id != ?",
        (username, user_id),
    ).fetchone()
    if username_row is not None:
        raise AdminValidationError("That username is already in use.")


def _now_iso() -> str:
    return datetime.now(UTC).isoformat()
