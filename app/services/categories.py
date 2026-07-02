"""User-created category creation — the "general log" write path.

Renderer-agnostic: no HTTP, no templates. Returns plain Python data structures
both renderers (HTMX web, HXML native) consume.

A user-created category is, by default, a single ``activity`` in
``count_mode="running"`` with exactly two ``field_def`` rows — ``memo`` and
``tag_group``. This is the "general log" shape described in the ``data-model``
skill. There are no seed templates and no level/ladder concept: every activity's
hero stat is always its running count.

Every write is scoped by ``owner_id`` (required, positional) — multi-user
isolation is the project's non-negotiable invariant.
"""

from __future__ import annotations

import sqlite3

import structlog

from app.models import db
from app.services import _db
from app.services.entries import ActivityNotFoundError
from app.services.slugs import unique_slug

log = structlog.get_logger()

#: Maximum length (characters) of an activity name accepted by
#: :func:`rename_activity`. Mirrors the cap used elsewhere for short names.
RENAME_ACTIVITY_MAX_NAME = 200

# ---------------------------------------------------------------------------
# Importable constants — used by routes (the icon picker / example cards) and
# by tests. Lucide icon names (https://lucide.dev).
# ---------------------------------------------------------------------------

#: Default fallback icon when a category has no icon (or an unknown one).
DEFAULT_ICON = "circle-dot"

#: Fixed set of icons offered in the create-category icon picker. ``circle-dot``
#: is the default fallback and is included so it can be re-selected explicitly.
ICON_CHOICES: tuple[str, ...] = (
    "dumbbell",
    "book-open",
    "circle-check",
    "pencil",
    "music",
    "heart",
    "footprints",
    "code",
    "sprout",
    "camera",
    "circle-dot",
)

#: The three one-tap onboarding example categories shown in the empty state.
EXAMPLE_CATEGORIES: list[dict[str, str]] = [
    {"name": "Workout", "icon": "dumbbell"},
    {"name": "Reading", "icon": "book-open"},
    {"name": "Habits", "icon": "circle-check"},
]


# ---------------------------------------------------------------------------
# General-log field recipe — the two field_def rows on the running activity.
# Labels/sort_order follow the conventions in seed_data.py.
# ---------------------------------------------------------------------------

_GENERAL_LOG_FIELD_DEFS: tuple[tuple[str, str], ...] = (
    # (kind, label) — sort_order is the enumeration index below.
    ("memo", "Memo"),
    ("tag_group", "Tags"),
)


def _normalize_icon(icon: str | None) -> str:
    """Return a valid icon name, falling back to ``DEFAULT_ICON``.

    Never raises on a bad value — an unknown or ``None`` icon becomes the
    default so a malformed picker submission can't break category creation.
    """
    if icon in ICON_CHOICES:
        return icon  # type: ignore[return-value]  # membership narrows to str
    return DEFAULT_ICON


def create_activity(owner_id: int, *, name: str, icon: str | None = None) -> dict:
    """Create a general-log activity for *owner_id*.

    In one transaction, inserts:
      * one ``category`` row (``owner_id``, ``name``, normalized ``icon``),
      * one ``activity`` row (``count_mode="running"``, a per-owner-unique
        ``slug`` derived from *name*, cache fields at their DB defaults of
        ``0`` / ``NULL``),
      * two ``field_def`` rows on that activity: ``memo`` and ``tag_group``.

    Returns ``{"category_id": int, "activity_id": int}``.

    An unknown/invalid *icon* silently falls back to ``circle-dot`` rather than
    erroring (see :func:`_normalize_icon`).
    """
    safe_icon = _normalize_icon(icon)

    with db.connect() as conn:
        conn.execute("BEGIN")

        cur = conn.execute(
            "INSERT INTO category (owner_id, name, icon, sort_order) VALUES (?, ?, ?, ?)",
            (owner_id, name, safe_icon, 0),
        )
        category_id = cur.lastrowid

        # Choose the slug inside the same transaction as the INSERT so the
        # per-owner uniqueness check sees a consistent view of existing rows.
        slug = unique_slug(conn, owner_id, name)

        cur = conn.execute(
            "INSERT INTO activity"
            " (owner_id, category_id, name, slug, count_mode, sort_order)"
            " VALUES (?, ?, ?, ?, ?, ?)",
            (owner_id, category_id, name, slug, "running", 0),
        )
        activity_id = cur.lastrowid

        for sort_order, (kind, label) in enumerate(_GENERAL_LOG_FIELD_DEFS):
            conn.execute(
                "INSERT INTO field_def (activity_id, kind, label, sort_order) VALUES (?, ?, ?, ?)",
                (activity_id, kind, label, sort_order),
            )

    log.info(
        "categories.create",
        owner_id=owner_id,
        category_id=category_id,
        activity_id=activity_id,
        icon=safe_icon,
    )
    return {"category_id": category_id, "activity_id": activity_id}


