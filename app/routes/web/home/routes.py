"""Entry screen, login, and the character-sheet profile.

Thin handlers only — business logic lives in app/services/. Full pages render
on initial navigation; fragments swap on interaction (detect via the
HX-Request header).
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Cookie, Request
from fastapi.responses import HTMLResponse, RedirectResponse, Response

from app.auth import sessions
from app.routes.web.home.handlers import (
    home_gate_response,
    login_page_response,
    redirect_logged_in_home,
    render_entry_page,
)
from app import ui_strings
from app.routes.web.common import _current_user, templates
from app.services.social import profiles

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
    content = (
        "User-agent: *\n"
        "Allow: /\n"
        "Allow: /privacy\n"
        "Allow: /terms\n"
        "Allow: /licenses\n"
        "Allow: /@*\n"
        "Disallow: /home\n"
        "Disallow: /settings\n"
        "Disallow: /social\n"
        "Disallow: /comments\n"
        "Disallow: /admin\n"
        "Disallow: /auth/\n"
        "Disallow: /welcome-sharing\n"
        "Disallow: /login\n"
        "Disallow: /health\n"
        "\n"
        "Sitemap: https://mushin.app/sitemap.xml\n"
    )
    return Response(content=content, media_type="text/plain")


@router.get("/sitemap.xml", response_class=Response, include_in_schema=False)
async def sitemap_xml(request: Request) -> Response:
    base = str(request.base_url)
    content = (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
        f"  <url><loc>{base}</loc><priority>1.0</priority></url>\n"
        f"  <url><loc>{base}privacy</loc><priority>0.5</priority></url>\n"
        f"  <url><loc>{base}terms</loc><priority>0.5</priority></url>\n"
        f"  <url><loc>{base}licenses</loc><priority>0.3</priority></url>\n"
        "</urlset>\n"
    )
    return Response(content=content, media_type="text/xml")


@router.get("/home", response_model=None)
async def home(
    request: Request,
    session: Annotated[str | None, Cookie(alias=sessions.COOKIE_NAME)] = None,
) -> HTMLResponse | RedirectResponse:
    """The character-sheet profile. Redirects to the entry screen with no
    session, or to the user's canonical profile URL when already logged in.
    """
    user = _current_user(session)
    gate = home_gate_response(user)
    if gate is not None:
        return gate
    return redirect_logged_in_home(user)
