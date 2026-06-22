"""Handler body for ``POST /activities/{activity_id}/log`` (quick-add create).

Internal companion module (route-structure rule, option 2) — split out from
``_entries_handlers.py`` because the create-log body is the single heaviest
handler in the entries group (form parsing, the entries service call, a
card-context rebuild, and an out-of-band competition-stats render). Not a
route group of its own: no ``APIRouter`` here.
"""

from __future__ import annotations

from fastapi import Request
from fastapi.responses import HTMLResponse

from app.auth import users
from app.models import db
from app.routes.web._contexts import _build_card_context, _field_defs_for_activity
from app.routes.web._shared import templates
from app.services import competition, entries


async def create_log_body(
    request: Request,
    activity_id: int,
    owner_id: int,
) -> HTMLResponse:
    """Create an entry and return the updated activity-card fragment.

    Tag selections, scale/count values and memo are read from the submitted
    form. ``occurred_at`` is editable-defaulting (backfillable). The
    just-used tag selections are echoed back into the swapped card so they
    "survive" the swap, per the component-patterns skill.
    """
    tz = users.get_user_timezone(owner_id)

    form = await request.form()

    with db.connect() as conn:
        conn.execute("BEGIN")
        sub_row = conn.execute(
            """SELECT st.id, st.name, st.count_mode, st.cached_count, st.cached_streak,
                      st.last_entry_at, st.category_id, c.name AS category_name, c.icon AS icon
                 FROM activity st
                 JOIN category c ON c.id = st.category_id
                WHERE st.id = ? AND st.owner_id = ?""",
            (activity_id, owner_id),
        ).fetchone()
        if sub_row is None:
            return HTMLResponse(status_code=404)
        field_defs = _field_defs_for_activity(conn, activity_id)

    result = entries.create_log_from_form(owner_id, activity_id, form, field_defs, tz=tz)
    selected_tags = result["selected_tags"]
    has_match_list = result["has_match_list"]

    with db.connect() as conn:
        conn.execute("BEGIN")
        # Re-fetch for fresh cached_count/streak after entries.create's cache refresh.
        sub_row = conn.execute(
            """SELECT st.id, st.name, st.count_mode, st.cached_count, st.cached_streak,
                      st.last_entry_at, st.category_id, c.name AS category_name, c.icon AS icon
                 FROM activity st
                 JOIN category c ON c.id = st.category_id
                WHERE st.id = ? AND st.owner_id = ?""",
            (activity_id, owner_id),
        ).fetchone()
        card = _build_card_context(conn, owner_id, sub_row, tz=tz, selected_tags=selected_tags)

    card["bumped"] = True

    html = templates.get_template("components/activity_card.html.jinja2").render(
        {
            "card": card,
        }
    )

    # A match-list log doesn't just update the hero card -- the Record
    # section (W/L/D, timeline, head-to-head) on the same detail page is
    # otherwise stale until a full reload. Append it as an out-of-band swap
    # alongside the hero-card fragment this response already targets.
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
