"""Handler bodies for the Basic Auth protected admin routes."""

from __future__ import annotations

from fastapi import HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse

from app.models import db
from app.routes.web._shared import templates
from app.services import admin_actions, admin_reports, visitor_reports


async def monitor(request: Request) -> HTMLResponse:
    period = request.query_params.get("period", "daily")
    page = _int_param(request, "page", default=1, minimum=1)
    selected_value = _selected_value(request, period)
    calendar_month = request.query_params.get("calendar_month")
    calendar_year = request.query_params.get("calendar_year")
    with db.connect() as conn:
        context = visitor_reports.dashboard_context(
            conn,
            period=period,
            selected_value=selected_value,
            calendar_month=calendar_month,
            calendar_year=calendar_year,
            page=page,
        )
        context.update(admin_reports.monitor_context(conn))
    context["admin_section"] = "monitor"
    return templates.TemplateResponse(
        request=request,
        name="admin/dashboard.html.jinja2",
        context=context,
    )


async def users(request: Request) -> HTMLResponse:
    with db.connect() as conn:
        context = admin_reports.users_context(conn)
    context["admin_section"] = "users"
    return templates.TemplateResponse(
        request=request,
        name="admin/dashboard.html.jinja2",
        context=context,
    )


async def user_detail(request: Request, user_id: int) -> HTMLResponse:
    with db.connect() as conn:
        context = admin_reports.user_detail_context(conn, user_id)
    if context is None:
        raise HTTPException(status_code=404, detail="User not found")
    context["admin_section"] = "users"
    context["admin_view"] = "user_detail"
    return templates.TemplateResponse(
        request=request,
        name="admin/dashboard.html.jinja2",
        context=context,
    )


async def edit_user(
    user_id: int, *, username: str, email: str | None, password: str | None
) -> RedirectResponse:
    with db.connect() as conn:
        try:
            admin_actions.update_user(conn, user_id, username=username, email=email, password=password)
        except admin_actions.AdminValidationError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
    return user_detail_redirect(user_id)


async def set_suspension(user_id: int, *, suspended: bool) -> RedirectResponse:
    with db.connect() as conn:
        admin_actions.set_user_suspended(conn, user_id, suspended=suspended)
    return user_detail_redirect(user_id)


async def edit_entry(user_id: int, entry_id: int, *, memo: str) -> RedirectResponse:
    with db.connect() as conn:
        admin_actions.update_entry_memo(conn, user_id, entry_id, memo)
    return user_detail_redirect(user_id)


async def set_entry_visibility(user_id: int, entry_id: int, *, hidden: bool) -> RedirectResponse:
    with db.connect() as conn:
        admin_actions.set_entry_hidden(conn, user_id, entry_id, hidden=hidden)
    return user_detail_redirect(user_id)


async def edit_comment(user_id: int, comment_id: int, *, body: str) -> RedirectResponse:
    with db.connect() as conn:
        try:
            admin_actions.update_comment_body(conn, user_id, comment_id, body)
        except admin_actions.AdminValidationError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
    return user_detail_redirect(user_id)


async def set_comment_visibility(
    user_id: int, comment_id: int, *, hidden: bool
) -> RedirectResponse:
    with db.connect() as conn:
        admin_actions.set_comment_hidden(conn, user_id, comment_id, hidden=hidden)
    return user_detail_redirect(user_id)


def user_detail_redirect(user_id: int) -> RedirectResponse:
    return RedirectResponse(url=f"/admin/users/{user_id}", status_code=303)


def _int_param(request: Request, name: str, *, default: int, minimum: int) -> int:
    raw = request.query_params.get(name)
    if raw is None:
        return default
    try:
        value = int(raw)
    except ValueError:
        return default
    return max(minimum, value)


def _selected_value(request: Request, period: str) -> str | None:
    key_by_period = {
        "daily": "day",
        "weekly": "week",
        "monthly": "month",
        "yearly": "year",
    }
    return request.query_params.get(key_by_period.get(period, "day"))
