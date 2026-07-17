"""Entry update and log-sheet helpers."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from fastapi import Request
from fastapi.responses import HTMLResponse

from app.auth import users
from app.models import db
from app.routes.web.entries.form_context import _build_log_sheet_fields
from app.routes.web.entries.row_render import _render_template_html
from app.routes.web.common import templates
from app.services.common import db as _db
from app.services.entries import entries

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
    time_value = "" if form.get("no_time") else str(form.get("time") or "").strip()
    occurred_at, time_known = entries.resolve_occurred_at(
        str(form.get("date") or "").strip(),
        time_value,
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
    date_param = request.query_params.get("date")
    selected_date = date_param if date_param else now.strftime("%Y-%m-%d")
    with db.connect() as conn:
        conn.execute("BEGIN")
        row = _db.fetch_one(conn, "activity", owner_id, where="id = ?", params=(activity_id,))
        if row is None:
            return HTMLResponse(status_code=404)
        fields = _build_log_sheet_fields(conn, activity_id)
    return templates.TemplateResponse(
        request=request,
        name="components/entries/log_sheet.html.jinja2",
        context={"activity_id": activity_id, "name": row["name"], "fields": fields, "today": selected_date, "time_known": True, "time_value": now.strftime("%H:%M"), "selected_date": selected_date},
    )


def _resolve_memo_and_tags(form: Any, field_defs: list[Any], owner_id: int) -> tuple[str | None, list[int]]:
    """Extract memo from form — tags system removed."""
    memo = str(form.get("memo") or "").strip() or None
    return memo, []


def _render_updated_entry_row(activity_id: int, owner_id: int, updated: dict[str, Any]) -> str:
    from app.auth import users as auth_users
    from app.models import db as model_db
    from app.services.entries import comments
    from app.services.social import profiles

    user = auth_users.get_user(owner_id)
    username = user.get("username") if user is not None else None
    with model_db.connect() as conn:
        conn.execute("BEGIN")
        activity_row = profiles.get_activity_for_owner(conn, activity_id=activity_id, owner_id=owner_id)
        slug = activity_row["slug"] if activity_row is not None else None
        counts = comments.counts_for_entries(conn, [updated["id"]])
    updated = dict(updated)
    updated["comment_count"] = counts.get(updated["id"], 0)
    row_html = _render_template_html("components/entries/entry_row.html.jinja2", {"activity_id": activity_id, "entry": updated, "username": username, "slug": slug, "expand_comment_entry_id": updated["id"]})
    return row_html
