"""Session and navigation helpers shared by web routes."""

from __future__ import annotations

from typing import Any

from fastapi import Request
from fastapi.responses import RedirectResponse

from app.auth import sessions, users
from app.services import profiles


def _current_user(session: str | None) -> dict[str, Any] | None:
    uid = sessions.read_uid(session)
    return None if uid is None else users.get_user(uid)


def _home_url_for(user: dict[str, Any] | None) -> str:
    if user is None:
        return "/"
    return profiles.canonical_profile_url(user["username"]) if user.get("username") else "/home"


def _home_url_context(request: Request) -> dict[str, str]:
    return {"home_url": _home_url_for(_current_user(request.cookies.get(sessions.COOKIE_NAME)))}


def consent_gate_redirect(user: dict[str, Any]) -> RedirectResponse | None:
    if user["auth_provider"] == "guest":
        return None
    if user["consent_seen_at"] is None:
        return RedirectResponse(url="/welcome-sharing", status_code=303)
    if user["visibility"] == "private" and user["private_redefinition_seen_at"] is None:
        return RedirectResponse(url="/visibility-update", status_code=303)
    return None
