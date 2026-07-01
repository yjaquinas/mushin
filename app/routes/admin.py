"""Admin dashboard — placeholder, HTTP Basic Auth gated.

No admin features yet. This is the auth gate and a landing page for future
operator tooling. Credentials come from the environment (``ADMIN_USERNAME``,
``ADMIN_PASSWORD_HASH``) — see ``.env.example`` for how to generate a hash.
Unset or wrong credentials always 401; there is no bypass.
"""

from __future__ import annotations

import os
import secrets
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import HTMLResponse
from fastapi.security import HTTPBasic, HTTPBasicCredentials

from app.auth.passwords import verify_password
from app.routes.web._shared import templates

router = APIRouter()

_security = HTTPBasic()


def _require_admin(credentials: Annotated[HTTPBasicCredentials, Depends(_security)]) -> None:
    """Verify HTTP Basic credentials against ``ADMIN_USERNAME``/``ADMIN_PASSWORD_HASH``.

    Both checks always run (never short-circuited) so a wrong username
    doesn't skip the password hash comparison — avoids a timing
    side-channel that could otherwise leak whether the username alone was
    correct. An unset ``ADMIN_PASSWORD_HASH`` fails closed: ``verify_password``
    returns ``False`` for a missing hash rather than raising or matching.
    """
    expected_username = os.getenv("ADMIN_USERNAME", "")
    expected_hash = os.getenv("ADMIN_PASSWORD_HASH", "")
    username_ok = secrets.compare_digest(credentials.username, expected_username)
    password_ok = verify_password(expected_hash, credentials.password)
    if not (username_ok and password_ok):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid admin credentials",
            headers={"WWW-Authenticate": "Basic"},
        )


@router.get("/admin", response_class=HTMLResponse, dependencies=[Depends(_require_admin)])
async def admin_dashboard(request: Request) -> HTMLResponse:
    """Placeholder admin dashboard. No features yet."""
    return templates.TemplateResponse(
        request=request,
        name="admin/dashboard.html.jinja2",
        context={},
    )
