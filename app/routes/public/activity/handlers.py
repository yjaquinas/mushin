"""Handler bodies for ``app/routes/public/activity_detail.py``."""

from __future__ import annotations

from datetime import datetime
from typing import Any
from urllib.parse import quote

from fastapi import Request
from fastapi.responses import HTMLResponse

from app import ui_strings
from app.models import db
from app.routes.public.common.contexts import templates
from app.routes.web import (
    _build_card_context,
    _build_field_stats_context,
    _build_history_context,
    _build_history_tags,
    _field_defs_for_activity,
    _resolve_comment_deep_link,
)
from app.services.entries import stats
from app.services.search import indexing
from app.services.social import profiles
from app.ui_strings import META_DESCRIPTION_ACTIVITY


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
    """Build + render the full owner-dashboard ``activity_detail.html.jinja2``."""
    today = datetime.now(tz).date()

    expand_comment_entry_id = _resolve_comment_deep_link(
        request.query_params.get("entry_id"), activity_id=activity_id, owner_id=owner_id
    )

    owner_context: dict[str, Any] = {
        "card": card,
    }

    owner_context["record"] = None
    owner_context["timeline"] = []
    owner_context["head_to_head"] = []

    owner_context["activity_id"] = activity_id
    cs = stats.card_stats(activity_id, owner_id, tz=tz)
    owner_context["counts"] = cs["counts"]
    owner_context["streaks"] = cs["streaks"]
    owner_context["heatmap"] = cs["heatmap"]
    owner_context["history"] = _build_history_context(
        activity_id,
        owner_id,
        period="month",
        anchor=today,
        tz=tz,
        is_owner=True,
        can_comment=can_comment,
        username=username,
        slug=slug,
        expand_comment_entry_id=expand_comment_entry_id,
    )
    owner_context["top_tags"] = _build_history_tags(owner_context["history"], tz=tz)
    owner_context["field_stats"] = _build_field_stats_context(
        activity_id, owner_id, field_defs, tz=tz
    )
    owner_context["username"] = username
    owner_context["slug"] = slug

    with db.connect() as conn:
        conn.execute("BEGIN")
        anon_cap = profiles.viewer_capability(conn, current_user_id=None, profile_user=user)

    if anon_cap == "public":
        owner_context["public_notice"] = ui_strings.ACTIVITY_PUBLIC_NOTICE
    else:
        owner_context["public_notice"] = None

    owner_context["is_owner"] = True
    owner_context["current_page"] = "profile"
    owner_context["page_title"] = username
    owner_context["meta_robots"] = "noindex, nofollow"
    owner_context["share_url"] = profiles.canonical_activity_url(username, slug)
    owner_context["share_label"] = f"@{username} / {card['name']}"
    owner_context["share_copied_text"] = f"Link to @{username}/{slug} copied"
    owner_context["share_failed_text"] = "Couldn't share the link."
    return templates.TemplateResponse(
        request=request,
        name="web/activity/detail.html.jinja2",
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
    """Build + render the read-only ``public_activity.html.jinja2`` response."""
    sub_row = conn.execute(
        """SELECT st.id, st.name, st.count, st.streak,
                  st.last_entry_at, st.icon, st.secret
             FROM activity st
            WHERE st.id = ? AND st.owner_id = ?""",
        (activity_id, owner_id),
    ).fetchone()
    field_defs = _field_defs_for_activity(conn, activity_id)
    card = _build_card_context(conn, owner_id, sub_row, tz=tz, linked=False)

    context: dict[str, Any] = {
        "username": username,
        "view_mode": "public",
        "card": card,
        "slug": slug,
    }
    context["record"] = None
    context["timeline"] = []
    context["head_to_head"] = []

    cs = stats.card_stats(activity_id, owner_id, tz=tz)
    context["counts"] = cs["counts"]
    context["streaks"] = cs["streaks"]
    context["heatmap"] = cs["heatmap"]
    context["field_stats"] = _build_field_stats_context(activity_id, owner_id, field_defs, tz=tz)

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

    login_redirect_url = None
    is_anonymous_real_visitor = profile_user is not None and current_user_id is None
    if is_anonymous_real_visitor:
        target = profiles.safe_next_path(str(request.url.path))
        login_redirect_url = f"/?next={quote(target or '', safe='')}"
    context["login_redirect_url"] = login_redirect_url
    context["current_page"] = "social"
    context["page_title"] = username
    context["share_url"] = profiles.canonical_activity_url(username, slug)
    context["share_label"] = f"@{username} / {card['name']}"
    context["share_copied_text"] = f"Link to @{username}/{slug} copied"
    context["share_failed_text"] = "Couldn't share the link."
    anon_cap = (
        profiles.viewer_capability(conn, current_user_id=None, profile_user=profile_user)
        if profile_user is not None
        else None
    )
    is_canonical_public_path = str(request.url.path) == profiles.canonical_activity_url(username, slug)
    is_indexable = profile_user is not None and indexing.is_indexable_activity(
        conn, owner_id=owner_id, activity_id=activity_id, profile_user=profile_user
    )
    context["meta_robots"] = "index, follow" if anon_cap == "public" and is_canonical_public_path and is_indexable else "noindex, nofollow"

    today = datetime.now(tz).date()

    expand_comment_entry_id = _resolve_comment_deep_link(
        request.query_params.get("entry_id"), activity_id=activity_id, owner_id=owner_id
    )

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
        expand_comment_entry_id=expand_comment_entry_id,
    )
    context["top_tags"] = _build_history_tags(context["history"], tz=tz)
    activity_name = card.get("name", slug)
    context["meta_description"] = META_DESCRIPTION_ACTIVITY.format(activity=activity_name, username=username)
    context["og_title"] = f"{activity_name} · {username} · {ui_strings.APP_NAME}"
    context["og_description"] = META_DESCRIPTION_ACTIVITY.format(activity=activity_name, username=username)
    context["og_type"] = "article"

    return templates.TemplateResponse(
        request=request,
        name="web/activity/public_detail.html.jinja2",
        context=context,
    )
