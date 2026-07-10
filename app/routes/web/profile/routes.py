"""Profile bio — inline-editable section on the owner profile page.

The ``/profile/bio`` and ``/profile/bio-edit`` endpoints return HTMX fragments
that are swapped into ``#profile-section-bio`` on the profile page.
The ``POST /profile/bio`` persists changes and returns the display fragment.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Cookie, Form, Request
from fastapi.responses import HTMLResponse

from app.auth import sessions
from app.routes.web.common import _current_user
from app.routes.web.profile.handlers import get_bio_edit_fragment, get_bio_fragment, update_bio

router = APIRouter()


@router.get("/profile/bio", response_class=HTMLResponse, response_model=None)
async def profile_bio_display(
    request: Request,
    session: Annotated[str | None, Cookie(alias=sessions.COOKIE_NAME)] = None,
) -> HTMLResponse:
    user = _current_user(session)
    if user is None:
        return HTMLResponse(status_code=401)
    return await get_bio_fragment(request, user)


@router.get("/profile/bio-edit", response_class=HTMLResponse, response_model=None)
async def profile_bio_edit(
    request: Request,
    session: Annotated[str | None, Cookie(alias=sessions.COOKIE_NAME)] = None,
) -> HTMLResponse:
    user = _current_user(session)
    if user is None:
        return HTMLResponse(status_code=401)
    return await get_bio_edit_fragment(request, user)


@router.post("/profile/bio", response_class=HTMLResponse, response_model=None)
async def profile_bio_update(
    request: Request,
    bio: Annotated[str | None, Form()] = None,
    session: Annotated[str | None, Cookie(alias=sessions.COOKIE_NAME)] = None,
) -> HTMLResponse:
    user = _current_user(session)
    if user is None:
        return HTMLResponse(status_code=401)
    return await update_bio(request, user, bio=bio)
