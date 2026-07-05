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
