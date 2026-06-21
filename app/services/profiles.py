"""Public-profile lookups: URL identifiers -> internal ids, plus the single
visibility authority.

Renderer-agnostic: no HTTP, no templates. The URL lookups
(``/@{username}`` and ``/@{username}/{activity-slug}``) go from a URL to
internal ids — keep them small and well-tested.

THE SINGLE VISIBILITY AUTHORITY
-------------------------------
``viewer_capability`` (and its derived ``can_view_activity_detail``) is the one
and only place where a visibility decision is made. Routes MUST NOT branch on a
user's ``visibility`` column directly, and MUST NOT cache a capability — every
request reads live state, because a block/disconnect/consent change must take
effect immediately. The function is fail-closed: any ambiguity (no session,
pending/declined connection, accepted-without-consent, a block in either
direction) resolves to the least-privileged outcome the precedence allows.

Everything here operates on an already-open connection (per
``app/models/db.py``: one connection per request, parameterized queries).
"""

from __future__ import annotations

import sqlite3
from typing import Literal
from urllib.parse import urlsplit

Capability = Literal["owner", "blocked", "connected", "public", "limited"]


def get_public_user(conn: sqlite3.Connection, username: str) -> dict | None:
    """Look up a user by *username* for the public-profile routes.

    Returns ``None`` when no such username exists, or when the matched account
    is a guest (``auth_provider='guest'``). Guests have no username in practice
    — they can't own a public URL — but the guest check is kept explicit and
    defensive so a future code path that assigns a guest a username can't
    accidentally expose one.

    On a match, returns at least ``{"id", "username", "visibility",
    "auth_provider", "consent_seen_at"}``. The caller decides, from
    ``visibility``, whether to render full content or the minimal "this page
    is private" stub; the owner-viewing branch in ``GET /@{username}`` also
    needs ``auth_provider``/``consent_seen_at`` to re-run the one-time
    visibility-consent gate.
    """
    row = conn.execute(
        "SELECT id, username, visibility, auth_provider, consent_seen_at FROM user WHERE username = ?",
        (username,),
    ).fetchone()
    if row is None:
        return None
    if row["auth_provider"] == "guest":
        return None
    return {
        "id": row["id"],
        "username": row["username"],
        "visibility": row["visibility"],
        "auth_provider": row["auth_provider"],
        "consent_seen_at": row["consent_seen_at"],
    }


def resolve_activity_slug(conn: sqlite3.Connection, owner_id: int, slug: str) -> int | None:
    """Resolve a sub-tally *slug* to its id for *owner_id*.

    Looks up the active (``archived_at IS NULL``) ``activity`` owned by
    *owner_id* with the given *slug*. Returns the id, or ``None`` when there is
    no such slug — including the case where the slug belongs to a *different*
    owner (the query is always owner-scoped, so a cross-owner slug never
    resolves here).
    """
    row = conn.execute(
        "SELECT id FROM activity WHERE owner_id = ? AND slug = ? AND archived_at IS NULL LIMIT 1",
        (owner_id, slug),
    ).fetchone()
    return row["id"] if row is not None else None


def is_owner_viewing(*, current_user_id: int | None, profile_user_id: int) -> bool:
    """Return ``True`` only when the viewer is the profile's owner.

    Pure function — no DB access. This is the security boundary for the owner
    vs. visitor branch in the unified ``/@{username}/{slug}`` route: it must be
    a single tested helper, never inlined in a handler. Fail-closed — any
    ambiguity (no ``current_user_id``, mismatch) returns ``False``.
    """
    return current_user_id is not None and current_user_id == profile_user_id


def is_connected(conn: sqlite3.Connection, user_a_id: int, user_b_id: int) -> bool:
    """Return ``True`` iff *user_a* and *user_b* are fellows.

    A "fellow" requires BOTH ``status='accepted'`` AND a non-null
    ``sharing_consent_at`` on the single canonical ``connection`` row for the
    pair. ``sharing_consent_at`` is the bit that actually gates private-note
    exposure (migration 0010): "accepted but not yet consented" is a real,
    queryable state that is NOT a fellow connection — it falls through to the
    account's public/limited visibility, never to ``connected``.

    One indexed lookup on the canonical ``(user_lo, user_hi)`` pair. The pair is
    directionless, so argument order does not matter.
    """
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
    """Return ``True`` iff a block exists between the two users in EITHER direction.

    A block is one-directional in the table, but for a visibility decision it
    silences both parties: if A blocked B, B must not see A (no existence
    oracle), and A must not see B. So we check both directions in one query.
    """
    row = conn.execute(
        "SELECT 1 FROM block"
        " WHERE (blocker_id = ? AND blocked_id = ?)"
        " OR (blocker_id = ? AND blocked_id = ?)"
        " LIMIT 1",
        (user_a_id, user_b_id, user_b_id, user_a_id),
    ).fetchone()
    return row is not None


