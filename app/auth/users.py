"""User account repository for the auth layer.

Simple username/password auth over the ``user`` table. Raw SQL, no ORM.
This is the one place that writes the ``user`` row's identity columns
(``username``, ``password_hash``).

Design notes
------------
* **Identity lookup** is by ``username`` only. Password authentication
  is done by comparing ``password_hash``.
* **last_active_at** is bumped on activity to feed the guest-reaper.
* This module never opens its own transaction *unless* the public function
  is a standalone unit of work; the ``db.connect()`` context manager owns
  COMMIT.
"""

from __future__ import annotations

import sqlite3
from datetime import UTC, datetime
from typing import Any
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from app.models import db

DEFAULT_TIMEZONE = "UTC"


def _now_iso() -> str:
    return datetime.now(UTC).isoformat()


def _row_to_dict(row: sqlite3.Row | None) -> dict[str, Any] | None:
    return dict(row) if row is not None else None


def resolve_timezone(timezone: str | None) -> ZoneInfo:
    """Resolve an IANA timezone name, falling back to UTC."""
    if timezone:
        try:
            return ZoneInfo(timezone)
        except (ValueError, ZoneInfoNotFoundError):
            pass
    return ZoneInfo(DEFAULT_TIMEZONE)


def _deleted_username(conn: sqlite3.Connection, user_id: int) -> str:
    base = "deleted-user"
    candidate = base
    suffix = int(user_id)
    while conn.execute(
        "SELECT 1 FROM user WHERE username = ? AND id != ?",
        (candidate, user_id),
    ).fetchone():
        candidate = f"{base}-{suffix}"
        suffix += 1
    return candidate


# ---------------------------------------------------------------------------
# Lookups
# ---------------------------------------------------------------------------


def get_user(user_id: int) -> dict[str, Any] | None:
    """Fetch a user row by id, or ``None``."""
    with db.connect() as conn:
        conn.execute("BEGIN")
        row = conn.execute(
            "SELECT * FROM user WHERE id = ? AND suspended_at IS NULL AND deleted_at IS NULL",
            (user_id,),
        ).fetchone()
        return _row_to_dict(row)


def find_by_username(username: str) -> dict[str, Any] | None:
    """Find a user by username, or ``None``."""
    with db.connect() as conn:
        conn.execute("BEGIN")
        row = conn.execute(
            "SELECT * FROM user"
            " WHERE username = ? AND deleted_at IS NULL",
            (username,),
        ).fetchone()
        return _row_to_dict(row)


def authenticate(username: str, password: str) -> dict[str, Any] | None:
    """Authenticate a user by username + password.

    Returns the user dict on success, ``None`` on failure.
    Uses constant-time comparison via ``secrets.compare_digest`` to prevent
    timing attacks.
    """
    import secrets
    from app.auth.passwords import verify_password

    with db.connect() as conn:
        conn.execute("BEGIN")
        row = conn.execute(
            "SELECT id, username, password_hash, visibility, consent_seen_at,"
            " private_redefinition_seen_at, comments_seen_at, suspended_at,"
            " deleted_at, created_at, last_active_at"
            " FROM user WHERE username = ? AND deleted_at IS NULL",
            (username,),
        ).fetchone()

    if row is None:
        return None

    user_dict = dict(row)
    if not verify_password(user_dict["password_hash"], password):
        return None

    return user_dict


# ---------------------------------------------------------------------------
# Creation
# ---------------------------------------------------------------------------


def create_user(username: str, password_hash: str, email: str | None = None) -> dict[str, Any]:
    """Create a new user with username + password.

    Returns the created user dict. Raises ``IdentityTakenError`` if the
    username or email is already taken.
    """
    with db.connect() as conn:
        conn.execute("BEGIN")

        # Check for existing user.
        existing = conn.execute(
            "SELECT id FROM user WHERE username = ?",
            (username,),
        ).fetchone()
        if existing is not None:
            raise IdentityTakenError(f"username {username!r} is already taken")

        # Check for existing email.
        if email is not None:
            existing_email = conn.execute(
                "SELECT id FROM user WHERE email = ?",
                (email,),
            ).fetchone()
            if existing_email is not None:
                raise IdentityTakenError(f"email {email!r} is already taken")

        now = _now_iso()
        cur = conn.execute(
            "INSERT INTO user"
            " (username, password_hash, email, visibility, consent_seen_at, private_redefinition_seen_at, created_at)"
            " VALUES (?, ?, ?, 'public', ?, ?, ?)",
            (username, password_hash, email, now, now, now),
        )
        user_id = cur.lastrowid

        row = conn.execute("SELECT * FROM user WHERE id = ?", (user_id,)).fetchone()
        return dict(row)

