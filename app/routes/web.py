"""Web (HTMX) routes for Mushin.

Thin handlers only — business logic lives in app/services/. Full pages render on
initial navigation; fragments swap on interaction (detect via the HX-Request
header). See .claude/rules/web-templates.md for conventions.
"""
from __future__ import annotations

from fastapi import APIRouter

router = APIRouter()

# Register web routes here, e.g.:
#
# @router.get("/categories", response_class=HTMLResponse)
# async def list_categories(request: Request) -> HTMLResponse:
#     ...
