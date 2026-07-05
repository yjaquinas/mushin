"""Handler bodies for public entry comment fragments."""

from __future__ import annotations

from typing import Any

from fastapi import Request
from fastapi.responses import HTMLResponse

from app.auth import sessions
from app.models import db
from app.routes.public.common.contexts import templates
from app.services.entries import comments as comments_service
from app.services.entries import entries
from app.services.entries.comments import CommentNotFoundError, CommentPermissionError
from app.services.entries.entries import EntryNotFoundError
from app.services.social import profiles


def _resolve_entry_for_comments(
    conn: Any, username: str, slug: str, entry_id: int, current_uid: int | None
) -> tuple[dict, int, int, dict] | HTMLResponse:
    user = profiles.get_public_user(conn, username)
    if user is None:
        return HTMLResponse(status_code=404)
    owner_id = int(user["id"])
    activity_id = profiles.resolve_activity_slug(conn, owner_id, slug)
    if activity_id is None:
        return HTMLResponse(status_code=404)

    if not profiles.can_view_activity_detail(
        conn, current_user_id=current_uid, profile_user=user
    ):
        return HTMLResponse(status_code=404)

    try:
        entry = entries.get(owner_id, entry_id)
    except EntryNotFoundError:
        return HTMLResponse(status_code=404)
    if entry["activity_id"] != activity_id:
        return HTMLResponse(status_code=404)

    return user, owner_id, activity_id, entry


def _render_comment_thread(
    request: Request,
    conn: Any,
    *,
    username: str,
    slug: str,
    owner_id: int,
    activity_id: int,
    entry_id: int,
    current_uid: int | None,
    user: dict,
) -> HTMLResponse:
    rows = comments_service.list_comments(conn, entry_id, viewer_id=current_uid)
    can_comment = profiles.can_comment_on_entry(
        conn, current_user_id=current_uid, profile_user=user, activity_id=activity_id
    )
    return templates.TemplateResponse(
        request=request,
        name="components/entries/comment_thread.html.jinja2",
        context={
            "activity_id": activity_id,
            "username": username,
            "slug": slug,
            "entry_id": entry_id,
            "entry_owner_id": owner_id,
            "comments": rows,
            "can_comment": can_comment,
            "viewer_logged_in": current_uid is not None,
            "current_user_id": current_uid,
        },
    )


async def get_entry_comments_body(
    request: Request,
    username: str,
    slug: str,
    entry_id: int,
    session: str | None,
) -> HTMLResponse:
    current_uid = sessions.read_uid(session)
    with db.connect() as conn:
        conn.execute("BEGIN")
        resolved = _resolve_entry_for_comments(conn, username, slug, entry_id, current_uid)
        if isinstance(resolved, HTMLResponse):
            return resolved
        user, owner_id, activity_id, _entry = resolved
        return _render_comment_thread(
            request,
            conn,
            username=username,
            slug=slug,
            owner_id=owner_id,
            activity_id=activity_id,
            entry_id=entry_id,
            current_uid=current_uid,
            user=user,
        )


async def post_entry_comment_body(
    request: Request,
    username: str,
    slug: str,
    entry_id: int,
    body: str,
    comment_timezone: str | None,
    session: str | None,
) -> HTMLResponse:
    current_uid = sessions.read_uid(session)
    with db.connect() as conn:
        conn.execute("BEGIN")
        resolved = _resolve_entry_for_comments(conn, username, slug, entry_id, current_uid)
        if isinstance(resolved, HTMLResponse):
            return resolved
        user, owner_id, activity_id, _entry = resolved

        if not profiles.can_comment_on_entry(
            conn, current_user_id=current_uid, profile_user=user, activity_id=activity_id
        ):
            return HTMLResponse(status_code=403)

        try:
            comments_service.create_comment(
                conn,
                entry_id,
                author_id=current_uid,
                body=body,
                timezone=comment_timezone,
            )
        except ValueError:
            return HTMLResponse(status_code=422)

        return _render_comment_thread(
            request,
            conn,
            username=username,
            slug=slug,
            owner_id=owner_id,
            activity_id=activity_id,
            entry_id=entry_id,
            current_uid=current_uid,
            user=user,
        )


async def get_delete_entry_comment_confirm_body(
    request: Request,
    username: str,
    slug: str,
    entry_id: int,
    comment_id: int,
    session: str | None,
) -> HTMLResponse:
    current_uid = sessions.read_uid(session)
    if current_uid is None:
        return HTMLResponse(status_code=401)

    with db.connect() as conn:
        conn.execute("BEGIN")
        resolved = _resolve_entry_for_comments(conn, username, slug, entry_id, current_uid)
        if isinstance(resolved, HTMLResponse):
            return resolved
        _user, owner_id, _activity_id, _entry = resolved

        rows = comments_service.list_comments(conn, entry_id, viewer_id=current_uid)
        comment = next((row for row in rows if row["id"] == comment_id), None)
        if comment is None:
            return HTMLResponse(status_code=404)
        if current_uid != comment["author_id"] and current_uid != owner_id:
            return HTMLResponse(status_code=403)

        return templates.TemplateResponse(
            request=request,
            name="components/entries/comment_delete_confirm.html.jinja2",
            context={
                "username": username,
                "slug": slug,
                "entry_id": entry_id,
                "comment_id": comment_id,
            },
        )


async def delete_entry_comment_body(
    request: Request,
    username: str,
    slug: str,
    entry_id: int,
    comment_id: int,
    session: str | None,
) -> HTMLResponse:
    current_uid = sessions.read_uid(session)
    if current_uid is None:
        return HTMLResponse(status_code=401)

    with db.connect() as conn:
        conn.execute("BEGIN")
        resolved = _resolve_entry_for_comments(conn, username, slug, entry_id, current_uid)
        if isinstance(resolved, HTMLResponse):
            return resolved
        user, owner_id, activity_id, _entry = resolved

        try:
            comments_service.soft_delete_comment(conn, comment_id, requester_id=current_uid)
        except CommentNotFoundError:
            return HTMLResponse(status_code=404)
        except CommentPermissionError:
            return HTMLResponse(status_code=403)

        return _render_comment_thread(
            request,
            conn,
            username=username,
            slug=slug,
            owner_id=owner_id,
            activity_id=activity_id,
            entry_id=entry_id,
            current_uid=current_uid,
            user=user,
        )
