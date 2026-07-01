"""Account settings, delete, and the theme toggle.

Covers the ``/account`` settings page, ``/delete``, and
the no-auth ``/preferences/theme`` toggle. The one-time consent interstitials
(``/welcome-sharing``, ``/visibility-update``) live in ``account_consent.py``.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Cookie, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse

from app.auth import sessions, users
from app.routes.web._shared import (
    THEME_COOKIE,
    THEME_CYCLE,
    _current_user,
    _theme_from_cookie,
    templates,
    ui_strings as strings,
)

router = APIRouter()


# ---------------------------------------------------------------------------
# Account settings (/account) — visibility toggle
# ---------------------------------------------------------------------------


@router.get("/account", response_class=HTMLResponse, response_model=None)
async def account_settings(
    request: Request,
    session: Annotated[str | None, Cookie(alias=sessions.COOKIE_NAME)] = None,
) -> HTMLResponse | RedirectResponse:
    """Account settings page.

    Shows the visibility toggle and the ``/@{username}`` share-link line for
    non-guest accounts; guests (no ``username``, no public profile) see neither
    — the section is suppressed entirely in the template.
    """
    user = _current_user(session)
    if user is None:
        return RedirectResponse(url="/", status_code=303)
    is_guest = user["auth_provider"] == "guest"
    return templates.TemplateResponse(
        request=request,
        name="web/account.html.jinja2",
        context={
            "is_guest": is_guest,
            "username": user["username"],
            "visibility": user["visibility"],
            "current_page": "account",
            "page_title": strings.ACCOUNT_TITLE,
            "show_back": False,
        },
    )


@router.post("/account", response_model=None)
async def update_visibility(
    request: Request,
    visibility: Annotated[str | None, Form()],
    session: Annotated[str | None, Cookie(alias=sessions.COOKIE_NAME)] = None,
) -> HTMLResponse:
    """Change the current account's ``visibility`` from the settings page.

    Validates *visibility* against ``users.VALID_VISIBILITIES`` (400 otherwise),
    persists via ``users.set_visibility_consent``, and re-renders the account
    page with a flash confirmation — matching the user's expectation of staying
    on the settings page after saving. Guests have no public profile and cannot
    toggle.

    The form action is ``/account`` (not ``/account/visibility``) so the URL
    never changes after saving.
    """
    user = _current_user(session)
    if user is None:
        return HTMLResponse(status_code=401)
    if user["auth_provider"] == "guest":
        return HTMLResponse(status_code=400)
    if visibility not in users.VALID_VISIBILITIES:
        return HTMLResponse(status_code=400)
    users.set_visibility_consent(int(user["id"]), visibility)
    return templates.TemplateResponse(
        request=request,
        name="web/account.html.jinja2",
        context={
            "is_guest": False,
            "username": user["username"],
            "visibility": visibility,
            "current_page": "account",
            "page_title": strings.ACCOUNT_TITLE,
            "show_back": False,
            "flash_message": (
                strings.HOME_FLASH_VISIBILITY_PUBLIC
                if visibility == "public"
                else strings.HOME_FLASH_VISIBILITY_PRIVATE
            ),
        },
    )


@router.post("/delete", response_model=None)
async def delete_account(
    session: Annotated[str | None, Cookie(alias=sessions.COOKIE_NAME)] = None,
) -> HTMLResponse:
    """Delete the current account and all its data, then redirect to /.

    ON DELETE CASCADE in the schema wipes every owned row (activities,
    entries, tags, etc.) in a single DELETE FROM user. The session cookie
    is cleared so the browser is fully logged out before the redirect.
    Guests cannot delete — they have no persistent data to remove.
    """
    user = _current_user(session)
    if user is None:
        return HTMLResponse(status_code=401)
    if user["auth_provider"] == "guest":
        return HTMLResponse(status_code=400)
    users.delete_user(int(user["id"]))
    response = HTMLResponse(content="")
    response.delete_cookie(key=sessions.COOKIE_NAME, path="/")
    return response


# ---------------------------------------------------------------------------
# Theme toggle
# ---------------------------------------------------------------------------


@router.post("/preferences/theme", response_class=HTMLResponse)
async def toggle_theme(request: Request) -> HTMLResponse:
    """Toggle the theme (light <-> dark) and return the toggle fragment.

    No auth required — works for guests and signed-in users alike. The
    ``mushin_theme`` cookie is not ``HttpOnly`` so it stays readable if a
    future client-side enhancement needs it, but is otherwise set the same
    way as the app's other preference cookies.
    """
    current = _theme_from_cookie(request.cookies.get(THEME_COOKIE))
    next_theme = THEME_CYCLE[current]

    # Render directly rather than via templates.TemplateResponse: the
    # _theme_context context processor would overwrite "theme" with the
    # (stale) request-cookie value before the new cookie is set on the
    # response.
    fragment = templates.get_template("components/theme_toggle_account.html.jinja2").render(
        request=request, theme=next_theme
    )
    response = HTMLResponse(content=fragment)
    response.set_cookie(
        key=THEME_COOKIE,
        value=next_theme,
        max_age=60 * 60 * 24 * 365,
        secure=True,
        samesite="lax",
        path="/",
    )
    return response
