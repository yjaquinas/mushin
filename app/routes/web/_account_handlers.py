"""Handler helpers for account settings and theme preferences."""

from __future__ import annotations

from fastapi import Request
from fastapi.responses import HTMLResponse, RedirectResponse

from app.auth import sessions, users
from app.routes.web._shared import (
    THEME_COOKIE,
    THEME_CYCLE,
    _clear_flash,
    _read_flash,
    _set_flash,
    _theme_from_cookie,
    templates,
)
from app.routes.web._shared import ui_strings as strings


def render_account_settings(request: Request, user: dict) -> HTMLResponse:
    """Render the account settings page for the current user."""
    response = templates.TemplateResponse(
        request=request,
        name="web/account.html.jinja2",
        context={
            "flash_message": _read_flash(request),
            "is_guest": user["auth_provider"] == "guest",
            "username": user["username"],
            "visibility": user["visibility"],
            "current_page": "account",
            "page_title": strings.ACCOUNT_TITLE,
            "show_back": False,
        },
    )
    _clear_flash(response)
    return response


def update_visibility_response(user: dict, visibility: str | None) -> RedirectResponse | HTMLResponse:
    """Persist a new visibility setting and redirect back to account."""
    if user["auth_provider"] == "guest":
        return HTMLResponse(status_code=400)
    if visibility not in users.VALID_VISIBILITIES:
        return HTMLResponse(status_code=400)
    users.set_visibility_consent(int(user["id"]), visibility)
    response = RedirectResponse(url="/account", status_code=303)
    _set_flash(
        response,
        "visibility_public" if visibility == "public" else "visibility_private",
    )
    return response


def delete_account_response(user: dict) -> RedirectResponse | HTMLResponse:
    """Delete the current non-guest user and clear the session cookie."""
    if user["auth_provider"] == "guest":
        return HTMLResponse(status_code=400)
    users.delete_user(int(user["id"]))
    response = RedirectResponse(url="/", status_code=303)
    response.delete_cookie(key=sessions.COOKIE_NAME, path="/")
    return response


def toggle_theme_response(request: Request) -> HTMLResponse:
    """Toggle the theme cookie and return the refreshed toggle fragment."""
    current = _theme_from_cookie(request.cookies.get(THEME_COOKIE))
    next_theme = THEME_CYCLE[current]
    fragment = templates.get_template("components/theme_toggle_account.html.jinja2").render(
        request=request, theme=next_theme
    )
    response = HTMLResponse(content=fragment)
    response.headers["HX-Refresh"] = "true"
    response.set_cookie(
        key=THEME_COOKIE,
        value=next_theme,
        max_age=60 * 60 * 24 * 365,
        secure=True,
        samesite="lax",
        path="/",
    )
    return response
