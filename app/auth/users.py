"""User account repository for the auth layer.

Raw SQL over the ``user`` table (and an owner-scoped delete that relies on the
schema's ``ON DELETE CASCADE`` from ``user`` to wipe every owned row). This is
the one place that writes the ``user`` row's identity columns
(``auth_provider``, ``provider_id``, ``password_hash``, ``username``, ``email``,
``display_name``).

Design notes
------------
* **Upgrade-in-place.** A guest is a real ``user`` row already; signing in
  *attaches* provider columns to that same row (``attach_provider``) instead of
  minting a new one. Because every owned table points at the guest's
  ``owner_id``, zero rows move — the upgrade is a single ``UPDATE user``.
* **Identity lookup** is ``(auth_provider, provider_id)`` for OAuth and
  ``(auth_provider='email', username=<username>)`` for password-auth. Username is
  a dedicated, partial-unique identity column; the optional ``email`` column is
  for future account recovery only (never a login key).
* **last_active_at** is bumped on guest activity to feed the guest-reaper.
* This module never opens its own transaction *unless* the public function is a
  standalone unit of work; the ``db.connect()`` context manager owns COMMIT.
"""

from __future__ import annotations

import sqlite3
from datetime import UTC, datetime
from typing import Any
from zoneinfo import ZoneInfo, available_timezones

from app.models import db

VALID_PROVIDERS = frozenset({"google", "email", "guest"})

DEFAULT_TIMEZONE = "UTC"


def _normalize_timezone(timezone: str | None) -> str:
    """Validate an IANA timezone name, falling back to ``'UTC'``.

    The value comes from the browser (``Intl.DateTimeFormat().resolvedOptions()
    .timeZone``) via a hidden form field, so it is untrusted: missing, blank, or
    garbage all resolve to ``'UTC'`` rather than raising. We check membership in
    ``zoneinfo.available_timezones()`` so only a real IANA name is stored.
    """
    if not timezone:
        return DEFAULT_TIMEZONE
    candidate = timezone.strip()
    if candidate in available_timezones():
        return candidate
    return DEFAULT_TIMEZONE


class AccountError(Exception):
    """Base class for account-layer errors."""


class IdentityTakenError(AccountError):
    """Raised when an identity (provider+provider_id, or email) already exists."""


class UsernameTakenError(IdentityTakenError):
    """Raised when a username is already attached to another live account."""


class EmailTakenError(IdentityTakenError):
    """Raised when a recovery email is already attached to another live account."""


def _now_iso() -> str:
    return datetime.now(UTC).isoformat()


def _row_to_dict(row: sqlite3.Row | None) -> dict[str, Any] | None:
    return dict(row) if row is not None else None


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


def get_user_timezone(owner_id: int) -> ZoneInfo:
    """Return the owner's stored timezone as a ``ZoneInfo``.

    Reads ``user.timezone`` for *owner_id* and constructs a ``ZoneInfo``. Falls
    back to ``ZoneInfo("UTC")`` if the user is missing or the stored value is
    somehow not a loadable IANA name — callers doing day/week-boundary math can
    rely on always getting a valid zone, never an exception.
    """
    with db.connect() as conn:
        conn.execute("BEGIN")
        row = conn.execute("SELECT timezone FROM user WHERE id = ?", (owner_id,)).fetchone()
    if row is None or not row["timezone"]:
        return ZoneInfo(DEFAULT_TIMEZONE)
    try:
        return ZoneInfo(row["timezone"])
    except Exception:  # noqa: BLE001 - any zoneinfo load failure falls back to UTC
        return ZoneInfo(DEFAULT_TIMEZONE)


def find_by_provider(auth_provider: str, provider_id: str) -> dict[str, Any] | None:
    """Find a user by OAuth identity ``(auth_provider, provider_id)``."""
    with db.connect() as conn:
        conn.execute("BEGIN")
        row = conn.execute(
            "SELECT * FROM user"
            " WHERE auth_provider = ? AND provider_id = ? AND deleted_at IS NULL",
            (auth_provider, provider_id),
        ).fetchone()
        return _row_to_dict(row)


