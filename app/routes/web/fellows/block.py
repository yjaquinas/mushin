"""Fellows: disconnect (remove a fellow) and block/unblock.

Disconnect and block each sit behind a two-step inline confirm (mirroring
``category_delete_confirm``); unblock is direct, no confirm step. See
``connection.py`` for the send/accept/decline/cancel request flow and the
module-level notes on session/ownership conventions shared by both files.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Cookie, Query, Request
from fastapi.responses import HTMLResponse

from app.auth import sessions
from app.routes.web._shared import _current_user, templates
from app.routes.web.fellows._shared import (
    _connect_error_message,
    _relationship_dom_id,
    _render_relationship_affordance,
    _resolve_other_user,
)
from app.services import connections

router = APIRouter()


# --- Disconnect (remove a fellow) — two-step inline confirm ---------------


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
    other = _resolve_other_user(username)
    if other is None:
        return HTMLResponse(status_code=404)

    return templates.TemplateResponse(
        request=request,
        name="components/connect_remove_confirm.html.jinja2",
        context={
            "username": username,
            "dom_id": _relationship_dom_id(username, from_search=source == "search"),
        },
    )


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
    other = _resolve_other_user(username)
    if other is None:
        return HTMLResponse(status_code=404)
    viewer_id = int(user["id"])

    connections.disconnect(viewer_id, int(other["id"]))

    return _render_relationship_affordance(
        request, username, int(other["id"]), viewer_id, from_search=source == "search"
    )


# --- Block / unblock --------------------------------------------------------


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
    other = _resolve_other_user(username)
    if other is None:
        return HTMLResponse(status_code=404)

    return templates.TemplateResponse(
        request=request,
        name="components/connect_block_confirm.html.jinja2",
        context={
            "username": username,
            "dom_id": _relationship_dom_id(username, from_search=source == "search"),
        },
    )


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
    other = _resolve_other_user(username)
    if other is None:
        return HTMLResponse(status_code=404)
    return _render_relationship_affordance(
        request, username, int(other["id"]), int(user["id"]), from_search=source == "search"
    )


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
    other = _resolve_other_user(username)
    if other is None:
        return HTMLResponse(status_code=404)
    viewer_id = int(user["id"])

    error: str | None = None
    try:
        connections.block(viewer_id, int(other["id"]))
    except connections.SelfConnectionError:
        return HTMLResponse(status_code=400)
    except connections.ConnectionError as exc:
        error = _connect_error_message(exc)

    return _render_relationship_affordance(
        request, username, int(other["id"]), viewer_id, error=error, from_search=source == "search"
    )


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
    other = _resolve_other_user(username)
    if other is None:
        return HTMLResponse(status_code=404)
    viewer_id = int(user["id"])

    connections.unblock(viewer_id, int(other["id"]))

    return _render_relationship_affordance(
        request, username, int(other["id"]), viewer_id, from_search=source == "search"
    )
