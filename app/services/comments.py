"""Entry comments for the Mushin service layer.

Renderer-agnostic: no HTTP, no Jinja, no HXML. Functions take the ids they need
plus the explicit actor (``viewer_id`` / ``author_id`` / ``requester_id``) and
return plain Python data structures the renderers consume.

A *comment* is co-owned, cross-user personal data: free text written by one user
(``author_id``) about another user's entry. Two security properties shape this
module:

1. **Visibility is never stored or cached.** Whether a viewer may read a
   comment is re-derived live from ``profiles.can_view_activity_detail`` on
   every read. A revoked fellow connection, a fresh block, or a public->private
   flip silently stops a comment from rendering for the viewer who lost access —
   the row is never deleted for that reason. ``list_comments`` therefore
   re-checks the capability itself (defense in depth) and returns ``[]`` — never
   an error — for a viewer without access.

2. **Soft delete, author-or-owner only.** Users never hard-delete a comment;
   ``soft_delete_comment`` stamps ``deleted_at`` and is allowed only for the
   comment's ``author_id`` or the entry's owner. Hard deletion happens solely by
   ``ON DELETE CASCADE`` when *either* the author's or the entry-owner's account
   is deleted.

The single authority for any visibility decision is
``app/services/profiles.py`` — this module wraps it, never reimplements it.
Operates on an already-open connection (per ``app/models/db.py``).
"""

from __future__ import annotations

import sqlite3
from datetime import UTC, datetime
from typing import Any

import structlog

from app.services import profiles

log = structlog.get_logger()

_COMMENT_MAX_CHARS = 200
_COMMENT_MAX_LINES = 5


class CommentNotFoundError(LookupError):
    """Raised when a comment row doesn't exist (or is already soft-deleted)."""


class CommentPermissionError(PermissionError):
    """Raised when the requester may neither author-delete nor owner-delete."""


def _now_iso() -> str:
    """Current instant as a UTC ISO8601 string (timezone-aware)."""
    return datetime.now(UTC).isoformat()


def _entry_profile_context(conn: sqlite3.Connection, entry_id: int) -> tuple[int, dict] | None:
    """Resolve an *entry_id* to ``(activity_id, profile_user)`` or ``None``.

    The ``profile_user`` dict carries exactly what ``profiles`` needs for a
    capability decision: the entry-owner's ``id`` and ``visibility``. Returns
    ``None`` when the entry doesn't exist (a deleted entry has no comments to
    show, by cascade). One indexed join entry -> user.
    """
    row = conn.execute(
        "SELECT e.activity_id AS activity_id, e.owner_id AS owner_id, u.visibility AS visibility"
        " FROM entry e JOIN user u ON u.id = e.owner_id"
        " WHERE e.id = ?",
        (entry_id,),
    ).fetchone()
    if row is None:
        return None
    profile_user = {"id": row["owner_id"], "visibility": row["visibility"]}
    return row["activity_id"], profile_user


def counts_for_entries(conn: sqlite3.Connection, entry_ids: list[int]) -> dict[int, int]:
    """Map ``entry_id -> visible comment count`` for *entry_ids*.

    A plain count of non-soft-deleted comments — no capability re-check here,
    because this is only ever used to render the collapsed affordance on a
    detail page a viewer has already been cleared to see (the route gates the
    whole page via ``can_view_activity_detail`` before this runs). The thread
    fragment itself (``list_comments``) re-checks live on every expand, so a
    stale count here is, at worst, an affordance that opens to an empty list —
    never a leak of comment content.
    """
    if not entry_ids:
        return {}
    placeholders = ",".join("?" for _ in entry_ids)
    rows = conn.execute(
        f"SELECT entry_id, COUNT(*) AS n FROM comment"
        f" WHERE entry_id IN ({placeholders}) AND deleted_at IS NULL"
        f" GROUP BY entry_id",
        tuple(entry_ids),
    ).fetchall()
    return {r["entry_id"]: r["n"] for r in rows}


