"""Search service: people search (all real accounts).

Renderer-agnostic — no HTTP, no templates. Each function opens its own
``db.connect()`` and returns plain Python data (lists of dicts).

PRIVACY — SEARCH MUST NOT LEAK
------------------------------
``search_people`` returns ONLY ``{id, username, visibility,
relationship_state}`` — never any activity / entry / tag / note / memo data.
All live real accounts (public AND private) are findable, including the
searcher themselves; deleted accounts and anyone blocked in either direction
are excluded.

LIKE WILDCARD ESCAPING
----------------------
Both queries do a prefix match with ``LIKE ? || '%' ESCAPE '\\'``. The user's
query is run through ``_escape_like`` first.
"""

from __future__ import annotations

from app.models import db
from app.services import connections

MAX_LIMIT = 50
_LIKE_ESCAPE = "\\"


def _escape_like(text: str) -> str:
    """Escape LIKE wildcards and the escape char itself."""
    return (
        text.replace(_LIKE_ESCAPE, _LIKE_ESCAPE + _LIKE_ESCAPE)
        .replace("%", _LIKE_ESCAPE + "%")
        .replace("_", _LIKE_ESCAPE + "_")
    )


def _clamp_limit(limit: int) -> int:
    if limit < 1:
        return 1
    return min(limit, MAX_LIMIT)


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

    pattern = _escape_like(q)
    capped = _clamp_limit(limit)

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
                _LIKE_ESCAPE,
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


def search_tags_public(searcher_id: int, query: str, *, limit: int = 20) -> list[dict]:
    """Search PUBLIC accounts' entries by tag name prefix.

    With the new flat schema, tags are stored as comma-separated ids on the
    entry row. This function is kept as a stub — tag-based public search
    requires a tag lookup table that no longer exists.
    """
    q = query.strip()
    if not q:
        return []

    return []
