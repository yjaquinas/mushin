"""Handler bodies for history and stats refresh fragments."""

from __future__ import annotations

import json
from datetime import UTC, date, datetime
from urllib.parse import quote

from fastapi import Request
from fastapi.responses import HTMLResponse

from app.auth import users
from app.models import db
from app.routes.web.common import templates
from app.routes.web.history.context import (
    _build_card_top_tags,
    _build_field_stats_context,
    _build_history_context,
    _build_history_tags,
    resolve_history_viewer,
)
from app.routes.web.home.contexts import _field_defs_for_activity
from app.services.common import db as _db
from app.services.entries import stats
from app.services.social import profiles


def _owner_context(owner_id: int, activity_id: int) -> tuple | None:
    tz = users.get_user_timezone(owner_id)
    with db.connect() as conn:
        conn.execute("BEGIN")
        if not _db.exists(conn, "activity", owner_id, where="id = ?", params=(activity_id,)):
            return None
        field_defs = _field_defs_for_activity(conn, activity_id)
    return tz, field_defs

def activity_history_response(
    request: Request,
    activity_id: int,
    period: str,
    anchor: str | None,
    day: str | None,
    page: int,
    current_uid: int | None,
) -> HTMLResponse:
    if period not in ("month", "all"):
        return HTMLResponse(status_code=400)

    anchor_date = _parse_date_or_default(anchor)
    if anchor_date is None:
        return HTMLResponse(status_code=400)
    selected_day = _parse_date(day) if day else None
    if day and selected_day is None:
        return HTMLResponse(status_code=400)

    with db.connect() as conn:
        conn.execute("BEGIN")
        viewer = resolve_history_viewer(conn, activity_id, current_uid)
    if isinstance(viewer, HTMLResponse):
        return viewer

    login_redirect_url = None
    if not viewer["is_owner"] and current_uid is None and viewer["username"] and viewer["slug"]:
        target = profiles.safe_next_path(profiles.canonical_activity_url(viewer["username"], viewer["slug"]))
        login_redirect_url = f"/?next={quote(target or '', safe='')}"

    history_ctx = _build_history_context(
        activity_id,
        viewer["owner_id"],
        period=period,
        anchor=anchor_date,
        tz=viewer["tz"],
        is_owner=viewer["is_owner"],
        can_comment=viewer["can_comment"],
        username=viewer["username"],
        slug=viewer["slug"],
        login_redirect_url=login_redirect_url,
        selected_day=selected_day,
        page=page,
    )
    response = templates.TemplateResponse(
        request=request,
        name="components/history/history.html.jinja2",
        context={
            "activity_id": activity_id,
            "history": history_ctx,
            "top_tags": _build_history_tags(history_ctx, tz=viewer["tz"]),
            "is_owner": viewer["is_owner"],
            "can_comment": viewer["can_comment"],
            "username": viewer["username"],
            "slug": viewer["slug"],
            "login_redirect_url": login_redirect_url,
        },
    )
    if period != "all":
        response.headers["HX-Trigger"] = json.dumps({"history-period-changed": {"period": period}})
    return response


def stats_summary_fragment_response(request: Request, activity_id: int, owner_id: int) -> HTMLResponse:
    owner_ctx = _owner_context(owner_id, activity_id)
    if owner_ctx is None:
        return HTMLResponse(status_code=404)
    tz, field_defs = owner_ctx
    with db.connect() as conn:
        row = conn.execute(
            "SELECT name FROM activity WHERE id = ? AND owner_id = ?",
            (activity_id, owner_id),
        ).fetchone()
        card_name = row["name"] if row else None
    cs = stats.card_stats(activity_id, owner_id, tz=tz)
    return templates.TemplateResponse(
        request=request,
        name="components/history/stats_summary.html.jinja2",
        context={
            "activity_id": activity_id,
            "card_name": card_name,
            "counts": cs["counts"],
            "streaks": cs["streaks"],
            "average_weekly_count": cs["average_weekly_count"],
            "heatmap": cs["heatmap"],
            "top_tags": _build_card_top_tags(activity_id, owner_id, field_defs, tz=tz),
            "is_owner": True,
            "title_editable": True,
            "show_top_tags": False,
        },
    )


def field_stats_fragment_response(
    request: Request,
    activity_id: int,
    owner_id: int,
    period: str,
) -> HTMLResponse:
    if period not in ("week", "month", "year"):
        period = "month"
    owner_ctx = _owner_context(owner_id, activity_id)
    if owner_ctx is None:
        return HTMLResponse(status_code=404)
    tz, field_defs = owner_ctx
    return templates.TemplateResponse(
        request=request,
        name="components/history/field_stats.html.jinja2",
        context={"activity_id": activity_id, "field_stats": _build_field_stats_context(activity_id, owner_id, field_defs, tz=tz, period=period), "is_owner": True},
    )


def _parse_date_or_default(raw: str | None) -> date | None:
    if raw is None:
        return datetime.now(UTC).date()
    try:
        return date.fromisoformat(raw)
    except ValueError:
        return None


def _parse_date(raw: str) -> date | None:
    try:
        return date.fromisoformat(raw)
    except ValueError:
        return None


