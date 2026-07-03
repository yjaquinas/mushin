"""Fellows: disconnect (remove a fellow) and block/unblock.

Disconnect and block each sit behind a two-step inline confirm (mirroring
``activity_delete_confirm``); unblock is direct, no confirm step. See
``connection.py`` for the send/accept/decline/cancel request flow and the
module-level notes on session/ownership conventions shared by both files.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Cookie, Query, Request
from fastapi.responses import HTMLResponse

from app.auth import sessions
from app.routes.web._shared import _current_user
from app.routes.web.fellows._block_handlers import (
    block_cancel_response,
    block_confirm_response,
    block_user_response,
    remove_fellow_confirm_response,
    remove_fellow_response,
    unblock_user_response,
)

router = APIRouter()


@router.get("/fellows/{username}/remove-confirm", response_class=HTMLResponse)
async def remove_fellow_confirm(
    request: Request,
    username: str,
    source: Annotated[str | None, Query()] = None,
    session: Annotated[str | None, Cookie(alias=sessions.COOKIE_NAME)] = None,
) -> HTMLResponse:
    """Return the inline "remove this fellow" confirm step."""
    user = _current_user(session)
    if user is None:
        return HTMLResponse(status_code=401)
    return remove_fellow_confirm_response(request, username, source == "search")


@router.post("/fellows/{username}/remove", response_class=HTMLResponse)
async def remove_fellow(
    request: Request,
    username: str,
    source: Annotated[str | None, Query()] = None,
    session: Annotated[str | None, Cookie(alias=sessions.COOKIE_NAME)] = None,
) -> HTMLResponse:
    """Confirm step: remove the fellow connection with *username*."""
    user = _current_user(session)
    if user is None:
        return HTMLResponse(status_code=401)
    return remove_fellow_response(request, username, int(user["id"]), source == "search")


@router.get("/fellows/{username}/block-confirm", response_class=HTMLResponse)
async def block_confirm(
    request: Request,
    username: str,
    source: Annotated[str | None, Query()] = None,
    session: Annotated[str | None, Cookie(alias=sessions.COOKIE_NAME)] = None,
) -> HTMLResponse:
    """Return the inline "block this account" confirm step."""
    user = _current_user(session)
    if user is None:
        return HTMLResponse(status_code=401)
    return block_confirm_response(request, username, source == "search")


@router.get("/fellows/{username}/block-cancel", response_class=HTMLResponse)
async def block_cancel(
    request: Request,
    username: str,
    source: Annotated[str | None, Query()] = None,
    session: Annotated[str | None, Cookie(alias=sessions.COOKIE_NAME)] = None,
) -> HTMLResponse:
    """Cancel out of the block confirm step back to the plain affordance."""
    user = _current_user(session)
    if user is None:
        return HTMLResponse(status_code=401)
    return block_cancel_response(request, username, int(user["id"]), source == "search")


@router.post("/fellows/{username}/block", response_class=HTMLResponse)
async def block_user(
    request: Request,
    username: str,
    source: Annotated[str | None, Query()] = None,
    session: Annotated[str | None, Cookie(alias=sessions.COOKIE_NAME)] = None,
) -> HTMLResponse:
    """Confirm step: block *username*. Tears down any connection both ways."""
    user = _current_user(session)
    if user is None:
        return HTMLResponse(status_code=401)
    return block_user_response(request, username, int(user["id"]), source == "search")


@router.post("/fellows/{username}/unblock", response_class=HTMLResponse)
async def unblock_user(
    request: Request,
    username: str,
    source: Annotated[str | None, Query()] = None,
    session: Annotated[str | None, Cookie(alias=sessions.COOKIE_NAME)] = None,
) -> HTMLResponse:
    """Lift a block on *username* — direct, no confirm step."""
    user = _current_user(session)
    if user is None:
        return HTMLResponse(status_code=401)
    return unblock_user_response(request, username, int(user["id"]), source == "search")
