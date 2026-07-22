"""Search-index eligibility and sitemap records.

This is the single authority for the consent, visibility, and content-quality
rules used by response metadata and the XML sitemap.
"""

from __future__ import annotations

import sqlite3

MIN_INDEXABLE_ENTRIES = 3
# A page can emit one profile plus one activity per SQL row.  Keeping the
# activity row limit at half the protocol limit guarantees <= 50,000 URLs.
SITEMAP_PAGE_SIZE = 25_000


def is_indexable_profile(conn: sqlite3.Connection, profile_user: dict) -> bool:
    """Return whether this public profile may be indexed by search engines."""
    if profile_user.get("visibility") != "public" or not profile_user.get("search_discovery"):
        return False
    row = conn.execute(
        """SELECT 1
             FROM activity AS a
            WHERE a.owner_id = ? AND a.archived_at IS NULL AND a.secret = 0
              AND length(trim(a.name)) > 0
              AND (SELECT COUNT(*) FROM entry AS e
                    WHERE e.owner_id = a.owner_id AND e.activity_id = a.id
                      AND e.hidden_at IS NULL) >= ?
            LIMIT 1""",
        (profile_user["id"], MIN_INDEXABLE_ENTRIES),
    ).fetchone()
    return row is not None


def is_indexable_activity(
    conn: sqlite3.Connection, *, owner_id: int, activity_id: int, profile_user: dict
) -> bool:
    """Return whether one owner-scoped activity may be indexed."""
    if not is_indexable_profile(conn, profile_user):
        return False
    row = conn.execute(
        """SELECT 1
             FROM activity AS a
            WHERE a.id = ? AND a.owner_id = ? AND a.archived_at IS NULL AND a.secret = 0
              AND length(trim(a.name)) > 0
              AND (SELECT COUNT(*) FROM entry AS e
                    WHERE e.owner_id = a.owner_id AND e.activity_id = a.id
                      AND e.hidden_at IS NULL) >= ?""",
        (activity_id, owner_id, MIN_INDEXABLE_ENTRIES),
    ).fetchone()
    return row is not None


def sitemap_records(conn: sqlite3.Connection, *, limit: int = SITEMAP_PAGE_SIZE) -> list[dict[str, str]]:
    """Return one bounded sitemap page of eligible canonical content.

    The explicit ``limit`` makes a future sitemap-index split mechanical: call
    this function with a page cursor instead of changing eligibility rules.
    """
    rows = conn.execute(
        """WITH eligible_activity AS (
                SELECT a.id, a.owner_id, a.slug, a.name, a.created_at,
                       MAX(COALESCE(e.updated_at, e.created_at, a.created_at)) AS lastmod
                  FROM activity AS a
                  JOIN user AS u ON u.id = a.owner_id
                  JOIN entry AS e ON e.activity_id = a.id AND e.owner_id = a.owner_id
                 WHERE u.deleted_at IS NULL AND u.suspended_at IS NULL
                   AND u.visibility = 'public' AND u.search_discovery = 1
                   AND a.archived_at IS NULL AND a.secret = 0
                   AND length(trim(a.name)) > 0 AND e.hidden_at IS NULL
                 GROUP BY a.id
                HAVING COUNT(e.id) >= ?
            )
            SELECT u.username, u.created_at AS profile_created_at,
                   u.search_discovery_updated_at, ea.slug, ea.lastmod
              FROM user AS u
              JOIN eligible_activity AS ea ON ea.owner_id = u.id
             ORDER BY u.username, ea.slug
             LIMIT ?""",
        (MIN_INDEXABLE_ENTRIES, limit),
    ).fetchall()
    seen_profiles: set[str] = set()
    records: list[dict[str, str]] = []
    for row in rows:
        username = row["username"]
        profile_lastmod = max(
            value for value in (row["profile_created_at"], row["search_discovery_updated_at"], row["lastmod"]) if value
        )
        if username not in seen_profiles:
            records.append({"path": f"/@{username}", "lastmod": profile_lastmod})
            seen_profiles.add(username)
        records.append({"path": f"/@{username}/{row['slug']}", "lastmod": row["lastmod"]})
    return records
