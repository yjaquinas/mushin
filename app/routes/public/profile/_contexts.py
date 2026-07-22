"""Shared read-only profile context for public and social routes."""

from __future__ import annotations

from typing import Any

from app.routes.web import _build_card_context, _build_fellows_context, _list_activities
from app.services.social import connections


def read_only_profile_context(
    conn: Any,
    username: str,
    owner_id: int,
    *,
    cap: str,
    tz: Any,
    current_uid: int | None,
    visibility: str = "public",
    bio: str = "",
) -> dict[str, Any]:
    """Assemble the read-only profile context for a viewer capability."""
    linked = cap in ("connected", "public")
    activities = _list_activities(conn, owner_id, include_secret=False)
    cards = [_build_card_context(conn, owner_id, row, tz=tz, linked=linked) for row in activities]
    fellows = _build_fellows_context(owner_id, viewer_id=current_uid, is_owner=False, visibility=visibility)
    state = connections.relationship_state(current_uid, owner_id) if current_uid is not None else "none"
    return {
        "username": username,
        "view_mode": cap,
        "cards": cards,
        "fellows": fellows,
        "state": state,
        "viewer_logged_in": current_uid is not None,
        "bio": bio,
    }
