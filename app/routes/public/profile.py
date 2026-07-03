"""Public profile route (``/@{username}``)."""

from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Cookie, Request
from fastapi.responses import HTMLResponse, RedirectResponse

from app.auth import sessions, users
from app.models import db
from app.routes.public._contexts import templates
from app.routes.web import (
    _build_card_context,
    _build_fellows_context,
    _build_home_context,
    _clear_flash,
    _home_url_for,
    _list_activities,
    _read_flash,
    consent_gate_redirect,
)
from app.services import connections, profiles

router = APIRouter()


def _read_only_profile_context(
    conn: Any,
    username: str,
    owner_id: int,
    *,
    cap: str,
    tz: Any,
    current_uid: int | None,
) -> dict[str, Any]:
    """Assemble the read-only ``public_profile.html.jinja2`` context for *cap*."""
    linked = cap in ("connected", "public")
    activities = _list_activities(conn, owner_id)
    cards = [_build_card_context(conn, owner_id, row, tz=tz, linked=linked) for row in activities]
    fellows_context = _build_fellows_context(owner_id, viewer_id=current_uid, is_owner=False)
    state = (
        connections.relationship_state(current_uid, owner_id) if current_uid is not None else "none"
    )
    return {
        "username": username,
        "view_mode": cap,
        "cards": cards,
        "fellows": fellows_context,
        "state": state,
        "viewer_logged_in": current_uid is not None,
    }


@router.get("/@{username}", response_class=HTMLResponse, response_model=None)
async def profile(
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
        cap = profiles.viewer_capability(conn, current_user_id=current_uid, profile_user=user)

        if cap == "owner":
            full_user = users.get_user(owner_id)
            if full_user is not None:
                gate = consent_gate_redirect(full_user)
                if gate is not None:
                    return gate
            tz = users.get_user_timezone(owner_id)
            context = _build_home_context(conn, owner_id, tz)
            context["flash_message"] = _read_flash(request)
            context["current_page"] = "logs"
            context["page_title"] = username
            context["profile_url"] = profiles.canonical_profile_url(username)
            context["show_back"] = False
            response = templates.TemplateResponse(
                request=request,
                name="web/home.html.jinja2",
                context=context,
            )
            _clear_flash(response)
            return response

        if cap == "blocked":
            return HTMLResponse(status_code=404)

        tz = users.get_user_timezone(owner_id)
        context = _read_only_profile_context(
            conn, username, owner_id, cap=cap, tz=tz, current_uid=current_uid
        )
        context["current_page"] = "logs"
        context["page_title"] = username
        context["profile_url"] = profiles.canonical_profile_url(username)
        context["show_back"] = False
        context["back_url"] = "/"

    return templates.TemplateResponse(
        request=request,
        name="web/public_profile.html.jinja2",
        context=context,
    )
