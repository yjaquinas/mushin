"""Handler bodies for activity creation and owner detail pages."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from fastapi import Request
from fastapi.responses import HTMLResponse, RedirectResponse

from app import ui_strings
from app.auth import users
from app.models import db
from app.routes.web.history.calendar import _resolve_comment_deep_link
from app.routes.web.home.contexts import _build_card_context, _field_defs_for_activity
from app.routes.web.history.context import (
    _build_field_stats_context,
    _build_history_context,
    _build_history_tags,
)
from app.routes.web.common import templates
from app.services.activities import categories
from app.services.entries import competition, stats
from app.services.social import profiles


def new_activity_response(request: Request) -> HTMLResponse:
    return templates.TemplateResponse(request=request, name="components/activities/activity_sheet.html.jinja2", context={})


def create_activity_response(request: Request, user: dict, name: str) -> HTMLResponse | RedirectResponse:
    owner_id = int(user["id"])
    name = name.strip()
    if not name:
        return _activity_form_error(request, ui_strings.ACTIVITY_FORM_NAME_REQUIRED)

    with db.connect() as conn:
        if conn.execute(
            "SELECT 1 FROM activity"
            " WHERE owner_id = ? AND LOWER(name) = LOWER(?) AND archived_at IS NULL"
            " LIMIT 1",
            (owner_id, name),
        ).fetchone():
            return _activity_form_error(request, ui_strings.ACTIVITY_FORM_NAME_DUPLICATE)

    result = categories.create_activity(owner_id, name=name)
    with db.connect() as conn:
        slug = conn.execute(
            "SELECT slug FROM activity WHERE id = ? AND owner_id = ?",
            (result["activity_id"], owner_id),
        ).fetchone()["slug"]

    username = user.get("username")
    if username is None:
        return RedirectResponse(url="/home", status_code=303)
    response = HTMLResponse(content="", status_code=201)
    response.headers["HX-Redirect"] = profiles.canonical_activity_url(username, slug)
    return response


def _activity_form_error(request: Request, message: str) -> HTMLResponse | RedirectResponse:
    if request.headers.get("HX-Request") != "true":
        return RedirectResponse(url="/home", status_code=303)
    return templates.TemplateResponse(
        request=request,
        name="components/activities/activity_form.html.jinja2",
        context={"hx_post": "/activities", "hx_target": "#cards", "hx_swap": "beforeend", "name_error": message},
        status_code=400,
    )


def activity_detail_response(
    request: Request,
    activity_id: int,
    user: dict,
) -> HTMLResponse | RedirectResponse:
    owner_id = int(user["id"])
    tz = users.get_user_timezone(owner_id)

    with db.connect() as conn:
        conn.execute("BEGIN")
        row = profiles.get_activity_for_owner(conn, activity_id=activity_id, owner_id=owner_id)
        if row is None:
            return HTMLResponse(status_code=404)

        username = user.get("username")
        if username is not None and row["slug"] is not None and row["archived_at"] is None:
            return RedirectResponse(
                url=profiles.canonical_activity_url(username, row["slug"]), status_code=301
            )

        sub_row = conn.execute(
            """SELECT st.id, st.name, st.slug, st.count, st.streak,
                      st.last_entry_at, st.icon
                 FROM activity st
                WHERE st.id = ? AND st.owner_id = ?""",
            (activity_id, owner_id),
        ).fetchone()
        if sub_row is None:
            return HTMLResponse(status_code=404)
        field_defs = _field_defs_for_activity(conn, activity_id)
        card = _build_card_context(conn, owner_id, sub_row, tz=tz)

    context: dict[str, Any] = {"card": card}
    context["record"] = None
    context["timeline"] = []
    context["head_to_head"] = []

    username = user.get("username")
    today = datetime.now(UTC).date()
    deep_link = _resolve_comment_deep_link(
        request.query_params.get("c"), activity_id=activity_id, owner_id=owner_id, tz=tz
    )
    expand_comment_entry_id, selected_day = deep_link if deep_link is not None else (None, None)

    cs = stats.card_stats(activity_id, owner_id, tz=tz)
    context["activity_id"] = activity_id
    context["counts"] = cs["counts"]
    context["streaks"] = cs["streaks"]
    context["heatmap"] = cs["heatmap"]
    context["history"] = _build_history_context(
        activity_id,
        owner_id,
        period="month",
        anchor=selected_day or today,
        tz=tz,
        selected=selected_day,
        is_owner=True,
        can_comment=True,
        username=username,
        slug=sub_row["slug"],
        expand_comment_entry_id=expand_comment_entry_id,
    )
    context["top_tags"] = _build_history_tags(context["history"], tz=tz)
    context["field_stats"] = _build_field_stats_context(activity_id, owner_id, field_defs, tz=tz)
    context["public_notice"] = None
    context["is_owner"] = True
    context["current_page"] = "profile"
    return templates.TemplateResponse(request=request, name="web/activity/detail.html.jinja2", context=context)
