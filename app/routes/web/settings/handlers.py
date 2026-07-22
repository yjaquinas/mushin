"""Handler helpers for settings and theme preferences."""

from __future__ import annotations

import re

from fastapi import Request
from fastapi.responses import HTMLResponse, RedirectResponse

from app.auth import passwords, sessions, users
from app.models import db
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
from app.services.plans import (
    get_all_plan_configs,
    get_subscription_end_date,
    get_user_payments,
    get_user_plan_config,
)

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
    owner_id = int(user["id"])
    with db.connect() as conn:
        user_plan = get_user_plan_config(conn, owner_id) or {}
        activity_count = conn.execute(
            "SELECT COUNT(*) FROM activity WHERE owner_id = ? AND archived_at IS NULL",
            (owner_id,),
        ).fetchone()[0]
        payments = get_user_payments(conn, owner_id)
        subscription_end = get_subscription_end_date(conn, owner_id)
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
            "search_discovery": bool(user.get("search_discovery")),
            "current_page": "settings",
            "page_title": strings.SETTINGS_TITLE,
            "meta_robots": "noindex, nofollow",
            "user_plan": user_plan,
            "activity_count": activity_count,
            "payments": payments,
            "subscription_end": subscription_end,
        },
    )
    _clear_flash(response)
    return response


def settings_plans_page(request: Request, user: dict) -> HTMLResponse:
    """Render the plans comparison page inside the settings tab."""
    with db.connect() as conn:
        plans = get_all_plan_configs(conn)
        current_user_plan = user.get("plan", "basic")
    basic = next((p for p in plans if p["plan"] == "basic"), None)
    premium = next((p for p in plans if p["plan"] == "premium"), None)
    return templates.TemplateResponse(
        request=request,
        name="web/settings/plans.html.jinja2",
        context={
            "current_page": "settings",
            "meta_robots": "noindex, nofollow",
            "page_title": "Plans",
            "basic": basic,
            "premium": premium,
            "current_user_plan": current_user_plan,
            "user": user,
        },
    )


def _email_flash_key(user: dict, email: str | None) -> str | None:
    """Return ``"email_updated"`` if *email* differs from the stored value, else ``None``."""
    return "email_updated" if email != user.get("email") else None


def update_settings_response(
    request: Request,
    user: dict,
    visibility: str | None = None,
    search_discovery: bool | None = None,
    email: str | None = None,
) -> RedirectResponse | HTMLResponse:
    """Persist visibility and/or email, then redirect back to settings.

    Only fields that differ from the stored value are persisted. On email
    validation failure the settings page is re-rendered with an inline error.
    """
    flash_key: str | None = None

    if visibility is not None:
        if visibility not in users.VALID_VISIBILITIES:
            return HTMLResponse(status_code=400)
        if visibility != user["visibility"]:
            users.set_visibility_consent(int(user["id"]), visibility)
            flash_key = "visibility_public" if visibility == "public" else "visibility_private"

    if search_discovery is not None and search_discovery != bool(user.get("search_discovery")):
        users.set_search_discovery(int(user["id"]), search_discovery)

    if email is not None:
        email = email.strip() or None
        key = _email_flash_key(user, email)
        if key is not None:
            if email is not None and not _EMAIL_RE.match(email):
                return render_account_settings(request, user, email_error=strings.ACCOUNT_EMAIL_INVALID, email_value=email)
            try:
                users.set_email(int(user["id"]), email)
            except Exception:
                return render_account_settings(request, user, email_error=strings.EMAIL_UPDATE_FAILED, email_value=email)
            flash_key = flash_key or key

    response = RedirectResponse(url="/settings", status_code=303)
    if flash_key:
        _set_flash(response, flash_key)
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
