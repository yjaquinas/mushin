"""Legacy comment notification redirect."""

from __future__ import annotations

from fastapi import APIRouter
from fastapi.responses import RedirectResponse

router = APIRouter()


@router.get("/comments")
async def comments_page() -> RedirectResponse:
    return RedirectResponse(url="/notifications", status_code=303)
