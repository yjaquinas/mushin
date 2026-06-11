"""User account repository for the auth layer.

Raw SQL over the ``user`` table (and an owner-scoped delete that relies on the
schema's ``ON DELETE CASCADE`` from ``user`` to wipe every owned row). This is
the one place that writes the ``user`` row's identity columns
(``auth_provider``, ``provider_id``, ``password_hash``, ``display_name``).

Design notes
------------
* **Upgrade-in-place.** A guest is a real ``user`` row already; signing in
  *attaches* provider columns to that same row (``attach_provider``) instead of
  minting a new one. Because every owned table points at the guest's
  ``owner_id``, zero rows move — the upgrade is a single ``UPDATE user``.
* **Identity lookup** is always ``(auth_provider, provider_id)`` for OAuth and
  ``(auth_provider='email', display_name=<email>)`` for the email provider
  (email is stored in ``display_name`` — the schema has no dedicated email
  column, and Kakao deliberately gives us no email at all).
* **last_active_at** is bumped on guest activity to feed the guest-reaper.
* This module never opens its own transaction *unless* the public function is a
  standalone unit of work; the ``db.connect()`` context manager owns COMMIT.
"""

from __future__ import annotations

import sqlite3
from datetime import UTC, datetime
from typing import Any

from app.models import db

VALID_PROVIDERS = frozenset({"kakao", "google", "email", "guest"})


class AccountError(Exception):
    """Base class for account-layer errors."""


class IdentityTakenError(AccountError):
    """Raised when an identity (provider+provider_id, or email) already exists."""


def _now_iso() -> str:
    return datetime.now(UTC).isoformat()


def _row_to_dict(row: sqlite3.Row | None) -> dict[str, Any] | None:
    return dict(row) if row is not None else None


# ---------------------------------------------------------------------------
# Lookups
# ---------------------------------------------------------------------------


def get_user(user_id: int) -> dict[str, Any] | None:
    """Fetch a user row by id, or ``None``."""
    with db.connect() as conn:
        conn.execute("BEGIN")
        row = conn.execute("SELECT * FROM user WHERE id = ?", (user_id,)).fetchone()
        return _row_to_dict(row)


def find_by_provider(auth_provider: str, provider_id: str) -> dict[str, Any] | None:
    """Find a user by OAuth identity ``(auth_provider, provider_id)``."""
    with db.connect() as conn:
        conn.execute("BEGIN")
        row = conn.execute(
            "SELECT * FROM user WHERE auth_provider = ? AND provider_id = ?",
            (auth_provider, provider_id),
        ).fetchone()
        return _row_to_dict(row)


def find_by_email(email: str) -> dict[str, Any] | None:
    """Find an email-provider user by email (stored in ``display_name``)."""
    with db.connect() as conn:
        conn.execute("BEGIN")
        row = conn.execute(
            "SELECT * FROM user WHERE auth_provider = 'email' AND display_name = ?",
            (email,),
        ).fetchone()
        return _row_to_dict(row)


# ---------------------------------------------------------------------------
# Creation
# ---------------------------------------------------------------------------


def create_guest() -> int:
    """Mint an anonymous guest user and return its id.

    Called on the user's *first interaction*, never on bare page load — the
    bot-guard rule. ``provider_id`` / ``password_hash`` stay NULL;
    ``last_active_at`` is stamped now so the reaper has a baseline.
    """
    now = _now_iso()
    with db.connect() as conn:
        conn.execute("BEGIN")
        cur = conn.execute(
            "INSERT INTO user (auth_provider, last_active_at) VALUES ('guest', ?)",
            (now,),
        )
        return int(cur.lastrowid)


def create_email_user(email: str, password_hash: str, display_name: str | None = None) -> int:
    """Create an email/password user. *password_hash* is the Argon2id encoded hash.

    Raises ``IdentityTakenError`` if the email is already registered.
    """
    with db.connect() as conn:
        conn.execute("BEGIN")
        existing = conn.execute(
            "SELECT 1 FROM user WHERE auth_provider = 'email' AND display_name = ?",
            (email,),
        ).fetchone()
        if existing is not None:
            raise IdentityTakenError(f"email {email!r} is already registered")
        cur = conn.execute(
            "INSERT INTO user (auth_provider, password_hash, display_name, last_active_at)"
            " VALUES ('email', ?, ?, ?)",
            (password_hash, display_name or email, _now_iso()),
        )
        return int(cur.lastrowid)


