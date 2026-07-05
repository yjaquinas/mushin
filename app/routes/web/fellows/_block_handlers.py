"""Handler bodies for fellows remove/block/unblock flows."""

from __future__ import annotations

from fastapi import Request
from fastapi.responses import HTMLResponse

from app.routes.web.common import templates
from app.routes.web.fellows._shared import (
    _connect_error_message,
    _remove_dialog_dom_id,
    _relationship_dom_id,
    _render_relationship_affordance,
    _resolve_other_user,
)
from app.services.social import connections


def _other_or_404(username: str) -> dict | HTMLResponse:
    other = _resolve_other_user(username)
    return other if other is not None else HTMLResponse(status_code=404)


def remove_fellow_confirm_response(request: Request, username: str, from_search: bool) -> HTMLResponse:
    other = _other_or_404(username)
    if isinstance(other, HTMLResponse):
        return other
    return templates.TemplateResponse(
        request=request,
        name="components/fellows/connect_remove_confirm.html.jinja2",
        context={
            "username": username,
            "dom_id": _relationship_dom_id(username, from_search=from_search),
            "dialog_id": _remove_dialog_dom_id(username, from_search=from_search),
            "from_search": from_search,
        },
    )


def remove_fellow_response(request: Request, username: str, viewer_id: int, from_search: bool) -> HTMLResponse:
    other = _other_or_404(username)
    if isinstance(other, HTMLResponse):
        return other
    connections.disconnect(viewer_id, int(other["id"]))
    return _render_relationship_affordance(request, username, int(other["id"]), viewer_id, from_search=from_search)


def block_confirm_response(request: Request, username: str, from_search: bool) -> HTMLResponse:
    other = _other_or_404(username)
    if isinstance(other, HTMLResponse):
        return other
    return templates.TemplateResponse(
        request=request,
        name="components/fellows/connect_block_confirm.html.jinja2",
        context={"username": username, "dom_id": _relationship_dom_id(username, from_search=from_search)},
    )


def block_cancel_response(request: Request, username: str, viewer_id: int, from_search: bool) -> HTMLResponse:
    other = _other_or_404(username)
    if isinstance(other, HTMLResponse):
        return other
    return _render_relationship_affordance(request, username, int(other["id"]), viewer_id, from_search=from_search)


def block_user_response(request: Request, username: str, viewer_id: int, from_search: bool) -> HTMLResponse:
    other = _other_or_404(username)
    if isinstance(other, HTMLResponse):
        return other
    error = None
    try:
        connections.block(viewer_id, int(other["id"]))
    except connections.SelfConnectionError:
        return HTMLResponse(status_code=400)
    except connections.ConnectionError as exc:
        error = _connect_error_message(exc)
    return _render_relationship_affordance(request, username, int(other["id"]), viewer_id, error=error, from_search=from_search)


def unblock_user_response(request: Request, username: str, viewer_id: int, from_search: bool) -> HTMLResponse:
    other = _other_or_404(username)
    if isinstance(other, HTMLResponse):
        return other
    connections.unblock(viewer_id, int(other["id"]))
    return _render_relationship_affordance(request, username, int(other["id"]), viewer_id, from_search=from_search)
