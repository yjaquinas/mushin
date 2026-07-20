"""Activity and tag search implementations."""

from __future__ import annotations

from app.models import db
from app.services.entries import entries
from app.services.search.common import LIKE_ESCAPE, clamp_limit, escape_like
from app.services.social import profiles


def search_activities(searcher_id: int, query: str, *, limit: int = 20) -> list[dict]:
    """Search visible activity names across live, non-blocked accounts."""
    q = query.strip()
    if not q:
        return []

    pattern = escape_like(q)
    capped = clamp_limit(limit)

    with db.connect() as conn:
        conn.execute("BEGIN")
        rows = conn.execute(
            "SELECT a.id, a.owner_id, a.name, a.count, a.slug,"
            " u.username, u.visibility"
            " FROM activity a"
            " JOIN user u ON u.id = a.owner_id"
            " WHERE a.archived_at IS NULL"
            " AND u.deleted_at IS NULL"
            " AND u.username IS NOT NULL"
            " AND a.name LIKE ? || '%' ESCAPE ?"
            " AND NOT EXISTS ("
            "   SELECT 1 FROM block b"
            "   WHERE (b.blocker_id = ? AND b.blocked_id = u.id)"
            "      OR (b.blocker_id = u.id AND b.blocked_id = ?)"
            " )"
            " AND (a.secret = 0 OR a.owner_id = ?)"
            " ORDER BY lower(a.name), lower(u.username)"
            " LIMIT ?",
            (pattern, LIKE_ESCAPE, searcher_id, searcher_id, searcher_id, capped),
        ).fetchall()

        results = []
        for row in rows:
            profile_user = {"id": row["owner_id"], "visibility": row["visibility"]}
            capability = profiles.viewer_capability(
                conn,
                current_user_id=searcher_id,
                profile_user=profile_user,
            )
            can_open_detail = capability in {"owner", "connected", "public"} and bool(row["slug"])
            profile_url = profiles.canonical_profile_url(row["username"])
            activity_url = profiles.canonical_activity_url(row["username"], row["slug"] or "")
            results.append(
                {
                    "id": row["id"],
                    "owner_id": row["owner_id"],
                    "username": row["username"],
                    "name": row["name"],
                    "count": row["count"],
                    "url": activity_url if can_open_detail else profile_url,
                    "detail_visible": can_open_detail,
                }
            )

    return results


def recent_public_entries(*, limit: int = 10) -> list[dict]:
    """Return recent public entries, newest added first."""
    capped = clamp_limit(limit)
    with db.connect() as conn:
        conn.execute("BEGIN")
        rows = conn.execute(
            """SELECT a.id, a.name, a.slug,
                      u.username,
                      e.id AS entry_id, e.memo, e.occurred_at, e.time_known, e.created_at
                 FROM entry e
                 JOIN activity a ON a.id = e.activity_id
                 JOIN user u ON u.id = e.owner_id
                WHERE e.hidden_at IS NULL
                  AND a.archived_at IS NULL
                  AND a.secret = 0
                  AND u.deleted_at IS NULL
                  AND u.visibility = 'public'
                ORDER BY e.created_at DESC, e.id DESC
                LIMIT ?""",
            (capped,),
        ).fetchall()

    return _feed_entries(rows)


def recent_fellow_entries(viewer_id: int, *, limit: int = 10) -> list[dict]:
    """Return recent non-secret entries from accepted, consented fellows."""
    capped = clamp_limit(limit)
    with db.connect() as conn:
        conn.execute("BEGIN")
        rows = conn.execute(
            """SELECT a.id, a.name, a.slug,
                      u.username,
                      e.id AS entry_id, e.memo, e.occurred_at, e.time_known, e.created_at
                 FROM connection c
                 JOIN user u ON u.id = CASE WHEN c.user_lo = ? THEN c.user_hi ELSE c.user_lo END
                 JOIN entry e ON e.owner_id = u.id
                 JOIN activity a ON a.id = e.activity_id
                WHERE (c.user_lo = ? OR c.user_hi = ?)
                  AND c.status = 'accepted'
                  AND c.sharing_consent_at IS NOT NULL
                  AND e.hidden_at IS NULL
                  AND a.archived_at IS NULL
                  AND a.secret = 0
                  AND u.deleted_at IS NULL
                ORDER BY e.created_at DESC, e.id DESC
                LIMIT ?""",
            (viewer_id, viewer_id, viewer_id, capped),
        ).fetchall()

    return _feed_entries(rows)


