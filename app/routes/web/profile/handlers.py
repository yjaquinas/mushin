from __future__ import annotations

from fastapi import Request
from fastapi.responses import HTMLResponse

from app.auth import users
from app.routes.web.common import templates
from app.routes.web.common import ui_strings as strings


def _bio_display(user: dict) -> str:
    return templates.get_template("components/profile/_bio_display.html.jinja2").render(
        bio=user.get("bio", ""),
    )


def _bio_edit(user: dict, *, bio_error: str | None = None) -> str:
    return templates.get_template("components/profile/_bio_edit.html.jinja2").render(
        bio=user.get("bio", ""),
        bio_error=bio_error,
    )


async def get_bio_fragment(request: Request, user: dict) -> HTMLResponse:
    return HTMLResponse(content=_bio_display(user))


async def get_bio_edit_fragment(request: Request, user: dict) -> HTMLResponse:
    return HTMLResponse(content=_bio_edit(user))


async def update_bio(request: Request, user: dict, bio: str | None) -> HTMLResponse:
    bio = (bio or "").strip()
    if len(bio) > 100:
        return HTMLResponse(content=_bio_edit(user, bio_error=strings.PROFILE_BIO_TOO_LONG), status_code=422)
    if bio != (user.get("bio") or ""):
        users.set_bio(int(user["id"]), bio)
        user["bio"] = bio
    return HTMLResponse(content=_bio_display(user))
