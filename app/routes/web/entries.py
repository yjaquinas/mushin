"""Entry edit-in-place, delete, and the quick-add/log sheet + match rows.

Thin route declarations only — handler bodies live in three internal
companions: ``_entries_handlers.py`` (edit/delete/log-sheet),
``_entries_log_handler.py`` (the create-log body), and
``_entries_match_rows.py`` (match-list add/remove-row bodies) — per the
route-structure rule's 300-line resolution order.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Cookie, Request
from fastapi.responses import HTMLResponse, RedirectResponse

from app.auth import sessions, users
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
from app.routes.web._shared import _current_user, templates
from app.services import _db, entries

router = APIRouter()


# ---------------------------------------------------------------------------
# Entry edit-in-place
# ---------------------------------------------------------------------------


@router.get(
    "/activities/{activity_id}/entries/{entry_id}/edit",
    response_class=HTMLResponse,
)
async def get_entry_edit_form(
    request: Request,
    activity_id: int,
    entry_id: int,
    session: Annotated[str | None, Cookie(alias=sessions.COOKIE_NAME)] = None,
) -> HTMLResponse:
    """Return the edit form fragment for *entry_id* under *activity_id*.

    Ownership checks (in order):
    1. Session required — 401 if not authenticated.
    2. Entry must exist for this owner — 404 via EntryNotFoundError.
    3. Entry must belong to the requested activity_id — 404 on mismatch.
    """
    user = _current_user(session)
    if user is None:
        return HTMLResponse(status_code=401)
    owner_id = int(user["id"])

    try:
        entry = entries.get(owner_id, entry_id)
    except EntryNotFoundError:
        return HTMLResponse(status_code=404)

    if entry["activity_id"] != activity_id:
        return HTMLResponse(status_code=404)

    with db.connect() as conn:
        conn.execute("BEGIN")
        if not _db.exists(conn, "activity", owner_id, where="id = ?", params=(activity_id,)):
            return HTMLResponse(status_code=404)
        fields = _build_edit_fields_context(conn, owner_id, activity_id, entry)

    return templates.TemplateResponse(
        request=request,
        name="components/entry_edit_form.html.jinja2",
        context={"activity_id": activity_id, "entry": entry, "fields": fields},
    )


@router.get(
    "/activities/{activity_id}/entries/{entry_id}/cancel-edit",
    response_class=HTMLResponse,
)
async def cancel_entry_edit(
    request: Request,
    activity_id: int,
    entry_id: int,
    session: Annotated[str | None, Cookie(alias=sessions.COOKIE_NAME)] = None,
) -> HTMLResponse:
    """Return the read-only entry row fragment (cancel path).

    Same ownership checks as the edit GET.
    """
    user = _current_user(session)
    if user is None:
        return HTMLResponse(status_code=401)
    owner_id = int(user["id"])

    try:
        entry = entries.get(owner_id, entry_id)
    except EntryNotFoundError:
        return HTMLResponse(status_code=404)

    if entry["activity_id"] != activity_id:
        return HTMLResponse(status_code=404)

    return _render_entry_row(request, activity_id, owner_id, entry)


@router.post(
    "/activities/{activity_id}/entries/{entry_id}",
    response_class=HTMLResponse,
)
async def update_entry(
    request: Request,
    activity_id: int,
    entry_id: int,
    session: Annotated[str | None, Cookie(alias=sessions.COOKIE_NAME)] = None,
) -> HTMLResponse:
    """Update *entry_id* and return the refreshed read-only row fragment."""
    user = _current_user(session)
    if user is None:
        return HTMLResponse(status_code=401)
    owner_id = int(user["id"])
    return await update_entry_body(request, activity_id, entry_id, owner_id)


# ---------------------------------------------------------------------------
# Entry delete
# ---------------------------------------------------------------------------


@router.get(
    "/activities/{activity_id}/entries/{entry_id}/delete-confirm",
    response_class=HTMLResponse,
)
async def get_entry_delete_confirm(
    request: Request,
    activity_id: int,
    entry_id: int,
    session: Annotated[str | None, Cookie(alias=sessions.COOKIE_NAME)] = None,
) -> HTMLResponse:
    """Return the inline delete-confirm fragment for *entry_id* under *activity_id*.

    Ownership checks (in order):
    1. Session required — 401 if not authenticated.
    2. Entry must exist for this owner — 404 via EntryNotFoundError.
    3. Entry must belong to the requested activity_id — 404 on mismatch.
    """
    user = _current_user(session)
    if user is None:
        return HTMLResponse(status_code=401)
    owner_id = int(user["id"])

    try:
        entry = entries.get(owner_id, entry_id)
    except EntryNotFoundError:
        return HTMLResponse(status_code=404)

    if entry["activity_id"] != activity_id:
        return HTMLResponse(status_code=404)

    return templates.TemplateResponse(
        request=request,
        name="components/entry_delete_confirm.html.jinja2",
        context={"activity_id": activity_id, "entry": entry},
    )


@router.post(
    "/activities/{activity_id}/entries/{entry_id}/delete",
    response_class=HTMLResponse,
)
async def delete_entry(
    request: Request,
    activity_id: int,
    entry_id: int,
    session: Annotated[str | None, Cookie(alias=sessions.COOKIE_NAME)] = None,
) -> HTMLResponse:
    """Delete *entry_id* and return an empty 200 so HTMX removes the row from the DOM.

    Ownership checks are the same as the delete-confirm GET.
    """
    user = _current_user(session)
    if user is None:
        return HTMLResponse(status_code=401)
    owner_id = int(user["id"])

    try:
        entry = entries.get(owner_id, entry_id)
    except EntryNotFoundError:
        return HTMLResponse(status_code=404)

    if entry["activity_id"] != activity_id:
        return HTMLResponse(status_code=404)

    tz = users.get_user_timezone(owner_id)
    entries.delete(owner_id, entry_id, tz=tz)
    return HTMLResponse(content="", status_code=200)


# ---------------------------------------------------------------------------
# Quick-add / log sheet
# ---------------------------------------------------------------------------


@router.get("/activities/{activity_id}/log", response_class=HTMLResponse)
async def log_sheet(
    request: Request,
    activity_id: int,
    session: Annotated[str | None, Cookie(alias=sessions.COOKIE_NAME)] = None,
) -> HTMLResponse:
    """Render the quick-add sheet fragment for a sub-tally."""
    user = _current_user(session)
    if user is None:
        return RedirectResponse(url="/", status_code=303)
    owner_id = int(user["id"])
    return await log_sheet_body(request, activity_id, owner_id)


@router.get("/activities/{activity_id}/log-inline", response_class=HTMLResponse)
async def log_sheet_inline(
    request: Request,
    activity_id: int,
    session: Annotated[str | None, Cookie(alias=sessions.COOKIE_NAME)] = None,
) -> HTMLResponse:
    """Render the quick-add form inline (no dialog wrapper)."""
    user = _current_user(session)
    if user is None:
        return RedirectResponse(url="/", status_code=303)
    owner_id = int(user["id"])
    return await log_sheet_body(request, activity_id, owner_id, inline=True)


@router.post("/activities/{activity_id}/match-rows/{field_def_id}/add", response_class=HTMLResponse)
async def add_match_row(
    request: Request,
    activity_id: int,
    field_def_id: int,
    session: Annotated[str | None, Cookie(alias=sessions.COOKIE_NAME)] = None,
) -> HTMLResponse:
    """Append an empty bout row to the match-list sub-form, preserving existing rows."""
    user = _current_user(session)
    if user is None:
        return HTMLResponse(status_code=401)
    owner_id = int(user["id"])
    return await add_match_row_body(request, activity_id, field_def_id, owner_id)


@router.post(
    "/activities/{activity_id}/match-rows/{field_def_id}/remove/{row_index}",
    response_class=HTMLResponse,
)
async def remove_match_row(
    request: Request,
    activity_id: int,
    field_def_id: int,
    row_index: int,
    session: Annotated[str | None, Cookie(alias=sessions.COOKIE_NAME)] = None,
) -> HTMLResponse:
    """Remove bout row *row_index* from the match-list sub-form.

    Always leaves at least one (possibly empty) row so the sub-form never
    disappears entirely.
    """
    user = _current_user(session)
    if user is None:
        return HTMLResponse(status_code=401)
    owner_id = int(user["id"])
    return await remove_match_row_body(request, activity_id, field_def_id, row_index, owner_id)


@router.post("/activities/{activity_id}/log", response_class=HTMLResponse)
async def create_log(
    request: Request,
    activity_id: int,
    session: Annotated[str | None, Cookie(alias=sessions.COOKIE_NAME)] = None,
) -> HTMLResponse:
    """Create an entry and return the updated activity-card fragment.

    Tag selections, scale/count values and memo are read from the submitted
    form. ``occurred_at`` is editable-defaulting (backfillable). The just-used
    tag selections are echoed back into the swapped card so they "survive" the
    swap, per the component-patterns skill.
    """
    user = _current_user(session)
    if user is None:
        return RedirectResponse(url="/", status_code=303)
    owner_id = int(user["id"])
    return await create_log_body(request, activity_id, owner_id)
