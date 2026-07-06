"""Handler helpers for settings and theme preferences."""

from __future__ import annotations

import re

from fastapi import Request
from fastapi.responses import HTMLResponse, RedirectResponse

from app.auth import passwords, sessions, users
from app.routes.web.common import (
    THEME_COOKIE,
    THEME_CYCLE,
    _clear_flash,
    _read_flash,
    _set_flash,
    _theme_from_cookie,
    templates,
)
from app.routes.web.common import ui_strings as strings

_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def render_account_settings(
    request: Request,
    user: dict,
    *,
    email_error: str | None = None,
    email_value: str | None = None,
    password_error: str | None = None,
) -> HTMLResponse:
    """Render the settings page for the current user."""
    email = email_value if email_value is not None else user.get("email")
    response = templates.TemplateResponse(
        request=request,
        name="web/settings/settings.html.jinja2",
        context={
            "flash_message": _read_flash(request),
            "username": user["username"],
            "email": email,
            "email_error": email_error,
            "password_error": password_error,
            "visibility": user["visibility"],
            "current_page": "settings",
            "page_title": strings.SETTINGS_TITLE,
        },
    )
    _clear_flash(response)
    return response


def update_visibility_response(user: dict, visibility: str | None) -> RedirectResponse | HTMLResponse:
    """Persist a new visibility setting and redirect back to account."""
    if visibility not in users.VALID_VISIBILITIES:
        return HTMLResponse(status_code=400)
    users.set_visibility_consent(int(user["id"]), visibility)
    response = RedirectResponse(url="/settings", status_code=303)
    _set_flash(
        response,
        "visibility_public" if visibility == "public" else "visibility_private",
    )
    return response


def delete_account_response(user: dict) -> RedirectResponse | HTMLResponse:
    """Delete the current user and clear the session cookie."""
    users.delete_user(int(user["id"]))
    response = RedirectResponse(url="/", status_code=303)
    response.delete_cookie(key=sessions.COOKIE_NAME, path="/")
    return response


def toggle_theme_response(request: Request) -> HTMLResponse:
    """Toggle the theme cookie and return the refreshed toggle fragment."""
    current = _theme_from_cookie(request.cookies.get(THEME_COOKIE))
    next_theme = THEME_CYCLE[current]
    fragment = templates.get_template("components/common/theme_toggle_settings.html.jinja2").render(
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


def update_email_response(
    request: Request,
    user: dict,
    email: str | None,
) -> RedirectResponse | HTMLResponse:
    """Change the current account's recovery email and redirect back."""
    email = email.strip() if email else None
    if email is not None and not _EMAIL_RE.match(email):
        return render_account_settings(request, user, email_error=strings.ACCOUNT_EMAIL_INVALID, email_value=email)
    try:
        users.set_email(int(user["id"]), email)
    except Exception:
        return render_account_settings(request, user, email_error=strings.EMAIL_UPDATE_FAILED, email_value=email)
    response = RedirectResponse(url="/settings", status_code=303)
    _set_flash(response, "email_updated")
    return response


def update_password_response(
    request: Request,
    user: dict,
    current_password: str | None,
    new_password: str | None,
) -> RedirectResponse | HTMLResponse:
    current_password = current_password or ""
    new_password = new_password or ""

    if users.authenticate(str(user["username"]), current_password) is None:
        return render_account_settings(request, user, password_error=strings.ACCOUNT_PASSWORD_INVALID)
    if len(new_password) < 8:
        return render_account_settings(request, user, password_error=strings.ACCOUNT_PASSWORD_TOO_SHORT)
    if any(ch.isspace() for ch in new_password):
        return render_account_settings(request, user, password_error=strings.ACCOUNT_PASSWORD_WHITESPACE)
    if new_password == current_password:
        return render_account_settings(request, user, password_error=strings.ACCOUNT_PASSWORD_SAME)

    users.update_password(int(user["id"]), passwords.hash_password(new_password))
    response = RedirectResponse(url="/settings", status_code=303)
    _set_flash(response, "password_updated")
    return response
