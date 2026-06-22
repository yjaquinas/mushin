"""History fragment + stats/field-stats refresh fragments for an activity."""

from __future__ import annotations

import json
from datetime import UTC, date, datetime
from typing import Annotated
from urllib.parse import quote

from fastapi import APIRouter, Cookie, Request
from fastapi.responses import HTMLResponse

from app.auth import sessions, users
from app.models import db
from app.routes.web._contexts import _field_defs_for_activity
from app.routes.web._history_context import _build_field_stats_context, _build_history_context
from app.routes.web._shared import _current_user, templates
from app.services import _db, profiles, stats

router = APIRouter()


@router.get("/activities/{activity_id}/history", response_class=HTMLResponse)
async def activity_history(
    request: Request,
    activity_id: int,
    period: str,
    anchor: str | None = None,
    day: str | None = None,
    session: Annotated[str | None, Cookie(alias=sessions.COOKIE_NAME)] = None,
) -> HTMLResponse:
    """Render the history fragment (visual + log) for *period* at *anchor*.

    *day*, when given, selects a calendar cell (month period) and includes
    that day's entries in the returned fragment.

    Shared by the owner dashboard AND every interactive control inside the
    same ``components/history.html.jinja2`` partial rendered read-only on
    ``/@{username}/{slug}`` (period tabs, prev/next nav, day-select taps, the
    "Calendar" back-control) — so the viewer here is not assumed to be the
    activity's owner. The activity's real owner is resolved from
    ``activity_id`` alone, then ``profiles.viewer_capability`` /
    ``can_view_activity_detail`` (the same fail-closed authority
    ``app/routes/public/`` uses for the initial page load) decides whether
    *this* viewer — owner, fellow, public visitor, or anonymous — may see it
    at all. A denied viewer (blocked, or limited-without-detail-access) gets
    404, matching the no-existence-oracle behavior the rest of the read-only
    surface uses; this never reveals whether the activity exists to someone
    who isn't allowed to know.

    Owner behavior is unchanged byte-for-byte: ``is_owner=True``,
    ``can_comment=True``, username/slug from the owner's own row. A non-owner
    viewer gets ``is_owner=False`` and ``can_comment`` from
    ``can_comment_on_entry`` (always ``False`` for an anonymous viewer, since
    that helper requires a session) — and, per the context-shape safety rule,
    no write-action context key is ever constructed for a non-owner response.
    """
    current_uid = sessions.read_uid(session)

    if period not in ("week", "month", "year", "all"):
        return HTMLResponse(status_code=400)

    if anchor is None:
        anchor_date = datetime.now(UTC).date()
    else:
        try:
            anchor_date = date.fromisoformat(anchor)
        except ValueError:
            return HTMLResponse(status_code=400)

    if day is None:
        selected_date = None
    else:
        try:
            selected_date = date.fromisoformat(day)
        except ValueError:
            return HTMLResponse(status_code=400)

    with db.connect() as conn:
        conn.execute("BEGIN")
        owner_row = conn.execute(
            """SELECT u.id, u.username, u.visibility, u.auth_provider, u.consent_seen_at,
                      st.slug AS activity_slug
                 FROM activity st
                 JOIN user u ON u.id = st.owner_id
                WHERE st.id = ?""",
            (activity_id,),
        ).fetchone()
        if owner_row is None:
            return HTMLResponse(status_code=404)

        profile_user = {
            "id": owner_row["id"],
            "username": owner_row["username"],
            "visibility": owner_row["visibility"],
            "auth_provider": owner_row["auth_provider"],
            "consent_seen_at": owner_row["consent_seen_at"],
        }
        owner_id = int(profile_user["id"])

        cap = profiles.viewer_capability(
            conn, current_user_id=current_uid, profile_user=profile_user
        )
        is_owner = cap == "owner"

        if not is_owner and not profiles.can_view_activity_detail(
            conn, current_user_id=current_uid, profile_user=profile_user
        ):
            # "blocked" or "limited" (non-connected visitor on a non-public
            # account) — fail closed, no existence oracle.
            return HTMLResponse(status_code=404)

        can_comment = (
            True
            if is_owner
            else profiles.can_comment_on_entry(
                conn,
                current_user_id=current_uid,
                profile_user=profile_user,
                activity_id=activity_id,
            )
        )

    tz = users.get_user_timezone(owner_id)
    username = profile_user["username"]
    slug = owner_row["activity_slug"]

    # Anonymous (no session) real visitor on an already-cleared-readable
    # activity (blocked/limited 404s above before this point) — same
    # "log in to comment" prompt the initial page load gets
    # (`public/_activity_detail_handlers.py::_render_readonly_activity_detail`),
    # threaded through this interactive fragment route too, since a visitor
    # can reach a fresh period/day swap without ever re-loading the full
    # page. `next` points at the canonical activity page (not this fragment
    # URL, which isn't a navigable page on its own), built from
    # `username`/`slug` rather than `request.url.path` — both are
    # already-trusted server-derived strings, so `safe_next_path` here is
    # defense in depth, not the primary guarantee.
    login_redirect_url = None
    if not is_owner and current_uid is None and username is not None and slug is not None:
        target = profiles.safe_next_path(profiles.canonical_activity_url(username, slug))
        login_redirect_url = f"/login?next={quote(target or '', safe='')}"

    history_ctx = _build_history_context(
        activity_id,
        owner_id,
        period=period,
        anchor=anchor_date,
        tz=tz,
        selected=selected_date,
        is_owner=is_owner,
        can_comment=can_comment,
        username=username,
        slug=slug,
        login_redirect_url=login_redirect_url,
    )
    response = templates.TemplateResponse(
        request=request,
        name="components/history.html.jinja2",
        context={
            "activity_id": activity_id,
            "history": history_ctx,
            "is_owner": is_owner,
            "can_comment": can_comment,
            "username": username,
            "slug": slug,
            "login_redirect_url": login_redirect_url,
        },
    )
    if period != "all":
        response.headers["HX-Trigger"] = json.dumps({"history-period-changed": {"period": period}})
    return response


