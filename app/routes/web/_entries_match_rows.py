"""Handler bodies for the match-list sub-form's add/remove-row fragments.

Internal companion module (route-structure rule, option 2), split out from
``_entries_handlers.py`` to keep that file clear of the 300-line ceiling.
Not a route group of its own: no ``APIRouter`` here.
"""

from __future__ import annotations

import sqlite3

from fastapi import Request
from fastapi.responses import HTMLResponse

from app.models import db
from app.routes.web._shared import templates
from app.services import _db, entries


def _require_match_list_field(
    conn: sqlite3.Connection, activity_id: int, field_def_id: int
) -> sqlite3.Row | None:
    """The ``match_list`` field_def for *field_def_id* under *activity_id*, or None."""
    return conn.execute(
        "SELECT id, label FROM field_def WHERE id = ? AND activity_id = ? AND kind = 'match_list'",
        (field_def_id, activity_id),
    ).fetchone()


async def add_match_row_body(
    request: Request,
    activity_id: int,
    field_def_id: int,
    owner_id: int,
) -> HTMLResponse:
    """Append an empty bout row to the match-list sub-form, preserving existing rows."""
    with db.connect() as conn:
        conn.execute("BEGIN")
        if not _db.exists(conn, "activity", owner_id, where="id = ?", params=(activity_id,)):
            return HTMLResponse(status_code=404)
        fd = _require_match_list_field(conn, activity_id, field_def_id)
        if fd is None:
            return HTMLResponse(status_code=404)

    form = await request.form()
    rows = entries.parse_match_rows(form, field_def_id)
    rows.append(dict(entries.EMPTY_MATCH_ROW))

    return templates.TemplateResponse(
        request=request,
        name="components/match_rows.html.jinja2",
        context={
            "activity_id": activity_id,
            "field": {"id": field_def_id, "label": fd["label"]},
            "rows": rows,
        },
    )


async def remove_match_row_body(
    request: Request,
    activity_id: int,
    field_def_id: int,
    row_index: int,
    owner_id: int,
) -> HTMLResponse:
    """Remove bout row *row_index* from the match-list sub-form.

    Always leaves at least one (possibly empty) row so the sub-form never
    disappears entirely.
    """
    with db.connect() as conn:
        conn.execute("BEGIN")
        if not _db.exists(conn, "activity", owner_id, where="id = ?", params=(activity_id,)):
            return HTMLResponse(status_code=404)
        fd = _require_match_list_field(conn, activity_id, field_def_id)
        if fd is None:
            return HTMLResponse(status_code=404)

    form = await request.form()
    rows = entries.parse_match_rows(form, field_def_id)
    if 0 <= row_index < len(rows):
        del rows[row_index]
    if not rows:
        rows.append(dict(entries.EMPTY_MATCH_ROW))

    return templates.TemplateResponse(
        request=request,
        name="components/match_rows.html.jinja2",
        context={
            "activity_id": activity_id,
            "field": {"id": field_def_id, "label": fd["label"]},
            "rows": rows,
        },
    )
