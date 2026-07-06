"""Social (people, tags, and activities).

Session-authenticated. The page route always renders the full page (with
an initial empty/prompt results region); the results route is HTMX-only,
debounced by the search box itself (see web/social/social.html.jinja2), and
always returns the components/social/explore_results.html.jinja2 fragment — a
blank query renders recent public entries instead.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Cookie, Query, Request
from fastapi.responses import HTMLResponse, RedirectResponse

from app.auth import sessions, users as auth_users
from app.models import db
from app.routes.web import (
    _build_card_context,
    _build_fellows_context,
    _list_activities,
)
from app.routes.web.common import _current_user, templates
from app.routes.web.common import ui_strings as strings
from app.routes.web.common.flash import _set_flash
from app.services.search import search
from app.services.search.discovery import recent_public_entries
from app.services.social import connections, profiles

router = APIRouter()


@router.get("/social", response_class=HTMLResponse, response_model=None)
async def social_page(
    request: Request,
    session: Annotated[str | None, Cookie(alias=sessions.COOKIE_NAME)] = None,
) -> HTMLResponse | RedirectResponse:
    """Render the social page — a search box plus an initially-empty results region."""
    user = _current_user(session)
    if user is None:
        response = RedirectResponse(url="/", status_code=303)
        _set_flash(response, "login_required")
        return response

    return templates.TemplateResponse(
        request=request,
        name="web/social/social.html.jinja2",
        context={
            "query": "",
            "kind": "",
            "people": [],
            "tags": [],
            "activities": [],
            "feed_entries": recent_public_entries(limit=10),
            "current_page": "social",
            "page_title": strings.SOCIAL_TITLE,
        },
    )


@router.get("/social/results", response_class=HTMLResponse)
async def social_results(
    request: Request,
    q: Annotated[str, Query()] = "",
    session: Annotated[str | None, Cookie(alias=sessions.COOKIE_NAME)] = None,
) -> HTMLResponse:
    """Return the grouped search results fragment for the search box.

    A blank *q* renders recent public entries instead of running a query.
    """
    user = _current_user(session)
    if user is None:
        return HTMLResponse(status_code=401)
    owner_id = int(user["id"])

    query = q.strip()
    results = search.grouped_results(owner_id, query, limit=20)

    if not query:
        results["feed_entries"] = recent_public_entries(limit=10)

    return templates.TemplateResponse(
        request=request,
        name="components/social/explore_results.html.jinja2",
        context=results,
    )


@router.get("/social/@{username}", response_class=HTMLResponse, response_model=None)
async def social_profile(
    request: Request,
    username: str,
    session: Annotated[str | None, Cookie(alias=sessions.COOKIE_NAME)] = None,
) -> HTMLResponse | RedirectResponse:
    """Render another user's profile within the social tab."""
    current_uid = sessions.read_uid(session)

    with db.connect() as conn:
        conn.execute("BEGIN")
        profile_user = profiles.get_public_user(conn, username)
        if profile_user is None:
            return HTMLResponse(status_code=404)

        owner_id = int(profile_user["id"])
        cap = profiles.viewer_capability(
            conn, current_user_id=current_uid, profile_user=profile_user
        )

        if cap == "owner":
            return RedirectResponse(url="/home", status_code=303)

        if cap == "blocked":
            return HTMLResponse(status_code=404)

        tz = auth_users.get_user_timezone(owner_id)
        context = _read_only_social_profile_context(
            conn, username, owner_id, cap=cap, tz=tz, current_uid=current_uid
        )
        context["current_page"] = "social"
        context["page_title"] = username
        context["profile_url"] = profiles.canonical_profile_url(username)
        context["share_label"] = f"@{username}"
        context["share_copied_text"] = f"Link to @{username} copied"
        context["share_failed_text"] = "Couldn't share the link."

    return templates.TemplateResponse(
        request=request,
        name="web/home/public_profile.html.jinja2",
        context=context,
    )


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

        cap = profiles.viewer_capability(
            conn, current_user_id=current_uid, profile_user=profile_user
        )

        if cap == "blocked":
            return HTMLResponse(status_code=404)

        if cap == "owner":
            return RedirectResponse(url=f"/@{username}/{slug}", status_code=303)

        if not profiles.can_view_activity_detail(
            conn, current_user_id=current_uid, profile_user=profile_user
        ):
            return RedirectResponse(url=f"/social/@{username}", status_code=303)

        tz = auth_users.get_user_timezone(owner_id)
        from app.routes.public.activity.handlers import _render_readonly_activity_detail

        return _render_readonly_activity_detail(
            request,
            conn,
            username,
            slug,
            owner_id,
            activity_id,
            tz=tz,
            current_user_id=current_uid,
            profile_user=profile_user,
        )


@router.get("/social/@{username}/{slug}/{entry_id}", response_class=HTMLResponse, response_model=None)
async def social_entry(
    request: Request,
    username: str,
    slug: str,
    entry_id: int,
    session: Annotated[str | None, Cookie(alias=sessions.COOKIE_NAME)] = None,
) -> HTMLResponse | RedirectResponse:
    """Deep-link to a specific entry on another user's activity page within the social tab."""
    user = _current_user(session)
    if user is None:
        return RedirectResponse(
            url=f"/@{username}/{slug}?entry_id={entry_id}", status_code=303
        )
    return RedirectResponse(
        url=f"/social/@{username}/{slug}?entry_id={entry_id}", status_code=303
    )


def _read_only_social_profile_context(
    conn,
    username: str,
    owner_id: int,
    *,
    cap: str,
    tz,
    current_uid: int | None,
) -> dict:
    """Assemble the read-only profile context for the social tab."""
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
