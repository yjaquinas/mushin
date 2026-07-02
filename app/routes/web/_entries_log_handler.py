"""Handler body for ``POST /activities/{activity_id}/log`` (quick-add create).

Internal companion module (route-structure rule, option 2) — split out from
``_entries_handlers.py`` because the create-log body is the single heaviest
handler in the entries group (form parsing, the entries service call, and an
out-of-band competition-stats render). Not a route group of its own: no
``APIRouter`` here.
"""

from __future__ import annotations

from fastapi import Request
from fastapi.responses import HTMLResponse

from app.auth import users
from app.models import db
from app.routes.web._contexts import _field_defs_for_activity
from app.routes.web._shared import templates
from app.services import competition, entries
from app.services.entries import PayloadError


async def create_log_body(
    request: Request,
    activity_id: int,
    owner_id: int,
) -> HTMLResponse:
    """Create an entry and report success with no visible swap content.

    Tag selections, scale/count values and memo are read from the submitted
    form. ``occurred_at`` is editable-defaulting (backfillable). The form
    posts with ``hx-swap="none"`` (see log_sheet.html.jinja2) — the detail
    screen's stats-summary and history sections refresh themselves off the
    ``log-saved`` HX-Trigger below, so this response carries no primary
    content, only the out-of-band competition update when applicable.
    """
    tz = users.get_user_timezone(owner_id)

    form = await request.form()

    with db.connect() as conn:
        conn.execute("BEGIN")
        sub_row = conn.execute(
            """SELECT st.id FROM activity st WHERE st.id = ? AND st.owner_id = ?""",
            (activity_id, owner_id),
        ).fetchone()
        if sub_row is None:
            return HTMLResponse(status_code=404)
        field_defs = _field_defs_for_activity(conn, activity_id)

    try:
        result = entries.create_log_from_form(owner_id, activity_id, form, field_defs, tz=tz)
    except PayloadError:
        return HTMLResponse(status_code=422)
    has_match_list = result["has_match_list"]

    html = ""

    # A match-list log doesn't just update the counts -- the Record section
    # (W/L/D, timeline, head-to-head) on the same detail page is otherwise
    # stale until a full reload. Append it as an out-of-band swap.
    if has_match_list:
        record_html = templates.get_template("components/competition_stats.html.jinja2").render(
            {
                "record": competition.record(owner_id, activity_id),
                "timeline": competition.results_timeline(owner_id, activity_id),
                "head_to_head": competition.head_to_head(owner_id, activity_id),
                "oob": True,
            }
        )
        html += record_html

    response = HTMLResponse(content=html)
    response.headers["HX-Trigger"] = "log-saved"
    return response
