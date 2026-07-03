"""Handler body for ``POST /activities/{activity_id}/log`` (quick-add create)."""

from __future__ import annotations

from fastapi import Request
from fastapi.responses import HTMLResponse

from app.auth import users
from app.models import db
from app.services import entries
from app.services.entries import PayloadError


async def create_log_body(
    request: Request,
    activity_id: int,
    owner_id: int,
) -> HTMLResponse:
    """Create an entry and report success with no visible swap content."""
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

    # Build payload from form.
    memo = str(form.get("memo") or "").strip() or None
    num_value_raw = str(form.get("num_value") or "").strip()
    num_value = None
    if num_value_raw:
        try:
            num_value = float(num_value_raw)
        except ValueError:
            pass

    payload = {"memo": memo, "num_value": num_value, "tags": []}

    occurred_at, time_known = entries.resolve_occurred_at(
        str(form.get("date") or "").strip(),
        str(form.get("time") or "").strip(),
        tz=tz,
        occurred_at_utc=str(form.get("occurred_at_utc") or "").strip() or None,
    )

    try:
        entries.create(
            owner_id, activity_id, payload,
            occurred_at=occurred_at,
            tz=tz,
            time_known=time_known,
        )
    except PayloadError:
        return HTMLResponse(status_code=422)

    html = ""

    response = HTMLResponse(content=html)
    response.headers["HX-Trigger"] = "log-saved"
    return response
