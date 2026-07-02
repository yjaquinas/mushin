"""Entry row rendering helpers."""

from __future__ import annotations

from typing import Any

from fastapi.responses import HTMLResponse

from app.auth import users
from app.models import db
from app.routes.web._shared import templates
from app.services import comments, profiles


def _render_template_html(name: str, context: dict[str, Any]) -> str:
    return templates.env.get_template(name).render(context)


def _render_entry_row(request: Any, activity_id: int, owner_id: int, entry: dict[str, Any]) -> HTMLResponse:
    user = users.get_user(owner_id)
    username = user.get("username") if user is not None else None
    with db.connect() as conn:
        conn.execute("BEGIN")
        activity_row = profiles.get_activity_for_owner(conn, activity_id=activity_id, owner_id=owner_id)
        slug = activity_row["slug"] if activity_row is not None else None
        counts = comments.counts_for_entries(conn, [entry["id"]])
    entry = dict(entry)
    entry["comment_count"] = counts.get(entry["id"], 0)
    return templates.TemplateResponse(
        request=request,
        name="components/entry_row.html.jinja2",
        context={"activity_id": activity_id, "entry": entry, "username": username, "slug": slug, "expand_comment_entry_id": entry["id"]},
    )

