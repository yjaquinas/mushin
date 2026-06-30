"""Entry screen, login, and the character-sheet home.

Thin handlers only — business logic lives in app/services/. Full pages render
on initial navigation; fragments swap on interaction (detect via the
HX-Request header). See .claude/rules/web-templates.md for conventions.
"""

from __future__ import annotations

import os
from typing import Annotated

from fastapi import APIRouter, Cookie, Request
from fastapi.responses import HTMLResponse, RedirectResponse

from app.auth import sessions, users
from app.models import db
from app.routes.web._contexts import _build_home_context
from app.routes.web._shared import (
    _clear_flash,
    _current_user,
    _home_url_for,
    _read_flash,
    consent_gate_redirect,
    templates,
)
from app.services import profiles

router = APIRouter()


async def _render_home(request: Request, user: dict) -> HTMLResponse:
    owner_id = int(user["id"])
    tz = users.get_user_timezone(owner_id)
    with db.connect() as conn:
        conn.execute("BEGIN")
        context = _build_home_context(conn, owner_id, tz)
    context["flash_message"] = _read_flash(request)
    context["current_page"] = "home"
    context["page_title"] = None
    context["show_back"] = False

    response = templates.TemplateResponse(
        request=request,
        name="web/home.html.jinja2",
        context=context,
    )
    _clear_flash(response)
    return response


@router.get("/privacy", response_class=HTMLResponse)
async def privacy(request: Request) -> HTMLResponse:
    """The privacy policy page. Reachable logged-out."""
    return templates.TemplateResponse(
        request=request,
        name="web/privacy.html.jinja2",
        context={"current_page": None},
    )


@router.get("/", response_class=HTMLResponse)
async def index(
    request: Request,
    session: Annotated[str | None, Cookie(alias=sessions.COOKIE_NAME)] = None,
) -> HTMLResponse:
    """First-run entry screen, or the character-sheet home for a known session."""
    user = _current_user(session)
    if user is None:
        demo_username = os.getenv("DEMO_PROFILE_USERNAME", "")
        return templates.TemplateResponse(
            request=request,
            name="web/entry.html.jinja2",
            context={
                "active": "login",
                "demo_username": demo_username,
                "next": None,
                "current_page": None,
            },
        )
    return await _render_home(request, user)


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
    safe_next = profiles.safe_next_path(next)
    user = _current_user(session)
    if user is not None:
        return RedirectResponse(url=safe_next or _home_url_for(user), status_code=303)

    demo_username = os.getenv("DEMO_PROFILE_USERNAME", "")
    return templates.TemplateResponse(
        request=request,
        name="web/entry.html.jinja2",
        context={
            "active": "login",
            "demo_username": demo_username,
            "next": safe_next,
            "current_page": None,
        },
    )


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
    if user is None:
        return RedirectResponse(url="/", status_code=303)
    gate = consent_gate_redirect(user)
    if gate is not None:
        return gate
    return await _render_home(request, user)
