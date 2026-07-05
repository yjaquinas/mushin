"""Handler bodies for fellows request and acceptance flows."""

from __future__ import annotations

from fastapi import Request
from fastapi.responses import HTMLResponse

from app.routes.web.common import templates
from app.routes.web.fellows._shared import (
    _cancel_request_dialog_dom_id,
    _connect_error_message,
    _relationship_dom_id,
    _render_fellows_section,
    _render_relationship_affordance,
    _resolve_other_user,
)
from app.services.social import connections


def _other_or_404(username: str) -> dict | HTMLResponse:
    other = _resolve_other_user(username)
    return other if other is not None else HTMLResponse(status_code=404)


def send_connect_request_response(request: Request, username: str, viewer_id: int, from_search: bool) -> HTMLResponse:
    other = _other_or_404(username)
    if isinstance(other, HTMLResponse):
        return other
    error = None
    try:
        connections.send_request(viewer_id, int(other["id"]))
    except connections.SelfConnectionError:
        return HTMLResponse(status_code=400)
    except connections.ConnectionError as exc:
        error = _connect_error_message(exc)
    return _render_relationship_affordance(request, username, int(other["id"]), viewer_id, error=error, from_search=from_search)


def cancel_connect_request_confirm_response(request: Request, username: str, from_search: bool) -> HTMLResponse:
    other = _other_or_404(username)
    if isinstance(other, HTMLResponse):
        return other
    return templates.TemplateResponse(
        request=request,
        name="components/fellows/connect_cancel_request_confirm.html.jinja2",
        context={
            "username": username,
            "dom_id": _relationship_dom_id(username, from_search=from_search),
            "dialog_id": _cancel_request_dialog_dom_id(username, from_search=from_search),
            "from_search": from_search,
        },
    )


def accept_connect_request_response(request: Request, username: str, owner_id: int, from_search: bool) -> HTMLResponse:
    other = _other_or_404(username)
    if isinstance(other, HTMLResponse):
        return other
    error = None
    try:
        connections.accept(owner_id, int(other["id"]))
    except connections.ConnectionError as exc:
        error = _connect_error_message(exc)
    if from_search:
        return _render_relationship_affordance(request, username, int(other["id"]), owner_id, error=error, from_search=True)
    return _render_fellows_section(request, owner_id, viewer_id=owner_id, is_owner=True, error=error)


def decline_connect_request_response(request: Request, username: str, owner_id: int, from_search: bool) -> HTMLResponse:
    other = _other_or_404(username)
    if isinstance(other, HTMLResponse):
        return other
    error = None
    try:
        connections.decline(owner_id, int(other["id"]))
    except connections.ConnectionError as exc:
        error = _connect_error_message(exc)
    if from_search:
        return _render_relationship_affordance(request, username, int(other["id"]), owner_id, error=error, from_search=True)
    return _render_fellows_section(request, owner_id, viewer_id=owner_id, is_owner=True, error=error)


def cancel_connect_request_response(
    request: Request, username: str, owner_id: int, from_search: bool, from_relationship: bool
) -> HTMLResponse:
    other = _other_or_404(username)
    if isinstance(other, HTMLResponse):
        return other
    connections.cancel(owner_id, int(other["id"]))
    if from_search:
        return _render_relationship_affordance(request, username, int(other["id"]), owner_id, from_search=True)
    if from_relationship:
        return _render_relationship_affordance(request, username, int(other["id"]), owner_id, from_search=False)
    return _render_fellows_section(request, owner_id, viewer_id=owner_id, is_owner=True)
