"""Shared render helpers for the ``fellows`` route group."""

from __future__ import annotations

from typing import Any

from fastapi import Request
from fastapi.responses import HTMLResponse

from app import ui_strings
from app.auth import users
from app.routes.web._contexts import _build_fellows_context
from app.routes.web._shared import templates
from app.services import connections


def _connect_error_message(exc: connections.ConnectionError) -> str:
    """Map a connections-service exception to a calm, centralized inline message."""
    if isinstance(exc, connections.AlreadyExistsError):
        return ui_strings.CONNECT_ERROR_ALREADY_EXISTS
    if isinstance(exc, connections.BlockedError):
        return ui_strings.CONNECT_ERROR_BLOCKED
    if isinstance(exc, connections.RateLimitedError):
        return ui_strings.CONNECT_ERROR_RATE_LIMITED
    if isinstance(exc, connections.NotFoundError):
        return ui_strings.CONNECT_ERROR_NOT_FOUND
    return ui_strings.CONNECT_ERROR_GENERIC


def _render_fellows_section(
    request: Request,
    profile_user_id: int,
    *,
    viewer_id: int,
    is_owner: bool,
    error: str | None = None,
) -> HTMLResponse:
    """Re-render the ``fellows_section`` fragment for *profile_user_id*'s page."""
    fellows_context = _build_fellows_context(
        profile_user_id, viewer_id=viewer_id, is_owner=is_owner
    )
    return templates.TemplateResponse(
        request=request,
        name="components/fellows_section.html.jinja2",
        context={"fellows": fellows_context, "error": error},
    )


def _relationship_dom_id(username: str, *, from_search: bool) -> str:
    """The id a relationship-affordance fragment should render with."""
    if from_search:
        return f"relationship-affordance-{username}"
    return "relationship-affordance"


def _remove_dialog_dom_id(username: str, *, from_search: bool) -> str:
    """The id used for the remove-connection confirm dialog host."""
    if from_search:
        return f"connect-remove-dialog-{username}"
    return "connect-remove-dialog"


def _cancel_request_dialog_dom_id(username: str, *, from_search: bool) -> str:
    """The id used for the cancel-request confirm dialog host."""
    if from_search:
        return f"connect-cancel-dialog-{username}"
    return "connect-cancel-dialog"


def _render_relationship_affordance(
    request: Request,
    profile_username: str,
    profile_user_id: int,
    viewer_id: int,
    *,
    error: str | None = None,
    from_search: bool = False,
) -> HTMLResponse:
    """Re-render the relationship-state affordance fragment for a non-owner viewer."""
    state = connections.relationship_state(viewer_id, profile_user_id)
    dom_id = _relationship_dom_id(profile_username, from_search=from_search)
    return templates.TemplateResponse(
        request=request,
        name="components/relationship_affordance.html.jinja2",
        context={
            "username": profile_username,
            "state": state,
            "error": error,
            "dom_id": dom_id,
            "remove_dialog_id": _remove_dialog_dom_id(profile_username, from_search=from_search),
            "cancel_request_dialog_id": _cancel_request_dialog_dom_id(profile_username, from_search=from_search),
            "pending_incoming_target_id": dom_id,
            "from_search": from_search,
        },
    )


def _resolve_other_user(username: str) -> dict[str, Any] | None:
    """Resolve a path ``{username}`` segment to a user row, or ``None``."""
    other = users.find_by_username(username)
    if other is None:
        return None
    return other
