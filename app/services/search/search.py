"""Search service: people, tag, and activity discovery.

Renderer-agnostic — no HTTP, no templates. Each function opens its own
``db.connect()`` and returns plain Python data (lists of dicts).

PRIVACY — SEARCH MUST NOT LEAK
------------------------------
``search_people`` returns ONLY ``{id, username, visibility,
relationship_state}`` — never any activity / entry / tag / note / memo data.
All live real accounts (public AND private) are findable, including the
searcher themselves; deleted accounts and anyone blocked in either direction
are excluded.

Activity search returns only public-profile-safe activity metadata. Tag search
returns aggregate tag names/counts from public users, the searcher, and accepted
fellows.

LIKE WILDCARD ESCAPING
----------------------
Both queries do a prefix match with ``LIKE ? || '%' ESCAPE '\\'``. The user's
query is run through shared LIKE escaping first.
"""

from __future__ import annotations

from app.models import db
from app.services.social import connections
from app.services.search.common import LIKE_ESCAPE, clamp_limit, escape_like
from app.services.search.discovery import search_activities, search_tags


def search_people(searcher_id: int, query: str, *, limit: int = 20) -> list[dict]:
    """Search all real accounts by username prefix.

    Case-insensitive prefix match (``LIKE ? || '%'``) against ``username``.
    A blank or whitespace-only query returns ``[]``.

    Each result is ONLY ``{id, username, visibility, relationship_state}``.

    Excluded: deleted accounts (``deleted_at IS NOT NULL``), and any account
    the searcher is blocked-with in EITHER direction.
    """
    q = query.strip()
    if not q:
        return []

    pattern = escape_like(q)
    capped = clamp_limit(limit)

    with db.connect() as conn:
        conn.execute("BEGIN")
        rows = conn.execute(
            "SELECT id, username, visibility FROM user"
            " WHERE deleted_at IS NULL"
            " AND username IS NOT NULL"
            " AND username LIKE ? || '%' ESCAPE ?"
            " AND NOT EXISTS ("
            "   SELECT 1 FROM block b"
            "   WHERE (b.blocker_id = ? AND b.blocked_id = user.id)"
            "      OR (b.blocker_id = user.id AND b.blocked_id = ?)"
            " )"
            " ORDER BY username"
            " LIMIT ?",
            (
                pattern,
                LIKE_ESCAPE,
                searcher_id,
                searcher_id,
                capped,
            ),
        ).fetchall()

    return [
        {
            "id": r["id"],
            "username": r["username"],
            "visibility": r["visibility"],
            "relationship_state": connections.relationship_state(searcher_id, r["id"]),
        }
        for r in rows
    ]


def grouped_results(searcher_id: int, query: str, *, limit: int = 20) -> dict:
    """Interpret the search prefix and return the matching result group."""
    raw = query.strip()
    result = {"kind": "", "query": raw, "people": [], "tags": [], "activities": []}
    if not raw:
        return result
    if raw.startswith("@"):
        result["kind"] = "people"
        result["people"] = search_people(searcher_id, raw[1:].strip(), limit=limit)
        return result
    if raw.startswith("#"):
        result["kind"] = "tags"
        result["tags"] = search_tags(searcher_id, raw[1:].strip(), limit=limit)
        return result
    result["kind"] = "activities"
    result["activities"] = search_activities(searcher_id, raw, limit=limit)
    return result
