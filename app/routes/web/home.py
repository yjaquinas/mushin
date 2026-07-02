"""Entry screen, login, and the character-sheet home.

Thin handlers only — business logic lives in app/services/. Full pages render
on initial navigation; fragments swap on interaction (detect via the
HX-Request header).
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Cookie, Request
from fastapi.responses import HTMLResponse, RedirectResponse

from app.auth import sessions
from app.routes.web._home_handlers import (
    home_gate_response,
    login_page_response,
    redirect_logged_in_home,
    render_entry_page,
    render_home,
)
from app.routes.web._shared import _current_user, templates
from app.services import profiles

router = APIRouter()


@router.get("/privacy", response_class=HTMLResponse)
async def privacy(request: Request) -> HTMLResponse:
    """The privacy policy page. Reachable logged-out."""
    return templates.TemplateResponse(
        request=request,
        name="web/privacy.html.jinja2",
        context={"current_page": None},
    )


@router.get("/terms", response_class=HTMLResponse)
async def terms(request: Request) -> HTMLResponse:
    """The terms page. Reachable logged-out."""
    return templates.TemplateResponse(
        request=request,
        name="web/terms.html.jinja2",
        context={"current_page": None},
    )


@router.get("/", response_class=HTMLResponse, response_model=None)
async def index(
    request: Request,
    next: str | None = None,  # noqa: A002 - query-param name is part of the public URL contract
    session: Annotated[str | None, Cookie(alias=sessions.COOKIE_NAME)] = None,
) -> HTMLResponse | RedirectResponse:
    """Entry screen for logged-out visitors, redirect for known users.

    ``?next=`` is accepted here too because anonymous public-page affordances
    return visitors to the entry screen at ``/`` rather than relying on a
    dedicated ``/login`` route.
    """
    user = _current_user(session)
    safe_next = profiles.safe_next_path(next)
    if user is None:
        return render_entry_page(request, next_path=safe_next)
    if safe_next:
        return RedirectResponse(url=safe_next, status_code=303)
    return redirect_logged_in_home(user)


@router.get("/login", response_class=HTMLResponse, response_model=None)
async def login(
    request: Request,
    next: str | None = None,  # noqa: A002 - query-param name is part of the public URL contract
    session: Annotated[str | None, Cookie(alias=sessions.COOKIE_NAME)] = None,
) -> HTMLResponse | RedirectResponse:
    """Dedicated login entry point that preserves a post-login redirect target.

    ``?next=`` is the page the visitor was trying to act on (e.g. an
    anonymous comment attempt on a public activity) — validated via
    ``profiles.safe_next_path`` so an attacker-supplied value can never become
    an open redirect; an unsafe or missing value silently falls back to no
    redirect target rather than erroring. A caller already logged in is sent
    straight to the (validated) target, or their home/profile if there is
    none — there's nothing to log into here.
    """
    user = _current_user(session)
    return login_page_response(request, user, next)


@router.get("/auth/login-form", response_class=HTMLResponse)
async def login_form(request: Request) -> HTMLResponse:
    """The Log in tab's fragment — swapped into ``#auth-form`` by the entry-screen toggle.

    Renders standalone (re-asserts the toggle with "Log in" selected) so a
    direct fragment load isn't visually orphaned.
    """
    return templates.TemplateResponse(
        request=request,
        name="components/auth_login_form.html.jinja2",
        context={"active": "login"},
    )


@router.get("/auth/create-form", response_class=HTMLResponse)
async def create_form(request: Request) -> HTMLResponse:
    """The Create account tab's fragment — swapped into ``#auth-form`` by the entry-screen toggle.

    Renders standalone (re-asserts the toggle with "Create account" selected)
    so a direct fragment load isn't visually orphaned.
    """
    return templates.TemplateResponse(
        request=request,
        name="components/auth_create_form.html.jinja2",
        context={"active": "create"},
    )


@router.get("/home", response_class=HTMLResponse)
async def home(
    request: Request,
    session: Annotated[str | None, Cookie(alias=sessions.COOKIE_NAME)] = None,
) -> HTMLResponse:
    """The character-sheet home. Redirects to the entry screen with no session.

    Renders in place for everyone (guest or real user) once past the
    one-time visibility-consent gate for non-guest accounts.
    """
    user = _current_user(session)
    gate = home_gate_response(user)
    if gate is not None:
        return gate
    return await render_home(request, user)
