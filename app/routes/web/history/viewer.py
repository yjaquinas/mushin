"""Viewer/capability helpers for history rendering."""

from __future__ import annotations

from typing import Any

from app.auth import users
from app.services.social import profiles

if True:
    from fastapi.responses import HTMLResponse


def resolve_history_viewer(conn: Any, activity_id: int, current_uid: int | None) -> "dict[str, Any] | HTMLResponse":
    from fastapi.responses import HTMLResponse

    owner_row = conn.execute(
        """SELECT u.id, u.username, u.visibility, st.slug AS activity_slug FROM activity st JOIN user u ON u.id = st.owner_id WHERE st.id = ?""",
        (activity_id,),
    ).fetchone()
    if owner_row is None:
        return HTMLResponse(status_code=404)
    profile_user = {
        "id": owner_row["id"],
        "username": owner_row["username"],
        "visibility": owner_row["visibility"],
    }
    owner_id = int(profile_user["id"])
    cap = profiles.viewer_capability(conn, current_user_id=current_uid, profile_user=profile_user)
    is_owner = cap == "owner"
    if not is_owner and not profiles.can_view_activity_detail(conn, current_user_id=current_uid, profile_user=profile_user):
        return HTMLResponse(status_code=404)
    can_comment = True if is_owner else profiles.can_comment_on_entry(conn, current_user_id=current_uid, profile_user=profile_user, activity_id=activity_id)
    return {
        "owner_id": owner_id,
        "is_owner": is_owner,
        "can_comment": can_comment,
        "username": profile_user["username"],
        "slug": owner_row["activity_slug"],
        "profile_user": profile_user,
        "tz": users.get_user_timezone(owner_id),
    }
