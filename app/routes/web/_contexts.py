"""Card, fellows, and home context-assembly helpers for the ``web`` surface.

Read helpers
------------
``app/services/`` doesn't yet expose a "list my categories/sub-tallies/fields"
view (that's outside this task's owned files), so the small read-only queries
needed to assemble the home screen and the quick-add recipe live here as
private helpers, built on the owner-scoped ``app.services._db`` accessors —
the same pattern ``app/services/stats.py`` uses for field lookups. They contain
no business rules (no counting/streak math — that's ``app/services/stats.py``).

History/calendar context-assembly (``_build_history_context`` and its
calendar/heatmap helpers) lives in the sibling ``_history_context.py`` —
split out to keep this file clear of the 300-line ceiling.
"""

from __future__ import annotations

import sqlite3
from datetime import UTC, datetime
from typing import Any
from zoneinfo import ZoneInfo

from app.services import categories, comments, connections, entries, stats

_EMPTY_MATCH_ROW: dict[str, str] = entries.EMPTY_MATCH_ROW


# ---------------------------------------------------------------------------
# Read-only view assembly (no business rules — see module docstring)
# ---------------------------------------------------------------------------


def _list_sub_tallies(conn: sqlite3.Connection, owner_id: int) -> list[sqlite3.Row]:
    """Active activities for *owner_id*, joined with their category, ordered
    by category sort_order then activity sort_order."""
    return conn.execute(
        """SELECT st.id, st.name, st.slug, st.count_mode, st.cached_count, st.cached_streak,
                  st.last_entry_at, st.category_id, c.name AS category_name, c.icon AS icon
             FROM activity st
             JOIN category c ON c.id = st.category_id
            WHERE st.owner_id = ?
              AND st.archived_at IS NULL
              AND c.archived_at IS NULL
            ORDER BY c.sort_order, st.sort_order""",
        (owner_id,),
    ).fetchall()


def _field_defs_for_activity(conn: sqlite3.Connection, activity_id: int) -> list[sqlite3.Row]:
    """Recipe fields for an activity, in the stored field-priority order."""
    return conn.execute(
        "SELECT id, kind, label, sort_order FROM field_def"
        " WHERE activity_id = ? ORDER BY sort_order",
        (activity_id,),
    ).fetchall()


def _build_card_context(
    conn: sqlite3.Connection,
    owner_id: int,
    activity_row: sqlite3.Row,
    *,
    tz: ZoneInfo,
    selected_tags: set[int] | None = None,
    linked: bool = False,
) -> dict[str, Any]:
    """Assemble the per-card render context: hero, progress, advance line.

    Field-priority order (shared domain rule): hero stat -> progress
    affordance -> advance line. The hero is always the running count — Mushin
    tracks activity and frequency, not tiers or levels.
    """
    activity_id = activity_row["id"]

    progress: dict[str, Any] | None = None
    advance_line: str | None = None
    hero_label = activity_row["cached_count"] or 0

    counts = stats.counts_for_sub_tallies([activity_id], owner_id, tz=tz).get(activity_id, {})
    streak = activity_row["cached_streak"] or 0

    field_defs = _field_defs_for_activity(conn, activity_id)
    fields = []
    for fd in field_defs:
        field_ctx: dict[str, Any] = {
            "id": fd["id"],
            "kind": fd["kind"],
            "label": fd["label"],
        }
        if fd["kind"] == "tag_group":
            field_ctx["hashtag_text"] = ""
        fields.append(field_ctx)

    slug = activity_row["slug"] if "slug" in activity_row.keys() else None

    return {
        "id": activity_id,
        "slug": slug,
        "category_name": activity_row["category_name"],
        "icon": activity_row["icon"] or categories.DEFAULT_ICON,
        "name": activity_row["name"],
        "show_breadcrumb": activity_row["category_name"] != activity_row["name"],
        # Always "running" — there is no leveling ladder left. Kept as a
        # context key (rather than removed) because some templates still
        # branch on this string; do not drop the key until they're updated.
        "count_mode": "running",
        "hero_label": hero_label,
        "progress": progress,
        "advance_line": advance_line,
        "lifetime": counts.get("lifetime", activity_row["cached_count"] or 0),
        "streak": streak,
        "fields": fields,
        "now": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M"),
        "linked": linked,
    }


def _build_fellows_context(
    profile_user_id: int,
    *,
    viewer_id: int | None,
    is_owner: bool,
) -> dict[str, Any]:
    """Assemble the ``fellows_section`` context for *profile_user_id*'s page.

    Names-vs-count rule: the fellow list's ``@username`` rows are shown only
    to the profile owner and to a viewer who is themselves a mutual fellow of
    that profile — every other viewer (stranger, logged-out, pending) gets
    only the ``fellow_count`` number, never the clickable names (so a private
    fellow can't be outed by association). The owner additionally gets the
    requests cluster (incoming/outgoing pending) and a content-free pending
    count badge.
    """
    fellows = connections.list_fellows(profile_user_id)
    is_mutual_fellow = (
        not is_owner
        and viewer_id is not None
        and connections.relationship_state(viewer_id, profile_user_id) == "fellow"
    )
    show_names = is_owner or is_mutual_fellow

    context: dict[str, Any] = {
        "fellow_count": len(fellows),
        "fellows": fellows if show_names else [],
        "show_fellow_names": show_names,
        "is_owner": is_owner,
        "profile_user_id": profile_user_id,
    }

    if is_owner:
        context["incoming_requests"] = connections.list_incoming_pending(profile_user_id)
        context["outgoing_requests"] = connections.list_outgoing_pending(profile_user_id)
        context["pending_count"] = connections.pending_count(profile_user_id)
    else:
        context["incoming_requests"] = []
        context["outgoing_requests"] = []
        context["pending_count"] = 0

    return context


def _build_home_context(conn: sqlite3.Connection, owner_id: int, tz: ZoneInfo) -> dict[str, Any]:
    """Assemble the owner-dashboard context: cards (linked) + example categories.

    Shared by ``_render_home`` (``GET /home``) and the unified profile route
    (``GET /@{username}`` in ``app/routes/public/profile.py``) so the owner-
    rendering logic lives in exactly one place. Takes an already-open
    connection per ``app/models/db.py`` convention (one connection per
    request).

    Also reads the unseen-comment count (``comments.unseen_comment_count``,
    derived live against the ``comments_seen_at`` watermark — no stored
    notification entity) for the home badge. Home **never writes**
    ``comments_seen_at`` — the badge only clears once the owner actually
    visits ``GET /comments`` (the dedicated notification-history page), which
    is the sole place that watermark advances. Stamping it on every home load
    made the badge show a count once and vanish before the owner could act on
    it; see ``comments`` route for the fix.
    """
    sub_tallies = _list_sub_tallies(conn, owner_id)
    cards = [_build_card_context(conn, owner_id, row, tz=tz, linked=True) for row in sub_tallies]
    fellows_context = _build_fellows_context(owner_id, viewer_id=owner_id, is_owner=True)

    unseen_comments = comments.unseen_comment_count(conn, owner_id)

    return {
        "cards": cards,
        "examples": categories.EXAMPLE_CATEGORIES,
        "fellows": fellows_context,
        "unseen_comments": unseen_comments,
    }
