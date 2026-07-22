"""Consent-safe retrieval for editorial public topic hubs."""

from __future__ import annotations

import sqlite3

from app.content.topic_hubs import TOPIC_HUBS, TopicHub
from app.services.search.indexing import MIN_INDEXABLE_ENTRIES
from app.services.social import profiles

MIN_TOPIC_ACTIVITIES = 5
TOPIC_PAGE_SIZE = 12


def topic_page(
    conn: sqlite3.Connection, topic: TopicHub, *, page: int = 1
) -> dict[str, object] | None:
    """Return one published topic page, or ``None`` if it is not useful yet."""
    if not topic.approved or page < 1:
        return None
    names = tuple(name.casefold() for name in topic.activity_names)
    placeholders = ", ".join("?" for _ in names)
    base_sql = f"""
        FROM activity AS a
        JOIN user AS u ON u.id = a.owner_id
        JOIN entry AS e ON e.activity_id = a.id AND e.owner_id = a.owner_id
        WHERE u.deleted_at IS NULL AND u.suspended_at IS NULL
          AND u.visibility = 'public' AND u.search_discovery = 1
          AND a.archived_at IS NULL AND a.secret = 0 AND a.slug IS NOT NULL
          AND length(trim(a.name)) > 0
          AND lower(trim(a.name)) IN ({placeholders})
          AND e.hidden_at IS NULL
        GROUP BY a.id, a.owner_id
        HAVING COUNT(e.id) >= ?
    """
    parameters = (*names, MIN_INDEXABLE_ENTRIES)
    total = conn.execute(
        f"SELECT COUNT(*) FROM (SELECT a.id {base_sql})", parameters
    ).fetchone()[0]
    if total < MIN_TOPIC_ACTIVITIES:
        return None
    offset = (page - 1) * TOPIC_PAGE_SIZE
    rows = conn.execute(
        "SELECT a.name, a.slug, a.owner_id, u.username, COUNT(e.id) AS entry_count "
        + base_sql
        + " ORDER BY lower(a.name), lower(u.username), a.id LIMIT ? OFFSET ?",
        (*parameters, TOPIC_PAGE_SIZE, offset),
    ).fetchall()
    if not rows:
        return None
    activities = [
        {
            "name": row["name"],
            "username": row["username"],
            "entry_count": row["entry_count"],
            "url": profiles.canonical_activity_url(row["username"], row["slug"]),
        }
        for row in rows
    ]
    return {
        "activities": activities,
        "page": page,
        "has_next": offset + len(activities) < total,
        "has_previous": page > 1,
    }


def published_topic_paths(conn: sqlite3.Connection) -> tuple[str, ...]:
    """Return only approved hubs that currently meet the publication floor."""
    return tuple(
        f"/topics/{topic.slug}"
        for topic in TOPIC_HUBS
        if topic_page(conn, topic) is not None
    )
