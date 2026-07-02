"""Entry comment threads on a public activity (collapsed affordance + fragment).

Three routes, all scoped under ``/@{username}/{slug}/entries/{entry_id}/comments``:
fetch the thread fragment (HTMX swap target), post a new comment, fetch the
delete-confirm dialog, and soft-delete a comment. All four share a visibility
gate (``_resolve_entry_for_comments``) and a render helper
(``_render_comment_thread``).

THE SINGLE VISIBILITY AUTHORITY
--------------------------------
Every route here drives its visibility decision through
``profiles.can_view_activity_detail`` — the sole, fail-closed authority (see
``app/services/profiles.py``) — never an inline ``visibility`` check. Comment
write permission goes through ``profiles.can_comment_on_entry`` the same way.

Business logic stays in ``app/services/comments.py``; this module is thin
handlers + the context-assembly helpers ``app/routes/web.py`` exports.
"""

from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Cookie, Form, Request
from fastapi.responses import HTMLResponse

from app.auth import sessions
from app.models import db
from app.routes.public._contexts import templates
from app.services import comments as comments_service
from app.services import entries, profiles
from app.services.comments import CommentNotFoundError, CommentPermissionError
from app.services.entries import EntryNotFoundError

router = APIRouter()


def _resolve_entry_for_comments(
    conn: Any, username: str, slug: str, entry_id: int, current_uid: int | None
) -> tuple[dict, int, int, dict] | HTMLResponse:
    """Shared lookup + visibility gate for all three comment routes.

    Returns ``(user, owner_id, activity_id, entry)`` on success, or an
    ``HTMLResponse`` (404) the caller should return directly. Mirrors the
    branch order in ``public_activity``: unknown username/slug/entry, a
    cross-activity entry id, or a viewer who fails
    ``can_view_activity_detail`` (limited/blocked) all 404 here rather than
    leaking anything about the entry's existence — this is a fragment route,
    not a navigable page, so there's no profile to redirect back to.
    """
    user = profiles.get_public_user(conn, username)
    if user is None:
        return HTMLResponse(status_code=404)
    owner_id = int(user["id"])
    activity_id = profiles.resolve_activity_slug(conn, owner_id, slug)
    if activity_id is None:
        return HTMLResponse(status_code=404)

    if not profiles.can_view_activity_detail(conn, current_user_id=current_uid, profile_user=user):
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
    """Build + render the comment-thread fragment for *entry_id*."""
    rows = comments_service.list_comments(conn, entry_id, viewer_id=current_uid)
    can_comment = profiles.can_comment_on_entry(
        conn, current_user_id=current_uid, profile_user=user, activity_id=activity_id
    )
    context = {
        "activity_id": activity_id,
        "username": username,
        "slug": slug,
        "entry_id": entry_id,
        "entry_owner_id": owner_id,
        "comments": rows,
        "can_comment": can_comment,
        "viewer_logged_in": current_uid is not None,
        "current_user_id": current_uid,
    }
    return templates.TemplateResponse(
        request=request,
        name="components/comment_thread.html.jinja2",
        context=context,
    )


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
    """Render the comment-thread fragment for *entry_id* (HTMX swap target).

    404s for an unknown username/slug/entry, a cross-activity entry id, or a
    viewer who fails ``can_view_activity_detail`` (limited/blocked) — same
    visibility authority the activity-detail route uses, never inlined. The
    composer only appears in the rendered markup when
    ``profiles.can_comment_on_entry`` is true for the current viewer; a
    logged-out viewer on an otherwise-visible entry gets the read-only list
    plus a "log in to comment" link.
    """
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
    session: Annotated[str | None, Cookie(alias=sessions.COOKIE_NAME)] = None,
) -> HTMLResponse:
    """Create a comment on *entry_id*, then return the refreshed thread fragment.

    Server-side gate, independent of anything the client sent: re-checks
    ``can_comment_on_entry`` (which itself requires a real session) before
    writing. An unauthorized POST — no session, a non-fellow on a private
    profile, a blocked viewer — gets 403, never a silent no-op and never a
    write. An empty/whitespace-only body is rejected the same way
    ``create_comment`` itself rejects it (422), so a tampered client can't
    bypass the textarea's ``required`` attribute either.
    """
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
            comments_service.create_comment(conn, entry_id, author_id=current_uid, body=body)
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
    """Return the comment-delete confirm dialog for *comment_id*."""
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
            name="components/comment_delete_confirm.html.jinja2",
            context={
                "username": username,
                "slug": slug,
                "entry_id": entry_id,
                "comment_id": comment_id,
            },
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
    """Soft-delete *comment_id*, then return the refreshed thread fragment.

    Restricted server-side to the comment's author or the entry's owner —
    ``soft_delete_comment`` itself raises ``CommentPermissionError`` for
    anyone else, which we map to 403 (never a silent no-op). A session is
    required (anonymous can't author or own anything); an unknown/already-
    deleted comment 404s.
    """
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
