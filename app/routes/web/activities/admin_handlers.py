"""Handler bodies for activity rename and delete admin actions."""

from __future__ import annotations

import json

from fastapi import Request
from fastapi.responses import HTMLResponse


from app import ui_strings
from app.models import db
from app.routes.web.common import _home_url_for, templates
from app.services.common import db as _db
from app.services.activities import categories
from app.services.plans import SecretActivityForbiddenError, get_user_plan_config
from app.services.social import profiles
from app.services.entries.entries import ActivityNotFoundError


def rename_form_response(request: Request, activity_id: int, owner_id: int) -> HTMLResponse:
    with db.connect() as conn:
        conn.execute("BEGIN")
        row = _db.fetch_one(conn, "activity", owner_id, where="id = ?", params=(activity_id,))
        cfg = get_user_plan_config(conn, owner_id)
    if row is None:
        return HTMLResponse(status_code=404)
    return templates.TemplateResponse(
        request=request,
        name="components/activities/rename_form.html.jinja2",
        context={
            "activity_id": activity_id,
            "current_name": row["name"],
            "is_secret": bool(row["secret"]),
            "secret_allowed": bool(cfg["secret_activities"]) if cfg else False,
            "secret_toast_message": ui_strings.SECRET_ACTIVITY_TOAST,
        },
    )


def rename_activity_response(request: Request, activity_id: int, owner_id: int, user: dict, name: str, secret: bool | None = None) -> HTMLResponse:
    if secret:
        with db.connect() as conn:
            conn.execute("BEGIN")
            try:
                from app.services.plans import check_secret_activity_allowed
                check_secret_activity_allowed(conn, owner_id)
            except SecretActivityForbiddenError:
                response = HTMLResponse(content="")
                response.headers["HX-Trigger"] = json.dumps({
                    "show-toast": {
                        "message": ui_strings.SECRET_ACTIVITY_TOAST,
                        "variant": "warning",
                    }
                })
                response.headers["HX-Reswap"] = "none"
                return response
    try:
        with db.connect() as conn:
            conn.execute("BEGIN")
            if secret is not None:
                new_slug = categories.update_activity(
                    conn, owner_id=owner_id, activity_id=activity_id, name=name, secret=secret
                )
            else:
                new_slug = categories.rename_activity(
                    conn, owner_id=owner_id, activity_id=activity_id, new_name=name
                )
    except ActivityNotFoundError:
        return HTMLResponse(status_code=404)
    except ValueError as exc:
        return templates.TemplateResponse(
            request=request,
            name="components/activities/rename_form.html.jinja2",
            context={"activity_id": activity_id, "current_name": name, "error": str(exc), "open_on_error": True},
            status_code=422,
        )
    response = HTMLResponse(content="", status_code=200)
    response.headers["HX-Redirect"] = profiles.canonical_activity_url(user.get("username"), new_slug)
    return response


def activity_delete_confirm_response(request: Request, activity_id: int, owner_id: int) -> HTMLResponse:
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
        name="components/activities/activity_delete_confirm.html.jinja2",
        context={"activity_id": activity_id, "activity_name": row["name"]},
    )


def delete_activity_response(activity_id: int, owner_id: int, user: dict) -> HTMLResponse:
    with db.connect() as conn:
        conn.execute("BEGIN")
        categories.delete_activity(conn, owner_id=owner_id, activity_id=activity_id)
    response = HTMLResponse(content="", status_code=200)
    response.headers["HX-Redirect"] = _home_url_for(user)
    return response
