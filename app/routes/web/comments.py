"""Comment notification history (``/comments``)."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, Cookie, Query, Request
from fastapi.responses import HTMLResponse, RedirectResponse

from app.auth import sessions
from app.models import db
from app.routes.web._shared import _current_user, consent_gate_redirect, templates
from app.services import comments

router = APIRouter()


@router.get("/comments", response_class=HTMLResponse)
async def comments_page(
    request: Request,
    session: Annotated[str | None, Cookie(alias=sessions.COOKIE_NAME)] = None,
    before_id: Annotated[int | None, Query()] = None,
) -> HTMLResponse:
    """The dedicated comment-notification history — the only place the
    ``comments_seen_at`` watermark advances.

    Order matters and is the entire point of this route: read the
    pre-visit watermark, use it to compute each row's ``is_new``, render,
    THEN advance the watermark. Stamping first (as the old ``home`` handler
    did) would make every row compute as already-seen on its own render.
    """
    user = _current_user(session)
    if user is None:
        return RedirectResponse(url="/", status_code=303)
    gate = consent_gate_redirect(user)
    if gate is not None:
        return gate

    owner_id = int(user["id"])
    with db.connect() as conn:
        conn.execute("BEGIN")
        watermark_row = conn.execute(
            "SELECT comments_seen_at FROM user WHERE id = ?", (owner_id,)
        ).fetchone()
        watermark = watermark_row["comments_seen_at"] if watermark_row else None

        rows = comments.list_comments_for_owner(
            conn, owner_id, before_id=before_id, watermark=watermark
        )

        conn.execute(
            "UPDATE user SET comments_seen_at = ? WHERE id = ?",
            (datetime.now(UTC).isoformat(), owner_id),
        )

    has_more = len(rows) == 50
    next_before_id = rows[-1]["comment_id"] if has_more and rows else None

    return templates.TemplateResponse(
        request=request,
        name="web/comments.html.jinja2",
        context={
            "comments": rows,
            "username": user["username"],
            "has_more": has_more,
            "next_before_id": next_before_id,
            "current_page": None,
        },
    )
