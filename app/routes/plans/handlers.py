"""Handler for the public /plans page — redirects to /settings/plans."""

from __future__ import annotations

from typing import Any

from fastapi import Request
from fastapi.responses import RedirectResponse


async def plans_page(request: Request, user: dict[str, Any] | None) -> RedirectResponse:
    """Redirect /plans to /settings/plans."""
    return RedirectResponse(url="/settings/plans", status_code=302)
