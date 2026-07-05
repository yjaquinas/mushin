"""Entry comments for the Mushin service layer.

Renderer-agnostic: no HTTP, no Jinja, no HXML.
"""

from __future__ import annotations

import sqlite3
from datetime import UTC, datetime
from typing import Any

import structlog

from app.auth import users
from app.services.social import profiles

log = structlog.get_logger()

_COMMENT_MAX_CHARS = 200
_COMMENT_MAX_LINES = 5


class CommentNotFoundError(LookupError):
    """Raised when a comment row doesn't exist (or is already soft-deleted)."""


class CommentPermissionError(PermissionError):
    """Raised when the requester may neither author-delete nor owner-delete."""


def current_timestamp_iso(timezone: str | None = None) -> str:
    """Current instant as a timezone-aware ISO string.

    Browser-originated writes pass an IANA timezone so the saved timestamp uses
    the viewer's offset. Non-browser callers fall back to UTC.
    """
    return datetime.now(users.resolve_timezone(timezone)).isoformat()


def _entry_profile_context(conn: sqlite3.Connection, entry_id: int) -> tuple[int, dict] | None:
    """Resolve an *entry_id* to ``(activity_id, profile_user)`` or ``None``."""
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
    """Map ``entry_id -> visible comment count`` for *entry_ids*."""
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
    """Return the visible comments on *entry_id*, oldest first, for *viewer_id*."""
    ctx = _entry_profile_context(conn, entry_id)
    if ctx is None:
        return []
    activity_id, profile_user = ctx
    if not profiles.can_view_activity_detail(
        conn, current_user_id=viewer_id, profile_user=profile_user
    ):
        return []

    rows = conn.execute(
        "SELECT c.id, c.entry_id, c.body, c.created_at, c.deleted_at, c.author_id,"
        " u.username AS author_username"
        " FROM comment c"
        " JOIN user u ON u.id = c.author_id"
        " WHERE c.entry_id = ? AND c.deleted_at IS NULL"
        " ORDER BY julianday(c.created_at) ASC, c.id ASC",
        (entry_id,),
    ).fetchall()

    return [
        {
            "id": r["id"],
            "entry_id": r["entry_id"],
            "author_id": r["author_id"],
            "author_username": r["author_username"],
            "body": r["body"],
            "created_at": r["created_at"],
        }
        for r in rows
    ]


def create_comment(
    conn: sqlite3.Connection,
    entry_id: int,
    author_id: int,
    body: str,
    *,
    timezone: str | None = None,
) -> dict[str, Any]:
    """Create a comment on an entry."""
    trimmed = body.strip()
    if len(trimmed) > _COMMENT_MAX_CHARS:
        raise ValueError("comment exceeds max characters")
    if len(trimmed.splitlines()) > _COMMENT_MAX_LINES:
        raise ValueError("comment exceeds max lines")

    ctx = _entry_profile_context(conn, entry_id)
    if ctx is None:
        raise CommentNotFoundError(f"entry {entry_id} not found")

    now = current_timestamp_iso(timezone)
    cur = conn.execute(
        "INSERT INTO comment (entry_id, author_id, body, created_at) VALUES (?, ?, ?, ?)",
        (entry_id, author_id, trimmed, now),
    )
    comment_id = cur.lastrowid

    row = conn.execute(
        "SELECT * FROM comment WHERE id = ?",
        (comment_id,),
    ).fetchone()
    return dict(row)


def soft_delete_comment(conn: sqlite3.Connection, comment_id: int, requester_id: int) -> None:
    """Soft-delete a comment (author or entry owner only)."""
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
        (current_timestamp_iso(), comment_id),
    )
    log.info("comment.soft_deleted", comment_id=comment_id, requester_id=requester_id)


def unseen_comment_count(conn: sqlite3.Connection, owner_id: int) -> int:
    """Count *owner_id*'s unseen comments — the home-page badge."""
    row = conn.execute(
        "SELECT COUNT(*) AS n"
        "  FROM comment c"
        "  JOIN entry e ON e.id = c.entry_id"
        "  JOIN user u ON u.id = ?"
        " WHERE e.owner_id = ?"
        "   AND c.author_id != ?"
        "   AND c.deleted_at IS NULL"
        "   AND (u.comments_seen_at IS NULL OR julianday(c.created_at) > julianday(u.comments_seen_at))",
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
    """List comments left on *owner_id*'s own entries — the notification feed."""
    params: list[Any] = [owner_id, owner_id]
    sql = (
        "SELECT c.id AS comment_id,"
        "       c.body AS body,"
        "       c.hidden_at AS hidden_at,"
        "       c.created_at AS created_at,"
        "       u.username AS author_username,"
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
    sql += " ORDER BY julianday(c.created_at) DESC, c.id DESC LIMIT ?"
    params.append(limit)

    rows = conn.execute(sql, params).fetchall()

    result: list[dict[str, Any]] = []
    for r in rows:
        row = dict(r)
        row["is_new"] = watermark is None or _is_after(row["created_at"], watermark)
        result.append(row)
    return result


def _is_after(value: str, watermark: str) -> bool:
    try:
        return _timestamp(value) > _timestamp(watermark)
    except (TypeError, ValueError):
        return value > watermark


def _timestamp(value: str) -> float:
    dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=UTC)
    return dt.timestamp()
