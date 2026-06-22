"""Create activity + activity detail (owner dashboard for one activity)."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Annotated, Any

from fastapi import APIRouter, Cookie, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse

from app import ui_strings
from app.auth import sessions, users
from app.models import db
from app.routes.web._calendar_context import _resolve_comment_deep_link
from app.routes.web._contexts import _build_card_context, _field_defs_for_activity
from app.routes.web._history_context import _build_field_stats_context, _build_history_context
from app.routes.web._shared import _current_user, _home_url_for, templates
from app.services import categories, competition, profiles, stats

router = APIRouter()


# ---------------------------------------------------------------------------
# Create activity
# ---------------------------------------------------------------------------


@router.get("/activities/new", response_class=HTMLResponse)
async def new_activity(
    request: Request,
    session: Annotated[str | None, Cookie(alias=sessions.COOKIE_NAME)] = None,
) -> HTMLResponse:
    """Manual create-activity form: name only, rendered as an inline sheet.

    Both home-page entry points ("+ Add activity" and "start from scratch")
    open this same HTMX sheet fragment — there is no standalone full-page
    create-activity route.
    """
    user = _current_user(session)
    if user is None:
        return RedirectResponse(url="/", status_code=303)

    return templates.TemplateResponse(
        request=request,
        name="components/category_sheet.html.jinja2",
        context={},
    )


@router.post("/activities", response_class=HTMLResponse)
async def create_activity(
    request: Request,
    name: Annotated[str, Form()],
    session: Annotated[str | None, Cookie(alias=sessions.COOKIE_NAME)] = None,
) -> HTMLResponse:
    """Create a general-log activity (manual form or one-tap example adopt).

    Returns the new ``activity_card`` fragment for an HTMX swap into
    ``#cards``, or a 303 to ``/home`` for the no-JS path.
    """
    user = _current_user(session)
    if user is None:
        return RedirectResponse(url="/", status_code=303)
    owner_id = int(user["id"])

    name = name.strip()
    if not name:
        if request.headers.get("HX-Request") == "true":
            return templates.TemplateResponse(
                request=request,
                name="components/category_form.html.jinja2",
                context={
                    "hx_post": "/activities",
                    "hx_target": "#cards",
                    "hx_swap": "beforeend",
                    "name_error": ui_strings.ACTIVITY_FORM_NAME_REQUIRED,
                },
                status_code=400,
            )

        return RedirectResponse(url="/home", status_code=303)

    tz = users.get_user_timezone(owner_id)
    result = categories.create_activity(owner_id, name=name)

    with db.connect() as conn:
        conn.execute("BEGIN")
        sub_row = conn.execute(
            """SELECT st.id, st.name, st.count_mode, st.cached_count, st.cached_streak,
                      st.last_entry_at, st.category_id, c.name AS category_name, c.icon AS icon
                 FROM activity st
                 JOIN category c ON c.id = st.category_id
                WHERE st.id = ? AND st.owner_id = ?""",
            (result["activity_id"], owner_id),
        ).fetchone()
        card = _build_card_context(conn, owner_id, sub_row, tz=tz, linked=True)

    if request.headers.get("HX-Request") == "true":
        return templates.TemplateResponse(
            request=request,
            name="components/activity_card.html.jinja2",
            context={"card": card},
        )

    return RedirectResponse(url=_home_url_for(user), status_code=303)


# ---------------------------------------------------------------------------
# Activity detail
# ---------------------------------------------------------------------------


@router.get("/activities/{activity_id}", response_class=HTMLResponse, response_model=None)
async def activity_detail(
    request: Request,
    activity_id: int,
    session: Annotated[str | None, Cookie(alias=sessions.COOKIE_NAME)] = None,
) -> HTMLResponse | RedirectResponse:
    """Activity detail screen: card + (for tournament activities) competition stats.

    Active activities with a slug redirect 301 to ``/@{username}/{slug}``
    (the canonical public/private unified URL).  Archived activities, or those
    somehow without a slug, render the dashboard in place — this preserves access
    to archived activities that are no longer addressable via the public route.

    Competition stats only render for activities whose recipe includes a
    ``match_list`` field (e.g. 검도 / 시합).
    """
    user = _current_user(session)
    if user is None:
        return RedirectResponse(url="/", status_code=303)
    owner_id = int(user["id"])
    tz = users.get_user_timezone(owner_id)

    with db.connect() as conn:
        conn.execute("BEGIN")
        row = profiles.get_activity_for_owner(conn, activity_id=activity_id, owner_id=owner_id)
        if row is None:
            return HTMLResponse(status_code=404)

        # Redirect active, slugged activities to the canonical URL —
        # only when the owner has a username (guests have username=None and
        # have no public profile URL to redirect to).
        username = user.get("username")
        if username is not None and row["slug"] is not None and row["archived_at"] is None:
            return RedirectResponse(
                url=profiles.canonical_activity_url(username, row["slug"]), status_code=301
            )

        sub_row = conn.execute(
            """SELECT st.id, st.name, st.slug, st.count_mode, st.cached_count, st.cached_streak,
                      st.last_entry_at, st.category_id, c.name AS category_name, c.icon AS icon
                 FROM activity st
                 JOIN category c ON c.id = st.category_id
                WHERE st.id = ? AND st.owner_id = ?""",
            (activity_id, owner_id),
        ).fetchone()
        if sub_row is None:
            return HTMLResponse(status_code=404)
        field_defs = _field_defs_for_activity(conn, activity_id)
        has_match_list = any(fd["kind"] == "match_list" for fd in field_defs)
        card = _build_card_context(conn, owner_id, sub_row, tz=tz)

    context: dict[str, Any] = {"card": card}

    if has_match_list:
        context["record"] = competition.record(owner_id, activity_id)
        context["timeline"] = competition.results_timeline(owner_id, activity_id)
        context["head_to_head"] = competition.head_to_head(owner_id, activity_id)
    else:
        context["record"] = None
        context["timeline"] = []
        context["head_to_head"] = []

    today = datetime.now(UTC).date()

    # `?c={entry_id}` (a notification click-through) pre-selects that entry's
    # calendar day and pre-expands its comment thread. Silently ignored — no
    # error, no 500 — when missing/non-numeric/unknown/cross-activity.
    deep_link = _resolve_comment_deep_link(
        request.query_params.get("c"), activity_id=activity_id, owner_id=owner_id, tz=tz
    )
    expand_comment_entry_id, selected_day = deep_link if deep_link is not None else (None, None)

    context["activity_id"] = activity_id
    context["counts"] = stats.counts(activity_id, owner_id, tz=tz)
    context["streaks"] = stats.streaks(activity_id, owner_id, tz=tz)
    context["history"] = _build_history_context(
        activity_id,
        owner_id,
        period="month",
        anchor=selected_day or today,
        tz=tz,
        selected=selected_day,
        is_owner=True,
        can_comment=True,
        username=username,
        slug=sub_row["slug"],
        expand_comment_entry_id=expand_comment_entry_id,
    )
    context["field_stats"] = _build_field_stats_context(activity_id, owner_id, field_defs, tz=tz)
    context["public_notice"] = None
    context["preview_visitor_url"] = None
    context["is_owner"] = True

    return templates.TemplateResponse(
        request=request,
        name="web/activity_detail.html.jinja2",
        context=context,
    )