def _feed_entries(rows) -> list[dict]:
    """Decorate feed rows with canonical public URLs."""
    return [
        {
            "id": row["id"],
            "name": row["name"],
            "slug": row["slug"],
            "username": row["username"],
            "memo": row["memo"],
            "entry_id": row["entry_id"],
            "occurred_at": row["occurred_at"],
            "time_known": bool(row["time_known"]),
            "created_at": row["created_at"],
            "profile_url": profiles.canonical_profile_url(row["username"]),
            "activity_url": profiles.canonical_activity_url(row["username"], row["slug"] or ""),
        }
        for row in rows
    ]


def search_tags(searcher_id: int, query: str, *, limit: int = 20) -> list[dict]:
    """Search entries matching a hashtag prefix from public, own, and fellow-visible entries."""
    q = query.strip().lower()
    if not q:
        return []

    pattern = f"%#{escape_like(q)}%"
    capped = clamp_limit(limit)

    with db.connect() as conn:
        conn.execute("BEGIN")
        rows = conn.execute(
            """SELECT e.id, e.memo, e.activity_id, e.occurred_at, e.time_known, e.created_at,
                      a.name AS activity_name, a.slug AS activity_slug,
                      u.username, u.visibility, u.id AS owner_id
               FROM entry e
               JOIN activity a ON a.id = e.activity_id
               JOIN user u ON u.id = e.owner_id
                WHERE e.hidden_at IS NULL
                AND e.memo IS NOT NULL
                AND e.memo LIKE ? ESCAPE ?
                AND u.deleted_at IS NULL
                AND (a.secret = 0 OR e.owner_id = ?)
                AND NOT EXISTS (
                  SELECT 1 FROM block b
                  WHERE (b.blocker_id = ? AND b.blocked_id = u.id)
                     OR (b.blocker_id = u.id AND b.blocked_id = ?)
                )
                AND (
                 u.id = ?
                 OR u.visibility = 'public'
                 OR EXISTS (
                   SELECT 1 FROM connection c
                   WHERE c.user_lo = min(?, u.id)
                   AND c.user_hi = max(?, u.id)
                   AND c.status = 'accepted'
                   AND c.sharing_consent_at IS NOT NULL
                 )
               )
               ORDER BY e.created_at DESC
               LIMIT ?""",
            (
                pattern,
                LIKE_ESCAPE,
                searcher_id,
                searcher_id,
                searcher_id,
                searcher_id,
                searcher_id,
                searcher_id,
                capped * 2,
            ),
        ).fetchall()

        results = []
        for row in rows:
            tags = set(entries.parse_hashtags(row["memo"] or ""))
            if not any(t.startswith(q) for t in tags):
                continue

            profile_user = {"id": row["owner_id"], "visibility": row["visibility"]}
            capability = profiles.viewer_capability(
                conn,
                current_user_id=searcher_id,
                profile_user=profile_user,
            )
            can_open_detail = capability in {"owner", "connected", "public"} and bool(
                row["activity_slug"]
            )
            profile_url = profiles.canonical_profile_url(row["username"])
            activity_url = profiles.canonical_activity_url(
                row["username"], row["activity_slug"] or ""
            )

            results.append(
                {
                    "entry_id": row["id"],
                    "username": row["username"],
                    "activity_name": row["activity_name"],
                    "memo": row["memo"],
                    "occurred_at": row["occurred_at"],
                    "time_known": bool(row["time_known"]),
                    "created_at": row["created_at"],
                    "activity_url": activity_url if can_open_detail else profile_url,
                    "detail_visible": can_open_detail,
                }
            )

            if len(results) >= capped:
                break

    return results