def create_oauth_user(auth_provider: str, provider_id: str, display_name: str | None) -> int:
    """Create a fresh OAuth user (no guest to upgrade). Returns its id."""
    if auth_provider not in {"kakao", "google"}:
        raise AccountError(f"{auth_provider!r} is not an OAuth provider")
    with db.connect() as conn:
        conn.execute("BEGIN")
        existing = conn.execute(
            "SELECT id FROM user WHERE auth_provider = ? AND provider_id = ?",
            (auth_provider, provider_id),
        ).fetchone()
        if existing is not None:
            raise IdentityTakenError(f"{auth_provider} identity {provider_id!r} already exists")
        cur = conn.execute(
            "INSERT INTO user (auth_provider, provider_id, display_name, last_active_at)"
            " VALUES (?, ?, ?, ?)",
            (auth_provider, provider_id, display_name, _now_iso()),
        )
        return int(cur.lastrowid)


# ---------------------------------------------------------------------------
# Upgrade-in-place
# ---------------------------------------------------------------------------


def attach_provider(
    user_id: int,
    auth_provider: str,
    *,
    provider_id: str | None = None,
    password_hash: str | None = None,
    display_name: str | None = None,
) -> dict[str, Any]:
    """Attach a real-provider identity to an existing (guest) user **in place**.

    This is the upgrade. The row keeps its ``id`` / ``owner_id``, so every owned
    row already pointing at it is preserved with zero migration — only the
    identity columns change.

    The caller is responsible for having verified consent and for resolving the
    edge case where the identity already maps to a *different* account (see
    ``find_by_provider`` / ``find_by_email`` before calling). This function does
    a final guard so a race can't create a duplicate identity.
    """
    if auth_provider not in {"kakao", "google", "email"}:
        raise AccountError(f"{auth_provider!r} is not a real provider")

    with db.connect() as conn:
        conn.execute("BEGIN")
        target = conn.execute("SELECT * FROM user WHERE id = ?", (user_id,)).fetchone()
        if target is None:
            raise AccountError(f"user {user_id} does not exist")

        # Final uniqueness guard against another row owning this identity.
        if auth_provider in {"kakao", "google"}:
            clash = conn.execute(
                "SELECT id FROM user WHERE auth_provider = ? AND provider_id = ? AND id != ?",
                (auth_provider, provider_id, user_id),
            ).fetchone()
        else:  # email
            clash = conn.execute(
                "SELECT id FROM user WHERE auth_provider = 'email'"
                " AND display_name = ? AND id != ?",
                (display_name, user_id),
            ).fetchone()
        if clash is not None:
            raise IdentityTakenError(
                f"{auth_provider} identity already mapped to user {clash['id']}"
            )

        conn.execute(
            "UPDATE user SET auth_provider = ?, provider_id = ?, password_hash = ?,"
            " display_name = ?, last_active_at = ? WHERE id = ?",
            (
                auth_provider,
                provider_id,
                password_hash,
                display_name,
                _now_iso(),
                user_id,
            ),
        )
        row = conn.execute("SELECT * FROM user WHERE id = ?", (user_id,)).fetchone()
        return dict(row)


# ---------------------------------------------------------------------------
# Activity + deletion
# ---------------------------------------------------------------------------


def touch_last_active(user_id: int) -> None:
    """Bump ``last_active_at`` to now. Feeds the guest-reaper retention timer."""
    with db.connect() as conn:
        conn.execute("BEGIN")
        conn.execute(
            "UPDATE user SET last_active_at = ? WHERE id = ?",
            (_now_iso(), user_id),
        )


def delete_user(user_id: int) -> bool:
    """Delete the ``user`` row, cascading to *all* owned data including memos.

    The schema declares ``ON DELETE CASCADE`` on every ``owner_id`` reference, so
    a single ``DELETE FROM user`` wipes category/sub_tally/field_def/tag/entry/
    entry_tag/entry_value/match/level/level_rule and every memo. PIPA deletion is
    therefore honest: no orphaned personal data survives. Returns ``True`` if a
    row was removed.

    ``PRAGMA foreign_keys=ON`` is set per-connection by ``db._configure``; the
    cascade depends on it.
    """
    with db.connect() as conn:
        conn.execute("BEGIN")
        cur = conn.execute("DELETE FROM user WHERE id = ?", (user_id,))
        return cur.rowcount > 0
