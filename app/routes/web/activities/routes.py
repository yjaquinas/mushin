"""Thin route declarations for activity creation."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Cookie, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse

from app.auth import sessions
from app.routes.web.activities.handlers import (
    create_activity_response,
    new_activity_response,
)
from app.routes.web.common import _current_user

router = APIRouter()


@router.get("/activities/new", response_class=HTMLResponse)
async def new_activity(
    request: Request,
    session: Annotated[str | None, Cookie(alias=sessions.COOKIE_NAME)] = None,
) -> HTMLResponse:
    """Manual create-activity form: name only, rendered as an inline sheet.

    Both home-page entry points ("+ Add activity" and "start from scratch")
    open this same HTMX sheet fragment — there is no standalone full-page
    create-activity route.
    """
    user = _current_user(session)
    if user is None:
        return RedirectResponse(url="/", status_code=303)
    return new_activity_response(request, user)


@router.post("/activities", response_model=None)
async def create_activity(
    request: Request,
    name: Annotated[str, Form()],
    secret: Annotated[bool, Form()] = False,
    session: Annotated[str | None, Cookie(alias=sessions.COOKIE_NAME)] = None,
) -> HTMLResponse | RedirectResponse:
    """Create a general-log activity (manual form or one-tap example adopt).

    On success, returns 201 with ``HX-Redirect`` to the new activity's
    detail page (``/@{username}/{slug}``).
    """
    user = _current_user(session)
    if user is None:
        return RedirectResponse(url="/", status_code=303)
    return create_activity_response(request, user, name, secret=secret)



