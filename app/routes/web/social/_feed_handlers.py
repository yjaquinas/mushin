"""Social feed and search handler bodies."""

from __future__ import annotations

from fastapi import Request
from fastapi.responses import HTMLResponse, RedirectResponse

from app.routes.web.common import _current_user, templates
from app.routes.web.common import ui_strings as strings
from app.routes.web.common.flash import _set_flash
from app.services.search import search
from app.services.search.discovery import recent_fellow_entries, recent_public_entries


async def social_page(request: Request, session: str | None) -> HTMLResponse | RedirectResponse:
    """Render the social page with the public feed selected."""
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
            "feed_scope": "public",
            "current_page": "social",
            "page_title": strings.SOCIAL_TITLE,
            "meta_robots": "noindex, nofollow",
        },
    )


async def social_feed(request: Request, session: str | None, scope: str) -> HTMLResponse:
    """Return the selected social feed fragment."""
    user = _current_user(session)
    if user is None:
        return HTMLResponse(status_code=401)

    owner_id = int(user["id"])
    feed_entries = (
        recent_fellow_entries(owner_id, limit=10)
        if scope == "fellows"
        else recent_public_entries(limit=10)
    )
    return templates.TemplateResponse(
        request=request,
        name="components/social/_feed.html.jinja2",
        context={"feed_entries": feed_entries, "feed_scope": scope},
    )


async def social_results(request: Request, session: str | None, q: str) -> HTMLResponse:
    """Return the grouped search results fragment for the search box."""
    user = _current_user(session)
    if user is None:
        return HTMLResponse(status_code=401)

    results = search.grouped_results(int(user["id"]), q.strip(), limit=20)
    return templates.TemplateResponse(
        request=request,
        name="components/social/explore_results.html.jinja2",
        context=results,
    )