def viewer_capability(
    conn: sqlite3.Connection,
    *,
    current_user_id: int | None,
    profile_user: dict,
) -> Capability:
    """Resolve what *current_user* may see of *profile_user* — the sole authority.

    Returns one of ``"owner" | "blocked" | "connected" | "public" | "limited"``,
    evaluated in this fail-closed precedence (first match wins):

    1. ``"owner"``    — viewer is the profile's owner.
    2. ``"blocked"``  — a block exists in either direction (overrides public
       visibility; the route maps this to 404 — no existence oracle).
    3. ``"connected"`` — viewer is an accepted-and-consented fellow (full
       record visible even on a private profile).
    4. ``"public"``   — the profile's ``visibility`` is ``"public"``.
    5. ``"limited"``  — everything else (the character-sheet-only view).

    Anonymous viewers (``current_user_id is None``) can never reach owner,
    blocked, or connected — they fall straight through to public/limited based
    on the profile's visibility. Pure of HTTP; never cache the result.
    """
    profile_user_id = profile_user["id"]

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
    """Return ``True`` iff the viewer may open ``/@{username}/{slug}`` detail.

    True only for ``owner``, ``connected``, and ``public`` capabilities. For
    ``limited`` and ``blocked`` it is ``False``; the *route* decides how to
    respond to each (limited → redirect to the profile; blocked → 404). This
    helper only returns the bool — call ``viewer_capability`` directly when the
    blocked/limited distinction is needed.
    """
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
    """Return ``True`` iff *current_user* may comment on an entry of *activity_id*.

    Comment permission is **exactly** the existing entry-detail visibility plus
    a login check — there is no separate comment-visibility tier. This helper
    therefore does not reimplement any authorization logic: it delegates wholly
    to ``can_view_activity_detail`` and only adds the "must be logged in"
    requirement (an anonymous viewer may *read* a public profile's comments but
    can never post one).

    ``activity_id`` is accepted for signature symmetry with the route caller and
    for forward-compatibility; the visibility decision itself is per-profile
    (owner/fellow/public) and does not vary per activity. Fail-closed: any
    ambiguity resolves to ``False``.
    """
    return current_user_id is not None and can_view_activity_detail(
        conn,
        current_user_id=current_user_id,
        profile_user=profile_user,
    )


def canonical_profile_url(username: str) -> str:
    """Build the canonical public-profile URL for *username* (e.g. ``/@yuki``).

    Single source of truth for the profile URL prefix — renames touch one line.
    """
    return f"/@{username}"


def canonical_activity_url(username: str, slug: str) -> str:
    """Build the canonical activity URL for *username* + *slug* (e.g. ``/@yuki/kendo``).

    Single source of truth for the activity URL prefix — renames touch one line.
    """
    return f"/@{username}/{slug}"


def safe_next_path(value: str | None) -> str | None:
    """Validate *value* as a same-origin relative path for a post-login redirect.

    Returns the value unchanged when it is safe to redirect to, or ``None``
    when it is missing or unsafe — callers must treat ``None`` as "no
    redirect target" (fall back to the default landing page), never pass an
    unsafe value through.

    Pure, no DB/HTTP — this is the single place that decides what counts as
    "same-origin relative path" so the rule can't drift between call sites.
    Rejects:

    - empty/``None``
    - anything not starting with a single ``/`` (relative paths, bare
      strings, ``javascript:`` etc. — none of those start with ``/``)
    - scheme-relative URLs (``//evil.com/...``) — these parse as having no
      scheme but a real ``netloc``, which is exactly the open-redirect shape
      a leading ``/`` alone doesn't rule out
    - any value that parses with a scheme or netloc at all (``https://...``,
      ``http://...``) — defense in depth alongside the ``//`` check, since
      ``urlsplit`` already exposes those independently
    """
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
    """Read a ``activity`` row only if it belongs to *owner_id*.

    Returns the full row as a dict (including ``slug``, ``archived_at``,
    ``name``) or ``None`` when no such row exists or it belongs to another
    owner. ``owner_id`` is a required keyword-only argument so an owner-scope
    predicate can never be omitted (multi-user isolation is non-negotiable).
    """
    row = conn.execute(
        "SELECT * FROM activity WHERE id = ? AND owner_id = ?",
        (activity_id, owner_id),
    ).fetchone()
    return dict(row) if row is not None else None
