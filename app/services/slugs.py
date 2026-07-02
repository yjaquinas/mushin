"""Slug generation for activity public URLs (``/u/{username}/{slug}``).

Renderer-agnostic: no HTTP, no templates. ``slugify`` is a pure function;
``unique_slug`` adds a per-owner uniqueness check against the DB.

The rules here mirror the migration 0006 slug backfill exactly
so a slug minted at create-time is indistinguishable from a back-filled one:

* lowercase,
* fold a fixed core set of accented Latin characters to plain ASCII,
* map every other non ``[a-z0-9]`` character to ``-``,
* collapse repeated ``-`` to a single ``-``,
* trim leading/trailing ``-``,
* fall back to a non-empty placeholder when nothing alphanumeric survives.

The migration's placeholder is a legacy row-id-based fallback value. A *new*
row has no id yet, so :func:`slugify` falls back to ``"activity"`` and
:func:`unique_slug` lets the numeric-suffix collision logic disambiguate.

Per-owner uniqueness is enforced at the DB level by the activity table's
partial unique index on (``owner_id, slug`` WHERE ``archived_at IS NULL``);
:func:`unique_slug` checks the same predicate so the suffix it returns will not
trip that index.
"""

from __future__ import annotations

import sqlite3

#: Accented-Latin -> ASCII folding, character-for-character identical to the
#: REPLACE() chain in the 0006 slug migration. Anything not in this map (Hangul,
#: CJK, other diacritics) is left for the [a-z0-9] filter to turn into '-'.
_ACCENT_FOLD = str.maketrans(
    {
        "á": "a",
        "à": "a",
        "â": "a",
        "ä": "a",
        "ã": "a",
        "å": "a",
        "é": "e",
        "è": "e",
        "ê": "e",
        "ë": "e",
        "í": "i",
        "ì": "i",
        "î": "i",
        "ï": "i",
        "ó": "o",
        "ò": "o",
        "ô": "o",
        "ö": "o",
        "õ": "o",
        "ú": "u",
        "ù": "u",
        "û": "u",
        "ü": "u",
        "ñ": "n",
        "ç": "c",
        "ý": "y",
    }
)

#: Fallback when a name slugifies to nothing (the migration used
#: the legacy row-id-based fallback form; a not-yet-inserted row has no id, so
#: use this and let
#: :func:`unique_slug` append a numeric suffix if it collides).
FALLBACK_SLUG = "activity"


def slugify(name: str) -> str:
    """Slugify *name* using the same rules as the 0006 migration backfill.

    Pure function — no DB access, no uniqueness guarantee. Returns
    :data:`FALLBACK_SLUG` when nothing alphanumeric survives.
    """
    # Fold accents first, then lowercase — matches the migration's
    # LOWER(REPLACE(... )) ordering (REPLACE targets are already lowercase, so
    # case here only affects the subsequent [a-z0-9] test).
    folded = name.translate(_ACCENT_FOLD).lower()

    out: list[str] = []
    for ch in folded:
        if ch.isascii() and (ch.isdigit() or ("a" <= ch <= "z")):
            out.append(ch)
        else:
            out.append("-")

    # Collapse runs of '-' and trim leading/trailing '-'.
    slug = "".join(out)
    slug = "-".join(part for part in slug.split("-") if part)

    return slug or FALLBACK_SLUG


def unique_slug(conn: sqlite3.Connection, owner_id: int, name: str) -> str:
    """Return a slug for *name* unique among *owner_id*'s active activities.

    Slugifies *name*, then checks ``activity(owner_id, slug)`` among
    non-archived rows. On collision it appends ``-2``, ``-3``, ... to the base
    slug until free — the same suffix scheme the migration's de-dup pass used.

    Operates on an already-open connection (the caller owns the transaction
    boundary) so the slug can be chosen inside the same transaction as the
    activity INSERT. ``owner_id`` is required — the lookup is always scoped.
    """
    base = slugify(name)
    candidate = base
    suffix = 2
    while _slug_taken(conn, owner_id, candidate):
        candidate = f"{base}-{suffix}"
        suffix += 1
    return candidate


def _slug_taken(conn: sqlite3.Connection, owner_id: int, slug: str) -> bool:
    """Whether *slug* is already used by an active activity of *owner_id*."""
    row = conn.execute(
        "SELECT 1 FROM activity WHERE owner_id = ? AND slug = ? AND archived_at IS NULL LIMIT 1",
        (owner_id, slug),
    ).fetchone()
    return row is not None
