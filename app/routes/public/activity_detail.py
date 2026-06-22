"""Public activity detail route (``/@{username}/{slug}``).

The slug route is unified: when the viewer is the profile's owner, it
renders the full owner-dashboard template (``activity_detail.html.jinja2``)
with all write affordances. For every other viewer that can see detail
(``connected``/``public``) it uses the read-only public template
(``web/public_activity.html.jinja2``); a ``limited`` viewer is
303-redirected back to the profile (no detail to leak), and a ``blocked``
viewer gets the same 404 a non-existent user would.

THE SINGLE VISIBILITY AUTHORITY
--------------------------------
This route drives its visibility decision through
``profiles.viewer_capability`` / ``profiles.can_view_activity_detail`` — the
sole, fail-closed authority (see ``app/services/profiles.py``). No handler
reads ``user["visibility"]`` directly; the owner's two-mode preview
(``?as=stranger`` / ``?as=connection``) re-derives the previewed capability
by calling ``viewer_capability`` with a substitute ``current_user_id`` (or a
literal ``"connected"`` override) rather than ever branching on the raw
column.

Business logic stays in ``app/services/``; the heavier render paths (owner
dashboard continuation, read-only public view) live in the internal
companion ``_activity_detail_handlers.py`` (route-structure rule, option 2 —
this file stays the thin dispatch + route declaration).

The entry-comment routes (``app/routes/public/comments.py``) are a separate
route group with their own visibility gate (``_resolve_entry_for_comments``);
the two modules share only the ``templates``/alias constants in
``_contexts.py``, no functions.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Cookie, Request
from fastapi.responses import HTMLResponse, RedirectResponse

from app.auth import sessions, users
from app.models import db
from app.routes.public._activity_detail_handlers import (
    _render_owner_activity_detail,
    _render_readonly_activity_detail,
)
from app.routes.public._contexts import _CONNECTION_ALIAS, _STRANGER_ALIASES
from app.routes.web import _build_card_context, _field_defs_for_activity
from app.services import profiles

router = APIRouter()


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
            # (inside the handler) so the merged calendar's per-entry comment
            # toggles render for the owner.
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
    # closed before building the heavier context from services) — delegated
    # to the internal companion module to keep this file under the 300-line
    # ceiling.
    # ------------------------------------------------------------------
    return _render_owner_activity_detail(
        request,
        username=username,
        slug=slug,
        owner_id=owner_id,
        activity_id=activity_id,
        user=user,
        card=card,
        field_defs=field_defs,
        has_match_list=has_match_list,
        can_comment=can_comment,
        tz=tz,
    )
