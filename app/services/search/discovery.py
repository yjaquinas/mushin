"""Activity and tag search implementations."""

from __future__ import annotations

from app.models import db
from app.services.entries import entries
from app.services.social import profiles
from app.services.search.common import LIKE_ESCAPE, clamp_limit, escape_like


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
            " ORDER BY lower(a.name), lower(u.username)"
            " LIMIT ?",
            (pattern, LIKE_ESCAPE, searcher_id, searcher_id, capped),
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
    """Return public activities with latest entry, one per activity, newest first."""
    capped = clamp_limit(limit)
    with db.connect() as conn:
        conn.execute("BEGIN")
        rows = conn.execute(
            """SELECT a.id, a.name, a.slug,
                      u.username,
                      latest.id AS entry_id, latest.memo, latest.occurred_at, latest.time_known, latest.updated_at,
                      (SELECT COUNT(*) FROM entry e2
                        WHERE e2.activity_id = a.id
                          AND e2.owner_id = a.owner_id
                          AND e2.hidden_at IS NULL) AS entry_count
                 FROM activity a
                 JOIN user u ON u.id = a.owner_id
                 LEFT JOIN entry latest ON latest.id = (
                   SELECT e3.id FROM entry e3
                   WHERE e3.activity_id = a.id
                     AND e3.owner_id = a.owner_id
                     AND e3.hidden_at IS NULL
                   ORDER BY e3.updated_at DESC
                   LIMIT 1
                 )
                WHERE a.archived_at IS NULL
                  AND u.deleted_at IS NULL
                  AND u.visibility = 'public'
                  AND latest.id IS NOT NULL
                ORDER BY latest.updated_at DESC
                LIMIT ?""",
            (capped,),
        ).fetchall()

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
            "updated_at": row["updated_at"],
            "profile_url": profiles.canonical_profile_url(row["username"]),
            "activity_url": profiles.canonical_activity_url(row["username"], row["slug"] or ""),
        }
        for row in rows
    ]


def search_tags(searcher_id: int, query: str, *, limit: int = 20) -> list[dict]:
    """Search hashtag names from public, own, and fellow-visible entries."""
    q = query.strip().lower()
    if not q:
        return []

    pattern = f"%#{escape_like(q)}%"
    capped = clamp_limit(limit)

    with db.connect() as conn:
        conn.execute("BEGIN")
        rows = conn.execute(
            "SELECT e.id, e.memo"
            " FROM entry e"
            " JOIN user u ON u.id = e.owner_id"
            " WHERE e.hidden_at IS NULL"
            " AND e.memo IS NOT NULL"
            " AND e.memo LIKE ? ESCAPE ?"
            " AND u.deleted_at IS NULL"
            " AND NOT EXISTS ("
            "   SELECT 1 FROM block b"
            "   WHERE (b.blocker_id = ? AND b.blocked_id = u.id)"
            "      OR (b.blocker_id = u.id AND b.blocked_id = ?)"
            " )"
            " AND ("
            "   u.id = ?"
            "   OR u.visibility = 'public'"
            "   OR EXISTS ("
            "     SELECT 1 FROM connection c"
            "     WHERE c.user_lo = min(?, u.id)"
            "     AND c.user_hi = max(?, u.id)"
            "     AND c.status = 'accepted'"
            "     AND c.sharing_consent_at IS NOT NULL"
            "   )"
            " )"
            " ORDER BY e.id DESC"
            " LIMIT 500",
            (
                pattern,
                LIKE_ESCAPE,
                searcher_id,
                searcher_id,
                searcher_id,
                searcher_id,
                searcher_id,
            ),
        ).fetchall()

    counts: dict[str, int] = {}
    for row in rows:
        for tag in set(entries.parse_hashtags(row["memo"] or "")):
            if tag.startswith(q):
                counts[tag] = counts.get(tag, 0) + 1

    return [
        {"name": name, "total": total}
        for name, total in sorted(counts.items(), key=lambda item: (-item[1], item[0]))[:capped]
    ]
