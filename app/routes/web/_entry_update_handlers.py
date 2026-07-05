"""Entry update and log-sheet helpers."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from fastapi import Request
from fastapi.responses import HTMLResponse

from app.auth import users
from app.models import db
from app.routes.web._entry_form_context import _build_log_sheet_fields
from app.routes.web._entry_row_render import _render_template_html
from app.routes.web._shared import templates
from app.services import _db, entries

PayloadError = entries.PayloadError
EntryNotFoundError = entries.EntryNotFoundError


async def update_entry_body(request: Request, activity_id: int, entry_id: int, owner_id: int) -> HTMLResponse:
    try:
        existing = entries.get(owner_id, entry_id)
    except EntryNotFoundError:
        return HTMLResponse(status_code=404)
    if existing["activity_id"] != activity_id:
        return HTMLResponse(status_code=404)

    form = await request.form()
    tz = users.resolve_timezone(str(form.get("entry_timezone") or "").strip() or None)
    occurred_at, time_known = entries.resolve_occurred_at(
        str(form.get("date") or "").strip(),
        str(form.get("time") or "").strip(),
        tz=tz,
    )

    # Extract memo from form. Numeric value is not editable here.
    memo = str(form.get("memo") or "").strip() or None

    try:
        updated = entries.update(
            owner_id, entry_id,
            memo=memo,
            occurred_at=occurred_at,
            time_known=time_known,
            tags=None,
            tz=tz,
        )
    except PayloadError:
        return HTMLResponse(status_code=422)

    row_html = _render_updated_entry_row(activity_id, owner_id, updated)
    return HTMLResponse(content=row_html, status_code=200, headers={"HX-Trigger": "log-saved"})


async def log_sheet_body(request: Request, activity_id: int, owner_id: int) -> HTMLResponse:
    tz = users.get_user_timezone(owner_id)
    now = datetime.now(tz)
    with db.connect() as conn:
        conn.execute("BEGIN")
        row = _db.fetch_one(conn, "activity", owner_id, where="id = ?", params=(activity_id,))
        if row is None:
            return HTMLResponse(status_code=404)
        fields = _build_log_sheet_fields(conn, activity_id)
    return templates.TemplateResponse(
        request=request,
        name="components/log_sheet.html.jinja2",
        context={"activity_id": activity_id, "name": row["name"], "fields": fields, "today": now.strftime("%Y-%m-%d"), "time_known": True, "time_value": now.strftime("%H:%M")},
    )


def _resolve_memo_and_tags(form: Any, field_defs: list[Any], owner_id: int) -> tuple[str | None, list[int]]:
    """Extract memo from form — tags system removed."""
    memo = str(form.get("memo") or "").strip() or None
    return memo, []


def _render_updated_entry_row(activity_id: int, owner_id: int, updated: dict[str, Any]) -> str:
    from app.auth import users as auth_users
    from app.models import db as model_db
    from app.services import comments, profiles

    user = auth_users.get_user(owner_id)
    username = user.get("username") if user is not None else None
    with model_db.connect() as conn:
        conn.execute("BEGIN")
        activity_row = profiles.get_activity_for_owner(conn, activity_id=activity_id, owner_id=owner_id)
        slug = activity_row["slug"] if activity_row is not None else None
        counts = comments.counts_for_entries(conn, [updated["id"]])
    updated = dict(updated)
    updated["comment_count"] = counts.get(updated["id"], 0)
    row_html = _render_template_html("components/entry_row.html.jinja2", {"activity_id": activity_id, "entry": updated, "username": username, "slug": slug, "expand_comment_entry_id": updated["id"]})
    return row_html
