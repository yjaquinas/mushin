"""One-time visibility-consent interstitials.

Covers the first-run consent screen (``/welcome-sharing``) and the
private-redefinition re-consent screen (``/visibility-update``). Both are
one-shot pages each non-guest account sees exactly once; after they clear
these gates, ``/account`` is the ongoing settings home.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Cookie, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse

from app.auth import sessions, users
from app.routes.web._shared import (
    _current_user,
    _home_url_for,
    templates,
)

router = APIRouter()


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
