"""Admin read models for users and recent content."""

from __future__ import annotations

import sqlite3

_RECENT_LIMIT = 12
_USER_LIMIT = 100


def monitor_context(conn: sqlite3.Connection) -> dict[str, object]:
    """Return recent activity, entry, and comment rows for the admin monitor."""
    return {
        "recent_activities": _recent_activities(conn),
        "recent_entries": _recent_entries(conn),
        "recent_comments": _recent_comments(conn),
    }


def users_context(conn: sqlite3.Connection) -> dict[str, object]:
    """Return user summaries and suggested future tracking fields."""
    return {
        "users": _users(conn),
    }


def user_detail_context(conn: sqlite3.Connection, user_id: int) -> dict[str, object] | None:
    """Return one user's admin detail context, or None when missing."""
    user = _admin_user(conn, user_id)
    if user is None:
        return None
    return {
        "detail_user": user,
        "recent_activities": _recent_activities(conn, owner_id=user_id),
        "recent_entries": _recent_entries(conn, owner_id=user_id),
        "recent_comments": _recent_comments(conn, user_id=user_id),
    }


def _recent_activities(
    conn: sqlite3.Connection, *, owner_id: int | None = None
) -> list[sqlite3.Row]:
    owner_filter = "AND a.owner_id = ?" if owner_id is not None else ""
    params = (owner_id, _RECENT_LIMIT) if owner_id is not None else (_RECENT_LIMIT,)
    return conn.execute(
        f"""
        SELECT a.id, a.name, a.slug, a.created_at, u.id AS user_id,
               u.username, u.display_name
        FROM activity a
        JOIN user u ON u.id = a.owner_id
        WHERE a.archived_at IS NULL
          {owner_filter}
        ORDER BY a.created_at DESC, a.id DESC
        LIMIT ?
        """,  # noqa: S608
        params,
    ).fetchall()


def _recent_entries(conn: sqlite3.Connection, *, owner_id: int | None = None) -> list[sqlite3.Row]:
    owner_filter = "WHERE e.owner_id = ?" if owner_id is not None else ""
    params = (owner_id, _RECENT_LIMIT) if owner_id is not None else (_RECENT_LIMIT,)
    return conn.execute(
        f"""
        SELECT e.id, e.memo, e.created_at, e.hidden_at,
               a.name AS activity_name, a.slug,
               u.id AS user_id, u.username, u.display_name
        FROM entry e
        JOIN activity a ON a.id = e.activity_id
        JOIN user u ON u.id = e.owner_id
        {owner_filter}
        ORDER BY e.created_at DESC, e.id DESC
        LIMIT ?
        """,  # noqa: S608
        params,
    ).fetchall()


def _recent_comments(conn: sqlite3.Connection, *, user_id: int | None = None) -> list[sqlite3.Row]:
    user_filter = (
        "AND (c.author_id = ? OR e.owner_id = ?)"
        if user_id is not None
        else ""
    )
    params = (user_id, user_id, _RECENT_LIMIT) if user_id is not None else (_RECENT_LIMIT,)
    return conn.execute(
        f"""
        SELECT c.id, c.body, c.created_at, c.entry_id, c.hidden_at,
               owner.username AS entry_username,
               owner.display_name AS entry_display_name,
               owner.id AS entry_user_id,
               commenter.username AS comment_username,
               commenter.display_name AS comment_display_name,
               commenter.id AS comment_user_id,
               a.name AS activity_name,
               a.slug
        FROM comment c
        JOIN entry e ON e.id = c.entry_id
        JOIN activity a ON a.id = e.activity_id
        JOIN user owner ON owner.id = e.owner_id
        JOIN user commenter ON commenter.id = c.author_id
        WHERE c.deleted_at IS NULL
          {user_filter}
        ORDER BY c.created_at DESC, c.id DESC
        LIMIT ?
        """,  # noqa: S608
        params,
    ).fetchall()


def _users(conn: sqlite3.Connection) -> list[sqlite3.Row]:
    return conn.execute(
        """
        SELECT u.id, u.username, u.display_name, u.auth_provider, u.created_at,
               u.last_active_at, u.visibility, u.suspended_at, u.deleted_at,
               COUNT(DISTINCT a.id) AS activity_count,
               COUNT(DISTINCT e.id) AS entry_count,
               COUNT(DISTINCT c_owned.id) AS received_comment_count,
               COUNT(DISTINCT c_authored.id) AS authored_comment_count
        FROM user u
        LEFT JOIN activity a ON a.owner_id = u.id AND a.archived_at IS NULL
        LEFT JOIN entry e ON e.owner_id = u.id
        LEFT JOIN comment c_owned ON c_owned.entry_id = e.id AND c_owned.deleted_at IS NULL
        LEFT JOIN comment c_authored ON c_authored.author_id = u.id
            AND c_authored.deleted_at IS NULL
        GROUP BY u.id
        ORDER BY COALESCE(u.last_active_at, u.created_at) DESC, u.id DESC
        LIMIT ?
        """,
        (_USER_LIMIT,),
    ).fetchall()


def _admin_user(conn: sqlite3.Connection, user_id: int) -> sqlite3.Row | None:
    return conn.execute(
        """
        SELECT id, username, email, display_name, auth_provider, created_at,
               last_active_at, visibility, suspended_at, deleted_at
        FROM user
        WHERE id = ?
        """,
        (user_id,),
    ).fetchone()
