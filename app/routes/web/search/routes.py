"""Search (people, tags, and activities).

Session-authenticated. The page route always renders the full page (with
an initial empty/prompt results region); the results route is HTMX-only,
debounced by the search box itself (see web/search/search.html.jinja2), and
always returns the components/search/search_results.html.jinja2 fragment — a
blank query renders a calm prompt, never an error.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Cookie, Query, Request
from fastapi.responses import HTMLResponse, RedirectResponse

from app.auth import sessions
from app.routes.web.common import _current_user, templates
from app.routes.web.common import ui_strings as strings
from app.services.search import search

router = APIRouter()


@router.get("/search", response_class=HTMLResponse, response_model=None)
async def search_page(
    request: Request,
    session: Annotated[str | None, Cookie(alias=sessions.COOKIE_NAME)] = None,
) -> HTMLResponse | RedirectResponse:
    """Render the search page — a search box plus an initially-empty results region."""
    user = _current_user(session)
    if user is None:
        return RedirectResponse(url="/", status_code=303)

    return templates.TemplateResponse(
        request=request,
        name="web/search/search.html.jinja2",
        context={
            "query": "",
            "kind": "",
            "people": [],
            "tags": [],
            "activities": [],
            "current_page": "search",
            "page_title": strings.SEARCH_TITLE,
            "show_back": False,
        },
    )


@router.get("/search/results", response_class=HTMLResponse)
async def search_results(
    request: Request,
    q: Annotated[str, Query()] = "",
    session: Annotated[str | None, Cookie(alias=sessions.COOKIE_NAME)] = None,
) -> HTMLResponse:
    """Return the grouped search results fragment for the search box.

    A blank *q* renders the calm prompt state (handled inside the template)
    rather than running a query.
    """
    user = _current_user(session)
    if user is None:
        return HTMLResponse(status_code=401)
    owner_id = int(user["id"])

    query = q.strip()
    results = search.grouped_results(owner_id, query, limit=20)

    return templates.TemplateResponse(
        request=request,
        name="components/search/search_results.html.jinja2",
        context=results,
    )