def find_by_username(username: str) -> dict[str, Any] | None:
    """Find a user by ``username`` (the password-auth identity key).

    A plain lookup against the ``username`` column. The caller is responsible for
    normalizing input (lowercase/NFKC) before passing it in.
    """
    with db.connect() as conn:
        conn.execute("BEGIN")
        row = conn.execute(
            "SELECT * FROM user WHERE username = ? AND deleted_at IS NULL",
            (username,),
        ).fetchone()
        return _row_to_dict(row)


def find_by_email(email: str) -> dict[str, Any] | None:
    """Find a user by the recovery ``email`` column.

    Used only for the optional-email uniqueness check during signup — never for
    login (login is by ``username``).
    """
    with db.connect() as conn:
        conn.execute("BEGIN")
        row = conn.execute(
            "SELECT * FROM user WHERE email = ? AND deleted_at IS NULL",
            (email,),
        ).fetchone()
        return _row_to_dict(row)


# ---------------------------------------------------------------------------
# Creation
# ---------------------------------------------------------------------------


def create_guest(timezone: str | None = None) -> int:
    """Mint an anonymous guest user and return its id.

    Called on the user's *first interaction*, never on bare page load — the
    bot-guard rule. ``provider_id`` / ``password_hash`` stay NULL;
    ``last_active_at`` is stamped now so the reaper has a baseline. *timezone* is
    the untrusted browser-detected IANA name; it's validated (``'UTC'`` fallback)
    and stored at creation only.
    """
    now = _now_iso()
    tz = _normalize_timezone(timezone)
    with db.connect() as conn:
        conn.execute("BEGIN")
        cur = conn.execute(
            "INSERT INTO user (auth_provider, timezone, last_active_at) VALUES ('guest', ?, ?)",
            (tz, now),
        )
        return int(cur.lastrowid)


def create_username_user(
    username: str,
    password_hash: str,
    email: str | None = None,
    timezone: str | None = None,
) -> int:
    """Create a username/password user. *password_hash* is the Argon2id encoded hash.

    The username is the identity key (and seeds ``display_name``); *email* is an
    optional recovery address. *timezone* is the untrusted browser-detected IANA
    name, validated (``'UTC'`` fallback) and stored at creation only. Raises
    ``IdentityTakenError`` if the username is already taken, or if *email* is
    given and already taken. New real accounts start ``public`` and stamped as
    having already cleared the legacy welcome-sharing gate.
    """
    tz = _normalize_timezone(timezone)
    now = _now_iso()
    with db.connect() as conn:
        conn.execute("BEGIN")
        existing = conn.execute(
            "SELECT 1 FROM user WHERE username = ?",
            (username,),
        ).fetchone()
        if existing is not None:
            raise UsernameTakenError(f"username {username!r} is already taken")
        if email is not None:
            email_taken = conn.execute(
                "SELECT 1 FROM user WHERE email = ?",
                (email,),
            ).fetchone()
            if email_taken is not None:
                raise EmailTakenError(f"email {email!r} is already taken")
        cur = conn.execute(
            "INSERT INTO user"
            " (auth_provider, username, password_hash, email, display_name, timezone,"
            " last_active_at, visibility, consent_seen_at, private_redefinition_seen_at)"
            " VALUES ('email', ?, ?, ?, ?, ?, ?, 'public', ?, ?)",
            (username, password_hash, email, username, tz, now, now, now),
        )
        return int(cur.lastrowid)


