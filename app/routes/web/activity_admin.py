"""Rename and activity-delete admin actions for an activity."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Cookie, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse

from app.auth import sessions
from app.routes.web._activity_admin_handlers import (
    activity_delete_confirm_response,
    delete_activity_response,
    rename_activity_response,
    rename_form_response,
)
from app.routes.web._shared import _current_user

router = APIRouter()


@router.get("/activities/{activity_id}/rename-form", response_class=HTMLResponse)
async def rename_form(
    request: Request,
    activity_id: int,
    session: Annotated[str | None, Cookie(alias=sessions.COOKIE_NAME)] = None,
) -> HTMLResponse:
    """Return the rename-dialog fragment for *activity_id*."""
    user = _current_user(session)
    if user is None:
        return HTMLResponse(status_code=401)
    return rename_form_response(request, activity_id, int(user["id"]))


@router.post("/activities/{activity_id}/rename", response_class=HTMLResponse, response_model=None)
async def rename_activity(
    request: Request,
    activity_id: int,
    name: Annotated[str, Form()],
    session: Annotated[str | None, Cookie(alias=sessions.COOKIE_NAME)] = None,
) -> HTMLResponse:
    """Rename *activity_id* and redirect to the new canonical URL.

    On success: 200 with ``HX-Redirect`` to ``/@{username}/{new_slug}``.
    On ``ActivityNotFoundError``: 404.
    On ``ValueError`` (empty / too-long name): return the rename dialog fragment
    with an inline error message and auto-open it again.
    """
    user = _current_user(session)
    if user is None:
        return RedirectResponse(url="/", status_code=303)
    return rename_activity_response(request, activity_id, int(user["id"]), user, name)


@router.get("/activities/{activity_id}/delete-confirm", response_class=HTMLResponse)
async def activity_delete_confirm(
    request: Request,
    activity_id: int,
    session: Annotated[str | None, Cookie(alias=sessions.COOKIE_NAME)] = None,
) -> HTMLResponse:
    """Return the delete-confirm dialog for *activity_id*.

    Ownership check: the activity must exist and belong to the session user — 404 otherwise.
    """
    user = _current_user(session)
    if user is None:
        return HTMLResponse(status_code=401)
    return activity_delete_confirm_response(request, activity_id, int(user["id"]))


@router.post("/activities/{activity_id}/delete", response_class=HTMLResponse)
async def delete_activity(
    activity_id: int,
    session: Annotated[str | None, Cookie(alias=sessions.COOKIE_NAME)] = None,
) -> HTMLResponse:
    """Delete *activity_id* and all its entries.

    On success (or if already gone): ``HX-Redirect`` to the owner's home/profile
    URL with status 200. Non-owner or unknown activity: 404.
    """
    user = _current_user(session)
    if user is None:
        return HTMLResponse(status_code=401)
    return delete_activity_response(activity_id, int(user["id"]), user)
