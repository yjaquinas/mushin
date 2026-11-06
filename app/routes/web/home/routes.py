"""Entry screen, login, and the character-sheet profile.

Thin handlers only — business logic lives in app/services/. Full pages render
on initial navigation; fragments swap on interaction (detect via the
HX-Request header).
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Cookie, Request
from fastapi.responses import HTMLResponse, RedirectResponse, Response

from app import ui_strings
from app.auth import sessions
from app.routes.web.common import templates
from app.routes.web.home._crawl import robots_response
from app.routes.web.home._entry_handlers import entry_response
from app.routes.web.home._sitemap import sitemap_response

router = APIRouter()


@router.get("/privacy", response_class=HTMLResponse)
async def privacy(request: Request) -> HTMLResponse:
    """The privacy policy page. Reachable logged-out."""
    return templates.TemplateResponse(
        request=request,
        name="web/legal/privacy.html.jinja2",
        context={
            "current_page": None,
            "meta_description": ui_strings.META_DESCRIPTION_PRIVACY,
        },
    )


@router.get("/terms", response_class=HTMLResponse)
async def terms(request: Request) -> HTMLResponse:
    """The terms page. Reachable logged-out."""
    return templates.TemplateResponse(
        request=request,
        name="web/legal/terms.html.jinja2",
        context={
            "current_page": None,
            "meta_description": ui_strings.META_DESCRIPTION_TERMS,
        },
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
    return entry_response(request, session, next)


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
    return entry_response(request, session, next)


@router.get("/auth/login-form", response_class=HTMLResponse)
async def login_form(request: Request) -> HTMLResponse:
    """The Log in tab's fragment — swapped into ``#auth-form`` by the entry-screen toggle.

    Renders standalone (re-asserts the toggle with "Log in" selected) so a
    direct fragment load isn't visually orphaned.
    """
    return templates.TemplateResponse(
        request=request,
        name="components/auth/auth_login_form.html.jinja2",
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
        name="components/auth/auth_create_form.html.jinja2",
        context={"active": "create"},
    )


@router.get("/robots.txt", response_class=Response, include_in_schema=False)
async def robots_txt() -> Response:
    return robots_response()


@router.get("/sitemap.xml", response_class=Response, include_in_schema=False)
async def sitemap_xml(request: Request) -> Response:
    return sitemap_response(request)


@router.get("/home", response_model=None)
async def home(
    request: Request,
    session: Annotated[str | None, Cookie(alias=sessions.COOKIE_NAME)] = None,
) -> HTMLResponse | RedirectResponse:
    """The character-sheet profile. Redirects to the entry screen with no
    session, or to the user's canonical profile URL when already logged in.
    """
    return entry_response(request, session, home=True)
