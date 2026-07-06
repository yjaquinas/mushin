"""Settings, delete, and the theme toggle.

Covers the ``/settings`` page, ``/delete``, and
the no-auth ``/preferences/theme`` toggle. The one-time consent interstitials
(``/welcome-sharing``, ``/visibility-update``) live in ``consent_routes.py``.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Cookie, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse

from app.auth import sessions
from app.routes.web.settings.handlers import (
    delete_account_response,
    render_account_settings,
    toggle_theme_response,
    update_email_response,
    update_password_response,
    update_visibility_response,
)
from app.routes.web.common import _current_user
from app.routes.web.common.flash import _set_flash

router = APIRouter()


@router.get("/settings", response_class=HTMLResponse, response_model=None)
async def settings_page(
    request: Request,
    session: Annotated[str | None, Cookie(alias=sessions.COOKIE_NAME)] = None,
) -> HTMLResponse | RedirectResponse:
    """Settings page.

    Shows the visibility toggle and the ``/@{username}`` share-link line for
    non-guest accounts; guests (no ``username``, no public profile) see neither
    — the section is suppressed entirely in the template.
    """
    user = _current_user(session)
    if user is None:
        response = RedirectResponse(url="/", status_code=303)
        _set_flash(response, "login_required")
        return response
    return render_account_settings(request, user)


@router.post("/settings", response_model=None)
async def update_visibility(
    request: Request,
    visibility: Annotated[str | None, Form()],
    session: Annotated[str | None, Cookie(alias=sessions.COOKIE_NAME)] = None,
) -> RedirectResponse | HTMLResponse:
    """Change the current account's ``visibility`` from the settings page.

    Validates *visibility* against ``users.VALID_VISIBILITIES`` (400 otherwise),
    persists via ``users.set_visibility_consent``, and re-renders the settings
    page with a flash confirmation — matching the user's expectation of staying
    on the settings page after saving. Guests have no public profile and cannot
    toggle.

    The form action is ``/settings`` (not ``/settings/visibility``) so the URL
    never changes after saving.
    """
    user = _current_user(session)
    if user is None:
        return HTMLResponse(status_code=401)
    return update_visibility_response(user, visibility)


@router.post("/settings/email", response_model=None)
async def update_email(
    request: Request,
    email: Annotated[str | None, Form()] = None,
    session: Annotated[str | None, Cookie(alias=sessions.COOKIE_NAME)] = None,
) -> RedirectResponse | HTMLResponse:
    """Change the current account's recovery email from the settings page."""
    user = _current_user(session)
    if user is None:
        return HTMLResponse(status_code=401)
    return update_email_response(request, user, email)


@router.post("/settings/password", response_model=None)
async def update_password(
    request: Request,
    current_password: Annotated[str | None, Form()] = None,
    new_password: Annotated[str | None, Form()] = None,
    session: Annotated[str | None, Cookie(alias=sessions.COOKIE_NAME)] = None,
) -> RedirectResponse | HTMLResponse:
    """Change the current account password from the settings page."""
    user = _current_user(session)
    if user is None:
        return HTMLResponse(status_code=401)
    return update_password_response(request, user, current_password, new_password)


@router.post("/delete", response_model=None)
async def delete_account(
    session: Annotated[str | None, Cookie(alias=sessions.COOKIE_NAME)] = None,
) -> RedirectResponse | HTMLResponse:
    """Delete account access while preserving history, then redirect to /."""
    user = _current_user(session)
    if user is None:
        return HTMLResponse(status_code=401)
    return delete_account_response(user)


@router.post("/preferences/theme", response_class=HTMLResponse)
async def toggle_theme(request: Request) -> HTMLResponse:
    """Toggle the theme (light <-> dark) and return the toggle fragment.

    No auth required — works for guests and signed-in users alike. The
    ``mushin_theme`` cookie is not ``HttpOnly`` so it stays readable if a
    future client-side enhancement needs it, but is otherwise set the same
    way as the app's other preference cookies.
    """
    return toggle_theme_response(request)
