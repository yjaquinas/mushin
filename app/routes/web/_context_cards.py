"""Card and fellows context helpers for the web surface."""

from __future__ import annotations

import sqlite3
from datetime import UTC, datetime
from typing import Any
from zoneinfo import ZoneInfo

from app.routes.web._history_context import _build_card_top_tags
from app.services import categories, comments, connections, entries, stats

_EMPTY_MATCH_ROW: dict[str, str] = entries.EMPTY_MATCH_ROW


def _list_activities(conn: sqlite3.Connection, owner_id: int) -> list[sqlite3.Row]:
    return conn.execute(
        """SELECT st.id, st.name, st.slug, st.count_mode, st.cached_count, st.cached_streak,
                  st.last_entry_at, st.category_id, c.name AS category_name, c.icon AS icon
             FROM activity st JOIN category c ON c.id = st.category_id
            WHERE st.owner_id = ? AND st.archived_at IS NULL AND c.archived_at IS NULL
            ORDER BY c.sort_order, st.sort_order""",
        (owner_id,),
    ).fetchall()


def _field_defs_for_activity(conn: sqlite3.Connection, activity_id: int) -> list[sqlite3.Row]:
    return conn.execute(
        "SELECT id, kind, label, sort_order FROM field_def WHERE activity_id = ? ORDER BY sort_order",
        (activity_id,),
    ).fetchall()


def _build_card_context(conn: sqlite3.Connection, owner_id: int, activity_row: sqlite3.Row, *, tz: ZoneInfo, linked: bool = False) -> dict[str, Any]:
    activity_id = activity_row["id"]
    field_defs = _field_defs_for_activity(conn, activity_id)
    card_stats = stats.card_stats(activity_id, owner_id, tz=tz)
    counts = card_stats["counts"]
    fields = []
    for fd in field_defs:
        field_ctx: dict[str, Any] = {"id": fd["id"], "kind": fd["kind"], "label": fd["label"]}
        if fd["kind"] == "tag_group":
            field_ctx["hashtag_text"] = ""
        fields.append(field_ctx)
    return {
        "id": activity_id,
        "slug": activity_row["slug"] if "slug" in activity_row.keys() else None,
        "category_name": activity_row["category_name"],
        "icon": activity_row["icon"] or categories.DEFAULT_ICON,
        "name": activity_row["name"],
        "show_breadcrumb": activity_row["category_name"] != activity_row["name"],
        "count_mode": "running",
        "hero_label": counts.get("lifetime", activity_row["cached_count"] or 0),
        "progress": None,
        "advance_line": None,
        "lifetime": counts.get("lifetime", activity_row["cached_count"] or 0),
        "streak": activity_row["cached_streak"] or 0,
        "counts": counts,
        "streaks": card_stats["streaks"],
        "heatmap": card_stats["heatmap"],
        "top_tags": _build_card_top_tags(activity_id, owner_id, field_defs, tz=tz),
        "fields": fields,
        "now": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M"),
        "linked": linked,
    }


def _build_fellows_context(profile_user_id: int, *, viewer_id: int | None, is_owner: bool) -> dict[str, Any]:
    fellows = connections.list_fellows(profile_user_id)
    show_names = is_owner or (
        viewer_id is not None and connections.relationship_state(viewer_id, profile_user_id) == "fellow"
    )
    context: dict[str, Any] = {
        "fellow_count": len(fellows),
        "fellows": fellows if show_names else [],
        "show_fellow_names": show_names,
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
        "examples": categories.EXAMPLE_CATEGORIES,
        "fellows": _build_fellows_context(owner_id, viewer_id=owner_id, is_owner=True),
        "unseen_comments": comments.unseen_comment_count(conn, owner_id),
    }