def list_comments(
    conn: sqlite3.Connection, entry_id: int, *, viewer_id: int | None
) -> list[dict[str, Any]]:
    """Return the visible comments on *entry_id*, oldest first, for *viewer_id*.

    Defense in depth: this function re-checks ``can_view_activity_detail`` for
    the viewer against the entry's owner before returning any rows — it never
    trusts that the caller already gated the read. A viewer who lacks access
    (anonymous-on-private, non-fellow, freshly blocked, or a profile that flipped
    public->private after the comment was posted) gets ``[]``, **not** an
    exception: a viewer who has lost access should see nothing, not an error.

    Soft-deleted comments (``deleted_at IS NOT NULL``) are always excluded.
    Each returned dict carries ``id``, ``entry_id``, ``author_id``,
    ``author_username``, ``author_display_name``, ``body`` and ``created_at``.
    """
    ctx = _entry_profile_context(conn, entry_id)
    if ctx is None:
        return []
    _activity_id, profile_user = ctx

    if not profiles.can_view_activity_detail(
        conn,
        current_user_id=viewer_id,
        profile_user=profile_user,
    ):
        return []

    rows = conn.execute(
        "SELECT c.id AS id, c.entry_id AS entry_id, c.author_id AS author_id,"
        "       u.username AS author_username, u.display_name AS author_display_name,"
        "       c.body AS body, c.created_at AS created_at, c.hidden_at AS hidden_at"
        "  FROM comment c JOIN user u ON u.id = c.author_id"
        " WHERE c.entry_id = ? AND c.deleted_at IS NULL"
        " ORDER BY c.created_at ASC, c.id ASC",
        (entry_id,),
    ).fetchall()
    return [dict(r) for r in rows]


def create_comment(conn: sqlite3.Connection, entry_id: int, *, author_id: int, body: str) -> int:
    """Insert a comment by *author_id* on *entry_id*; return the new comment id.

    The *route* is responsible for calling ``profiles.can_comment_on_entry``
    before invoking this. We do **not** re-run the full capability check here:
    doing so would require the route to also pass a ``profile_user`` dict, and
    the authorization authority for a *write* is the route's pre-check — adding a
    second, differently-shaped check here would risk drifting from that single
    authority. We do enforce a cheap, schema-level guard that does not duplicate
    any visibility logic: the body must be non-empty after trimming (matching the
    table's ``CHECK (length(trim(body)) > 0)``), surfaced as a ``ValueError``
    instead of a raw ``sqlite3.IntegrityError`` so callers get a clean signal.

    Caller owns the transaction boundary (commit/rollback).
    """
    trimmed = body.strip()
    if not trimmed:
        raise ValueError("comment body must not be empty")
    if len(trimmed) > _COMMENT_MAX_CHARS:
        raise ValueError("comment body exceeds max characters")
    if len(trimmed.splitlines()) > _COMMENT_MAX_LINES:
        raise ValueError("comment body exceeds max lines")

    cur = conn.execute(
        "INSERT INTO comment (entry_id, author_id, body, created_at) VALUES (?, ?, ?, ?)",
        (entry_id, author_id, trimmed, _now_iso()),
    )
    comment_id = cur.lastrowid
    log.info("comment.created", comment_id=comment_id, entry_id=entry_id, author_id=author_id)
    return comment_id


def soft_delete_comment(conn: sqlite3.Connection, comment_id: int, *, requester_id: int) -> None:
    """Soft-delete *comment_id* on behalf of *requester_id*.

    Allowed only when *requester_id* is the comment's ``author_id`` OR the owner
    of the entry the comment hangs off (entry -> owner_id). Anyone else gets a
    ``CommentPermissionError`` — never a silent no-op, so the route can map the
    denial to a 403. A missing or already-soft-deleted comment raises
    ``CommentNotFoundError``.

    Caller owns the transaction boundary (commit/rollback).
    """
    row = conn.execute(
        "SELECT c.author_id AS author_id, e.owner_id AS entry_owner_id"
        "  FROM comment c JOIN entry e ON e.id = c.entry_id"
        " WHERE c.id = ? AND c.deleted_at IS NULL",
        (comment_id,),
    ).fetchone()
    if row is None:
        raise CommentNotFoundError(f"comment {comment_id} not found")
    if not profiles.is_active_user(conn, requester_id):
        raise CommentPermissionError(f"user {requester_id} may not delete comment {comment_id}")

    if requester_id != row["author_id"] and requester_id != row["entry_owner_id"]:
        raise CommentPermissionError(f"user {requester_id} may not delete comment {comment_id}")

    conn.execute(
        "UPDATE comment SET deleted_at = ? WHERE id = ? AND deleted_at IS NULL",
        (_now_iso(), comment_id),
    )
    log.info("comment.soft_deleted", comment_id=comment_id, requester_id=requester_id)


