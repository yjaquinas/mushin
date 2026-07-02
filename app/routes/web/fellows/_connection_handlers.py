"""Handler bodies for fellows request and acceptance flows."""

from __future__ import annotations

from fastapi import Request
from fastapi.responses import HTMLResponse

from app import ui_strings
from app.routes.web._shared import templates
from app.routes.web.fellows._shared import (
    _connect_error_message,
    _relationship_dom_id,
    _render_fellows_section,
    _render_relationship_affordance,
    _resolve_other_user,
)
from app.services import connections


def _other_or_404(username: str) -> dict | HTMLResponse:
    other = _resolve_other_user(username)
    return other if other is not None else HTMLResponse(status_code=404)


def connect_confirm_response(request: Request, username: str, from_search: bool) -> HTMLResponse:
    other = _other_or_404(username)
    if isinstance(other, HTMLResponse):
        return other
    suffix = "?source=search" if from_search else ""
    return templates.TemplateResponse(
        request=request,
        name="components/sharing_consent_confirm.html.jinja2",
        context={
            "username": username,
            "action": "connect",
            "confirm_url": f"/fellows/{username}/connect{suffix}",
            "cancel_url": f"/fellows/{username}/connect-cancel{suffix}",
            "dom_id": _relationship_dom_id(username, from_search=from_search),
            "body": ui_strings.SHARING_CONSENT_BODY_SEND,
            "confirm_label": ui_strings.SHARING_CONSENT_CONFIRM,
        },
    )


def connect_cancel_response(request: Request, username: str, viewer_id: int, from_search: bool) -> HTMLResponse:
    other = _other_or_404(username)
    if isinstance(other, HTMLResponse):
        return other
    return _render_relationship_affordance(request, username, int(other["id"]), viewer_id, from_search=from_search)


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


def accept_confirm_response(request: Request, username: str, from_search: bool) -> HTMLResponse:
    other = _other_or_404(username)
    if isinstance(other, HTMLResponse):
        return other
    action = "connect" if from_search else "accept"
    return templates.TemplateResponse(
        request=request,
        name="components/sharing_consent_confirm.html.jinja2",
        context={
            "username": username,
            "action": action,
            "confirm_url": f"/fellows/requests/{username}/accept" + ("?source=search" if from_search else ""),
            "cancel_url": f"/fellows/{username}/connect-cancel?source=search" if from_search else "/fellows/requests-cancel",
            "dom_id": _relationship_dom_id(username, from_search=from_search),
            "body": ui_strings.SHARING_CONSENT_BODY_SEND if from_search else ui_strings.SHARING_CONSENT_BODY_ACCEPT,
            "confirm_label": ui_strings.SHARING_CONSENT_CONFIRM if from_search else ui_strings.SHARING_CONSENT_CONFIRM_ACCEPT,
        },
    )


def requests_cancel_response(request: Request, owner_id: int) -> HTMLResponse:
    return _render_fellows_section(request, owner_id, viewer_id=owner_id, is_owner=True)


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


def cancel_connect_request_response(request: Request, username: str, owner_id: int) -> HTMLResponse:
    other = _other_or_404(username)
    if isinstance(other, HTMLResponse):
        return other
    connections.cancel(owner_id, int(other["id"]))
    return _render_fellows_section(request, owner_id, viewer_id=owner_id, is_owner=True)

