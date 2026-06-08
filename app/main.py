"""Mushin — FastAPI entrypoint."""
from __future__ import annotations

from pathlib import Path

import structlog
from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

log = structlog.get_logger()

# Module layout (templates and static now live inside the app module):
#   app/main.py           ← this file
#   app/templates/web/    ← HTMX templates
#   app/templates/mobile/ ← HXML templates (if --mobile)
#   app/static/           ← CSS, JS, images
APP_DIR = Path(__file__).resolve().parent
TEMPLATE_DIR = APP_DIR / "templates"
STATIC_DIR = APP_DIR / "static"

app = FastAPI(title="Mushin")
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

# Two Jinja2 environments: one for web (.html.jinja2), one for mobile (.hxml.jinja2)
templates_web = Jinja2Templates(directory=str(TEMPLATE_DIR / "web"))

# Uncomment if --mobile was used at scaffold time:
# templates_mobile = Jinja2Templates(directory=str(TEMPLATE_DIR / "mobile"))


@app.get("/health", response_class=HTMLResponse)
async def health() -> str:
    """Cron-pingable health endpoint. Do not gate behind auth."""
    return "ok"


@app.get("/", response_class=HTMLResponse)
async def index(request: Request) -> HTMLResponse:
    return templates_web.TemplateResponse(
        request=request,
        name="index.html.jinja2",
        context={"title": "Mushin"},
    )


# Import route modules here to register them
# from app.routes import web, mobile, api  # noqa: F401
