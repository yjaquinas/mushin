"""Handler body for ``POST /activities/{activity_id}/log`` (quick-add create)."""

from __future__ import annotations

from fastapi import Request
from fastapi.responses import HTMLResponse

import json

from app import ui_strings
from app.auth import users
from app.models import db
from app.services.entries import entries
from app.services.entries.entries import PayloadError
from app.services.plans import EntryDateLimitError, get_all_plan_configs


async def create_log_body(
    request: Request,
    activity_id: int,
    owner_id: int,
) -> HTMLResponse:
    """Create an entry and report success with no visible swap content."""
    form = await request.form()
    tz = users.resolve_timezone(str(form.get("entry_timezone") or "").strip() or None)

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

    time_value = "" if form.get("no_time") else str(form.get("time") or "").strip()
    occurred_at, time_known = entries.resolve_occurred_at(
        str(form.get("date") or "").strip(),
        time_value,
        tz=tz,
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
    except EntryDateLimitError:
        with db.connect() as conn:
            plans = get_all_plan_configs(conn)
        basic = next((p for p in plans if p["plan"] == "basic"), {})
        premium = next((p for p in plans if p["plan"] == "premium"), {})
        max_val = basic.get("max_entries_per_date", 1)
        premium_max = premium.get("max_entries_per_date", 10)
        response = HTMLResponse(content="", status_code=400)
        response.headers["HX-Trigger"] = json.dumps({
            "show-toast": {
                "message": ui_strings.ENTRY_DATE_LIMIT_TOAST.format(max=max_val, premium_max=premium_max),
                "variant": "warning",
            }
        })
        response.headers["HX-Reswap"] = "none"
        return response

    html = ""

    response = HTMLResponse(content=html)
    response.headers["HX-Trigger"] = "log-saved"
    return response