@router.get("/activities/{activity_id}/stats-summary", response_class=HTMLResponse)
async def stats_summary_fragment(
    request: Request,
    activity_id: int,
    session: Annotated[str | None, Cookie(alias=sessions.COOKIE_NAME)] = None,
) -> HTMLResponse:
    """Stats summary fragment for HTMX refresh after a log."""
    user = _current_user(session)
    if user is None:
        return HTMLResponse(status_code=401)
    owner_id = int(user["id"])
    tz = users.get_user_timezone(owner_id)
    with db.connect() as conn:
        conn.execute("BEGIN")
        if not _db.exists(conn, "activity", owner_id, where="id = ?", params=(activity_id,)):
            return HTMLResponse(status_code=404)
    return templates.TemplateResponse(
        request=request,
        name="components/stats_summary.html.jinja2",
        context={
            "activity_id": activity_id,
            "counts": stats.counts(activity_id, owner_id, tz=tz),
            "streaks": stats.streaks(activity_id, owner_id, tz=tz),
            "is_owner": True,
        },
    )


@router.get("/activities/{activity_id}/field-stats", response_class=HTMLResponse)
async def field_stats_fragment(
    request: Request,
    activity_id: int,
    period: str = "month",
    session: Annotated[str | None, Cookie(alias=sessions.COOKIE_NAME)] = None,
) -> HTMLResponse:
    """Tag-frequency + scale-distribution fragment for HTMX refresh after a log or period change."""
    user = _current_user(session)
    if user is None:
        return HTMLResponse(status_code=401)
    if period not in ("week", "month", "year"):
        period = "month"
    owner_id = int(user["id"])
    tz = users.get_user_timezone(owner_id)
    with db.connect() as conn:
        conn.execute("BEGIN")
        if not _db.exists(conn, "activity", owner_id, where="id = ?", params=(activity_id,)):
            return HTMLResponse(status_code=404)
        field_defs = _field_defs_for_activity(conn, activity_id)
    return templates.TemplateResponse(
        request=request,
        name="components/field_stats.html.jinja2",
        context={
            "activity_id": activity_id,
            "field_stats": _build_field_stats_context(
                activity_id, owner_id, field_defs, tz=tz, period=period
            ),
            "is_owner": True,
        },
    )
