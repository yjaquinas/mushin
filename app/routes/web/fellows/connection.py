"""Fellows request and acceptance routes."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Cookie, Query, Request
from fastapi.responses import HTMLResponse

from app.auth import sessions
from app.routes.web.common import _current_user
from app.routes.web.fellows._connection_handlers import (
    accept_connect_request_response,
    cancel_connect_request_confirm_response,
    cancel_connect_request_response,
    decline_connect_request_response,
    send_connect_request_response,
)

router = APIRouter()


@router.post("/fellows/{username}/connect", response_class=HTMLResponse)
async def send_connect_request(
    request: Request,
    username: str,
    source: Annotated[str | None, Query()] = None,
    session: Annotated[str | None, Cookie(alias=sessions.COOKIE_NAME)] = None,
) -> HTMLResponse:
    """Send a connection request to *username*."""
    user = _current_user(session)
    if user is None:
        return HTMLResponse(status_code=401)
    return send_connect_request_response(request, username, int(user["id"]), source == "search")


@router.get("/fellows/requests/{username}/cancel-confirm", response_class=HTMLResponse)
async def cancel_connect_request_confirm(
    request: Request,
    username: str,
    source: Annotated[str | None, Query()] = None,
    session: Annotated[str | None, Cookie(alias=sessions.COOKIE_NAME)] = None,
) -> HTMLResponse:
    user = _current_user(session)
    if user is None:
        return HTMLResponse(status_code=401)
    return cancel_connect_request_confirm_response(request, username, source == "search")


@router.post("/fellows/requests/{username}/accept", response_class=HTMLResponse)
async def accept_connect_request(
    request: Request,
    username: str,
    source: Annotated[str | None, Query()] = None,
    session: Annotated[str | None, Cookie(alias=sessions.COOKIE_NAME)] = None,
) -> HTMLResponse:
    user = _current_user(session)
    if user is None:
        return HTMLResponse(status_code=401)
    return accept_connect_request_response(request, username, int(user["id"]), source == "search")


@router.post("/fellows/requests/{username}/decline", response_class=HTMLResponse)
async def decline_connect_request(
    request: Request,
    username: str,
    source: Annotated[str | None, Query()] = None,
    session: Annotated[str | None, Cookie(alias=sessions.COOKIE_NAME)] = None,
) -> HTMLResponse:
    user = _current_user(session)
    if user is None:
        return HTMLResponse(status_code=401)
    return decline_connect_request_response(request, username, int(user["id"]), source == "search")


@router.post("/fellows/requests/{username}/cancel", response_class=HTMLResponse)
async def cancel_connect_request(
    request: Request,
    username: str,
    source: Annotated[str | None, Query()] = None,
    session: Annotated[str | None, Cookie(alias=sessions.COOKIE_NAME)] = None,
) -> HTMLResponse:
    """Withdraw one's own pending outgoing request to *username* — direct."""
    user = _current_user(session)
    if user is None:
        return HTMLResponse(status_code=401)
    return cancel_connect_request_response(
        request,
        username,
        int(user["id"]),
        source == "search",
        source == "profile",
    )
