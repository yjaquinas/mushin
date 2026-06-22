"""Handler bodies for ``app/routes/public/activity_detail.py``.

Internal companion module (route-structure rule, option 2) — the route
declaration/dispatch stays in ``activity_detail.py``; the two heavier render
paths (owner dashboard continuation, read-only public view) live here so
``activity_detail.py`` stays under the 300-line ceiling. Not a route group of
its own: no ``APIRouter`` here, no direct import from outside this package.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from urllib.parse import quote

from fastapi import Request
from fastapi.responses import HTMLResponse

from app import ui_strings
from app.models import db
from app.routes.public._contexts import templates
from app.routes.web import (
    _build_card_context,
    _build_field_stats_context,
    _build_history_context,
    _field_defs_for_activity,
    _resolve_comment_deep_link,
)
from app.services import competition, profiles, stats


def _render_owner_activity_detail(
    request: Request,
    *,
    username: str,
    slug: str,
    owner_id: int,
    activity_id: int,
    user: Any,
    card: Any,
    field_defs: list[Any],
    has_match_list: bool,
    can_comment: bool,
    tz: Any,
) -> HTMLResponse:
    """Build + render the full owner-dashboard ``activity_detail.html.jinja2``.

    Called by ``public_activity`` once the connection used to resolve
    ``user``/``card``/``field_defs`` has been closed — this function opens
    its own (second) connection only for the anonymous-viewpoint public-notice
    check, matching the original inline behavior exactly.
    """
    today = datetime.now(UTC).date()

    # `?c={entry_id}` (a notification click-through) pre-selects that entry's
    # calendar day and pre-expands its comment thread. Silently ignored — no
    # error, no 500 — when missing/non-numeric/unknown/cross-activity.
    deep_link = _resolve_comment_deep_link(
        request.query_params.get("c"), activity_id=activity_id, owner_id=owner_id, tz=tz
    )
    expand_comment_entry_id, selected_day = deep_link if deep_link is not None else (None, None)

    owner_context: dict[str, Any] = {
        "card": card,
    }

    if has_match_list:
        owner_context["record"] = competition.record(owner_id, activity_id)
        owner_context["timeline"] = competition.results_timeline(owner_id, activity_id)
        owner_context["head_to_head"] = competition.head_to_head(owner_id, activity_id)
    else:
        owner_context["record"] = None
        owner_context["timeline"] = []
        owner_context["head_to_head"] = []

    owner_context["activity_id"] = activity_id
    owner_context["counts"] = stats.counts(activity_id, owner_id, tz=tz)
    owner_context["streaks"] = stats.streaks(activity_id, owner_id, tz=tz)
    owner_context["history"] = _build_history_context(
        activity_id,
        owner_id,
        period="month",
        anchor=selected_day or today,
        tz=tz,
        selected=selected_day,
        is_owner=True,
        can_comment=can_comment,
        username=username,
        slug=slug,
        expand_comment_entry_id=expand_comment_entry_id,
    )
    owner_context["field_stats"] = _build_field_stats_context(
        activity_id, owner_id, field_defs, tz=tz
    )
    owner_context["username"] = username
    owner_context["slug"] = slug

    # Public-notice strip — only when the account is public so the owner
    # knows the page (including notes) is visible to anyone with the link.
    # Re-derive via the capability helper (anonymous viewpoint) rather than
    # reading user["visibility"] directly.
    with db.connect() as conn:
        conn.execute("BEGIN")
        anon_cap = profiles.viewer_capability(conn, current_user_id=None, profile_user=user)

    if anon_cap == "public":
        owner_context["public_notice"] = ui_strings.ACTIVITY_PUBLIC_NOTICE
        base_url = profiles.canonical_activity_url(username, slug)
        owner_context["preview_visitor_url"] = base_url + "?as=stranger"
        owner_context["preview_connection_url"] = base_url + "?as=connection"
    else:
        owner_context["public_notice"] = None
        owner_context["preview_visitor_url"] = None
        owner_context["preview_connection_url"] = None

    owner_context["is_owner"] = True

    return templates.TemplateResponse(
        request=request,
        name="web/activity_detail.html.jinja2",
        context=owner_context,
    )


def _render_readonly_activity_detail(
    request: Request,
    conn: Any,
    username: str,
    slug: str,
    owner_id: int,
    activity_id: int,
    *,
    tz: Any,
    current_user_id: int | None = None,
    profile_user: Any = None,
) -> HTMLResponse:
    """Build + render the read-only ``public_activity.html.jinja2`` response.

    Shared by the real connected/public visitor branch and the owner's
    ``?as=stranger``/``?as=connection`` preview — both render identically
    once the caller has confirmed the viewer (real or previewed) may see
    detail.
    """
    sub_row = conn.execute(
        """SELECT st.id, st.name, st.count_mode, st.cached_count, st.cached_streak,
                  st.last_entry_at, st.category_id,
                  c.name AS category_name, c.icon AS icon
             FROM activity st
             JOIN category c ON c.id = st.category_id
            WHERE st.id = ? AND st.owner_id = ?""",
        (activity_id, owner_id),
    ).fetchone()
    field_defs = _field_defs_for_activity(conn, activity_id)
    has_match_list = any(fd["kind"] == "match_list" for fd in field_defs)
    card = _build_card_context(conn, owner_id, sub_row, tz=tz, linked=False)

    context: dict[str, Any] = {
        "username": username,
        "view_mode": "public",
        "card": card,
        "slug": slug,
    }
    if has_match_list:
        context["record"] = competition.record(owner_id, activity_id)
        context["timeline"] = competition.results_timeline(owner_id, activity_id)
        context["head_to_head"] = competition.head_to_head(owner_id, activity_id)
    else:
        context["record"] = None
        context["timeline"] = []
        context["head_to_head"] = []

    context["counts"] = stats.counts(activity_id, owner_id, tz=tz)
    context["streaks"] = stats.streaks(activity_id, owner_id, tz=tz)
    context["field_stats"] = _build_field_stats_context(activity_id, owner_id, field_defs, tz=tz)

    # Real (non-preview) visitor only — a preview render never grants a
    # comment-write affordance, since posting "as" a downgraded persona
    # while actually authenticated as the owner would be a confusing,
    # capability-bypassing surface.
    can_comment = bool(
        profile_user is not None
        and profiles.can_comment_on_entry(
            conn,
            current_user_id=current_user_id,
            profile_user=profile_user,
            activity_id=activity_id,
        )
    )
    context["can_comment"] = can_comment

    # An anonymous (no session) real visitor — never the owner's
    # ?as=stranger/?as=connection preview, which calls this function with no
    # `profile_user` at all — on an activity already cleared as readable here
    # (this branch only runs for connected/public/preview capabilities; a
    # blocked/limited viewer 404s/redirects in `public_activity` before this
    # function is ever reached) gets a same-origin `/login?next=...` link
    # instead of a silently-missing composer. `safe_next_path` is the only
    # thing that decides "safe" here, so this can never become an open
    # redirect even though `request.url.path` is otherwise untrusted input.
    login_redirect_url = None
    is_anonymous_real_visitor = profile_user is not None and current_user_id is None
    if is_anonymous_real_visitor:
        target = profiles.safe_next_path(request.url.path)
        login_redirect_url = f"/login?next={quote(target or '', safe='')}"
    context["login_redirect_url"] = login_redirect_url

    # Merged calendar/log view — the same `components/history.html.jinja2`
    # partial the owner dashboard renders (per .claude/rules/web-templates.md,
    # this shared-partial sharing is sanctioned; the safety boundary is this
    # route's context shape, not the template's `{% if %}`s). `is_owner` is
    # explicitly `False` and NO write-action context key (entry edit/delete
    # URL, log-new-entry trigger, etc.) is constructed or present anywhere in
    # this read-only path — `_build_history_context` itself takes no such
    # argument, and `is_owner=False` here is what suppresses the edit pencil
    # in `period_log.html.jinja2`/`day_entries.html.jinja2`.
    today = datetime.now(UTC).date()
    context["activity_id"] = activity_id
    context["history"] = _build_history_context(
        activity_id,
        owner_id,
        period="month",
        anchor=today,
        tz=tz,
        is_owner=False,
        can_comment=can_comment,
        username=username,
        slug=slug,
        login_redirect_url=login_redirect_url,
    )

    return templates.TemplateResponse(
        request=request,
        name="web/public_activity.html.jinja2",
        context=context,
    )
