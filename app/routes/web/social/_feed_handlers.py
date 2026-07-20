"""Social feed and search handler bodies."""

from __future__ import annotations

from fastapi import Request
from fastapi.responses import HTMLResponse, RedirectResponse

from app.routes.web.common import _current_user, templates
from app.routes.web.common import ui_strings as strings
from app.routes.web.common.flash import _set_flash
from app.services.search import search
from app.services.search.discovery import FeedCursorError, recent_social_entries

_FEED_PAGE_SIZE = 10


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
            "feed_page": recent_social_entries(int(user["id"]), "public", limit=_FEED_PAGE_SIZE),
            "feed_scope": "public",
            "current_page": "social",
            "page_title": strings.SOCIAL_TITLE,
            "meta_robots": "noindex, nofollow",
        },
    )


async def social_feed(
    request: Request, session: str | None, scope: str, cursor: str | None
) -> HTMLResponse:
    """Return the selected social feed fragment."""
    user = _current_user(session)
    if user is None:
        return HTMLResponse(status_code=401)

    owner_id = int(user["id"])
    try:
        feed_page = recent_social_entries(owner_id, scope, limit=_FEED_PAGE_SIZE, cursor=cursor)
    except FeedCursorError:
        return HTMLResponse(status_code=422)
    template_name = (
        "components/social/_feed_page.html.jinja2"
        if cursor is not None
        else "components/social/_feed.html.jinja2"
    )
    return templates.TemplateResponse(
        request=request,
        name=template_name,
        context={"feed_page": feed_page, "feed_scope": scope, "feed_append": cursor is not None},
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
