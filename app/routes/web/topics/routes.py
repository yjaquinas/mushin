"""Routes for curated, consent-safe topic collections."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Cookie, Request
from fastapi.responses import HTMLResponse

from app import ui_strings
from app.auth import sessions
from app.content.guides import guide_for_slug
from app.content.topic_hubs import topic_for_slug
from app.models import db
from app.routes.web.common import _current_user, templates
from app.services.search.topic_hubs import topic_page

router = APIRouter()


@router.get("/topics/{slug}", response_class=HTMLResponse)
@router.get("/topics/{slug}/page/{page}", response_class=HTMLResponse)
async def topic_detail(
    request: Request,
    slug: str,
    page: int = 1,
    session: Annotated[str | None, Cookie(alias=sessions.COOKIE_NAME)] = None,
) -> HTMLResponse:
    topic = topic_for_slug(slug)
    if topic is None:
        return _not_found(request)
    with db.connect() as conn:
        conn.execute("BEGIN")
        result = topic_page(conn, topic, page=page)
    if result is None:
        return _not_found(request)
    canonical_url = str(request.url).split("?", 1)[0]
    activities = result["activities"]
    base_url = str(request.base_url).rstrip("/")
    structured_data = {
        "@context": "https://schema.org",
        "@type": "ItemList",
        "name": topic.title,
        "url": canonical_url,
        "numberOfItems": len(activities),
        "itemListElement": [
            {
                "@type": "ListItem",
                "position": index,
                "url": base_url + activity["url"],
                "name": activity["name"],
            }
            for index, activity in enumerate(activities, start=1)
        ],
    }
    return templates.TemplateResponse(
        request=request,
        name="web/topics/detail.html.jinja2",
        context={
            "current_page": None,
            "show_bottom_nav": _current_user(session) is not None,
            "topic": topic,
            "guides": tuple(
                guide for slug in topic.guide_slugs if (guide := guide_for_slug(slug)) is not None
            ),
            "meta_description": topic.description,
            "og_title": f"{topic.title} · {ui_strings.APP_NAME}",
            "og_description": topic.description,
            "structured_data": structured_data,
            **result,
        },
    )


def _not_found(request: Request) -> HTMLResponse:
    return templates.TemplateResponse(
        request=request,
        name="web/errors/404.html.jinja2",
        context={"current_page": None, "meta_robots": "noindex, nofollow"},
        status_code=404,
    )
