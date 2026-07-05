"""Data-portability routes for Mushin."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Cookie, File, Request, UploadFile
from fastapi.responses import Response

from app.auth import sessions
from app.routes.data_io import handlers

router = APIRouter()


@router.get("/export")
async def export_data(
    session: Annotated[str | None, Cookie(alias=sessions.COOKIE_NAME)] = None,
) -> Response:
    return await handlers.export_data_body(session)


@router.post("/import")
async def import_data(
    request: Request,
    file: Annotated[UploadFile, File()],
    session: Annotated[str | None, Cookie(alias=sessions.COOKIE_NAME)] = None,
) -> Response:
    return await handlers.import_data_body(request, file, session)


@router.get("/export-entries")
async def export_entries(
    session: Annotated[str | None, Cookie(alias=sessions.COOKIE_NAME)] = None,
) -> Response:
    return await handlers.export_entries_body(session)


@router.post("/import-entries")
async def import_entries(
    request: Request,
    file: Annotated[UploadFile, File()],
    session: Annotated[str | None, Cookie(alias=sessions.COOKIE_NAME)] = None,
) -> Response:
    return await handlers.import_entries_body(request, file, session)
