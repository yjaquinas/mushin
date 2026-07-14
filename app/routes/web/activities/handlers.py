"""Handler bodies for activity creation."""

from __future__ import annotations

import json

from fastapi import Request
from fastapi.responses import HTMLResponse, RedirectResponse

from app import ui_strings
from app.models import db
from app.routes.web.common import templates
from app.services.activities import categories
from app.services.plans import ActivityLimitError, SecretActivityForbiddenError, get_all_plan_configs, get_plan_config
from app.services.social import profiles


def new_activity_response(request: Request, user: dict) -> HTMLResponse:
    """Return the create-activity sheet, or a toast if the user's plan limit is reached."""
    owner_id = int(user["id"])
    with db.connect() as conn:
        from app.services.plans import get_user_plan_config
        cfg = get_user_plan_config(conn, owner_id)
        max_activities = cfg["max_activities"] if cfg else 3
        secret_allowed = cfg["secret_activities"] if cfg else False
        count = conn.execute(
            "SELECT COUNT(*) FROM activity WHERE owner_id = ? AND archived_at IS NULL",
            (owner_id,),
        ).fetchone()[0]
        if count >= max_activities:
            premium_cfg = get_plan_config(conn, "premium")
            premium_max = premium_cfg["max_activities"] if premium_cfg else 20
            response = HTMLResponse(content="")
            response.headers["HX-Trigger"] = json.dumps({
                "show-toast": {
                    "message": ui_strings.ACTIVITY_LIMIT_TOAST.format(max=max_activities, premium_max=premium_max),
                    "variant": "warning",
                }
            })
            response.headers["HX-Reswap"] = "none"
            return response

    return templates.TemplateResponse(
        request=request,
        name="components/activities/activity_sheet.html.jinja2",
        context={
            "secret_allowed": secret_allowed,
            "secret_toast_message": ui_strings.SECRET_ACTIVITY_TOAST,
        },
    )


def create_activity_response(request: Request, user: dict, name: str, secret: bool = False) -> HTMLResponse | RedirectResponse:
    owner_id = int(user["id"])
    name = name.strip()
    if not name:
        return _activity_form_error(request, ui_strings.ACTIVITY_FORM_NAME_REQUIRED)
    if len(name) < 2:
        response = HTMLResponse(content="", status_code=400)
        response.headers["HX-Trigger"] = json.dumps({"show-toast": {"message": ui_strings.ACTIVITY_FORM_NAME_TOO_SHORT, "variant": "error"}})
        response.headers["HX-Reswap"] = "none"
        return response

    with db.connect() as conn:
        conn.execute("BEGIN")
        if conn.execute(
            "SELECT 1 FROM activity"
            " WHERE owner_id = ? AND LOWER(name) = LOWER(?) AND archived_at IS NULL"
            " LIMIT 1",
            (owner_id, name),
        ).fetchone():
            return _activity_form_error(request, ui_strings.ACTIVITY_FORM_NAME_DUPLICATE)

    try:
        result = categories.create_activity(owner_id, name=name, secret=secret)
    except ActivityLimitError:
        with db.connect() as conn:
            plans = get_all_plan_configs(conn)
        basic = next((p for p in plans if p["plan"] == "basic"), {})
        premium = next((p for p in plans if p["plan"] == "premium"), {})
        max_act = basic.get("max_activities", 3)
        premium_max = premium.get("max_activities", 20)
        response = HTMLResponse(content="", status_code=400)
        response.headers["HX-Trigger"] = json.dumps({
            "show-toast": {
                "message": ui_strings.ACTIVITY_LIMIT_TOAST.format(max=max_act, premium_max=premium_max),
                "variant": "warning",
            }
        })
        response.headers["HX-Reswap"] = "none"
        return response
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
        context={
            "hx_post": "/activities",
            "hx_target": "#profile-target-activity-cards",
            "hx_swap": "beforeend",
            "name_error": message,
        },
        status_code=400,
    )
