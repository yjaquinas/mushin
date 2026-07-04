"""Thin route handler bodies for entry and log-sheet endpoints."""

from __future__ import annotations

from datetime import datetime

from fastapi import Request
from fastapi.responses import HTMLResponse

from app.auth import users
from app.models import db
from app.routes.web._entries_handlers import (
    EntryNotFoundError,
    _build_edit_fields_context,
    _render_entry_row,
    log_sheet_body,
    update_entry_body,
)
from app.routes.web._entries_log_handler import create_log_body
from app.routes.web._entries_match_rows import add_match_row_body, remove_match_row_body
from app.routes.web._shared import templates
from app.services import _db, entries


def owner_id_from_user(user: dict | None) -> int | None:
    if user is None:
        return None
    return int(user["id"])


def owned_entry(owner_id: int, activity_id: int, entry_id: int) -> dict | None:
    try:
        entry = entries.get(owner_id, entry_id)
    except EntryNotFoundError:
        return None
    if entry["activity_id"] != activity_id:
        return None
    return entry


def _entry_local_datetime_fields(entry: dict, owner_id: int) -> tuple[str, str]:
    tz = users.get_user_timezone(owner_id)
    try:
        dt = datetime.fromisoformat(str(entry["occurred_at"]).replace("Z", "+00:00"))
    except (KeyError, TypeError, ValueError):
        dt = datetime.now(tz)
    return dt.strftime("%Y-%m-%d"), dt.strftime("%H:%M")


async def get_entry_edit_form_response(
    request: Request,
    activity_id: int,
    entry_id: int,
    owner_id: int,
) -> HTMLResponse:
    entry = owned_entry(owner_id, activity_id, entry_id)
    if entry is None:
        return HTMLResponse(status_code=404)

    with db.connect() as conn:
        conn.execute("BEGIN")
        if not _db.exists(conn, "activity", owner_id, where="id = ?", params=(activity_id,)):
            return HTMLResponse(status_code=404)
        activity_row = _db.fetch_one(
            conn,
            "activity",
            owner_id,
            where="id = ?",
            params=(activity_id,),
            columns="name",
        )
        fields = _build_edit_fields_context(conn, owner_id, activity_id, entry)

    date_value, time_value = _entry_local_datetime_fields(entry, owner_id)

    return templates.TemplateResponse(
        request=request,
        name="components/entry_edit_form.html.jinja2",
        context={
            "activity_id": activity_id,
            "entry": entry,
            "fields": fields,
            "activity_name": activity_row["name"] if activity_row is not None else "",
            "today": date_value,
            "time_known": entry["time_known"] == 1,
            "time_value": time_value if entry["time_known"] == 1 else "",
        },
    )


def cancel_entry_edit_response(
    request: Request,
    activity_id: int,
    entry_id: int,
    owner_id: int,
) -> HTMLResponse:
    entry = owned_entry(owner_id, activity_id, entry_id)
    if entry is None:
        return HTMLResponse(status_code=404)
    return _render_entry_row(request, activity_id, owner_id, entry)


async def update_entry_response(
    request: Request,
    activity_id: int,
    entry_id: int,
    owner_id: int,
) -> HTMLResponse:
    if owned_entry(owner_id, activity_id, entry_id) is None:
        return HTMLResponse(status_code=404)
    return await update_entry_body(request, activity_id, entry_id, owner_id)


def get_entry_delete_confirm_response(
    request: Request,
    activity_id: int,
    entry_id: int,
    owner_id: int,
) -> HTMLResponse:
    entry = owned_entry(owner_id, activity_id, entry_id)
    if entry is None:
        return HTMLResponse(status_code=404)
    return templates.TemplateResponse(
        request=request,
        name="components/entry_delete_confirm.html.jinja2",
        context={"activity_id": activity_id, "entry": entry},
    )


def delete_entry_response(activity_id: int, entry_id: int, owner_id: int) -> HTMLResponse:
    if owned_entry(owner_id, activity_id, entry_id) is None:
        return HTMLResponse(status_code=404)
    tz = users.get_user_timezone(owner_id)
    entries.delete(owner_id, entry_id, tz=tz)
    return HTMLResponse(content="", status_code=200)


async def log_sheet_response(request: Request, activity_id: int, owner_id: int) -> HTMLResponse:
    return await log_sheet_body(request, activity_id, owner_id)


async def add_match_row_response(
    request: Request,
    activity_id: int,
    field_def_id: int,
    owner_id: int,
) -> HTMLResponse:
    return await add_match_row_body(request, activity_id, field_def_id, owner_id)


async def remove_match_row_response(
    request: Request,
    activity_id: int,
    field_def_id: int,
    row_index: int,
    owner_id: int,
) -> HTMLResponse:
    return await remove_match_row_body(request, activity_id, field_def_id, row_index, owner_id)


async def create_log_response(request: Request, activity_id: int, owner_id: int) -> HTMLResponse:
    return await create_log_body(request, activity_id, owner_id)
