"""Routes for the small, editorial Mushin guide library."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Cookie, Request
from fastapi.responses import HTMLResponse

from app import ui_strings
from app.auth import sessions
from app.content.guides import GUIDES, guide_for_slug, related_guides
from app.routes.web.common import _current_user, templates

router = APIRouter()


@router.get("/guides", response_class=HTMLResponse)
async def guide_index(
    request: Request,
    session: Annotated[str | None, Cookie(alias=sessions.COOKIE_NAME)] = None,
) -> HTMLResponse:
    return templates.TemplateResponse(
        request=request,
        name="web/guides/index.html.jinja2",
        context={
            "current_page": None,
            "show_bottom_nav": _current_user(session) is not None,
            "guides": GUIDES,
            "meta_description": ui_strings.GUIDES_INDEX_DESCRIPTION,
            "og_title": f"{ui_strings.GUIDES_INDEX_TITLE} · {ui_strings.APP_NAME}",
            "og_description": ui_strings.GUIDES_INDEX_DESCRIPTION,
            "twitter_card_type": "summary_large_image",
        },
    )


@router.get("/guides/{slug}", response_class=HTMLResponse)
async def guide_detail(
    request: Request,
    slug: str,
    session: Annotated[str | None, Cookie(alias=sessions.COOKIE_NAME)] = None,
) -> HTMLResponse:
    guide = guide_for_slug(slug)
    if guide is None:
        return templates.TemplateResponse(
            request=request,
            name="web/errors/404.html.jinja2",
            context={"current_page": None, "meta_robots": "noindex, nofollow"},
            status_code=404,
        )
    canonical_url = str(request.url).split("?", 1)[0]
    structured_data = {
        "@context": "https://schema.org",
        "@type": "Article",
        "headline": guide.title,
        "description": guide.description,
        "mainEntityOfPage": canonical_url,
        "datePublished": guide.published_on,
        "author": {"@type": "Organization", "name": ui_strings.GUIDES_EDITORIAL_AUTHOR},
        "publisher": {"@type": "Organization", "name": ui_strings.APP_NAME},
    }
    return templates.TemplateResponse(
        request=request,
        name="web/guides/detail.html.jinja2",
        context={
            "current_page": None,
            "show_bottom_nav": _current_user(session) is not None,
            "guide": guide,
            "related_guides": related_guides(guide),
            "meta_description": guide.description,
            "og_title": f"{guide.title} · {ui_strings.APP_NAME}",
            "og_description": guide.description,
            "og_type": "article",
            "twitter_card_type": "summary_large_image",
            "structured_data": structured_data,
        },
    )
