"""Public profile route (``/@{username}``)."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Cookie, Request
from fastapi.responses import HTMLResponse, RedirectResponse

from app.auth import sessions, users
from app.models import db
from app.routes.public.common.contexts import templates
from app.routes.public.profile._contexts import read_only_profile_context
from app.routes.web import (
    _build_home_context,
    _clear_flash,
    _read_flash,
    consent_gate_redirect,
)
from app.services.search import indexing
from app.services.social import profiles
from app.ui_strings import META_DESCRIPTION_PROFILE

router = APIRouter()

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
            context = _build_home_context(conn, owner_id, tz, bio=(full_user or {}).get("bio", ""))
            context["flash_message"] = _read_flash(request)
            context["current_page"] = "profile"
            context["page_title"] = username
            context["username"] = username
            context["profile_url"] = profiles.canonical_profile_url(username)
            context["share_label"] = f"@{username}"
            context["meta_robots"] = "noindex, nofollow"
            context["share_copied_text"] = f"Link to @{username} copied"
            context["share_failed_text"] = "Couldn't share the link."
            response = templates.TemplateResponse(
                request=request,
                name="web/home/profile.html.jinja2",
                context=context,
            )
            _clear_flash(response)
            return response

        if cap == "blocked":
            return HTMLResponse(status_code=404)

        context = read_only_profile_context(
            conn,
            username,
            owner_id,
            cap=cap,
            tz=users.get_user_timezone(owner_id),
            current_uid=current_uid,
            visibility=user["visibility"],
            bio=user.get("bio", "") if cap != "limited" else "",
        )
        is_indexable = cap == "public" and indexing.is_indexable_profile(conn, user)
        context.update(
            flash_message=_read_flash(request),
            current_page="social",
            page_title=username,
            profile_url=profiles.canonical_profile_url(username),
            share_label=f"@{username}",
            share_copied_text=f"Link to @{username} copied",
            share_failed_text="Couldn't share the link.",
            meta_robots="index, follow" if is_indexable else "noindex, nofollow",
            meta_description=META_DESCRIPTION_PROFILE.format(username=username),
            og_title=f"{username} · Mushin",
            og_description=META_DESCRIPTION_PROFILE.format(username=username),
            og_type="profile",
        )

    response = templates.TemplateResponse(
        request=request,
        name="web/social/public_profile.html.jinja2",
        context=context,
    )
    _clear_flash(response)
    return response