def create_oauth_user(
    auth_provider: str,
    provider_id: str,
    display_name: str | None,
    timezone: str | None = None,
) -> int:
    """Create a fresh OAuth user (no guest to upgrade). Returns its id.

    *timezone* is the untrusted browser-detected IANA name, validated (``'UTC'``
    fallback) and stored at creation only. New real accounts start ``public``
    and stamped as having already cleared the legacy welcome-sharing gate.
    """
    if auth_provider != "google":
        raise AccountError(f"{auth_provider!r} is not an OAuth provider")
    tz = _normalize_timezone(timezone)
    now = _now_iso()
    with db.connect() as conn:
        conn.execute("BEGIN")
        existing = conn.execute(
            "SELECT id FROM user WHERE auth_provider = ? AND provider_id = ?",
            (auth_provider, provider_id),
        ).fetchone()
        if existing is not None:
            raise IdentityTakenError(f"{auth_provider} identity {provider_id!r} already exists")
        cur = conn.execute(
            "INSERT INTO user (auth_provider, provider_id, display_name, timezone,"
            " last_active_at, visibility, consent_seen_at, private_redefinition_seen_at)"
            " VALUES (?, ?, ?, ?, ?, 'public', ?, ?)",
            (auth_provider, provider_id, display_name, tz, now, now, now),
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
    username: str | None = None,
    email: str | None = None,
) -> dict[str, Any]:
    """Attach a real-provider identity to an existing (guest) user **in place**.

    This is the upgrade. The row keeps its ``id`` / ``owner_id``, so every owned
    row already pointing at it is preserved with zero migration — only the
    identity columns change.

    The caller is responsible for having verified signup consent and for
    resolving the edge case where the identity already maps to a *different*
    account (see ``find_by_provider`` / ``find_by_email`` before calling). This
    function does a final guard so a race can't create a duplicate identity.
    Upgraded rows become ``public`` and stamped as having already cleared the
    legacy welcome-sharing gate.
    """
    if auth_provider not in {"google", "email"}:
        raise AccountError(f"{auth_provider!r} is not a real provider")

    now = _now_iso()
    with db.connect() as conn:
        conn.execute("BEGIN")
        target = conn.execute("SELECT * FROM user WHERE id = ?", (user_id,)).fetchone()
        if target is None:
            raise AccountError(f"user {user_id} does not exist")

        # Final uniqueness guard against another row owning this identity.
        clash_exc: type[IdentityTakenError] = IdentityTakenError
        if auth_provider == "google":
            clash = conn.execute(
                "SELECT id FROM user WHERE auth_provider = ? AND provider_id = ? AND id != ?",
                (auth_provider, provider_id, user_id),
            ).fetchone()
        else:  # email
            clash = conn.execute(
                "SELECT id FROM user WHERE username = ? AND id != ?",
                (username, user_id),
            ).fetchone()
            clash_exc = UsernameTakenError
            if clash is None and email is not None:
                clash = conn.execute(
                    "SELECT id FROM user WHERE email = ? AND id != ?",
                    (email, user_id),
                ).fetchone()
                if clash is not None:
                    clash_exc = EmailTakenError
        if clash is not None:
            raise clash_exc(
                f"{auth_provider} identity already mapped to user {clash['id']}"
            )

        if auth_provider == "email":
            conn.execute(
                "UPDATE user SET auth_provider = ?, provider_id = ?, password_hash = ?,"
                " username = ?, email = ?, display_name = ?, last_active_at = ?, visibility = 'public',"
                " consent_seen_at = ?, private_redefinition_seen_at = ?"
                " WHERE id = ?",
                (
                    auth_provider,
                    provider_id,
                    password_hash,
                    username,
                    email,
                    username,
                    now,
                    now,
                    now,
                    user_id,
                ),
            )
        else:  # google — unchanged behavior
            conn.execute(
                "UPDATE user SET auth_provider = ?, provider_id = ?, password_hash = ?,"
                " display_name = ?, last_active_at = ?, visibility = 'public',"
                " consent_seen_at = ?, private_redefinition_seen_at = ? WHERE id = ?",
                (
                    auth_provider,
                    provider_id,
                    password_hash,
                    display_name,
                    now,
                    now,
                    now,
                    user_id,
                ),
            )
        row = conn.execute("SELECT * FROM user WHERE id = ?", (user_id,)).fetchone()
        return dict(row)


