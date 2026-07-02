"""Thin route declarations for history and stats refresh fragments."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Cookie, Request
from fastapi.responses import HTMLResponse

from app.auth import sessions
from app.routes.web._history_handlers import (
    activity_history_response,
    field_stats_fragment_response,
    stats_summary_fragment_response,
)
from app.routes.web._shared import _current_user

router = APIRouter()


@router.get("/activities/{activity_id}/history", response_class=HTMLResponse)
async def activity_history(
    request: Request,
    activity_id: int,
    period: str,
    anchor: str | None = None,
    day: str | None = None,
    session: Annotated[str | None, Cookie(alias=sessions.COOKIE_NAME)] = None,
) -> HTMLResponse:
    return activity_history_response(
        request, activity_id, period, anchor, day, sessions.read_uid(session)
    )


@router.get("/activities/{activity_id}/stats-summary", response_class=HTMLResponse)
async def stats_summary_fragment(
    request: Request,
    activity_id: int,
    session: Annotated[str | None, Cookie(alias=sessions.COOKIE_NAME)] = None,
) -> HTMLResponse:
    user = _current_user(session)
    if user is None:
        return HTMLResponse(status_code=401)
    return stats_summary_fragment_response(request, activity_id, int(user["id"]))


@router.get("/activities/{activity_id}/field-stats", response_class=HTMLResponse)
async def field_stats_fragment(
    request: Request,
    activity_id: int,
    period: str = "month",
    session: Annotated[str | None, Cookie(alias=sessions.COOKIE_NAME)] = None,
) -> HTMLResponse:
    user = _current_user(session)
    if user is None:
        return HTMLResponse(status_code=401)
    return field_stats_fragment_response(request, activity_id, int(user["id"]), period)
