"""Public profile route (``/@{username}``).

``/@{username}`` is the unified profile route: when the viewer is the
profile's owner (session matches the profile user id), it renders the same
owner-dashboard context/template ``GET /home`` does (write affordances,
``web/home.html.jinja2``). For every other viewer it uses the read-only
public template (``web/public_profile.html.jinja2``) at one of two read
states — full (``connected``/``public``) or the character-sheet-only
``limited`` view.

THE SINGLE VISIBILITY AUTHORITY
--------------------------------
This route drives every visibility decision through
``profiles.viewer_capability`` — the sole, fail-closed authority (see
``app/services/profiles.py``). The handler never reads ``user["visibility"]``
directly.

Session handling: the route reads the ``mushin_session`` cookie via
``app.auth.sessions.read_uid`` and delegates the owner-vs-visitor branch to
``profiles.is_owner_viewing`` — a pure, fail-closed helper. No write actions
ever happen in this module; the owner view merely displays the same
dashboard the private route would.

Business logic stays in ``app/services/``; this module is thin handlers +
the same context-assembly helpers ``app/routes/web.py`` exports.
"""

from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Cookie, Request
from fastapi.responses import HTMLResponse, RedirectResponse

from app.auth import sessions, users
from app.models import db
from app.routes.public._contexts import templates
from app.routes.web import (
    _build_card_context,
    _build_fellows_context,
    _build_home_context,
    _clear_flash,
    _home_url_for,
    _list_activities,
    _read_flash,
    consent_gate_redirect,
)
from app.services import connections, profiles

router = APIRouter()


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
    activities = _list_activities(conn, owner_id)
    cards = [_build_card_context(conn, owner_id, row, tz=tz, linked=linked) for row in activities]
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

      1. ``"owner"`` → owner dashboard (same context/template ``GET /home``
         renders), including the one-time visibility-consent redirect for
         non-guest accounts that haven't seen it yet.
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

        if cap == "owner":
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
            context["flash_message"] = _read_flash(request)
            context["current_page"] = "logs"
            context["page_title"] = username
            context["profile_url"] = profiles.canonical_profile_url(username)
            context["show_back"] = False
            response = templates.TemplateResponse(
                request=request,
                name="web/home.html.jinja2",
                context=context,
            )
            _clear_flash(response)
            return response

        if cap == "blocked":
            return HTMLResponse(status_code=404)

        tz = users.get_user_timezone(owner_id)
        context = _read_only_profile_context(
            conn, username, owner_id, cap=cap, tz=tz, current_uid=current_uid
        )
        context["current_page"] = "logs"
        context["page_title"] = username
        context["profile_url"] = profiles.canonical_profile_url(username)
        context["show_back"] = False
        context["back_url"] = "/"

    return templates.TemplateResponse(
        request=request,
        name="web/public_profile.html.jinja2",
        context=context,
    )
