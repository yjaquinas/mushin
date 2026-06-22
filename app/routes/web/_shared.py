"""Request-coupled helpers shared across the ``web`` surface's route groups.

Session resolution
-------------------
This module resolves the current user the same way ``app/auth/routes.py``
does (via the signed ``mushin_session`` cookie + ``app.auth.users``), but never
*creates* anything on a bare GET — guest creation stays an explicit
``POST /auth/guest`` the entry screen calls on the user's first tap, per the
bot-guard rule.

Also home to the shared ``Jinja2Templates`` instance every leaf module in
this package (and ``app/routes/public/``, via its own
``app/routes/public/_contexts.py``) renders through, so context processors
and template globals stay identical across surfaces.
"""

from __future__ import annotations

import os
from datetime import datetime
from typing import Any

from fastapi import Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from itsdangerous import BadSignature, URLSafeSerializer

from app import ui_strings
from app.auth import sessions, users
from app.services import profiles

# Cookie holding the user's explicit theme choice: "light" | "dark".
# Missing/invalid values default to "light" (no OS/prefers-color-scheme
# detection — first visit is always light until the user toggles).
THEME_COOKIE = "mushin_theme"
THEME_VALUES = ("light", "dark")
THEME_CYCLE = {"light": "dark", "dark": "light"}

# ---------------------------------------------------------------------------
# One-shot flash messages
# ---------------------------------------------------------------------------
#
# A minimal flash mechanism: a short-lived signed cookie set on a redirect
# response, read exactly once by the next full-page render, then explicitly
# deleted on that same response so a refresh or back-button visit never
# replays it. Signed (not encrypted) with itsdangerous, same library and
# pattern as app/auth/sessions.py, but its own salt namespace — a flash
# value can never be replayed as a session token or vice versa. The payload
# is a bare key (e.g. "visibility_public"), never personal data beyond the
# state being confirmed.
FLASH_COOKIE = "mushin_flash"
_FLASH_SALT = "mushin.flash.v1"
_FLASH_MAX_AGE = 30  # one page load's worth of validity; it's read-once anyway

_FLASH_MESSAGES: dict[str, str] = {
    "visibility_public": ui_strings.HOME_FLASH_VISIBILITY_PUBLIC,
    "visibility_private": ui_strings.HOME_FLASH_VISIBILITY_PRIVATE,
}


def _flash_serializer() -> URLSafeSerializer:
    secret = os.getenv("SESSION_SECRET", "")
    return URLSafeSerializer(secret, salt=_FLASH_SALT)


def _set_flash(response: RedirectResponse, key: str) -> None:
    """Attach a one-shot flash cookie carrying *key* to *response*.

    *key* must be one of ``_FLASH_MESSAGES`` — an internal identifier, never
    free text, so the cookie can never carry personal data.
    """
    value = _flash_serializer().dumps({"key": key})
    response.set_cookie(
        key=FLASH_COOKIE,
        value=value,
        max_age=_FLASH_MAX_AGE,
        httponly=True,
        secure=True,
        samesite="lax",
        path="/",
    )


def _read_flash(request: Request) -> str | None:
    """Return the flash message text for the current request, or ``None``.

    Does not clear the cookie — pair with ``_clear_flash`` on the response
    that renders the message so it never reappears on a later request.
    """
    raw = request.cookies.get(FLASH_COOKIE)
    if not raw:
        return None
    try:
        data = _flash_serializer().loads(raw)
    except BadSignature:
        return None
    key = data.get("key") if isinstance(data, dict) else None
    if not isinstance(key, str):
        return None
    return _FLASH_MESSAGES.get(key)


def _clear_flash(response: HTMLResponse) -> None:
    """Delete the flash cookie so a one-shot message is never read twice."""
    response.delete_cookie(key=FLASH_COOKIE, path="/", secure=True, httponly=True, samesite="lax")


def _theme_from_cookie(value: str | None) -> str:
    """Normalize the ``mushin_theme`` cookie to a known value, defaulting to "light"."""
    if value in THEME_VALUES:
        return value
    return "light"


def _theme_context(request: Request) -> dict[str, Any]:
    """Context processor: exposes ``theme`` to every template render."""
    return {"theme": _theme_from_cookie(request.cookies.get(THEME_COOKIE))}


def _home_url_for(user: dict[str, Any] | None) -> str:
    """Where "go to my home/profile" should point for *user* (or an anonymous visitor)."""
    if user is None:
        return "/"
    username = user.get("username")
    if username:
        return profiles.canonical_profile_url(username)
    return "/home"


def _home_url_context(request: Request) -> dict[str, Any]:
    """Context processor: exposes ``home_url`` to every template render."""
    session = request.cookies.get(sessions.COOKIE_NAME)
    user = _current_user(session)
    return {"home_url": _home_url_for(user)}


templates = Jinja2Templates(
    directory="app/templates", context_processors=[_theme_context, _home_url_context]
)
# Centralized copy is exposed to every template as `strings` — templates
# never hardcode user-facing text (see .claude/skills/copy-patterns).
templates.env.globals["strings"] = ui_strings


def _format_entry_time(occurred_at: str) -> str:
    """Format the time portion of an ISO8601 ``occurred_at`` string as 12h AM/PM.

    Input: ``"2026-06-16T14:30:00"`` → output: ``"2:30 PM"``.
    Falls back to an empty string on any parse error.
    """
    try:
        dt = datetime.fromisoformat(occurred_at)
        hour = dt.hour
        minute = dt.minute
        period = "AM" if hour < 12 else "PM"
        hour12 = hour % 12 or 12
        return f"{hour12}:{minute:02d} {period}"
    except (ValueError, AttributeError):
        return ""


templates.env.filters["format_entry_time"] = _format_entry_time


# ---------------------------------------------------------------------------
# Session helpers
# ---------------------------------------------------------------------------


def _current_user(session: str | None) -> dict[str, Any] | None:
    """Resolve the session cookie to a user row, or ``None`` if logged out.

    Never mints a guest — that only happens via the explicit
    ``POST /auth/guest`` the entry screen's "그냥 시작하기" button calls.
    """
    uid = sessions.read_uid(session)
    if uid is None:
        return None
    return users.get_user(uid)


def consent_gate_redirect(user: dict[str, Any]) -> RedirectResponse | None:
    """One-time consent gating for a logged-in owner, or ``None`` to proceed.

    Two ordered, fail-once gates for non-guest accounts (guests have no public
    profile and are never gated):

    1. **First-run visibility consent** — ``consent_seen_at IS NULL`` → send to
       ``/welcome-sharing``. This takes precedence so a brand-new account picks
       a visibility under the current three-tier copy.
    2. **Private redefinition re-consent** — a pre-existing private account
       (``visibility='private' AND private_redefinition_seen_at IS NULL``) →
       send to ``/visibility-update`` once.

    New users never hit gate 2: ``users.set_visibility_consent`` (the
    welcome-sharing / account-settings write path) stamps
    ``private_redefinition_seen_at`` at the same moment it stamps
    ``consent_seen_at``, so by the time they clear gate 1 the redefinition flag
    is already set. Gate 2 therefore fires only for accounts that chose
    ``private`` under the old "nothing shown" copy. Shared verbatim by the owner
    branch of ``GET /@{username}`` in ``app/routes/public/profile.py``.
    """
    if user["auth_provider"] == "guest":
        return None
    if user["consent_seen_at"] is None:
        return RedirectResponse(url="/welcome-sharing", status_code=303)
    if user["visibility"] == "private" and user["private_redefinition_seen_at"] is None:
        return RedirectResponse(url="/visibility-update", status_code=303)
    return None
