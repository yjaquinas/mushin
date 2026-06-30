"""Search service: people search (all real accounts) and tag search (public-only).

Renderer-agnostic — no HTTP, no templates. Each function opens its own
``db.connect()`` (the dominant service pattern) and returns plain Python data
(lists of dicts) that any renderer can consume.

PRIVACY — SEARCH MUST NOT LEAK
------------------------------
These two surfaces have different, deliberately narrow contracts:

* ``search_people`` returns ONLY ``{id, username, display_name, visibility,
  relationship_state}`` — never any activity / entry / tag / note / memo data.
  All real accounts (public AND private) are findable, including the searcher
  themselves; guests and anyone blocked in either direction are excluded.

* ``search_tags_public`` is structurally incapable of returning private or
  limited accounts: ``user.visibility = 'public'`` is a join predicate, not a
  post-filter, so a non-public owner can never appear in the result set. It
  matches the *tag name only* — the query is never compared against
  ``entry.memo``, ``entry_value`` text, or any free-text column, so a memo or
  entry that happens to equal the search string can never surface.

LIKE WILDCARD ESCAPING
----------------------
Both queries do a prefix match with ``LIKE ? || '%' ESCAPE '\\'``. The user's
query is run through ``_escape_like`` first, so a user typing ``%`` or ``_``
matches those characters literally and can't turn the prefix match into a
match-all.
"""

from __future__ import annotations

from app.models import db
from app.services import connections

# Hard cap on rows returned regardless of the caller's requested limit, so a
# caller can't ask for an unbounded scan.
MAX_LIMIT = 50

# Escape character for LIKE. Backslash is escaped in SQL with ESCAPE '\'.
_LIKE_ESCAPE = "\\"


def _escape_like(text: str) -> str:
    """Escape LIKE wildcards (``%``, ``_``) and the escape char itself.

    Used with ``LIKE ? || '%' ESCAPE '\\'`` so the user's query matches its
    characters literally — a user typing ``%`` can't match every account.
    """
    return (
        text.replace(_LIKE_ESCAPE, _LIKE_ESCAPE + _LIKE_ESCAPE)
        .replace("%", _LIKE_ESCAPE + "%")
        .replace("_", _LIKE_ESCAPE + "_")
    )


def _clamp_limit(limit: int) -> int:
    """Clamp a caller-supplied limit into ``1..MAX_LIMIT``."""
    if limit < 1:
        return 1
    return min(limit, MAX_LIMIT)


def search_people(searcher_id: int, query: str, *, limit: int = 20) -> list[dict]:
    """Search all real accounts by username / display-name prefix.

    Case-insensitive prefix match (``LIKE ? || '%'``) against BOTH ``username``
    and ``display_name``, with LIKE wildcards in *query* escaped. A blank or
    whitespace-only query returns ``[]``.

    Each result is ONLY ``{id, username, display_name, visibility,
    relationship_state}`` — never activity/entry/tag/note data. ``visibility``
    drives the UI's lock/badge; ``relationship_state`` is resolved via
    ``connections.relationship_state(searcher_id, row_id)`` and picks the
    Connect / Requested / Respond / "fellows" affordance.

    Excluded: guests (``auth_provider='guest'`` or NULL username), and any
    account the searcher is blocked-with in EITHER direction (a ``block`` row
    either way). The searcher themselves IS included in results. Results are
    capped at ``limit`` (≤ MAX_LIMIT).
    """
    q = query.strip()
    if not q:
        return []

    pattern = _escape_like(q)
    capped = _clamp_limit(limit)

    with db.connect() as conn:
        conn.execute("BEGIN")
        rows = conn.execute(
            "SELECT id, username, display_name, visibility FROM user"
            " WHERE auth_provider != 'guest'"
            " AND username IS NOT NULL"
            " AND ("
            "   username LIKE ? || '%' ESCAPE ?"
            "   OR display_name LIKE ? || '%' ESCAPE ?"
            " )"
            # No block in either direction between the searcher and this row.
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
            "display_name": r["display_name"],
            "visibility": r["visibility"],
            "relationship_state": connections.relationship_state(searcher_id, r["id"]),
        }
        for r in rows
    ]


def search_tags_public(searcher_id: int, query: str, *, limit: int = 20) -> list[dict]:
    """Search PUBLIC accounts' activities by tag-name prefix.

    Join path (structural, no entry data):

        tag → field_def (tag.field_def_id = field_def.id)
            → activity  (field_def.activity_id = activity.id)
            → user      (activity.owner_id = user.id)

    A ``tag`` belongs to a ``field_def`` which belongs to an ``activity``, so a
    tag maps to its activity without touching any ``entry`` / ``entry_value`` /
    memo row. ``user.visibility = 'public'`` is a JOIN predicate — private and
    limited accounts are structurally absent, not filtered after the fact. Only
    active (non-archived) tags and activities are considered.

    Matching is a prefix ``LIKE`` against the tag NAME only — never against
    ``entry.memo``, ``entry_value`` text, or any free-text column — so a memo or
    entry equal to the query string can never surface here.

    Each result is ``{username, activity_slug, activity_name, tag}``, de-duped.
    A blank query returns ``[]``. Owners the searcher is blocked-with (either
    direction) are excluded. Results are capped at ``limit`` (≤ MAX_LIMIT).
    """
    q = query.strip()
    if not q:
        return []

    pattern = _escape_like(q)
    capped = _clamp_limit(limit)

    with db.connect() as conn:
        conn.execute("BEGIN")
        rows = conn.execute(
            "SELECT DISTINCT u.username AS username,"
            "       a.slug AS activity_slug,"
            "       a.name AS activity_name,"
            "       t.name AS tag"
            " FROM tag t"
            " JOIN field_def f ON f.id = t.field_def_id"
            " JOIN activity a ON a.id = f.activity_id"
            " JOIN user u ON u.id = a.owner_id"
            " WHERE u.visibility = 'public'"
            "   AND u.auth_provider != 'guest'"
            "   AND u.username IS NOT NULL"
            "   AND t.archived_at IS NULL"
            "   AND a.archived_at IS NULL"
            "   AND t.name LIKE ? || '%' ESCAPE ?"
            # Exclude owners the searcher is blocked-with in either direction.
            "   AND NOT EXISTS ("
            "       SELECT 1 FROM block b"
            "       WHERE (b.blocker_id = ? AND b.blocked_id = u.id)"
            "          OR (b.blocker_id = u.id AND b.blocked_id = ?)"
            "   )"
            " ORDER BY u.username, a.slug, t.name"
            " LIMIT ?",
            (pattern, _LIKE_ESCAPE, searcher_id, searcher_id, capped),
        ).fetchall()

    return [
        {
            "username": r["username"],
            "activity_slug": r["activity_slug"],
            "activity_name": r["activity_name"],
            "tag": r["tag"],
        }
        for r in rows
    ]
