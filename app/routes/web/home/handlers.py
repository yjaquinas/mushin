"""Handler helpers for entry, login, and profile page routes."""

from __future__ import annotations

import os

from fastapi import Request
from fastapi.responses import HTMLResponse, RedirectResponse

from app.auth import users
from app.models import db
from app.routes.web.home.contexts import _build_home_context
from app.routes.web.common import (
    _clear_flash,
    _home_url_for,
    _read_flash,
    consent_gate_redirect,
    templates,
)
from app.services.search.discovery import recent_public_entries
from app.services.social import profiles
from app.ui_strings import (
    META_DESCRIPTION_INDEX,
    META_TITLE_INDEX,
)


async def render_home(request: Request, user: dict) -> HTMLResponse:
    """Render the signed-in profile page for the current user."""
    owner_id = int(user["id"])
    tz = users.get_user_timezone(owner_id)
    with db.connect() as conn:
        conn.execute("BEGIN")
        context = _build_home_context(conn, owner_id, tz)
    context["flash_message"] = _read_flash(request)
    context["current_page"] = "profile"
    context["page_title"] = None
    context["username"] = user.get("username")
    context["meta_robots"] = "noindex, nofollow"
    response = templates.TemplateResponse(
        request=request,
        name="web/home/profile.html.jinja2",
        context=context,
    )
    _clear_flash(response)
    return response


def render_entry_page(request: Request, *, next_path: str | None = None) -> HTMLResponse:
    """Render the logged-out entry page with the login tab selected."""
    entries = recent_public_entries(limit=10)
    context = {
        "active": "login",
        "demo_username": os.getenv("DEMO_PROFILE_USERNAME", ""),
        "next": next_path,
        "current_page": None,
        "feed_entries": entries,
        "flash_message": _read_flash(request),
        "meta_description": META_DESCRIPTION_INDEX,
        "og_title": META_TITLE_INDEX,
        "og_description": META_DESCRIPTION_INDEX,
        "twitter_card_type": "summary_large_image",
    }
    response = templates.TemplateResponse(
        request=request,
        name="web/home/entry.html.jinja2",
        context=context,
    )
    _clear_flash(response)
    return response


def redirect_logged_in_home(user: dict) -> RedirectResponse:
    """Redirect a signed-in user to their canonical home URL."""
    return RedirectResponse(url=_home_url_for(user), status_code=303)


def login_page_response(
    request: Request,
    user: dict | None,
    next_path: str | None,
) -> HTMLResponse | RedirectResponse:
    """Render or redirect for the dedicated login entry point."""
    safe_next = profiles.safe_next_path(next_path)
    if user is not None:
        return RedirectResponse(url=safe_next or _home_url_for(user), status_code=303)
    return render_entry_page(request, next_path=safe_next)


def home_gate_response(user: dict | None) -> RedirectResponse | None:
    """Return the required redirect before rendering /home, if any."""
    if user is None:
        return RedirectResponse(url="/", status_code=303)
    return consent_gate_redirect(user)
