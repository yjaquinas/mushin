"""Handler helpers for account settings and theme preferences."""

from __future__ import annotations

import re

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
from app.services import profiles


_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def _normalize_email(email: str | None) -> str | None:
    if email is None:
        return None
    cleaned = email.strip().lower()
    if not cleaned:
        return None
    if not _EMAIL_RE.fullmatch(cleaned):
        raise ValueError(strings.ACCOUNT_EMAIL_INVALID)
    return cleaned


def render_account_settings(
    request: Request,
    user: dict,
    *,
    email_error: str | None = None,
    email_value: str | None = None,
) -> HTMLResponse:
    """Render the account settings page for the current user."""
    response = templates.TemplateResponse(
        request=request,
        name="web/account.html.jinja2",
        context={
            "flash_message": _read_flash(request),
            "is_guest": user["auth_provider"] == "guest",
            "username": user["username"],
            "email": email_value if email_value is not None else user["email"],
            "email_error": email_error,
            "profile_url": profiles.canonical_profile_url(user["username"]) if user["username"] else None,
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


def update_email_response(request: Request, user: dict, email: str | None) -> RedirectResponse | HTMLResponse:
    """Persist a new recovery email and redirect back to account."""
    if user["auth_provider"] == "guest":
        return HTMLResponse(status_code=400)
    try:
        normalized_email = _normalize_email(email)
        users.update_email(int(user["id"]), normalized_email)
    except ValueError as exc:
        return render_account_settings(request, user, email_error=str(exc), email_value=email)
    except users.EmailTakenError:
        return render_account_settings(
            request,
            user,
            email_error=strings.ACCOUNT_EMAIL_TAKEN,
            email_value=email,
        )
    response = RedirectResponse(url="/account", status_code=303)
    _set_flash(response, "email_updated")
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
