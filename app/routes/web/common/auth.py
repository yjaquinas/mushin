"""Session and navigation helpers shared by web routes."""

from __future__ import annotations

from typing import Any

from fastapi import Request
from fastapi.responses import RedirectResponse

from app.auth import sessions, users
from app.models import db
from app.services.social import notifications, profiles


def _current_user(session: str | None) -> dict[str, Any] | None:
    uid = sessions.read_uid(session)
    return None if uid is None else users.get_user(uid)


def _home_url_for(user: dict[str, Any] | None) -> str:
    if user is None:
        return "/"
    return profiles.canonical_profile_url(user["username"]) if user.get("username") else "/home"


def _home_url_context(request: Request) -> dict[str, int | str]:
    user = _current_user(request.cookies.get(sessions.COOKIE_NAME))
    context: dict[str, int | str] = {"home_url": _home_url_for(user), "unseen_notifications": 0}
    if user is None:
        return context
    with db.connect() as conn:
        context["unseen_notifications"] = notifications.unseen_count(conn, int(user["id"]))
    return context


def consent_gate_redirect(user: dict[str, Any]) -> RedirectResponse | None:
    """No-op: consent gate removed (default visibility is public)."""
    return None
