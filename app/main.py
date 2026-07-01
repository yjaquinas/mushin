"""Mushin — FastAPI entrypoint."""

from __future__ import annotations

from contextlib import asynccontextmanager
from pathlib import Path

import structlog
from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles

load_dotenv()

from app.auth.routes import router as auth_router  # noqa: E402
from app.middleware.visitor_tracking import VisitorTrackingMiddleware  # noqa: E402
from app.models.db import DATABASE_PATH  # noqa: E402
from app.models.migrate import run_migrations  # noqa: E402
from app.routes.admin import router as admin_router  # noqa: E402
from app.routes.data_io import router as data_io_router  # noqa: E402
from app.routes.public import router as public_router  # noqa: E402
from app.routes.web import router as web_router  # noqa: E402

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
    applied = run_migrations(DATABASE_PATH)
    for name in applied:
        log.info("migration.applied", filename=name)
    yield


app = FastAPI(title="Mushin", lifespan=lifespan)
app.add_middleware(VisitorTrackingMiddleware)
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

# Auth / guest / upgrade routes live in their own router (app/auth/), not in
# app/routes/web.py, which the page-UI task owns. See app/auth/routes.py.
app.include_router(auth_router)

# Page-UI routes (entry screen, character-sheet home, quick-add log flow).
app.include_router(web_router)

# Public, unauthenticated profile routes (/@{username}, /@{username}/{slug}).
app.include_router(public_router)

# Data-portability routes (export download).
app.include_router(data_io_router)

# Operator dashboard, HTTP Basic Auth gated. No admin features yet.
app.include_router(admin_router)


@app.get("/health", response_class=HTMLResponse)
async def health() -> str:
    """Cron-pingable health endpoint. Do not gate behind auth."""
    return "ok"
