"""Handler bodies for activity creation."""

from __future__ import annotations

from fastapi import Request
from fastapi.responses import HTMLResponse, RedirectResponse

from app import ui_strings
from app.models import db
from app.routes.web.common import templates
from app.services.activities import categories
from app.services.social import profiles


def new_activity_response(request: Request) -> HTMLResponse:
    return templates.TemplateResponse(request=request, name="components/activities/activity_sheet.html.jinja2", context={})


def create_activity_response(request: Request, user: dict, name: str) -> HTMLResponse | RedirectResponse:
    owner_id = int(user["id"])
    name = name.strip()
    if not name:
        return _activity_form_error(request, ui_strings.ACTIVITY_FORM_NAME_REQUIRED)
    if len(name) < 5:
        return _activity_form_error(request, ui_strings.ACTIVITY_FORM_NAME_TOO_SHORT)

    with db.connect() as conn:
        if conn.execute(
            "SELECT 1 FROM activity"
            " WHERE owner_id = ? AND LOWER(name) = LOWER(?) AND archived_at IS NULL"
            " LIMIT 1",
            (owner_id, name),
        ).fetchone():
            return _activity_form_error(request, ui_strings.ACTIVITY_FORM_NAME_DUPLICATE)

    result = categories.create_activity(owner_id, name=name)
    with db.connect() as conn:
        slug = conn.execute(
            "SELECT slug FROM activity WHERE id = ? AND owner_id = ?",
            (result["activity_id"], owner_id),
        ).fetchone()["slug"]

    username = user.get("username")
    if username is None:
        return RedirectResponse(url="/home", status_code=303)
    response = HTMLResponse(content="", status_code=201)
    response.headers["HX-Redirect"] = profiles.canonical_activity_url(username, slug)
    return response


def _activity_form_error(request: Request, message: str) -> HTMLResponse | RedirectResponse:
    if request.headers.get("HX-Request") != "true":
        return RedirectResponse(url="/home", status_code=303)
    return templates.TemplateResponse(
        request=request,
        name="components/activities/activity_form.html.jinja2",
        context={"hx_post": "/activities", "hx_target": "#cards", "hx_swap": "beforeend", "name_error": message},
        status_code=400,
    )
