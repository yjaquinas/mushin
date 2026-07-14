"""Routes for the public plans comparison page."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Cookie, Request
from fastapi.responses import HTMLResponse

from app.auth import sessions
from app.routes.plans.handlers import plans_page
from app.routes.web.common import _current_user

router = APIRouter()


@router.get("/plans", response_class=HTMLResponse)
async def public_plans(
    request: Request,
    session: Annotated[str | None, Cookie(alias=sessions.COOKIE_NAME)] = None,
) -> HTMLResponse:
    user = _current_user(session)
    return await plans_page(request, user)
