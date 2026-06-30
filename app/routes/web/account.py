"""Visibility consent, account settings, and the theme toggle.

Covers the one-time visibility-consent screen (``/welcome-sharing``), the
private-redefinition re-consent interstitial (``/visibility-update``), the
``/account`` settings page, and the no-auth ``/preferences/theme`` toggle.
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
    _home_url_for,
    _set_flash,
    _theme_from_cookie,
    templates,
    ui_strings as strings,
)

router = APIRouter()


# ---------------------------------------------------------------------------
# Visibility consent (one-time, before first /home use)
# ---------------------------------------------------------------------------


@router.get("/welcome-sharing", response_class=HTMLResponse)
async def welcome_sharing(
    request: Request,
    session: Annotated[str | None, Cookie(alias=sessions.COOKIE_NAME)] = None,
) -> HTMLResponse:
    """The one-time visibility-consent screen.

    Shown once to every non-guest account before they can use ``/home``: it
    explains the new ``visibility`` setting plainly and lets them choose
    ``public`` or ``private`` (private pre-selected). Once chosen, the gate in
    ``home()`` never sends them here again. Guests have no public profile and
    are bounced straight to ``/home``.
    """
    user = _current_user(session)
    if user is None:
        return RedirectResponse(url="/", status_code=303)
    if user["auth_provider"] == "guest" or user["consent_seen_at"] is not None:
        return RedirectResponse(url=_home_url_for(user), status_code=303)
    return templates.TemplateResponse(
        request=request,
        name="web/welcome_sharing.html.jinja2",
        context={"current_page": "home"},
    )


@router.post("/welcome-sharing", response_model=None)
async def submit_welcome_sharing(
    visibility: Annotated[str, Form()],
    session: Annotated[str | None, Cookie(alias=sessions.COOKIE_NAME)] = None,
) -> RedirectResponse | HTMLResponse:
    """Persist the user's one-time visibility choice, then go to ``/home``.

    Validates *visibility* is ``'public'`` or ``'private'`` (400 otherwise),
    writes ``user.visibility`` + ``user.consent_seen_at`` for the session user,
    and redirects to ``/home`` (which now passes the consent gate).
    """
    user = _current_user(session)
    if user is None:
        return RedirectResponse(url="/", status_code=303)
    if visibility not in users.VALID_VISIBILITIES:
        return HTMLResponse(status_code=400)
    users.set_visibility_consent(int(user["id"]), visibility)
    return RedirectResponse(url=_home_url_for(user), status_code=303)


# ---------------------------------------------------------------------------
# Private redefinition (one-time re-consent interstitial)
# ---------------------------------------------------------------------------


@router.get("/visibility-update", response_class=HTMLResponse, response_model=None)
async def visibility_update(
    request: Request,
    session: Annotated[str | None, Cookie(alias=sessions.COOKIE_NAME)] = None,
) -> HTMLResponse | RedirectResponse:
    """The one-time "what Private means has changed" interstitial.

    Shown once to a pre-existing private account whose meaning of ``private``
    changed under them. Self-guards the same way ``welcome_sharing`` does: a
    guest, a still-unconsented account (gate 1 owns them), a public account, or
    an account that has already acknowledged the change is bounced straight
    home — so a direct visit can't show the screen out of turn.
    """
    user = _current_user(session)
    if user is None:
        return RedirectResponse(url="/", status_code=303)
    if (
        user["auth_provider"] == "guest"
        or user["consent_seen_at"] is None
        or user["visibility"] != "private"
        or user["private_redefinition_seen_at"] is not None
    ):
        return RedirectResponse(url=_home_url_for(user), status_code=303)
    return templates.TemplateResponse(
        request=request,
        name="web/visibility_update.html.jinja2",
        context={"current_page": "home"},
    )


@router.post("/visibility-update", response_model=None)
async def submit_visibility_update(
    session: Annotated[str | None, Cookie(alias=sessions.COOKIE_NAME)] = None,
) -> RedirectResponse:
    """Acknowledge the private-redefinition interstitial, then go to ``/home``.

    Stamps ``private_redefinition_seen_at`` for the session user via
    ``users.mark_redefinition_seen`` so the re-consent gate never fires again,
    then redirects to the owner's home/profile URL. No body to validate — this
    is a single affirmative acknowledgement, not a re-choice.
    """
    user = _current_user(session)
    if user is None:
        return RedirectResponse(url="/", status_code=303)
    users.mark_redefinition_seen(int(user["id"]))
    return RedirectResponse(url=_home_url_for(user), status_code=303)


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


@router.post("/account/visibility", response_model=None)
async def update_visibility(
    visibility: Annotated[str, Form()],
    session: Annotated[str | None, Cookie(alias=sessions.COOKIE_NAME)] = None,
) -> RedirectResponse | HTMLResponse:
    """Change the current account's ``visibility`` from the settings page.

    Validates *visibility* against ``users.VALID_VISIBILITIES`` (400 otherwise),
    persists via ``users.set_visibility_consent`` (re-stamping ``consent_seen_at``
    is idempotent — the user already passed the one-time screen), and redirects
    to the owner's home/profile URL (``_home_url_for``) — matching the two
    sibling consent-write handlers (``submit_welcome_sharing``,
    ``submit_visibility_update``) rather than bouncing back to ``/account``.
    A one-shot flash cookie carries the confirmation message to that next
    render. Guests have no public profile and cannot toggle.
    """
    user = _current_user(session)
    if user is None:
        return RedirectResponse(url="/", status_code=303)
    if user["auth_provider"] == "guest":
        return HTMLResponse(status_code=400)
    if visibility not in users.VALID_VISIBILITIES:
        return HTMLResponse(status_code=400)
    users.set_visibility_consent(int(user["id"]), visibility)
    response = RedirectResponse(url=_home_url_for(user), status_code=303)
    _set_flash(response, f"visibility_{visibility}")
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
