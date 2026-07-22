"""Read-only social profile handler body and context builder."""

from __future__ import annotations

from fastapi import Request
from fastapi.responses import HTMLResponse

from app.auth import users as auth_users
from app.models import db
from app.routes.public.profile._contexts import read_only_profile_context
from app.routes.web.common import templates
from app.routes.web.common import ui_strings as strings
from app.routes.web.common.flash import _clear_flash, _read_flash
from app.services.social import profiles
from app.ui_strings import META_DESCRIPTION_PROFILE


async def social_profile(request: Request, username: str, current_uid: int | None) -> HTMLResponse:
    """Render another user's profile within the social tab."""
    with db.connect() as conn:
        conn.execute("BEGIN")
        profile_user = profiles.get_public_user(conn, username)
        if profile_user is None:
            return HTMLResponse(status_code=404)

        owner_id = int(profile_user["id"])
        cap = profiles.viewer_capability(
            conn, current_user_id=current_uid, profile_user=profile_user
        )
        if cap == "owner":
            from fastapi.responses import RedirectResponse

            return RedirectResponse(url="/home", status_code=303)
        if cap == "blocked":
            return HTMLResponse(status_code=404)

        context = read_only_profile_context(
            conn,
            username,
            owner_id,
            cap=cap,
            tz=auth_users.get_user_timezone(owner_id),
            current_uid=current_uid,
            visibility=profile_user["visibility"],
            bio=profile_user.get("bio", "") if cap != "limited" else "",
        )
        context.update(
            flash_message=_read_flash(request),
            current_page="social",
            page_title=username,
            profile_url=profiles.canonical_profile_url(username),
            share_label=f"@{username}",
            share_copied_text=f"Link to @{username} copied",
            share_failed_text="Couldn't share the link.",
            meta_robots="noindex, nofollow",
            meta_description=META_DESCRIPTION_PROFILE.format(username=username),
            og_title=f"{username} · {strings.APP_NAME}",
            og_description=META_DESCRIPTION_PROFILE.format(username=username),
            og_type="profile",
        )

    response = templates.TemplateResponse(
        request=request, name="web/social/public_profile.html.jinja2", context=context
    )
    _clear_flash(response)
    return response
