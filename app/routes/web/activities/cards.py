"""Card and fellows context helpers for the web surface."""

from __future__ import annotations

import sqlite3
from datetime import UTC, datetime
from typing import Any
from zoneinfo import ZoneInfo

from app.routes.web.history.context import _build_card_top_tags
from app.services.activities import categories
from app.services.entries import comments, entries, stats
from app.services.social import connections


def _list_activities(conn: sqlite3.Connection, owner_id: int) -> list[sqlite3.Row]:
    return conn.execute(
        """SELECT id, name, slug, count, streak,
                  last_entry_at, icon
             FROM activity
            WHERE owner_id = ? AND archived_at IS NULL
            ORDER BY sort_order, id""",
        (owner_id,),
    ).fetchall()


def _field_defs_for_activity(conn: sqlite3.Connection, activity_id: int) -> list[sqlite3.Row]:
    """Return an empty list — field system removed."""
    return []


def _build_card_context(
    conn: sqlite3.Connection,
    owner_id: int,
    activity_row: sqlite3.Row,
    *,
    tz: ZoneInfo,
    linked: bool = False,
    include_top_tags: bool = False,
) -> dict[str, Any]:
    activity_id = activity_row["id"]
    field_defs = _field_defs_for_activity(conn, activity_id)
    card_stats = stats.card_stats(activity_id, owner_id, tz=tz)
    counts = card_stats["counts"]
    return {
        "id": activity_id,
        "slug": activity_row["slug"] if "slug" in activity_row.keys() else None,
        "icon": activity_row["icon"] or categories.DEFAULT_ICON,
        "name": activity_row["name"],
        "show_breadcrumb": False,
        "count_mode": "running",
        "hero_label": counts.get("lifetime", activity_row["count"] or 0),
        "progress": None,
        "advance_line": None,
        "lifetime": counts.get("lifetime", activity_row["count"] or 0),
        "streak": activity_row["streak"] or 0,
        "counts": counts,
        "streaks": card_stats["streaks"],
        "average_weekly_count": card_stats["average_weekly_count"],
        "heatmap": card_stats["heatmap"],
        "top_tags": _build_card_top_tags(activity_id, owner_id, field_defs, tz=tz) if include_top_tags else None,
        "fields": [],
        "now": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M"),
        "linked": linked,
    }


def _build_fellows_context(
    profile_user_id: int,
    *,
    viewer_id: int | None,
    is_owner: bool,
    visibility: str = "public",
    limit: int | None = 5,
) -> dict[str, Any]:
    fellows = connections.list_fellows(profile_user_id)
    fellow_count = len(fellows)
    show_names = is_owner or (
        viewer_id is not None
        and connections.relationship_state(viewer_id, profile_user_id) == "fellow"
        and visibility == "public"
    )
    sliced = fellows if limit is None else fellows[:limit]
    context: dict[str, Any] = {
        "fellow_count": fellow_count,
        "fellows": sliced if show_names else [],
        "show_fellow_names": show_names,
        "has_more": limit is not None and fellow_count > limit,
        "is_owner": is_owner,
        "profile_user_id": profile_user_id,
        "incoming_requests": [],
        "outgoing_requests": [],
        "pending_count": 0,
    }
    if is_owner:
        context["incoming_requests"] = connections.list_incoming_pending(profile_user_id)
        context["outgoing_requests"] = connections.list_outgoing_pending(profile_user_id)
        context["pending_count"] = connections.pending_count(profile_user_id)
    return context


def _build_home_context(conn: sqlite3.Connection, owner_id: int, tz: ZoneInfo) -> dict[str, Any]:
    cards = [_build_card_context(conn, owner_id, row, tz=tz, linked=True) for row in _list_activities(conn, owner_id)]
    return {
        "cards": cards,
        "examples": categories.EXAMPLE_ACTIVITIES,
        "fellows": _build_fellows_context(owner_id, viewer_id=owner_id, is_owner=True),
        "unseen_comments": comments.unseen_comment_count(conn, owner_id),
    }
