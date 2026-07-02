"""Rename and category-delete admin actions for an activity."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Cookie, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse

from app.auth import sessions
from app.models import db
from app.routes.web._shared import _current_user, _home_url_for, templates
from app.services import _db, categories, profiles
from app.services.entries import SubTallyNotFoundError

router = APIRouter()


# ---------------------------------------------------------------------------
# Rename dialog
# ---------------------------------------------------------------------------


@router.get("/activities/{activity_id}/rename-form", response_class=HTMLResponse)
async def rename_form(
    request: Request,
    activity_id: int,
    session: Annotated[str | None, Cookie(alias=sessions.COOKIE_NAME)] = None,
) -> HTMLResponse:
    """Return the rename-dialog fragment for *activity_id*."""
    user = _current_user(session)
    if user is None:
        return HTMLResponse(status_code=401)
    owner_id = int(user["id"])

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


@router.post("/activities/{activity_id}/rename", response_class=HTMLResponse, response_model=None)
async def rename_activity(
    request: Request,
    activity_id: int,
    name: Annotated[str, Form()],
    session: Annotated[str | None, Cookie(alias=sessions.COOKIE_NAME)] = None,
) -> HTMLResponse:
    """Rename *activity_id* and redirect to the new canonical URL.

    On success: 200 with ``HX-Redirect`` to ``/@{username}/{new_slug}``.
    On ``SubTallyNotFoundError``: 404.
    On ``ValueError`` (empty / too-long name): return the rename dialog fragment
    with an inline error message and auto-open it again.
    """
    user = _current_user(session)
    if user is None:
        return RedirectResponse(url="/", status_code=303)
    owner_id = int(user["id"])

    try:
        with db.connect() as conn:
            conn.execute("BEGIN")
            new_slug = categories.rename_activity(
                conn, owner_id=owner_id, activity_id=activity_id, new_name=name
            )
    except SubTallyNotFoundError:
        return HTMLResponse(status_code=404)
    except ValueError as exc:
        # Return the inline form with a validation error — never a bare 400.
        return templates.TemplateResponse(
            request=request,
            name="components/rename_form.html.jinja2",
            context={
                "activity_id": activity_id,
                "current_name": name,
                "error": str(exc),
                "open_on_error": True,
            },
            status_code=422,
        )

    username = user.get("username")
    response = HTMLResponse(content="", status_code=200)
    response.headers["HX-Redirect"] = profiles.canonical_activity_url(username, new_slug)
    return response


# ---------------------------------------------------------------------------
# Category delete dialog
# ---------------------------------------------------------------------------


@router.get("/activities/{activity_id}/delete-confirm", response_class=HTMLResponse)
async def category_delete_confirm(
    request: Request,
    activity_id: int,
    session: Annotated[str | None, Cookie(alias=sessions.COOKIE_NAME)] = None,
) -> HTMLResponse:
    """Return the delete-confirm dialog for the category that owns *activity_id*.

    Ownership check: the sub-tally must exist and belong to the session user — 404 otherwise.
    """
    user = _current_user(session)
    if user is None:
        return HTMLResponse(status_code=401)
    owner_id = int(user["id"])

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


@router.post("/activities/{activity_id}/delete", response_class=HTMLResponse)
async def delete_category(
    activity_id: int,
    session: Annotated[str | None, Cookie(alias=sessions.COOKIE_NAME)] = None,
) -> HTMLResponse:
    """Delete the category (and all sub-tallies/entries) that owns *activity_id*.

    On success (or if already gone): ``HX-Redirect`` to the owner's home/profile
    URL with status 200. Non-owner or unknown sub-tally: 404.
    """
    user = _current_user(session)
    if user is None:
        return HTMLResponse(status_code=401)
    owner_id = int(user["id"])

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
