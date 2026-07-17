"""Activity management for Mushin.

Renderer-agnostic: no HTTP, no templates. Returns plain Python data structures
both renderers (HTMX web, HXML native) consume.

Every write is scoped by ``owner_id`` (required, positional) — multi-user
isolation is the project's non-negotiable invariant.
"""

from __future__ import annotations

import sqlite3

import structlog

from app.models import db
from app.services.activities.slugs import unique_slug
from app.services.common import db as _db
from app.services.entries.entries import ActivityNotFoundError
from app.services.plans import check_activity_limit, check_secret_activity_allowed

log = structlog.get_logger()

#: Maximum length (characters) of an activity name.
ACTIVITY_MAX_NAME = 20

#: Default fallback icon when an activity has no icon (or an unknown one).
DEFAULT_ICON = "circle-dot"

#: Fixed set of icons offered in the create-activity icon picker.
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

#: The three one-tap onboarding example activities shown in the empty state.
EXAMPLE_ACTIVITIES: list[dict[str, str]] = [
    {"name": "Workout", "icon": "dumbbell"},
    {"name": "Reading", "icon": "book-open"},
    {"name": "Habits", "icon": "circle-check"},
]


def _normalize_icon(icon: str | None) -> str:
    """Return a valid icon name, falling back to ``DEFAULT_ICON``."""
    if icon in ICON_CHOICES:
        return icon  # type: ignore[return-value]
    return DEFAULT_ICON


def create_activity(
    owner_id: int, *, name: str, icon: str | None = None, secret: bool = False
) -> dict:
    """Create an activity for *owner_id*.

    In one transaction, inserts one ``activity`` row (a per-owner-unique
    ``slug`` derived from *name*, cache fields at their DB defaults).

    Returns ``{"activity_id": int}``.
    """
    if len(name) > ACTIVITY_MAX_NAME:
        raise ValueError(f"activity name must be at most {ACTIVITY_MAX_NAME} characters")
    safe_icon = _normalize_icon(icon)

    with db.connect() as conn:
        conn.execute("BEGIN")

        check_activity_limit(conn, owner_id)
        if secret:
            check_secret_activity_allowed(conn, owner_id)

        slug = unique_slug(conn, owner_id, name)

        cur = conn.execute(
            "INSERT INTO activity"
            " (owner_id, name, slug, sort_order, icon, secret)"
            " VALUES (?, ?, ?, ?, ?, ?)",
            (owner_id, name, slug, 0, safe_icon, int(secret)),
        )
        activity_id = cur.lastrowid

    log.info(
        "activities.create",
        owner_id=owner_id,
        activity_id=activity_id,
        icon=safe_icon,
    )
    return {"activity_id": activity_id}


def rename_activity(
    conn: sqlite3.Connection,
    *,
    owner_id: int,
    activity_id: int,
    new_name: str,
) -> str:
    """Rename an activity and re-derive its slug, returning the new slug."""
    name = new_name.strip()
    if not name:
        raise ValueError("activity name must not be empty")
    if len(name) < 2:
        raise ValueError("activity name must be at least 2 characters")
    if len(name) > ACTIVITY_MAX_NAME:
        raise ValueError(f"activity name must be at most {ACTIVITY_MAX_NAME} characters")

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
        "activities.rename",
        owner_id=owner_id,
        activity_id=activity_id,
        slug=slug,
    )
    return slug


def update_activity(
    conn: sqlite3.Connection,
    *,
    owner_id: int,
    activity_id: int,
    name: str | None = None,
    secret: bool | None = None,
) -> str | None:
    """Update an activity's name and/or secret flag. Returns the new slug if name changed."""
    if name is not None:
        name = name.strip()
        if not name:
            raise ValueError("activity name must not be empty")
        if len(name) < 2:
            raise ValueError("activity name must be at least 2 characters")
        if len(name) > ACTIVITY_MAX_NAME:
            raise ValueError(f"activity name must be at most {ACTIVITY_MAX_NAME} characters")

    assignments = []
    params = []

    if name is not None:
        slug = unique_slug(conn, owner_id, name)
        assignments.append("name = ?")
        params.append(name)
        assignments.append("slug = ?")
        params.append(slug)
    else:
        slug = None

    if secret is not None:
        assignments.append("secret = ?")
        params.append(int(secret))

    if not assignments:
        return slug

    rows = _db.update(
        conn,
        "activity",
        owner_id,
        assignments=", ".join(assignments),
        assignment_params=params,
        where="id = ?",
        params=(activity_id,),
    )
    if rows == 0:
        raise ActivityNotFoundError(f"activity {activity_id} not found for owner {owner_id}")

    log.info(
        "activities.update",
        owner_id=owner_id,
        activity_id=activity_id,
        slug=slug,
        secret=secret,
    )
    return slug


def delete_activity(
    conn: sqlite3.Connection,
    *,
    owner_id: int,
    activity_id: int,
) -> bool:
    """Delete an activity and its entire subtree, scoped to *owner_id*.

    The delete is owner-scoped. ``ON DELETE CASCADE`` from ``activity -> entry``
    removes the whole subtree. Returns ``True`` if the activity row was deleted.
    """
    rows = _db.delete(
        conn,
        "activity",
        owner_id,
        where="id = ?",
        params=(activity_id,),
    )
    deleted = rows == 1

    log.info(
        "activities.delete",
        owner_id=owner_id,
        activity_id=activity_id,
        deleted=deleted,
    )
    return deleted
