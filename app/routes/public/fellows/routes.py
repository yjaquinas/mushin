"""Public fellows list (``/@{username}/fellows``)."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Cookie, Request
from fastapi.responses import HTMLResponse, RedirectResponse

from app.auth import sessions, users as auth_users
from app.models import db
from app.routes.public.common.contexts import templates
from app.routes.web import _build_fellows_context
from app.routes.web.common.flash import _set_flash
from app.services.social import connections, profiles

router = APIRouter()


@router.get("/@{username}/fellows", response_class=HTMLResponse, response_model=None)
async def public_fellows(
    request: Request,
    username: str,
    session: Annotated[str | None, Cookie(alias=sessions.COOKIE_NAME)] = None,
) -> HTMLResponse | RedirectResponse:
    current_uid = sessions.read_uid(session)

    with db.connect() as conn:
        conn.execute("BEGIN")
        user = profiles.get_public_user(conn, username)
        if user is None:
            return HTMLResponse(status_code=404)

        owner_id = int(user["id"])
        cap = profiles.viewer_capability(
            conn, current_user_id=current_uid, profile_user=user
        )

        if cap == "blocked":
            return HTMLResponse(status_code=404)

        if cap == "limited":
            response = RedirectResponse(url=f"/social/@{username}", status_code=303)
            _set_flash(response, "fellows_private")
            return response

        if cap == "owner":
            full_user = auth_users.get_user(owner_id)
            if full_user is not None:
                from app.routes.web.common import consent_gate_redirect
                gate = consent_gate_redirect(full_user)
                if gate is not None:
                    return gate

        tz = auth_users.get_user_timezone(owner_id)
        fellows_context = _build_fellows_context(
            owner_id, viewer_id=current_uid, is_owner=(cap == "owner"),
            visibility=user["visibility"], limit=None,
        )
        state = (
            connections.relationship_state(current_uid, owner_id)
            if current_uid is not None else "none"
        )

    return templates.TemplateResponse(
        request=request,
        name="web/fellows/fellows_list.html.jinja2",
        context={
            "username": username,
            "view_mode": cap,
            "fellows": fellows_context,
            "state": state,
            "viewer_logged_in": current_uid is not None,
            "is_owner": cap == "owner",
            "requests_hx_target": "#fellows-content",
            "requests_hx_source": "?source=fellows-page",
            "current_page": "profile" if cap == "owner" else "social",
            "page_title": username,
            "profile_url": profiles.canonical_profile_url(username),
        },
    )
