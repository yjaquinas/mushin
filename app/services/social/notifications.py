"""Unified social notification feed."""

from __future__ import annotations

import sqlite3
from datetime import UTC, datetime
from typing import Any, Literal

NotificationType = Literal[
    "comment",
    "comment_reply",
    "comment_reply_participant",
    "connection_request",
    "connection_accepted",
]


def current_timestamp_iso() -> str:
    return datetime.now(UTC).isoformat()


def comment_preview(body: str) -> str:
    """Return a compact, single-line notification excerpt for a comment."""
    words = body.split()
    if len(words) <= 12:
        return " ".join(words)
    return f"{' '.join(words[:12])}…"


def create(
    conn: sqlite3.Connection,
    *,
    user_id: int,
    type: NotificationType,
    actor_id: int,
    entry_id: int | None = None,
    comment_id: int | None = None,
    comment_preview: str | None = None,
    created_at: str | None = None,
) -> int:
    """Create one notification row and return its id."""
    cur = conn.execute(
        "INSERT INTO notification (user_id, type, actor_id, entry_id, comment_id, comment_preview, created_at)"
        " VALUES (?, ?, ?, ?, ?, ?, ?)",
        (
            user_id,
            type,
            actor_id,
            entry_id,
            comment_id,
            comment_preview,
            created_at or current_timestamp_iso(),
        ),
    )
    return int(cur.lastrowid)


def unseen_count(conn: sqlite3.Connection, user_id: int) -> int:
    row = conn.execute(
        "SELECT COUNT(*) AS n FROM notification WHERE user_id = ? AND read_at IS NULL",
        (user_id,),
    ).fetchone()
    return int(row["n"])


def mark_read(conn: sqlite3.Connection, user_id: int) -> None:
    conn.execute(
        "UPDATE notification SET read_at = ? WHERE user_id = ? AND read_at IS NULL",
        (current_timestamp_iso(), user_id),
    )


def list_notifications(
    conn: sqlite3.Connection,
    user_id: int,
    *,
    username: str,
    limit: int = 10,
    before_id: int | None = None,
) -> list[dict[str, Any]]:
    params: list[Any] = [user_id]
    sql = (
        "SELECT n.id, n.type, n.actor_id, n.entry_id, n.comment_id, n.comment_preview, n.created_at, n.read_at,"
        "       actor.username AS actor_username,"
        "       owner.username AS owner_username,"
        "       a.name AS activity_name, a.slug AS activity_slug"
        "  FROM notification n"
        "  JOIN user actor ON actor.id = n.actor_id"
        "  LEFT JOIN entry e ON e.id = n.entry_id"
        "  LEFT JOIN activity a ON a.id = e.activity_id"
        "  LEFT JOIN user owner ON owner.id = e.owner_id"
        " WHERE n.user_id = ?"
    )
    if before_id is not None:
        sql += " AND n.id < ?"
        params.append(before_id)
    sql += " ORDER BY julianday(n.created_at) DESC, n.id DESC LIMIT ?"
    params.append(limit)

    rows = conn.execute(sql, params).fetchall()
    return [_row_context(dict(row), username) for row in rows]


def _row_context(row: dict[str, Any], username: str) -> dict[str, Any]:
    row["is_new"] = row["read_at"] is None
    if row["comment_preview"]:
        row["comment_preview"] = comment_preview(row["comment_preview"])
    row["target_url"] = _target_url(row, username)
    return row


def _target_url(row: dict[str, Any], username: str) -> str:
    if row["type"] in {"comment", "comment_reply", "comment_reply_participant"} and row.get("owner_username") and row.get("activity_slug"):
        entry_id = row["entry_id"]
        comment_id = row.get("comment_id")
        fragment = f"#comment-{comment_id}" if comment_id is not None else f"#comment-slot-{entry_id}"
        return (
            f"/@{row['owner_username']}/{row['activity_slug']}"
            f"?entry_id={entry_id}{fragment}"
        )
    if row["type"] == "connection_request":
        return f"/@{username}/fellows"
    if row["type"] == "connection_accepted":
        return f"/@{row['actor_username']}"
    return f"/@{username}"
