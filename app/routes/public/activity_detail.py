"""Public activity detail route (``/@{username}/{slug}``)."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Cookie, Request
from fastapi.responses import HTMLResponse, RedirectResponse

from app.auth import sessions, users
from app.models import db
from app.routes.public._activity_detail_handlers import (
    _render_owner_activity_detail,
    _render_readonly_activity_detail,
)
from app.routes.web import _build_card_context, _field_defs_for_activity
from app.services import profiles

router = APIRouter()


@router.get("/@{username}/{slug}", response_class=HTMLResponse, response_model=None)
async def public_activity(
    request: Request,
    username: str,
    slug: str,
    session: Annotated[str | None, Cookie(alias=sessions.COOKIE_NAME)] = None,
) -> HTMLResponse | RedirectResponse:
    current_uid = sessions.read_uid(session)

    with db.connect() as conn:
        conn.execute("BEGIN")
        user = profiles.get_public_user(conn, username)
        if user is None:
            return HTMLResponse(status_code=404)

        owner_id = int(user["id"])
        activity_id = profiles.resolve_activity_slug(conn, owner_id, slug)
        if activity_id is None:
            return HTMLResponse(status_code=404)

        cap = profiles.viewer_capability(conn, current_user_id=current_uid, profile_user=user)
        tz = users.get_user_timezone(owner_id)

        # ------------------------------------------------------------------
        # Branch 1 — owner viewing their own activity
        # ------------------------------------------------------------------
        if cap == "owner":
            sub_row = conn.execute(
                """SELECT st.id, st.name, st.slug, st.count, st.streak,
                          st.last_entry_at, st.icon
                     FROM activity st
                    WHERE st.id = ? AND st.owner_id = ?""",
                (activity_id, owner_id),
            ).fetchone()
            field_defs = _field_defs_for_activity(conn, activity_id)
            card = _build_card_context(conn, owner_id, sub_row, tz=tz)
            can_comment = profiles.can_comment_on_entry(
                conn, current_user_id=current_uid, profile_user=user, activity_id=activity_id
            )

        # ------------------------------------------------------------------
        # Branches 2-4 — non-owner viewer
        # ------------------------------------------------------------------
        else:
            if cap == "blocked":
                return HTMLResponse(status_code=404)

            if not profiles.can_view_activity_detail(
                conn, current_user_id=current_uid, profile_user=user
            ):
                return RedirectResponse(
                    url=profiles.canonical_profile_url(username), status_code=303
                )

            return _render_readonly_activity_detail(
                request,
                conn,
                username,
                slug,
                owner_id,
                activity_id,
                tz=tz,
                current_user_id=current_uid,
                profile_user=user,
            )

    return _render_owner_activity_detail(
        request,
        username=username,
        slug=slug,
        owner_id=owner_id,
        activity_id=activity_id,
        user=user,
        card=card,
        field_defs=field_defs,
        has_match_list=False,
        can_comment=can_comment,
        tz=tz,
    )
