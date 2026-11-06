"""Initial entry orchestration, shared by /, /login, and /home."""

from fastapi import Request
from fastapi.responses import HTMLResponse, RedirectResponse

from app.routes.web.common import _current_user
from app.routes.web.home._bootstrap import bootstrap_response
from app.routes.web.home.handlers import (
    home_gate_response,
    login_page_response,
    redirect_logged_in_home,
)


def entry_response(
    request: Request, session: str | None, next_path: str | None = None, *, home: bool = False
) -> HTMLResponse | RedirectResponse:
    shell = bootstrap_response(request)
    if shell is not None:
        return shell
    user = _current_user(session)
    if home:
        response = home_gate_response(user)
        if response is None:
            response = redirect_logged_in_home(user)
    else:
        response = login_page_response(request, user, next_path)
    response.headers["Cache-Control"] = "private, no-store"
    return response