def unseen_comment_count(conn: sqlite3.Connection, owner_id: int) -> int:
    """Count *owner_id*'s unseen comments — the home-page badge, derived live.

    Counts comments that are: on an entry owned by *owner_id*, authored by
    *someone else* (a user never gets a badge for their own comments on their own
    entries), not soft-deleted, and newer than *owner_id*'s ``comments_seen_at``
    watermark. A NULL watermark means the user has never cleared the badge, so
    everything counts as unseen.

    No notification table — this is a single query against the existing schema,
    re-derived on every home load.
    """
    row = conn.execute(
        "SELECT COUNT(*) AS n"
        "  FROM comment c"
        "  JOIN entry e ON e.id = c.entry_id"
        "  JOIN user u ON u.id = ?"
        " WHERE e.owner_id = ?"
        "   AND c.author_id != ?"
        "   AND c.deleted_at IS NULL"
        "   AND (u.comments_seen_at IS NULL OR c.created_at > u.comments_seen_at)",
        (owner_id, owner_id, owner_id),
    ).fetchone()
    return int(row["n"])


def list_comments_for_owner(
    conn: sqlite3.Connection,
    owner_id: int,
    *,
    limit: int = 50,
    before_id: int | None = None,
    watermark: str | None = None,
) -> list[dict[str, Any]]:
    """List comments left on *owner_id*'s own entries — the notification feed.

    The notification-history counterpart to ``unseen_comment_count``: same join
    shape (``comment -> entry`` filtered to ``entry.owner_id == owner_id``), but
    returns the comment rows themselves, newest first, instead of a count. It
    joins ``activity`` (for the entry's activity name/slug) and ``user`` (the
    comment's ``author_id``, for the commenter's handle/display name).

    Filtering matches ``unseen_comment_count``: only the owner's own entries,
    excluding soft-deleted comments and the owner's own comments on their own
    entries (a user is never notified of themselves).

    Pagination is keyset (not OFFSET): pass the smallest ``comment_id`` of the
    previous page as *before_id* to fetch the next page (``c.id < before_id``).
    Rows are ordered ``created_at DESC, id DESC`` so the ``id`` cursor is a stable
    tiebreaker for same-instant comments.

    *watermark* is the caller's pre-visit ``comments_seen_at`` value — this
    function neither reads nor writes that column (the caller reads it before
    advancing it). Each row gets an ``is_new`` bool: ``created_at > watermark``,
    or ``True`` for every row when *watermark* is ``None`` (the user has never
    visited the notifications page, so nothing has been seen yet).
    """
    params: list[Any] = [owner_id, owner_id]
    sql = (
        "SELECT c.id AS comment_id,"
        "       c.body AS body,"
        "       c.hidden_at AS hidden_at,"
        "       c.created_at AS created_at,"
        "       u.username AS author_username,"
        "       u.display_name AS author_display_name,"
        "       c.entry_id AS entry_id,"
        "       a.id AS activity_id,"
        "       a.name AS activity_name,"
        "       a.slug AS activity_slug"
        "  FROM comment c"
        "  JOIN entry e ON e.id = c.entry_id"
        "  JOIN activity a ON a.id = e.activity_id"
        "  JOIN user u ON u.id = c.author_id"
        " WHERE e.owner_id = ?"
        "   AND c.author_id != ?"
        "   AND c.deleted_at IS NULL"
    )
    if before_id is not None:
        sql += " AND c.id < ?"
        params.append(before_id)
    sql += " ORDER BY c.created_at DESC, c.id DESC LIMIT ?"
    params.append(limit)

    rows = conn.execute(sql, params).fetchall()

    result: list[dict[str, Any]] = []
    for r in rows:
        row = dict(r)
        row["is_new"] = watermark is None or row["created_at"] > watermark
        result.append(row)
    return result
