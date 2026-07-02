"""Handler bodies for activity rename and delete admin actions."""

from __future__ import annotations

from fastapi import Request
from fastapi.responses import HTMLResponse

from app.models import db
from app.routes.web._shared import _home_url_for, templates
from app.services import _db, categories, profiles
from app.services.entries import ActivityNotFoundError


def rename_form_response(request: Request, activity_id: int, owner_id: int) -> HTMLResponse:
    with db.connect() as conn:
        conn.execute("BEGIN")
        row = _db.fetch_one(conn, "activity", owner_id, where="id = ?", params=(activity_id,))
    if row is None:
        return HTMLResponse(status_code=404)
    return templates.TemplateResponse(
        request=request,
        name="components/rename_form.html.jinja2",
        context={"activity_id": activity_id, "current_name": row["name"]},
    )


def rename_activity_response(request: Request, activity_id: int, owner_id: int, user: dict, name: str) -> HTMLResponse:
    try:
        with db.connect() as conn:
            conn.execute("BEGIN")
            new_slug = categories.rename_activity(
                conn, owner_id=owner_id, activity_id=activity_id, new_name=name
            )
    except ActivityNotFoundError:
        return HTMLResponse(status_code=404)
    except ValueError as exc:
        return templates.TemplateResponse(
            request=request,
            name="components/rename_form.html.jinja2",
            context={"activity_id": activity_id, "current_name": name, "error": str(exc), "open_on_error": True},
            status_code=422,
        )
    response = HTMLResponse(content="", status_code=200)
    response.headers["HX-Redirect"] = profiles.canonical_activity_url(user.get("username"), new_slug)
    return response


def category_delete_confirm_response(request: Request, activity_id: int, owner_id: int) -> HTMLResponse:
    with db.connect() as conn:
        conn.execute("BEGIN")
        row = conn.execute(
            "SELECT id, name FROM activity WHERE id = ? AND owner_id = ?",
            (activity_id, owner_id),
        ).fetchone()
    if row is None:
        return HTMLResponse(status_code=404)
    return templates.TemplateResponse(
        request=request,
        name="components/category_delete_confirm.html.jinja2",
        context={"activity_id": activity_id, "activity_name": row["name"]},
    )


def delete_category_response(activity_id: int, owner_id: int, user: dict) -> HTMLResponse:
    with db.connect() as conn:
        conn.execute("BEGIN")
        row = conn.execute(
            "SELECT category_id FROM activity WHERE id = ? AND owner_id = ?",
            (activity_id, owner_id),
        ).fetchone()
        if row is None:
            return HTMLResponse(status_code=404)
        categories.delete_category(conn, owner_id=owner_id, category_id=row["category_id"])
    response = HTMLResponse(content="", status_code=200)
    response.headers["HX-Redirect"] = _home_url_for(user)
    return response