def rename_activity(
    conn: sqlite3.Connection,
    *,
    owner_id: int,
    activity_id: int,
    new_name: str,
) -> str:
    """Rename an activity and re-derive its slug, returning the new slug.

    Operates on an *already-open* connection — the caller owns the transaction
    boundary (same convention as the ``_db`` helpers and the cache writes in
    ``entries.py``), so the slug uniqueness check and the UPDATE see a single
    consistent view and commit atomically with whatever else the caller does.

    *new_name* is trimmed of surrounding whitespace, then validated: it must be
    non-empty and at most :data:`RENAME_ACTIVITY_MAX_NAME` characters, else a
    :class:`ValueError`. The new slug is :func:`unique_slug` of the new name —
    so a name whose slug collides with one of *owner_id*'s other active
    activities gets a ``-2`` (``-3``, ...) suffix.

    The write is scoped by ``owner_id``: a *activity_id* not owned by
    *owner_id* (or that does not exist) updates zero rows and raises
    :class:`~app.services.entries.ActivityNotFoundError`.
    """
    name = new_name.strip()
    if not name:
        raise ValueError("activity name must not be empty")
    if len(name) > RENAME_ACTIVITY_MAX_NAME:
        raise ValueError(f"activity name must be at most {RENAME_ACTIVITY_MAX_NAME} characters")

    slug = unique_slug(conn, owner_id, name)

    rows = _db.update(
        conn,
        "activity",
        owner_id,
        assignments="name = ?, slug = ?",
        assignment_params=(name, slug),
        where="id = ?",
        params=(activity_id,),
    )
    if rows == 0:
        raise ActivityNotFoundError(f"activity {activity_id} not found for owner {owner_id}")

    log.info(
        "categories.rename_activity",
        owner_id=owner_id,
        activity_id=activity_id,
        slug=slug,
    )
    return slug


def delete_category(
    conn: sqlite3.Connection,
    *,
    owner_id: int,
    category_id: int,
) -> bool:
    """Delete a category and its entire subtree, scoped to *owner_id*.

    Operates on an *already-open* connection — the caller owns the transaction
    boundary (same convention as :func:`rename_activity` and the ``_db``
    helpers).

    The delete is owner-scoped: a *category_id* not owned by *owner_id* (or that
    does not exist) deletes zero rows. ``ON DELETE CASCADE`` from
    ``category → activity → {entry, entry_tag, entry_value, match}``
    (wired in migration 0001, with ``foreign_keys=ON`` enforced by
    the db connection) removes the whole subtree, so no extra deletes are needed.
    No cache refresh is needed — the cached fields live on ``activity`` rows
    that are themselves gone.

    Returns ``True`` if the category row was deleted, ``False`` if no matching
    owned row existed.
    """
    rows = _db.delete(
        conn,
        "category",
        owner_id,
        where="id = ?",
        params=(category_id,),
    )
    deleted = rows == 1

    log.info(
        "categories.delete",
        owner_id=owner_id,
        category_id=category_id,
        deleted=deleted,
    )
    return deleted
