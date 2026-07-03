"""Auth routes for Mushin.

Simple username/password signup + login. No OAuth, no guests.
"""

from __future__ import annotations

import re
import secrets
import unicodedata
from typing import Annotated

import structlog
from fastapi import APIRouter, Cookie, Form, HTTPException, Request, Response
from fastapi.responses import JSONResponse, RedirectResponse

from app.auth import oauth, passwords, sessions, users
from app.services import profiles

log = structlog.get_logger()

router = APIRouter(prefix="/auth", tags=["auth"])

PRIVACY_POLICY_URL = "/privacy"

CONSENT_REQUIRED_MESSAGE = (
    f"Please agree to how we collect and use your data to continue. "
    f"(Privacy policy: {PRIVACY_POLICY_URL})"
)


_USERNAME_RE = re.compile(r"^[a-z0-9_]{3,20}$")
_USERNAME_ERROR = (
    "Username must be 3-20 characters: lowercase letters, numbers, "
    "and underscores only."
)


def _current_uid(cookie_value: str | None) -> int | None:
    return sessions.read_uid(cookie_value)


def _set_session(response: Response, user_id: int) -> None:
    response.set_cookie(value=sessions.sign_uid(user_id), **sessions.cookie_kwargs())


def _require_consent(consent: bool) -> None:
    if not consent:
        raise HTTPException(status_code=400, detail=CONSENT_REQUIRED_MESSAGE)


def _normalize_username(username: str) -> str:
    normalized = unicodedata.normalize("NFKC", username.strip()).casefold()
    if not _USERNAME_RE.match(normalized):
        raise HTTPException(status_code=400, detail=_USERNAME_ERROR)
    return normalized


# ---------------------------------------------------------------------------
# Signup
# ---------------------------------------------------------------------------


@router.post("/signup")
async def signup(
    response: Response,
    username: Annotated[str, Form()],
    password: Annotated[str, Form()],
    email: Annotated[str | None, Form()] = None,
    consent: Annotated[bool, Form()] = False,
) -> JSONResponse:
    """Create a new account with username + password."""
    _require_consent(consent)

    normalized = _normalize_username(username)

    if len(password) < 8:
        raise HTTPException(status_code=400, detail="Password must be at least 8 characters.")

    try:
        pw_hash = passwords.hash_password(password)
        user = users.create_user(normalized, pw_hash, email)
    except users.IdentityTakenError:
        detail = f"Username is already taken."
        if email:
            try:
                users.create_user("x", "x", email)
            except users.IdentityTakenError:
                detail = "Email is already taken."
        raise HTTPException(status_code=409, detail=detail)

    resp = JSONResponse({"user_id": user["id"], "redirect_url": f"/@{normalized}"})
    _set_session(resp, user["id"])
    log.info("auth.signup", user_id=user["id"])
    return resp


# ---------------------------------------------------------------------------
# Login
# ---------------------------------------------------------------------------


@router.post("/login")
async def login(
    response: Response,
    username: Annotated[str, Form()],
    password: Annotated[str, Form()],
) -> JSONResponse:
    """Authenticate with username + password."""
    normalized = _normalize_username(username)
    user = users.authenticate(normalized, password)

    if user is None:
        raise HTTPException(status_code=401, detail="Incorrect username or password.")

    if user["suspended_at"] is not None:
        raise HTTPException(status_code=401, detail="Account is suspended.")

    resp = JSONResponse({"user_id": user["id"], "redirect_url": f"/@{normalized}"})
    _set_session(resp, user["id"])
    log.info("auth.login", user_id=user["id"])
    return resp


# ---------------------------------------------------------------------------
# Logout / Delete
# ---------------------------------------------------------------------------


@router.post("/delete")
async def delete_account(
    session: Annotated[str | None, Cookie(alias=sessions.COOKIE_NAME)] = None,
) -> Response:
    """Delete current account access, then log out."""
    current = _current_uid(session)
    if current is None or users.get_user(current) is None:
        raise HTTPException(status_code=401, detail="no active session")

    users.delete_user(current)
    resp = RedirectResponse(url="/", status_code=303)
    resp.delete_cookie(key=sessions.COOKIE_NAME, path="/")
    log.info("auth.account.deleted", user_id=current)
    return resp


@router.post("/logout")
async def logout() -> Response:
    """Clear the session cookie."""
    resp = JSONResponse({"ok": True})
    resp.delete_cookie(key=sessions.COOKIE_NAME, path="/")
    return resp


# ---------------------------------------------------------------------------
# Session inspection
# ---------------------------------------------------------------------------


@router.get("/me")
async def whoami(
    request: Request,
    session: Annotated[str | None, Cookie(alias=sessions.COOKIE_NAME)] = None,
) -> JSONResponse:
    """Return the current user's identity summary."""
    current = _current_uid(session)
    if current is None:
        return JSONResponse({"user_id": None})
    user = users.get_user(current)
    if user is None:
        return JSONResponse({"user_id": None})
    return JSONResponse(
        {
            "user_id": user["id"],
            "username": user["username"],
        }
    )
