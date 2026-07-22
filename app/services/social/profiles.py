"""Public-profile lookups: URL identifiers -> internal ids, plus the single
visibility authority.

Renderer-agnostic: no HTTP, no templates.
"""

from __future__ import annotations

import sqlite3
from typing import Literal
from urllib.parse import urlsplit

Capability = Literal["owner", "blocked", "connected", "public", "limited"]


def get_public_user(conn: sqlite3.Connection, username: str) -> dict | None:
    """Look up a user by *username* for the public-profile routes.

    Returns ``None`` when no such username exists or the account is deleted.
    On a match, returns at least ``{"id", "username", "visibility",
    "consent_seen_at"}``.
    """
    row = conn.execute(
        "SELECT id, username, visibility, search_discovery, consent_seen_at, bio"
        " FROM user WHERE username = ? AND deleted_at IS NULL",
        (username,),
    ).fetchone()
    if row is None:
        return None
    return {
        "id": row["id"],
        "username": row["username"],
        "visibility": row["visibility"],
        "search_discovery": bool(row["search_discovery"]),
        "consent_seen_at": row["consent_seen_at"],
        "bio": row["bio"],
    }


def resolve_activity_slug(conn: sqlite3.Connection, owner_id: int, slug: str) -> int | None:
    """Resolve an activity *slug* to its id for *owner_id*."""
    row = conn.execute(
        "SELECT id FROM activity WHERE owner_id = ? AND slug = ? AND archived_at IS NULL LIMIT 1",
        (owner_id, slug),
    ).fetchone()
    return row["id"] if row is not None else None


def is_owner_viewing(*, current_user_id: int | None, profile_user_id: int) -> bool:
    """Return ``True`` only when the viewer is the profile's owner."""
    return current_user_id is not None and current_user_id == profile_user_id


def is_connected(conn: sqlite3.Connection, user_a_id: int, user_b_id: int) -> bool:
    """Return ``True`` iff *user_a* and *user_b* are fellows."""
    lo, hi = (user_a_id, user_b_id) if user_a_id < user_b_id else (user_b_id, user_a_id)
    row = conn.execute(
        "SELECT 1 FROM connection"
        " WHERE user_lo = ? AND user_hi = ?"
        " AND status = 'accepted' AND sharing_consent_at IS NOT NULL"
        " LIMIT 1",
        (lo, hi),
    ).fetchone()
    return row is not None


def is_blocked(conn: sqlite3.Connection, user_a_id: int, user_b_id: int) -> bool:
    """Return ``True`` iff *user_a* has blocked *user_b*."""
    return conn.execute(
        "SELECT 1 FROM block WHERE blocker_id = ? AND blocked_id = ? LIMIT 1",
        (user_a_id, user_b_id),
    ).fetchone() is not None


def is_active_user(conn: sqlite3.Connection, user_id: int) -> bool:
    """Return ``True`` if the user exists and is not suspended/deleted."""
    return conn.execute(
        "SELECT 1 FROM user WHERE id = ? AND suspended_at IS NULL AND deleted_at IS NULL LIMIT 1",
        (user_id,),
    ).fetchone() is not None


def viewer_capability(
    conn: sqlite3.Connection,
    *,
    current_user_id: int | None,
    profile_user: dict,
) -> Capability:
    """Determine the viewer's capability for a given profile.

    Returns one of: ``"owner" | "blocked" | "connected" | "public" | "limited"``.
    """
    profile_user_id = int(profile_user["id"])

    if current_user_id is not None and not is_active_user(conn, current_user_id):
        current_user_id = None

    if is_owner_viewing(current_user_id=current_user_id, profile_user_id=profile_user_id):
        return "owner"

    if current_user_id is not None:
        if is_blocked(conn, current_user_id, profile_user_id):
            return "blocked"
        if is_connected(conn, current_user_id, profile_user_id):
            return "connected"

    if profile_user["visibility"] == "public":
        return "public"

    return "limited"


def can_view_activity_detail(
    conn: sqlite3.Connection,
    *,
    current_user_id: int | None,
    profile_user: dict,
) -> bool:
    """Return ``True`` iff the viewer may open ``/@{username}/{slug}`` detail."""
    return viewer_capability(
        conn,
        current_user_id=current_user_id,
        profile_user=profile_user,
    ) in {"owner", "connected", "public"}


def can_comment_on_entry(
    conn: sqlite3.Connection,
    *,
    current_user_id: int | None,
    profile_user: dict,
    activity_id: int,
) -> bool:
    """Return ``True`` iff *current_user* may comment on an entry of *activity_id*."""
    return current_user_id is not None and is_active_user(conn, current_user_id) and can_view_activity_detail(
        conn,
        current_user_id=current_user_id,
        profile_user=profile_user,
    )


def canonical_profile_url(username: str) -> str:
    """Build the canonical public-profile URL for *username*."""
    return f"/@{username}"


def canonical_activity_url(username: str, slug: str) -> str:
    """Build the canonical activity URL for *username* + *slug*."""
    return f"/@{username}/{slug}"


def safe_next_path(value: str | None) -> str | None:
    """Validate *value* as a same-origin relative path for a post-login redirect."""
    if not value:
        return None
    if not value.startswith("/") or value.startswith("//"):
        return None
    parts = urlsplit(value)
    if parts.scheme or parts.netloc:
        return None
    return value


def get_activity_for_owner(
    conn: sqlite3.Connection, *, activity_id: int, owner_id: int
) -> dict | None:
    """Read a ``activity`` row only if it belongs to *owner_id*."""
    row = conn.execute(
        "SELECT * FROM activity WHERE id = ? AND owner_id = ?",
        (activity_id, owner_id),
    ).fetchone()
    return dict(row) if row is not None else None
