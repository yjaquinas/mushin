"""Fellows request and acceptance routes."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Cookie, Query, Request
from fastapi.responses import HTMLResponse

from app.auth import sessions
from app.routes.web._shared import _current_user
from app.routes.web.fellows._connection_handlers import (
    accept_confirm_response,
    accept_connect_request_response,
    cancel_connect_request_response,
    connect_cancel_response,
    connect_confirm_response,
    decline_connect_request_response,
    requests_cancel_response,
    send_connect_request_response,
)

router = APIRouter()


@router.get("/fellows/{username}/connect-confirm", response_class=HTMLResponse)
async def connect_confirm(
    request: Request,
    username: str,
    source: Annotated[str | None, Query()] = None,
    session: Annotated[str | None, Cookie(alias=sessions.COOKIE_NAME)] = None,
) -> HTMLResponse:
    """Return the sharing-consent confirm step before sending a request."""
    user = _current_user(session)
    if user is None:
        return HTMLResponse(status_code=401)
    return connect_confirm_response(request, username, source == "search")


@router.get("/fellows/{username}/connect-cancel", response_class=HTMLResponse)
async def connect_cancel(
    request: Request,
    username: str,
    source: Annotated[str | None, Query()] = None,
    session: Annotated[str | None, Cookie(alias=sessions.COOKIE_NAME)] = None,
) -> HTMLResponse:
    """Cancel out of the connect consent step back to the plain affordance."""
    user = _current_user(session)
    if user is None:
        return HTMLResponse(status_code=401)
    return connect_cancel_response(request, username, int(user["id"]), source == "search")


@router.post("/fellows/{username}/connect", response_class=HTMLResponse)
async def send_connect_request(
    request: Request,
    username: str,
    source: Annotated[str | None, Query()] = None,
    session: Annotated[str | None, Cookie(alias=sessions.COOKIE_NAME)] = None,
) -> HTMLResponse:
    """Confirm step: send a connection request to *username*."""
    user = _current_user(session)
    if user is None:
        return HTMLResponse(status_code=401)
    return send_connect_request_response(request, username, int(user["id"]), source == "search")


@router.get("/fellows/requests/{username}/accept-confirm", response_class=HTMLResponse)
async def accept_confirm(
    request: Request,
    username: str,
    source: Annotated[str | None, Query()] = None,
    session: Annotated[str | None, Cookie(alias=sessions.COOKIE_NAME)] = None,
) -> HTMLResponse:
    """Return the sharing-consent confirm step before accepting *username*'s request."""
    user = _current_user(session)
    if user is None:
        return HTMLResponse(status_code=401)
    return accept_confirm_response(request, username, source == "search")


@router.get("/fellows/requests-cancel", response_class=HTMLResponse)
async def requests_cancel(
    request: Request,
    session: Annotated[str | None, Cookie(alias=sessions.COOKIE_NAME)] = None,
) -> HTMLResponse:
    """Cancel out of the accept consent step back to the requests cluster."""
    user = _current_user(session)
    if user is None:
        return HTMLResponse(status_code=401)
    return requests_cancel_response(request, int(user["id"]))


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
    session: Annotated[str | None, Cookie(alias=sessions.COOKIE_NAME)] = None,
) -> HTMLResponse:
    """Withdraw one's own pending outgoing request to *username* — direct."""
    user = _current_user(session)
    if user is None:
        return HTMLResponse(status_code=401)
    return cancel_connect_request_response(request, username, int(user["id"]))
