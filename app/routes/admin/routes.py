"""Admin dashboard, HTTP Basic Auth gated."""

from __future__ import annotations

import os
import secrets
from typing import Annotated

from fastapi import APIRouter, Depends, Form, HTTPException, Request, status
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.security import HTTPBasic, HTTPBasicCredentials

from app.auth.passwords import verify_password
from app.routes.admin import handlers as _admin_handlers

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


@router.get("/admin", dependencies=[Depends(_require_admin)])
async def admin_index(request: Request) -> RedirectResponse:
    """Redirect the legacy admin root to the monitor tab."""
    query = f"?{request.url.query}" if request.url.query else ""
    return RedirectResponse(url=f"/admin/monitor{query}", status_code=303)


@router.get("/admin/monitor", response_class=HTMLResponse, dependencies=[Depends(_require_admin)])
async def admin_monitor(request: Request) -> HTMLResponse:
    """Operator dashboard for visitor analytics and recent content."""
    return await _admin_handlers.monitor(request)


@router.get("/admin/users", response_class=HTMLResponse, dependencies=[Depends(_require_admin)])
async def admin_users(request: Request) -> HTMLResponse:
    """Operator dashboard for user and account monitoring."""
    return await _admin_handlers.users(request)


@router.get("/admin/users/{user_id}", response_class=HTMLResponse, dependencies=[Depends(_require_admin)])
async def admin_user_detail(request: Request, user_id: int) -> HTMLResponse:
    """Admin detail page for one user."""
    return await _admin_handlers.user_detail(request, user_id)


@router.post("/admin/users/{user_id}/edit", dependencies=[Depends(_require_admin)])
async def admin_edit_user(
    user_id: int,
    username: Annotated[str, Form()],
    email: Annotated[str | None, Form()] = None,
    password: Annotated[str | None, Form()] = None,
) -> RedirectResponse:
    """Edit a user's identity fields."""
    return await _admin_handlers.edit_user(
        user_id, username=username, email=email, password=password
    )


@router.post("/admin/users/{user_id}/delete", dependencies=[Depends(_require_admin)])
async def admin_delete_user(user_id: int) -> RedirectResponse:
    """Permanently delete a user's account access."""
    return await _admin_handlers.delete_user(user_id)


@router.post("/admin/users/{user_id}/visibility", dependencies=[Depends(_require_admin)])
async def admin_set_visibility(
    user_id: int,
    visibility: Annotated[str, Form()],
) -> RedirectResponse:
    """Set a user's visibility to public or private."""
    return await _admin_handlers.set_visibility(user_id, visibility=visibility)


@router.post("/admin/users/{user_id}/suspension", dependencies=[Depends(_require_admin)])
async def admin_set_suspension(
    user_id: int,
    suspended: Annotated[bool, Form()] = False,
) -> RedirectResponse:
    """Suspend or unsuspend a user."""
    return await _admin_handlers.set_suspension(user_id, suspended=suspended)


@router.post("/admin/users/{user_id}/entries/{entry_id}/edit", dependencies=[Depends(_require_admin)])
async def admin_edit_entry(
    user_id: int,
    entry_id: int,
    memo: Annotated[str, Form()] = "",
) -> RedirectResponse:
    """Edit a user-owned entry memo."""
    return await _admin_handlers.edit_entry(user_id, entry_id, memo=memo)


@router.post("/admin/users/{user_id}/entries/{entry_id}/visibility", dependencies=[Depends(_require_admin)])
async def admin_set_entry_visibility(
    user_id: int,
    entry_id: int,
    hidden: Annotated[bool, Form()] = False,
) -> RedirectResponse:
    """Hide or unhide a user-owned entry."""
    return await _admin_handlers.set_entry_visibility(user_id, entry_id, hidden=hidden)


@router.post("/admin/users/{user_id}/comments/{comment_id}/edit", dependencies=[Depends(_require_admin)])
async def admin_edit_comment(
    user_id: int,
    comment_id: int,
    body: Annotated[str, Form()],
) -> RedirectResponse:
    """Edit a related comment."""
    return await _admin_handlers.edit_comment(user_id, comment_id, body=body)


@router.post("/admin/users/{user_id}/comments/{comment_id}/visibility", dependencies=[Depends(_require_admin)])
async def admin_set_comment_visibility(
    user_id: int,
    comment_id: int,
    hidden: Annotated[bool, Form()] = False,
) -> RedirectResponse:
    """Hide or unhide a related comment."""
    return await _admin_handlers.set_comment_visibility(user_id, comment_id, hidden=hidden)


@router.post("/admin/users/{user_id}/plan", dependencies=[Depends(_require_admin)])
async def admin_set_user_plan(
    user_id: int,
    plan: Annotated[str, Form()],
) -> RedirectResponse:
    """Change a user's plan (for testing)."""
    return await _admin_handlers.set_user_plan(user_id, plan=plan)


@router.get("/admin/plans", response_class=HTMLResponse, dependencies=[Depends(_require_admin)])
async def admin_plans(request: Request) -> HTMLResponse:
    """Operator dashboard for plan configuration."""
    return await _admin_handlers.plans(request)


@router.post("/admin/plans/{plan}", dependencies=[Depends(_require_admin)])
async def admin_update_plan(
    plan: str,
    max_activities: Annotated[int, Form()],
    max_entries_per_date: Annotated[int, Form()],
    secret_activities: Annotated[bool, Form()] = False,
    price_monthly: Annotated[int | None, Form()] = None,
    price_yearly: Annotated[int | None, Form()] = None,
) -> RedirectResponse:
    """Update a plan's configuration."""
    return await _admin_handlers.update_plan(
        plan,
        max_activities=max_activities,
        max_entries_per_date=max_entries_per_date,
        secret_activities=secret_activities,
        price_monthly=price_monthly,
        price_yearly=price_yearly,
    )