def update_email(user_id: int, email: str | None) -> dict[str, Any]:
    """Update the recovery email for an existing live account."""
    with db.connect() as conn:
        conn.execute("BEGIN")
        target = conn.execute(
            "SELECT * FROM user WHERE id = ? AND deleted_at IS NULL",
            (user_id,),
        ).fetchone()
        if target is None:
            raise AccountError(f"user {user_id} does not exist")
        if email is not None:
            clash = conn.execute(
                "SELECT id FROM user WHERE email = ? AND id != ? AND deleted_at IS NULL",
                (email, user_id),
            ).fetchone()
            if clash is not None:
                raise EmailTakenError(f"email {email!r} is already taken")
        conn.execute("UPDATE user SET email = ? WHERE id = ?", (email, user_id))
        row = conn.execute("SELECT * FROM user WHERE id = ?", (user_id,)).fetchone()
        return dict(row)


# ---------------------------------------------------------------------------
# Activity + deletion
# ---------------------------------------------------------------------------


VALID_VISIBILITIES = frozenset({"public", "private"})


def set_visibility_consent(owner_id: int, visibility: str) -> None:
    """Record the user's one-time visibility choice for *owner_id*.

    Writes ``user.visibility`` (``'public'`` | ``'private'``) and stamps
    ``consent_seen_at`` now (UTC ISO) so the one-time consent screen never shows
    again. Takes *owner_id* as a required argument per the owner-scoping
    convention. Raises ``AccountError`` for any visibility value outside
    ``VALID_VISIBILITIES`` — the route validates first, but this is a final guard
    so a bad value can never reach the ``CHECK`` constraint.

    Also stamps ``private_redefinition_seen_at`` in the same write. The
    welcome-sharing and account-settings copy already describe the three-tier
    meaning of ``private``, so anyone who passes through this write path has
    already consented to that meaning — they must not then be shown the
    re-consent interstitial. Stamping here makes the re-consent gate fire
    *only* for pre-existing accounts that chose ``private`` under the old copy.
    """
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
    """Stamp ``private_redefinition_seen_at`` now for *owner_id*.

    Records that the user acknowledged the one-time "what Private means has
    changed" interstitial, so the re-consent gate never sends them there again.
    Leaves ``visibility`` and ``consent_seen_at`` untouched — this is purely an
    acknowledgement, not a re-choice. Takes *owner_id* as a required argument
    per the owner-scoping convention.
    """
    with db.connect() as conn:
        conn.execute("BEGIN")
        conn.execute(
            "UPDATE user SET private_redefinition_seen_at = ? WHERE id = ?",
            (_now_iso(), owner_id),
        )


def touch_last_active(user_id: int) -> None:
    """Bump ``last_active_at`` to now. Feeds the guest-reaper retention timer."""
    with db.connect() as conn:
        conn.execute("BEGIN")
        conn.execute(
            "UPDATE user SET last_active_at = ? WHERE id = ?",
            (_now_iso(), user_id),
        )


def delete_user(user_id: int) -> bool:
    """Remove account access while preserving owned history.

    The tombstoned row keeps no reusable login identifiers: recovery email,
    provider id, and password hash are cleared so a future signup can claim the
    same email address without colliding with the deleted account.
    """
    with db.connect() as conn:
        conn.execute("BEGIN")
        cur = conn.execute(
            "UPDATE user"
            " SET username = ?, display_name = 'deleted-user', email = NULL,"
            " provider_id = NULL, password_hash = NULL, suspended_at = NULL,"
            " deleted_at = ?, comments_seen_at = NULL"
            " WHERE id = ? AND deleted_at IS NULL",
            (_deleted_username(conn, user_id), _now_iso(), user_id),
        )
        return cur.rowcount > 0
