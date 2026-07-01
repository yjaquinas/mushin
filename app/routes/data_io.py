"""Data-portability routes for Mushin ("carry over your data").

Thin handlers only — the actual snapshot assembly/replacement lives in
``app/services/portability.py``. This router owns the download endpoint and
the "replace all my data" upload endpoint, both reached via footer links.
"""

from __future__ import annotations

import json
from typing import Annotated, Any

from fastapi import APIRouter, Cookie, File, Request, UploadFile
from fastapi.responses import HTMLResponse, RedirectResponse, Response

from app.auth import sessions, users
from app.routes.web._shared import _home_url_for, templates
from app.services import portability

router = APIRouter()

#: Reject uploads larger than this. A personal activity-log export is tiny;
#: this is a sanity bound against hostile/oversized uploads, read as
#: ``MAX_IMPORT_BYTES + 1`` so we can detect "too large" without buffering an
#: unbounded file.
MAX_IMPORT_BYTES = 2 * 1024 * 1024


def _resolve_user(session: str | None) -> dict[str, Any] | None:
    """Resolve the current user from the session cookie (guest or real)."""
    uid = sessions.read_uid(session)
    return users.get_user(uid) if uid is not None else None


@router.get("/export")
async def export_data(
    session: Annotated[str | None, Cookie(alias=sessions.COOKIE_NAME)] = None,
) -> Response:
    """Download the current user's full data as a JSON file.

    Works for guest accounts too — guests carry the same signed session
    cookie as real accounts. With no session, redirects to ``/`` (matching
    the unauthenticated pattern used throughout ``app/routes/web.py``).
    """
    user = _resolve_user(session)
    if user is None:
        return RedirectResponse(url="/", status_code=303)

    snapshot = portability.export_data(int(user["id"]))
    body = json.dumps(snapshot, ensure_ascii=False, indent=2)
    return Response(
        content=body,
        media_type="application/json",
        headers={"Content-Disposition": 'attachment; filename="mushin-export.json"'},
    )


@router.post("/import")
async def import_data(
    request: Request,
    file: Annotated[UploadFile, File()],
    session: Annotated[str | None, Cookie(alias=sessions.COOKIE_NAME)] = None,
) -> Response:
    """Replace the current user's data with the contents of an uploaded export file.

    Accepts a single ``.json`` / ``application/json`` file (no archives), caps
    it at :data:`MAX_IMPORT_BYTES`, and hands the parsed payload to
    ``portability.import_data``. On success, ``HX-Redirect`` to the user's
    home/profile URL forces a full reload reflecting the replaced data. On any
    failure, the import dialog fragment is re-rendered with an inline error.
    """
    user = _resolve_user(session)
    if user is None:
        return RedirectResponse(url="/", status_code=303)
    owner_id = int(user["id"])

    filename = file.filename or ""
    content_type = file.content_type or ""
    if content_type != "application/json" or not filename.lower().endswith(".json"):
        return _import_error_response(request, ui_strings.IMPORT_DATA_ERROR_INVALID_FILE)

    body = await file.read(MAX_IMPORT_BYTES + 1)
    if len(body) > MAX_IMPORT_BYTES:
        return _import_error_response(request, ui_strings.IMPORT_DATA_ERROR_TOO_LARGE)

    try:
        payload = json.loads(body)
    except json.JSONDecodeError:
        return _import_error_response(request, ui_strings.IMPORT_DATA_ERROR_INVALID_FILE)

    try:
        portability.import_data(owner_id, payload)
    except portability.ImportValidationError as exc:
        message = ui_strings.IMPORT_DATA_ERROR_VALIDATION.format(reason=str(exc))
        return _import_error_response(request, message)

    return Response(status_code=200, headers={"HX-Redirect": _home_url_for(user)})


def _import_error_response(request: Request, message: str) -> HTMLResponse:
    """Re-render the import dialog fragment with *message* shown inline.

    Status 200, not 400: this fragment IS the error UI, swapped in place by
    htmx. htmx 2's default `responseHandling` only swaps 2xx responses, so a
    4xx here would leave the dialog showing its stale pre-submit content with
    the error silently dropped.
    """
    return templates.TemplateResponse(
        request=request,
        name="components/import_data_dialog.html.jinja2",
        context={"import_error": message, "open_on_error": True},
    )
