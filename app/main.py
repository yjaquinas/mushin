"""Mushin — FastAPI entrypoint."""

from __future__ import annotations

from contextlib import asynccontextmanager
from pathlib import Path

import structlog
from fastapi import FastAPI
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles

from app.auth.routes import router as auth_router
from app.models.migrate import run_migrations
from app.routes.web import router as web_router

log = structlog.get_logger()

# Module layout (templates and static now live inside the app module):
#   app/main.py           ← this file
#   app/templates/web/    ← HTMX templates
#   app/templates/mobile/ ← HXML templates (if --mobile)
#   app/static/           ← CSS, JS, images
APP_DIR = Path(__file__).resolve().parent
STATIC_DIR = APP_DIR / "static"


@asynccontextmanager
async def lifespan(application: FastAPI):  # noqa: ARG001
    applied = run_migrations()
    for name in applied:
        log.info("migration.applied", filename=name)
    yield


app = FastAPI(title="Mushin", lifespan=lifespan)
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

# Auth / guest / upgrade routes live in their own router (app/auth/), not in
# app/routes/web.py, which the page-UI task owns. See app/auth/routes.py.
app.include_router(auth_router)

# Page-UI routes (entry screen, character-sheet home, quick-add log flow).
app.include_router(web_router)


@app.get("/health", response_class=HTMLResponse)
async def health() -> str:
    """Cron-pingable health endpoint. Do not gate behind auth."""
    return "ok"
