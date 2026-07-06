"""Handler bodies for data import/export routes."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import Any

from fastapi import Request, UploadFile
from fastapi.responses import HTMLResponse, RedirectResponse, Response

from app import ui_strings
from app.auth import sessions, users
from app.routes.web.common import _home_url_for, templates
from app.services.portability import portability

MAX_IMPORT_BYTES = 2 * 1024 * 1024
MAX_ENTRY_IMPORT_BYTES = 2 * 1024 * 1024


def _resolve_user(session: str | None) -> dict[str, Any] | None:
    uid = sessions.read_uid(session)
    return users.get_user(uid) if uid is not None else None


def _timestamped_export_filename(prefix: str) -> str:
    timestamp = datetime.now(UTC).strftime("%Y%m%d-%H%M%S")
    return f"{prefix}-{timestamp}.json"


async def export_data_body(session: str | None) -> Response:
    user = _resolve_user(session)
    if user is None:
        return RedirectResponse(url="/", status_code=303)

    snapshot = portability.export_data(int(user["id"]))
    body = json.dumps(snapshot, ensure_ascii=False, indent=2)
    return Response(
        content=body,
        media_type="application/json",
        headers={
            "Content-Disposition": f'attachment; filename="{_timestamped_export_filename("mushin-export")}"'
        },
    )


async def import_data_body(
    request: Request, file: UploadFile, session: str | None
) -> Response:
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
    return templates.TemplateResponse(
        request=request,
        name="components/settings/import_data_dialog.html.jinja2",
        context={"import_error": message, "open_on_error": True},
    )


async def export_entries_body(session: str | None) -> Response:
    user = _resolve_user(session)
    if user is None:
        return RedirectResponse(url="/", status_code=303)

    snapshot = portability.export_entries(int(user["id"]))
    body = json.dumps(snapshot, ensure_ascii=False, indent=2)
    return Response(
        content=body,
        media_type="application/json",
        headers={
            "Content-Disposition": f'attachment; filename="{_timestamped_export_filename("mushin-entries")}"'
        },
    )


async def import_entries_body(
    request: Request, file: UploadFile, session: str | None
) -> Response:
    user = _resolve_user(session)
    if user is None:
        return RedirectResponse(url="/", status_code=303)
    owner_id = int(user["id"])

    filename = file.filename or ""
    content_type = file.content_type or ""
    if content_type != "application/json" or not filename.lower().endswith(".json"):
        return _entry_import_error_response(
            request, ui_strings.IMPORT_ENTRIES_ERROR_INVALID_FILE
        )

    body = await file.read(MAX_ENTRY_IMPORT_BYTES + 1)
    if len(body) > MAX_ENTRY_IMPORT_BYTES:
        return _entry_import_error_response(
            request, ui_strings.IMPORT_ENTRIES_ERROR_TOO_LARGE
        )

    try:
        payload = json.loads(body)
    except json.JSONDecodeError:
        return _entry_import_error_response(
            request, ui_strings.IMPORT_ENTRIES_ERROR_INVALID_FILE
        )

    try:
        summary = portability.import_entries(owner_id, payload)
    except portability.EntryImportError as exc:
        message = ui_strings.IMPORT_ENTRIES_ERROR_VALIDATION.format(reason=str(exc))
        return _entry_import_error_response(request, message)

    return _entry_import_success_response(request, summary)


def _entry_import_error_response(request: Request, message: str) -> HTMLResponse:
    return templates.TemplateResponse(
        request=request,
        name="components/settings/entry_import_dialog.html.jinja2",
        context={"import_error": message, "open_on_error": True},
    )


def _entry_import_success_response(request: Request, summary: dict[str, int]) -> HTMLResponse:
    return templates.TemplateResponse(
        request=request,
        name="components/settings/entry_import_dialog.html.jinja2",
        context={
            "import_success": summary,
            "open_on_error": True,
        },
    )
