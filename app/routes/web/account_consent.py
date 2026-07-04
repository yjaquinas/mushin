"""One-time visibility interstitials.

Covers the retired first-run screen (``/welcome-sharing``) and the
private-redefinition re-consent screen (``/visibility-update``). New accounts
now default to public at creation, so only legacy links may hit
``/welcome-sharing``; ``/account`` is the ongoing settings home.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Cookie, Request
from fastapi.responses import HTMLResponse, RedirectResponse

from app.auth import sessions, users
from app.routes.web._shared import (
    _current_user,
    _home_url_for,
    templates,
)

router = APIRouter()


@router.get("/welcome-sharing", response_model=None)
async def welcome_sharing(
    session: Annotated[str | None, Cookie(alias=sessions.COOKIE_NAME)] = None,
) -> RedirectResponse:
    """Retired first-run screen: redirect to the normal post-login destination."""
    user = _current_user(session)
    if user is None:
        return RedirectResponse(url="/", status_code=303)
    return RedirectResponse(url=_home_url_for(user), status_code=303)


@router.post("/welcome-sharing", response_model=None)
async def submit_welcome_sharing(
    session: Annotated[str | None, Cookie(alias=sessions.COOKIE_NAME)] = None,
) -> RedirectResponse:
    """Retired first-run submit endpoint: redirect to the normal destination."""
    user = _current_user(session)
    if user is None:
        return RedirectResponse(url="/", status_code=303)
    return RedirectResponse(url=_home_url_for(user), status_code=303)


@router.get("/visibility-update", response_model=None)
async def visibility_update(
    request: Request,
    session: Annotated[str | None, Cookie(alias=sessions.COOKIE_NAME)] = None,
) -> HTMLResponse | RedirectResponse:
    """The one-time "what Private means has changed" interstitial."""
    user = _current_user(session)
    if user is None:
        return RedirectResponse(url="/", status_code=303)
    if (
        user["consent_seen_at"] is None
        or user["visibility"] != "private"
        or user["private_redefinition_seen_at"] is not None
    ):
        return RedirectResponse(url=_home_url_for(user), status_code=303)
    return templates.TemplateResponse(
        request=request,
        name="web/visibility_update.html.jinja2",
        context={"current_page": "profile"},
    )


@router.post("/visibility-update", response_model=None)
async def submit_visibility_update(
    session: Annotated[str | None, Cookie(alias=sessions.COOKIE_NAME)] = None,
) -> RedirectResponse:
    """Acknowledge the private-redefinition interstitial, then go to ``/home``."""
    user = _current_user(session)
    if user is None:
        return RedirectResponse(url="/", status_code=303)
    users.mark_redefinition_seen(int(user["id"]))
    return RedirectResponse(url=_home_url_for(user), status_code=303)
