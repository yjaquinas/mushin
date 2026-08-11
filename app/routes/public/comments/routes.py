"""Public entry comment routes."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Cookie, Form, Query, Request
from fastapi.responses import HTMLResponse

from app.auth import sessions
from app.routes.public.comments import handlers, reply_handlers

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


@router.post(
    "/@{username}/{slug}/entries/{entry_id}/comments/{comment_id}/replies",
    response_class=HTMLResponse,
    response_model=None,
)
async def post_entry_comment_reply(
    request: Request,
    username: str,
    slug: str,
    entry_id: int,
    comment_id: int,
    body: Annotated[str, Form()],
    comment_timezone: Annotated[str | None, Form()] = None,
    session: Annotated[str | None, Cookie(alias=sessions.COOKIE_NAME)] = None,
) -> HTMLResponse:
    return await reply_handlers.post_entry_comment_reply_body(
        request, username, slug, entry_id, comment_id, body, comment_timezone, session
    )


@router.get(
    "/@{username}/{slug}/entries/{entry_id}/comments/{comment_id}/reply-form",
    response_class=HTMLResponse,
    response_model=None,
)
async def get_entry_comment_reply_form(
    request: Request,
    username: str,
    slug: str,
    entry_id: int,
    comment_id: int,
    closed: Annotated[bool, Query()] = False,
    session: Annotated[str | None, Cookie(alias=sessions.COOKIE_NAME)] = None,
) -> HTMLResponse:
    return await reply_handlers.get_entry_comment_reply_form_body(
        request, username, slug, entry_id, comment_id, closed, session
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


@router.post(
    "/@{username}/{slug}/entries/{entry_id}/comments/{comment_id}/visibility",
    response_class=HTMLResponse,
    response_model=None,
)
async def set_entry_comment_visibility(
    request: Request,
    username: str,
    slug: str,
    entry_id: int,
    comment_id: int,
    hidden: Annotated[bool, Form()],
    session: Annotated[str | None, Cookie(alias=sessions.COOKIE_NAME)] = None,
) -> HTMLResponse:
    if hidden:
        return await handlers.hide_entry_comment_body(
            request, username, slug, entry_id, comment_id, session
        )
    return await handlers.unhide_entry_comment_body(
        request, username, slug, entry_id, comment_id, session
    )
