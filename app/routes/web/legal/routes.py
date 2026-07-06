"""Legal content routes — fragment (HTMX) and full-page variants.

Fragments are loaded into the legal dialog; full-page routes exist for
direct access (e.g. search-engine links or logged-out visitors).
"""

from __future__ import annotations

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse

from app.routes.web.common import templates

router = APIRouter()

_LEGAL_TEMPLATES: dict[str, str] = {
    "privacy": "web/legal/_privacy_content.html",
    "terms": "web/legal/_terms_content.html",
    "licenses": "web/legal/_licenses_content.html",
}


@router.get("/legal/{type}", response_class=HTMLResponse)
async def legal_fragment(type: str, request: Request) -> HTMLResponse:
    """Return the legal content fragment for the given type.

    Used by the legal dialog via HTMX. Valid types: privacy, terms, licenses.
    Invalid types return a 204 No Content.
    """
    template = _LEGAL_TEMPLATES.get(type)
    if template is None:
        return HTMLResponse(status_code=204)
    return templates.TemplateResponse(
        request=request, name=template, context={}
    )


@router.get("/licenses", response_class=HTMLResponse)
async def licenses_page(request: Request) -> HTMLResponse:
    """The open source licenses page. Reachable logged-out."""
    return templates.TemplateResponse(
        request=request,
        name="web/legal/licenses.html.jinja2",
        context={"current_page": None},
    )
