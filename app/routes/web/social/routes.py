"""Social routes; handler bodies live in companion modules."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Cookie, Query, Request
from fastapi.responses import HTMLResponse, RedirectResponse

from app.auth import sessions
from app.auth import users as auth_users
from app.models import db
from app.routes.web.social import _feed_handlers, _profile_handlers
from app.services.social import profiles

router = APIRouter()


@router.get("/social", response_class=HTMLResponse, response_model=None)
async def social_page(
    request: Request,
    session: Annotated[str | None, Cookie(alias=sessions.COOKIE_NAME)] = None,
) -> HTMLResponse | RedirectResponse:
    return await _feed_handlers.social_page(request, session)


@router.get("/social/feed", response_class=HTMLResponse)
async def social_feed(
    request: Request,
    scope: Annotated[str, Query(pattern="^(public|fellows)$")] = "public",
    cursor: Annotated[str | None, Query()] = None,
    session: Annotated[str | None, Cookie(alias=sessions.COOKIE_NAME)] = None,
) -> HTMLResponse:
    return await _feed_handlers.social_feed(request, session, scope, cursor)


@router.get("/social/results", response_class=HTMLResponse)
async def social_results(
    request: Request,
    q: Annotated[str, Query()] = "",
    session: Annotated[str | None, Cookie(alias=sessions.COOKIE_NAME)] = None,
) -> HTMLResponse:
    return await _feed_handlers.social_results(request, session, q)


@router.get("/social/@{username}", response_class=HTMLResponse, response_model=None)
async def social_profile(
    request: Request,
    username: str,
    session: Annotated[str | None, Cookie(alias=sessions.COOKIE_NAME)] = None,
) -> HTMLResponse | RedirectResponse:
    return await _profile_handlers.social_profile(request, username, sessions.read_uid(session))


@router.get("/social/@{username}/{slug}", response_class=HTMLResponse, response_model=None)
async def social_activity(
    request: Request,
    username: str,
    slug: str,
    session: Annotated[str | None, Cookie(alias=sessions.COOKIE_NAME)] = None,
) -> HTMLResponse | RedirectResponse:
    """Render another user's activity detail within the social tab."""
    current_uid = sessions.read_uid(session)

    with db.connect() as conn:
        conn.execute("BEGIN")
        profile_user = profiles.get_public_user(conn, username)
        if profile_user is None:
            return HTMLResponse(status_code=404)

        owner_id = int(profile_user["id"])
        activity_id = profiles.resolve_activity_slug(conn, owner_id, slug)
        if activity_id is None:
            return HTMLResponse(status_code=404)

        is_secret = conn.execute(
            "SELECT secret FROM activity WHERE id = ?", (activity_id,)
        ).fetchone()
        if is_secret and is_secret["secret"] and current_uid != owner_id:
            return HTMLResponse(status_code=404)

        cap = profiles.viewer_capability(
            conn, current_user_id=current_uid, profile_user=profile_user
        )
        if cap == "blocked":
            return HTMLResponse(status_code=404)
        if cap == "owner":
            target = profiles.canonical_activity_url(username, slug)
            if request.url.query:
                target = f"{target}?{request.url.query}"
            return RedirectResponse(url=target, status_code=303)
        if not profiles.can_view_activity_detail(
            conn, current_user_id=current_uid, profile_user=profile_user
        ):
            return RedirectResponse(url=f"/social/@{username}", status_code=303)

        from app.routes.public.activity.handlers import _render_readonly_activity_detail

        return _render_readonly_activity_detail(
            request,
            conn,
            username,
            slug,
            owner_id,
            activity_id,
            tz=auth_users.get_user_timezone(owner_id),
            current_user_id=current_uid,
            profile_user=profile_user,
        )
