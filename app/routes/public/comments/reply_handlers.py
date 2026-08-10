"""Reply-composer and submission handlers for public comment fragments."""

from __future__ import annotations

from fastapi import Request
from fastapi.responses import HTMLResponse

from app.auth import sessions
from app.models import db
from app.routes.public.comments import handlers
from app.routes.public.common.contexts import templates
from app.services.entries import comments as comments_service
from app.services.entries.comments import CommentNotFoundError
from app.services.social import profiles


async def get_entry_comment_reply_form_body(
    request: Request,
    username: str,
    slug: str,
    entry_id: int,
    comment_id: int,
    closed: bool,
    session: str | None,
) -> HTMLResponse:
    current_uid = sessions.read_uid(session)
    with db.connect() as conn:
        conn.execute("BEGIN")
        resolved = handlers._resolve_entry_for_comments(
            conn, username, slug, entry_id, current_uid
        )
        if isinstance(resolved, HTMLResponse):
            return resolved
        user, _owner_id, activity_id, _entry = resolved
        if not profiles.can_comment_on_entry(
            conn, current_user_id=current_uid, profile_user=user, activity_id=activity_id
        ):
            return HTMLResponse(status_code=403)
        comment = comments_service.get_reply_target(conn, entry_id, comment_id)
        if comment is None:
            return HTMLResponse(status_code=404)
        return templates.TemplateResponse(
            request=request,
            name="components/entries/_comment_reply_form.html.jinja2",
            context={
                "username": username,
                "slug": slug,
                "entry_id": entry_id,
                "comment": comment,
                "closed": closed,
            },
        )


async def post_entry_comment_reply_body(
    request: Request,
    username: str,
    slug: str,
    entry_id: int,
    comment_id: int,
    body: str,
    comment_timezone: str | None,
    session: str | None,
) -> HTMLResponse:
    current_uid = sessions.read_uid(session)
    with db.connect() as conn:
        conn.execute("BEGIN")
        resolved = handlers._resolve_entry_for_comments(
            conn, username, slug, entry_id, current_uid
        )
        if isinstance(resolved, HTMLResponse):
            return resolved
        user, owner_id, activity_id, _entry = resolved
        if not profiles.can_comment_on_entry(
            conn, current_user_id=current_uid, profile_user=user, activity_id=activity_id
        ):
            return HTMLResponse(status_code=403)
        try:
            comments_service.create_reply(
                conn, entry_id, comment_id, current_uid, body, timezone=comment_timezone
            )
        except CommentNotFoundError:
            return HTMLResponse(status_code=404)
        except ValueError:
            return HTMLResponse(status_code=422)
        return handlers._render_comment_thread(
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
