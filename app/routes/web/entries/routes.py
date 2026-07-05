"""Thin route declarations for entry editing and logging."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Cookie, Request
from fastapi.responses import HTMLResponse, RedirectResponse

from app.auth import sessions
from app.routes.web.entries.route_handlers import (
    cancel_entry_edit_response,
    create_log_response,
    delete_entry_response,
    get_entry_delete_confirm_response,
    get_entry_edit_form_response,
    log_sheet_response,
    owner_id_from_user,
    remove_match_row_response,
    update_entry_response,
)
from app.routes.web.common import _current_user

router = APIRouter()


def _owner_gate(session: str | None, *, redirect: bool = False) -> int | HTMLResponse | RedirectResponse:
    owner_id = owner_id_from_user(_current_user(session))
    if owner_id is None:
        if redirect:
            return RedirectResponse(url="/", status_code=303)
        return HTMLResponse(status_code=401)
    return owner_id

@router.get("/activities/{activity_id}/entries/{entry_id}/edit", response_class=HTMLResponse)
async def get_entry_edit_form(
    request: Request,
    activity_id: int,
    entry_id: int,
    session: Annotated[str | None, Cookie(alias=sessions.COOKIE_NAME)] = None,
) -> HTMLResponse:
    owner_id = _owner_gate(session)
    if not isinstance(owner_id, int):
        return owner_id
    return await get_entry_edit_form_response(request, activity_id, entry_id, owner_id)

@router.get("/activities/{activity_id}/entries/{entry_id}/cancel-edit", response_class=HTMLResponse)
async def cancel_entry_edit(
    request: Request,
    activity_id: int,
    entry_id: int,
    session: Annotated[str | None, Cookie(alias=sessions.COOKIE_NAME)] = None,
) -> HTMLResponse:
    owner_id = _owner_gate(session)
    if not isinstance(owner_id, int):
        return owner_id
    return cancel_entry_edit_response(request, activity_id, entry_id, owner_id)

@router.post("/activities/{activity_id}/entries/{entry_id}", response_class=HTMLResponse)
async def update_entry(
    request: Request,
    activity_id: int,
    entry_id: int,
    session: Annotated[str | None, Cookie(alias=sessions.COOKIE_NAME)] = None,
) -> HTMLResponse:
    owner_id = _owner_gate(session)
    if not isinstance(owner_id, int):
        return owner_id
    return await update_entry_response(request, activity_id, entry_id, owner_id)

@router.get("/activities/{activity_id}/entries/{entry_id}/delete-confirm", response_class=HTMLResponse)
async def get_entry_delete_confirm(
    request: Request,
    activity_id: int,
    entry_id: int,
    session: Annotated[str | None, Cookie(alias=sessions.COOKIE_NAME)] = None,
) -> HTMLResponse:
    owner_id = _owner_gate(session)
    if not isinstance(owner_id, int):
        return owner_id
    return get_entry_delete_confirm_response(request, activity_id, entry_id, owner_id)

@router.post("/activities/{activity_id}/entries/{entry_id}/delete", response_class=HTMLResponse)
async def delete_entry(
    request: Request,
    activity_id: int,
    entry_id: int,
    session: Annotated[str | None, Cookie(alias=sessions.COOKIE_NAME)] = None,
) -> HTMLResponse:
    owner_id = _owner_gate(session)
    if not isinstance(owner_id, int):
        return owner_id
    return delete_entry_response(activity_id, entry_id, owner_id)

@router.get("/activities/{activity_id}/log", response_class=HTMLResponse)
async def log_sheet(
    request: Request,
    activity_id: int,
    session: Annotated[str | None, Cookie(alias=sessions.COOKIE_NAME)] = None,
) -> HTMLResponse:
    owner_id = _owner_gate(session, redirect=True)
    if not isinstance(owner_id, int):
        return owner_id
    return await log_sheet_response(request, activity_id, owner_id)

# Match-row routes removed — match table dropped.

@router.post("/activities/{activity_id}/log", response_class=HTMLResponse)
async def create_log(
    request: Request,
    activity_id: int,
    session: Annotated[str | None, Cookie(alias=sessions.COOKIE_NAME)] = None,
) -> HTMLResponse:
    owner_id = _owner_gate(session, redirect=True)
    if not isinstance(owner_id, int):
        return owner_id
    return await create_log_response(request, activity_id, owner_id)
