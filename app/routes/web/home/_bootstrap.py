"""Cheap entry response before the original page is fetched."""

from fastapi import Request
from fastapi.responses import HTMLResponse
from user_agents import parse as parse_user_agent

from app.routes.web.common import templates


def bootstrap_response(request: Request) -> HTMLResponse | None:
    if (
        request.method != "GET"
        or request.headers.get("sec-fetch-dest") != "document"
        or "text/html" not in request.headers.get("accept", "")
        or request.headers.get("x-mushin-bootstrap") == "content"
        or request.headers.get("hx-request") == "true"
        or request.headers.get("x-in-tab-nav")
        or request.query_params.get("__mushin_ssr") == "1"
        or parse_user_agent(request.headers.get("user-agent", "")).is_bot
    ):
        return None
    request.state.bootstrap_shell = True
    return templates.TemplateResponse(
        request=request,
        name="web/home/bootstrap.html.jinja2",
        context={
            "bootstrap_url": str(request.url),
            "bootstrap_fallback": str(request.url.include_query_params(__mushin_ssr="1")),
        },
        headers={"Cache-Control": "private, no-store", "X-Mushin-Bootstrap": "shell"},
    )
