"""Public entry comment routes."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Cookie, Form, Request
from fastapi.responses import HTMLResponse

from app.auth import sessions
from app.routes.public.comments import handlers

router = APIRouter()


@router.get(
    "/@{username}/{slug}/entries/{entry_id}/comments",
    response_class=HTMLResponse,
    response_model=None,
)
async def get_entry_comments(
    request: Request,
    username: str,
    slug: str,
    entry_id: int,
    session: Annotated[str | None, Cookie(alias=sessions.COOKIE_NAME)] = None,
) -> HTMLResponse:
    return await handlers.get_entry_comments_body(
        request, username, slug, entry_id, session
    )


@router.post(
    "/@{username}/{slug}/entries/{entry_id}/comments",
    response_class=HTMLResponse,
    response_model=None,
)
async def post_entry_comment(
    request: Request,
    username: str,
    slug: str,
    entry_id: int,
    body: Annotated[str, Form()],
    comment_timezone: Annotated[str | None, Form()] = None,
    session: Annotated[str | None, Cookie(alias=sessions.COOKIE_NAME)] = None,
) -> HTMLResponse:
    return await handlers.post_entry_comment_body(
        request, username, slug, entry_id, body, comment_timezone, session
    )


@router.get(
    "/@{username}/{slug}/entries/{entry_id}/comments/{comment_id}/delete-confirm",
    response_class=HTMLResponse,
    response_model=None,
)
async def get_delete_entry_comment_confirm(
    request: Request,
    username: str,
    slug: str,
    entry_id: int,
    comment_id: int,
    session: Annotated[str | None, Cookie(alias=sessions.COOKIE_NAME)] = None,
) -> HTMLResponse:
    return await handlers.get_delete_entry_comment_confirm_body(
        request, username, slug, entry_id, comment_id, session
    )


@router.post(
    "/@{username}/{slug}/entries/{entry_id}/comments/{comment_id}/delete",
    response_class=HTMLResponse,
    response_model=None,
)
async def delete_entry_comment(
    request: Request,
    username: str,
    slug: str,
    entry_id: int,
    comment_id: int,
    session: Annotated[str | None, Cookie(alias=sessions.COOKIE_NAME)] = None,
) -> HTMLResponse:
    return await handlers.delete_entry_comment_body(
        request, username, slug, entry_id, comment_id, session
    )
