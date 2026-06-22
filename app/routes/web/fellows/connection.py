"""Fellows: send/accept/decline/cancel a connection request.

All action routes here are session-authenticated and operate on the
session user as one side of the pair; the other side is resolved from the
``{username}`` path segment via ``users.find_by_username`` — never a raw id
from the client. Every route returns an HTMX fragment (never a full
reload) and catches the ``connections`` service exceptions into a calm
inline message (never a bare 500). Sending a request and accepting one
each require a GET-then-POST consent step (the ``SHARING_CONSENT_*``
consequence screen) before the mutation fires; decline/cancel are direct.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Cookie, Query, Request
from fastapi.responses import HTMLResponse

from app import ui_strings
from app.auth import sessions
from app.routes.web._shared import _current_user, templates
from app.routes.web.fellows._shared import (
    _connect_error_message,
    _relationship_dom_id,
    _render_fellows_section,
    _render_relationship_affordance,
    _resolve_other_user,
)
from app.services import connections

router = APIRouter()


# --- Send request (Connect) — consent-gated -------------------------------


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
    other = _resolve_other_user(username)
    if other is None:
        return HTMLResponse(status_code=404)

    from_search = source == "search"
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
    other = _resolve_other_user(username)
    if other is None:
        return HTMLResponse(status_code=404)
    return _render_relationship_affordance(
        request, username, int(other["id"]), int(user["id"]), from_search=source == "search"
    )


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
    other = _resolve_other_user(username)
    if other is None:
        return HTMLResponse(status_code=404)
    other_id = int(other["id"])
    viewer_id = int(user["id"])

    error: str | None = None
    try:
        connections.send_request(viewer_id, other_id)
    except connections.SelfConnectionError:
        return HTMLResponse(status_code=400)
    except connections.ConnectionError as exc:
        error = _connect_error_message(exc)

    return _render_relationship_affordance(
        request, username, other_id, viewer_id, error=error, from_search=source == "search"
    )


# --- Accept / decline / cancel (incoming + outgoing requests) -------------


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
    other = _resolve_other_user(username)
    if other is None:
        return HTMLResponse(status_code=404)

    from_search = source == "search"
    if from_search:
        # No page-singleton #fellows-section on the search page — swap this
        # row's own relationship-affordance instead (see
        # _relationship_dom_id / accept_connect_request below).
        confirm_url = f"/fellows/requests/{username}/accept?source=search"
        cancel_url = f"/fellows/{username}/connect-cancel?source=search"
    else:
        confirm_url = f"/fellows/requests/{username}/accept"
        cancel_url = "/fellows/requests-cancel"

    action = "accept" if not from_search else "connect"
    if action == "accept":
        body = ui_strings.SHARING_CONSENT_BODY_ACCEPT
        confirm_label = ui_strings.SHARING_CONSENT_CONFIRM_ACCEPT
    else:
        body = ui_strings.SHARING_CONSENT_BODY_SEND
        confirm_label = ui_strings.SHARING_CONSENT_CONFIRM

    return templates.TemplateResponse(
        request=request,
        name="components/sharing_consent_confirm.html.jinja2",
        context={
            "username": username,
            "action": action,
            "confirm_url": confirm_url,
            "cancel_url": cancel_url,
            "dom_id": _relationship_dom_id(username, from_search=from_search),
            "body": body,
            "confirm_label": confirm_label,
        },
    )


@router.get("/fellows/requests-cancel", response_class=HTMLResponse)
async def requests_cancel(
    request: Request,
    session: Annotated[str | None, Cookie(alias=sessions.COOKIE_NAME)] = None,
) -> HTMLResponse:
    """Cancel out of the accept consent step back to the requests cluster."""
    user = _current_user(session)
    if user is None:
        return HTMLResponse(status_code=401)
    owner_id = int(user["id"])
    return _render_fellows_section(request, owner_id, viewer_id=owner_id, is_owner=True)


@router.post("/fellows/requests/{username}/accept", response_class=HTMLResponse)
async def accept_connect_request(
    request: Request,
    username: str,
    source: Annotated[str | None, Query()] = None,
    session: Annotated[str | None, Cookie(alias=sessions.COOKIE_NAME)] = None,
) -> HTMLResponse:
    """Confirm step: accept *username*'s pending incoming request.

    From search (``?source=search``) there's no page-level fellows section to
    refresh, so the response is this one row's relationship-affordance
    fragment (now "fellow") instead of the owner's whole fellows section.
    """
    user = _current_user(session)
    if user is None:
        return HTMLResponse(status_code=401)
    other = _resolve_other_user(username)
    if other is None:
        return HTMLResponse(status_code=404)
    owner_id = int(user["id"])

    error: str | None = None
    try:
        connections.accept(owner_id, int(other["id"]))
    except connections.ConnectionError as exc:
        error = _connect_error_message(exc)

    if source == "search":
        return _render_relationship_affordance(
            request, username, int(other["id"]), owner_id, error=error, from_search=True
        )

    return _render_fellows_section(
        request, owner_id, viewer_id=owner_id, is_owner=True, error=error
    )


@router.post("/fellows/requests/{username}/decline", response_class=HTMLResponse)
async def decline_connect_request(
    request: Request,
    username: str,
    source: Annotated[str | None, Query()] = None,
    session: Annotated[str | None, Cookie(alias=sessions.COOKIE_NAME)] = None,
) -> HTMLResponse:
    """Decline *username*'s pending incoming request — direct, no confirm step.

    From search (``?source=search``), returns this row's relationship-
    affordance fragment (now "none") instead of the owner's fellows section.
    """
    user = _current_user(session)
    if user is None:
        return HTMLResponse(status_code=401)
    other = _resolve_other_user(username)
    if other is None:
        return HTMLResponse(status_code=404)
    owner_id = int(user["id"])

    error: str | None = None
    try:
        connections.decline(owner_id, int(other["id"]))
    except connections.ConnectionError as exc:
        error = _connect_error_message(exc)

    if source == "search":
        return _render_relationship_affordance(
            request, username, int(other["id"]), owner_id, error=error, from_search=True
        )

    return _render_fellows_section(
        request, owner_id, viewer_id=owner_id, is_owner=True, error=error
    )


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
    other = _resolve_other_user(username)
    if other is None:
        return HTMLResponse(status_code=404)
    owner_id = int(user["id"])

    connections.cancel(owner_id, int(other["id"]))

    return _render_fellows_section(request, owner_id, viewer_id=owner_id, is_owner=True)
