"""Public profile routes (``/@{username}``, ``/@{username}/{slug}``).

``/@{username}`` is the unified profile route: when the viewer is the
profile's owner (session matches the profile user id), it renders the same
owner-dashboard context/template ``GET /home`` does (write affordances,
``web/home.html.jinja2``). For every other viewer it uses the read-only
public template (``web/public_profile.html.jinja2``) at one of two read
states — full (``connected``/``public``) or the character-sheet-only
``limited`` view.

The slug route (``/@{username}/{slug}``) is unified similarly: when the
viewer is the profile's owner, it renders the full owner-dashboard template
(``activity_detail.html.jinja2``) with all write affordances. For every
other viewer that can see detail (``connected``/``public``) it uses the
read-only public template (``web/public_activity.html.jinja2``); a
``limited`` viewer is 303-redirected back to the profile (no detail to
leak), and a ``blocked`` viewer gets the same 404 a non-existent user would.

THE SINGLE VISIBILITY AUTHORITY
--------------------------------
Both routes drive every visibility decision through
``profiles.viewer_capability`` / ``profiles.can_view_activity_detail`` — the
sole, fail-closed authority (see ``app/services/profiles.py``). Neither
handler reads ``user["visibility"]`` directly; the owner's two-mode preview
(``?as=stranger`` / ``?as=connection``) re-derives the previewed capability
by calling ``viewer_capability`` with a substitute ``current_user_id`` (or a
literal ``"connected"`` override) rather than ever branching on the raw
column.

Session handling: routes read the ``mushin_session`` cookie via
``app.auth.sessions.read_uid`` and delegate the owner-vs-visitor branch to
``profiles.is_owner_viewing`` — a pure, fail-closed helper.  No write actions
ever happen in this module; the owner view merely displays the same
dashboard the private route would.

Business logic stays in ``app/services/``; this module is thin handlers +
the same context-assembly helpers ``app/routes/web.py`` exports.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Annotated, Any
from urllib.parse import quote

from fastapi import APIRouter, Cookie, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates

from app import ui_strings
from app.auth import sessions, users
from app.models import db
from app.routes.web import (
    _build_card_context,
    _build_fellows_context,
    _build_field_stats_context,
    _build_history_context,
    _build_home_context,
    _field_defs_for_activity,
    _format_entry_time,
    _home_url_context,
    _list_sub_tallies,
    _resolve_comment_deep_link,
    _theme_context,
    consent_gate_redirect,
)
from app.services import comments as comments_service
from app.services import competition, connections, entries, profiles, stats
from app.services.comments import CommentNotFoundError, CommentPermissionError
from app.services.entries import EntryNotFoundError

router = APIRouter()

templates = Jinja2Templates(
    directory="app/templates", context_processors=[_theme_context, _home_url_context]
)
templates.env.globals["strings"] = ui_strings
templates.env.filters["format_entry_time"] = _format_entry_time

# Aliases accepted on the ``?as=`` preview query param. ``visitor`` is a
# legacy alias for ``stranger`` so existing links/strings/tests keep working.
_STRANGER_ALIASES = {"stranger", "visitor"}
_CONNECTION_ALIAS = "connection"


def _read_only_profile_context(
    conn: Any,
    username: str,
    owner_id: int,
    *,
    cap: str,
    tz: Any,
    current_uid: int | None,
) -> dict[str, Any]:
    """Assemble the read-only ``public_profile.html.jinja2`` context for *cap*.

    ``cap`` is ``"connected"``, ``"public"``, or ``"limited"`` — never any
    other capability (callers gate on owner/blocked before reaching here).
    Cards are clickable (``linked=True``) for connected/public, and
    non-clickable (``linked=False``) for limited (the character sheet).

    Also threads the fellows section (count, or names only when the viewer
    is themselves a mutual fellow of this profile — never to a stranger) and
    the relationship-state affordance ("Connect" / "Requested" / accept-
    decline / "You're fellows") for a non-owner viewer, per
    ``connections.relationship_state``.
    """
    linked = cap in ("connected", "public")
    sub_tallies = _list_sub_tallies(conn, owner_id)
    cards = [_build_card_context(conn, owner_id, row, tz=tz, linked=linked) for row in sub_tallies]
    fellows_context = _build_fellows_context(owner_id, viewer_id=current_uid, is_owner=False)
    state = (
        connections.relationship_state(current_uid, owner_id) if current_uid is not None else "none"
    )
    return {
        "username": username,
        "view_mode": cap,
        "cards": cards,
        "fellows": fellows_context,
        "state": state,
        "viewer_logged_in": current_uid is not None,
    }


@router.get("/@{username}", response_class=HTMLResponse, response_model=None)
async def profile(
    request: Request,
    username: str,
    session: Annotated[str | None, Cookie(alias=sessions.COOKIE_NAME)] = None,
) -> HTMLResponse | RedirectResponse:
    """Unified profile: owner dashboard or read-only public profile.

    404s for unknown usernames and guests (``profiles.get_public_user``
    returns ``None`` for both). Branch order — entirely driven by
    ``profiles.viewer_capability``, never an inline ``visibility`` check:

      1. ``"owner"``, no preview param → owner dashboard (same context/
         template ``GET /home`` renders), including the one-time
         visibility-consent redirect for non-guest accounts that haven't
         seen it yet.
      1b. ``"owner"`` + ``?as=stranger``/``?as=connection`` → the owner
          previews the read-only view at the downgraded capability; the
          consent-gate redirect is skipped (it's a preview, not real
          navigation).
      2. ``"blocked"`` → 404, identical to a non-existent user (no
         existence oracle).
      3. ``"connected"`` / ``"public"`` → read-only profile, activity cards
         clickable.
      4. ``"limited"`` → the character sheet: same read-only profile, cards
         present (names + levels/progress/counts) but NOT clickable, plus a
         quiet line that the full record opens for fellows.
    """
    current_uid = sessions.read_uid(session)

    with db.connect() as conn:
        conn.execute("BEGIN")
        user = profiles.get_public_user(conn, username)
        if user is None:
            return HTMLResponse(status_code=404)

        owner_id = int(user["id"])
        cap = profiles.viewer_capability(conn, current_user_id=current_uid, profile_user=user)

        preview_as = request.query_params.get("as")
        is_preview = cap == "owner" and preview_as in (_STRANGER_ALIASES | {_CONNECTION_ALIAS})

        if cap == "owner" and not is_preview:
            # ``get_public_user`` returns only a column subset, so re-fetch the
            # full row for the consent gate (it needs visibility +
            # private_redefinition_seen_at). The gate is the single shared
            # authority in web.py — first-run consent then private-redefinition
            # re-consent, never inlined here.
            full_user = users.get_user(owner_id)
            if full_user is not None:
                gate = consent_gate_redirect(full_user)
                if gate is not None:
                    return gate
            tz = users.get_user_timezone(owner_id)
            context = _build_home_context(conn, owner_id, tz)
            return templates.TemplateResponse(
                request=request,
                name="web/home.html.jinja2",
                context=context,
            )

        if is_preview:
            # Re-derive the previewed capability WITHOUT reading visibility
            # directly: a stranger preview asks the helper what an anonymous
            # viewer (current_user_id=None) would see of this same account;
            # a connection preview is the literal "connected" capability. A
            # preview can never raise capability above what a real such
            # viewer would see, because it's computed by the same helper.
            if preview_as == _CONNECTION_ALIAS:
                cap = "connected"
            else:
                cap = profiles.viewer_capability(conn, current_user_id=None, profile_user=user)

        if cap == "blocked":
            return HTMLResponse(status_code=404)

        # In a preview (the owner viewing their own page as a downgraded
        # viewer class), the relationship-state/fellows-names logic must
        # reflect the *previewed* viewer, never the literal owner — so pass
        # None (a stranger has no relationship; "connected" cap already
        # grants linked cards, and the fellows section still shows count
        # only, matching what a real fellow who isn't a mutual fellow of
        # themselves would never need anyway).
        effective_uid = None if is_preview else current_uid

        tz = users.get_user_timezone(owner_id)
        context = _read_only_profile_context(
            conn, username, owner_id, cap=cap, tz=tz, current_uid=effective_uid
        )

    return templates.TemplateResponse(
        request=request,
        name="web/public_profile.html.jinja2",
        context=context,
    )


@router.get("/@{username}/{slug}", response_class=HTMLResponse, response_model=None)
async def public_activity(
    request: Request,
    username: str,
    slug: str,
    session: Annotated[str | None, Cookie(alias=sessions.COOKIE_NAME)] = None,
) -> HTMLResponse | RedirectResponse:
    """Unified activity detail: owner view or read-only public view.

    Branch order (security-critical — do not reorder), entirely driven by
    ``profiles.viewer_capability`` / ``can_view_activity_detail``:

      1. Owner, no preview param → ``activity_detail.html.jinja2`` (full
         dashboard with write affordances); a public-notice strip when the
         account is public.
      1b. Owner + ``?as=stranger``/``?as=connection`` → preview the
          read-only view at the downgraded capability (never more than that
          real viewer class would see).
      2. ``"blocked"`` → 404 (no existence oracle).
      3. ``can_view_activity_detail`` True (``connected``/``public``) →
         read-only ``public_activity.html.jinja2`` — full entries + notes.
      4. ``"limited"`` → 303 redirect to the canonical profile URL. A
         non-connected visitor cannot open detail on a non-public account.

    404s for unknown usernames, guests, or an unresolvable *slug*.
    """
    current_uid = sessions.read_uid(session)

    with db.connect() as conn:
        conn.execute("BEGIN")
        user = profiles.get_public_user(conn, username)
        if user is None:
            return HTMLResponse(status_code=404)

        owner_id = int(user["id"])
        activity_id = profiles.resolve_activity_slug(conn, owner_id, slug)
        if activity_id is None:
            return HTMLResponse(status_code=404)

        cap = profiles.viewer_capability(conn, current_user_id=current_uid, profile_user=user)
        preview_as = request.query_params.get("as")
        is_preview = cap == "owner" and preview_as in (_STRANGER_ALIASES | {_CONNECTION_ALIAS})

        tz = users.get_user_timezone(owner_id)

        # ------------------------------------------------------------------
        # Branch 1 — owner viewing their own activity (not previewing):
        # render the full owner dashboard.
        # ------------------------------------------------------------------
        if cap == "owner" and not is_preview:
            sub_row = conn.execute(
                """SELECT st.id, st.name, st.slug, st.count_mode,
                          st.cached_count, st.cached_streak,
                          st.last_entry_at, st.category_id,
                          c.name AS category_name, c.icon AS icon
                     FROM activity st
                     JOIN category c ON c.id = st.category_id
                    WHERE st.id = ? AND st.owner_id = ?""",
                (activity_id, owner_id),
            ).fetchone()
            field_defs = _field_defs_for_activity(conn, activity_id)
            has_match_list = any(fd["kind"] == "match_list" for fd in field_defs)
            card = _build_card_context(conn, owner_id, sub_row, tz=tz)

            # Owner capability always grants comment permission via
            # `can_comment_on_entry`; threaded into `_build_history_context`
            # below so the merged calendar's per-entry comment toggles render
            # for the owner.
            can_comment = profiles.can_comment_on_entry(
                conn, current_user_id=current_uid, profile_user=user, activity_id=activity_id
            )

        # ------------------------------------------------------------------
        # Branch 1b — owner previewing as a downgraded viewer class.
        # ------------------------------------------------------------------
        elif is_preview:
            if preview_as == _CONNECTION_ALIAS:
                effective_cap = "connected"
            else:
                effective_cap = profiles.viewer_capability(
                    conn, current_user_id=None, profile_user=user
                )

            if effective_cap == "limited":
                return RedirectResponse(
                    url=profiles.canonical_profile_url(username), status_code=303
                )

            return _render_readonly_activity_detail(
                request, conn, username, slug, owner_id, activity_id, tz=tz
            )

        # ------------------------------------------------------------------
        # Branches 2-4 — non-owner viewer.
        # ------------------------------------------------------------------
        else:
            if cap == "blocked":
                return HTMLResponse(status_code=404)

            if not profiles.can_view_activity_detail(
                conn, current_user_id=current_uid, profile_user=user
            ):
                # "limited" — non-connected visitor on a non-public account.
                return RedirectResponse(
                    url=profiles.canonical_profile_url(username), status_code=303
                )

            return _render_readonly_activity_detail(
                request,
                conn,
                username,
                slug,
                owner_id,
                activity_id,
                tz=tz,
                current_user_id=current_uid,
                profile_user=user,
            )

    # ------------------------------------------------------------------
    # Owner view continued (outside the `with` block so the connection is
    # closed before building the heavier context from services).
    # ------------------------------------------------------------------
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


# ---------------------------------------------------------------------------
# Entry comments — collapsed per-entry affordance + thread fragment
# ---------------------------------------------------------------------------


def _resolve_entry_for_comments(
    conn: Any, username: str, slug: str, entry_id: int, current_uid: int | None
) -> tuple[dict, int, int, dict] | HTMLResponse:
    """Shared lookup + visibility gate for both comment routes.

    Returns ``(user, owner_id, activity_id, entry)`` on success, or an
    ``HTMLResponse`` (404) the caller should return directly. Mirrors the
    branch order in ``public_activity``: unknown username/slug/entry, a
    cross-activity entry id, or a viewer who fails
    ``can_view_activity_detail`` (limited/blocked) all 404 here rather than
    leaking anything about the entry's existence — this is a fragment route,
    not a navigable page, so there's no profile to redirect back to.
    """
    user = profiles.get_public_user(conn, username)
    if user is None:
        return HTMLResponse(status_code=404)
    owner_id = int(user["id"])
    activity_id = profiles.resolve_activity_slug(conn, owner_id, slug)
    if activity_id is None:
        return HTMLResponse(status_code=404)

    if not profiles.can_view_activity_detail(conn, current_user_id=current_uid, profile_user=user):
        return HTMLResponse(status_code=404)

    try:
        entry = entries.get(owner_id, entry_id)
    except EntryNotFoundError:
        return HTMLResponse(status_code=404)
    if entry["activity_id"] != activity_id:
        return HTMLResponse(status_code=404)

    return user, owner_id, activity_id, entry


def _render_comment_thread(
    request: Request,
    conn: Any,
    *,
    username: str,
    slug: str,
    owner_id: int,
    activity_id: int,
    entry_id: int,
    current_uid: int | None,
    user: dict,
) -> HTMLResponse:
    """Build + render the comment-thread fragment for *entry_id*."""
    rows = comments_service.list_comments(conn, entry_id, viewer_id=current_uid)
    can_comment = profiles.can_comment_on_entry(
        conn, current_user_id=current_uid, profile_user=user, activity_id=activity_id
    )
    context = {
        "activity_id": activity_id,
        "username": username,
        "slug": slug,
        "entry_id": entry_id,
        "entry_owner_id": owner_id,
        "comments": rows,
        "can_comment": can_comment,
        "viewer_logged_in": current_uid is not None,
        "current_user_id": current_uid,
    }
    return templates.TemplateResponse(
        request=request,
        name="components/comment_thread.html.jinja2",
        context=context,
    )


@router.get(
    "/@{username}/{slug}/entries/{entry_id}/comments",
    response_class=HTMLResponse,
    response_model=None,
)
async def get_entry_comments(
    request: Request,
    username: str,
    slug: str,
    entry_id: int,
    session: Annotated[str | None, Cookie(alias=sessions.COOKIE_NAME)] = None,
) -> HTMLResponse:
    """Render the comment-thread fragment for *entry_id* (HTMX swap target).

    404s for an unknown username/slug/entry, a cross-activity entry id, or a
    viewer who fails ``can_view_activity_detail`` (limited/blocked) — same
    visibility authority the activity-detail route uses, never inlined. The
    composer only appears in the rendered markup when
    ``profiles.can_comment_on_entry`` is true for the current viewer; a
    logged-out viewer on an otherwise-visible entry gets the read-only list
    plus a "log in to comment" link.
    """
    current_uid = sessions.read_uid(session)
    with db.connect() as conn:
        conn.execute("BEGIN")
        resolved = _resolve_entry_for_comments(conn, username, slug, entry_id, current_uid)
        if isinstance(resolved, HTMLResponse):
            return resolved
        user, owner_id, activity_id, _entry = resolved
        return _render_comment_thread(
            request,
            conn,
            username=username,
            slug=slug,
            owner_id=owner_id,
            activity_id=activity_id,
            entry_id=entry_id,
            current_uid=current_uid,
            user=user,
        )


@router.post(
    "/@{username}/{slug}/entries/{entry_id}/comments",
    response_class=HTMLResponse,
    response_model=None,
)
async def post_entry_comment(
    request: Request,
    username: str,
    slug: str,
    entry_id: int,
    body: Annotated[str, Form()],
    session: Annotated[str | None, Cookie(alias=sessions.COOKIE_NAME)] = None,
) -> HTMLResponse:
    """Create a comment on *entry_id*, then return the refreshed thread fragment.

    Server-side gate, independent of anything the client sent: re-checks
    ``can_comment_on_entry`` (which itself requires a real session) before
    writing. An unauthorized POST — no session, a non-fellow on a private
    profile, a blocked viewer — gets 403, never a silent no-op and never a
    write. An empty/whitespace-only body is rejected the same way
    ``create_comment`` itself rejects it (422), so a tampered client can't
    bypass the textarea's ``required`` attribute either.
    """
    current_uid = sessions.read_uid(session)
    with db.connect() as conn:
        conn.execute("BEGIN")
        resolved = _resolve_entry_for_comments(conn, username, slug, entry_id, current_uid)
        if isinstance(resolved, HTMLResponse):
            return resolved
        user, owner_id, activity_id, _entry = resolved

        if not profiles.can_comment_on_entry(
            conn, current_user_id=current_uid, profile_user=user, activity_id=activity_id
        ):
            return HTMLResponse(status_code=403)

        try:
            comments_service.create_comment(conn, entry_id, author_id=current_uid, body=body)
        except ValueError:
            return HTMLResponse(status_code=422)

        return _render_comment_thread(
            request,
            conn,
            username=username,
            slug=slug,
            owner_id=owner_id,
            activity_id=activity_id,
            entry_id=entry_id,
            current_uid=current_uid,
            user=user,
        )


@router.post(
    "/@{username}/{slug}/entries/{entry_id}/comments/{comment_id}/delete",
    response_class=HTMLResponse,
    response_model=None,
)
async def delete_entry_comment(
    request: Request,
    username: str,
    slug: str,
    entry_id: int,
    comment_id: int,
    session: Annotated[str | None, Cookie(alias=sessions.COOKIE_NAME)] = None,
) -> HTMLResponse:
    """Soft-delete *comment_id*, then return the refreshed thread fragment.

    Restricted server-side to the comment's author or the entry's owner —
    ``soft_delete_comment`` itself raises ``CommentPermissionError`` for
    anyone else, which we map to 403 (never a silent no-op). A session is
    required (anonymous can't author or own anything); an unknown/already-
    deleted comment 404s.
    """
    current_uid = sessions.read_uid(session)
    if current_uid is None:
        return HTMLResponse(status_code=401)

    with db.connect() as conn:
        conn.execute("BEGIN")
        resolved = _resolve_entry_for_comments(conn, username, slug, entry_id, current_uid)
        if isinstance(resolved, HTMLResponse):
            return resolved
        user, owner_id, activity_id, _entry = resolved

        try:
            comments_service.soft_delete_comment(conn, comment_id, requester_id=current_uid)
        except CommentNotFoundError:
            return HTMLResponse(status_code=404)
        except CommentPermissionError:
            return HTMLResponse(status_code=403)

        return _render_comment_thread(
            request,
            conn,
            username=username,
            slug=slug,
            owner_id=owner_id,
            activity_id=activity_id,
            entry_id=entry_id,
            current_uid=current_uid,
            user=user,
        )