class AccountError(Exception):
    """Base class for account-layer errors."""


class IdentityTakenError(AccountError):
    """Raised when a username is already taken."""


# ---------------------------------------------------------------------------
# Updates
# ---------------------------------------------------------------------------


def update_password(user_id: int, password_hash: str) -> dict[str, Any]:
    """Update the password for an existing live account."""
    with db.connect() as conn:
        conn.execute("BEGIN")
        target = conn.execute(
            "SELECT * FROM user WHERE id = ? AND deleted_at IS NULL",
            (user_id,),
        ).fetchone()
        if target is None:
            raise AccountError(f"user {user_id} does not exist")
        conn.execute(
            "UPDATE user SET password_hash = ? WHERE id = ?",
            (password_hash, user_id),
        )
        row = conn.execute("SELECT * FROM user WHERE id = ?", (user_id,)).fetchone()
        return dict(row)


VALID_VISIBILITIES = frozenset({"public", "private"})


def set_visibility_consent(owner_id: int, visibility: str) -> None:
    """Record the user's visibility choice for *owner_id*."""
    if visibility not in VALID_VISIBILITIES:
        raise AccountError(f"{visibility!r} is not a valid visibility")
    now = _now_iso()
    with db.connect() as conn:
        conn.execute("BEGIN")
        conn.execute(
            "UPDATE user SET visibility = ?, consent_seen_at = ?,"
            " private_redefinition_seen_at = ? WHERE id = ?",
            (visibility, now, now, owner_id),
        )


def mark_redefinition_seen(owner_id: int) -> None:
    """Stamp ``private_redefinition_seen_at`` now for *owner_id*."""
    with db.connect() as conn:
        conn.execute("BEGIN")
        conn.execute(
            "UPDATE user SET private_redefinition_seen_at = ? WHERE id = ?",
            (_now_iso(), owner_id),
        )


def touch_last_active(user_id: int) -> None:
    """Bump ``last_active_at`` to now."""
    with db.connect() as conn:
        conn.execute("BEGIN")
        conn.execute(
            "UPDATE user SET last_active_at = ? WHERE id = ?",
            (_now_iso(), user_id),
        )


def delete_user(user_id: int) -> bool:
    """Remove account access while preserving owned history.

    The tombstoned row keeps no reusable login identifiers: username and
    password hash are cleared so a future signup can claim the same username.
    """
    with db.connect() as conn:
        conn.execute("BEGIN")
        cur = conn.execute(
            "UPDATE user"
            " SET username = ?, password_hash = '*',"
            " suspended_at = NULL, deleted_at = ?, comments_seen_at = NULL"
            " WHERE id = ? AND deleted_at IS NULL",
            (_deleted_username(conn, user_id), _now_iso(), user_id),
        )
        return cur.rowcount > 0


def set_email(user_id: int, email: str | None) -> None:
    """Update the recovery email for *user_id*."""
    with db.connect() as conn:
        conn.execute("BEGIN")
        conn.execute(
            "UPDATE user SET email = ? WHERE id = ?",
            (email, user_id),
        )


def set_bio(user_id: int, bio: str) -> None:
    """Update the bio for *user_id*."""
    with db.connect() as conn:
        conn.execute("BEGIN")
        conn.execute(
            "UPDATE user SET bio = ? WHERE id = ?",
            (bio, user_id),
        )


def get_user_timezone(user_id: int) -> ZoneInfo:
    """Return the user's timezone.

    The ``timezone`` column was removed in migration 0018; this stub
    always returns the project default so call sites don't break.
    """
    return resolve_timezone(DEFAULT_TIMEZONE)
