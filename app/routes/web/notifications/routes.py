"""Unified notification history."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Cookie, Query, Request
from fastapi.responses import HTMLResponse, RedirectResponse

from app.auth import sessions
from app.models import db
from app.routes.web.common import _current_user, consent_gate_redirect, templates
from app.routes.web.common import ui_strings as strings
from app.services.social import notifications

router = APIRouter()

_PAGE_SIZE = 10


@router.get("/notifications", response_class=HTMLResponse, response_model=None)
async def notifications_page(
    request: Request,
    session: Annotated[str | None, Cookie(alias=sessions.COOKIE_NAME)] = None,
    before_id: Annotated[int | None, Query()] = None,
) -> HTMLResponse | RedirectResponse:
    user = _current_user(session)
    if user is None:
        return RedirectResponse(url="/", status_code=303)
    gate = consent_gate_redirect(user)
    if gate is not None:
        return gate

    owner_id = int(user["id"])
    with db.connect() as conn:
        conn.execute("BEGIN")
        rows = notifications.list_notifications(
            conn,
            owner_id,
            username=user["username"],
            limit=_PAGE_SIZE + 1,
            before_id=before_id,
        )
        notifications.mark_read(conn, owner_id)

    has_more = len(rows) > _PAGE_SIZE
    rows = rows[:_PAGE_SIZE]
    next_before_id = rows[-1]["id"] if has_more and rows else None
    return templates.TemplateResponse(
        request=request,
        name="web/notifications/notifications.html.jinja2",
        context={
            "notifications": rows,
            "has_more": has_more,
            "next_before_id": next_before_id,
            "current_page": "notifications",
            "page_title": strings.NOTIFICATIONS_PAGE_TITLE,
            "meta_robots": "noindex, nofollow",
        },
    )
